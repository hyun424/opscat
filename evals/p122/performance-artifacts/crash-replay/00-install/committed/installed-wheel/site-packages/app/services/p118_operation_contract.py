"""P118 immutable local/mock/sandbox operation contract."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from app.services.p110_evaluation import stable_hash

P118_OPERATION_SCHEMA_VERSION = "p118.operation_envelope.v1"
P118_LIFECYCLE_STATES = frozenset(
    {
        "received",
        "verified",
        "approved",
        "prechecked",
        "action_attempted",
        "postchecked",
        "succeeded",
        "precheck_failed",
        "action_failed",
        "postcheck_failed",
        "rollback_attempted",
        "rollback_postchecked",
        "rolled_back",
        "rollback_failed",
        "validation_failed",
        "rejected",
        "expired",
        "orphaned_recovered",
        "aborted_fail_closed",
    }
)
P118_TERMINAL_STATUSES = frozenset(
    {
        "succeeded",
        "rolled_back",
        "rollback_failed",
        "validation_failed",
        "rejected",
        "expired",
        "orphaned_recovered",
        "aborted_fail_closed",
    }
)
P118_AUTHORITY_COUNTER_KEYS = (
    "auth",
    "credentials",
    "executor",
    "shell",
    "subprocess",
    "kubernetes",
    "cloud",
    "database_mutation",
    "production_adapter",
    "network_mutation",
    "online_policy_write",
    "production_mutation",
)
_REQUIRED_FIELDS = (
    "operation_id",
    "schema_version",
    "p117_decision_episode_id",
    "p117_selected_action_pack_id",
    "p115_action_pack_digest",
    "fixture_target_id",
    "action_level",
    "precondition_refs",
    "validation_plan_ref",
    "rollback_plan_ref",
    "approval_receipt",
    "lease_receipt",
    "wal_position",
    "cas_version",
    "idempotency_key",
    "authority_counter_snapshot",
)
_FORBIDDEN_FIELDS = frozenset(
    {
        "auth",
        "authcontext",
        "authrequired",
        "cloudmutation",
        "command",
        "commandtext",
        "credential",
        "credentials",
        "database",
        "databasemutation",
        "executor",
        "freeformaction",
        "kubernetes",
        "liveconnector",
        "network",
        "networkmutation",
        "onlinepolicywrite",
        "password",
        "productionadapter",
        "productionmutation",
        "secret",
        "shell",
        "shelltext",
        "subprocess",
        "targetselector",
    }
)
_FORBIDDEN_TEXT_RE = re.compile(
    r"(prod|production|staging|kubectl|curl|ssh|aws\s|gcloud\s|terraform\s+apply|postgres://|mysql://|https?://|password|secret|credential|subprocess|shell)",
    re.IGNORECASE,
)
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_LOCAL_TARGET_PREFIXES = ("local:fixture:", "mock:fixture:", "sandbox:fixture:")


class P118ContractError(ValueError):
    """Raised when a P118 contract artifact crosses the authority boundary."""


@dataclass(frozen=True)
class P118OperationEnvelope:
    operation_id: str
    schema_version: str
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", _freeze(self.payload))

    @property
    def idempotency_key(self) -> str:
        return str(self.payload["idempotency_key"])

    @property
    def cas_version(self) -> int:
        return int(self.payload["cas_version"])

    def to_dict(self) -> dict[str, Any]:
        thawed = _thaw(self.payload)
        if not isinstance(thawed, dict):
            raise P118ContractError("invalid_operation_payload")
        return thawed


def exact_zero_authority_counters() -> dict[str, int]:
    return {key: 0 for key in P118_AUTHORITY_COUNTER_KEYS}


def build_operation_envelope(data: Mapping[str, Any]) -> P118OperationEnvelope:
    for field in _REQUIRED_FIELDS:
        if field not in data:
            raise P118ContractError(f"missing_{field}")
    _reject_authority_fields(data, allow_authority_counters=True)
    if data.get("schema_version") != P118_OPERATION_SCHEMA_VERSION:
        raise P118ContractError(f"unsupported_schema_version:{data.get('schema_version')}")
    operation_id = _required_text(data, "operation_id")
    action_level = _action_level(data.get("action_level"))
    target = _fixture_target(data.get("fixture_target_id"))
    digest = _required_hash(data, "p115_action_pack_digest", "invalid_p115_action_pack_digest")
    preconditions = _text_list(data.get("precondition_refs"), "missing_precondition_refs")
    validation_ref = _required_text(data, "validation_plan_ref")
    rollback_ref = _required_text(data, "rollback_plan_ref")
    approval = _required_mapping(data, "approval_receipt", "missing_approval_receipt")
    lease = _required_mapping(data, "lease_receipt", "missing_lease_receipt")
    wal_position = _non_negative_int(data.get("wal_position"), "missing_wal_position")
    cas_version = _non_negative_int(data.get("cas_version"), "missing_cas_version")
    counters = validate_exact_zero_authority_counters(data.get("authority_counter_snapshot"))
    payload: dict[str, Any] = {
        "operation_id": operation_id,
        "schema_version": P118_OPERATION_SCHEMA_VERSION,
        "p117_decision_episode_id": _required_text(data, "p117_decision_episode_id"),
        "p117_selected_action_pack_id": _required_text(data, "p117_selected_action_pack_id"),
        "p115_action_pack_digest": digest,
        "fixture_target_id": target,
        "action_level": action_level,
        "precondition_refs": preconditions,
        "validation_plan_ref": validation_ref,
        "rollback_plan_ref": rollback_ref,
        "approval_receipt": _plain_mapping(approval),
        "lease_receipt": _plain_mapping(lease),
        "wal_position": wal_position,
        "cas_version": cas_version,
        "idempotency_key": _required_text(data, "idempotency_key"),
        "authority_counter_snapshot": counters,
        "lifecycle_states": sorted(P118_LIFECYCLE_STATES),
        "terminal_statuses": sorted(P118_TERMINAL_STATUSES),
    }
    payload["envelope_hash"] = stable_hash(payload)
    return P118OperationEnvelope(operation_id=operation_id, schema_version=P118_OPERATION_SCHEMA_VERSION, payload=payload)


def validate_exact_zero_authority_counters(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping):
        raise P118ContractError("missing_authority_counter_snapshot")
    unknown = sorted(set(str(key) for key in value) - set(P118_AUTHORITY_COUNTER_KEYS))
    if unknown:
        raise P118ContractError(f"unknown_authority_counter:{unknown[0]}")
    counters: dict[str, int] = {}
    for key in P118_AUTHORITY_COUNTER_KEYS:
        counter = value.get(key)
        if not isinstance(counter, int) or isinstance(counter, bool):
            raise P118ContractError(f"missing_authority_counter:{key}")
        if counter != 0:
            raise P118ContractError(f"authority_counter_nonzero:{key}")
        counters[key] = 0
    return counters


def reject_authority_boundary(value: Any) -> None:
    _reject_authority_fields(value, allow_authority_counters=True)


def _reject_authority_fields(value: Any, *, allow_authority_counters: bool = False) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = _normalized_field(key)
            if normalized == "authoritycountersnapshot" and allow_authority_counters:
                continue
            if normalized in {"counters", "policycounters"} and allow_authority_counters:
                continue
            if normalized in _FORBIDDEN_FIELDS:
                raise P118ContractError(f"forbidden_authority_field:{key}")
            _reject_authority_fields(item, allow_authority_counters=allow_authority_counters)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            _reject_authority_fields(item, allow_authority_counters=allow_authority_counters)
    elif isinstance(value, str) and _FORBIDDEN_TEXT_RE.search(value):
        raise P118ContractError("forbidden_authority_text")


def _action_level(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"L[0-9]+", value):
        raise P118ContractError("invalid_action_level")
    if int(value[1:]) > 3:
        raise P118ContractError("action_level_above_l3")
    return value


def _fixture_target(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise P118ContractError("missing_fixture_target_id")
    if not value.startswith(_LOCAL_TARGET_PREFIXES):
        raise P118ContractError("invalid_fixture_target")
    if _FORBIDDEN_TEXT_RE.search(value):
        raise P118ContractError("forbidden_authority_text")
    return value


def _required_hash(data: Mapping[str, Any], key: str, error: str) -> str:
    value = _required_text(data, key)
    if not _SHA256_RE.fullmatch(value):
        raise P118ContractError(error)
    return value


def _required_text(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise P118ContractError(f"missing_{key}")
    return value.strip()


def _required_mapping(data: Mapping[str, Any], key: str, error: str) -> Mapping[str, Any]:
    value = data.get(key)
    if not isinstance(value, Mapping) or not value:
        raise P118ContractError(error)
    return value


def _text_list(value: Any, error: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)) or not value:
        raise P118ContractError(error)
    result = [item for item in value if isinstance(item, str) and item]
    if len(result) != len(value) or len(result) != len(set(result)):
        raise P118ContractError(error)
    return sorted(result)


def _non_negative_int(value: Any, error: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise P118ContractError(error)
    return value


def _plain_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): _plain_value(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}


def _plain_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _plain_mapping(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_plain_value(item) for item in value]
    return value


def _normalized_field(value: Any) -> str:
    separated = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", str(value))
    return re.sub(r"[^a-z0-9]+", "", separated.casefold())


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
