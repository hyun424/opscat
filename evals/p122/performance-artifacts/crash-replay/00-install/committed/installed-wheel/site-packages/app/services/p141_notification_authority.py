"""P141 credential-free notification-only authority simulator.

P141 consumes validated P133 dead-man events and persists deterministic local
notification envelopes plus simulated delivery receipts.  It deliberately has
no network, credential, acknowledgement, action, remediation, or production
mutation authority.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import shutil
import stat
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p133_deadman_outbox import DeadmanConfig, list_outbox, load_deadman_config

CONFIG_SCHEMA_VERSION = "p141.notification_config.v1"
ENVELOPE_SCHEMA_VERSION = "p141.notification_envelope.v1"
RECEIPT_SCHEMA_VERSION = "p141.simulated_delivery_receipt.v1"
CURSOR_SCHEMA_VERSION = "p141.notification_cursor.v1"
RUN_SCHEMA_VERSION = "p141.notification_run.v1"
MAX_CLOCK_ROLLBACK_SECONDS = 5.0
MAX_LOCAL_JSON_BYTES = 16_777_216

FORBIDDEN_AUTHORITY_COUNTER_KEYS: tuple[str, ...] = (
    "credential_read_count",
    "environment_read_count",
    "dns_socket_call_count",
    "network_call_count",
    "provider_sdk_call_count",
    "external_message_send_count",
    "ticket_creation_count",
    "p133_ack_write_count",
    "approval_count",
    "subprocess_shell_count",
    "action_execution_count",
    "remediation_execution_count",
    "staging_mutation_count",
    "production_mutation_count",
    "operator_replacement_count",
    "authority_escape_count",
)

_CONFIG_FIELDS = frozenset(
    {
        "schema_version",
        "simulator_id",
        "allowed_artifact_roots",
        "p133_config_path",
        "envelope_dir",
        "receipt_dir",
        "cursor_path",
        "destination_ids",
        "transition_kinds",
        "template_version",
        "poll_interval_seconds",
        "max_envelope_bytes",
        "max_receipt_bytes",
        "max_artifact_files",
        "max_total_bytes",
        "min_artifact_free_bytes",
    }
)
_FORBIDDEN_FIELD_WORDS = frozenset(
    {
        "action",
        "api",
        "auth",
        "bearer",
        "command",
        "credential",
        "endpoint",
        "header",
        "key",
        "mutation",
        "password",
        "provider",
        "remediation",
        "secret",
        "shell",
        "subprocess",
        "token",
        "url",
        "webhook",
    }
)
_UNSAFE_VALUE_RE = re.compile(
    r"(?:https?://|wss?://|@|\+?[0-9][0-9 ()-]{7,}|\$\{|\benv(?:ironment)?\b|"
    r"\b(?:api[-_]?key|auth|bearer|credential|password|provider|secret|token|webhook|"
    r"command|shell|subprocess|remediation|mutation)\b)",
    re.IGNORECASE,
)
_LOCAL_LABEL_RE = re.compile(r"[a-z0-9][a-z0-9_.:-]{0,63}\Z")
_UNSAFE_LABEL_WORDS = frozenset(
    {
        "action",
        "approval",
        "email",
        "pagerduty",
        "phone",
        "post",
        "provider",
        "publish",
        "remediation",
        "send",
        "slack",
        "sms",
        "ticket",
        "webhook",
    }
)
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_TRANSITIONS = frozenset({"opened", "updated", "reminder", "recovered"})
_ENVELOPE_FIELDS = frozenset(
    {
        "schema_version",
        "envelope_id",
        "attempt_id",
        "simulator_id",
        "destination_id",
        "template_version",
        "config_hash",
        "source_event",
        "message",
        "authority_counters",
        "envelope_hash",
    }
)
_SOURCE_EVENT_FIELDS = frozenset(
    {
        "event_id",
        "event_hash",
        "incident_id",
        "sequence",
        "transition_kind",
        "occurred_at",
        "reason",
        "healthy",
        "state_hash",
        "snapshot_fingerprint",
    }
)
_MESSAGE_FIELDS = frozenset({"title", "summary", "evidence_refs"})
_RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "attempt_id",
        "envelope_id",
        "envelope_hash",
        "event_id",
        "event_hash",
        "destination_id",
        "processed_at",
        "simulated",
        "delivered",
        "acknowledged",
        "authority_counters",
        "receipt_hash",
    }
)
_CURSOR_FIELDS = frozenset(
    {
        "schema_version",
        "config_hash",
        "last_sequence",
        "last_event_id",
        "last_event_hash",
        "last_processed_at",
        "authority_counters",
        "cursor_hash",
    }
)


class NotificationAuthorityError(ValueError):
    """Raised whenever P141 cannot prove its local simulated boundary."""


@dataclass(frozen=True)
class NotificationConfig:
    schema_version: str
    config_hash: str
    simulator_id: str
    allowed_artifact_roots: tuple[Path, ...]
    p133_config_path: Path
    p133_config: DeadmanConfig
    envelope_dir: Path
    receipt_dir: Path
    cursor_path: Path
    lease_path: Path
    destination_ids: tuple[str, ...]
    transition_kinds: tuple[str, ...]
    template_version: str
    poll_interval_seconds: int
    max_envelope_bytes: int
    max_receipt_bytes: int
    max_artifact_files: int
    max_total_bytes: int
    min_artifact_free_bytes: int


def zero_notification_authority_counters() -> dict[str, int]:
    return {key: 0 for key in FORBIDDEN_AUTHORITY_COUNTER_KEYS}


def load_notification_config(path: Path | str) -> NotificationConfig:
    """Load a schema-closed, explicit-path, local simulator configuration."""

    config_path = _absolute(Path(path).expanduser())
    _reject_symlink_components(config_path)
    _regular_file_stat(config_path, "configuration")
    raw = _read_json(config_path, "configuration")
    if set(raw) != _CONFIG_FIELDS:
        unknown = set(raw) - _CONFIG_FIELDS
        if any(_field_is_forbidden(item) for item in unknown):
            raise NotificationAuthorityError("forbidden_configuration_field")
        raise NotificationAuthorityError("invalid_configuration_fields")
    if raw.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise NotificationAuthorityError("invalid_configuration_schema")
    _reject_unsafe_values(raw)

    roots_raw = raw.get("allowed_artifact_roots")
    if not _sequence(roots_raw) or not roots_raw:
        raise NotificationAuthorityError("allowed_artifact_roots_required")
    roots = tuple(_resolve(config_path.parent, item) for item in roots_raw)
    if len(set(roots)) != len(roots):
        raise NotificationAuthorityError("duplicate_allowed_artifact_root")
    for root in roots:
        _reject_symlink_components(root)
        root.mkdir(parents=True, exist_ok=True)
        if not root.is_dir():
            raise NotificationAuthorityError("allowed_root_not_directory")

    p133_config_path = _resolve(config_path.parent, raw.get("p133_config_path"))
    envelope_dir = _resolve(config_path.parent, raw.get("envelope_dir"))
    receipt_dir = _resolve(config_path.parent, raw.get("receipt_dir"))
    cursor_path = _resolve(config_path.parent, raw.get("cursor_path"))
    lease_path = cursor_path.with_name(f".{cursor_path.name}.lock")
    paths = (p133_config_path, envelope_dir, receipt_dir, cursor_path, lease_path)
    for candidate in paths:
        _reject_symlink_components(candidate)
        if not any(candidate == root or candidate.is_relative_to(root) for root in roots):
            raise NotificationAuthorityError("path_outside_allowed_roots")
    _require_distinct_output_paths(envelope_dir, receipt_dir, cursor_path, lease_path)

    destinations = _closed_labels(raw.get("destination_ids"), label="destination_id")
    transitions = _closed_labels(raw.get("transition_kinds"), label="transition_kind")
    if not set(transitions).issubset(_TRANSITIONS):
        raise NotificationAuthorityError("unsafe_transition_kind")
    simulator_id = _safe_label(raw.get("simulator_id"), "simulator_id")
    template_version = _safe_label(raw.get("template_version"), "template_version")
    integers = {
        key: _positive_int(raw, key)
        for key in (
            "poll_interval_seconds",
            "max_envelope_bytes",
            "max_receipt_bytes",
            "max_artifact_files",
            "max_total_bytes",
            "min_artifact_free_bytes",
        )
    }
    if integers["max_envelope_bytes"] > integers["max_total_bytes"] or integers["max_receipt_bytes"] > integers["max_total_bytes"]:
        raise NotificationAuthorityError("per_artifact_budget_exceeds_total")
    p133_config = load_deadman_config(p133_config_path)
    for p133_owned in (p133_config.outbox_dir, p133_config.cursor_path, p133_config.ack_dir, p133_config.lease_path):
        for p141_owned in (envelope_dir, receipt_dir, cursor_path, lease_path):
            if _overlaps(p133_owned, p141_owned):
                raise NotificationAuthorityError("p133_p141_path_overlap")
    return NotificationConfig(
        schema_version=CONFIG_SCHEMA_VERSION,
        config_hash=stable_hash(raw),
        simulator_id=simulator_id,
        allowed_artifact_roots=roots,
        p133_config_path=p133_config_path,
        p133_config=p133_config,
        envelope_dir=envelope_dir,
        receipt_dir=receipt_dir,
        cursor_path=cursor_path,
        lease_path=lease_path,
        destination_ids=destinations,
        transition_kinds=transitions,
        template_version=template_version,
        **integers,
    )


def process_pending_notifications(
    config: NotificationConfig,
    *,
    now: datetime | Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Create durable local simulated artifacts for every pending P133 event."""

    observed_at = _utc(now() if callable(now) else now or datetime.now(UTC))
    with _NotificationLease(config):
        _ensure_output_dirs(config)
        cursor = _load_cursor(config)
        _validate_clock(cursor, observed_at)
        events = list_outbox(config.p133_config)
        _validate_event_chain(events, cursor)
        _validate_completed_attempts(config, events, cursor)
        pending = [event for event in events if int(event["sequence"]) > int(cursor["last_sequence"])]
        processed = 0
        attempts = 0
        replayed = 0
        current = cursor
        for event in pending:
            if event["transition_kind"] not in config.transition_kinds:
                raise NotificationAuthorityError("transition_not_allowed")
            _preflight_event_budget(config, event)
            event_replayed = 0
            for destination_id in config.destination_ids:
                was_replayed = _persist_attempt(config, event, destination_id, observed_at)
                attempts += 0 if was_replayed else 1
                event_replayed += int(was_replayed)
            current = _cursor_for_event(config, event, observed_at)
            _write_cursor(config.cursor_path, current, config.allowed_artifact_roots)
            processed += 1
            replayed += event_replayed
        return _run_result(config, current, processed=processed, attempts=attempts, replayed=replayed, observed_at=observed_at)


def list_notification_envelopes(config: NotificationConfig) -> list[dict[str, Any]]:
    with _NotificationLease(config):
        events = list_outbox(config.p133_config)
        cursor = _load_cursor(config)
        _validate_event_chain(events, cursor)
        items = _load_artifact_directory(config.envelope_dir, _validate_envelope, config=config, kind="envelope")
        expected = _expected_envelopes(config, events)
        for item in items:
            attempt_id = str(item["attempt_id"])
            if attempt_id not in expected or item != expected[attempt_id]:
                raise NotificationAuthorityError("envelope_not_backed_by_p133")
        return items


def list_simulated_receipts(config: NotificationConfig) -> list[dict[str, Any]]:
    with _NotificationLease(config):
        events = list_outbox(config.p133_config)
        cursor = _load_cursor(config)
        _validate_event_chain(events, cursor)
        envelopes = _load_artifact_directory(config.envelope_dir, _validate_envelope, config=config, kind="envelope")
        receipts = _load_artifact_directory(config.receipt_dir, _validate_receipt, config=config, kind="receipt")
        expected = _expected_envelopes(config, events)
        actual_envelopes = {str(item["attempt_id"]): item for item in envelopes}
        for attempt_id, envelope in actual_envelopes.items():
            if attempt_id not in expected or envelope != expected[attempt_id]:
                raise NotificationAuthorityError("envelope_not_backed_by_p133")
        events_by_id = {str(event["event_id"]): event for event in events}
        for receipt in receipts:
            attempt_id = str(receipt["attempt_id"])
            receipt_envelope = actual_envelopes.get(attempt_id)
            event = events_by_id.get(str(receipt["event_id"]))
            if receipt_envelope is None or event is None or not _receipt_matches(receipt, receipt_envelope, event, str(receipt["destination_id"])):
                raise NotificationAuthorityError("receipt_not_backed_by_p133")
        return receipts


def _expected_envelopes(
    config: NotificationConfig, events: Sequence[Mapping[str, Any]]
) -> dict[str, dict[str, Any]]:
    expected: dict[str, dict[str, Any]] = {}
    for event in events:
        if event["transition_kind"] not in config.transition_kinds:
            continue
        for destination_id in config.destination_ids:
            envelope = _build_envelope(config, event, destination_id)
            expected[str(envelope["attempt_id"])] = envelope
    return expected


def _persist_attempt(config: NotificationConfig, event: Mapping[str, Any], destination_id: str, now: datetime) -> bool:
    envelope = _build_envelope(config, event, destination_id)
    attempt_id = str(envelope["attempt_id"])
    envelope_path = config.envelope_dir / f"{attempt_id}.json"
    receipt_path = config.receipt_dir / f"{attempt_id}.json"
    replayed = False
    if (receipt_path.exists() or receipt_path.is_symlink()) and not (envelope_path.exists() or envelope_path.is_symlink()):
        raise NotificationAuthorityError("receipt_without_envelope")
    if envelope_path.exists() or envelope_path.is_symlink():
        existing_envelope = _read_json(envelope_path, "envelope")
        _validate_envelope(existing_envelope, config)
        if existing_envelope != envelope:
            raise NotificationAuthorityError("conflicting_existing_envelope")
        replayed = True
    else:
        _reserve_budget(config, envelope)
        _atomic_write_json(envelope_path, envelope, config.allowed_artifact_roots)

    if receipt_path.exists() or receipt_path.is_symlink():
        receipt = _read_json(receipt_path, "receipt")
        _validate_receipt(receipt, config)
        if not _receipt_matches(receipt, envelope, event, destination_id):
            raise NotificationAuthorityError("conflicting_existing_receipt")
        return True

    receipt = _build_receipt(envelope, event, destination_id, now)
    _reserve_budget(config, receipt)
    _atomic_write_json(receipt_path, receipt, config.allowed_artifact_roots)
    return replayed


def _preflight_event_budget(config: NotificationConfig, event: Mapping[str, Any]) -> None:
    """Reserve the whole event batch before the first destination write."""

    required_bytes = 0
    required_files = 0
    probe_time = _parse_timestamp(event["occurred_at"])
    for destination_id in config.destination_ids:
        envelope = _build_envelope(config, event, destination_id)
        attempt_id = str(envelope["attempt_id"])
        envelope_path = config.envelope_dir / f"{attempt_id}.json"
        receipt_path = config.receipt_dir / f"{attempt_id}.json"
        if not envelope_path.exists() and not envelope_path.is_symlink():
            required_files += 1
            required_bytes += len(_json_bytes(envelope))
        if not receipt_path.exists() and not receipt_path.is_symlink():
            required_files += 1
            required_bytes += len(_json_bytes(_build_receipt(envelope, event, destination_id, probe_time)))
    file_count, total_bytes = _artifact_usage(config)
    if file_count + required_files > config.max_artifact_files or total_bytes + required_bytes > config.max_total_bytes:
        raise NotificationAuthorityError("artifact_budget_exhausted")
    if shutil.disk_usage(config.cursor_path.parent).free < config.min_artifact_free_bytes + required_bytes:
        raise NotificationAuthorityError("insufficient_artifact_space")


def _validate_completed_attempts(
    config: NotificationConfig, events: Sequence[Mapping[str, Any]], cursor: Mapping[str, Any]
) -> None:
    """Prove the cursor cannot skip missing or conflicting destination artifacts."""

    last_sequence = int(cursor["last_sequence"])
    for event in events[:last_sequence]:
        for destination_id in config.destination_ids:
            envelope = _build_envelope(config, event, destination_id)
            attempt_id = str(envelope["attempt_id"])
            envelope_path = config.envelope_dir / f"{attempt_id}.json"
            receipt_path = config.receipt_dir / f"{attempt_id}.json"
            if not envelope_path.exists() or not receipt_path.exists():
                raise NotificationAuthorityError("cursor_artifact_missing")
            existing_envelope = _read_json(envelope_path, "envelope")
            _validate_envelope(existing_envelope, config)
            if existing_envelope != envelope:
                raise NotificationAuthorityError("cursor_envelope_binding_invalid")
            receipt = _read_json(receipt_path, "receipt")
            _validate_receipt(receipt, config)
            if not _receipt_matches(receipt, envelope, event, destination_id):
                raise NotificationAuthorityError("cursor_receipt_binding_invalid")


def _build_envelope(config: NotificationConfig, event: Mapping[str, Any], destination_id: str) -> dict[str, Any]:
    source = {
        "event_id": event["event_id"],
        "event_hash": event["event_hash"],
        "incident_id": event["incident_id"],
        "sequence": event["sequence"],
        "transition_kind": event["transition_kind"],
        "occurred_at": event["occurred_at"],
        "reason": event["snapshot"]["reason"],
        "healthy": event["snapshot"]["healthy"],
        "state_hash": event["snapshot"]["state_hash"],
        "snapshot_fingerprint": event["snapshot"]["snapshot_fingerprint"],
    }
    attempt_id = stable_hash(
        {
            "config_hash": config.config_hash,
            "event_hash": event["event_hash"],
            "destination_id": destination_id,
            "template_version": config.template_version,
        }
    )
    envelope: dict[str, Any] = {
        "schema_version": ENVELOPE_SCHEMA_VERSION,
        "envelope_id": stable_hash({"attempt_id": attempt_id, "source_event": source}),
        "attempt_id": attempt_id,
        "simulator_id": config.simulator_id,
        "destination_id": destination_id,
        "template_version": config.template_version,
        "config_hash": config.config_hash,
        "source_event": source,
        "message": {
            "title": f"OpsCat incident {event['transition_kind']}",
            "summary": f"Incident {event['incident_id']} is {event['transition_kind']} because {event['snapshot']['reason']}.",
            "evidence_refs": [event["event_id"], event["event_hash"], event["snapshot"]["snapshot_fingerprint"]],
        },
        "authority_counters": zero_notification_authority_counters(),
    }
    envelope["envelope_hash"] = stable_hash(envelope)
    _validate_envelope(envelope, config)
    return envelope


def _build_receipt(
    envelope: Mapping[str, Any], event: Mapping[str, Any], destination_id: str, now: datetime
) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "attempt_id": envelope["attempt_id"],
        "envelope_id": envelope["envelope_id"],
        "envelope_hash": envelope["envelope_hash"],
        "event_id": event["event_id"],
        "event_hash": event["event_hash"],
        "destination_id": destination_id,
        "processed_at": _timestamp(now),
        "simulated": True,
        "delivered": False,
        "acknowledged": False,
        "authority_counters": zero_notification_authority_counters(),
    }
    receipt["receipt_hash"] = stable_hash(receipt)
    return receipt


def _receipt_matches(
    receipt: Mapping[str, Any], envelope: Mapping[str, Any], event: Mapping[str, Any], destination_id: str
) -> bool:
    expected = {
        "attempt_id": envelope["attempt_id"],
        "envelope_id": envelope["envelope_id"],
        "envelope_hash": envelope["envelope_hash"],
        "event_id": event["event_id"],
        "event_hash": event["event_hash"],
        "destination_id": destination_id,
        "simulated": True,
        "delivered": False,
        "acknowledged": False,
        "authority_counters": zero_notification_authority_counters(),
    }
    return all(receipt.get(key) == value for key, value in expected.items())


def _validate_envelope(value: Mapping[str, Any], config: NotificationConfig) -> None:
    if set(value) != _ENVELOPE_FIELDS or value.get("schema_version") != ENVELOPE_SCHEMA_VERSION:
        raise NotificationAuthorityError("invalid_envelope_fields")
    if value.get("config_hash") != config.config_hash or value.get("simulator_id") != config.simulator_id:
        raise NotificationAuthorityError("envelope_config_mismatch")
    if value.get("destination_id") not in config.destination_ids or value.get("template_version") != config.template_version:
        raise NotificationAuthorityError("envelope_contract_invalid")
    source = value.get("source_event")
    message = value.get("message")
    if not isinstance(source, Mapping) or set(source) != _SOURCE_EVENT_FIELDS:
        raise NotificationAuthorityError("invalid_envelope_source")
    if not isinstance(message, Mapping) or set(message) != _MESSAGE_FIELDS:
        raise NotificationAuthorityError("invalid_envelope_message")
    if not all(_SHA256_RE.fullmatch(str(source.get(key, ""))) for key in ("event_id", "event_hash", "incident_id", "snapshot_fingerprint")):
        raise NotificationAuthorityError("invalid_envelope_source_hash")
    state_hash = source.get("state_hash")
    if state_hash is not None and not _SHA256_RE.fullmatch(str(state_hash)):
        raise NotificationAuthorityError("invalid_envelope_state_hash")
    if source.get("transition_kind") not in config.transition_kinds or source.get("reason") not in {
        "heartbeat_current",
        "runtime_stopped",
        "heartbeat_stale",
        "state_missing",
        "heartbeat_invalid",
        "state_invalid",
        "watchdog_contract_invalid",
    }:
        raise NotificationAuthorityError("invalid_envelope_source_value")
    expected_attempt_id = stable_hash(
        {
            "config_hash": config.config_hash,
            "event_hash": source["event_hash"],
            "destination_id": value["destination_id"],
            "template_version": config.template_version,
        }
    )
    expected_envelope_id = stable_hash({"attempt_id": expected_attempt_id, "source_event": dict(source)})
    expected_message = {
        "title": f"OpsCat incident {source['transition_kind']}",
        "summary": f"Incident {source['incident_id']} is {source['transition_kind']} because {source['reason']}.",
        "evidence_refs": [source["event_id"], source["event_hash"], source["snapshot_fingerprint"]],
    }
    if value.get("attempt_id") != expected_attempt_id or value.get("envelope_id") != expected_envelope_id or dict(message) != expected_message:
        raise NotificationAuthorityError("envelope_contract_invalid")
    _parse_timestamp(source.get("occurred_at"))
    _validate_zero_authority(value.get("authority_counters"))
    if value.get("envelope_hash") != stable_hash({key: item for key, item in value.items() if key != "envelope_hash"}):
        raise NotificationAuthorityError("envelope_hash_invalid")
    if not _SHA256_RE.fullmatch(str(value.get("attempt_id", ""))) or not _SHA256_RE.fullmatch(str(value.get("envelope_id", ""))):
        raise NotificationAuthorityError("invalid_envelope_identity")
    if len(_json_bytes(value)) > config.max_envelope_bytes:
        raise NotificationAuthorityError("envelope_size_exceeded")


def _validate_receipt(value: Mapping[str, Any], config: NotificationConfig) -> None:
    if set(value) != _RECEIPT_FIELDS or value.get("schema_version") != RECEIPT_SCHEMA_VERSION:
        raise NotificationAuthorityError("invalid_receipt_fields")
    for key in ("attempt_id", "envelope_id", "envelope_hash", "event_id", "event_hash", "receipt_hash"):
        if not _SHA256_RE.fullmatch(str(value.get(key, ""))):
            raise NotificationAuthorityError("invalid_receipt_hash")
    if value.get("destination_id") not in config.destination_ids:
        raise NotificationAuthorityError("receipt_destination_invalid")
    if value.get("simulated") is not True or value.get("delivered") is not False or value.get("acknowledged") is not False:
        raise NotificationAuthorityError("receipt_contract_invalid")
    _parse_timestamp(value.get("processed_at"))
    _validate_zero_authority(value.get("authority_counters"))
    if value.get("receipt_hash") != stable_hash({key: item for key, item in value.items() if key != "receipt_hash"}):
        raise NotificationAuthorityError("receipt_hash_invalid")
    if len(_json_bytes(value)) > config.max_receipt_bytes:
        raise NotificationAuthorityError("receipt_size_exceeded")


def _validate_event_chain(events: Sequence[Mapping[str, Any]], cursor: Mapping[str, Any]) -> None:
    expected_sequence = 1
    previous_by_incident: dict[str, str] = {}
    for event in events:
        sequence = int(event["sequence"])
        if sequence != expected_sequence:
            raise NotificationAuthorityError("p133_event_sequence_gap")
        incident_id = str(event["incident_id"])
        transition = str(event["transition_kind"])
        previous = event.get("previous_event_id")
        if transition == "opened":
            if previous is not None:
                raise NotificationAuthorityError("p133_event_chain_invalid")
        elif previous_by_incident.get(incident_id) != previous:
            raise NotificationAuthorityError("p133_event_chain_invalid")
        previous_by_incident[incident_id] = str(event["event_id"])
        expected_sequence += 1
    last_sequence = int(cursor["last_sequence"])
    if last_sequence > len(events):
        raise NotificationAuthorityError("cursor_sequence_ahead")
    if last_sequence:
        event = events[last_sequence - 1]
        if cursor.get("last_event_id") != event.get("event_id") or cursor.get("last_event_hash") != event.get("event_hash"):
            raise NotificationAuthorityError("cursor_event_binding_invalid")


def _load_cursor(config: NotificationConfig) -> dict[str, Any]:
    if not config.cursor_path.exists() and not config.cursor_path.is_symlink():
        return {
            "schema_version": CURSOR_SCHEMA_VERSION,
            "config_hash": config.config_hash,
            "last_sequence": 0,
            "last_event_id": None,
            "last_event_hash": None,
            "last_processed_at": None,
            "authority_counters": zero_notification_authority_counters(),
            "cursor_hash": stable_hash(
                {
                    "schema_version": CURSOR_SCHEMA_VERSION,
                    "config_hash": config.config_hash,
                    "last_sequence": 0,
                    "last_event_id": None,
                    "last_event_hash": None,
                    "last_processed_at": None,
                    "authority_counters": zero_notification_authority_counters(),
                }
            ),
        }
    value = _read_json(config.cursor_path, "cursor")
    if set(value) != _CURSOR_FIELDS or value.get("schema_version") != CURSOR_SCHEMA_VERSION:
        raise NotificationAuthorityError("invalid_cursor_fields")
    if value.get("config_hash") != config.config_hash:
        raise NotificationAuthorityError("cursor_config_mismatch")
    if type(value.get("last_sequence")) is not int or value["last_sequence"] < 0:
        raise NotificationAuthorityError("invalid_cursor_sequence")
    if value.get("last_processed_at") is not None:
        _parse_timestamp(value["last_processed_at"])
    _validate_zero_authority(value.get("authority_counters"))
    if value.get("cursor_hash") != stable_hash({key: item for key, item in value.items() if key != "cursor_hash"}):
        raise NotificationAuthorityError("cursor_hash_invalid")
    return value


def _cursor_for_event(config: NotificationConfig, event: Mapping[str, Any], now: datetime) -> dict[str, Any]:
    cursor: dict[str, Any] = {
        "schema_version": CURSOR_SCHEMA_VERSION,
        "config_hash": config.config_hash,
        "last_sequence": event["sequence"],
        "last_event_id": event["event_id"],
        "last_event_hash": event["event_hash"],
        "last_processed_at": _timestamp(now),
        "authority_counters": zero_notification_authority_counters(),
    }
    cursor["cursor_hash"] = stable_hash(cursor)
    return cursor


def _run_result(
    config: NotificationConfig,
    cursor: Mapping[str, Any],
    *,
    processed: int,
    attempts: int,
    replayed: int,
    observed_at: datetime,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": RUN_SCHEMA_VERSION,
        "simulator_id": config.simulator_id,
        "config_hash": config.config_hash,
        "observed_at": _timestamp(observed_at),
        "processed_event_count": processed,
        "simulated_attempt_count": attempts,
        "replayed_attempt_count": replayed,
        "last_sequence": cursor["last_sequence"],
        "simulated": True,
        "delivered_count": 0,
        "acknowledged_count": 0,
        "authority_counters": zero_notification_authority_counters(),
    }
    result["run_hash"] = stable_hash(result)
    return result


class _NotificationLease:
    def __init__(self, config: NotificationConfig) -> None:
        self.config = config
        self.handle: Any = None

    def __enter__(self) -> None:
        parent_fd, name = _open_artifact_parent(self.config.lease_path, create=True)
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        try:
            fd = os.open(name, flags, 0o600, dir_fd=parent_fd)
        finally:
            os.close(parent_fd)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            os.close(fd)
            raise NotificationAuthorityError("notification_lease_not_regular")
        self.handle = os.fdopen(fd, "a+", encoding="utf-8")
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self.handle.close()
            self.handle = None
            raise NotificationAuthorityError("notification_lease_unavailable") from exc

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self.handle is not None:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()


def _load_artifact_directory(
    directory: Path,
    validator: Callable[[Mapping[str, Any], NotificationConfig], None],
    *,
    config: NotificationConfig,
    kind: str,
) -> list[dict[str, Any]]:
    if not directory.exists() and not directory.is_symlink():
        return []
    directory_fd = _open_directory_tree(directory, create=False)
    result: list[dict[str, Any]] = []
    try:
        for name in sorted(os.listdir(directory_fd)):
            path = Path(name)
            if not name.endswith(".json") or not _SHA256_RE.fullmatch(path.stem):
                raise NotificationAuthorityError(f"invalid_{kind}_filename")
            value = _read_json_at(directory_fd, name, kind)
            validator(value, config)
            if value.get("attempt_id") != path.stem:
                raise NotificationAuthorityError(f"{kind}_filename_mismatch")
            result.append(value)
    finally:
        os.close(directory_fd)
    return result


def _ensure_output_dirs(config: NotificationConfig) -> None:
    for directory in (config.envelope_dir, config.receipt_dir, config.cursor_path.parent):
        directory_fd = _open_directory_tree(directory, create=True)
        os.close(directory_fd)


def _reserve_budget(config: NotificationConfig, value: object) -> None:
    data_size = len(_json_bytes(value))
    file_count, total_bytes = _artifact_usage(config)
    if file_count + 1 > config.max_artifact_files or total_bytes + data_size > config.max_total_bytes:
        raise NotificationAuthorityError("artifact_budget_exhausted")
    if shutil.disk_usage(config.cursor_path.parent).free < config.min_artifact_free_bytes + data_size:
        raise NotificationAuthorityError("insufficient_artifact_space")


def _artifact_usage(config: NotificationConfig) -> tuple[int, int]:
    file_count = 0
    total_bytes = 0
    for directory in (config.envelope_dir, config.receipt_dir):
        directory_fd = _open_directory_tree(directory, create=False)
        try:
            for name in os.listdir(directory_fd):
                try:
                    info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                except OSError as exc:
                    raise NotificationAuthorityError("artifact_missing") from exc
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise NotificationAuthorityError("artifact_not_regular")
                file_count += 1
                total_bytes += info.st_size
        finally:
            os.close(directory_fd)
    return file_count, total_bytes


def _write_cursor(path: Path, value: Mapping[str, Any], roots: Sequence[Path]) -> None:
    _atomic_write_json(path, value, roots)


def _atomic_write_json(path: Path, value: object, roots: Sequence[Path]) -> None:
    if not any(path.is_relative_to(root) for root in roots):
        raise NotificationAuthorityError("write_path_outside_roots")
    data = _json_bytes(value)
    parent_fd, name = _open_artifact_parent(path, create=True)
    temporary = f".{name}.{os.getpid()}.{time.monotonic_ns()}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    fd = -1
    try:
        try:
            current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            current = None
        if current is not None and (not stat.S_ISREG(current.st_mode) or current.st_nlink != 1):
            raise NotificationAuthorityError("write_target_not_regular")
        fd = os.open(temporary, flags, 0o600, dir_fd=parent_fd)
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        temporary = ""
        os.fsync(parent_fd)
    finally:
        if fd >= 0:
            os.close(fd)
        if temporary:
            try:
                os.unlink(temporary, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
        os.close(parent_fd)


def _read_json(path: Path, kind: str) -> dict[str, Any]:
    parent_fd, name = _open_artifact_parent(path, create=False)
    try:
        return _read_json_at(parent_fd, name, kind)
    finally:
        os.close(parent_fd)


def _read_json_at(parent_fd: int, name: str, kind: str) -> dict[str, Any]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(name, flags, dir_fd=parent_fd)
    except OSError as exc:
        raise NotificationAuthorityError(f"{kind}_missing_or_unsafe") from exc
    try:
        info_before = os.fstat(fd)
        if not stat.S_ISREG(info_before.st_mode) or info_before.st_nlink != 1:
            raise NotificationAuthorityError(f"{kind}_not_regular")
        with os.fdopen(fd, "rb") as handle:
            fd = -1
            data = handle.read(MAX_LOCAL_JSON_BYTES + 1)
            info_after = os.fstat(handle.fileno())
        if len(data) > MAX_LOCAL_JSON_BYTES:
            raise NotificationAuthorityError(f"{kind}_size_exceeded")
        if (info_before.st_dev, info_before.st_ino, info_before.st_size, info_before.st_mtime_ns) != (
            info_after.st_dev,
            info_after.st_ino,
            info_after.st_size,
            info_after.st_mtime_ns,
        ):
            raise NotificationAuthorityError(f"{kind}_changed_during_read")
        try:
            value = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise NotificationAuthorityError(f"invalid_{kind}_json") from exc
        if not isinstance(value, dict):
            raise NotificationAuthorityError(f"invalid_{kind}_shape")
        return value
    finally:
        if fd >= 0:
            os.close(fd)


def _open_artifact_parent(path: Path, *, create: bool) -> tuple[int, str]:
    if not path.is_absolute() or not path.name:
        raise NotificationAuthorityError("artifact_path_invalid")
    return _open_directory_tree(path.parent, create=create), path.name


def _open_directory_tree(path: Path, *, create: bool) -> int:
    if not path.is_absolute():
        raise NotificationAuthorityError("directory_path_not_absolute")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(path.anchor, flags)
    except OSError as exc:
        raise NotificationAuthorityError("directory_root_invalid") from exc
    try:
        for part in path.parts[1:]:
            try:
                next_fd = os.open(part, flags, dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    raise NotificationAuthorityError("directory_missing") from None
                try:
                    os.mkdir(part, 0o700, dir_fd=fd)
                    next_fd = os.open(part, flags, dir_fd=fd)
                except OSError as exc:
                    raise NotificationAuthorityError("directory_create_failed") from exc
            except OSError as exc:
                raise NotificationAuthorityError("directory_component_unsafe") from exc
            os.close(fd)
            fd = next_fd
        info = os.fstat(fd)
        if not stat.S_ISDIR(info.st_mode):
            raise NotificationAuthorityError("directory_not_directory")
        return fd
    except Exception:
        os.close(fd)
        raise


def _regular_file_stat(path: Path, kind: str) -> os.stat_result:
    try:
        info = os.lstat(path)
    except OSError as exc:
        raise NotificationAuthorityError(f"{kind}_missing") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise NotificationAuthorityError(f"{kind}_not_regular")
    if info.st_nlink != 1:
        raise NotificationAuthorityError(f"{kind}_has_multiple_links")
    return info


def _directory_stat(path: Path, kind: str) -> os.stat_result:
    try:
        info = os.lstat(path)
    except OSError as exc:
        raise NotificationAuthorityError(f"{kind}_directory_missing") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise NotificationAuthorityError(f"{kind}_not_directory")
    return info


def _reject_symlink_components(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode):
            raise NotificationAuthorityError("path_has_symlink_component")


def _closed_labels(value: Any, *, label: str) -> tuple[str, ...]:
    if not _sequence(value) or not value:
        raise NotificationAuthorityError(f"{label}_list_required")
    labels = tuple(_safe_label(item, label) for item in value)
    if len(set(labels)) != len(labels):
        raise NotificationAuthorityError(f"duplicate_{label}")
    return labels


def _safe_label(value: Any, label: str) -> str:
    words = set(re.split(r"[^a-z0-9]+", value.lower())) if isinstance(value, str) else set()
    if (
        not isinstance(value, str)
        or not _LOCAL_LABEL_RE.fullmatch(value)
        or _UNSAFE_VALUE_RE.search(value)
        or bool(words & _UNSAFE_LABEL_WORDS)
    ):
        raise NotificationAuthorityError(f"unsafe_{label}")
    return value


def _positive_int(raw: Mapping[str, Any], key: str) -> int:
    value = raw.get(key)
    if type(value) is not int or value <= 0 or value > 1_099_511_627_776:
        raise NotificationAuthorityError(f"invalid_positive_integer:{key}")
    return value


def _reject_unsafe_values(raw: Mapping[str, Any]) -> None:
    def walk(value: Any) -> None:
        if isinstance(value, str) and _UNSAFE_VALUE_RE.search(value):
            raise NotificationAuthorityError("forbidden_configuration_value")
        if isinstance(value, Mapping):
            for key, item in value.items():
                if _field_is_forbidden(str(key)) and key not in _CONFIG_FIELDS:
                    raise NotificationAuthorityError("forbidden_configuration_field")
                walk(item)
        elif _sequence(value):
            for item in value:
                walk(item)

    walk(raw)


def _field_is_forbidden(value: str) -> bool:
    words = {word for word in re.split(r"[^a-z0-9]+", value.lower()) if word}
    return bool(words & _FORBIDDEN_FIELD_WORDS)


def _require_distinct_output_paths(*paths: Path) -> None:
    for index, left in enumerate(paths):
        for right in paths[index + 1 :]:
            if _overlaps(left, right):
                raise NotificationAuthorityError("p141_artifact_paths_overlap")


def _overlaps(left: Path, right: Path) -> bool:
    return left == right or left.is_relative_to(right) or right.is_relative_to(left)


def _resolve(base: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise NotificationAuthorityError("invalid_local_path")
    candidate = Path(value).expanduser()
    return _absolute(candidate if candidate.is_absolute() else base / candidate)


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(path))


def _sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _validate_zero_authority(value: Any) -> None:
    if not isinstance(value, Mapping) or set(value) != set(FORBIDDEN_AUTHORITY_COUNTER_KEYS):
        raise NotificationAuthorityError("authority_counters_invalid")
    if any(type(value[key]) is not int or value[key] != 0 for key in FORBIDDEN_AUTHORITY_COUNTER_KEYS):
        raise NotificationAuthorityError("authority_not_exact_zero")


def _validate_clock(cursor: Mapping[str, Any], now: datetime) -> None:
    previous = cursor.get("last_processed_at")
    if previous is not None and _parse_timestamp(previous).timestamp() - now.timestamp() > MAX_CLOCK_ROLLBACK_SECONDS:
        raise NotificationAuthorityError("clock_rollback_exceeds_tolerance")


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise NotificationAuthorityError("utc_timestamp_required")
    return value.astimezone(UTC)


def _timestamp(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise NotificationAuthorityError("invalid_timestamp")
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        return _utc(datetime.fromisoformat(candidate))
    except ValueError as exc:
        raise NotificationAuthorityError("invalid_timestamp") from exc


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


__all__ = [
    "CONFIG_FIELDS",
    "CONFIG_SCHEMA_VERSION",
    "CURSOR_FIELDS",
    "CURSOR_SCHEMA_VERSION",
    "ENVELOPE_FIELDS",
    "ENVELOPE_SCHEMA_VERSION",
    "FORBIDDEN_AUTHORITY_COUNTER_KEYS",
    "MESSAGE_FIELDS",
    "NotificationAuthorityError",
    "NotificationConfig",
    "RECEIPT_FIELDS",
    "RECEIPT_SCHEMA_VERSION",
    "RUN_SCHEMA_VERSION",
    "SOURCE_EVENT_FIELDS",
    "list_notification_envelopes",
    "list_simulated_receipts",
    "load_notification_config",
    "process_pending_notifications",
    "zero_notification_authority_counters",
]

# Public immutable schema contracts used by source-bound release validation.
CONFIG_FIELDS = _CONFIG_FIELDS
ENVELOPE_FIELDS = _ENVELOPE_FIELDS
SOURCE_EVENT_FIELDS = _SOURCE_EVENT_FIELDS
MESSAGE_FIELDS = _MESSAGE_FIELDS
RECEIPT_FIELDS = _RECEIPT_FIELDS
CURSOR_FIELDS = _CURSOR_FIELDS
