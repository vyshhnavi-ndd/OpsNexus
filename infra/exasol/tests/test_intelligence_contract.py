"""Static contract checks for the first Exasol intelligence view."""

from pathlib import Path
import unittest


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
            "QUALITY_FAILURE",
            "KPI_ANOMALY",
            "INCIDENT_RECURRENCE",
        ):
            self.assertIn(finding_type, SQL)
        self.assertIn("OPS_STAGE.STG_PIPELINE_RUNS", SQL)
        self.assertIn("OPS_STAGE.STG_QUALITY_RESULTS", SQL)
        self.assertIn("OPS_STAGE.STG_BUSINESS_KPIS", SQL)
        self.assertIn("OPS_STAGE.STG_INCIDENT_HISTORY", SQL)
        self.assertNotIn("EXPECTED_OUTCOMES", SQL.upper())
        self.assertNotIn("GROUND_TRUTH", SQL.upper())


if __name__ == "__main__":
    unittest.main()
