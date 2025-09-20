# Invoice Anomaly Sieve: Architecture

**Status:** Draft v1.0  
**Owner:** Finance Ops Engineering  
**Goal:** Detect and stop duplicate and anomalous vendor invoices with vendor‑specific behavior.  
**Non‑goal:** Post payments or modify ERP data.

---

## 1. System overview

- The platform shall support two paths.
  - Online scoring path with p95 latency targets from Requirements.
  - Batch backfill path for historical scoring and model training.
- The platform shall be multi‑tenant and shall isolate data per tenant.
- The platform shall degrade to rules‑only when models are unhealthy.

---

## 2. High level topology

- Entry: API Gateway  
- Services: Ingestion, Normalization, Candidate Retrieval, Feature, Duplicate Scorer, Anomaly Scorer, Decision Engine, Case, Config, Export  
- Stores: Object Storage, Relational DB, Search Index, Feature Store, Warehouse, Model Registry, Cache  
- Messaging: Event Bus  
- Surfaces: Review UI, Admin UI, Exports

---

## 3. Core services and responsibilities

1) **Ingestion Service**
   - Shall validate the data contract.
   - Shall compute content hashes for attachments.
   - Shall write raw payloads to Object Storage.
   - Shall emit `invoice.received` on the Event Bus.

2) **Normalization Service**
   - Shall compute canonical fields: invoice_number_norm, amount_norm, desc_norm.
   - Shall be deterministic and versioned.
   - Shall enrich with vendor master snapshots.

3) **Candidate Retrieval Service**
   - Shall build and query blocking keys inside the same vendor_id.
   - Shall cap fan‑out per invoice.
   - Shall query Search Index for near‑text matches when structured blocks miss.

4) **Feature Service**
   - Shall compute pairwise header features.
   - Shall perform line matching and compute coverage and unmatched metrics.
   - Shall compute document text similarities.
   - Shall cache features for repeated pairs.

5) **Duplicate Scorer**
   - Shall load the active supervised model per tenant.
   - Shall output dup_prob and top contributory features.

6) **Anomaly Scorer**
   - Shall run vendor‑specific detectors if volume allows.
   - Shall fall back to global detectors with vendor embedding.
   - Shall output anom_prob and component reason flags.

7) **Decision Engine**
   - Shall execute deterministic rules first.
   - Shall fuse scores and apply thresholds per vendor.
   - Shall persist decision, reason codes, and top matches.
   - Shall emit `invoice.decided`.

8) **Case Service**
   - Shall create or update review cases on HOLD and REVIEW.
   - Shall store dispositions and send feedback to MLOps.

9) **Config Service**
   - Shall manage thresholds, rule toggles, and safe parameter ranges.
   - Shall expose audit‑logged, role‑gated changes.

10) **Export Service**
    - Shall provide dated exports for SOX and analytics.
    - Shall strip PII and full bank numbers.

---

## 4. Data stores and roles

- **Object Storage**  
  - Purpose: raw payloads, PDFs, extracted text, export files.  
  - Choice: S3 compatible.  
  - Must keep immutable blobs with content‑addressable paths.

- **Relational DB**  
  - Purpose: decisions, cases, configs, audit, metadata.  
  - Choice: PostgreSQL with row‑level security per tenant.  
  - Must enforce idempotency and referential integrity.

- **Search Index**  
  - Purpose: near‑text retrieval and MinHash LSH.  
  - Choice: OpenSearch.  
  - Must support character 3‑gram analyzers and MinHash signatures.

- **Feature Store**  
  - Purpose: online features for scoring and historical aggregates.  
  - Choice: dual store pattern. Online KV in Redis, offline Parquet tables in the Warehouse.  
  - Must provide point‑in‑time correctness for training.

- **Warehouse**  
  - Purpose: batch retrieval, analytics, training sets.  
  - Choice: Snowflake or BigQuery.  
  - Must host blocking tables and vendor baselines.

- **Model Registry**  
  - Purpose: versioned models, metadata, lineage.  
  - Choice: MLflow Model Registry.  
  - Must store signatures, metrics, and approval state.

- **Cache**  
  - Purpose: hot vendor baselines, candidate IDs, feature vectors.  
  - Choice: Redis with TTL.  
  - Must not be source of truth.

- **Event Bus**  
  - Purpose: decoupled processing and backpressure.  
  - Choice: Kafka or Pub/Sub.  
  - Must retain events for replay.

---

## 5. Tenancy and isolation

- Every table, topic, and object path shall carry tenant_id.
- Row‑level security shall restrict reads and writes by tenant.
- Models shall be scoped per tenant with optional shared baselines.

---

## 6. Data model essentials

- **Invoice**  
  - Keys: tenant_id, invoice_id, vendor_id, version.  
  - Snapshots shall be immutable and addressable by payload_hash.

- **Vendor snapshot**  
  - Keys: tenant_id, vendor_id, valid_from, valid_to.  
  - Shall include remit accounts and names.

- **Decision**  
  - Keys: tenant_id, decision_id, invoice_id, model_version, ruleset_version.  
  - Shall store risk_score, decision, reason codes, top match IDs, feature digest.

- **Case**  
  - Keys: tenant_id, case_id, invoice_id.  
  - Shall store status, SLA timers, user actions, disposition, notes.

---

## 7. Online scoring flow

1) Client calls synchronous score API with invoice payload.  
2) Ingestion validates and writes raw payload to Object Storage.  
3) Normalization computes canonical fields.  
4) Candidate Retrieval queries blocks and Search Index.  
5) Feature Service computes pairwise features against each candidate.  
6) Duplicate Scorer returns dup_prob and explanations.  
7) Anomaly Scorer returns anom_prob and component flags.  
8) Decision Engine applies rules, fuses scores, sets action.  
9) Persistence writes Decision and emits event.  
10) Response returns risk_score, action, reason codes, and top matches.

---

## 8. Batch and training flow

- A nightly job shall load invoices from the Warehouse by tenant and day.  
- Blocking and candidate generation shall run inside the Warehouse for cost efficiency.  
- Label join shall use reviewer dispositions and payment outcomes.  
- Training jobs shall produce per‑tenant or shared models and log to the Registry.  
- Calibration jobs shall update scalers without retraining the core model.  
- Promotion gates shall require metrics at or above acceptance criteria.

---

## 9. Retrieval and blocking detail

- Structured blocks shall be materialized tables keyed by:
  - vendor_id, round(total,2), yyyymm(invoice_date)
  - vendor_id, po_number
  - vendor_id, last4(remit_bank)
  - vendor_id, invoice_number_norm
- Near‑text paths shall index header plus line text with char 3‑grams.  
- MinHash signatures shall approximate shingle Jaccard for PDFs.  
- Candidate fan‑out cap shall be enforced per invoice with deterministic ordering:
  - rule hits first
  - same PO next
  - amount and month next
  - text neighbors last

---

## 10. Feature computation detail

- Header features shall include exact matches, edit distances, date gaps, and bank or remit deltas.  
- Line alignment shall use costed bipartite matching over normalized strings and z‑scores of unit prices and quantities.  
- Coverage features shall capture unmatched amount fraction and count of new items.  
- Text features shall use TF‑IDF cosine over header and lines.  
- All features shall be logged with stable names and units.  
- Feature governance shall version feature definitions and backfill incompatibilities.

---

## 11. Models and MLOps

- Duplicate model shall be a supervised binary classifier.  
- Anomaly detectors shall include:
  - robust z‑score baselines for totals and cadence
  - unit price regressors per SKU or text cluster
  - Isolation Forest or one‑class SVM for structure outliers
  - sequence checks for invoice_number_norm
- Model Registry shall store train data snapshot ID, code commit, parameters, metrics, and calibration curves.  
- CI shall run:
  - unit tests on normalization and feature math
  - invariant checks on feature distributions
  - canary scoring on holdout pairs  
- CD shall deploy models behind a traffic switch with shadow evaluation before promotion.  
- Drift monitors shall compute PSI and KS by vendor and shall trigger rule‑only fallback on breach.

---

## 12. Decisioning and rules

- Rule engine shall execute before ML.  
- Conflicts shall resolve to the strictest outcome.  
- Score fusion shall follow the formula in Requirements and shall be idempotent given inputs.  
- Thresholds shall be read from Config and cached with short TTL.  
- Explanations shall list top feature attributions and rule hits.

---

## 13. APIs and contracts

- **POST scoreInvoice**  
  - Purpose: synchronous scoring.  
  - Shall enforce idempotency via invoice_id and payload_hash.  
  - Shall return risk_score, decision, reason codes, top matches, and trace_id.

- **POST bulkScore**  
  - Purpose: batch scoring by object reference.  
  - Shall return a job_id and emit progress events.

- **GET decision**  
  - Purpose: retrieve persisted decision by invoice_id.  
  - Shall support pagination for match lists.

- **Webhooks**  
  - Shall support push delivery of decided invoices per vendor.

- All APIs shall require OAuth2 and tenant scope.  
- Rate limits shall be per client and per tenant.

---

## 14. Review UI and Case integration

- Review Queue shall sort by risk_score and SLA.  
- Case View shall display header diffs, line alignment, bank deltas, invoice number distance, PDF preview, and actions.  
- Dispositions shall map to labels for training and shall be immutable after 24 hours except by Admin.

---

## 15. Security, privacy, and compliance

- Data in transit must use TLS 1.2 or higher.  
- Data at rest must use AES‑256.  
- Secrets shall be stored in a managed secrets vault.  
- RBAC shall enforce least privilege with roles: Viewer, Reviewer, Admin.  
- PII and bank data shall be masked in UI and logs.  
- Audit logs shall be append‑only and tamper evident.  
- The platform shall support evidence exports for SOX with decision reconstruction.

---

## 16. Performance and scaling

- Services shall be stateless and horizontally scalable on Kubernetes.  
- Async paths shall use the Event Bus to buffer spikes.  
- Candidate Retrieval shall prewarm vendor caches for high volume vendors.  
- Search Index shall shard by tenant and vendor_id hash.  
- Warehouse jobs shall be partitioned by tenant and day.  
- Backpressure shall shed near‑text retrieval first and fall back to structured blocks.

---

## 17. Reliability and disaster recovery

- All critical stores shall be multi‑AZ.  
- Object Storage shall enable versioning and lifecycle policies.  
- Relational DB shall have PITR and daily verified backups.  
- Event Bus shall retain seven days minimum.  
- Runbooks shall define failover to rules‑only mode when:
  - Model service is unavailable
  - Feature service is degraded
  - Search Index exceeds latency SLO

---

## 18. Observability

- Metrics shall include:
  - latency per stage
  - candidate fan‑out
  - rule hit rates
  - duplicate recall at top‑1
  - reviewer precision at threshold
  - false hold rate
  - drift scores per vendor
- Tracing shall propagate a trace_id from API through all services.  
- Logs shall be structured and tenant tagged.  
- Alerts shall trigger on SLA breach, drift breach, high fan‑out, or queue backlog.

---

## 19. Configuration management

- Configs shall be stored in the Relational DB and cached.  
- Changes shall be versioned, audited, and scoped to vendor, tenant, or global.  
- Safe ranges shall be enforced for blocks, LSH, thresholds, and time windows.

---

## 20. Data quality and safeguards

- Validators shall check line sum vs header total, currency codes, date plausibility.  
- Failures shall route to REVIEW with reason codes and shall not crash scoring.  
- Attachment processing shall never execute embedded content.  
- PDF text extraction shall run in sandboxed workers.

---

## 21. Data retention

- Raw payloads shall retain for 7 years or per tenant policy.  
- Features and decisions shall retain for 7 years.  
- Training datasets and model artifacts shall retain for the model lifetime plus 2 years.  
- PII in exports shall be minimized by default.

---

## 22. Deployment and environments

- Environments shall include dev, stage, prod with isolated tenants.  
- Blue green deployments shall be supported for services and models.  
- Rollback shall restore prior config and model version atomically.  
- Schema changes shall be backwards compatible with dual write during migration.

---

## 23. Testing strategy

- Unit tests shall cover normalization and feature math with golden vectors.  
- Contract tests shall validate API schemas and error codes.  
- Simulation tests shall replay historical days and verify acceptance metrics.  
- Load tests shall validate p95 and p99 latencies with realistic fan‑out.  
- Chaos tests shall validate rule‑only fallback and data integrity.

---

## 24. Phased delivery

- Phase 1  
  - Rules engine, structured blocking, supervised duplicate model.  
  - Postgres, Redis, S3, Warehouse.  
  - Minimal Review UI.

- Phase 2  
  - Search Index LSH, vendor anomaly models, calibration jobs.  
  - Model Registry, drift monitors, shadow deployments.

- Phase 3  
  - Per vendor unit price regressors, advanced structure checks, webhook ecosystem.

---

## 25. Risk register and mitigations

- High candidate fan‑out  
  - Mitigation: strict caps, ordered blocks, sampling, cache.

- Model drift from vendor pricing changes  
  - Mitigation: weekly retrain, daily calibration, drift gates.

- Bank account spoofing  
  - Mitigation: strong bank change rules, vendor master cross‑checks, manual verification flows.

- OCR noise  
  - Mitigation: heavy reliance on totals, PO, and near‑text with char 3‑grams; human review.

---

## 26. Interfaces summary

- Inputs: invoice payloads, vendor master snapshots, attachments.  
- Outputs: risk_score, decision, reason codes, top matches, cases, exports.  
- Events: invoice.received, invoice.normalized, invoice.candidates, invoice.decided, case.updated, model.promoted.

---

## 27. Acceptance hooks

- The system shall expose a replay API for auditors that re‑scores an invoice payload with a frozen model and ruleset version and shall match the stored decision.  
- The system shall produce a single export that can reconstruct any decision within one minute using stored artifacts.
