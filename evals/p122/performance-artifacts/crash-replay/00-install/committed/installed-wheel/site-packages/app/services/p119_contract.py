"""P119 local/mock/sandbox incident contract and authority boundary."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from app.services.p110_evaluation import stable_hash

P119_INCIDENT_SCHEMA_VERSION = "p119.incident_envelope.v1"
P119_TIMELINE_SCHEMA_VERSION = "p119.timeline_event.v1"
P119_AUTHORITY_COUNTER_KEYS = (
    "auth_context_count",
    "credential_scope_count",
    "secret_material_count",
    "shell_execution_count",
    "subprocess_execution_count",
    "kubernetes_mutation_count",
    "cloud_mutation_count",
    "database_mutation_count",
    "network_mutation_count",
    "live_connector_call_count",
    "online_policy_write_count",
    "staging_mutation_count",
    "production_mutation_count",
    "l4_plus_action_count",
    "freeform_action_execution_count",
    "llm_command_execution_count",
    "authority_escape_count",
)
P119_INCIDENT_STATES = frozenset(
    {
        "detected",
        "triage_started",
        "diagnosing",
        "evidence_acquiring",
        "selection_pending",
        "approval_pending",
        "approved",
        "local_execution_pending",
        "local_executing",
        "validating",
        "rollback_pending",
        "rolling_back",
        "learning",
        "recovered",
        "escalated",
        "aborted_fail_closed",
        "expired",
        "orphaned_recovered",
    }
)
P119_TERMINAL_STATES = frozenset({"recovered", "escalated", "aborted_fail_closed", "expired", "orphaned_recovered"})
P119_LEGAL_TRANSITIONS: Mapping[str, frozenset[str]] = {
    "detected": frozenset({"triage_started", "aborted_fail_closed", "expired"}),
    "triage_started": frozenset({"diagnosing", "aborted_fail_closed", "expired"}),
    "diagnosing": frozenset({"evidence_acquiring", "selection_pending", "escalated", "aborted_fail_closed", "expired"}),
    "evidence_acquiring": frozenset({"diagnosing", "selection_pending", "escalated", "aborted_fail_closed", "expired"}),
    "selection_pending": frozenset({"approval_pending", "escalated", "aborted_fail_closed", "expired"}),
    "approval_pending": frozenset({"approved", "escalated", "aborted_fail_closed", "expired"}),
    "approved": frozenset({"local_execution_pending", "aborted_fail_closed", "expired"}),
    "local_execution_pending": frozenset({"local_executing", "aborted_fail_closed", "expired"}),
    "local_executing": frozenset({"validating", "rollback_pending", "escalated", "aborted_fail_closed", "expired"}),
    "validating": frozenset({"recovered", "rollback_pending", "learning", "escalated", "aborted_fail_closed", "expired"}),
    "rollback_pending": frozenset({"rolling_back", "escalated", "aborted_fail_closed", "expired"}),
    "rolling_back": frozenset({"orphaned_recovered", "escalated", "aborted_fail_closed", "expired"}),
    "learning": frozenset({"recovered", "escalated", "aborted_fail_closed", "expired"}),
}
P119_TIMELINE_EVENT_TYPES = frozenset(
    {
        "incident_detected",
        "dedupe_or_correlation_decision",
        "triage_started",
        "evidence_packet_bound",
        "hypothesis_created",
        "hypothesis_falsified",
        "missing_evidence_identified",
        "evidence_acquisition_requested",
        "evidence_acquisition_completed",
        "decision_selected",
        "approval_requested",
        "approval_granted",
        "approval_rejected",
        "human_escalation_required",
        "operation_enqueued",
        "lease_acquired",
        "local_action_attempted",
        "validation_started",
        "validation_succeeded",
        "validation_failed",
        "rollback_started",
        "rollback_succeeded",
        "rollback_failed",
        "causal_attribution_recorded",
        "recurrence_checked",
        "learning_record_written",
        "incident_terminalized",
        "crash_recovery_resumed",
        "orphan_inventory_recorded",
        "authority_counter_snapshot",
        "transition_rejected_fail_closed",
        "scheduler_budget_receipt",
    }
)

_FORBIDDEN_FIELD_NAMES = frozenset(
    {
        "auth",
        "authcontext",
        "cloudmutation",
        "command",
        "commandtext",
        "credential",
        "credentials",
        "databasemutation",
        "freeformaction",
        "kubernetesmutation",
        "liveconnector",
        "llmcommand",
        "networkmutation",
        "onlinepolicywrite",
        "password",
        "productionmutation",
        "secret",
        "shell",
        "shelltext",
        "stagingmutation",
        "subprocess",
        "subprocesscommand",
    }
)
_FORBIDDEN_TEXT_RE = re.compile(
    r"(prod|production|staging|kubectl|curl|ssh|aws\s|gcloud\s|terraform\s+apply|postgres://|mysql://|https?://|password|secret|credential|subprocess|shell|llm command)",
    re.IGNORECASE,
)
_LOCAL_TARGET_PREFIXES = ("local:fixture:", "mock:fixture:", "sandbox:fixture:")


class P119ContractError(ValueError):
    """Raised when a P119 artifact violates local fail-closed contracts."""


@dataclass(frozen=True)
class P119IncidentEnvelope:
    incident_id: str
    schema_version: str
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", _freeze(self.payload))

    @property
    def state(self) -> str:
        return str(self.payload["state"])

    @property
    def cas_version(self) -> int:
        return int(self.payload["cas_version"])

    @property
    def idempotency_key(self) -> str:
        return str(self.payload["idempotency_key"])

    @property
    def payload_hash(self) -> str:
        return str(self.payload["payload_hash"])

    def to_dict(self) -> dict[str, Any]:
        thawed = _thaw(self.payload)
        if not isinstance(thawed, dict):
            raise P119ContractError("invalid_incident_payload")
        return thawed


def exact_zero_authority_counters() -> dict[str, int]:
    return {key: 0 for key in P119_AUTHORITY_COUNTER_KEYS}


def validate_exact_zero_authority_counters(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping):
        raise P119ContractError("missing_authority_snapshot")
    unknown = sorted(set(str(key) for key in value) - set(P119_AUTHORITY_COUNTER_KEYS))
    if unknown:
        raise P119ContractError(f"unknown_authority_counter:{unknown[0]}")
    counters: dict[str, int] = {}
    for key in P119_AUTHORITY_COUNTER_KEYS:
        counter = value.get(key)
        if not isinstance(counter, int) or isinstance(counter, bool):
            raise P119ContractError(f"missing_authority_counter:{key}")
        if counter != 0:
            raise P119ContractError(f"authority_counter_nonzero:{key}")
        counters[key] = 0
    return counters


def reject_authority_boundary(value: Any) -> None:
    _reject_authority(value, allow_authority_snapshot=True)


def build_incident_envelope(data: Mapping[str, Any]) -> P119IncidentEnvelope:
    required = (
        "incident_id",
        "schema_version",
        "alert_fingerprint",
        "state",
        "wal_position",
        "cas_version",
        "idempotency_key",
        "budget_snapshot",
        "timeline_hash",
        "replay_refs",
        "authority_counter_snapshot",
    )
    for field in required:
        if field not in data:
            raise P119ContractError(f"missing_{field}")
    reject_authority_boundary(data)
    if data.get("schema_version") != P119_INCIDENT_SCHEMA_VERSION:
        raise P119ContractError(f"unsupported_schema_version:{data.get('schema_version')}")
    incident_id = _required_text(data, "incident_id")
    state = _state(data.get("state"))
    terminal_status = data.get("terminal_status")
    if state in P119_TERMINAL_STATES:
        if terminal_status != state:
            raise P119ContractError("missing_terminal_status")
    elif terminal_status is not None:
        raise P119ContractError("nonterminal_terminal_status")
    alert_fingerprint = _required_text(data, "alert_fingerprint")
    if not _fixture_id(data.get("fixture_id", "local:fixture:unspecified")).startswith(_LOCAL_TARGET_PREFIXES):
        raise P119ContractError("invalid_fixture_id")
    wal_position = _non_negative_int(data.get("wal_position"), "missing_wal_position")
    cas_version = _non_negative_int(data.get("cas_version"), "missing_cas_version")
    budget_snapshot = _required_mapping(data, "budget_snapshot")
    replay_refs = _required_sequence(data.get("replay_refs"), "missing_replay_refs")
    counters = validate_exact_zero_authority_counters(data.get("authority_counter_snapshot"))
    payload: dict[str, Any] = {
        "incident_id": incident_id,
        "schema_version": P119_INCIDENT_SCHEMA_VERSION,
        "alert_fingerprint": alert_fingerprint,
        "fixture_id": _fixture_id(data.get("fixture_id", "local:fixture:unspecified")),
        "state": state,
        "terminal_status": terminal_status,
        "wal_position": wal_position,
        "cas_version": cas_version,
        "idempotency_key": _required_text(data, "idempotency_key"),
        "budget_snapshot": _plain_mapping(budget_snapshot),
        "timeline_hash": _required_text(data, "timeline_hash"),
        "replay_refs": sorted(str(item) for item in replay_refs),
        "authority_counter_snapshot": counters,
    }
    payload["payload_hash"] = stable_hash(payload)
    return P119IncidentEnvelope(incident_id=incident_id, schema_version=P119_INCIDENT_SCHEMA_VERSION, payload=payload)


def build_timeline_event(
    *,
    incident_id: str,
    event_type: str,
    state_before: str,
    state_after: str,
    timestamp: int,
    actor_type: str,
    payload: Mapping[str, Any],
    previous_hash: str,
    budget_snapshot: Mapping[str, Any],
    authority_counter_snapshot: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    reject_authority_boundary(payload)
    if event_type not in P119_TIMELINE_EVENT_TYPES:
        raise P119ContractError(f"unknown_timeline_event_type:{event_type}")
    event = {
        "schema_version": P119_TIMELINE_SCHEMA_VERSION,
        "incident_id": _clean_text(incident_id, "missing_incident_id"),
        "event_type": event_type,
        "state_before": _state(state_before),
        "state_after": _state(state_after),
        "timestamp": _non_negative_int(timestamp, "invalid_timestamp"),
        "actor_type": _clean_text(actor_type, "missing_actor_type"),
        "payload": _plain_mapping(payload),
        "budget_snapshot": _plain_mapping(budget_snapshot),
        "authority_counter_snapshot": validate_exact_zero_authority_counters(authority_counter_snapshot or exact_zero_authority_counters()),
        "previous_hash": previous_hash,
        "redaction_receipt": {"redacted": True, "receipt_hash": stable_hash({"incident_id": incident_id, "event_type": event_type, "payload": payload})},
    }
    event["current_hash"] = stable_hash(event)
    return event


def legal_transition(state_before: str, state_after: str) -> bool:
    return state_after in P119_LEGAL_TRANSITIONS.get(state_before, frozenset())


def _reject_authority(value: Any, *, allow_authority_snapshot: bool) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = _normalized_field(key)
            if allow_authority_snapshot and normalized in {"authoritycountersnapshot", "authoritysnapshot"}:
                continue
            if allow_authority_snapshot and normalized == "counters" and isinstance(item, Mapping):
                if not item or any(not isinstance(counter, int) or isinstance(counter, bool) or counter != 0 for counter in item.values()):
                    raise P119ContractError("authority_counter_nonzero_or_invalid")
                continue
            if normalized in _FORBIDDEN_FIELD_NAMES:
                raise P119ContractError(f"forbidden_authority_field:{key}")
            _reject_authority(item, allow_authority_snapshot=allow_authority_snapshot)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            _reject_authority(item, allow_authority_snapshot=allow_authority_snapshot)
    elif isinstance(value, str) and _FORBIDDEN_TEXT_RE.search(value):
        raise P119ContractError("forbidden_authority_text")


def _state(value: Any) -> str:
    if not isinstance(value, str) or value not in P119_INCIDENT_STATES:
        raise P119ContractError(f"unknown_state:{value}")
    return value


def _fixture_id(value: Any) -> str:
    text = _clean_text(value, "missing_fixture_id")
    if not text.startswith(_LOCAL_TARGET_PREFIXES):
        raise P119ContractError("invalid_fixture_id")
    return text


def _required_text(data: Mapping[str, Any], key: str) -> str:
    return _clean_text(data.get(key), f"missing_{key}")


def _clean_text(value: Any, error: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise P119ContractError(error)
    if _FORBIDDEN_TEXT_RE.search(value):
        raise P119ContractError("forbidden_authority_text")
    return value.strip()


def _required_mapping(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = data.get(key)
    if not isinstance(value, Mapping) or not value:
        raise P119ContractError(f"missing_{key}")
    return value


def _required_sequence(value: Any, error: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)) or not value:
        raise P119ContractError(error)
    return value


def _non_negative_int(value: Any, error: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise P119ContractError(error)
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
