from __future__ import annotations

from decimal import Decimal
from difflib import SequenceMatcher

import pandas as pd
try:
    from rapidfuzz import fuzz, process
except ImportError:  # pragma: no cover - exercised only without optional dependency
    fuzz = None
    process = None

from models import db
from models.schemas import ExtractedInvoice, POMatch
from pipeline.normalize import normalize_po, normalize_vendor_name

PO_PATH = "data/pos.csv"


def load_pos() -> pd.DataFrame:
    frame = pd.read_csv(PO_PATH)
    frame["norm_po"] = frame["po_number"].map(normalize_po)
    frame["norm_vendor"] = frame["vendor_name"].map(lambda v: (normalize_vendor_name(v) or "").lower())
    frame["po_date"] = pd.to_datetime(frame["po_date"]).dt.date
    frame["valid_from"] = pd.to_datetime(frame["valid_from"]).dt.date
    frame["valid_to"] = pd.to_datetime(frame["valid_to"]).dt.date
    return frame


def _record(row) -> dict:
    return {k: (v.item() if hasattr(v, "item") else v) for k, v in row.to_dict().items()}


def _with_cumulative(match: POMatch) -> POMatch:
    if match.po_number:
        match.cumulative_invoiced = Decimal(str(db.get_cumulative_invoiced(match.po_number)))
    return match


def _fuzzy_po(query: str, choices: list[str]) -> tuple[str, float] | None:
    if process and fuzz:
        result = process.extractOne(query, choices, scorer=fuzz.ratio)
        return (result[0], float(result[1])) if result else None
    scored = [(choice, SequenceMatcher(None, query, choice).ratio() * 100) for choice in choices]
    return max(scored, key=lambda item: item[1]) if scored else None


def _row_reasons(invoice: ExtractedInvoice, row, *, exact: bool = False, fuzzy_score: float | None = None) -> list[str]:
    reasons: list[str] = []
    if exact:
        reasons.append(f"Invoice cites PO {row['po_number']} explicitly")
    elif fuzzy_score is not None:
        reasons.append(f"PO text on invoice looks like {row['po_number']} (similarity {fuzzy_score:.0f}%)")
    else:
        reasons.append(f"Vendor on invoice matches PO vendor ({row['vendor_name']})")
    po_amount = Decimal(str(row["po_amount"]))
    tolerance = Decimal(str(row["tolerance_pct"])) / Decimal("100")
    diff_pct = abs(invoice.total - po_amount) / po_amount * Decimal("100") if po_amount else Decimal("0")
    if abs(invoice.total - po_amount) <= po_amount * tolerance:
        reasons.append(
            f"Invoice total {invoice.total} is within {row['tolerance_pct']}% tolerance of PO amount {po_amount}"
        )
    elif invoice.total <= po_amount:
        reasons.append(
            f"Invoice total {invoice.total} is {diff_pct:.1f}% below PO amount {po_amount} (fits recurring/partial billing pattern)"
        )
    if invoice.invoice_date and row.get("valid_from") and row.get("valid_to"):
        reasons.append(
            f"Invoice date {invoice.invoice_date} is inside PO validity {row['valid_from']} → {row['valid_to']}"
        )
    if str(row.get("status", "")).upper() == "OPEN":
        reasons.append("PO status is OPEN")
    return reasons


def match_po(invoice: ExtractedInvoice) -> POMatch:
    pos = load_pos()
    po_ref = normalize_po(invoice.po_reference)
    if po_ref:
        exact = pos[pos["norm_po"] == po_ref]
        if len(exact) == 1:
            row = exact.iloc[0]
            return _with_cumulative(POMatch(matched=True, match_type="exact", po_number=row["po_number"], confidence=1.0, notes="PO reference matched exactly.", po_record=_record(row), reasons=_row_reasons(invoice, row, exact=True)))
        choices = pos["po_number"].tolist()
        fuzzy = _fuzzy_po(po_ref, choices)
        if fuzzy and fuzzy[1] >= 85:
            row = pos[pos["po_number"] == fuzzy[0]].iloc[0]
            return _with_cumulative(POMatch(matched=True, match_type="fuzzy_vendor", po_number=row["po_number"], confidence=fuzzy[1] / 100, notes=f"PO reference looked like {po_ref}; fuzzy matched {fuzzy[0]}.", po_record=_record(row), reasons=_row_reasons(invoice, row, fuzzy_score=fuzzy[1])))

    vendor = (normalize_vendor_name(invoice.vendor.name) or "").lower()
    candidates = pos[(pos["norm_vendor"] == vendor) & (pos["status"] == "OPEN")]
    if invoice.invoice_date:
        candidates = candidates[(candidates["valid_from"] <= invoice.invoice_date) & (candidates["valid_to"] >= invoice.invoice_date)]
    scored = []
    for _, row in candidates.iterrows():
        po_amount = Decimal(str(row["po_amount"]))
        tolerance = Decimal(str(row["tolerance_pct"])) / Decimal("100")
        amount_ok = abs(invoice.total - po_amount) <= po_amount * tolerance
        recurring_ok = invoice.total <= po_amount * (Decimal("1") + tolerance)
        confidence = Decimal("0.85") if amount_ok else Decimal("0.72") if recurring_ok else Decimal("0.45")
        if recurring_ok:
            scored.append((confidence, row))
    if len(scored) == 1:
        confidence, row = scored[0]
        return _with_cumulative(POMatch(matched=True, match_type="vendor_amount_date", po_number=row["po_number"], confidence=float(confidence), notes="No PO reference on invoice; inferred from vendor, amount, and validity window.", po_record=_record(row), reasons=_row_reasons(invoice, row)))
    if len(scored) > 1:
        best = sorted(scored, key=lambda item: item[0], reverse=True)[0]
        return _with_cumulative(POMatch(matched=True, match_type="multiple", po_number=best[1]["po_number"], confidence=float(best[0]), notes="Multiple possible POs found; selected best candidate but requires review.", po_record=_record(best[1]), reasons=_row_reasons(invoice, best[1]) + [f"{len(scored)} candidate POs matched vendor+amount+date — best chosen"]))

    return POMatch(matched=False, match_type="none", confidence=0.0, notes="No matching PO found.", reasons=["Vendor + amount + date did not narrow down to any open PO"])
