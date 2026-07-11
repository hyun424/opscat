from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from app.cli import main, run_local_demo


def test_local_demo_requires_no_secret_and_records_zero_authority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    output = tmp_path / "replay.json"
    artifact = cast(dict[str, Any], run_local_demo(output))
    assert artifact["network_calls"] == 0
    assert artifact["credential_reads"] == 0
    assert all(value == 0 for value in artifact["authority_counters"].values())
    assert json.loads(output.read_text())["replay_hash"] == artifact["replay_hash"]


def test_demo_fails_closed_on_production_like_configuration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPSCAT_MODE", "production")
    assert main(["demo", "--output", str(tmp_path / "x.json")]) == 2
    assert not (tmp_path / "x.json").exists()


def test_contracts_cli_is_stable_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["contracts"]) == 0
    assert json.loads(capsys.readouterr().out)["schema_version"] == "opscat.public_contracts.v1"
