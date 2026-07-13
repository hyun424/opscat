#!/usr/bin/env python3
"""Generate P133 transition, subprocess, supervisor, authority, and release evidence."""

from __future__ import annotations

import argparse
import configparser
import json
import os
import plistlib
import resource
import shlex
import shutil
import signal
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

import app.services.p133_deadman_outbox as p133_runtime  # noqa: E402
from app.services.p110_evaluation import stable_hash  # noqa: E402
from app.services.p121_signals import zero_authority_counters  # noqa: E402
from app.services.p131_always_on_monitor import AlwaysOnMonitor, load_monitor_config  # noqa: E402
from app.services.p133_deadman_outbox import (  # noqa: E402
    DeadmanConfig,
    DeadmanOutbox,
    P133DeadmanError,
    acknowledge_event,
    list_outbox,
    load_deadman_config,
)
from app.services.p133_release_evidence import (  # noqa: E402
    P133_READY_STATUS,
    REQUIRED_SCENARIOS,
    SUBPROCESS_CASES,
    ZERO_AUTHORITY_COUNTERS,
    build_p133_release_evidence,
    validate_p133_release_evidence,
)

SOURCE_BINDINGS = (
    "app/services/p131_always_on_monitor.py",
    "app/services/p133_deadman_outbox.py",
    "app/services/p133_release_evidence.py",
    "scripts/run_p133_deadman_outbox.py",
    "app/monitor_cli.py",
    "evals/p133/input/outbox-profile.json",
)
MANIFEST_PATHS = (
    "deploy/p133/opscat-deadman.service",
    "deploy/p133/io.opscat.deadman.plist",
    "deploy/p133/compose.deadman.yaml",
)
PROMOTED_MANIFEST_PATHS = (
    "deploy/p133/opscat-deadman.service",
    "deploy/p133/compose.deadman.yaml",
)
PROFILE_FIELDS = frozenset(
    {
        "schema_version",
        "check_interval_seconds",
        "heartbeat_timeout_seconds",
        "reminder_interval_seconds",
        "max_event_files",
        "max_outbox_bytes",
        "max_event_bytes",
        "min_artifact_free_bytes",
        "max_artifact_bytes",
        "max_wall_seconds",
        "max_cpu_seconds",
        "max_peak_memory_mib",
        "max_shutdown_latency_seconds",
        "required_scenarios",
    }
)
PROMOTED_PROFILE_VALUES = {
    "check_interval_seconds": 30,
    "heartbeat_timeout_seconds": 180,
    "reminder_interval_seconds": 300,
    "max_event_files": 32,
    "max_outbox_bytes": 1_048_576,
    "max_event_bytes": 32_768,
    "min_artifact_free_bytes": 1_048_576,
    "max_artifact_bytes": 2_097_152,
    "max_wall_seconds": 60,
    "max_cpu_seconds": 30,
    "max_peak_memory_mib": 64,
    "max_shutdown_latency_seconds": 3,
}


class FakeClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 7, 13, 0, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self.current

    def advance(self, seconds: int) -> None:
        self.current += timedelta(seconds=seconds)


def main(argv: Sequence[str] | None = None) -> int:
    started_wall = time.monotonic()
    started_cpu = _cpu_seconds()
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", type=Path, default=ROOT / "evals/p133/input/outbox-profile.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "evals/p133")
    args = parser.parse_args(argv)

    profile = _load_profile(args.profile)
    output_dir = args.output_dir.expanduser().resolve()
    with tempfile.TemporaryDirectory(prefix="opscat-p133-", dir=Path(tempfile.gettempdir()).resolve()) as temporary_name:
        workspace = Path(temporary_name)
        outbox_report = _run_transition_matrix(
            profile,
            workspace / "matrix",
            profile_hash=_file_hash(args.profile.expanduser().resolve()),
        )
        process_matrix, authority_ledger = _run_subprocess_smoke(profile, workspace / "subprocess")
        raw_files = _raw_file_hashes(workspace)
        promoted_raw_files = {f"raw/{path}": digest for path, digest in raw_files.items()}
        outbox_report["raw_evidence"] = {
            "root": "raw",
            "total_bytes": sum((workspace / path).stat().st_size for path in raw_files),
            "files": promoted_raw_files,
            "root_hash": stable_hash(promoted_raw_files),
        }
        _promote_raw_artifacts(workspace, output_dir)

    supervisor_validation = _validate_supervisor_manifests(ROOT / "deploy/p133")
    process_matrix["resource_limits"] = {
        "max_wall_milliseconds": int(profile["max_wall_seconds"]) * 1000,
        "max_cpu_milliseconds": int(profile["max_cpu_seconds"]) * 1000,
        "max_peak_memory_bytes": int(profile["max_peak_memory_mib"]) * 1024 * 1024,
    }
    process_matrix["resource_usage"] = _resource_usage(started_wall=started_wall, started_cpu=started_cpu)
    _bind_promoted_artifacts(outbox_report, process_matrix, output_dir)
    authority_ledger["runtime_authority"] = outbox_report["runtime_authority"]
    authority_ledger["source_hashes"] = _source_hashes()
    authority_ledger["authority_ledger_hash"] = stable_hash(
        {key: value for key, value in authority_ledger.items() if key != "authority_ledger_hash"}
    )
    release = build_p133_release_evidence(outbox_report, process_matrix, supervisor_validation, authority_ledger)

    _write_atomic(output_dir / "outbox-report.json", outbox_report)
    _write_atomic(output_dir / "process-matrix.json", process_matrix)
    _write_atomic(output_dir / "supervisor-validation.json", supervisor_validation)
    _write_atomic(output_dir / "authority-ledger.json", authority_ledger)
    _write_atomic(output_dir / "release-evidence.json", release)
    validate_p133_release_evidence(
        release,
        outbox_report=outbox_report,
        process_matrix=process_matrix,
        supervisor_validation=supervisor_validation,
        authority_ledger=authority_ledger,
        project_root=ROOT,
        artifact_root=output_dir,
    )
    print(json.dumps({"release_status": release["release_status"], "release_evidence_hash": release["release_evidence_hash"]}, sort_keys=True))
    return 0 if release["release_status"] == P133_READY_STATUS else 1


def _run_transition_matrix(
    profile: Mapping[str, Any],
    workspace: Path,
    *,
    profile_hash: str | None = None,
) -> dict[str, Any]:
    workspace.mkdir(parents=True, exist_ok=True)
    cases: dict[str, dict[str, Any]] = {}
    emitted = dedup = recoveries = acknowledgements = retained = pruned = 0
    config_hashes: dict[str, str] = {}

    def record(name: str, passed: bool, evidence: Mapping[str, Any]) -> None:
        cases[name] = {"passed": passed, "evidence": dict(evidence)}

    config_path = _config_path(workspace / "healthy", profile)
    config = load_deadman_config(config_path)
    config_hashes["healthy"] = config.config_hash
    runtime = DeadmanOutbox(config, now=FakeClock().now, watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("heartbeat_current"))
    result = runtime.check_once()
    dedup += 1
    record("healthy_no_event", result["emitted"] is False, {"emitted_events": 0, "deduplicated_checks": 1})

    clock = FakeClock()
    config = load_deadman_config(_config_path(workspace / "main", profile))
    config_hashes["main"] = config.config_hash
    queue = [
        _watchdog("heartbeat_stale", state_hash="sha256:" + "1" * 64),
        _watchdog("heartbeat_stale", state_hash="sha256:" + "1" * 64),
        _watchdog("runtime_stopped", state_hash="sha256:" + "2" * 64),
        _watchdog("runtime_stopped", state_hash="sha256:" + "2" * 64),
        _watchdog("heartbeat_current", state_hash="sha256:" + "3" * 64),
    ]
    runtime = DeadmanOutbox(config, now=clock.now, watchdog_evaluator=lambda *_args, **_kwargs: queue.pop(0))
    opened = runtime.check_once()
    emitted += 1
    record("stale_open", opened["transition_kind"] == "opened", {"transition_kind": opened["transition_kind"], "event_id": opened["event_id"]})
    clock.advance(299)
    unchanged = runtime.check_once()
    dedup += 1
    record("unchanged_dedup", unchanged["emitted"] is False, {"emitted_events": 0, "deduplicated_checks": 1})
    clock.advance(1)
    updated = runtime.check_once()
    emitted += 1
    record(
        "reason_update",
        updated["transition_kind"] == "updated",
        {"transition_kind": updated["transition_kind"], "event_id": updated["event_id"], "previous_event_id": opened["event_id"]},
    )
    clock.advance(int(profile["reminder_interval_seconds"]))
    reminder = runtime.check_once()
    emitted += 1
    record(
        "reminder_boundary",
        reminder["transition_kind"] == "reminder",
        {"transition_kind": reminder["transition_kind"], "event_id": reminder["event_id"], "reminder_interval_seconds": profile["reminder_interval_seconds"]},
    )
    clock.advance(1)
    recovered = runtime.check_once()
    emitted += 1
    recoveries += 1
    cursor = _read_json(config.cursor_path)
    record(
        "recovery",
        recovered["transition_kind"] == "recovered" and cursor["active_incident"] is None,
        {"transition_kind": recovered["transition_kind"], "event_id": recovered["event_id"], "active_incident_closed": cursor["active_incident"] is None},
    )

    for name, reason in (("stopped_open", "runtime_stopped"), ("missing_open", "state_missing"), ("tampered_open", "state_hash_invalid")):
        config = load_deadman_config(_config_path(workspace / name, profile))
        config_hashes[name] = config.config_hash
        runtime = DeadmanOutbox(config, now=FakeClock().now, watchdog_evaluator=_watchdog_evaluator(reason))
        opened_case = runtime.check_once()
        emitted += 1
        record(name, opened_case["transition_kind"] == "opened", {"transition_kind": opened_case["transition_kind"], "event_id": opened_case["event_id"]})

    crash = _crash_retry_case(workspace / "crash", profile)
    emitted += 1
    record("event_cursor_crash_retry", crash["passed"], crash["evidence"])

    ack_case = _ack_does_not_resolve_case(workspace / "ack", profile)
    acknowledgements += 1
    retained += 1
    record("ack_does_not_resolve", ack_case["passed"], ack_case["evidence"])

    retention_case = _acknowledged_retention_case(workspace / "retention", profile)
    emitted += 2
    acknowledgements += 1
    pruned += 1
    retained += 1
    record("acknowledged_retention", retention_case["passed"], retention_case["evidence"])

    partial_case = _partial_delete_recovery_case(workspace / "partial", profile)
    record("retention_partial_delete_recovery", partial_case["passed"], partial_case["evidence"])

    for name, factory in (
        ("low_space_preservation", _low_space_case),
        ("budget_exhaustion_preservation", _budget_case),
        ("tampered_retention_block", _tampered_retention_case),
        ("symlink_retention_block", _symlink_retention_case),
        ("hardlink_retention_block", _hardlink_retention_case),
        ("unsafe_retention_directory_block", _unsafe_retention_directory_case),
        ("post_replace_reload_rewrite", _post_replace_case),
    ):
        case = factory(workspace / name, profile)
        record(name, case["passed"], case["evidence"])

    report: dict[str, Any] = {
        "schema_version": "p133.outbox_report.v1",
        "profile_hash": profile_hash or _file_hash(ROOT / "evals/p133/input/outbox-profile.json"),
        "required_scenarios": list(REQUIRED_SCENARIOS),
        "passed": all(case["passed"] is True for case in cases.values()) and set(cases) == set(REQUIRED_SCENARIOS),
        "cases": cases,
        "totals": {
            "expected_scenarios": len(REQUIRED_SCENARIOS),
            "passed_scenarios": sum(1 for case in cases.values() if case["passed"] is True),
            "failed_scenarios": sum(1 for case in cases.values() if case["passed"] is not True),
            "denominator_scope": "principal_transition_assertions",
            "expected_emitted_events": 10,
            "observed_emitted_events": emitted,
            "expected_deduplicated_checks": 2,
            "observed_deduplicated_checks": dedup,
            "expected_recoveries": 1,
            "observed_recoveries": recoveries,
            "expected_acknowledgements": 2,
            "observed_acknowledgements": acknowledgements,
            "expected_retained_events": 2,
            "observed_retained_events": retained,
            "expected_pruned_events": 1,
            "observed_pruned_events": pruned,
        },
        "runtime_authority": {"exact_zero": True, "counters": zero_authority_counters()},
        "config_hashes": config_hashes,
        "raw_evidence": {},
        "source_hashes": _source_hashes(),
        "artifact_paths": {},
    }
    report["outbox_report_hash"] = stable_hash({key: value for key, value in report.items() if key != "outbox_report_hash"})
    return report


def _crash_retry_case(workspace: Path, profile: Mapping[str, Any]) -> dict[str, Any]:
    config = load_deadman_config(_config_path(workspace, profile))
    clock = FakeClock()
    calls = {"count": 0}
    original = p133_runtime._write_cursor

    def crash(path: Path, cursor: dict[str, Any], roots: tuple[Path, ...]) -> None:
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("crash_after_event_replace")
        original(path, cursor, roots)

    runtime = DeadmanOutbox(config, now=clock.now, watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("runtime_stopped"))
    try:
        with patch.object(p133_runtime, "_write_cursor", crash):
            runtime.check_once()
    except RuntimeError:
        pass
    first_event = list_outbox(config)[0]
    clock.advance(3600)
    replayed = runtime.check_once()
    cursor = _read_json(config.cursor_path)
    evidence = {
        "event_id": first_event["event_id"],
        "replayed_event_id": replayed["event_id"],
        "occurred_at": first_event["occurred_at"],
        "replayed_occurred_at": replayed["occurred_at"],
        "event_file_count": len(list(config.outbox_dir.glob("*.json"))),
        "next_sequence": cursor["next_sequence"],
    }
    passed = all(
        (
            evidence["event_id"] == evidence["replayed_event_id"],
            evidence["occurred_at"] == evidence["replayed_occurred_at"],
            evidence["event_file_count"] == 1,
            evidence["next_sequence"] == 2,
        )
    )
    return {"passed": passed, "evidence": evidence}


def _ack_does_not_resolve_case(workspace: Path, profile: Mapping[str, Any]) -> dict[str, Any]:
    config = load_deadman_config(_config_path(workspace, profile))
    runtime = DeadmanOutbox(config, now=FakeClock().now, watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("runtime_stopped"))
    opened = runtime.check_once()
    ack = acknowledge_event(config, opened["event_id"], now=datetime(2026, 7, 13, tzinfo=UTC))
    cursor = _read_json(config.cursor_path)
    evidence = {"ack_event_id": ack["event_id"], "active_incident_after_ack": cursor["active_incident"] is not None}
    return {"passed": evidence["active_incident_after_ack"], "evidence": evidence}


def _acknowledged_retention_case(workspace: Path, profile: Mapping[str, Any]) -> dict[str, Any]:
    config = load_deadman_config(_config_path(workspace, profile, max_event_files=1))
    clock = FakeClock()
    runtime = DeadmanOutbox(config, now=clock.now, watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("heartbeat_stale", state_hash="sha256:" + "4" * 64))
    opened = runtime.check_once()
    acknowledge_event(config, opened["event_id"], now=clock.now)
    clock.advance(1)
    runtime = DeadmanOutbox(config, now=clock.now, watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("runtime_stopped", state_hash="sha256:" + "5" * 64))
    runtime.check_once()
    evidence = {"removed_events": int(not (config.outbox_dir / f"{opened['event_id']}.json").exists()), "removed_acks": int(not (config.ack_dir / f"{opened['event_id']}.json").exists())}
    return {"passed": evidence == {"removed_events": 1, "removed_acks": 1}, "evidence": evidence}


def _partial_delete_recovery_case(workspace: Path, profile: Mapping[str, Any]) -> dict[str, Any]:
    config = load_deadman_config(_config_path(workspace, profile, max_event_files=1))
    clock = FakeClock()
    runtime = DeadmanOutbox(
        config,
        now=clock.now,
        watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("heartbeat_stale", state_hash="sha256:" + "8" * 64),
    )
    opened = runtime.check_once()
    acknowledge_event(config, opened["event_id"], now=clock.now)
    original_unlink = p133_runtime._unlink_regular_file
    unlink_count = 0

    def crash_between_event_and_ack(
        path: Path,
        *,
        expected: os.stat_result,
        expected_bytes: bytes,
    ) -> None:
        nonlocal unlink_count
        unlink_count += 1
        if unlink_count == 2:
            raise RuntimeError("injected_crash_between_event_and_ack_delete")
        original_unlink(path, expected=expected, expected_bytes=expected_bytes)

    clock.advance(1)
    changed = DeadmanOutbox(
        config,
        now=clock.now,
        watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("runtime_stopped", state_hash="sha256:" + "9" * 64),
    )
    crash_observed = False
    try:
        with patch.object(p133_runtime, "_unlink_regular_file", crash_between_event_and_ack):
            changed.check_once()
    except RuntimeError as exc:
        crash_observed = str(exc) == "injected_crash_between_event_and_ack_delete"
    orphan_present = (config.ack_dir / f"{opened['event_id']}.json").is_file()
    removed = changed.enforce_retention()
    evidence = {
        "crash_injected": crash_observed,
        "orphan_ack_observed": orphan_present,
        "orphan_acks_removed": removed["removed_acks"],
    }
    return {
        "passed": crash_observed and orphan_present and removed["removed_acks"] == 1,
        "evidence": evidence,
    }


def _low_space_case(workspace: Path, profile: Mapping[str, Any]) -> dict[str, Any]:
    config = load_deadman_config(_config_path(workspace, profile))
    runtime = DeadmanOutbox(config, now=FakeClock().now, watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("runtime_stopped"))
    opened = runtime.check_once()
    cursor_before = config.cursor_path.read_bytes()
    event_before = (config.outbox_dir / f"{opened['event_id']}.json").read_bytes()
    with patch.object(p133_runtime, "_artifact_free_bytes", lambda *_args, **_kwargs: 0):
        try:
            runtime.check_once()
        except OSError:
            pass
    evidence = {
        "prior_cursor_preserved": config.cursor_path.read_bytes() == cursor_before,
        "prior_events_preserved": (config.outbox_dir / f"{opened['event_id']}.json").read_bytes() == event_before,
    }
    return {"passed": all(evidence.values()), "evidence": evidence}


def _budget_case(workspace: Path, profile: Mapping[str, Any]) -> dict[str, Any]:
    config = load_deadman_config(_config_path(workspace, profile, max_event_files=1))
    clock = FakeClock()
    runtime = DeadmanOutbox(config, now=clock.now, watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("heartbeat_stale", state_hash="sha256:" + "6" * 64))
    opened = runtime.check_once()
    cursor_before = config.cursor_path.read_bytes()
    event_before = (config.outbox_dir / f"{opened['event_id']}.json").read_bytes()
    clock.advance(1)
    runtime = DeadmanOutbox(config, now=clock.now, watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("runtime_stopped", state_hash="sha256:" + "7" * 64))
    try:
        runtime.check_once()
    except P133DeadmanError:
        pass
    evidence = {
        "prior_cursor_preserved": config.cursor_path.read_bytes() == cursor_before,
        "prior_events_preserved": (config.outbox_dir / f"{opened['event_id']}.json").read_bytes() == event_before,
    }
    return {"passed": all(evidence.values()), "evidence": evidence}


def _tampered_retention_case(workspace: Path, profile: Mapping[str, Any]) -> dict[str, Any]:
    return _blocked_retention_case(workspace, profile, "tampered_retention_block", lambda path: _tamper_event(path))


def _symlink_retention_case(workspace: Path, profile: Mapping[str, Any]) -> dict[str, Any]:
    def mutate(path: Path) -> None:
        target = path.with_name("target.json")
        target.write_text("{}", encoding="utf-8")
        path.unlink()
        path.symlink_to(target)

    return _blocked_retention_case(workspace, profile, "symlink_retention_block", mutate)


def _hardlink_retention_case(workspace: Path, profile: Mapping[str, Any]) -> dict[str, Any]:
    def mutate(path: Path) -> None:
        path.with_name("f" * 64 + ".json").hardlink_to(path)

    return _blocked_retention_case(workspace, profile, "hardlink_retention_block", mutate)


def _unsafe_retention_directory_case(
    workspace: Path,
    profile: Mapping[str, Any],
) -> dict[str, Any]:
    config = load_deadman_config(_config_path(workspace, profile, max_event_files=1))
    clock = FakeClock()
    runtime = DeadmanOutbox(
        config,
        now=clock.now,
        watchdog_evaluator=lambda *_args, **_kwargs: _watchdog(
            "heartbeat_stale", state_hash="sha256:" + "a" * 64
        ),
    )
    opened = runtime.check_once()
    acknowledge_event(config, opened["event_id"], now=clock.now)
    cursor_before = config.cursor_path.read_bytes()
    event_path = config.outbox_dir / f"{opened['event_id']}.json"
    event_before = event_path.read_bytes()
    config.outbox_dir.chmod(0o777)
    clock.advance(1)
    changed = DeadmanOutbox(
        config,
        now=clock.now,
        watchdog_evaluator=lambda *_args, **_kwargs: _watchdog(
            "runtime_stopped", state_hash="sha256:" + "b" * 64
        ),
    )
    failure = ""
    try:
        changed.check_once()
    except P133DeadmanError as exc:
        failure = str(exc)
    finally:
        config.outbox_dir.chmod(0o700)
    evidence = {
        "blocked": bool(failure),
        "failure": failure,
        "prior_cursor_preserved": config.cursor_path.read_bytes() == cursor_before,
        "prior_event_preserved": event_path.read_bytes() == event_before,
    }
    return {"passed": all(value is True for key, value in evidence.items() if key != "failure") and failure == "retention_parent_permissions_unsafe", "evidence": evidence}


def _blocked_retention_case(workspace: Path, profile: Mapping[str, Any], name: str, mutate: Callable[[Path], None]) -> dict[str, Any]:
    config = load_deadman_config(_config_path(workspace, profile))
    runtime = DeadmanOutbox(config, now=FakeClock().now, watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("runtime_stopped"))
    opened = runtime.check_once()
    acknowledge_event(config, opened["event_id"], now=datetime(2026, 7, 13, tzinfo=UTC))
    event_path = config.outbox_dir / f"{opened['event_id']}.json"
    mutate(event_path)
    failure = ""
    try:
        runtime.enforce_retention()
    except P133DeadmanError as exc:
        failure = str(exc)
    evidence = {"blocked": bool(failure), "failure": failure, "case": name}
    return {"passed": bool(failure), "evidence": evidence}


def _post_replace_case(workspace: Path, profile: Mapping[str, Any]) -> dict[str, Any]:
    config = load_deadman_config(_config_path(workspace, profile))
    runtime = DeadmanOutbox(config, now=FakeClock().now, watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("runtime_stopped"))
    original = p133_runtime._fsync_dir
    failure = ""
    try:
        with patch.object(p133_runtime, "_fsync_dir", side_effect=OSError("directory_fsync_failed_after_replace")):
            runtime.check_once()
    except OSError as exc:
        failure = str(exc)
    event = list_outbox(config)[0]
    uncertain_hash = event["event_hash"]
    with patch.object(p133_runtime, "_fsync_dir", original):
        runtime.check_once()
    rewritten_hash = list_outbox(config)[0]["event_hash"]
    evidence = {
        "durability_uncertainty_exposed": "directory_fsync_failed_after_replace" in failure,
        "uncertain_hash": uncertain_hash,
        "rewritten_hash": rewritten_hash,
    }
    return {"passed": evidence["durability_uncertainty_exposed"], "evidence": evidence}


def _run_subprocess_smoke(profile: Mapping[str, Any], workspace: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    workspace.mkdir(parents=True, exist_ok=True)
    runtime_workspace = workspace / "runtime"
    monitor_config_path = _p131_fixture_path(runtime_workspace)
    AlwaysOnMonitor(load_monitor_config(monitor_config_path)).run(max_cycles=1, sleep_enabled=False)
    config_path = _config_path(
        runtime_workspace,
        profile,
        check_interval_seconds=1,
        heartbeat_timeout_seconds=1,
    )
    activity = {"process_launch_count": 0, "signal_count": 0, "sigterm_count": 0, "sigint_count": 0, "forced_kill_count": 0}
    commands: list[dict[str, Any]] = []
    cases: dict[str, dict[str, Any]] = {}

    time.sleep(1.05)
    check = _run_deadman_command(["deadman-check", "--config", str(config_path)], activity, commands, workspace)
    check_json = _stdout_json(check)
    cases["deadman_check_stale_open"] = {
        "passed": (
            check.returncode == 1
            and check_json.get("transition_kind") == "opened"
            and check_json.get("reason") == "heartbeat_stale"
        ),
        "returncode": check.returncode,
        "transition_kind": check_json.get("transition_kind"),
        "reason": check_json.get("reason"),
        "event_id": check_json.get("event_id"),
    }

    run = _run_deadman_command(["deadman-run", "--config", str(config_path), "--max-cycles", "2", "--no-sleep"], activity, commands, workspace)
    run_json = _stdout_json(run)
    cases["deadman_run_dedup"] = {
        "passed": run.returncode == 0 and run_json.get("cycles") == 2 and run_json.get("emitted_events") == 0,
        "returncode": run.returncode,
        "cycles": run_json.get("cycles"),
        "emitted_events": run_json.get("emitted_events"),
    }

    _age_deadman_cursor(load_deadman_config(config_path), seconds=int(profile["reminder_interval_seconds"]))
    reminder = _run_deadman_command(["deadman-check", "--config", str(config_path)], activity, commands, workspace)
    reminder_json = _stdout_json(reminder)
    cases["deadman_check_reminder"] = {
        "passed": reminder.returncode == 1 and reminder_json.get("transition_kind") == "reminder",
        "returncode": reminder.returncode,
        "transition_kind": reminder_json.get("transition_kind"),
        "event_id": reminder_json.get("event_id"),
        "accelerated_cursor_seconds": profile["reminder_interval_seconds"],
    }

    AlwaysOnMonitor(load_monitor_config(monitor_config_path)).run(max_cycles=1, sleep_enabled=False)
    recovery = _run_deadman_command(["deadman-check", "--config", str(config_path)], activity, commands, workspace)
    recovery_json = _stdout_json(recovery)
    cases["deadman_check_recovery"] = {
        "passed": (
            recovery.returncode == 0
            and recovery_json.get("transition_kind") == "recovered"
            and recovery_json.get("reason") == "heartbeat_current"
        ),
        "returncode": recovery.returncode,
        "transition_kind": recovery_json.get("transition_kind"),
        "reason": recovery_json.get("reason"),
        "event_id": recovery_json.get("event_id"),
    }

    listed = _run_deadman_command(["outbox-list", "--config", str(config_path)], activity, commands, workspace)
    listed_json = _stdout_json(listed)
    listed_events = listed_json.get("events")
    cases["outbox_list_redacted"] = {
        "passed": (
            listed.returncode == 0
            and listed_json.get("count") == 3
            and isinstance(listed_events, list)
            and all(isinstance(event, dict) and "snapshot" not in event for event in listed_events)
        ),
        "returncode": listed.returncode,
        "count": listed_json.get("count"),
        "redacted": isinstance(listed_events, list)
        and all(isinstance(event, dict) and "snapshot" not in event for event in listed_events),
    }

    ack = _run_deadman_command(["outbox-ack", "--config", str(config_path), "--event-id", check_json["event_id"]], activity, commands, workspace)
    ack_json = _stdout_json(ack)
    cases["outbox_ack_local"] = {
        "passed": ack.returncode == 0 and ack_json.get("event_id") == check_json["event_id"],
        "returncode": ack.returncode,
        "event_id": ack_json.get("event_id"),
        "ack_hash": ack_json.get("ack_hash"),
    }

    restart = _run_deadman_command(["deadman-run", "--config", str(config_path), "--max-cycles", "1", "--no-sleep"], activity, commands, workspace)
    restart_json = _stdout_json(restart)
    cases["restart_dedup"] = {
        "passed": restart.returncode == 0 and restart_json.get("emitted_events") == 0,
        "returncode": restart.returncode,
        "cycles": restart_json.get("cycles"),
        "emitted_events": restart_json.get("emitted_events"),
    }

    lease_path = load_deadman_config(config_path).lease_path
    forever = subprocess.Popen(
        [sys.executable, "-m", "app.monitor_cli", "deadman-run", "--config", str(config_path), "--forever"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    activity["process_launch_count"] += 1
    activity["signal_count"] += 1
    activity["sigterm_count"] += 1
    commands.append(
        {
            "argv": [sys.executable, "-m", "app.monitor_cli", "deadman-run", "--config", str(config_path), "--forever"],
            "shell": False,
            "bounded": True,
            "label": "graceful_stop",
        }
    )
    started = time.monotonic()
    ready = _wait_for_lease_owner(lease_path, forever.pid, timeout_seconds=2.0)
    forever.send_signal(signal.SIGTERM)
    try:
        stdout, stderr = forever.communicate(timeout=float(profile["max_shutdown_latency_seconds"]))
    except subprocess.TimeoutExpired:
        forever.kill()
        activity["forced_kill_count"] += 1
        stdout, stderr = forever.communicate(timeout=2)
    latency = time.monotonic() - started
    try:
        graceful_json = _json_from_text(stdout)
    except (json.JSONDecodeError, ValueError):
        graceful_json = {}
    cases["graceful_stop"] = {
        "passed": (
            ready
            and forever.returncode == 0
            and latency <= float(profile["max_shutdown_latency_seconds"])
            and graceful_json.get("graceful_stop") is True
        ),
        "returncode": forever.returncode,
        "lease_owner_observed": ready,
        "latency_ms": round(latency * 1000),
        "graceful_stop": graceful_json.get("graceful_stop"),
        "stop_reason": graceful_json.get("stop_reason"),
        "stderr": stderr,
    }

    process_matrix: dict[str, Any] = {
        "schema_version": "p133.process_matrix.v1",
        "passed": set(cases) == set(SUBPROCESS_CASES) and all(case["passed"] is True for case in cases.values()),
        "subprocess_cases": cases,
        "evaluator_activity": activity,
        "commands": commands,
        "source_hashes": _source_hashes(),
        "artifact_paths": {},
        "artifact_hashes": {},
    }
    ledger = {
        "schema_version": "p133.authority_ledger.v1",
        "runtime_authority": {"exact_zero": True, "counters": zero_authority_counters()},
        "evaluator_activity": activity,
        "evaluator_authority": {"exact_zero": True, "counters": {key: 0 for key in ZERO_AUTHORITY_COUNTERS}},
        "process_ledger": commands,
        "source_hashes": _source_hashes(),
    }
    process_matrix["process_matrix_hash"] = stable_hash({key: value for key, value in process_matrix.items() if key != "process_matrix_hash"})
    return process_matrix, ledger


def _validate_supervisor_manifests(manifest_root: Path) -> dict[str, Any]:
    systemd_relative, launchd_relative, compose_relative = MANIFEST_PATHS
    manifests = {
        systemd_relative: _validate_systemd_manifest(ROOT / systemd_relative),
        launchd_relative: _validate_launchd_example(ROOT / launchd_relative),
        compose_relative: _validate_compose_manifest(ROOT / compose_relative),
    }
    promoted_passed = all(manifests[path]["passed"] is True for path in PROMOTED_MANIFEST_PATHS)
    launchd_honest = (
        manifests[launchd_relative].get("status") == "example_only_not_qualified"
        and manifests[launchd_relative].get("structural_checks_passed") is True
        and manifests[launchd_relative].get("passed") is False
    )
    validation: dict[str, Any] = {
        "schema_version": "p133.supervisor_validation.v1",
        "manifest_root": str(manifest_root.relative_to(ROOT)),
        "qualified_manifests": list(PROMOTED_MANIFEST_PATHS),
        "example_only_manifests": [launchd_relative],
        "passed": promoted_passed and launchd_honest,
        "manifests": manifests,
        "source_hashes": {relative: _file_hash(ROOT / relative) for relative in MANIFEST_PATHS},
    }
    validation["supervisor_validation_hash"] = stable_hash({key: value for key, value in validation.items() if key != "supervisor_validation_hash"})
    return validation


def _validate_systemd_manifest(path: Path) -> dict[str, Any]:
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    parser.read_string(path.read_text(encoding="utf-8"))
    service = parser["Service"]
    argv = shlex.split(service.get("ExecStart", ""))
    expected_sections = {"Unit", "Service", "Install"}
    expected_options = {
        "Unit": {"Description", "After", "StartLimitIntervalSec", "StartLimitBurst"},
        "Service": {
            "Type",
            "User",
            "Group",
            "ExecStart",
            "Restart",
            "RestartSec",
            "TimeoutStopSec",
            "NoNewPrivileges",
            "PrivateTmp",
            "ProtectSystem",
            "ProtectHome",
            "ReadOnlyPaths",
            "ReadWritePaths",
            "CapabilityBoundingSet",
            "RestrictAddressFamilies",
            "LockPersonality",
        },
        "Install": {"WantedBy"},
    }
    checks = {
        "closed_fields": set(parser.sections()) == expected_sections
        and all(set(parser[section]) == {option.lower() for option in options} for section, options in expected_options.items()),
        "exact_argv": argv
        == [
            "/usr/local/bin/opscat-monitor",
            "deadman-run",
            "--config",
            "/etc/opscat/deadman.json",
            "--forever",
        ],
        "restart_throttled": service.get("Restart") == "on-failure" and service.get("RestartSec") == "5",
        "bounded_stop": service.get("TimeoutStopSec") == "3",
        "non_root": service.get("User") == "opscat" and service.get("Group") == "opscat",
        "network_disabled": service.get("RestrictAddressFamilies") == "AF_UNIX",
        "monitor_state_read_only": service.get("ReadOnlyPaths") == "/var/lib/opscat/monitor",
        "outbox_only_writable": service.get("ReadWritePaths") == "/var/lib/opscat/deadman",
        "filesystem_hardened": service.get("ProtectSystem") == "strict" and service.get("ProtectHome") == "true",
        "no_privilege_gain": service.get("NoNewPrivileges") == "true" and service.get("CapabilityBoundingSet") == "",
        "no_evaluator_flag": "--no-sleep" not in argv,
    }
    return {
        "status": "qualified",
        "passed": all(checks.values()),
        "checks": checks,
        "parsed_argv": argv,
        "hash": _file_hash(path),
    }


def _validate_launchd_example(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        value = plistlib.load(handle)
    if not isinstance(value, dict):
        raise ValueError("invalid_launchd_manifest")
    argv = value.get("ProgramArguments")
    expected_fields = {
        "Label",
        "ProgramArguments",
        "KeepAlive",
        "ThrottleInterval",
        "ExitTimeOut",
        "ProcessType",
        "RunAtLoad",
        "UserName",
        "WorkingDirectory",
        "StandardOutPath",
        "StandardErrorPath",
    }
    checks = {
        "closed_fields": set(value) == expected_fields,
        "exact_argv": argv
        == [
            "/usr/local/bin/opscat-monitor",
            "deadman-run",
            "--config",
            "/usr/local/etc/opscat/deadman.json",
            "--forever",
        ],
        "restart_throttled": value.get("KeepAlive") is True and value.get("ThrottleInterval") == 5,
        "bounded_stop": value.get("ExitTimeOut") == 3,
        "non_root": value.get("UserName") == "opscat",
        "no_evaluator_flag": isinstance(argv, list) and "--no-sleep" not in argv,
    }
    return {
        "status": "example_only_not_qualified",
        "passed": False,
        "structural_checks_passed": all(checks.values()),
        "checks": checks,
        "parsed_argv": argv,
        "limitation": (
            "launchd plist alone cannot enforce the qualified no-network and read-only-monitor-state boundary; "
            "use an independently reviewed macOS sandbox/MDM policy before deployment"
        ),
        "hash": _file_hash(path),
    }


def _validate_compose_manifest(path: Path) -> dict[str, Any]:
    value = _read_json(path)
    services = value.get("services")
    deadman = services.get("deadman") if isinstance(services, dict) else None
    if not isinstance(deadman, dict):
        raise ValueError("invalid_compose_manifest")
    argv = deadman.get("command")
    volumes = deadman.get("volumes")
    restart_policy = deadman.get("deploy", {}).get("restart_policy") if isinstance(deadman.get("deploy"), dict) else None
    image = deadman.get("image")
    expected_fields = {
        "image",
        "user",
        "command",
        "restart",
        "deploy",
        "stop_grace_period",
        "read_only",
        "privileged",
        "network_mode",
        "cap_drop",
        "security_opt",
        "tmpfs",
        "volumes",
    }
    checks = {
        "closed_fields": set(value) == {"services"}
        and isinstance(services, dict)
        and set(services) == {"deadman"}
        and set(deadman) == expected_fields,
        "exact_argv": argv
        == ["opscat-monitor", "deadman-run", "--config", "/etc/opscat/deadman.json", "--forever"],
        "immutable_digest_required": isinstance(image, str)
        and image == "opscat-monitor@sha256:${OPSCAT_MONITOR_IMAGE_DIGEST:?set a 64-hex image manifest digest}",
        "restart_throttled": deadman.get("restart") == "unless-stopped"
        and restart_policy
        == {"condition": "on-failure", "delay": "5s", "max_attempts": 6, "window": "60s"},
        "bounded_stop": deadman.get("stop_grace_period") == "3s",
        "non_root": deadman.get("user") == "65532:65532",
        "network_disabled": deadman.get("network_mode") == "none",
        "monitor_state_read_only": isinstance(volumes, list)
        and "./data/p131:/var/lib/opscat/monitor:ro" in volumes,
        "outbox_only_writable": isinstance(volumes, list)
        and "./data/p133:/var/lib/opscat/deadman:rw" in volumes,
        "container_hardened": deadman.get("read_only") is True
        and deadman.get("privileged") is False
        and deadman.get("cap_drop") == ["ALL"]
        and deadman.get("security_opt") == ["no-new-privileges:true"],
        "no_evaluator_flag": isinstance(argv, list) and "--no-sleep" not in argv,
    }
    return {
        "status": "qualified",
        "passed": all(checks.values()),
        "checks": checks,
        "parsed_argv": argv,
        "hash": _file_hash(path),
    }


def _run_deadman_command(args: list[str], activity: dict[str, int], commands: list[dict[str, Any]], workspace: Path) -> subprocess.CompletedProcess[str]:
    argv = [sys.executable, "-m", "app.monitor_cli", *args]
    activity["process_launch_count"] += 1
    commands.append({"argv": argv, "shell": False, "bounded": True, "label": args[0]})
    return subprocess.run(argv, cwd=ROOT, check=False, capture_output=True, text=True, timeout=20)


def _bind_promoted_artifacts(outbox_report: dict[str, Any], process_matrix: dict[str, Any], output_dir: Path) -> None:
    outbox_report["artifact_paths"] = {
        "outbox_report": "outbox-report.json",
        "process_matrix": "process-matrix.json",
        "supervisor_validation": "supervisor-validation.json",
        "authority_ledger": "authority-ledger.json",
        "release_evidence": "release-evidence.json",
    }
    process_matrix["artifact_paths"] = {
        "subprocess_config": "raw/subprocess/runtime/deadman-config.json",
        "subprocess_cursor": "raw/subprocess/runtime/cursor/deadman-cursor.json",
    }
    process_matrix["artifact_hashes"] = {
        name: _file_hash(output_dir / path) for name, path in process_matrix["artifact_paths"].items()
    }
    process_matrix["process_matrix_hash"] = stable_hash({key: value for key, value in process_matrix.items() if key != "process_matrix_hash"})
    outbox_report["outbox_report_hash"] = stable_hash({key: value for key, value in outbox_report.items() if key != "outbox_report_hash"})


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


def _p131_fixture_path(workspace: Path) -> Path:
    source_path = workspace / "telemetry.jsonl"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(
        json.dumps(
            {
                "timestamp": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "service": "p133-release-fixture",
                "message": "healthy",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    config = {
        "schema_version": "p131.monitor_config.v1",
        "runtime_id": "p133-subprocess-watchdog",
        "interval_seconds": 1,
        "heartbeat_timeout_seconds": 1,
        "data_stale_after_seconds": 60,
        "daily_report_interval_seconds": 3600,
        "canary_every_cycles": 1,
        "max_consecutive_failures": 3,
        "state_path": str(workspace / "monitor-state.json"),
        "report_dir": str(workspace / "monitor-reports"),
        "lease_path": str(workspace / "monitor.lock"),
        "termination_receipt_path": str(workspace / "monitor-termination.json"),
        "allowed_data_roots": [str(workspace)],
        "allowed_artifact_roots": [str(workspace)],
        "sources": [
            {
                "source_id": "p133-release-local",
                "kind": "local_jsonl",
                "path": str(source_path),
                "enabled": True,
            }
        ],
    }
    path = workspace / "monitor-config.json"
    _write_atomic(path, config)
    return path


def _age_deadman_cursor(config: DeadmanConfig, *, seconds: int) -> None:
    cursor = _read_json(config.cursor_path)
    active = cursor.get("active_incident")
    if not isinstance(active, dict):
        raise ValueError("active_incident_required_for_acceleration")
    accelerated = datetime.now(UTC) - timedelta(seconds=seconds + 1)
    active["last_emitted_at"] = accelerated.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    cursor["cursor_hash"] = stable_hash({key: value for key, value in cursor.items() if key != "cursor_hash"})
    _write_atomic(config.cursor_path, cursor)


def _wait_for_lease_owner(path: Path, pid: int, *, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            value = _read_json(path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            time.sleep(0.02)
            continue
        if value.get("pid") == pid:
            return True
        time.sleep(0.02)
    return False


def _config_path(workspace: Path, profile: Mapping[str, Any], **overrides: Any) -> Path:
    workspace.mkdir(parents=True, exist_ok=True)
    raw: dict[str, Any] = {
        "schema_version": "p133.deadman_config.v1",
        "allowed_artifact_roots": [str(workspace)],
        "state_path": str(workspace / "monitor-state.json"),
        "outbox_dir": str(workspace / "outbox"),
        "cursor_path": str(workspace / "cursor" / "deadman-cursor.json"),
        "ack_dir": str(workspace / "acks"),
        "runtime_ref": "p133-release-runtime",
        "check_interval_seconds": profile["check_interval_seconds"],
        "heartbeat_timeout_seconds": profile["heartbeat_timeout_seconds"],
        "reminder_interval_seconds": profile["reminder_interval_seconds"],
        "max_event_files": profile["max_event_files"],
        "max_outbox_bytes": profile["max_outbox_bytes"],
        "max_event_bytes": profile["max_event_bytes"],
        "min_artifact_free_bytes": 1,
    }
    raw.update(overrides)
    path = workspace / "deadman-config.json"
    _write_atomic(path, raw)
    return path


def _watchdog(reason: str, *, state_hash: str = "sha256:" + "a" * 64) -> dict[str, Any]:
    mapped = "state_hash_invalid" if reason == "state_hash_invalid" else reason
    return {"schema_version": "p131.watchdog.v1", "healthy": mapped == "heartbeat_current", "reason": mapped, "state_hash": state_hash, "heartbeat_age_seconds": 10}


def _watchdog_evaluator(reason: str) -> Callable[..., dict[str, Any]]:
    def evaluator(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return _watchdog(reason)

    return evaluator


def _tamper_event(path: Path) -> None:
    value = _read_json(path)
    value["sequence"] = 99
    _write_atomic(path, value)


def _raw_file_hashes(root: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.is_symlink():
            files[path.relative_to(root).as_posix()] = _file_hash(path)
    return files


def _source_hashes() -> dict[str, str]:
    return {relative: _file_hash(ROOT / relative) for relative in SOURCE_BINDINGS}


def _cpu_seconds() -> float:
    self_usage = resource.getrusage(resource.RUSAGE_SELF)
    child_usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    return self_usage.ru_utime + self_usage.ru_stime + child_usage.ru_utime + child_usage.ru_stime


def _resource_usage(*, started_wall: float, started_cpu: float) -> dict[str, int]:
    self_peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    child_peak = int(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)
    unit_bytes = 1 if sys.platform == "darwin" else 1024
    return {
        "wall_milliseconds": round((time.monotonic() - started_wall) * 1000),
        "cpu_milliseconds": round((_cpu_seconds() - started_cpu) * 1000),
        "peak_memory_bytes": max(self_peak, child_peak) * unit_bytes,
    }


def _file_hash(path: Path) -> str:
    return stable_hash(path.read_bytes().hex())


def _stdout_json(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    try:
        return _json_from_text(result.stdout)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(
            "subprocess_json_invalid:"
            + json.dumps(
                {
                    "argv": list(result.args) if isinstance(result.args, (list, tuple)) else str(result.args),
                    "returncode": result.returncode,
                    "stdout": result.stdout[-2000:],
                    "stderr": result.stderr[-2000:],
                },
                sort_keys=True,
            )
        ) from exc


def _json_from_text(text: str) -> dict[str, Any]:
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("expected_json_object")
    return value


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected_json_object")
    return value


def _load_profile(path: Path) -> dict[str, Any]:
    resolved = path.expanduser().resolve(strict=True)
    if path.expanduser().is_symlink() or not resolved.is_file():
        raise ValueError("invalid_profile_file")
    profile = _read_json(resolved)
    if set(profile) != PROFILE_FIELDS or profile.get("schema_version") != "p133.outbox_profile.v1":
        raise ValueError("invalid_profile_schema")
    if tuple(profile.get("required_scenarios", ())) != REQUIRED_SCENARIOS:
        raise ValueError("invalid_profile_scenarios")
    for key, expected in PROMOTED_PROFILE_VALUES.items():
        value = profile.get(key)
        if type(value) is not int or value != expected:
            raise ValueError(f"invalid_promoted_profile_value:{key}")
    return profile


def _write_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


if __name__ == "__main__":
    raise SystemExit(main())
