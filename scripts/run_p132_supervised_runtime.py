#!/usr/bin/env python3
"""Generate P132 endurance, real-process, supervisor, and release evidence."""

from __future__ import annotations

import argparse
import errno
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app.services.p131_always_on_monitor as p131_runtime  # noqa: E402
from app.services.p110_evaluation import stable_hash  # noqa: E402
from app.services.p131_always_on_monitor import (  # noqa: E402
    AlwaysOnMonitor,
    P131DurabilityUncertainError,
    load_monitor_config,
    load_monitor_state,
)
from app.services.p132_release_evidence import (  # noqa: E402
    P132_READY_STATUS,
    build_p132_release_evidence,
    validate_p132_release_evidence,
)
from app.services.p132_supervised_runtime import (  # noqa: E402
    load_endurance_profile,
    run_endurance_qualification,
    validate_supervisor_manifests,
)

_FORBIDDEN_EVALUATOR_KEYS = (
    "arbitrary_command_count",
    "credential_read_count",
    "network_call_count",
    "connector_write_count",
    "remediation_count",
    "staging_mutation_count",
    "production_mutation_count",
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", type=Path, default=ROOT / "evals/p132/input/endurance-profile.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "evals/p132")
    args = parser.parse_args(argv)

    profile = load_endurance_profile(args.profile)
    output_dir = args.output_dir.expanduser().resolve()
    with tempfile.TemporaryDirectory(prefix="opscat-p132-") as temporary_name:
        workspace = Path(temporary_name)
        endurance = run_endurance_qualification(profile, workspace=workspace / "endurance")
        process_matrix, evaluator_activity, supervisor_ledger = _run_process_matrix(
            workspace / "process",
            shutdown_timeout=float(profile["max_shutdown_latency_seconds"]),
        )
        _promote_raw_artifacts(workspace, output_dir)
        _bind_promoted_artifact_paths(endurance, process_matrix)
    supervisor = validate_supervisor_manifests(ROOT / "deploy/p132", project_root=ROOT)
    release = build_p132_release_evidence(
        endurance,
        process_matrix,
        supervisor,
        evaluator_activity=evaluator_activity,
    )
    _write_atomic(output_dir / "endurance-report.json", endurance)
    _write_atomic(output_dir / "process-matrix.json", process_matrix)
    _write_atomic(output_dir / "supervisor-validation.json", supervisor)
    _write_atomic(output_dir / "supervisor-ledger.json", supervisor_ledger)
    _write_atomic(output_dir / "release-evidence.json", release)
    validate_p132_release_evidence(
        release,
        endurance_report=endurance,
        process_matrix=process_matrix,
        supervisor_validation=supervisor,
        project_root=ROOT,
        artifact_root=output_dir,
    )
    print(
        json.dumps(
            {
                "release_status": release["release_status"],
                "release_evidence_hash": release["release_evidence_hash"],
            },
            sort_keys=True,
        )
    )
    return 0 if release["release_status"] == P132_READY_STATUS else 1


def _promote_raw_artifacts(workspace: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / "raw"
    staging = output_dir / f".raw.{os.getpid()}.tmp"
    if staging.exists():
        shutil.rmtree(staging)
    try:
        shutil.copytree(workspace, staging, symlinks=False)
        if target.exists():
            shutil.rmtree(target)
        os.replace(staging, target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def _bind_promoted_artifact_paths(endurance: dict[str, Any], process_matrix: dict[str, Any]) -> None:
    endurance_artifacts = endurance.get("artifacts")
    if not isinstance(endurance_artifacts, dict):
        raise ValueError("endurance_artifacts_missing")
    endurance_artifacts.update(
        {
            "workspace": "raw/endurance",
            "source_path": "raw/endurance/telemetry.jsonl",
            "state_path": "raw/endurance/state.json",
            "report_dir": "raw/endurance/reports",
        }
    )
    endurance["endurance_report_hash"] = stable_hash(
        {key: value for key, value in endurance.items() if key != "endurance_report_hash"}
    )

    process_matrix["artifact_paths"] = {
        "monitor_config": "raw/process/monitor.json",
        "telemetry": "raw/process/telemetry.jsonl",
        "final_state": "raw/process/state.json",
        "termination_receipt": "raw/process/termination-receipt.json",
        "storage_low_space_state": "raw/process/storage/low-space/state.json",
        "storage_pre_replace_canonical": "raw/process/storage/pre-replace/canonical.json",
        "storage_post_replace_state": "raw/process/storage/post-replace/state.json",
        "storage_report_interruption_state": "raw/process/storage/report-interruption/state.json",
    }
    process_matrix["process_matrix_hash"] = stable_hash(
        {key: value for key, value in process_matrix.items() if key != "process_matrix_hash"}
    )


def _run_process_matrix(workspace: Path, *, shutdown_timeout: float) -> tuple[dict[str, Any], dict[str, int], dict[str, Any]]:
    workspace.mkdir(parents=True, exist_ok=True)
    source = workspace / "telemetry.jsonl"
    _append_observation(source, 0)
    config_path = workspace / "monitor.json"
    state_path = workspace / "state.json"
    receipt_path = workspace / "termination-receipt.json"
    config = {
        "schema_version": "p131.monitor_config.v1",
        "runtime_id": "p132-real-process-runtime",
        "interval_seconds": 1,
        "heartbeat_timeout_seconds": 1,
        "data_stale_after_seconds": 30,
        "daily_report_interval_seconds": 10,
        "canary_every_cycles": 1,
        "max_consecutive_failures": 3,
        "max_bytes_per_cycle": 65536,
        "max_records_per_cycle": 10,
        "max_line_bytes": 4096,
        "max_report_files": 8,
        "max_report_dir_bytes": 1048576,
        "min_artifact_free_bytes": 1,
        "state_path": str(state_path),
        "report_dir": str(workspace / "reports"),
        "lease_path": str(workspace / "runtime.lock"),
        "termination_receipt_path": str(receipt_path),
        "allowed_data_roots": [str(workspace)],
        "allowed_artifact_roots": [str(workspace)],
        "sources": [{"source_id": "local", "kind": "local_jsonl", "path": str(source), "enabled": True}],
    }
    _write_atomic(config_path, config)

    activity = {
        "process_launch_count": 0,
        "signal_count": 0,
        "sigterm_count": 0,
        "sigint_count": 0,
        "forced_kill_count": 0,
        "watchdog_call_count": 0,
        "status_call_count": 0,
        "lease_conflict_count": 0,
        **{key: 0 for key in _FORBIDDEN_EVALUATOR_KEYS},
    }
    ledger: list[dict[str, Any]] = []

    owner = _start_owner(config_path, activity, ledger, "sigterm-owner")
    _wait_for_state(state_path, lambda state: state["lifecycle"]["phase"] == "running" and state["cycle_count"] >= 1, owner)
    current_watchdog = _run_monitor_command(
        ["watchdog", "--state", str(state_path), "--timeout-seconds", "1"],
        activity,
        ledger,
        "watchdog-current",
        workspace=workspace,
        counter="watchdog_call_count",
    )
    current_status = _run_monitor_command(
        [
            "status",
            "--state",
            str(state_path),
            "--heartbeat-timeout-seconds",
            "1",
            "--data-stale-after-seconds",
            "30",
        ],
        activity,
        ledger,
        "status-current",
        workspace=workspace,
        counter="status_call_count",
    )
    competitor = _run_monitor_command(
        ["run", "--config", str(config_path), "--max-cycles", "1", "--no-sleep"],
        activity,
        ledger,
        "lease-competitor",
        workspace=workspace,
    )
    lease_conflict = competitor.returncode != 0 and "runtime_lease_unavailable" in competitor.stderr
    activity["lease_conflict_count"] += int(lease_conflict)

    sigterm = _stop_owner(owner, signal.SIGTERM, "sigterm", activity, ledger, shutdown_timeout)
    stopped_after_term = load_monitor_state(state_path)
    term_receipt = _read_json(receipt_path)
    stopped_watchdog = _run_monitor_command(
        ["watchdog", "--state", str(state_path), "--timeout-seconds", "1"],
        activity,
        ledger,
        "watchdog-stopped",
        workspace=workspace,
        counter="watchdog_call_count",
    )
    sigterm_passed = all(
        (
            sigterm["returncode"] == 0,
            sigterm["latency_seconds"] <= shutdown_timeout,
            stopped_after_term["lifecycle"]["phase"] == "stopped",
            stopped_after_term["lifecycle"]["last_stop_reason"] == "sigterm",
            _valid_receipt(term_receipt, stopped_after_term, reason="sigterm"),
            stopped_watchdog.returncode == 1,
            _stdout_json(stopped_watchdog).get("reason") == "runtime_stopped",
        )
    )

    _append_observation(source, 1)
    crash_owner = _start_owner(config_path, activity, ledger, "crash-owner")
    resumed_before_crash = _wait_for_state(
        state_path,
        lambda state: state["lifecycle"]["phase"] == "running"
        and state["resume_count"] >= 1
        and state["totals"]["accepted_observation_count"] == 2,
        crash_owner,
    )
    crash = _stop_owner(crash_owner, signal.SIGKILL, "sigkill", activity, ledger, shutdown_timeout)
    time.sleep(1.2)
    stale_watchdog = _run_monitor_command(
        ["watchdog", "--state", str(state_path), "--timeout-seconds", "1"],
        activity,
        ledger,
        "watchdog-stale",
        workspace=workspace,
        counter="watchdog_call_count",
    )

    _append_observation(source, 2)
    sigint_owner = _start_owner(config_path, activity, ledger, "sigint-owner")
    resumed_after_crash = _wait_for_state(
        state_path,
        lambda state: state["lifecycle"]["phase"] == "running"
        and state["resume_count"] >= 2
        and state["totals"]["accepted_observation_count"] == 3,
        sigint_owner,
    )
    sigint = _stop_owner(sigint_owner, signal.SIGINT, "sigint", activity, ledger, shutdown_timeout)
    final_state = load_monitor_state(state_path)
    int_receipt = _read_json(receipt_path)
    sigint_passed = all(
        (
            sigint["returncode"] == 0,
            sigint["latency_seconds"] <= shutdown_timeout,
            final_state["lifecycle"]["phase"] == "stopped",
            final_state["lifecycle"]["last_stop_reason"] == "sigint",
            final_state["lifecycle"]["graceful_stop_count"] == 2,
            _valid_receipt(int_receipt, final_state, reason="sigint"),
        )
    )
    forced_restart_passed = all(
        (
            crash["returncode"] != 0,
            stale_watchdog.returncode == 1,
            _stdout_json(stale_watchdog).get("reason") == "heartbeat_stale",
            resumed_before_crash["totals"]["accepted_observation_count"] == 2,
            resumed_after_crash["resume_count"] >= 2,
            final_state["totals"]["accepted_observation_count"] == 3,
            final_state["totals"]["duplicate_observation_count"] == 0,
        )
    )

    missing_watchdog = _run_monitor_command(
        ["watchdog", "--state", str(workspace / "missing.json"), "--timeout-seconds", "1"],
        activity,
        ledger,
        "watchdog-missing",
        workspace=workspace,
        counter="watchdog_call_count",
    )
    tampered_path = workspace / "tampered.json"
    tampered = dict(final_state)
    tampered["cycle_count"] = 999999
    _write_atomic(tampered_path, tampered)
    tampered_watchdog = _run_monitor_command(
        ["watchdog", "--state", str(tampered_path), "--timeout-seconds", "1"],
        activity,
        ledger,
        "watchdog-tampered",
        workspace=workspace,
        counter="watchdog_call_count",
    )

    storage_cases, storage_artifacts = _run_storage_matrix(workspace / "storage")

    matrix: dict[str, Any] = {
        "schema_version": "p132.process_matrix.v1",
        "runtime_id": config["runtime_id"],
        "cases": {
            "sigterm": {"passed": sigterm_passed, **sigterm},
            "sigint": {"passed": sigint_passed, **sigint},
            "forced_crash_restart": {
                "passed": forced_restart_passed,
                "kill_returncode": crash["returncode"],
                "resume_count": final_state["resume_count"],
                "accepted_observation_count": final_state["totals"]["accepted_observation_count"],
                "duplicate_observation_count": final_state["totals"]["duplicate_observation_count"],
            },
            "lease_conflict": {"passed": lease_conflict, "competitor_returncode": competitor.returncode},
        },
        "watchdog_cases": {
            "current": current_watchdog.returncode == 0 and _stdout_json(current_watchdog).get("healthy") is True,
            "stopped": stopped_watchdog.returncode == 1 and _stdout_json(stopped_watchdog).get("reason") == "runtime_stopped",
            "stale": stale_watchdog.returncode == 1 and _stdout_json(stale_watchdog).get("reason") == "heartbeat_stale",
            "missing": missing_watchdog.returncode == 1 and _stdout_json(missing_watchdog).get("reason") == "state_missing",
            "tampered": tampered_watchdog.returncode == 1 and _stdout_json(tampered_watchdog).get("reason") == "state_hash_invalid",
            "status_current": current_status.returncode == 0 and _stdout_json(current_status).get("live") is True,
        },
        "storage_cases": storage_cases,
        "storage_matrix_hash": stable_hash(storage_cases),
        "runtime_authority": final_state["authority"],
        "evaluator_activity": dict(activity),
        "final_state_hash": final_state["state_hash"],
        "source_hashes": {
            path.relative_to(ROOT).as_posix(): _file_hash(path)
            for path in (
                ROOT / "app/services/p131_always_on_monitor.py",
                ROOT / "app/services/p132_supervised_runtime.py",
                ROOT / "app/services/p132_release_evidence.py",
                ROOT / "app/monitor_cli.py",
                ROOT / "scripts/run_p132_supervised_runtime.py",
            )
        },
        "artifact_hashes": {
            "monitor_config": _file_hash(config_path),
            "telemetry": _file_hash(source),
            "final_state": _file_hash(state_path),
            "termination_receipt": _file_hash(receipt_path),
            **storage_artifacts,
        },
    }
    matrix["passed"] = (
        all(case["passed"] is True for case in matrix["cases"].values())
        and all(matrix["watchdog_cases"].values())
        and all(case["passed"] is True for case in storage_cases.values())
    )
    matrix["process_matrix_hash"] = stable_hash(matrix)
    supervisor_ledger: dict[str, Any] = {
        "schema_version": "p132.supervisor_ledger.v1",
        "commands": ledger,
        "evaluator_activity": dict(activity),
    }
    supervisor_ledger["supervisor_ledger_hash"] = stable_hash(supervisor_ledger)
    return matrix, activity, supervisor_ledger


class _StorageClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 7, 13, tzinfo=UTC)

    def now(self) -> datetime:
        return self.current

    def sleep(self, seconds: float) -> None:
        self.current += timedelta(seconds=seconds)

    def monotonic(self) -> float:
        return self.current.timestamp()


def _run_storage_matrix(workspace: Path) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    workspace.mkdir(parents=True, exist_ok=True)

    low_config = load_monitor_config(_write_storage_config(workspace / "low-space", "p132-storage-low-space"))
    low_clock = _StorageClock()
    AlwaysOnMonitor(low_config, clock=low_clock).run(max_cycles=1, sleep_enabled=False)
    low_before = low_config.state_path.read_bytes()
    low_error: OSError | None = None
    try:
        with patch.object(p131_runtime, "_artifact_free_bytes", lambda *_: 0):
            AlwaysOnMonitor(low_config, clock=low_clock).run(max_cycles=1, sleep_enabled=False)
    except OSError as exc:
        low_error = exc
    low_state = load_monitor_state(low_config.state_path, allowed_roots=low_config.allowed_artifact_roots)
    low_passed = (
        low_error is not None
        and "artifact_free_space_below_floor" in str(low_error)
        and low_config.state_path.read_bytes() == low_before
        and low_state.get("state_hash") == stable_hash({key: value for key, value in low_state.items() if key != "state_hash"})
    )

    pre_root = workspace / "pre-replace"
    pre_target = pre_root / "canonical.json"
    _write_atomic(pre_target, {"generation": "old"})
    pre_before = pre_target.read_bytes()
    pre_error: OSError | None = None

    def fail_replace(*_: object, **__: object) -> None:
        raise OSError(errno.ENOSPC, "replace failed")

    try:
        with patch.object(p131_runtime.os, "replace", fail_replace):
            p131_runtime._atomic_write_json(pre_target, {"generation": "new"})
    except OSError as exc:
        pre_error = exc
    pre_passed = pre_error is not None and pre_error.errno == errno.ENOSPC and pre_target.read_bytes() == pre_before

    post_config = load_monitor_config(_write_storage_config(workspace / "post-replace", "p132-storage-post-replace"))
    post_clock = _StorageClock()
    original_fsync = p131_runtime.os.fsync
    post_error: P131DurabilityUncertainError | None = None

    def fail_directory_fsync(file_descriptor: int) -> None:
        if stat.S_ISDIR(os.fstat(file_descriptor).st_mode):
            raise OSError(errno.ENOSPC, "directory fsync failed")
        original_fsync(file_descriptor)

    try:
        with patch.object(p131_runtime.os, "fsync", fail_directory_fsync):
            AlwaysOnMonitor(post_config, clock=post_clock).run(max_cycles=1, sleep_enabled=False)
    except P131DurabilityUncertainError as exc:
        post_error = exc
    uncertain_state = load_monitor_state(post_config.state_path, allowed_roots=post_config.allowed_artifact_roots)
    uncertain_hash = str(uncertain_state["state_hash"])
    AlwaysOnMonitor(post_config, clock=post_clock).run(max_cycles=1, sleep_enabled=False)
    recovered_state = load_monitor_state(post_config.state_path, allowed_roots=post_config.allowed_artifact_roots)
    post_passed = (
        post_error is not None
        and "directory_fsync_failed_after_replace" in str(post_error)
        and recovered_state["cycle_count"] > uncertain_state["cycle_count"]
        and recovered_state["state_hash"] != uncertain_hash
    )

    report_config = load_monitor_config(
        _write_storage_config(workspace / "report-interruption", "p132-storage-report-interruption")
    )
    report_clock = _StorageClock()
    AlwaysOnMonitor(report_config, clock=report_clock).run(max_cycles=1, sleep_enabled=False)
    report_before = load_monitor_state(report_config.state_path, allowed_roots=report_config.allowed_artifact_roots)
    report_clock.sleep(float(report_config.daily_report_interval_seconds))
    original_atomic_write = p131_runtime._atomic_write_json
    report_error: OSError | None = None

    def fail_report_write(
        path: Path,
        value: object,
        *,
        allowed_roots: Sequence[Path] | None = None,
    ) -> None:
        if path.parent.resolve() == report_config.report_dir.resolve():
            raise OSError(errno.EIO, "report write interrupted")
        original_atomic_write(path, value, allowed_roots=allowed_roots)

    try:
        with patch.object(p131_runtime, "_atomic_write_json", fail_report_write):
            AlwaysOnMonitor(report_config, clock=report_clock).run(max_cycles=1, sleep_enabled=False)
    except OSError as exc:
        report_error = exc
    report_after = load_monitor_state(report_config.state_path, allowed_roots=report_config.allowed_artifact_roots)
    report_passed = (
        report_error is not None
        and report_error.errno == errno.EIO
        and report_after["last_report_bucket"] == report_before["last_report_bucket"]
        and report_after["cycle_count"] > report_before["cycle_count"]
    )

    cases = {
        "low_space_preserves_checkpoint": {
            "passed": low_passed,
            "failure": str(low_error) if low_error is not None else None,
            "state_hash": low_state["state_hash"],
        },
        "pre_replace_preserves_canonical": {
            "passed": pre_passed,
            "failure": str(pre_error) if pre_error is not None else None,
            "canonical_hash": _file_hash(pre_target),
        },
        "post_replace_recovery": {
            "passed": post_passed,
            "failure": str(post_error) if post_error is not None else None,
            "uncertain_state_hash": uncertain_hash,
            "recovered_state_hash": recovered_state["state_hash"],
        },
        "report_interruption_preserves_bucket": {
            "passed": report_passed,
            "failure": str(report_error) if report_error is not None else None,
            "prior_report_bucket": report_before["last_report_bucket"],
            "current_report_bucket": report_after["last_report_bucket"],
        },
    }
    artifacts = {
        "storage_low_space_state": _file_hash(low_config.state_path),
        "storage_pre_replace_canonical": _file_hash(pre_target),
        "storage_post_replace_state": _file_hash(post_config.state_path),
        "storage_report_interruption_state": _file_hash(report_config.state_path),
    }
    return cases, artifacts


def _write_storage_config(workspace: Path, runtime_id: str) -> Path:
    workspace.mkdir(parents=True, exist_ok=True)
    source = workspace / "telemetry.jsonl"
    _append_observation(source, 0)
    config_path = workspace / "monitor.json"
    _write_atomic(
        config_path,
        {
            "schema_version": "p131.monitor_config.v1",
            "runtime_id": runtime_id,
            "interval_seconds": 1,
            "heartbeat_timeout_seconds": 1,
            "data_stale_after_seconds": 30,
            "daily_report_interval_seconds": 10,
            "canary_every_cycles": 1,
            "max_consecutive_failures": 3,
            "max_bytes_per_cycle": 65536,
            "max_records_per_cycle": 10,
            "max_line_bytes": 4096,
            "max_report_files": 8,
            "max_report_dir_bytes": 1048576,
            "min_artifact_free_bytes": 1,
            "state_path": str(workspace / "state.json"),
            "report_dir": str(workspace / "reports"),
            "lease_path": str(workspace / "runtime.lock"),
            "termination_receipt_path": str(workspace / "termination-receipt.json"),
            "allowed_data_roots": [str(workspace)],
            "allowed_artifact_roots": [str(workspace)],
            "sources": [{"source_id": "local", "kind": "local_jsonl", "path": str(source), "enabled": True}],
        },
    )
    return config_path


def _start_owner(config_path: Path, activity: dict[str, int], ledger: list[dict[str, Any]], label: str) -> subprocess.Popen[str]:
    command = [sys.executable, "-m", "app.monitor_cli", "run", "--config", str(config_path), "--forever"]
    _validate_command(command, workspace=config_path.parent)
    activity["process_launch_count"] += 1
    ledger.append({"label": label, "command_kind": "monitor_run_forever", "argv_hash": stable_hash(command)})
    return subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _run_monitor_command(
    arguments: list[str],
    activity: dict[str, int],
    ledger: list[dict[str, Any]],
    label: str,
    *,
    workspace: Path,
    counter: str | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, "-m", "app.monitor_cli", *arguments]
    _validate_command(command, workspace=workspace)
    activity["process_launch_count"] += 1
    if counter is not None:
        activity[counter] += 1
    ledger.append({"label": label, "command_kind": f"monitor_{arguments[0]}", "argv_hash": stable_hash(command)})
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=10, check=False)


def _validate_command(command: Sequence[str], *, workspace: Path) -> None:
    if len(command) < 4 or command[0] != sys.executable or tuple(command[1:3]) != ("-m", "app.monitor_cli"):
        raise ValueError("evaluator_command_not_allowlisted")
    workspace = workspace.expanduser().resolve()
    arguments = list(command[3:])
    accepted_shapes = (
        ("run", "--config", "PATH", "--forever"),
        ("run", "--config", "PATH", "--max-cycles", "1", "--no-sleep"),
        ("watchdog", "--state", "PATH", "--timeout-seconds", "1"),
        (
            "status",
            "--state",
            "PATH",
            "--heartbeat-timeout-seconds",
            "1",
            "--data-stale-after-seconds",
            "30",
        ),
    )
    normalized = tuple("PATH" if index == 2 else value for index, value in enumerate(arguments))
    if normalized not in accepted_shapes:
        raise ValueError("evaluator_command_not_allowlisted")
    target = Path(arguments[2]).expanduser().resolve()
    if not target.is_relative_to(workspace):
        raise ValueError("evaluator_command_path_outside_workspace")


def _stop_owner(
    process: subprocess.Popen[str],
    process_signal: signal.Signals,
    reason: str,
    activity: dict[str, int],
    ledger: list[dict[str, Any]],
    timeout: float,
) -> dict[str, Any]:
    started = time.monotonic()
    process.send_signal(process_signal)
    if process_signal == signal.SIGKILL:
        activity["forced_kill_count"] += 1
    else:
        activity["signal_count"] += 1
        activity[f"{reason}_count"] += 1
    stdout, stderr = process.communicate(timeout=timeout)
    latency = time.monotonic() - started
    ledger.append({"label": f"stop-{reason}", "signal": reason, "returncode": process.returncode})
    return {
        "returncode": int(process.returncode or 0),
        "latency_seconds": latency,
        "stdout_hash": stable_hash(stdout),
        "stderr_hash": stable_hash(stderr),
    }


def _wait_for_state(
    path: Path,
    predicate: Callable[[Mapping[str, Any]], bool],
    process: subprocess.Popen[str],
    *,
    timeout: float = 8.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise RuntimeError(f"monitor_exited_early:{process.returncode}:{stdout}:{stderr}")
        if path.exists():
            try:
                state = load_monitor_state(path)
                if predicate(state):
                    return state
            except (OSError, ValueError) as exc:
                last_error = exc
        time.sleep(0.02)
    raise TimeoutError(f"monitor_state_timeout:{last_error}")


def _valid_receipt(receipt: Mapping[str, Any], state: Mapping[str, Any], *, reason: str) -> bool:
    unsigned = {key: value for key, value in receipt.items() if key != "receipt_hash"}
    return all(
        (
            receipt.get("schema_version") == "p132.termination_receipt.v1",
            receipt.get("runtime_id") == state.get("runtime_id"),
            receipt.get("config_hash") == state.get("config_hash"),
            receipt.get("reason") == reason,
            receipt.get("final_cycle_count") == state.get("cycle_count"),
            receipt.get("final_state_hash") == state.get("state_hash"),
            receipt.get("receipt_hash") == stable_hash(unsigned),
        )
    )


def _append_observation(path: Path, sequence: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {"event_id": f"p132-process-{sequence}", "service": "checkout", "message": "ok", "sequence": sequence},
                sort_keys=True,
            )
            + "\n"
        )


def _stdout_json(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected_json_object")
    return value


def _file_hash(path: Path) -> str:
    return stable_hash(path.read_bytes().hex())


def _write_atomic(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
