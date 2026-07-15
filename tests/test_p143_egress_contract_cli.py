from __future__ import annotations

import json
from pathlib import Path

from _pytest.capture import CaptureFixture

from app.p143_egress_contract_cli import main
from app.services.p143_egress_contract_lab import ALLOWED_COUNTER_KEYS, FORBIDDEN_COUNTER_KEYS
from tests.fixtures.p143.builders import build_p143_fixture


def test_cli_emits_exact_int_only_counter_keysets(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    fixture = build_p143_fixture(tmp_path)
    assert main(["process", "--config", str(fixture.config_path)]) == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert tuple(payload["forbidden_counters"]) == FORBIDDEN_COUNTER_KEYS
    assert tuple(payload["allowed_counters"]) == ALLOWED_COUNTER_KEYS
    assert all(type(value) is int and value == 0 for value in payload["forbidden_counters"].values())
    assert all(type(value) is int and value >= 0 for value in payload["allowed_counters"].values())
