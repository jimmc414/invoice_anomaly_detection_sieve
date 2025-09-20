"""Replay historical invoices to refresh decisions."""
from __future__ import annotations

import json
import os

from sqlalchemy import create_engine, text

from app.config import settings
from app.main import score_invoice
from app.models import InvoiceIn

DSN = os.getenv("DB_DSN", settings.db_dsn)


def main() -> None:
    engine = create_engine(DSN, future=True)
    with engine.begin() as connection:
        rows = connection.execute(
            text(
                """
                SELECT raw_json
                FROM invoices
                WHERE tenant_id=:t
                ORDER BY created_at
                """
            ),
            {"t": settings.tenant_id},
        ).scalars().all()

    if not rows:
        print("No invoices found for backfill.")
        return

    for raw in rows:
        payload = InvoiceIn.model_validate_json(raw)
        result = score_invoice(payload, claims={"sub": "backfill"})
        print(json.dumps({"invoice_id": payload.invoice_id, "decision": result["decision"]}))


if __name__ == "__main__":  # pragma: no cover
    main()
