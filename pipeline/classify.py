from __future__ import annotations

from pathlib import Path

import fitz


def classify_pdf(pdf_path: str | Path) -> str:
    doc = fitz.open(str(pdf_path))
    text = " ".join(page.get_text() or "" for page in doc)
    return "text" if len(text.strip()) > 50 else "scanned"


def page_count(pdf_path: str | Path) -> int:
    return fitz.open(str(pdf_path)).page_count
