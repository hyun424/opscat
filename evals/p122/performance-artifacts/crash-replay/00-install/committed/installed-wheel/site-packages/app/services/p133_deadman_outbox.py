"""P133 local dead-man outbox core.

This module persists redacted local evidence when the independent P131 watchdog
reports that the monitor is unhealthy.  It has no delivery, command execution,
credential, network, or remediation authority.
"""

from __future__ import annotations

import errno
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
from typing import Any, Protocol, cast

from app.services.p110_evaluation import stable_hash
from app.services.p121_signals import P121_AUTHORITY_COUNTER_KEYS, zero_authority_counters

CONFIG_SCHEMA_VERSION = "p133.deadman_config.v1"
EVENT_SCHEMA_VERSION = "p133.deadman_event.v1"
CURSOR_SCHEMA_VERSION = "p133.deadman_cursor.v1"
ACK_SCHEMA_VERSION = "p133.deadman_ack.v1"
MAX_CLOCK_ROLLBACK_SECONDS = 5.0
MAX_CONFIG_INTEGER = 1_099_511_627_776
_SHA256_RE = re.compile(r"(?:sha256:)?[0-9a-f]{64}\Z")
_LOCAL_LABEL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:@+-]{0,127}\Z")
_CONFIG_FIELDS = frozenset(
    {
        "schema_version",
        "allowed_artifact_roots",
        "state_path",
        "outbox_dir",
        "cursor_path",
        "ack_dir",
        "runtime_ref",
        "check_interval_seconds",
        "heartbeat_timeout_seconds",
        "reminder_interval_seconds",
        "max_event_files",
        "max_outbox_bytes",
        "max_event_bytes",
        "min_artifact_free_bytes",
    }
)
_FORBIDDEN_FIELD_TOKENS = (
    "action",
    "api",
    "auth",
    "bearer",
    "command",
    "connector",
    "credential",
    "curl",
    "endpoint",
    "header",
    "http",
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
)
_FORBIDDEN_VALUE_RE = re.compile(
    r"(?:^|[^a-z0-9])(?:api[-_]?key|auth|bearer|credential|password|secret|token|webhook)(?:$|[^a-z0-9])",
    re.IGNORECASE,
)
NORMALIZED_REASONS = frozenset(
    {
        "heartbeat_current",
        "runtime_stopped",
        "heartbeat_stale",
        "state_missing",
        "heartbeat_invalid",
        "state_invalid",
        "watchdog_contract_invalid",
    }
)
_STATE_INVALID_REASONS = frozenset(
    {
        "state_invalid",
        "state_hash_invalid",
        "authority_not_exact_zero",
        "runtime_execution_boundary_violated",
        "invalid_source_state",
        "invalid_canary_state",
        "invalid_lifecycle_state",
        "source_manifest_mismatch",
        "invalid_timestamp",
    }
)
_HEARTBEAT_INVALID_REASONS = frozenset({"heartbeat_missing", "heartbeat_in_future"})
_TRANSITIONS = frozenset({"opened", "updated", "reminder", "recovered"})
_EVENT_FIELDS = frozenset(
    {
        "schema_version",
        "event_id",
        "incident_id",
        "sequence",
        "transition_kind",
        "occurred_at",
        "previous_event_id",
        "config_hash",
        "snapshot",
        "authority_counters",
        "event_hash",
    }
)
_SNAPSHOT_FIELDS = frozenset(
    {
        "reason",
        "healthy",
        "state_hash",
        "heartbeat_age_seconds",
        "runtime_ref_hash",
        "snapshot_fingerprint",
    }
)
_CURSOR_FIELDS = frozenset(
    {
        "schema_version",
        "config_hash",
        "next_sequence",
        "last_checked_at",
        "active_incident",
        "authority_counters",
        "cursor_hash",
    }
)
_ACTIVE_INCIDENT_FIELDS = frozenset(
    {
        "incident_id",
        "opened_at",
        "last_reason",
        "last_snapshot_fingerprint",
        "last_event_id",
        "last_emitted_at",
    }
)
_ACK_FIELDS = frozenset(
    {
        "schema_version",
        "event_id",
        "event_hash",
        "config_hash",
        "acknowledged_at",
        "authority_counters",
        "ack_hash",
    }
)


class P133DeadmanError(ValueError):
    """Raised when the P133 dead-man outbox fails closed."""


class P133DurabilityUncertainError(OSError):
    """Raised after replacement when directory durability cannot be proven."""


class WatchdogEvaluator(Protocol):
    def __call__(self, path: Path | str, *, now: datetime, heartbeat_timeout_seconds: int) -> Mapping[str, Any]:
        """Evaluate P131 watchdog liveness."""


@dataclass(frozen=True)
class DeadmanConfig:
    schema_version: str
    config_hash: str
    allowed_artifact_roots: tuple[Path, ...]
    state_path: Path
    outbox_dir: Path
    cursor_path: Path
    ack_dir: Path
    lease_path: Path
    runtime_ref_hash: str
    runtime_ref: str
    check_interval_seconds: int
    heartbeat_timeout_seconds: int
    reminder_interval_seconds: int
    max_event_files: int
    max_outbox_bytes: int
    max_event_bytes: int
    min_artifact_free_bytes: int


class _DeadmanLease:
    """Serialize every P133 read/write operation across local processes."""

    def __init__(self, config: DeadmanConfig) -> None:
        self.config = config
        self.handle: Any = None

    def __enter__(self) -> None:
        path = self.config.lease_path
        flags = (
            os.O_RDWR
            | os.O_CREAT
            | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        try:
            parent_fd, name = _open_artifact_parent(path, self.config.allowed_artifact_roots, create=True)
        except OSError as exc:
            raise P133DeadmanError("deadman_lease_invalid") from exc
        try:
            file_fd = os.open(name, flags, 0o600, dir_fd=parent_fd)
        except OSError as exc:
            raise P133DeadmanError("deadman_lease_invalid") from exc
        finally:
            os.close(parent_fd)
        info = os.fstat(file_fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            os.close(file_fd)
            raise P133DeadmanError("deadman_lease_not_regular")
        self.handle = os.fdopen(file_fd, "a+", encoding="utf-8")
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self.handle.close()
            self.handle = None
            raise P133DeadmanError("deadman_lease_unavailable") from exc
        self.handle.seek(0)
        self.handle.truncate()
        self.handle.write(json.dumps({"pid": os.getpid(), "runtime_ref_hash": self.config.runtime_ref_hash}, sort_keys=True) + "\n")
        self.handle.flush()
        os.fsync(self.handle.fileno())

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self.handle is not None:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


def load_deadman_config(path: Path | str) -> DeadmanConfig:
    """Load the closed, local-only P133 configuration."""

    config_input = Path(path).expanduser()
    if not config_input.is_absolute():
        config_input = Path.cwd() / config_input
    _reject_symlink_components(config_input)
    _regular_file_stat(config_input, "configuration")
    config_path = config_input.resolve()
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise P133DeadmanError("invalid_configuration_file") from exc
    if not isinstance(raw, Mapping):
        raise P133DeadmanError("invalid_configuration_shape")
    if raw.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise P133DeadmanError("invalid_configuration_schema")
    _reject_forbidden_fields(raw)
    if set(raw) - _CONFIG_FIELDS:
        raise P133DeadmanError("unknown_configuration_field")

    base = config_path.parent
    roots_value = raw.get("allowed_artifact_roots")
    if not _is_sequence(roots_value) or not roots_value:
        raise P133DeadmanError("allowed_artifact_roots_required")
    roots = tuple(_resolve_local_path(base, value) for value in roots_value)
    for root in roots:
        _reject_symlink_components(root)
        root.mkdir(parents=True, exist_ok=True)
        if not root.is_dir():
            raise P133DeadmanError("allowed_root_not_directory")

    state_path = _resolve_local_path(base, raw.get("state_path"))
    outbox_dir = _resolve_local_path(base, raw.get("outbox_dir"))
    cursor_path = _resolve_local_path(base, raw.get("cursor_path"))
    ack_dir = _resolve_local_path(base, raw.get("ack_dir"))
    lease_path = cursor_path.with_name(f".{cursor_path.name}.lock")
    for candidate in (state_path, outbox_dir, cursor_path, ack_dir, lease_path):
        _reject_symlink_components(candidate)
        if not any(_is_relative_to(candidate, root) for root in roots):
            raise P133DeadmanError("path_outside_allowed_roots")
    _require_pairwise_non_overlapping((state_path, outbox_dir, cursor_path, ack_dir, lease_path))

    runtime_ref = _required_text(raw, "runtime_ref")
    if not _LOCAL_LABEL_RE.fullmatch(runtime_ref) or _contains_forbidden_text(runtime_ref):
        raise P133DeadmanError("unsafe_runtime_ref")
    values = {
        key: _positive_int(raw, key)
        for key in (
            "check_interval_seconds",
            "heartbeat_timeout_seconds",
            "reminder_interval_seconds",
            "max_event_files",
            "max_outbox_bytes",
            "max_event_bytes",
            "min_artifact_free_bytes",
        )
    }
    if values["heartbeat_timeout_seconds"] < values["check_interval_seconds"]:
        raise P133DeadmanError("heartbeat_timeout_shorter_than_interval")
    if values["max_event_bytes"] > values["max_outbox_bytes"]:
        raise P133DeadmanError("max_event_bytes_exceeds_outbox_budget")

    config_hash = stable_hash(raw)
    return DeadmanConfig(
        schema_version=CONFIG_SCHEMA_VERSION,
        config_hash=config_hash,
        allowed_artifact_roots=roots,
        state_path=state_path,
        outbox_dir=outbox_dir,
        cursor_path=cursor_path,
        ack_dir=ack_dir,
        lease_path=lease_path,
        runtime_ref_hash=stable_hash({"runtime_ref": runtime_ref}),
        runtime_ref=runtime_ref,
        check_interval_seconds=values["check_interval_seconds"],
        heartbeat_timeout_seconds=values["heartbeat_timeout_seconds"],
        reminder_interval_seconds=values["reminder_interval_seconds"],
        max_event_files=values["max_event_files"],
        max_outbox_bytes=values["max_outbox_bytes"],
        max_event_bytes=values["max_event_bytes"],
        min_artifact_free_bytes=values["min_artifact_free_bytes"],
    )


def normalize_watchdog_result(result: Mapping[str, Any], *, config: DeadmanConfig) -> dict[str, Any]:
    """Map arbitrary P131 watchdog output into the seven-value P133 snapshot."""

    reason_value = result.get("reason") if isinstance(result, Mapping) else None
    healthy_value = result.get("healthy") if isinstance(result, Mapping) else None
    reason = "watchdog_contract_invalid"
    healthy = False
    if reason_value == "heartbeat_current" and healthy_value is True:
        reason = "heartbeat_current"
        healthy = True
    elif reason_value == "runtime_stopped" and healthy_value is False:
        reason = "runtime_stopped"
    elif reason_value == "heartbeat_stale" and healthy_value is False:
        reason = "heartbeat_stale"
    elif reason_value == "state_missing" and healthy_value is False:
        reason = "state_missing"
    elif reason_value in _HEARTBEAT_INVALID_REASONS and healthy_value is False:
        reason = "heartbeat_invalid"
    elif reason_value in _STATE_INVALID_REASONS and healthy_value is False:
        reason = "state_invalid"

    state_hash = result.get("state_hash")
    safe_state_hash = (
        state_hash
        if isinstance(state_hash, str)
        and state_hash.startswith("sha256:")
        and _SHA256_RE.fullmatch(state_hash)
        else None
    )
    age = _bounded_number(result.get("heartbeat_age_seconds"))
    snapshot: dict[str, Any] = {
        "reason": reason,
        "healthy": healthy,
        "state_hash": safe_state_hash,
        "heartbeat_age_seconds": age,
        "runtime_ref_hash": config.runtime_ref_hash,
    }
    snapshot["snapshot_fingerprint"] = _snapshot_fingerprint(snapshot)
    return snapshot


class DeadmanOutbox:
    """P133 runtime supporting one check and bounded/forever runs."""

    def __init__(
        self,
        config: DeadmanConfig,
        *,
        now: Callable[[], datetime] | None = None,
        sleep: Callable[[float], None] | None = None,
        watchdog_evaluator: WatchdogEvaluator | None = None,
    ) -> None:
        self.config = config
        clock = SystemClock()
        self._now = now or clock.now
        self._sleep = sleep or clock.sleep
        if watchdog_evaluator is None:
            from app.services.p131_always_on_monitor import evaluate_watchdog

            self._watchdog_evaluator: WatchdogEvaluator = evaluate_watchdog
        else:
            self._watchdog_evaluator = watchdog_evaluator

    def check_once(self) -> dict[str, Any]:
        """Run one watchdog check and persist an event if the transition requires it."""

        with _DeadmanLease(self.config):
            return self._check_once_locked()

    def _check_once_locked(self) -> dict[str, Any]:
        """Run one check while holding the process-wide P133 lease."""

        now = _require_utc(self._now())
        self._ensure_dirs()
        _ensure_artifact_space(self.config.outbox_dir, write_bytes=0, config=self.config)
        cursor = _load_cursor(self.config)
        self._validate_clock(cursor, now)
        self._validate_sequence_against_events(cursor)
        raw_result = self._watchdog_evaluator(
            self.config.state_path,
            now=now,
            heartbeat_timeout_seconds=self.config.heartbeat_timeout_seconds,
        )
        snapshot = normalize_watchdog_result(raw_result, config=self.config)
        pending = self._pending_transition(cursor, snapshot, now)
        if pending is None:
            if self._pending_replay_event_id(cursor) is not None:
                raise P133DeadmanError("pending_event_requires_matching_replay")
            cursor["last_checked_at"] = _timestamp(now)
            _write_cursor(self.config.cursor_path, _hashed_cursor(cursor), self.config.allowed_artifact_roots)
            return {
                "transition_kind": "deduplicated",
                "healthy": snapshot["healthy"],
                "reason": snapshot["reason"],
                "emitted": False,
                "authority_counters": zero_authority_counters(),
            }

        event, existing = self._event_for_pending(cursor, pending, snapshot, now)
        event_bytes = _json_bytes(event)
        if len(event_bytes) > self.config.max_event_bytes:
            raise P133DeadmanError("event_exceeds_max_event_bytes")
        _ensure_artifact_space(self.config.outbox_dir, write_bytes=len(event_bytes), config=self.config)
        self._enforce_retention(
            prospective_event_count=0 if existing else 1,
            prospective_event_bytes=0 if existing else len(event_bytes),
        )
        if not existing:
            _atomic_write_json(
                self.config.outbox_dir / f"{event['event_id']}.json",
                event,
                allowed_roots=self.config.allowed_artifact_roots,
            )
        new_cursor = self._advanced_cursor(cursor, pending, snapshot, event, now)
        _write_cursor(self.config.cursor_path, _hashed_cursor(new_cursor), self.config.allowed_artifact_roots)
        return {
            "transition_kind": pending["transition_kind"],
            "healthy": snapshot["healthy"],
            "reason": snapshot["reason"],
            "emitted": True,
            "event_id": event["event_id"],
            "incident_id": event["incident_id"],
            "sequence": event["sequence"],
            "occurred_at": event["occurred_at"],
            "authority_counters": zero_authority_counters(),
        }

    def run(
        self,
        *,
        max_cycles: int | None = None,
        forever: bool = False,
        stop_reason: Callable[[], str | None] | None = None,
        wait_for_stop: Callable[[float], bool] | None = None,
    ) -> dict[str, Any]:
        """Run a bounded count or forever loop with injected sleep."""

        if forever == (max_cycles is not None):
            raise P133DeadmanError("run_requires_forever_or_max_cycles")
        if max_cycles is not None and (type(max_cycles) is not int or max_cycles <= 0):
            raise P133DeadmanError("max_cycles_must_be_positive")
        cycles = 0
        emitted = 0
        final_stop_reason: str | None = None
        while forever or cycles < cast(int, max_cycles):
            requested_reason = stop_reason() if stop_reason is not None else None
            if requested_reason is not None:
                final_stop_reason = requested_reason
                break
            result = self.check_once()
            cycles += 1
            if result.get("emitted") is True:
                emitted += 1
            if forever or cycles < cast(int, max_cycles):
                if wait_for_stop is not None and wait_for_stop(self.config.check_interval_seconds):
                    requested_reason = stop_reason() if stop_reason is not None else None
                    if requested_reason is None:
                        raise P133DeadmanError("stop_wait_triggered_without_reason")
                    final_stop_reason = requested_reason
                    break
                if wait_for_stop is None:
                    self._sleep(self.config.check_interval_seconds)
        return {
            "schema_version": "p133.deadman_run_report.v1",
            "cycles": cycles,
            "emitted_events": emitted,
            "graceful_stop": final_stop_reason is not None,
            "stop_reason": final_stop_reason,
            "authority_counters": zero_authority_counters(),
        }

    def enforce_retention(self) -> dict[str, int]:
        """Prune only acknowledged owned events and valid orphan acknowledgements."""

        with _DeadmanLease(self.config):
            return self._enforce_retention(prospective_event_count=0, prospective_event_bytes=0)

    def _enforce_retention(
        self,
        *,
        prospective_event_count: int,
        prospective_event_bytes: int,
    ) -> dict[str, int]:
        """Recover enough budget before a new transition becomes canonical."""

        self._ensure_dirs()
        removed_events = 0
        removed_acks = 0
        events = _validated_events(self.config)
        ack_map = _validated_acks(self.config, allow_orphans=True)
        for event_id, ack_path in sorted(ack_map.items()):
            if event_id not in events:
                ack_identity, ack_bytes = _revalidate_ack_for_delete(self.config, ack_path)
                _unlink_regular_file(ack_path, expected=ack_identity, expected_bytes=ack_bytes)
                _fsync_dir(self.config.ack_dir)
                removed_acks += 1
        events = _validated_events(self.config)
        event_bytes = sum(len(_json_bytes(event)) for event, _ in events.values()) + prospective_event_bytes
        event_count = len(events) + prospective_event_count
        pressure = event_count > self.config.max_event_files or event_bytes > self.config.max_outbox_bytes
        if not pressure:
            return {"removed_events": removed_events, "removed_acks": removed_acks}
        ack_map = _validated_acks(self.config, allow_orphans=True)
        acknowledged_events = [
            (event_id, event, event_path, ack_map[event_id])
            for event_id, (event, event_path) in events.items()
            if event_id in ack_map
        ]
        for event_id, event, event_path, ack_candidate in sorted(
            acknowledged_events,
            key=lambda item: (int(item[1]["sequence"]), item[0]),
        ):
            if event_count <= self.config.max_event_files and event_bytes <= self.config.max_outbox_bytes:
                break
            _validate_ack_for_event(self.config, ack_candidate, event)
            event_identity, event_bytes_for_delete = _revalidate_event_for_delete(
                self.config, event_path, event
            )
            ack_identity, ack_bytes = _revalidate_ack_for_delete(
                self.config, ack_candidate, event=event
            )
            _unlink_regular_file(
                event_path,
                expected=event_identity,
                expected_bytes=event_bytes_for_delete,
            )
            _fsync_dir(self.config.outbox_dir)
            removed_events += 1
            event_bytes -= len(_json_bytes(event))
            event_count -= 1
            del events[event_id]
            _unlink_regular_file(
                ack_candidate,
                expected=ack_identity,
                expected_bytes=ack_bytes,
            )
            _fsync_dir(self.config.ack_dir)
            removed_acks += 1
        if event_count > self.config.max_event_files or event_bytes > self.config.max_outbox_bytes:
            raise P133DeadmanError("outbox_budget_exhausted")
        return {"removed_events": removed_events, "removed_acks": removed_acks}

    def _ensure_dirs(self) -> None:
        for path in (self.config.outbox_dir, self.config.cursor_path.parent, self.config.ack_dir):
            directory_fd = _open_directory_tree(path, create=True)
            os.close(directory_fd)

    def _validate_clock(self, cursor: dict[str, Any], now: datetime) -> None:
        last = cursor.get("last_checked_at")
        if last is None:
            return
        previous = _parse_timestamp(last)
        if previous.timestamp() - now.timestamp() > MAX_CLOCK_ROLLBACK_SECONDS:
            raise P133DeadmanError("clock_rollback_exceeds_tolerance")

    def _validate_sequence_against_events(self, cursor: dict[str, Any]) -> None:
        events = _validated_events(self.config)
        highest = max((int(event["sequence"]) for event, _ in events.values()), default=0)
        next_sequence = int(cursor["next_sequence"])
        if highest < next_sequence:
            return
        if highest > next_sequence:
            raise P133DeadmanError("cursor_sequence_regression")
        pending_event_id = _event_id_for_sequence(events, next_sequence)
        if pending_event_id is None:
            raise P133DeadmanError("cursor_sequence_regression")
        pending_event = events[pending_event_id][0]
        active = cursor.get("active_incident")
        if active is None:
            replay_is_compatible = pending_event.get("transition_kind") == "opened" and pending_event.get("previous_event_id") is None
        elif isinstance(active, Mapping):
            replay_is_compatible = (
                pending_event.get("transition_kind") in {"updated", "reminder", "recovered"}
                and pending_event.get("incident_id") == active.get("incident_id")
                and pending_event.get("previous_event_id") == active.get("last_event_id")
            )
        else:
            replay_is_compatible = False
        if not replay_is_compatible:
            raise P133DeadmanError("cursor_sequence_regression")

    def _pending_replay_event_id(self, cursor: Mapping[str, Any]) -> str | None:
        events = _validated_events(self.config)
        return _event_id_for_sequence(events, int(cursor["next_sequence"]))

    def _pending_transition(
        self,
        cursor: dict[str, Any],
        snapshot: dict[str, Any],
        now: datetime,
    ) -> dict[str, Any] | None:
        active = cursor.get("active_incident")
        if snapshot["healthy"]:
            if active is None:
                return None
            if not isinstance(active, Mapping):
                raise P133DeadmanError("invalid_active_incident")
            return {
                "transition_kind": "recovered",
                "incident_id": str(active["incident_id"]),
                "previous_event_id": str(active["last_event_id"]),
            }
        if active is None:
            incident_id = stable_hash(
                {
                    "config_hash": self.config.config_hash,
                    "sequence": cursor["next_sequence"],
                    "snapshot_fingerprint": snapshot["snapshot_fingerprint"],
                }
            )
            return {"transition_kind": "opened", "incident_id": incident_id, "previous_event_id": None}
        if not isinstance(active, Mapping):
            raise P133DeadmanError("invalid_active_incident")
        if active.get("last_reason") != snapshot["reason"] or active.get("last_snapshot_fingerprint") != snapshot["snapshot_fingerprint"]:
            return {
                "transition_kind": "updated",
                "incident_id": str(active["incident_id"]),
                "previous_event_id": str(active["last_event_id"]),
            }
        last_emitted = _parse_timestamp(active.get("last_emitted_at"))
        if now.timestamp() - last_emitted.timestamp() >= self.config.reminder_interval_seconds:
            return {
                "transition_kind": "reminder",
                "incident_id": str(active["incident_id"]),
                "previous_event_id": str(active["last_event_id"]),
            }
        return None

    def _event_for_pending(
        self,
        cursor: dict[str, Any],
        pending: Mapping[str, Any],
        snapshot: dict[str, Any],
        now: datetime,
    ) -> tuple[dict[str, Any], bool]:
        event_id = _event_id(
            self.config.config_hash,
            int(cursor["next_sequence"]),
            str(pending["incident_id"]),
            str(pending["transition_kind"]),
            snapshot["snapshot_fingerprint"],
            pending.get("previous_event_id"),
        )
        event_path = self.config.outbox_dir / f"{event_id}.json"
        events = _validated_events(self.config)
        existing_for_sequence = _event_id_for_sequence(events, int(cursor["next_sequence"]))
        if existing_for_sequence is not None and existing_for_sequence != event_id:
            raise P133DeadmanError("conflicting_existing_event")
        if event_path.exists() or event_path.is_symlink():
            existing = _load_event_file(self.config, event_path)
            expected = self._build_event(cursor, pending, snapshot, existing["occurred_at"], event_id=event_id)
            stable_fields = set(_EVENT_FIELDS) - {"snapshot", "event_hash"}
            if (
                any(existing.get(key) != expected.get(key) for key in stable_fields)
                or existing["snapshot"].get("snapshot_fingerprint") != snapshot["snapshot_fingerprint"]
            ):
                raise P133DeadmanError("conflicting_existing_event")
            return existing, True
        return self._build_event(cursor, pending, snapshot, _timestamp(now), event_id=event_id), False

    def _build_event(
        self,
        cursor: Mapping[str, Any],
        pending: Mapping[str, Any],
        snapshot: dict[str, Any],
        occurred_at: str,
        *,
        event_id: str,
    ) -> dict[str, Any]:
        event: dict[str, Any] = {
            "schema_version": EVENT_SCHEMA_VERSION,
            "event_id": event_id,
            "incident_id": str(pending["incident_id"]),
            "sequence": int(cursor["next_sequence"]),
            "transition_kind": str(pending["transition_kind"]),
            "occurred_at": occurred_at,
            "previous_event_id": pending.get("previous_event_id"),
            "config_hash": self.config.config_hash,
            "snapshot": snapshot,
            "authority_counters": zero_authority_counters(),
        }
        event["event_hash"] = stable_hash(event)
        return event

    def _advanced_cursor(
        self,
        cursor: Mapping[str, Any],
        pending: Mapping[str, Any],
        snapshot: dict[str, Any],
        event: Mapping[str, Any],
        now: datetime,
    ) -> dict[str, Any]:
        next_sequence = int(cursor["next_sequence"]) + 1
        if pending["transition_kind"] == "recovered":
            active: dict[str, Any] | None = None
        else:
            opened_at = event["occurred_at"]
            current_active = cursor.get("active_incident")
            if isinstance(current_active, Mapping):
                opened_at = str(current_active["opened_at"])
            active = {
                "incident_id": event["incident_id"],
                "opened_at": opened_at,
                "last_reason": snapshot["reason"],
                "last_snapshot_fingerprint": snapshot["snapshot_fingerprint"],
                "last_event_id": event["event_id"],
                "last_emitted_at": event["occurred_at"],
            }
        return {
            "schema_version": CURSOR_SCHEMA_VERSION,
            "config_hash": self.config.config_hash,
            "next_sequence": next_sequence,
            "last_checked_at": _timestamp(now),
            "active_incident": active,
            "authority_counters": zero_authority_counters(),
        }


def list_outbox(config: DeadmanConfig) -> list[dict[str, Any]]:
    """Return redacted, validated outbox events in sequence order."""

    with _DeadmanLease(config):
        events = [event for event, _ in _validated_events(config).values()]
        return sorted(events, key=lambda event: (int(event["sequence"]), str(event["event_id"])))


def acknowledge_event(config: DeadmanConfig, event_id: str, now: Callable[[], datetime] | datetime) -> dict[str, Any]:
    """Write a local self-hashed ack for one exact event ID."""

    with _DeadmanLease(config):
        return _acknowledge_event_locked(config, event_id, now)


def _acknowledge_event_locked(
    config: DeadmanConfig,
    event_id: str,
    now: Callable[[], datetime] | datetime,
) -> dict[str, Any]:
    if not _SHA256_RE.fullmatch(event_id):
        raise P133DeadmanError("event_id_must_be_sha256")
    ack_directory_fd = _open_directory_tree(config.ack_dir, create=True)
    os.close(ack_directory_fd)
    event_path = config.outbox_dir / f"{event_id}.json"
    event = _load_event_file(config, event_path)
    ack_path = config.ack_dir / f"{event_id}.json"
    if ack_path.exists() or ack_path.is_symlink():
        existing = _load_ack_file(config, ack_path, require_event=False)
        _validate_ack_for_event(config, ack_path, event)
        return existing
    acknowledged_at = _timestamp(_require_utc(now() if callable(now) else now))
    ack: dict[str, Any] = {
        "schema_version": ACK_SCHEMA_VERSION,
        "event_id": event_id,
        "event_hash": event["event_hash"],
        "config_hash": config.config_hash,
        "acknowledged_at": acknowledged_at,
        "authority_counters": zero_authority_counters(),
    }
    ack["ack_hash"] = stable_hash(ack)
    _ensure_artifact_space(config.ack_dir, write_bytes=len(_json_bytes(ack)), config=config)
    _atomic_write_json(ack_path, ack, allowed_roots=config.allowed_artifact_roots)
    return ack


def _load_cursor(config: DeadmanConfig) -> dict[str, Any]:
    if not config.cursor_path.exists():
        return {
            "schema_version": CURSOR_SCHEMA_VERSION,
            "config_hash": config.config_hash,
            "next_sequence": 1,
            "last_checked_at": None,
            "active_incident": None,
            "authority_counters": zero_authority_counters(),
        }
    cursor = _read_json_regular(config.cursor_path)
    if set(cursor) != _CURSOR_FIELDS:
        raise P133DeadmanError("invalid_cursor_fields")
    if not isinstance(cursor, dict):
        raise P133DeadmanError("invalid_cursor_shape")
    expected_hash = cursor.get("cursor_hash")
    if not isinstance(expected_hash, str) or stable_hash({key: value for key, value in cursor.items() if key != "cursor_hash"}) != expected_hash:
        raise P133DeadmanError("cursor_hash_invalid")
    if cursor.get("schema_version") != CURSOR_SCHEMA_VERSION:
        raise P133DeadmanError("invalid_cursor_schema")
    if cursor.get("config_hash") != config.config_hash:
        raise P133DeadmanError("cursor_config_mismatch")
    _validate_zero_authority(cursor.get("authority_counters"))
    if type(cursor.get("next_sequence")) is not int or cursor["next_sequence"] <= 0:
        raise P133DeadmanError("invalid_cursor_sequence")
    if cursor.get("last_checked_at") is not None:
        _parse_timestamp(cursor.get("last_checked_at"))
    active = cursor.get("active_incident")
    if active is not None:
        _validate_active_incident(active)
    return cursor


def _hashed_cursor(cursor: Mapping[str, Any]) -> dict[str, Any]:
    payload = {key: value for key, value in cursor.items() if key != "cursor_hash"}
    payload["cursor_hash"] = stable_hash(payload)
    return payload


def _write_cursor(path: Path, cursor: dict[str, Any], roots: tuple[Path, ...]) -> None:
    _atomic_write_json(path, cursor, allowed_roots=roots)


_ORIGINAL_WRITE_CURSOR = _write_cursor


def _validated_events(config: DeadmanConfig) -> dict[str, tuple[dict[str, Any], Path]]:
    if not config.outbox_dir.exists() and not config.outbox_dir.is_symlink():
        return {}
    events: dict[str, tuple[dict[str, Any], Path]] = {}
    sequences: set[int] = set()
    for path in _artifact_directory_entries(config.outbox_dir, "outbox"):
        event = _load_event_file(config, path)
        event_id = str(event["event_id"])
        if event_id in events:
            raise P133DeadmanError("duplicate_event_id")
        sequence = int(event["sequence"])
        if sequence in sequences:
            raise P133DeadmanError("duplicate_event_sequence")
        sequences.add(sequence)
        events[event_id] = (event, path)
    for event_id, (event, _) in events.items():
        previous_event_id = event.get("previous_event_id")
        if previous_event_id is None or previous_event_id not in events:
            continue
        previous = events[str(previous_event_id)][0]
        if int(previous["sequence"]) >= int(event["sequence"]):
            raise P133DeadmanError("event_link_sequence_invalid")
        if previous.get("incident_id") != event.get("incident_id"):
            raise P133DeadmanError("event_link_incident_mismatch")
        if previous.get("event_id") == event_id:
            raise P133DeadmanError("event_self_link")
    return events


def _validated_acks(config: DeadmanConfig, *, allow_orphans: bool) -> dict[str, Path]:
    if not config.ack_dir.exists() and not config.ack_dir.is_symlink():
        return {}
    acks: dict[str, Path] = {}
    for path in _artifact_directory_entries(config.ack_dir, "ack_directory"):
        ack = _load_ack_file(config, path, require_event=not allow_orphans)
        acks[str(ack["event_id"])] = path
    return acks


def _artifact_directory_entries(path: Path, artifact: str) -> list[Path]:
    _reject_symlink_components(path)
    try:
        info = os.lstat(path)
    except OSError as exc:
        raise P133DeadmanError(f"{artifact}_missing") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise P133DeadmanError(f"{artifact}_not_directory")
    try:
        return sorted(path.iterdir())
    except OSError as exc:
        raise P133DeadmanError(f"{artifact}_unreadable") from exc


def _load_event_file(config: DeadmanConfig, path: Path) -> dict[str, Any]:
    if not path.name.endswith(".json"):
        raise P133DeadmanError("invalid_event_filename")
    event_id = path.name.removesuffix(".json")
    if not _SHA256_RE.fullmatch(event_id):
        raise P133DeadmanError("invalid_event_filename")
    stat_result = _regular_file_stat(path, "event")
    value = _read_json_path(path)
    if not isinstance(value, dict):
        raise P133DeadmanError("invalid_event_shape")
    if set(value) != _EVENT_FIELDS:
        raise P133DeadmanError("invalid_event_fields")
    if value.get("event_id") != event_id:
        raise P133DeadmanError("event_filename_mismatch")
    if value.get("schema_version") != EVENT_SCHEMA_VERSION:
        raise P133DeadmanError("invalid_event_schema")
    if value.get("config_hash") != config.config_hash:
        raise P133DeadmanError("event_config_mismatch")
    if value.get("event_hash") != stable_hash({key: item for key, item in value.items() if key != "event_hash"}):
        raise P133DeadmanError("event_hash_invalid")
    if _json_size(value) != stat_result.st_size:
        raise P133DeadmanError("event_size_changed")
    _validate_event_shape(value)
    if value["snapshot"].get("runtime_ref_hash") != config.runtime_ref_hash:
        raise P133DeadmanError("snapshot_runtime_ref_mismatch")
    expected_event_id = _event_id(
        config.config_hash,
        int(value["sequence"]),
        str(value["incident_id"]),
        str(value["transition_kind"]),
        str(value["snapshot"]["snapshot_fingerprint"]),
        value.get("previous_event_id"),
    )
    if value.get("event_id") != expected_event_id:
        raise P133DeadmanError("event_id_derivation_mismatch")
    return value


def _load_ack_file(config: DeadmanConfig, path: Path, *, require_event: bool) -> dict[str, Any]:
    if not path.name.endswith(".json"):
        raise P133DeadmanError("invalid_ack_filename")
    event_id = path.name.removesuffix(".json")
    if not _SHA256_RE.fullmatch(event_id):
        raise P133DeadmanError("invalid_ack_filename")
    _regular_file_stat(path, "ack")
    value = _read_json_path(path)
    if not isinstance(value, dict):
        raise P133DeadmanError("invalid_ack_shape")
    if set(value) != _ACK_FIELDS:
        raise P133DeadmanError("invalid_ack_fields")
    if value.get("event_id") != event_id:
        raise P133DeadmanError("ack_filename_mismatch")
    if value.get("schema_version") != ACK_SCHEMA_VERSION:
        raise P133DeadmanError("invalid_ack_schema")
    if value.get("config_hash") != config.config_hash:
        raise P133DeadmanError("ack_config_mismatch")
    if not _SHA256_RE.fullmatch(str(value.get("event_hash", ""))):
        raise P133DeadmanError("invalid_ack_event_hash")
    if value.get("ack_hash") != stable_hash({key: item for key, item in value.items() if key != "ack_hash"}):
        raise P133DeadmanError("ack_hash_invalid")
    _parse_timestamp(value.get("acknowledged_at"))
    _validate_zero_authority(value.get("authority_counters"))
    if require_event:
        event = _load_event_file(config, config.outbox_dir / f"{event_id}.json")
        _validate_ack_for_event(config, path, event)
    return value


def _validate_ack_for_event(config: DeadmanConfig, ack_path: Path, event: Mapping[str, Any]) -> None:
    ack = _load_ack_file(config, ack_path, require_event=False)
    if ack.get("event_id") != event.get("event_id") or ack.get("event_hash") != event.get("event_hash"):
        raise P133DeadmanError("ack_event_mismatch")


def _validate_event_shape(event: Mapping[str, Any]) -> None:
    if not _SHA256_RE.fullmatch(str(event.get("event_id", ""))):
        raise P133DeadmanError("invalid_event_id")
    if not _SHA256_RE.fullmatch(str(event.get("incident_id", ""))):
        raise P133DeadmanError("invalid_incident_id")
    if type(event.get("sequence")) is not int or event["sequence"] <= 0:
        raise P133DeadmanError("invalid_event_sequence")
    if event.get("transition_kind") not in _TRANSITIONS:
        raise P133DeadmanError("invalid_transition_kind")
    _parse_timestamp(event.get("occurred_at"))
    previous = event.get("previous_event_id")
    if previous is not None and not _SHA256_RE.fullmatch(str(previous)):
        raise P133DeadmanError("invalid_previous_event_id")
    if event.get("transition_kind") == "opened" and previous is not None:
        raise P133DeadmanError("opened_event_has_previous_link")
    if event.get("transition_kind") != "opened" and previous is None:
        raise P133DeadmanError("linked_event_missing_previous_link")
    snapshot = event.get("snapshot")
    if not isinstance(snapshot, Mapping):
        raise P133DeadmanError("invalid_snapshot")
    if set(snapshot) != _SNAPSHOT_FIELDS:
        raise P133DeadmanError("invalid_snapshot_fields")
    if snapshot.get("reason") not in NORMALIZED_REASONS:
        raise P133DeadmanError("invalid_snapshot_reason")
    if type(snapshot.get("healthy")) is not bool:
        raise P133DeadmanError("invalid_snapshot_health")
    if snapshot.get("reason") == "heartbeat_current" and snapshot.get("healthy") is not True:
        raise P133DeadmanError("invalid_snapshot_health")
    if snapshot.get("reason") != "heartbeat_current" and snapshot.get("healthy") is not False:
        raise P133DeadmanError("invalid_snapshot_health")
    state_hash = snapshot.get("state_hash")
    if state_hash is not None and (
        not isinstance(state_hash, str)
        or not state_hash.startswith("sha256:")
        or not _SHA256_RE.fullmatch(state_hash)
    ):
        raise P133DeadmanError("invalid_snapshot_state_hash")
    heartbeat_age = snapshot.get("heartbeat_age_seconds")
    if heartbeat_age is not None and _bounded_number(heartbeat_age) != heartbeat_age:
        raise P133DeadmanError("invalid_snapshot_heartbeat_age")
    if not _SHA256_RE.fullmatch(str(snapshot.get("runtime_ref_hash", ""))):
        raise P133DeadmanError("invalid_snapshot_runtime_ref_hash")
    expected_snapshot_hash = _snapshot_fingerprint(snapshot)
    if snapshot.get("snapshot_fingerprint") != expected_snapshot_hash:
        raise P133DeadmanError("snapshot_fingerprint_invalid")
    _validate_zero_authority(event.get("authority_counters"))


def _validate_active_incident(active: Any) -> None:
    if not isinstance(active, Mapping):
        raise P133DeadmanError("invalid_active_incident")
    if set(active) != _ACTIVE_INCIDENT_FIELDS:
        raise P133DeadmanError("invalid_active_incident")
    for key in ("incident_id", "opened_at", "last_reason", "last_snapshot_fingerprint", "last_event_id", "last_emitted_at"):
        if key not in active:
            raise P133DeadmanError("invalid_active_incident")
    if not _SHA256_RE.fullmatch(str(active["incident_id"])) or not _SHA256_RE.fullmatch(str(active["last_event_id"])):
        raise P133DeadmanError("invalid_active_incident")
    if not _SHA256_RE.fullmatch(str(active["last_snapshot_fingerprint"])):
        raise P133DeadmanError("invalid_active_incident")
    if active["last_reason"] not in NORMALIZED_REASONS or active["last_reason"] == "heartbeat_current":
        raise P133DeadmanError("invalid_active_incident")
    _parse_timestamp(active["opened_at"])
    _parse_timestamp(active["last_emitted_at"])


def _event_id(
    config_hash: str,
    sequence: int,
    incident_id: str,
    transition_kind: str,
    snapshot_fingerprint: str,
    previous_event_id: object,
) -> str:
    return stable_hash(
        {
            "config_hash": config_hash,
            "sequence": sequence,
            "incident_id": incident_id,
            "transition_kind": transition_kind,
            "snapshot_fingerprint": snapshot_fingerprint,
            "previous_event_id": previous_event_id,
        }
    )


def _snapshot_fingerprint(snapshot: Mapping[str, Any]) -> str:
    """Hash incident identity while excluding monotonically changing heartbeat age."""

    return stable_hash(
        {
            "reason": snapshot.get("reason"),
            "healthy": snapshot.get("healthy"),
            "state_hash": snapshot.get("state_hash"),
            "runtime_ref_hash": snapshot.get("runtime_ref_hash"),
        }
    )


def _event_id_for_sequence(events: Mapping[str, tuple[Mapping[str, Any], Path]], sequence: int) -> str | None:
    for event_id, (event, _) in events.items():
        if event.get("sequence") == sequence:
            return event_id
    return None


def _atomic_write_json(path: Path, value: object, *, allowed_roots: Sequence[Path] | None = None) -> None:
    if allowed_roots is None:
        raise P133DeadmanError("allowed_roots_required")
    try:
        parent_fd, name = _open_artifact_parent(path, allowed_roots, create=True)
    except OSError as exc:
        raise P133DeadmanError("write_parent_invalid") from exc
    data = _json_bytes(value)
    fd = -1
    tmp_name = ""
    try:
        try:
            current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            current = None
        if current is not None and (not stat.S_ISREG(current.st_mode) or current.st_nlink != 1):
            raise P133DeadmanError("write_target_not_regular")
        tmp_name = f".{name}.{os.getpid()}.{time.monotonic_ns()}.tmp"
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        fd = os.open(tmp_name, flags, 0o600, dir_fd=parent_fd)
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        tmp_name = ""
        try:
            _fsync_dir(path.parent)
        except OSError as exc:
            raise P133DurabilityUncertainError("directory_fsync_failed_after_replace") from exc
    finally:
        if fd >= 0:
            os.close(fd)
        if tmp_name:
            try:
                os.unlink(tmp_name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
        os.close(parent_fd)


def _write_json_path(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json_regular(path: Path) -> dict[str, Any]:
    _regular_file_stat(path, "cursor")
    value = _read_json_path(path)
    if not isinstance(value, dict):
        raise P133DeadmanError("invalid_json_shape")
    return value


def _read_json_path(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise P133DeadmanError("invalid_json_file") from exc


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _json_size(value: object) -> int:
    return len(_json_bytes(value))


def _regular_file_stat(path: Path, artifact: str) -> os.stat_result:
    try:
        info = os.lstat(path)
    except OSError as exc:
        raise P133DeadmanError(f"{artifact}_missing") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise P133DeadmanError(f"{artifact}_not_regular")
    if info.st_nlink != 1:
        raise P133DeadmanError(f"{artifact}_has_multiple_links")
    return info


def _revalidate_event_for_delete(
    config: DeadmanConfig,
    path: Path,
    expected_event: Mapping[str, Any],
) -> tuple[os.stat_result, bytes]:
    before = _regular_file_stat(path, "retention_candidate")
    current = _load_event_file(config, path)
    after = _regular_file_stat(path, "retention_candidate")
    if current != expected_event or _file_identity(before) != _file_identity(after):
        raise P133DeadmanError("retention_candidate_changed")
    return after, _json_bytes(current)


def _revalidate_ack_for_delete(
    config: DeadmanConfig,
    path: Path,
    *,
    event: Mapping[str, Any] | None = None,
) -> tuple[os.stat_result, bytes]:
    before = _regular_file_stat(path, "retention_candidate")
    ack = _load_ack_file(config, path, require_event=False)
    if event is not None and (
        ack.get("event_id") != event.get("event_id") or ack.get("event_hash") != event.get("event_hash")
    ):
        raise P133DeadmanError("ack_event_mismatch")
    after = _regular_file_stat(path, "retention_candidate")
    if _file_identity(before) != _file_identity(after):
        raise P133DeadmanError("retention_candidate_changed")
    return after, _json_bytes(ack)


def _file_identity(info: os.stat_result) -> tuple[int, int, int, int, int, int, int]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _unlink_regular_file(
    path: Path,
    *,
    expected: os.stat_result,
    expected_bytes: bytes,
) -> None:
    try:
        parent_fd = _open_directory_tree(path.parent, create=False)
    except OSError as exc:
        raise P133DeadmanError("retention_parent_invalid") from exc
    candidate_fd = -1
    try:
        _validate_retention_directory(parent_fd)
        try:
            candidate_fd = os.open(
                path.name,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
                dir_fd=parent_fd,
            )
        except OSError as exc:
            raise P133DeadmanError("retention_candidate_missing") from exc
        opened = os.fstat(candidate_fd)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise P133DeadmanError("retention_candidate_not_regular")
        if _file_identity(opened) != _file_identity(expected):
            raise P133DeadmanError("retention_candidate_changed")
        content = _read_fd_bytes(candidate_fd, limit=len(expected_bytes) + 1)
        after_read = os.fstat(candidate_fd)
        try:
            current_path = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        except OSError as exc:
            raise P133DeadmanError("retention_candidate_missing") from exc
        if (
            content != expected_bytes
            or _file_identity(after_read) != _file_identity(expected)
            or _file_identity(current_path) != _file_identity(after_read)
        ):
            raise P133DeadmanError("retention_candidate_changed")
        os.unlink(path.name, dir_fd=parent_fd)
    finally:
        if candidate_fd >= 0:
            os.close(candidate_fd)
        os.close(parent_fd)


def _read_fd_bytes(fd: int, *, limit: int) -> bytes:
    os.lseek(fd, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    remaining = limit
    while remaining > 0:
        chunk = os.read(fd, min(65_536, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _validate_retention_directory(fd: int) -> None:
    metadata = os.fstat(fd)
    owner_permissions = stat.S_IWUSR | stat.S_IXUSR
    unsafe_writer_permissions = stat.S_IWGRP | stat.S_IWOTH
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_mode & owner_permissions != owner_permissions
        or metadata.st_mode & unsafe_writer_permissions
    ):
        raise P133DeadmanError("retention_parent_permissions_unsafe")


def _fsync_dir(path: Path) -> None:
    fd = _open_directory_tree(path, create=False)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _open_artifact_parent(path: Path, allowed_roots: Sequence[Path], *, create: bool) -> tuple[int, str]:
    matching = [root for root in allowed_roots if _is_relative_to(path, root)]
    if not matching:
        raise OSError("artifact_path_outside_allowed_roots")
    root = max(matching, key=lambda candidate: len(candidate.parts))
    relative = path.relative_to(root)
    if not relative.parts:
        raise OSError("artifact_path_is_directory")
    directory_fd = _open_directory_tree(root, create=create)
    try:
        flags = (
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        for component in relative.parts[:-1]:
            try:
                next_fd = os.open(component, flags, dir_fd=directory_fd)
            except FileNotFoundError:
                if not create:
                    raise
                os.mkdir(component, 0o700, dir_fd=directory_fd)
                next_fd = os.open(component, flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd
        return directory_fd, relative.parts[-1]
    except Exception:
        os.close(directory_fd)
        raise


def _open_directory_tree(path: Path, *, create: bool) -> int:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    directory_fd = os.open("/", flags)
    try:
        for component in path.parts[1:]:
            try:
                next_fd = os.open(component, flags, dir_fd=directory_fd)
            except FileNotFoundError:
                if not create:
                    raise
                os.mkdir(component, 0o700, dir_fd=directory_fd)
                next_fd = os.open(component, flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd
        return directory_fd
    except Exception:
        os.close(directory_fd)
        raise


def _ensure_artifact_space(path: Path, *, write_bytes: int, config: DeadmanConfig) -> None:
    required_free = config.min_artifact_free_bytes + write_bytes
    if _artifact_free_bytes(path, config.allowed_artifact_roots) < required_free:
        raise OSError(errno.ENOSPC, "artifact_free_space_below_floor")


def _artifact_free_bytes(path: Path, allowed_roots: Sequence[Path]) -> int:
    target = path if path.exists() else path.parent
    resolved = target.resolve(strict=False)
    if not any(_is_relative_to(resolved, root) for root in allowed_roots):
        raise P133DeadmanError("path_outside_allowed_roots")
    return shutil.disk_usage(target).free


_ORIGINAL_ARTIFACT_FREE_BYTES = _artifact_free_bytes


def _resolve_local_path(base: Path, value: object) -> Path:
    if not isinstance(value, str) or not value:
        raise P133DeadmanError("invalid_path_value")
    if "://" in value or "\x00" in value:
        raise P133DeadmanError("non_local_path")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    return Path(os.path.abspath(path))


def _reject_symlink_components(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try:
            if current.is_symlink():
                raise P133DeadmanError("path_has_symlink_parent")
        except OSError as exc:
            raise P133DeadmanError("path_has_symlink_parent") from exc


def _require_pairwise_non_overlapping(paths: Sequence[Path]) -> None:
    for index, left in enumerate(paths):
        for right in paths[index + 1 :]:
            if left == right or _is_relative_to(left, right) or _is_relative_to(right, left):
                raise P133DeadmanError("artifact_paths_overlap")


def _reject_forbidden_fields(raw: Mapping[str, Any]) -> None:
    for key in raw:
        lowered = str(key).lower()
        if any(token in lowered for token in _FORBIDDEN_FIELD_TOKENS):
            raise P133DeadmanError("forbidden_configuration_field")
    for value in _iter_text_values(raw):
        if _contains_forbidden_text(value):
            raise P133DeadmanError("forbidden_configuration_value")


def _contains_forbidden_text(value: str) -> bool:
    lowered = value.lower()
    return any(token in lowered for token in ("http://", "https://", " sh -c", "/bin/sh", "/bin/bash")) or bool(
        _FORBIDDEN_VALUE_RE.search(lowered)
    )


def _iter_text_values(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [item for nested in value.values() for item in _iter_text_values(nested)]
    if _is_sequence(value):
        return [item for nested in cast(Sequence[object], value) for item in _iter_text_values(nested)]
    return []


def _positive_int(raw: Mapping[str, Any], key: str) -> int:
    value = raw.get(key)
    if type(value) is not int or value <= 0 or value > MAX_CONFIG_INTEGER:
        raise P133DeadmanError(f"invalid_positive_integer:{key}")
    return int(value)


def _required_text(raw: Mapping[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise P133DeadmanError(f"invalid_text:{key}")
    return value


def _bounded_number(value: object) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0 or value > MAX_CONFIG_INTEGER:
        return None
    if value != value or value in (float("inf"), float("-inf")):
        return None
    return value


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise P133DeadmanError("timestamp_must_be_utc")
    return value.astimezone(UTC)


def _timestamp(value: datetime) -> str:
    return _require_utc(value).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise P133DeadmanError("invalid_timestamp")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise P133DeadmanError("invalid_timestamp") from exc
    return _require_utc(parsed)


def _validate_zero_authority(counters: object) -> None:
    if not isinstance(counters, Mapping) or set(counters) != set(P121_AUTHORITY_COUNTER_KEYS):
        raise P133DeadmanError("invalid_authority_counters")
    for key in P121_AUTHORITY_COUNTER_KEYS:
        if type(counters.get(key)) is not int or counters.get(key) != 0:
            raise P133DeadmanError("invalid_authority_counters")


def _is_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


__all__ = [
    "ACK_SCHEMA_VERSION",
    "CONFIG_SCHEMA_VERSION",
    "CURSOR_SCHEMA_VERSION",
    "EVENT_SCHEMA_VERSION",
    "DeadmanConfig",
    "DeadmanOutbox",
    "NORMALIZED_REASONS",
    "P133DeadmanError",
    "P133DurabilityUncertainError",
    "acknowledge_event",
    "list_outbox",
    "load_deadman_config",
    "normalize_watchdog_result",
]
