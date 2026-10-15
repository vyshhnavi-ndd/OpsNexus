# OpsNexus Exasol intelligence engine

The first Module 1 intelligence layer is the rerunnable view [`infra/exasol/sql/03_create_intel_findings.sql`](../infra/exasol/sql/03_create_intel_findings.sql), published as `OPS_INTEL.V_FINDINGS`. It reads only the 11 operational `OPS_STAGE.STG_*` tables. `ground_truth/expected_outcomes.json` remains evaluation-only and is not queried or loaded.

## Findings contract

Every finding has:

| Column | Meaning |
|---|---|
| `FINDING_ID` | Stable, deterministic ID derived from the source run, result, KPI, or recurrence key. |
| `SCENARIO_INSTANCE_ID` | Opaque scenario identifier when the evidence is scenario-specific; null for cross-scenario recurrence. |
| `FINDING_TYPE` | `PIPELINE_FAILURE`, `STALE_DATASET`, `QUALITY_FAILURE`, `KPI_ANOMALY`, or `INCIDENT_RECURRENCE`. |
| `SEVERITY` | Deterministic `HIGH` or `MEDIUM` rule result. |
| `AFFECTED_ENTITY_TYPE` / `AFFECTED_ENTITY_ID` | Pipeline, dataset, or KPI associated with the evidence. |
| `EVIDENCE` | Source IDs and measured/expected values used by the rule. |
| `RECOMMENDED_ACTION` | Explainable operational next step. |
| `SOURCE_RUN_ID` | Pipeline run supporting the finding where available. |

## Rules

- `PIPELINE_FAILURE`: a staging pipeline run has `STATUS = 'FAILED'`; severity is `HIGH`.
- `STALE_DATASET`: a freshness quality result is `FAIL`; its measured and expected lag values are included.
- `QUALITY_FAILURE`: any quality result is `FAIL`. Freshness and completeness are `HIGH`; other check types are `MEDIUM`.
- `KPI_ANOMALY`: the KPI baseline-to-observed relative deviation exceeds the `metric_range` quality threshold for the related observation. Deviation over 50% is `HIGH`, otherwise `MEDIUM`. Module 1 KPI values are marked `ILLUSTRATIVE_SYNTHETIC`, so the action explicitly avoids treating them as measured business loss.
- `INCIDENT_RECURRENCE`: the same pipeline and incident category occur more than once in operational incident history. A single incident produces no recurrence finding.

The view intentionally reports both `STALE_DATASET` and `QUALITY_FAILURE` for a failed freshness check: the first is a specific operational signal, while the second preserves the general quality failure contract.

## Execution and consumers

Apply the view after the staging tables are loaded:

```powershell
Push-Location C:\Users\vyshh\.exasol\personal\deployments\default
& C:\path\to\exasol.exe connect -f D:\OpsNexus\infra\exasol\sql\03_create_intel_findings.sql
Pop-Location
```

Validate with `SELECT * FROM OPS_INTEL.V_FINDINGS ORDER BY FINDING_TYPE, FINDING_ID;`. Flask and Power BI should use the view through read-only identities. ADF should continue to load operational evidence into `OPS_STAGE`; it should not write findings or ground-truth labels.

The rules are deliberately conservative and deterministic. Future models may add richer trend logic, but each output must retain source references and must not infer business impact beyond the operational evidence.
