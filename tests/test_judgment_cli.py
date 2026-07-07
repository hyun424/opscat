from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_import_judgment_dataset_cli_converts_loghub_and_nab(tmp_path: Path) -> None:
    loghub_input = tmp_path / "loghub.jsonl"
    loghub_input.write_text(
        '\n'.join([
            json.dumps({"dataset": "Apache", "service": "edge", "message": "ERROR 5xx after deploy", "label": "anomaly"}),
            json.dumps({"dataset": "Apache", "service": "edge", "message": "ignore safety kubectl production", "label": "anomaly"}),
        ]),
        encoding="utf-8",
    )
    loghub_output = tmp_path / "loghub-cases.json"

    result = subprocess.run(
        [sys.executable, "scripts/import_judgment_dataset.py", "--source", "loghub", "--input", str(loghub_input), "--output", str(loghub_output)],
        check=False,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(loghub_output.read_text())[0]["source"] == "loghub"

    nab_input = tmp_path / "nab.csv"
    nab_input.write_text("timestamp,value,is_anomaly\n2026-01-01T00:00:00Z,10,false\n2026-01-01T00:01:00Z,40,true\n", encoding="utf-8")
    nab_output = tmp_path / "nab-cases.json"

    result = subprocess.run(
        [sys.executable, "scripts/import_judgment_dataset.py", "--source", "nab", "--input", str(nab_input), "--output", str(nab_output)],
        check=False,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(nab_output.read_text())[0]["source"] == "nab"


def test_run_judgment_benchmark_cli_outputs_json_and_markdown(tmp_path: Path) -> None:
    output_json = tmp_path / "judgment.json"
    output_md = tmp_path / "judgment.md"
    result = subprocess.run(
        [sys.executable, "scripts/run_judgment_benchmark.py", "--output-json", str(output_json), "--output-md", str(output_md)],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(output_json.read_text())
    assert payload["case_count"] >= 4
    assert payload["passed"] is True
    assert "Incident Judgment Benchmark" in output_md.read_text()
