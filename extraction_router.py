"""
Invoice extraction router for iStatis.
Mounts at /extract in main.py via: app.include_router(extraction_router)
"""

import base64
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from openai import AsyncOpenAI
from pydantic import BaseModel

from database import supabase

# Single-tenant: hardcoded UUID for iStatis internal use.
# Replace with a real tenants lookup if/when multi-tenant is needed.
_ISTATIS_TENANT_ID = "00000000-0000-0000-0000-000000000001"


def get_tenant_id() -> str:
    return _ISTATIS_TENANT_ID

router = APIRouter(prefix="/extract", tags=["extraction"])
_openai = AsyncOpenAI()


# ---------------------------------------------------------------------------
# Prompt — domain-aware, year injected at call time
# ---------------------------------------------------------------------------

def _system_prompt() -> str:
    year = datetime.now().year
    return f"""You are a data extraction assistant for a Pakistani paper trading business.
You extract structured data from handwritten business documents including:
- Khata pages (account ledger pages with running balances)
- Price lists (multi-column lists of paper products and wholesale prices)
- Sales slips (individual transaction notes with date, quantity, product, price)
- Distribution records (how many reams of each paper type went to which party)

PRODUCT CODE VOCABULARY (paper sizes and types used in Pakistan):
Sizes: A/4, F/S or F15 (Foolscap), A/3, 9x4, 11x5, 8x10, 9x6, 7x5, 7.5x5
Types: open (uncoated offset), PRT or print (printing grade), windo or window (window envelope),
       DCP (digital copy), G-2 or G2 (Grade 2), USA (imported brand),
       Endlife (brand name), callon or callory (carbon copy paper)
Colors: green (گرین), blue (بلیو)
Units: reams (ریم), sheets (شیٹ), bags (بیگ)

EXTRACTION RULES:
1. Dates are usually DD/MM/YY or DD-MM-YY format.
2. For Urdu party names: keep both the Urdu text and your best Roman transliteration.
3. Product codes like "9x4-PRT" mean size 9x4 inches, printing grade.
4. Circled numbers are key values — usually confirmed totals or quantities.
5. BBF means Brought Forward Balance.
6. Assign a confidence score 0.0 to 1.0 to each extracted field.
7. If a value is unclear or ambiguous, flag it in low_confidence_fields.
8. The current year is {year}. When reading a 2-digit year, map it to the nearest plausible
   year within 1 year of today. If the result falls outside {year - 1}-{year + 1},
   re-examine the digit — it is likely a misread.
9. For documents with multiple columns, each column is a separate attribute (e.g., left =
   product size, middle = type/grade, right = price). Do not concatenate values across
   columns with "=" or other separators. Extract each column independently.

Return ONLY valid JSON. No markdown code blocks, no explanation text."""


_EXTRACTION_PROMPT = """Extract all data from this business document image.

Return this exact JSON structure (use null for fields not present in the image):
{
  "document_type": "price_list | sales_slip | distribution_record | account_ledger | calculation_note | unknown",
  "date": "DD/MM/YY or null",
  "party_name": "Roman transliteration or null",
  "party_name_urdu": "Urdu script text or null",
  "overall_confidence": 0.0,
  "line_items": [
    {
      "product_code": "e.g. A/4, F/S, 9x4-PRT",
      "description": "any additional description",
      "quantity": null,
      "unit_price": null,
      "amount": null,
      "confidence": 0.0,
      "notes": "anything uncertain or unclear about this line"
    }
  ],
  "totals": {
    "subtotal": null,
    "discount": null,
    "grand_total": null
  },
  "low_confidence_fields": ["list any field names that are uncertain"],
  "unreadable_sections": "describe anything you could not read, or null",
  "raw_text_urdu": "any Urdu text present verbatim, or null"
}"""


# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------

async def _run_extraction(image_bytes: bytes, content_type: str) -> dict:
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    response = await _openai.chat.completions.create(
        model="gpt-4o",
        max_tokens=2500,
        messages=[
            {"role": "system", "content": _system_prompt()},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{content_type};base64,{b64}",
                            "detail": "high",
                        },
                    },
                    {"type": "text", "text": _EXTRACTION_PROMPT},
                ],
            },
        ],
    )
    raw = response.choices[0].message.content.strip()
    # Strip markdown fences if model adds them despite instructions
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class LineItemIn(BaseModel):
    product_code: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    amount: Optional[float] = None
    confidence: Optional[float] = None
    notes: Optional[str] = None


class ConfirmRequest(BaseModel):
    party_name: Optional[str] = None
    party_name_urdu: Optional[str] = None
    transaction_date: Optional[str] = None  # "DD/MM/YY" or "DD/MM/YYYY"
    document_type: Optional[str] = None
    transaction_type: Optional[str] = "sale"  # sale | payment_received | purchase | expense
    total_amount: Optional[float] = None
    line_items: list[LineItemIn] = []
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("")
async def extract_document(file: UploadFile = File(...)):
    """
    Upload an image -> GPT-4o extraction -> stored in document_extractions.
    Returns extraction_id + data for the review screen.
    """
    content_type = file.content_type or "image/jpeg"
    image_bytes = await file.read()

    try:
        data = await _run_extraction(image_bytes, content_type)
    except json.JSONDecodeError as exc:
        raise HTTPException(422, detail=f"Extraction returned invalid JSON: {exc}") from exc
    except Exception as exc:
        raise HTTPException(502, detail=f"GPT-4o error: {exc}") from exc

    tenant_id = get_tenant_id()
    low_fields: list[str] = data.get("low_confidence_fields") or []
    has_warnings = bool(low_fields) or bool(data.get("unreadable_sections"))

    row = (
        supabase.table("document_extractions")
        .insert({
            "tenant_id": tenant_id,
            "image_filename": file.filename,
            "raw_extraction": data,
            "document_type": data.get("document_type"),
            "overall_confidence": data.get("overall_confidence"),
            "has_warnings": has_warnings,
            "low_confidence_fields": low_fields,
            "unreadable_sections": data.get("unreadable_sections"),
            "status": "pending_review",
        })
        .execute()
    )
    extraction_id = row.data[0]["id"]

    return {
        "extraction_id": extraction_id,
        "has_warnings": has_warnings,
        "data": data,
    }


@router.post("/{extraction_id}/confirm")
async def confirm_extraction(extraction_id: str, body: ConfirmRequest):
    """
    User approved the extraction (possibly after editing).
    Creates/matches party, saves transaction + line items, marks extraction approved.
    """
    tenant_id = get_tenant_id()

    # --- Party matching ---
    party_id = None
    if body.party_name or body.party_name_urdu:
        search = (body.party_name or body.party_name_urdu or "").strip().lower()

        alias_hit = (
            supabase.table("party_aliases")
            .select("party_id")
            .ilike("alias", search)
            .limit(1)
            .execute()
        )

        if alias_hit.data:
            party_id = alias_hit.data[0]["party_id"]
        else:
            party_row = (
                supabase.table("parties")
                .insert({
                    "tenant_id": tenant_id,
                    "name_roman": body.party_name or search,
                    "name_urdu": body.party_name_urdu,
                    "party_type": "unknown",
                })
                .execute()
            )
            party_id = party_row.data[0]["id"]

            aliases = []
            if body.party_name:
                aliases.append({"party_id": party_id, "alias": body.party_name.lower()})
            if body.party_name_urdu:
                aliases.append({"party_id": party_id, "alias": body.party_name_urdu})
            if aliases:
                supabase.table("party_aliases").insert(aliases).execute()

    # --- Date parsing ---
    tx_date = None
    if body.transaction_date:
        for fmt in ("%d/%m/%y", "%d-%m-%y", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                tx_date = datetime.strptime(body.transaction_date, fmt).date().isoformat()
                break
            except ValueError:
                continue

    # --- Transaction ---
    tx_row = (
        supabase.table("transactions")
        .insert({
            "tenant_id": tenant_id,
            "extraction_id": extraction_id,
            "party_id": party_id,
            "transaction_date": tx_date,
            "document_type": body.document_type,
            "transaction_type": body.transaction_type or "sale",
            "total_amount": body.total_amount,
            "notes": body.notes,
        })
        .execute()
    )
    transaction_id = tx_row.data[0]["id"]

    # --- Line items ---
    if body.line_items:
        supabase.table("transaction_line_items").insert([
            {
                "transaction_id": transaction_id,
                "product_code": item.product_code,
                "description": item.description,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "amount": item.amount,
                "confidence": item.confidence,
                "notes": item.notes,
            }
            for item in body.line_items
        ]).execute()

    # --- Mark approved ---
    supabase.table("document_extractions").update({
        "status": "approved",
        "reviewed_at": datetime.now().isoformat(),
    }).eq("id", extraction_id).execute()

    return {"transaction_id": transaction_id, "party_id": party_id}


@router.get("/pending")
async def list_pending():
    """Extractions waiting for user review."""
    tenant_id = get_tenant_id()
    rows = (
        supabase.table("document_extractions")
        .select("id, image_filename, document_type, overall_confidence, has_warnings, created_at")
        .eq("tenant_id", tenant_id)
        .eq("status", "pending_review")
        .order("created_at", desc=True)
        .execute()
    )
    return rows.data


@router.get("/transactions")
async def list_transactions(party_id: Optional[str] = None):
    """Confirmed transactions with party info, newest first.
    Optional ?party_id=UUID to filter by party."""
    tenant_id = get_tenant_id()
    query = (
        supabase.table("transactions")
        .select(
            "id, transaction_date, document_type, transaction_type, "
            "total_amount, notes, created_at, "
            "parties(id, name_roman, name_urdu)"
        )
        .eq("tenant_id", tenant_id)
        .order("transaction_date", desc=True)
        .limit(100)
    )
    if party_id:
        query = query.eq("party_id", party_id)
    return query.execute().data


@router.get("/transactions/{transaction_id}")
async def get_transaction_detail(transaction_id: str):
    """Single transaction with party info and all line items."""
    row = (
        supabase.table("transactions")
        .select(
            "id, transaction_date, document_type, transaction_type, "
            "total_amount, notes, created_at, "
            "parties(id, name_roman, name_urdu), "
            "transaction_line_items(id, product_code, description, "
            "quantity, unit_price, amount, confidence, notes)"
        )
        .eq("id", transaction_id)
        .single()
        .execute()
    )
    if not row.data:
        raise HTTPException(404, detail="Transaction not found")
    return row.data


@router.get("/parties/balances")
async def get_party_balances():
    """
    Per-party running balance, sorted by outstanding amount descending.
    Balance = SUM(sales) - SUM(payments_received).
    Positive = party owes iStatis. Negative = iStatis owes party.
    """
    tenant_id = get_tenant_id()
    rows = (
        supabase.table("transactions")
        .select(
            "party_id, transaction_type, total_amount, transaction_date, "
            "parties(id, name_roman, name_urdu)"
        )
        .eq("tenant_id", tenant_id)
        .not_.is_("party_id", "null")
        .execute()
    )

    # Aggregate in Python — simple enough at this data volume
    from collections import defaultdict
    balances: dict = defaultdict(lambda: {
        "party_id": None,
        "name_roman": None,
        "name_urdu": None,
        "balance": 0.0,
        "total_sales": 0.0,
        "total_payments": 0.0,
        "transaction_count": 0,
        "last_transaction_date": None,
    })

    for row in rows.data:
        pid = row["party_id"]
        party = row.get("parties") or {}
        b = balances[pid]
        b["party_id"] = pid
        b["name_roman"] = party.get("name_roman")
        b["name_urdu"] = party.get("name_urdu")
        b["transaction_count"] += 1

        amount = float(row.get("total_amount") or 0)
        tx_type = row.get("transaction_type") or "sale"
        if tx_type == "sale":
            b["total_sales"] += amount
            b["balance"] += amount
        elif tx_type == "payment_received":
            b["total_payments"] += amount
            b["balance"] -= amount
        elif tx_type == "purchase":
            b["balance"] -= amount
        # expense doesn't affect party balance

        date = row.get("transaction_date")
        if date and (b["last_transaction_date"] is None or date > b["last_transaction_date"]):
            b["last_transaction_date"] = date

    result = sorted(balances.values(), key=lambda x: x["balance"], reverse=True)
    return result
