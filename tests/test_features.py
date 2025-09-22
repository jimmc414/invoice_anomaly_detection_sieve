from datetime import date
from decimal import Decimal

import pytest

from app.features import header_features, line_assign_features


def test_line_features():
    a = [{"desc_norm": "paper a4", "qty": 10, "unit_price": 10.0, "amount": 100.0}]
    b = [{"desc_norm": "paper a4", "qty": 10, "unit_price": 10.0, "amount": 100.0}]
    features = line_assign_features(a, b)
    assert features["line_coverage_pct"] >= 0.99
    assert features["unmatched_amount_frac"] <= 0.01


def test_header_features_decimal_totals():
    a = {"total": Decimal("100.00"), "invoice_date": date(2023, 1, 1)}
    b = {"total": Decimal("110.00"), "invoice_date": date(2023, 1, 2)}

    features = header_features(a, b)

    assert features["abs_total_diff_pct"] == pytest.approx(0.1)
    assert features["days_diff"] == pytest.approx(1.0)


def test_line_assign_features_decimal_amounts_with_empty_candidates():
    a_lines = [{"amount": Decimal("50.00"), "unit_price": Decimal("5.00"), "qty": Decimal("10")}] 
    b_lines = []

    features = line_assign_features(a_lines, b_lines)

    assert features["line_coverage_pct"] == pytest.approx(0.0)
    assert features["unmatched_amount_frac"] == pytest.approx(1.0)
    assert features["count_new_items"] == pytest.approx(1.0)
    assert features["median_unit_price_diff"] == pytest.approx(50.0)
