"""Audit logging helpers."""
from __future__ import annotations

import json
from typing import Any, Dict

from sqlalchemy import text

from app.config import settings
from app.storage import SessionLocal


def log_action(actor: str, action: str, entity: str, entity_id: str, payload: Dict[str, Any] | None = None) -> None:
    """Persist an audit log entry."""

    session = SessionLocal()
    with session.begin():
        session.execute(
            text(
                """
                INSERT INTO audit_log(tenant_id, actor, action, entity, entity_id, payload)
                VALUES (:tenant, :actor, :action, :entity, :entity_id, :payload::jsonb)
                """
            ),
            {
                "tenant": settings.tenant_id,
                "actor": actor,
                "action": action,
                "entity": entity,
                "entity_id": entity_id,
                "payload": json.dumps(payload or {}),
            },
        )
