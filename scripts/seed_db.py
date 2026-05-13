from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models import db
from models.schemas import Decision, ExtractedInvoice, POMatch, ValidationResult, VendorInfo


def make_decision(run_id: str, filename: str, vendor: str, invoice_number: str, total: Decimal, po: str) -> Decision:
    extracted = ExtractedInvoice(
        invoice_number=invoice_number,
        invoice_date="2026-04-25",
        vendor=VendorInfo(name=vendor),
        po_reference=po,
        total=total,
        currency="INR",
        bank_account="555000111222" if "DataWorks" in vendor else "123456789012",
        extraction_confidence=0.95,
    )
    po_match = POMatch(matched=True, match_type="exact", po_number=po, confidence=1.0, notes="Seeded prior approved invoice.")
    validations = [ValidationResult(rule_id="SEED", rule_name="Seeded historical run", passed=True, severity="info", detail="Used for split PO and duplicate edge cases.")]
    decision = Decision(
        invoice_id=run_id,
        status="APPROVED",
        confidence=0.95,
        reasoning="Seeded prior approved invoice for demo state.",
        next_action="Already approved.",
        extracted=extracted,
        po_match=po_match,
        validations=validations,
        processing_time_ms=80,
        timestamp=datetime.now(timezone.utc),
    )
    db.save_decision(decision, filename, [])
    return decision


def main() -> None:
    db.init_db()
    make_decision("seed-split-1", "seed_split_1.pdf", "DataWorks Analytics Pvt Ltd", "DW-2026-001", Decimal("50000"), "PO-2026-0014")
    make_decision("seed-split-2", "seed_split_2.pdf", "DataWorks Analytics Pvt Ltd", "DW-2026-002", Decimal("50000"), "PO-2026-0014")
    make_decision("seed-duplicate-acme", "seed_duplicate_acme.pdf", "Acme Office Supplies Pvt Ltd", "INV-2026-001", Decimal("125000"), "PO-2026-0001")
    print("Seeded split-PO and duplicate-history demo records.")


if __name__ == "__main__":
    main()
