"""Fail-closed, read-only, always-on monitoring runtime for P131.

The runtime deliberately tails only local JSONL telemetry.  Live connector
polling belongs behind a later authority contract because P121 treats every
live connector call as non-zero authority.  P131 therefore proves continuous
operation without credentials, network calls, subprocesses, or remediation.
"""

from __future__ import annotations

import errno
import fcntl
import json
import os
import re
import stat
import tempfile
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO, Protocol, cast

from app.services.p110_evaluation import stable_hash
from app.services.p121_signals import P121_AUTHORITY_COUNTER_KEYS, zero_authority_counters

CONFIG_SCHEMA_VERSION = "p131.monitor_config.v1"
STATE_SCHEMA_VERSION = "p131.monitor_state.v1"
REPORT_SCHEMA_VERSION = "p131.health_report.v1"
TERMINATION_RECEIPT_SCHEMA_VERSION = "p132.termination_receipt.v1"
MAX_RECENT_OBSERVATION_HASHES = 2_000
MAX_STATE_BYTES = 1_048_576
MAX_FUTURE_CLOCK_SKEW_SECONDS = 5.0
MAX_REPORT_FILES = 10_000
MAX_REPORT_DIR_BYTES = 1_073_741_824
MAX_MIN_ARTIFACT_FREE_BYTES = 1_099_511_627_776
_REPORT_FILENAME = re.compile(r"p131-health-\d{8}T\d{6}Z\.json\Z")
_FORBIDDEN_FIELD_TOKENS = (
    "auth",
    "credential",
    "header",
    "password",
    "secret",
    "token",
    "command",
    "subprocess",
    "mutation",
)
_CONFIG_FIELDS = frozenset(
    {
        "schema_version",
        "runtime_id",
        "interval_seconds",
        "heartbeat_timeout_seconds",
        "data_stale_after_seconds",
        "daily_report_interval_seconds",
        "canary_every_cycles",
        "max_consecutive_failures",
        "max_bytes_per_cycle",
        "max_records_per_cycle",
        "max_line_bytes",
        "max_report_files",
        "max_report_dir_bytes",
        "min_artifact_free_bytes",
        "state_path",
        "report_dir",
        "lease_path",
        "termination_receipt_path",
        "allowed_data_roots",
        "allowed_artifact_roots",
        "sources",
    }
)
_SOURCE_FIELDS = frozenset({"source_id", "kind", "path", "enabled"})


class P131ConfigError(ValueError):
    """Raised when monitor configuration violates the P131 safety contract."""


class P131StateError(ValueError):
    """Raised when persisted monitor state is malformed or tampered with."""


class P131LeaseError(RuntimeError):
    """Raised when another process already owns the runtime lease."""


class P131DurabilityUncertainError(OSError):
    """Raised after replacement when directory durability cannot be proven."""


class Clock(Protocol):
    def now(self) -> datetime:
        """Return an aware UTC-compatible timestamp."""

    def sleep(self, seconds: float) -> None:
        """Block for the requested duration."""


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def monotonic(self) -> float:
        return time.monotonic()


@dataclass(frozen=True)
class LocalJsonlSource:
    source_id: str
    path: Path
    allowed_root: Path
    relative_path: Path
    enabled: bool = True


@dataclass(frozen=True)
class MonitorConfig:
    config_hash: str
    runtime_id: str
    interval_seconds: int
    heartbeat_timeout_seconds: int
    data_stale_after_seconds: int
    daily_report_interval_seconds: int
    canary_every_cycles: int
    max_consecutive_failures: int
    max_bytes_per_cycle: int
    max_records_per_cycle: int
    max_line_bytes: int
    max_report_files: int
    max_report_dir_bytes: int
    min_artifact_free_bytes: int
    state_path: Path
    report_dir: Path
    lease_path: Path
    termination_receipt_path: Path
    allowed_data_roots: tuple[Path, ...]
    allowed_artifact_roots: tuple[Path, ...]
    sources: tuple[LocalJsonlSource, ...]


def load_monitor_config(path: Path | str) -> MonitorConfig:
    """Load and validate a credential-free, local-only monitor configuration."""

    config_path = Path(path).expanduser().resolve()
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise P131ConfigError("invalid_configuration_file") from exc
    if not isinstance(raw, Mapping):
        raise P131ConfigError("invalid_configuration_shape")
    if raw.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise P131ConfigError("invalid_configuration_schema")
    raw_sources = raw.get("sources")
    if _is_sequence(raw_sources):
        for raw_source in cast(Sequence[Any], raw_sources):
            if isinstance(raw_source, Mapping) and raw_source.get("kind") != "local_jsonl":
                raise P131ConfigError("unsupported_source_kind")
    _reject_forbidden_fields(raw)
    if set(raw) - _CONFIG_FIELDS:
        raise P131ConfigError("unknown_configuration_field")

    interval = _positive_int(raw, "interval_seconds", "interval_must_be_positive")
    heartbeat_timeout = _positive_int(raw, "heartbeat_timeout_seconds", "heartbeat_timeout_must_be_positive")
    if heartbeat_timeout < interval:
        raise P131ConfigError("heartbeat_timeout_shorter_than_interval")
    stale_after = _positive_int(raw, "data_stale_after_seconds", "data_stale_after_must_be_positive")
    report_interval = _positive_int(raw, "daily_report_interval_seconds", "daily_report_interval_must_be_positive")
    if stale_after < interval:
        raise P131ConfigError("data_stale_after_shorter_than_interval")
    if report_interval < interval:
        raise P131ConfigError("report_interval_shorter_than_interval")
    canary_every = _positive_int(raw, "canary_every_cycles", "canary_interval_must_be_positive")
    max_failures = _positive_int(raw, "max_consecutive_failures", "max_consecutive_failures_must_be_positive")
    max_bytes = _optional_positive_int(raw, "max_bytes_per_cycle", 1_048_576)
    max_records = _optional_positive_int(raw, "max_records_per_cycle", 10_000)
    max_line_bytes = _optional_positive_int(raw, "max_line_bytes", 65_536)
    max_report_files = _optional_bounded_positive_int(raw, "max_report_files", 32, MAX_REPORT_FILES)
    max_report_dir_bytes = _optional_bounded_positive_int(
        raw, "max_report_dir_bytes", 10_485_760, MAX_REPORT_DIR_BYTES
    )
    min_artifact_free_bytes = _optional_bounded_positive_int(
        raw, "min_artifact_free_bytes", 1_048_576, MAX_MIN_ARTIFACT_FREE_BYTES
    )
    if max_line_bytes > max_bytes:
        raise P131ConfigError("max_line_bytes_exceeds_cycle_budget")
    runtime_id = _required_text(raw, "runtime_id")
    base = config_path.parent
    roots_value = raw.get("allowed_data_roots")
    if not _is_sequence(roots_value) or not roots_value:
        raise P131ConfigError("allowed_data_roots_required")
    roots = tuple(_resolve_path(base, value) for value in roots_value)

    sources_value = raw.get("sources")
    if not _is_sequence(sources_value) or not sources_value:
        raise P131ConfigError("sources_required")
    sources: list[LocalJsonlSource] = []
    seen_ids: set[str] = set()
    for item in sources_value:
        if not isinstance(item, Mapping):
            raise P131ConfigError("invalid_source_configuration")
        if set(item) - _SOURCE_FIELDS:
            raise P131ConfigError("unknown_source_configuration_field")
        if item.get("kind") != "local_jsonl":
            raise P131ConfigError("unsupported_source_kind")
        source_id = _required_text(item, "source_id")
        if source_id in seen_ids:
            raise P131ConfigError("duplicate_source_id")
        seen_ids.add(source_id)
        source_path = _resolve_path(base, item.get("path"))
        if not any(_is_relative_to(source_path, root) for root in roots):
            raise P131ConfigError("source_outside_allowed_data_roots")
        enabled = item.get("enabled", True)
        if not isinstance(enabled, bool):
            raise P131ConfigError("invalid_source_enabled_flag")
        matching_roots = [root for root in roots if _is_relative_to(source_path, root)]
        allowed_root = max(matching_roots, key=lambda root: len(root.parts))
        sources.append(
            LocalJsonlSource(
                source_id=source_id,
                path=source_path,
                allowed_root=allowed_root,
                relative_path=source_path.relative_to(allowed_root),
                enabled=enabled,
            )
        )
    if not any(source.enabled for source in sources):
        raise P131ConfigError("enabled_source_required")

    artifact_roots_value = raw.get("allowed_artifact_roots", [str(base)])
    if not _is_sequence(artifact_roots_value) or not artifact_roots_value:
        raise P131ConfigError("allowed_artifact_roots_required")
    artifact_roots = tuple(_resolve_path(base, value) for value in artifact_roots_value)
    state_path = _resolve_path(base, raw.get("state_path"))
    report_dir = _resolve_path(base, raw.get("report_dir"))
    lease_path = _resolve_path(base, raw.get("lease_path"))
    receipt_value = raw.get("termination_receipt_path")
    termination_receipt_path = (
        state_path.with_name("termination-receipt.json")
        if receipt_value is None
        else _resolve_path(base, receipt_value)
    )
    artifact_paths = (state_path, report_dir, lease_path, termination_receipt_path)
    if not all(any(_is_relative_to(path, root) for root in artifact_roots) for path in artifact_paths):
        raise P131ConfigError("artifact_path_outside_allowed_roots")

    return MonitorConfig(
        config_hash=stable_hash(raw),
        runtime_id=runtime_id,
        interval_seconds=interval,
        heartbeat_timeout_seconds=heartbeat_timeout,
        data_stale_after_seconds=stale_after,
        daily_report_interval_seconds=report_interval,
        canary_every_cycles=canary_every,
        max_consecutive_failures=max_failures,
        max_bytes_per_cycle=max_bytes,
        max_records_per_cycle=max_records,
        max_line_bytes=max_line_bytes,
        max_report_files=max_report_files,
        max_report_dir_bytes=max_report_dir_bytes,
        min_artifact_free_bytes=min_artifact_free_bytes,
        state_path=state_path,
        report_dir=report_dir,
        lease_path=lease_path,
        termination_receipt_path=termination_receipt_path,
        allowed_data_roots=roots,
        allowed_artifact_roots=artifact_roots,
        sources=tuple(sources),
    )


class AlwaysOnMonitor:
    """Continuously tail bounded local telemetry and persist tamper-evident health."""

    def __init__(
        self,
        config: MonitorConfig,
        *,
        clock: Clock | None = None,
        canary_probe: Callable[[], bool | Mapping[str, Any]] | None = None,
    ) -> None:
        self.config = config
        self.clock = clock or SystemClock()
        self.canary_probe = canary_probe or _default_canary_probe

    def run(
        self,
        *,
        max_cycles: int | None = None,
        sleep_enabled: bool = True,
        stop_reason: Callable[[], str | None] | None = None,
        wait_for_stop: Callable[[float], bool] | None = None,
    ) -> dict[str, Any]:
        """Run forever by default, or for a bounded number of cycles in tests."""

        if max_cycles is not None and (isinstance(max_cycles, bool) or max_cycles <= 0):
            raise ValueError("max_cycles_must_be_positive")
        if max_cycles is None and not sleep_enabled:
            raise ValueError("unbounded_run_requires_sleep")
        if wait_for_stop is not None and not sleep_enabled:
            raise ValueError("stop_wait_requires_sleep")

        invocation = {
            "cycle_count": 0,
            "accepted_observation_count": 0,
            "duplicate_observation_count": 0,
            "source_failure_count": 0,
        }
        scheduler_anchor = _clock_monotonic(self.clock)
        next_tick_index = 1
        graceful_stop = False
        final_stop_reason: str | None = None

        with _RuntimeLease(self.config.lease_path, self.config.runtime_id, self.config.allowed_artifact_roots):
            existing = self.config.state_path.exists()
            state = self._load_or_initialize_state()
            if existing:
                state["resume_count"] = int(state["resume_count"]) + 1
            while max_cycles is None or invocation["cycle_count"] < max_cycles:
                requested_reason = stop_reason() if stop_reason is not None else None
                if requested_reason is not None:
                    self._graceful_stop(state, requested_reason)
                    graceful_stop = True
                    final_stop_reason = requested_reason
                    break
                cycle = self._run_cycle(state)
                for key in invocation:
                    invocation[key] += int(cycle.get(key, 0))
                final_cycle = max_cycles is not None and invocation["cycle_count"] >= max_cycles
                delay = 0.0
                if not final_cycle and sleep_enabled:
                    delay, next_tick_index = self._schedule_next(state, scheduler_anchor, next_tick_index)
                elif final_cycle:
                    scheduler = _mapping_dict(state.get("scheduler"))
                    scheduler["next_delay_seconds"] = None
                    state["scheduler"] = scheduler
                self._persist_state(state)
                self._write_report_if_due(state)
                if final_cycle:
                    break
                if sleep_enabled:
                    stopped_while_waiting = wait_for_stop(delay) if wait_for_stop is not None else False
                    if stopped_while_waiting:
                        requested_reason = stop_reason() if stop_reason is not None else None
                        if requested_reason is None:
                            raise ValueError("stop_wait_triggered_without_reason")
                        self._graceful_stop(state, requested_reason)
                        graceful_stop = True
                        final_stop_reason = requested_reason
                        break
                    if wait_for_stop is None:
                        self.clock.sleep(delay)

        status = _status_from_state(
            state,
            now=self.clock.now(),
            heartbeat_timeout_seconds=self.config.heartbeat_timeout_seconds,
            data_stale_after_seconds=self.config.data_stale_after_seconds,
        )
        return {
            "schema_version": "p131.monitor_run.v1",
            "runtime_id": self.config.runtime_id,
            "summary": {
                **invocation,
                "live": status["live"],
                "ready": status["ready"],
                "reasons": status["reasons"],
                "graceful_stop": graceful_stop,
                "stop_reason": final_stop_reason,
            },
            "authority": _authority_snapshot(),
            "state_path": str(self.config.state_path),
        }

    def _load_or_initialize_state(self) -> dict[str, Any]:
        if self.config.state_path.exists():
            state = load_monitor_state(self.config.state_path, allowed_roots=self.config.allowed_artifact_roots)
            if state.get("runtime_id") != self.config.runtime_id:
                raise P131StateError("runtime_id_mismatch")
            if state.get("config_hash") != self.config.config_hash:
                raise P131StateError("config_hash_mismatch")
            _validate_configured_sources(state, self.config.sources)
            if "lifecycle" not in state:
                state["lifecycle"] = {
                    "phase": "running",
                    "last_stop_reason": None,
                    "last_stop_requested_at": None,
                    "last_stopped_at": None,
                    "graceful_stop_count": 0,
                }
            return state
        now = _timestamp(self.clock.now())
        return {
            "schema_version": STATE_SCHEMA_VERSION,
            "runtime_id": self.config.runtime_id,
            "config_hash": self.config.config_hash,
            "started_at": now,
            "last_heartbeat_at": None,
            "last_cycle_at": None,
            "last_report_at": None,
            "last_report_bucket": None,
            "cycle_count": 0,
            "resume_count": 0,
            "status": "starting",
            "lifecycle": {
                "phase": "starting",
                "last_stop_reason": None,
                "last_stop_requested_at": None,
                "last_stopped_at": None,
                "graceful_stop_count": 0,
            },
            "process_health": {"heartbeat_current": False},
            "scheduler": {"last_progress_at": None, "missed_tick_count": 0, "next_delay_seconds": None},
            "source_health": {
                source.source_id: {
                    "kind": "local_jsonl",
                    "path_hash": stable_hash(str(source.path)),
                    "enabled": source.enabled,
                    "cursor_bytes": 0,
                    "file_identity": None,
                    "prefix_length": 0,
                    "prefix_hash": None,
                    "last_data_at": None,
                    "last_success_at": None,
                    "last_error": None,
                    "consecutive_failures": 0,
                    "failure_limit": self.config.max_consecutive_failures,
                    "rotation_count": 0,
                }
                for source in self.config.sources
            },
            "canary": {
                "last_result": "not_run",
                "last_run_at": None,
                "success_count": 0,
                "failure_count": 0,
                "last_stages": {
                    "serialization_round_trip_passed": False,
                    "signal_detection_passed": False,
                    "policy_no_action_passed": False,
                },
                "action_execution_count": 0,
            },
            "totals": {
                "accepted_observation_count": 0,
                "duplicate_observation_count": 0,
                "source_failure_count": 0,
                "action_execution_count": 0,
                "network_call_count": 0,
            },
            "recent_observation_hashes": [],
            "authority": _authority_snapshot(),
        }

    def _run_cycle(self, state: dict[str, Any]) -> dict[str, int]:
        observed_at = self.clock.now()
        accepted = 0
        duplicates = 0
        failures = 0
        for source in self.config.sources:
            if not source.enabled:
                continue
            result = self._poll_local_jsonl(source, state, observed_at)
            accepted += result["accepted"]
            duplicates += result["duplicates"]
            failures += result["failures"]

        state["cycle_count"] = int(state["cycle_count"]) + 1
        state["last_cycle_at"] = _timestamp(observed_at)
        state["last_heartbeat_at"] = _timestamp(observed_at)
        lifecycle = _mapping_dict(state.get("lifecycle"))
        lifecycle["phase"] = "running"
        state["lifecycle"] = lifecycle
        state["process_health"] = {"heartbeat_current": True}
        scheduler = _mapping_dict(state.get("scheduler"))
        scheduler["last_progress_at"] = _timestamp(observed_at)
        state["scheduler"] = scheduler
        totals = _mapping_dict(state["totals"])
        totals["accepted_observation_count"] = int(totals["accepted_observation_count"]) + accepted
        totals["duplicate_observation_count"] = int(totals["duplicate_observation_count"]) + duplicates
        totals["source_failure_count"] = int(totals["source_failure_count"]) + failures
        state["totals"] = totals

        if state.get("canary", {}).get("last_run_at") is None or int(state["cycle_count"]) % self.config.canary_every_cycles == 0:
            self._run_canary(state, observed_at)
        status = _status_from_state(
            state,
            now=observed_at,
            heartbeat_timeout_seconds=self.config.heartbeat_timeout_seconds,
            data_stale_after_seconds=self.config.data_stale_after_seconds,
        )
        state["status"] = "ready" if status["ready"] else "degraded"
        return {
            "cycle_count": 1,
            "accepted_observation_count": accepted,
            "duplicate_observation_count": duplicates,
            "source_failure_count": failures,
        }

    def _schedule_next(self, state: dict[str, Any], anchor: float, tick_index: int) -> tuple[float, int]:
        interval = float(self.config.interval_seconds)
        deadline = anchor + tick_index * interval
        current = _clock_monotonic(self.clock)
        missed = 0
        if current > deadline:
            missed = int((current - deadline) // interval) + 1
            tick_index += missed
            deadline = anchor + tick_index * interval
        delay = max(0.0, deadline - current)
        scheduler = _mapping_dict(state.get("scheduler"))
        scheduler["missed_tick_count"] = int(scheduler.get("missed_tick_count", 0)) + missed
        scheduler["next_delay_seconds"] = delay
        state["scheduler"] = scheduler
        return delay, tick_index + 1

    def _poll_local_jsonl(self, source: LocalJsonlSource, state: dict[str, Any], observed_at: datetime) -> dict[str, int]:
        source_health = _mapping_dict(_mapping_dict(state["source_health"])[source.source_id])
        accepted = 0
        duplicates = 0
        failures = 0
        try:
            with _open_source_binary(source) as handle:
                stat = os.fstat(handle.fileno())
                identity = f"{stat.st_dev}:{stat.st_ino}"
                cursor = int(source_health.get("cursor_bytes", 0))
                prefix_changed = _source_prefix_changed(handle, source_health, identity)
                if source_health.get("file_identity") not in (None, identity) or stat.st_size < cursor or prefix_changed:
                    cursor = 0
                    source_health["rotation_count"] = int(source_health.get("rotation_count", 0)) + 1
                recent = list(state.get("recent_observation_hashes", []))
                recent_set = set(str(value) for value in recent)
                handle.seek(cursor)
                bytes_read = 0
                records_read = 0
                while True:
                    line_start = handle.tell()
                    line = handle.readline(self.config.max_line_bytes + 1)
                    if not line:
                        break
                    if len(line) > self.config.max_line_bytes:
                        failures += 1
                        handle.seek(line_start)
                        break
                    if bytes_read + len(line) > self.config.max_bytes_per_cycle or records_read >= self.config.max_records_per_cycle:
                        handle.seek(line_start)
                        break
                    if not line.endswith(b"\n"):
                        handle.seek(line_start)
                        break
                    cursor = handle.tell()
                    bytes_read += len(line)
                    records_read += 1
                    try:
                        value = json.loads(line.decode("utf-8"))
                        if not isinstance(value, Mapping):
                            raise ValueError("observation_not_mapping")
                    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                        failures += 1
                        continue
                    observation_hash = _observation_identity(source.source_id, value, file_identity=identity, offset=line_start)
                    if observation_hash in recent_set:
                        duplicates += 1
                        continue
                    recent.append(observation_hash)
                    recent_set.add(observation_hash)
                    accepted += 1
                prefix_length, prefix_hash = _source_prefix(handle)
            state["recent_observation_hashes"] = recent[-MAX_RECENT_OBSERVATION_HASHES:]
            source_health.update(
                {
                    "cursor_bytes": cursor,
                    "file_identity": identity,
                    "prefix_length": prefix_length,
                    "prefix_hash": prefix_hash,
                    "last_success_at": _timestamp(observed_at),
                    "last_error": None,
                    "consecutive_failures": 0 if failures == 0 else int(source_health.get("consecutive_failures", 0)) + 1,
                }
            )
            if accepted:
                source_health["last_data_at"] = _timestamp(observed_at)
            if failures:
                source_health["last_error"] = "invalid_jsonl_observation"
        except OSError:
            failures += 1
            source_health["last_error"] = "source_unavailable"
            source_health["consecutive_failures"] = int(source_health.get("consecutive_failures", 0)) + 1
        source_map = _mapping_dict(state["source_health"])
        source_map[source.source_id] = source_health
        state["source_health"] = source_map
        return {"accepted": accepted, "duplicates": duplicates, "failures": failures}

    def _run_canary(self, state: dict[str, Any], observed_at: datetime) -> None:
        canary = _mapping_dict(state["canary"])
        try:
            result = self.canary_probe()
        except Exception:
            result = False
        if isinstance(result, Mapping):
            stages = {
                "serialization_round_trip_passed": result.get("serialization_round_trip_passed") is True,
                "signal_detection_passed": result.get("signal_detection_passed") is True,
                "policy_no_action_passed": result.get("policy_no_action_passed") is True,
            }
            passed = all(stages.values()) and result.get("action_execution_count") == 0
        else:
            passed = result is True
            stages = {
                "serialization_round_trip_passed": passed,
                "signal_detection_passed": passed,
                "policy_no_action_passed": passed,
            }
        canary["last_result"] = "passed" if passed else "failed"
        canary["last_run_at"] = _timestamp(observed_at)
        canary["last_stages"] = stages
        count_key = "success_count" if passed else "failure_count"
        canary[count_key] = int(canary[count_key]) + 1
        canary["action_execution_count"] = 0
        state["canary"] = canary

    def _persist_state(self, state: dict[str, Any]) -> None:
        _validate_runtime_boundary(state)
        payload = {key: value for key, value in state.items() if key != "state_hash"}
        payload["state_hash"] = stable_hash(payload)
        state.clear()
        state.update(payload)
        self._ensure_artifact_space(self.config.state_path, write_bytes=len(_json_bytes(state)))
        _atomic_write_json(self.config.state_path, state, allowed_roots=self.config.allowed_artifact_roots)

    def _graceful_stop(self, state: dict[str, Any], reason: str) -> dict[str, Any]:
        if reason not in {"sigterm", "sigint"}:
            raise ValueError("unsupported_stop_reason")
        requested_at = _timestamp(self.clock.now())
        lifecycle = _mapping_dict(state.get("lifecycle"))
        lifecycle.update(
            {
                "phase": "stopped",
                "last_stop_reason": reason,
                "last_stop_requested_at": requested_at,
                "last_stopped_at": _timestamp(self.clock.now()),
                "graceful_stop_count": int(lifecycle.get("graceful_stop_count", 0)) + 1,
            }
        )
        state["lifecycle"] = lifecycle
        state["status"] = "stopped"
        state["process_health"] = {"heartbeat_current": False}
        scheduler = _mapping_dict(state.get("scheduler"))
        scheduler["next_delay_seconds"] = None
        state["scheduler"] = scheduler
        self._persist_state(state)
        receipt: dict[str, Any] = {
            "schema_version": TERMINATION_RECEIPT_SCHEMA_VERSION,
            "runtime_id": self.config.runtime_id,
            "config_hash": self.config.config_hash,
            "reason": reason,
            "stop_requested_at": requested_at,
            "stopped_at": lifecycle["last_stopped_at"],
            "final_cycle_count": state["cycle_count"],
            "final_state_hash": state["state_hash"],
        }
        receipt["receipt_hash"] = stable_hash(receipt)
        self._ensure_artifact_space(
            self.config.termination_receipt_path,
            write_bytes=len(_json_bytes(receipt)),
        )
        _atomic_write_json(
            self.config.termination_receipt_path,
            receipt,
            allowed_roots=self.config.allowed_artifact_roots,
        )
        return receipt

    def _ensure_artifact_space(self, path: Path, *, write_bytes: int) -> None:
        required_free = self.config.min_artifact_free_bytes + write_bytes
        if _artifact_free_bytes(path, self.config.allowed_artifact_roots) < required_free:
            raise OSError(errno.ENOSPC, "artifact_free_space_below_floor")

    def _write_report_if_due(self, state: dict[str, Any]) -> None:
        now = self.clock.now()
        current_bucket = int(now.astimezone(UTC).timestamp()) // self.config.daily_report_interval_seconds
        if state.get("last_report_bucket") == current_bucket:
            self._prepare_report_capacity(0)
            return
        status = _status_from_state(
            state,
            now=now,
            heartbeat_timeout_seconds=self.config.heartbeat_timeout_seconds,
            data_stale_after_seconds=self.config.data_stale_after_seconds,
        )
        generated_at = _timestamp(now)
        report: dict[str, Any] = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "runtime_id": self.config.runtime_id,
            "config_hash": self.config.config_hash,
            "generated_at": generated_at,
            "status": status,
            "cycle_count": state["cycle_count"],
            "resume_count": state["resume_count"],
            "totals": state["totals"],
            "source_health": state["source_health"],
            "canary": state["canary"],
            "authority": _authority_snapshot(),
            "state_hash": state.get("state_hash"),
        }
        report["report_hash"] = stable_hash(report)
        bucket_start = datetime.fromtimestamp(current_bucket * self.config.daily_report_interval_seconds, tz=UTC)
        filename = f"p131-health-{bucket_start.strftime('%Y%m%dT%H%M%SZ')}.json"
        report_path = self.config.report_dir / filename
        report_bytes = len(_json_bytes(report))
        self._prepare_report_capacity(report_bytes, prospective_name=filename)
        self._ensure_artifact_space(report_path, write_bytes=report_bytes)
        _atomic_write_json(report_path, report, allowed_roots=self.config.allowed_artifact_roots)
        state["last_report_at"] = generated_at
        state["last_report_bucket"] = current_bucket
        self._persist_state(state)

    def _prepare_report_capacity(self, prospective_bytes: int, *, prospective_name: str | None = None) -> None:
        if prospective_bytes > self.config.max_report_dir_bytes:
            raise OSError(errno.ENOSPC, "report_exceeds_directory_budget")
        parent_fd, _ = _open_artifact_parent(
            self.config.report_dir / ".retention-sentinel",
            self.config.allowed_artifact_roots,
            create=True,
        )
        candidates: list[tuple[str, int, int, int]] = []
        try:
            with os.scandir(parent_fd) as entries:
                for entry in entries:
                    if _REPORT_FILENAME.fullmatch(entry.name) is None:
                        continue
                    size, device, inode = self._validated_report_candidate(parent_fd, entry.name)
                    candidates.append((entry.name, size, device, inode))

            candidates.sort()
            retained = [candidate for candidate in candidates if candidate[0] != prospective_name]
            total_bytes = sum(size for _, size, _, _ in retained) + prospective_bytes
            projected_count = len(retained) + (1 if prospective_name is not None else 0)
            removed = False
            while retained and (
                projected_count > self.config.max_report_files
                or total_bytes > self.config.max_report_dir_bytes
            ):
                name, size, device, inode = retained.pop(0)
                current_size, current_device, current_inode = self._validated_report_candidate(parent_fd, name)
                if (current_size, current_device, current_inode) != (size, device, inode):
                    raise P131StateError("report_retention_candidate_changed")
                os.unlink(name, dir_fd=parent_fd)
                total_bytes -= size
                projected_count -= 1
                removed = True
            if projected_count > self.config.max_report_files or total_bytes > self.config.max_report_dir_bytes:
                raise OSError(errno.ENOSPC, "report_retention_budget_exhausted")
            if removed:
                os.fsync(parent_fd)
        finally:
            os.close(parent_fd)

    def _validated_report_candidate(self, parent_fd: int, name: str) -> tuple[int, int, int]:
        try:
            flags = (
                os.O_RDONLY
                | getattr(os, "O_NONBLOCK", 0)
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0)
            )
            file_fd = os.open(name, flags, dir_fd=parent_fd)
            try:
                metadata = os.fstat(file_fd)
                payload = json.loads(_read_bounded_text(file_fd))
            except Exception:
                try:
                    os.close(file_fd)
                except OSError:
                    pass
                raise
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise P131StateError("report_retention_candidate_invalid") from exc
        if (
            not stat.S_ISREG(metadata.st_mode)
            or not isinstance(payload, Mapping)
            or payload.get("schema_version") != REPORT_SCHEMA_VERSION
            or payload.get("runtime_id") != self.config.runtime_id
            or payload.get("config_hash") != self.config.config_hash
            or payload.get("report_hash")
            != stable_hash({key: value for key, value in payload.items() if key != "report_hash"})
        ):
            raise P131StateError("report_retention_candidate_invalid")
        return int(metadata.st_size), int(metadata.st_dev), int(metadata.st_ino)


def load_monitor_state(path: Path | str, *, allowed_roots: Sequence[Path] | None = None) -> dict[str, Any]:
    """Read and verify one tamper-evident monitor checkpoint."""

    try:
        payload = json.loads(_read_text(Path(path), allowed_roots=allowed_roots))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise P131StateError("state_invalid") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != STATE_SCHEMA_VERSION:
        raise P131StateError("state_invalid")
    claimed_hash = payload.get("state_hash")
    unsigned = {key: value for key, value in payload.items() if key != "state_hash"}
    if claimed_hash != stable_hash(unsigned):
        raise P131StateError("state_hash_invalid")
    _validate_runtime_boundary(payload)
    _validate_checkpoint_shape(payload)
    _validate_source_state_shape(payload)
    _validate_state_timestamps(payload)
    return payload


def evaluate_watchdog(path: Path | str, *, now: datetime, heartbeat_timeout_seconds: int) -> dict[str, Any]:
    """Independently assess whether the monitor process is still heartbeating."""

    state_path = Path(path)
    if not state_path.exists():
        return {"schema_version": "p131.watchdog.v1", "healthy": False, "reason": "state_missing"}
    try:
        state = load_monitor_state(state_path)
    except P131StateError as exc:
        return {"schema_version": "p131.watchdog.v1", "healthy": False, "reason": str(exc)}
    lifecycle = state.get("lifecycle")
    if isinstance(lifecycle, Mapping) and lifecycle.get("phase") == "stopped":
        return {
            "schema_version": "p131.watchdog.v1",
            "healthy": False,
            "reason": "runtime_stopped",
            "runtime_id": state.get("runtime_id"),
            "state_hash": state.get("state_hash"),
        }
    heartbeat = state.get("last_heartbeat_at")
    if not isinstance(heartbeat, str):
        return {"schema_version": "p131.watchdog.v1", "healthy": False, "reason": "heartbeat_missing"}
    age = (now.astimezone(UTC) - _parse_timestamp(heartbeat)).total_seconds()
    if age < -MAX_FUTURE_CLOCK_SKEW_SECONDS:
        return {
            "schema_version": "p131.watchdog.v1",
            "healthy": False,
            "reason": "heartbeat_in_future",
            "heartbeat_age_seconds": age,
            "runtime_id": state.get("runtime_id"),
            "state_hash": state.get("state_hash"),
        }
    healthy = age <= heartbeat_timeout_seconds
    return {
        "schema_version": "p131.watchdog.v1",
        "healthy": healthy,
        "reason": "heartbeat_current" if healthy else "heartbeat_stale",
        "heartbeat_age_seconds": age,
        "runtime_id": state.get("runtime_id"),
        "state_hash": state.get("state_hash"),
    }


def monitor_status_snapshot(
    path: Path | str,
    *,
    now: datetime,
    heartbeat_timeout_seconds: int = 180,
    data_stale_after_seconds: int = 300,
) -> dict[str, Any]:
    """Return liveness and readiness without mutating runtime state."""

    if not Path(path).exists():
        return {"schema_version": "p131.monitor_status.v1", "live": False, "ready": False, "reasons": ["state_missing"]}
    try:
        state = load_monitor_state(path)
    except P131StateError as exc:
        return {"schema_version": "p131.monitor_status.v1", "live": False, "ready": False, "reasons": [str(exc)]}
    return _status_from_state(
        state,
        now=now,
        heartbeat_timeout_seconds=heartbeat_timeout_seconds,
        data_stale_after_seconds=data_stale_after_seconds,
    )


def _status_from_state(
    state: Mapping[str, Any],
    *,
    now: datetime,
    heartbeat_timeout_seconds: int,
    data_stale_after_seconds: int,
) -> dict[str, Any]:
    lifecycle = state.get("lifecycle")
    if isinstance(lifecycle, Mapping) and lifecycle.get("phase") == "stopped":
        return {
            "schema_version": "p131.monitor_status.v1",
            "runtime_id": state.get("runtime_id"),
            "live": False,
            "ready": False,
            "reasons": ["runtime_stopped"],
            "last_heartbeat_at": state.get("last_heartbeat_at"),
            "state_hash": state.get("state_hash"),
        }
    reasons: list[str] = []
    heartbeat = state.get("last_heartbeat_at")
    heartbeat_age = None if not isinstance(heartbeat, str) else (now.astimezone(UTC) - _parse_timestamp(heartbeat)).total_seconds()
    live = heartbeat_age is not None and -MAX_FUTURE_CLOCK_SKEW_SECONDS <= heartbeat_age <= heartbeat_timeout_seconds
    if heartbeat is None:
        reasons.append("heartbeat_missing")
    elif heartbeat_age is not None and heartbeat_age < -MAX_FUTURE_CLOCK_SKEW_SECONDS:
        reasons.append("heartbeat_in_future")
    elif not live:
        reasons.append("heartbeat_stale")
    canary = state.get("canary")
    if not isinstance(canary, Mapping) or canary.get("last_result") != "passed":
        reasons.append("canary_failed")
    source_health = state.get("source_health")
    enabled_sources = [] if not isinstance(source_health, Mapping) else [value for value in source_health.values() if isinstance(value, Mapping) and value.get("enabled") is True]
    for source in enabled_sources:
        if int(source.get("consecutive_failures", 0)) >= int(source.get("failure_limit", 1)):
            reasons.append("source_failure_limit_exceeded")
        last_data = source.get("last_data_at")
        if not isinstance(last_data, str):
            reasons.append("source_data_missing")
            continue
        source_age = (now.astimezone(UTC) - _parse_timestamp(last_data)).total_seconds()
        if source_age < -MAX_FUTURE_CLOCK_SKEW_SECONDS:
            reasons.append("source_data_in_future")
        elif source_age > data_stale_after_seconds:
            reasons.append("source_data_stale")
    ready = live and not reasons
    return {
        "schema_version": "p131.monitor_status.v1",
        "runtime_id": state.get("runtime_id"),
        "live": live,
        "ready": ready,
        "reasons": list(dict.fromkeys(reasons)),
        "last_heartbeat_at": heartbeat,
        "state_hash": state.get("state_hash"),
    }


class _RuntimeLease:
    def __init__(self, path: Path, runtime_id: str, allowed_roots: Sequence[Path]) -> None:
        self.path = path
        self.runtime_id = runtime_id
        self.allowed_roots = tuple(allowed_roots)
        self.handle: Any = None

    def __enter__(self) -> None:
        parent_fd, name = _open_artifact_parent(self.path, self.allowed_roots, create=True)
        try:
            flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
            file_fd = os.open(name, flags, 0o600, dir_fd=parent_fd)
        finally:
            os.close(parent_fd)
        if not stat.S_ISREG(os.fstat(file_fd).st_mode):
            os.close(file_fd)
            raise OSError("runtime_lease_not_regular_file")
        self.handle = os.fdopen(file_fd, "a+", encoding="utf-8")
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self.handle.close()
            raise P131LeaseError("runtime_lease_unavailable") from exc
        self.handle.seek(0)
        self.handle.truncate()
        self.handle.write(json.dumps({"runtime_id": self.runtime_id, "pid": os.getpid()}, sort_keys=True) + "\n")
        self.handle.flush()
        os.fsync(self.handle.fileno())

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self.handle is not None:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()


def _default_canary_probe() -> Mapping[str, Any]:
    encoded = json.dumps({"kind": "synthetic_read_only", "signal": "p131-canary", "value": 1}, sort_keys=True)
    observation = json.loads(encoded)
    round_trip = isinstance(observation, Mapping) and observation.get("kind") == "synthetic_read_only"
    detected = round_trip and observation.get("signal") == "p131-canary" and observation.get("value") == 1
    no_action = detected and _authority_snapshot()["exact_zero"] is True
    return {
        "serialization_round_trip_passed": round_trip,
        "signal_detection_passed": detected,
        "policy_no_action_passed": no_action,
        "action_execution_count": 0,
    }


def _authority_snapshot() -> dict[str, Any]:
    return {"exact_zero": True, "counters": zero_authority_counters()}


def _validate_runtime_boundary(state: Mapping[str, Any]) -> None:
    authority = state.get("authority")
    counters = authority.get("counters") if isinstance(authority, Mapping) else None
    if (
        not isinstance(authority, Mapping)
        or authority.get("exact_zero") is not True
        or not isinstance(counters, Mapping)
        or set(counters) != set(P121_AUTHORITY_COUNTER_KEYS)
        or any(type(counters.get(key)) is not int or counters.get(key) != 0 for key in P121_AUTHORITY_COUNTER_KEYS)
    ):
        raise P131StateError("authority_not_exact_zero")
    totals = state.get("totals")
    canary = state.get("canary")
    if (
        not isinstance(totals, Mapping)
        or type(totals.get("action_execution_count")) is not int
        or totals.get("action_execution_count") != 0
        or type(totals.get("network_call_count")) is not int
        or totals.get("network_call_count") != 0
        or not isinstance(canary, Mapping)
        or type(canary.get("action_execution_count")) is not int
        or canary.get("action_execution_count") != 0
    ):
        raise P131StateError("runtime_execution_boundary_violated")


def _observation_identity(source_id: str, value: Mapping[str, Any], *, file_identity: str, offset: int) -> str:
    for field in ("event_id", "id"):
        event_id = value.get(field)
        if isinstance(event_id, str) and event_id.strip():
            return stable_hash({"source_id": source_id, "event_id": event_id.strip()})
    timestamp = value.get("timestamp")
    if isinstance(timestamp, str) and timestamp.strip():
        return stable_hash({"source_id": source_id, "timestamp": timestamp.strip(), "observation": value})
    return stable_hash({"source_id": source_id, "file_identity": file_identity, "offset": offset, "observation": value})


def _source_prefix_changed(handle: BinaryIO, source_health: Mapping[str, Any], identity: str) -> bool:
    previous_identity = source_health.get("file_identity")
    previous_length = source_health.get("prefix_length", 0)
    previous_hash = source_health.get("prefix_hash")
    if previous_identity != identity or not isinstance(previous_length, int) or previous_length <= 0 or not isinstance(previous_hash, str):
        return False
    handle.seek(0)
    current = handle.read(previous_length)
    return len(current) != previous_length or stable_hash(current.hex()) != previous_hash


def _source_prefix(handle: BinaryIO) -> tuple[int, str]:
    handle.seek(0)
    prefix = handle.read(4_096)
    return len(prefix), stable_hash(prefix.hex())


@contextmanager
def _open_source_binary(source: LocalJsonlSource) -> Iterator[BinaryIO]:
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    file_flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    directory_fd = os.open("/", directory_flags)
    try:
        for component in source.allowed_root.parts[1:]:
            next_fd = os.open(component, directory_flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd
        relative_parts = source.relative_path.parts
        if not relative_parts:
            raise OSError("source_path_is_directory")
        for component in relative_parts[:-1]:
            next_fd = os.open(component, directory_flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd
        file_fd = os.open(relative_parts[-1], file_flags, dir_fd=directory_fd)
        if not stat.S_ISREG(os.fstat(file_fd).st_mode):
            os.close(file_fd)
            raise OSError("source_not_regular_file")
        with os.fdopen(file_fd, "rb") as handle:
            yield handle
    finally:
        os.close(directory_fd)


def _validate_state_timestamps(state: Mapping[str, Any]) -> None:
    for key in ("started_at", "last_heartbeat_at", "last_cycle_at", "last_report_at"):
        value = state.get(key)
        if value is not None:
            _parse_timestamp(value)
    canary = state.get("canary")
    if isinstance(canary, Mapping) and canary.get("last_run_at") is not None:
        _parse_timestamp(canary.get("last_run_at"))
    scheduler = state.get("scheduler")
    if isinstance(scheduler, Mapping) and scheduler.get("last_progress_at") is not None:
        _parse_timestamp(scheduler.get("last_progress_at"))
    lifecycle = state.get("lifecycle")
    if isinstance(lifecycle, Mapping):
        for key in ("last_stop_requested_at", "last_stopped_at"):
            if lifecycle.get(key) is not None:
                _parse_timestamp(lifecycle.get(key))
    source_health = state.get("source_health")
    if isinstance(source_health, Mapping):
        for source in source_health.values():
            if not isinstance(source, Mapping):
                raise P131StateError("invalid_source_state")
            for key in ("last_data_at", "last_success_at"):
                if source.get(key) is not None:
                    _parse_timestamp(source.get(key))


def _validate_checkpoint_shape(state: Mapping[str, Any]) -> None:
    if not all(isinstance(state.get(key), str) and state.get(key) for key in ("runtime_id", "config_hash")):
        raise P131StateError("state_invalid")
    if state.get("status") not in {"starting", "ready", "degraded", "stopped"}:
        raise P131StateError("state_invalid")
    _validate_lifecycle_state(state)
    for key in ("cycle_count", "resume_count"):
        if type(state.get(key)) is not int or int(state[key]) < 0:
            raise P131StateError("state_invalid")
    process_health = state.get("process_health")
    if not isinstance(process_health, Mapping) or not isinstance(process_health.get("heartbeat_current"), bool):
        raise P131StateError("state_invalid")
    scheduler = state.get("scheduler")
    if not isinstance(scheduler, Mapping) or type(scheduler.get("missed_tick_count")) is not int or int(scheduler["missed_tick_count"]) < 0:
        raise P131StateError("state_invalid")
    delay = scheduler.get("next_delay_seconds")
    if delay is not None and (isinstance(delay, bool) or not isinstance(delay, (int, float)) or float(delay) < 0):
        raise P131StateError("state_invalid")
    totals = state.get("totals")
    if not isinstance(totals, Mapping):
        raise P131StateError("state_invalid")
    for key in ("accepted_observation_count", "duplicate_observation_count", "source_failure_count"):
        if type(totals.get(key)) is not int or int(totals[key]) < 0:
            raise P131StateError("state_invalid")
    recent = state.get("recent_observation_hashes")
    if (
        not isinstance(recent, list)
        or len(recent) > MAX_RECENT_OBSERVATION_HASHES
        or any(not isinstance(value, str) or not value for value in recent)
    ):
        raise P131StateError("state_invalid")
    canary = state.get("canary")
    if not isinstance(canary, Mapping) or canary.get("last_result") not in {"not_run", "passed", "failed"}:
        raise P131StateError("invalid_canary_state")
    for key in ("success_count", "failure_count"):
        if type(canary.get(key)) is not int or int(canary[key]) < 0:
            raise P131StateError("invalid_canary_state")
    stages = canary.get("last_stages")
    stage_keys = {
        "serialization_round_trip_passed",
        "signal_detection_passed",
        "policy_no_action_passed",
    }
    if not isinstance(stages, Mapping) or set(stages) != stage_keys or any(not isinstance(stages.get(key), bool) for key in stage_keys):
        raise P131StateError("invalid_canary_state")
    result = canary.get("last_result")
    if result == "passed" and (
        not isinstance(canary.get("last_run_at"), str)
        or int(canary["success_count"]) <= 0
        or not all(stages.get(key) is True for key in stage_keys)
    ):
        raise P131StateError("invalid_canary_state")
    if result == "failed" and (not isinstance(canary.get("last_run_at"), str) or int(canary["failure_count"]) <= 0):
        raise P131StateError("invalid_canary_state")
    if result == "not_run" and (
        canary.get("last_run_at") is not None
        or int(canary["success_count"]) != 0
        or int(canary["failure_count"]) != 0
        or any(stages.get(key) is not False for key in stage_keys)
    ):
        raise P131StateError("invalid_canary_state")


def _validate_lifecycle_state(state: Mapping[str, Any]) -> None:
    lifecycle = state.get("lifecycle")
    if lifecycle is None:
        if state.get("status") == "stopped":
            raise P131StateError("invalid_lifecycle_state")
        return
    fields = {
        "phase",
        "last_stop_reason",
        "last_stop_requested_at",
        "last_stopped_at",
        "graceful_stop_count",
    }
    if not isinstance(lifecycle, Mapping) or set(lifecycle) != fields:
        raise P131StateError("invalid_lifecycle_state")
    phase = lifecycle.get("phase")
    reason = lifecycle.get("last_stop_reason")
    requested_at = lifecycle.get("last_stop_requested_at")
    stopped_at = lifecycle.get("last_stopped_at")
    count = lifecycle.get("graceful_stop_count")
    if phase not in {"starting", "running", "stopped"} or type(count) is not int or int(count) < 0:
        raise P131StateError("invalid_lifecycle_state")
    if (state.get("status") == "stopped") != (phase == "stopped"):
        raise P131StateError("invalid_lifecycle_state")
    if count == 0:
        if any(value is not None for value in (reason, requested_at, stopped_at)) or phase == "stopped":
            raise P131StateError("invalid_lifecycle_state")
        return
    if reason not in {"sigterm", "sigint"} or not isinstance(requested_at, str) or not isinstance(stopped_at, str):
        raise P131StateError("invalid_lifecycle_state")


def _validate_source_state_shape(state: Mapping[str, Any]) -> None:
    source_health = state.get("source_health")
    if not isinstance(source_health, Mapping) or not source_health:
        raise P131StateError("invalid_source_state")
    enabled_count = 0
    for source_id, source in source_health.items():
        if not isinstance(source_id, str) or not source_id or not isinstance(source, Mapping):
            raise P131StateError("invalid_source_state")
        enabled = source.get("enabled")
        nonnegative_int_fields = ("cursor_bytes", "prefix_length", "consecutive_failures", "rotation_count")
        if (
            source.get("kind") != "local_jsonl"
            or not isinstance(source.get("path_hash"), str)
            or not source.get("path_hash")
            or not isinstance(enabled, bool)
            or any(type(source.get(field)) is not int or int(source[field]) < 0 for field in nonnegative_int_fields)
            or type(source.get("failure_limit")) is not int
            or int(source["failure_limit"]) <= 0
            or (source.get("file_identity") is not None and (not isinstance(source.get("file_identity"), str) or not source.get("file_identity")))
            or (source.get("prefix_hash") is not None and (not isinstance(source.get("prefix_hash"), str) or not source.get("prefix_hash")))
            or (source.get("last_error") is not None and not isinstance(source.get("last_error"), str))
        ):
            raise P131StateError("invalid_source_state")
        file_identity = source.get("file_identity")
        prefix_length = int(source["prefix_length"])
        prefix_hash = source.get("prefix_hash")
        if (file_identity is None and (prefix_length != 0 or prefix_hash is not None)) or (file_identity is not None and prefix_hash is None):
            raise P131StateError("invalid_source_state")
        enabled_count += int(enabled)
    if enabled_count == 0:
        raise P131StateError("invalid_source_state")


def _validate_configured_sources(state: Mapping[str, Any], sources: Sequence[LocalJsonlSource]) -> None:
    source_health = state.get("source_health")
    expected = {
        source.source_id: {
            "enabled": source.enabled,
            "kind": "local_jsonl",
            "path_hash": stable_hash(str(source.path)),
        }
        for source in sources
    }
    if not isinstance(source_health, Mapping) or set(source_health) != set(expected):
        raise P131StateError("source_manifest_mismatch")
    for source_id, expected_source in expected.items():
        value = source_health.get(source_id)
        if not isinstance(value, Mapping) or any(value.get(key) != expected_value for key, expected_value in expected_source.items()):
            raise P131StateError("source_manifest_mismatch")


def _atomic_write_json(path: Path, value: object, *, allowed_roots: Sequence[Path] | None = None) -> None:
    if allowed_roots is None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        temporary = Path(temporary_name)
        replaced = False
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            replaced = True
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError as exc:
            if replaced:
                raise P131DurabilityUncertainError("directory_fsync_failed_after_replace") from exc
            raise
        finally:
            temporary.unlink(missing_ok=True)
        return

    parent_fd, name = _open_artifact_parent(path, allowed_roots, create=True)
    temporary_name = f".{name}.{os.getpid()}.{time.time_ns()}.tmp"
    replaced = False
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        descriptor = os.open(temporary_name, flags, 0o600, dir_fd=parent_fd)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        replaced = True
        os.fsync(parent_fd)
    except OSError as exc:
        if replaced:
            raise P131DurabilityUncertainError("directory_fsync_failed_after_replace") from exc
        raise
    finally:
        try:
            os.unlink(temporary_name, dir_fd=parent_fd)
        except FileNotFoundError:
            pass
        os.close(parent_fd)


def _artifact_free_bytes(path: Path, allowed_roots: Sequence[Path]) -> int:
    parent_fd, _ = _open_artifact_parent(path, allowed_roots, create=True)
    try:
        filesystem = os.fstatvfs(parent_fd)
        return int(filesystem.f_bavail) * int(filesystem.f_frsize)
    finally:
        os.close(parent_fd)


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode("utf-8")


def _read_text(path: Path, *, allowed_roots: Sequence[Path] | None) -> str:
    if allowed_roots is None:
        flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        file_fd = os.open(path, flags)
        return _read_bounded_text(file_fd)
    parent_fd, name = _open_artifact_parent(path, allowed_roots, create=False)
    try:
        flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        file_fd = os.open(name, flags, dir_fd=parent_fd)
        return _read_bounded_text(file_fd)
    finally:
        os.close(parent_fd)


def _read_bounded_text(file_fd: int) -> str:
    metadata = os.fstat(file_fd)
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_STATE_BYTES:
        os.close(file_fd)
        raise OSError("state_file_invalid")
    with os.fdopen(file_fd, "r", encoding="utf-8") as handle:
        value = handle.read(MAX_STATE_BYTES + 1)
    if len(value.encode("utf-8")) > MAX_STATE_BYTES:
        raise OSError("state_file_too_large")
    return value


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
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
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
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
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


def _reject_forbidden_fields(value: object) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = str(key).lower()
            if any(token in normalized for token in _FORBIDDEN_FIELD_TOKENS):
                raise P131ConfigError("forbidden_configuration_field")
            _reject_forbidden_fields(nested)
    elif _is_sequence(value):
        for nested in cast(Sequence[Any], value):
            _reject_forbidden_fields(nested)


def _required_text(value: Mapping[str, Any], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result.strip():
        raise P131ConfigError(f"missing_{key}")
    return result.strip()


def _positive_int(value: Mapping[str, Any], key: str, error: str) -> int:
    result = value.get(key)
    if not isinstance(result, int) or isinstance(result, bool) or result <= 0:
        raise P131ConfigError(error)
    return result


def _optional_positive_int(value: Mapping[str, Any], key: str, default: int) -> int:
    result = value.get(key, default)
    if not isinstance(result, int) or isinstance(result, bool) or result <= 0:
        raise P131ConfigError(f"{key}_must_be_positive")
    return result


def _optional_bounded_positive_int(value: Mapping[str, Any], key: str, default: int, maximum: int) -> int:
    result = _optional_positive_int(value, key, default)
    if result > maximum:
        raise P131ConfigError(f"{key}_exceeds_maximum")
    return result


def _resolve_path(base: Path, value: object) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise P131ConfigError("invalid_path")
    path = Path(value).expanduser()
    return (path if path.is_absolute() else base / path).resolve()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _is_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _mapping_dict(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("naive_datetime_not_allowed")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise P131StateError("invalid_timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise P131StateError("invalid_timestamp") from exc
    if parsed.tzinfo is None:
        raise P131StateError("invalid_timestamp")
    return parsed.astimezone(UTC)


def _clock_monotonic(clock: Clock) -> float:
    monotonic = getattr(clock, "monotonic", None)
    if callable(monotonic):
        return float(monotonic())
    return clock.now().timestamp()
