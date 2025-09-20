# Invoice Anomaly Sieve

Invoice Anomaly Sieve is a FastAPI service that scores vendor invoices for duplicate or anomalous
behavior, routes suspect items to review, and maintains auditable decision trails. The project
implements the requirements and architecture captured in [`requirements.md`](requirements.md) and
[`architecture.md`](architecture.md) while providing a runnable reference stack for local
development and testing.

## Table of contents

- [Overview](#overview)
- [Key capabilities](#key-capabilities)
- [Core architecture and data flow](#core-architecture-and-data-flow)
- [Local development quickstart](#local-development-quickstart)
- [Repository layout](#repository-layout)
- [Configuration](#configuration)
- [Operational dependencies](#operational-dependencies)
- [API surfaces](#api-surfaces)
- [Models and offline jobs](#models-and-offline-jobs)
- [Quality and testing](#quality-and-testing)
- [Observability and logs](#observability-and-logs)
- [Additional documentation](#additional-documentation)

## Overview

The service receives invoice payloads, normalizes and enriches the data, retrieves historical
candidates from storage and search, computes pairwise similarity features, and combines deterministic
rules with machine learning scores to produce a final risk score and action. Persisted decisions,
audit logs, and case artifacts ensure every outcome can be reconstructed for compliance purposes.

## Key capabilities

- **Real-time scoring** – `POST /scoreInvoice` ingests an invoice, applies normalization, retrieves
  historical candidates, and fuses rule, duplicate, and anomaly signals into a 0–100 risk score.
- **Rules-first decisioning** – deterministic duplicate and fraud heuristics execute before ML
  scoring and can force HOLD/REVIEW outcomes when thresholds are breached.
- **Vendor-aware anomaly detection** – vendor baselines capture historical behavior to detect amount
  outliers and bank account changes.
- **Persistent audit trail** – invoices, candidate pairs, decisions, cases, and audit entries are
  stored in PostgreSQL so decisions are reproducible.
- **Extensible offline workflows** – scripts train and refresh models, seed infrastructure, and
  replay historical invoices for backfills.

## Core architecture and data flow

The codebase maps to the layered architecture described in `architecture.md`:

1. **Ingestion & persistence** (`app/main.py`, `app/normalization.py`, `app/storage.py`) validate the
   payload, compute normalized fields, and store invoices, lines, and vendor remit accounts.
2. **Candidate retrieval** (`app/retrieval.py`) queries PostgreSQL for structured blocks (amount,
   PO, bank account hash, invoice number). Optional OpenSearch indexing is used for near-text
   retrieval when configured.
3. **Feature engineering** (`app/features.py`) computes header, line-level, and text similarity
   metrics used by the duplicate model.
4. **Duplicate scoring** (`app/duplicate_model.py`) loads a trained logistic regression model when
   available or falls back to heuristic weights.
5. **Anomaly scoring** (`app/anomaly.py`) evaluates vendor-specific baselines, unit price outliers,
   and bank account changes.
6. **Decisioning & cases** (`app/decision.py`, `app.rules`, `app.case`, `app.audit`) fuse signals,
   apply thresholds, and persist audit trails and review cases.

A nightly batch path (see `scripts/` and `models/`) supports vendor baseline refreshes, duplicate
model training, and backfill scoring.

## Local development quickstart

### Prerequisites

- Python 3.11+
- Docker (for PostgreSQL, Redis, MinIO, OpenSearch, Redpanda, MLflow)
- `make`, `curl`, and `jq`

### Environment setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
pip install -e .[dev]
```

### Start local dependencies

```bash
docker compose -f ops/docker-compose.yaml up -d
make init  # creates database schema, object storage bucket, and OpenSearch index
```

### Run the API locally

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

### Smoke test the scoring endpoint

```bash
curl -s -X POST http://localhost:8080/scoreInvoice \
  -H "Authorization: Bearer devtoken" \
  -H "Content-Type: application/json" \
  -d @samples/invoice_example.json | jq
```

### Shut down infrastructure

```bash
docker compose -f ops/docker-compose.yaml down
```

## Repository layout

| Path | Purpose |
| --- | --- |
| `app/` | FastAPI application modules (API entrypoint, config, storage, feature engineering, rules, anomaly, duplicate model, cases, audit). |
| `models/` | Model artifacts such as the trained duplicate model (`dup_model.joblib`). |
| `ops/` | Docker Compose definitions and environment files for local infrastructure. |
| `samples/` | Example invoice payloads for manual testing. |
| `scripts/` | Operational scripts to initialize storage, train models, compute vendor baselines, and backfill decisions. |
| `tests/` | Unit tests covering normalization, rules, features, and decision fusion. |
| `Makefile` | Convenience targets for initialization (`make init`), formatting (`make fmt`), and tests (`make test`). |

For the authoritative blueprint, refer to [`implementation.md`](implementation.md).

## Configuration

Runtime behavior is controlled via environment variables parsed in `app/config.py`:

| Variable | Default | Description |
| --- | --- | --- |
| `APP_ENV` | `dev` | Environment label used for logging and behavior toggles. |
| `DB_DSN` | `postgresql+psycopg://postgres:postgres@localhost:5432/sieve` | SQLAlchemy DSN for PostgreSQL. |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis URL for caching and feature storage. |
| `S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET` | — | Object storage connection for raw invoice payloads and model artifacts. |
| `OS_HOST` | `http://localhost:9200` | OpenSearch endpoint for near-text retrieval. |
| `MLFLOW_TRACKING_URI` | `http://localhost:5001` | MLflow tracking server used for model lineage. |
| `TENANT_ID` | `tenant_demo` | Current tenant identifier applied to all persisted records. |
| `JWT_SECRET`, `JWT_AUDIENCE`, `JWT_ISSUER` | — | Authentication parameters for JWT validation. |
| `HOLD_THRESHOLD_DEFAULT`, `REVIEW_THRESHOLD_DEFAULT` | `80`, `50` | Default risk score thresholds applied when vendor overrides are absent. |
| `DUP_MODEL_PATH` | `models/dup_model.joblib` | Path to the duplicate model artifact; if missing, heuristic fallback weights apply. |

## Operational dependencies

Local development relies on the services defined in `ops/docker-compose.yaml`:

- **PostgreSQL 16** – decision store, invoice metadata, cases, vendor baselines (`scripts/init_db.py`).
- **Redis 7** – caching layer for hot features (optional during unit tests).
- **MinIO** – S3-compatible object store for raw invoice blobs and MLflow artifacts (`scripts/init_s3.py`).
- **OpenSearch 2.13** – near-text retrieval index seeded via `scripts/init_search.py`.
- **Redpanda** – Kafka-compatible event bus placeholder for asynchronous flows.
- **MLflow** – experiment tracking and model registry.

Each service exposes a health check in Compose and is required for end-to-end scoring parity with the
architecture document.

## API surfaces

### `POST /scoreInvoice`

Synchronously score a single invoice.

- **Auth** – Bearer token, with `devtoken` accepted for local development.
- **Request body** – conforms to `app.models.InvoiceIn` and includes header fields, vendor metadata,
  line items, and optional attachments.
- **Response** – `app.models.ScoreResponse` containing:
  - `risk_score` – fused 0–100 risk score.
  - `decision` – `PASS`, `REVIEW`, or `HOLD`.
  - `reason_codes` – deterministic rules and anomaly components triggered during scoring.
  - `top_matches` – candidate invoices contributing to the decision.
  - `trace_id` – identifier for correlating logs and audit entries.

Additional API contracts (`bulkScore`, `decision`, webhooks) are specified in
[`architecture.md`](architecture.md) for future expansion.

## Models and offline jobs

Offline workflows live in `scripts/` and `models/`:

- `scripts/train_duplicate.py` – trains or refreshes the logistic regression duplicate detector using
  historical invoices stored in PostgreSQL. Results are saved to `models/dup_model.joblib` by default.
- `scripts/train_anomaly.py` / `scripts/calc_vendor_baselines.py` – compute vendor-level amount
  baselines used by `app.anomaly.anomaly_score`.
- `scripts/backfill_score.py` – replays historical invoices through the scoring stack to recompute
  decisions, useful after model or rules changes.
- `scripts/init_*` – idempotent setup for database schema, OpenSearch index, and object storage.

Model and data lineage are recorded in MLflow when `MLFLOW_TRACKING_URI` points at a running
tracking server.

## Quality and testing

- `make fmt` – runs Ruff for linting with autofix and a best-effort mypy type check.
- `make test` – executes the unit test suite (`pytest`).
- Tests focus on deterministic behaviors (normalization, feature calculations, rule firing, decision
  fusion) to keep the reference implementation verifiable.

## Observability and logs

- Structured logs include `tenant_id`, `invoice_id`, and `trace_id` fields for correlation.
- Metrics recommended by the architecture include per-stage latency, candidate fan-out, duplicate
  recall, reviewer precision, and drift indicators. Surface these via your observability stack when
  deploying beyond local development.
- Audit logs created through `app.audit.log_action` capture scoring operations, decisions, and case
  actions for compliance review.

## Additional documentation

- [`architecture.md`](architecture.md) – system design, data flow, and platform considerations.
- [`implementation.md`](implementation.md) – detailed implementation plan and file-by-file guidance.
- [`requirements.md`](requirements.md) – functional and non-functional requirements.
- [`runbook.md`](runbook.md) – operational procedures, monitoring, and incident response guidance.
