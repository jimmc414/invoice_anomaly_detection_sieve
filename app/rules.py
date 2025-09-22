"""Deterministic duplicate and anomaly rules."""
from __future__ import annotations

from decimal import Decimal

HOLD = "HOLD"
REVIEW = "REVIEW"
PASS = "PASS"


def rule_same_invnum_norm(invnum_a: str, invnum_b: str) -> bool:
    return bool(invnum_a and invnum_b and invnum_a == invnum_b)


def rule_same_po_near_total(
    po_a: str | None,
    po_b: str | None,
    total_a: float | int | Decimal,
    total_b: float | int | Decimal,
    date_gap_days: int,
    pct_tol: float = 0.005,
    window: int = 30,
) -> bool:
    if not po_a or not po_b or po_a != po_b:
        return False
    total_a_num = float(total_a) if total_a is not None else 0.0
    total_b_num = float(total_b) if total_b is not None else 0.0
    pct_tol_num = float(pct_tol)
    tolerance_base = max(abs(total_a_num), 1.0)
    if abs(total_a_num - total_b_num) > pct_tol_num * tolerance_base:
        return False
    return date_gap_days <= window


def rule_pdf_near_dup(hash_a: str | None, hash_b: str | None, shingle_jaccard: float | None = None) -> bool:
    if hash_a and hash_b and hash_a == hash_b:
        return True
    return bool((shingle_jaccard or 0.0) >= 0.9)


def rule_new_bank(first_seen_recent: bool) -> bool:
    return first_seen_recent


def apply_rules(context: dict) -> list[str]:
    """Evaluate core rules and return triggered reason codes."""

    reasons: list[str] = []
    cand = context.get("candidate")
    invoice = context.get("invoice")
    features = context.get("features", {})

    if cand and invoice:
        if rule_same_invnum_norm(invoice.get("invoice_number_norm", ""), cand.get("invoice_number_norm", "")):
            reasons.append("EXACT_INVNUM")
        if rule_same_po_near_total(
            invoice.get("po_number"),
            cand.get("po_number"),
            invoice.get("total", 0.0),
            cand.get("total", 0.0),
            int(features.get("days_diff", 9999)),
        ):
            reasons.append("SAME_PO_NEAR_TOTAL")
        if rule_pdf_near_dup(invoice.get("pdf_hash"), cand.get("pdf_hash")):
            reasons.append("PDF_NEAR_DUP")

    if context.get("bank_change", False):
        reasons.append("BANK_CHANGE")

    return reasons
