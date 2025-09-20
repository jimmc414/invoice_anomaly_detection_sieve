"""Feature engineering for duplicate detection."""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
from rapidfuzz.distance import JaroWinkler
from scipy.optimize import linear_sum_assignment


def header_features(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, float]:
    features: Dict[str, float] = {}
    features["abs_total_diff_pct"] = abs(a.get("total", 0.0) - b.get("total", 0.0)) / max(
        abs(a.get("total", 0.0)), 1.0
    )
    features["days_diff"] = float(abs((a.get("invoice_date") - b.get("invoice_date")).days))
    features["same_po"] = float(1.0 if a.get("po_number") and a.get("po_number") == b.get("po_number") else 0.0)
    features["same_currency"] = float(1.0 if a.get("currency") == b.get("currency") else 0.0)
    features["same_tax_total"] = float(
        1.0 if round((a.get("tax_total") or 0.0), 2) == round((b.get("tax_total") or 0.0), 2) else 0.0
    )
    features["bank_change_flag"] = float(
        1.0 if a.get("remit_account_hash") and b.get("remit_account_hash") and a.get("remit_account_hash") != b.get("remit_account_hash") else 0.0
    )
    features["payee_name_change_flag"] = float(
        1.0 if (a.get("remit_name") or "") != (b.get("remit_name") or "") else 0.0
    )
    a_norm = a.get("invoice_number_norm", "")
    b_norm = b.get("invoice_number_norm", "")
    features["invnum_edit"] = 1.0 - float(JaroWinkler.normalized_similarity(a_norm, b_norm))
    return features


def _string_distance(a: str, b: str) -> float:
    return 1.0 - float(JaroWinkler.normalized_similarity(a, b))


def line_assign_features(
    a_lines: List[Dict[str, Any]],
    b_lines: List[Dict[str, Any]],
    alpha: float = 0.7,
    beta: float = 0.2,
    gamma: float = 0.1,
) -> Dict[str, float]:
    if not a_lines or not b_lines:
        total_amount = sum(x.get("amount", 0.0) for x in a_lines)
        unmatched = float(total_amount)
        return {
            "line_coverage_pct": 0.0,
            "unmatched_amount_frac": float(unmatched / max(total_amount, 1.0)) if total_amount else 1.0,
            "count_new_items": float(len(a_lines)),
            "median_unit_price_diff": float(total_amount),
        }

    n, m = len(a_lines), len(b_lines)
    cost = np.zeros((n, m), dtype=float)

    for i, a_line in enumerate(a_lines):
        for j, b_line in enumerate(b_lines):
            desc_cost = _string_distance(a_line.get("desc_norm", ""), b_line.get("desc_norm", ""))
            up_a = float(a_line.get("unit_price", 0.0))
            up_b = float(b_line.get("unit_price", 0.0))
            qty_a = float(a_line.get("qty", 0.0))
            qty_b = float(b_line.get("qty", 0.0))
            up_term = min(abs(up_a - up_b) / max(abs(up_a), 1.0), 5.0)
            qty_term = min(abs(qty_a - qty_b) / max(abs(qty_a), 1.0), 5.0)
            cost[i, j] = alpha * desc_cost + beta * up_term + gamma * qty_term

    row_ind, col_ind = linear_sum_assignment(cost)
    matched_rows = set(row_ind.tolist())

    matched_amount = sum(float(a_lines[i].get("amount", 0.0)) for i in matched_rows)
    total_amount = sum(float(line.get("amount", 0.0)) for line in a_lines)
    unmatched_amount = max(total_amount - matched_amount, 0.0)
    unmatched_amount_frac = float(unmatched_amount / max(total_amount, 1.0)) if total_amount else 1.0
    coverage = float(1.0 - unmatched_amount_frac)

    med_diffs: List[float] = []
    for i, j in zip(row_ind, col_ind, strict=False):
        med_diffs.append(abs(float(a_lines[i].get("unit_price", 0.0)) - float(b_lines[j].get("unit_price", 0.0))))

    median_unit_price_diff = float(np.median(med_diffs)) if med_diffs else 0.0

    return {
        "line_coverage_pct": coverage,
        "unmatched_amount_frac": unmatched_amount_frac,
        "count_new_items": float(max(0, len(a_lines) - len(matched_rows))),
        "median_unit_price_diff": median_unit_price_diff,
    }
