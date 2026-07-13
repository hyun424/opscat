from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

import app.services.p131_always_on_monitor as p131_runtime
from app.services.p110_evaluation import stable_hash
from app.services.p121_signals import P121_AUTHORITY_COUNTER_KEYS
from app.services.p131_always_on_monitor import (
    AlwaysOnMonitor,
    P131ConfigError,
    P131LeaseError,
    evaluate_watchdog,
    load_monitor_config,
    load_monitor_state,
    monitor_status_snapshot,
)


class FakeClock:
    def __init__(self, start: datetime) -> None:
        self.current = start
        self.sleeps: list[float] = []

    def now(self) -> datetime:
        return self.current

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.current += timedelta(seconds=seconds)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _append_jsonl(path: Path, *rows: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def _config(tmp_path: Path, *, interval_seconds: int = 60, stale_after_seconds: int = 180, canary_every_cycles: int = 1) -> Path:
    source = tmp_path / "telemetry.jsonl"
    _append_jsonl(source, {"timestamp": "2026-07-13T00:00:00Z", "service": "checkout", "message": "ok"})
    config = {
        "schema_version": "p131.monitor_config.v1",
        "runtime_id": "p131-test-runtime",
        "interval_seconds": interval_seconds,
        "heartbeat_timeout_seconds": max(interval_seconds * 3, 30),
        "data_stale_after_seconds": stale_after_seconds,
        "daily_report_interval_seconds": 120,
        "canary_every_cycles": canary_every_cycles,
        "max_consecutive_failures": 3,
        "state_path": str(tmp_path / "state.json"),
        "report_dir": str(tmp_path / "reports"),
        "lease_path": str(tmp_path / "runtime.lock"),
        "allowed_data_roots": [str(tmp_path)],
        "sources": [
            {
                "source_id": "local-log",
                "kind": "local_jsonl",
                "path": str(source),
                "enabled": True,
            }
        ],
    }
    path = tmp_path / "config.json"
    _write_json(path, config)
    return path


def test_real_cadence_heartbeats_and_exact_zero_authority(tmp_path: Path) -> None:
    clock = FakeClock(datetime(2026, 7, 13, tzinfo=UTC))
    runtime = AlwaysOnMonitor(load_monitor_config(_config(tmp_path)), clock=clock)

    report = runtime.run(max_cycles=3, sleep_enabled=True)
    state = load_monitor_state(tmp_path / "state.json")

    assert clock.sleeps == [60.0, 60.0]
    assert report["summary"]["cycle_count"] == 3
    assert state["cycle_count"] == 3
    assert state["process_health"]["heartbeat_current"] is True
    counters = state["authority"]["counters"]
    assert set(counters) == set(P121_AUTHORITY_COUNTER_KEYS)
    assert all(type(counters[key]) is int and counters[key] == 0 for key in P121_AUTHORITY_COUNTER_KEYS)


def test_scheduler_skips_missed_deadlines_without_catch_up_burst(tmp_path: Path) -> None:
    clock = FakeClock(datetime(2026, 7, 13, tzinfo=UTC))
    calls = 0

    def slow_first_canary() -> bool:
        nonlocal calls
        calls += 1
        if calls == 1:
            clock.current += timedelta(seconds=130)
        return True

    runtime = AlwaysOnMonitor(load_monitor_config(_config(tmp_path)), clock=clock, canary_probe=slow_first_canary)
    runtime.run(max_cycles=2, sleep_enabled=True)
    state = load_monitor_state(tmp_path / "state.json")

    assert clock.sleeps == [50.0]
    assert state["scheduler"]["missed_tick_count"] == 2


def test_restart_resumes_jsonl_cursor_without_duplicate_acceptance(tmp_path: Path) -> None:
    config_path = _config(tmp_path)
    clock = FakeClock(datetime(2026, 7, 13, tzinfo=UTC))
    first = AlwaysOnMonitor(load_monitor_config(config_path), clock=clock).run(max_cycles=1, sleep_enabled=False)
    _append_jsonl(
        tmp_path / "telemetry.jsonl",
        {"timestamp": "2026-07-13T00:01:00Z", "service": "checkout", "message": "latency warning"},
    )
    clock.current += timedelta(seconds=60)
    second = AlwaysOnMonitor(load_monitor_config(config_path), clock=clock).run(max_cycles=1, sleep_enabled=False)
    state = load_monitor_state(tmp_path / "state.json")

    assert first["summary"]["accepted_observation_count"] == 1
    assert second["summary"]["accepted_observation_count"] == 1
    assert state["totals"]["accepted_observation_count"] == 2
    assert state["totals"]["duplicate_observation_count"] == 0
    assert state["resume_count"] == 1


def test_rotation_replays_only_unseen_observations(tmp_path: Path) -> None:
    config_path = _config(tmp_path)
    clock = FakeClock(datetime(2026, 7, 13, tzinfo=UTC))
    AlwaysOnMonitor(load_monitor_config(config_path), clock=clock).run(max_cycles=1, sleep_enabled=False)
    replacement = tmp_path / "replacement.jsonl"
    _append_jsonl(
        replacement,
        {"timestamp": "2026-07-13T00:00:00Z", "service": "checkout", "message": "ok"},
        {"timestamp": "2026-07-13T00:01:00Z", "service": "checkout", "message": "new after rotation"},
    )
    os.replace(replacement, tmp_path / "telemetry.jsonl")
    clock.current += timedelta(seconds=60)

    report = AlwaysOnMonitor(load_monitor_config(config_path), clock=clock).run(max_cycles=1, sleep_enabled=False)
    state = load_monitor_state(tmp_path / "state.json")

    assert report["summary"]["accepted_observation_count"] == 1
    assert report["summary"]["duplicate_observation_count"] == 1
    assert state["source_health"]["local-log"]["rotation_count"] == 1


def test_partial_jsonl_line_is_not_committed_until_complete(tmp_path: Path) -> None:
    config_path = _config(tmp_path)
    source = tmp_path / "telemetry.jsonl"
    source.write_text('{"service":"checkout"', encoding="utf-8")
    clock = FakeClock(datetime(2026, 7, 13, tzinfo=UTC))

    first = AlwaysOnMonitor(load_monitor_config(config_path), clock=clock).run(max_cycles=1, sleep_enabled=False)
    with source.open("a", encoding="utf-8") as handle:
        handle.write("}\n")
    clock.current += timedelta(seconds=1)
    second = AlwaysOnMonitor(load_monitor_config(config_path), clock=clock).run(max_cycles=1, sleep_enabled=False)

    assert first["summary"]["accepted_observation_count"] == 0
    assert second["summary"]["accepted_observation_count"] == 1


def test_per_cycle_record_budget_prevents_unbounded_drain(tmp_path: Path) -> None:
    config_path = _config(tmp_path)
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    payload["max_records_per_cycle"] = 1
    _write_json(config_path, payload)
    _append_jsonl(tmp_path / "telemetry.jsonl", {"service": "checkout", "message": "second"})
    clock = FakeClock(datetime(2026, 7, 13, tzinfo=UTC))

    first = AlwaysOnMonitor(load_monitor_config(config_path), clock=clock).run(max_cycles=1, sleep_enabled=False)
    second = AlwaysOnMonitor(load_monitor_config(config_path), clock=clock).run(max_cycles=1, sleep_enabled=False)

    assert first["summary"]["accepted_observation_count"] == 1
    assert second["summary"]["accepted_observation_count"] == 1


def test_identical_rows_without_event_identity_are_not_silently_dropped(tmp_path: Path) -> None:
    config_path = _config(tmp_path)
    source = tmp_path / "telemetry.jsonl"
    source.write_text('', encoding="utf-8")
    _append_jsonl(source, {"service": "checkout", "message": "same"}, {"service": "checkout", "message": "same"})

    report = AlwaysOnMonitor(load_monitor_config(config_path), clock=FakeClock(datetime(2026, 7, 13, tzinfo=UTC))).run(max_cycles=1, sleep_enabled=False)

    assert report["summary"]["accepted_observation_count"] == 2
    assert report["summary"]["duplicate_observation_count"] == 0


def test_stale_data_is_not_ready_even_when_heartbeat_is_current(tmp_path: Path) -> None:
    config_path = _config(tmp_path, stale_after_seconds=60)
    clock = FakeClock(datetime(2026, 7, 13, tzinfo=UTC))
    runtime = AlwaysOnMonitor(load_monitor_config(config_path), clock=clock)
    runtime.run(max_cycles=1, sleep_enabled=False)
    clock.current += timedelta(seconds=90)

    status = monitor_status_snapshot(tmp_path / "state.json", now=clock.now(), heartbeat_timeout_seconds=180, data_stale_after_seconds=30)

    assert status["live"] is True
    assert status["ready"] is False
    assert "source_data_stale" in status["reasons"]


def test_canary_failure_fails_readiness_without_action_execution(tmp_path: Path) -> None:
    clock = FakeClock(datetime(2026, 7, 13, tzinfo=UTC))
    runtime = AlwaysOnMonitor(load_monitor_config(_config(tmp_path)), clock=clock, canary_probe=lambda: False)

    report = runtime.run(max_cycles=1, sleep_enabled=False)
    state = load_monitor_state(tmp_path / "state.json")

    assert report["summary"]["ready"] is False
    assert state["canary"]["last_result"] == "failed"
    assert state["canary"]["action_execution_count"] == 0
    assert state["totals"]["action_execution_count"] == 0


def test_source_failure_limit_fails_readiness(tmp_path: Path) -> None:
    config_path = _config(tmp_path)
    (tmp_path / "telemetry.jsonl").unlink()
    clock = FakeClock(datetime(2026, 7, 13, tzinfo=UTC))

    report = AlwaysOnMonitor(load_monitor_config(config_path), clock=clock).run(max_cycles=3, sleep_enabled=False)

    assert report["summary"]["ready"] is False
    assert "source_failure_limit_exceeded" in report["summary"]["reasons"]


def test_exclusive_lease_rejects_a_second_runtime(tmp_path: Path) -> None:
    config = load_monitor_config(_config(tmp_path))
    config.lease_path.parent.mkdir(parents=True, exist_ok=True)
    with config.lease_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(P131LeaseError, match="runtime_lease_unavailable"):
            AlwaysOnMonitor(config, clock=FakeClock(datetime(2026, 7, 13, tzinfo=UTC))).run(max_cycles=1, sleep_enabled=False)
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def test_restart_rejects_configuration_drift(tmp_path: Path) -> None:
    config_path = _config(tmp_path)
    clock = FakeClock(datetime(2026, 7, 13, tzinfo=UTC))
    AlwaysOnMonitor(load_monitor_config(config_path), clock=clock).run(max_cycles=1, sleep_enabled=False)
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    payload["canary_every_cycles"] = 2
    _write_json(config_path, payload)

    with pytest.raises(ValueError, match="config_hash_mismatch"):
        AlwaysOnMonitor(load_monitor_config(config_path), clock=clock).run(max_cycles=1, sleep_enabled=False)


def test_restart_rejects_rehashed_source_manifest_drift(tmp_path: Path) -> None:
    config_path = _config(tmp_path)
    clock = FakeClock(datetime(2026, 7, 13, tzinfo=UTC))
    config = load_monitor_config(config_path)
    AlwaysOnMonitor(config, clock=clock).run(max_cycles=1, sleep_enabled=False)
    state_path = tmp_path / "state.json"
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    payload["source_health"]["local-log"]["path_hash"] = stable_hash("/different/source.jsonl")
    payload["state_hash"] = stable_hash({key: value for key, value in payload.items() if key != "state_hash"})
    _write_json(state_path, payload)

    with pytest.raises(ValueError, match="source_manifest_mismatch"):
        AlwaysOnMonitor(config, clock=clock).run(max_cycles=1, sleep_enabled=False)


def test_checkpoint_load_happens_only_while_lease_is_owned(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = load_monitor_config(_config(tmp_path))
    clock = FakeClock(datetime(2026, 7, 13, tzinfo=UTC))
    AlwaysOnMonitor(config, clock=clock).run(max_cycles=1, sleep_enabled=False)
    lease_owned = False
    original_enter = p131_runtime._RuntimeLease.__enter__
    original_exit = p131_runtime._RuntimeLease.__exit__
    original_load = p131_runtime.load_monitor_state

    def tracked_enter(lease: Any) -> None:
        nonlocal lease_owned
        original_enter(lease)
        lease_owned = True

    def tracked_exit(lease: Any, exc_type: object, exc: object, traceback: object) -> None:
        nonlocal lease_owned
        lease_owned = False
        original_exit(lease, exc_type, exc, traceback)

    def guarded_load(path: Path | str, *, allowed_roots: Any = None) -> dict[str, Any]:
        assert lease_owned is True
        return original_load(path, allowed_roots=allowed_roots)

    monkeypatch.setattr(p131_runtime._RuntimeLease, "__enter__", tracked_enter)
    monkeypatch.setattr(p131_runtime._RuntimeLease, "__exit__", tracked_exit)
    monkeypatch.setattr(p131_runtime, "load_monitor_state", guarded_load)

    AlwaysOnMonitor(config, clock=clock).run(max_cycles=1, sleep_enabled=False)


def test_symlink_swap_cannot_escape_source_allowlist(tmp_path: Path) -> None:
    config_path = _config(tmp_path)
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    source = allowed / "telemetry.jsonl"
    os.replace(tmp_path / "telemetry.jsonl", source)
    payload["allowed_data_roots"] = [str(allowed)]
    payload["sources"][0]["path"] = str(source)
    _write_json(config_path, payload)
    config = load_monitor_config(config_path)
    outside = tmp_path / "outside.jsonl"
    _append_jsonl(outside, {"timestamp": "2026-07-13T00:00:00Z", "service": "outside", "message": "must not be read"})
    source.unlink()
    source.symlink_to(outside)

    report = AlwaysOnMonitor(config, clock=FakeClock(datetime(2026, 7, 13, tzinfo=UTC))).run(max_cycles=1, sleep_enabled=False)

    assert report["summary"]["accepted_observation_count"] == 0
    assert report["summary"]["source_failure_count"] == 1


def test_non_regular_source_fails_without_blocking(tmp_path: Path) -> None:
    config_path = _config(tmp_path)
    source = tmp_path / "telemetry.jsonl"
    source.unlink()
    os.mkfifo(source)

    report = AlwaysOnMonitor(
        load_monitor_config(config_path),
        clock=FakeClock(datetime(2026, 7, 13, tzinfo=UTC)),
    ).run(max_cycles=1, sleep_enabled=False)

    assert report["summary"]["accepted_observation_count"] == 0
    assert report["summary"]["source_failure_count"] == 1


def test_symlink_swap_cannot_escape_artifact_allowlist(tmp_path: Path) -> None:
    config_path = _config(tmp_path)
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    payload["allowed_artifact_roots"] = [str(artifact_root)]
    payload["state_path"] = str(artifact_root / "state.json")
    payload["report_dir"] = str(artifact_root / "reports")
    payload["lease_path"] = str(artifact_root / "runtime.lock")
    _write_json(config_path, payload)
    config = load_monitor_config(config_path)
    retained = tmp_path / "retained-artifacts"
    outside = tmp_path / "outside-artifacts"
    outside.mkdir()
    artifact_root.rename(retained)
    artifact_root.symlink_to(outside, target_is_directory=True)

    with pytest.raises(OSError):
        AlwaysOnMonitor(config, clock=FakeClock(datetime(2026, 7, 13, tzinfo=UTC))).run(
            max_cycles=1,
            sleep_enabled=False,
        )

    assert list(outside.iterdir()) == []


def test_watchdog_detects_missing_stale_and_tampered_state(tmp_path: Path) -> None:
    now = datetime(2026, 7, 13, tzinfo=UTC)
    missing = evaluate_watchdog(tmp_path / "missing.json", now=now, heartbeat_timeout_seconds=120)
    assert missing["healthy"] is False
    assert missing["reason"] == "state_missing"

    config_path = _config(tmp_path)
    AlwaysOnMonitor(load_monitor_config(config_path), clock=FakeClock(now)).run(max_cycles=1, sleep_enabled=False)
    current = evaluate_watchdog(tmp_path / "state.json", now=now + timedelta(seconds=60), heartbeat_timeout_seconds=120)
    stale = evaluate_watchdog(tmp_path / "state.json", now=now + timedelta(seconds=121), heartbeat_timeout_seconds=120)
    assert current["healthy"] is True
    assert stale["healthy"] is False
    assert stale["reason"] == "heartbeat_stale"
    future = evaluate_watchdog(tmp_path / "state.json", now=now - timedelta(seconds=6), heartbeat_timeout_seconds=120)
    assert future["healthy"] is False
    assert future["reason"] == "heartbeat_in_future"

    payload = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    payload["cycle_count"] = 999
    _write_json(tmp_path / "state.json", payload)
    tampered = evaluate_watchdog(tmp_path / "state.json", now=now, heartbeat_timeout_seconds=120)
    assert tampered["healthy"] is False
    assert tampered["reason"] == "state_hash_invalid"


def test_oversized_state_file_fails_closed(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text("{" + (" " * 1_048_576) + "}", encoding="utf-8")

    watchdog = evaluate_watchdog(state_path, now=datetime(2026, 7, 13, tzinfo=UTC), heartbeat_timeout_seconds=120)

    assert watchdog == {"schema_version": "p131.watchdog.v1", "healthy": False, "reason": "state_invalid"}


def test_rehashed_empty_source_manifest_fails_closed(tmp_path: Path) -> None:
    now = datetime(2026, 7, 13, tzinfo=UTC)
    AlwaysOnMonitor(load_monitor_config(_config(tmp_path)), clock=FakeClock(now)).run(max_cycles=1, sleep_enabled=False)
    state_path = tmp_path / "state.json"
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    payload["source_health"] = {}
    payload["state_hash"] = stable_hash({key: value for key, value in payload.items() if key != "state_hash"})
    _write_json(state_path, payload)

    watchdog = evaluate_watchdog(state_path, now=now, heartbeat_timeout_seconds=120)
    status = monitor_status_snapshot(state_path, now=now)

    assert watchdog == {"schema_version": "p131.watchdog.v1", "healthy": False, "reason": "invalid_source_state"}
    assert status["live"] is False
    assert status["ready"] is False
    assert status["reasons"] == ["invalid_source_state"]


def test_rehashed_incomplete_source_checkpoint_fails_closed(tmp_path: Path) -> None:
    now = datetime(2026, 7, 13, tzinfo=UTC)
    AlwaysOnMonitor(load_monitor_config(_config(tmp_path)), clock=FakeClock(now)).run(max_cycles=1, sleep_enabled=False)
    state_path = tmp_path / "state.json"
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    payload["source_health"]["local-log"] = {"enabled": True, "last_data_at": "2026-07-13T00:00:00Z"}
    payload["state_hash"] = stable_hash({key: value for key, value in payload.items() if key != "state_hash"})
    _write_json(state_path, payload)

    watchdog = evaluate_watchdog(state_path, now=now, heartbeat_timeout_seconds=120)
    status = monitor_status_snapshot(state_path, now=now)

    assert watchdog["healthy"] is False
    assert watchdog["reason"] == "invalid_source_state"
    assert status["live"] is False
    assert status["ready"] is False
    assert status["reasons"] == ["invalid_source_state"]


def test_rehashed_incomplete_canary_checkpoint_fails_closed(tmp_path: Path) -> None:
    now = datetime(2026, 7, 13, tzinfo=UTC)
    AlwaysOnMonitor(load_monitor_config(_config(tmp_path)), clock=FakeClock(now)).run(max_cycles=1, sleep_enabled=False)
    state_path = tmp_path / "state.json"
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    payload["canary"] = {"last_result": "passed", "action_execution_count": 0}
    payload["state_hash"] = stable_hash({key: value for key, value in payload.items() if key != "state_hash"})
    _write_json(state_path, payload)

    watchdog = evaluate_watchdog(state_path, now=now, heartbeat_timeout_seconds=120)
    status = monitor_status_snapshot(state_path, now=now)

    assert watchdog["healthy"] is False
    assert watchdog["reason"] == "invalid_canary_state"
    assert status["live"] is False
    assert status["ready"] is False
    assert status["reasons"] == ["invalid_canary_state"]


def test_rehashed_nonzero_authority_state_still_fails_closed(tmp_path: Path) -> None:
    now = datetime(2026, 7, 13, tzinfo=UTC)
    AlwaysOnMonitor(load_monitor_config(_config(tmp_path)), clock=FakeClock(now)).run(max_cycles=1, sleep_enabled=False)
    payload = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    payload["authority"]["counters"]["live_connector_call_count"] = 1
    payload["state_hash"] = stable_hash({key: value for key, value in payload.items() if key != "state_hash"})
    _write_json(tmp_path / "state.json", payload)

    result = evaluate_watchdog(tmp_path / "state.json", now=now, heartbeat_timeout_seconds=120)

    assert result["healthy"] is False
    assert result["reason"] == "authority_not_exact_zero"


def test_malformed_and_future_timestamps_fail_closed_in_watchdog_status_and_cli(tmp_path: Path) -> None:
    now = datetime(2026, 7, 13, tzinfo=UTC)
    AlwaysOnMonitor(load_monitor_config(_config(tmp_path)), clock=FakeClock(now)).run(max_cycles=1, sleep_enabled=False)
    state_path = tmp_path / "state.json"
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    payload["last_heartbeat_at"] = "not-a-time"
    payload["state_hash"] = stable_hash({key: value for key, value in payload.items() if key != "state_hash"})
    _write_json(state_path, payload)

    watchdog = evaluate_watchdog(state_path, now=now, heartbeat_timeout_seconds=120)
    status = monitor_status_snapshot(state_path, now=now)
    cli = subprocess.run(
        [sys.executable, "-m", "app.monitor_cli", "watchdog", "--state", str(state_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert watchdog["healthy"] is False
    assert watchdog["reason"] == "invalid_timestamp"
    assert status["ready"] is False
    assert status["reasons"] == ["invalid_timestamp"]
    assert cli.returncode == 1
    assert json.loads(cli.stdout)["reason"] == "invalid_timestamp"

    payload["last_heartbeat_at"] = "2026-07-13T00:00:00Z"
    payload["source_health"]["local-log"]["last_data_at"] = "2026-07-13T01:00:00Z"
    payload["state_hash"] = stable_hash({key: value for key, value in payload.items() if key != "state_hash"})
    _write_json(state_path, payload)
    future = monitor_status_snapshot(state_path, now=now)
    assert future["ready"] is False
    assert "source_data_in_future" in future["reasons"]


def test_daily_report_and_atomic_checkpoint_leave_no_temp_files(tmp_path: Path) -> None:
    clock = FakeClock(datetime(2026, 7, 13, tzinfo=UTC))
    runtime = AlwaysOnMonitor(load_monitor_config(_config(tmp_path)), clock=clock)

    runtime.run(max_cycles=3, sleep_enabled=True)

    reports = list((tmp_path / "reports").glob("p131-health-*.json"))
    assert len(reports) == 2
    report = json.loads(reports[-1].read_text(encoding="utf-8"))
    assert report["runtime_id"] == "p131-test-runtime"
    assert report["authority"]["exact_zero"] is True
    runtime.run(max_cycles=1, sleep_enabled=False)
    assert len(list((tmp_path / "reports").glob("p131-health-*.json"))) == 2
    assert not list(tmp_path.rglob("*.tmp"))


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("sources", [{"source_id": "bad", "kind": "shell", "command": "uptime"}], "unsupported_source_kind"),
        ("credential", "secret-token", "forbidden_configuration_field"),
        ("interval_seconds", 0, "interval_must_be_positive"),
        ("state_path", "../outside/state.json", "artifact_path_outside_allowed_roots"),
        ("network_url", "https://example.invalid", "unknown_configuration_field"),
        ("production_mutation", True, "forbidden_configuration_field"),
    ],
)
def test_unsafe_or_invalid_configuration_fails_closed(tmp_path: Path, field: str, value: object, reason: str) -> None:
    path = _config(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload[field] = value
    _write_json(path, payload)

    with pytest.raises(P131ConfigError, match=reason):
        load_monitor_config(path)


def test_cli_bounded_run_watchdog_and_status(tmp_path: Path) -> None:
    config = _config(tmp_path, interval_seconds=1)
    run = subprocess.run(
        [sys.executable, "-m", "app.monitor_cli", "run", "--config", str(config), "--max-cycles", "2", "--no-sleep"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout)["summary"]["cycle_count"] == 2

    watchdog = subprocess.run(
        [sys.executable, "-m", "app.monitor_cli", "watchdog", "--state", str(tmp_path / "state.json"), "--timeout-seconds", "180"],
        check=False,
        capture_output=True,
        text=True,
    )
    status = subprocess.run(
        [sys.executable, "-m", "app.monitor_cli", "status", "--state", str(tmp_path / "state.json")],
        check=False,
        capture_output=True,
        text=True,
    )
    assert watchdog.returncode == 0, watchdog.stdout + watchdog.stderr
    assert json.loads(watchdog.stdout)["healthy"] is True
    assert status.returncode == 0
    assert json.loads(status.stdout)["live"] is True


def test_monitor_http_health_and_readiness_are_fail_closed(tmp_path: Path, client: Any, app: Any) -> None:
    from app.config import Settings, get_settings

    state_path = tmp_path / "state.json"
    app.dependency_overrides[get_settings] = lambda: Settings(
        monitor_state_path=str(state_path),
        monitor_heartbeat_timeout_seconds=180,
        monitor_data_stale_after_seconds=300,
    )
    missing_health = client.get("/monitor/health")
    missing_ready = client.get("/monitor/readiness")
    assert missing_health.status_code == 503
    assert missing_health.json()["reason"] == "state_missing"
    assert missing_ready.status_code == 503

    AlwaysOnMonitor(load_monitor_config(_config(tmp_path))).run(max_cycles=1, sleep_enabled=False)
    current_health = client.get("/monitor/health")
    current_ready = client.get("/monitor/readiness")
    assert current_health.status_code == 200
    assert current_health.json()["healthy"] is True
    assert "state_hash" not in current_health.json()
    assert "runtime_id" not in current_health.json()
    assert current_ready.status_code == 200
    assert current_ready.json()["ready"] is True

    malformed = json.loads(state_path.read_text(encoding="utf-8"))
    malformed["last_heartbeat_at"] = "bad"
    malformed["state_hash"] = stable_hash({key: value for key, value in malformed.items() if key != "state_hash"})
    _write_json(state_path, malformed)
    assert client.get("/monitor/health").status_code == 503
    assert client.get("/monitor/readiness").status_code == 503
