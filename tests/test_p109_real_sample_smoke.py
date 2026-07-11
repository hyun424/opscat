from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_real_upstream_sample_is_parsed_but_never_claims_accuracy(tmp_path: Path) -> None:
    output = tmp_path / "real-sample.json"
    command = [sys.executable, "scripts/run_rcaeval_real_sample.py", "--output-json", str(output)]

    first = subprocess.run(command, check=True, capture_output=True, text=True)
    first_bytes = output.read_bytes()
    second = subprocess.run(command, check=True, capture_output=True, text=True)
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert first.stdout == second.stdout
    assert first_bytes == output.read_bytes()
    assert payload["source_sha256"] == "3eb6169a63f86c5878c277434936e1f4bbbd7f30dcf7f87dc3496bea8cae7f1a"
    assert payload["observation_count"] == 41097
    assert payload["service_count"] >= 12
    assert payload["truth_available"] is False
    assert payload["real_telemetry_smoke_only"] is True
    assert payload["release_qualified"] is False
    assert payload["status"] == "unevaluable_real_data_missing"
    assert set(payload["authority"].values()) == {0}
