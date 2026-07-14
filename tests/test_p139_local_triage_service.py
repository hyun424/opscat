from __future__ import annotations

import fcntl
import json
import signal
import subprocess
import sys
import time
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p138_observation_triage_supervisor import (
    build_observation_triage_supervisor_config,
)
from app.services.p139_local_triage_service import (
    P139InjectedCrash,
    P139ServiceError,
    P139StopController,
    build_local_triage_service_bundle,
    inspect_local_triage_service,
    read_local_triage_service_bundle,
    run_local_triage_service_for_evaluation,
    validate_exit_receipt,
    write_local_triage_service_bundle,
    zero_forbidden_authority,
)
from tests.fixtures.p139.builders import P139Fixture, build_p139_fixture

NOW_VALUES = ("2026-07-13T00:10:04Z", "2026-07-13T00:10:05Z")


def _run(fixture: P139Fixture) -> dict[str, Any]:
    return run_local_triage_service_for_evaluation(
        base_path=fixture.root,
        bundle=fixture.bundle,
        now_values=NOW_VALUES,
        monotonic=lambda: 1.0,
        sleep=lambda _: None,
    )


def _read(root: Path, relative: str) -> dict[str, object]:
    return json.loads((root / relative).read_text(encoding="utf-8"))


def test_bundle_round_trip_and_rejects_secret_or_callable(tmp_path: Path) -> None:
    fixture = build_p139_fixture(tmp_path)
    path = tmp_path / "service-bundle.json"
    write_local_triage_service_bundle(path, fixture.bundle)
    assert read_local_triage_service_bundle(path) == fixture.bundle

    for index, forbidden in enumerate(("token=abc", "https://example.invalid", "$NVIDIA_API_KEY")):
        with pytest.raises(P139ServiceError, match="forbidden_bundle_text"):
            build_p139_fixture(tmp_path / f"forbidden-{index}", service_id=forbidden)
    invalid = deepcopy(fixture.bundle_input)
    invalid["p136_runtime"]["probe"] = lambda: None
    with pytest.raises(P139ServiceError, match="callable_forbidden"):
        build_p139_fixture(tmp_path / "callable", **invalid)
    unknown = deepcopy(fixture.bundle_input)
    unknown["unknown"] = True
    with pytest.raises(P139ServiceError, match="invalid_bundle_input_fields"):
        build_local_triage_service_bundle(unknown)


def test_service_runs_to_clean_stop_with_zero_authority(tmp_path: Path) -> None:
    fixture = build_p139_fixture(tmp_path)
    result = _run(fixture)

    assert result["status"] == "stopped"
    assert result["start_classification"] == "clean_start"
    assert result["stop_reason"] == "max_cycles_reached"
    assert result["forbidden_authority"] == zero_forbidden_authority()
    assert result["service_status"]["health"] == "stopped_clean"
    assert result["exit_receipt"]["last_valid_ledger_hash"] == result["service_status"]["last_valid_ledger_hash"]


def test_clean_restart_rolls_controls_and_extends_receipt_chain(tmp_path: Path) -> None:
    fixture = build_p139_fixture(tmp_path)
    first = _run(fixture)
    second = _run(fixture)

    assert second["start_classification"] == "clean_restart"
    assert second["exit_receipt"]["generation"] == 2
    assert second["exit_receipt"]["previous_receipt_hash"] == first["exit_receipt"]["receipt_hash"]
    assert (
        validate_exit_receipt(
            second["exit_receipt"],
            bundle=fixture.bundle,
            previous=first["exit_receipt"],
        )
        == second["exit_receipt"]
    )
    assert not (fixture.root / fixture.bundle["p138_config"]["termination_dir"] / f"{str(first['exit_receipt']['p138_termination_hash']).removeprefix('sha256:')}.json").is_symlink()


@pytest.mark.parametrize("boundary", ["exit_intent", "exit_history", "exit_current"])
def test_exit_split_commit_recovers_without_fork(tmp_path: Path, boundary: str) -> None:
    fixture = build_p139_fixture(tmp_path)
    with pytest.raises(P139InjectedCrash, match=boundary):
        run_local_triage_service_for_evaluation(
            base_path=fixture.root,
            bundle=fixture.bundle,
            now_values=NOW_VALUES,
            monotonic=lambda: 1.0,
            sleep=lambda _: None,
            crash_after=boundary,
        )
    recovered = _run(fixture)
    assert recovered["exit_receipt"]["generation"] == 2
    assert recovered["start_classification"] == "clean_restart"


@pytest.mark.parametrize("boundary", ["restart_intent", "restart_history", "restart_controls_removed"])
def test_restart_split_commit_recovers_exact_archived_controls(tmp_path: Path, boundary: str) -> None:
    fixture = build_p139_fixture(tmp_path)
    first = _run(fixture)
    with pytest.raises(P139InjectedCrash, match=boundary):
        run_local_triage_service_for_evaluation(
            base_path=fixture.root,
            bundle=fixture.bundle,
            now_values=NOW_VALUES,
            monotonic=lambda: 1.0,
            sleep=lambda _: None,
            crash_after=boundary,
        )
    recovered = _run(fixture)
    assert recovered["start_classification"] == "clean_restart"
    assert recovered["exit_receipt"]["generation"] == int(first["exit_receipt"]["generation"]) + 1


def test_status_requires_live_service_lease_for_ready(tmp_path: Path) -> None:
    fixture = build_p139_fixture(tmp_path)
    result = _run(fixture)
    readiness_path = fixture.root / fixture.bundle["p138_config"]["readiness_path"]
    readiness = _read(fixture.root, fixture.bundle["p138_config"]["readiness_path"])
    readiness["status"] = "ready"
    readiness["reason"] = "running"
    readiness["readiness_hash"] = stable_hash({key: value for key, value in readiness.items() if key != "readiness_hash"})
    readiness_path.write_text(
        json.dumps(readiness, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    status = inspect_local_triage_service(
        base_path=fixture.root,
        bundle=fixture.bundle,
        now=str(result["exit_receipt"]["created_at"]),
    )
    assert status["health"] == "stopped_unclean"
    assert status["reason"] == "active_readiness_without_service_lease"


def test_status_reports_ready_only_with_held_lease_and_matching_heartbeat(
    tmp_path: Path,
) -> None:
    fixture = build_p139_fixture(tmp_path)
    result = _run(fixture)
    readiness_path = fixture.root / fixture.bundle["p138_config"]["readiness_path"]
    heartbeat_path = fixture.root / fixture.bundle["p138_config"]["heartbeat_path"]
    readiness = _read(fixture.root, fixture.bundle["p138_config"]["readiness_path"])
    heartbeat = _read(fixture.root, fixture.bundle["p138_config"]["heartbeat_path"])
    readiness.update({"status": "ready", "reason": "cycle_complete"})
    readiness["readiness_hash"] = stable_hash({key: value for key, value in readiness.items() if key != "readiness_hash"})
    heartbeat["readiness_state"] = "ready"
    heartbeat["heartbeat_hash"] = stable_hash({key: value for key, value in heartbeat.items() if key != "heartbeat_hash"})
    for path, value in ((readiness_path, readiness), (heartbeat_path, heartbeat)):
        path.write_text(
            json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
    termination_dir = fixture.root / fixture.bundle["p138_config"]["termination_dir"]
    termination_before = {path.name: path.read_bytes() for path in termination_dir.glob("*.json")}
    lease_path = fixture.root / fixture.bundle["service_lease_path"]
    with lease_path.open("a+", encoding="utf-8") as lease:
        fcntl.flock(lease.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        status = inspect_local_triage_service(
            base_path=fixture.root,
            bundle=fixture.bundle,
            now=str(result["exit_receipt"]["created_at"]),
        )
    assert status["health"] == "ready"
    assert {path.name: path.read_bytes() for path in termination_dir.glob("*.json")} == termination_before


@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM])
def test_signal_controller_stops_before_a_new_cycle_with_bound_receipt(tmp_path: Path, signum: int) -> None:
    fixture = build_p139_fixture(tmp_path)
    controller = P139StopController()
    controller.handle_signal(signum, None)
    result = run_local_triage_service_for_evaluation(
        base_path=fixture.root,
        bundle=fixture.bundle,
        now_values=NOW_VALUES,
        stop_controller=controller,
        monotonic=lambda: 1.0,
        sleep=lambda _: None,
    )
    assert result["stop_reason"] in {"sigint", "sigterm"}
    assert result["cycles_completed"] == 0
    assert result["service_status"]["health"] == "stopped_clean"


def test_bundle_and_runtime_paths_reject_symlinks(tmp_path: Path) -> None:
    fixture = build_p139_fixture(tmp_path)
    bundle_path = tmp_path / "bundle.json"
    target = tmp_path / "target.json"
    target.write_text("{}\n", encoding="utf-8")
    bundle_path.symlink_to(target)
    with pytest.raises(P139ServiceError, match="path_not_secure_regular_file"):
        read_local_triage_service_bundle(bundle_path)

    (fixture.root / "p139").mkdir(exist_ok=True)
    (fixture.root / "outside").mkdir()
    (fixture.root / "p139" / "exit-history").symlink_to(fixture.root / "outside")
    with pytest.raises(P139ServiceError, match="runtime_path_symlink_forbidden"):
        _run(fixture)


def test_real_subprocess_validate_run_restart_and_status(tmp_path: Path) -> None:
    fixture = build_p139_fixture(tmp_path)
    bundle_path = tmp_path / "service-bundle.json"
    write_local_triage_service_bundle(bundle_path, fixture.bundle)
    validate = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.p139_service_cli",
            "validate",
            "--bundle",
            str(bundle_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )
    assert validate.returncode == 0, validate.stderr
    assert json.loads(validate.stdout)["status"] == "valid"

    command = [
        sys.executable,
        "scripts/run_p139_service_evaluation.py",
        "--bundle",
        str(bundle_path),
        "--base",
        str(fixture.root),
        "--now",
        NOW_VALUES[0],
        "--now",
        NOW_VALUES[1],
    ]
    first = subprocess.run(
        command,
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )
    assert first.returncode == 0, first.stdout + first.stderr
    assert json.loads(first.stdout)["start_classification"] == "clean_start"
    second = subprocess.run(
        command,
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )
    assert second.returncode == 0, second.stdout + second.stderr
    assert json.loads(second.stdout)["start_classification"] == "clean_restart"

    status = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.p139_service_cli",
            "status",
            "--bundle",
            str(bundle_path),
            "--base",
            str(fixture.root),
            "--now",
            NOW_VALUES[1],
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )
    assert status.returncode == 0, status.stderr
    assert json.loads(status.stdout)["health"] == "stopped_clean"


def test_real_subprocess_sigterm_then_restart_has_one_receipt_successor(
    tmp_path: Path,
) -> None:
    fixture = build_p139_fixture(tmp_path)
    config_input = deepcopy(fixture.p138.config_input)
    config_input["limits"] = {
        **config_input["limits"],
        "max_supervisor_cycles": 100,
        "poll_interval_ms": 100,
        "heartbeat_interval_ms": 100,
    }
    bundle_input = deepcopy(fixture.bundle_input)
    bundle_input["p138_config"] = build_observation_triage_supervisor_config(config_input)
    bundle = build_local_triage_service_bundle(bundle_input)
    bundle_path = tmp_path / "signal-service-bundle.json"
    write_local_triage_service_bundle(bundle_path, bundle)
    start = datetime(2026, 7, 13, 0, 10, 4, tzinfo=UTC)
    now_values = [(start + timedelta(seconds=index)).isoformat().replace("+00:00", "Z") for index in range(50)]
    command = [
        sys.executable,
        "scripts/run_p139_service_evaluation.py",
        "--bundle",
        str(bundle_path),
        "--base",
        str(fixture.root),
        "--real-sleep",
    ]
    for value in now_values:
        command.extend(("--now", value))
    process = subprocess.Popen(
        command,
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    readiness_path = fixture.root / bundle["p138_config"]["readiness_path"]
    deadline = time.monotonic() + 10
    while not readiness_path.exists() and process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.02)
    assert process.poll() is None, process.communicate(timeout=1)
    process.send_signal(signal.SIGTERM)
    stdout, stderr = process.communicate(timeout=10)
    assert process.returncode == 0, stdout + stderr
    first = json.loads(stdout)
    assert first["stop_reason"] == "sigterm"
    assert 0 <= first["cycles_completed"] < 100

    restart = subprocess.run(
        [
            sys.executable,
            "scripts/run_p139_service_evaluation.py",
            "--bundle",
            str(bundle_path),
            "--base",
            str(fixture.root),
            "--now",
            "2026-07-13T00:11:00Z",
            "--now",
            "2026-07-13T00:11:01Z",
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )
    assert restart.returncode == 0, restart.stdout + restart.stderr
    second = json.loads(restart.stdout)
    assert second["start_classification"] == "clean_restart"
    assert second["exit_receipt"]["generation"] == int(first["exit_receipt"]["generation"]) + 1
    assert second["exit_receipt"]["previous_receipt_hash"] == first["exit_receipt"]["receipt_hash"]
    assert second["forbidden_authority"] == zero_forbidden_authority()
