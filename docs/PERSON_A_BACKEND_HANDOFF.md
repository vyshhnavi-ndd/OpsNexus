# OpsNexus backend handoff for Logesh

Status as of 2026-10-19. Person A owns synthetic-data generation/validation, Exasol intelligence SQL, Flask, and backend tests. Logesh owns ADF/SHIR, React/dashboard, Power BI, and remaining UI integration.

## Backend status

- **Synthetic data:** deterministic generator supports all eight scenarios. The operational bundle has 11 CSVs mapped to the 11 `OPS_STAGE.STG_*` tables. Semantic scenario labels, expected causes, trust bands, and rationale remain in offline `ground_truth/expected_outcomes.json`; the generator and operational SQL do not ingest it.
- **Exasol intelligence:** `OPS_INTEL.V_FINDINGS` has seven deterministic rule families: pipeline failure, stale data, incomplete data, quality failure, KPI anomaly, cross-domain inconsistency, and incident recurrence. Source mappings and thresholds are summarized below and detailed in [`EXASOL_INTELLIGENCE_ENGINE.md`](./EXASOL_INTELLIGENCE_ENGINE.md).
- **API:** read-only Flask adapter over `OPS_INTEL.V_FINDINGS`; current request/response contract and errors are in [`FLASK_API.md`](./FLASK_API.md).
- **Evidence audit UDF:** local implementation, SQL deployment file, and tests exist. It has not been deployed and is not needed for the dashboard integration; no deployment is requested by this handoff.

## Verification

On 2026-10-19 the configured read-only `OPSNEXUS_API` connection returned `CURRENT_USER=OPSNEXUS_API`; `SELECT 1` succeeded and the findings view returned 17 rows. No SYS connection was used.

The offline evaluator compared the live findings with the separate fixture labels:

| Scenario | Expected target | Live result |
|---|---|---|
| `healthy_baseline` | No findings | No findings |
| `pipeline_failure` | `PIPELINE_FAILURE` | Matched |
| `stale_data` | `STALE_DATASET` | Matched; also `QUALITY_FAILURE` |
| `incomplete_data` | `INCOMPLETE_DATA` | Matched; also `QUALITY_FAILURE` |
| `metric_anomaly` | `KPI_ANOMALY` | Matched; additional evidence-backed signals include cross-domain and quality findings |
| `cross_domain_inconsistency` | `CROSS_DOMAIN_INCONSISTENCY` | Matched |
| `recurring_incident` | `INCIDENT_RECURRENCE` | Matched; also freshness and quality findings |
| `inconclusive` | No established cause | No cause label; stale, incomplete, and quality signals remain visible |

All 17 current findings passed the local evidence-audit check. The seven families appeared in live results. This is a small synthetic fixture check, not production precision/recall evidence. The current read-only API identity cannot inspect `OPS_STAGE`; Logesh reports the staging tables and ODBC/ADF/SHIR connection were verified. ADF run status and staging row counts were not independently queried here.

## Rule inputs and evidence

| Finding family | Operational source tables | Main evidence fields | Severity |
|---|---|---|---|
| `PIPELINE_FAILURE` | `STG_PIPELINE_RUNS`, `STG_DEPENDENCIES` | Run status, start time, dependency run context, run reference | `HIGH` |
| `STALE_DATASET` | `STG_QUALITY_CHECKS`, `STG_QUALITY_RESULTS`, `STG_DATASET_OBSERVATIONS` | Observed freshness lag, selected configured limit, result/reference IDs | `HIGH` |
| `INCOMPLETE_DATA` | `STG_QUALITY_CHECKS`, `STG_QUALITY_RESULTS`, `STG_DATASET_OBSERVATIONS` | Observed/expected counts, completeness ratio, configured minimum | `HIGH` |
| `QUALITY_FAILURE` | `STG_QUALITY_RESULTS`, `STG_QUALITY_CHECKS`, `STG_DATASET_OBSERVATIONS` | Check type, measured/expected values, check/result/observation references | Freshness/completeness `HIGH`; other checks `MEDIUM` |
| `KPI_ANOMALY` | `STG_BUSINESS_KPIS`, `STG_DATASET_OBSERVATIONS`, metric-range check/results | Baseline, observed value, relative deviation, configured maximum | `MEDIUM` |
| `CROSS_DOMAIN_INCONSISTENCY` | `STG_DATASET_OBSERVATIONS`, `STG_DATASETS`, `STG_PIPELINE_RUNS`, `STG_BUSINESS_KPIS`, `STG_DEPENDENCIES` | Same metric across related domains, normalized relative gap, both source chains | `MEDIUM`; 10% is a proposed threshold |
| `INCIDENT_RECURRENCE` | `STG_INCIDENT_HISTORY` plus current run/observation/freshness results for an active recurrence | Distinct incident/event count, category, run and quality-result references | `MEDIUM`; two occurrences, with no age window |

The data generator writes timestamps in UTC ISO-8601 form. `STARTED_AT` is a timezone-naive Exasol `TIMESTAMP`, defined as UTC by the project schema. Exasol's timestamp cast drops the offset. The repository's view SQL has a pending correction to append `Z`, but it has not been deployed and the live view remains unchanged. As a temporary compatibility measure, Flask normalizes only the `started_at` value in `PIPELINE_FAILURE` evidence: naive contractually UTC values receive one `Z`, explicit offsets are converted to UTC, existing `Z` values are kept singular, and unparseable/local labels are left untouched. This API behavior and its tests are documented in [`FLASK_API.md`](./FLASK_API.md). The view does not claim recovery or root cause. Specific stale/incomplete/KPI findings can coexist with `QUALITY_FAILURE` by design. The inconclusive case is not forced into a cause label.

## Stable dashboard contract

- `GET /health`: `200` with `{ "status": "ok", "database": "connected" }`, or sanitized `503`.
- `GET /api/findings`: optional `page` (default 1), `page_size` (default 50, range 1 to 100), `finding_type`, `severity`, and opaque `scenario_instance_id`. Results sort by `finding_id` and include `data` and `pagination` (`page`, `page_size`, `total_count`, `total_pages`).
- `GET /api/findings/<finding_id>`: `{ "data": <finding> }`; valid unknown IDs return `404`.
- Finding fields: `finding_id`, `finding_type`, `severity`, nested `affected_entity` (`type`, `id`), `evidence`, `recommended_action`, `source_references`, `measured_value`, `expected_value`, `threshold`, `source_run_id`, and `scenario_instance_id`. Numeric values are strings; unavailable values are `null`.
- Errors are `{ "error": { "code": "...", "message": "..." } }`: `400` for invalid input, `404` for absent routes/findings, `405` for unsupported methods, `503` for database unavailable, and `500` for unexpected failures. Driver errors and credentials are not returned.
- The API has no built-in authentication. Keep it loopback-only or put it behind an approved authenticated gateway. Use a same-origin frontend proxy in development; CORS is not configured.

## Logesh acceptance criteria

### ADF and SHIR

1. Test the linked service from the actual SHIR host and record `CURRENT_USER`; use the dedicated non-SYS ingestion identity and validated TLS. Do not use a local DSN whose configured UID is `SYS` or whose host disables certificate checks.
2. Validate the bundle manifest and validation report before loading. Load only the 11 operational CSVs into their matching staging tables; exclude the ground-truth directory entirely.
3. Preserve opaque scenario IDs, schema version, UTC timestamps, stable source keys, and header/type mappings. Make reprocessing idempotent and record accepted/rejected row counts per file.
4. Verify staging row counts, key uniqueness, foreign-key/reference integrity, and representative rows after a test bundle. Report the evidence and run timestamp without credentials.
5. Confirm the expected finding family appears for each non-healthy scenario and healthy baseline remains empty. Do not interpret additional rule signals as a proven root cause.

### React dashboard

1. Use only the API routes above for findings; do not query raw staging tables or the ground-truth file.
2. Exercise each filter, page navigation, detail lookup, empty results, invalid input, `404`, and database-unavailable response.
3. Render `evidence`, source references, and recommended action as evidence/next-step text. Do not label a signal as a confirmed root cause or convert synthetic impact to business loss.
4. Use a same-origin proxy or approved gateway; keep the unauthenticated local API private.

### Power BI and final integration

1. Use an approved read-only identity and curated `OPS_INTEL` surface; never use `SYS` or expose raw staging/ground-truth labels to consumers.
2. Validate the live count, stable finding IDs, severity/type filters, null fields, and refresh behavior against the API/view contract.
3. Record ownership, connection identity (username only), TLS posture, validation timestamp, and any remaining limitation without storing secrets in this repository.

## Current blockers and scope

- ADF pipeline definitions/run status and staging table row counts are Logesh-owned and not independently verified by the `OPSNEXUS_API` identity.
- The API does not configure CORS or authentication; frontend integration must stay same-origin/private or use an approved gateway.
- No standalone project-plan file was present during this audit; this handoff captures backend status and acceptance criteria.
- Do not deploy the evidence-audit UDF absent a concrete requirement and separate explicit approval.

## Backend verification commands

Run from the repository root with the existing Windows project environment:

```powershell
& '.\synthetic-data\.venv\Scripts\python.exe' -m unittest discover -s synthetic-data/tests
& '.\synthetic-data\.venv\Scripts\python.exe' -m unittest discover -s infra/exasol/tests
& '.\synthetic-data\.venv\Scripts\python.exe' -m unittest discover -s api/tests
git diff --check
```

The timestamp SQL correction still requires a manual review and execution in an approved SQL client as an authorized non-SYS identity that can replace `OPS_INTEL.V_FINDINGS`. Verify `CURRENT_USER` and effective view-replacement permission in that session first. Do not use the API identity, a SYS-default Launcher connection, or an unverified ODBC DSN. Until the authorized identity is available and the SQL executes successfully, treat the live view timestamp as unchanged; the Flask normalization is the temporary workaround.
