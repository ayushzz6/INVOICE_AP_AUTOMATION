from __future__ import annotations

import shutil
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from models import db
from models.schemas import Decision, ProgressEvent
from pipeline.classify import classify_pdf, page_count
from pipeline.decide import decide
from pipeline.extract import extract_invoice
from pipeline.match import match_po
from pipeline.normalize import normalize_invoice
from pipeline.validate import find_duplicate_candidates, validate_invoice

UPLOAD_DIR = Path("data/uploads")


@contextmanager
def stage(events: list[ProgressEvent], run_id: str, name: str, input_summary: str | None = None) -> Iterator[ProgressEvent]:
    event = ProgressEvent(run_id=run_id, stage_name=name, status="running", started_at=db.utc_now(), input_summary=input_summary)
    events.append(event)
    try:
        yield event
        event.status = "completed"
        event.finished_at = db.utc_now()
    except Exception as exc:
        event.status = "failed"
        event.error = str(exc)
        event.finished_at = db.utc_now()
        raise


def process_invoice(pdf_path: str | Path, original_filename: str | None = None) -> tuple[Decision, list[ProgressEvent]]:
    db.init_db()
    run_id = str(uuid.uuid4())
    source = Path(pdf_path)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored_path = UPLOAD_DIR / f"{run_id}-{source.name}"
    if source.resolve() != stored_path.resolve():
        shutil.copyfile(source, stored_path)
    filename = original_filename or source.name
    events: list[ProgressEvent] = []
    started = time.perf_counter()

    with stage(events, run_id, "Classify", filename) as event:
        source_type = classify_pdf(stored_path)
        event.output_summary = f"{source_type} PDF, {page_count(stored_path)} page(s)"

    with stage(events, run_id, "Extract", source_type) as event:
        extracted = extract_invoice(stored_path, source_type)
        event.output_summary = f"{len(extracted.model_dump(exclude_none=True))} fields, confidence {extracted.extraction_confidence:.2f}"

    with stage(events, run_id, "Normalize", extracted.invoice_number) as event:
        normalized = normalize_invoice(extracted)
        event.output_summary = f"Vendor={normalized.vendor.name}, PO={normalized.po_reference}"

    with stage(events, run_id, "Match", normalized.po_reference) as event:
        po_match = match_po(normalized)
        event.output_summary = f"{po_match.match_type}: {po_match.po_number or 'none'} ({po_match.confidence:.2f})"

    with stage(events, run_id, "Validate", po_match.po_number) as event:
        validations = validate_invoice(normalized, po_match)
        failed = [v.rule_name for v in validations if not v.passed and v.severity != "info"]
        event.output_summary = "Needs review: " + (", ".join(failed) if failed else "all controls passed")

    processing_ms = int((time.perf_counter() - started) * 1000)
    with stage(events, run_id, "Decide", None) as event:
        duplicates = find_duplicate_candidates(normalized, po_match)
        decision = decide(
            run_id,
            normalized,
            po_match,
            validations,
            processing_ms,
            duplicate_candidates=duplicates,
            stored_path=str(stored_path),
        )
        event.output_summary = f"{decision.status}: {decision.reasoning[:140]}"

    with stage(events, run_id, "Persist", None) as event:
        db.save_decision(decision, filename, events)
        event.output_summary = "Decision and audit trail stored in SQLite."

    return decision, events
