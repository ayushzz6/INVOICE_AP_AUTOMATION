from __future__ import annotations

from decimal import Decimal

from models.schemas import ExtractedInvoice, POMatch, VendorInfo
from pipeline.decide import decide
from pipeline.match import match_po
from pipeline.validate import validate_invoice


def test_exact_po_match() -> None:
    invoice = ExtractedInvoice(
        invoice_number="T-1",
        invoice_date="2026-04-20",
        vendor=VendorInfo(name="Acme Office Supplies Pvt Ltd"),
        po_reference="PO20260001",
        total=Decimal("125000"),
        bank_account="123456789012",
        extraction_confidence=0.95,
    )
    match = match_po(invoice)
    assert match.matched is True
    assert match.match_type == "exact"
    assert match.po_number == "PO-2026-0001"


def test_missing_po_inferred_match_is_flagged() -> None:
    invoice = ExtractedInvoice(
        invoice_number="RS-1",
        invoice_date="2026-05-02",
        vendor=VendorInfo(name="RecurringSaaS India Pvt Ltd"),
        po_reference=None,
        total=Decimal("20000"),
        bank_account="444333222111",
        extraction_confidence=0.93,
        missing_fields=["po_reference"],
    )
    match = match_po(invoice)
    validations = validate_invoice(invoice, match)
    decision = decide("test-run", invoice, match, validations, 100)
    assert match.matched is True
    assert match.match_type == "vendor_amount_date"
    assert decision.status == "FLAGGED"
    assert decision.readiness is not None
    assert decision.readiness.queue == "Needs Procurement Review"
    assert "does not print a PO reference" in decision.readiness.recommendation


def test_unapproved_vendor_rejected() -> None:
    invoice = ExtractedInvoice(
        invoice_number="BAD-1",
        invoice_date="2026-05-02",
        vendor=VendorInfo(name="Unknown Vendor"),
        po_reference="PO-2026-0001",
        total=Decimal("1000"),
        extraction_confidence=0.9,
    )
    match = POMatch(matched=True, match_type="exact", po_number="PO-2026-0001", confidence=1, notes="test", po_record={"po_amount": 125000, "tolerance_pct": 3, "currency": "INR"})
    validations = validate_invoice(invoice, match)
    decision = decide("test-run-2", invoice, match, validations, 100)
    assert any(v.rule_id == "R2" and not v.passed for v in validations)
    assert decision.status == "REJECTED"


def test_readiness_score_and_queue_for_approved_invoice() -> None:
    invoice = ExtractedInvoice(
        invoice_number="T-DESIGNHUB-001",
        invoice_date="2026-05-02",
        vendor=VendorInfo(name="DesignHub Studio", tax_id="29DESGN2026J1Z0"),
        po_reference="PO-2026-0068",
        total=Decimal("135000"),
        bank_account="707070707070",
        extraction_confidence=0.95,
    )
    match = match_po(invoice)
    validations = validate_invoice(invoice, match)
    decision = decide("test-readiness-1", invoice, match, validations, 100)
    assert decision.readiness is not None
    assert decision.readiness.recommendation
    assert decision.readiness.score >= 70


def test_readiness_over_po_routes_to_procurement() -> None:
    invoice = ExtractedInvoice(
        invoice_number="T-DESIGNHUB-002",
        invoice_date="2026-05-02",
        vendor=VendorInfo(name="DesignHub Studio", tax_id="29DESGN2026J1Z0"),
        po_reference="PO-2026-0068",
        total=Decimal("220000"),
        bank_account="707070707070",
        extraction_confidence=0.95,
    )
    match = match_po(invoice)
    validations = validate_invoice(invoice, match)
    decision = decide("test-readiness-2", invoice, match, validations, 100)
    assert decision.readiness is not None
    assert decision.readiness.queue == "Over PO Limit"
    assert decision.readiness.approver in {"Procurement Owner", "Finance Controller"}
