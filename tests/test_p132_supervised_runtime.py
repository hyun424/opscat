from __future__ import annotations

import errno
import json
import os
import shutil
import stat
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

import app.services.p131_always_on_monitor as p131_runtime
from app.services.p110_evaluation import stable_hash
from app.services.p131_always_on_monitor import (
    AlwaysOnMonitor,
    P131DurabilityUncertainError,
    P131StateError,
    evaluate_watchdog,
    load_monitor_config,
    load_monitor_state,
    monitor_status_snapshot,
)
from app.services.p132_supervised_runtime import (
    load_endurance_profile,
    restart_attempt_after_window,
    restart_backoff_seconds,
    run_endurance_qualification,
    validate_supervisor_manifests,
)
from scripts.run_p132_supervised_runtime import _validate_command


class FakeClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 7, 13, tzinfo=UTC)

    def now(self) -> datetime:
        return self.current

    def sleep(self, seconds: float) -> None:
        self.current += timedelta(seconds=seconds)

    def monotonic(self) -> float:
        return self.current.timestamp()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def _config(tmp_path: Path, *, max_report_files: int = 8, report_interval: int = 10) -> Path:
    source = tmp_path / "telemetry.jsonl"
    _append_jsonl(source, {"event_id": "event-0", "service": "checkout", "message": "ok"})
    path = tmp_path / "monitor.json"
    _write_json(
        path,
        {
            "schema_version": "p131.monitor_config.v1",
            "runtime_id": "p132-test-runtime",
            "interval_seconds": 1,
            "heartbeat_timeout_seconds": 3,
            "data_stale_after_seconds": 30,
            "daily_report_interval_seconds": report_interval,
            "canary_every_cycles": 1,
            "max_consecutive_failures": 3,
            "max_bytes_per_cycle": 65536,
            "max_records_per_cycle": 10,
            "max_line_bytes": 4096,
            "max_report_files": max_report_files,
            "max_report_dir_bytes": 1048576,
            "min_artifact_free_bytes": 1,
            "state_path": str(tmp_path / "state.json"),
            "report_dir": str(tmp_path / "reports"),
            "lease_path": str(tmp_path / "runtime.lock"),
            "termination_receipt_path": str(tmp_path / "termination-receipt.json"),
            "allowed_data_roots": [str(tmp_path)],
            "allowed_artifact_roots": [str(tmp_path)],
            "sources": [{"source_id": "local", "kind": "local_jsonl", "path": str(source), "enabled": True}],
        },
    )
    return path


def test_graceful_stop_persists_bound_receipt_and_immediately_fails_liveness(tmp_path: Path) -> None:
    clock = FakeClock()
    requested = False

    def stop_reason() -> str | None:
        return "sigterm" if requested else None

    def wait_for_stop(_: float) -> bool:
        nonlocal requested
        requested = True
        return True

    config = load_monitor_config(_config(tmp_path))
    report = AlwaysOnMonitor(config, clock=clock).run(
        sleep_enabled=True,
        stop_reason=stop_reason,
        wait_for_stop=wait_for_stop,
    )
    state = load_monitor_state(config.state_path, allowed_roots=config.allowed_artifact_roots)
    receipt = json.loads(config.termination_receipt_path.read_text(encoding="utf-8"))

    assert report["summary"]["graceful_stop"] is True
    assert state["status"] == "stopped"
    assert state["lifecycle"]["phase"] == "stopped"
    assert state["lifecycle"]["last_stop_reason"] == "sigterm"
    assert state["lifecycle"]["graceful_stop_count"] == 1
    assert receipt["schema_version"] == "p132.termination_receipt.v1"
    assert receipt["final_state_hash"] == state["state_hash"]
    assert receipt["receipt_hash"] == stable_hash({key: value for key, value in receipt.items() if key != "receipt_hash"})
    watchdog = evaluate_watchdog(config.state_path, now=clock.now(), heartbeat_timeout_seconds=3)
    status = monitor_status_snapshot(config.state_path, now=clock.now())
    assert watchdog["healthy"] is False and watchdog["reason"] == "runtime_stopped"
    assert status["live"] is False and status["reasons"] == ["runtime_stopped"]

    restarted = AlwaysOnMonitor(config, clock=clock).run(max_cycles=1, sleep_enabled=False)
    resumed = load_monitor_state(config.state_path, allowed_roots=config.allowed_artifact_roots)
    assert restarted["summary"]["live"] is True
    assert resumed["lifecycle"]["phase"] == "running"
    assert resumed["lifecycle"]["last_stop_reason"] == "sigterm"
    assert resumed["lifecycle"]["graceful_stop_count"] == 1


def test_report_retention_is_bounded_and_rejects_unowned_candidate(tmp_path: Path) -> None:
    clock = FakeClock()
    config = load_monitor_config(_config(tmp_path, max_report_files=2, report_interval=1))
    AlwaysOnMonitor(config, clock=clock).run(max_cycles=5, sleep_enabled=True)
    reports = sorted(config.report_dir.glob("p131-health-*.json"))
    assert len(reports) == 2
    for report_path in reports:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["runtime_id"] == config.runtime_id
        assert report["config_hash"] == config.config_hash
        assert report["report_hash"] == stable_hash({key: value for key, value in report.items() if key != "report_hash"})

    bad = config.report_dir / "p131-health-20260713T235959Z.json"
    _write_json(bad, {"schema_version": "p131.health_report.v1", "runtime_id": "foreign"})
    before = bad.read_bytes()
    with pytest.raises(P131StateError, match="report_retention_candidate_invalid"):
        AlwaysOnMonitor(config, clock=clock).run(max_cycles=1, sleep_enabled=False)
    assert bad.read_bytes() == before


def test_report_retention_revalidates_identity_immediately_before_delete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = FakeClock()
    config = load_monitor_config(_config(tmp_path, max_report_files=2, report_interval=1))
    monitor = AlwaysOnMonitor(config, clock=clock)
    monitor.run(max_cycles=2, sleep_enabled=True)
    reports = sorted(config.report_dir.glob("p131-health-*.json"))
    assert len(reports) == 2
    oldest = reports[0]
    clock.sleep(1)

    original = AlwaysOnMonitor._validated_report_candidate
    validations: dict[str, int] = {}

    def changed_identity(self: AlwaysOnMonitor, parent_fd: int, name: str) -> tuple[int, int, int]:
        identity = original(self, parent_fd, name)
        validations[name] = validations.get(name, 0) + 1
        if name == oldest.name and validations[name] == 2:
            return identity[0], identity[1], identity[2] + 1
        return identity

    monkeypatch.setattr(AlwaysOnMonitor, "_validated_report_candidate", changed_identity)
    with pytest.raises(P131StateError, match="report_retention_candidate_changed"):
        monitor.run(max_cycles=1, sleep_enabled=False)
    assert oldest.exists()


def test_report_retention_rejects_group_or_world_writable_directory(tmp_path: Path) -> None:
    clock = FakeClock()
    config = load_monitor_config(_config(tmp_path, max_report_files=1, report_interval=1))
    monitor = AlwaysOnMonitor(config, clock=clock)
    monitor.run(max_cycles=2, sleep_enabled=True)
    retained = sorted(config.report_dir.glob("p131-health-*.json"))
    assert len(retained) == 1
    config.report_dir.chmod(0o777)

    with pytest.raises(P131StateError, match="report_retention_directory_permissions_unsafe"):
        monitor.run(max_cycles=1, sleep_enabled=False)
    assert retained[0].exists()


def test_low_space_preserves_prior_checkpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = load_monitor_config(_config(tmp_path))
    AlwaysOnMonitor(config, clock=FakeClock()).run(max_cycles=1, sleep_enabled=False)
    before = config.state_path.read_bytes()
    monkeypatch.setattr(p131_runtime, "_artifact_free_bytes", lambda *_: 0)

    with pytest.raises(OSError, match="artifact_free_space_below_floor"):
        AlwaysOnMonitor(config, clock=FakeClock()).run(max_cycles=1, sleep_enabled=False)

    assert config.state_path.read_bytes() == before
    load_monitor_state(config.state_path, allowed_roots=config.allowed_artifact_roots)


def test_atomic_write_distinguishes_pre_replace_and_post_replace_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "state.json"
    _write_json(target, {"generation": "old"})
    before = target.read_bytes()
    original_replace = os.replace

    def fail_replace(*args: object, **kwargs: object) -> None:
        raise OSError(errno.ENOSPC, "replace failed")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        p131_runtime._atomic_write_json(target, {"generation": "new"})
    assert target.read_bytes() == before

    monkeypatch.setattr(os, "replace", original_replace)
    original_fsync = os.fsync

    def fail_directory_fsync(fd: int) -> None:
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError(errno.ENOSPC, "directory fsync failed")
        original_fsync(fd)

    monkeypatch.setattr(os, "fsync", fail_directory_fsync)
    with pytest.raises(P131DurabilityUncertainError, match="directory_fsync_failed_after_replace"):
        p131_runtime._atomic_write_json(target, {"generation": "new"})
    assert json.loads(target.read_text(encoding="utf-8"))["generation"] == "new"

    monkeypatch.setattr(os, "fsync", original_fsync)
    p131_runtime._atomic_write_json(target, {"generation": "recovered"})
    assert json.loads(target.read_text(encoding="utf-8"))["generation"] == "recovered"


def test_promoted_profile_backoff_and_supervisor_manifests_are_exact(tmp_path: Path) -> None:
    profile = load_endurance_profile(Path("evals/p132/input/endurance-profile.json"))
    delays = [
        restart_backoff_seconds(attempt, base_seconds=profile["backoff_base_seconds"], cap_seconds=profile["backoff_cap_seconds"])
        for attempt in range(1, profile["backoff_attempts"] + 1)
    ]
    assert delays == profile["expected_backoff_seconds"]
    assert restart_attempt_after_window(6, runtime_seconds=59, stable_window_seconds=60) == 7
    assert restart_attempt_after_window(6, runtime_seconds=60, stable_window_seconds=60) == 0

    validation = validate_supervisor_manifests(Path("deploy/p132"), project_root=Path.cwd())
    assert validation["schema_version"] == "p132.supervisor_validation.v1"
    assert validation["passed"] is True
    assert all(validation["manifests"].values())
    assert validation["console_entrypoint"] == "app.monitor_cli:main"


@pytest.mark.parametrize("mutation", ("mutable_image", "missing_stop_grace", "missing_restart_throttle"))
def test_compose_manifest_rejects_mutable_or_incomplete_supervision(tmp_path: Path, mutation: str) -> None:
    manifest_dir = tmp_path / "deploy/p132"
    shutil.copytree("deploy/p132", manifest_dir)
    shutil.copy("pyproject.toml", tmp_path / "pyproject.toml")
    compose_path = manifest_dir / "compose.monitor.yaml"
    compose = json.loads(compose_path.read_text(encoding="utf-8"))
    service = compose["services"]["opscat-monitor"]
    if mutation == "mutable_image":
        service["image"] = "opscat-monitor:0.2.0"
    elif mutation == "missing_stop_grace":
        service.pop("stop_grace_period")
    else:
        service.pop("deploy", None)
    _write_json(compose_path, compose)

    validation = validate_supervisor_manifests(manifest_dir, project_root=tmp_path)
    assert validation["passed"] is False
    assert validation["manifests"]["compose"] is False


def test_systemd_manifest_rejects_service_scoped_start_limits(tmp_path: Path) -> None:
    manifest_dir = tmp_path / "deploy/p132"
    shutil.copytree("deploy/p132", manifest_dir)
    shutil.copy("pyproject.toml", tmp_path / "pyproject.toml")
    unit_path = manifest_dir / "opscat-monitor.service"
    text = unit_path.read_text(encoding="utf-8")
    throttle = "StartLimitIntervalSec=60\nStartLimitBurst=6\n"
    text = text.replace(throttle, "").replace("[Service]\n", f"[Service]\n{throttle}")
    unit_path.write_text(text, encoding="utf-8")

    validation = validate_supervisor_manifests(manifest_dir, project_root=tmp_path)
    assert validation["passed"] is False
    assert validation["manifests"]["systemd"] is False


def test_accelerated_endurance_meets_exact_local_resource_profile(tmp_path: Path) -> None:
    profile = load_endurance_profile(Path("evals/p132/input/endurance-profile.json"))
    report = run_endurance_qualification(profile, workspace=tmp_path)

    assert report["schema_version"] == "p132.endurance_report.v1"
    assert report["accounting"] == {
        "expected": 1000,
        "accepted": 1000,
        "invalid": 0,
        "duplicated": 0,
        "lost": 0,
    }
    assert report["cycle_count"] == 1000
    assert report["resource_gates"]["passed"] is True
    assert report["retained_report_count"] <= 8
    assert report["runtime_authority"]["exact_zero"] is True
    assert all(type(value) is int and value == 0 for value in report["runtime_authority"]["counters"].values())
    assert report["endurance_report_hash"] == stable_hash({key: value for key, value in report.items() if key != "endurance_report_hash"})


def test_evaluator_command_allowlist_rejects_trailing_flags_and_paths_outside_workspace(tmp_path: Path) -> None:
    config = tmp_path / "monitor.json"
    state = tmp_path / "state.json"
    executable = os.fspath(Path(sys.executable))
    _validate_command(
        [executable, "-m", "app.monitor_cli", "run", "--config", str(config), "--forever"],
        workspace=tmp_path,
    )
    _validate_command(
        [executable, "-m", "app.monitor_cli", "watchdog", "--state", str(state), "--timeout-seconds", "1"],
        workspace=tmp_path,
    )
    with pytest.raises(ValueError, match="evaluator_command_not_allowlisted"):
        _validate_command(
            [executable, "-m", "app.monitor_cli", "run", "--config", str(config), "--forever", "--extra"],
            workspace=tmp_path,
        )
    with pytest.raises(ValueError, match="evaluator_command_path_outside_workspace"):
        _validate_command(
            [executable, "-m", "app.monitor_cli", "watchdog", "--state", str(tmp_path.parent / "foreign.json"), "--timeout-seconds", "1"],
            workspace=tmp_path,
        )
