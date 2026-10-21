from __future__ import annotations

import unittest
from decimal import Decimal
from unittest.mock import patch

from api.app import FINDING_COLUMNS, _connect_from_environment, create_app


class FakeStatement:
    def __init__(self, rows=(), scalar=None):
        self.rows = list(rows)
        self.scalar = scalar

    def fetchall(self):
        return self.rows

    def fetchval(self):
        return self.scalar


class FakeConnection:
    def __init__(self, rows, calls):
        self.rows = rows
        self.calls = calls

    def execute(self, sql, query_params):
        self.calls.append((sql, query_params))
        if "COUNT(*)" in sql:
            return FakeStatement(scalar=len(self.rows))
        if "SELECT 1" in sql:
            return FakeStatement(scalar=1)
        if "WHERE FINDING_ID" in sql:
            return FakeStatement([row for row in self.rows if row["FINDING_ID"] == query_params["finding_id"]])
        return FakeStatement(self.rows)

    def close(self):
        pass


def sample_finding():
    values = [
        "F-001", "KPI_ANOMALY", "HIGH", "KPI", "orders_total", "observed=8; baseline=10",
        "Investigate source data", "kpi_id=K1; observation_id=O1", Decimal("8"), Decimal("10"),
        Decimal("2"), "RUN-1", "SCENARIO-1",
    ]
    return dict(zip(FINDING_COLUMNS, values))


class FindingsApiTests(unittest.TestCase):
    def setUp(self):
        self.rows = [sample_finding()]
        self.calls = []
        self.app = create_app(lambda: FakeConnection(self.rows, self.calls))
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def test_health_checks_database(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"status": "ok", "database": "connected"})

    def test_list_returns_full_contract_and_pagination(self):
        response = self.client.get("/api/findings?page=1&page_size=10&finding_type=kpi_anomaly&severity=high&scenario_instance_id=SCENARIO-1")
        self.assertEqual(response.status_code, 200)
        result = response.json["data"][0]
        self.assertEqual(result["finding_id"], "F-001")
        self.assertEqual(result["affected_entity"], {"type": "KPI", "id": "orders_total"})
        self.assertEqual(result["measured_value"], "8")
        self.assertEqual(result["threshold"], "2")
        self.assertEqual(response.json["pagination"]["total_count"], 1)
        self.assertEqual(self.calls[-1][1], {
            "finding_type": "KPI_ANOMALY", "severity": "HIGH", "scenario_instance_id": "SCENARIO-1",
            "limit": 10, "offset": 0,
        })

    def test_pipeline_failure_timestamp_evidence_is_normalized_as_utc(self):
        cases = (
            ("2026-10-14 08:00:00", "2026-10-14T08:00:00Z"),
            ("2026-10-14T08:00:00Z", "2026-10-14T08:00:00Z"),
            ("2026-10-14T13:30:00+05:30", "2026-10-14T08:00:00Z"),
        )
        for source, expected in cases:
            with self.subTest(source=source):
                self.rows[0]["FINDING_TYPE"] = "PIPELINE_FAILURE"
                self.rows[0]["EVIDENCE"] = f"run_id=RUN-1; started_at={source}; other=value"
                response = self.client.get("/api/findings")
                self.assertEqual(
                    response.json["data"][0]["evidence"],
                    f"run_id=RUN-1; started_at={expected}; other=value",
                )

    def test_unknown_or_local_timestamp_evidence_is_not_labeled_utc(self):
        for source in ("yesterday morning", "2026-10-14 08:00:00 PST"):
            with self.subTest(source=source):
                original = f"run_id=RUN-1; started_at={source}; other=value"
                self.rows[0]["FINDING_TYPE"] = "PIPELINE_FAILURE"
                self.rows[0]["EVIDENCE"] = original
                response = self.client.get("/api/findings")
                self.assertEqual(response.json["data"][0]["evidence"], original)

    def test_single_finding_and_not_found(self):
        listed = self.client.get("/api/findings?page=1&page_size=1")
        detailed = self.client.get("/api/findings/F-001")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(detailed.status_code, 200)
        self.assertEqual(detailed.json["data"], listed.json["data"][0])
        self.assertEqual(self.client.get("/api/findings/UNKNOWN").status_code, 404)

    def test_empty_list_has_zero_counts(self):
        app = create_app(lambda: FakeConnection([], []))
        app.config["TESTING"] = True
        response = app.test_client().get("/api/findings")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {
            "data": [],
            "pagination": {"page": 1, "page_size": 50, "total_count": 0, "total_pages": 0},
        })

    def test_rejects_invalid_filters_and_pagination(self):
        for url in ("/api/findings?page=0", "/api/findings?page_size=101", "/api/findings?severity=BOGUS", "/api/findings?scenario_instance_id=x%20OR%201=1"):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 400)

    def test_database_error_is_structured_and_does_not_leak(self):
        app = create_app(lambda: (_ for _ in ()).throw(RuntimeError("password=secret")))
        app.config["TESTING"] = True
        client = app.test_client()
        for path in ("/health", "/api/findings", "/api/findings/F-001"):
            with self.subTest(path=path):
                response = client.get(path)
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json, {
                    "error": {"code": "database_unavailable", "message": "Database is unavailable"},
                })
                self.assertNotIn("secret", response.get_data(as_text=True))

    def test_sys_is_rejected_as_api_identity(self):
        with patch.dict("os.environ", {
            "EXASOL_HOST": "127.0.0.1",
            "EXASOL_API_USER": "sys",
            "EXASOL_API_PASSWORD": "placeholder",
        }, clear=False):
            with self.assertRaisesRegex(Exception, "dedicated read-only"):
                _connect_from_environment()

    def test_connection_uses_pinned_certificate_with_pyexasol(self):
        import os

        fingerprint = "a1" * 32
        env = {
            "EXASOL_HOST": "127.0.0.1",
            "EXASOL_PORT": "8563",
            "EXASOL_API_USER": "OPSNEXUS_API",
            "EXASOL_API_PASSWORD": "private-test-value",
            "EXASOL_ENCRYPTION": "true",
            "EXASOL_VALIDATE_CERTIFICATE": "true",
            "EXASOL_CERTIFICATE_FINGERPRINT": fingerprint,
        }
        with patch.dict(os.environ, env, clear=False), patch("pyexasol.connect") as connect:
            result = _connect_from_environment()
        self.assertIs(result, connect.return_value)
        self.assertEqual(connect.call_args.kwargs["dsn"], f"127.0.0.1/{fingerprint.upper()}:8563")
        self.assertTrue(connect.call_args.kwargs["encryption"])
        self.assertNotIn("validate_server_certificate", connect.call_args.kwargs)

    def test_connection_requires_validated_tls(self):
        import os

        with patch.dict(os.environ, {
            "EXASOL_HOST": "127.0.0.1",
            "EXASOL_API_USER": "OPSNEXUS_API",
            "EXASOL_API_PASSWORD": "private-test-value",
            "EXASOL_VALIDATE_CERTIFICATE": "false",
        }, clear=False):
            with self.assertRaisesRegex(Exception, "certificate validation"):
                _connect_from_environment()

    def test_method_errors_are_json(self):
        response = self.client.post("/health")
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json["error"]["code"], "method_not_allowed")

    def test_assistant_missing_ollama_model_has_clear_non_secret_error(self):
        from io import BytesIO

        with patch.dict("os.environ", {
            "OLLAMA_URL": "http://127.0.0.1:11434",
            "OLLAMA_MODEL": "llama3:latest",
        }, clear=False), patch("api.app.load_dotenv"), patch(
            "api.app.urlopen", return_value=BytesIO(b'{"models":[]}'),
        ):
            response = self.client.post(
                "/api/rag/query",
                json={"question": "Summarize the current findings."},
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json["error"]["code"], "assistant_model_missing")
        self.assertNotIn("http://", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
