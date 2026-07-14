"""CAS-chained investigation ledger contracts for P137."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p137_classification import validate_classification_record
from app.services.p137_contracts import LEDGER_SCHEMA_VERSION as CONTRACT_LEDGER_SCHEMA_VERSION
from app.services.p137_requests import validate_evidence_request

LEDGER_SCHEMA_VERSION = CONTRACT_LEDGER_SCHEMA_VERSION
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_FIELDS = frozenset(
    {
        "schema_version",
        "config_hash",
        "next_incident_sequence",
        "next_request_sequence",
        "next_classification_sequence",
        "incident_hashes",
        "classification_hashes",
        "attempted_request_hashes",
        "counters",
        "authority_counters",
        "runtime_activity",
        "evaluator_activity",
        "resource_usage",
        "previous_ledger_hash",
        "ledger_hash",
    }
)


class P137LedgerError(ValueError):
    """Raised when ledger lineage, counters, or attached evidence are invalid."""


def new_investigation_ledger(
    *,
    config_hash: str,
    counters: Mapping[str, int],
    authority_counters: Mapping[str, int],
    runtime_activity: Mapping[str, int],
    evaluator_activity: Mapping[str, int],
    resource_usage: Mapping[str, int],
) -> dict[str, Any]:
    _hash(config_hash, "config_hash")
    ledger: dict[str, Any] = {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "config_hash": config_hash,
        "next_incident_sequence": 1,
        "next_request_sequence": 1,
        "next_classification_sequence": 1,
        "incident_hashes": [],
        "classification_hashes": [],
        "attempted_request_hashes": [],
        "counters": _integer_map(counters, "counters"),
        "authority_counters": _zero_map(authority_counters, "authority_counters"),
        "runtime_activity": _integer_map(runtime_activity, "runtime_activity"),
        "evaluator_activity": _integer_map(evaluator_activity, "evaluator_activity"),
        "resource_usage": _integer_map(resource_usage, "resource_usage"),
        "previous_ledger_hash": None,
    }
    ledger["ledger_hash"] = stable_hash(ledger)
    validate_investigation_ledger(ledger)
    return ledger


def advance_investigation_ledger(
    prior: Mapping[str, Any],
    *,
    expected_previous_hash: str,
    incidents: Sequence[Mapping[str, Any]] = (),
    requests: Sequence[Mapping[str, Any]] = (),
    classifications: Sequence[Mapping[str, Any]] = (),
    counters: Mapping[str, int] | None = None,
    runtime_activity: Mapping[str, int] | None = None,
    evaluator_activity: Mapping[str, int] | None = None,
    resource_usage: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    validate_investigation_ledger(prior)
    if prior.get("ledger_hash") != expected_previous_hash:
        raise P137LedgerError("ledger_cas_predecessor_mismatch")
    incident_values = [_mapping(item, "incident") for item in incidents]
    request_values = [_mapping(item, "request") for item in requests]
    classification_values = [_mapping(item, "classification") for item in classifications]
    for request in request_values:
        validate_evidence_request(request)
    for classification in classification_values:
        validate_classification_record(classification)

    expected_request_sequence = int(prior["next_request_sequence"])
    for request in request_values:
        if request.get("request_sequence") != expected_request_sequence:
            raise P137LedgerError("request_sequence_mismatch")
        expected_request_sequence += 1
    expected_classification_sequence = int(prior["next_classification_sequence"])
    for classification in classification_values:
        if classification.get("classification_sequence") != expected_classification_sequence:
            raise P137LedgerError("classification_sequence_mismatch")
        expected_classification_sequence += 1
    expected_incident_sequence = int(prior["next_incident_sequence"])
    incident_hashes: list[str] = []
    for incident in incident_values:
        if incident.get("incident_sequence") != expected_incident_sequence:
            raise P137LedgerError("incident_sequence_mismatch")
        incident_hashes.append(_hash(incident.get("incident_hash"), "incident_hash"))
        expected_incident_sequence += 1

    next_attempts = [*prior["attempted_request_hashes"], *[request["attempted_request_hash"] for request in request_values]]
    if len(next_attempts) != len(set(next_attempts)):
        raise P137LedgerError("attempted_request_hash_reuse")
    next_incidents = [*prior["incident_hashes"], *incident_hashes]
    next_classifications = [*prior["classification_hashes"], *[classification["classification_hash"] for classification in classification_values]]
    if len(next_incidents) != len(set(next_incidents)) or len(next_classifications) != len(set(next_classifications)):
        raise P137LedgerError("duplicate_ledger_member")

    ledger: dict[str, Any] = {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "config_hash": prior["config_hash"],
        "next_incident_sequence": expected_incident_sequence,
        "next_request_sequence": expected_request_sequence,
        "next_classification_sequence": expected_classification_sequence,
        "incident_hashes": next_incidents,
        "classification_hashes": next_classifications,
        "attempted_request_hashes": next_attempts,
        "counters": _integer_map(counters or prior["counters"], "counters"),
        "authority_counters": deepcopy(dict(prior["authority_counters"])),
        "runtime_activity": _integer_map(runtime_activity or prior["runtime_activity"], "runtime_activity"),
        "evaluator_activity": _integer_map(evaluator_activity or prior["evaluator_activity"], "evaluator_activity"),
        "resource_usage": _integer_map(resource_usage or prior["resource_usage"], "resource_usage"),
        "previous_ledger_hash": prior["ledger_hash"],
    }
    ledger["ledger_hash"] = stable_hash(ledger)
    validate_investigation_ledger(
        ledger,
        prior=prior,
        incidents=incident_values,
        requests=request_values,
        classifications=classification_values,
    )
    return ledger


def validate_investigation_ledger(
    ledger: Mapping[str, Any],
    *,
    prior: Mapping[str, Any] | None = None,
    incidents: Sequence[Mapping[str, Any]] = (),
    requests: Sequence[Mapping[str, Any]] = (),
    classifications: Sequence[Mapping[str, Any]] = (),
) -> None:
    value = _mapping(ledger, "ledger")
    if set(value) != _FIELDS or value.get("schema_version") != LEDGER_SCHEMA_VERSION:
        raise P137LedgerError("invalid_ledger_fields")
    _hash(value.get("config_hash"), "config_hash")
    for field in ("next_incident_sequence", "next_request_sequence", "next_classification_sequence"):
        _positive_int(value.get(field), field)
    incident_hashes = _hashes(_sequence(value.get("incident_hashes"), "incident_hashes"), "incident_hashes")
    classification_hashes = _hashes(_sequence(value.get("classification_hashes"), "classification_hashes"), "classification_hashes")
    attempt_hashes = _hashes(_sequence(value.get("attempted_request_hashes"), "attempted_request_hashes"), "attempted_request_hashes")
    for field in ("counters", "runtime_activity", "evaluator_activity", "resource_usage"):
        _integer_map(_mapping(value.get(field), field), field)
    _zero_map(_mapping(value.get("authority_counters"), "authority_counters"), "authority_counters")
    previous_hash = value.get("previous_ledger_hash")
    if previous_hash is not None:
        _hash(previous_hash, "previous_ledger_hash")
    if prior is None:
        expected_sequences = (
            len(incident_hashes) + 1,
            len(attempt_hashes) + 1,
            len(classification_hashes) + 1,
        )
        actual_sequences = (
            value["next_incident_sequence"],
            value["next_request_sequence"],
            value["next_classification_sequence"],
        )
        if actual_sequences != expected_sequences:
            raise P137LedgerError("standalone_ledger_sequence_mismatch")
        has_members = bool(incident_hashes or classification_hashes or attempt_hashes)
        if has_members != (previous_hash is not None):
            raise P137LedgerError("standalone_ledger_predecessor_mismatch")
    else:
        validate_investigation_ledger(prior)
        if previous_hash != prior.get("ledger_hash") or value.get("config_hash") != prior.get("config_hash"):
            raise P137LedgerError("ledger_predecessor_mismatch")
        expected_incidents = [*prior["incident_hashes"], *[_mapping(item, "incident").get("incident_hash") for item in incidents]]
        expected_classifications = [*prior["classification_hashes"], *[_mapping(item, "classification").get("classification_hash") for item in classifications]]
        expected_attempts = [*prior["attempted_request_hashes"], *[_mapping(item, "request").get("attempted_request_hash") for item in requests]]
        if list(value["incident_hashes"]) != expected_incidents:
            raise P137LedgerError("incident_membership_mismatch")
        if list(value["classification_hashes"]) != expected_classifications:
            raise P137LedgerError("classification_membership_mismatch")
        if list(value["attempted_request_hashes"]) != expected_attempts:
            raise P137LedgerError("attempted_request_membership_mismatch")
        if value["next_incident_sequence"] != prior["next_incident_sequence"] + len(incidents):
            raise P137LedgerError("incident_sequence_advance_mismatch")
        if value["next_request_sequence"] != prior["next_request_sequence"] + len(requests):
            raise P137LedgerError("request_sequence_advance_mismatch")
        if value["next_classification_sequence"] != prior["next_classification_sequence"] + len(classifications):
            raise P137LedgerError("classification_sequence_advance_mismatch")
    expected_hash = stable_hash({key: item for key, item in value.items() if key != "ledger_hash"})
    if value.get("ledger_hash") != expected_hash:
        raise P137LedgerError("ledger_hash_invalid")


def _integer_map(value: Mapping[str, Any], field: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for key, raw in value.items():
        if not isinstance(key, str) or not key or isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
            raise P137LedgerError(f"invalid_{field}")
        result[key] = raw
    return dict(sorted(result.items()))


def _zero_map(value: Mapping[str, Any], field: str) -> dict[str, int]:
    result = _integer_map(value, field)
    if any(result.values()):
        raise P137LedgerError(f"nonzero_{field}")
    return result


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise P137LedgerError(f"invalid_{field}")
    return value


def _sequence(value: Any, field: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise P137LedgerError(f"invalid_{field}")
    return value


def _hash(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _HASH_RE.fullmatch(value):
        raise P137LedgerError(f"invalid_{field}")
    return value


def _hashes(values: Sequence[Any], field: str) -> list[str]:
    result = [_hash(item, field) for item in values]
    if len(result) != len(set(result)):
        raise P137LedgerError(f"duplicate_{field}")
    return result


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise P137LedgerError(f"invalid_{field}")
    return value


__all__ = [
    "P137LedgerError",
    "advance_investigation_ledger",
    "new_investigation_ledger",
    "validate_investigation_ledger",
]
