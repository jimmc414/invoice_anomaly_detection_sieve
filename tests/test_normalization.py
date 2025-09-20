from app.normalization import desc_norm, invnum_norm


def test_invnum_norm():
    assert invnum_norm(" inv-000123 ") == "123"
    assert invnum_norm("invoice-001A") == "1A"


def test_desc_norm():
    assert desc_norm("Printer Ink, Black!!!") == "printer ink black"
