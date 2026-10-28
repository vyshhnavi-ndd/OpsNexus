"""Stable CSV/JSON bundle export for the Module 1 handoff."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from . import __version__, SCHEMA_VERSION
from .generator import ANCHOR, generate
from .schemas import SCHEMAS, schema_document


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def export_bundle(output_dir: str | Path, seed: int = 20261014) -> dict[str, object]:
    """Write all tables, separate ground truth, and a deterministic manifest."""
    root = Path(output_dir)
    tables, ground_truth = generate(seed)
    scenario_instance_ids = sorted(row["scenario_instance_id"] for row in tables["scenario_metadata"])
    file_entries: list[dict[str, object]] = []
    for table_name, schema in SCHEMAS.items():
        relpath = Path("data") / schema.filename
        path = root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        fields = [field.name for field in schema.fields]
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="raise", lineterminator="\n")
            writer.writeheader()
            for row in tables[table_name]:
                writer.writerow({key: _csv_value(value) for key, value in row.items()})
        file_entries.append({
            "table": table_name, "path": relpath.as_posix(), "format": "csv",
            "schema_version": schema.schema_version, "row_count": len(tables[table_name]),
            "scenario_instance_ids": scenario_instance_ids,
        })

    truth_path = Path("ground_truth") / "expected_outcomes.json"
    _write_json(root / truth_path, ground_truth)
    manifest: dict[str, object] = {
        "manifest_version": "1.0.0", "generator_version": __version__,
        "schema_version": SCHEMA_VERSION, "seed": seed,
        "bundle_id": f"opsnexus-synthetic-v{__version__}-schema-{SCHEMA_VERSION}-seed-{seed}",
        "generated_at": ANCHOR.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "timestamp_convention": "ISO-8601 UTC; Z suffix; second precision",
        "data_classification": "SYNTHETIC_DEMO_DATA_NOT_LIVE_OPERATIONAL_DATA",
        "scenario_instance_ids": scenario_instance_ids, "scenario_count": len(scenario_instance_ids),
        "files": file_entries,
        "schemas": schema_document(),
        "ground_truth": {
            "path": truth_path.as_posix(), "format": "json", "ingest": False,
            "classification": "SYNTHETIC_GROUND_TRUTH_NOT_OPERATIONAL_EVIDENCE",
        },
    }
    _write_json(root / "manifest.json", manifest)
    return manifest
