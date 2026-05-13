from __future__ import annotations

import json
import os
import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import fitz

from models.schemas import ExtractedInvoice, LineItem, VendorInfo


def _pdf_text(pdf_path: str | Path) -> str:
    doc = fitz.open(str(pdf_path))
    return "\n".join(page.get_text() or "" for page in doc)


def _search(pattern: str, text: str, default: str | None = None) -> str | None:
    match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
    return match.group(1).strip() if match else default


def _date(value: str | None) -> date | None:
    if not value:
        return None
    for pattern in (r"(\d{4})-(\d{2})-(\d{2})", r"(\d{2})/(\d{2})/(\d{4})"):
        match = re.match(pattern, value.strip())
        if match and pattern.startswith("(\\d{4}"):
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if match:
            return date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
    return None


def _amount(value: str | None) -> Decimal | None:
    if not value:
        return None
    cleaned = re.sub(r"[^0-9.\-]", "", value)
    return Decimal(cleaned) if cleaned else None


def fallback_extract(pdf_path: str | Path, source_type: str) -> ExtractedInvoice:
    text = _pdf_text(pdf_path)
    filename = Path(pdf_path).stem.lower()
    vendor_name = _search(r"Vendor:\s*(.+)", text) or _search(r"Bill From:\s*(.+)", text)
    invoice_number = _search(r"Invoice(?:\s+No\.?| Number)?:\s*([A-Za-z0-9\-]+)", text)
    invoice_date = _date(_search(r"Invoice Date:\s*([0-9\-/]+)", text))
    due_date = _date(_search(r"Due Date:\s*([0-9\-/]+)", text))
    po_reference = _search(r"(?:PO|Order Ref|Reference):\s*([A-Za-z0-9\-]+)", text)
    tax_id = _search(r"(?:GSTIN|Tax ID):\s*([A-Z0-9]+)", text)
    bank_account = _search(r"Bank Account:\s*([0-9]+)", text)
    bank_ifsc = _search(r"IFSC:\s*([A-Z0-9]+)", text)
    subtotal = _amount(_search(r"Subtotal:\s*(?:INR|Rs\.?)?\s*([0-9,.]+)", text))
    tax_amount = _amount(_search(r"Tax(?: Amount)?:\s*(?:INR|Rs\.?)?\s*([0-9,.]+)", text))
    tax_rate = _amount(_search(r"Tax Rate:\s*([0-9.]+)%", text))
    total = _amount(_search(r"Total:\s*(?:INR|Rs\.?)?\s*([0-9,.]+)", text))

    line_items: list[LineItem] = []
    for line in text.splitlines():
        match = re.match(r"\s*-\s*(.+?)\s+qty\s+([0-9.]+)\s+x\s+([0-9,.]+)\s+=\s+([0-9,.]+)", line, re.I)
        if match:
            line_items.append(
                LineItem(
                    description=match.group(1),
                    quantity=Decimal(match.group(2)),
                    unit_price=Decimal(match.group(3).replace(",", "")),
                    amount=Decimal(match.group(4).replace(",", "")),
                )
            )

    if total is None:
        total = Decimal("0")
    if not line_items and total:
        line_items.append(LineItem(description="Invoice charges", amount=total))

    tracked = {
        "invoice_number": invoice_number,
        "invoice_date": invoice_date,
        "due_date": due_date,
        "vendor.name": vendor_name,
        "vendor.tax_id": tax_id,
        "po_reference": po_reference,
        "total": total if total else None,
        "subtotal": subtotal,
        "tax_amount": tax_amount,
        "bank_account": bank_account,
        "bank_ifsc": bank_ifsc,
    }
    missing = [name for name, value in tracked.items() if value is None]
    field_status: dict[str, str] = {
        name: ("extracted" if value is not None else "missing") for name, value in tracked.items()
    }
    if total and subtotal and tax_amount and abs((subtotal + tax_amount) - total) > Decimal("1"):
        field_status["total"] = "suspicious"

    confidence = 0.92 if source_type == "text" else 0.74
    if missing:
        confidence -= min(len(missing) * 0.08, 0.25)

    return ExtractedInvoice(
        invoice_number=invoice_number,
        invoice_date=invoice_date,
        due_date=due_date,
        vendor=VendorInfo(name=vendor_name, tax_id=tax_id),
        po_reference=po_reference,
        line_items=line_items,
        subtotal=subtotal,
        tax_amount=tax_amount,
        tax_rate=tax_rate,
        total=total,
        currency="INR",
        bank_account=bank_account,
        bank_ifsc=bank_ifsc,
        extraction_confidence=max(confidence, 0.35),
        missing_fields=missing,
        raw_notes=f"Extracted with local deterministic parser from {filename}; set GEMINI_API_KEY for Gemini PDF extraction.",
        source_type=source_type,
        field_status=field_status,  # type: ignore[arg-type]
    )


def _strip_json_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned.removeprefix("```json").strip()
    elif cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```").strip()
    if cleaned.endswith("```"):
        cleaned = cleaned.removesuffix("```").strip()
    return cleaned


def _extract_json_object(text: str) -> str:
    """Return the first balanced JSON object from a model response."""
    start = text.find("{")
    if start == -1:
        return text
    depth = 0
    in_string = False
    escaped = False
    for idx, char in enumerate(text[start:], start=start):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : idx + 1]
    return text[start:]


def _escape_control_chars_in_strings(text: str) -> str:
    """Gemini can occasionally emit literal newlines inside JSON strings."""
    out: list[str] = []
    in_string = False
    escaped = False
    for char in text:
        if escaped:
            out.append(char)
            escaped = False
            continue
        if char == "\\":
            out.append(char)
            escaped = True
            continue
        if char == '"':
            out.append(char)
            in_string = not in_string
            continue
        if in_string and char == "\n":
            out.append("\\n")
        elif in_string and char == "\r":
            out.append("\\r")
        elif in_string and char == "\t":
            out.append("\\t")
        else:
            out.append(char)
    return "".join(out)


def _coerce_json(text: str) -> dict[str, Any]:
    cleaned = _extract_json_object(_strip_json_fences(text))
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        repaired = _escape_control_chars_in_strings(cleaned)
        return json.loads(repaired)


def gemini_extract(pdf_path: str | Path, source_type: str) -> ExtractedInvoice | None:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        from google import genai
        from google.genai import types

        prompt = Path("prompts/extraction.txt").read_text(encoding="utf-8")
        pdf_bytes = Path(pdf_path).read_bytes()
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-3-flash-preview"),
            contents=[
                types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                prompt,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0,
                max_output_tokens=4096,
            ),
        )
        data = _coerce_json(response.text or "")
        data["source_type"] = source_type
        invoice = ExtractedInvoice.model_validate(data)
        if not invoice.field_status:
            tracked = {
                "invoice_number": invoice.invoice_number,
                "invoice_date": invoice.invoice_date,
                "due_date": invoice.due_date,
                "vendor.name": invoice.vendor.name,
                "vendor.tax_id": invoice.vendor.tax_id,
                "po_reference": invoice.po_reference,
                "total": invoice.total if invoice.total else None,
                "subtotal": invoice.subtotal,
                "tax_amount": invoice.tax_amount,
                "bank_account": invoice.bank_account,
                "bank_ifsc": invoice.bank_ifsc,
            }
            invoice.field_status = {  # type: ignore[assignment]
                name: ("extracted" if value is not None else "missing") for name, value in tracked.items()
            }
        return invoice
    except Exception as exc:
        local = fallback_extract(pdf_path, source_type)
        local.raw_notes = f"Gemini extraction failed; local fallback used. Error: {exc}"
        return local


def extract_invoice(pdf_path: str | Path, source_type: str) -> ExtractedInvoice:
    return gemini_extract(pdf_path, source_type) or fallback_extract(pdf_path, source_type)
