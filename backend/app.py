import os
import re
import ssl
import logging
import importlib.util
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import math
import pyexasol
from pyexasol.exceptions import ExaAuthError
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv


import time
import threading
import requests

from datetime import date, timedelta
from flask import jsonify, request
from azure.identity import ClientSecretCredential

# Cost data is cached for 6 hours.
COST_CACHE_TTL = 6 * 60 * 60

# Fallback wait if Azure does not provide a retry interval.
COST_RATE_LIMIT_WAIT = 15 * 60

_cost_cache = {
    "data": None,
    "expires_at": 0,
    "blocked_until": 0
}

_cost_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=True)

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False

frontend_origins = [
    origin.strip()
    for origin in os.getenv("FRONTEND_URL", "http://localhost:5173").split(",")
    if origin.strip()
]
CORS(
    app,
    resources={
        r"/api/*": {
            "origins": [
                "http://localhost:3000",
                "http://localhost:5173",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:5173",
            ]
        }
    },
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

EXASOL_HOST = os.getenv("EXASOL_HOST", "127.0.0.1").strip()
EXASOL_PORT = int(os.getenv("EXASOL_PORT", "8563"))
EXASOL_USER = os.getenv("EXASOL_USER", "sys").strip()
EXASOL_PASSWORD = os.getenv("EXASOL_PASSWORD", "")
EXASOL_SCHEMA = os.getenv("EXASOL_SCHEMA", "HACKATHON").strip().upper()
NO_CERT_CHECK = os.getenv("EXASOL_NOCERTCHECK", "false").strip().lower() == "true"

# Exasol SQL identifiers are quoted only after validation.
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")
READ_ONLY_START = re.compile(r"^(SELECT|WITH)\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Exasol connection and SQL helpers
# ---------------------------------------------------------------------------

# ==================== AZURE DATA FACTORY PIPELINE API ====================

import os
import requests

from datetime import datetime, timedelta, timezone
from flask import jsonify
from azure.identity import ClientSecretCredential

import os
from datetime import date, datetime, timedelta, timezone

import requests
from flask import jsonify, request
from azure.identity import ClientSecretCredential


# Use the environment variables already configured for OpsNexus.
SUBSCRIPTION_ID = os.environ["AZURE_SUBSCRIPTION_ID"]
TENANT_ID = os.environ["AZURE_TENANT_ID"]
CLIENT_ID = os.environ["AZURE_CLIENT_ID"]
CLIENT_SECRET = os.environ["AZURE_CLIENT_SECRET"]

RESOURCE_GROUP = os.getenv("AZURE_RESOURCE_GROUP", "opsnexus")
DATA_FACTORY = os.getenv("AZURE_DATA_FACTORY", "opsnexus")

# ============================================================
# USAGE & BILLING CONFIGURATION
# Keep your existing imports and Azure credentials above this section.
# ============================================================

NORMAL_DAILY_COST = float(os.getenv("COST_NORMAL_MAX_INR", "10"))
ELEVATED_DAILY_COST = float(os.getenv("COST_ELEVATED_MAX_INR", "50"))
MONTHLY_BUDGET = float(os.getenv("AZURE_MONTHLY_BUDGET_INR", "1000"))

NORMAL_RUNS_MAX = int(os.getenv("NORMAL_RUNS_MAX", "5"))
ELEVATED_RUNS_MAX = int(os.getenv("ELEVATED_RUNS_MAX", "20"))

ARM = "https://management.azure.com"
API_VERSION = "2018-06-01"

from flask_cors import CORS

CORS(app, resources={
    r"/api/*": {
        "origins": [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:5000",
        ]
    }
})
# ============================================================
# AZURE COST MANAGEMENT
# Returns: {"YYYY-MM-DD": cost}
# ============================================================

def fetch_daily_cost(access_token, start_date, end_date):
    url = (
        f"{ARM}/subscriptions/{SUBSCRIPTION_ID}"
        "/providers/Microsoft.CostManagement/query"
    )

    payload = {
        "type": "ActualCost",
        "timeframe": "Custom",
        "timePeriod": {
            "from": f"{start_date.isoformat()}T00:00:00Z",
            "to": f"{end_date.isoformat()}T23:59:59Z",
        },
        "dataset": {
            "granularity": "Daily",
            "aggregation": {
                "totalCost": {
                    "name": "PreTaxCost",
                    "function": "Sum",
                }
            },
        },
    }

    response = requests.post(
        url,
        params={"api-version": "2023-11-01"},
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=60,
    )

    if not response.ok:
        app.logger.error(
            "Azure billing API returned HTTP %s: %s",
            response.status_code,
            response.text,
        )
        response.raise_for_status()

    result = response.json()
    properties = result.get("properties", {})
    columns = properties.get("columns", [])
    rows = properties.get("rows", [])

    column_names = [
        column.get("name", "")
        for column in columns
    ]

    date_column = next(
        (
            name for name in column_names
            if name.lower() in ("usagedate", "date")
        ),
        None,
    )

    cost_column = next(
        (
            name for name in column_names
            if name.lower() in ("pretaxcost", "cost", "totalcost")
        ),
        None,
    )

    if date_column is None or cost_column is None:
        raise ValueError(
            "Unexpected Azure Cost Management response columns: "
            f"{column_names}. Check the Azure response and aggregation."
        )

    date_index = column_names.index(date_column)
    cost_index = column_names.index(cost_column)

    daily_costs = {}

    for row in rows:
        if len(row) <= max(date_index, cost_index):
            continue

        raw_date = row[date_index]
        raw_cost = row[cost_index]

        if raw_date is None or raw_cost is None:
            continue

        date_text = str(raw_date)

        if len(date_text) == 8 and date_text.isdigit():
            day = (
                f"{date_text[:4]}-{date_text[4:6]}-"
                f"{date_text[6:8]}"
            )
        else:
            day = date.fromisoformat(date_text[:10]).isoformat()

        daily_costs[day] = daily_costs.get(day, 0.0) + float(raw_cost)

    return daily_costs


# ============================================================
# AZURE AUTHENTICATION
# ============================================================

def get_azure_token():
    credential = ClientSecretCredential(
        tenant_id=TENANT_ID,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
    )

    return credential.get_token(
        "https://management.azure.com/.default"
    ).token


# ============================================================
# COST CLASSIFICATION
# ============================================================

def classify_cost(cost):
    if cost is None:
        return {
            "level": "unknown",
            "reason": "No cost record was returned for this date.",
        }

    if cost <= NORMAL_DAILY_COST:
        return {
            "level": "normal",
            "reason": (
                f"Daily cost is within the configured normal limit "
                f"of ₹{NORMAL_DAILY_COST:.2f}."
            ),
        }

    if cost <= ELEVATED_DAILY_COST:
        return {
            "level": "elevated",
            "reason": (
                f"Daily cost exceeds ₹{NORMAL_DAILY_COST:.2f}, "
                f"but is within the configured elevated limit of "
                f"₹{ELEVATED_DAILY_COST:.2f}."
            ),
        }

    return {
        "level": "heavy",
        "reason": (
            f"Daily cost exceeds the configured threshold of "
            f"₹{ELEVATED_DAILY_COST:.2f}. Inspect resource-level "
            "charges and usage."
        ),
    }


# ============================================================
# PIPELINE RUN CLASSIFICATION
# ============================================================

def classify_runs(run_count):
    if run_count is None:
        return {
            "level": "unknown",
            "reason": "Pipeline execution history is unavailable.",
        }

    if run_count <= NORMAL_RUNS_MAX:
        return {
            "level": "normal",
            "reason": (
                f"{run_count} runs; normal limit is "
                f"{NORMAL_RUNS_MAX} runs per day."
            ),
        }

    if run_count <= ELEVATED_RUNS_MAX:
        return {
            "level": "elevated",
            "reason": (
                f"{run_count} runs; above the normal limit of "
                f"{NORMAL_RUNS_MAX}, but within the elevated limit "
                f"of {ELEVATED_RUNS_MAX}."
            ),
        }

    return {
        "level": "heavy",
        "reason": (
            f"{run_count} runs; above the configured limit of "
            f"{ELEVATED_RUNS_MAX} runs per day."
        ),
    }


# ============================================================
# AZURE DATA FACTORY PIPELINE RUNS
# ============================================================

def fetch_pipeline_runs(token, start_date, end_date):
    url = (
        f"{ARM}/subscriptions/{SUBSCRIPTION_ID}"
        f"/resourceGroups/{RESOURCE_GROUP}"
        f"/providers/Microsoft.DataFactory/factories/{DATA_FACTORY}"
        "/queryPipelineRuns"
    )

    end_exclusive = end_date + timedelta(days=1)

    body = {
        "lastUpdatedAfter": datetime.combine(
            start_date,
            datetime.min.time(),
            tzinfo=timezone.utc,
        ).isoformat(),
        "lastUpdatedBefore": datetime.combine(
            end_exclusive,
            datetime.min.time(),
            tzinfo=timezone.utc,
        ).isoformat(),
        "orderBy": [
            {
                "orderBy": "RunStart",
                "order": "ASC",
            }
        ],
    }

    runs = []
    continuation_token = None

    while True:
        payload = dict(body)

        if continuation_token:
            payload["continuationToken"] = continuation_token

        response = requests.post(
            url,
            params={"api-version": API_VERSION},
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=45,
        )

        if not response.ok:
            app.logger.error(
                "ADF pipeline API returned HTTP %s: %s",
                response.status_code,
                response.text,
            )
            response.raise_for_status()

        result = response.json()
        runs.extend(result.get("value", []))

        continuation_token = result.get("continuationToken")

        if not continuation_token:
            break

    return runs


def load_adf_pipeline_id_map():
    """Load optional ADF-name -> EXISTING pipeline ID mappings from .env.

    Example .env value (only use a mapping that is correct for your data):
      ADF_PIPELINE_ID_MAP={"pipeline1":"PL001","sales_load":"PL002"}

    Unmapped ADF pipelines are skipped instead of being assigned invented IDs.
    """
    raw = os.getenv("ADF_PIPELINE_ID_MAP", "{}").strip() or "{}"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "ADF_PIPELINE_ID_MAP must be valid JSON mapping ADF pipeline names "
            "to existing PIPELINE_ID values."
        ) from exc
    if not isinstance(parsed, dict):
        raise ValueError("ADF_PIPELINE_ID_MAP must be a JSON object.")
    return {
        str(name).strip().casefold(): str(pipeline_id).strip()
        for name, pipeline_id in parsed.items()
        if str(name).strip() and str(pipeline_id).strip()
    }


# ============================================================
# SYNCHRONIZE ADF PIPELINES, RUNS AND INCIDENTS INTO EXASOL
# POST /api/adf/sync-pipelines-to-exasol?days=30
# ============================================================
@app.post("/api/adf/sync-pipelines-to-exasol")
def sync_adf_pipelines_to_exasol():
    connection = None

    try:
        days = request.args.get("days", default=30, type=int)

        if days is None or not 1 <= days <= 90:
            return jsonify({
                "success": False,
                "error": "days must be between 1 and 90",
            }), 400

        # --------------------------------------------------
        # 1. Fetch actual Azure Data Factory data
        # --------------------------------------------------

        token = get_azure_token()

        end_date = datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=days - 1)

        runs = fetch_pipeline_runs(
            token,
            start_date,
            end_date,
        )

        factory_url = (
            f"{ARM}/subscriptions/{SUBSCRIPTION_ID}"
            f"/resourceGroups/{RESOURCE_GROUP}"
            f"/providers/Microsoft.DataFactory/factories/"
            f"{DATA_FACTORY}/pipelines"
        )

        response = requests.get(
            factory_url,
            headers={"Authorization": f"Bearer {token}"},
            params={"api-version": API_VERSION},
            timeout=45,
        )
        response.raise_for_status()

        pipeline_definitions = response.json().get("value", [])

        # --------------------------------------------------
        # 2. Connect and verify Exasol tables
        # --------------------------------------------------

        connection = get_connection()
        schema_name = "HACKATHON"
        quoted_schema = quote_identifier(schema_name)

        existing_tables = {
            row["table_name"].upper()
            for row in metadata_tables(connection, schema_name)
        }

        required_tables = {
            "STG_PIPELINE_DEFINITIONS",
            "STG_PIPELINE_RUNS",
            "STG_INCIDENT_HISTORY",
            "STG_SCENARIO_METADATA",
        }

        missing_tables = required_tables - existing_tables

        if missing_tables:
            return jsonify({
                "success": False,
                "error": "Required Exasol tables are missing",
                "missing_tables": sorted(missing_tables),
            }), 400

        # SCENARIO_INSTANCE_ID is a foreign key, not just a required text
        # column. Resolve IDs against the parent scenario metadata table before
        # inserting any ADF run/incident rows.
        scenario_metadata_table = f"{quoted_schema}.{quote_identifier('STG_SCENARIO_METADATA')}"
        scenario_rows = query_rows(
            connection,
            f"SELECT SCENARIO_INSTANCE_ID FROM {scenario_metadata_table}"
        )
        valid_scenario_ids = {
            str(row.get("scenario_instance_id")).strip()
            for row in scenario_rows
            if row.get("scenario_instance_id") is not None
            and str(row.get("scenario_instance_id")).strip()
        }
        if not valid_scenario_ids:
            raise ValueError(
                "STG_SCENARIO_METADATA has no SCENARIO_INSTANCE_ID values. "
                "Insert at least one valid scenario metadata row before syncing ADF runs."
            )
        default_scenario_id = sorted(valid_scenario_ids)[0]

        table_columns_cache = {}

        def get_table_columns(table_name):
            if table_name not in table_columns_cache:
                table_columns_cache[table_name] = {
                    row["column_name"].upper()
                    for row in metadata_columns(
                        connection,
                        schema_name,
                        table_name,
                    )
                }

            return table_columns_cache[table_name]

        # --------------------------------------------------
        # 3. Build safe SQL literals.
        # No query_params are passed to connection.execute().
        # --------------------------------------------------

        def sql_literal(value):
            if value is None:
                return "NULL"

            if isinstance(value, bool):
                return "TRUE" if value else "FALSE"

            if isinstance(value, datetime):
                if value.tzinfo is not None:
                    value = value.astimezone(
                        timezone.utc
                    ).replace(tzinfo=None)

                timestamp = value.strftime(
                    "%Y-%m-%d %H:%M:%S.%f"
                )

                return f"CAST('{timestamp}' AS TIMESTAMP)"

            if isinstance(value, date):
                return f"DATE '{value.isoformat()}'"

            if isinstance(value, Decimal):
                if not value.is_finite():
                    return "NULL"
                return str(value)

            if isinstance(value, int):
                return str(value)

            if isinstance(value, float):
                if not math.isfinite(value):
                    return "NULL"
                return repr(value)

            escaped = str(value).replace("'", "''")
            return f"'{escaped}'"

        # --------------------------------------------------
        # 4. Insert only when the primary key does not exist
        # --------------------------------------------------

        def insert_if_new(
            table_name,
            key_column,
            record,
            required_columns,
        ):
            if record.get(key_column) in (None, ""):
                return False

            table_columns = get_table_columns(table_name)

            missing_columns = (
                set(required_columns) - table_columns
            )

            if missing_columns:
                raise ValueError(
                    f"{table_name} is missing columns: "
                    f"{', '.join(sorted(missing_columns))}"
                )

            columns = [
                column
                for column in record
                if column.upper() in table_columns
            ]

            if key_column.upper() not in {
                column.upper() for column in columns
            }:
                raise ValueError(
                    f"{table_name} does not contain "
                    f"key column {key_column}"
                )

            quoted_table = (
                f"{quoted_schema}."
                f"{quote_identifier(table_name)}"
            )

            key_sql = sql_literal(record[key_column])

            check_sql = (
                f"SELECT 1 FROM {quoted_table} "
                f"WHERE {quote_identifier(key_column)} "
                f"= {key_sql} LIMIT 1"
            )

            check_statement = connection.execute(check_sql)

            try:
                exists = check_statement.fetchone() is not None
            finally:
                check_statement.close()

            if exists:
                return False

            quoted_columns = ", ".join(
                quote_identifier(column)
                for column in columns
            )

            values_sql = ", ".join(
                sql_literal(record[column])
                for column in columns
            )

            insert_sql = (
                f"INSERT INTO {quoted_table} "
                f"({quoted_columns}) "
                f"VALUES ({values_sql})"
            )

            statement = connection.execute(insert_sql)
            statement.close()

            return True

        # --------------------------------------------------
        # 5. Load existing pipeline and source mappings
        # --------------------------------------------------

        definitions_table = (
            f"{quoted_schema}."
            f"{quote_identifier('STG_PIPELINE_DEFINITIONS')}"
        )

        existing_definitions = query_rows(
            connection,
            f"""
                SELECT PIPELINE_ID, PIPELINE_NAME, SOURCE_ID
                FROM {definitions_table}
            """,
        )

        pipeline_id_by_name = {}
        source_id_by_name = {}
        existing_source_ids = []

        for row in existing_definitions:
            name = row.get("pipeline_name")
            pipeline_id = row.get("pipeline_id")
            source_id = row.get("source_id")

            if name and pipeline_id:
                pipeline_id_by_name[name] = pipeline_id

            if name and source_id:
                source_id_by_name[name] = source_id

            if source_id and source_id not in existing_source_ids:
                existing_source_ids.append(source_id)

        # Fallback prevents NULL SOURCE_ID. This is only a
        # technical fallback, not proof of correct data lineage.
        fallback_source_id = (
            existing_source_ids[0]
            if existing_source_ids
            else None
        )

        definitions_inserted = 0
        runs_inserted = 0
        incidents_inserted = 0
        source_fallbacks_used = []

        # --------------------------------------------------
        # --------------------------------------------------
        # 6. Resolve ADF pipeline names to EXISTING parent IDs.
        # Never manufacture a PIPELINE_ID from an Azure name such as pipeline1.
        # Use ADF_PIPELINE_ID_MAP only for intentional business mappings.
        # --------------------------------------------------
        valid_pipeline_ids = {
            str(row.get("pipeline_id")).strip()
            for row in existing_definitions
            if row.get("pipeline_id") is not None
            and str(row.get("pipeline_id")).strip()
        }
        pipeline_id_by_normalized_name = {
            str(row.get("pipeline_name")).strip().casefold():
                str(row.get("pipeline_id")).strip()
            for row in existing_definitions
            if row.get("pipeline_name") and row.get("pipeline_id")
        }
        explicit_pipeline_map = load_adf_pipeline_id_map()
        unmapped_pipeline_definitions = []
        definitions_inserted = 0
        runs_inserted = 0
        incidents_inserted = 0
        source_fallbacks_used = []

        for definition in pipeline_definitions:
            pipeline_name = definition.get("name")
            if not pipeline_name:
                continue
            normalized_name = str(pipeline_name).strip().casefold()
            pipeline_id = (
                explicit_pipeline_map.get(normalized_name)
                or pipeline_id_by_normalized_name.get(normalized_name)
            )
            if pipeline_id is None and str(pipeline_name).strip() in valid_pipeline_ids:
                pipeline_id = str(pipeline_name).strip()
            if pipeline_id not in valid_pipeline_ids:
                unmapped_pipeline_definitions.append({
                    "pipeline_name": pipeline_name,
                    "reason": (
                        "No matching existing PIPELINE_ID. Add the correct mapping "
                        "to ADF_PIPELINE_ID_MAP or register the pipeline in "
                        "STG_PIPELINE_DEFINITIONS first."
                    ),
                })
                continue
            pipeline_id_by_name[pipeline_name] = pipeline_id

        # --------------------------------------------------

        skipped_pipeline_runs = []

        # 7. Parse timestamps returned by Azure
        # --------------------------------------------------

        def parse_timestamp(value):
            if not value:
                return None

            parsed = datetime.fromisoformat(
                value.replace("Z", "+00:00")
            )

            if parsed.tzinfo is not None:
                parsed = parsed.astimezone(
                    timezone.utc
                ).replace(tzinfo=None)

            return parsed

        # --------------------------------------------------
        # 8. Sync actual ADF runs and failure incidents
        # --------------------------------------------------

        for run in runs:
            run_id = run.get("runId")
            pipeline_name = run.get("pipelineName")

            if not run_id or not pipeline_name:
                continue

            pipeline_id = (
                pipeline_id_by_name.get(pipeline_name)
                or explicit_pipeline_map.get(str(pipeline_name).strip().casefold())
                or pipeline_id_by_normalized_name.get(str(pipeline_name).strip().casefold())
            )
            if pipeline_id is None or str(pipeline_id).strip() not in valid_pipeline_ids:
                skipped_pipeline_runs.append({
                    "run_id": run_id,
                    "pipeline_name": pipeline_name,
                    "reason": "No matching PIPELINE_ID exists in STG_PIPELINE_DEFINITIONS",
                })
                app.logger.warning(
                    "Skipping ADF run %s: pipeline '%s' has no valid parent definition",
                    run_id, pipeline_name,
                )
                continue

            status = str(
                run.get("status") or "UNKNOWN"
            ).upper()

            started_at = parse_timestamp(run.get("runStart"))
            ended_at = parse_timestamp(run.get("runEnd"))
            if started_at is None:
                skipped_pipeline_runs.append({
                    "run_id": run_id,
                    "pipeline_name": pipeline_name,
                    "reason": "ADF run has no runStart; STARTED_AT is required by Exasol.",
                })
                continue

            duration_ms = run.get("durationInMs")
            # STG_PIPELINE_RUNS.DURATION_SECONDS is DECIMAL(18,0).
            duration_seconds = (
                round(float(duration_ms) / 1000)
                if duration_ms is not None
                else None
            )

            parameters = run.get("parameters") or {}

            # ADF runs do not always provide scenarioInstanceId.
            # STG_PIPELINE_RUNS.SCENARIO_INSTANCE_ID is NOT NULL, so
            # generate a stable, run-specific fallback when it is absent.
            requested_scenario_id = str(
                parameters.get("scenarioInstanceId") or ""
            ).strip()
            # ADF run parameters are not guaranteed to refer to a scenario
            # registered in STG_SCENARIO_METADATA. Use a valid parent key to
            # satisfy the Exasol foreign-key constraint.
            scenario_instance_id = (
                requested_scenario_id
                if requested_scenario_id in valid_scenario_ids
                else default_scenario_id
            )

            run_record = {
                "RUN_ID": run_id,
                "PIPELINE_ID": pipeline_id,
                "SCENARIO_INSTANCE_ID": scenario_instance_id,
                "STATUS": status,
                "STARTED_AT": started_at,
                "ENDED_AT": ended_at,
                "DURATION_SECONDS": duration_seconds,
                "SCHEMA_VERSION": "2.0.0",
            }

            if insert_if_new(
                "STG_PIPELINE_RUNS",
                "RUN_ID",
                run_record,
                {"RUN_ID", "PIPELINE_ID", "STATUS"},
            ):
                runs_inserted += 1

            # Only create incidents for actual failures/cancellations.
            if status not in {"FAILED", "CANCELLED"}:
                continue

            incident_record = {
                "INCIDENT_ID": f"ADF_{run_id}",
                "PIPELINE_ID": pipeline_id,
                "SCENARIO_INSTANCE_ID": scenario_instance_id,
                "OCCURRED_AT": ended_at or started_at or datetime.now(timezone.utc).replace(tzinfo=None),
                "INCIDENT_CATEGORY": (
                    "PIPELINE_FAILURE"
                    if status == "FAILED"
                    else "PIPELINE_CANCELLED"
                ),
                "RESOLUTION_STATUS": "OPEN",
                "SCHEMA_VERSION": "2.0.0",
            }

            if insert_if_new(
                "STG_INCIDENT_HISTORY",
                "INCIDENT_ID",
                incident_record,
                {
                    "INCIDENT_ID",
                    "PIPELINE_ID",
                    "OCCURRED_AT",
                    "INCIDENT_CATEGORY",
                    "RESOLUTION_STATUS",
                },
            ):
                incidents_inserted += 1

        # --------------------------------------------------
        # 9. Return sync results
        # --------------------------------------------------

        return jsonify({
            "success": True,
            "source": "Azure Data Factory",
            "destination_schema": schema_name,
            "period": {
                "from": start_date.isoformat(),
                "to": end_date.isoformat(),
                "days": days,
            },
            "azure": {
                "pipeline_definitions_fetched": len(
                    pipeline_definitions
                ),
                "pipeline_runs_fetched": len(runs),
            },
            "inserted": {
                "STG_PIPELINE_DEFINITIONS": definitions_inserted,
                "STG_PIPELINE_RUNS": runs_inserted,
                "STG_INCIDENT_HISTORY": incidents_inserted,
            },
            "source_mapping_fallbacks": source_fallbacks_used,
            "unmapped_pipeline_definitions": unmapped_pipeline_definitions,
            "unmapped_pipeline_definitions_count": len(unmapped_pipeline_definitions),
            "skipped_pipeline_runs": skipped_pipeline_runs,
            "skipped_pipeline_runs_count": len(skipped_pipeline_runs),
            "note": (
                "Existing run IDs are skipped. ADF pipeline names must match an "
                "existing PIPELINE_NAME/PIPELINE_ID or be mapped through "
                "ADF_PIPELINE_ID_MAP in .env. Unmapped pipelines and runs are reported "
                "rather than inserted with invalid foreign keys. Existing run records "
                "are not updated by this endpoint."
            ),
        }), 200

    except requests.RequestException as exc:
        app.logger.exception(
            "ADF-to-Exasol synchronization failed"
        )

        return jsonify({
            "success": False,
            "error": "Unable to fetch pipeline data from Azure Data Factory",
            "details": str(exc),
        }), 502

    except Exception as exc:
        app.logger.exception(
            "ADF-to-Exasol synchronization failed"
        )

        return jsonify({
            "success": False,
            "error": str(exc),
            "error_type": type(exc).__name__,
        }), 500

    finally:
        if connection is not None:
            connection.close()
#===========
# USAGE & BILLING DASHBOARD API
# GET /api/metrics/usage-billing?days=30
# ============================================================

@app.get("/api/metrics/usage-billing")
def usage_billing():
    try:
        days = request.args.get("days", default=30, type=int)

        if days is None or not 1 <= days <= 90:
            return jsonify({
                "success": False,
                "error": "days must be between 1 and 90",
            }), 400

        end_date = datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=days - 1)

        token = get_azure_token()
        errors = {}

        # ----------------------------------------------------
        # Fetch Azure costs
        # ----------------------------------------------------

        try:
            daily_costs = fetch_daily_cost(
                token,
                start_date,
                end_date,
            )
            billing_status = "working"

        except (
            requests.RequestException,
            ValueError,
            KeyError,
            TypeError,
        ) as exc:
            app.logger.exception("Unable to retrieve Azure billing data")
            daily_costs = {}
            billing_status = "unavailable"
            errors["billing"] = str(exc)

        # ----------------------------------------------------
        # Fetch ADF pipeline runs
        # ----------------------------------------------------

        try:
            runs = fetch_pipeline_runs(
                token,
                start_date,
                end_date,
            )
            pipeline_status = "working"

        except requests.RequestException as exc:
            app.logger.exception("Unable to retrieve ADF pipeline runs")
            runs = []
            pipeline_status = "unavailable"
            errors["pipelines"] = str(exc)

        # ----------------------------------------------------
        # Group pipeline runs by their start date
        # ----------------------------------------------------

        runs_by_day = {}

        if pipeline_status == "working":
            for run in runs:
                started = run.get("runStart")

                if not started:
                    continue

                try:
                    parsed_start = datetime.fromisoformat(
                        started.replace("Z", "+00:00")
                    )

                    if parsed_start.tzinfo is None:
                        parsed_start = parsed_start.replace(
                            tzinfo=timezone.utc
                        )

                    run_day = parsed_start.astimezone(
                        timezone.utc
                    ).date().isoformat()

                except (ValueError, TypeError, AttributeError):
                    continue

                runs_by_day.setdefault(run_day, []).append(run)

        # ----------------------------------------------------
        # Build daily usage and billing metrics
        # ----------------------------------------------------

        daily = []

        for offset in range(days):
            day = (
                start_date + timedelta(days=offset)
            ).isoformat()

            cost = (
                daily_costs.get(day)
                if billing_status == "working"
                else None
            )

            day_runs = (
                runs_by_day.get(day, [])
                if pipeline_status == "working"
                else None
            )

            cost_assessment = classify_cost(cost)

            run_assessment = classify_runs(
                len(day_runs) if day_runs is not None else None
            )

            cost_per_run = (
                round(cost / len(day_runs), 2)
                if cost is not None
                and day_runs is not None
                and len(day_runs) > 0
                else None
            )

            # ------------------------------------------------
            # Compare costs and pipeline usage
            # ------------------------------------------------

            if cost is None or day_runs is None:
                relationship = (
                    "Comparison is incomplete because billing or "
                    "pipeline data is unavailable, or no cost record "
                    "was returned for this date."
                )

            elif (
                cost > ELEVATED_DAILY_COST
                and len(day_runs) == 0
            ):
                relationship = (
                    "High recorded cost with no pipeline runs in "
                    "the returned history. Check other Azure resources, "
                    "billing delays, and the run-history window."
                )

            elif (
                cost > ELEVATED_DAILY_COST
                and len(day_runs) > ELEVATED_RUNS_MAX
            ):
                relationship = (
                    "High cost and high run volume occurred on the "
                    "same date. Investigate resource charges and "
                    "pipeline activity; correlation does not prove causation."
                )

            elif cost > ELEVATED_DAILY_COST:
                relationship = (
                    "Cost exceeds the configured threshold. Inspect "
                    "resource-level charges before attributing the "
                    "cost to pipeline execution."
                )

            else:
                relationship = (
                    "Compare daily cost and pipeline trends with "
                    "previous days. A causal relationship is not established."
                )

            daily.append({
                "date": day,
                "cost_inr": (
                    round(cost, 2)
                    if cost is not None
                    else None
                ),
                "pipeline_runs": (
                    len(day_runs)
                    if day_runs is not None
                    else None
                ),
                "succeeded": (
                    sum(
                        run.get("status") == "Succeeded"
                        for run in day_runs
                    )
                    if day_runs is not None
                    else None
                ),
                "failed": (
                    sum(
                        run.get("status") == "Failed"
                        for run in day_runs
                    )
                    if day_runs is not None
                    else None
                ),
                "cost_level": cost_assessment["level"],
                "cost_reason": cost_assessment["reason"],
                "usage_level": run_assessment["level"],
                "usage_reason": run_assessment["reason"],
                "cost_per_run_inr": cost_per_run,
                "relationship_reason": relationship,
            })

        # ----------------------------------------------------
        # Calculate summary metrics
        # ----------------------------------------------------

        recorded_cost = sum(
            row["cost_inr"]
            for row in daily
            if row["cost_inr"] is not None
        )

        recorded_days = sum(
            row["cost_inr"] is not None
            for row in daily
        )

        return jsonify({
            "success": (
                billing_status == "working"
                and pipeline_status == "working"
            ),
            "billing_status": billing_status,
            "pipeline_status": pipeline_status,
            "scope": f"subscription/{SUBSCRIPTION_ID}",
            "resource_group": RESOURCE_GROUP,
            "data_factory": DATA_FACTORY,
            "period": {
                "from": start_date.isoformat(),
                "to": end_date.isoformat(),
                "days_requested": days,
                "days_with_cost_records": recorded_days,
            },
            "summary": {
                "recorded_cost_inr": round(recorded_cost, 2),
                "pipeline_runs": (
                    len(runs)
                    if pipeline_status == "working"
                    else None
                ),
                "monthly_budget_inr": MONTHLY_BUDGET,
                "daily_normal_max_inr": NORMAL_DAILY_COST,
                "daily_elevated_max_inr": ELEVATED_DAILY_COST,
            },
            "daily": daily,
            "errors": errors,
            "note": (
                "Missing daily cost records are not assumed to be zero. "
                "Azure cost data may be delayed. Cost per run is an "
                "overall comparison, not direct per-pipeline attribution. "
                "Confirm the returned billing currency before treating "
                "amounts as INR."
            ),
        }), 200

    except Exception as exc:
        app.logger.exception(
            "Usage and billing endpoint failed"
        )

        return jsonify({
            "success": False,
            "error": str(exc),
            "error_type": type(exc).__name__,
        }), 500


# ============================================================
# GET ONE ADF PIPELINE RUN + ACTIVITY LOGS
# GET /api/adf/debug-run/<run_id>

# ============================================================
# ADF PIPELINE FAILURE ALERTS
# GET /api/adf/failure-alerts?hours=24
# ============================================================

@app.get("/api/adf/failure-alerts")
def adf_failure_alerts():
    try:
        hours = request.args.get("hours", default=24, type=int)

        if hours is None or not 1 <= hours <= 168:
            return jsonify({
                "success": False,
                "error": "hours must be between 1 and 168",
            }), 400

        token = get_azure_token()
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(hours=hours)

        url = (
            f"{ARM}/subscriptions/{SUBSCRIPTION_ID}"
            f"/resourceGroups/{RESOURCE_GROUP}"
            f"/providers/Microsoft.DataFactory/factories/{DATA_FACTORY}"
            "/queryPipelineRuns"
        )

        body = {
            "lastUpdatedAfter": start_time.isoformat(),
            "lastUpdatedBefore": now.isoformat(),
            "orderBy": [
                {
                    "orderBy": "RunStart",
                    "order": "DESC",
                }
            ],
        }

        all_runs = []
        continuation_token = None

        while True:
            payload = dict(body)

            if continuation_token:
                payload["continuationToken"] = continuation_token

            response = requests.post(
                url,
                params={"api-version": API_VERSION},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=45,
            )

            if not response.ok:
                app.logger.error(
                    "ADF failure-alert query failed: HTTP %s: %s",
                    response.status_code,
                    response.text,
                )
                response.raise_for_status()

            result = response.json()
            all_runs.extend(result.get("value", []))

            continuation_token = result.get("continuationToken")

            if not continuation_token:
                break

        failures = []

        for run in all_runs:
            if (run.get("status") or "").lower() != "failed":
                continue

            failures.append({
                "run_id": run.get("runId"),
                "pipeline_name": run.get("pipelineName"),
                "status": run.get("status"),
                "run_start": run.get("runStart"),
                "run_end": run.get("runEnd"),
                "duration_in_ms": run.get("durationInMs"),
                "message": run.get("message") or "Pipeline execution failed.",
                "parameters": run.get("parameters") or {},
            })

        failures.sort(
            key=lambda item: item.get("run_end")
            or item.get("run_start")
            or "",
            reverse=True,
        )

        return jsonify({
            "success": True,
            "alert": len(failures) > 0,
            "count": len(failures),
            "checked_at": now.isoformat(),
            "window_hours": hours,
            "failures": failures,
        }), 200

    except requests.RequestException:
        app.logger.exception("Azure request failed in ADF failure alerts")

        return jsonify({
            "success": False,
            "error": "Unable to retrieve pipeline failure information.",
        }), 502

    except Exception:
        app.logger.exception("ADF failure-alert endpoint failed")

        return jsonify({
            "success": False,
            "error": "Unable to process pipeline failure alerts.",
        }), 500

@app.get("/api/adf/debug-runs")
def debug_adf():
    config = {
        "tenant_id": os.getenv("AZURE_TENANT_ID"),
        "client_id": os.getenv("AZURE_CLIENT_ID"),
        "client_secret": os.getenv("AZURE_CLIENT_SECRET"),
        "subscription_id": os.getenv("AZURE_SUBSCRIPTION_ID"),
        "resource_group": os.getenv("AZURE_RESOURCE_GROUP"),
        "factory_name": os.getenv("AZURE_DATA_FACTORY"),
    }

    missing = [
        key for key, value in config.items() if not value
    ]

    if missing:
        return jsonify({
            "success": False,
            "error": "Missing Azure configuration",
            "missing": missing
        }), 500

    try:
        # 1. Authenticate with Azure
        credential = ClientSecretCredential(
            tenant_id=config["tenant_id"],
            client_id=config["client_id"],
            client_secret=config["client_secret"]
        )

        token = credential.get_token(
            "https://management.azure.com/.default"
        ).token

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        api_version = "2018-06-01"

        base_url = (
            "https://management.azure.com/subscriptions/"
            f"{config['subscription_id']}/resourceGroups/"
            f"{config['resource_group']}/providers/"
            "Microsoft.DataFactory/factories/"
            f"{config['factory_name']}"
        )

        # 2. Define the history window.
        # Example: /api/adf/debug-runs?days=7
        days = request.args.get("days", default=7, type=int)

        if days is None or not 1 <= days <= 90:
            return jsonify({
                "success": False,
                "error": "days must be between 1 and 90"
            }), 400

        now = datetime.now(timezone.utc)

        payload = {
            "lastUpdatedAfter": (
                now - timedelta(days=days)
            ).isoformat(),
            "lastUpdatedBefore": now.isoformat(),
            "filters": [],
            "orderBy": [
                {
                    "orderBy": "RunStart",
                    "order": "DESC"
                }
            ]
        }

        # 3. Query ALL pipeline runs, not a single run_id.
        runs_url = f"{base_url}/queryPipelineRuns"

        all_runs = []
        continuation_token = None

        while True:
            body = dict(payload)

            if continuation_token:
                body["continuationToken"] = continuation_token

            response = requests.post(
                runs_url,
                headers=headers,
                params={"api-version": api_version},
                json=body,
                timeout=60
            )

            if not response.ok:
                app.logger.error(
                    "ADF pipeline query failed: HTTP %s: %s",
                    response.status_code,
                    response.text[:2000]
                )

                return jsonify({
                    "success": False,
                    "error": "Unable to retrieve ADF pipeline runs",
                    "azure_status_code": response.status_code,
                    "azure_response": safe_json(response)
                }), response.status_code

            result = response.json()

            all_runs.extend(result.get("value", []))

            continuation_token = result.get("continuationToken")

            if not continuation_token:
                break

        # 4. Optional activity logs for every returned run.
        # Enable using ?include_activities=true
        include_activities = (
            request.args.get("include_activities", "false").lower()
            == "true"
        )

        pipeline_runs = []

        for run in all_runs:
            invoked_by = run.get("invokedBy") or {}

            details = {
                "run_id": run.get("runId"),
                "pipeline_name": run.get("pipelineName"),
                "status": run.get("status"),
                "run_start": run.get("runStart"),
                "run_end": run.get("runEnd"),
                "duration_in_ms": run.get("durationInMs"),
                "message": run.get("message"),
                "parameters": run.get("parameters", {}),
                "invoked_by": invoked_by,
                "trigger_name": invoked_by.get("name"),
                "trigger_id": invoked_by.get("id"),
                "last_updated": run.get("lastUpdated"),
                "annotations": run.get("annotations", []),
                "activity_count": None,
                "activities": [],
                "activity_log_error": None
            }

            # 5. Fetch activities only when explicitly requested.
            if include_activities and run.get("runId"):
                run_start = run.get("runStart")
                run_end = run.get("runEnd")

                def parse_utc(value):
                    if not value:
                        return None

                    return datetime.fromisoformat(
                        value.replace("Z", "+00:00")
                    )

                start = parse_utc(run_start)
                end = parse_utc(run_end)

                activity_start = (
                    start - timedelta(minutes=10)
                    if start else now - timedelta(days=days)
                )

                activity_end = (
                    end + timedelta(minutes=10)
                    if end else now + timedelta(minutes=1)
                )

                activity_url = (
                    f"{base_url}/pipelineruns/"
                    f"{run['runId']}/queryActivityruns"
                )

                activity_payload = {
                    "lastUpdatedAfter": activity_start.isoformat(),
                    "lastUpdatedBefore": activity_end.isoformat(),
                    "filters": [],
                    "orderBy": [{
                        "orderBy": "ActivityRunStart",
                        "order": "ASC"
                    }]
                }

                try:
                    activity_response = requests.post(
                        activity_url,
                        headers=headers,
                        params={"api-version": api_version},
                        json=activity_payload,
                        timeout=30
                    )

                    activity_response.raise_for_status()

                    activities = activity_response.json().get(
                        "value", []
                    )

                    details["activities"] = activities
                    details["activity_count"] = len(activities)

                except requests.RequestException as exc:
                    details["activity_log_error"] = str(exc)

            pipeline_runs.append(details)

        # 6. Return all runs with summary statistics.
        status_counts = {}

        for run in pipeline_runs:
            status = run.get("status") or "Unknown"
            status_counts[status] = status_counts.get(status, 0) + 1

        return jsonify({
            "success": True,
            "factory": config["factory_name"],
            "resource_group": config["resource_group"],
            "history_days": days,
            "total_runs": len(pipeline_runs),
            "status_summary": status_counts,
            "include_activities": include_activities,
            "pipelines": pipeline_runs
        }), 200

    except Exception as exc:
        app.logger.exception("ADF all-runs lookup failed")

        return jsonify({
            "success": False,
            "error": "Failed to retrieve pipeline runs",
            "details": str(exc)
        }), 500



@app.route("/api/metrics/cost", methods=["GET"])
def get_azure_cost():
    # Use the cache first, without contacting Azure.
    now = time.time()

    with _cost_lock:
        if (
            _cost_cache["data"] is not None
            and now < _cost_cache["expires_at"]
        ):
            cached = dict(_cost_cache["data"])
            cached["cached"] = True
            return jsonify(cached), 200

        if now < _cost_cache["blocked_until"]:
            return jsonify({
                "success": False,
                "error": "Azure cost API temporarily rate-limited",
                "retry_after_seconds": int(
                    _cost_cache["blocked_until"] - now
                )
            }), 429

    try:
        subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID")
        tenant_id = os.getenv("AZURE_TENANT_ID")
        client_id = os.getenv("AZURE_CLIENT_ID")
        client_secret = os.getenv("AZURE_CLIENT_SECRET")

        if not all([
            subscription_id,
            tenant_id,
            client_id,
            client_secret
        ]):
            return jsonify({
                "success": False,
                "error": "Azure credentials are missing"
            }), 500

        days = request.args.get("days", default=30, type=int)

        if days is None or not 1 <= days <= 90:
            return jsonify({
                "success": False,
                "error": "days must be between 1 and 90"
            }), 400

        end_date = date.today()
        start_date = end_date - timedelta(days=days - 1)

        credential = ClientSecretCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret
        )

        try:
            token = credential.get_token(
                "https://management.azure.com/.default"
            ).token

            url = (
                f"https://management.azure.com/subscriptions/"
                f"{subscription_id}/providers/Microsoft.CostManagement/"
                f"query?api-version=2026-06-01"
            )

            payload = {
                "type": "ActualCost",
                "timeframe": "Custom",
                "timePeriod": {
                    "from": start_date.isoformat(),
                    "to": end_date.isoformat()
                },
                "dataset": {
                    "granularity": "Daily",
                    "aggregation": {
                        "totalCost": {
                            "name": "PreTaxCost",
                            "function": "Sum"
                        }
                    },
                    "grouping": [{
                        "type": "Dimension",
                        "name": "ResourceGroup"
                    }]
                }
            }

            response = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                },
                json=payload,
                timeout=60
            )

        finally:
            credential.close()

        if not response.ok:
            try:
                details = response.json()
            except ValueError:
                details = response.text[:2000]

            app.logger.error(
                "Azure cost API failed: status=%s details=%s",
                response.status_code,
                str(details)[:2000]
            )

            if response.status_code == 429:
                retry_after = (
                    response.headers.get("Retry-After")
                    or response.headers.get(
                        "x-ms-ratelimit-microsoft.costmanagement-qpu-retry-after"
                    )
                    or response.headers.get(
                        "x-ms-ratelimit-microsoft.consumption-retry-after"
                    )
                )

                try:
                    wait_seconds = max(60, int(float(retry_after)))
                except (TypeError, ValueError):
                    wait_seconds = COST_RATE_LIMIT_WAIT

                with _cost_lock:
                    _cost_cache["blocked_until"] = (
                        time.time() + wait_seconds
                    )

                return jsonify({
                    "success": False,
                    "error": "Azure cost API rate limit exceeded",
                    "azure_status": 429,
                    "retry_after_seconds": wait_seconds,
                    "details": details
                }), 429

            return jsonify({
                "success": False,
                "error": "Azure Cost Management API failed",
                "azure_status": response.status_code,
                "details": details
            }), response.status_code

        result = response.json()
        properties = result.get("properties", {})

        columns = [
            column.get("name")
            for column in properties.get("columns", [])
        ]

        rows = [
            dict(zip(columns, row))
            for row in properties.get("rows", [])
        ]

        output = {
            "success": True,
            "scope": f"subscription/{subscription_id}",
            "period": {
                "from": start_date.isoformat(),
                "to": end_date.isoformat()
            },
            "columns": columns,
            "total_rows": len(rows),
            "cost_data": rows,
            "cached": False
        }

        with _cost_lock:
            _cost_cache["data"] = output
            _cost_cache["expires_at"] = (
                time.time() + COST_CACHE_TTL
            )
            _cost_cache["blocked_until"] = 0

        return jsonify(output), 200

    except Exception:
        app.logger.exception("Azure cost retrieval failed")

        return jsonify({
            "success": False,
            "error": "Failed to retrieve Azure costs"
        }), 500

@app.route("/api/debug/azure-config")
def debug_azure_config():
    names = [
        "AZURE_SUBSCRIPTION_ID",
        "AZURE_TENANT_ID",
        "AZURE_CLIENT_ID",
        "AZURE_CLIENT_SECRET",
    ]

    return jsonify({
        name: bool(os.getenv(name))
        for name in names
    })
@app.get("/api/adf/debug-run/<run_id>")
def debug_adf_run1(run_id):

    config = {
        "tenant_id": os.getenv("AZURE_TENANT_ID"),
        "client_id": os.getenv("AZURE_CLIENT_ID"),
        "client_secret": os.getenv("AZURE_CLIENT_SECRET"),
        "subscription_id": os.getenv("AZURE_SUBSCRIPTION_ID"),
        "resource_group": os.getenv("AZURE_RESOURCE_GROUP"),
        "factory_name": os.getenv("AZURE_DATA_FACTORY"),
    }

    missing = [
        key for key, value in config.items()
        if not value
    ]

    if missing:
        return jsonify({
            "success": False,
            "error": "Missing Azure configuration",
            "missing": missing
        }), 500

    try:
        # 1. Authenticate with Azure
        credential = ClientSecretCredential(
            tenant_id=config["tenant_id"],
            client_id=config["client_id"],
            client_secret=config["client_secret"]
        )

        token = credential.get_token(
            "https://management.azure.com/.default"
        ).token

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        api_version = "2018-06-01"

        # 2. Build ADF factory URL
        base_url = (
            "https://management.azure.com/subscriptions/"
            f"{config['subscription_id']}/resourceGroups/"
            f"{config['resource_group']}/providers/"
            "Microsoft.DataFactory/factories/"
            f"{config['factory_name']}"
        )

        # 3. Get the exact pipeline run
        run_url = (
            f"{base_url}/pipelineruns/{run_id}"
        )

        run_response = requests.get(
            run_url,
            headers=headers,
            params={"api-version": api_version},
            timeout=30
        )

        if not run_response.ok:
            app.logger.error(
                "ADF run lookup failed: HTTP %s: %s",
                run_response.status_code,
                run_response.text[:2000]
            )

            return jsonify({
                "success": False,
                "error": "Unable to retrieve ADF pipeline run",
                "run_id": run_id,
                "azure_status_code": run_response.status_code,
                "azure_response": safe_json(run_response)
            }), run_response.status_code

        run = run_response.json()

        # 4. Determine the time window for activity logs.
        # The window is based on this run, not a fixed history
        # period. A small margin accommodates delayed log updates.
        now = datetime.now(timezone.utc)

        def parse_utc(value):
            if not value:
                return None

            return datetime.fromisoformat(
                value.replace("Z", "+00:00")
            )

        run_start = parse_utc(run.get("runStart"))
        run_end = parse_utc(run.get("runEnd"))

        activity_start = (
            run_start - timedelta(minutes=10)
            if run_start else now - timedelta(days=1)
        )

        activity_end = (
            run_end + timedelta(minutes=10)
            if run_end else now + timedelta(minutes=1)
        )

        # 5. Fetch activity execution logs for this run
        activity_url = (
            f"{base_url}/pipelineruns/{run_id}"
            "/queryActivityruns"
        )

        activity_payload = {
            "lastUpdatedAfter": activity_start.isoformat(),
            "lastUpdatedBefore": activity_end.isoformat(),
            "filters": [],
            "orderBy": [
                {
                    "orderBy": "ActivityRunStart",
                    "order": "ASC"
                }
            ]
        }

        activities = []
        activity_error = None

        try:
            activity_response = requests.post(
                activity_url,
                headers=headers,
                params={"api-version": api_version},
                json=activity_payload,
                timeout=30
            )

            activity_response.raise_for_status()

            activities = activity_response.json().get(
                "value", []
            )

        except requests.RequestException as exc:
            activity_error = str(exc)

            app.logger.warning(
                "Could not fetch activities for run %s: %s",
                run_id,
                activity_error
            )

        # 6. Build useful pipeline details
        pipeline_details = {
            "run_id": run.get("runId"),
            "pipeline_name": run.get("pipelineName"),
            "status": run.get("status"),
            "run_start": run.get("runStart"),
            "run_end": run.get("runEnd"),
            "duration_in_ms": run.get("durationInMs"),
            "message": run.get("message"),
            "parameters": run.get("parameters", {}),
            "invoked_by": run.get("invokedBy"),
            "last_updated": run.get("lastUpdated"),
            "annotations": run.get("annotations", []),
            "activity_count": len(activities),
            "activities": activities,
            "activity_log_error": activity_error
        }

        return jsonify({
            "success": True,
            "factory": config["factory_name"],
            "pipeline": pipeline_details
        }), 200

    except Exception as exc:
        app.logger.exception(
            "ADF debug run failed for %s",
            run_id
        )

        return jsonify({
            "success": False,
            "error": "Failed to retrieve pipeline details",
            "details": str(exc),
            "run_id": run_id
        }), 500


def safe_json(response):
    try:
        return response.json()
    except ValueError:
        return {"message": response.text[:2000]}
@app.get("/api/adf/debug-run")
def debug_adf_run(run_id):

    config = {
        "tenant_id": os.getenv("AZURE_TENANT_ID"),
        "client_id": os.getenv("AZURE_CLIENT_ID"),
        "client_secret": os.getenv("AZURE_CLIENT_SECRET"),
        "subscription_id": os.getenv("AZURE_SUBSCRIPTION_ID"),
        "resource_group": os.getenv("AZURE_RESOURCE_GROUP"),
        "factory_name": os.getenv("AZURE_DATA_FACTORY"),
    }

    missing = [
        key for key, value in config.items()
        if not value
    ]

    if missing:
        return jsonify({
            "success": False,
            "error": "Missing Azure configuration",
            "missing": missing
        }), 500

    try:
        # 1. Authenticate with Azure
        credential = ClientSecretCredential(
            tenant_id=config["tenant_id"],
            client_id=config["client_id"],
            client_secret=config["client_secret"]
        )

        token = credential.get_token(
            "https://management.azure.com/.default"
        ).token

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        api_version = "2018-06-01"

        # 2. Build ADF factory URL
        base_url = (
            "https://management.azure.com/subscriptions/"
            f"{config['subscription_id']}/resourceGroups/"
            f"{config['resource_group']}/providers/"
            "Microsoft.DataFactory/factories/"
            f"{config['factory_name']}"
        )

        # 3. Get the exact pipeline run
        run_url = (
            f"{base_url}/pipelineruns/{run_id}"
        )

        run_response = requests.get(
            run_url,
            headers=headers,
            params={"api-version": api_version},
            timeout=30
        )

        if not run_response.ok:
            app.logger.error(
                "ADF run lookup failed: HTTP %s: %s",
                run_response.status_code,
                run_response.text[:2000]
            )

            return jsonify({
                "success": False,
                "error": "Unable to retrieve ADF pipeline run",
                "run_id": run_id,
                "azure_status_code": run_response.status_code,
                "azure_response": safe_json(run_response)
            }), run_response.status_code

        run = run_response.json()

        # 4. Determine the time window for activity logs.
        # The window is based on this run, not a fixed history
        # period. A small margin accommodates delayed log updates.
        now = datetime.now(timezone.utc)

        def parse_utc(value):
            if not value:
                return None

            return datetime.fromisoformat(
                value.replace("Z", "+00:00")
            )

        run_start = parse_utc(run.get("runStart"))
        run_end = parse_utc(run.get("runEnd"))

        activity_start = (
            run_start - timedelta(minutes=10)
            if run_start else now - timedelta(days=1)
        )

        activity_end = (
            run_end + timedelta(minutes=10)
            if run_end else now + timedelta(minutes=1)
        )

        # 5. Fetch activity execution logs for this run
        activity_url = (
            f"{base_url}/pipelineruns/{run_id}"
            "/queryActivityruns"
        )

        activity_payload = {
            "lastUpdatedAfter": activity_start.isoformat(),
            "lastUpdatedBefore": activity_end.isoformat(),
            "filters": [],
            "orderBy": [
                {
                    "orderBy": "ActivityRunStart",
                    "order": "ASC"
                }
            ]
        }

        activities = []
        activity_error = None

        try:
            activity_response = requests.post(
                activity_url,
                headers=headers,
                params={"api-version": api_version},
                json=activity_payload,
                timeout=30
            )

            activity_response.raise_for_status()

            activities = activity_response.json().get(
                "value", []
            )

        except requests.RequestException as exc:
            activity_error = str(exc)

            app.logger.warning(
                "Could not fetch activities for run %s: %s",
                run_id,
                activity_error
            )

        # 6. Build useful pipeline details
        pipeline_details = {
            "run_id": run.get("runId"),
            "pipeline_name": run.get("pipelineName"),
            "status": run.get("status"),
            "run_start": run.get("runStart"),
            "run_end": run.get("runEnd"),
            "duration_in_ms": run.get("durationInMs"),
            "message": run.get("message"),
            "parameters": run.get("parameters", {}),
            "invoked_by": run.get("invokedBy"),
            "last_updated": run.get("lastUpdated"),
            "annotations": run.get("annotations", []),
            "activity_count": len(activities),
            "activities": activities,
            "activity_log_error": activity_error
        }

        return jsonify({
            "success": True,
            "factory": config["factory_name"],
            "pipeline": pipeline_details
        }), 200

    except Exception as exc:
        app.logger.exception(
            "ADF debug run failed for %s",
            run_id
        )

        return jsonify({
            "success": False,
            "error": "Failed to retrieve pipeline details",
            "details": str(exc),
            "run_id": run_id
        }), 500


def safe_json(response):
    try:
        return response.json()
    except ValueError:
        return {"message": response.text[:2000]}

def get_connection():
    """Create a PyExasol connection using this app's .env configuration."""
    if not EXASOL_PASSWORD or EXASOL_PASSWORD == "YOUR_ACTUAL_EXASOL_PASSWORD":
        raise RuntimeError(
            f"EXASOL_PASSWORD is missing or still a placeholder. Set it in {BASE_DIR / '.env'}."
        )

    options = {
        "dsn": f"{EXASOL_HOST}:{EXASOL_PORT}",
        "user": EXASOL_USER,
        "password": EXASOL_PASSWORD,
        "schema": EXASOL_SCHEMA,
        "encryption": True,
        "compression": True,
        "autocommit": True,
    }
    if NO_CERT_CHECK:
        options["websocket_sslopt"] = {"cert_reqs": ssl.CERT_NONE}

    try:
        return pyexasol.connect(**options)
    except ExaAuthError as exc:
        raise RuntimeError(
            "Exasol authentication failed. Check EXASOL_USER and EXASOL_PASSWORD "
            f"in {BASE_DIR / '.env'}."
        ) from exc


def quote_identifier(value):
    """Validate and quote a schema/table/column identifier."""
    if not isinstance(value, str) or not IDENTIFIER_PATTERN.fullmatch(value):
        raise ValueError(f"Invalid SQL identifier: {value!r}")
    return '"' + value.replace('"', '""') + '"'


def sql_string(value):
    """Escape a string literal for SQL metadata filters."""
    return "'" + str(value).replace("'", "''") + "'"


def serialize(value):
    """Convert common Exasol/Python values to JSON-compatible values."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def query_rows(connection, sql):
    """Run a query and return rows as dictionaries with lowercase keys."""
    cursor = connection.execute(sql)
    try:
        columns = [str(name).lower() for name in cursor.column_names()]
        return [
            {key: serialize(value) for key, value in zip(columns, row)}
            for row in cursor.fetchall()
        ]
    finally:
        cursor.close()


def metadata_tables(connection, schema):
    return query_rows(
        connection,
        f"""
        SELECT TABLE_SCHEMA, TABLE_NAME
        FROM EXA_ALL_TABLES
        WHERE TABLE_SCHEMA = {sql_string(schema.upper())}
        ORDER BY TABLE_NAME
        """,
    )


def metadata_columns(connection, schema, table):
    return query_rows(
        connection,
        f"""
        SELECT
            COLUMN_NAME,
            COLUMN_TYPE,
            COLUMN_IS_NULLABLE,
            COLUMN_ORDINAL_POSITION
        FROM EXA_ALL_COLUMNS
        WHERE COLUMN_SCHEMA = {sql_string(schema.upper())}
          AND COLUMN_TABLE = {sql_string(table.upper())}
        ORDER BY COLUMN_ORDINAL_POSITION
        """,
    )


def table_exists(tables, name):
    return any(row.get("table_name", "").upper() == name.upper() for row in tables)


def first_existing(columns, *names):
    column_set = {name.upper() for name in columns}
    return next((name.upper() for name in names if name.upper() in column_set), None)


def count_by_status(connection, schema, table, status_column):
    qschema = quote_identifier(schema.upper())
    qtable = quote_identifier(table.upper())
    qcolumn = quote_identifier(status_column)
    return query_rows(
        connection,
        f"""
        SELECT
            UPPER(CAST({qcolumn} AS VARCHAR(100))) AS STATUS,
            COUNT(*) AS TOTAL
        FROM {qschema}.{qtable}
        GROUP BY 1
        ORDER BY 1
        """,
    )


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def error_response(exc, status=500):
    """Return safe API errors; detailed exception is available in server logs."""
    app.logger.exception("API request failed")

    text = str(exc).lower()
    if isinstance(exc, RuntimeError) and "authentication failed" in text:
        message = str(exc)
        code = "EXASOL_AUTH_FAILED"
        status = 503
    elif isinstance(exc, RuntimeError) and (
        "exasol_password" in text or "placeholder" in text
    ):
        message = str(exc)
        code = "EXASOL_CONFIG_MISSING"
        status = 503
    else:
        message = "The request could not be completed. Check the Flask log for details."
        code = "API_ERROR"

    return jsonify({"success": False, "error": {"code": code, "message": message}}), status


# ---------------------------------------------------------------------------
# Root and health
# ---------------------------------------------------------------------------

@app.get("/")
def home():
    return jsonify({
        "name": "OpsNexus Exasol DataOps Intelligence API",
        "status": "running",
        "database": "Exasol",
        "host": EXASOL_HOST,
        "port": EXASOL_PORT,
        "configured_schema": EXASOL_SCHEMA,
        "endpoints": [
            "/api/health",
            "/api/database",
            "/api/schemas",
            "/api/database-structure",
            "/api/tables?schema=HACKATHON",
            "/api/tables/<schema>/<table>",
            "/api/sql/execute (POST, read-only)",
            "/api/metrics/overview",
            "/api/metrics/pipelines",
            "/api/metrics/trust",
            "/api/metrics/cost",
        ],
    })


@app.get("/api/health")
def health():
    connection = None
    try:
        connection = get_connection()
        rows = query_rows(connection, "SELECT CURRENT_SCHEMA AS SCHEMA_NAME FROM DUAL")
        return jsonify({
            "success": True,
            "database": "Exasol",
            "connected": True,
            "host": EXASOL_HOST,
            "port": EXASOL_PORT,
            "schema": rows[0]["schema_name"] if rows else None,
        })
    except Exception as exc:
        return error_response(exc, 503)
    finally:
        if connection:
            connection.close()


@app.get("/api/database")
def get_database_name():
    """Return the database product label and active connection target."""
    return jsonify({
        "success": True,
        "database": "Exasol",
        "host": EXASOL_HOST,
        "port": EXASOL_PORT,
        "configured_schema": EXASOL_SCHEMA,
    })


# ---------------------------------------------------------------------------
# SQL Workbench-style database explorer
# ---------------------------------------------------------------------------

@app.get("/api/schemas")
def schemas():
    connection = None
    try:
        connection = get_connection()
        rows = query_rows(
            connection,
            """
            SELECT SCHEMA_NAME
            FROM EXA_ALL_SCHEMAS
            ORDER BY SCHEMA_NAME
            """,
        )
        return jsonify({
            "success": True,
            "count": len(rows),
            "schemas": rows,
        })
    except Exception as exc:
        return error_response(exc)
    finally:
        if connection:
            connection.close()


@app.get("/api/database-structure")
def database_structure():
    """
    Return the hierarchy:
    Exasol -> schemas -> tables -> columns and column data types.
    query_rows() returns dictionaries, so access fields by key (not row[0]).
    """
    connection = None
    try:
        connection = get_connection()

        schema_rows = query_rows(
            connection,
            """
            SELECT SCHEMA_NAME
            FROM EXA_ALL_SCHEMAS
            ORDER BY SCHEMA_NAME
            """,
        )

        schemas_result = []
        for schema_row in schema_rows:
            schema_name = schema_row["schema_name"]

            table_rows = metadata_tables(connection, schema_name)
            tables_result = []

            for table_row in table_rows:
                table_name = table_row["table_name"]
                column_rows = metadata_columns(connection, schema_name, table_name)

                tables_result.append({
                    "table_name": table_name,
                    "columns": [
                        {
                            "column_name": column["column_name"],
                            "data_type": column.get("column_type"),
                            "nullable": column.get("column_is_nullable"),
                            "position": column.get("column_ordinal_position"),
                        }
                        for column in column_rows
                    ],
                })

            schemas_result.append({
                "schema_name": schema_name,
                "table_count": len(tables_result),
                "tables": tables_result,
            })

        return jsonify({
            "success": True,
            "database": "Exasol",
            "host": EXASOL_HOST,
            "port": EXASOL_PORT,
            "schema_count": len(schemas_result),
            "schemas": schemas_result,
        })
    except Exception as exc:
        return error_response(exc)
    finally:
        if connection:
            connection.close()


@app.get("/api/tables")
def tables():
    connection = None
    try:
        schema = request.args.get("schema", EXASOL_SCHEMA).strip().upper()
        quote_identifier(schema)

        connection = get_connection()
        rows = metadata_tables(connection, schema)
        return jsonify({
            "success": True,
            "schema": schema,
            "count": len(rows),
            "tables": rows,
        })
    except ValueError as exc:
        return jsonify({
            "success": False,
            "error": {"code": "INVALID_SCHEMA", "message": str(exc)},
        }), 400
    except Exception as exc:
        return error_response(exc)
    finally:
        if connection:
            connection.close()


@app.get("/api/tables/<schema>/<table>")
def table_data(schema, table):
    connection = None
    try:
        schema = schema.strip().upper()
        table = table.strip().upper()
        qschema = quote_identifier(schema)
        qtable = quote_identifier(table)

        limit = min(max(request.args.get("limit", 100, type=int) or 100, 1), 500)
        offset = max(request.args.get("offset", 0, type=int) or 0, 0)

        connection = get_connection()
        available = metadata_tables(connection, schema)
        if not table_exists(available, table):
            return jsonify({
                "success": False,
                "error": {
                    "code": "TABLE_NOT_FOUND",
                    "message": f"Table {schema}.{table} was not found.",
                },
            }), 404

        columns = metadata_columns(connection, schema, table)
        column_names = [row["column_name"].upper() for row in columns]

        count_rows = query_rows(
            connection,
            f"SELECT COUNT(*) AS TOTAL FROM {qschema}.{qtable}",
        )
        total = count_rows[0]["total"] if count_rows else 0

        if column_names:
            order_column = quote_identifier(column_names[0])
            page_sql = (
                f"SELECT * FROM {qschema}.{qtable} "
                f"ORDER BY {order_column} LIMIT {limit} OFFSET {offset}"
            )
        else:
            page_sql = f"SELECT * FROM {qschema}.{qtable} LIMIT {limit}"

        rows = query_rows(connection, page_sql)
        return jsonify({
            "success": True,
            "schema": schema,
            "table": table,
            "columns": [
                {
                    "column_name": row["column_name"],
                    "data_type": row.get("column_type"),
                    "nullable": row.get("column_is_nullable"),
                    "position": row.get("column_ordinal_position"),
                }
                for row in columns
            ],
            "total_rows": total,
            "limit": limit,
            "offset": offset,
            "data": rows,
        })
    except ValueError as exc:
        return jsonify({
            "success": False,
            "error": {"code": "INVALID_IDENTIFIER", "message": str(exc)},
        }), 400
    except Exception as exc:
        return error_response(exc)
    finally:
        if connection:
            connection.close()


@app.post("/api/sql/execute")
def execute_read_only_sql():
    """
    Execute a single read-only SELECT/WITH query for the SQL editor.
    This deliberately rejects non-read-only statements and multiple statements.
    """
    connection = None
    try:
        payload = request.get_json(silent=True) or {}
        sql = payload.get("sql", "")
        if not isinstance(sql, str) or not sql.strip():
            return jsonify({
                "success": False,
                "error": {"code": "SQL_REQUIRED", "message": "Provide SQL in the 'sql' field."},
            }), 400

        sql = sql.strip()
        if not READ_ONLY_START.match(sql):
            return jsonify({
                "success": False,
                "error": {
                    "code": "READ_ONLY_ONLY",
                    "message": "Only SELECT and WITH queries are allowed by this endpoint.",
                },
            }), 403

        # Keep this editor endpoint to one statement. Semicolons inside string
        # literals are also rejected; this is intentionally conservative.
        if ";" in sql or "--" in sql or "/*" in sql or "*/" in sql:
            return jsonify({
                "success": False,
                "error": {
                    "code": "INVALID_SQL_FORMAT",
                    "message": "Submit one SQL statement without semicolons or comments.",
                },
            }), 400

        connection = get_connection()
        rows = query_rows(connection, sql)
        columns = list(rows[0].keys()) if rows else []
        return jsonify({
            "success": True,
            "columns": columns,
            "row_count": len(rows),
            "data": rows,
        })
    except Exception as exc:
        return error_response(exc, 400)
    finally:
        if connection:
            connection.close()


# ---------------------------------------------------------------------------
# OpsNexus metrics
# ---------------------------------------------------------------------------

@app.get("/api/metrics/overview")
def overview():
    connection = None
    try:
        connection = get_connection()
        found = metadata_tables(connection, EXASOL_SCHEMA)
        names = [row["table_name"].upper() for row in found]
        return jsonify({
            "success": True,
            "database": "Exasol",
            "schema": EXASOL_SCHEMA,
            "table_count": len(names),
            "tables": names,
            "dashboards": {
                "pipelines": "PIPELINE_RUNS" in names,
                "trust": bool({"TRUST_SCORES", "DATA_QUALITY_RESULTS"} & set(names)),
                "cost": "COST_USAGE_HISTORY" in names,
            },
        })
    except Exception as exc:
        return error_response(exc)
    finally:
        if connection:
            connection.close()


@app.get("/api/metrics/pipelines")
def pipeline_metrics():
    connection = None
    try:
        connection = get_connection()
        available = metadata_tables(connection, EXASOL_SCHEMA)
        if not table_exists(available, "PIPELINE_RUNS"):
            return jsonify({
                "success": True,
                "available": False,
                "message": "PIPELINE_RUNS does not exist in the configured schema.",
                "metrics": {},
            })

        columns = metadata_columns(connection, EXASOL_SCHEMA, "PIPELINE_RUNS")
        column_names = [row["column_name"].upper() for row in columns]
        qschema = quote_identifier(EXASOL_SCHEMA)
        qtable = quote_identifier("PIPELINE_RUNS")

        total_rows = query_rows(
            connection,
            f"SELECT COUNT(*) AS TOTAL_RUNS FROM {qschema}.{qtable}",
        )
        total = total_rows[0]["total_runs"] if total_rows else 0
        result = {"total_runs": total}

        status_col = first_existing(column_names, "STATUS", "RUN_STATUS")
        duration_col = first_existing(column_names, "DURATION_SECONDS", "DURATION")

        if status_col:
            groups = count_by_status(connection, EXASOL_SCHEMA, "PIPELINE_RUNS", status_col)
            status_counts = {
                row["status"] or "UNKNOWN": row["total"]
                for row in groups
            }
            successful = sum(
                count for status, count in status_counts.items()
                if status in ("SUCCESS", "SUCCEEDED", "COMPLETED")
            )
            failed = sum(
                count for status, count in status_counts.items()
                if status in ("FAILED", "FAILURE", "ERROR")
            )
            result.update({
                "successful_runs": successful,
                "failed_runs": failed,
                "success_rate_pct": round(successful * 100 / total, 2) if total else 0,
                "status_breakdown": status_counts,
            })

        if duration_col:
            qduration = quote_identifier(duration_col)
            duration_rows = query_rows(
                connection,
                f"""
                SELECT AVG({qduration}) AS AVG_DURATION_SECONDS
                FROM {qschema}.{qtable}
                """,
            )
            result["average_duration_seconds"] = (
                duration_rows[0]["avg_duration_seconds"] if duration_rows else None
            )

        return jsonify({"success": True, "available": True, "metrics": result})
    except Exception as exc:
        return error_response(exc)
    finally:
        if connection:
            connection.close()


@app.route("/api/trust/metrics", methods=["GET"])
def get_trust_metrics():
    """
    Return Data Trust metrics from the processed and rejected Exasol tables.

    The shared get_connection() helper applies the app's configured Exasol
    connection settings, including the local self-signed certificate option
    when EXASOL_NOCERTCHECK=true.
    """
    connection = None

    try:
        connection = get_connection()

        processed_result = connection.execute("""
            SELECT COUNT(*)
            FROM HACKATHON.SALES_PROCESSED
        """).fetchone()

        rejected_result = connection.execute("""
            SELECT COUNT(*)
            FROM HACKATHON.SALES_REJECTED
        """).fetchone()

        valid_records = int(processed_result[0] or 0)
        invalid_records = int(rejected_result[0] or 0)
        total_records = valid_records + invalid_records

        rejection_rate = (
            round(invalid_records * 100.0 / total_records, 2)
            if total_records else 0.0
        )
        trust_score = (
            round(valid_records * 100.0 / total_records, 2)
            if total_records else 0.0
        )

        metrics = {
            "trust_score": trust_score,
            "total_records": total_records,
            "valid_records": valid_records,
            "invalid_records": invalid_records,
            "avg_completeness": None,
            "financial_mismatches": None,
            "accuracy_failures": None,
            "correctness_failures": None,
            "missing_ids": None,
            "rejection_rate": rejection_rate,
            "reported_total_at_risk": None,
            "source": (
                "HACKATHON.SALES_PROCESSED, "
                "HACKATHON.SALES_REJECTED"
            ),
            "status": (
                "REVIEW_REQUIRED" if invalid_records else "HEALTHY"
            ),
            "charts": {
                "record_distribution": [
                    {"label": "Valid", "value": valid_records},
                    {"label": "Invalid", "value": invalid_records},
                ],
                # Financial mismatches are not calculated by this endpoint.
                # Keep the values null rather than reporting invented counts.
                "financial_quality": [
                    {"label": "Mismatches", "value": None},
                    {"label": "Other records", "value": None},
                ],
            },
        }

        app.logger.info(
            "Trust metrics retrieved: processed=%s, rejected=%s, total=%s",
            valid_records,
            invalid_records,
            total_records,
        )
        return jsonify(metrics), 200

    except Exception:
        app.logger.exception("Data Trust metrics endpoint failed")
        return jsonify({
            "success": False,
            "error": "Unable to retrieve Data Trust metrics from Exasol.",
        }), 500

    finally:
        if connection is not None:
            connection.close()

import os
import re
import json
import requests
from uuid import uuid4

from flask import request, jsonify


OLLAMA_URL = os.getenv(
    "OLLAMA_URL", "http://127.0.0.1:11434"
).rstrip("/")

OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL", "llama3:latest"
)
OLLAMA_BASE_URL = os.getenv(
    "OLLAMA_BASE_URL", OLLAMA_URL
).rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3:latest")
OLLAMA_TIMEOUT_SECONDS = int(
    os.getenv("OLLAMA_TIMEOUT_SECONDS", "120")
)
def ollama_chat(messages, json_mode=False):
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.2},
    }

    if json_mode:
        payload["format"] = "json"

    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat",
            json=payload,
            timeout=OLLAMA_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()

        answer = data.get("message", {}).get("content", "").strip()

        if not answer:
            raise RuntimeError("Ollama returned an empty response.")

        return answer

    except requests.exceptions.ConnectionError as exc:
        raise RuntimeError(
            "Cannot connect to Ollama. Ensure Ollama is running."
        ) from exc
    except requests.exceptions.Timeout as exc:
        raise RuntimeError("Ollama request timed out.") from exc
    except requests.exceptions.HTTPError as exc:
        raise RuntimeError(
            f"Ollama HTTP error: {response.text}"
        ) from exc

@app.post("/api/ollama/chat")
def ollama_chat_api():
    body = request.get_json(silent=True) or {}
    message = body.get("message", "")

    if not isinstance(message, str) or not message.strip():
        return jsonify({
            "success": False,
            "error": "Message is required.",
        }), 400

    messages = [
        {
            "role": "system",
            "content": (
                "You are the OpsNexus data engineering assistant. "
                "Help with Exasol, Azure Data Factory, SQL, and "
                "pipeline troubleshooting."
            ),
        },
        {
            "role": "user",
            "content": message.strip(),
        },
    ]

    try:
        answer = ollama_chat(messages)

        return jsonify({
            "success": True,
            "model": OLLAMA_MODEL,
            "response": answer,
        })

    except RuntimeError as exc:
        return jsonify({
            "success": False,
            "error": str(exc),
        }), 502
@app.route("/api/rag/sql-query", methods=["POST"], strict_slashes=False)
@app.route("/api/rag/query", methods=["POST"], strict_slashes=False)
def rag_query():
    connection = None

    try:
        payload = request.get_json(silent=True) or {}
        question = payload.get("question", payload.get("query", ""))

        if not isinstance(question, str) or not question.strip():
            return jsonify({
                "success": False,
                "error": "Please provide a question."
            }), 400

        question = question.strip()

        if len(question) > 2000:
            return jsonify({
                "success": False,
                "error": "Question must not exceed 2000 characters."
            }), 400

        # 1. Retrieve Exasol schema
        connection = get_connection()
        tables = metadata_tables(connection, EXASOL_SCHEMA)

        schema_parts = []
        allowed_tables = set()

        for item in tables:
            table = item["table_name"].upper()
            allowed_tables.add(table)

            columns = metadata_columns(
                connection, EXASOL_SCHEMA, table
            )

            column_names = [
                col["column_name"].upper()
                for col in columns
            ]

            schema_parts.append(
                f"{EXASOL_SCHEMA}.{table}: "
                f"{', '.join(column_names)}"
            )

        if not schema_parts:
            return jsonify({
                "success": False,
                "error": "No tables found in the configured schema."
            }), 404

        # 2. Ask Ollama to generate SQL
        sql_prompt = f"""
Generate one read-only Exasol SELECT query.

Available schema:
{chr(10).join(schema_parts)}

User question:
{question}

Rules:
- Return SQL only, without Markdown.
- Use only the supplied tables and columns.
- Qualify tables with {EXASOL_SCHEMA}.
- Do not generate write or administrative statements.
- Generate a single SELECT query.
- Do not use semicolons or SQL comments.
- Include LIMIT 100.
"""

        response = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": sql_prompt
                    }
                ],
                "stream": False,
                "options": {"temperature": 0}
            },
            timeout=180
        )
        response.raise_for_status()
        
        sql = response.json()["message"]["content"].strip()

        # Remove Markdown fences sometimes returned by Ollama.
        sql = re.sub(r"^\s*```(?:sql)?\s*", "", sql, flags=re.I)
        sql = re.sub(r"\s*```\s*$", "", sql).strip()

        # Remove one trailing statement terminator, if present.
        # Semicolons anywhere else remain prohibited.
        if sql.endswith(";"):
            sql = sql[:-1].rstrip()

        if not re.match(r"^(SELECT|WITH)\b", sql, re.I):
            raise ValueError("Only SELECT queries are permitted.")

        if any(token in sql for token in (";", "--", "/*", "*/")):
            raise ValueError("Multiple statements or SQL comments rejected.")


        forbidden = re.compile(
            r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|CREATE|"
            r"TRUNCATE|GRANT|REVOKE|CALL|EXECUTE|IMPORT|EXPORT)\b",
            re.I
        )

        if forbidden.search(sql):
            raise ValueError("Unsafe SQL operation rejected.")

        table_pattern = re.compile(
            r'\b(?:FROM|JOIN)\s+'
            r'(?:(?:"?([A-Za-z_][\w$]*)"?)[.])?'
            r'"?([A-Za-z_][\w$]*)"?',
            re.I
        )

        matches = list(table_pattern.finditer(sql))

        if not matches:
            raise ValueError("No approved table found in query.")

        for match in matches:
            schema_name, table_name = match.groups()

            # Allow unqualified tables or HACKATHON.TABLE_NAME.
            if schema_name and schema_name.upper() != EXASOL_SCHEMA:
                raise ValueError(
                    f"Access to schema '{schema_name}' is forbidden. "
                    f"Allowed schema: {EXASOL_SCHEMA}"
                )

            if table_name.upper() not in allowed_tables:
                raise ValueError(
                    f"Table '{table_name}' is not available "
                    f"in schema '{EXASOL_SCHEMA}'."
                )

        if not re.search(r"\bLIMIT\s+\d+\b", sql, re.I):
            sql += " LIMIT 100"

        # 4. Execute query against Exasol.
        # If Ollama invents a column or produces invalid SQL, send the exact
        # Exasol error and the live schema back to Ollama for one correction.
        try:
            rows = query_rows(connection, sql)
        except Exception as first_sql_error:
            app.logger.warning(
                "Ollama-generated SQL failed; requesting one schema-grounded correction: %s",
                str(first_sql_error)[:1000],
            )

            correction_prompt = f"""
Correct the failed Exasol SQL using only the exact live schema below.
Return one read-only SELECT query only, without Markdown, comments, or semicolons.
Do not invent table or column names. Qualify tables with {EXASOL_SCHEMA}.
Include LIMIT 100.

LIVE SCHEMA:
{chr(10).join(schema_parts)}

USER QUESTION:
{question}

FAILED SQL:
{sql}

EXASOL ERROR:
{str(first_sql_error)[:2000]}
"""
            correction_response = requests.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You repair Exasol SQL using supplied live schema metadata. "
                                "Never invent identifiers. Return SQL only."
                            ),
                        },
                        {"role": "user", "content": correction_prompt},
                    ],
                    "stream": False,
                    "options": {"temperature": 0},
                },
                timeout=OLLAMA_TIMEOUT_SECONDS,
            )
            correction_response.raise_for_status()
            sql = correction_response.json().get("message", {}).get("content", "").strip()
            sql = re.sub(r"^```(?:sql)?\s*", "", sql, flags=re.I)
            sql = re.sub(r"\s*```$", "", sql).strip()

            if not re.match(r"^(SELECT|WITH)\b", sql, re.I):
                raise ValueError("Ollama correction was not a read-only SELECT query.")

            if any(token in sql for token in (";", "--", "/*", "*/")):
                raise ValueError("Ollama correction contained a semicolon or SQL comment.")

            if forbidden.search(sql):
                raise ValueError("Unsafe SQL operation rejected after Ollama correction.")

            corrected_matches = list(table_pattern.finditer(sql))
            if not corrected_matches:
                raise ValueError("No approved table found in corrected SQL.")

            for match in corrected_matches:
                schema_name, table_name = match.groups()
                if schema_name and schema_name.upper() != EXASOL_SCHEMA:
                    raise ValueError(
                        f"Access to schema '{schema_name}' is forbidden. "
                        f"Allowed schema: {EXASOL_SCHEMA}"
                    )
                if table_name.upper() not in allowed_tables:
                    raise ValueError(
                        f"Table '{table_name}' is not available "
                        f"in schema '{EXASOL_SCHEMA}'."
                    )

            if not re.search(r"\bLIMIT\s+\d+\b", sql, re.I):
                sql += " LIMIT 100"

            # Execute the corrected query once. If it still fails, report it.
            rows = query_rows(connection, sql)

        connection.close()
        connection = None

        # 5. Generate an answer from actual retrieved data
        answer_prompt = f"""
Answer the user's question using only the database results.

Question:
{question}

Executed SQL:
{sql}

Database results:
{json.dumps(rows, default=str)}

Rules:
- Never invent values or records.
- If results are empty, say no matching records were found.
- Explain the results clearly and concisely.
"""

        response = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": answer_prompt
                    }
                ],
                "stream": False,
                "options": {"temperature": 0}
            },
            timeout=180
        )
        response.raise_for_status()

        answer = response.json()["message"]["content"]

        return jsonify({
            "success": True,
            "question": question,
            "sql": sql,
            "row_count": len(rows),
            "data": rows,
            "answer": answer,
            "model": OLLAMA_MODEL
        }), 200

    except ValueError as exc:
        return jsonify({
            "success": False,
            "error": str(exc)
        }), 400

    except Exception:
        app.logger.exception("RAG API failed")
        return jsonify({
            "success": False,
            "error": "RAG request failed. Check Flask logs."
        }), 500

    finally:
        if connection:
            connection.close()
# ============================================================
# DATA REQUESTS — EXASOL + OLLAMA
# Place this section AFTER the existing database helper functions
# and BEFORE if __name__ == "__main__".
# ============================================================

# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------

REQUEST_TABLE = "HACKATHON.DATA_REQUESTS"

VALID_PRIORITIES = {"Low", "Medium", "High", "Urgent"}
VALID_RECOMMENDATIONS = {"APPROVE", "REJECT", "UNDER REVIEW"}
VALID_RISKS = {"LOW", "MEDIUM", "HIGH"}


# ------------------------------------------------------------
# 1. Ollama AI review
# ------------------------------------------------------------

def review_data_request_with_ollama(
    schema_name,
    table_name,
    priority,
    description,
):
    prompt = f"""
You are a data governance reviewer.

Review this data access request:
Schema: {schema_name}
Table: {table_name}
Priority: {priority}
Business justification: {description}

Return only valid JSON with:
{{
  "recommendation": "APPROVE, REJECT, or UNDER REVIEW",
  "reasoning": "Brief explanation",
  "risk_level": "LOW, MEDIUM, or HIGH"
}}

Rules:
- Do not assume the user's permissions or data sensitivity.
- Use UNDER REVIEW when information is insufficient.
- Do not approve a request based on priority alone.
- Keep reasoning to exactly five words.
- State whether the justification is clear or unclear.
"""

    response = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": OLLAMA_MODEL,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0},
        },
        timeout=90,
    )
    response.raise_for_status()

    content = (
        response.json()
        .get("message", {})
        .get("content", "")
    )

    if not content:
        raise ValueError("Ollama returned an empty response.")

    result = json.loads(content)

    recommendation = str(
        result.get("recommendation", "UNDER REVIEW")
    ).strip().upper()

    risk_level = str(
        result.get("risk_level", "MEDIUM")
    ).strip().upper()

    if recommendation not in VALID_RECOMMENDATIONS:
        recommendation = "UNDER REVIEW"

    if risk_level not in VALID_RISKS:
        risk_level = "MEDIUM"

    reasoning = str(
        result.get(
            "reasoning",
            "Manual review is required.",
        )
    ).strip()[:2000]

    return {
        "recommendation": recommendation,
        "reasoning": reasoning,
        "risk_level": risk_level,
    }


# ------------------------------------------------------------
# 2. Standard response formatter
# ------------------------------------------------------------

def format_data_request(row):
    created_at = row[6]

    return {
        "id": str(row[0]) if row[0] is not None else "",
        "schema": row[1],
        "table_name": row[2],
        "dataset": f"{row[1]}.{row[2]}",
        "priority": row[3],
        "reason": row[4],
        "status": row[5],
        "created_at": (
            created_at.isoformat()
            if hasattr(created_at, "isoformat")
            else str(created_at) if created_at else None
        ),
        "ai_recommendation": row[7] or "UNDER REVIEW",
        "ai_reasoning": row[8] or "",
        "risk_level": row[9] or "MEDIUM",
    }


# ------------------------------------------------------------
# 3. GET requests from Exasol
# GET /api/data-requests
# GET /api/data-requests/
# GET /api/requests       (compatibility alias)
# ------------------------------------------------------------

@app.route(
    "/api/data-requests",
    methods=["GET"],
    strict_slashes=False,
)
@app.route(
    "/api/requests",
    methods=["GET"],
    strict_slashes=False,
)
def get_data_requests():
    connection = None
    cursor = None

    try:
        connection = get_connection()

        cursor = connection.execute(f"""
            SELECT
                REQUEST_ID,
                SCHEMA_NAME,
                TABLE_NAME,
                PRIORITY,
                DESCRIPTION,
                STATUS,
                CREATED_AT,
                AI_RECOMMENDATION,
                AI_REASONING,
                RISK_LEVEL
            FROM {REQUEST_TABLE}
            ORDER BY CREATED_AT DESC
        """)

        rows = cursor.fetchall()
        requests_list = [
            format_data_request(row)
            for row in rows
        ]

        return jsonify({
            "success": True,
            "count": len(requests_list),
            "requests": requests_list,
        }), 200

    except Exception:
        app.logger.exception(
            "GET data requests failed"
        )

        return jsonify({
            "success": False,
            "error": "Unable to load requests. Check Flask logs.",
        }), 500

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


# ------------------------------------------------------------
# 4. CREATE request in Exasol
# POST /api/data-requests
# POST /api/requests       (compatibility alias)
# ------------------------------------------------------------

@app.route(
    "/api/data-requests",
    methods=["POST"],
    strict_slashes=False,
)
@app.route(
    "/api/requests",
    methods=["POST"],
    strict_slashes=False,
)
def create_data_request():
    payload = request.get_json(silent=True) or {}

    schema_name = str(
        payload.get("schema_name", payload.get("schema", ""))
    ).strip().upper()

    table_name = str(
        payload.get("table_name", payload.get("table", ""))
    ).strip().upper()

    priority = str(
        payload.get("priority", "Medium")
    ).strip().capitalize()

    description = str(
        payload.get("description", payload.get("reason", ""))
    ).strip()

    if not all([
        schema_name,
        table_name,
        priority,
        description,
    ]):
        return jsonify({
            "success": False,
            "error": "Schema, table, priority, and description are required.",
        }), 400

    if priority not in VALID_PRIORITIES:
        return jsonify({
            "success": False,
            "error": "Priority must be Low, Medium, High, or Urgent.",
        }), 400

    if not 5 <= len(description) <= 2000:
        return jsonify({
            "success": False,
            "error": "Description must contain 5–2000 characters.",
        }), 400

    if not IDENTIFIER_PATTERN.fullmatch(schema_name):
        return jsonify({
            "success": False,
            "error": "Invalid schema name.",
        }), 400

    if not IDENTIFIER_PATTERN.fullmatch(table_name):
        return jsonify({
            "success": False,
            "error": "Invalid table name.",
        }), 400

    connection = None

    try:
        connection = get_connection()

        # Validate schema existence.
        schema_rows = query_rows(
            connection,
            f"""
                SELECT SCHEMA_NAME
                FROM EXA_ALL_SCHEMAS
                WHERE SCHEMA_NAME = {sql_string(schema_name)}
            """,
        )

        if not schema_rows:
            return jsonify({
                "success": False,
                "error": f"Schema '{schema_name}' was not found.",
            }), 400

        # Validate that the selected table belongs to the schema.
        available_tables = metadata_tables(
            connection,
            schema_name,
        )

        if not table_exists(available_tables, table_name):
            return jsonify({
                "success": False,
                "error": (
                    f"Table '{schema_name}.{table_name}' was not found."
                ),
            }), 400

        # If Ollama is unavailable, allow the request to be saved
        # for human review instead of losing the request.
        try:
            ai_review = review_data_request_with_ollama(
                schema_name,
                table_name,
                priority,
                description,
            )

        except (
            requests.RequestException,
            ValueError,
            KeyError,
            TypeError,
        ) as exc:
            app.logger.warning(
                "Ollama review unavailable: %s", exc
            )

            ai_review = {
                "recommendation": "UNDER REVIEW",
                "reasoning": (
                    "AI review is unavailable. Manual review is required."
                ),
                "risk_level": "MEDIUM",
            }

        request_id = str(uuid4())

        # Use the existing sql_string helper for SQL string literals.
        connection.execute(f"""
            INSERT INTO {REQUEST_TABLE}
            (
                REQUEST_ID,
                SCHEMA_NAME,
                TABLE_NAME,
                PRIORITY,
                DESCRIPTION,
                STATUS,
                CREATED_AT,
                AI_RECOMMENDATION,
                AI_REASONING,
                RISK_LEVEL
            )
            VALUES
            (
                {sql_string(request_id)},
                {sql_string(schema_name)},
                {sql_string(table_name)},
                {sql_string(priority)},
                {sql_string(description)},
                'Pending',
                CURRENT_TIMESTAMP,
                {sql_string(ai_review["recommendation"])},
                {sql_string(ai_review["reasoning"])},
                {sql_string(ai_review["risk_level"])}
            )
        """)

        app.logger.info(
            "Created data request %s", request_id
        )

        return jsonify({
            "success": True,
            "message": "Request saved successfully.",
            "request": {
                "id": request_id,
                "schema": schema_name,
                "table_name": table_name,
                "dataset": f"{schema_name}.{table_name}",
                "priority": priority,
                "reason": description,
                "status": "Pending",
                "ai_recommendation": ai_review["recommendation"],
                "ai_reasoning": ai_review["reasoning"],
                "risk_level": ai_review["risk_level"],
            },
        }), 201

    except Exception:
        app.logger.exception(
            "POST data request failed"
        )

        return jsonify({
            "success": False,
            "error": (
                "Failed to save the request. Check the Flask console."
            ),
        }), 500

    finally:
        if connection:
            connection.close()


# ------------------------------------------------------------
# 5. API route diagnostics
# GET /api/routes
# ------------------------------------------------------------

@app.get("/api/routes")
def list_api_routes():
    routes = []

    for rule in app.url_map.iter_rules():
        if rule.rule.startswith("/api/"):
            routes.append({
                "path": rule.rule,
                "methods": sorted(
                    method
                    for method in rule.methods
                    if method not in {"HEAD", "OPTIONS"}
                ),
            })

    return jsonify({
        "success": True,
        "count": len(routes),
        "routes": sorted(
            routes,
            key=lambda item: item["path"],
        ),
    }), 200


@app.route("/api/adf/explain-error", methods=["POST", "OPTIONS"])
def explain_adf_error():
    if request.method == "OPTIONS":
        return "", 204

    body = request.get_json(silent=True) or {}

    activity = body.get("activity") or {}
    if not isinstance(activity, dict):
        activity = {}

    error = activity.get("error") or {}
    if isinstance(error, dict):
        error_message = error.get("message", "")
        error_code = error.get("errorCode", "")
    else:
        error_message = str(error)
        error_code = ""

    error_message = (
        error_message
        or body.get("pipeline_message")
        or "No detailed error message was returned."
    )

    diagnostic_input = {
        "pipeline_name": body.get("pipeline_name", "Unknown"),
        "run_id": body.get("run_id", ""),
        "pipeline_status": body.get("pipeline_status", "Failed"),
        "activity_name": activity.get("activity_name", "Pipeline"),
        "activity_type": activity.get("activity_type", ""),
        "error_code": str(error_code),
        "error_message": str(error_message),
        "activity_output": activity.get("output", ""),
    }

    messages = [
        {
            "role": "system",
            "content": (
                "You are an Azure Data Factory troubleshooting assistant. "
                "Analyze the provided error without inventing facts. "
                "Return only valid JSON containing these string fields: "
                "error_code, error_message, likely_cause, "
                "recommended_solution, next_action, confidence_note."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(diagnostic_input, default=str),
        },
    ]

    try:
        answer = ollama_chat(messages, json_mode=True)
        diagnostic = json.loads(answer)

        diagnostic.setdefault("error_code", str(error_code or "Not provided"))
        diagnostic.setdefault("error_message", str(error_message))
        diagnostic.setdefault("likely_cause", "Root cause requires verification.")
        diagnostic.setdefault(
            "recommended_solution",
            "Inspect the failed activity output in ADF Monitor.",
        )
        diagnostic.setdefault(
            "next_action",
            "Verify the cause, apply the fix, and rerun the pipeline.",
        )
        diagnostic.setdefault(
            "confidence_note",
            "AI-generated suggestion; verify against Azure logs.",
        )

        diagnostic["pipeline_name"] = diagnostic_input["pipeline_name"]
        diagnostic["activity_name"] = diagnostic_input["activity_name"]

        return jsonify({"success": True, "diagnostic": diagnostic})

    except (RuntimeError, json.JSONDecodeError) as exc:
        app.logger.exception("Ollama error diagnosis failed")
        return jsonify({"success": False, "error": str(exc)}), 502

# ============================================================
# UNIFIED AZURE -> EXASOL STAGING SYNCHRONIZATION
# POST /api/azure/sync-all-to-exasol?days=30
#
# Loads:
#   - Azure Data Factory pipeline definitions -> STG_PIPELINE_DEFINITIONS
#   - Azure Data Factory runs              -> STG_PIPELINE_RUNS
#   - Failed/cancelled runs                -> STG_INCIDENT_HISTORY
#   - Daily Azure costs                    -> STG_DATASET_OBSERVATIONS
#   - Daily pipeline usage metrics         -> STG_DATASET_OBSERVATIONS
#   - Dataset metadata                     -> STG_DATASETS
#
# Existing IDs are skipped, making repeated runs safe.
# ============================================================

@app.post("/api/azure/sync-all-to-exasol")
def sync_all_azure_to_exasol():
    connection = None
    try:
        days = request.args.get("days", default=30, type=int)
        if days is None or not 1 <= days <= 90:
            return jsonify({
                "success": False,
                "error": "days must be between 1 and 90",
            }), 400

        token = get_azure_token()
        end_date = datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=days - 1)

        # Fetch the actual source data from Azure.
        pipeline_runs = fetch_pipeline_runs(token, start_date, end_date)
        definitions_url = (
            f"{ARM}/subscriptions/{SUBSCRIPTION_ID}"
            f"/resourceGroups/{RESOURCE_GROUP}"
            f"/providers/Microsoft.DataFactory/factories/"
            f"{DATA_FACTORY}/pipelines"
        )
        definitions_response = requests.get(
            definitions_url,
            headers={"Authorization": f"Bearer {token}"},
            params={"api-version": API_VERSION},
            timeout=45,
        )
        definitions_response.raise_for_status()
        pipeline_definitions = definitions_response.json().get("value", [])

        # Costs are loaded independently so a billing API issue is reported
        # clearly rather than silently creating fake zero-cost records.
        billing_error = None
        try:
            daily_costs = fetch_daily_cost(token, start_date, end_date)
            billing_status = "working"
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            app.logger.exception("Cost retrieval failed during unified sync")
            daily_costs = {}
            billing_status = "unavailable"
            billing_error = str(exc)

        connection = get_connection()
        schema = "HACKATHON"
        qschema = quote_identifier(schema)
        existing_tables = {
            row["table_name"].upper()
            for row in metadata_tables(connection, schema)
        }
        required_tables = {
            "STG_DATASETS",
            "STG_DATASET_OBSERVATIONS",
            "STG_PIPELINE_DEFINITIONS",
            "STG_PIPELINE_RUNS",
            "STG_INCIDENT_HISTORY",
            "STG_SCENARIO_METADATA",
        }
        missing = sorted(required_tables - existing_tables)
        if missing:
            return jsonify({
                "success": False,
                "error": "Required Exasol tables are missing",
                "missing_tables": missing,
                "hint": "Create the missing tables using the supplied HACKATHON staging schema.",
            }), 400

        # Resolve scenario foreign keys using the actual parent table values.
        scenario_metadata_table = f"{qschema}.{quote_identifier('STG_SCENARIO_METADATA')}"
        scenario_rows = query_rows(
            connection,
            f"SELECT SCENARIO_INSTANCE_ID FROM {scenario_metadata_table}"
        )
        valid_scenario_ids = {
            str(row.get("scenario_instance_id")).strip()
            for row in scenario_rows
            if row.get("scenario_instance_id") is not None
            and str(row.get("scenario_instance_id")).strip()
        }
        if not valid_scenario_ids:
            raise ValueError(
                "STG_SCENARIO_METADATA has no SCENARIO_INSTANCE_ID values. "
                "Insert at least one valid scenario metadata row before syncing ADF runs."
            )
        default_scenario_id = sorted(valid_scenario_ids)[0]

        columns_cache = {}

        def table_columns(table):
            if table not in columns_cache:
                columns_cache[table] = {
                    row["column_name"].upper()
                    for row in metadata_columns(connection, schema, table)
                }
            return columns_cache[table]

        def literal(value):
            if value is None:
                return "NULL"
            if isinstance(value, bool):
                return "TRUE" if value else "FALSE"
            if isinstance(value, datetime):
                if value.tzinfo:
                    value = value.astimezone(timezone.utc).replace(tzinfo=None)
                stamp = value.strftime("%Y-%m-%d %H:%M:%S.%f")
                return f"CAST('{stamp}' AS TIMESTAMP)"
            if isinstance(value, date):
                return f"CAST('{value.isoformat()} 00:00:00' AS TIMESTAMP)"
            if isinstance(value, Decimal):
                return str(value) if value.is_finite() else "NULL"
            if isinstance(value, int):
                return str(value)
            if isinstance(value, float):
                return repr(value) if math.isfinite(value) else "NULL"
            return "'" + str(value).replace("'", "''") + "'"

        def insert_if_missing(table, key, record, required):
            actual_columns = table_columns(table)
            missing_columns = set(required) - actual_columns
            if missing_columns:
                raise ValueError(
                    f"{table} is missing required columns: {sorted(missing_columns)}"
                )
            if record.get(key) in (None, ""):
                raise ValueError(f"Cannot insert {table}: {key} is empty")

            qtable = f"{qschema}.{quote_identifier(table)}"
            qkey = quote_identifier(key)
            key_value = literal(record[key])
            check = connection.execute(
                f"SELECT 1 FROM {qtable} WHERE {qkey} = {key_value} LIMIT 1"
            )
            try:
                if check.fetchone() is not None:
                    return False
            finally:
                check.close()

            names = [name for name in record if name.upper() in actual_columns]
            values = [literal(record[name]) for name in names]
            sql = (
                f"INSERT INTO {qtable} "
                f"({', '.join(quote_identifier(n) for n in names)}) "
                f"VALUES ({', '.join(values)})"
            )
            statement = connection.execute(sql)
            statement.close()
            return True

        # Source IDs are based on the existing source catalog. The endpoint
        # does not invent a new source ID if SRC001 is absent.
        source_rows = query_rows(
            connection,
            f"SELECT SOURCE_ID FROM {qschema}.{quote_identifier('STG_DATA_SOURCES')}"
        ) if "STG_DATA_SOURCES" in existing_tables else []
        source_ids = [row.get("source_id") for row in source_rows if row.get("source_id")]
        if not source_ids:
            raise ValueError(
                "STG_DATA_SOURCES has no source IDs. Add a valid source such as SRC001 first."
            )
        source_id = "SRC001" if "SRC001" in source_ids else source_ids[0]

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        schema_version = "2.0.0"

        # Register datasets for the two daily observation streams.
        dataset_specs = [
            ("DS_AZURE_COST_DAILY", "Azure Daily Cost", "COST"),
            ("DS_ADF_USAGE_DAILY", "ADF Daily Pipeline Usage", "PIPELINE"),
        ]
        for dataset_id, dataset_name, domain in dataset_specs:
            insert_if_missing(
                "STG_DATASETS",
                "DATASET_ID",
                {
                    "DATASET_ID": dataset_id,
                    "DATASET_NAME": dataset_name,
                    "DOMAIN": domain,
                    "SOURCE_ID": source_id,
                    "SCHEMA_VERSION": schema_version,
                },
                {"DATASET_ID", "DATASET_NAME", "DOMAIN", "SOURCE_ID", "SCHEMA_VERSION"},
            )

        # Resolve ADF pipeline names only to registered parent IDs. Do not
        # create a new ID from an Azure display name because run rows have FKs.
        definition_rows = query_rows(
            connection,
            f"""SELECT PIPELINE_ID, PIPELINE_NAME, SOURCE_ID
                FROM {qschema}.{quote_identifier('STG_PIPELINE_DEFINITIONS')}"""
        )
        id_by_name = {
            str(row["pipeline_name"]): str(row["pipeline_id"]).strip()
            for row in definition_rows
            if row.get("pipeline_name") and row.get("pipeline_id")
        }
        id_by_normalized_name = {
            str(row["pipeline_name"]).strip().casefold(): str(row["pipeline_id"]).strip()
            for row in definition_rows
            if row.get("pipeline_name") and row.get("pipeline_id")
        }
        valid_pipeline_ids = {
            str(row.get("pipeline_id")).strip()
            for row in definition_rows
            if row.get("pipeline_id") is not None and str(row.get("pipeline_id")).strip()
        }
        explicit_pipeline_map = load_adf_pipeline_id_map()
        unmapped_pipeline_definitions = []
        for definition in pipeline_definitions:
            name = definition.get("name")
            if not name:
                continue
            normalized_name = str(name).strip().casefold()
            mapped_id = explicit_pipeline_map.get(normalized_name) or id_by_normalized_name.get(normalized_name)
            if mapped_id is None and str(name).strip() in valid_pipeline_ids:
                mapped_id = str(name).strip()
            if mapped_id and mapped_id in valid_pipeline_ids:
                id_by_name[name] = mapped_id
            else:
                unmapped_pipeline_definitions.append({
                    "pipeline_name": name,
                    "reason": (
                        "No matching existing PIPELINE_ID. Add the correct mapping "
                        "to ADF_PIPELINE_ID_MAP or register the pipeline in "
                        "STG_PIPELINE_DEFINITIONS first."
                    ),
                })

        inserted = {
            "STG_DATASETS": 0,
            "STG_DATASET_OBSERVATIONS": 0,
            "STG_PIPELINE_DEFINITIONS": 0,
            "STG_PIPELINE_RUNS": 0,
            "STG_INCIDENT_HISTORY": 0,
        }

        # Parent IDs were validated from STG_PIPELINE_DEFINITIONS above.
        skipped_pipeline_runs = []
        observation_context_by_day = {}
        skipped_observation_days = []

        runs_by_day = {}
        for run in pipeline_runs:
            run_id = run.get("runId")
            name = run.get("pipelineName")
            if not run_id or not name:
                continue
            pipeline_id = (
                id_by_name.get(name)
                or explicit_pipeline_map.get(str(name).strip().casefold())
                or id_by_normalized_name.get(str(name).strip().casefold())
            )
            if pipeline_id is None or str(pipeline_id).strip() not in valid_pipeline_ids:
                skipped_pipeline_runs.append({
                    "run_id": run_id,
                    "pipeline_name": name,
                    "reason": "No matching PIPELINE_ID exists in STG_PIPELINE_DEFINITIONS",
                })
                app.logger.warning(
                    "Skipping ADF run %s: pipeline '%s' has no valid parent definition",
                    run_id, name,
                )
                continue
            status = str(run.get("status") or "UNKNOWN").upper()

            def parse_azure_timestamp(value):
                if not value:
                    return None
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if parsed.tzinfo:
                    parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
                return parsed

            started = parse_azure_timestamp(run.get("runStart"))
            ended = parse_azure_timestamp(run.get("runEnd"))
            if started is None:
                skipped_pipeline_runs.append({
                    "run_id": run_id,
                    "pipeline_name": name,
                    "reason": "ADF run has no runStart; STARTED_AT is required by Exasol.",
                })
                continue
            duration_ms = run.get("durationInMs")
            duration_seconds = (
                round(float(duration_ms) / 1000)
                if duration_ms is not None else None
            )
            parameters = run.get("parameters") or {}
            requested_scenario_id = str(
                parameters.get("scenarioInstanceId") or ""
            ).strip()
            scenario_id = (
                requested_scenario_id
                if requested_scenario_id in valid_scenario_ids
                else default_scenario_id
            )
            if insert_if_missing(
                "STG_PIPELINE_RUNS",
                "RUN_ID",
                {
                    "RUN_ID": run_id,
                    "PIPELINE_ID": pipeline_id,
                    "SCENARIO_INSTANCE_ID": scenario_id,
                    "STATUS": status,
                    "STARTED_AT": started,
                    "ENDED_AT": ended,
                    "DURATION_SECONDS": duration_seconds,
                    "SCHEMA_VERSION": schema_version,
                },
                {"RUN_ID", "PIPELINE_ID", "STATUS"},
            ):
                inserted["STG_PIPELINE_RUNS"] += 1

            if started:
                day = started.date().isoformat()
                runs_by_day.setdefault(day, []).append(run)
                observation_context_by_day.setdefault(day, []).append({
                    "run_id": run_id,
                    "scenario_id": scenario_id,
                })

            if status in {"FAILED", "CANCELLED"}:
                incident_time = ended or started or now
                if insert_if_missing(
                    "STG_INCIDENT_HISTORY",
                    "INCIDENT_ID",
                    {
                        "INCIDENT_ID": f"ADF_{run_id}",
                        "PIPELINE_ID": pipeline_id,
                        "SCENARIO_INSTANCE_ID": scenario_id,
                        "OCCURRED_AT": incident_time,
                        "INCIDENT_CATEGORY": (
                            "PIPELINE_FAILURE" if status == "FAILED"
                            else "PIPELINE_CANCELLED"
                        ),
                        "RESOLUTION_STATUS": "OPEN",
                        "SCHEMA_VERSION": schema_version,
                    },
                    {
                        "INCIDENT_ID", "PIPELINE_ID", "OCCURRED_AT",
                        "INCIDENT_CATEGORY", "RESOLUTION_STATUS",
                    },
                ):
                    inserted["STG_INCIDENT_HISTORY"] += 1

        # One daily observation per dataset/date/metric. The observation ID
        # is deterministic so retries do not duplicate data.
        for offset in range(days):
            day = start_date + timedelta(days=offset)
            day_text = day.isoformat()
            window_start = datetime.combine(day, datetime.min.time())
            window_end = window_start + timedelta(days=1)
            day_runs = runs_by_day.get(day_text, [])
            total_runs = len(day_runs)
            succeeded = sum(
                str(r.get("status") or "").lower() == "succeeded"
                for r in day_runs
            )
            failed = sum(
                str(r.get("status") or "").lower() == "failed"
                for r in day_runs
            )

            # Observations use a real run ID and valid scenario ID. If there is
            # no registered run on this date, skip instead of inventing an ID
            # that may violate STG_DATASET_OBSERVATIONS foreign keys.
            day_contexts = observation_context_by_day.get(day_text, [])
            if not day_contexts:
                skipped_observation_days.append({
                    "date": day_text,
                    "reason": (
                        "No valid registered ADF run for this date; observation "
                        "was skipped to preserve RUN_ID referential integrity."
                    ),
                })
                continue
            observation_run_id = day_contexts[0]["run_id"]
            observation_scenario_id = day_contexts[0]["scenario_id"]

            metrics = []
            if billing_status == "working" and day_text in daily_costs:
                metrics.append((
                    "DS_AZURE_COST_DAILY",
                    "AZURE_DAILY_COST",
                    float(daily_costs[day_text]),
                    1,
                ))
            metrics.extend([
                ("DS_ADF_USAGE_DAILY", "ADF_PIPELINE_RUN_COUNT", total_runs, total_runs),
                ("DS_ADF_USAGE_DAILY", "ADF_PIPELINE_SUCCEEDED_COUNT", succeeded, total_runs),
                ("DS_ADF_USAGE_DAILY", "ADF_PIPELINE_FAILED_COUNT", failed, total_runs),
            ])

            for dataset_id, metric_name, metric_value, expected in metrics:
                observation_id = (
                    f"{dataset_id}_{day.strftime('%Y%m%d')}_{metric_name}"
                )
                record = {
                    "OBSERVATION_ID": observation_id,
                    "DATASET_ID": dataset_id,
                    "RUN_ID": observation_run_id,
                    "SCENARIO_INSTANCE_ID": observation_scenario_id,
                    "OBSERVED_AT": now,
                    "WINDOW_START": window_start,
                    "WINDOW_END": window_end,
                    "ROW_COUNT": int(metric_value) if metric_name != "AZURE_DAILY_COST" else 1,
                    "EXPECTED_ROW_COUNT": int(expected),
                    "FRESHNESS_LAG_SECONDS": 0,
                    "COMPLETENESS_RATIO": 1.0 if expected else 1.0,
                    "METRIC_NAME": metric_name,
                    "METRIC_VALUE": metric_value,
                    "SCHEMA_VERSION": schema_version,
                }
                if insert_if_missing(
                    "STG_DATASET_OBSERVATIONS",
                    "OBSERVATION_ID",
                    record,
                    {
                        "OBSERVATION_ID", "DATASET_ID", "RUN_ID",
                        "SCENARIO_INSTANCE_ID", "OBSERVED_AT", "WINDOW_START",
                        "WINDOW_END", "ROW_COUNT", "EXPECTED_ROW_COUNT",
                        "FRESHNESS_LAG_SECONDS", "COMPLETENESS_RATIO",
                        "METRIC_NAME", "METRIC_VALUE", "SCHEMA_VERSION",
                    },
                ):
                    inserted["STG_DATASET_OBSERVATIONS"] += 1

        return jsonify({
            "success": True,
            "source": {
                "data_factory": DATA_FACTORY,
                "resource_group": RESOURCE_GROUP,
                "subscription_scope": f"subscription/{SUBSCRIPTION_ID}",
            },
            "destination_schema": schema,
            "period": {"from": start_date.isoformat(), "to": end_date.isoformat(), "days": days},
            "fetched": {
                "pipeline_definitions": len(pipeline_definitions),
                "pipeline_runs": len(pipeline_runs),
                "daily_cost_records": len(daily_costs),
            },
            "billing_status": billing_status,
            "billing_error": billing_error,
            "inserted": inserted,
            "unmapped_pipeline_definitions": unmapped_pipeline_definitions,
            "unmapped_pipeline_definitions_count": len(unmapped_pipeline_definitions),
            "skipped_pipeline_runs": skipped_pipeline_runs,
            "skipped_pipeline_runs_count": len(skipped_pipeline_runs),
            "skipped_observation_days": skipped_observation_days,
            "skipped_observation_days_count": len(skipped_observation_days),
            "note": (
                "Existing IDs are skipped. ADF pipeline names must map to existing "
                "PIPELINE_ID values by matching PIPELINE_NAME/PIPELINE_ID or using "
                "ADF_PIPELINE_ID_MAP in .env. Unmapped pipelines/runs are reported "
                "instead of inserted with invalid foreign keys. Daily observations "
                "require a real registered run on that date; skipped dates are reported. "
                "Cost observations are written only for dates returned by Azure; missing "
                "cost dates are not treated as zero. Azure cost totals are subscription-level "
                "daily totals and are not directly attributed to individual pipeline runs."
            ),
        }), 200

    except requests.RequestException as exc:
        app.logger.exception("Unified Azure-to-Exasol sync failed")
        return jsonify({
            "success": False,
            "error": "Azure API request failed",
            "details": str(exc),
        }), 502
    except Exception as exc:
        app.logger.exception("Unified Azure-to-Exasol sync failed")
        return jsonify({
            "success": False,
            "error": str(exc),
            "error_type": type(exc).__name__,
        }), 500
    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Starting OpsNexus Exasol DataOps Intelligence API")
    print(f"Configuration file: {BASE_DIR / '.env'}")
    print(f"Exasol target: {EXASOL_HOST}:{EXASOL_PORT}")
    print(f"Configured schema: {EXASOL_SCHEMA}")
    print("Password loaded:", "yes" if EXASOL_PASSWORD else "NO - set EXASOL_PASSWORD in .env")
    app.run(
        host=os.getenv("FLASK_HOST", "127.0.0.1"),
        port=int(os.getenv("FLASK_PORT", "5000")),
        debug=False,
    )
