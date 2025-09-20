# Invoice Anomaly Sieve — Requirements

**Status:** Draft v1.0  
**Owner:** Finance Ops Engineering  
**Purpose:** Detect and stop duplicate and anomalous vendor invoices.  
**Keywords:** must, must not, shall, shall not

---

## 1. Scope

- The system **shall** ingest invoices and vendor master data, score risk, and route cases to review.
- The system **shall not** initiate or block payments directly; it **shall** emit decisions for downstream systems to act on.
- The system **must** operate per vendor with optional global fallbacks.

---

## 2. Roles

- **AP Processor:** reviews cases, dispositions them.
- **Finance Ops Manager:** configures rules, thresholds, vendor policies.
- **ML Engineer:** maintains models and features.
- **Security Admin:** manages access and audit.

---

## 3. Core Concepts

- **Risk Score (0–100):** unified score per invoice.
- **Decision:** `HOLD`, `REVIEW`, or `PASS`.
- **Reason Codes:** machine‑readable strings (e.g., `NEAR_DUP_NUMBER`, `BANK_CHANGE`).
- **Top Matches:** likely duplicates with diffs.

---

## 4. Data Contract Requirements (DCR)

DCR‑001 The ingestion schema **must** accept:
| Field | Type | Required | Notes |
|---|---|---|---|
| invoice_id | string | yes | Unique per tenant |
| vendor_id | string | yes | Foreign key to vendor master |
| vendor_name | string | yes | |
| invoice_number | string | yes | Raw input |
| invoice_date | date | yes | ISO 8601 |
| currency | string(ISO 4217) | yes | |
| total | decimal(18,4) | yes | Gross amount |
| tax_total | decimal(18,4) | no | Default 0 |
| po_number | string | no | |
| remit_bank_iban_or_account | string | no | Masked in UI |
| remit_name | string | no | |
| pdf_hash | string | no | SHA‑256 of canonical PDF bytes |
| terms | string | no | |
| line_items | array | yes | see below |

DCR‑002 Each `line_items[]` element **must** contain:
- `desc` string (required)
- `qty` decimal(18,6) (required)
- `unit_price` decimal(18,6) (required)
- `amount` decimal(18,6) (required)
- `sku` string (optional)
- `gl_code` string (optional)
- `cost_center` string (optional)

DCR‑003 The system **shall** reject payloads that miss required fields with `400` and a machine‑readable error.

DCR‑004 The system **must** enforce referential integrity on `vendor_id`; unknown vendors **shall** be rejected or quarantined per configuration.

DCR‑005 Attachments **must not** be executed or rendered server‑side; only hashed and text‑extracted.

---

## 5. Normalization Requirements (NR)

NR‑001 `invoice_number_norm` **shall** be computed by:
1) uppercase, 2) remove spaces, hyphens, slashes, underscores, 3) drop prefixes `INV|INVOICE|BILL`, 4) strip leading zeros.  
Empty results **shall** resolve to `"0"`.

NR‑002 `amount_norm` **shall** be derived after currency conversion to vendor home currency using the invoice date FX rate; rounding to 2 decimals **shall** apply for blocking, not for scoring.

NR‑003 `desc_norm` **shall** lowercase, strip punctuation, collapse whitespace; tokenization **shall** use character 3‑grams for similarity.

NR‑004 All normalization steps **must** be deterministic and versioned.

---

## 6. Blocking and Candidate Retrieval (BR)

BR‑001 The system **shall** build candidate pairs only within the same `vendor_id`.

BR‑002 The system **shall** create blocking keys:
- `(vendor_id, round(total,2), yyyymm(invoice_date))`
- `(vendor_id, po_number)` where `po_number` not null
- `(vendor_id, last4(remit_bank_iban_or_account))` where available
- `(vendor_id, invoice_number_norm)`

BR‑003 A text LSH index over TF‑IDF(char‑3gram) of header+lines **shall** be used for near‑text matches when other blocks miss.

BR‑004 Candidate fan‑out **must not** exceed 200 pairs per invoice by default; overflow **shall** use highest‑recall blocks first.

---

## 7. Pairwise Duplicate Scoring (DS)

DS‑001 For each candidate pair, the system **shall** compute header features:
- `abs_total_diff_pct`, `days_diff`, `same_po`, `same_currency`, `same_tax_total`, `bank_change_flag`, `payee_name_change_flag`, `invnum_edit_distance`.

DS‑002 The system **shall** compute line‑item similarity via optimal bipartite matching (Hungarian) on cost  
`α*desc_distance + β*|unit_price_z| + γ*|qty_z|` with configurable `α,β,γ`.

DS‑003 The system **shall** compute `unmatched_amount_frac`, `median_unit_price_z`, `count_new_items`, and `line_coverage_pct`.

DS‑004 The system **shall** compute document text cosine similarity over TF‑IDF(header+lines).

DS‑005 A supervised classifier **must** output `dup_prob ∈ [0,1]`. Logistic regression or gradient boosting **shall** be supported. Model versioning **must** be recorded.

DS‑006 Feature and model inputs **shall** be tenant‑isolated.

---

## 8. Vendor Anomaly Models (VA)

VA‑001 For vendors with ≥ 50 historical invoices, vendor‑specific anomaly models **shall** be trained; otherwise global models with a vendor embedding **shall** be used.

VA‑002 The system **shall** compute:
- Amount/time anomalies: robust z‑scores via median/MAD by vendor and weekday/month patterns.
- Unit‑price anomalies: per SKU or description centroid using Huber regression; flag when `|z| ≥ k` (configurable).
- Structural anomalies: unusual `line_item_count`, new tax rates, new terms, new GL/cost center mix.
- Sequence anomalies: regressions or gaps in normalized invoice numbers.
- Counterparty anomalies: new remit bank account or remit name unseen in last 12 months.

VA‑003 An unsupervised detector (Isolation Forest or one‑class SVM) **shall** output `anom_prob ∈ [0,1]`.

---

## 9. Score Fusion and Decisioning (SD)

SD‑001 The final `risk_score` **shall** be computed as:  
`risk_score = 100 * (1 - (1-dup_prob)*(1-anom_prob)*(1-bank_change_prob)*(1-text_dup_prob))`.

SD‑002 Decision thresholds **must** be configurable globally and per vendor:
- `risk_score ≥ T_hold` → `HOLD`
- `T_review ≤ risk_score < T_hold` → `REVIEW`
- otherwise `PASS`

SD‑003 The system **shall** emit `reason_codes`, `top_matches` (id, similarity, diffs), and `explanations` (top feature contributions).

SD‑004 The system **must not** auto‑release a `HOLD` without an explicit disposition.

---

## 10. Day‑One Deterministic Rules (RR)

RR‑001 Same vendor + same `invoice_number_norm` → `HOLD`.

RR‑002 Same vendor + same `po_number` + totals within ±0.5% + dates within 30 days → `HOLD`.

RR‑003 Same vendor + identical `pdf_hash` or shingle Jaccard ≥ 0.9 → `HOLD`.

RR‑004 Same vendor + new remit bank account unseen in last 12 months → `REVIEW`.

RR‑005 Rules **must** execute before ML scoring; conflicts **shall** take the strictest outcome (`HOLD` > `REVIEW` > `PASS`).

---

## 11. Ingestion and APIs (API)

API‑001 The system **shall** expose:
- `POST /scoreInvoice` synchronous scoring, timeout 5s p95.
- `POST /bulkScore` batch by file reference, eventual result.
- `GET /invoice/{id}/decision` decision and explanations.

API‑002 APIs **must** require OAuth2 client credentials and tenant scoping.

API‑003 Payload size **shall** support invoices up to 200 line items and 5 MB attachments. Larger payloads **shall** be rejected with guidance.

API‑004 Versioned schemas (`v1`, `v2`) **shall** be supported for backward compatibility.

---

## 12. Review UI (UI)

UI‑001 The Review Queue **shall** sort by `risk_score` descending and SLA aging.

UI‑002 The Case View **shall** display:
- Header diffs (totals, dates, PO, terms).
- Line‑match table with matched/unmatched amounts and coverage.
- Bank and remit deltas with masking.
- Invoice number edit distance.
- PDF thumbnails or text preview.
- One‑click dispositions: `duplicate`, `valid`, `price_update`, `other`.

UI‑003 The UI **must not** display full bank details; last 4 characters only.

UI‑004 Dispositions **shall** persist and **shall** feed model retraining.

---

## 13. Security and Privacy (SEC)

SEC‑001 Data in transit **must** use TLS 1.2+; data at rest **must** be encrypted with AES‑256.

SEC‑002 Access control **shall** enforce least privilege via RBAC (roles: Viewer, Reviewer, Admin).

SEC‑003 Audit logs **shall** be immutable and tamper‑evident.

SEC‑004 PII and bank data **shall** be masked in UI and logs.

SEC‑005 The system **shall not** export PII to third‑party services without an explicit data processing agreement.

---

## 14. Auditability and Governance (AUD)

AUD‑001 Every decision **shall** store:
- input payload hash,
- features,
- model id/version,
- rule hits,
- thresholds,
- final decision and reason codes,
- user disposition (if any),
- timestamp and actor.

AUD‑002 The system **shall** provide export of decisions for SOX evidence.

---

## 15. Performance and Availability (NFR)

NFR‑001 Online scoring **must** achieve p95 latency ≤ 3s for invoices with ≤ 50 lines and ≤ 5 candidate pairs; ≤ 5s for up to 200 lines and ≤ 200 candidates.

NFR‑002 Availability **must** be ≥ 99.9% monthly for scoring APIs.

NFR‑003 Batch scoring **shall** support ≥ 100k invoices per hour per tenant.

NFR‑004 The system **shall** degrade gracefully by skipping text LSH when under load rather than failing the request.

---

## 16. Data Quality (DQ)

DQ‑001 The system **shall** validate:
- line item sum within 1% of header total unless tax lines explain delta,
- currency code validity,
- date plausibility (not > 365 days in future).

DQ‑002 Failed checks **shall** flag `REVIEW` with `reason_codes` and **shall not** crash scoring.

---

## 17. MLOps (ML)

ML‑001 Models **shall** be versioned and reproducible; training code, data snapshot, and parameters **must** be tracked.

ML‑002 Weekly retraining **shall** be supported; daily calibration (Platt or isotonic) **shall** be supported.

ML‑003 Drift monitors **shall** track feature and label drift per vendor; on high drift the system **shall** auto‑fallback to rules‑only mode and alert.

ML‑004 Feedback ingestion from dispositions **shall** update training labels within 24 hours.

---

## 18. Monitoring and Alerting (MON)

MON‑001 The system **shall** emit metrics:
- duplicate recall @ top‑1 suggestion,
- reviewer precision @ threshold,
- false hold rate,
- average time to resolution,
- model latency and candidate fan‑out,
- rule hit rates,
- drift scores.

MON‑002 Alerts **must** trigger on SLA breach, recall below target, or drift above threshold.

---

## 19. Configuration (CFG)

CFG‑001 Thresholds (`T_hold`, `T_review`) **shall** be configurable globally and per vendor.

CFG‑002 Rule toggles **shall** be configurable per vendor.

CFG‑003 Blocking parameters and LSH settings **shall** be configurable with safe ranges.

CFG‑004 Cold‑start vendor threshold (default 50 invoices) **shall** be configurable.

---

## 20. Edge Cases (EC)

EC‑001 Credit notes **shall** be recognized by negative totals and **shall not** be matched as duplicates of invoices.

EC‑002 Split shipments on same PO **shall** be allowed; duplicates **must not** be raised when line coverage is low but PO and dates differ significantly.

EC‑003 Currency conversions **shall** use invoice‑date FX; re‑rates **shall not** change historical scores.

EC‑004 Consolidated invoices and partials **shall** be handled by line coverage and unmatched amount thresholds.

EC‑005 Tax‑inclusive vs tax‑exclusive totals **shall** be normalized before comparisons.

---

## 21. Reporting and Export (RPT)

RPT‑001 The system **shall** provide CSV/Parquet exports of decisions, features (aggregated), and audit logs by date range and vendor.

RPT‑002 Exports **must not** include raw PII or full bank numbers.

---

## 22. Internationalization (I18N)

I18N‑001 The system **shall** support multi‑currency invoices and localized number/date formats in UI.

I18N‑002 All scoring **must** use normalized canonical formats internally.

---

## 23. Reliability and Operations (OPS)

OPS‑001 The system **shall** support blue‑green deployments with config and model rollback.

OPS‑002 Backfills **shall** be idempotent; re‑ingested invoices with same `invoice_id` **must not** create duplicate decisions.

OPS‑003 The system **shall** expose health and readiness probes.

---

## 24. Non‑Goals / Must Not (OOS)

OOS‑001 The system **must not** post journal entries or trigger payments.

OOS‑002 The system **must not** change vendor master data.

OOS‑003 The system **shall not** require ERP downtime.

---

## 25. Acceptance Criteria (AC)

AC‑001 On a labeled historical dataset, `HOLD` rule set **must** achieve ≥ 0.90 recall for confirmed duplicates with ≤ 0.05 false hold rate at vendor‑weighted average.

AC‑002 Pairwise model **shall** propose the correct duplicate in `top_matches[0]` for ≥ 95% of true duplicates.

AC‑003 Bank‑change detection **shall** flag ≥ 99% of first‑seen remit accounts in the last 12 months.

AC‑004 Online scoring p95 latency **must** meet NFR‑001 under synthetic load matching Section 15.

AC‑005 Audit trail **shall** reconstruct any decision end‑to‑end within 1 minute via exported artifacts.

AC‑006 UI **shall** allow a reviewer to disposition a case in ≤ 3 clicks and ≤ 15 seconds on average with training data.

---

## 26. Appendix A — Reason Codes

- `NEAR_DUP_NUMBER`, `EXACT_INVNUM`
- `SAME_PO_NEAR_TOTAL`
- `PDF_NEAR_DUP`
- `BANK_CHANGE`
- `UNIT_PRICE_OUTLIER`
- `STRUCTURE_ANOMALY`
- `SEQUENCE_ANOMALY`
- `NEW_TAX_RATE`
- `MISSING_REQUIRED_FIELD`
- `DATA_QUALITY_CHECK_FAIL`

---

## 27. Appendix B — Default Parameters

- `T_hold = 80`, `T_review = 50`
- LSH candidates cap = 200
- Date window for same‑PO rule = 30 days
- Total tolerance for same‑PO rule = 0.5%
- Vendor history window for bank change = 12 months
- Cold‑start cutoff = 50 invoices

---

## 28. Appendix C — Logging Fields

- `decision_id`, `tenant_id`, `vendor_id`, `invoice_id`
- `payload_hash`, `pdf_hash`
- `features_digest` (hashed or summarized)
- `model_id`, `model_version`, `ruleset_version`
- `risk_score`, `decision`, `reason_codes`
- `top_match_ids` with similarities
- `timestamp_created`, `timestamp_decided`, `actor`

---
