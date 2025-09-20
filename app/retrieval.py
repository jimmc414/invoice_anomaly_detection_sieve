"""Candidate retrieval logic for duplicate detection."""
from __future__ import annotations

from typing import Dict, List

from sqlalchemy import text

from app.config import settings
from app.storage import SessionLocal


def candidate_pairs(invoice_row: Dict, cap: int = 200) -> List[Dict]:
    """Retrieve structured candidate invoices for the same vendor."""

    sql = """
    WITH base AS (
      SELECT vendor_id, invoice_id, invoice_number_norm, po_number, currency, total, tax_total,
             invoice_date, remit_account_hash, remit_name, pdf_hash
      FROM invoices
      WHERE tenant_id=:tenant AND vendor_id=:vendor AND invoice_id != :invoice_id
    )
    SELECT * FROM base
     WHERE (
       round(total,2)=round(:total,2)
       AND date_trunc('month', invoice_date)=date_trunc('month', :invoice_date::date)
     )
     OR (po_number IS NOT NULL AND po_number=:po)
     OR (invoice_number_norm=:invnum_norm)
     OR (remit_account_hash IS NOT NULL AND remit_account_hash=:acct_hash)
    LIMIT :cap;
    """

    with SessionLocal() as session:
        rows = session.execute(
            text(sql),
            {
                "tenant": settings.tenant_id,
                "vendor": invoice_row["vendor_id"],
                "invoice_id": invoice_row["invoice_id"],
                "total": invoice_row["total"],
                "invoice_date": invoice_row["invoice_date"],
                "po": invoice_row.get("po_number"),
                "invnum_norm": invoice_row.get("invoice_number_norm"),
                "acct_hash": invoice_row.get("remit_account_hash"),
                "cap": cap,
            },
        ).mappings().all()
    return [dict(r) for r in rows]
