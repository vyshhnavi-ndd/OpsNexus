"""Read-only Flask API for the OpsNexus Exasol findings view."""

from __future__ import annotations

import os
import re
import ssl
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

from flask import Flask, jsonify, request
from dotenv import load_dotenv


FINDING_COLUMNS = (
    "FINDING_ID", "FINDING_TYPE", "SEVERITY", "AFFECTED_ENTITY_TYPE",
    "AFFECTED_ENTITY_ID", "EVIDENCE", "RECOMMENDED_ACTION",
    "SOURCE_REFERENCES", "MEASURED_VALUE", "EXPECTED_VALUE", "THRESHOLD_VALUE",
    "SOURCE_RUN_ID", "SCENARIO_INSTANCE_ID",
)
FINDING_TYPES = {
    "PIPELINE_FAILURE", "STALE_DATASET", "INCOMPLETE_DATA", "QUALITY_FAILURE",
    "KPI_ANOMALY", "CROSS_DOMAIN_INCONSISTENCY", "INCIDENT_RECURRENCE",
}
SEVERITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
MAX_PAGE_SIZE = 100
_SCENARIO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$")
_FINDING_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:|=-]{0,399}$")
_STARTED_AT_EVIDENCE_RE = re.compile(r"(?P<prefix>(?:^|;\s*)started_at=)(?P<value>[^;]+)")


class DatabaseUnavailable(Exception):
    """Raised when a database query cannot be completed."""


def _connect_from_environment():
    """Open PyExasol using environment settings and never permit SYS for API use."""
    load_dotenv(Path(__file__).with_name(".env"), override=False)
    user = os.environ.get("EXASOL_API_USER", "").strip()
    password = os.environ.get("EXASOL_API_PASSWORD", "")
    host = os.environ.get("EXASOL_HOST", "").strip()
    port = os.environ.get("EXASOL_PORT", "8563").strip()
    if not host or not user or not password:
        raise DatabaseUnavailable("Database configuration is incomplete")
    if user.casefold() == "sys":
        raise DatabaseUnavailable("A dedicated read-only API identity is required")
    if os.environ.get("EXASOL_ENCRYPTION", "true").casefold() != "true":
        raise DatabaseUnavailable("Encrypted database connections are required")
    if os.environ.get("EXASOL_VALIDATE_CERTIFICATE", "true").casefold() != "true":
        raise DatabaseUnavailable("Database certificate validation is required")
    fingerprint = os.environ.get("EXASOL_CERTIFICATE_FINGERPRINT", "").strip()
    if fingerprint and not re.fullmatch(r"[A-Fa-f0-9]{64}", fingerprint):
        raise DatabaseUnavailable("Database certificate fingerprint is invalid")
    try:
        import pyexasol
    except ImportError as exc:  # pragma: no cover - exercised only in misconfigured deployments
        raise DatabaseUnavailable("Exasol client is unavailable") from exc
    try:
        return pyexasol.connect(
            # PyExasol 0.27.0 supports certificate pinning in its DSN. When
            # no pin is configured, require normal CA validation explicitly.
            dsn=f"{host}/{fingerprint.upper()}:{port}" if fingerprint else f"{host}:{port}",
            user=user,
            password=password,
            schema="OPS_INTEL",
            encryption=True,
            **({} if fingerprint else {"websocket_sslopt": {"cert_reqs": ssl.CERT_REQUIRED}}),
            fetch_dict=True,
        )
    except Exception as exc:
        raise DatabaseUnavailable("Database connection failed") from exc


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _normalize_pipeline_failure_timestamp(evidence: Any) -> Any:
    """Render the contractually UTC STARTED_AT evidence with one Z suffix.

    STARTED_AT is a timezone-naive Exasol TIMESTAMP, but the staging contract
    defines it as UTC. Explicit offsets are converted to UTC; unparseable values
    are preserved rather than being labeled UTC.
    """
    if not isinstance(evidence, str):
        return evidence

    def normalize(match: re.Match[str]) -> str:
        value = match.group("value")
        raw = value.strip()
        if "T" not in raw and " " not in raw:
            return match.group(0)
        try:
            if raw.endswith(("Z", "z")):
                parsed = datetime.fromisoformat(raw[:-1] + "+00:00")
            else:
                parsed = datetime.fromisoformat(raw)
        except ValueError:
            return match.group(0)

        if parsed.tzinfo is None:
            # This field is specifically sourced from OPS_STAGE.STG_PIPELINE_RUNS.STARTED_AT,
            # whose project data contract defines naive values as UTC.
            parsed = parsed.replace(tzinfo=timezone.utc)
        parsed = parsed.astimezone(timezone.utc)
        padding = value[: len(value) - len(value.lstrip())]
        trailing = value[len(value.rstrip()):]
        return f"{match.group('prefix')}{padding}{parsed.isoformat().replace('+00:00', 'Z')}{trailing}"

    return _STARTED_AT_EVIDENCE_RE.sub(normalize, evidence, count=1)


def _finding(row: dict[str, Any]) -> dict[str, Any]:
    normalized = {str(key).upper(): value for key, value in row.items()}
    evidence = normalized.get("EVIDENCE")
    if str(normalized.get("FINDING_TYPE", "")).upper() == "PIPELINE_FAILURE":
        evidence = _normalize_pipeline_failure_timestamp(evidence)
    return {
        "finding_id": _json_value(normalized.get("FINDING_ID")),
        "finding_type": _json_value(normalized.get("FINDING_TYPE")),
        "severity": _json_value(normalized.get("SEVERITY")),
        "affected_entity": {
            "type": _json_value(normalized.get("AFFECTED_ENTITY_TYPE")),
            "id": _json_value(normalized.get("AFFECTED_ENTITY_ID")),
        },
        "evidence": _json_value(evidence),
        "recommended_action": _json_value(normalized.get("RECOMMENDED_ACTION")),
        "source_references": _json_value(normalized.get("SOURCE_REFERENCES")),
        "measured_value": _json_value(normalized.get("MEASURED_VALUE")),
        "expected_value": _json_value(normalized.get("EXPECTED_VALUE")),
        "threshold": _json_value(normalized.get("THRESHOLD_VALUE")),
        "source_run_id": _json_value(normalized.get("SOURCE_RUN_ID")),
        "scenario_instance_id": _json_value(normalized.get("SCENARIO_INSTANCE_ID")),
    }


def create_app(connection_factory: Callable[[], Any] | None = None) -> Flask:
    app = Flask(__name__)
    app.json.sort_keys = False
    connector = connection_factory or _connect_from_environment

    def query(sql: str, params: dict[str, Any] | None = None, *, scalar: bool = False):
        connection = None
        try:
            connection = connector()
            statement = connection.execute(sql, query_params=params or {})
            return statement.fetchval() if scalar else statement.fetchall()
        except DatabaseUnavailable:
            raise
        except Exception as exc:
            raise DatabaseUnavailable("Database query failed") from exc
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    app.logger.warning("Failed to close Exasol connection")

    @app.errorhandler(DatabaseUnavailable)
    def database_error(_error):
        return jsonify(error={"code": "database_unavailable", "message": "Database is unavailable"}), 503

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify(error={"code": "not_found", "message": "Resource not found"}), 404

    @app.errorhandler(405)
    def method_not_allowed(_error):
        return jsonify(error={"code": "method_not_allowed", "message": "Method not allowed"}), 405

    @app.errorhandler(Exception)
    def unexpected_error(_error):
        app.logger.error("Unexpected API error")
        return jsonify(error={"code": "internal_error", "message": "The request could not be completed"}), 500

    @app.get("/health")
    def health():
        query("SELECT 1", scalar=True)
        return jsonify(status="ok", database="connected"), 200

    @app.get("/api/findings")
    def list_findings():
        try:
            page = int(request.args.get("page", "1"))
            page_size = int(request.args.get("page_size", "50"))
        except ValueError:
            return jsonify(error={"code": "invalid_pagination", "message": "page and page_size must be integers"}), 400
        if page < 1 or page_size < 1 or page_size > MAX_PAGE_SIZE:
            return jsonify(error={"code": "invalid_pagination", "message": f"page must be positive and page_size must be between 1 and {MAX_PAGE_SIZE}"}), 400

        filters: list[str] = []
        params: dict[str, Any] = {}
        finding_type = request.args.get("finding_type")
        severity = request.args.get("severity")
        scenario = request.args.get("scenario_instance_id")
        if finding_type is not None:
            finding_type = finding_type.strip().upper()
            if finding_type not in FINDING_TYPES:
                return jsonify(error={"code": "invalid_filter", "message": "Unsupported finding_type"}), 400
            filters.append("FINDING_TYPE = {finding_type}")
            params["finding_type"] = finding_type
        if severity is not None:
            severity = severity.strip().upper()
            if severity not in SEVERITIES:
                return jsonify(error={"code": "invalid_filter", "message": "Unsupported severity"}), 400
            filters.append("SEVERITY = {severity}")
            params["severity"] = severity
        if scenario is not None:
            scenario = scenario.strip()
            if not _SCENARIO_RE.fullmatch(scenario):
                return jsonify(error={"code": "invalid_filter", "message": "Invalid scenario_instance_id"}), 400
            filters.append("SCENARIO_INSTANCE_ID = {scenario_instance_id}")
            params["scenario_instance_id"] = scenario

        where = " WHERE " + " AND ".join(filters) if filters else ""
        total = int(query(f"SELECT COUNT(*) FROM OPS_INTEL.V_FINDINGS{where}", params, scalar=True) or 0)
        params.update(limit=page_size, offset=(page - 1) * page_size)
        rows = query(
            f"SELECT {', '.join(FINDING_COLUMNS)} FROM ("
            f"SELECT {', '.join(FINDING_COLUMNS)}, "
            "ROW_NUMBER() OVER (ORDER BY FINDING_ID) AS API_ROW_NUM "
            f"FROM OPS_INTEL.V_FINDINGS{where}) "
            "WHERE API_ROW_NUM > {offset} AND API_ROW_NUM <= {offset} + {limit} "
            "ORDER BY API_ROW_NUM",
            params,
        )
        return jsonify(
            data=[_finding(row) for row in rows],
            pagination={
                "page": page,
                "page_size": page_size,
                "total_count": total,
                "total_pages": (total + page_size - 1) // page_size,
            },
        )

    @app.get("/api/findings/<finding_id>")
    def get_finding(finding_id: str):
        if not _FINDING_ID_RE.fullmatch(finding_id):
            return jsonify(error={"code": "invalid_finding_id", "message": "Invalid finding_id"}), 400
        rows = query(
            f"SELECT {', '.join(FINDING_COLUMNS)} FROM OPS_INTEL.V_FINDINGS "
            "WHERE FINDING_ID = {finding_id}",
            {"finding_id": finding_id},
        )
        if not rows:
            return jsonify(error={"code": "not_found", "message": "Finding not found"}), 404
        return jsonify(data=_finding(rows[0]))

    return app


app = create_app()
