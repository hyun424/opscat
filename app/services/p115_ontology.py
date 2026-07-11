"""Immutable, offline-only P115 remediation benchmark ontology."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any

from app.services.p110_evaluation import stable_hash

ACTION_PACK_SCHEMA_VERSION = "p115.action_pack.v1"
INCIDENT_CASE_SCHEMA_VERSION = "p115.incident_case.v1"
ACTION_LABEL_SCHEMA_VERSION = "p115.action_label.v1"
_SIGNATURE_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_DECISIONS = frozenset({"act", "no_action", "investigate_more", "escalate"})
_RELEASE_ROLES = frozenset({"development", "holdout"})
_TRUTH_FIELDS = frozenset(
    {"answer", "answer_key", "ground_truth", "hidden_outcome", "label", "oracle", "root_cause", "scorer_only_truth", "truth", "truth_hash"}
)
_COMMAND_FIELDS = frozenset({"command", "commands", "shell", "script", "argv", "executable", "kubectl", "ansible"})


class P115OntologyError(ValueError):
    """Raised when a benchmark artifact violates the offline ontology."""


@dataclass(frozen=True)
class P115Artifact:
    schema_version: str
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", _freeze(self.payload))

    def to_dict(self) -> dict[str, Any]:
        value = _thaw(self.payload)
        if not isinstance(value, dict):
            raise P115OntologyError("invalid_artifact")
        return value


def sign_action_pack_payload(payload: Mapping[str, Any], *, key_id: str, key: bytes) -> str:
    """Create an offline detached HMAC signature without retaining the key."""

    if not key_id or not key:
        raise P115OntologyError("missing_signer")
    signing_payload = {str(k): _thaw(v) for k, v in payload.items() if str(k) not in {"signature", "pack_hash", "schema_version"}}
    signing_payload["signer_key_id"] = key_id
    message = json.dumps(signing_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return "sha256:" + hmac.new(key, message, hashlib.sha256).hexdigest()


def build_action_pack(data: Mapping[str, Any], *, keyring: Mapping[str, bytes]) -> P115Artifact:
    _reject_forbidden_fields(data)
    action_id = _required_text(data, "action_id")
    signer_key_id = _required_text(data, "signer_key_id")
    signature = _required_text(data, "signature")
    key = keyring.get(signer_key_id)
    if key is None:
        raise P115OntologyError("unknown_signer")
    if not _SIGNATURE_RE.fullmatch(signature):
        raise P115OntologyError("invalid_action_pack_signature")
    expected = sign_action_pack_payload(data, key_id=signer_key_id, key=key)
    if not hmac.compare_digest(signature, expected):
        raise P115OntologyError("action_pack_signature_mismatch")
    if data.get("executor_disabled") is not True:
        raise P115OntologyError("executor_must_be_disabled")
    if _normalized(data.get("target_scope")) not in {"local_lab", "offline_fixture", "sandbox"}:
        raise P115OntologyError("production_target_selector")
    prerequisites = _required_text_list(data, "prerequisites")
    contraindications = _required_text_list(data, "contraindications")
    if set(prerequisites) & set(contraindications):
        raise P115OntologyError("contradictory_prerequisites")
    rollback = _required_mapping(data, "rollback_plan", "missing_rollback")
    validation = _required_mapping(data, "validation_query", "missing_validation")
    payload: dict[str, Any] = {
        "schema_version": ACTION_PACK_SCHEMA_VERSION,
        "action_id": action_id,
        "action_family": _required_text(data, "action_family"),
        "description": _required_text(data, "description"),
        "prerequisites": prerequisites,
        "contraindications": contraindications,
        "reversibility": _required_text(data, "reversibility"),
        "blast_radius": dict(_required_mapping(data, "blast_radius", "missing_blast_radius")),
        "expected_effect": dict(_required_mapping(data, "expected_effect", "missing_expected_effect")),
        "expected_evidence": _required_text_list(data, "expected_evidence"),
        "validation_query": dict(validation),
        "rollback_plan": dict(rollback),
        "executor_disabled": True,
        "target_scope": str(data["target_scope"]),
        "signer_key_id": signer_key_id,
        "signature": signature,
        "authority_level": "L1",
        "executable_body": None,
    }
    payload["pack_hash"] = stable_hash(payload)
    return P115Artifact(ACTION_PACK_SCHEMA_VERSION, payload)


def build_incident_case(data: Mapping[str, Any]) -> P115Artifact:
    _reject_forbidden_fields(data)
    window = _required_mapping(data, "time_window", "missing_time_window")
    start = _parse_timestamp(window.get("start"))
    end = _parse_timestamp(window.get("end"))
    if end <= start:
        raise P115OntologyError("invalid_time_window")
    release_role = _required_text(data, "release_role")
    if release_role not in _RELEASE_ROLES:
        raise P115OntologyError("invalid_release_role")
    payload: dict[str, Any] = {
        "schema_version": INCIDENT_CASE_SCHEMA_VERSION,
        "case_id": _required_text(data, "case_id"),
        "source_family": _required_text(data, "source_family"),
        "scenario_family": _required_text(data, "scenario_family"),
        "topology_handle": _required_handle(data, "topology_handle"),
        "time_window": {"start": str(window["start"]), "end": str(window["end"])},
        "visible_evidence_handle": _required_handle(data, "visible_evidence_handle"),
        "diagnosis_handle": _required_handle(data, "diagnosis_handle"),
        "eligible_action_pack_ids": _required_text_list(data, "eligible_action_pack_ids"),
        "required_evidence_classes": _required_text_list(data, "required_evidence_classes"),
        "partition_group": _required_text(data, "partition_group"),
        "release_role": release_role,
    }
    payload["artifact_hash"] = stable_hash(payload)
    return P115Artifact(INCIDENT_CASE_SCHEMA_VERSION, payload)


def build_action_label(data: Mapping[str, Any], *, eligible_action_pack_ids: Sequence[str]) -> P115Artifact:
    _reject_forbidden_fields(data)
    decision = _required_text(data, "decision")
    if decision not in _DECISIONS:
        raise P115OntologyError("invalid_decision")
    action_ids = _text_list(data.get("action_pack_ids"), allow_empty=True, error="invalid_action_pack_ids")
    unknown = sorted(set(action_ids) - set(eligible_action_pack_ids))
    if unknown:
        raise P115OntologyError(f"unknown_action_pack:{unknown[0]}")
    if decision == "act" and not action_ids:
        raise P115OntologyError("act_requires_action_pack")
    if decision != "act" and action_ids:
        raise P115OntologyError("non_action_decision_has_action_pack")
    reason = data.get("abstention_reason")
    if decision in {"no_action", "investigate_more", "escalate"} and (not isinstance(reason, str) or not reason):
        raise P115OntologyError("missing_abstention_reason")
    payload: dict[str, Any] = {
        "schema_version": ACTION_LABEL_SCHEMA_VERSION,
        "case_id": _required_text(data, "case_id"),
        "decision": decision,
        "action_pack_ids": action_ids,
        "evidence_ids": _required_text_list(data, "evidence_ids"),
        "prerequisite_checks": dict(_mapping(data.get("prerequisite_checks"))),
        "contraindication_checks": dict(_mapping(data.get("contraindication_checks"))),
        "expected_benefit": _required_number(data, "expected_benefit"),
        "expected_harm": _required_number(data, "expected_harm"),
        "validation_plan": dict(_required_mapping(data, "validation_plan", "missing_validation")),
        "rollback_plan": dict(_required_mapping(data, "rollback_plan", "missing_rollback")),
        "abstention_reason": reason,
        "authority_level": "L1",
        "executed_actions": [],
    }
    payload["artifact_hash"] = stable_hash(payload)
    return P115Artifact(ACTION_LABEL_SCHEMA_VERSION, payload)


def _reject_forbidden_fields(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = _normalized(key)
            if normalized in _TRUTH_FIELDS:
                raise P115OntologyError(f"truth_bearing_field:{key}")
            if normalized in _COMMAND_FIELDS:
                raise P115OntologyError(f"executable_command:{key}")
            _reject_forbidden_fields(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            _reject_forbidden_fields(item)


def _normalized(value: Any) -> str:
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", str(value))
    return re.sub(r"[^a-z0-9]+", "_", text.casefold()).strip("_")


def _required_text(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise P115OntologyError(f"missing_{key}")
    return value


def _required_handle(data: Mapping[str, Any], key: str) -> str:
    value = _required_text(data, key)
    if ":" not in value or any(character.isspace() for character in value):
        raise P115OntologyError(f"invalid_{key}")
    return value


def _required_mapping(data: Mapping[str, Any], key: str, error: str) -> Mapping[str, Any]:
    value = data.get(key)
    if not isinstance(value, Mapping) or not value:
        raise P115OntologyError(error)
    return value


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _required_text_list(data: Mapping[str, Any], key: str) -> list[str]:
    return _text_list(data.get(key), allow_empty=False, error=f"missing_{key}")


def _text_list(value: Any, *, allow_empty: bool, error: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise P115OntologyError(error)
    result = [item for item in value if isinstance(item, str) and item]
    if len(result) != len(value) or (not allow_empty and not result) or len(result) != len(set(result)):
        raise P115OntologyError(error)
    return result


def _required_number(data: Mapping[str, Any], key: str) -> float:
    value = data.get(key)
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise P115OntologyError(f"missing_{key}")
    return float(value)


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise P115OntologyError("invalid_time_window")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise P115OntologyError("invalid_time_window") from exc
    if parsed.tzinfo is None:
        raise P115OntologyError("invalid_time_window")
    return parsed


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


__all__ = [
    "ACTION_LABEL_SCHEMA_VERSION",
    "ACTION_PACK_SCHEMA_VERSION",
    "INCIDENT_CASE_SCHEMA_VERSION",
    "P115Artifact",
    "P115OntologyError",
    "build_action_label",
    "build_action_pack",
    "build_incident_case",
    "sign_action_pack_payload",
]
