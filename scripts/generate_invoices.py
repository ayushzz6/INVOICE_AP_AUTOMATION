from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

OUT = Path("data/sample_invoices")
OUT.mkdir(parents=True, exist_ok=True)


def make_invoice(filename: str, vendor: str, tax_id: str, inv_no: str, invoice_date: str, po_ref: str | None, items: list[tuple[str, int, float]], tax_rate: float, bank_account: str, ifsc: str, note: str = "") -> None:
    path = OUT / filename
    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    y = height - 60
    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, y, "INVOICE")
    y -= 38
    c.setFont("Helvetica", 10)
    rows = [
        ("Vendor", vendor),
        ("GSTIN", tax_id),
        ("Invoice No.", inv_no),
        ("Invoice Date", invoice_date),
        ("Due Date", "2026-05-30"),
    ]
    if po_ref:
        rows.append(("PO", po_ref))
    rows.extend([("Bank Account", bank_account), ("IFSC", ifsc)])
    for label, value in rows:
        c.drawString(50, y, f"{label}: {value}")
        y -= 18
    y -= 14
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y, "Line Items")
    y -= 22
    c.setFont("Helvetica", 10)
    subtotal = 0.0
    for desc, qty, unit in items:
        amount = qty * unit
        subtotal += amount
        c.drawString(65, y, f"- {desc} qty {qty} x {unit:,.2f} = {amount:,.2f}")
        y -= 18
    tax = round(subtotal * tax_rate / 100, 2)
    total = round(subtotal + tax, 2)
    y -= 14
    c.drawString(50, y, f"Subtotal: INR {subtotal:,.2f}")
    y -= 18
    c.drawString(50, y, f"Tax Rate: {tax_rate:.2f}%")
    y -= 18
    c.drawString(50, y, f"Tax: INR {tax:,.2f}")
    y -= 18
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, f"Total: INR {total:,.2f}")
    y -= 30
    c.setFont("Helvetica", 9)
    c.drawString(50, y, note)
    c.save()
    print(path)


def main() -> None:
    make_invoice("01_happy_path_acme.pdf", "Acme Office Supplies Pvt Ltd", "29ABCDE1234F1Z5", "INV-2026-010", "2026-04-20", "PO-2026-0001", [("Office supplies bundle", 1, 120000.0)], 0.0, "123456789012", "HDFC0001234")
    make_invoice("02_amount_over_cloudops.pdf", "CloudOps Technologies", "27FGHIJ5678K2L9", "INV-7281", "2026-05-03", "PO-2026-0002", [("Cloud migration sprint", 1, 500000.0)], 0.0, "987654321098", "ICIC0005678", "Amount is intentionally over PO tolerance for review.")
    make_invoice("03_split_po_dataworks.pdf", "DataWorks Analytics Pvt Ltd", "29DATA2026A1Z9", "DW-2026-003", "2026-05-01", "PO-2026-0014", [("Monthly analytics subscription", 1, 50000.0)], 0.0, "555000111222", "SBIN0002222", "Third expected installment under annual PO.")
    make_invoice("04_duplicate_acme.pdf", "Acme Office Supplies Pvt Ltd", "29ABCDE1234F1Z5", "INV-2026-001", "2026-05-05", "PO-2026-0001", [("Office supplies duplicate batch", 1, 130000.0)], 0.0, "123456789012", "HDFC0001234", "Duplicate invoice number with different total.")
    make_invoice("05_missing_po_recurring_saas.pdf", "RecurringSaaS India Pvt Ltd", "07SAAS2026B1Z2", "RS-2026-009", "2026-05-02", None, [("Monthly SaaS licenses", 1, 20000.0)], 0.0, "444333222111", "UTIB0003333", "No PO printed on the invoice.")
    make_invoice("06_scanned_style_facilities.pdf", "FacilitiesCo Services", "27FACIL2026C1Z8", "FAC-2026-018", "2026-05-06", "PO-2026-0030", [("Facility maintenance", 1, 89000.0)], 0.0, "777888999000", "KKBK0004444", "Use this as the printed-and-photographed demo candidate.")


if __name__ == "__main__":
    main()
