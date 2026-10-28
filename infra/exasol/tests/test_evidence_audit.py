from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
UDF_DIR = ROOT / "infra" / "exasol" / "udf"
sys.path.insert(0, str(UDF_DIR))

from evidence_audit import audit_finding_evidence, run  # noqa: E402


def finding(kind, evidence, references, measured=None, expected=None, threshold=None, run_id=None):
    return (kind, evidence, references, measured, expected, threshold, run_id)


PIPELINE_FAILURE = finding(
    "PIPELINE_FAILURE",
    "run_id=RUN-1; measured_status=FAILED; expected_status=SUCCEEDED; started_at=2026-10-18T00:00:00Z; upstream_dependency_context=none; downstream_dependency_context=none",
    "run_id=RUN-1; upstream_runs=NO_RUN",
    run_id="RUN-1",
)
STALE_DATASET = finding(
    "STALE_DATASET",
    "observation_id=OBS-1; run_id=RUN-2; measured_freshness_lag_seconds=900; expected_max_lag_seconds=600; quality_result=FAIL",
    "observation_id=OBS-1; quality_result_id=QR-1",
    "900", "600", "600", "RUN-2",
)
INCOMPLETE_DATA = finding(
    "INCOMPLETE_DATA",
    "observation_id=OBS-2; run_id=RUN-3; measured_row_count=75; expected_row_count=100; measured_completeness_ratio=0.75; configured_min_ratio=0.9",
    "observation_id=OBS-2; quality_result_id=QR-2",
    "0.75", "0.9", "0.9", "RUN-3",
)
QUALITY_FAILURE = finding(
    "QUALITY_FAILURE",
    "quality_result_id=QR-3; observation_id=OBS-3; run_id=RUN-4; check_type=VALIDITY; measured_value=0.7; expected_value=0.9; configured_threshold={}",
    "quality_result_id=QR-3; quality_check_id=QC-1; observation_id=OBS-3",
    "0.7", "0.9", "0.9", "RUN-4",
)
KPI_ANOMALY = finding(
    "KPI_ANOMALY",
    "kpi_id=KPI-1; observation_id=OBS-4; dataset_id=DS-1; metric=orders; measured_relative_deviation=0.2; baseline_value=100; observed_value=120; configured_max_relative_deviation=0.1; impact_type=SYNTHETIC",
    "kpi_id=KPI-1; observation_id=OBS-4; quality_result_id=QR-4",
    "0.2", "0.1", "0.1", "RUN-5",
)
CROSS_DOMAIN = finding(
    "CROSS_DOMAIN_INCONSISTENCY",
    "metric=orders; dataset_1=DS-1(OPS) measured=100; dataset_2=DS-2(SALES) measured=118; measured_relative_gap=0.1525; proposed_max_relative_gap=0.10; related_by_shared_downstream_dependencies=true",
    "observation_id=OBS-5; observation_id=OBS-6; run_id=RUN-6; run_id=RUN-7; kpi_id=KPI-2; kpi_id=KPI-3; dependency_id=DEP-1; dependency_id=DEP-2",
    "0.1525", "0.10", "0.10", "RUN-6",
)
HISTORICAL_RECURRENCE = finding(
    "INCIDENT_RECURRENCE",
    "incident_category=REPEATED_FAILURE; distinct_historical_incidents=2; recurrence_threshold=2",
    "incident_ids=INC-1, INC-2",
    "2", "2", "2",
)


SCENARIOS = {
    "healthy_baseline": [],
    "pipeline_failure": [PIPELINE_FAILURE],
    "stale_data": [STALE_DATASET],
    "incomplete_data": [INCOMPLETE_DATA],
    "metric_anomaly": [KPI_ANOMALY],
    "cross_domain_inconsistency": [CROSS_DOMAIN],
    "recurring_incident": [HISTORICAL_RECURRENCE],
    # Audit each observed finding independently; it must not assign a cause.
    "inconclusive": [PIPELINE_FAILURE, QUALITY_FAILURE],
}


class EvidenceAuditTests(unittest.TestCase):
    def test_eight_scenario_cases_are_deterministic_and_non_causal(self):
        self.assertEqual(len(SCENARIOS), 8)
        self.assertEqual(SCENARIOS["healthy_baseline"], [])
        for scenario, rows in SCENARIOS.items():
            with self.subTest(scenario=scenario):
                results = [json.loads(audit_finding_evidence(*row)) for row in rows]
                self.assertTrue(all(result["audit_status"] == "VALID" for result in results))
                self.assertTrue(all("root_cause" not in result for result in results))
                self.assertEqual(
                    [audit_finding_evidence(*row) for row in rows],
                    [audit_finding_evidence(*row) for row in rows],
                )

    def test_exasol_run_callback_uses_named_scalar_arguments(self):
        class Context:
            finding_type, evidence, source_references = PIPELINE_FAILURE[:3]
            measured_value = expected_value = threshold_value = source_run_id = None
            source_run_id = PIPELINE_FAILURE[6]

        self.assertEqual(json.loads(run(Context()))["audit_status"], "VALID")

    def test_missing_reference_is_explicitly_incomplete(self):
        row = list(STALE_DATASET)
        row[2] = "observation_id=OBS-1"
        result = json.loads(audit_finding_evidence(*row))
        self.assertEqual(result["audit_status"], "INCOMPLETE")
        self.assertEqual(result["reference_status"], "MISSING")
        self.assertIn("missing_required_reference:quality_result_id", result["issues"])

    def test_malformed_reference_is_invalid(self):
        row = list(STALE_DATASET)
        row[2] = "observation_id=OBS 1; quality_result_id=QR-1"
        result = json.loads(audit_finding_evidence(*row))
        self.assertEqual(result["audit_status"], "INVALID")
        self.assertIn("malformed_reference:observation_id", result["issues"])

    def test_non_numeric_required_value_is_invalid(self):
        row = list(KPI_ANOMALY)
        row[3] = "NaN"
        result = json.loads(audit_finding_evidence(*row))
        self.assertEqual(result["audit_status"], "INVALID")
        self.assertEqual(result["numeric_status"], "INVALID")
        self.assertIn("invalid_numeric:measured_value", result["issues"])

    def test_non_numeric_value_inside_evidence_is_invalid(self):
        row = list(STALE_DATASET)
        row[1] = row[1].replace("measured_freshness_lag_seconds=900", "measured_freshness_lag_seconds=unknown")
        result = json.loads(audit_finding_evidence(*row))
        self.assertEqual(result["numeric_status"], "INVALID")
        self.assertIn("invalid_numeric:evidence.measured_freshness_lag_seconds", result["issues"])

    def test_evidence_reference_must_be_structurally_valid(self):
        row = list(STALE_DATASET)
        row[1] = row[1].replace("observation_id=OBS-1", "observation_id=OBS 1")
        result = json.loads(audit_finding_evidence(*row))
        self.assertEqual(result["audit_status"], "INVALID")
        self.assertEqual(result["evidence_status"], "INVALID")
        self.assertIn("malformed_evidence_reference:observation_id", result["issues"])

    def test_source_run_mismatch_is_invalid(self):
        row = list(PIPELINE_FAILURE)
        row[6] = "RUN-OTHER"
        result = json.loads(audit_finding_evidence(*row))
        self.assertEqual(result["audit_status"], "INVALID")
        self.assertIn("source_run_id_mismatch", result["issues"])

    def test_empty_optional_dependency_context_is_allowed(self):
        row = list(PIPELINE_FAILURE)
        row[2] = "run_id=RUN-1; upstream_runs=; dependent_runs="
        result = json.loads(audit_finding_evidence(*row))
        self.assertEqual(result["audit_status"], "VALID")

    def test_malformed_evidence_delimiter_is_invalid(self):
        row = list(PIPELINE_FAILURE)
        row[1] = "run_id=RUN-1; measured_status FAILED; expected_status=SUCCEEDED"
        result = json.loads(audit_finding_evidence(*row))
        self.assertEqual(result["evidence_status"], "INVALID")
        self.assertIn("malformed_evidence", result["issues"])

    def test_quality_result_lists_with_nested_semicolons_parse(self):
        row = list(HISTORICAL_RECURRENCE)
        row[2] = (
            "incident_ids=INC-1, INC-2; run_ids=RUN-1, RUN-2; "
            "quality_result_ids=QR-1; QR-2"
        )
        row[6] = "RUN-1"
        result = json.loads(audit_finding_evidence(*row))
        self.assertEqual(result["audit_status"], "VALID")

    def test_contract_deployment_script_embeds_tested_python_source(self):
        source = (UDF_DIR / "evidence_audit.py").read_text(encoding="utf-8")
        sql = (ROOT / "infra" / "exasol" / "sql" / "05_create_evidence_audit_udf.sql").read_text(encoding="utf-8")
        marker = ") RETURNS VARCHAR(4000) AS\n"
        start = sql.index(marker) + len(marker)
        end = sql.index("\n/\n", start)
        self.assertEqual(sql[start:end + 1], source)
        self.assertIn("CREATE PYTHON3 SCALAR SCRIPT OPS_INTEL.AUDIT_FINDING_EVIDENCE", sql)
        self.assertNotIn("CREATE OR REPLACE", sql.upper())
        self.assertNotIn("GROUND_TRUTH", sql.upper())
        self.assertNotRegex(sql.upper(), r"\b(INSERT|UPDATE|DELETE|CREATE TABLE|DROP TABLE)\b")


if __name__ == "__main__":
    unittest.main()
