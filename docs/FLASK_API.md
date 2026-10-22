# OpsNexus findings API

The Flask API in [`api/app.py`](../api/app.py) is a read-only adapter over `OPS_INTEL.V_FINDINGS`. It does not read staging tables, change database data, or include offline ground-truth labels.

## Configuration and least privilege

Install the API dependencies into the project virtual environment:

```powershell
& '.\synthetic-data\.venv\Scripts\python.exe' -m pip install -r .\api\requirements.txt
```

Copy [`api/.env.example`](../api/.env.example) to the ignored `api/.env` file and replace its placeholders locally, or provide the same variables through the approved secret store/process environment. The API loads `api/.env` without overriding values already set in the process environment. The example contains placeholders only and `.env` files are ignored by Git. Keep the password in the approved secret store or protected local file; never print it or place it in shell history. `EXASOL_API_USER` must be a dedicated read-only Exasol user and must not be `SYS`; `EXASOL_API_PASSWORD` is its secret. Use the existing local host and port for Exasol Personal. Encrypted connections and certificate validation are required. PyExasol 0.27.0 does not accept a `validate_server_certificate` connection argument: for a local self-signed Exasol Personal certificate, set `EXASOL_CERTIFICATE_FINGERPRINT` to its 64-character SHA-256 fingerprint (the DBeaver TLS error displays it). PyExasol then pins the server certificate through its DSN form `host/fingerprint:port`. When no pin is configured, the API explicitly requires CA certificate validation. Do not disable validation.

Have a database administrator create or identify a dedicated API user. Its least-privilege grants for this API are `CREATE SESSION`, `USAGE ON SCHEMA OPS_INTEL`, and `SELECT ON VIEW OPS_INTEL.V_FINDINGS`. The grant-only script [`infra/exasol/sql/04_grant_findings_api_readonly.sql`](../infra/exasol/sql/04_grant_findings_api_readonly.sql) has those statements and should be run manually as an authorized administrator after the user exists. Exasol may already provide schema usage via an effective role; the explicit `USAGE` grant makes the dependency clear if broad default schema access is restricted. Do not grant schema-wide `SELECT`, access to `OPS_STAGE` or `OPS_SOURCE`, or DDL/DML privileges. The view owner must retain the rights Exasol requires to grant access on the view and its referenced objects; the API identity itself needs only the three direct grants above. Exasol documents `CREATE SESSION` as the connection privilege and `USAGE` plus object `SELECT` for view access ([GRANT reference](https://docs.exasol.com/db/latest/sql/grant.htm), [database user reference](https://docs.exasol.com/db/latest/database_concepts/database_users_roles.htm)).

Create the account separately through the approved administrative SQL client or account workflow, entering a generated password through its secure input mechanism. The SQL operation is `CREATE USER OPSNEXUS_API IDENTIFIED BY "<password-entered-securely>";`; the angle-bracket value is explanatory and must never be used literally or saved in this repository. Keep the real password in the approved secret store and make it available as `EXASOL_API_PASSWORD`. This repository neither provisions users nor contains credentials. The API refuses a `SYS` username.

Run locally from the repository root:

```powershell
$env:EXASOL_HOST = '127.0.0.1'
$env:EXASOL_PORT = '8563'
$env:EXASOL_API_USER = '<dedicated-read-only-user>'
# Load EXASOL_API_PASSWORD into this process from the approved secret store.
& '.\synthetic-data\.venv\Scripts\python.exe' -m flask --app api.app run --host 127.0.0.1 --port 5000
```

Do not replace the comment with a literal password command. The application never returns connection details or raw database exceptions.

## Endpoints

The exact dashboard contract, nullable fields, examples, and error schemas are detailed in the `Dashboard integration contract` section below.

- `GET /health` checks API availability and executes `SELECT 1`; returns `200` when Exasol is reachable or structured `503` when it is not.
- `GET /api/findings?page=1&page_size=50&finding_type=KPI_ANOMALY&severity=HIGH&scenario_instance_id=...` lists findings. All filters are optional. Page size is restricted to 1–100. Results are ordered by stable finding ID and include pagination totals.
- `GET /api/findings/<finding_id>` returns one finding or structured `404`.

Finding objects expose `finding_id`, `finding_type`, `severity`, `affected_entity` (`type` and `id`), `evidence`, `recommended_action`, `source_references`, `measured_value`, `expected_value`, `threshold`, `source_run_id`, and `scenario_instance_id`. Nullable source fields are returned as JSON `null`.

For `PIPELINE_FAILURE`, the API normalizes the `started_at` value inside evidence to a single UTC `Z` suffix. `OPS_STAGE.STG_PIPELINE_RUNS.STARTED_AT` is a timezone-naive Exasol `TIMESTAMP`, while the project schema and generator define it as UTC. Explicit offsets are converted to UTC; already-UTC values remain single-suffixed, and unparseable/local labels are preserved unchanged. The SQL file `infra/exasol/sql/03_create_intel_findings.sql` already appends `'Z'` to `STARTED_AT` in the `PIPELINE_FAILURE` evidence; if the live view was not yet replaced after the last SQL update, re-execute that file as an authorized non-SYS identity.

## Dashboard integration contract

All routes return JSON. There is no built-in user authentication; keep Flask bound to loopback or place it behind an approved authenticated gateway. For a browser dashboard on another development port, use the frontend dev-server proxy or a same-origin reverse proxy. Do not expose the unauthenticated Flask development server to a network.

### `GET /health`

Runs `SELECT 1` through the configured Exasol identity.

```json
{"status":"ok","database":"connected"}
```

Returns `200` when the query succeeds and `503` with `database_unavailable` when the database connection or query fails.

### `GET /api/findings`

Optional query parameters:

| Parameter | Type | Default | Allowed values / behavior |
|---|---|---:|---|
| `page` | positive integer | `1` | One-based page number. |
| `page_size` | integer | `50` | `1` through `100`. |
| `finding_type` | string | omitted | `PIPELINE_FAILURE`, `STALE_DATASET`, `INCOMPLETE_DATA`, `QUALITY_FAILURE`, `KPI_ANOMALY`, `CROSS_DOMAIN_INCONSISTENCY`, or `INCIDENT_RECURRENCE`; case-insensitive. |
| `severity` | string | omitted | `LOW`, `MEDIUM`, `HIGH`, or `CRITICAL`; case-insensitive. |
| `scenario_instance_id` | string | omitted | Opaque token matching `[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}`. |

Results are ordered by `finding_id`. A page beyond the result set returns an empty `data` array while preserving totals.

```json
{
  "data": [{
    "finding_id": "kpi_anomaly:kpi_demo_001",
    "finding_type": "KPI_ANOMALY",
    "severity": "MEDIUM",
    "affected_entity": {"type": "KPI", "id": "kpi_demo_001"},
    "evidence": "kpi_id=kpi_demo_001; measured_relative_deviation=0.5",
    "recommended_action": "Validate the metric definition and its source observation.",
    "source_references": "kpi_id=kpi_demo_001; observation_id=obs_demo_001; quality_result_id=qr_demo_001",
    "measured_value": "0.5",
    "expected_value": "0.2",
    "threshold": "0.2",
    "source_run_id": "run_demo_001",
    "scenario_instance_id": "case_demo_001"
  }],
  "pagination": {"page": 1, "page_size": 50, "total_count": 1, "total_pages": 1}
}
```

The view contract has 13 database columns. The JSON object has 12 top-level keys because `AFFECTED_ENTITY_TYPE` and `AFFECTED_ENTITY_ID` are grouped under `affected_entity`, which contains `type` and `id`. Missing values are JSON `null`; numeric Exasol values are serialized as strings to preserve decimal precision.

### `GET /api/findings/<finding_id>`

Returns `{"data": <finding>}` using the same finding shape as the list response. It returns `404` when the identifier is valid but no finding matches.

### Error responses

Errors use `{"error":{"code":"...","message":"..."}}`.

| HTTP | Code | Condition |
|---:|---|---|
| `400` | `invalid_pagination` | `page`/`page_size` is not an integer or is outside its allowed range. |
| `400` | `invalid_filter` | Unsupported type/severity or malformed scenario token. |
| `400` | `invalid_finding_id` | Detail ID fails identifier validation. |
| `404` | `not_found` | Route or finding does not exist. |
| `405` | `method_not_allowed` | HTTP method is unsupported. |
| `503` | `database_unavailable` | Database connection or query failed. |
| `500` | `internal_error` | Unexpected application failure. |

Example invalid-filter response: `{"error":{"code":"invalid_filter","message":"Unsupported severity"}}`. Database errors never return driver messages or credential details.

## Integration smoke test

After the existing Exasol Personal instance is running and the dedicated read-only identity has access, start the API as above and run these requests from another PowerShell window:

```powershell
Invoke-RestMethod http://127.0.0.1:5000/health
Invoke-RestMethod 'http://127.0.0.1:5000/api/findings?page=1&page_size=10'
```

Use an ID from the list response for the single-finding request:

```powershell
Invoke-RestMethod 'http://127.0.0.1:5000/api/findings/<finding-id>'
```

This smoke test only reads the view. It does not alter staging data or reload CSVs. The automated API tests use a mocked database connection and do not require a running Exasol instance.

### Verification snapshot (2026-10-18)

Verification on 2026-10-18 used the dedicated API identity from the ignored local configuration; no SYS login was used and credentials were not emitted. Direct PyExasol `SELECT 1` succeeded, and `OPS_INTEL.V_FINDINGS` contained 17 findings. Live Flask requests all returned HTTP 200: `/health` reported the database connected; page 1 and page 2 with page size 2 each returned 2 rows; the list total was 17; finding-type, severity, and scenario-instance filters returned 3, 6, and 2 matches respectively; and the single-finding endpoint returned the requested record. The API code now uses PyExasol 0.27.0's certificate-pin DSN format, and pagination applies a parameterized row-number range because Exasol rejected PyExasol-formatted parameters inside `LIMIT`.

The API suite passed 9 tests, Exasol contract suite passed 7 tests, and synthetic-data suite passed 12 tests. `git diff --check` passed. These live endpoint results verified authentication, view access, response serialization, filtering, pagination, and single-record lookup at that time.

### Latest verification status (2026-10-19)

The configured read-only identity returned `CURRENT_USER=OPSNEXUS_API`; `SELECT 1` succeeded and the view returned 17 rows. All eight expected scenario targets matched: healthy baseline had no findings, each of the six labeled positive scenarios contained its target family, and the inconclusive scenario remained unlabelled while showing evidence signals. Every live finding passed the local evidence-audit implementation. Live `/health`, paginated list pages, all seven finding-type filters, a scenario filter, empty results, and detail/list response consistency were verified. Staging table visibility and ADF run status remain outside this API identity's access and were not independently verified. Current test totals at handoff: synthetic **12**, Exasol SQL/UDF contract **21**, and API **10**.
