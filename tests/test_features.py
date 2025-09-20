from app.features import line_assign_features


def test_line_features():
    a = [{"desc_norm": "paper a4", "qty": 10, "unit_price": 10.0, "amount": 100.0}]
    b = [{"desc_norm": "paper a4", "qty": 10, "unit_price": 10.0, "amount": 100.0}]
    features = line_assign_features(a, b)
    assert features["line_coverage_pct"] >= 0.99
    assert features["unmatched_amount_frac"] <= 0.01
