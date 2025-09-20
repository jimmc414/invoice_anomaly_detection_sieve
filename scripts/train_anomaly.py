"""Calculate vendor amount baselines for anomaly scoring."""
from __future__ import annotations

import os

import pandas as pd
from sqlalchemy import create_engine, text

from app.config import settings

DSN = os.getenv("DB_DSN", settings.db_dsn)


def main() -> None:
    engine = create_engine(DSN, future=True)
    with engine.begin() as connection:
        rows = connection.execute(
            text(
                """
                SELECT vendor_id, total
                FROM invoices
                WHERE tenant_id=:t
                """
            ),
            {"t": settings.tenant_id},
        ).mappings().all()
        if not rows:
            print("No invoices available; skipping baselines.")
            return
        frame = pd.DataFrame(rows)
        grouped = frame.groupby("vendor_id")["total"].agg(["mean", "std", "count"]).reset_index()
        for _, row in grouped.iterrows():
            std_val = float(row["std"] or 0.0)
            connection.execute(
                text(
                    """
                    INSERT INTO vendor_amount_baselines(tenant_id, vendor_id, mean_total, std_total, sample_count)
                    VALUES (:t,:v,:mean,:std,:count)
                    ON CONFLICT (tenant_id, vendor_id)
                    DO UPDATE SET mean_total=EXCLUDED.mean_total,
                                  std_total=EXCLUDED.std_total,
                                  sample_count=EXCLUDED.sample_count,
                                  updated_at=NOW()
                    """
                ),
                {
                    "t": settings.tenant_id,
                    "v": row["vendor_id"],
                    "mean": float(row["mean"]),
                    "std": std_val,
                    "count": int(row["count"]),
                },
            )
    print("Vendor baselines updated.")


if __name__ == "__main__":  # pragma: no cover
    main()
