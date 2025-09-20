"""Pydantic request/response models."""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, field_validator


class LineItem(BaseModel):
    desc: str
    qty: float
    unit_price: float
    amount: float
    sku: Optional[str] = None
    gl_code: Optional[str] = None
    cost_center: Optional[str] = None


class InvoiceIn(BaseModel):
    invoice_id: str
    vendor_id: str
    vendor_name: str
    invoice_number: str
    invoice_date: date
    currency: str
    total: float
    tax_total: float | None = 0.0
    po_number: str | None = None
    remit_bank_iban_or_account: str | None = None
    remit_name: str | None = None
    pdf_hash: str | None = None
    terms: str | None = None
    line_items: List[LineItem]

    @field_validator("line_items")
    @classmethod
    def _validate_line_items(cls, value: List[LineItem]) -> List[LineItem]:
        if not value:
            raise ValueError("line_items required")
        return value


class ScoreResponse(BaseModel):
    risk_score: float
    decision: str
    reason_codes: List[str]
    top_matches: List[Dict[str, Any]]
    explanations: List[Dict[str, Any]]
