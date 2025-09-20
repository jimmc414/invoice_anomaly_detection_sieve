"""Anomaly heuristics for invoices."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

from sqlalchemy import text

from app.config import settings
from app.storage import SessionLocal


def _fetch_vendor_baseline(session, vendor_id: str) -> Dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT mean_total, std_total, sample_count
            FROM vendor_amount_baselines
            WHERE tenant_id=:t AND vendor_id=:v
            """
        ),
        {"t": settings.tenant_id, "v": vendor_id},
    ).mappings().first()
    return dict(row) if row else None


def anomaly_score(invoice_row: Dict[str, Any], vendor_hist_count: int | None = None) -> Tuple[float, List[str]]:
    """Return anomaly probability and reason codes."""

    reasons: List[str] = []
    with SessionLocal() as session:
        if vendor_hist_count is None:
            vendor_hist_count = session.execute(
                text(
                    """
                    SELECT COUNT(*) FROM invoices
                    WHERE tenant_id=:t AND vendor_id=:v AND invoice_id != :i
                    """
                ),
                {"t": settings.tenant_id, "v": invoice_row["vendor_id"], "i": invoice_row["invoice_id"]},
            ).scalar_one()

        baseline = _fetch_vendor_baseline(session, invoice_row["vendor_id"])

        bank_change = False
        if invoice_row.get("remit_account_hash"):
            bank_row = session.execute(
                text(
                    """
                    SELECT first_seen, last_seen FROM vendor_remit_accounts
                    WHERE tenant_id=:t AND vendor_id=:v AND remit_account_hash=:h
                    """
                ),
                {
                    "t": settings.tenant_id,
                    "v": invoice_row["vendor_id"],
                    "h": invoice_row["remit_account_hash"],
                },
            ).mappings().first()
            if bank_row:
                first_seen = bank_row["first_seen"]
                last_seen = bank_row["last_seen"]
                if isinstance(first_seen, datetime) and isinstance(last_seen, datetime):
                    bank_change = (last_seen - first_seen) <= timedelta(minutes=1)
                else:
                    bank_change = False
            else:
                bank_change = True
        if bank_change:
            reasons.append("BANK_CHANGE")

    amount_z = 0.0
    if baseline and baseline.get("std_total") and baseline.get("std_total") > 0:
        amount_z = abs(invoice_row.get("total", 0.0) - baseline.get("mean_total", 0.0)) / baseline["std_total"]
    elif baseline and baseline.get("sample_count", 0) > 10:
        # fallback using MAD-like heuristic
        amount_z = abs(invoice_row.get("total", 0.0) - baseline.get("mean_total", 0.0)) / max(
            abs(baseline.get("mean_total", 0.0)), 1.0
        )

    if amount_z >= 2.5:
        reasons.append("UNIT_PRICE_OUTLIER")

    prob = 0.1 + min(amount_z / 5.0, 0.6)
    if bank_change:
        prob += 0.25
    if vendor_hist_count is not None and vendor_hist_count < 5:
        prob *= 0.8  # reduce sensitivity for cold vendors

    return float(min(prob, 1.0)), reasons
