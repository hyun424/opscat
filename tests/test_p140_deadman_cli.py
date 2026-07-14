from __future__ import annotations

import json
import signal
import subprocess
import sys
import time
import tomllib
from pathlib import Path
from typing import Any

import pytest

import app.p140_deadman_cli as cli
from app.services.p121_signals import zero_authority_counters
from app.services.p139_local_triage_service import zero_forbidden_authority
from app.services.p140_p139_deadman_adapter import P140AdapterConfig, P140StopController
from tests.fixtures.p140.builders import build_p140_fixture


def _read_stdout(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    captured = capsys.readouterr()
    assert captured.err == ""
    return json.loads(captured.out)


def _read_stderr(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    captured = capsys.readouterr()
    assert captured.out == ""
    return json.loads(captured.err)


def test_validate_loads_explicit_config_and_emits_identity(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fixture = build_p140_fixture(tmp_path)

    assert cli.main(["validate", "--config", str(fixture.p140_config_path)]) == 0

    payload = _read_stdout(capsys)
    assert payload == {
        "status": "valid",
        "adapter_id": fixture.config.adapter_id,
        "adapter_config_hash": fixture.config.config_hash,
    }


def test_check_accepts_only_utc_now_and_returns_unhealthy_exit(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fixture = build_p140_fixture(tmp_path)

    code = cli.main(["check", "--config", str(fixture.p140_config_path), "--now", "2026-07-13T00:10:04Z"])

    assert code == 1
    payload = _read_stdout(capsys)
    assert payload["reason"] == "state_missing"
    assert payload["healthy"] is False
    assert payload["adapter_config_hash"] == fixture.config.config_hash

    assert cli.main(["check", "--config", str(fixture.p140_config_path), "--now", "2026-07-13T00:10:04"]) == 2
    error = _read_stderr(capsys)
    assert error["ok"] is False
    assert error["error"] == "--now must be timezone-aware UTC"


def test_run_requires_exactly_one_bound_and_installs_safe_signal_handlers(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_p140_fixture(tmp_path)
    observed: dict[str, Any] = {}
    previous_term = signal.getsignal(signal.SIGTERM)

    def fake_run(
        config: P140AdapterConfig,
        *,
        max_cycles: int | None = None,
        forever: bool = False,
        stop_controller: P140StopController | None = None,
    ) -> dict[str, Any]:
        assert stop_controller is not None
        handler = signal.getsignal(signal.SIGTERM)
        assert callable(handler)
        handler(signal.SIGTERM, None)
        observed.update(
            {
                "config_hash": config.config_hash,
                "max_cycles": max_cycles,
                "forever": forever,
                "stop_reason": stop_controller.reason(),
            }
        )
        return {"schema_version": "test.run.v1", "healthy": True, "stop_reason": stop_controller.reason()}

    monkeypatch.setattr(cli, "run_p139_deadman_adapter", fake_run)

    assert cli.main(["run", "--config", str(fixture.p140_config_path), "--max-cycles", "2"]) == 0

    payload = _read_stdout(capsys)
    assert payload["stop_reason"] == "sigterm"
    assert observed == {
        "config_hash": fixture.config.config_hash,
        "max_cycles": 2,
        "forever": False,
        "stop_reason": "sigterm",
    }
    assert signal.getsignal(signal.SIGTERM) == previous_term

    assert cli.main(["run", "--config", str(fixture.p140_config_path)]) == 2
    assert _read_stderr(capsys)["error"] == "choose exactly one of --forever or --max-cycles"
    assert cli.main(["run", "--config", str(fixture.p140_config_path), "--forever", "--max-cycles", "1"]) == 2
    assert _read_stderr(capsys)["error"] == "choose exactly one of --forever or --max-cycles"


def test_cli_parse_errors_are_json_exit_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["check"]) == 2
    error = _read_stderr(capsys)
    assert error["ok"] is False
    assert "--config" in error["error"]


def test_pyproject_maps_console_script_to_p140_cli_main() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["scripts"]["opscat-triage-deadman"] == "app.p140_deadman_cli:main"


def test_real_child_process_sigterm_cli_json_has_zero_counters(tmp_path: Path) -> None:
    fixture = build_p140_fixture(tmp_path)
    command = [
        sys.executable,
        "-m",
        "app.p140_deadman_cli",
        "run",
        "--config",
        str(fixture.p140_config_path),
        "--forever",
    ]
    process = subprocess.Popen(
        command,
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    lease_path = fixture.config.adapter_lease_path
    stdout = ""
    stderr = ""
    try:
        deadline = time.monotonic() + 10
        while not lease_path.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert process.poll() is None, process.communicate(timeout=1)
        process.send_signal(signal.SIGTERM)
        stdout, stderr = process.communicate(timeout=10)
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=2)

    assert process.returncode == 0, stdout + stderr
    assert stderr == ""
    payload = json.loads(stdout)
    assert payload["schema_version"] == "p140.p139_deadman_adapter_run.v1"
    assert payload["graceful_stop"] is True
    assert payload["stop_reason"] == "sigterm"
    assert payload["authority_counters"] == zero_authority_counters()
    assert payload["p139_forbidden_authority"] == zero_forbidden_authority()


def test_deployment_manifests_are_networkless_nonroot_and_state_writable_only() -> None:
    compose = json.loads(Path("deploy/p140/compose.triage-deadman.yaml").read_text(encoding="utf-8"))
    assert compose["x-opscat-preflight"] == {
        "required_regular_files": ["./data/p139/service.lock"],
        "required_owner": "65532:65532",
        "required_mode": "0600",
    }
    service = compose["services"]["opscat-triage-deadman"]
    assert service["command"] == [
        "opscat-triage-deadman",
        "run",
        "--config",
        "/etc/opscat/p140-deadman-adapter.json",
        "--forever",
    ]
    assert service["network_mode"] == "none"
    assert service["user"] == "65532:65532"
    assert service["read_only"] is True
    assert service["cap_drop"] == ["ALL"]
    assert "environment" not in service
    assert "./data/p140:/var/lib/opscat/p140:rw" in service["volumes"]
    assert "./data/p139:/var/lib/opscat/p139:ro" in service["volumes"]
    assert "./data/p139/service.lock:/var/lib/opscat/p139/service.lock:rw" in service["volumes"]
    assert "./data/p139:/var/lib/opscat/p139:rw" not in service["volumes"]
    assert all(not volume.startswith("./data/p139/service.lock/:") for volume in service["volumes"])

    unit = Path("deploy/p140/opscat-triage-deadman.service").read_text(encoding="utf-8")
    assert "ExecStart=/usr/local/bin/opscat-triage-deadman run --config /etc/opscat/p140-deadman-adapter.json --forever" in unit
    assert "ExecStartPre=/usr/local/bin/opscat-triage-deadman validate --config /etc/opscat/p140-deadman-adapter.json" in unit
    assert "User=opscat" in unit
    assert "PrivateNetwork=true" in unit
    assert "ProtectSystem=strict" in unit
    assert "ReadWritePaths=/var/lib/opscat/p140" in unit
    assert "ReadOnlyPaths=/var/lib/opscat/p139" in unit
    assert "ReadWritePaths=/var/lib/opscat/p139/service.lock" in unit
    assert "ReadWritePaths=/var/lib/opscat/p139\n" not in unit
    assert "CapabilityBoundingSet=\n" in unit
    assert "Environment=" not in unit
