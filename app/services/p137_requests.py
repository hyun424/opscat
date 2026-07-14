"""Closed, local-only evidence selection for P137.

The catalog operates only on validated evidence atoms already present in
memory.  It deliberately exposes no path, provider-client, network, command,
credential, or mutation surface.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p137_contracts import ALLOWED_REQUEST_CATALOG, EVIDENCE_REQUEST_SCHEMA_VERSION

REQUEST_SCHEMA_VERSION = EVIDENCE_REQUEST_SCHEMA_VERSION

_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_FORBIDDEN_TEXT_RE = re.compile(
    r"(?:https?://|file://|(?:^|[\\/])\.\.?[\\/]|/etc/|/var/|api[_-]?key|"
    r"authorization|password|credential|secret|curl\s|wget\s|bash\s|sh\s+-c|"
    r"delete|restart|rollback|deploy|execute|provider[_-]?query)",
    re.IGNORECASE,
)

_PARAMETER_FIELDS: dict[str, frozenset[str]] = {
    "compare_current_window_to_promoted_baseline": frozenset(
        {"signal_name", "current_window_start", "current_window_end", "baseline_window_start", "baseline_window_end", "limit"}
    ),
    "fetch_record_by_evidence_id": frozenset({"evidence_id", "limit"}),
    "join_records_by_entity_and_window": frozenset({"entity_ref_hash", "window_start", "window_end", "limit"}),
    "select_records_by_content_hash": frozenset({"content_hash", "limit"}),
    "select_records_by_entity_ref": frozenset({"entity_ref_hash", "limit"}),
    "select_records_by_label_hash": frozenset({"label_hash", "limit"}),
    "select_records_by_provider": frozenset({"provider", "limit"}),
    "select_records_by_risk_flag": frozenset({"risk_flag", "limit"}),
    "select_records_by_signal_family": frozenset({"signal_family", "limit"}),
    "select_records_by_system_id": frozenset({"system_id", "limit"}),
    "select_records_by_time_window": frozenset({"window_start", "window_end", "limit"}),
    "select_rejections_by_reason": frozenset({"reason_code", "limit"}),
    "summarize_log_preview_hashes": frozenset({"limit"}),
    "summarize_numeric_samples": frozenset({"signal_name", "limit"}),
    "summarize_topology_refs": frozenset({"limit"}),
}

_BUDGET_FIELDS = frozenset(
    {
        "max_input_records",
        "max_output_records",
        "max_output_bytes",
        "max_requests_per_incident",
        "wall_limit_ms",
        "cpu_limit_ms",
        "peak_memory_limit_bytes",
    }
)
_REQUEST_FIELDS = frozenset(
    {
        "schema_version",
        "request_id",
        "incident_id",
        "request_sequence",
        "catalog_name",
        "parameters",
        "input_atom_hashes",
        "budget",
        "attempted_request_hash",
        "result_summary",
        "runtime_activity",
        "previous_request_hash",
        "request_hash",
    }
)


class P137RequestError(ValueError):
    """Raised when a bounded local request is invalid or unsafe."""


@dataclass(frozen=True)
class EvidenceRequestResult:
    record: dict[str, Any]
    duplicate: bool


def build_request_budget(data: Mapping[str, Any] | None = None) -> dict[str, int]:
    value = dict(
        data
        or {
            "max_input_records": 256,
            "max_output_records": 64,
            "max_output_bytes": 65_536,
            "max_requests_per_incident": 8,
            "wall_limit_ms": 1_000,
            "cpu_limit_ms": 500,
            "peak_memory_limit_bytes": 16_777_216,
        }
    )
    if set(value) != _BUDGET_FIELDS:
        raise P137RequestError("invalid_request_budget_fields")
    for key, raw in value.items():
        if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
            raise P137RequestError(f"invalid_request_budget:{key}")
    return {key: int(value[key]) for key in sorted(value)}


def compute_attempted_request_hash(
    *,
    incident_hash: str,
    catalog_name: str,
    parameters: Mapping[str, Any],
    input_atom_hashes: Sequence[str],
    budget: Mapping[str, Any],
    request_sequence: int,
) -> str:
    _hash(incident_hash, "incident_hash")
    _positive_int(request_sequence, "request_sequence")
    validated_parameters = validate_request_parameters(catalog_name, parameters)
    validated_budget = build_request_budget(budget)
    hashes = _hashes(input_atom_hashes, "input_atom_hashes")
    return stable_hash(
        {
            "incident_hash": incident_hash,
            "catalog_name": catalog_name,
            "parameters": validated_parameters,
            "input_atom_hashes": hashes,
            "budget": validated_budget,
            "request_sequence": request_sequence,
        }
    )


def validate_request_parameters(catalog_name: str, parameters: Mapping[str, Any]) -> dict[str, Any]:
    if catalog_name not in ALLOWED_REQUEST_CATALOG:
        raise P137RequestError("request_catalog_not_allowlisted")
    value = _mapping(parameters, "parameters")
    expected = _PARAMETER_FIELDS[catalog_name]
    if set(value) != expected:
        raise P137RequestError("invalid_request_parameter_fields")
    _scan_safe(value)
    limit = _positive_int(value.get("limit"), "limit")
    if limit > 1_000:
        raise P137RequestError("request_limit_exceeded")
    for field in ("content_hash", "entity_ref_hash", "label_hash"):
        if field in value:
            _hash(value[field], field)
    for field in ("window_start", "window_end", "current_window_start", "current_window_end", "baseline_window_start", "baseline_window_end"):
        if field in value:
            _text(value[field], field)
    for field in ("signal_name", "evidence_id", "provider", "risk_flag", "signal_family", "system_id", "reason_code"):
        if field in value:
            _text(value[field], field)
    return deepcopy(dict(value))


def execute_evidence_request(
    *,
    incident_id: str,
    incident_hash: str,
    request_sequence: int,
    catalog_name: str,
    parameters: Mapping[str, Any],
    atoms: Sequence[Mapping[str, Any]],
    budget: Mapping[str, Any],
    previous_request_hash: str | None = None,
    existing_by_attempt: Mapping[str, Mapping[str, Any]] | None = None,
) -> EvidenceRequestResult:
    _text(incident_id, "incident_id")
    _hash(incident_hash, "incident_hash")
    if previous_request_hash is not None:
        _hash(previous_request_hash, "previous_request_hash")
    params = validate_request_parameters(catalog_name, parameters)
    limits = build_request_budget(budget)
    atom_values = _request_input_atoms(atoms, limits)
    input_hashes = _hashes([str(atom.get("atom_hash", "")) for atom in atom_values], "input_atom_hashes")
    attempt_hash = compute_attempted_request_hash(
        incident_hash=incident_hash,
        catalog_name=catalog_name,
        parameters=params,
        input_atom_hashes=input_hashes,
        budget=limits,
        request_sequence=request_sequence,
    )
    existing = (existing_by_attempt or {}).get(attempt_hash)
    if existing is not None:
        validate_evidence_request(existing)
        if existing.get("attempted_request_hash") != attempt_hash:
            raise P137RequestError("attempted_request_hash_conflict")
        expected = derive_evidence_request_record(
            incident_id=incident_id,
            incident_hash=incident_hash,
            request_sequence=request_sequence,
            catalog_name=catalog_name,
            parameters=params,
            atoms=atom_values,
            budget=limits,
            previous_request_hash=previous_request_hash,
        )
        if dict(existing) != expected:
            raise P137RequestError("durable_request_semantic_mismatch")
        return EvidenceRequestResult(record=deepcopy(dict(existing)), duplicate=True)

    record = derive_evidence_request_record(
        incident_id=incident_id,
        incident_hash=incident_hash,
        request_sequence=request_sequence,
        catalog_name=catalog_name,
        parameters=params,
        atoms=atom_values,
        budget=limits,
        previous_request_hash=previous_request_hash,
    )
    return EvidenceRequestResult(record=record, duplicate=False)


def derive_evidence_request_record(
    *,
    incident_id: str,
    incident_hash: str,
    request_sequence: int,
    catalog_name: str,
    parameters: Mapping[str, Any],
    atoms: Sequence[Mapping[str, Any]],
    budget: Mapping[str, Any],
    previous_request_hash: str | None = None,
) -> dict[str, Any]:
    _text(incident_id, "incident_id")
    _hash(incident_hash, "incident_hash")
    if previous_request_hash is not None:
        _hash(previous_request_hash, "previous_request_hash")
    params = validate_request_parameters(catalog_name, parameters)
    limits = build_request_budget(budget)
    atom_values = _request_input_atoms(atoms, limits)
    input_hashes = _hashes([str(atom.get("atom_hash", "")) for atom in atom_values], "input_atom_hashes")
    attempt_hash = compute_attempted_request_hash(
        incident_hash=incident_hash,
        catalog_name=catalog_name,
        parameters=params,
        input_atom_hashes=input_hashes,
        budget=limits,
        request_sequence=request_sequence,
    )
    selected, aggregate = _execute_catalog(catalog_name, params, atom_values)
    selected = selected[: min(params["limit"], limits["max_output_records"])]
    result_summary = {
        "operation": catalog_name,
        "matched_atom_hashes": [str(atom["atom_hash"]) for atom in selected],
        "output_count": len(selected),
        "aggregate": aggregate,
    }
    encoded = _canonical_bytes(result_summary)
    if len(encoded) > limits["max_output_bytes"]:
        raise P137RequestError("request_output_byte_budget_exceeded")
    runtime_activity = {
        "input_records_scanned": len(atom_values),
        "output_records_selected": len(selected),
        "output_bytes": len(encoded),
        "local_selection_count": 1,
        "external_call_count": 0,
    }
    request_id = stable_hash({"incident_id": incident_id, "request_sequence": request_sequence, "attempt": attempt_hash})
    record: dict[str, Any] = {
        "schema_version": REQUEST_SCHEMA_VERSION,
        "request_id": request_id,
        "incident_id": incident_id,
        "request_sequence": request_sequence,
        "catalog_name": catalog_name,
        "parameters": params,
        "input_atom_hashes": input_hashes,
        "budget": limits,
        "attempted_request_hash": attempt_hash,
        "result_summary": result_summary,
        "runtime_activity": runtime_activity,
        "previous_request_hash": previous_request_hash,
    }
    record["request_hash"] = stable_hash(record)
    validate_evidence_request(record)
    return record


def validate_evidence_request(record: Mapping[str, Any]) -> None:
    value = _mapping(record, "request")
    if set(value) != _REQUEST_FIELDS or value.get("schema_version") != REQUEST_SCHEMA_VERSION:
        raise P137RequestError("invalid_request_fields")
    _text(value.get("request_id"), "request_id")
    _text(value.get("incident_id"), "incident_id")
    _positive_int(value.get("request_sequence"), "request_sequence")
    validate_request_parameters(str(value.get("catalog_name")), _mapping(value.get("parameters"), "parameters"))
    build_request_budget(_mapping(value.get("budget"), "budget"))
    _hashes(_sequence(value.get("input_atom_hashes"), "input_atom_hashes"), "input_atom_hashes")
    _hash(value.get("attempted_request_hash"), "attempted_request_hash")
    previous = value.get("previous_request_hash")
    if previous is not None:
        _hash(previous, "previous_request_hash")
    summary = _mapping(value.get("result_summary"), "result_summary")
    if set(summary) != {"operation", "matched_atom_hashes", "output_count", "aggregate"}:
        raise P137RequestError("invalid_request_summary_fields")
    _scan_safe(summary)
    activity = _mapping(value.get("runtime_activity"), "runtime_activity")
    if set(activity) != {"input_records_scanned", "output_records_selected", "output_bytes", "local_selection_count", "external_call_count"}:
        raise P137RequestError("invalid_request_activity_fields")
    if any(isinstance(item, bool) or not isinstance(item, int) or item < 0 for item in activity.values()):
        raise P137RequestError("invalid_request_activity")
    if activity["external_call_count"] != 0:
        raise P137RequestError("request_external_authority_forbidden")
    expected = stable_hash({key: item for key, item in value.items() if key != "request_hash"})
    if value.get("request_hash") != expected:
        raise P137RequestError("request_hash_invalid")


def _execute_catalog(name: str, p: Mapping[str, Any], atoms: Sequence[Mapping[str, Any]]) -> tuple[list[Mapping[str, Any]], dict[str, Any]]:
    selected: list[Mapping[str, Any]]
    aggregate: dict[str, Any] = {}
    if name == "fetch_record_by_evidence_id":
        selected = [a for a in atoms if a.get("atom_id") == p["evidence_id"]]
    elif name == "select_records_by_content_hash":
        selected = [a for a in atoms if a.get("content_hash") == p["content_hash"]]
    elif name == "select_records_by_entity_ref":
        selected = [a for a in atoms if a.get("entity_ref_hash") == p["entity_ref_hash"]]
    elif name == "select_records_by_label_hash":
        selected = [a for a in atoms if p["label_hash"] in _sequence(a.get("label_hashes"), "label_hashes")]
    elif name == "select_records_by_provider":
        selected = [a for a in atoms if a.get("provider") == p["provider"]]
    elif name == "select_records_by_risk_flag":
        selected = [a for a in atoms if p["risk_flag"] in _sequence(a.get("risk_flags"), "risk_flags")]
    elif name == "select_records_by_signal_family":
        selected = [a for a in atoms if a.get("signal_family") == p["signal_family"]]
    elif name == "select_records_by_system_id":
        selected = [a for a in atoms if a.get("system_id") == p["system_id"]]
    elif name == "select_rejections_by_reason":
        selected = [a for a in atoms if p["reason_code"] in _sequence(a.get("state_reason_codes"), "state_reason_codes")]
    elif name in {"select_records_by_time_window", "join_records_by_entity_and_window"}:
        selected = [a for a in atoms if _overlaps(_mapping(a.get("window"), "window"), str(p["window_start"]), str(p["window_end"]))]
        if name == "join_records_by_entity_and_window":
            selected = [a for a in selected if a.get("entity_ref_hash") == p["entity_ref_hash"]]
    elif name == "summarize_log_preview_hashes":
        selected = [a for a in atoms if a.get("redacted_preview_hash")]
        aggregate = {"distinct_preview_hashes": len({str(a["redacted_preview_hash"]) for a in selected})}
    elif name == "summarize_topology_refs":
        selected = [a for a in atoms if _sequence(a.get("topology_ref_hashes"), "topology_ref_hashes")]
        aggregate = {"distinct_topology_refs": len({str(ref) for a in selected for ref in _sequence(a.get("topology_ref_hashes"), "topology_ref_hashes")})}
    elif name == "summarize_numeric_samples":
        selected = [a for a in atoms if a.get("signal_name") == p["signal_name"] and _finite_number(a.get("numeric_value"))]
        values = [float(a["numeric_value"]) for a in selected]
        aggregate = {"count": len(values), "min": min(values) if values else None, "max": max(values) if values else None}
    elif name == "compare_current_window_to_promoted_baseline":
        current = [
            atom
            for atom in atoms
            if atom.get("signal_name") == p["signal_name"]
            and _overlaps(
                _mapping(atom.get("window"), "window"),
                str(p["current_window_start"]),
                str(p["current_window_end"]),
            )
            and _finite_number(atom.get("numeric_value"))
        ]
        baseline = [
            atom
            for atom in atoms
            if atom.get("signal_name") == p["signal_name"]
            and _overlaps(
                _mapping(atom.get("window"), "window"),
                str(p["baseline_window_start"]),
                str(p["baseline_window_end"]),
            )
            and _finite_number(atom.get("numeric_value"))
        ]
        selected = [*current, *baseline]
        current_mean = sum(float(a["numeric_value"]) for a in current) / len(current) if current else None
        baseline_mean = sum(float(a["numeric_value"]) for a in baseline) / len(baseline) if baseline else None
        aggregate = {"current_mean": current_mean, "baseline_mean": baseline_mean, "delta": current_mean - baseline_mean if current_mean is not None and baseline_mean is not None else None}
    else:
        raise P137RequestError("request_catalog_not_allowlisted")
    return selected, aggregate


def _request_input_atoms(atoms: Sequence[Mapping[str, Any]], limits: Mapping[str, int]) -> list[Mapping[str, Any]]:
    atom_values = [_mapping(atom, "atom") for atom in atoms]
    if len(atom_values) > limits["max_input_records"]:
        raise P137RequestError("request_input_record_budget_exceeded")
    atom_values.sort(key=lambda atom: str(atom.get("atom_hash", "")))
    return atom_values


def _overlaps(window: Mapping[str, Any], start: str, end: str) -> bool:
    return str(window.get("start", "")) <= end and str(window.get("end", "")) >= start


def _scan_safe(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if _FORBIDDEN_TEXT_RE.search(str(key)):
                raise P137RequestError("request_authority_forbidden")
            _scan_safe(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            _scan_safe(item)
    elif isinstance(value, str) and _FORBIDDEN_TEXT_RE.search(value):
        raise P137RequestError("request_authority_forbidden")


def _finite_number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(float(value))


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise P137RequestError(f"invalid_{field}")
    return value


def _sequence(value: Any, field: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise P137RequestError(f"invalid_{field}")
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or len(value.encode()) > 256:
        raise P137RequestError(f"invalid_{field}")
    _scan_safe(value)
    return value


def _hash(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _HASH_RE.fullmatch(value):
        raise P137RequestError(f"invalid_{field}")
    return value


def _hashes(values: Sequence[Any], field: str) -> list[str]:
    result = [_hash(value, field) for value in values]
    if len(result) != len(set(result)):
        raise P137RequestError(f"duplicate_{field}")
    return sorted(result)


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise P137RequestError(f"invalid_{field}")
    return value


__all__ = [
    "ALLOWED_REQUEST_CATALOG",
    "EvidenceRequestResult",
    "P137RequestError",
    "build_request_budget",
    "compute_attempted_request_hash",
    "derive_evidence_request_record",
    "execute_evidence_request",
    "validate_evidence_request",
    "validate_request_parameters",
]
