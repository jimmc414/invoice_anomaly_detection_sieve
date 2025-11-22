"""FastAPI application entrypoint."""
from __future__ import annotations

import uuid
from typing import Any, Dict, Iterable, List

import orjson
from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import ARRAY, String, bindparam, text

from app.audit import log_action
from app.anomaly import anomaly_score
from app.case import create_or_update_case
from app.config import settings
from app.decision import decide, fuse_scores
from app.duplicate_model import predict_dup_prob
from app.features import header_features, line_assign_features
from app.models import InvoiceIn, ScoreResponse
from app.normalization import (
    desc_norm,
    hash_account,
    invnum_norm,
    invoice_payload_hash,
    mask_account_last4,
    text_blob,
)
from app.retrieval import candidate_pairs
from app.rules import apply_rules
from app.security import require_auth
from app.storage import SessionLocal, os_client

app = FastAPI(title="Invoice Anomaly Sieve")


def _fetch_invoice(invoice_id: str) -> Dict[str, Any]:
    with SessionLocal() as session:
        row = session.execute(
            text(
                """
                SELECT * FROM invoices WHERE tenant_id=:t AND invoice_id=:i
                """
            ),
            {"t": settings.tenant_id, "i": invoice_id},
        ).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="invoice not found")
        return dict(row)


def _fetch_invoice_lines(invoice_id: str) -> List[Dict[str, Any]]:
    with SessionLocal() as session:
        rows = session.execute(
            text(
                """
                SELECT line_no, sku, "desc" AS desc, qty, unit_price, amount, gl_code, cost_center
                FROM invoice_lines
                WHERE tenant_id=:t AND invoice_id=:i
                ORDER BY line_no
                """
            ),
            {"t": settings.tenant_id, "i": invoice_id},
        ).mappings().all()
    return [dict(r) for r in rows]


def _persist_invoice(invoice: Dict[str, Any]) -> Dict[str, Any]:
    payload = invoice.copy()
    payload["invoice_number_norm"] = invnum_norm(payload["invoice_number"])
    payload["remit_bank_account_masked"] = mask_account_last4(payload.get("remit_bank_iban_or_account"))
    payload["remit_account_hash"] = hash_account(payload.get("remit_bank_iban_or_account"))
    payload_hash = invoice_payload_hash(payload)

    session = SessionLocal()
    with session.begin():
        session.execute(
            text(
                """
                INSERT INTO vendors(tenant_id, vendor_id, vendor_name)
                VALUES (:t,:v,:name)
                ON CONFLICT (tenant_id, vendor_id) DO UPDATE SET vendor_name=EXCLUDED.vendor_name
                """
            ),
            {"t": settings.tenant_id, "v": payload["vendor_id"], "name": payload["vendor_name"]},
        )

        session.execute(
            text(
                """
                INSERT INTO invoices(
                  tenant_id, invoice_id, payload_hash, vendor_id, invoice_number,
                  invoice_number_norm, invoice_date, currency, total, tax_total, po_number,
                  remit_bank_account_masked, remit_account_hash, remit_name, pdf_hash, terms, raw_json
                )
                VALUES (
                  :t,:invoice_id,:payload_hash,:vendor_id,:invoice_number,
                  :invoice_number_norm,:invoice_date,:currency,:total,:tax_total,:po_number,
                  :remit_bank_account_masked,:remit_account_hash,:remit_name,:pdf_hash,:terms,:raw_json
                )
                ON CONFLICT (tenant_id, invoice_id) DO UPDATE
                  SET payload_hash=EXCLUDED.payload_hash,
                      invoice_number=EXCLUDED.invoice_number,
                      invoice_number_norm=EXCLUDED.invoice_number_norm,
                      invoice_date=EXCLUDED.invoice_date,
                      currency=EXCLUDED.currency,
                      total=EXCLUDED.total,
                      tax_total=EXCLUDED.tax_total,
                      po_number=EXCLUDED.po_number,
                      remit_bank_account_masked=EXCLUDED.remit_bank_account_masked,
                      remit_account_hash=EXCLUDED.remit_account_hash,
                      remit_name=EXCLUDED.remit_name,
                      pdf_hash=EXCLUDED.pdf_hash,
                      terms=EXCLUDED.terms,
                      raw_json=EXCLUDED.raw_json
                """
            ),
            {
                "t": settings.tenant_id,
                "invoice_id": payload["invoice_id"],
                "payload_hash": payload_hash,
                "vendor_id": payload["vendor_id"],
                "invoice_number": payload["invoice_number"],
                "invoice_number_norm": payload["invoice_number_norm"],
                "invoice_date": payload["invoice_date"],
                "currency": payload["currency"],
                "total": payload["total"],
                "tax_total": payload.get("tax_total") or 0.0,
                "po_number": payload.get("po_number"),
                "remit_bank_account_masked": payload.get("remit_bank_account_masked"),
                "remit_account_hash": payload.get("remit_account_hash"),
                "remit_name": payload.get("remit_name"),
                "pdf_hash": payload.get("pdf_hash"),
                "terms": payload.get("terms"),
                "raw_json": orjson.dumps(payload).decode("utf8"),
            },
        )

        session.execute(
            text(
                """
                DELETE FROM invoice_lines WHERE tenant_id=:t AND invoice_id=:i
                """
            ),
            {"t": settings.tenant_id, "i": payload["invoice_id"]},
        )

        for idx, line in enumerate(payload.get("line_items", []), start=1):
            session.execute(
                text(
                    """
                    INSERT INTO invoice_lines(
                        tenant_id, invoice_id, line_no, sku, "desc", qty, unit_price, amount, gl_code, cost_center
                    )
                    VALUES (:t,:invoice_id,:line_no,:sku,:desc,:qty,:unit_price,:amount,:gl_code,:cost_center)
                    """
                ),
                {
                    "t": settings.tenant_id,
                    "invoice_id": payload["invoice_id"],
                    "line_no": idx,
                    "sku": line.get("sku"),
                    "desc": line.get("desc"),
                    "qty": line.get("qty"),
                    "unit_price": line.get("unit_price"),
                    "amount": line.get("amount"),
                    "gl_code": line.get("gl_code"),
                    "cost_center": line.get("cost_center"),
                },
            )

        if payload.get("remit_account_hash"):
            session.execute(
                text(
                    """
                    INSERT INTO vendor_remit_accounts(tenant_id, vendor_id, remit_account_hash, remit_name)
                    VALUES (:t,:vendor_id,:hash,:name)
                    ON CONFLICT (tenant_id, vendor_id, remit_account_hash)
                      DO UPDATE SET last_seen=NOW(), remit_name=EXCLUDED.remit_name
                    """
                ),
                {
                    "t": settings.tenant_id,
                    "vendor_id": payload["vendor_id"],
                    "hash": payload["remit_account_hash"],
                    "name": payload.get("remit_name"),
                },
            )

    if os_client is not None:
        try:
            os_client.index(
                index="invoice_text",
                id=f"{settings.tenant_id}:{payload['invoice_id']}",
                body={
                    "tenant_id": settings.tenant_id,
                    "vendor_id": payload["vendor_id"],
                    "invoice_id": payload["invoice_id"],
                    "text_blob": text_blob(payload),
                },
            )
        except Exception:  # pragma: no cover - search failures should not crash API
            pass

    return payload


def _ngram_slices(text_value: str, n: int = 3) -> Iterable[str]:
    if len(text_value) < n:
        return []
    return [text_value[i : i + n] for i in range(len(text_value) - n + 1)]


def _get_cfg(key: str, default: float) -> float:
    with SessionLocal() as session:
        row = session.execute(
            text(
                """
                SELECT value FROM configs
                WHERE tenant_id=:t AND scope='global' AND key=:k
                """
            ),
            {"t": settings.tenant_id, "k": key},
        ).mappings().first()
        if not row:
            return float(default)
        value = row["value"]
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, dict) and "value" in value:
            try:
                return float(value["value"])
            except (TypeError, ValueError):  # pragma: no cover - config edge cases
                return float(default)
        try:
            return float(value)
        except (TypeError, ValueError):  # pragma: no cover - config edge cases
            return float(default)


def _persist_decision(invoice_id: str, score: float, decision: str, reasons: List[str], top: List[Dict[str, Any]]):
    explanations = top[0]["features"] if top else {}
    stmt = (
        text(
            """
            INSERT INTO decisions(
              tenant_id, decision_id, invoice_id, model_id, model_version, ruleset_version,
              risk_score, decision, reason_codes, top_matches, explanations
            )
            VALUES (:t,:decision_id,:invoice_id,:model_id,:model_version,:ruleset_version,
                    :risk_score,:decision,:reason_codes,:top_matches::jsonb,:explanations::jsonb)
            """
        )
        .bindparams(bindparam("reason_codes", type_=ARRAY(String())))
    )

    session = SessionLocal()
    with session.begin():
        session.execute(
            stmt,
            {
                "t": settings.tenant_id,
                "decision_id": f"dec_{uuid.uuid4().hex[:12]}",
                "invoice_id": invoice_id,
                "model_id": "dup_model",
                "model_version": "v1",
                "ruleset_version": "r1",
                "risk_score": score,
                "decision": decision,
                "reason_codes": reasons,
                "top_matches": orjson.dumps(top).decode("utf8"),
                "explanations": orjson.dumps(explanations).decode("utf8"),
            },
        )


@app.post("/scoreInvoice", response_model=ScoreResponse)
def score_invoice(invoice: InvoiceIn, claims=Depends(require_auth)):
    inv_payload = invoice.model_dump()
    persisted = _persist_invoice(inv_payload)
    invoice_row = _fetch_invoice(persisted["invoice_id"])

    candidates = candidate_pairs(invoice_row)

    base_lines = _fetch_invoice_lines(invoice_row["invoice_id"])
    base_lines_norm = [{"desc_norm": desc_norm(line["desc"]), **line} for line in base_lines]

    top: List[Dict[str, Any]] = []
    for candidate in candidates:
        cand_lines = _fetch_invoice_lines(candidate["invoice_id"])
        cand_lines_norm = [{"desc_norm": desc_norm(line["desc"]), **line} for line in cand_lines]
        header = header_features(invoice_row, candidate)
        line_feats = line_assign_features(base_lines_norm, cand_lines_norm)
        a_text = " ".join(line["desc_norm"] for line in base_lines_norm)
        b_text = " ".join(line["desc_norm"] for line in cand_lines_norm)
        a_ngrams = set(_ngram_slices(a_text))
        b_ngrams = set(_ngram_slices(b_text))
        overlap = len(a_ngrams & b_ngrams)
        denom = max(len(a_ngrams) + len(b_ngrams), 1)
        text_cosine = float(min(1.0, 2.0 * overlap / denom))
        feats = {**header, **line_feats, "text_cosine": text_cosine}
        dup_prob = predict_dup_prob(feats)
        top.append({
            "invoice_id": candidate["invoice_id"],
            "similarity": dup_prob,
            "features": feats,
        })

    top = sorted(top, key=lambda item: item["similarity"], reverse=True)[:3]
    dup_prob = top[0]["similarity"] if top else 0.0
    text_dup_prob = max((match["features"]["text_cosine"] for match in top), default=0.0)

    anom_prob, anom_reasons = anomaly_score(invoice_row)
    bank_change = "BANK_CHANGE" in anom_reasons

    risk_score = fuse_scores(dup_prob, anom_prob, bank_change, text_dup_prob)

    reason_codes = []
    if top:
        top_context = {
            "invoice": invoice_row,
            "candidate": next(c for c in candidates if c["invoice_id"] == top[0]["invoice_id"]),
            "features": top[0]["features"],
            "bank_change": bank_change,
        }
        reason_codes.extend(apply_rules(top_context))
    if not reason_codes and bank_change:
        reason_codes.append("BANK_CHANGE")

    reason_codes = list(dict.fromkeys(reason_codes))
    reason_codes.extend(code for code in anom_reasons if code not in reason_codes)

    hold_threshold = _get_cfg("T_hold", settings.hold_threshold_default)
    review_threshold = _get_cfg("T_review", settings.review_threshold_default)

    decision = decide(risk_score, review_threshold, hold_threshold)
    create_or_update_case(invoice_row["invoice_id"], decision)
    _persist_decision(invoice_row["invoice_id"], risk_score, decision, reason_codes, top)
    log_action(claims["sub"], "score", "invoice", invoice_row["invoice_id"], {"risk_score": risk_score, "decision": decision})

    explanations = (
        [{"feature": key, "value": value} for key, value in top[0]["features"].items()]
        if top
        else []
    )

    return {
        "risk_score": round(risk_score, 2),
        "decision": decision,
        "reason_codes": reason_codes,
        "top_matches": top,
        "explanations": explanations,
    }


@app.get("/invoice/{invoice_id}/decision")
def get_decision(invoice_id: str, claims=Depends(require_auth)):
    with SessionLocal() as session:
        row = session.execute(
            text(
                """
                SELECT risk_score, decision, reason_codes, top_matches, explanations
                FROM decisions
                WHERE tenant_id=:t AND invoice_id=:i
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"t": settings.tenant_id, "i": invoice_id},
        ).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="decision not found")
        return dict(row)


@app.get("/healthz")
def healthz():
    return {"status": "ok", "tenant": settings.tenant_id}
