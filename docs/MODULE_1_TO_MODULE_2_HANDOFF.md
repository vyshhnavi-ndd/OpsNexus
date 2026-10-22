# Module 1 → Module 2 handoff: synthetic files for ADF

**Purpose:** give Person B an exact, locally reproducible file contract to evaluate for ADF ingestion. This handoff does not create ADF pipelines, provision Azure resources, or claim a live integration. All example values are synthetic.

## Contract status

- **Implemented and locally tested by Module 1:** schema version `2.0.0`; file names and CSV headers below; UTC timestamp convention; stable opaque case IDs; manifest and validation-report structure; eight scenario fixtures; ground-truth separation; referential checks.
- **Proposed, pending confirmation by Person B (and Person A where analytics/investigation semantics are involved):** ADF linked services/datasets, landing-zone location, CSV ingestion configuration, load order, Exasol staging/table design, downstream API mappings, and operational acceptance of these fields/enums. The local implementation is not itself team sign-off.
- **Not implemented or verified:** Azure access, ADF pipelines, Exasol connection, or cloud credentials. No service calls are made.

## Exact example bundle and files

The checked-in example is `synthetic-data/examples/seed-20261014/`. Generate another bundle into any chosen output directory; the format is unchanged.

ADF candidate operational files (all paths relative to the bundle root):

```text
data/data_sources.csv
data/pipeline_definitions.csv
data/datasets.csv
data/quality_checks.csv
data/dependencies.csv
data/scenario_metadata.csv
data/pipeline_runs.csv
data/dataset_observations.csv
data/quality_results.csv
data/business_kpis.csv
data/incident_history.csv
```

`manifest.json` describes the bundle and is orchestration metadata. Person B should decide whether ADF reads it as a control file or whether a pipeline parameter supplies the equivalent values. `validation-report.json` is Module 1's local pre-ingestion report; it is not operational evidence. **Do not ingest** `ground_truth/expected_outcomes.json`. It contains expected labels for test/demo evaluation, not observed facts.

## File schemas and field mappings

Every CSV is UTF-8, comma-delimited, has a header row, uses `\n` record separators, and follows the exact field order listed. There is no implicit index column. Empty CSV cells represent nullable values only; empty strings are not used as null for required fields. JSON-valued CSV cells are compact JSON text. `schema_version` is `2.0.0` in every row. Detailed type/nullability declarations also appear under `manifest.json.schemas`.

| File | Fields in CSV order | Key and references / use |
|---|---|---|
| `data_sources.csv` | `source_id, source_name, source_type, classification, schema_version` | PK `source_id`; source registry. Every source is marked `SYNTHETIC` / `SYNTHETIC_DEMO`. |
| `pipeline_definitions.csv` | `pipeline_id, pipeline_name, source_id, schema_version` | PK `pipeline_id`; FK `source_id → data_sources.source_id`. |
| `pipeline_runs.csv` | `run_id, pipeline_id, scenario_instance_id, status, started_at, ended_at, duration_seconds, schema_version` | PK `run_id`; FKs to pipeline and opaque scenario instance. Status enum: `SUCCEEDED`, `FAILED`, `SKIPPED`. |
| `datasets.csv` | `dataset_id, dataset_name, domain, source_id, schema_version` | PK `dataset_id`; FK to source. Dataset versions are represented by observation windows in the observation file. |
| `dataset_observations.csv` | `observation_id, dataset_id, run_id, scenario_instance_id, observed_at, window_start, window_end, row_count, expected_row_count, freshness_lag_seconds, completeness_ratio, metric_name, metric_value, schema_version` | PK `observation_id`; FKs to dataset, successful run, opaque scenario instance. Counts/lag are non-negative; ratio is `[0,1]`. |
| `quality_checks.csv` | `quality_check_id, dataset_id, check_type, description, threshold_json, schema_version` | PK `quality_check_id`; FK to dataset. Check types: `freshness`, `completeness`, `metric_range`. Threshold text is JSON. |
| `quality_results.csv` | `quality_result_id, quality_check_id, observation_id, result, measured_value, expected_value, schema_version` | PK `quality_result_id`; references a check and matching dataset observation. Result enum: `PASS`, `FAIL`. |
| `dependencies.csv` | `dependency_id, upstream_pipeline_id, downstream_pipeline_id, dependency_type, schema_version` | PK `dependency_id`; both pipeline FKs; no self-dependency. Type in fixture: `REQUIRED`. |
| `business_kpis.csv` | `kpi_id, scenario_instance_id, observation_id, kpi_name, domain, dataset_id, unit, baseline_value, observed_value, impact_type, schema_version` | PK `kpi_id`; opaque scenario and observation/dataset references. `ILLUSTRATIVE_SYNTHETIC` means values are synthetic examples, not measured business loss. |
| `incident_history.csv` | `incident_id, pipeline_id, scenario_instance_id, occurred_at, incident_category, resolution_status, schema_version` | PK `incident_id`; pipeline and opaque scenario references. Prior incident is synthetic; category `FRESHNESS_DELAY`, status `CLOSED`. |
| `scenario_metadata.csv` | `scenario_instance_id, scenario_type, description, seed, schema_version` | PK `scenario_instance_id`; opaque case token. Operational `scenario_type` is always `SYNTHETIC_DEMO`; description is generic. |

`scenario_instance_id` is an opaque deterministic token assigned per scenario per seed. It is used consistently by operational runs, observations, KPIs, incident history, and scenario metadata so Person B can correlate a case without receiving a semantic scenario label. The semantic label-to-token mapping exists only in `ground_truth/expected_outcomes.json`.

## Identifiers, timestamps, and manifest

- IDs are deterministic strings. Static reference IDs (`source_id`, `pipeline_id`, `dataset_id`, checks, dependencies) stay the same because their definitions stay the same. Scenario-instance tokens are opaque values generated from a seeded ID stream, not semantic names. Generated run, observation, KPI, incident, and scenario-instance IDs include package version, schema version, seed, opaque instance token, and entity key as applicable. Re-running the same version/schema/seed produces the same IDs and bytes. A different seed produces a different `bundle_id` and namespaced event IDs.
- `manifest.json.bundle_id` is `opsnexus-synthetic-v<package-version>-schema-<schema-version>-seed-<seed>`. Use it as the bundle-level idempotency key; do not treat a different seed as a replay of the same payload.
- Timestamps are ISO 8601 UTC with `Z` suffix and second precision. The fixed synthetic anchor is `2026-10-14T08:00:00Z`; these are generated demonstration times, not wall-clock execution times.
- The manifest records manifest/generator/schema versions, seed, bundle ID, synthetic classification, timestamp convention, opaque `scenario_instance_ids`, each relative CSV path, format, schema version, row count, and schema fields. It contains no semantic scenario labels. The `ground_truth` entry explicitly has `ingest: false`.
- `validation-report.json` records `valid`, error count/list, row counts and opaque scenario-instance IDs. ADF should stop before loading if it is absent or `valid` is not `true`, and should still perform its own landing/schema checks.

## Proposed ADF ingestion sequence

This sequence is a practical proposal; Person B must confirm it against their ADF design.

1. Read and validate manifest format/version, allowed relative file paths, expected file set, and `validation-report.json`. Reject the bundle if local validation failed.
2. Land files unchanged in an immutable bundle-specific folder, e.g. `.../<bundle_id>/data/`. Do not land the ground-truth directory in an operational container or table.
3. Load/upsert reference entities in FK order: `data_sources`, `pipeline_definitions`, `datasets`, `quality_checks`, `dependencies`, `scenario_metadata`.
4. Load event/measurement entities: `pipeline_runs`, `dataset_observations`, `quality_results`, `business_kpis`, then `incident_history`.
5. Validate counts against manifest, schema version, IDs/FKs, enums, timestamps, and bundle ID before exposing staged rows to downstream analytics.

ADF-specific linked services, storage account, file format dataset, trigger, identity, retries, and secret handling remain Person B's implementation decisions. Module 1 supplies no Azure configuration or credentials.

## Replay, duplicates, and failures

- Use `(bundle_id, file path)` as the ingestion-batch identity. Reprocessing the exact same bundle should be an idempotent upsert/no-op keyed by each file's documented primary key. Static dimensions should be upserted by their stable IDs; bundle-scoped rows use seed/version-namespaced IDs.
- If a bundle path is reused with different content, compare manifest and row counts and fail/quarantine rather than silently overwriting accepted rows. Module 1 does not provide cryptographic checksums; Person B may compute/store hashes in ADF landing metadata.
- A missing file, header mismatch, invalid row count, unsupported schema version, null in a required field, invalid type/enum/timestamp, duplicate primary key, invalid FK, scenario-instance mismatch, leaked semantic scenario label, or `valid=false` report is a validation failure. Fail the bundle before publication and retain the landing copy plus error details for diagnosis.
- Do not partially publish a bundle. ADF can stage files and publish only after its cross-file checks pass; cleanup/retention policies are owned by Module 2.

## Proposed downstream mapping (not implemented)

**Proposed Exasol staging:** one staging table per CSV, preserving source columns and schema version; retain manifest `bundle_id` as ingestion metadata added by the loader. Enforce primary/foreign keys in a validation layer or views. Candidate analytical views can join observations to runs, dataset/source definitions, quality results, KPI mappings, dependencies, and incident history. Person A/Person B must agree table naming, data types, load strategy, and whether to use native constraints or view-based checks.

**Proposed investigation workflow mapping:** use successful/failed/skipped run records and quality results as observed evidence; calculate trust/candidate explanations downstream and mark them as inferences. Use KPI rows only as illustrative synthetic impact links. Group records by opaque `scenario_instance_id`; never load or use the semantic mapping from ground truth as operational evidence. Keep the ground-truth JSON only in test/demo evaluation. Recovery approval, execution, verification, and final `RECOVERED` / `NOT_RECOVERED` / `INCONCLUSIVE` statuses belong to later modules and must be independently evidenced.

## Local commands

From `synthetic-data/` in PowerShell, install the local package into its project venv first:

```powershell
# Create the venv only if it does not already exist; use the approved Python 3.11+ interpreter.
& 'C:\Users\vyshh\AppData\Local\Python\bin\python.exe' -m venv .venv
& '.venv\Scripts\python.exe' -m pip install -e .
& '.venv\Scripts\python.exe' -m opsnexus_synthetic generate --seed 20261014 --out examples/seed-20261014
& '.venv\Scripts\python.exe' -m opsnexus_synthetic validate examples/seed-20261014
& '.venv\Scripts\python.exe' -m unittest discover -s tests -p 'test_*.py' -v
```

This local generation/validation path requires no cloud credentials and makes no Azure connection. The package and these proposed inter-module contracts should be reviewed with Person B before ADF ingestion is configured.
