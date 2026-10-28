"""Schema, domain, and referential-integrity validation for exported bundles."""

from __future__ import annotations

import csv
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from . import SCHEMA_VERSION, __version__
from .scenarios import SCENARIO_IDS
from .schemas import SCHEMAS

INTEGER = re.compile(r"^-?\d+$")


def _is_valid(value: str, kind: str) -> bool:
    if kind == "string":
        return True
    if kind == "integer":
        return bool(INTEGER.fullmatch(value))
    if kind == "number":
        try:
            return math.isfinite(float(value))
        except ValueError:
            return False
    if kind == "timestamp_utc":
        if not value.endswith("Z"):
            return False
        try:
            parsed = datetime.fromisoformat(value[:-1] + "+00:00")
            return parsed.utcoffset() is not None and parsed.utcoffset().total_seconds() == 0
        except ValueError:
            return False
    if kind == "json":
        try:
            json.loads(value)
            return True
        except json.JSONDecodeError:
            return False
    if kind == "boolean":
        return value in {"true", "false"}
    return False


def _read_table(root: Path, table_name: str, errors: list[str]) -> list[dict[str, str]]:
    schema = SCHEMAS[table_name]
    path = root / "data" / schema.filename
    if not path.is_file():
        errors.append(f"MISSING_FILE: data/{schema.filename}")
        return []
    try:
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            expected = [field.name for field in schema.fields]
            if reader.fieldnames != expected:
                errors.append(f"INVALID_HEADER: data/{schema.filename}: expected {expected}, got {reader.fieldnames}")
                return []
            rows = list(reader)
    except (UnicodeDecodeError, csv.Error, OSError) as exc:
        errors.append(f"UNREADABLE_FILE: data/{schema.filename}: {exc}")
        return []

    seen: set[str] = set()
    for index, row in enumerate(rows, start=2):
        for field in schema.fields:
            value = row.get(field.name, "")
            if value == "":
                if not field.nullable:
                    errors.append(f"NULL_NOT_ALLOWED: data/{schema.filename}:{index}:{field.name}")
                continue
            if not _is_valid(value, field.kind):
                errors.append(f"INVALID_TYPE: data/{schema.filename}:{index}:{field.name} expected {field.kind}")
        key = row.get(schema.primary_key, "")
        if key and key in seen:
            errors.append(f"DUPLICATE_PRIMARY_KEY: data/{schema.filename}:{index}:{key}")
        seen.add(key)
        if row.get("schema_version") != SCHEMA_VERSION:
            errors.append(f"SCHEMA_VERSION_MISMATCH: data/{schema.filename}:{index}")
    return rows


def _fk(errors: list[str], label: str, value: str, known: set[str]) -> None:
    if value not in known:
        errors.append(f"INVALID_REFERENCE: {label} references unknown id {value!r}")


def validate_bundle(bundle_dir: str | Path, write_report: bool = True) -> dict[str, Any]:
    """Validate an exported bundle and optionally write validation-report.json."""
    root = Path(bundle_dir)
    errors: list[str] = []
    manifest_path = root / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        manifest = {}
        errors.append(f"INVALID_MANIFEST: {exc}")

    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append("INVALID_MANIFEST_SCHEMA_VERSION")
    if not isinstance(manifest.get("seed"), int):
        errors.append("INVALID_MANIFEST_SEED")
    entries = {entry.get("table"): entry for entry in manifest.get("files", []) if isinstance(entry, dict)}
    if set(entries) != set(SCHEMAS):
        errors.append("MANIFEST_TABLE_SET_MISMATCH")

    tables: dict[str, list[dict[str, str]]] = {}
    for table_name, schema in SCHEMAS.items():
        entry = entries.get(table_name, {})
        if entry.get("path") != f"data/{schema.filename}" or entry.get("schema_version") != schema.schema_version:
            errors.append(f"INVALID_MANIFEST_ENTRY: {table_name}")
        rows = _read_table(root, table_name, errors)
        tables[table_name] = rows
        if entry and entry.get("row_count") != len(rows):
            errors.append(f"ROW_COUNT_MISMATCH: {table_name}: manifest={entry.get('row_count')} actual={len(rows)}")

    pipeline_ids = {r["pipeline_id"] for r in tables["pipeline_definitions"]}
    source_ids = {r["source_id"] for r in tables["data_sources"]}
    dataset_ids = {r["dataset_id"] for r in tables["datasets"]}
    run_by_id = {r["run_id"]: r for r in tables["pipeline_runs"]}
    observation_by_id = {r["observation_id"]: r for r in tables["dataset_observations"]}
    check_by_id = {r["quality_check_id"]: r for r in tables["quality_checks"]}
    scenario_instance_by_id = {r["scenario_instance_id"]: r for r in tables["scenario_metadata"]}
    scenario_instance_ids = set(scenario_instance_by_id)
    if len(scenario_instance_ids) != len(SCENARIO_IDS):
        errors.append("SCENARIO_SET_MISMATCH")
    if sorted(manifest.get("scenario_instance_ids", [])) != sorted(scenario_instance_ids):
        errors.append("MANIFEST_SCENARIO_SET_MISMATCH")
    if manifest.get("scenario_count") != len(scenario_instance_ids):
        errors.append("MANIFEST_SCENARIO_COUNT_MISMATCH")

    for row in tables["data_sources"]:
        if row["source_type"] != "SYNTHETIC" or row["classification"] != "SYNTHETIC_DEMO":
            errors.append(f"INVALID_SOURCE_CLASSIFICATION: {row['source_id']}")
    for row in tables["pipeline_definitions"]:
        _fk(errors, "pipeline_definitions.source_id", row["source_id"], source_ids)
    for row in tables["datasets"]:
        _fk(errors, "datasets.source_id", row["source_id"], source_ids)

    for row in tables["pipeline_runs"]:
        _fk(errors, "pipeline_runs.pipeline_id", row["pipeline_id"], pipeline_ids)
        _fk(errors, "pipeline_runs.scenario_instance_id", row["scenario_instance_id"], scenario_instance_ids)
        if row["status"] not in {"SUCCEEDED", "FAILED", "SKIPPED"}:
            errors.append(f"INVALID_RUN_STATUS: {row['run_id']}={row['status']}")
        if row["ended_at"] and row["ended_at"] < row["started_at"]:
            errors.append(f"INVALID_RUN_TIME_ORDER: {row['run_id']}")
        if row["duration_seconds"] and int(row["duration_seconds"]) < 0:
            errors.append(f"NEGATIVE_RUN_DURATION: {row['run_id']}")

    for row in tables["dataset_observations"]:
        _fk(errors, "dataset_observations.dataset_id", row["dataset_id"], dataset_ids)
        _fk(errors, "dataset_observations.scenario_instance_id", row["scenario_instance_id"], scenario_instance_ids)
        run = run_by_id.get(row["run_id"])
        if run is None:
            errors.append(f"INVALID_REFERENCE: dataset_observations.run_id={row['run_id']!r}")
        elif run["scenario_instance_id"] != row["scenario_instance_id"] or run["status"] != "SUCCEEDED":
            errors.append(f"OBSERVATION_RUN_MISMATCH: {row['observation_id']}")
        if int(row["row_count"]) < 0 or int(row["expected_row_count"]) < 0 or int(row["freshness_lag_seconds"]) < 0:
            errors.append(f"NEGATIVE_MEASUREMENT: {row['observation_id']}")
        expected = int(row["expected_row_count"])
        count = int(row["row_count"])
        if (expected == 0 and float(row["completeness_ratio"]) != 0) or (expected > 0 and abs(float(row["completeness_ratio"]) - count / expected) > 0.0001):
            errors.append(f"COMPLETENESS_MISMATCH: {row['observation_id']}")
        ratio = float(row["completeness_ratio"])
        if not 0 <= ratio <= 1:
            errors.append(f"INVALID_COMPLETENESS_RATIO: {row['observation_id']}")
        if row["window_end"] < row["window_start"]:
            errors.append(f"INVALID_OBSERVATION_WINDOW: {row['observation_id']}")

    for row in tables["quality_checks"]:
        _fk(errors, "quality_checks.dataset_id", row["dataset_id"], dataset_ids)
        if row["check_type"] not in {"freshness", "completeness", "metric_range"}:
            errors.append(f"INVALID_CHECK_TYPE: {row['quality_check_id']}")
    for row in tables["quality_results"]:
        check = check_by_id.get(row["quality_check_id"])
        observation = observation_by_id.get(row["observation_id"])
        if check is None:
            errors.append(f"INVALID_REFERENCE: quality_results.quality_check_id={row['quality_check_id']!r}")
        if observation is None:
            errors.append(f"INVALID_REFERENCE: quality_results.observation_id={row['observation_id']!r}")
        if check and observation and check["dataset_id"] != observation["dataset_id"]:
            errors.append(f"QUALITY_DATASET_MISMATCH: {row['quality_result_id']}")
        if row["result"] not in {"PASS", "FAIL"}:
            errors.append(f"INVALID_QUALITY_RESULT: {row['quality_result_id']}")
        if check and observation and check["check_type"] in {"freshness", "completeness", "metric_range"}:
            threshold = json.loads(check["threshold_json"])
            measured = float(row["measured_value"])
            expected_value = float(row["expected_value"])
            if check["check_type"] == "freshness":
                source_value = float(observation["freshness_lag_seconds"])
                limit = float(threshold["max_lag_seconds"])
                passed = source_value <= limit
            elif check["check_type"] == "completeness":
                source_value = float(observation["completeness_ratio"])
                limit = float(threshold["min_ratio"])
                passed = source_value >= limit
            else:
                baseline = float(threshold["baseline"])
                source_value = abs(float(observation["metric_value"]) - baseline) / baseline
                limit = float(threshold["max_relative_deviation"])
                passed = source_value <= limit
            if abs(measured - source_value) > 0.001 or abs(expected_value - limit) > 0.0001:
                errors.append(f"QUALITY_MEASUREMENT_MISMATCH: {row['quality_result_id']}")
            if row["result"] != ("PASS" if passed else "FAIL"):
                errors.append(f"QUALITY_RESULT_MISMATCH: {row['quality_result_id']}")
    results_by_observation = {
        observation_id: {row["quality_check_id"] for row in tables["quality_results"] if row["observation_id"] == observation_id}
        for observation_id in observation_by_id
    }
    checks_by_dataset: dict[str, set[str]] = {}
    for check in tables["quality_checks"]:
        checks_by_dataset.setdefault(check["dataset_id"], set()).add(check["quality_check_id"])
    for observation in tables["dataset_observations"]:
        if results_by_observation.get(observation["observation_id"], set()) != checks_by_dataset.get(observation["dataset_id"], set()):
            errors.append(f"QUALITY_RESULT_COVERAGE_MISMATCH: {observation['observation_id']}")

    for row in tables["dependencies"]:
        _fk(errors, "dependencies.upstream_pipeline_id", row["upstream_pipeline_id"], pipeline_ids)
        _fk(errors, "dependencies.downstream_pipeline_id", row["downstream_pipeline_id"], pipeline_ids)
        if row["upstream_pipeline_id"] == row["downstream_pipeline_id"]:
            errors.append(f"SELF_DEPENDENCY: {row['dependency_id']}")
        if row["dependency_type"] != "REQUIRED":
            errors.append(f"INVALID_DEPENDENCY_TYPE: {row['dependency_id']}")
    for row in tables["business_kpis"]:
        _fk(errors, "business_kpis.dataset_id", row["dataset_id"], dataset_ids)
        _fk(errors, "business_kpis.scenario_instance_id", row["scenario_instance_id"], scenario_instance_ids)
        observation = observation_by_id.get(row["observation_id"])
        if observation is None or observation["dataset_id"] != row["dataset_id"] or observation["scenario_instance_id"] != row["scenario_instance_id"]:
            errors.append(f"KPI_OBSERVATION_MISMATCH: {row['kpi_id']}")
        elif abs(float(row["observed_value"]) - float(observation["metric_value"])) > 0.0001:
            errors.append(f"KPI_VALUE_MISMATCH: {row['kpi_id']}")
        if row["impact_type"] != "ILLUSTRATIVE_SYNTHETIC":
            errors.append(f"INVALID_KPI_IMPACT_TYPE: {row['kpi_id']}")
    for row in tables["incident_history"]:
        _fk(errors, "incident_history.pipeline_id", row["pipeline_id"], pipeline_ids)
        _fk(errors, "incident_history.scenario_instance_id", row["scenario_instance_id"], scenario_instance_ids)
    for row in tables["scenario_metadata"]:
        if row["scenario_type"] != "SYNTHETIC_DEMO":
            errors.append(f"INVALID_SCENARIO_METADATA_TYPE: {row['scenario_instance_id']}")

    truth_entry = manifest.get("ground_truth", {})
    if truth_entry.get("ingest") is not False or truth_entry.get("path") != "ground_truth/expected_outcomes.json":
        errors.append("GROUND_TRUTH_MUST_BE_SEPARATE_AND_NON_INGEST")
    else:
        try:
            truth = json.loads((root / truth_entry["path"]).read_text(encoding="utf-8"))
            truth_scenarios = truth.get("scenarios", {})
            if set(truth_scenarios) != set(SCENARIO_IDS):
                errors.append("GROUND_TRUTH_SCENARIO_SET_MISMATCH")
            truth_instance_ids = [row.get("scenario_instance_id") for row in truth_scenarios.values()]
            if set(truth_instance_ids) != scenario_instance_ids or len(truth_instance_ids) != len(set(truth_instance_ids)):
                errors.append("GROUND_TRUTH_SCENARIO_REFERENCE_MISMATCH")
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"INVALID_GROUND_TRUTH: {exc}")

    # Scenario labels belong only in the separate truth document, never in manifest or operational tables.
    operational_text = json.dumps(manifest, sort_keys=True).casefold()
    for rows in tables.values():
        operational_text += "\n" + json.dumps(rows, sort_keys=True).casefold()
    if any(label.casefold() in operational_text for label in SCENARIO_IDS):
        errors.append("GROUND_TRUTH_LABEL_LEAKAGE")

    report: dict[str, Any] = {
        "report_version": "1.0.0", "validator_version": __version__,
        "schema_version": SCHEMA_VERSION, "seed": manifest.get("seed"),
        "valid": not errors, "error_count": len(errors), "errors": errors,
        "checked_row_counts": {name: len(rows) for name, rows in tables.items()},
        "scenario_instance_ids": sorted(scenario_instance_ids),
    }
    if write_report:
        (root / "validation-report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
        )
    return report
