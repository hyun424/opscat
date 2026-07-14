"""Credential-free local process host for the qualified P138 supervisor."""

from __future__ import annotations

import fcntl
import json
import math
import os
import re
import resource
import stat
import time
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p138_observation_triage_supervisor import (
    EVALUATOR_ACTIVITY_KEYS as P138_EVALUATOR_ACTIVITY_KEYS,
)
from app.services.p138_observation_triage_supervisor import (
    FORBIDDEN_AUTHORITY_KEYS,
    HEARTBEAT_SCHEMA_VERSION,
    READINESS_SCHEMA_VERSION,
    TERMINATION_SCHEMA_VERSION,
    P138StopController,
    P138SupervisorError,
    run_p138_supervisor_loop,
    run_p138_supervisor_loop_for_evaluation,
    validate_observation_triage_supervisor_config,
    validate_supervisor_ledger,
)
from app.services.p138_observation_triage_supervisor import (
    RUNTIME_ACTIVITY_KEYS as P138_RUNTIME_ACTIVITY_KEYS,
)

SERVICE_BUNDLE_SCHEMA_VERSION = "p139.local_triage_service_bundle.v1"
EXIT_RECEIPT_SCHEMA_VERSION = "p139.service_exit_receipt.v1"
EXIT_INTENT_SCHEMA_VERSION = "p139.service_exit_intent.v1"
RESTART_CONTROL_SCHEMA_VERSION = "p139.restart_control_record.v1"
SERVICE_STATUS_SCHEMA_VERSION = "p139.local_triage_service_status.v1"
SERVICE_RESULT_SCHEMA_VERSION = "p139.local_triage_service_result.v1"
_BYTES_TAG = "__opscat_p139_bytes_hex__"

P138_QUALIFIED_STATUS = "p138_local_observation_to_triage_supervisor_qualified"
# Updated by the P139 release freeze whenever qualified P138 source changes.
EXPECTED_P138_EVIDENCE_HASH = "sha256:d49eb7ad7cbf28d10d3afcecfb2cb7841bb36e40b24e717e78d478ad49eca43d"
EXPECTED_P138_REVIEW_HASH = "sha256:ffb8f4c6d7d99ee5ad56633e552d260a4ecea8074c87e347f1d971e111153f33"

MAX_BOOTSTRAP_BUNDLE_BYTES = 16_777_216
_HASH_NONE = "sha256:" + ("0" * 64)
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_LABEL_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_FORBIDDEN_TEXT_RE = re.compile(
    r"(?:https?://|bearer\s+[A-Za-z0-9._~+/=-]+|(?:api[_-]?key|password|secret|token)\s*[:=]\s*\S+|\$\{?[A-Z][A-Z0-9_]{2,}\}?)",
    re.IGNORECASE,
)

SERVICE_ACTIVITY_KEYS = (
    "service_lease_acquire_count",
    "bundle_read_count",
    "restart_reconciliation_count",
    "restart_intent_write_count",
    "restart_history_write_count",
    "restart_control_unlink_count",
    "exit_intent_write_count",
    "exit_history_write_count",
    "exit_receipt_write_count",
    "status_snapshot_write_count",
    "fsync_count",
)
EVALUATOR_ACTIVITY_KEYS = (
    "runner_invocation_count",
    "artifact_write_count",
    "subprocess_launch_count",
    "signal_injection_count",
    "crash_injection_count",
)
RESOURCE_USAGE_KEYS = (
    "wall_time_ms",
    "cpu_time_ms",
    "child_cpu_time_ms",
    "peak_memory_bytes",
    "wall_limit_ms",
    "cpu_limit_ms",
    "peak_memory_limit_bytes",
)

_BUNDLE_INPUT_FIELDS = frozenset(
    {
        "service_id",
        "config_version",
        "created_at",
        "base_dir_ref_hash",
        "p138_config",
        "p136_runtime",
        "publisher_inputs",
        "validated_p138_release_status",
        "p138_release_evidence_hash",
        "p138_final_review_hash",
        "service_lease_path",
        "exit_receipt_path",
        "exit_intent_path",
        "exit_history_dir",
        "restart_control_path",
        "restart_history_dir",
        "status_snapshot_path",
        "limits",
        "forbidden_authority",
    }
)
_BUNDLE_FIELDS = _BUNDLE_INPUT_FIELDS | {"schema_version", "bundle_hash"}
_LIMIT_FIELDS = frozenset(
    {
        "max_bundle_bytes",
        "max_state_bytes",
        "max_exit_history_records",
        "startup_readiness_stale_after_ms",
        "wall_limit_ms",
        "cpu_limit_ms",
        "peak_memory_limit_bytes",
    }
)


class P139ServiceError(ValueError):
    """Raised when the local service host cannot prove a safe transition."""


class P139InjectedCrash(RuntimeError):
    """Evaluator-only deterministic split-commit crash."""


class P139StopController(P138StopController):
    """Named alias for the P139 CLI signal surface."""


def zero_forbidden_authority() -> dict[str, int]:
    return {key: 0 for key in FORBIDDEN_AUTHORITY_KEYS}


def zero_service_activity(**overrides: int) -> dict[str, int]:
    value = {key: 0 for key in SERVICE_ACTIVITY_KEYS}
    value.update(overrides)
    return value


def zero_evaluator_activity(**overrides: int) -> dict[str, int]:
    value = {key: 0 for key in EVALUATOR_ACTIVITY_KEYS}
    value.update(overrides)
    return value


def serialize_p136_runtime(runtime: Mapping[str, Any]) -> dict[str, Any]:
    """Remove process-local values and encode byte authorities canonically."""
    value = deepcopy(dict(_mapping(runtime, "p136_runtime")))
    value.pop("probe", None)
    base_path = value.pop("base_path", None)
    export_root = value.pop("export_root", None)
    if base_path is not None and export_root is not None:
        try:
            relative = Path(export_root).relative_to(Path(base_path))
        except ValueError:
            pass
        else:
            value["export_root_path"] = relative.as_posix()
    encoded = _encode_runtime_value(value)
    if not isinstance(encoded, dict):
        raise P139ServiceError("serialized_runtime_not_mapping")
    return encoded


def build_local_triage_service_bundle(data: Mapping[str, Any]) -> dict[str, Any]:
    raw = _mapping(data, "service_bundle")
    if set(raw) != _BUNDLE_INPUT_FIELDS:
        raise P139ServiceError("invalid_bundle_input_fields")
    _reject_callable_values(raw, "service_bundle")
    _reject_forbidden_text(raw)
    p138_config = deepcopy(dict(_mapping(raw.get("p138_config"), "p138_config")))
    try:
        validate_observation_triage_supervisor_config(p138_config)
    except P138SupervisorError as exc:
        raise P139ServiceError(f"invalid_p138_config:{exc}") from exc
    p136_runtime = deepcopy(dict(_mapping(raw.get("p136_runtime"), "p136_runtime")))
    if "probe" in p136_runtime or "base_path" in p136_runtime:
        raise P139ServiceError("serialized_p136_runtime_contains_process_value")
    _validate_serialized_runtime(p136_runtime)
    if dict(_mapping(p136_runtime.get("config"), "p136_runtime_config")) != dict(p138_config["p136_config"]):
        raise P139ServiceError("p136_runtime_config_mismatch")
    publisher_inputs = deepcopy(dict(_mapping(raw.get("publisher_inputs"), "publisher_inputs")))
    expected_publisher_fields = {
        "canonical_entry_map",
        "p136_independent_review",
        "p136_release_evidence",
        "p137_release_evidence",
        "p137_final_implementation_review",
        "created_at",
    }
    if set(publisher_inputs) != expected_publisher_fields:
        raise P139ServiceError("invalid_publisher_input_fields")
    status = _text(raw.get("validated_p138_release_status"), "p138_release_status")
    if status != P138_QUALIFIED_STATUS:
        raise P139ServiceError("p138_release_status_unqualified")
    evidence_hash = _hash(raw.get("p138_release_evidence_hash"), "p138_evidence_hash")
    review_hash = _hash(raw.get("p138_final_review_hash"), "p138_review_hash")
    if evidence_hash != EXPECTED_P138_EVIDENCE_HASH:
        raise P139ServiceError("p138_release_evidence_drift")
    if review_hash != EXPECTED_P138_REVIEW_HASH:
        raise P139ServiceError("p138_final_review_drift")
    paths = {
        key: _relative_path(raw.get(key), key)
        for key in (
            "service_lease_path",
            "exit_receipt_path",
            "exit_intent_path",
            "exit_history_dir",
            "restart_control_path",
            "restart_history_dir",
            "status_snapshot_path",
        )
    }
    _validate_path_topology(paths, p138_config)
    limits = _exact_positive_int_map(raw.get("limits"), _LIMIT_FIELDS)
    if limits["max_bundle_bytes"] > MAX_BOOTSTRAP_BUNDLE_BYTES:
        raise P139ServiceError("bundle_limit_exceeds_bootstrap_limit")
    if limits["max_exit_history_records"] < 2:
        raise P139ServiceError("exit_history_limit_too_small")
    bundle: dict[str, Any] = {
        "schema_version": SERVICE_BUNDLE_SCHEMA_VERSION,
        "service_id": _label(raw.get("service_id"), "service_id"),
        "config_version": _positive_int(raw.get("config_version"), "config_version"),
        "created_at": _timestamp(raw.get("created_at"), "created_at"),
        "base_dir_ref_hash": _hash(raw.get("base_dir_ref_hash"), "base_dir_ref_hash"),
        "p138_config": p138_config,
        "p136_runtime": p136_runtime,
        "publisher_inputs": publisher_inputs,
        "validated_p138_release_status": status,
        "p138_release_evidence_hash": evidence_hash,
        "p138_final_review_hash": review_hash,
        **paths,
        "limits": limits,
        "forbidden_authority": _exact_counter_map(
            raw.get("forbidden_authority"),
            FORBIDDEN_AUTHORITY_KEYS,
            "invalid_forbidden_authority",
            require_zero=True,
        ),
    }
    bundle["bundle_hash"] = stable_hash(bundle)
    return bundle


def validate_local_triage_service_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]:
    value = _mapping(bundle, "service_bundle")
    if set(value) != _BUNDLE_FIELDS or value.get("schema_version") != SERVICE_BUNDLE_SCHEMA_VERSION:
        raise P139ServiceError("invalid_bundle_fields")
    if value.get("bundle_hash") != stable_hash({key: item for key, item in value.items() if key != "bundle_hash"}):
        raise P139ServiceError("bundle_hash_invalid")
    rebuilt = build_local_triage_service_bundle({key: deepcopy(value[key]) for key in _BUNDLE_INPUT_FIELDS})
    if rebuilt != dict(value):
        raise P139ServiceError("bundle_semantics_invalid")
    return deepcopy(dict(value))


def write_local_triage_service_bundle(path: Path | str, bundle: Mapping[str, Any]) -> None:
    value = validate_local_triage_service_bundle(bundle)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = _canonical_bytes(value)
    if len(payload) > int(value["limits"]["max_bundle_bytes"]):
        raise P139ServiceError("bundle_byte_budget_exceeded")
    _atomic_write_path(target, payload)


def read_local_triage_service_bundle(path: Path | str) -> dict[str, Any]:
    raw = _read_regular_path(Path(path), maximum=MAX_BOOTSTRAP_BUNDLE_BYTES)
    value = _decode_canonical_json(raw, "bundle")
    bundle = validate_local_triage_service_bundle(value)
    if len(raw) > int(bundle["limits"]["max_bundle_bytes"]):
        raise P139ServiceError("bundle_byte_budget_exceeded")
    return bundle


class _ActivityProbe:
    def __init__(self) -> None:
        self.events: list[str] = []

    def record(self, event: str) -> None:
        self.events.append(event)


class _AdvisoryLease:
    def __init__(self, root: Path, relative_path: str, *, create: bool = True) -> None:
        self._root = root
        self._relative_path = relative_path
        self._create = create
        self._handle: Any | None = None

    def acquire(self) -> bool:
        path = _secure_runtime_path(
            self._root,
            self._relative_path,
            create_parent=self._create,
        )
        if not self._create and not path.exists():
            return True
        mode = "a+" if self._create else "r+"
        try:
            handle = path.open(mode, encoding="utf-8")
        except FileNotFoundError:
            return True
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            handle.close()
            raise P139ServiceError("lease_path_not_secure_regular_file")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            return False
        self._handle = handle
        return True

    def release(self) -> None:
        if self._handle is None:
            return
        fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        self._handle.close()
        self._handle = None


def _hydrate_p136_runtime(
    bundle: Mapping[str, Any],
    *,
    base_path: Path,
) -> dict[str, Any]:
    decoded = _decode_runtime_value(bundle.get("p136_runtime"))
    runtime = deepcopy(dict(_mapping(decoded, "p136_runtime")))
    runtime["base_path"] = base_path
    runtime["probe"] = _ActivityProbe()
    export_relative = runtime.pop("export_root_path", None)
    if export_relative is not None:
        runtime["export_root"] = _secure_runtime_path(
            base_path,
            _relative_path(export_relative, "export_root_path"),
            create_parent=False,
        )
    checkpoint_path = str(bundle["p138_config"]["p136_config"]["checkpoint_path"])
    persisted = _read_json_optional(
        base_path,
        checkpoint_path,
        maximum=int(bundle["limits"]["max_state_bytes"]),
    )
    if persisted is not None:
        runtime["checkpoint"] = persisted
    return runtime


def run_local_triage_service(
    *,
    base_path: Path | str,
    bundle: Mapping[str, Any],
    stop_controller: P139StopController | None = None,
) -> dict[str, Any]:
    return _run_local_triage_service(
        base_path=Path(base_path),
        bundle=bundle,
        stop_controller=stop_controller,
        evaluator=False,
        now_values=None,
        monotonic=time.monotonic,
        sleep=time.sleep,
        crash_after=None,
    )


def run_local_triage_service_for_evaluation(
    *,
    base_path: Path | str,
    bundle: Mapping[str, Any],
    now_values: Sequence[str],
    stop_controller: P139StopController | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    crash_after: str | None = None,
) -> dict[str, Any]:
    return _run_local_triage_service(
        base_path=Path(base_path),
        bundle=bundle,
        stop_controller=stop_controller,
        evaluator=True,
        now_values=now_values,
        monotonic=monotonic,
        sleep=sleep,
        crash_after=crash_after,
    )


def _run_local_triage_service(
    *,
    base_path: Path,
    bundle: Mapping[str, Any],
    stop_controller: P139StopController | None,
    evaluator: bool,
    now_values: Sequence[str] | None,
    monotonic: Callable[[], float],
    sleep: Callable[[float], None],
    crash_after: str | None,
) -> dict[str, Any]:
    cfg = validate_local_triage_service_bundle(bundle)
    root = Path(base_path)
    if root.is_symlink() or not root.is_dir():
        raise P139ServiceError("base_path_not_secure_directory")
    if stable_hash({"path": root.name}) != cfg["base_dir_ref_hash"]:
        raise P139ServiceError("base_path_ref_mismatch")
    started = _resource_start()
    activity = zero_service_activity()
    evaluator_activity = zero_evaluator_activity()
    service_lease = _AdvisoryLease(root, str(cfg["service_lease_path"]))
    if not service_lease.acquire():
        raise P139ServiceError("service_lease_unavailable")
    activity["service_lease_acquire_count"] = 1
    try:
        _recover_exit_commit(root, cfg, activity=activity)
        prior = _read_exit_receipt(root, cfg)
        _recover_restart_control(root, cfg, activity=activity)
        start_classification = _classify_start(root, cfg, prior)
        _rollover_prior_controls(
            root,
            cfg,
            prior,
            activity=activity,
            crash_after=crash_after if evaluator else None,
        )
        runtime = _hydrate_p136_runtime(cfg, base_path=root)
        publisher_inputs = deepcopy(dict(cfg["publisher_inputs"]))
        try:
            if evaluator:
                if now_values is None:
                    raise P139ServiceError("evaluation_now_values_required")
                loop_result = run_p138_supervisor_loop_for_evaluation(
                    base_path=root,
                    config=cfg["p138_config"],
                    p136_runtime=runtime,
                    publisher_inputs=publisher_inputs,
                    now_values=now_values,
                    stop_controller=stop_controller,
                    monotonic=monotonic,
                    sleep=sleep,
                )
            else:
                loop_result = run_p138_supervisor_loop(
                    base_path=root,
                    config=cfg["p138_config"],
                    p136_runtime=runtime,
                    publisher_inputs=publisher_inputs,
                    stop_controller=stop_controller,
                )
        except P138SupervisorError as exc:
            raise P139ServiceError(f"p138_loop_failed:{exc}") from exc
        resource_usage = _resource_end(started, cfg)
        if _resource_exceeded(resource_usage):
            raise P139ServiceError("service_resource_budget_exceeded")
        receipt = _build_exit_receipt(
            root,
            cfg,
            prior=prior,
            start_classification=start_classification,
            loop_result=loop_result,
            resource_usage=resource_usage,
        )
        _commit_exit_receipt(
            root,
            cfg,
            receipt,
            activity=activity,
            crash_after=crash_after if evaluator else None,
        )
        status = inspect_local_triage_service(
            base_path=root,
            bundle=cfg,
            now=str(receipt["created_at"]),
            assume_service_lease_held=True,
        )
        _atomic_write_json(
            root,
            str(cfg["status_snapshot_path"]),
            status,
            maximum=int(cfg["limits"]["max_state_bytes"]),
        )
        activity["status_snapshot_write_count"] += 1
        activity["fsync_count"] += 2
        result: dict[str, Any] = {
            "schema_version": SERVICE_RESULT_SCHEMA_VERSION,
            "status": "stopped",
            "start_classification": start_classification,
            "stop_reason": loop_result["stop_reason"],
            "cycles_completed": loop_result["cycles_completed"],
            "exit_receipt": receipt,
            "service_status": status,
            "p138_loop_result": loop_result,
            "service_activity": activity,
            "evaluator_activity": evaluator_activity,
            "forbidden_authority": zero_forbidden_authority(),
            "resource_usage": resource_usage,
        }
        result["result_hash"] = stable_hash(result)
        return result
    finally:
        service_lease.release()


def inspect_local_triage_service(
    *,
    base_path: Path | str,
    bundle: Mapping[str, Any],
    now: str,
    assume_service_lease_held: bool = False,
) -> dict[str, Any]:
    cfg = validate_local_triage_service_bundle(bundle)
    root = Path(base_path)
    current = _timestamp(now, "now")
    current_dt = _parse_timestamp(current, "now")
    lease_held = assume_service_lease_held or _probe_lease_held(root, str(cfg["service_lease_path"]))
    ledger_hash = _current_ledger_hash(root, cfg)
    readiness = _read_json_optional(
        root,
        str(cfg["p138_config"]["readiness_path"]),
        maximum=int(cfg["limits"]["max_state_bytes"]),
    )
    heartbeat = _read_json_optional(
        root,
        str(cfg["p138_config"]["heartbeat_path"]),
        maximum=int(cfg["limits"]["max_state_bytes"]),
    )
    receipt = _read_exit_receipt(root, cfg)
    health = "stopped_unclean"
    reason = "no_terminal_receipt"
    readiness_hash: str | None = None
    heartbeat_hash: str | None = None
    if readiness is not None:
        _validate_readiness(readiness, cfg, ledger_hash)
        readiness_hash = str(readiness["readiness_hash"])
    if heartbeat is not None:
        _validate_heartbeat(heartbeat, cfg, ledger_hash)
        heartbeat_hash = str(heartbeat["heartbeat_hash"])
    stale = False
    for record in (readiness, heartbeat):
        if record is None:
            continue
        age_ms = int((current_dt - _parse_timestamp(record["written_at"], "control_written_at")).total_seconds() * 1000)
        if age_ms < 0:
            raise P139ServiceError("control_record_from_future")
        if age_ms > int(cfg["limits"]["startup_readiness_stale_after_ms"]):
            stale = True
    if stale:
        health, reason = "stale", "control_record_stale"
    elif lease_held and readiness is not None and readiness.get("status") == "ready" and heartbeat is not None and heartbeat.get("readiness_state") == "ready":
        health, reason = "ready", "active_lease_and_fresh_readiness"
    elif receipt is not None and readiness is not None and readiness.get("status") == "stopped":
        _validate_receipt_controls(receipt, readiness, heartbeat)
        termination = _required_json(
            root,
            f"{cfg['p138_config']['termination_dir']}/{str(receipt['p138_termination_hash']).removeprefix('sha256:')}.json",
            cfg,
        )
        _validate_termination(termination, cfg, ledger_hash)
        if termination.get("termination_hash") != receipt.get("p138_termination_hash"):
            raise P139ServiceError("exit_receipt_termination_mismatch")
        health, reason = "stopped_clean", str(receipt["stop_reason"])
    elif readiness is not None and readiness.get("status") == "ready" and not lease_held:
        health, reason = "stopped_unclean", "active_readiness_without_service_lease"
    status: dict[str, Any] = {
        "schema_version": SERVICE_STATUS_SCHEMA_VERSION,
        "service_id": cfg["service_id"],
        "bundle_hash": cfg["bundle_hash"],
        "health": health,
        "reason": reason,
        "service_lease_held": lease_held,
        "last_valid_ledger_hash": ledger_hash,
        "readiness_hash": readiness_hash,
        "heartbeat_hash": heartbeat_hash,
        "exit_receipt_hash": None if receipt is None else receipt["receipt_hash"],
        "observed_at": current,
        "forbidden_authority": zero_forbidden_authority(),
    }
    status["status_hash"] = stable_hash(status)
    return status


def validate_exit_receipt(
    receipt: Mapping[str, Any],
    *,
    bundle: Mapping[str, Any],
    previous: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    value = _validate_exit_receipt_shape(receipt, bundle=bundle)
    generation = int(value["generation"])
    previous_hash = value.get("previous_receipt_hash")
    if previous is None:
        if generation != 1 or previous_hash is not None:
            raise P139ServiceError("exit_receipt_genesis_invalid")
    else:
        prior = _validate_exit_receipt_shape(previous, bundle=bundle)
        if generation != int(prior["generation"]) + 1 or previous_hash != prior["receipt_hash"]:
            raise P139ServiceError("exit_receipt_chain_invalid")
    return deepcopy(dict(value))


def _validate_exit_receipt_shape(
    receipt: Mapping[str, Any],
    *,
    bundle: Mapping[str, Any],
) -> dict[str, Any]:
    value = _mapping(receipt, "exit_receipt")
    expected_fields = {
        "schema_version",
        "service_id",
        "bundle_hash",
        "generation",
        "previous_receipt_hash",
        "start_classification",
        "stop_reason",
        "cycles_completed",
        "last_valid_ledger_hash",
        "p138_readiness_hash",
        "p138_heartbeat_hash",
        "p138_termination_hash",
        "p138_runtime_activity",
        "p138_evaluator_activity",
        "forbidden_authority",
        "resource_usage",
        "created_at",
        "receipt_hash",
    }
    if set(value) != expected_fields or value.get("schema_version") != EXIT_RECEIPT_SCHEMA_VERSION:
        raise P139ServiceError("invalid_exit_receipt_fields")
    if value.get("service_id") != bundle["service_id"] or value.get("bundle_hash") != bundle["bundle_hash"]:
        raise P139ServiceError("exit_receipt_bundle_mismatch")
    _positive_int(value.get("generation"), "generation")
    previous_hash = value.get("previous_receipt_hash")
    if previous_hash is not None:
        _hash(previous_hash, "previous_receipt_hash")
    if value.get("start_classification") not in {"clean_start", "clean_restart", "unclean_restart"}:
        raise P139ServiceError("invalid_start_classification")
    _text(value.get("stop_reason"), "stop_reason")
    _nonnegative_int(value.get("cycles_completed"), "cycles_completed")
    _hash(value.get("last_valid_ledger_hash"), "last_valid_ledger_hash")
    for key in ("p138_readiness_hash", "p138_heartbeat_hash", "p138_termination_hash"):
        _hash(value.get(key), key)
    _exact_counter_map(value.get("p138_runtime_activity"), P138_RUNTIME_ACTIVITY_KEYS, "invalid_p138_runtime_activity")
    _exact_counter_map(value.get("p138_evaluator_activity"), P138_EVALUATOR_ACTIVITY_KEYS, "invalid_p138_evaluator_activity")
    _exact_counter_map(value.get("forbidden_authority"), FORBIDDEN_AUTHORITY_KEYS, "invalid_exit_authority", require_zero=True)
    _resource_usage(value.get("resource_usage"), bundle)
    _timestamp(value.get("created_at"), "exit_created_at")
    if value.get("receipt_hash") != stable_hash({key: item for key, item in value.items() if key != "receipt_hash"}):
        raise P139ServiceError("exit_receipt_hash_invalid")
    return deepcopy(dict(value))


def _build_exit_receipt(
    root: Path,
    bundle: Mapping[str, Any],
    *,
    prior: Mapping[str, Any] | None,
    start_classification: str,
    loop_result: Mapping[str, Any],
    resource_usage: Mapping[str, int],
) -> dict[str, Any]:
    ledger_hash = _current_ledger_hash(root, bundle)
    readiness = _required_json(root, str(bundle["p138_config"]["readiness_path"]), bundle)
    heartbeat = _required_json(root, str(bundle["p138_config"]["heartbeat_path"]), bundle)
    _validate_readiness(readiness, bundle, ledger_hash)
    _validate_heartbeat(heartbeat, bundle, ledger_hash)
    termination = _mapping(loop_result.get("termination"), "p138_termination")
    _validate_termination(termination, bundle, ledger_hash)
    created_at = str(termination["written_at"])
    value: dict[str, Any] = {
        "schema_version": EXIT_RECEIPT_SCHEMA_VERSION,
        "service_id": bundle["service_id"],
        "bundle_hash": bundle["bundle_hash"],
        "generation": 1 if prior is None else int(prior["generation"]) + 1,
        "previous_receipt_hash": None if prior is None else prior["receipt_hash"],
        "start_classification": start_classification,
        "stop_reason": loop_result["stop_reason"],
        "cycles_completed": loop_result["cycles_completed"],
        "last_valid_ledger_hash": ledger_hash,
        "p138_readiness_hash": readiness["readiness_hash"],
        "p138_heartbeat_hash": heartbeat["heartbeat_hash"],
        "p138_termination_hash": termination["termination_hash"],
        "p138_runtime_activity": deepcopy(loop_result["runtime_activity"]),
        "p138_evaluator_activity": deepcopy(loop_result["evaluator_activity"]),
        "forbidden_authority": zero_forbidden_authority(),
        "resource_usage": dict(resource_usage),
        "created_at": created_at,
    }
    value["receipt_hash"] = stable_hash(value)
    return validate_exit_receipt(value, bundle=bundle, previous=prior)


def _commit_exit_receipt(
    root: Path,
    bundle: Mapping[str, Any],
    receipt: Mapping[str, Any],
    *,
    activity: dict[str, int],
    crash_after: str | None,
) -> None:
    intent = {
        "schema_version": EXIT_INTENT_SCHEMA_VERSION,
        "status": "pending",
        "bundle_hash": bundle["bundle_hash"],
        "receipt": deepcopy(dict(receipt)),
    }
    intent["intent_hash"] = stable_hash(intent)
    _atomic_write_json(root, str(bundle["exit_intent_path"]), intent, maximum=int(bundle["limits"]["max_state_bytes"]))
    activity["exit_intent_write_count"] += 1
    activity["fsync_count"] += 2
    _crash(crash_after, "exit_intent")
    history_path = f"{bundle['exit_history_dir']}/{str(receipt['receipt_hash']).removeprefix('sha256:')}.json"
    _write_immutable_json(root, history_path, receipt, maximum=int(bundle["limits"]["max_state_bytes"]))
    activity["exit_history_write_count"] += 1
    activity["fsync_count"] += 2
    _crash(crash_after, "exit_history")
    _atomic_write_json(root, str(bundle["exit_receipt_path"]), receipt, maximum=int(bundle["limits"]["max_state_bytes"]))
    activity["exit_receipt_write_count"] += 1
    activity["fsync_count"] += 2
    _crash(crash_after, "exit_current")
    completed = dict(intent)
    completed["status"] = "completed"
    completed["intent_hash"] = stable_hash({key: item for key, item in completed.items() if key != "intent_hash"})
    _atomic_write_json(root, str(bundle["exit_intent_path"]), completed, maximum=int(bundle["limits"]["max_state_bytes"]))
    activity["exit_intent_write_count"] += 1
    activity["fsync_count"] += 2
    _prune_exit_history(root, bundle, current=receipt)


def _recover_exit_commit(
    root: Path,
    bundle: Mapping[str, Any],
    *,
    activity: dict[str, int],
) -> None:
    intent = _read_json_optional(
        root,
        str(bundle["exit_intent_path"]),
        maximum=int(bundle["limits"]["max_state_bytes"]),
    )
    if intent is None:
        return
    expected = {"schema_version", "status", "bundle_hash", "receipt", "intent_hash"}
    if (
        set(intent) != expected
        or intent.get("schema_version") != EXIT_INTENT_SCHEMA_VERSION
        or intent.get("status") not in {"pending", "completed"}
        or intent.get("bundle_hash") != bundle["bundle_hash"]
        or intent.get("intent_hash") != stable_hash({key: value for key, value in intent.items() if key != "intent_hash"})
    ):
        raise P139ServiceError("invalid_exit_intent")
    receipt = _validate_recovered_receipt(
        root,
        bundle,
        _mapping(intent.get("receipt"), "exit_intent_receipt"),
    )
    history_path = f"{bundle['exit_history_dir']}/{str(receipt['receipt_hash']).removeprefix('sha256:')}.json"
    _write_immutable_json(
        root,
        history_path,
        receipt,
        maximum=int(bundle["limits"]["max_state_bytes"]),
    )
    current = _read_json_optional(
        root,
        str(bundle["exit_receipt_path"]),
        maximum=int(bundle["limits"]["max_state_bytes"]),
    )
    if current is None:
        _atomic_write_json(
            root,
            str(bundle["exit_receipt_path"]),
            receipt,
            maximum=int(bundle["limits"]["max_state_bytes"]),
        )
        activity["exit_receipt_write_count"] += 1
        activity["fsync_count"] += 2
    elif current != receipt:
        raise P139ServiceError("exit_recovery_current_conflict")
    if intent["status"] == "pending":
        completed = dict(intent)
        completed["status"] = "completed"
        completed["intent_hash"] = stable_hash({key: value for key, value in completed.items() if key != "intent_hash"})
        _atomic_write_json(
            root,
            str(bundle["exit_intent_path"]),
            completed,
            maximum=int(bundle["limits"]["max_state_bytes"]),
        )
        activity["exit_intent_write_count"] += 1
        activity["fsync_count"] += 2
    _prune_exit_history(root, bundle, current=receipt)


def _validate_recovered_receipt(
    root: Path,
    bundle: Mapping[str, Any],
    receipt: Mapping[str, Any],
) -> dict[str, Any]:
    generation = _positive_int(receipt.get("generation"), "generation")
    if generation == 1:
        return validate_exit_receipt(receipt, bundle=bundle)
    prior_hash = _hash(receipt.get("previous_receipt_hash"), "previous_receipt_hash")
    previous = _required_json(
        root,
        f"{bundle['exit_history_dir']}/{prior_hash.removeprefix('sha256:')}.json",
        bundle,
    )
    return validate_exit_receipt(receipt, bundle=bundle, previous=previous)


def _prune_exit_history(
    root: Path,
    bundle: Mapping[str, Any],
    *,
    current: Mapping[str, Any],
) -> None:
    directory = _secure_runtime_directory(
        root,
        str(bundle["exit_history_dir"]),
        create=True,
    )
    records: list[tuple[int, str, Path]] = []
    for path in directory.iterdir():
        if path.name.startswith(".") or path.suffix != ".json":
            continue
        record = _decode_canonical_json(
            _read_regular_path(path, maximum=int(bundle["limits"]["max_state_bytes"])),
            "exit_history",
        )
        validated = _validate_exit_receipt_shape(record, bundle=bundle)
        expected_name = f"{str(validated['receipt_hash']).removeprefix('sha256:')}.json"
        if path.name != expected_name:
            raise P139ServiceError("exit_history_filename_mismatch")
        records.append((int(validated["generation"]), str(validated["receipt_hash"]), path))
    limit = int(bundle["limits"]["max_exit_history_records"])
    protected = {str(current["receipt_hash"])}
    if current.get("previous_receipt_hash") is not None:
        protected.add(str(current["previous_receipt_hash"]))
    removable = sorted(
        (item for item in records if item[1] not in protected),
        key=lambda item: item[0],
    )
    excess = max(0, len(records) - limit)
    for _generation, _digest, path in removable[:excess]:
        path.unlink()
    if excess:
        _fsync_directory(directory)


def _read_exit_receipt(root: Path, bundle: Mapping[str, Any]) -> dict[str, Any] | None:
    current = _read_json_optional(root, str(bundle["exit_receipt_path"]), maximum=int(bundle["limits"]["max_state_bytes"]))
    if current is None:
        return None
    generation = _positive_int(current.get("generation"), "generation")
    previous: dict[str, Any] | None = None
    if generation > 1:
        prior_hash = _hash(current.get("previous_receipt_hash"), "previous_receipt_hash")
        previous = _required_json(
            root,
            f"{bundle['exit_history_dir']}/{prior_hash.removeprefix('sha256:')}.json",
            bundle,
        )
    value = validate_exit_receipt(current, bundle=bundle, previous=previous)
    history = _required_json(
        root,
        f"{bundle['exit_history_dir']}/{str(value['receipt_hash']).removeprefix('sha256:')}.json",
        bundle,
    )
    if history != value:
        raise P139ServiceError("exit_history_current_mismatch")
    return value


def _classify_start(
    root: Path,
    bundle: Mapping[str, Any],
    prior: Mapping[str, Any] | None,
) -> str:
    readiness = _read_json_optional(root, str(bundle["p138_config"]["readiness_path"]), maximum=int(bundle["limits"]["max_state_bytes"]))
    ledger_hash = _current_ledger_hash(root, bundle)
    if prior is None and readiness is None and ledger_hash == _HASH_NONE:
        return "clean_start"
    if prior is not None and prior.get("last_valid_ledger_hash") == ledger_hash and readiness is not None and readiness.get("status") == "stopped":
        return "clean_restart"
    restart = _read_json_optional(
        root,
        str(bundle["restart_control_path"]),
        maximum=int(bundle["limits"]["max_state_bytes"]),
    )
    if restart is not None:
        record = _validate_restart_control(restart, bundle)
        archived_readiness = record.get("readiness")
        if (
            prior is not None
            and readiness is None
            and record["status"] == "completed"
            and record["previous_exit_receipt_hash"] == prior["receipt_hash"]
            and isinstance(archived_readiness, Mapping)
            and archived_readiness.get("status") == "stopped"
            and record["last_valid_ledger_hash"] == ledger_hash
        ):
            return "clean_restart"
    return "unclean_restart"


def _restart_record_hash(record: Mapping[str, Any]) -> str:
    return stable_hash({key: value for key, value in record.items() if key not in {"status", "record_hash"}})


def _validate_restart_control(record: Mapping[str, Any], bundle: Mapping[str, Any]) -> dict[str, Any]:
    value = _mapping(record, "restart_control")
    fields = {
        "schema_version",
        "status",
        "bundle_hash",
        "previous_exit_receipt_hash",
        "last_valid_ledger_hash",
        "readiness",
        "heartbeat",
        "record_hash",
    }
    if (
        set(value) != fields
        or value.get("schema_version") != RESTART_CONTROL_SCHEMA_VERSION
        or value.get("status") not in {"pending", "completed"}
        or value.get("bundle_hash") != bundle["bundle_hash"]
        or value.get("record_hash") != _restart_record_hash(value)
    ):
        raise P139ServiceError("invalid_restart_control")
    if value.get("previous_exit_receipt_hash") is not None:
        _hash(value.get("previous_exit_receipt_hash"), "restart_previous_receipt_hash")
    ledger_hash = _hash(value.get("last_valid_ledger_hash"), "restart_ledger_hash")
    readiness = value.get("readiness")
    heartbeat = value.get("heartbeat")
    if readiness is not None:
        _validate_readiness(_mapping(readiness, "restart_readiness"), bundle, ledger_hash)
    if heartbeat is not None:
        _validate_heartbeat(_mapping(heartbeat, "restart_heartbeat"), bundle, ledger_hash)
    return deepcopy(dict(value))


def _recover_restart_control(
    root: Path,
    bundle: Mapping[str, Any],
    *,
    activity: dict[str, int],
) -> None:
    current = _read_json_optional(
        root,
        str(bundle["restart_control_path"]),
        maximum=int(bundle["limits"]["max_state_bytes"]),
    )
    if current is None:
        return
    record = _validate_restart_control(current, bundle)
    pending = dict(record)
    pending["status"] = "pending"
    pending["record_hash"] = _restart_record_hash(pending)
    history_path = f"{bundle['restart_history_dir']}/{str(record['record_hash']).removeprefix('sha256:')}.json"
    _write_immutable_json(
        root,
        history_path,
        pending,
        maximum=int(bundle["limits"]["max_state_bytes"]),
    )
    if record["status"] == "completed":
        return
    p138_lease = _AdvisoryLease(root, str(bundle["p138_config"]["lease_path"]))
    if not p138_lease.acquire():
        raise P139ServiceError("p138_lease_unavailable_during_recovery")
    try:
        activity["restart_reconciliation_count"] += 1
        for field, config_key in (
            ("readiness", "readiness_path"),
            ("heartbeat", "heartbeat_path"),
        ):
            archived = record.get(field)
            if archived is None:
                continue
            live = _read_json_optional(
                root,
                str(bundle["p138_config"][config_key]),
                maximum=int(bundle["limits"]["max_state_bytes"]),
            )
            if live is None:
                continue
            if live != archived:
                raise P139ServiceError("restart_recovery_control_conflict")
            _unlink_exact_json(
                root,
                str(bundle["p138_config"][config_key]),
                _mapping(archived, field),
                maximum=int(bundle["limits"]["max_state_bytes"]),
            )
            activity["restart_control_unlink_count"] += 1
            activity["fsync_count"] += 1
        completed = dict(record)
        completed["status"] = "completed"
        completed["record_hash"] = _restart_record_hash(completed)
        _atomic_write_json(
            root,
            str(bundle["restart_control_path"]),
            completed,
            maximum=int(bundle["limits"]["max_state_bytes"]),
        )
        activity["restart_intent_write_count"] += 1
        activity["fsync_count"] += 2
    finally:
        p138_lease.release()


def _rollover_prior_controls(
    root: Path,
    bundle: Mapping[str, Any],
    prior: Mapping[str, Any] | None,
    *,
    activity: dict[str, int],
    crash_after: str | None,
) -> None:
    readiness_path = str(bundle["p138_config"]["readiness_path"])
    heartbeat_path = str(bundle["p138_config"]["heartbeat_path"])
    readiness = _read_json_optional(root, readiness_path, maximum=int(bundle["limits"]["max_state_bytes"]))
    heartbeat = _read_json_optional(root, heartbeat_path, maximum=int(bundle["limits"]["max_state_bytes"]))
    if readiness is None and heartbeat is None:
        return
    ledger_hash = _current_ledger_hash(root, bundle)
    if readiness is not None:
        _validate_readiness(readiness, bundle, ledger_hash)
    if heartbeat is not None:
        _validate_heartbeat(heartbeat, bundle, ledger_hash)
    if prior is not None and readiness is not None and readiness.get("status") == "stopped":
        _validate_receipt_controls(prior, readiness, heartbeat)
    p138_lease = _AdvisoryLease(root, str(bundle["p138_config"]["lease_path"]))
    if not p138_lease.acquire():
        raise P139ServiceError("p138_lease_unavailable_during_rollover")
    try:
        activity["restart_reconciliation_count"] += 1
        record: dict[str, Any] = {
            "schema_version": RESTART_CONTROL_SCHEMA_VERSION,
            "status": "pending",
            "bundle_hash": bundle["bundle_hash"],
            "previous_exit_receipt_hash": None if prior is None else prior["receipt_hash"],
            "last_valid_ledger_hash": ledger_hash,
            "readiness": readiness,
            "heartbeat": heartbeat,
        }
        record["record_hash"] = _restart_record_hash(record)
        _atomic_write_json(root, str(bundle["restart_control_path"]), record, maximum=int(bundle["limits"]["max_state_bytes"]))
        activity["restart_intent_write_count"] += 1
        activity["fsync_count"] += 2
        _crash(crash_after, "restart_intent")
        history_path = f"{bundle['restart_history_dir']}/{str(record['record_hash']).removeprefix('sha256:')}.json"
        _write_immutable_json(root, history_path, record, maximum=int(bundle["limits"]["max_state_bytes"]))
        activity["restart_history_write_count"] += 1
        activity["fsync_count"] += 2
        _crash(crash_after, "restart_history")
        if readiness is not None:
            _unlink_exact_json(root, readiness_path, readiness, maximum=int(bundle["limits"]["max_state_bytes"]))
            activity["restart_control_unlink_count"] += 1
            activity["fsync_count"] += 1
        if heartbeat is not None:
            _unlink_exact_json(root, heartbeat_path, heartbeat, maximum=int(bundle["limits"]["max_state_bytes"]))
            activity["restart_control_unlink_count"] += 1
            activity["fsync_count"] += 1
        _crash(crash_after, "restart_controls_removed")
        completed = dict(record)
        completed["status"] = "completed"
        completed["record_hash"] = _restart_record_hash(completed)
        _atomic_write_json(root, str(bundle["restart_control_path"]), completed, maximum=int(bundle["limits"]["max_state_bytes"]))
        activity["restart_intent_write_count"] += 1
        activity["fsync_count"] += 2
    finally:
        p138_lease.release()


def _validate_readiness(record: Mapping[str, Any], bundle: Mapping[str, Any], ledger_hash: str) -> None:
    fields = {"schema_version", "config_hash", "status", "reason", "last_valid_ledger_hash", "written_at", "readiness_hash"}
    if set(record) != fields or record.get("schema_version") != READINESS_SCHEMA_VERSION or record.get("config_hash") != bundle["p138_config"]["config_hash"]:
        raise P139ServiceError("invalid_p138_readiness")
    if record.get("readiness_hash") != stable_hash({key: item for key, item in record.items() if key != "readiness_hash"}):
        raise P139ServiceError("invalid_p138_readiness_hash")
    if record.get("status") not in {"ready", "stopped"} or record.get("last_valid_ledger_hash") != ledger_hash:
        raise P139ServiceError("p138_readiness_ledger_mismatch")
    _timestamp(record.get("written_at"), "readiness_written_at")


def _validate_heartbeat(record: Mapping[str, Any], bundle: Mapping[str, Any], ledger_hash: str) -> None:
    fields = {"schema_version", "config_hash", "cycle_sequence", "monotonic_elapsed_ms", "last_valid_ledger_hash", "readiness_state", "written_at", "heartbeat_hash"}
    if set(record) != fields or record.get("schema_version") != HEARTBEAT_SCHEMA_VERSION or record.get("config_hash") != bundle["p138_config"]["config_hash"]:
        raise P139ServiceError("invalid_p138_heartbeat")
    if record.get("heartbeat_hash") != stable_hash({key: item for key, item in record.items() if key != "heartbeat_hash"}):
        raise P139ServiceError("invalid_p138_heartbeat_hash")
    if record.get("last_valid_ledger_hash") != ledger_hash or record.get("readiness_state") not in {"ready", "stopped"}:
        raise P139ServiceError("p138_heartbeat_ledger_mismatch")
    _nonnegative_int(record.get("cycle_sequence"), "heartbeat_cycle_sequence")
    _nonnegative_int(record.get("monotonic_elapsed_ms"), "heartbeat_elapsed_ms")
    _timestamp(record.get("written_at"), "heartbeat_written_at")


def _validate_termination(record: Mapping[str, Any], bundle: Mapping[str, Any], ledger_hash: str) -> None:
    fields = {"schema_version", "config_hash", "stop_reason", "safe_boundary", "last_valid_ledger_hash", "cycles_completed", "forbidden_authority", "written_at", "termination_hash"}
    if set(record) != fields or record.get("schema_version") != TERMINATION_SCHEMA_VERSION or record.get("config_hash") != bundle["p138_config"]["config_hash"]:
        raise P139ServiceError("invalid_p138_termination")
    if record.get("termination_hash") != stable_hash({key: item for key, item in record.items() if key != "termination_hash"}):
        raise P139ServiceError("invalid_p138_termination_hash")
    if record.get("safe_boundary") != "between_supervisor_cycles" or record.get("last_valid_ledger_hash") != ledger_hash:
        raise P139ServiceError("p138_termination_ledger_mismatch")
    _exact_counter_map(record.get("forbidden_authority"), FORBIDDEN_AUTHORITY_KEYS, "invalid_termination_authority", require_zero=True)


def _validate_receipt_controls(
    receipt: Mapping[str, Any],
    readiness: Mapping[str, Any],
    heartbeat: Mapping[str, Any] | None,
) -> None:
    if receipt.get("p138_readiness_hash") != readiness.get("readiness_hash"):
        raise P139ServiceError("exit_receipt_readiness_mismatch")
    if heartbeat is None or receipt.get("p138_heartbeat_hash") != heartbeat.get("heartbeat_hash"):
        raise P139ServiceError("exit_receipt_heartbeat_mismatch")


def _current_ledger_hash(root: Path, bundle: Mapping[str, Any]) -> str:
    config = bundle["p138_config"]
    current = _read_json_optional(root, str(config["ledger_path"]), maximum=int(bundle["limits"]["max_state_bytes"]))
    if current is None:
        return _HASH_NONE
    cursor = current
    while True:
        validate_supervisor_ledger(cursor, config=config, _allow_unbound_non_genesis=True)
        digest = str(cursor["ledger_hash"])
        ledger_path = PurePosixPath(str(config["ledger_path"]))
        history_relative = str(ledger_path.parent / f".{ledger_path.name}.history" / f"{digest.removeprefix('sha256:')}.json")
        archived = _required_json(root, history_relative, bundle)
        if archived != cursor:
            raise P139ServiceError("p138_ledger_history_mismatch")
        if int(cursor["cycle_sequence"]) == 1:
            validate_supervisor_ledger(cursor, config=config)
            break
        previous_hash = _hash(cursor.get("previous_ledger_hash"), "previous_ledger_hash")
        predecessor_relative = str(ledger_path.parent / f".{ledger_path.name}.history" / f"{previous_hash.removeprefix('sha256:')}.json")
        predecessor = _required_json(root, predecessor_relative, bundle)
        validate_supervisor_ledger(cursor, config=config, previous=predecessor)
        cursor = predecessor
    return str(current["ledger_hash"])


def _probe_lease_held(root: Path, relative_path: str) -> bool:
    lease = _AdvisoryLease(root, relative_path, create=False)
    acquired = lease.acquire()
    if acquired:
        lease.release()
        return False
    return True


def _resource_start() -> tuple[float, float, float, int]:
    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return time.monotonic(), time.process_time(), children.ru_utime + children.ru_stime, int(usage.ru_maxrss)


def _resource_end(start: tuple[float, float, float, int], bundle: Mapping[str, Any]) -> dict[str, int]:
    wall, cpu, child_cpu, peak = start
    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    usage = resource.getrusage(resource.RUSAGE_SELF)
    child_now = children.ru_utime + children.ru_stime
    limits = bundle["limits"]
    return {
        "wall_time_ms": max(0, int((time.monotonic() - wall) * 1000)),
        "cpu_time_ms": max(0, int((time.process_time() - cpu) * 1000)),
        "child_cpu_time_ms": max(0, int((child_now - child_cpu) * 1000)),
        "peak_memory_bytes": max(0, _rss_bytes(int(usage.ru_maxrss)) - _rss_bytes(peak)),
        "wall_limit_ms": int(limits["wall_limit_ms"]),
        "cpu_limit_ms": int(limits["cpu_limit_ms"]),
        "peak_memory_limit_bytes": int(limits["peak_memory_limit_bytes"]),
    }


def _rss_bytes(value: int) -> int:
    return value if __import__("sys").platform == "darwin" else value * 1024


def _resource_exceeded(value: Mapping[str, int]) -> bool:
    return value["wall_time_ms"] > value["wall_limit_ms"] or value["cpu_time_ms"] > value["cpu_limit_ms"] or value["peak_memory_bytes"] > value["peak_memory_limit_bytes"]


def _resource_usage(value: Any, bundle: Mapping[str, Any]) -> dict[str, int]:
    result = _exact_counter_map(value, RESOURCE_USAGE_KEYS, "invalid_resource_usage")
    limits = bundle["limits"]
    if result["wall_limit_ms"] != limits["wall_limit_ms"] or result["cpu_limit_ms"] != limits["cpu_limit_ms"] or result["peak_memory_limit_bytes"] != limits["peak_memory_limit_bytes"]:
        raise P139ServiceError("resource_limit_binding_mismatch")
    if _resource_exceeded(result):
        raise P139ServiceError("resource_budget_exceeded")
    return result


def _crash(crash_after: str | None, boundary: str) -> None:
    if crash_after == boundary:
        raise P139InjectedCrash(boundary)


def _required_json(root: Path, relative_path: str, bundle: Mapping[str, Any]) -> dict[str, Any]:
    value = _read_json_optional(root, relative_path, maximum=int(bundle["limits"]["max_state_bytes"]))
    if value is None:
        raise P139ServiceError(f"required_state_missing:{relative_path}")
    return value


def _read_json_optional(root: Path, relative_path: str, *, maximum: int) -> dict[str, Any] | None:
    path = _secure_runtime_path(root, relative_path, create_parent=False)
    try:
        raw = _read_regular_path(path, maximum=maximum)
    except FileNotFoundError:
        return None
    return _decode_canonical_json(raw, "state")


def _write_immutable_json(root: Path, relative_path: str, value: Mapping[str, Any], *, maximum: int) -> None:
    existing = _read_json_optional(root, relative_path, maximum=maximum)
    if existing is not None:
        if existing != dict(value):
            raise P139ServiceError("immutable_history_conflict")
        return
    _atomic_write_json(root, relative_path, value, maximum=maximum)


def _atomic_write_json(root: Path, relative_path: str, value: Mapping[str, Any], *, maximum: int) -> None:
    payload = _canonical_bytes(value)
    if len(payload) > maximum:
        raise P139ServiceError("state_byte_budget_exceeded")
    _atomic_write_path(_secure_runtime_path(root, relative_path, create_parent=True), payload)


def _atomic_write_path(path: Path, payload: bytes) -> None:
    temp = path.parent / f".{path.name}.{os.getpid()}.{time.monotonic_ns()}.tmp"
    descriptor: int | None = None
    replaced = False
    try:
        try:
            existing = path.lstat()
        except FileNotFoundError:
            existing = None
        if existing is not None and (path.is_symlink() or not stat.S_ISREG(existing.st_mode) or existing.st_nlink != 1):
            raise P139ServiceError("atomic_target_not_secure_regular_file")
        descriptor = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0), 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        replaced = True
        parent_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    except OSError as exc:
        raise P139ServiceError("state_durability_uncertain" if replaced else "state_atomic_write_failed") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def _unlink_exact_json(root: Path, relative_path: str, expected: Mapping[str, Any], *, maximum: int) -> None:
    path = _secure_runtime_path(root, relative_path, create_parent=False)
    current = _decode_canonical_json(_read_regular_path(path, maximum=maximum), "state")
    if current != dict(expected):
        raise P139ServiceError("restart_control_replaced_before_unlink")
    path.unlink()
    parent_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)


def _read_regular_path(path: Path, *, maximum: int) -> bytes:
    before_path = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(before_path.st_mode) or before_path.st_nlink != 1:
        raise P139ServiceError("path_not_secure_regular_file")
    if before_path.st_size > maximum:
        raise P139ServiceError("file_byte_budget_exceeded")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
    try:
        before = os.fstat(descriptor)
        if (before.st_dev, before.st_ino, before.st_size) != (before_path.st_dev, before_path.st_ino, before_path.st_size):
            raise P139ServiceError("path_binding_changed")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(65_536, maximum + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > maximum:
                raise P139ServiceError("file_byte_budget_exceeded")
        after = os.fstat(descriptor)
        if (before.st_dev, before.st_ino, before.st_size) != (after.st_dev, after.st_ino, after.st_size):
            raise P139ServiceError("file_identity_changed_during_read")
        current = path.lstat()
        if (after.st_dev, after.st_ino, after.st_size) != (current.st_dev, current.st_ino, current.st_size):
            raise P139ServiceError("path_binding_changed")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _decode_canonical_json(raw: bytes, label: str) -> dict[str, Any]:
    if not raw.endswith(b"\n") or raw.endswith(b"\n\n"):
        raise P139ServiceError(f"{label}_json_noncanonical")
    try:
        decoded = raw[:-1].decode("utf-8", errors="strict")
        value = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise P139ServiceError(f"{label}_json_invalid") from exc
    if not isinstance(value, Mapping) or _canonical_bytes(value) != raw:
        raise P139ServiceError(f"{label}_json_noncanonical")
    return dict(value)


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _secure_runtime_path(root: Path, relative_path: str, *, create_parent: bool) -> Path:
    relative = PurePosixPath(_relative_path(relative_path, "runtime_path"))
    if root.is_symlink() or not root.is_dir():
        raise P139ServiceError("base_path_not_secure_directory")
    current = root
    for part in relative.parts[:-1]:
        current = current / part
        if create_parent:
            current.mkdir(mode=0o700, exist_ok=True)
        try:
            info = current.lstat()
        except FileNotFoundError as exc:
            if create_parent:
                raise P139ServiceError("runtime_parent_missing_after_create") from exc
            return root.joinpath(*relative.parts)
        if current.is_symlink() or not stat.S_ISDIR(info.st_mode):
            raise P139ServiceError("runtime_path_symlink_forbidden")
    path = root.joinpath(*relative.parts)
    if path.is_symlink():
        raise P139ServiceError("runtime_path_symlink_forbidden")
    return path


def _secure_runtime_directory(
    root: Path,
    relative_path: str,
    *,
    create: bool,
) -> Path:
    relative = PurePosixPath(_relative_path(relative_path, "runtime_directory"))
    if root.is_symlink() or not root.is_dir():
        raise P139ServiceError("base_path_not_secure_directory")
    current = root
    for part in relative.parts:
        current = current / part
        if create:
            current.mkdir(mode=0o700, exist_ok=True)
        try:
            info = current.lstat()
        except FileNotFoundError as exc:
            raise P139ServiceError("runtime_directory_missing") from exc
        if current.is_symlink() or not stat.S_ISDIR(info.st_mode):
            raise P139ServiceError("runtime_directory_not_secure")
    return current


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _validate_path_topology(paths: Mapping[str, str], p138_config: Mapping[str, Any]) -> None:
    values = [PurePosixPath(value) for value in paths.values()]
    p138_paths = [
        PurePosixPath(str(p138_config[key]))
        for key in (
            "phase_path",
            "ledger_path",
            "checkpoint_path",
            "lease_path",
            "heartbeat_path",
            "readiness_path",
            "termination_dir",
            "publisher_state_path",
            "publisher_intent_path",
            "publisher_lease_path",
            "p136_handoff_bundle_path",
        )
    ]
    for index, left in enumerate(values):
        for right in values[index + 1 :] + p138_paths:
            if left == right or _is_ancestor(left, right) or _is_ancestor(right, left):
                raise P139ServiceError("service_path_overlap")


def _is_ancestor(left: PurePosixPath, right: PurePosixPath) -> bool:
    return len(left.parts) < len(right.parts) and right.parts[: len(left.parts)] == left.parts


def _reject_callable_values(value: Any, label: str) -> None:
    if callable(value):
        raise P139ServiceError(f"callable_forbidden:{label}")
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_callable_values(item, f"{label}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            _reject_callable_values(item, f"{label}[{index}]")


def _encode_runtime_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return {_BYTES_TAG: value.hex()}
    if isinstance(value, Mapping):
        if _BYTES_TAG in value:
            raise P139ServiceError("reserved_runtime_tag_collision")
        if any(not isinstance(key, str) for key in value):
            raise P139ServiceError("serialized_runtime_key_not_string")
        return {key: _encode_runtime_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_encode_runtime_value(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise P139ServiceError("serialized_runtime_float_not_finite")
    if value is None or isinstance(value, str) or type(value) in {bool, int, float}:
        return value
    raise P139ServiceError("unsupported_serialized_runtime_value")


def _decode_runtime_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        if set(value) == {_BYTES_TAG}:
            encoded = value[_BYTES_TAG]
            if not isinstance(encoded, str) or len(encoded) % 2 or not re.fullmatch(r"[0-9a-f]*", encoded):
                raise P139ServiceError("invalid_serialized_runtime_bytes")
            return bytes.fromhex(encoded)
        if _BYTES_TAG in value:
            raise P139ServiceError("invalid_serialized_runtime_tag")
        return {str(key): _decode_runtime_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decode_runtime_value(item) for item in value]
    return value


def _validate_serialized_runtime(value: Mapping[str, Any]) -> None:
    decoded = _decode_runtime_value(value)
    if _encode_runtime_value(decoded) != dict(value):
        raise P139ServiceError("serialized_runtime_noncanonical")
    try:
        _canonical_bytes(value)
    except (TypeError, ValueError) as exc:
        raise P139ServiceError("serialized_runtime_not_json") from exc


def _reject_forbidden_text(value: Any) -> None:
    if isinstance(value, str) and _FORBIDDEN_TEXT_RE.search(value):
        raise P139ServiceError("forbidden_bundle_text")
    if isinstance(value, Mapping):
        for item in value.values():
            _reject_forbidden_text(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            _reject_forbidden_text(item)


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise P139ServiceError(f"invalid_{label}_shape")
    return value


def _relative_path(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 512:
        raise P139ServiceError(f"invalid_{label}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise P139ServiceError(f"invalid_{label}")
    return str(path)


def _label(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _LABEL_RE.fullmatch(value):
        raise P139ServiceError(f"invalid_{label}")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 256:
        raise P139ServiceError(f"invalid_{label}")
    return value


def _hash(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _HASH_RE.fullmatch(value):
        raise P139ServiceError(f"invalid_{label}")
    return value


def _positive_int(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise P139ServiceError(f"invalid_{label}")
    return value


def _nonnegative_int(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise P139ServiceError(f"invalid_{label}")
    return value


def _exact_positive_int_map(value: Any, keys: frozenset[str]) -> dict[str, int]:
    raw = _mapping(value, "limits")
    if set(raw) != keys:
        raise P139ServiceError("invalid_limit_schema")
    return {key: _positive_int(raw[key], key) for key in sorted(keys)}


def _exact_counter_map(value: Any, keys: Sequence[str], error: str, *, require_zero: bool = False) -> dict[str, int]:
    raw = _mapping(value, "counter_map")
    if set(raw) != set(keys):
        raise P139ServiceError(error)
    result = {key: _nonnegative_int(raw[key], key) for key in keys}
    if require_zero and any(result.values()):
        raise P139ServiceError(error)
    return result


def _timestamp(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise P139ServiceError(f"invalid_{label}")
    _parse_timestamp(value, label)
    return value


def _parse_timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise P139ServiceError(f"invalid_{label}")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise P139ServiceError(f"invalid_{label}") from exc
    if parsed.tzinfo != UTC:
        raise P139ServiceError(f"invalid_{label}")
    return parsed


def utc_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


__all__ = [
    "EVALUATOR_ACTIVITY_KEYS",
    "EXIT_RECEIPT_SCHEMA_VERSION",
    "EXPECTED_P138_EVIDENCE_HASH",
    "EXPECTED_P138_REVIEW_HASH",
    "P138_QUALIFIED_STATUS",
    "P139InjectedCrash",
    "P139ServiceError",
    "P139StopController",
    "RESOURCE_USAGE_KEYS",
    "SERVICE_ACTIVITY_KEYS",
    "SERVICE_BUNDLE_SCHEMA_VERSION",
    "SERVICE_STATUS_SCHEMA_VERSION",
    "build_local_triage_service_bundle",
    "inspect_local_triage_service",
    "read_local_triage_service_bundle",
    "run_local_triage_service",
    "run_local_triage_service_for_evaluation",
    "serialize_p136_runtime",
    "utc_timestamp",
    "validate_exit_receipt",
    "validate_local_triage_service_bundle",
    "write_local_triage_service_bundle",
    "zero_evaluator_activity",
    "zero_forbidden_authority",
    "zero_service_activity",
]
