"""Contract checks for the proposed Exasol staging layer."""

from __future__ import annotations

import csv
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
BUNDLE_DATA = ROOT / "synthetic-data" / "examples" / "seed-20261014" / "data"
SQL = (ROOT / "infra" / "exasol" / "sql" / "02_create_staging_tables.sql").read_text(
    encoding="utf-8"
)

EXPECTED = {
    "data_sources.csv": ("source_id", "STG_DATA_SOURCES"),
    "pipeline_definitions.csv": ("pipeline_id", "STG_PIPELINE_DEFINITIONS"),
    "pipeline_runs.csv": ("run_id", "STG_PIPELINE_RUNS"),
    "datasets.csv": ("dataset_id", "STG_DATASETS"),
    "dataset_observations.csv": ("observation_id", "STG_DATASET_OBSERVATIONS"),
    "quality_checks.csv": ("quality_check_id", "STG_QUALITY_CHECKS"),
    "quality_results.csv": ("quality_result_id", "STG_QUALITY_RESULTS"),
    "dependencies.csv": ("dependency_id", "STG_DEPENDENCIES"),
    "business_kpis.csv": ("kpi_id", "STG_BUSINESS_KPIS"),
    "incident_history.csv": ("incident_id", "STG_INCIDENT_HISTORY"),
    "scenario_metadata.csv": ("scenario_instance_id", "STG_SCENARIO_METADATA"),
}


class StagingContractTests(unittest.TestCase):
    def test_every_operational_csv_header_and_key_are_mapped(self) -> None:
        for filename, (key, table) in EXPECTED.items():
            with self.subTest(filename=filename):
                with (BUNDLE_DATA / filename).open(newline="", encoding="utf-8") as handle:
                    header = next(csv.reader(handle))
                self.assertIn(key, header)
                self.assertRegex(SQL, rf"CREATE TABLE(?: IF NOT EXISTS)? OPS_STAGE\.{table} ")
                self.assertRegex(SQL, rf"PRIMARY KEY \({key.upper()}\)")

    def test_ground_truth_is_not_an_operational_mapping(self) -> None:
        self.assertNotIn("EXPECTED_OUTCOMES", SQL.upper())
        self.assertNotIn("GROUND_TRUTH", SQL.upper())


if __name__ == "__main__":
    unittest.main()
