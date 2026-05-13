from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from models.schemas import ExtractedInvoice


def normalize_vendor_name(name: str | None) -> str | None:
    if not name:
        return None
    name = re.sub(r"\s+", " ", name.strip())
    return name.title().replace("Pvt Ltd", "Pvt Ltd").replace("Llp", "LLP")


def normalize_po(value: str | None) -> str | None:
    if not value:
        return None
    compact = re.sub(r"[^A-Za-z0-9]", "", value).upper()
    match = re.search(r"PO(\d{4})(\d{4})", compact)
    if match:
        return f"PO-{match.group(1)}-{match.group(2)}"
    return value.strip().upper()


def normalize_tax_id(value: str | None) -> str | None:
    if not value:
        return None
    return re.sub(r"\s+", "", value).upper()


def normalize_currency(value: str | None) -> str:
    if not value:
        return "INR"
    return value.upper().strip()[:3]


def normalize_amount(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    cleaned = re.sub(r"[^0-9.\-]", "", str(value))
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def normalize_invoice(invoice: ExtractedInvoice) -> ExtractedInvoice:
    data = invoice.model_dump()
    data["vendor"]["name"] = normalize_vendor_name(invoice.vendor.name)
    data["vendor"]["tax_id"] = normalize_tax_id(invoice.vendor.tax_id)
    data["po_reference"] = normalize_po(invoice.po_reference)
    data["currency"] = normalize_currency(invoice.currency)
    data["bank_account"] = re.sub(r"\D", "", invoice.bank_account or "") or None
    data["bank_ifsc"] = (invoice.bank_ifsc or "").strip().upper() or None
    return ExtractedInvoice.model_validate(data)
