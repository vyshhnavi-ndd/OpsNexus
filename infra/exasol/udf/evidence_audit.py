"""Deterministic, non-causal audit of one OPS_INTEL finding's evidence."""

import json
import re
from decimal import Decimal, InvalidOperation


_FIELD_START = re.compile(r"(?:^|;\s*)([A-Za-z][A-Za-z0-9_]*)\s*=")
_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_REFERENCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
_NUMBER = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")

_EVIDENCE_FIELDS = {
    "PIPELINE_FAILURE": ("run_id", "measured_status", "expected_status"),
    "STALE_DATASET": (
        "observation_id", "run_id", "measured_freshness_lag_seconds",
        "expected_max_lag_seconds", "quality_result",
    ),
    "INCOMPLETE_DATA": (
        "observation_id", "run_id", "measured_row_count", "expected_row_count",
        "measured_completeness_ratio", "configured_min_ratio",
    ),
    "QUALITY_FAILURE": ("quality_result_id", "observation_id", "run_id", "check_type"),
    "KPI_ANOMALY": (
        "kpi_id", "observation_id", "dataset_id", "measured_relative_deviation",
        "baseline_value", "observed_value", "configured_max_relative_deviation",
    ),
    "CROSS_DOMAIN_INCONSISTENCY": (
        "metric", "dataset_1", "dataset_2", "measured_relative_gap",
        "proposed_max_relative_gap",
    ),
    "INCIDENT_RECURRENCE": ("incident_category",),
}

_REFERENCE_COUNTS = {
    "PIPELINE_FAILURE": {"run_id": 1},
    "STALE_DATASET": {"observation_id": 1, "quality_result_id": 1},
    "INCOMPLETE_DATA": {"observation_id": 1, "quality_result_id": 1},
    "QUALITY_FAILURE": {"quality_result_id": 1, "quality_check_id": 1, "observation_id": 1},
    "KPI_ANOMALY": {"kpi_id": 1, "observation_id": 1, "quality_result_id": 1},
    "CROSS_DOMAIN_INCONSISTENCY": {
        "observation_id": 2, "run_id": 2, "kpi_id": 2, "dependency_id": 2,
    },
}

_EVIDENCE_REFERENCE_KEYS = {
    "PIPELINE_FAILURE": ("run_id",),
    "STALE_DATASET": ("observation_id", "run_id"),
    "INCOMPLETE_DATA": ("observation_id", "run_id"),
    "QUALITY_FAILURE": ("quality_result_id", "quality_check_id", "observation_id", "run_id"),
    "KPI_ANOMALY": ("kpi_id", "observation_id", "dataset_id"),
    "CROSS_DOMAIN_INCONSISTENCY": ("dataset_1", "dataset_2"),
    "INCIDENT_RECURRENCE": ("prior_incident_ids",),
}

_NUMERIC_EVIDENCE_FIELDS = {
    "STALE_DATASET": ("measured_freshness_lag_seconds", "expected_max_lag_seconds"),
    "INCOMPLETE_DATA": (
        "measured_row_count", "expected_row_count", "measured_completeness_ratio",
        "configured_min_ratio",
    ),
    "KPI_ANOMALY": (
        "measured_relative_deviation", "baseline_value", "observed_value",
        "configured_max_relative_deviation",
    ),
    "CROSS_DOMAIN_INCONSISTENCY": ("measured_relative_gap", "proposed_max_relative_gap"),
}

_NUMERIC_REQUIRED = {
    "STALE_DATASET", "INCOMPLETE_DATA", "KPI_ANOMALY",
    "CROSS_DOMAIN_INCONSISTENCY", "INCIDENT_RECURRENCE",
}
_SUPPORTED_FINDINGS = frozenset(_EVIDENCE_FIELDS)
_OPTIONAL_REFERENCE_KEYS = frozenset({"upstream_runs", "dependent_runs"})


def _parse_fields(value, allow_nested_semicolon_key=None):
    """Parse key=value fields separated by semicolons; retain repeated keys."""
    if not isinstance(value, str) or not value.strip():
        return {}, "MISSING"

    text = value.strip()
    matches = list(_FIELD_START.finditer(text))
    if not matches or text[:matches[0].start()].strip():
        return {}, "INVALID"

    fields = {}
    status = "VALID"
    for index, match in enumerate(matches):
        key = match.group(1).lower()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        raw = text[match.end():end].strip()
        if raw.endswith(";"):
            raw = raw[:-1].strip()
        if not _KEY.fullmatch(key):
            status = "INVALID"
            continue
        if ";" in raw and key != allow_nested_semicolon_key:
            status = "INVALID"
        if not raw:
            if status == "VALID":
                status = "EMPTY"
        fields.setdefault(key, []).append(raw)
    return fields, status


def _field_values(fields, key):
    return fields.get(key, [])


def _reference_tokens(values):
    tokens = []
    for value in values:
        tokens.extend(token.strip() for token in re.split(r"[;,]", value) if token.strip())
    return tokens


def _numeric_value(value):
    if not isinstance(value, str):
        return False
    candidate = value.strip()
    if not _NUMBER.fullmatch(candidate):
        return False
    try:
        return Decimal(candidate).is_finite()
    except InvalidOperation:
        return False


def audit_finding_evidence(
    finding_type,
    evidence,
    source_references,
    measured_value,
    expected_value,
    threshold_value,
    source_run_id,
):
    """Return a stable JSON audit result without inferring cause or severity."""
    issues = set()
    kind = finding_type.strip().upper() if isinstance(finding_type, str) else ""
    if not kind:
        issues.add("missing_finding_type")
    elif kind not in _SUPPORTED_FINDINGS:
        issues.add("unsupported_finding_type")

    evidence_fields, evidence_parse = _parse_fields(evidence)
    reference_fields, reference_parse = _parse_fields(
        source_references, allow_nested_semicolon_key="quality_result_ids"
    )
    if evidence_parse == "MISSING":
        issues.add("missing_evidence")
    elif evidence_parse == "INVALID":
        issues.add("malformed_evidence")
    if reference_parse == "MISSING":
        issues.add("missing_source_references")
    elif reference_parse == "INVALID":
        issues.add("malformed_source_references")

    if kind in _SUPPORTED_FINDINGS:
        for key in _EVIDENCE_FIELDS[kind]:
            if not _field_values(evidence_fields, key) or not any(
                value.strip() for value in _field_values(evidence_fields, key)
            ):
                issues.add("missing_evidence_field:" + key)

        required_refs = dict(_REFERENCE_COUNTS.get(kind, {}))
        if kind == "INCIDENT_RECURRENCE":
            incident_ids = _reference_tokens(_field_values(reference_fields, "incident_ids"))
            required_refs["incident_ids"] = 1 if source_run_id else 2
            if source_run_id:
                required_refs["run_ids"] = 1
                required_refs["quality_result_ids"] = 1
            elif len(incident_ids) < 2:
                issues.add("missing_required_reference:second_incident_id")

        for key, minimum in required_refs.items():
            values = _reference_tokens(_field_values(reference_fields, key))
            if len(values) < minimum:
                issues.add("missing_required_reference:" + key)

        # Every reference value is an identifier or a delimited identifier list.
        for key, values in reference_fields.items():
            tokens = _reference_tokens(values)
            if not tokens:
                if key not in _OPTIONAL_REFERENCE_KEYS:
                    issues.add("missing_reference_value:" + key)
            elif any(not _REFERENCE_ID.fullmatch(token) for token in tokens):
                issues.add("malformed_reference:" + key)

        for key in _EVIDENCE_REFERENCE_KEYS[kind]:
            values = _field_values(evidence_fields, key)
            if not values:
                continue
            tokens = []
            for value in values:
                if kind == "CROSS_DOMAIN_INCONSISTENCY" and key in {"dataset_1", "dataset_2"}:
                    token = value.split("(", 1)[0].strip().split(" ", 1)[0]
                    tokens.append(token)
                else:
                    tokens.extend(_reference_tokens([value]))
            if not tokens or any(not _REFERENCE_ID.fullmatch(token) for token in tokens):
                issues.add("malformed_evidence_reference:" + key)

        numeric_evidence_fields = list(_NUMERIC_EVIDENCE_FIELDS.get(kind, ()))
        if kind == "INCIDENT_RECURRENCE":
            occurrence_key = (
                "distinct_occurrences"
                if _field_values(evidence_fields, "distinct_occurrences")
                else "distinct_historical_incidents"
            )
            numeric_evidence_fields.extend((occurrence_key, "recurrence_threshold"))
        for key in numeric_evidence_fields:
            values = _field_values(evidence_fields, key)
            if not values or not any(value.strip() for value in values):
                issues.add("missing_numeric:evidence." + key)
            elif any(not _numeric_value(value) for value in values):
                issues.add("invalid_numeric:evidence." + key)

        if kind == "QUALITY_FAILURE":
            for key in ("measured_value", "expected_value"):
                values = _field_values(evidence_fields, key)
                if any(value.strip() and value.strip().upper() != "NULL" and not _numeric_value(value) for value in values):
                    issues.add("invalid_numeric:evidence." + key)

        needs_run = kind != "INCIDENT_RECURRENCE" or bool(source_run_id)
        if needs_run:
            if not isinstance(source_run_id, str) or not source_run_id.strip():
                issues.add("missing_source_run_id")
            elif not _REFERENCE_ID.fullmatch(source_run_id.strip()):
                issues.add("malformed_source_run_id")
            else:
                run_refs = _reference_tokens(
                    _field_values(reference_fields, "run_id")
                    + _field_values(reference_fields, "run_ids")
                )
                evidence_runs = _reference_tokens(_field_values(evidence_fields, "run_id"))
                if kind in {"PIPELINE_FAILURE", "STALE_DATASET", "INCOMPLETE_DATA", "QUALITY_FAILURE"} and evidence_runs:
                    if source_run_id.strip() not in evidence_runs:
                        issues.add("source_run_id_mismatch")
                if kind in {"PIPELINE_FAILURE", "CROSS_DOMAIN_INCONSISTENCY"} and source_run_id.strip() not in run_refs:
                    issues.add("source_run_id_mismatch")

        consistency = {
            "STALE_DATASET": ("observation_id",),
            "INCOMPLETE_DATA": ("observation_id",),
            "QUALITY_FAILURE": ("quality_result_id", "quality_check_id", "observation_id"),
            "KPI_ANOMALY": ("kpi_id", "observation_id"),
        }.get(kind, ())
        for key in consistency:
            evidence_ids = _reference_tokens(_field_values(evidence_fields, key))
            source_ids = _reference_tokens(_field_values(reference_fields, key))
            if evidence_ids and source_ids and not set(evidence_ids).intersection(source_ids):
                issues.add("reference_mismatch:" + key)

    numeric_values = {
        "measured_value": measured_value,
        "expected_value": expected_value,
        "threshold_value": threshold_value,
    }
    if kind in _NUMERIC_REQUIRED:
        for key, value in numeric_values.items():
            if value is None or (isinstance(value, str) and not value.strip()):
                issues.add("missing_numeric:" + key)
            elif not _numeric_value(value):
                issues.add("invalid_numeric:" + key)
    elif kind == "QUALITY_FAILURE":
        supplied = [value for value in numeric_values.values() if value is not None and str(value).strip()]
        if supplied:
            for key, value in numeric_values.items():
                if value is not None and str(value).strip() and not _numeric_value(value):
                    issues.add("invalid_numeric:" + key)

    if any(issue.startswith(("malformed", "invalid_numeric", "reference_mismatch", "source_run_id_mismatch", "unsupported")) for issue in issues):
        audit_status = "INVALID"
    elif issues:
        audit_status = "INCOMPLETE"
    else:
        audit_status = "VALID"

    if evidence_parse == "INVALID" or any(issue.startswith("malformed_evidence") for issue in issues):
        evidence_status = "INVALID"
    elif evidence_parse == "MISSING" or any(issue.startswith("missing_evidence") for issue in issues):
        evidence_status = "MISSING"
    else:
        evidence_status = "VALID"

    if reference_parse == "INVALID" or any(issue.startswith("malformed_reference") or issue in {"malformed_source_references", "malformed_source_run_id"} for issue in issues):
        reference_status = "INVALID"
    elif reference_parse == "MISSING" or any(issue.startswith("missing_required_reference") or issue.startswith("missing_source_references") or issue.startswith("missing_reference_value") or issue == "missing_source_run_id" for issue in issues):
        reference_status = "MISSING"
    else:
        reference_status = "VALID"

    numeric_issues = [issue for issue in issues if issue.startswith(("missing_numeric", "invalid_numeric"))]
    if any(issue.startswith("invalid_numeric") for issue in numeric_issues):
        numeric_status = "INVALID"
    elif any(issue.startswith("missing_numeric") for issue in numeric_issues):
        numeric_status = "MISSING"
    elif kind == "QUALITY_FAILURE" and not any(value is not None and str(value).strip() for value in numeric_values.values()):
        numeric_status = "NOT_REQUIRED"
    elif kind not in _SUPPORTED_FINDINGS or (kind in _SUPPORTED_FINDINGS and kind not in _NUMERIC_REQUIRED and kind != "QUALITY_FAILURE"):
        numeric_status = "NOT_REQUIRED"
    else:
        numeric_status = "VALID"

    result = {
        "audit_status": audit_status,
        "evidence_status": evidence_status,
        "finding_type": kind or None,
        "issues": sorted(issues),
        "numeric_status": numeric_status,
        "reference_status": reference_status,
    }
    return json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def run(ctx):
    return audit_finding_evidence(
        ctx.finding_type,
        ctx.evidence,
        ctx.source_references,
        ctx.measured_value,
        ctx.expected_value,
        ctx.threshold_value,
        ctx.source_run_id,
    )
