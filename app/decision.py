"""Decision fusion logic."""
from __future__ import annotations

from app.rules import HOLD, PASS, REVIEW


def fuse_scores(dup_prob: float, anom_prob: float, bank_change: bool, text_dup_prob: float) -> float:
    """Combine multiple probability signals into a 0-100 risk score."""

    dup_component = 0.7 * dup_prob
    text_component = 0.2 * max(dup_prob, text_dup_prob)
    anomaly_component = 0.1 * anom_prob
    score = (dup_component + text_component + anomaly_component) * 100.0

    if bank_change:
        score = min(100.0, score + 15.0)
        score = max(score, 80.0)

    return float(max(0.0, min(score, 100.0)))


def decide(score: float, review_threshold: float, hold_threshold: float) -> str:
    """Return HOLD/REVIEW/PASS based on thresholds."""

    if hold_threshold < review_threshold:
        raise ValueError("hold_threshold must be >= review_threshold")

    if score >= hold_threshold:
        return HOLD
    if score >= review_threshold:
        return REVIEW
    return PASS
