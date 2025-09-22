from decimal import Decimal

from app.rules import rule_same_po_near_total


def test_same_po_near_total_ok():
    assert rule_same_po_near_total("PO1", "PO1", 100.0, 100.4, 5, 0.005, 30) is True


def test_same_po_near_total_fail_total():
    assert rule_same_po_near_total("PO1", "PO1", 100.0, 106.0, 5, 0.005, 30) is False


def test_same_po_near_total_decimal_inputs():
    total_a = Decimal("100.00")
    total_b = Decimal("100.40")

    assert rule_same_po_near_total("PO1", "PO1", total_a, total_b, 5, 0.005, 30) is True
