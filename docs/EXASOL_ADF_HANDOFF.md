# Exasol / Azure Data Factory handoff

Status: proposed integration contract for Logesh. The fixed deployment choice is local Exasol Personal, not Exasol SaaS. No Azure resource, network rule, credential, or ADF pipeline is provisioned by this repository change.

## Responsibilities

`OPS_SOURCE` is optional reference/source metadata. `OPS_STAGE` owns operational records ingested from validated Module 1 bundles and future ADF sources. `OPS_INTEL` owns analytical SQL, views, models, and intelligence outputs. Ground-truth labels remain test/evaluation assets only; `ground_truth/expected_outcomes.json` must not be copied into an operational landing area or table.

ADF should land the immutable bundle first, validate `manifest.json` and `validation-report.json`, reject invalid bundles, and load the 11 files under `data/` into the matching `OPS_STAGE.STG_*` tables. The SQL and exact mapping are in [`infra/exasol/README.md`](../infra/exasol/README.md) and [`infra/exasol/sql/02_create_staging_tables.sql`](../infra/exasol/sql/02_create_staging_tables.sql). Load parents before children: sources, pipelines, datasets, checks, dependencies, scenario metadata, then runs, observations, quality results, KPIs, and incidents.

ADF belongs at the staging boundary because it can validate headers, row counts, schema version, timestamps, duplicate keys, and referential integrity before publishing data to analytical consumers. Use `(bundle_id, relative file path)` as the ingestion-batch identity and make exact replays idempotent. The final decision on `bundle_id` as a loader metadata column, upsert behavior, retention, and physical foreign-key enforcement is open.

## Connection properties (no secrets)

The current Personal manifest proposes host `127.0.0.1`, TCP port `8563`, user `sys`, TLS enabled with `insecureSkipCertValidation=true`, and a self-signed/local certificate posture. This is an observed configuration value, not a successful connection result; the port currently refuses connections. The launcher reports the deployment as running, but recovery and `SELECT 1` remain pending because `exasol` is not on the PowerShell PATH. After recovery, use `exasol info` as the source of truth for host/port/TLS details.

For the eventual ADF linked service, Logesh needs the final reachable Personal host/address, TCP port, database name if applicable, least-privilege username, password/secret reference, Exasol ODBC driver installation on the SHIR host, encryption/TLS setting, and certificate-validation policy. Do not place passwords in JSON, SQL, URLs, DSNs, Git, or this handoff. Use the approved secret store.

Do not expose Exasol publicly. A Self-Hosted Integration Runtime on a suitable reachable machine with the Exasol ODBC driver installed and configured is the proposed ADF topology, subject to final network architecture, firewall rules, DNS, routing, and certificate policy. The SHIR host must reach the Personal deployment privately; `127.0.0.1` on a developer workstation is not a valid remote ADF endpoint. The driver version and TLS behavior must be validated by the platform owner before handoff.

## Validation for Logesh

After network and credentials are provisioned, validate from the SHIR host using the approved Exasol ODBC/ADF connection:

1. Open the linked service test and confirm TLS/certificate validation succeeds.
2. Run `SELECT CURRENT_TIMESTAMP, CURRENT_USER;`.
3. Confirm `OPS_SOURCE`, `OPS_STAGE`, and `OPS_INTEL` exist.
4. Load one known synthetic bundle into a quarantined/test batch and compare each table count with its manifest: sources 3, pipeline definitions 3, runs 24, datasets 3, observations 22, quality checks 9, quality results 66, dependencies 2, KPIs 22, incidents 1, scenario metadata 8.
5. Check `SCHEMA_VERSION = '2.0.0'`, primary-key uniqueness, required columns, and representative foreign-key joins. Confirm there are zero rows or files sourced from `ground_truth/expected_outcomes.json`.
6. Record the connection test, bundle ID, row counts, validation outcome, and timestamp without recording the password.

## Downstream consumers

Analytical SQL can run directly in Exasol over `OPS_STAGE`, with curated views/materialized outputs in `OPS_INTEL`. dbt is optional and remains an open architecture decision; if adopted, its Exasol adapter, incremental strategy, and deployment identity must be agreed separately. Flask should read approved `OPS_INTEL` views through a read-only service identity and return evidence-backed results. Power BI should use a read-only Exasol connection to curated `OPS_INTEL` views, not raw staging tables and never ground-truth labels.

## Handoff checklist

- Confirm Exasol edition/version and licensing; Docker DB is evaluation/testing scope and limited to 10 GiB raw data.
- Provision Exasol on an officially supported Linux environment with adequate RAM/storage and private networking.
- Create least-privilege ADF ingestion and read-only Flask/Power BI identities; store secrets outside Git.
- Install and validate the Exasol ODBC driver on the selected SHIR host.
- Apply the schema SQL, agree load/constraint/replay policy, and run the synthetic row-count validation.
- Document private endpoint/firewall/certificate details in the team’s secure operations record, not here.
