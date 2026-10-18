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

## Live evaluation

Run from the repository root with the existing virtual environment and an Exasol Launcher path:

```powershell
$env:EXASOL_LAUNCHER = 'C:\path\to\exasol.exe'
& .\synthetic-data\.venv\Scripts\python.exe .\infra\exasol\tests\evaluate_intelligence.py --repeats 2
```

The evaluator queries the live view twice by default, compares deterministic results, maps opaque scenario IDs using the offline ground-truth file, reports per-scenario target coverage, and prints per-rule TP/FP/FN/TN, precision, recall, and live counts by type/severity. Only `healthy_baseline` is an explicit negative label; other scenarios are not presumed negative for unlisted rule types. `inconclusive` is displayed but excluded from precision/recall. The expected cause label is a scenario-level target, not an exhaustive annotation of every operational signal.

Apply the view from the existing deployment directory after staging loads:

```powershell
Push-Location $env:USERPROFILE\.exasol\personal\deployments\default
& $env:EXASOL_LAUNCHER connect -f D:\OpsNexus\infra\exasol\sql\03_create_intel_findings.sql
Pop-Location
```

The Flask API should next consume `OPS_INTEL.V_FINDINGS` via a read-only Exasol identity, serialize the stable finding contract, and apply API-level filtering/pagination. ADF remains the operational loader into `OPS_STAGE`; it must not write findings or ground-truth labels.
