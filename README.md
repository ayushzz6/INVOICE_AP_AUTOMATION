# Zamp AP Automation

An AI-powered Accounts Payable workflow that takes vendor invoice PDFs and produces an explainable payment decision: `APPROVED`, `FLAGGED`, or `REJECTED`.

This project was built for the Zamp AI Solutions Associate case study. It focuses on the AP problem statement: companies receive hundreds of invoice PDFs by email, manually match them to purchase orders, check vendor and payment details, and decide whether the invoice can be paid. The goal is to make that process run live, handle realistic edge cases, and show every step between input and decision.

## Highlights

- Real PDF input, either one invoice at a time or as a bulk upload.
- Simulated email inbox for invoice attachments.
- Live seven-stage processing trace: classify, extract, normalize, match, validate, decide, persist.
- Gemini-based extraction with deterministic fallback for generated demo PDFs.
- Text and scanned/image-heavy invoice handling.
- Field-level extraction status: extracted, missing, inferred, suspicious.
- Exact, fuzzy, and inferred PO matching.
- "Why this PO?" explainability panel.
- Eleven validation rules covering vendor approval, PO matching, tolerance, duplicate detection, line math, cumulative PO spend, currency, tax rate, bank verification, and extraction quality.
- Fuzzy duplicate detection using vendor, amount, date, invoice number similarity, PO, and bank signals.
- Payment Readiness score, queue routing, recommended approver, and plain-English next action.
- Side-by-side invoice review: original PDF preview on the left, extracted fields and controls on the right.
- Exception workflow with owner, status, comments, and manual override.
- Vendor email draft generator for missing fields, rejected invoices, and clarification requests.
- Aging and SLA dashboard.
- PO consumption and vendor risk views.
- Payment run summary and CSV export.
- Downloadable audit report for each invoice.

## Tech Stack

- Python 3.11
- Streamlit for the UI
- FastAPI for the optional API server
- SQLite for run history, audit events, inbox state, workflow state, and payment runs
- Pydantic for typed schemas
- PyMuPDF for PDF inspection, text extraction, and preview rendering
- Google Gemini (`google-genai`) for LLM-based invoice extraction
- Pandas for PO/vendor datasets and dashboard views
- Pytest for validation tests

## How The Workflow Works

The main invoice pipeline runs through seven stages:

1. **Classify** - determines whether the PDF is text-based or scanned/image-heavy.
2. **Extract** - extracts invoice number, dates, vendor, PO reference, line items, tax, total, currency, and bank details.
3. **Normalize** - cleans vendor names, PO references, amounts, and identifiers.
4. **Match** - links the invoice to a PO using exact PO reference, fuzzy PO reference, or vendor + amount + date inference.
5. **Validate** - applies business rules for vendor approval, PO tolerance, duplicate detection, bank account verification, and related checks.
6. **Decide** - produces `APPROVED`, `FLAGGED`, or `REJECTED`, plus reasoning and payment recommendation.
7. **Persist** - stores the decision, audit trail, workflow metadata, and uploaded PDF path in SQLite.

## Project Structure

```text
app.py                         Streamlit AP operations console
api.py                         Optional FastAPI backend
requirements.txt               Python dependencies
.env.example                   Environment variable template
pytest.ini                     Pytest configuration

models/
  schemas.py                   Pydantic models for invoices, matches, decisions, readiness, duplicates
  db.py                        SQLite persistence for runs, events, inbox, workflow, payment runs

pipeline/
  classify.py                  Text vs scanned PDF classification
  extract.py                   Gemini extraction plus local deterministic fallback
  normalize.py                 Field normalization helpers
  match.py                     PO matching and explainability reasons
  validate.py                  Validation rules and fuzzy duplicate detection
  decide.py                    Decision engine
  readiness.py                 Payment readiness score and queue routing
  orchestrator.py              End-to-end seven-stage workflow

data/
  pos.csv                      Mock purchase order dataset
  approved_vendors.csv         Mock approved vendor master
  sample_invoices/             Generated demo invoices

scripts/
  generate_invoices.py         Generates sample invoice PDFs
  seed_db.py                   Seeds prior approved invoices for duplicate/split-PO demos

prompts/
  extraction.txt               Gemini extraction prompt

tests/
  test_pipeline.py             Focused tests for matching, validation, and readiness behavior
```

## Setup

The commands below assume the project is located at `C:\downloads\ZAMP`.

### 1. Create and activate environment

```powershell
cd C:\downloads\ZAMP
conda create -p venv python=3.11
conda activate C:\downloads\ZAMP\venv
```

If you already have the environment, just activate it:

```powershell
conda activate C:\downloads\ZAMP\venv
```

### 2. Install dependencies

```powershell
pip install -r requirements.txt
```

### 3. Configure Gemini

Create `.env` from `.env.example`:

```powershell
copy .env.example .env
```

Then edit `.env`:

```text
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-3-flash-preview
DATABASE_URL=sqlite:///data/zamp_ap.db
API_BASE_URL=http://localhost:8000
```

Gemini is optional for the generated text-based demo invoices because the project includes a deterministic local parser. Gemini is recommended for scanned/image-heavy PDFs.

### 4. Generate sample invoices and seed database

```powershell
python scripts\generate_invoices.py
python scripts\seed_db.py
```

### 5. Run the app

```powershell
streamlit run app.py
```

Streamlit will print a local URL, usually `http://localhost:8501`.

### 6. Optional API server

```powershell
uvicorn api:app --reload
```

FastAPI docs will be available at `http://localhost:8000/docs`.

## App Pages

### Dashboard

Top-level AP operations view showing total processed invoices, approvals, reviews, blocked invoices, ready-to-pay value, queue distribution, and recent activity across runs.

### Inbox

Simulates the real workflow where invoices arrive by email. Each inbox row includes sender, subject, attachment filename, received date, guessed vendor, and status. The attachment can be processed directly from the inbox.

### Upload & Live Run

Single-invoice processing page. Upload a PDF and watch the live processing trace execute stage by stage. The output is a decision card, readiness score, recommendation, extracted fields, and audit events.

### Bulk Upload

Processes multiple PDFs together. After the batch completes, the app summarizes total uploaded, processed successfully, failed extraction, ready to pay, needs review, and blocked.

### Exception Queue

Triage page for invoices routed to:

- Ready for Payment
- Needs AP Review
- Needs Procurement Review
- Possible Duplicate
- Vendor/Bank Risk
- Over PO Limit
- Payment Blocked

### Aging & SLA

Prioritization dashboard based on days since received, due date, overdue status, and SLA breach risk.

### Invoice Detail

Investigation workspace for a single run. It includes:

- Original PDF preview
- Extracted fields with field-level status pills
- Line items
- Why-this-PO explanation
- Duplicate candidates
- Validation results
- Workflow owner/status
- Comment history
- Manual override
- Vendor email draft
- Audit trail
- Downloadable HTML audit report

### PO Consumption

Shows PO budget, approved invoiced amount, pending review amount, remaining balance, tolerance cap, exceedance, and per-PO invoice drilldown.

### Vendor Risk

Shows approved vendor master status, tax ID, bank details, duplicate history, rejection history, and payment totals.

### Payment Runs

Previews the payment batch before export. It shows invoice count, total amount, vendors included, high-value payments, overrides included, payment date, CSV export, and saved payment run history.

### AP Assistant

Simple natural-language assistant over recorded invoice decisions. It can answer questions about ready-to-pay invoices, PO consumption, tolerance issues, duplicates, and recent rejections.

### POs & Vendors

Raw reference datasets used by the matching and validation logic.

## Demo Inputs

Sample invoice PDFs are generated in `data/sample_invoices/`.

Recommended demo files:

- `01_happy_path_acme.pdf` - clean happy path before duplicate history is seeded; after seeding it can also demonstrate cumulative or duplicate awareness depending on state.
- `02_amount_over_cloudops.pdf` - amount-over-tolerance review.
- `03_split_po_dataworks.pdf` - split PO / cumulative PO spend awareness.
- `04_duplicate_acme.pdf` - exact or fuzzy duplicate detection.
- `05_missing_po_recurring_saas.pdf` - missing PO reference with inferred PO matching.
- `06_scanned_style_facilities.pdf` - scanned/image-heavy invoice candidate for Gemini extraction.

## Suggested Demo Flow

1. Start on **Dashboard** and explain the goal: PDF invoice in, reasoned AP decision out.
2. Open **Inbox** and click **Populate inbox with sample emails** if the inbox is empty.
3. Process one email attachment live.
4. Narrate the live stages: classify, extract, normalize, match, validate, decide, persist.
5. Open the run in **Invoice Detail**.
6. Show the side-by-side invoice preview and extracted fields.
7. Explain the field status pills and missing/inferred values.
8. Open the **Why this PO?** panel and explain the PO match.
9. Show validation rules, duplicate candidates, and the recommendation.
10. Show workflow assignment and vendor email draft for an exception.
11. Open **Payment Runs** and show the payment batch preview/export.

## Edge Cases Covered

- Missing required invoice fields.
- Missing PO reference with inferred PO matching.
- PO amount variance and tolerance failures.
- Cumulative spend against the same PO.
- Duplicate invoices and near-duplicate invoices.
- Vendor not present or inactive in approved vendor master.
- Bank account mismatch.
- Scanned/image-heavy PDFs.
- Low extraction confidence.
- Human override with audit trail.

## Validation Rules

- `R1` - Required fields present.
- `R2` - Vendor exists and is active in the approved vendor list.
- `R3` - PO reference resolves or can be inferred.
- `R4` - Invoice total is within PO tolerance or recurring PO envelope.
- `R5` - Invoice is not an exact or fuzzy duplicate.
- `R6` - Line item math is consistent.
- `R7` - Cumulative spend stays within PO cap.
- `R8` - Currency matches the PO.
- `R9` - Tax rate is sensible.
- `R10` - Bank account matches approved vendor master.
- `R11` - Extraction confidence is acceptable.

Critical failures reject an invoice. Warning failures usually flag it for review. Informational checks are logged for auditability.

## Payment Readiness

Every invoice decision includes a `PaymentReadiness` payload:

- **Score** - 0 to 100 based on whether key payment checks passed.
- **Checks** - vendor verified, PO matched, bank verified, duplicate check, amount tolerance, PO budget, approval required.
- **Queue** - operational routing bucket.
- **Recommendation** - plain-English instruction for AP.
- **Approver** - suggested owner such as AP Manager, Procurement Owner, Finance Controller, or Vendor Master Team.
- **Blockers** - list of issues preventing payment.

## Gemini Extraction Behavior

When `GEMINI_API_KEY` is present, the app sends the PDF to Gemini using the model configured in `GEMINI_MODEL`.

The extraction prompt requires strict JSON. The code also includes basic response repair for common LLM issues such as code fences, extra surrounding text, and literal newlines inside JSON strings.

If Gemini is unavailable or still returns unusable output, the app falls back to the local parser. For scanned PDFs, the local parser may not recover fields. In that case, the invoice is deliberately rejected or flagged with missing-field reasons instead of hallucinating values.

## Database Reset

PowerShell:

```powershell
Remove-Item data\zamp_ap.db -ErrorAction SilentlyContinue
python scripts\seed_db.py
```

Command Prompt:

```cmd
del data\zamp_ap.db
python scripts\seed_db.py
```

After reset, use the **Inbox** page to seed sample email rows again if needed.

## Running Tests

```powershell
python -m pytest -q
```

Expected result:

```text
5 passed
```

## Push To GitHub

This project intentionally excludes secrets, local virtual environments, generated uploads, inbox files, cache folders, and SQLite databases through `.gitignore`.

Create a new empty GitHub repository, then run:

```powershell
cd C:\downloads\ZAMP
git init
git add .
git commit -m "Initial Zamp AP automation project"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo>.git
git push -u origin main
```

Before pushing, confirm `.env` is not staged:

```powershell
git status --short
```

## Deployment

### Recommended deployment for the full Streamlit UI

The main user interface is a Streamlit app (`app.py`). Vercel does not natively run Streamlit applications as long-running web apps. For the full demo UI, use one of these:

- Streamlit Community Cloud
- Render
- Railway
- Hugging Face Spaces

For Streamlit Cloud, point the app to:

```text
app.py
```

Add this secret in the hosting provider:

```text
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-3-flash-preview
```

### Vercel deployment

This repo includes `vercel.json` and `vercel_app/index.py` so the FastAPI API can be deployed on Vercel.

Vercel will expose endpoints such as:

```text
/health
/process
/history
/invoice/{run_id}
/pos
/vendors
```

Set these Vercel environment variables:

```text
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-3-flash-preview
ZAMP_DB_PATH=/tmp/zamp_ap.db
```

Important Vercel limitation: `/tmp` storage is ephemeral. That is acceptable for a lightweight API demo, but not for persistent production history. For persistent deployment, replace SQLite with a hosted database such as Supabase Postgres, Neon, or Railway Postgres.

Deploy with Vercel CLI:

```powershell
npm install -g vercel
vercel login
vercel
vercel --prod
```

Or connect the GitHub repo in the Vercel dashboard and deploy from `main`.

## Troubleshooting

### Streamlit does not start

Make sure the environment is active and dependencies are installed:

```powershell
conda activate C:\downloads\ZAMP\venv
pip install -r requirements.txt
streamlit run app.py
```

### Gemini extraction falls back

Check that `.env` contains a valid key:

```text
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-3-flash-preview
```

If the invoice is scanned, Gemini is needed for best results. If Gemini returns malformed JSON, the app attempts repair and then falls back safely.

### The demo state looks confusing

Reset and reseed:

```powershell
Remove-Item data\zamp_ap.db -ErrorAction SilentlyContinue
python scripts\seed_db.py
```

Then restart Streamlit and seed the inbox from the **Inbox** page.

### Tests cannot import project modules

Run tests from the project root:

```powershell
cd C:\downloads\ZAMP
python -m pytest -q
```

## Submission Notes

This project is designed to demonstrate:

- A live process that actually runs end to end.
- A clear operational workflow, not just a one-off extractor.
- Realistic AP edge cases.
- Explainable decisions that a non-technical AP or finance user can understand.
- A dashboard and history across runs.
- Human-in-the-loop exception handling and auditability.