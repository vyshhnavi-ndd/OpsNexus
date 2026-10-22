"""Deterministic synthetic operational data generator."""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from . import __version__, SCHEMA_VERSION
from .scenarios import EXPECTED_OUTCOMES, SCENARIO_CATALOGUE

ANCHOR = datetime(2026, 10, 14, 8, 0, tzinfo=timezone.utc)
PIPELINES = [
    {"pipeline_id": "pl_orders_ingest", "pipeline_name": "Orders ingestion", "source_id": "src_synthetic_erp", "schema_version": SCHEMA_VERSION},
    {"pipeline_id": "pl_finance_ingest", "pipeline_name": "Finance ingestion", "source_id": "src_synthetic_ledger", "schema_version": SCHEMA_VERSION},
    {"pipeline_id": "pl_warehouse_refresh", "pipeline_name": "Warehouse refresh", "source_id": "src_synthetic_warehouse", "schema_version": SCHEMA_VERSION},
]
DATASETS = [
    {"dataset_id": "ds_orders", "dataset_name": "orders_daily", "domain": "commerce", "source_id": "src_synthetic_erp", "schema_version": SCHEMA_VERSION},
    {"dataset_id": "ds_inventory", "dataset_name": "inventory_daily", "domain": "supply", "source_id": "src_synthetic_erp", "schema_version": SCHEMA_VERSION},
    {"dataset_id": "ds_finance", "dataset_name": "finance_daily", "domain": "finance", "source_id": "src_synthetic_ledger", "schema_version": SCHEMA_VERSION},
]


def _stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _scenario_instance_ids(seed: int) -> dict[str, str]:
    """Assign opaque deterministic case tokens without putting labels in evidence."""
    id_rng = random.Random(f"opsnexus-opaque-cases:{SCHEMA_VERSION}:{seed}")
    return {
        row["scenario_id"]: f"case_{id_rng.getrandbits(96):024x}"
        for row in SCENARIO_CATALOGUE
    }


def generate(seed: int = 20261014) -> tuple[dict[str, list[dict[str, object]]], dict[str, object]]:
    """Generate normalized operational tables and a separate ground-truth payload."""
    rng = random.Random(seed)
    bundle_id = f"opsnexus-synthetic-v{__version__}-schema-{SCHEMA_VERSION}-seed-{seed}"
    instance_ids = _scenario_instance_ids(seed)
    tables: dict[str, list[dict[str, object]]] = {
        name: [] for name in (
            "pipeline_definitions", "pipeline_runs", "datasets", "dataset_observations",
            "quality_checks", "quality_results", "dependencies", "business_kpis",
            "incident_history", "scenario_metadata",
        )
    }
    tables["data_sources"] = [
        {"source_id": "src_synthetic_erp", "source_name": "Synthetic ERP", "source_type": "SYNTHETIC", "classification": "SYNTHETIC_DEMO", "schema_version": SCHEMA_VERSION},
        {"source_id": "src_synthetic_ledger", "source_name": "Synthetic Ledger", "source_type": "SYNTHETIC", "classification": "SYNTHETIC_DEMO", "schema_version": SCHEMA_VERSION},
        {"source_id": "src_synthetic_warehouse", "source_name": "Synthetic Warehouse", "source_type": "SYNTHETIC", "classification": "SYNTHETIC_DEMO", "schema_version": SCHEMA_VERSION},
    ]
    tables["pipeline_definitions"] = [dict(row) for row in PIPELINES]
    tables["datasets"] = [dict(row) for row in DATASETS]
    tables["dependencies"] = [
        {"dependency_id": "dep_orders_warehouse", "upstream_pipeline_id": "pl_orders_ingest", "downstream_pipeline_id": "pl_warehouse_refresh", "dependency_type": "REQUIRED", "schema_version": SCHEMA_VERSION},
        {"dependency_id": "dep_finance_warehouse", "upstream_pipeline_id": "pl_finance_ingest", "downstream_pipeline_id": "pl_warehouse_refresh", "dependency_type": "REQUIRED", "schema_version": SCHEMA_VERSION},
    ]
    check_specs = (
        ("freshness", "Maximum freshness lag in seconds", {"max_lag_seconds": 3600}),
        ("completeness", "Minimum expected row completeness", {"min_ratio": 0.95}),
        ("metric_range", "Maximum relative metric deviation from 100", {"baseline": 100, "max_relative_deviation": 0.2}),
    )
    for dataset in DATASETS:
        for check_type, description, threshold in check_specs:
            tables["quality_checks"].append({
                "quality_check_id": f"qc_{dataset['dataset_id']}_{check_type}",
                "dataset_id": dataset["dataset_id"], "check_type": check_type,
                "description": description, "threshold_json": threshold,
                "schema_version": SCHEMA_VERSION,
            })
    kpi_specs = {
        "ds_orders": ("daily_orders", "commerce", "orders"),
        "ds_inventory": ("stock_coverage", "supply", "percent"),
        "ds_finance": ("recognized_revenue", "finance", "USD_illustrative"),
    }

    truth: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "data_classification": "SYNTHETIC_GROUND_TRUTH_NOT_OPERATIONAL_EVIDENCE",
        "scenarios": {},
    }
    scenario_truth: dict[str, object] = truth["scenarios"]  # type: ignore[assignment]
    pipeline_for_dataset = {"ds_orders": "pl_orders_ingest", "ds_inventory": "pl_orders_ingest", "ds_finance": "pl_finance_ingest"}
    for scenario in SCENARIO_CATALOGUE:
        scenario_id = scenario["scenario_id"]
        scenario_type = scenario["scenario_type"]
        scenario_instance_id = instance_ids[scenario_id]
        tables["scenario_metadata"].append({
            "scenario_instance_id": scenario_instance_id,
            "scenario_type": "SYNTHETIC_DEMO",
            "description": "Deterministic generated demonstration records.",
            "seed": seed, "schema_version": SCHEMA_VERSION,
        })
        start = ANCHOR + timedelta(seconds=rng.randrange(0, 300))
        target_dataset_ids = ["ds_orders", "ds_inventory", "ds_finance"]
        if scenario_id == "pipeline_failure":
            status_by_pipeline = {"pl_orders_ingest": "FAILED", "pl_finance_ingest": "SUCCEEDED", "pl_warehouse_refresh": "SKIPPED"}
        else:
            status_by_pipeline = {pipeline["pipeline_id"]: "SUCCEEDED" for pipeline in PIPELINES}
        run_by_pipeline: dict[str, str] = {}
        for pipeline in PIPELINES:
            pipeline_id = pipeline["pipeline_id"]
            run_id = f"run_{bundle_id}_{scenario_instance_id}_{pipeline_id}"
            run_by_pipeline[pipeline_id] = run_id
            status = status_by_pipeline[pipeline_id]
            ended = _stamp(start + timedelta(seconds=120))
            tables["pipeline_runs"].append({
                "run_id": run_id, "pipeline_id": pipeline_id,
                "scenario_instance_id": scenario_instance_id,
                "status": status, "started_at": _stamp(start), "ended_at": ended,
                "duration_seconds": 120,
                "schema_version": SCHEMA_VERSION,
            })

        for dataset_id in target_dataset_ids:
            pipeline_id = pipeline_for_dataset[dataset_id]
            if status_by_pipeline[pipeline_id] != "SUCCEEDED":
                continue
            lag = 300
            row_count = 1000 + rng.randrange(0, 30)
            expected_count = row_count
            metric = 100.0 + rng.uniform(-5, 5)
            if scenario_id == "stale_data" and dataset_id == "ds_orders":
                lag = 10800
            elif scenario_id == "incomplete_data" and dataset_id == "ds_orders":
                expected_count = 1000
                row_count = 800
            elif scenario_id == "metric_anomaly" and dataset_id == "ds_orders":
                metric = 150.0
            elif scenario_id == "cross_domain_inconsistency":
                metric = 100.0 if dataset_id in {"ds_orders", "ds_inventory"} else 82.0
            elif scenario_id == "recurring_incident" and dataset_id == "ds_orders":
                lag = 7200
            elif scenario_id == "inconclusive":
                if dataset_id == "ds_orders":
                    lag = 7200
                if dataset_id == "ds_finance":
                    row_count = 850
                    expected_count = 1000

            observation_id = f"obs_{bundle_id}_{scenario_instance_id}_{dataset_id}"
            window_end = start
            observed_at = start + timedelta(seconds=120)
            tables["dataset_observations"].append({
                "observation_id": observation_id, "dataset_id": dataset_id,
                "run_id": run_by_pipeline[pipeline_id],
                "scenario_instance_id": scenario_instance_id,
                "observed_at": _stamp(observed_at), "window_start": _stamp(window_end - timedelta(days=1)),
                "window_end": _stamp(window_end), "row_count": row_count,
                "expected_row_count": expected_count, "freshness_lag_seconds": lag,
                "completeness_ratio": round(row_count / expected_count, 4),
                "metric_name": "daily_value_index", "metric_value": round(metric, 2),
                "schema_version": SCHEMA_VERSION,
            })
            kpi_name, domain, unit = kpi_specs[dataset_id]
            tables["business_kpis"].append({
                "kpi_id": f"kpi_{bundle_id}_{scenario_instance_id}_{kpi_name}",
                "scenario_instance_id": scenario_instance_id,
                "observation_id": observation_id, "kpi_name": kpi_name, "domain": domain,
                "dataset_id": dataset_id, "unit": unit, "baseline_value": 100.0,
                "observed_value": round(metric, 2), "impact_type": "ILLUSTRATIVE_SYNTHETIC",
                "schema_version": SCHEMA_VERSION,
            })
            for check in (c for c in tables["quality_checks"] if c["dataset_id"] == dataset_id):
                check_type = check["check_type"]
                if check_type == "freshness":
                    measured, expected = float(lag), 3600.0
                    passed = lag <= 3600
                elif check_type == "completeness":
                    measured, expected = row_count / expected_count, 0.95
                    passed = measured >= 0.95
                else:
                    measured, expected = abs(metric - 100.0) / 100.0, 0.2
                    passed = measured <= 0.2
                tables["quality_results"].append({
                    "quality_result_id": f"qr_{bundle_id}_{scenario_instance_id}_{dataset_id}_{check_type}",
                    "quality_check_id": check["quality_check_id"], "observation_id": observation_id,
                    "result": "PASS" if passed else "FAIL", "measured_value": round(measured, 4),
                    "expected_value": expected, "schema_version": SCHEMA_VERSION,
                })

        if scenario_id == "recurring_incident":
            tables["incident_history"].append({
                "incident_id": f"inc_{bundle_id}_{scenario_instance_id}_prior_001", "pipeline_id": "pl_orders_ingest",
                "scenario_instance_id": scenario_instance_id,
                "occurred_at": _stamp(start - timedelta(days=7)),
                "incident_category": "FRESHNESS_DELAY", "resolution_status": "CLOSED",
                "schema_version": SCHEMA_VERSION,
            })

        expected = dict(EXPECTED_OUTCOMES[scenario_id])
        expected["scenario_type"] = scenario_type
        expected["scenario_instance_id"] = scenario_instance_id
        expected["evidence_run_ids"] = list(run_by_pipeline.values())
        scenario_truth[scenario_id] = expected

    return tables, truth
