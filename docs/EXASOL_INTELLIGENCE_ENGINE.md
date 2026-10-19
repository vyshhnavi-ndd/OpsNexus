# OpsNexus Exasol intelligence engine

The rerunnable implementation is [`infra/exasol/sql/03_create_intel_findings.sql`](../infra/exasol/sql/03_create_intel_findings.sql), published as `OPS_INTEL.V_FINDINGS`. It reads only operational `OPS_STAGE.STG_*` tables. The view does not reference or load `ground_truth/expected_outcomes.json`; that file is read only by the offline evaluator [`infra/exasol/tests/evaluate_intelligence.py`](../infra/exasol/tests/evaluate_intelligence.py).

## Findings contract

The original nine columns remain in their existing order for named-column compatibility. Four evidence columns are appended:

| Column | Meaning |
|---|---|
| `FINDING_ID` | Stable ID derived from an operational key or a stable related-entity pair. |
| `SCENARIO_INSTANCE_ID` | Opaque scenario reference when the source evidence is scoped; otherwise null. |
| `FINDING_TYPE` / `SEVERITY` | Deterministic rule and severity. |
| `AFFECTED_ENTITY_TYPE` / `AFFECTED_ENTITY_ID` | Pipeline, dataset, KPI, or related dataset pair. |
| `EVIDENCE` | Human-readable measured/expected values, relevant thresholds, and rationale. |
| `RECOMMENDED_ACTION` | Evidence-specific next step. |
| `SOURCE_RUN_ID` | Supporting run when one exists. |
| `SOURCE_REFERENCES` | Source run, observation, check/result, KPI, dependency, or incident identifiers. |
| `MEASURED_VALUE` / `EXPECTED_VALUE` / `THRESHOLD_VALUE` | Values used by the rule, represented as strings so status and numeric rules share the contract. `EVIDENCE` carries the full context. |

Finding IDs are deterministic for unchanged source keys and relationships. Output order is not guaranteed by the view; consumers should order by `FINDING_TYPE, FINDING_ID`.

## Detection rules

| Rule | Trigger and threshold | Limitations |
|---|---|---|
| `PIPELINE_FAILURE` | A run status is `FAILED`; `HIGH`. The evidence aggregates upstream and downstream run statuses over declared dependency edges for the same scenario instance. | It reports observed direct failures and related dependency state; it does not infer root cause or mark skipped work as another failure. |
| `STALE_DATASET` | Freshness result is `FAIL` or observed freshness lag exceeds the configured result threshold; `HIGH`. If multiple freshness checks apply to an observation, the strictest non-null expected limit is selected. | Requires a configured freshness result with a numeric expected value. The view emits the specific signal plus the general quality finding. |
| `INCOMPLETE_DATA` | Expected row count is positive, observed rows are fewer than expected, and observed completeness ratio is below the configured completeness result threshold; `HIGH`. | Requires a configured completeness result with a numeric expected value. Zero expected rows do not produce a ratio-based finding. |
| `QUALITY_FAILURE` | A configured quality result is `FAIL`; freshness/completeness are `HIGH`, other check types `MEDIUM`. Evidence includes check definition, measured/expected values, and result ID. | Intentionally coexists with the specific stale, incomplete, and KPI signals; this is separate rule coverage, not a join duplicate. |
| `KPI_ANOMALY` | Absolute KPI deviation divided by absolute non-zero KPI baseline exceeds the configured metric-range result threshold; `MEDIUM`. Duplicate range results use the strictest threshold and stable result-ID tie-break. | Zero baselines are skipped because relative deviation is undefined. Synthetic KPI impacts remain explicitly illustrative, never business-loss estimates. |
| `CROSS_DOMAIN_INCONSISTENCY` | Two KPI-linked dataset observations with the same metric name, different domains, and upstream pipelines connected to the same downstream pipeline disagree by more than a **proposed 10% relative gap** (`abs(a-b)/max(abs(a),abs(b))`). | The data contract has no cross-domain tolerance. The 10% proposal is explicit and chosen to exceed the generated healthy spread (values within ±5% of 100) while detecting the 18% fixture gap. Compare the normalized observation metric, not KPI values with unlike units. This is an investigation signal, not proof that either source is wrong. |
| `INCIDENT_RECURRENCE` | At least two distinct incident IDs share a pipeline/category; or one history incident plus one current failed freshness event with matching `FRESHNESS_DELAY` category and scenario link. Threshold: **two distinct occurrences**, `MEDIUM`. | No age window is applied because the contract has no recurrence window/retention field. The single-category-to-check mapping is deliberately limited to `FRESHNESS_DELAY` → freshness. |

Thresholds for freshness, completeness, and metric range come from the staged quality results generated from configured checks. The proposed cross-domain 10% gap and two-occurrence recurrence threshold are documented proposals because those thresholds are absent from the source schema. If the operational owner chooses different semantics, update this document and SQL together.

## Finding-evidence audit UDF

[`OPS_INTEL.AUDIT_FINDING_EVIDENCE`](../infra/exasol/sql/05_create_evidence_audit_udf.sql) is a separate deterministic audit of a finding row. Its matching standard-library Python implementation is [`infra/exasol/udf/evidence_audit.py`](../infra/exasol/udf/evidence_audit.py). It does not change the seven finding rules, severity, thresholds, or recommended actions, and it never infers a root cause.

The scalar UDF accepts `FINDING_TYPE`, `EVIDENCE`, `SOURCE_REFERENCES`, the three string-valued numeric fields, and `SOURCE_RUN_ID`. It returns one JSON string with `audit_status` (`VALID`, `INCOMPLETE`, or `INVALID`), evidence/reference/numeric statuses, and sorted issue codes. It checks the source-reference format and finding-type-specific references (run, observation, quality-result/check, KPI, dependency, or incident IDs as applicable). It parses numeric outputs for rules that require numbers, and checks supplied numeric values on quality failures. Empty upstream/dependent run context is permitted; it means no related run was recorded. Results describe evidence quality only.

The Python 3 scalar script uses only the standard library. It runs under the existing Exasol `PYTHON3` runtime backed by the installed Python 3.12 SLC. Local unit/contract tests cover all eight named scenarios without reading the ground-truth file: healthy baseline has no finding to audit, while each emitted finding in the other scenarios is checked independently. The inconclusive case intentionally asserts no cause conclusion.

Review and deploy manually with an identity authorized to create scripts in `OPS_INTEL` and the Python 3 runtime enabled. Do not use the API's read-only identity. Exasol Launcher `connect` defaults to `SYS`; do not use a bare `connect -f` command for deployment. Open the SQL file in an approved client authenticated as the verified non-SYS deployment identity, check `CURRENT_USER` and script existence/permissions in that session, and execute only after explicit deployment approval. Keep the credential in the client's approved secure store; do not pass it on a command line.

The deployment SQL creates only the script object; it does not run automatically, alter tables, or change data. It deliberately omits `OR REPLACE`, so it will stop if that name already exists rather than replacing it. After deployment, inspect results with:

```sql
SELECT FINDING_ID,
       OPS_INTEL.AUDIT_FINDING_EVIDENCE(
         FINDING_TYPE, EVIDENCE, SOURCE_REFERENCES,
         MEASURED_VALUE, EXPECTED_VALUE, THRESHOLD_VALUE, SOURCE_RUN_ID
       ) AS EVIDENCE_AUDIT
FROM OPS_INTEL.V_FINDINGS
ORDER BY FINDING_ID;
```

Calling the script as another identity requires that identity to already have permission to execute it; this change does not grant permissions.

## Live evaluation

Run from the repository root with the existing virtual environment and the configured read-only API credentials in `api/.env` or the approved process environment. The evaluator uses the same TLS-validating PyExasol connector as Flask and does not use Exasol Launcher's default `SYS` identity:

```powershell
& .\synthetic-data\.venv\Scripts\python.exe .\infra\exasol\tests\evaluate_intelligence.py --repeats 2
```

The evaluator queries the live view twice by default, compares deterministic results, maps opaque scenario IDs using the offline ground-truth file, reports per-scenario target coverage, and prints per-rule TP/FP/FN/TN, precision, recall, and live counts by type/severity. Only `healthy_baseline` is an explicit negative label; other scenarios are not presumed negative for unlisted rule types. `inconclusive` is displayed but excluded from precision/recall. The expected cause label is a scenario-level target, not an exhaustive annotation of every operational signal.

Apply the view from an approved SQL client after staging loads. Verify the session's `CURRENT_USER` and the identity's view-replacement authorization first. Do not use bare Exasol Launcher `connect -f`: its default identity is `SYS`. Do not place credentials in shell history or command-line arguments.

The Flask API in [`api/app.py`](../api/app.py) consumes `OPS_INTEL.V_FINDINGS` through a read-only Exasol identity, serializes the stable finding contract, and applies API-level filtering/pagination. ADF is the designated operational loader into `OPS_STAGE`; it must not write findings or ground-truth labels.
