from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from models import db
from models.schemas import OverrideRequest
from pipeline.orchestrator import process_invoice

app = FastAPI(title="Zamp AP Automation", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def startup() -> None:
    db.init_db()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/process")
async def process(file: UploadFile = File(...)) -> dict:
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Upload a PDF invoice.")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(await file.read())
        tmp_path = Path(tmp.name)
    try:
        decision, events = process_invoice(tmp_path, file.filename)
        return {"decision": decision.model_dump(mode="json"), "events": [e.model_dump(mode="json") for e in events]}
    finally:
        tmp_path.unlink(missing_ok=True)


@app.get("/history")
def history(status: str | None = None, vendor: str | None = None) -> list[dict]:
    return [run.model_dump(mode="json") for run in db.list_runs(status=status, vendor=vendor)]


@app.get("/invoice/{run_id}")
def invoice(run_id: str) -> dict:
    decision = db.get_decision(run_id)
    if not decision:
        raise HTTPException(status_code=404, detail="Run not found.")
    return {"decision": decision.model_dump(mode="json"), "events": db.get_events(run_id)}


@app.get("/pos")
def pos() -> list[dict]:
    return pd.read_csv("data/pos.csv").to_dict(orient="records")


@app.get("/vendors")
def vendors() -> list[dict]:
    return pd.read_csv("data/approved_vendors.csv").to_dict(orient="records")


@app.post("/invoice/{run_id}/override")
def override(run_id: str, request: OverrideRequest) -> dict[str, str]:
    ok = db.override_run(run_id, request.new_status, request.override_reason, request.overridden_by)
    if not ok:
        raise HTTPException(status_code=404, detail="Run not found.")
    return {"status": "updated"}
