from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

P108_CASES_PATH = Path("evals/prevention/p108_learning_cases.json")
P108_LEARNING_CLI = Path("scripts/run_prevention_learning_eval.py")


def test_learning_eval_cli_defaults_to_real_fixture_and_reports_six_gates() -> None:
    assert P108_LEARNING_CLI.exists(), f"P108 RED: missing learning eval CLI {P108_LEARNING_CLI}"
    assert P108_CASES_PATH.exists(), f"P108 RED: missing real learning fixture file {P108_CASES_PATH}"

    result = subprocess.run(
        [sys.executable, str(P108_LEARNING_CLI), "--dry-run"],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "p108.learning_eval_dry_run.v1"
    assert payload["fixture_path"] == str(P108_CASES_PATH)
    assert payload["trusted_now"] == "2026-07-10T04:00:00Z"
    assert tuple(payload["fixture_ids"]) == tuple(f"L{index:02d}" for index in range(1, 17))
    assert set(payload["six_release_gates"]) == {
        "p107_ingress_ready",
        "immutable_ledger_ready",
        "benchmark_metrics_ready",
        "recommendation_manifest_ready",
        "promotion_ready",
        "authority_boundary_ready",
    }


def test_learning_eval_cli_writes_byte_stable_json_and_markdown(tmp_path: Path) -> None:
    output_json_a = tmp_path / "p108-a.json"
    output_json_b = tmp_path / "p108-b.json"
    output_md = tmp_path / "p108.md"

    first = subprocess.run(
        [sys.executable, str(P108_LEARNING_CLI), "--output-json", str(output_json_a), "--output-md", str(output_md)],
        check=False,
        text=True,
        capture_output=True,
    )
    second = subprocess.run(
        [sys.executable, str(P108_LEARNING_CLI), "--output-json", str(output_json_b)],
        check=False,
        text=True,
        capture_output=True,
    )

    assert first.returncode == 0
    assert second.returncode == 0
    assert output_json_a.read_bytes() == output_json_b.read_bytes()
    payload = json.loads(output_json_a.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "p108.learning_evidence.v1"
    assert payload["trusted_now"] == "2026-07-10T04:00:00Z"
    assert "p108.release_evidence.v1" in output_md.read_text(encoding="utf-8")
    assert "p107_ingress_ready" in output_md.read_text(encoding="utf-8")


def test_learning_eval_cli_rejects_noncanonical_or_incompatible_fixture_path(tmp_path: Path) -> None:
    wrong_fixture = tmp_path / "cases.json"
    wrong_fixture.write_text(json.dumps({"schema_version": "p107.canary_fixture_matrix.v1", "fixtures": []}), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(P108_LEARNING_CLI), "--fixture-path", str(wrong_fixture), "--dry-run"],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert "evals/prevention/p108_learning_cases.json" in result.stderr
