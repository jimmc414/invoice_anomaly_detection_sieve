"""Normalization utilities for invoice ingestion."""
from __future__ import annotations

import hashlib
import re
from typing import Any, Dict

INV_PREFIX = re.compile(r"^(INVOICE|INV|BILL)", re.I)
SPACE_PUNCT = re.compile(r"[\s\-_\/]")
NON_WORD = re.compile(r"[^a-z0-9\s]")
MULTI_SPACE = re.compile(r"\s+")


def invnum_norm(value: str) -> str:
    """Normalize invoice numbers according to the requirements."""

    value = value.strip().upper()
    value = SPACE_PUNCT.sub("", value)
    value = INV_PREFIX.sub("", value)
    value = value.lstrip("0")
    return value or "0"


def desc_norm(value: str) -> str:
    """Normalize free-text descriptions for similarity comparison."""

    value = value.lower()
    value = NON_WORD.sub(" ", value)
    value = MULTI_SPACE.sub(" ", value).strip()
    return value


def mask_account_last4(account: str | None) -> str | None:
    """Return masked last-four digits for display."""

    if not account:
        return None
    digits = re.sub(r"\D", "", account)
    if not digits:
        return "****"
    return f"****{digits[-4:]}"


def hash_account(account: str | None) -> str | None:
    """Create a deterministic hash for remit account comparison."""

    if not account:
        return None
    return hashlib.sha256(account.encode("utf8")).hexdigest()


def text_blob(invoice: Dict[str, Any]) -> str:
    """Concatenate vendor/header/line text for indexing."""

    parts: list[str] = [
        invoice.get("vendor_name", ""),
        invoice.get("po_number", ""),
        invoice.get("terms", ""),
    ]
    for line in invoice.get("line_items", []) or []:
        parts.append(str(line.get("sku", "")))
        parts.append(str(line.get("desc", "")))
    return " ".join(p for p in parts if p).lower()


def invoice_payload_hash(payload: Dict[str, Any]) -> str:
    """Return a stable hash for the invoice payload."""

    normalized = repr(sorted(payload.items())).encode("utf8")
    return hashlib.sha256(normalized).hexdigest()
