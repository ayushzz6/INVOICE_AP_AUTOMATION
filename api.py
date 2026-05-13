from __future__ import annotations

import base64
import shutil
import tempfile
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from models import db
from models.schemas import OverrideRequest
from pipeline.orchestrator import process_invoice

app = FastAPI(title="Zamp AP Automation", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def startup() -> None:
    db.init_db()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


QUEUE_ORDER = [
    "Ready for Payment",
    "Needs AP Review",
    "Needs Procurement Review",
    "Possible Duplicate",
    "Vendor/Bank Risk",
    "Over PO Limit",
]

FIELD_LABELS = {
    "invoice_number": "Invoice number",
    "invoice_date": "Invoice date",
    "due_date": "Due date",
    "vendor.name": "Vendor name",
    "vendor.tax_id": "Vendor tax ID",
    "po_reference": "PO reference",
    "total": "Total",
    "subtotal": "Subtotal",
    "tax_amount": "Tax amount",
    "bank_account": "Bank account",
    "bank_ifsc": "Bank IFSC",
}

WORKFLOW_OWNERS = [
    "AP Manager",
    "Procurement Owner",
    "Vendor Master",
    "Finance Controller",
    "Compliance",
]

WORKFLOW_STATES = [
    "Open",
    "Waiting for Vendor",
    "Waiting for Procurement",
    "Approved",
    "Rejected",
]

SAMPLE_PDF_DIR = Path("data/sample_invoices")
INBOX_PDF_DIR = Path("data/inbox")

SEED_EMAILS: list[dict[str, str]] = [
    {
        "filename": "01_happy_path_acme.pdf",
        "sender": "billing@acmesteel.in",
        "subject": "Invoice ACME-2026-001 for May steel order",
        "body": "Please find attached our invoice for the May steel shipment against PO-2026-0068.",
        "vendor_guess": "Acme Steel Pvt Ltd",
    },
    {
        "filename": "02_amount_over_cloudops.pdf",
        "sender": "ar@cloudops.in",
        "subject": "CloudOps May invoice",
        "body": "Attaching the May cloud operations invoice for AP processing.",
        "vendor_guess": "CloudOps Managed Services",
    },
    {
        "filename": "03_split_po_dataworks.pdf",
        "sender": "billing@dataworks.in",
        "subject": "DataWorks split PO invoice",
        "body": "Please process this partial invoice against the active analytics PO.",
        "vendor_guess": "DataWorks Analytics Pvt Ltd",
    },
    {
        "filename": "04_duplicate_acme.pdf",
        "sender": "billing@acmesteel.in",
        "subject": "Resending ACME invoice",
        "body": "Resending the invoice in case the earlier attachment was missed.",
        "vendor_guess": "Acme Office Supplies Pvt Ltd",
    },
    {
        "filename": "05_missing_po_recurring_saas.pdf",
        "sender": "ar@recurringsaas.in",
        "subject": "Monthly subscription invoice RS-2026-009",
        "body": "Recurring monthly subscription invoice. No PO is printed on the invoice.",
        "vendor_guess": "RecurringSaaS India Pvt Ltd",
    },
    {
        "filename": "06_scanned_style_facilities.pdf",
        "sender": "facilities@northstar.in",
        "subject": "Scanned facilities invoice",
        "body": "Scanned copy attached. Please process after validating details.",
        "vendor_guess": "Northstar Facilities",
    },
]


class WorkflowUpdate(BaseModel):
    owner: str | None = None
    state: str | None = None


class CommentCreate(BaseModel):
    author: str = "ap_manager_demo"
    body: str


class InboxUpdate(BaseModel):
    status: str


class AssistantQuery(BaseModel):
    query: str


class PaymentRunCreate(BaseModel):
    payment_date: str | None = None


def queue_for(decision: dict[str, Any]) -> str:
    readiness = decision.get("readiness") or {}
    return readiness.get("queue") or ("Payment Blocked" if decision.get("status") == "REJECTED" else "Needs AP Review")


def all_decisions() -> list[dict[str, Any]]:
    return [d.model_dump(mode="json") for d in db.get_all_decisions()]


def queue_counts(decisions: list[dict[str, Any]]) -> dict[str, int]:
    counts = {q: 0 for q in QUEUE_ORDER}
    counts["Payment Blocked"] = 0
    for decision in decisions:
        queue = queue_for(decision)
        counts[queue] = counts.get(queue, 0) + 1
    return counts


def safe_lower(value: object) -> str:
    return str(value or "").strip().lower()


def default_owner_and_state(decision: dict[str, Any]) -> tuple[str, str]:
    queue = ((decision.get("readiness") or {}).get("queue") or "")
    if queue == "Ready for Payment":
        return "AP Manager", "Approved"
    if queue in {"Needs Procurement Review", "Over PO Limit"}:
        return "Procurement Owner", "Waiting for Procurement"
    if queue == "Vendor/Bank Risk":
        return "Vendor Master", "Waiting for Vendor"
    if queue == "Payment Blocked":
        return "Compliance", "Rejected"
    return "AP Manager", "Open"


def build_vendor_email_draft(decision: dict[str, Any]) -> dict[str, str]:
    extracted = decision.get("extracted") or {}
    vendor = extracted.get("vendor") or {}
    invoice_no = extracted.get("invoice_number") or "(no invoice number)"
    vendor_name = vendor.get("name") or "Vendor"
    currency = extracted.get("currency", "INR")
    total = float(extracted.get("total") or 0)
    missing = extracted.get("missing_fields") or []
    status = decision.get("status")
    blockers = ((decision.get("readiness") or {}).get("blockers") or [])

    if missing:
        subject = f"Missing information for invoice {invoice_no}"
        readable = ", ".join(FIELD_LABELS.get(m, m.replace("_", " ").title()) for m in missing)
        body = (
            f"Hi {vendor_name} team,\n\n"
            f"Thanks for sending invoice {invoice_no} for {currency} {total:,.2f}. "
            f"Before we can process payment, we need clarification on: {readable}.\n\n"
            f"Please confirm the missing values so we can continue processing.\n\n"
            f"Thank you,\nAccounts Payable Team"
        )
    elif status == "REJECTED":
        subject = f"Invoice {invoice_no} cannot be processed"
        reasons = "\n".join(f"- {b}" for b in blockers) or "- Validation rules failed."
        body = (
            f"Hi {vendor_name} team,\n\n"
            f"We received invoice {invoice_no} for {currency} {total:,.2f}, but we cannot process it "
            f"at this time for the following reasons:\n\n{reasons}\n\n"
            f"Please review and re-issue once corrected.\n\nThank you,\nAccounts Payable Team"
        )
    elif status == "FLAGGED":
        subject = f"Quick clarification on invoice {invoice_no}"
        reason = blockers[0] if blockers else decision.get("reasoning", "An internal check needs review.")
        body = (
            f"Hi {vendor_name} team,\n\n"
            f"We received invoice {invoice_no} for {currency} {total:,.2f}. It is on hold pending this clarification:\n\n"
            f"- {reason}\n\nCould you confirm so we can continue processing?\n\nThank you,\nAccounts Payable Team"
        )
    else:
        subject = f"Invoice {invoice_no} approved for payment"
        body = (
            f"Hi {vendor_name} team,\n\n"
            f"Invoice {invoice_no} for {currency} {total:,.2f} has been approved and is scheduled for payment.\n\n"
            f"Thank you,\nAccounts Payable Team"
        )
    return {"subject": subject, "body": body}


def answer_question(query: str, decisions: list[dict[str, Any]]) -> str:
    q = (query or "").strip().lower()
    if not q:
        return "Ask about an invoice, vendor, PO, or queue."
    if "ready to pay" in q or "ready for payment" in q:
        ready = [d for d in decisions if queue_for(d) == "Ready for Payment"]
        if not ready:
            return "No invoices are currently ready to pay."
        lines = [
            f"- {(d.get('extracted') or {}).get('invoice_number')} from {((d.get('extracted') or {}).get('vendor') or {}).get('name')} for {(d.get('extracted') or {}).get('currency','INR')} {float((d.get('extracted') or {}).get('total') or 0):,.2f}"
            for d in ready[:10]
        ]
        return f"There are {len(ready)} invoices ready to pay:\n" + "\n".join(lines)
    if "duplicate" in q:
        dup = [d for d in decisions if queue_for(d) == "Possible Duplicate"]
        return f"{len(dup)} invoice(s) flagged as possible duplicates." if dup else "No possible duplicates."
    if "over po" in q or "tolerance" in q:
        over = [d for d in decisions if queue_for(d) == "Over PO Limit"]
        return f"{len(over)} invoice(s) exceed PO tolerance." if over else "No invoices are currently exceeding PO tolerance."
    if "summary" in q or "queue" in q or "status" in q:
        counts = queue_counts(decisions)
        return "Queue summary: " + ", ".join(f"{k}: {v}" for k, v in counts.items())
    return "I can answer questions about ready-to-pay invoices, PO consumption, tolerance issues, duplicates, and recent rejections."


def days_between(value: str | None, today: date | None = None) -> int | None:
    if not value:
        return None
    today = today or datetime.now(timezone.utc).date()
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except Exception:
        try:
            parsed = datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
        except Exception:
            return None
    return (today - parsed).days


def days_until(value: str | None, today: date | None = None) -> int | None:
    days = days_between(value, today)
    return -days if days is not None else None


def payment_run_candidates(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [d for d in decisions if queue_for(d) == "Ready for Payment" or d.get("overridden_status") == "APPROVED"]


@app.post("/process")
async def process(file: UploadFile = File(...)) -> dict:
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Upload a PDF invoice.")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(await file.read())
        tmp_path = Path(tmp.name)
    try:
        decision, events = process_invoice(tmp_path, file.filename)
        return {"decision": decision.model_dump(mode="json"), "events": [e.model_dump(mode="json") for e in events]}
    finally:
        tmp_path.unlink(missing_ok=True)


@app.post("/process/bulk")
async def process_bulk(files: list[UploadFile] = File(...)) -> dict:
    results: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for file in files:
        if not file.filename.lower().endswith(".pdf"):
            failures.append({"filename": file.filename, "error": "Not a PDF"})
            continue
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(await file.read())
            tmp_path = Path(tmp.name)
        try:
            decision, events = process_invoice(tmp_path, file.filename)
            results.append({"decision": decision.model_dump(mode="json"), "events": [e.model_dump(mode="json") for e in events]})
        except Exception as exc:
            failures.append({"filename": file.filename, "error": str(exc)})
        finally:
            tmp_path.unlink(missing_ok=True)
    ready = sum(1 for item in results if queue_for(item["decision"]) == "Ready for Payment")
    review = sum(1 for item in results if item["decision"].get("status") == "FLAGGED")
    blocked = sum(1 for item in results if item["decision"].get("status") == "REJECTED")
    return {
        "summary": {
            "total_uploaded": len(files),
            "processed_successfully": len(results),
            "failed_extraction": len(failures),
            "ready_to_pay": ready,
            "needs_review": review,
            "blocked": blocked,
        },
        "results": results,
        "failures": failures,
    }


@app.get("/history")
def history(status: str | None = None, vendor: str | None = None) -> list[dict]:
    return [run.model_dump(mode="json") for run in db.list_runs(status=status, vendor=vendor)]


@app.get("/decisions")
def decisions() -> list[dict]:
    return all_decisions()


@app.get("/dashboard")
def dashboard() -> dict:
    decisions_data = all_decisions()
    counts = queue_counts(decisions_data)
    total = len(decisions_data)
    approved = sum(1 for d in decisions_data if d.get("status") == "APPROVED")
    flagged = sum(1 for d in decisions_data if d.get("status") == "FLAGGED")
    rejected = sum(1 for d in decisions_data if d.get("status") == "REJECTED")
    total_amount = sum(float((d.get("extracted") or {}).get("total") or 0) for d in decisions_data)
    ready_amount = sum(float((d.get("extracted") or {}).get("total") or 0) for d in decisions_data if queue_for(d) == "Ready for Payment")
    recent = sorted(decisions_data, key=lambda d: d.get("timestamp") or "", reverse=True)[:15]
    return {
        "metrics": {
            "total_processed": total,
            "approved": approved,
            "flagged": flagged,
            "rejected": rejected,
            "total_amount": total_amount,
            "ready_amount": ready_amount,
        },
        "queues": counts,
        "recent": recent,
    }


@app.get("/queues")
def queues() -> dict:
    decisions_data = all_decisions()
    counts = queue_counts(decisions_data)
    grouped: dict[str, list[dict[str, Any]]] = {q: [] for q in QUEUE_ORDER + ["Payment Blocked"]}
    for decision in decisions_data:
        grouped.setdefault(queue_for(decision), []).append(decision)
    return {"counts": counts, "queues": grouped}


@app.get("/invoice/{run_id}")
def invoice(run_id: str) -> dict:
    decision = db.get_decision(run_id)
    if not decision:
        raise HTTPException(status_code=404, detail="Run not found.")
    return {"decision": decision.model_dump(mode="json"), "events": db.get_events(run_id)}


@app.get("/invoice/{run_id}/preview")
def invoice_preview(run_id: str) -> dict:
    decision = db.get_decision(run_id)
    if not decision:
        raise HTTPException(status_code=404, detail="Run not found.")
    stored_path = decision.stored_path
    if not stored_path or not Path(stored_path).exists():
        raise HTTPException(status_code=404, detail="Stored PDF not available.")
    try:
        import fitz

        doc = fitz.open(str(stored_path))
        page = doc.load_page(0)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        image = base64.b64encode(pix.tobytes("png")).decode("ascii")
        return {
            "image": f"data:image/png;base64,{image}",
            "filename": Path(stored_path).name,
            "page_count": doc.page_count,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not render preview: {exc}") from exc


@app.get("/pos")
def pos() -> list[dict]:
    return pd.read_csv("data/pos.csv").to_dict(orient="records")


@app.get("/vendors")
def vendors() -> list[dict]:
    return pd.read_csv("data/approved_vendors.csv").to_dict(orient="records")


@app.get("/po-consumption")
def po_consumption() -> dict:
    pos_frame = pd.read_csv("data/pos.csv")
    decisions_data = all_decisions()
    rows = []
    for _, po in pos_frame.iterrows():
        po_number = po["po_number"]
        related = [d for d in decisions_data if (d.get("extracted") or {}).get("po_reference") == po_number]
        invoiced_approved = sum(float((d.get("extracted") or {}).get("total") or 0) for d in related if d.get("status") == "APPROVED")
        invoiced_pending = sum(float((d.get("extracted") or {}).get("total") or 0) for d in related if d.get("status") == "FLAGGED")
        po_amount = float(po["po_amount"])
        tolerance = float(po["tolerance_pct"]) / 100
        cap = po_amount * (1 + tolerance)
        rows.append({
            "po_number": po_number,
            "vendor": po["vendor_name"],
            "po_amount": po_amount,
            "approved_invoiced": invoiced_approved,
            "pending_review": invoiced_pending,
            "remaining": po_amount - invoiced_approved,
            "tolerance_cap": cap,
            "exceedance": max(0.0, (invoiced_approved + invoiced_pending) - cap),
            "status": po["status"],
            "invoices": db.get_po_invoices(po_number),
        })
    return {"rows": rows}


@app.get("/vendor-risk")
def vendor_risk() -> dict:
    vendors_frame = pd.read_csv("data/approved_vendors.csv")
    decisions_data = all_decisions()
    rows = []
    for _, vendor in vendors_frame.iterrows():
        vendor_name = vendor["vendor_name"]
        history_items = [
            d for d in decisions_data
            if safe_lower(((d.get("extracted") or {}).get("vendor") or {}).get("name")) == safe_lower(vendor_name)
        ]
        rows.append({
            "vendor": vendor_name,
            "active": str(vendor.get("active")).lower() == "true",
            "tax_id": vendor.get("tax_id"),
            "bank_account": vendor.get("bank_account"),
            "bank_ifsc": vendor.get("bank_ifsc"),
            "invoices": len(history_items),
            "approved": sum(1 for d in history_items if d.get("status") == "APPROVED"),
            "flagged": sum(1 for d in history_items if d.get("status") == "FLAGGED"),
            "rejected": sum(1 for d in history_items if d.get("status") == "REJECTED"),
            "duplicates": sum(1 for d in history_items if queue_for(d) == "Possible Duplicate"),
            "total_paid": sum(float((d.get("extracted") or {}).get("total") or 0) for d in history_items if d.get("status") == "APPROVED"),
            "history": db.get_vendor_invoices(vendor_name),
        })
    return {"rows": rows}


@app.get("/inbox")
def inbox(status: str | None = None) -> dict:
    return {"counts": db.inbox_counts(), "emails": db.list_inbox(status)}


@app.post("/inbox/seed")
def seed_inbox() -> dict:
    INBOX_PDF_DIR.mkdir(parents=True, exist_ok=True)
    existing = {row["attachment_name"] for row in db.list_inbox()}
    inserted = 0
    for seed in SEED_EMAILS:
        if seed["filename"] in existing:
            continue
        src = SAMPLE_PDF_DIR / seed["filename"]
        if not src.exists():
            continue
        dest = INBOX_PDF_DIR / seed["filename"]
        if not dest.exists():
            shutil.copyfile(src, dest)
        db.upsert_inbox_email({
            "id": str(uuid.uuid4()),
            "received_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "sender": seed["sender"],
            "subject": seed["subject"],
            "body": seed["body"],
            "attachment_name": seed["filename"],
            "vendor_guess": seed["vendor_guess"],
            "status": "New",
            "run_id": None,
            "pdf_path": str(dest),
        })
        inserted += 1
    return {"inserted": inserted, "counts": db.inbox_counts(), "emails": db.list_inbox()}


@app.patch("/inbox/{email_id}")
def update_inbox(email_id: str, payload: InboxUpdate) -> dict:
    if not db.get_inbox_email(email_id):
        raise HTTPException(status_code=404, detail="Email not found.")
    db.update_inbox_status(email_id, payload.status)
    return {"status": "updated", "email": db.get_inbox_email(email_id)}


@app.post("/inbox/{email_id}/process")
def process_inbox(email_id: str) -> dict:
    email = db.get_inbox_email(email_id)
    if not email:
        raise HTTPException(status_code=404, detail="Email not found.")
    if email.get("run_id"):
        decision = db.get_decision(email["run_id"])
        return {"decision": decision.model_dump(mode="json") if decision else None, "events": db.get_events(email["run_id"]), "email": email}
    pdf_path = email.get("pdf_path")
    if not pdf_path or not Path(pdf_path).exists():
        raise HTTPException(status_code=404, detail="Attachment not found.")
    db.update_inbox_status(email_id, "Processing")
    decision, events = process_invoice(pdf_path, email.get("attachment_name") or "inbox.pdf")
    db.update_inbox_status(email_id, "Reviewed", decision.invoice_id)
    return {"decision": decision.model_dump(mode="json"), "events": [e.model_dump(mode="json") for e in events], "email": db.get_inbox_email(email_id)}


@app.get("/workflow/{run_id}")
def workflow(run_id: str) -> dict:
    decision = db.get_decision(run_id)
    if not decision:
        raise HTTPException(status_code=404, detail="Run not found.")
    decision_data = decision.model_dump(mode="json")
    wf = db.get_workflow(run_id)
    if not wf:
        owner, state = default_owner_and_state(decision_data)
        wf = {"run_id": run_id, "owner": owner, "state": state, "updated_at": None}
    return {"workflow": wf, "comments": db.list_comments(run_id), "owners": WORKFLOW_OWNERS, "states": WORKFLOW_STATES}


@app.patch("/workflow/{run_id}")
def update_workflow(run_id: str, payload: WorkflowUpdate) -> dict:
    if not db.get_decision(run_id):
        raise HTTPException(status_code=404, detail="Run not found.")
    db.set_workflow(run_id, payload.owner, payload.state)
    return workflow(run_id)


@app.post("/workflow/{run_id}/comments")
def create_comment(run_id: str, payload: CommentCreate) -> dict:
    if not db.get_decision(run_id):
        raise HTTPException(status_code=404, detail="Run not found.")
    db.add_comment(run_id, payload.author, payload.body)
    return workflow(run_id)


@app.get("/aging")
def aging() -> dict:
    decisions_data = all_decisions()
    today = datetime.now(timezone.utc).date()
    rows = []
    breach_count = 0
    overdue_count = 0
    for decision in decisions_data:
        extracted = decision.get("extracted") or {}
        received_days = days_between(decision.get("timestamp"), today) or 0
        due_in = days_until(extracted.get("due_date"), today)
        sla_at_risk = decision.get("status") != "APPROVED" and received_days > 7
        overdue = due_in is not None and due_in < 0 and decision.get("status") != "APPROVED"
        breach_count += int(sla_at_risk)
        overdue_count += int(overdue)
        rows.append({
            "run_id": decision.get("invoice_id"),
            "invoice": extracted.get("invoice_number"),
            "vendor": (extracted.get("vendor") or {}).get("name"),
            "amount": float(extracted.get("total") or 0),
            "currency": extracted.get("currency") or "INR",
            "received_days": received_days,
            "due_in": due_in,
            "status": decision.get("status"),
            "queue": queue_for(decision),
            "sla_at_risk": sla_at_risk,
            "overdue": overdue,
        })
    rows.sort(key=lambda row: row["received_days"], reverse=True)
    return {"metrics": {"in_flight": len(rows), "sla_at_risk": breach_count, "overdue": overdue_count}, "rows": rows}


@app.get("/payment-runs")
def payment_runs() -> list[dict]:
    return db.list_payment_runs()


@app.post("/payment-runs/preview")
def payment_run_preview(payload: PaymentRunCreate | None = None) -> dict:
    decisions_data = all_decisions()
    candidates = payment_run_candidates(decisions_data)
    total = sum(float((d.get("extracted") or {}).get("total") or 0) for d in candidates)
    vendors_included = sorted({((d.get("extracted") or {}).get("vendor") or {}).get("name") or "Unknown" for d in candidates})
    high_value = [d for d in candidates if float((d.get("extracted") or {}).get("total") or 0) >= 100000]
    overrides = [d for d in candidates if d.get("overridden_status") == "APPROVED"]
    return {
        "payment_date": payload.payment_date if payload else datetime.now(timezone.utc).date().isoformat(),
        "invoice_count": len(candidates),
        "total_amount": total,
        "vendor_count": len(vendors_included),
        "vendors": vendors_included,
        "high_value": high_value,
        "overrides": overrides,
        "invoices": candidates,
    }


@app.post("/payment-runs")
def create_payment_run(payload: PaymentRunCreate) -> dict:
    preview = payment_run_preview(payload)
    run_id = str(uuid.uuid4())
    db.save_payment_run({
        "id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "payment_date": preview["payment_date"],
        "total_amount": preview["total_amount"],
        "invoice_count": preview["invoice_count"],
        "vendor_count": preview["vendor_count"],
        "details": {
            "invoices": [d.get("invoice_id") for d in preview["invoices"]],
            "overrides": [d.get("invoice_id") for d in preview["overrides"]],
            "high_value": [d.get("invoice_id") for d in preview["high_value"]],
        },
    })
    return {"id": run_id, "preview": preview, "runs": db.list_payment_runs()}


@app.post("/assistant")
def assistant(payload: AssistantQuery) -> dict:
    return {"answer": answer_question(payload.query, all_decisions())}


@app.get("/invoice/{run_id}/vendor-email")
def vendor_email(run_id: str) -> dict:
    decision = db.get_decision(run_id)
    if not decision:
        raise HTTPException(status_code=404, detail="Run not found.")
    return build_vendor_email_draft(decision.model_dump(mode="json"))


@app.post("/invoice/{run_id}/override")
def override(run_id: str, request: OverrideRequest) -> dict[str, str]:
    ok = db.override_run(run_id, request.new_status, request.override_reason, request.overridden_by)
    if not ok:
        raise HTTPException(status_code=404, detail="Run not found.")
    return {"status": "updated"}
