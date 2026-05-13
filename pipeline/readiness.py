from __future__ import annotations

from decimal import Decimal

from models.schemas import (
    ExtractedInvoice,
    PaymentReadiness,
    POMatch,
    QueueCategory,
    ReadinessCheck,
    ValidationResult,
)


HIGH_VALUE_THRESHOLD = Decimal("400000")


def _rule(validations: list[ValidationResult], rule_id: str) -> ValidationResult | None:
    return next((v for v in validations if v.rule_id == rule_id), None)


def _check(validations: list[ValidationResult], key: str, label: str, rule_id: str, fallback: str) -> ReadinessCheck:
    rule = _rule(validations, rule_id)
    if rule is None:
        return ReadinessCheck(key=key, label=label, passed=False, detail=fallback)
    return ReadinessCheck(key=key, label=label, passed=rule.passed, detail=rule.detail)


def compute_readiness(
    extracted: ExtractedInvoice,
    po_match: POMatch,
    validations: list[ValidationResult],
    status: str,
) -> PaymentReadiness:
    checks: list[ReadinessCheck] = [
        _check(validations, "vendor", "Vendor verified", "R2", "Vendor approval status unknown."),
        _check(validations, "po", "PO matched", "R3", "PO match status unknown."),
        _check(validations, "bank", "Bank account verified", "R10", "Bank account verification unknown."),
        _check(validations, "duplicate", "Duplicate check passed", "R5", "Duplicate status unknown."),
        _check(validations, "tolerance", "Amount within tolerance", "R4", "Tolerance check unknown."),
        _check(validations, "cumulative", "PO budget not exceeded", "R7", "Cumulative spend check unknown."),
    ]

    approval_required = ReadinessCheck(
        key="approval",
        label="Approval required",
        passed=status == "APPROVED",
        detail=(
            "Auto-approved by AP automation."
            if status == "APPROVED"
            else f"Manager review required before payment ({status.lower()})."
        ),
    )
    checks.append(approval_required)

    passed_count = sum(1 for c in checks if c.passed)
    score = round((passed_count / len(checks)) * 100)

    blockers = [c.label for c in checks if not c.passed]
    queue = _queue_category(extracted, po_match, validations, status, blockers)
    approver = _approver(extracted, po_match, validations, queue)
    recommendation = _recommendation(extracted, po_match, validations, status, queue, blockers)

    return PaymentReadiness(
        score=score,
        checks=checks,
        recommendation=recommendation,
        approver=approver,
        queue=queue,
        blockers=blockers,
    )


def _queue_category(
    extracted: ExtractedInvoice,
    po_match: POMatch,
    validations: list[ValidationResult],
    status: str,
    blockers: list[str],
) -> QueueCategory:
    duplicate_rule = _rule(validations, "R5")
    bank_rule = _rule(validations, "R10")
    vendor_rule = _rule(validations, "R2")
    tolerance_rule = _rule(validations, "R4")
    cumulative_rule = _rule(validations, "R7")
    po_rule = _rule(validations, "R3")

    if status == "REJECTED":
        if duplicate_rule and not duplicate_rule.passed:
            return "Possible Duplicate"
        if (bank_rule and not bank_rule.passed) or (vendor_rule and not vendor_rule.passed):
            return "Vendor/Bank Risk"
        return "Payment Blocked"

    if cumulative_rule and not cumulative_rule.passed:
        return "Over PO Limit"
    if po_rule and not po_rule.passed:
        return "Needs Procurement Review"
    if po_match.match_type in {"vendor_amount_date", "multiple", "fuzzy_vendor"}:
        return "Needs Procurement Review"
    if tolerance_rule and not tolerance_rule.passed:
        return "Over PO Limit"
    if duplicate_rule and not duplicate_rule.passed:
        return "Possible Duplicate"
    if bank_rule and not bank_rule.passed:
        return "Vendor/Bank Risk"
    if status == "FLAGGED" or blockers:
        return "Needs AP Review"
    return "Ready for Payment"


def _approver(
    extracted: ExtractedInvoice,
    po_match: POMatch,
    validations: list[ValidationResult],
    queue: QueueCategory,
) -> str:
    if queue == "Over PO Limit":
        return "Procurement Owner"
    if queue == "Needs Procurement Review":
        return "Procurement Owner"
    if queue == "Vendor/Bank Risk":
        return "Vendor Master Team"
    if queue == "Possible Duplicate":
        return "AP Manager"
    if queue == "Payment Blocked":
        return "Finance Controller"
    if extracted.total and extracted.total >= HIGH_VALUE_THRESHOLD:
        return "Finance Controller"
    if queue == "Needs AP Review":
        return "AP Manager"
    return "Auto-approved"


def _recommendation(
    extracted: ExtractedInvoice,
    po_match: POMatch,
    validations: list[ValidationResult],
    status: str,
    queue: QueueCategory,
    blockers: list[str],
) -> str:
    vendor = extracted.vendor.name or "the vendor"
    currency = extracted.currency or "INR"
    total = extracted.total or Decimal("0")

    if status == "APPROVED" and queue == "Ready for Payment":
        return f"Safe to pay. Vendor, PO, bank account, and duplicate checks passed for invoice {extracted.invoice_number} ({currency} {total:,.2f})."

    tolerance_rule = _rule(validations, "R4")
    if queue == "Over PO Limit" and po_match.po_record:
        po_amount = Decimal(str(po_match.po_record["po_amount"]))
        diff = total - po_amount
        if diff > 0:
            return f"Do not pay yet. Invoice exceeds PO {po_match.po_number} by {currency} {diff:,.2f}. Ask procurement to approve variance."
        return f"Do not pay yet. Cumulative spend on PO {po_match.po_number} is over budget. Procurement must approve."

    duplicate_rule = _rule(validations, "R5")
    if queue == "Possible Duplicate" and duplicate_rule:
        return f"Hold payment. {duplicate_rule.detail} Confirm with {vendor} before paying."

    bank_rule = _rule(validations, "R10")
    if queue == "Vendor/Bank Risk":
        if bank_rule and not bank_rule.passed:
            return f"Do not pay yet. {bank_rule.detail} Verify with vendor master team."
        return f"Do not pay yet. Vendor {vendor} failed risk checks. Verify with vendor master team."

    if queue == "Needs Procurement Review":
        if po_match.po_number and not extracted.po_reference:
            return (
                f"Hold payment. Invoice does not print a PO reference, but it was inferred as "
                f"{po_match.po_number} from vendor, date, and amount. Ask procurement to confirm "
                "the PO before payment."
            )
        return f"Hold payment. PO link is weak for invoice {extracted.invoice_number}. Ask procurement to confirm the PO."

    if queue == "Payment Blocked":
        return f"Reject invoice {extracted.invoice_number or 'without a number'} from {vendor}. Critical controls failed: " + "; ".join(blockers[:3])

    return f"Needs AP review. Issues to resolve before payment: " + ("; ".join(blockers[:3]) if blockers else "see audit trail")
