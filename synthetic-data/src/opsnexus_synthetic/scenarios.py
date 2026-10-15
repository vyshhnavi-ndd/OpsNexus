"""Approved deterministic demonstration scenarios and private expected outcomes."""

from __future__ import annotations

SCENARIO_CATALOGUE: tuple[dict[str, str], ...] = (
    {"scenario_id": "healthy_baseline", "scenario_type": "healthy", "description": "All measured checks pass."},
    {"scenario_id": "pipeline_failure", "scenario_type": "pipeline_failure", "description": "An upstream run fails and its dependent work is blocked."},
    {"scenario_id": "stale_data", "scenario_type": "stale_data", "description": "A successful run leaves data beyond the freshness limit."},
    {"scenario_id": "incomplete_data", "scenario_type": "incomplete_data", "description": "Observed row count is below the expected count."},
    {"scenario_id": "metric_anomaly", "scenario_type": "anomaly", "description": "A measured business metric is outside its configured range."},
    {"scenario_id": "cross_domain_inconsistency", "scenario_type": "cross_domain_inconsistency", "description": "Two related domain measurements disagree."},
    {"scenario_id": "recurring_incident", "scenario_type": "recurring_incident", "description": "Evidence resembles a previous synthetic incident."},
    {"scenario_id": "inconclusive", "scenario_type": "inconclusive", "description": "Available signals conflict and do not establish a cause."},
)

# This table is intentionally exported only to ground_truth/expected_outcomes.json.
EXPECTED_OUTCOMES: dict[str, dict[str, object]] = {
    "healthy_baseline": {"expected_trust_band": "HIGH", "expected_investigation_disposition": "HEALTHY_NO_ACTION", "expected_cause_category": None, "expected_recovery_status": None, "rationale": "Healthy fixture is already valid; no recovery action or verification run is expected."},
    "pipeline_failure": {"expected_trust_band": "LOW", "expected_investigation_disposition": "ACTIONABLE_CANDIDATE", "expected_cause_category": "UPSTREAM_PIPELINE_FAILURE", "expected_recovery_status": None, "rationale": "The fixture has a failed upstream run. Module 1 does not execute recovery or verification."},
    "stale_data": {"expected_trust_band": "LOW", "expected_investigation_disposition": "ACTIONABLE_CANDIDATE", "expected_cause_category": "STALE_DATA", "expected_recovery_status": None, "rationale": "Observed freshness lag exceeds the fixture threshold. No recovery verification is generated."},
    "incomplete_data": {"expected_trust_band": "LOW", "expected_investigation_disposition": "ACTIONABLE_CANDIDATE", "expected_cause_category": "INCOMPLETE_DATA", "expected_recovery_status": None, "rationale": "Observed completeness is below the fixture threshold. No recovery verification is generated."},
    "metric_anomaly": {"expected_trust_band": "MEDIUM", "expected_investigation_disposition": "AMBIGUOUS", "expected_cause_category": "METRIC_ANOMALY", "expected_recovery_status": None, "rationale": "A metric deviation is observed; a causal explanation is not established by this evidence."},
    "cross_domain_inconsistency": {"expected_trust_band": "LOW", "expected_investigation_disposition": "AMBIGUOUS", "expected_cause_category": "CROSS_DOMAIN_INCONSISTENCY", "expected_recovery_status": None, "rationale": "Related domain metrics disagree; the fixture does not establish which source is authoritative."},
    "recurring_incident": {"expected_trust_band": "MEDIUM", "expected_investigation_disposition": "AMBIGUOUS", "expected_cause_category": "RECURRING_PATTERN", "expected_recovery_status": None, "rationale": "Synthetic history is similar, but similarity alone does not prove the present cause."},
    "inconclusive": {"expected_trust_band": "UNKNOWN", "expected_investigation_disposition": "INCONCLUSIVE", "expected_cause_category": None, "expected_recovery_status": None, "rationale": "Contradictory freshness and completeness signals do not establish a cause."},
}

SCENARIO_IDS = tuple(item["scenario_id"] for item in SCENARIO_CATALOGUE)
