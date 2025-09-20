"""Duplicate scoring model loading and inference."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import joblib
import numpy as np

_MODEL = None
_MODEL_PATH = Path(os.getenv("DUP_MODEL_PATH", "models/dup_model.joblib"))

FEATURE_ORDER = [
    "abs_total_diff_pct",
    "days_diff",
    "same_po",
    "same_currency",
    "same_tax_total",
    "bank_change_flag",
    "payee_name_change_flag",
    "invnum_edit",
    "line_coverage_pct",
    "unmatched_amount_frac",
    "count_new_items",
    "median_unit_price_diff",
    "text_cosine",
]

# Coefficients derived from heuristic expectations to provide a reasonable default.
_FALLBACK_WEIGHTS = np.array(
    [
        -1.2,  # abs_total_diff_pct
        -0.03,  # days_diff
        0.8,  # same_po
        0.3,  # same_currency
        0.2,  # same_tax_total
        -0.4,  # bank_change_flag (bank changes reduce dup probability)
        -0.1,  # payee_name_change_flag
        -1.5,  # invnum_edit (distance -> lower dup prob)
        1.6,  # line_coverage_pct
        -1.8,  # unmatched_amount_frac
        -0.4,  # count_new_items
        -0.05,  # median_unit_price_diff
        2.2,  # text_cosine
    ]
)
_FALLBACK_BIAS = -0.3


class _FallbackModel:
    """Simple logistic regression approximation used when no trained model exists."""

    def predict_proba(self, matrix: np.ndarray) -> np.ndarray:
        logits = matrix @ _FALLBACK_WEIGHTS + _FALLBACK_BIAS
        probs = 1 / (1 + np.exp(-logits))
        return np.vstack([1 - probs, probs]).T


def load_model():
    """Load the duplicate model artifact, falling back to heuristics when absent."""

    global _MODEL
    if _MODEL is not None:
        return _MODEL

    if _MODEL_PATH.exists():
        _MODEL = joblib.load(_MODEL_PATH)
    else:
        _MODEL = _FallbackModel()
    return _MODEL


def predict_dup_prob(features: Dict[str, Any]) -> float:
    """Predict duplicate probability given feature dictionary."""

    model = load_model()
    vector = np.array([[float(features.get(name, 0.0)) for name in FEATURE_ORDER]], dtype=float)
    proba = model.predict_proba(vector)[0][1]
    return float(max(0.0, min(1.0, proba)))
