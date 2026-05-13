from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from pydantic.json import pydantic_encoder

from models.schemas import Decision, ProgressEvent, RunSummary

DB_PATH = Path(os.getenv("ZAMP_DB_PATH", "/tmp/zamp_ap.db" if os.getenv("VERCEL") else "data/zamp_ap.db"))


SCHEMA = """
CREATE TABLE IF NOT EXISTS invoice_runs (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    uploaded_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('APPROVED','FLAGGED','REJECTED')),
    invoice_number TEXT,
    vendor_name TEXT,
    total_amount REAL,
    currency TEXT,
    po_reference TEXT,
    confidence REAL,
    decision_json TEXT NOT NULL,
    processing_time_ms INTEGER,
    overridden_status TEXT,
    overridden_by TEXT,
    override_reason TEXT,
    overridden_at TEXT,
    stored_path TEXT
);
CREATE INDEX IF NOT EXISTS idx_dup ON invoice_runs(invoice_number, vendor_name);
CREATE INDEX IF NOT EXISTS idx_po ON invoice_runs(po_reference);
CREATE INDEX IF NOT EXISTS idx_status ON invoice_runs(status);
CREATE INDEX IF NOT EXISTS idx_uploaded ON invoice_runs(uploaded_at DESC);

CREATE TABLE IF NOT EXISTS stage_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    stage_name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    input_summary TEXT,
    output_summary TEXT,
    error TEXT,
    FOREIGN KEY (run_id) REFERENCES invoice_runs(id)
);

CREATE TABLE IF NOT EXISTS inbox_emails (
    id TEXT PRIMARY KEY,
    received_at TEXT NOT NULL,
    sender TEXT,
    subject TEXT,
    body TEXT,
    attachment_name TEXT,
    vendor_guess TEXT,
    status TEXT DEFAULT 'New',
    run_id TEXT,
    pdf_path TEXT
);
CREATE INDEX IF NOT EXISTS idx_inbox_status ON inbox_emails(status);

CREATE TABLE IF NOT EXISTS workflow_state (
    run_id TEXT PRIMARY KEY,
    owner TEXT,
    state TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS workflow_comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    author TEXT,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS payment_runs (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    payment_date TEXT,
    total_amount REAL,
    invoice_count INTEGER,
    vendor_count INTEGER,
    details_json TEXT NOT NULL
);
"""


def _ensure_columns(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(invoice_runs)").fetchall()}
    if "stored_path" not in columns:
        conn.execute("ALTER TABLE invoice_runs ADD COLUMN stored_path TEXT")


def _json_default(value: Any) -> Any:
    return pydantic_encoder(value)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def init_db(path: Path = DB_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        conn.executescript(SCHEMA)
        _ensure_columns(conn)
        conn.commit()


@contextmanager
def get_conn(path: Path = DB_PATH):
    init_db(path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def save_decision(decision: Decision, filename: str, events: Iterable[ProgressEvent]) -> None:
    decision_json = json.dumps(decision.model_dump(), default=_json_default)
    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO invoice_runs (
                id, filename, uploaded_at, status, invoice_number, vendor_name,
                total_amount, currency, po_reference, confidence, decision_json,
                processing_time_ms, stored_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision.invoice_id,
                filename,
                decision.timestamp.isoformat(),
                decision.status,
                decision.extracted.invoice_number,
                decision.extracted.vendor.name,
                float(decision.extracted.total),
                decision.extracted.currency,
                decision.extracted.po_reference or decision.po_match.po_number,
                decision.confidence,
                decision_json,
                decision.processing_time_ms,
                decision.stored_path,
            ),
        )
        conn.execute("DELETE FROM stage_events WHERE run_id = ?", (decision.invoice_id,))
        for event in events:
            conn.execute(
                """
                INSERT INTO stage_events (
                    run_id, stage_name, started_at, finished_at, status,
                    input_summary, output_summary, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.run_id,
                    event.stage_name,
                    event.started_at.isoformat(),
                    event.finished_at.isoformat() if event.finished_at else None,
                    event.status,
                    event.input_summary,
                    event.output_summary,
                    event.error,
                ),
            )


def list_runs(status: str | None = None, vendor: str | None = None, limit: int = 100) -> list[RunSummary]:
    query = "SELECT * FROM invoice_runs WHERE 1=1"
    params: list[Any] = []
    if status and status != "All":
        query += " AND status = ?"
        params.append(status)
    if vendor and vendor != "All":
        query += " AND vendor_name = ?"
        params.append(vendor)
    query += " ORDER BY uploaded_at DESC LIMIT ?"
    params.append(limit)
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [RunSummary(**dict(row)) for row in rows]


def get_decision(run_id: str) -> Decision | None:
    with get_conn() as conn:
        row = conn.execute("SELECT decision_json FROM invoice_runs WHERE id = ?", (run_id,)).fetchone()
    if not row:
        return None
    return Decision.model_validate_json(row["decision_json"])


def get_events(run_id: str) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM stage_events WHERE run_id = ? ORDER BY id ASC", (run_id,)
        ).fetchall()
    return [dict(row) for row in rows]


def get_cumulative_invoiced(po_number: str) -> float:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(total_amount), 0) AS total
            FROM invoice_runs
            WHERE po_reference = ? AND status = 'APPROVED'
            """,
            (po_number,),
        ).fetchone()
    return float(row["total"] or 0)


def find_prior_invoice(invoice_number: str | None, vendor_name: str | None) -> dict[str, Any] | None:
    if not invoice_number or not vendor_name:
        return None
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT * FROM invoice_runs
            WHERE invoice_number = ? AND lower(vendor_name) = lower(?)
            ORDER BY uploaded_at DESC LIMIT 1
            """,
            (invoice_number, vendor_name),
        ).fetchone()
    return dict(row) if row else None


def override_run(run_id: str, new_status: str, reason: str, user: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            """
            UPDATE invoice_runs
            SET overridden_status = ?, overridden_by = ?, override_reason = ?, overridden_at = ?
            WHERE id = ?
            """,
            (new_status, user, reason, utc_now().isoformat(), run_id),
        )
    return cur.rowcount > 0


def get_all_runs_raw() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM invoice_runs ORDER BY uploaded_at DESC").fetchall()
    return [dict(row) for row in rows]


def get_all_decisions() -> list[Decision]:
    rows = get_all_runs_raw()
    out: list[Decision] = []
    for row in rows:
        payload = row.get("decision_json")
        if payload:
            try:
                out.append(Decision.model_validate_json(payload))
            except Exception:
                continue
    return out


def get_po_invoices(po_number: str) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, invoice_number, vendor_name, total_amount, currency, status,
                   uploaded_at, overridden_status, decision_json
            FROM invoice_runs
            WHERE po_reference = ?
            ORDER BY uploaded_at ASC
            """,
            (po_number,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_vendor_invoices(vendor_name: str) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, invoice_number, total_amount, currency, status, uploaded_at,
                   overridden_status, po_reference
            FROM invoice_runs
            WHERE lower(vendor_name) = lower(?)
            ORDER BY uploaded_at DESC
            """,
            (vendor_name,),
        ).fetchall()
    return [dict(row) for row in rows]


def find_similar_invoices(
    vendor_name: str | None,
    invoice_number: str | None,
    total: float | None,
    bank_account: str | None,
    po_reference: str | None,
    invoice_date: str | None,
    exclude_run_id: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Return potential duplicate candidates (vendor or PO or bank-account overlap)."""
    clauses: list[str] = []
    params: list[Any] = []
    if vendor_name:
        clauses.append("lower(vendor_name) = lower(?)")
        params.append(vendor_name)
    if po_reference:
        clauses.append("po_reference = ?")
        params.append(po_reference)
    if not clauses:
        return []
    query = (
        "SELECT id, invoice_number, vendor_name, total_amount, uploaded_at, "
        "po_reference, decision_json FROM invoice_runs WHERE (" + " OR ".join(clauses) + ")"
    )
    if exclude_run_id:
        query += " AND id <> ?"
        params.append(exclude_run_id)
    query += " ORDER BY uploaded_at DESC LIMIT ?"
    params.append(limit)
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


# ---------------- Inbox emails ----------------


def upsert_inbox_email(email: dict[str, Any]) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO inbox_emails (
                id, received_at, sender, subject, body, attachment_name,
                vendor_guess, status, run_id, pdf_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                email["id"],
                email["received_at"],
                email.get("sender"),
                email.get("subject"),
                email.get("body"),
                email.get("attachment_name"),
                email.get("vendor_guess"),
                email.get("status", "New"),
                email.get("run_id"),
                email.get("pdf_path"),
            ),
        )


def list_inbox(status: str | None = None) -> list[dict[str, Any]]:
    query = "SELECT * FROM inbox_emails"
    params: list[Any] = []
    if status and status != "All":
        query += " WHERE status = ?"
        params.append(status)
    query += " ORDER BY received_at DESC"
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def get_inbox_email(email_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM inbox_emails WHERE id = ?", (email_id,)).fetchone()
    return dict(row) if row else None


def update_inbox_status(email_id: str, status: str, run_id: str | None = None) -> None:
    with get_conn() as conn:
        if run_id:
            conn.execute(
                "UPDATE inbox_emails SET status = ?, run_id = ? WHERE id = ?",
                (status, run_id, email_id),
            )
        else:
            conn.execute(
                "UPDATE inbox_emails SET status = ? WHERE id = ?", (status, email_id)
            )


def inbox_counts() -> dict[str, int]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS c FROM inbox_emails GROUP BY status"
        ).fetchall()
    return {row["status"]: row["c"] for row in rows}


# ---------------- Workflow ----------------


def set_workflow(run_id: str, owner: str | None, state: str | None) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO workflow_state (run_id, owner, state, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                owner = excluded.owner,
                state = excluded.state,
                updated_at = excluded.updated_at
            """,
            (run_id, owner, state, utc_now().isoformat()),
        )


def get_workflow(run_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM workflow_state WHERE run_id = ?", (run_id,)
        ).fetchone()
    return dict(row) if row else None


def add_comment(run_id: str, author: str, body: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO workflow_comments (run_id, author, body, created_at) VALUES (?, ?, ?, ?)",
            (run_id, author, body, utc_now().isoformat()),
        )


def list_comments(run_id: str) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM workflow_comments WHERE run_id = ? ORDER BY id ASC",
            (run_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def all_workflows() -> dict[str, dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM workflow_state").fetchall()
    return {row["run_id"]: dict(row) for row in rows}


# ---------------- Payment runs ----------------


def save_payment_run(payload: dict[str, Any]) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO payment_runs (
                id, created_at, payment_date, total_amount, invoice_count,
                vendor_count, details_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["id"],
                payload["created_at"],
                payload.get("payment_date"),
                payload.get("total_amount", 0.0),
                payload.get("invoice_count", 0),
                payload.get("vendor_count", 0),
                json.dumps(payload.get("details", {}), default=_json_default),
            ),
        )


def list_payment_runs() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM payment_runs ORDER BY created_at DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def get_payment_run(run_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM payment_runs WHERE id = ?", (run_id,)
        ).fetchone()
    return dict(row) if row else None
