# iStatis — Invoice Extraction Eval Harness

A repeatable test suite for the GPT-4o invoice extraction pipeline.
Run it before deploying any prompt change to catch regressions.

## Folder structure

```
eval/
  build_dataset.py   — Step 1: pull ground truth from Supabase → dataset.json
  run_eval.py        — Step 2: run each test image through extraction API → score it
  dataset.json       — Generated ground truth (do not edit manually)
  coverage.txt       — Dataset balance report (generated)
  results/           — Per-run score reports (generated, tracked over time)
  test_images/       — Put your test invoice images here
```

## How to run

```bash
cd istatis-papers
source venv/Scripts/activate   # Windows
# source venv/bin/activate     # Mac/Linux

# Step 1 — build ground truth from confirmed Supabase data
python eval/build_dataset.py

# Step 2 — run eval (after run_eval.py is built)
python eval/run_eval.py
```

## What "ground truth" means

Every invoice you confirmed through the app wrote two things to Supabase:
- `document_extractions.raw_extraction` — what GPT-4o originally extracted
- `transactions` + `transaction_line_items` — what you verified as correct

The confirmed data is ground truth. The raw extraction is what we score.

## Adding new test cases

1. Import and confirm the image through the app as normal
2. Re-run `build_dataset.py` — it picks up the new confirmed extraction automatically
3. Copy the image file into `eval/test_images/`

## Dataset health

Aim for at least 4-5 cases per document type:
- sales_slip
- price_list
- distribution_record
- account_ledger
- calculation_note

Check `coverage.txt` after running `build_dataset.py`.
