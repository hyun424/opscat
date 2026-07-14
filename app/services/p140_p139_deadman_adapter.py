"""Credential-free P139 health adapter for the P133 local dead-man outbox."""

from __future__ import annotations

import fcntl
import json
import math
import os
import re
import resource
import signal
import stat
import sys
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p121_signals import zero_authority_counters
from app.services.p133_deadman_outbox import DeadmanConfig, DeadmanOutbox, load_deadman_config
from app.services.p139_local_triage_service import (
    P139ServiceError,
    inspect_local_triage_service,
    read_local_triage_service_bundle,
    zero_forbidden_authority,
)

CONFIG_SCHEMA_VERSION = "p140.p139_deadman_adapter_config.v1"
STATE_SCHEMA_VERSION = "p140.p139_deadman_state.v1"
RESULT_SCHEMA_VERSION = "p140.p139_deadman_adapter_result.v1"
RUN_SCHEMA_VERSION = "p140.p139_deadman_adapter_run.v1"
MAX_BOOTSTRAP_CONFIG_BYTES = 16_777_216
_LOCAL_LABEL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:@+-]{0,127}\Z")
_HASH_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_CONFIG_FIELDS = frozenset(
    {
        "schema_version",
        "adapter_id",
        "allowed_artifact_roots",
        "p139_bundle_path",
        "p139_base_path",
        "p133_config_path",
        "adapter_lease_path",
        "max_config_bytes",
        "max_runtime_seconds",
        "max_peak_memory_bytes",
        "config_hash",
    }
)
_FORBIDDEN_TOKENS = (
    "api_key",
    "apikey",
    "auth",
    "bearer",
    "command",
    "credential",
    "endpoint",
    "environment",
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
_INVALID_ERROR_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("receipt", "receipt_invalid"),
    ("termination", "termination_invalid"),
    ("ledger", "ledger_invalid"),
    ("heartbeat", "heartbeat_invalid"),
    ("readiness", "readiness_invalid"),
    ("history", "history_invalid"),
    ("fork", "history_invalid"),
    ("chain", "history_invalid"),
    ("lease", "lease_probe_invalid"),
    ("path", "target_path_invalid"),
    ("json", "target_encoding_invalid"),
)


class P140AdapterError(ValueError):
    """Raised when P140 cannot safely evaluate or persist local state."""


@dataclass(frozen=True)
class P140AdapterConfig:
    schema_version: str
    adapter_id: str
    allowed_artifact_roots: tuple[Path, ...]
    p139_bundle_path: Path
    p139_base_path: Path
    p133_config_path: Path
    adapter_lease_path: Path
    max_config_bytes: int
    max_runtime_seconds: int
    max_peak_memory_bytes: int
    config_hash: str


class P140StopController:
    """Signal-safe request flag checked only between P133 checks."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._reason: str | None = None

    def handle_signal(self, signum: int, _frame: object) -> None:
        self._reason = signal.Signals(signum).name.lower()
        self._event.set()

    def reason(self) -> str | None:
        return self._reason if self._event.is_set() else None

    def wait(self, seconds: float) -> bool:
        return self._event.wait(seconds)


class _AdapterLease:
    def __init__(self, config: P140AdapterConfig) -> None:
        self.config = config
        self.handle: Any = None

    def __enter__(self) -> None:
        path = self.config.adapter_lease_path
        _require_path_in_roots(path, self.config.allowed_artifact_roots)
        _reject_symlink_components(path.parent)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        try:
            fd = os.open(path, flags, 0o600)
        except OSError as exc:
            raise P140AdapterError("adapter_lease_invalid") from exc
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            os.close(fd)
            raise P140AdapterError("adapter_lease_not_regular")
        self.handle = os.fdopen(fd, "r+", encoding="utf-8")
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self.handle.close()
            self.handle = None
            raise P140AdapterError("adapter_lease_unavailable") from exc
        self.handle.seek(0)
        self.handle.truncate()
        self.handle.write(json.dumps({"adapter_id": self.config.adapter_id, "pid": os.getpid()}, sort_keys=True) + "\n")
        self.handle.flush()
        os.fsync(self.handle.fileno())

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self.handle is not None:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()


def build_p140_config(value: Mapping[str, Any]) -> dict[str, Any]:
    """Build a self-hashed exact P140 config without touching the filesystem."""

    raw = dict(value)
    raw.pop("config_hash", None)
    if set(raw) != _CONFIG_FIELDS - {"config_hash"}:
        raise P140AdapterError("invalid_config_fields")
    _validate_json_value(raw)
    raw["config_hash"] = stable_hash(raw)
    return raw


def write_p140_config(path: Path | str, value: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(_canonical_bytes(build_p140_config(value)))


def load_p140_config(path: Path | str) -> P140AdapterConfig:
    """Load and rebind an exact explicit-path local adapter configuration."""

    config_input = Path(path).expanduser()
    if not config_input.is_absolute():
        config_input = Path.cwd() / config_input
    _reject_symlink_components(config_input)
    raw_bytes = _read_regular(config_input, MAX_BOOTSTRAP_CONFIG_BYTES, "config")
    raw = _decode_canonical_json(raw_bytes, "config")
    if set(raw) != _CONFIG_FIELDS or raw.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise P140AdapterError("invalid_config_fields")
    claimed_hash = _hash(raw.get("config_hash"), "config_hash")
    unsigned = {key: item for key, item in raw.items() if key != "config_hash"}
    if claimed_hash != stable_hash(unsigned):
        raise P140AdapterError("config_hash_invalid")
    _reject_forbidden_text(raw)
    max_config_bytes = _positive_int(raw.get("max_config_bytes"), "max_config_bytes")
    if len(raw_bytes) > max_config_bytes or max_config_bytes > MAX_BOOTSTRAP_CONFIG_BYTES:
        raise P140AdapterError("config_size_invalid")
    base = config_input.resolve().parent
    roots_value = raw.get("allowed_artifact_roots")
    if not _is_sequence(roots_value) or not roots_value:
        raise P140AdapterError("allowed_artifact_roots_required")
    roots = tuple(_resolve_path(base, item) for item in roots_value)
    for root in roots:
        _reject_symlink_components(root)
        if not root.is_dir():
            raise P140AdapterError("allowed_root_not_directory")
    p139_bundle_path = _resolve_path(base, raw.get("p139_bundle_path"))
    p139_base_path = _resolve_path(base, raw.get("p139_base_path"))
    p133_config_path = _resolve_path(base, raw.get("p133_config_path"))
    adapter_lease_path = _resolve_path(base, raw.get("adapter_lease_path"))
    for candidate in (p139_bundle_path, p139_base_path, p133_config_path, adapter_lease_path):
        _require_path_in_roots(candidate, roots)
        _reject_symlink_components(candidate)
    if not p139_base_path.is_dir():
        raise P140AdapterError("p139_base_not_directory")
    _read_regular(p139_bundle_path, max_config_bytes, "p139_bundle")
    _read_regular(p133_config_path, max_config_bytes, "p133_config")
    _require_nonoverlap((p139_bundle_path, p139_base_path, p133_config_path, adapter_lease_path))
    config = P140AdapterConfig(
        schema_version=CONFIG_SCHEMA_VERSION,
        adapter_id=_label(raw.get("adapter_id"), "adapter_id"),
        allowed_artifact_roots=roots,
        p139_bundle_path=p139_bundle_path,
        p139_base_path=p139_base_path,
        p133_config_path=p133_config_path,
        adapter_lease_path=adapter_lease_path,
        max_config_bytes=max_config_bytes,
        max_runtime_seconds=_positive_int(raw.get("max_runtime_seconds"), "max_runtime_seconds"),
        max_peak_memory_bytes=_positive_int(raw.get("max_peak_memory_bytes"), "max_peak_memory_bytes"),
        config_hash=claimed_hash,
    )
    _load_bound_dependencies(config)
    return config


class P139DeadmanWatchdog:
    """Public-API-only P139 evaluator consumed by the existing P133 writer."""

    def __init__(self, config: P140AdapterConfig) -> None:
        self.config = config
        self._started_peak_rss_bytes = _peak_rss_bytes()

    def __call__(
        self,
        path: Path | str,
        *,
        now: datetime,
        heartbeat_timeout_seconds: int,
    ) -> Mapping[str, Any]:
        p133, bundle = _load_bound_dependencies(self.config)
        if Path(path).resolve() != self.config.p139_bundle_path or heartbeat_timeout_seconds != p133.heartbeat_timeout_seconds:
            return _invalid_watchdog_result(self.config, p133, bundle, "watchdog_contract_invalid")
        observed = _utc_timestamp(now)
        try:
            status = inspect_local_triage_service(
                base_path=self.config.p139_base_path,
                bundle=bundle,
                now=observed,
            )
        except (OSError, P139ServiceError) as exc:
            category = _classify_target_error(str(exc))
            return _invalid_watchdog_result(self.config, p133, bundle, category)
        _require_memory_budget(self.config, self._started_peak_rss_bytes)
        projection = _status_projection(status)
        state_hash = stable_hash(projection)
        health = status.get("health")
        if health == "ready":
            reason, healthy = "heartbeat_current", True
        elif health == "stale":
            reason, healthy = "heartbeat_stale", False
        elif health == "stopped_clean":
            reason, healthy = "runtime_stopped", False
        elif health == "stopped_unclean":
            missing = (
                status.get("reason") == "no_terminal_receipt"
                and status.get("readiness_hash") is None
                and status.get("heartbeat_hash") is None
                and status.get("exit_receipt_hash") is None
            )
            reason, healthy = ("state_missing", False) if missing else ("runtime_stopped", False)
        else:
            return _invalid_watchdog_result(self.config, p133, bundle, "unknown_status")
        return {
            "reason": reason,
            "healthy": healthy,
            "state_hash": None if reason == "state_missing" else state_hash,
            "heartbeat_age_seconds": None,
        }


def check_p139_deadman_once(
    config: P140AdapterConfig,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Evaluate once while holding the adapter lease outside the P133 lease."""

    started = _resource_start()
    with _AdapterLease(config):
        p133, bundle = _load_bound_dependencies(config)
        runtime = DeadmanOutbox(
            p133,
            now=(None if now is None else lambda: _require_utc(now)),
            watchdog_evaluator=P139DeadmanWatchdog(config),
        )
        result = runtime.check_once()
    return _bound_result(config, p133, bundle, result, resources=_resource_end(started, config))


def run_p139_deadman_adapter(
    config: P140AdapterConfig,
    *,
    max_cycles: int | None = None,
    forever: bool = False,
    stop_controller: P140StopController | None = None,
    sleep: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    """Run the P133 transition loop under one whole-adapter lease."""

    if forever == (max_cycles is not None):
        raise P140AdapterError("run_requires_forever_or_max_cycles")
    if max_cycles is not None and (type(max_cycles) is not int or max_cycles <= 0):
        raise P140AdapterError("max_cycles_must_be_positive")
    controller = stop_controller or P140StopController()
    started = _resource_start()
    with _AdapterLease(config):
        p133, bundle = _load_bound_dependencies(config)
        runtime = DeadmanOutbox(
            p133,
            sleep=sleep,
            watchdog_evaluator=P139DeadmanWatchdog(config),
        )
        result = runtime.run(
            max_cycles=max_cycles,
            forever=forever,
            stop_reason=controller.reason,
            wait_for_stop=controller.wait,
        )
    resources = _resource_end(started, config)
    if resources["wall_time_ms"] > config.max_runtime_seconds * 1000 and not forever:
        raise P140AdapterError("runtime_budget_exceeded")
    value = _bound_result(config, p133, bundle, result, resources=resources)
    value["schema_version"] = RUN_SCHEMA_VERSION
    return value


def _bound_result(
    config: P140AdapterConfig,
    p133: DeadmanConfig,
    bundle: Mapping[str, Any],
    result: Mapping[str, Any],
    *,
    resources: Mapping[str, int],
) -> dict[str, Any]:
    if result.get("authority_counters") != zero_authority_counters():
        raise P140AdapterError("p133_authority_nonzero")
    value = dict(result)
    value.update(
        {
            "schema_version": RESULT_SCHEMA_VERSION,
            "adapter_id": config.adapter_id,
            "adapter_config_hash": config.config_hash,
            "p133_config_hash": p133.config_hash,
            "p139_bundle_hash": bundle["bundle_hash"],
            "p139_forbidden_authority": zero_forbidden_authority(),
            "resource_usage": dict(resources),
        }
    )
    return value


def _load_bound_dependencies(config: P140AdapterConfig) -> tuple[DeadmanConfig, dict[str, Any]]:
    _read_regular(config.p139_bundle_path, config.max_config_bytes, "p139_bundle")
    _read_regular(config.p133_config_path, config.max_config_bytes, "p133_config")
    try:
        bundle = read_local_triage_service_bundle(config.p139_bundle_path)
        p133 = load_deadman_config(config.p133_config_path)
    except (OSError, P139ServiceError, ValueError) as exc:
        raise P140AdapterError("bound_dependency_invalid") from exc
    expected_runtime_ref = f"p139:{bundle['service_id']}"
    if p133.state_path.resolve() != config.p139_bundle_path or p133.runtime_ref != expected_runtime_ref:
        raise P140AdapterError("p133_p139_binding_invalid")
    if p133.config_hash == config.config_hash or bundle["bundle_hash"] == config.config_hash:
        raise P140AdapterError("config_domain_hash_collision")
    for root in p133.allowed_artifact_roots:
        _require_path_in_roots(root, config.allowed_artifact_roots)
    for write_path in (p133.outbox_dir, p133.cursor_path, p133.ack_dir, p133.lease_path):
        _require_path_in_roots(write_path, config.allowed_artifact_roots)
    _require_nonoverlap(
        (
            config.p139_base_path,
            config.p133_config_path,
            config.adapter_lease_path,
            p133.outbox_dir,
            p133.cursor_path,
            p133.ack_dir,
            p133.lease_path,
        )
    )
    return p133, bundle


def _resource_start() -> tuple[float, int]:
    return time.monotonic(), _peak_rss_bytes()


def _resource_end(started: tuple[float, int], config: P140AdapterConfig) -> dict[str, int]:
    wall_started, peak_started = started
    usage = {
        "wall_time_ms": max(0, int((time.monotonic() - wall_started) * 1000)),
        "wall_limit_ms": config.max_runtime_seconds * 1000,
        "peak_memory_bytes": max(0, _peak_rss_bytes() - peak_started),
        "peak_memory_limit_bytes": config.max_peak_memory_bytes,
    }
    if usage["peak_memory_bytes"] > usage["peak_memory_limit_bytes"]:
        raise P140AdapterError("memory_budget_exceeded")
    return usage


def _require_memory_budget(config: P140AdapterConfig, started_peak_rss_bytes: int) -> None:
    if max(0, _peak_rss_bytes() - started_peak_rss_bytes) > config.max_peak_memory_bytes:
        raise P140AdapterError("memory_budget_exceeded")


def _peak_rss_bytes() -> int:
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return value if sys.platform == "darwin" else value * 1024


def _status_projection(status: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "schema_version",
        "service_id",
        "bundle_hash",
        "health",
        "reason",
        "service_lease_held",
        "last_valid_ledger_hash",
        "readiness_hash",
        "heartbeat_hash",
        "exit_receipt_hash",
        "observed_at",
        "forbidden_authority",
        "status_hash",
    }
    if set(status) != expected or status.get("forbidden_authority") != zero_forbidden_authority():
        raise P140AdapterError("p139_status_contract_invalid")
    for key in ("bundle_hash", "last_valid_ledger_hash"):
        _hash(status.get(key), key)
    for key in ("readiness_hash", "heartbeat_hash", "exit_receipt_hash"):
        value = status.get(key)
        if value is not None:
            _hash(value, key)
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "service_id": status["service_id"],
        "bundle_hash": status["bundle_hash"],
        "health": status["health"],
        "reason": status["reason"],
        "service_lease_held": status["service_lease_held"],
        "last_valid_ledger_hash": status["last_valid_ledger_hash"],
        "readiness_hash": status["readiness_hash"],
        "heartbeat_hash": status["heartbeat_hash"],
        "exit_receipt_hash": status["exit_receipt_hash"],
        "forbidden_authority": zero_forbidden_authority(),
    }


def _invalid_watchdog_result(
    config: P140AdapterConfig,
    p133: DeadmanConfig,
    bundle: Mapping[str, Any],
    category: str,
) -> dict[str, Any]:
    state_hash = stable_hash(
        {
            "schema_version": "p140.invalid_observation.v1",
            "category": category,
            "adapter_config_hash": config.config_hash,
            "p133_config_hash": p133.config_hash,
            "p139_bundle_hash": bundle["bundle_hash"],
        }
    )
    return {"reason": "state_invalid", "healthy": False, "state_hash": state_hash, "heartbeat_age_seconds": None}


def _classify_target_error(message: str) -> str:
    lowered = message.lower()
    for token, category in _INVALID_ERROR_CATEGORIES:
        if token in lowered:
            return category
    return "target_state_invalid"


def _decode_canonical_json(payload: bytes, label: str) -> dict[str, Any]:
    try:
        text = payload.decode("utf-8")
        value = json.loads(text, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise P140AdapterError(f"{label}_json_invalid") from exc
    if not isinstance(value, dict):
        raise P140AdapterError(f"{label}_object_required")
    _validate_json_value(value)
    if payload != _canonical_bytes(value):
        raise P140AdapterError(f"{label}_canonical_json_required")
    return value


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def _validate_json_value(value: Any) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise P140AdapterError("nonfinite_json_value")
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item)
        return
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise P140AdapterError("json_key_invalid")
        for item in value.values():
            _validate_json_value(item)
        return
    raise P140AdapterError("json_value_invalid")


def _read_regular(path: Path, maximum: int, label: str) -> bytes:
    _reject_symlink_components(path)
    try:
        fd = _open_readonly_nofollow(path)
    except OSError as exc:
        raise P140AdapterError(f"{label}_missing") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > maximum:
            raise P140AdapterError(f"{label}_not_safe_regular_file")
        with os.fdopen(fd, "rb") as handle:
            fd = -1
            payload = handle.read(maximum + 1)
    except OSError as exc:
        raise P140AdapterError(f"{label}_read_failed") from exc
    finally:
        if fd >= 0:
            os.close(fd)
    if len(payload) != info.st_size or len(payload) > maximum:
        raise P140AdapterError(f"{label}_changed_during_read")
    return payload


def _open_readonly_nofollow(path: Path) -> int:
    absolute = path if path.is_absolute() else (Path.cwd() / path)
    parts = absolute.parts
    parent_fd = os.open(absolute.anchor, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0))
    try:
        for part in parts[1:-1]:
            next_fd = os.open(
                part,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                dir_fd=parent_fd,
            )
            os.close(parent_fd)
            parent_fd = next_fd
        return os.open(
            parts[-1],
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent_fd,
        )
    finally:
        os.close(parent_fd)


def _resolve_path(base: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise P140AdapterError("path_invalid")
    candidate = Path(value).expanduser()
    lexical = candidate if candidate.is_absolute() else base / candidate
    _reject_symlink_components(lexical)
    return lexical.resolve(strict=False)


def _reject_symlink_components(path: Path) -> None:
    current = Path(path.anchor) if path.is_absolute() else Path.cwd()
    parts = path.parts[1:] if path.is_absolute() else path.parts
    for part in parts:
        current /= part
        if current.is_symlink():
            raise P140AdapterError("symlink_path_rejected")


def _require_path_in_roots(path: Path, roots: Sequence[Path]) -> None:
    if not any(_is_relative_to(path, root) for root in roots):
        raise P140AdapterError("path_outside_allowed_roots")


def _require_nonoverlap(paths: Sequence[Path]) -> None:
    for index, left in enumerate(paths):
        for right in paths[index + 1 :]:
            if left == right or _is_relative_to(left, right) or _is_relative_to(right, left):
                raise P140AdapterError("path_topology_overlap")


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _reject_forbidden_text(value: Any) -> None:
    texts: list[str] = []
    if isinstance(value, str):
        texts.append(value)
    elif isinstance(value, Mapping):
        for key, item in value.items():
            texts.append(str(key))
            _reject_forbidden_text(item)
    elif _is_sequence(value):
        for item in value:
            _reject_forbidden_text(item)
    for text in texts:
        lowered = text.lower()
        if "://" in lowered or "${" in text or any(token in lowered for token in _FORBIDDEN_TOKENS):
            raise P140AdapterError("forbidden_config_text")


def _positive_int(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0 or value > 1_099_511_627_776:
        raise P140AdapterError(f"{label}_invalid")
    return value


def _hash(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _HASH_RE.fullmatch(value):
        raise P140AdapterError(f"{label}_invalid")
    return value


def _label(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _LOCAL_LABEL_RE.fullmatch(value):
        raise P140AdapterError(f"{label}_invalid")
    return value


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise P140AdapterError("utc_datetime_required")
    return value.astimezone(UTC)


def _utc_timestamp(value: datetime) -> str:
    return _require_utc(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


__all__ = [
    "CONFIG_SCHEMA_VERSION",
    "P139DeadmanWatchdog",
    "P140AdapterConfig",
    "P140AdapterError",
    "P140StopController",
    "build_p140_config",
    "check_p139_deadman_once",
    "load_p140_config",
    "run_p139_deadman_adapter",
    "write_p140_config",
]
