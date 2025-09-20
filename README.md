# Invoice Anomaly Sieve

Invoice Anomaly Sieve detects duplicate or anomalous vendor invoices. It exposes a FastAPI service
for scoring invoices, routing suspect items to review, and maintaining audit trails. The
implementation follows the requirements and architecture documents in this repository.

## Features

- FastAPI scoring endpoint that ingests invoices, normalizes fields, computes candidate matches,
  and fuses duplicate/anomaly signals into a unified risk score.
- Deterministic rules (same invoice number, PO near total, PDF hash, bank change) with configurable
  thresholds.
- Feature engineering for header similarity, line-item assignment, and lightweight text similarity.
- Persistence in PostgreSQL with idempotent invoice storage, audit logs, and case creation.
- Vendor-specific anomaly detection heuristics and bank account change monitoring.
- Scripts to initialize local infrastructure, train baseline models, backfill decisions, and compute
  vendor baselines.

## Repository layout

See [`implementation.md`](implementation.md) for the authoritative structure. Key folders:

- `app/` – FastAPI application modules and SQL schema.
- `scripts/` – Utilities for initializing infra and running training/backfill jobs.
- `ops/` – Docker Compose and environment files for local dependencies.
- `tests/` – Unit tests that exercise normalization, rules, features, and decision logic.
- `samples/` – Example invoice payloads for manual testing.

## Getting started

1. Create a virtual environment and install dependencies:
   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install --upgrade pip
   pip install -e .[dev]
   ```
2. Start local infrastructure:
   ```bash
   docker compose -f ops/docker-compose.yaml up -d
   ```
3. Initialize storage targets and indices:
   ```bash
   make init
   ```
4. Run the API:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
   ```
5. Score an invoice:
   ```bash
   curl -s -X POST http://localhost:8080/scoreInvoice \
     -H "Authorization: Bearer devtoken" \
     -H "Content-Type: application/json" \
     -d @samples/invoice_example.json | jq
   ```

## Development

- `make fmt` runs Ruff autofix and a best-effort mypy pass.
- `make test` executes the unit test suite.
- `scripts/train_duplicate.py` derives weak labels from stored invoices to train a logistic regression
  duplicate detector. The model artifact is saved to `models/dup_model.joblib` and automatically
  loaded by the API.
- `scripts/train_anomaly.py` calculates vendor amount baselines and stores them for online use.
- `scripts/backfill_score.py` replays historical invoices and persists refreshed decisions.

## Security & operations

- Authentication uses a local JWT stub for development; replace with your SSO provider before
  production use.
- Tenant isolation is enforced via scoped queries using the configured `TENANT_ID`.
- Audit logs capture every scoring action. Decisions and cases are immutable records with timestamps
  for compliance traceability.

Refer to `requirements.md` and `architecture.md` for the full specification and rationale behind the
components delivered here.
