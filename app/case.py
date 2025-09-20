"""Case management helpers."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import text

from app.config import settings
from app.storage import SessionLocal


CASE_OPEN_DECISIONS = {"HOLD", "REVIEW"}


def create_or_update_case(invoice_id: str, decision: str) -> str | None:
    """Create or update a case when the decision requires manual work."""

    if decision not in CASE_OPEN_DECISIONS:
        return None

    with SessionLocal().begin() as session:
        existing = session.execute(
            text(
                """
                SELECT case_id FROM cases
                WHERE tenant_id=:t AND invoice_id=:i
                """
            ),
            {"t": settings.tenant_id, "i": invoice_id},
        ).first()
        case_id = existing[0] if existing else f"case_{uuid.uuid4().hex[:12]}"
        session.execute(
            text(
                """
                INSERT INTO cases(tenant_id, case_id, invoice_id, status, sla_due, created_at, updated_at)
                VALUES (:t,:c,:i,:status,:due,NOW(),NOW())
                ON CONFLICT (tenant_id, case_id)
                DO UPDATE SET status=EXCLUDED.status, updated_at=NOW(), sla_due=EXCLUDED.sla_due
                """
            ),
            {
                "t": settings.tenant_id,
                "c": case_id,
                "i": invoice_id,
                "status": "OPEN",
                "due": datetime.utcnow() + timedelta(days=2),
            },
        )
    return case_id
