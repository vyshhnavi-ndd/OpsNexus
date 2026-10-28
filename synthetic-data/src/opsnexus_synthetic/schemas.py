"""Versioned tabular contracts exported by Module 1.

Types are descriptive contract names used by the validator and handoff:
string, integer, number, boolean, timestamp_utc, and json.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import SCHEMA_VERSION


@dataclass(frozen=True)
class Field:
    name: str
    kind: str
    nullable: bool = False


@dataclass(frozen=True)
class TableSchema:
    filename: str
    primary_key: str
    fields: tuple[Field, ...]
    schema_version: str = SCHEMA_VERSION


def F(name: str, kind: str, nullable: bool = False) -> Field:
    return Field(name, kind, nullable)


SCHEMAS: dict[str, TableSchema] = {
    "data_sources": TableSchema("data_sources.csv", "source_id", (
        F("source_id", "string"), F("source_name", "string"), F("source_type", "string"),
        F("classification", "string"), F("schema_version", "string"),
    )),
    "pipeline_definitions": TableSchema("pipeline_definitions.csv", "pipeline_id", (
        F("pipeline_id", "string"), F("pipeline_name", "string"), F("source_id", "string"),
        F("schema_version", "string"),
    )),
    "pipeline_runs": TableSchema("pipeline_runs.csv", "run_id", (
        F("run_id", "string"), F("pipeline_id", "string"), F("scenario_instance_id", "string"),
        F("status", "string"), F("started_at", "timestamp_utc"), F("ended_at", "timestamp_utc", True),
        F("duration_seconds", "integer", True), F("schema_version", "string"),
    )),
    "datasets": TableSchema("datasets.csv", "dataset_id", (
        F("dataset_id", "string"), F("dataset_name", "string"), F("domain", "string"),
        F("source_id", "string"), F("schema_version", "string"),
    )),
    "dataset_observations": TableSchema("dataset_observations.csv", "observation_id", (
        F("observation_id", "string"), F("dataset_id", "string"), F("run_id", "string"),
        F("scenario_instance_id", "string"),
        F("observed_at", "timestamp_utc"), F("window_start", "timestamp_utc"),
        F("window_end", "timestamp_utc"), F("row_count", "integer"), F("expected_row_count", "integer"),
        F("freshness_lag_seconds", "integer"), F("completeness_ratio", "number"),
        F("metric_name", "string"), F("metric_value", "number"), F("schema_version", "string"),
    )),
    "quality_checks": TableSchema("quality_checks.csv", "quality_check_id", (
        F("quality_check_id", "string"), F("dataset_id", "string"), F("check_type", "string"),
        F("description", "string"), F("threshold_json", "json"), F("schema_version", "string"),
    )),
    "quality_results": TableSchema("quality_results.csv", "quality_result_id", (
        F("quality_result_id", "string"), F("quality_check_id", "string"),
        F("observation_id", "string"), F("result", "string"), F("measured_value", "number", True),
        F("expected_value", "number", True), F("schema_version", "string"),
    )),
    "dependencies": TableSchema("dependencies.csv", "dependency_id", (
        F("dependency_id", "string"), F("upstream_pipeline_id", "string"),
        F("downstream_pipeline_id", "string"), F("dependency_type", "string"),
        F("schema_version", "string"),
    )),
    "business_kpis": TableSchema("business_kpis.csv", "kpi_id", (
        F("kpi_id", "string"), F("scenario_instance_id", "string"), F("observation_id", "string"),
        F("kpi_name", "string"), F("domain", "string"), F("dataset_id", "string"),
        F("unit", "string"), F("baseline_value", "number"),
        F("observed_value", "number"), F("impact_type", "string"), F("schema_version", "string"),
    )),
    "incident_history": TableSchema("incident_history.csv", "incident_id", (
        F("incident_id", "string"), F("pipeline_id", "string"),
        F("scenario_instance_id", "string"),
        F("occurred_at", "timestamp_utc"), F("incident_category", "string"),
        F("resolution_status", "string"), F("schema_version", "string"),
    )),
    "scenario_metadata": TableSchema("scenario_metadata.csv", "scenario_instance_id", (
        F("scenario_instance_id", "string"), F("scenario_type", "string"), F("description", "string"),
        F("seed", "integer"), F("schema_version", "string"),
    )),
}


def schema_document() -> dict[str, object]:
    """Return JSON-serializable schema metadata for the manifest."""
    return {
        name: {
            "filename": schema.filename,
            "schema_version": schema.schema_version,
            "primary_key": schema.primary_key,
            "fields": [
                {"name": field.name, "type": field.kind, "nullable": field.nullable}
                for field in schema.fields
            ],
        }
        for name, schema in SCHEMAS.items()
    }
