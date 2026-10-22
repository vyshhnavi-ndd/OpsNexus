"""Static contract checks for the first Exasol intelligence view."""

from pathlib import Path
import unittest
from unittest.mock import patch

from infra.exasol.tests.evaluate_intelligence import (
    CAUSE_TO_FINDING,
    FINDINGS_SQL,
    _query_live_view,
    evaluate_results,
)


ROOT = Path(__file__).resolve().parents[3]
SQL = (ROOT / "infra" / "exasol" / "sql" / "03_create_intel_findings.sql").read_text(
    encoding="utf-8"
)


class IntelligenceContractTests(unittest.TestCase):
    def test_findings_view_and_contract_columns_exist(self) -> None:
        self.assertIn("CREATE OR REPLACE VIEW OPS_INTEL.V_FINDINGS", SQL)
        for column in (
            "FINDING_ID",
            "SCENARIO_INSTANCE_ID",
            "FINDING_TYPE",
            "SEVERITY",
            "AFFECTED_ENTITY_TYPE",
            "AFFECTED_ENTITY_ID",
            "EVIDENCE",
            "RECOMMENDED_ACTION",
            "SOURCE_RUN_ID",
        ):
            self.assertIn(column, SQL)

    def test_all_rules_use_staging_and_exclude_ground_truth(self) -> None:
        for finding_type in (
            "PIPELINE_FAILURE",
            "STALE_DATASET",
            "INCOMPLETE_DATA",
            "QUALITY_FAILURE",
            "KPI_ANOMALY",
            "CROSS_DOMAIN_INCONSISTENCY",
            "INCIDENT_RECURRENCE",
        ):
            self.assertIn(finding_type, SQL)
        self.assertIn("OPS_STAGE.STG_PIPELINE_RUNS", SQL)
        self.assertIn("OPS_STAGE.STG_QUALITY_RESULTS", SQL)
        self.assertIn("OPS_STAGE.STG_BUSINESS_KPIS", SQL)
        self.assertIn("OPS_STAGE.STG_INCIDENT_HISTORY", SQL)
        self.assertNotIn("EXPECTED_OUTCOMES", SQL.upper())
        self.assertNotIn("GROUND_TRUTH", SQL.upper())

    def test_extended_evidence_columns_and_safe_threshold_handling_exist(self) -> None:
        for column in ("SOURCE_REFERENCES", "MEASURED_VALUE", "EXPECTED_VALUE", "THRESHOLD_VALUE"):
            self.assertIn(column, SQL)
        self.assertIn("NULLIF(ABS(k.BASELINE_VALUE), 0)", SQL)
        self.assertIn("o.EXPECTED_ROW_COUNT > 0", SQL)
        self.assertIn("p.RELATIVE_GAP > 0.10", SQL)
        self.assertIn("COUNT(DISTINCT i.INCIDENT_ID) >= 2", SQL)

    def test_pipeline_failure_timestamp_is_explicitly_utc_in_evidence(self) -> None:
        self.assertIn("CAST(r.STARTED_AT AS VARCHAR(50)) || 'Z'", SQL)

    def test_evaluator_maps_findings_without_using_live_sql_as_ground_truth(self) -> None:
        self.assertEqual(
            CAUSE_TO_FINDING["CROSS_DOMAIN_INCONSISTENCY"],
            "CROSS_DOMAIN_INCONSISTENCY",
        )
        self.assertIn("OPS_INTEL.V_FINDINGS", FINDINGS_SQL)

    def test_live_evaluator_uses_configured_api_connection_and_closes_it(self) -> None:
        class Statement:
            def fetchall(self):
                return [{"finding_id": "F-1", "scenario_instance_id": "case-1",
                         "finding_type": "PIPELINE_FAILURE", "severity": "HIGH"}]

        class Connection:
            closed = False

            def execute(self, sql):
                self.sql = sql
                return Statement()

            def close(self):
                self.closed = True

        connection = Connection()
        with patch("api.app._connect_from_environment", return_value=connection) as connect:
            rows = _query_live_view()

        connect.assert_called_once_with()
        self.assertTrue(connection.closed)
        self.assertIn("OPS_INTEL.V_FINDINGS", connection.sql)
        self.assertEqual(rows[0]["FINDING_ID"], "F-1")

    def test_evaluator_excludes_inconclusive_and_unlabeled_scenarios_from_metrics(self) -> None:
        from json import loads

        truth_path = ROOT / "synthetic-data" / "examples" / "seed-20261014" / "ground_truth" / "expected_outcomes.json"
        truth = loads(truth_path.read_text(encoding="utf-8"))
        findings = []
        for scenario in truth["scenarios"].values():
            cause = scenario.get("expected_cause_category")
            target = CAUSE_TO_FINDING.get(cause)
            if target:
                findings.append({
                    "SCENARIO_INSTANCE_ID": scenario["scenario_instance_id"],
                    "FINDING_TYPE": target,
                })
        findings.append({
            "SCENARIO_INSTANCE_ID": truth["scenarios"]["inconclusive"]["scenario_instance_id"],
            "FINDING_TYPE": "STALE_DATASET",
        })

        result = evaluate_results(findings, truth)
        self.assertEqual(result["rule_metrics"]["PIPELINE_FAILURE"]["tp"], 1)
        self.assertEqual(result["rule_metrics"]["PIPELINE_FAILURE"]["fp"], 0)
        self.assertEqual(result["rule_metrics"]["PIPELINE_FAILURE"]["fn"], 0)
        inconclusive = next(row for row in result["scenarios"] if row["scenario"] == "inconclusive")
        self.assertEqual(inconclusive["status"], "UNLABELED_INCONCLUSIVE")


if __name__ == "__main__":
    unittest.main()
