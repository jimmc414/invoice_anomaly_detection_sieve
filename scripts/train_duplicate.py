"""Train a duplicate detection model from stored invoices."""
from __future__ import annotations

import itertools
import os
from pathlib import Path
from typing import Dict, List, Tuple

import joblib
import numpy as np
from sqlalchemy import create_engine, text
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score

from app.config import settings
from app.features import header_features, line_assign_features
from app.normalization import desc_norm
from app.duplicate_model import FEATURE_ORDER

DSN = os.getenv("DB_DSN", settings.db_dsn)
MODEL_PATH = Path(os.getenv("DUP_MODEL_PATH", "models/dup_model.joblib"))


def _fetch_invoices(connection) -> Tuple[List[Dict], Dict[str, List[Dict]]]:
    invoices = connection.execute(
        text(
            """
            SELECT invoice_id, vendor_id, invoice_number_norm, invoice_date, currency, total, tax_total,
                   po_number, remit_account_hash, remit_name, pdf_hash
            FROM invoices
            WHERE tenant_id=:t
            """
        ),
        {"t": settings.tenant_id},
    ).mappings().all()
    line_rows = connection.execute(
        text(
            """
            SELECT invoice_id, line_no, "desc" AS desc, qty, unit_price, amount
            FROM invoice_lines
            WHERE tenant_id=:t
            ORDER BY invoice_id, line_no
            """
        ),
        {"t": settings.tenant_id},
    ).mappings().all()
    line_map: Dict[str, List[Dict]] = {}
    for row in line_rows:
        line_map.setdefault(row["invoice_id"], []).append({
            "desc": row["desc"],
            "desc_norm": desc_norm(row["desc"]),
            "qty": float(row["qty"]),
            "unit_price": float(row["unit_price"]),
            "amount": float(row["amount"]),
        })
    return [dict(r) for r in invoices], line_map


def _label_pair(a: Dict, b: Dict) -> int:
    if a["invoice_number_norm"] and a["invoice_number_norm"] == b["invoice_number_norm"]:
        return 1
    if a.get("pdf_hash") and a.get("pdf_hash") == b.get("pdf_hash"):
        return 1
    if abs(a.get("total", 0.0) - b.get("total", 0.0)) <= 0.01 and abs(
        (a.get("invoice_date") - b.get("invoice_date")).days
    ) <= 5:
        return 1
    return 0


def build_dataset(invoices: List[Dict], line_map: Dict[str, List[Dict]]):
    rows: List[Dict[str, float]] = []
    labels: List[int] = []
    for _, vendor_invoices in itertools.groupby(
        sorted(invoices, key=lambda i: i["vendor_id"]), key=lambda x: x["vendor_id"]
    ):
        vendor_list = list(vendor_invoices)
        for a, b in itertools.combinations(vendor_list, 2):
            lines_a = line_map.get(a["invoice_id"], [])
            lines_b = line_map.get(b["invoice_id"], [])
            if not lines_a or not lines_b:
                continue
            features = {
                **header_features(a, b),
                **line_assign_features(lines_a, lines_b),
            }
            a_text = " ".join(line["desc_norm"] for line in lines_a)
            b_text = " ".join(line["desc_norm"] for line in lines_b)
            a_tokens = set(a_text[i : i + 3] for i in range(max(len(a_text) - 2, 1)))
            b_tokens = set(b_text[i : i + 3] for i in range(max(len(b_text) - 2, 1)))
            overlap = len(a_tokens & b_tokens)
            denom = max(len(a_tokens) + len(b_tokens), 1)
            features["text_cosine"] = float(min(1.0, 2.0 * overlap / denom))
            label = _label_pair(a, b)
            rows.append(features)
            labels.append(label)
    return rows, labels


def main() -> None:
    engine = create_engine(DSN, future=True)
    with engine.begin() as connection:
        invoices, line_map = _fetch_invoices(connection)

    rows, labels = build_dataset(invoices, line_map)
    if not rows or len(set(labels)) < 2:
        print("Not enough labeled data to train; skipping model update.")
        return

    X = np.array([[float(row.get(name, 0.0)) for name in FEATURE_ORDER] for row in rows])
    y = np.array(labels)

    model = LogisticRegression(max_iter=500, class_weight="balanced")
    model.fit(X, y)

    probs = model.predict_proba(X)[:, 1]
    auc = roc_auc_score(y, probs)
    ap = average_precision_score(y, probs)
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    print(f"Model trained. ROC-AUC={auc:.3f} AP={ap:.3f} -> {MODEL_PATH}")


if __name__ == "__main__":  # pragma: no cover
    main()
