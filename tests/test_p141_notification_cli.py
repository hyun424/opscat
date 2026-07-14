from __future__ import annotations

import json
from pathlib import Path

import pytest

import app.p141_notification_cli as p141_cli
from app.p141_notification_cli import main
from tests.fixtures.p141.builders import build_p141_fixture


def test_validate_process_and_list_commands_are_json_only(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fixture = build_p141_fixture(tmp_path)
    assert main(["validate", "--config", str(fixture.config_path)]) == 0
    validated = json.loads(capsys.readouterr().out)
    assert validated["status"] == "valid"

    assert main(["process", "--config", str(fixture.config_path), "--now", "2026-07-14T01:00:00Z"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["simulated_attempt_count"] == 2
    assert result["delivered_count"] == 0

    assert main(["list-receipts", "--config", str(fixture.config_path)]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed["count"] == 2
    assert all(item["delivered"] is False for item in listed["items"])


def test_run_is_bounded_and_errors_are_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fixture = build_p141_fixture(tmp_path)
    assert main(["run", "--config", str(fixture.config_path), "--max-cycles", "1"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["cycles"] == 1
    assert result["delivered_count"] == 0

    assert main(["process", "--config", str(fixture.config_path), "--now", "not-a-time"]) == 2
    error = json.loads(capsys.readouterr().err)
    assert error["ok"] is False


def test_cli_has_no_send_or_network_address_surface(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["send"]) == 2
    error = json.loads(capsys.readouterr().err)
    assert error["ok"] is False

    module_file = p141_cli.__file__
    assert module_file is not None
    source = Path(module_file).read_text(encoding="utf-8")
    assert "--url" not in source
    assert "--webhook" not in source
    assert "--token" not in source


def test_deployment_manifests_are_networkless_nonroot_and_p141_writable_only() -> None:
    root = Path(__file__).resolve().parents[1]
    compose = json.loads((root / "deploy/p141/compose.notification-authority.yaml").read_text(encoding="utf-8"))
    service = compose["services"]["opscat-notification-authority"]
    assert service["network_mode"] == "none"
    assert service["read_only"] is True
    assert service["privileged"] is False
    assert service["user"] == "65532:65532"
    assert service["cap_drop"] == ["ALL"]
    assert "./data/p141:/var/lib/opscat/p141:rw" in service["volumes"]
    assert "./data/p133:/var/lib/opscat/p133:ro" in service["volumes"]
    assert service["volumes"].count("./data/p133/.cursor.json.lock:/var/lib/opscat/p133/.cursor.json.lock:rw") == 1

    systemd = (root / "deploy/p141/opscat-notification-authority.service").read_text(encoding="utf-8")
    for directive in ("PrivateNetwork=true", "NoNewPrivileges=true", "ProtectSystem=strict", "RestrictAddressFamilies=AF_UNIX"):
        assert directive in systemd
    assert "ReadWritePaths=/var/lib/opscat/p141" in systemd
    assert "ReadWritePaths=/var/lib/opscat/p133/.cursor.json.lock" in systemd
