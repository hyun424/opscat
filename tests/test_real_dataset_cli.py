from __future__ import annotations

import json
import subprocess
from pathlib import Path


def test_p12_convert_cli_writes_cases_and_quality_report(tmp_path: Path) -> None:
    output_cases = tmp_path / "cases.json"
    output_quality = tmp_path / "quality.json"

    subprocess.run(
        [
            "python",
            "scripts/import_real_dataset.py",
            "--family",
            "aiops",
            "--input",
            "evals/real_datasets/fixtures/aiops/multisignal_sample.jsonl",
            "--output-cases",
            str(output_cases),
            "--output-quality",
            str(output_quality),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    cases = json.loads(output_cases.read_text(encoding="utf-8"))
    quality = json.loads(output_quality.read_text(encoding="utf-8"))
    assert len(cases) >= 1
    assert quality["accepted_records"] >= 1
    assert quality["unsupported_records"] == 0


def test_p12_evaluation_cli_writes_json_and_markdown(tmp_path: Path) -> None:
    output_json = tmp_path / "real-eval.json"
    output_md = tmp_path / "real-eval.md"
    output_cases = tmp_path / "real-cases.json"

    subprocess.run(
        [
            "python",
            "scripts/run_real_dataset_eval.py",
            "--fixture-pack",
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
            "--output-cases",
            str(output_cases),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(output_json.read_text(encoding="utf-8"))
    markdown = output_md.read_text(encoding="utf-8")
    assert payload["passed"] is True
    assert payload["benchmark"]["passed"] is True
    assert payload["case_count"] >= 3
    assert "# OpsCat Real Dataset Evaluation" in markdown
    assert "local/mock" in markdown
    assert output_cases.exists()
