from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from difflib import SequenceMatcher

import pandas as pd

from models import db
from models.schemas import DuplicateCandidate, ExtractedInvoice, POMatch, ValidationResult
from pipeline.normalize import normalize_vendor_name


def _coerce_date(value) -> date | None:
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except Exception:
        try:
            return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
        except Exception:
            return None


def find_duplicate_candidates(invoice: ExtractedInvoice, po_match: POMatch) -> list[DuplicateCandidate]:
    candidates = db.find_similar_invoices(
        vendor_name=invoice.vendor.name,
        invoice_number=invoice.invoice_number,
        total=float(invoice.total) if invoice.total else None,
        bank_account=invoice.bank_account,
        po_reference=po_match.po_number,
        invoice_date=str(invoice.invoice_date) if invoice.invoice_date else None,
    )
    inv_date = invoice.invoice_date
    inv_total = float(invoice.total) if invoice.total else None
    out: list[DuplicateCandidate] = []
    for row in candidates:
        score = 0.0
        reasons: list[str] = []
        if invoice.invoice_number and row.get("invoice_number"):
            ratio = SequenceMatcher(
                None, str(invoice.invoice_number).lower(), str(row["invoice_number"]).lower()
            ).ratio()
            if invoice.invoice_number == row["invoice_number"]:
                reasons.append("identical invoice number")
                score = max(score, 1.0)
            elif ratio >= 0.85:
                reasons.append(f"invoice number similarity {ratio*100:.0f}%")
                score = max(score, ratio)
        if inv_total is not None and row.get("total_amount"):
            try:
                diff_pct = abs(inv_total - float(row["total_amount"])) / max(float(row["total_amount"]), 1.0)
            except Exception:
                diff_pct = 1.0
            if diff_pct <= 0.02:
                reasons.append(f"amount within {diff_pct*100:.1f}% of prior invoice")
                score = max(score, 0.85 - min(diff_pct * 5, 0.2))
        if inv_date and row.get("uploaded_at"):
            other = _coerce_date(row.get("uploaded_at"))
            if other and abs((inv_date - other).days) <= 14:
                reasons.append(f"prior invoice received within 14 days of this one")
                score = max(score, 0.6)
        if po_match.po_number and row.get("po_reference") == po_match.po_number:
            reasons.append("same PO reference")
            score = max(score, 0.55)
        if score >= 0.55 and reasons:
            out.append(
                DuplicateCandidate(
                    run_id=row["id"],
                    invoice_number=row.get("invoice_number"),
                    vendor_name=row.get("vendor_name"),
                    total_amount=row.get("total_amount"),
                    uploaded_at=row.get("uploaded_at"),
                    similarity=round(score, 2),
                    reason="; ".join(reasons),
                )
            )
    out.sort(key=lambda d: d.similarity, reverse=True)
    return out[:5]

VENDORS_PATH = "data/approved_vendors.csv"


def load_vendors() -> pd.DataFrame:
    frame = pd.read_csv(VENDORS_PATH)
    frame["norm_vendor"] = frame["vendor_name"].map(lambda v: (normalize_vendor_name(v) or "").lower())
    frame["active"] = frame["active"].astype(str).str.lower().eq("true")
    frame["bank_account"] = frame["bank_account"].astype(str)
    return frame


def result(rule_id: str, name: str, passed: bool, severity: str, detail: str) -> ValidationResult:
    return ValidationResult(rule_id=rule_id, rule_name=name, passed=passed, severity=severity, detail=detail)


def validate_invoice(invoice: ExtractedInvoice, po_match: POMatch) -> list[ValidationResult]:
    vendors = load_vendors()
    vendor_norm = (normalize_vendor_name(invoice.vendor.name) or "").lower()
    vendor_rows = vendors[(vendors["norm_vendor"] == vendor_norm) & vendors["active"]]
    approved_vendor = len(vendor_rows) > 0
    po = po_match.po_record or {}

    required_missing = [f for f in ["invoice_number", "invoice_date", "vendor.name", "total"] if f in invoice.missing_fields]
    if not invoice.invoice_number:
        required_missing.append("invoice_number")
    if not invoice.invoice_date:
        required_missing.append("invoice_date")
    if not invoice.vendor.name:
        required_missing.append("vendor.name")
    if not invoice.total:
        required_missing.append("total")

    validations = [
        result("R1", "Required fields present", not required_missing, "critical", "Missing: " + ", ".join(sorted(set(required_missing))) if required_missing else "Invoice number, date, vendor, and total are present."),
        result("R2", "Vendor in approved list", approved_vendor, "critical", f"Vendor {invoice.vendor.name or 'unknown'} is {'approved' if approved_vendor else 'not approved or inactive'}."),
        result("R3", "PO reference resolves", po_match.matched, "critical", po_match.notes),
    ]

    if po:
        po_amount = Decimal(str(po["po_amount"]))
        tolerance = Decimal(str(po["tolerance_pct"])) / Decimal("100")
        recurring_context = po_match.match_type == "vendor_amount_date" or any(
            token in str(po.get("description", "")).lower()
            for token in ("recurring", "subscription", "monthly", "annual")
        )
        if recurring_context:
            within = invoice.total <= po_amount * (Decimal("1") + tolerance)
            detail = (
                f"Invoice total {invoice.total} is within the remaining PO envelope for "
                f"recurring/subscription PO {po.get('po_number')}; PO amount {po_amount}, "
                f"tolerance {po['tolerance_pct']}%."
            )
        else:
            delta = abs(invoice.total - po_amount)
            within = delta / po_amount <= tolerance if po_amount else False
            detail = f"Invoice total {invoice.total} vs PO {po_amount}; tolerance {po['tolerance_pct']}%."
        validations.append(result("R4", "Total within tolerance", within, "warning", detail))
    else:
        validations.append(result("R4", "Total within tolerance", False, "warning", "Cannot compare total because no PO matched."))

    prior = db.find_prior_invoice(invoice.invoice_number, invoice.vendor.name)
    fuzzy_dups = find_duplicate_candidates(invoice, po_match)
    high_conf = [c for c in fuzzy_dups if c.similarity >= 0.85]
    duplicate_ok = prior is None and not high_conf
    if prior:
        dup_detail = f"Duplicate candidate: prior run {prior['id']} for {prior['total_amount']} on {prior['uploaded_at']}."
    elif high_conf:
        top = high_conf[0]
        dup_detail = (
            f"Possible duplicate of run {top.run_id} (invoice {top.invoice_number}, "
            f"{top.vendor_name}, similarity {int(top.similarity*100)}%): {top.reason}."
        )
    elif fuzzy_dups:
        dup_detail = f"No exact duplicate, but {len(fuzzy_dups)} near-match(es) found for review."
    else:
        dup_detail = "No prior invoice with same vendor and invoice number; no near-duplicates."
    validations.append(result("R5", "Not a duplicate", duplicate_ok, "critical", dup_detail))

    line_sum = sum((item.amount for item in invoice.line_items), Decimal("0"))
    line_ok = not invoice.line_items or abs(line_sum - (invoice.subtotal or line_sum)) <= Decimal("1")
    total_ok = True
    if invoice.subtotal is not None and invoice.tax_amount is not None:
        total_ok = abs((invoice.subtotal + invoice.tax_amount) - invoice.total) <= Decimal("1")
    validations.append(result("R6", "Line item math", line_ok and total_ok, "warning", f"Line items sum to {line_sum}; subtotal={invoice.subtotal}; tax={invoice.tax_amount}; total={invoice.total}."))

    if po:
        po_amount = Decimal(str(po["po_amount"]))
        tolerance = Decimal(str(po["tolerance_pct"])) / Decimal("100")
        cumulative = po_match.cumulative_invoiced + invoice.total
        cumulative_ok = cumulative <= po_amount * (Decimal("1") + tolerance)
        validations.append(result("R7", "Cumulative within PO", cumulative_ok, "warning", f"Prior approved total {po_match.cumulative_invoiced}; with this invoice {cumulative}; PO cap incl tolerance {po_amount * (Decimal('1') + tolerance)}."))
        currency_ok = invoice.currency == po.get("currency")
        validations.append(result("R8", "Currency matches PO", currency_ok, "warning", f"Invoice currency {invoice.currency}; PO currency {po.get('currency')}."))
    else:
        validations.append(result("R7", "Cumulative within PO", False, "warning", "Cannot check cumulative spend because no PO matched."))
        validations.append(result("R8", "Currency matches PO", False, "warning", "Cannot compare currency because no PO matched."))

    tax_rate = invoice.tax_rate if invoice.tax_rate is not None else Decimal("0")
    validations.append(result("R9", "Tax rate sensible", Decimal("0") <= tax_rate <= Decimal("30"), "info", f"Tax rate is {tax_rate}%."))

    if approved_vendor and invoice.bank_account:
        expected = str(vendor_rows.iloc[0]["bank_account"])
        bank_ok = invoice.bank_account == expected
        bank_detail = "Bank account matches approved vendor record." if bank_ok else f"Bank account {invoice.bank_account} does not match approved account {expected}."
    elif approved_vendor:
        bank_ok = False
        bank_detail = "Invoice does not include a bank account to verify."
    else:
        bank_ok = False
        bank_detail = "Cannot verify bank account because vendor is not approved."
    validations.append(result("R10", "Bank account matches approved", bank_ok, "critical", bank_detail))

    validations.append(result("R11", "Extraction confidence acceptable", invoice.extraction_confidence >= 0.7, "warning", f"Extraction confidence is {invoice.extraction_confidence:.2f}."))
    return validations
