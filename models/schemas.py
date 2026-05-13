from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

DecisionStatus = Literal["APPROVED", "FLAGGED", "REJECTED"]
Severity = Literal["critical", "warning", "info"]
StageStatus = Literal["running", "completed", "failed"]


class LineItem(BaseModel):
    description: str
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    amount: Decimal


class VendorInfo(BaseModel):
    name: str | None = None
    address: str | None = None
    tax_id: str | None = None
    email: str | None = None


FieldStatus = Literal["extracted", "missing", "inferred", "suspicious"]


class ExtractedInvoice(BaseModel):
    invoice_number: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    vendor: VendorInfo = Field(default_factory=VendorInfo)
    po_reference: str | None = None
    line_items: list[LineItem] = Field(default_factory=list)
    subtotal: Decimal | None = None
    tax_amount: Decimal | None = None
    tax_rate: Decimal | None = None
    total: Decimal
    currency: str = "INR"
    bank_account: str | None = None
    bank_ifsc: str | None = None
    extraction_confidence: float = 0.0
    missing_fields: list[str] = Field(default_factory=list)
    raw_notes: str | None = None
    source_type: str | None = None
    field_status: dict[str, FieldStatus] = Field(default_factory=dict)


class ValidationResult(BaseModel):
    rule_id: str
    rule_name: str
    passed: bool
    severity: Severity
    detail: str


class POMatch(BaseModel):
    matched: bool
    match_type: Literal["exact", "fuzzy_vendor", "vendor_amount_date", "none", "multiple"]
    po_number: str | None = None
    confidence: float = 0.0
    notes: str
    po_record: dict[str, Any] | None = None
    cumulative_invoiced: Decimal = Decimal("0")
    reasons: list[str] = Field(default_factory=list)


class DuplicateCandidate(BaseModel):
    run_id: str
    invoice_number: str | None = None
    vendor_name: str | None = None
    total_amount: float | None = None
    uploaded_at: str | None = None
    similarity: float = 0.0
    reason: str


QueueCategory = Literal[
    "Ready for Payment",
    "Needs AP Review",
    "Needs Procurement Review",
    "Possible Duplicate",
    "Vendor/Bank Risk",
    "Over PO Limit",
    "Payment Blocked",
]


class ReadinessCheck(BaseModel):
    key: str
    label: str
    passed: bool
    detail: str


class PaymentReadiness(BaseModel):
    score: int
    checks: list[ReadinessCheck]
    recommendation: str
    approver: str
    queue: QueueCategory
    blockers: list[str] = Field(default_factory=list)


class Decision(BaseModel):
    invoice_id: str
    status: DecisionStatus
    confidence: float
    reasoning: str
    next_action: str
    extracted: ExtractedInvoice
    po_match: POMatch
    validations: list[ValidationResult]
    processing_time_ms: int
    timestamp: datetime
    readiness: PaymentReadiness | None = None
    duplicate_candidates: list[DuplicateCandidate] = Field(default_factory=list)
    stored_path: str | None = None


class ProgressEvent(BaseModel):
    run_id: str
    stage_name: str
    status: StageStatus
    started_at: datetime
    finished_at: datetime | None = None
    input_summary: str | None = None
    output_summary: str | None = None
    error: str | None = None


class OverrideRequest(BaseModel):
    new_status: DecisionStatus
    override_reason: str
    overridden_by: str = "demo_user"


class RunSummary(BaseModel):
    id: str
    filename: str
    uploaded_at: datetime
    status: DecisionStatus
    invoice_number: str | None = None
    vendor_name: str | None = None
    total_amount: float | None = None
    currency: str | None = None
    po_reference: str | None = None
    confidence: float | None = None
    processing_time_ms: int | None = None
    overridden_status: str | None = None
    overridden_by: str | None = None
    overridden_at: datetime | None = None
