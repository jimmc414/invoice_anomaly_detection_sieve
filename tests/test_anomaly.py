"""Regression tests for anomaly heuristics."""
from __future__ import annotations

from decimal import Decimal

import pytest

from app import anomaly


class _DummySession:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


@pytest.mark.parametrize(
    "std_total, sample_count",
    [
        (Decimal("12.5"), 20),
        (Decimal("0"), 20),
    ],
)
def test_anomaly_score_decimal_baseline(monkeypatch, std_total, sample_count):
    baseline = {
        "mean_total": Decimal("100.0"),
        "std_total": std_total,
        "sample_count": sample_count,
    }
    invoice_row = {
        "invoice_id": "inv-1",
        "vendor_id": "vendor-1",
        "total": Decimal("110.0"),
    }

    monkeypatch.setattr(anomaly, "SessionLocal", lambda: _DummySession())
    monkeypatch.setattr(
        anomaly, "_fetch_vendor_baseline", lambda session, vendor_id, data=baseline: data
    )

    prob, reasons = anomaly.anomaly_score(invoice_row, vendor_hist_count=11)

    assert isinstance(prob, float)
    assert isinstance(reasons, list)
    assert all(isinstance(reason, str) for reason in reasons)
    assert 0.0 <= prob <= 1.0
