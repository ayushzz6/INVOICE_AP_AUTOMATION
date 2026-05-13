from __future__ import annotations

from datetime import datetime, timezone

from models.schemas import Decision, DuplicateCandidate, ExtractedInvoice, POMatch, ValidationResult
from pipeline.readiness import compute_readiness


def _failed(validations: list[ValidationResult], severity: str) -> list[ValidationResult]:
    return [v for v in validations if not v.passed and v.severity == severity]


def build_reasoning(status: str, validations: list[ValidationResult], extracted: ExtractedInvoice, po_match: POMatch) -> str:
    vendor = extracted.vendor.name or "Unknown vendor"
    total = f"{extracted.currency} {extracted.total:,.2f}"
    failed_critical = _failed(validations, "critical")
    failed_warning = _failed(validations, "warning")
    po_text = po_match.po_number or "no matched PO"
    if status == "APPROVED":
        remaining = ""
        if po_match.po_record:
            po_amount = float(po_match.po_record["po_amount"])
            remaining_amount = po_amount - float(po_match.cumulative_invoiced) - float(extracted.total)
            remaining = f" About INR {remaining_amount:,.2f} remains on the PO after this invoice."
        return f"Invoice {extracted.invoice_number} from {vendor} for {total} matches {po_text}, the vendor is approved, and the bank account matches the vendor master. Approve for payment and schedule according to payment terms.{remaining}"
    if status == "REJECTED":
        reasons = "; ".join(v.detail for v in failed_critical[:3])
        return f"Reject invoice {extracted.invoice_number or 'without a number'} from {vendor} for {total}. {reasons} Escalate to compliance or procurement before any payment is made."
    reasons = "; ".join(v.detail for v in (failed_warning or failed_critical)[:3])
    return f"Flag invoice {extracted.invoice_number or 'without a number'} from {vendor} for review before payment. It is linked to {po_text}, but {reasons} Ask the AP manager or procurement owner to confirm the exception."


def next_action(status: str) -> str:
    if status == "APPROVED":
        return "Approve for payment. Schedule per payment terms."
    if status == "REJECTED":
        return "Do not pay. Escalate to compliance/procurement with the audit trail."
    return "Route to AP Manager for human review before payment."


def decide(
    invoice_id: str,
    extracted: ExtractedInvoice,
    po_match: POMatch,
    validations: list[ValidationResult],
    processing_time_ms: int,
    duplicate_candidates: list[DuplicateCandidate] | None = None,
    stored_path: str | None = None,
) -> Decision:
    criticals_failed = _failed(validations, "critical")
    warnings_failed = _failed(validations, "warning")
    if criticals_failed:
        status = "REJECTED"
    elif warnings_failed or po_match.match_type in {"vendor_amount_date", "multiple"} or "po_reference" in extracted.missing_fields:
        status = "FLAGGED"
    else:
        status = "APPROVED"
    confidence = max(0.0, min(1.0, extracted.extraction_confidence * (po_match.confidence or 0.5)))
    readiness = compute_readiness(extracted, po_match, validations, status)
    if po_match.match_type in {"vendor_amount_date", "multiple"} and extracted.field_status:
        extracted.field_status["po_reference"] = "inferred"  # type: ignore[index]
    return Decision(
        invoice_id=invoice_id,
        status=status,
        confidence=confidence,
        reasoning=build_reasoning(status, validations, extracted, po_match),
        next_action=readiness.recommendation,
        extracted=extracted,
        po_match=po_match,
        validations=validations,
        processing_time_ms=processing_time_ms,
        timestamp=datetime.now(timezone.utc),
        readiness=readiness,
        duplicate_candidates=duplicate_candidates or [],
        stored_path=stored_path,
    )
