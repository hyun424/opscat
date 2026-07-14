from __future__ import annotations

import json
from pathlib import Path

import pytest

import app.p142_loopback_cli as p142_cli
from app.p142_loopback_cli import StopController, main
from app.services.p142_loopback_transport_lab import FORBIDDEN_AUTHORITY_COUNTER_KEYS, TRANSPORT_COUNTER_KEYS, LoopbackTransportError, zero_forbidden_authority_counters
from tests.fixtures.p142.builders import build_p142_fixture


def test_run_stops_on_signal_and_rejects_clock_rollback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = build_p142_fixture(tmp_path)
    controller = StopController()
    controller.handle_signal(15, None)
    result = p142_cli._run_loop(fixture.config, controller, max_cycles=None)
    assert result["stop_requested"] is True
    assert result["signal_number"] == 15

    ticks = iter([10.0, 1.0])
    monkeypatch.setattr(p142_cli.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(p142_cli, "process_loopback_transport", lambda _config: {})
    with pytest.raises(LoopbackTransportError, match="monotonic_clock_rollback"):
        p142_cli._run_loop(fixture.config, StopController(), max_cycles=2)


def test_cli_outputs_exact_zero_non_transport_authority_counters(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fixture = build_p142_fixture(tmp_path)
    assert main(["process", "--config", str(fixture.config_path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert set(result["authority_counters"]) == set(FORBIDDEN_AUTHORITY_COUNTER_KEYS)
    assert result["authority_counters"] == zero_forbidden_authority_counters()
    assert set(result["transport_counters"]) == set(TRANSPORT_COUNTER_KEYS)
    assert all(type(value) is int for value in result["authority_counters"].values())


def test_validate_process_list_and_run_commands_are_json_only(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = build_p142_fixture(tmp_path)
    assert main(["validate", "--config", str(fixture.config_path)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "valid"

    monkeypatch.setattr(
        p142_cli,
        "process_loopback_transport",
        lambda _config: {
            "schema_version": "p142.loopback_transport_run.v1",
            "authority_counters": zero_forbidden_authority_counters(),
            "transport_counters": {key: 0 for key in TRANSPORT_COUNTER_KEYS},
        },
    )
    assert main(["process", "--config", str(fixture.config_path)]) == 0
    assert json.loads(capsys.readouterr().out)["schema_version"] == "p142.loopback_transport_run.v1"

    assert main(["list", "--config", str(fixture.config_path)]) == 0
    assert json.loads(capsys.readouterr().out)["schema_version"] == "p142.loopback_transport_receipt_list.v1"

    assert main(["run", "--config", str(fixture.config_path), "--max-cycles", "1"]) == 0
    assert json.loads(capsys.readouterr().out)["cycles"] == 1


def test_cli_rejects_send_url_token_and_errors_are_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fixture = build_p142_fixture(tmp_path)
    assert main(["send"]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
    assert main(["validate", "--config", str(fixture.config_path), "--url", "http://127.0.0.1"]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
    source = Path(p142_cli.__file__).read_text(encoding="utf-8")
    assert "--url" not in source
    assert "--webhook" not in source
    assert "--token" not in source
