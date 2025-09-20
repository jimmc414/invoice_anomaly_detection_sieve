# Invoice Anomaly Sieve Runbook

This runbook documents day-2 operations for the Invoice Anomaly Sieve scoring service. It covers
monitoring, routine procedures, and incident response for the FastAPI API, supporting services, and
offline jobs.

## Service summary

| Item | Detail |
| --- | --- |
| **Service** | Invoice Anomaly Sieve |
| **Description** | Scores vendor invoices for duplicate/anomalous behavior and routes suspect cases to review. |
| **Owners** | Finance Ops Engineering (primary), Data/ML Platform (secondary). |
| **Runtime** | Python 3.11, FastAPI, uvicorn (`app/main.py`). |
| **Default port** | 8080 |
| **Authentication** | JWT bearer token validated by `app.security.require_auth`; `devtoken` bypass for local usage. |
| **Data stores** | PostgreSQL, Redis, MinIO (S3), OpenSearch, MLflow, Redpanda (Kafka-compatible). |
| **Critical dependencies** | `app/storage.py` configured DSNs and clients, Docker services from `ops/docker-compose.yaml`. |
| **Documentation** | [`README.md`](README.md), [`architecture.md`](architecture.md), [`implementation.md`](implementation.md). |

## On-call daily checklist

1. Confirm API health from the load balancer or uptime monitor (expect <200 ms p95 in steady state).
2. Review latency, candidate fan-out, and error-rate dashboards.
3. Check drift and model health alerts (duplicate ROC-AUC shadow eval, anomaly false hold rate).
4. Verify overnight batch jobs (vendor baselines, duplicate training, backfills) completed and
   uploaded results to MLflow / object storage.
5. Skim audit logs for unusual HOLD surge or bank-change spikes.

## Environments

| Environment | Notes |
| --- | --- |
| **Local / Dev** | Run via `uvicorn app.main:app --reload`; dependencies launched with `docker compose -f ops/docker-compose.yaml up -d`. |
| **Stage** | Mirrors production DSN/queues with smaller datasets; use for release validation and replay tests. |
| **Prod** | Multi-AZ deployment, autoscaling, strict RBAC, TLS termination at gateway. |

## Runtime operations

### Start / stop the service

```bash
# Start (local/dev example)
uvicorn app.main:app --host 0.0.0.0 --port 8080 --workers 4

# Stop (Ctrl+C or orchestrator scale-down)
```

In Kubernetes, ensure liveness probes call `GET /healthz` (add if absent) and readiness probes check
database connectivity.

### Verify scoring end-to-end

1. Insert or identify a sample invoice payload (e.g., `samples/invoice_example.json`).
2. Call the API:
   ```bash
   curl -s -X POST http://<host>:8080/scoreInvoice \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d @samples/invoice_example.json | jq
   ```
3. Confirm response includes `risk_score`, `decision`, and non-empty `trace_id`.
4. Query PostgreSQL to ensure the invoice and decision rows were persisted:
   ```sql
   SELECT decision, risk_score FROM decisions WHERE invoice_id='<invoice_id>';
   ```

### Initialize or rebuild infrastructure

Run the bundled scripts when onboarding a new environment or after destructive maintenance:

```bash
make init  # runs scripts/init_db.py, scripts/init_s3.py, scripts/init_search.py
```

Individual components:

- `python scripts/init_db.py` – executes `app/schema.sql` to create tables/indexes.
- `python scripts/init_s3.py` – ensures the MinIO/S3 bucket exists for invoice blobs.
- `python scripts/init_search.py` – recreates the `invoice_text` OpenSearch index using the template
  in `app/index_templates/invoices_text.json`.

### Configuration changes

- Runtime configuration is sourced from environment variables in `app/config.py` (DB_DSN, REDIS_URL,
  thresholds, tenant ID, JWT params).
- Persist configuration overrides in your secrets manager / deployment manifests; changes require a
  rolling restart.
- Threshold changes (`HOLD_THRESHOLD_DEFAULT`, `REVIEW_THRESHOLD_DEFAULT`) should be coordinated with
  Finance operations to avoid unexpected HOLD volume.

## Batch and model operations

### Duplicate model refresh

1. Ensure recent invoices and reviewer dispositions are loaded in PostgreSQL.
2. Run the trainer:
   ```bash
   python scripts/train_duplicate.py
   ```
3. Validate the console output for ROC-AUC / Average Precision metrics.
4. Upload the resulting artifact (`models/dup_model.joblib` by default) to the model registry or ship
   with the deployment package.
5. Restart API pods to load the new model (cached by `app.duplicate_model.load_model`).

If the trainer reports "Not enough labeled data" the service falls back to heuristic weights, which
is acceptable for low-volume tenants.

### Vendor anomaly baseline refresh

```bash
python scripts/train_anomaly.py
python scripts/calc_vendor_baselines.py
```

These scripts compute and persist `vendor_amount_baselines` used by `app.anomaly.anomaly_score`.
Schedule nightly; rerun manually if large vendor behavior shifts occur.

### Backfill decisions

Use `scripts/backfill_score.py` to rescore historical invoices after significant logic changes. Run
per tenant or date range to control load and confirm database capacity before launching.

## Monitoring and alerts

Recommended telemetry (align with architecture section 18):

- **Latency** – overall API, candidate retrieval, feature computation, duplicate model scoring,
  anomaly scoring, decision persistence.
- **Fan-out** – number of candidate invoices per request; alert if consistently >200 (retrieval cap).
- **Rules vs ML mix** – rate of HOLD/REVIEW triggered by rules vs models; sudden shifts may indicate
  drift or misconfiguration.
- **Duplicate precision/recall** – track via shadow evaluation on adjudicated cases; degrade triggers
  model retraining or threshold tuning.
- **Bank change rate** – proportion of invoices flagged with `BANK_CHANGE` reason codes.
- **Infrastructure** – DB connections, Redis latency, OpenSearch cluster health, MLflow availability,
  S3 bucket errors.

Log aggregation should preserve `tenant_id`, `invoice_id`, and `trace_id` from request contexts for
correlation. Persisted audit logs via `app.audit.log_action` support SOX evidence and should be
forwarded to cold storage.

## Incident response playbooks

### API returning 5xx or timing out

1. Check service logs for traceback; 5xx often stem from database connectivity issues.
2. Validate PostgreSQL availability (connection limits, replication lag). Restart session pods if
   necessary.
3. Inspect Redis and OpenSearch; if optional dependencies are down, expect degraded functionality but
   API should continue (search writes are wrapped in try/except).
4. If degradation persists, route traffic to a standby deployment or enable maintenance mode.

### Database initialization or migration failure

1. Re-run `python scripts/init_db.py` and inspect output for offending SQL statement.
2. Ensure the deployment identity has privileges to create schemas, indices, and run idempotent
   `INSERT ... ON CONFLICT` statements defined in `app/schema.sql`.
3. On production, apply migrations via a controlled Alembic revision and double-write if downtime
   would violate SLOs.

### Search index unhealthy

1. OpenSearch issues surface as increased candidate miss rates and drop in duplicate detection.
2. Check cluster health via `_cluster/health`; if red, restart the node or fail over.
3. Recreate the index using `python scripts/init_search.py` after confirming data retention (only
   derived text is stored, so rebuild is safe).
4. During outage, scoring continues using structured blocking with reduced recall.

### High false HOLD rate / model drift

1. Review drift dashboards (PSI/KS per vendor) and rule hit distribution.
2. Confirm recent config or threshold changes; revert if misapplied.
3. Trigger duplicate trainer and anomaly baseline refresh; deploy new artifacts after validation.
4. If precision remains poor, temporarily raise HOLD threshold or enable rules-only mode by removing
   the model artifact (`models/dup_model.joblib`) so the fallback heuristics run.

### Bank account spoofing incident

1. Identify impacted vendor and invoices (audit reason code `BANK_CHANGE`).
2. Freeze payments externally if needed.
3. Verify vendor remit accounts in `vendor_remit_accounts` table for abnormal churn.
4. Coordinate with Finance to validate bank changes and update allow-lists.

## Disaster recovery

- **Database** – restore from latest PITR snapshot; replay `invoice.decided` events or audit logs to
  rebuild downstream systems.
- **Object storage** – S3/MinIO buckets use versioning; recover prior payloads if ingestion corrupted
  data.
- **Search** – rebuild index from PostgreSQL using `scripts/init_search.py` and `text_blob` helper in
  `app.normalization`.
- **Models** – fetch previous approved artifact from MLflow registry and redeploy.

Document failover drills annually and validate that rules-only mode maintains minimum viable fraud
coverage when ML services are offline.

## Support and escalation

- Pager rotation: Finance Ops Eng (primary), Data/ML Platform (secondary).
- Slack: `#finops-invoice-sieve` (primary), `#ml-platform` (model support).
- Email: invoice-sieve-oncall@company.example.
- Vendor support: escalate to Procurement Ops if supplier master data is stale.

Record all incidents in the team's tracker with postmortem templates referencing this runbook.
