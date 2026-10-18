"""Evaluate OPS_INTEL.V_FINDINGS against the offline synthetic labels.

Ground truth is read only in this client-side evaluator. The production SQL
view does not access this file or create evaluation tables.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_GROUND_TRUTH = (
    ROOT / "synthetic-data" / "examples" / "seed-20261014" / "ground_truth" / "expected_outcomes.json"
)
CAUSE_TO_FINDING = {
    "UPSTREAM_PIPELINE_FAILURE": "PIPELINE_FAILURE",
    "STALE_DATA": "STALE_DATASET",
    "INCOMPLETE_DATA": "INCOMPLETE_DATA",
    "METRIC_ANOMALY": "KPI_ANOMALY",
    "CROSS_DOMAIN_INCONSISTENCY": "CROSS_DOMAIN_INCONSISTENCY",
    "RECURRING_PATTERN": "INCIDENT_RECURRENCE",
}
FINDINGS_SQL = (
    "SELECT FINDING_ID, SCENARIO_INSTANCE_ID, FINDING_TYPE, SEVERITY "
    "FROM OPS_INTEL.V_FINDINGS ORDER BY FINDING_ID"
)


def _scenario_rows(findings: list[dict[str, Any]], truth: dict[str, Any]) -> list[dict[str, Any]]:
    by_instance: dict[str, set[str]] = defaultdict(set)
    for finding in findings:
        instance_id = finding.get("SCENARIO_INSTANCE_ID")
        if instance_id:
            by_instance[str(instance_id)].add(str(finding["FINDING_TYPE"]).upper())

    rows = []
    for scenario_name, expected in sorted(truth["scenarios"].items()):
        instance_id = expected["scenario_instance_id"]
        actual = sorted(by_instance.get(instance_id, set()))
        target = CAUSE_TO_FINDING.get(expected.get("expected_cause_category"))
        disposition = expected.get("expected_investigation_disposition")
        if disposition == "INCONCLUSIVE":
            status = "UNLABELED_INCONCLUSIVE"
        elif target is None:
            status = "PASS_NO_FINDINGS" if not actual else "FALSE_POSITIVE"
        else:
            status = "MATCH" if target in actual else "MISSING_EXPECTED_FINDING"
        rows.append({
            "scenario": scenario_name,
            "expected_cause": expected.get("expected_cause_category"),
            "target_finding": target,
            "actual_findings": actual,
            "status": status,
            "rationale": expected.get("rationale", ""),
        })
    return rows


def evaluate_results(findings: list[dict[str, Any]], truth: dict[str, Any]) -> dict[str, Any]:
    """Return scenario coverage and per-rule confusion metrics.

    Only healthy_baseline is an explicit negative label. Other non-target
    scenarios are not treated as negatives; the inconclusive case is excluded.
    """
    scenarios = _scenario_rows(findings, truth)
    finding_by_instance: dict[str, set[str]] = defaultdict(set)
    for finding in findings:
        if finding.get("SCENARIO_INSTANCE_ID"):
            finding_by_instance[str(finding["SCENARIO_INSTANCE_ID"])].add(
                str(finding["FINDING_TYPE"]).upper()
            )

    metrics: dict[str, dict[str, Any]] = {}
    for cause, finding_type in CAUSE_TO_FINDING.items():
        positives = [
            record for record in truth["scenarios"].values()
            if record.get("expected_cause_category") == cause
        ]
        tp = sum(finding_type in finding_by_instance[str(record["scenario_instance_id"])] for record in positives)
        fn = len(positives) - tp
        explicit_negatives = [
            record for record in truth["scenarios"].values()
            if record.get("expected_investigation_disposition") == "HEALTHY_NO_ACTION"
        ]
        fp = sum(finding_type in finding_by_instance[str(record["scenario_instance_id"])] for record in explicit_negatives)
        tn = len(explicit_negatives) - fp
        metrics[finding_type] = {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
            "precision": round(tp / (tp + fp), 4) if tp + fp else None,
            "recall": round(tp / (tp + fn), 4) if tp + fn else None,
            "labeled_positive_scenarios": len(positives),
            "explicit_negative_scenarios": len(explicit_negatives),
        }
    return {"scenarios": scenarios, "rule_metrics": metrics}


def _query_live_view(launcher: str, deployment_dir: Path) -> list[dict[str, Any]]:
    result = subprocess.run(
        [launcher, "connect", "--json", "-c", FINDINGS_SQL],
        cwd=deployment_dir,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Exasol query failed")
    payload = json.loads(result.stdout)
    statement = next(
        (item for item in payload.get("statements", []) if item.get("statementType") == "SELECT"),
        None,
    )
    if statement is None:
        raise RuntimeError("Exasol launcher returned no SELECT result for V_FINDINGS")
    columns = statement["columns"]
    findings = [dict(zip(columns, row)) for row in statement["rows"]]
    identifiers = [str(finding["FINDING_ID"]) for finding in findings]
    if len(identifiers) != len(set(identifiers)):
        raise RuntimeError("OPS_INTEL.V_FINDINGS returned duplicate FINDING_ID values")
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--launcher",
        default=os.environ.get("EXASOL_LAUNCHER") or shutil.which("exasol"),
        help="path to the Exasol Launcher executable (or set EXASOL_LAUNCHER)",
    )
    parser.add_argument(
        "--deployment-dir",
        type=Path,
        default=Path(os.environ.get("USERPROFILE", str(Path.home())))
        / ".exasol" / "personal" / "deployments" / "default",
    )
    parser.add_argument("--ground-truth", type=Path, default=DEFAULT_GROUND_TRUTH)
    parser.add_argument("--repeats", type=int, default=2, help="number of live-view reads to compare for stability")
    args = parser.parse_args(argv)
    if not args.launcher:
        parser.error("provide --launcher or set EXASOL_LAUNCHER")
    if args.repeats < 1:
        parser.error("--repeats must be at least 1")

    truth = json.loads(args.ground_truth.read_text(encoding="utf-8"))
    findings = _query_live_view(args.launcher, args.deployment_dir)
    for _ in range(args.repeats - 1):
        repeated = _query_live_view(args.launcher, args.deployment_dir)
        if repeated != findings:
            raise RuntimeError("OPS_INTEL.V_FINDINGS changed between repeated reads")
    result = evaluate_results(findings, truth)
    print("Scenario evaluation (ground truth is offline-only):")
    for row in result["scenarios"]:
        target = row["target_finding"] or "none"
        actual = ",".join(row["actual_findings"]) or "none"
        print(f"{row['scenario']}: {row['status']}; target={target}; actual={actual}")
        if row["status"] == "MISSING_EXPECTED_FINDING":
            print(f"  mismatch: expected evidence was labeled as {row['expected_cause']}; {row['rationale']}")
        elif row["status"] == "FALSE_POSITIVE":
            print(f"  mismatch: explicit healthy/no-action label; {row['rationale']}")
        elif row["status"] == "UNLABELED_INCONCLUSIVE" and row["actual_findings"]:
            print("  interpretation: operational rule evidence is present, but this cause label is inconclusive and is excluded from scoring.")
        elif row["target_finding"]:
            extras = [kind for kind in row["actual_findings"] if kind != row["target_finding"]]
            if extras:
                print("  interpretation: additional evidence-backed rule signals; ground truth labels a target cause, not an exhaustive finding set, so these are not scored as false positives.")
    print("\nPer-rule metrics (only explicitly labeled negatives are counted):")
    for finding_type, values in result["rule_metrics"].items():
        print(
            f"{finding_type}: TP={values['tp']} FP={values['fp']} "
            f"FN={values['fn']} TN={values['tn']} "
            f"precision={values['precision']} recall={values['recall']}"
        )
    unlabeled = [row for row in result["scenarios"] if row["status"] == "UNLABELED_INCONCLUSIVE"]
    if unlabeled:
        print("\nInconclusive scenarios are shown but excluded from precision/recall.")
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for finding in findings:
        counts[(str(finding["FINDING_TYPE"]), str(finding["SEVERITY"]))] += 1
    print("\nLive finding counts by type/severity:")
    for (finding_type, severity), count in sorted(counts.items()):
        print(f"{finding_type}/{severity}: {count}")
    print(f"Repeated view reads compared: {args.repeats}")
    print(f"\nLive view findings evaluated: {len(findings)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
