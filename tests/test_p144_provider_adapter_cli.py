from __future__ import annotations

import json
from pathlib import Path

from app.p144_provider_adapter_cli import main
from tests.fixtures.p144.builders import build_p144_fixture


def test_cli_counters_reconcile_to_artifacts_and_transport(tmp_path: Path) -> None:
    fixture = build_p144_fixture(tmp_path, max_sources_per_run=1)
    output = tmp_path / "cli-output.json"
    assert main(["--config", str(fixture.config_path), "--output", str(output)]) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "ok"
    assert payload["adapter_counters"]["terminal_receipt_write_count"] == 1
    assert payload["transport_counters"]["loopback_socket_attempt_count"] == 1
    assert all(type(value) is int and value == 0 for value in payload["forbidden_counters"].values())
