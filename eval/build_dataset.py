#!/usr/bin/env python3
"""
build_dataset.py — Generate the ground truth eval dataset from confirmed Supabase data.

HOW IT WORKS
------------
Every time you confirmed an extraction in the app, iStatis wrote two things to Supabase:
  1. document_extractions row — the raw GPT-4o output (what we are testing)
  2. transactions + transaction_line_items rows — what you verified as correct (ground truth)

This script pulls both, compares them, and produces a structured JSON file that the
eval runner (next script) will use to score future extractions.

KEY CONCEPTS
------------
- Ground truth: the correct answer for each test case (from your confirmed transactions)
- had_edits: True if you changed anything during review — these cases are the most
  valuable because they represent known model failures
- Coverage: how many cases per document type — you want balance across all five types

RUN
---
  cd istatis-papers
  source venv/Scripts/activate   (Windows) or source venv/bin/activate (Mac/Linux)
  python eval/build_dataset.py

OUTPUT
------
  eval/dataset.json  — the ground truth file used by the eval runner
  eval/coverage.txt  — quick summary of dataset balance
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Make sure we can import database.py from the parent directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from database import supabase

TENANT_ID = "00000000-0000-0000-0000-000000000001"
OUTPUT_FILE = Path(__file__).parent / "dataset.json"
COVERAGE_FILE = Path(__file__).parent / "coverage.txt"

# Document types the system handles — we track coverage across all five
DOC_TYPES = ["sales_slip", "price_list", "distribution_record", "account_ledger",
             "calculation_note", "unknown"]


def fetch_approved_extractions():
    """
    Pull all approved extractions with their confirmed transaction data.
    Returns a list of dicts, each with extraction + transaction + party + line items.
    """
    print("Fetching approved extractions from Supabase...")

    # Step 1: get all approved extractions for our tenant
    extractions = (
        supabase.table("document_extractions")
        .select("id, image_filename, document_type, overall_confidence, "
                "raw_extraction, created_at, has_warnings, low_confidence_fields")
        .eq("tenant_id", TENANT_ID)
        .eq("status", "approved")
        .order("created_at", desc=False)
        .execute()
    )

    if not extractions.data:
        print("No approved extractions found. Import and confirm some documents first.")
        sys.exit(0)

    print(f"Found {len(extractions.data)} approved extractions.")

    # Step 2: for each extraction, fetch the confirmed transaction + party + line items
    cases = []
    for ext in extractions.data:
        extraction_id = ext["id"]

        # Get the transaction that was created from this extraction
        tx_result = (
            supabase.table("transactions")
            .select("id, transaction_date, document_type, transaction_type, "
                    "total_amount, notes, created_at, "
                    "parties(id, name_roman, name_urdu)")
            .eq("extraction_id", extraction_id)
            .eq("tenant_id", TENANT_ID)
            .limit(1)
            .execute()
        )

        if not tx_result.data:
            # Extraction was approved but no transaction found — skip
            print(f"  Skipping {extraction_id[:8]}... (no linked transaction)")
            continue

        tx = tx_result.data[0]
        party = tx.get("parties") or {}

        # Get line items for this transaction
        items_result = (
            supabase.table("transaction_line_items")
            .select("product_code, description, quantity, unit_price, amount, confidence, notes")
            .eq("transaction_id", tx["id"])
            .execute()
        )

        line_items = [
            {
                "product_code": item.get("product_code"),
                "description": item.get("description"),
                "quantity": item.get("quantity"),
                "unit_price": item.get("unit_price"),
                "amount": item.get("amount"),
                # confidence is stored from the extraction — useful for calibration evals
                "confidence": item.get("confidence"),
            }
            for item in (items_result.data or [])
        ]

        # Build the ground truth expected values
        expected = {
            "document_type": tx.get("document_type") or ext.get("document_type"),
            "date": tx.get("transaction_date"),   # ISO format from DB
            "party_name": party.get("name_roman"),
            "party_name_urdu": party.get("name_urdu"),
            "grand_total": tx.get("total_amount"),
            "transaction_type": tx.get("transaction_type"),
            "line_items": line_items,
        }

        # Compare ground truth to raw extraction to detect edits
        raw = ext.get("raw_extraction") or {}
        had_edits = _detect_edits(raw, expected)

        case = {
            # Unique ID for this test case — use first 8 chars of extraction UUID
            "id": f"tc_{extraction_id[:8]}",
            "extraction_id": extraction_id,
            # You need to have this image in your local test_images/ folder
            # for the eval runner to re-run extraction on it
            "image_filename": ext.get("image_filename"),
            "document_type": expected["document_type"],
            "expected": expected,
            # Keep the original raw extraction — useful for debugging
            # and for seeing what the model said before your edits
            "original_extraction": raw,
            "metadata": {
                "confirmed_at": tx.get("created_at"),
                "extraction_created_at": ext.get("created_at"),
                # had_edits = True means you corrected something during review
                # These are your most valuable test cases
                "had_edits": had_edits,
                "had_warnings": ext.get("has_warnings", False),
                "low_confidence_fields": ext.get("low_confidence_fields") or [],
                "overall_confidence": ext.get("overall_confidence"),
                "notes": tx.get("notes") or "",
            },
        }

        cases.append(case)
        status = "EDITED" if had_edits else "clean"
        party_display = party.get("name_roman") or party.get("name_urdu") or "Unknown"
        print(f"  [{status}] {ext['image_filename'] or extraction_id[:8]} "
              f"— {expected['document_type']} — {party_display}")

    return cases


def _detect_edits(raw_extraction: dict, confirmed: dict) -> bool:
    """
    Returns True if the confirmed data differs meaningfully from the raw extraction.
    This means you corrected something during review — a known model error.

    We check document_type, party_name, and grand_total.
    Date is tricky (format differences) so we skip it here.
    """
    if not raw_extraction:
        return False

    raw_doc_type = raw_extraction.get("document_type")
    raw_party = raw_extraction.get("party_name") or ""
    raw_total = None
    if raw_extraction.get("totals"):
        raw_total = raw_extraction["totals"].get("grand_total")

    confirmed_doc_type = confirmed.get("document_type")
    confirmed_party = confirmed.get("party_name") or ""
    confirmed_total = confirmed.get("grand_total")

    if raw_doc_type != confirmed_doc_type:
        return True
    if raw_party.lower().strip() != confirmed_party.lower().strip():
        return True
    if raw_total is not None and confirmed_total is not None:
        if abs(float(raw_total) - float(confirmed_total)) > 1.0:  # PKR 1 tolerance
            return True

    return False


def compute_coverage(cases: list) -> dict:
    """Count how many test cases exist per document type."""
    coverage = {doc_type: 0 for doc_type in DOC_TYPES}
    for case in cases:
        dt = case.get("document_type") or "unknown"
        if dt in coverage:
            coverage[dt] += 1
        else:
            coverage["unknown"] += 1
    return coverage


def write_coverage_report(cases: list, coverage: dict):
    """Write a human-readable coverage summary."""
    total = len(cases)
    edited = sum(1 for c in cases if c["metadata"]["had_edits"])
    warned = sum(1 for c in cases if c["metadata"]["had_warnings"])

    lines = [
        "=" * 50,
        "EVAL DATASET COVERAGE REPORT",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "=" * 50,
        f"Total cases       : {total}",
        f"Cases with edits  : {edited}  (model made errors you corrected — high value)",
        f"Cases with warnings: {warned}  (low confidence fields flagged)",
        "",
        "Coverage by document type:",
    ]

    min_recommended = 4
    for doc_type, count in coverage.items():
        flag = ""
        if count == 0:
            flag = "  ← NO CASES — add some"
        elif count < min_recommended:
            flag = f"  ← below recommended ({min_recommended})"
        lines.append(f"  {doc_type:<25} {count:>3}{flag}")

    lines += [
        "",
        "RECOMMENDATION:",
    ]

    gaps = [dt for dt, count in coverage.items() if count < min_recommended and dt != "unknown"]
    if gaps:
        lines.append(f"  Add more cases for: {', '.join(gaps)}")
        lines.append("  Aim for 4-5 per type minimum before running evals.")
    else:
        lines.append("  Coverage looks good. Grow the dataset by adding images")
        lines.append("  that surprised you or produced warnings in production.")

    lines += [
        "",
        "NEXT STEP:",
        "  Make sure you have the image files in istatis-papers/eval/test_images/",
        "  matching the image_filename values above.",
        "  Then run: python eval/run_eval.py",
        "=" * 50,
    ]

    report = "\n".join(lines)
    with open(COVERAGE_FILE, "w", encoding="utf-8") as f:
        f.write(report)
    print("\n" + report)


def main():
    cases = fetch_approved_extractions()

    if not cases:
        print("No cases built. Nothing to write.")
        sys.exit(0)

    coverage = compute_coverage(cases)

    dataset = {
        "version": "1.0",
        "description": "Ground truth eval dataset for iStatis invoice extraction pipeline.",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_cases": len(cases),
        "coverage_by_type": coverage,
        # IMPORTANT: image_path_prefix tells the eval runner where to look for image files.
        # Put your test images in istatis-papers/eval/test_images/ and name them
        # to match the image_filename field in each case.
        "image_path_prefix": "eval/test_images/",
        "cases": cases,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2, ensure_ascii=False, default=str)

    print(f"\nDataset written to: {OUTPUT_FILE}")
    print(f"  {len(cases)} cases, "
          f"{sum(1 for c in cases if c['metadata']['had_edits'])} with edits")

    write_coverage_report(cases, coverage)


if __name__ == "__main__":
    main()
