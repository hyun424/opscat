"""Deterministic P137 incident correlation over validated evidence atoms."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p137_contracts import INCIDENT_SCHEMA_VERSION as CONTRACT_INCIDENT_SCHEMA_VERSION

INCIDENT_SCHEMA_VERSION = CONTRACT_INCIDENT_SCHEMA_VERSION
ATOM_SCHEMA_VERSION = "p137.evidence_atom.v1"

NONTERMINAL_STATUSES = frozenset({"open", "correlating", "investigating", "ready_to_classify", "classification_pending"})
TERMINAL_STATUSES = frozenset({"confirmed_incident", "insufficient_evidence", "benign_anomaly", "aborted_fail_closed"})
_TRANSITIONS = {
    "open": frozenset({"correlating", "aborted_fail_closed"}),
    "correlating": frozenset({"investigating", "aborted_fail_closed"}),
    "investigating": frozenset({"ready_to_classify", "aborted_fail_closed"}),
    "ready_to_classify": frozenset({"classification_pending", "aborted_fail_closed"}),
    "classification_pending": frozenset({"confirmed_incident", "insufficient_evidence", "benign_anomaly", "aborted_fail_closed"}),
}

_ATOM_FIELDS = frozenset(
    {
        "schema_version",
        "atom_id",
        "promotion_record_hash",
        "promotion_key",
        "p136_entry_hash",
        "p135_bundle_hash",
        "source_id",
        "provider",
        "format",
        "signal_family",
        "system_id",
        "entity_ref_hash",
        "window",
        "signal_name",
        "numeric_value",
        "numeric_unit",
        "evidence_state",
        "severity_code",
        "metric_breach_code",
        "marker_code",
        "counter_signal_code",
        "state_reason_codes",
        "denominator_visible",
        "content_hash",
        "label_hashes",
        "topology_ref_hashes",
        "deploy_config_ref_hashes",
        "risk_flags",
        "redacted_preview_hash",
        "ordinal",
        "atom_hash",
    }
)
_REJECTION_FIELDS = frozenset({"rejection_hash", "system_id", "entity_ref_hash", "window", "reason_code"})
_DEFAULT_LIMITS = {
    "max_open_incidents": 64,
    "max_atoms_per_incident": 128,
    "max_correlation_window_seconds": 900,
    "max_incident_duration_seconds": 86_400,
    "max_journal_entries": 1_024,
    "max_ledger_edges": 4_096,
}


class P137CorrelationError(ValueError):
    """Raised when P137 correlation must fail closed."""

    def __init__(self, message: str, *, incident: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.incident = dict(incident) if incident is not None else None


def transition_incident_status(current: str, target: str) -> str:
    if current in TERMINAL_STATUSES:
        raise P137CorrelationError("terminal_incident_transition_forbidden")
    if current not in NONTERMINAL_STATUSES or target not in NONTERMINAL_STATUSES | TERMINAL_STATUSES:
        raise P137CorrelationError("unknown_incident_status")
    if target not in _TRANSITIONS[current]:
        raise P137CorrelationError("illegal_incident_transition")
    return target


def correlate_incident_state(
    atoms: Sequence[Mapping[str, Any]],
    *,
    rejections: Sequence[Mapping[str, Any]] | None = None,
    now: str = "1970-01-01T00:00:00Z",
    limits: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    effective_limits = _limits(limits)
    validated_atoms = [_validate_atom(atom) for atom in atoms]
    validated_rejections = [_validate_rejection(rejection) for rejection in rejections or ()]
    groups = _correlate_groups(validated_atoms, effective_limits["max_correlation_window_seconds"])
    if len(groups) > effective_limits["max_open_incidents"]:
        raise P137CorrelationError("open_incident_budget_exceeded")

    incidents: list[dict[str, Any]] = []
    journal_entries = 0
    ledger_edges = 0
    for sequence, group in enumerate(groups, start=1):
        if len(group) > effective_limits["max_atoms_per_incident"]:
            raise P137CorrelationError("incident_atom_budget_exceeded")
        incident_rejections = _matching_rejections(group, validated_rejections, effective_limits["max_correlation_window_seconds"])
        ledger_edges += max(0, len(group) - 1) + len(incident_rejections)
        journal_entries += len(group) + len(incident_rejections)
        incident = _build_incident(sequence, group, incident_rejections, now=now)
        _enforce_duration(incident, effective_limits["max_incident_duration_seconds"])
        incidents.append(incident)

    if journal_entries > effective_limits["max_journal_entries"]:
        raise P137CorrelationError("journal_budget_exceeded")
    if ledger_edges > effective_limits["max_ledger_edges"]:
        raise P137CorrelationError("ledger_budget_exceeded")
    incidents.sort(key=lambda item: (str(item["primary_system_id"]), str(item["incident_id"])))
    return {"schema_version": "p137.correlation_result.v1", "incidents": incidents, "incident_count": len(incidents)}


def _limits(overrides: Mapping[str, int] | None) -> dict[str, int]:
    values = dict(_DEFAULT_LIMITS)
    for key, value in (overrides or {}).items():
        if key not in values:
            raise P137CorrelationError("unknown_budget_key")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise P137CorrelationError("invalid_budget_value")
        values[key] = value
    return values


def _validate_atom(atom: Mapping[str, Any]) -> dict[str, Any]:
    if set(atom) != _ATOM_FIELDS:
        raise P137CorrelationError("unexpected_atom_keys")
    if atom.get("schema_version") != ATOM_SCHEMA_VERSION:
        raise P137CorrelationError("invalid_atom_schema")
    window = atom.get("window")
    if not isinstance(window, Mapping) or set(window) != {"start", "end"}:
        raise P137CorrelationError("invalid_atom_window")
    labels = atom.get("label_hashes")
    if not isinstance(labels, list) or any(not isinstance(label, str) for label in labels):
        raise P137CorrelationError("invalid_label_hashes")
    return dict(atom)


def _validate_rejection(rejection: Mapping[str, Any]) -> dict[str, Any]:
    allowed = _REJECTION_FIELDS | {"free_form_detail"}
    if not _REJECTION_FIELDS <= set(rejection) or set(rejection) - allowed:
        raise P137CorrelationError("unexpected_rejection_keys")
    window = rejection.get("window")
    if not isinstance(window, Mapping) or set(window) != {"start", "end"}:
        raise P137CorrelationError("invalid_rejection_window")
    return {key: rejection[key] for key in _REJECTION_FIELDS}


def _correlate_groups(atoms: Sequence[dict[str, Any]], max_window_seconds: int) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    for atom in sorted(atoms, key=lambda item: str(item["atom_hash"])):
        matches = [index for index, group in enumerate(groups) if any(_relations(atom, existing, max_window_seconds) for existing in group)]
        if not matches:
            groups.append([atom])
            continue
        first = matches[0]
        groups[first].append(atom)
        for index in reversed(matches[1:]):
            groups[first].extend(groups.pop(index))
    return [sorted(group, key=lambda item: str(item["atom_hash"])) for group in groups]


def _relations(left: Mapping[str, Any], right: Mapping[str, Any], max_window_seconds: int) -> list[str]:
    relations: list[str] = []
    overlapping = _windows_overlap(left["window"], right["window"])
    if left["system_id"] == right["system_id"] and overlapping and _window_distance_seconds(left["window"], right["window"]) <= max_window_seconds:
        relations.append("system_id_time_window")
    if left["entity_ref_hash"] == right["entity_ref_hash"] and overlapping:
        relations.append("entity_ref_hash")
    if left["provider"] == right["provider"] and left["signal_family"] == right["signal_family"]:
        relations.append("provider_signal_family")
    if set(left["label_hashes"]) & set(right["label_hashes"]):
        relations.append("label_hash")
    if left["content_hash"] and left["content_hash"] == right["content_hash"]:
        relations.append("content_hash")
    return relations


def _matching_rejections(group: Sequence[Mapping[str, Any]], rejections: Sequence[Mapping[str, Any]], max_window_seconds: int) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    for rejection in rejections:
        for atom in group:
            same_scope = atom["system_id"] == rejection["system_id"] or atom["entity_ref_hash"] == rejection["entity_ref_hash"]
            if same_scope and _windows_overlap(atom["window"], rejection["window"]) and _window_distance_seconds(atom["window"], rejection["window"]) <= max_window_seconds:
                matched.append(dict(rejection))
                break
    return sorted(matched, key=lambda item: str(item["rejection_hash"]))


def _build_incident(sequence: int, group: Sequence[dict[str, Any]], rejections: Sequence[dict[str, Any]], *, now: str) -> dict[str, Any]:
    first_window_start = min(str(atom["window"]["start"]) for atom in group)
    last_window_end = max(str(atom["window"]["end"]) for atom in group)
    ordered_group = sorted(group, key=lambda atom: (int(atom["ordinal"]), str(atom["atom_hash"])))
    atom_hashes = [str(atom["atom_hash"]) for atom in ordered_group]
    relation_set = sorted({relation for left in group for right in group if left is not right for relation in _relations(left, right, _DEFAULT_LIMITS["max_correlation_window_seconds"])})
    key = {
        "primary_system_id": min(str(atom["system_id"]) for atom in group),
        "entity_ref_hashes": sorted({str(atom["entity_ref_hash"]) for atom in group}),
        "provider_signal_families": sorted({f"{atom['provider']}:{atom['signal_family']}" for atom in group}),
        "label_hashes": sorted({str(label) for atom in group for label in atom["label_hashes"]}),
        "content_hashes": sorted({str(atom["content_hash"]) for atom in group if atom["content_hash"]}),
        "p136_rejection_reasons": sorted({str(rejection["reason_code"]) for rejection in rejections}),
        "relations": relation_set,
    }
    payload: dict[str, Any] = {
        "schema_version": INCIDENT_SCHEMA_VERSION,
        "incident_id": _incident_id(key),
        "incident_sequence": sequence,
        "status": "open",
        "created_at": first_window_start,
        "updated_at": now,
        "correlation_key": key,
        "primary_system_id": key["primary_system_id"],
        "entity_ref_hashes": key["entity_ref_hashes"],
        "time_window": {"start": first_window_start, "end": last_window_end},
        "source_promotion_record_hashes": sorted({str(atom["promotion_record_hash"]) for atom in group}),
        "evidence_atom_hashes": atom_hashes,
        "rejection_hashes": sorted(str(rejection["rejection_hash"]) for rejection in rejections),
        "hypothesis_hashes": [],
        "request_hashes": [],
        "attempted_request_hashes": [],
        "classification_hash": None,
        "previous_incident_hash": None,
    }
    payload["incident_hash"] = stable_hash(payload)
    return payload


def _incident_id(correlation_key: Mapping[str, Any]) -> str:
    return f"p137-{stable_hash({'schema_version': 'p137.incident_id.v1', 'correlation_key': correlation_key}).removeprefix('sha256:')[:40]}"


def _enforce_duration(incident: Mapping[str, Any], max_seconds: int) -> None:
    window = incident["time_window"]
    if _seconds_between(str(window["start"]), str(window["end"])) > max_seconds:
        raise P137CorrelationError("incident_duration_budget_exceeded", incident=incident)


def _windows_overlap(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return _parse_time(str(left["start"])) <= _parse_time(str(right["end"])) and _parse_time(str(right["start"])) <= _parse_time(str(left["end"]))


def _window_distance_seconds(left: Mapping[str, Any], right: Mapping[str, Any]) -> int:
    if _windows_overlap(left, right):
        return 0
    left_end = _parse_time(str(left["end"]))
    right_start = _parse_time(str(right["start"]))
    right_end = _parse_time(str(right["end"]))
    left_start = _parse_time(str(left["start"]))
    if left_end < right_start:
        return int((right_start - left_end).total_seconds())
    return int((left_start - right_end).total_seconds())


def _seconds_between(start: str, end: str) -> int:
    return int((_parse_time(end) - _parse_time(start)).total_seconds())


def _parse_time(value: str) -> datetime:
    if not value.endswith("Z"):
        raise P137CorrelationError("timestamp_must_be_utc_z")
    return datetime.fromisoformat(value.removesuffix("Z") + "+00:00").astimezone(UTC)
