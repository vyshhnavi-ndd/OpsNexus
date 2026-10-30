# OpsNexus documentation overview

This file consolidates the project documentation formerly kept as separate
Markdown files in this folder. It summarizes the maintained local application,
API and dashboard contracts, Exasol setup, synthetic-data schema, intelligence
rules, ADF handoff, and validation status.

The PDF documents in this folder are retained as supplementary project
references. See [`how to run.txt`](how%20to%20run.txt) for step-by-step local
startup instructions. For source-of-truth implementation details, use the
code and contracts identified below.

## Project and implementation status

OpsNexus is a data operations and observability prototype built around React,
Flask, Exasol, and synthetic operational data. The maintained integrated
dashboard is in `frontend/`, served by the Flask application in `api/`.
`exasol-dashboard/` is a separate supplied dashboard, and `backend/` is a
separate legacy service with independent configuration requirements.

The repository does not provision Azure resources, deploy ADF pipelines, or
configure Power BI. ADF/SHIR and Power BI details below describe proposed
contracts and integration acceptance checks, not resources deployed by this
project.

The operational data flow is:

1. Synthetic bundles or approved operational sources supply records.
2. An approved loader or future ADF/SHIR integration validates and loads
   operational records into `OPS_STAGE`.
3. Exasol SQL publishes the curated `OPS_INTEL.V_FINDINGS` view.
4. The Flask API reads that view with a dedicated read-only identity.
5. The integrated React dashboard presents findings, evidence, and
   recommendations.

`OPS_SOURCE` is reserved for optional source/reference data. Ground-truth
labels are isolated test/evaluation data and must never be treated as
operational evidence.

## Local application setup

Commands assume Windows PowerShell from the repository root.

### Python environment and dependencies

The synthetic-data package requires Python 3.11 or later. Create the
environment only if it does not already exist, then install the package and
API dependencies:

```powershell
py -3.11 -m venv .\synthetic-data\.venv
& '.\synthetic-data\.venv\Scripts\python.exe' -m pip install -e .\synthetic-data
& '.\synthetic-data\.venv\Scripts\python.exe' -m pip install -r .\api\requirements.txt
```

### Exasol and API configuration

1. Start the existing Exasol Personal deployment using its supported launcher.
   The local run guide uses:

   ```powershell
   & '.\Deployment\exasol.exe' start
   ```

   Confirm current connection information with the approved launcher/client
   configuration.
2. Copy `api/.env.example` to the ignored local file `api/.env`.
3. Configure the Exasol host and port, a dedicated read-only non-`SYS` API
   identity, and TLS validation. For local self-signed certificates, use the
   configured SHA-256 certificate fingerprint pin; otherwise validate the
   certificate through the trusted CA configuration.
4. Keep passwords in an approved secret store or protected local
   configuration. Never commit or print credentials.
5. The API identity should have only `CREATE SESSION`, `USAGE ON SCHEMA
   OPS_INTEL`, and `SELECT ON VIEW OPS_INTEL.V_FINDINGS`. The SQL grant script
   is `infra/exasol/sql/04_grant_findings_api_readonly.sql`; an authorized
   administrator must create/identify the account and apply grants.

The API rejects `SYS`. Do not bypass certificate validation or grant the API
identity access to staging tables as a workaround.

### Run the integrated dashboard

Start Flask from the repository root:

```powershell
& '.\synthetic-data\.venv\Scripts\python.exe' -m flask --app api.app run --host 127.0.0.1 --port 5000
```

Open <http://127.0.0.1:5000/>. Flask serves the built frontend from
`api/static/`. For frontend changes, rebuild from `frontend/`:

```powershell
Set-Location .\frontend
npm install
npm run build
Set-Location ..
```

For Vite hot reload, run `npm run dev` in `frontend/`; its proxy sends
`/api` and `/health` to Flask at `127.0.0.1:5000`.

The API has no built-in authentication. Keep it bound to loopback for local
use, or put it behind an approved authenticated gateway before broader access.
The optional Ollama assistant uses `OLLAMA_URL` and `OLLAMA_MODEL` from
`api/.env`; it uses curated finding evidence and does not generate or execute
SQL.

### Separate supplied dashboard

`exasol-dashboard/` is a second Vite app. Its intelligence page uses the
findings API at port `5001`; its staging/ADF panels use the separate legacy
`backend/` at port `5000`.

Start the findings API from the repository root:

```powershell
& '.\synthetic-data\.venv\Scripts\python.exe' -m flask --app api.app run --host 127.0.0.1 --port 5001
```

Then in another terminal:

```powershell
Set-Location .\exasol-dashboard
npm install
npm run dev
```

Open <http://127.0.0.1:5173/>. The legacy backend requires its own approved
non-`SYS` Exasol identity and validated TLS before its Exasol features can be
used. Do not copy credentials between services.

## Exasol setup and schema

Exasol Personal is the selected local database. This repository does not
provision a database. Exasol Docker DB is not the selected path; its
distribution has evaluation-oriented constraints and requires Linux.

Review the SQL scripts in order:

1. `infra/exasol/sql/01_create_schemas.sql` — creates `OPS_SOURCE`,
   `OPS_STAGE`, and `OPS_INTEL`.
2. `infra/exasol/sql/02_create_staging_tables.sql` — creates 11
   `OPS_STAGE.STG_*` operational tables.
3. Load validated operational data using an approved loader.
4. `infra/exasol/sql/03_create_intel_findings.sql` — creates the curated
   intelligence view after staging data is ready.
5. `infra/exasol/sql/04_grant_findings_api_readonly.sql` — grants the API
   identity read-only access to the view.
6. `infra/exasol/sql/05_create_evidence_audit_udf.sql` — optional evidence
   audit script; not required by the dashboard and requires separate
   deployment approval and script-creation privileges.

Use authorized identities, verify `CURRENT_USER`, and keep the database
private. Do not use a `SYS`-default Launcher connection for API access or
ordinary deployment. Do not make Exasol publicly reachable.

## Findings engine

The intelligence view is `OPS_INTEL.V_FINDINGS` in
`infra/exasol/sql/03_create_intel_findings.sql`. It reads operational staging
tables only and does not read ground-truth labels. Finding IDs are stable for
unchanged source keys and relationships. Consumers should order results
explicitly because view output order is not guaranteed.

| Finding family | Summary |
| --- | --- |
| `PIPELINE_FAILURE` | Reports failed runs and related dependency-run context. A skipped dependent run is not misrepresented as a separate failure. |
| `STALE_DATASET` | Reports configured freshness failures or lag beyond the configured threshold. |
| `INCOMPLETE_DATA` | Reports insufficient observed rows/completeness against configured expectations. |
| `QUALITY_FAILURE` | Reports failed configured quality checks; can coexist with more specific findings. |
| `KPI_ANOMALY` | Reports relative deviation against a non-zero baseline and configured metric-range threshold. |
| `CROSS_DOMAIN_INCONSISTENCY` | Compares matching metrics across related domains; the documented 10% relative-gap threshold is a proposal, not a source-contract value. |
| `INCIDENT_RECURRENCE` | Reports at least two distinct occurrences; the proposed rule has no age window because the source contract defines none. |

Findings carry type, severity, affected entity, human-readable evidence,
recommended action, source references, and optional run/scenario/numeric
values. A finding is an investigation signal, not proof of root cause or
successful recovery. KPI impacts in the synthetic fixtures are illustrative,
not measured business loss.

The optional `OPS_INTEL.AUDIT_FINDING_EVIDENCE` UDF checks evidence and
reference quality. It does not change finding rules or infer causes. Its
Python implementation is `infra/exasol/udf/evidence_audit.py`.

## Flask API and dashboard contracts

The maintained API is `api/app.py`. It is a read-only adapter for
`OPS_INTEL.V_FINDINGS`; it does not read staging tables or offline ground
truth.

| Endpoint | Behavior |
| --- | --- |
| `GET /health` | Checks API/database availability; reports connected status or sanitized `503`. |
| `GET /api/findings` | Lists findings with optional page, page size, finding type, severity, and opaque scenario filters. |
| `GET /api/findings/<finding_id>` | Returns a finding or `404`. |
| `POST /api/rag/query` | Optional local Ollama assistant using curated finding evidence. |
| `GET /api/requests` | Lists local workflow requests. |
| `POST /api/requests` | Creates a local workflow request; does not write to Exasol. |

The findings list uses `page` (default `1`) and `page_size` (default `50`,
allowed `1`–`100`). Finding-type and severity filters are case-insensitive.
Results are ordered by finding ID and include pagination totals. Finding
values that are absent are JSON `null`; numeric database values are serialized
as strings to preserve precision.

Errors use a sanitized JSON object with `error.code` and `error.message`.
Invalid filters/pagination return `400`; unknown findings return `404`;
unsupported methods return `405`; database unavailability returns `503`; and
unexpected failures return `500`. Database driver messages and credentials
are not returned.

Data requests accept `dataset`, `reason`, and `priority`. The `dataset_id` and
`business_justification` fields are not aliases. Requests are persisted in
local SQLite storage, not Exasol. In the separate dashboard, unavailable
values should be rendered as **Unavailable**, unsupported features as
**Not configured**, and an actual numeric zero must remain `0`.

The shared dashboard route/request contract is in `contracts/dashboard_api.json`.
Keep frontend, Flask routes, and Vite proxy behavior aligned with that
contract.

## Synthetic data and Module 1 → Module 2 contract

`synthetic-data/` generates deterministic synthetic records using schema
version `2.0.0`. It makes no Azure calls and requires no cloud credentials.
The checked-in example bundle is
`synthetic-data/examples/seed-20261014/`.

From the repository root, generate and validate a bundle by running:

```powershell
Set-Location .\synthetic-data
& '.\.venv\Scripts\python.exe' -m opsnexus_synthetic generate --seed 20261014 --out examples/seed-20261014
& '.\.venv\Scripts\python.exe' -m opsnexus_synthetic validate examples/seed-20261014
Set-Location ..
```

The 11 operational files map to staging tables as follows:

| CSV | Staging table |
| --- | --- |
| `data_sources.csv` | `OPS_STAGE.STG_DATA_SOURCES` |
| `pipeline_definitions.csv` | `OPS_STAGE.STG_PIPELINE_DEFINITIONS` |
| `pipeline_runs.csv` | `OPS_STAGE.STG_PIPELINE_RUNS` |
| `datasets.csv` | `OPS_STAGE.STG_DATASETS` |
| `dataset_observations.csv` | `OPS_STAGE.STG_DATASET_OBSERVATIONS` |
| `quality_checks.csv` | `OPS_STAGE.STG_QUALITY_CHECKS` |
| `quality_results.csv` | `OPS_STAGE.STG_QUALITY_RESULTS` |
| `dependencies.csv` | `OPS_STAGE.STG_DEPENDENCIES` |
| `business_kpis.csv` | `OPS_STAGE.STG_BUSINESS_KPIS` |
| `incident_history.csv` | `OPS_STAGE.STG_INCIDENT_HISTORY` |
| `scenario_metadata.csv` | `OPS_STAGE.STG_SCENARIO_METADATA` |

The data contract defines stable record keys, schema version, UTC ISO-8601
timestamps, opaque scenario-instance IDs, and references between entities.
Re-running the same generator/schema/seed produces deterministic output;
`manifest.json` provides bundle ID, file schemas, and row counts.

`validation-report.json` is local pre-ingestion validation metadata. ADF or
another loader should validate the manifest, report, file set, exact headers,
types, keys, references, and counts before publication. Use
`(bundle_id, relative file path)` as a batch identity and make exact replays
idempotent. Reject or quarantine incomplete/invalid bundles and do not
partially publish them.

The scenario fixtures are `healthy_baseline`, `pipeline_failure`,
`stale_data`, `incomplete_data`, `metric_anomaly`,
`cross_domain_inconsistency`, `recurring_incident`, and `inconclusive`.
Semantic names and expected outcomes are recorded only in
`ground_truth/expected_outcomes.json`; operational records use opaque
scenario-instance tokens and generic `SYNTHETIC_DEMO` metadata.
**Never ingest or expose the ground-truth file as operational evidence.**
The fixtures do not assert recovery outcomes.

## ADF/SHIR handoff

ADF is a proposed integration and is not provisioned here. The selected
Self-Hosted Integration Runtime (SHIR) must privately reach Exasol, use an
approved Exasol ODBC driver, and validate TLS. A developer workstation's
`127.0.0.1` is not a remote endpoint for ADF. Final network topology,
firewall, DNS, routing, certificates, and driver compatibility must be
approved by the platform owner. Do not expose Exasol publicly.

Recommended process:

1. Validate bundle metadata and reject bundles whose report is invalid.
2. Land source files unchanged under an immutable bundle-specific path.
3. Load reference entities first: sources, pipeline definitions, datasets,
   quality checks, dependencies, and scenario metadata.
4. Load event/measurement entities next: pipeline runs, observations, quality
   results, business KPIs, and incidents.
5. Verify manifest row counts, schema version, uniqueness, references, and
   representative joins before making the batch visible downstream.
6. Record linked-service validation, `CURRENT_USER`, bundle ID, row counts,
   outcome, and timestamp. Never record the password.

The sample bundle's expected counts are: sources `3`, pipeline definitions
`3`, runs `24`, datasets `3`, observations `22`, quality checks `9`, quality
results `66`, dependencies `2`, KPIs `22`, incidents `1`, and scenario
metadata `8`.

ADF linked services, datasets, landing-zone location, triggers, retries,
secret handling, and production acceptance remain implementation decisions.
Power BI should consume curated `OPS_INTEL` data using read-only access, not
raw staging tables or ground-truth labels.

## Validation and recorded verification

Run local test suites from the repository root using the existing
`synthetic-data/.venv`:

```powershell
$env:PYTHONPATH = 'D:\OpsNexus\OpsNexus'
& '.\synthetic-data\.venv\Scripts\python.exe' -m unittest discover -s .\synthetic-data\tests -p 'test_*.py' -v
& '.\synthetic-data\.venv\Scripts\python.exe' -m unittest discover -s .\infra\exasol\tests -p 'test_*.py' -v
& '.\synthetic-data\.venv\Scripts\python.exe' -m unittest discover -s .\api\tests -p 'test_*.py' -v
& '.\backend\venv\Scripts\python.exe' -m unittest discover -s .\backend\tests -p 'test_*.py' -v
git diff --check
```

The API and Exasol contract tests include mocked/offline checks; they do not
require a live database. `infra/exasol/tests/evaluate_intelligence.py` is a
live evaluator and requires configured read-only API credentials and access
to the findings view.

Historical verification recorded in the source handoff documents (October
2026) reported a successful read-only `OPSNEXUS_API` connection, `SELECT 1`,
17 findings, matching fixture target coverage, and passing evidence audits.
These are historical snapshots, not a guarantee of current deployment state.
The API identity could not inspect `OPS_STAGE`, so ADF run status and staging
counts were not independently verified by that identity. Live ADF and staging
verification must be performed from the approved SHIR/ingestion identity.

## Source-of-truth map

| Subject | Primary implementation or contract |
| --- | --- |
| API request/response field names | `contracts/dashboard_api.json` |
| Findings Flask API | `api/app.py` |
| API environment template | `api/.env.example` |
| Integrated dashboard | `frontend/` |
| Separate supplied dashboard | `exasol-dashboard/` |
| Exasol schema and intelligence SQL | `infra/exasol/sql/` |
| Evidence-audit implementation | `infra/exasol/udf/evidence_audit.py` |
| Synthetic-data generator and package schema | `synthetic-data/` |
| Example synthetic bundle | `synthetic-data/examples/seed-20261014/` |

When implementation and historical prose disagree, prefer the current code,
SQL, configuration templates, and shared contract. Keep this overview and the
root `README.md` aligned when those interfaces or setup steps change.
