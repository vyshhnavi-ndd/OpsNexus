# OpsNexus Exasol integration foundation

This is a proposed Exasol Personal contract for Module 1 schema version `2.0.0`. It does not provision a database, download software, or define ADF resources. The operational source is the generated bundle under `synthetic-data/examples/seed-20261014/data/`.

## Deployment decision and prerequisites

The deployment decision is fixed: use the existing local Exasol Personal deployment only; do not use Exasol SaaS. The deployment directory is `C:\Users\vyshh\.exasol\personal\deployments\default`, Launcher version `2.3.0`, deployment ID `8028e1bc`, single local node, host `127.0.0.1`, database port `8563`. The prior recovery-pending note is superseded: on 2026-10-19 the configured read-only `OPSNEXUS_API` connection returned `CURRENT_USER`, `SELECT 1`, and 17 rows from `OPS_INTEL.V_FINDINGS`. This verifies the API path only; it does not verify staging-table visibility or ADF runs. Use `& "$env:USERPROFILE\Downloads\exasol.exe" info` for current deployment connection details.

The official [Exasol Docker DB documentation](https://github.com/exasol/docker-db) describes Docker DB as a testing/evaluation distribution, limited to 10 GiB of raw data. It requires x86-64, Linux, a privileged container, storage supporting `O_DIRECT`, and at least 2 GiB RAM per database instance; 4 GiB per running container is recommended. It also requires correct NTP and sufficient entropy. The documentation explicitly says Windows hosts are unsupported and a Linux VM is required. Exasol Docker DB is distinct from Exasol Community Edition, which is distributed as a virtual machine.

Exasol Personal local is the chosen path; Docker DB guidance is not the deployment path for this project. Do not pull a database image, create a second deployment, change Docker Desktop storage, or delete `exa_volume`.

The current Docker state was inspected only: no Exasol containers/images are present and `exa_volume` exists. A volume is persistent database state; never remove or reset it as routine cleanup.

## Schemas and contract

- `OPS_SOURCE`: optional source/reference data. No Module 1 operational CSV is placed here by default.
- `OPS_STAGE`: ADF and Module 1 operational evidence, one `STG_` table per CSV.
- `OPS_INTEL`: analytical views/models and intelligence outputs. dbt remains optional and is not assumed.

`ground_truth/expected_outcomes.json` is evaluation-only and must never be loaded as ordinary operational evidence. `manifest.json` and `validation-report.json` are control/validation metadata, not staging tables. Preserve CSV headers exactly; the proposed SQL types are ingestion types, not a change to the file contract.

| CSV | Proposed table | Key | Types (in CSV order) | References |
|---|---|---|---|---|
| `data_sources.csv` | `OPS_STAGE.STG_DATA_SOURCES` | PK `source_id` | string, string, string, string, string | — |
| `pipeline_definitions.csv` | `OPS_STAGE.STG_PIPELINE_DEFINITIONS` | PK `pipeline_id` | string, string, string, string | `source_id` → sources |
| `pipeline_runs.csv` | `OPS_STAGE.STG_PIPELINE_RUNS` | PK `run_id` | string, string, string, string, timestamp, timestamp nullable, integer nullable, string | pipeline, scenario |
| `datasets.csv` | `OPS_STAGE.STG_DATASETS` | PK `dataset_id` | string, string, string, string, string | `source_id` → sources |
| `dataset_observations.csv` | `OPS_STAGE.STG_DATASET_OBSERVATIONS` | PK `observation_id` | string ×4, timestamp ×3, integer ×3, number ×2, string ×2 | dataset, run, scenario |
| `quality_checks.csv` | `OPS_STAGE.STG_QUALITY_CHECKS` | PK `quality_check_id` | string, string, string, string, JSON text, string | dataset |
| `quality_results.csv` | `OPS_STAGE.STG_QUALITY_RESULTS` | PK `quality_result_id` | string ×3, string, number nullable ×2, string | check, observation |
| `dependencies.csv` | `OPS_STAGE.STG_DEPENDENCIES` | PK `dependency_id` | string ×4, string | upstream/downstream pipeline |
| `business_kpis.csv` | `OPS_STAGE.STG_BUSINESS_KPIS` | PK `kpi_id` | string ×7, number ×2, string ×2 | scenario, observation, dataset |
| `incident_history.csv` | `OPS_STAGE.STG_INCIDENT_HISTORY` | PK `incident_id` | string ×3, timestamp, string ×3 | pipeline, scenario |
| `scenario_metadata.csv` | `OPS_STAGE.STG_SCENARIO_METADATA` | PK `scenario_instance_id` | string ×3, integer, string | — |

The complete column names and constraints are in [`sql/02_create_staging_tables.sql`](./sql/02_create_staging_tables.sql). Foreign keys are proposed compatibility checks; confirm whether the selected Exasol version/load strategy should enforce them or validate through ADF and views. Open questions are bundle metadata columns (for example `bundle_id`), upsert/duplicate policy, retention, and whether physical constraints are acceptable for ADF load order.

## Setup and connection

1. Confirm the Linux-host/VM decision, Exasol version, license/terms, network path, and an appropriately scoped ingest user with no unnecessary administration rights.
2. Review and run [`sql/01_create_schemas.sql`](./sql/01_create_schemas.sql), then [`sql/02_create_staging_tables.sql`](./sql/02_create_staging_tables.sql) using an administrator.
3. Copy [`.env.example`](./.env.example) to an ignored local `.env` and fill secrets through the approved secret store. The image documentation must be followed for credentials; do not assume an arbitrary environment variable changes the Exasol password.
4. For Python, use the `pyexasol` driver and environment variables:

   ```python
   import os
   import pyexasol

   connection = pyexasol.connect(
       dsn=f"{os.environ['EXASOL_HOST']}:{os.getenv('EXASOL_PORT', '8563')}",
       user=os.environ['EXASOL_USER'],
       password=os.environ['EXASOL_PASSWORD'],
       schema=os.getenv('EXASOL_SCHEMA', 'OPS_STAGE'),
       encryption=True,
       validate_server_certificate=os.getenv('EXASOL_VALIDATE_CERTIFICATE', 'true').lower() == 'true',
   )
   ```

Do not commit `.env`, passwords, tokens, or password-bearing DSNs. Keep the Personal database bound to loopback; never publish port `8563` on all interfaces. The current local manifest has `insecureSkipCertValidation=true`, so TLS/certificate handling must be corrected and verified before any non-local client is allowed. ADF cannot reach `127.0.0.1` on the developer workstation unless the approved Self-Hosted Integration Runtime is colocated and explicitly permitted; a private reachable Personal host is required for the handoff.

## Health checks and cleanup

Run `SELECT CURRENT_TIMESTAMP, CURRENT_USER;`, then count checks against the manifest row counts after loading. Validate schema version, duplicate keys, nullability, and foreign-key coverage before exposing `OPS_INTEL` views.

Stop the database gracefully using the version-specific Exasol procedure/documentation before stopping a container. Do not remove `exa_volume`, reset Docker Desktop, or manually move Docker storage. Tests that need a live database are intentionally not run by this change.
