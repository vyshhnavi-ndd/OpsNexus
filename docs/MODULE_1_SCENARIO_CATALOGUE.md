# Module 1 scenario catalogue

All records are deterministic synthetic fixtures. Semantic scenario names and expected assessments are in `synthetic-data/examples/<bundle>/ground_truth/expected_outcomes.json` only. Operational files use opaque `scenario_instance_id` values; `scenario_metadata.csv` uses `scenario_type=SYNTHETIC_DEMO` for every row and a generic description. The ground-truth file maps each semantic scenario name to its opaque case ID.

| `scenario_id` | Synthetic evidence pattern | Expected investigation result in ground truth |
|---|---|---|
| `healthy_baseline` | All runs succeed; freshness, completeness, and metric-range checks pass. | `HIGH`, `HEALTHY_NO_ACTION`, no cause. |
| `pipeline_failure` | Orders ingestion fails; dependent warehouse refresh is skipped; failed pipeline has no fabricated dataset observations. | `LOW`, `ACTIONABLE_CANDIDATE`, candidate `UPSTREAM_PIPELINE_FAILURE`. |
| `stale_data` | Successful run with orders freshness lag of 10,800 seconds against a 3,600-second limit. | `LOW`, `ACTIONABLE_CANDIDATE`, candidate `STALE_DATA`. |
| `incomplete_data` | Successful run with 800 observed versus 1,000 expected orders rows. | `LOW`, `ACTIONABLE_CANDIDATE`, candidate `INCOMPLETE_DATA`. |
| `metric_anomaly` | Successful run with an orders metric of 150 against a fixture baseline of 100 and maximum 20% deviation. | `MEDIUM`, `AMBIGUOUS`, anomaly observed but causal explanation not established. |
| `cross_domain_inconsistency` | Commerce/supply metrics are near 100 while finance is 82. | `LOW`, `AMBIGUOUS`, candidate `CROSS_DOMAIN_INCONSISTENCY`; authority is not established. |
| `recurring_incident` | Current orders freshness is delayed and one synthetic prior closed freshness incident exists. | `MEDIUM`, `AMBIGUOUS`, candidate `RECURRING_PATTERN`; similarity is not proof of cause. |
| `inconclusive` | Orders is stale while finance is incomplete, leaving conflicting signals. | `UNKNOWN`, `INCONCLUSIVE`, no established cause. |

`expected_recovery_status` is `null` in these fixtures because Module 1 does not execute a recovery or create independent post-recovery verification evidence. The ground truth must not be interpreted as claiming a recovery outcome. Trust bands and candidate labels are fixture expectations, not scientific guarantees.
