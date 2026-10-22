import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from backend import app as backend_app
from backend.app import APPROVED_TABLES, ensure_approved_object, metadata_tables, summarize_cost_records
from api.app import create_app as create_findings_app


CONTRACT = json.loads(
    (Path(__file__).resolve().parents[2] / "contracts" / "dashboard_api.json")
    .read_text(encoding="utf-8")
)


class DashboardContractTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = str(Path(self.temp_dir.name) / "requests.sqlite3")
        self.client = backend_app.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_shared_routes_are_registered(self):
        methods = set()
        for rule in backend_app.app.url_map.iter_rules():
            if rule.rule == CONTRACT["requests"]["path"]:
                methods.update(rule.methods)
        self.assertIn("GET", methods)
        self.assertIn("POST", methods)
        self.assertEqual(CONTRACT["assistant"]["path"], "/api/rag/query")
        self.assertEqual(CONTRACT["assistant"]["upstream"], "http://127.0.0.1:5001")

        findings_app = create_findings_app(lambda: None)
        api_paths = {rule.rule for rule in findings_app.url_map.iter_rules()}
        self.assertIn(CONTRACT["assistant"]["path"], api_paths)

    def test_request_list_and_create_contract(self):
        with patch.dict(os.environ, {"OPSNEXUS_REQUEST_DB": self.database}):
            listed = self.client.get(CONTRACT["requests"]["path"])
            self.assertEqual(listed.status_code, 200)
            self.assertEqual(listed.json[CONTRACT["requests"]["listResponseKey"]], [])

            created = self.client.post(
                CONTRACT["requests"]["path"],
                json={"dataset": "OPS_STAGE.STG_DATASETS", "reason": "Review data", "priority": "High"},
            )
            self.assertEqual(created.status_code, 201)
            request_record = created.json[CONTRACT["requests"]["createResponseKey"]]
            self.assertEqual(request_record["dataset"], "OPS_STAGE.STG_DATASETS")
            self.assertEqual(request_record["reason"], "Review data")
            self.assertEqual(request_record["priority"], "High")

            mismatch = self.client.post(
                CONTRACT["requests"]["path"],
                json={"dataset_id": "wrong", "business_justification": "wrong", "priority": "High"},
            )
            self.assertEqual(mismatch.status_code, 400)

    def test_missing_billing_is_not_reported_as_zero_cost(self):
        daily = [{"cost_inr": None}, {"cost_inr": None}]
        self.assertEqual(
            summarize_cost_records(daily, "unavailable"),
            {"recorded_cost_inr": None, "days_with_cost_records": None},
        )
        self.assertEqual(
            summarize_cost_records([{"cost_inr": 0.0}], "working"),
            {"recorded_cost_inr": 0.0, "days_with_cost_records": 1},
        )

    def test_database_browser_allowlist_is_the_ops_stage_contract(self):
        expected = {
            "STG_DATA_SOURCES",
            "STG_PIPELINE_DEFINITIONS",
            "STG_DATASETS",
            "STG_QUALITY_CHECKS",
            "STG_DEPENDENCIES",
            "STG_SCENARIO_METADATA",
            "STG_PIPELINE_RUNS",
            "STG_DATASET_OBSERVATIONS",
            "STG_QUALITY_RESULTS",
            "STG_BUSINESS_KPIS",
            "STG_INCIDENT_HISTORY",
        }
        self.assertEqual(APPROVED_TABLES, expected)
        ensure_approved_object("OPS_STAGE", "STG_PIPELINE_RUNS")
        with self.assertRaises(ValueError):
            ensure_approved_object("OTHER_SCHEMA", "STG_PIPELINE_RUNS")
        with self.assertRaises(ValueError):
            ensure_approved_object("OPS_STAGE", "UNAPPROVED_TABLE")

    def test_metadata_query_only_lists_approved_staging_tables(self):
        with patch.object(backend_app, "query_rows", return_value=[]) as query:
            metadata_tables(Mock(), "OPS_STAGE")

        sql = query.call_args.args[1]
        self.assertIn("TABLE_SCHEMA = 'OPS_STAGE'", sql)
        self.assertIn("TABLE_NAME IN (", sql)
        self.assertIn("'STG_PIPELINE_RUNS'", sql)
        self.assertNotIn("V_FINDINGS", sql)

    def test_exasol_cost_metrics_are_unavailable_for_current_stage_contract(self):
        with patch.object(backend_app, "get_connection") as connect:
            response = self.client.get("/api/metrics/cost")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json["available"])
        self.assertIn("no cost-usage table", response.json["message"])
        connect.assert_not_called()

    def test_dashboard_backend_rejects_sys_with_clear_configuration_error(self):
        with patch.object(backend_app, "EXASOL_USER", "SYS"):
            response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json["error"]["code"], "EXASOL_SYS_FORBIDDEN")
        self.assertIn("authorized non-SYS", response.json["error"]["message"])

    def test_pipeline_metrics_query_the_staging_run_table(self):
        connection = Mock()
        columns = [
            {"column_name": "RUN_ID"},
            {"column_name": "STATUS"},
            {"column_name": "DURATION_SECONDS"},
        ]

        def query_result(_connection, sql):
            if "TOTAL_RUNS" in sql:
                return [{"total_runs": 3}]
            if "GROUP BY 1" in sql:
                return [
                    {"status": "SUCCEEDED", "total": 2},
                    {"status": "FAILED", "total": 1},
                ]
            return [{"avg_duration_seconds": 12}]

        with (
            patch.object(backend_app, "get_connection", return_value=connection),
            patch.object(backend_app, "metadata_tables", return_value=[{"table_name": "STG_PIPELINE_RUNS"}]),
            patch.object(backend_app, "metadata_columns", return_value=columns),
            patch.object(backend_app, "query_rows", side_effect=query_result) as query,
        ):
            response = self.client.get("/api/metrics/pipelines")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["metrics"]["total_runs"], 3)
        self.assertEqual(response.json["metrics"]["success_rate_pct"], 66.67)
        sql_calls = [call.args[1] for call in query.call_args_list]
        self.assertTrue(all('"STG_PIPELINE_RUNS"' in sql for sql in sql_calls))


if __name__ == "__main__":
    unittest.main()
