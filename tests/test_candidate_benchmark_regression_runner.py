from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.candidate_benchmark_regression_runner import (
    CandidateBenchmarkRegressionRunnerReport,
    build_candidate_benchmark_regression_runner_report,
    render_candidate_benchmark_regression_runner_markdown,
)

CASES = Path("evals/investigator/p51_operator_judgment_benchmark_v2_cases.json")


def test_candidate_benchmark_regression_runner_proves_repeatable_candidate_stability() -> None:
    report = build_candidate_benchmark_regression_runner_report(CASES, repeat_count=3)
    payload = report.to_dict()

    assert isinstance(report, CandidateBenchmarkRegressionRunnerReport)
    assert payload["summary"]["passed"] is True
    assert payload["summary"]["repeat_count"] == 3
    assert payload["summary"]["stable_source_fingerprint"] is True
    assert payload["summary"]["stable_candidate_fingerprint"] is True
    assert payload["summary"]["all_gap_closures_stable"] is True
    assert payload["summary"]["all_score_deltas_non_negative"] is True
    assert payload["summary"]["unsafe_action_count"] == 0
    assert payload["stability"]["source_fingerprint_unique_count"] == 1
    assert payload["stability"]["candidate_fingerprint_unique_count"] == 1
    assert len(payload["runs"]) == 3
    assert all(run["promotion_status"] == "candidate_ready" for run in payload["runs"])
    assert all(run["evidence_gap_closed"] is True for run in payload["runs"])
    assert all(run["recovery_verification_gap_closed"] is True for run in payload["runs"])
    assert all(run["score_delta"]["evidence_quality_score"] > 0 for run in payload["runs"])
    assert all(run["score_delta"]["recovery_verification_coverage"] > 0 for run in payload["runs"])
    assert all(gate["passed"] is True for gate in payload["regression_gates"])
    assert payload["boundary"]["regression_gate_only"] is True
    assert payload["boundary"]["production_mutation_enabled"] is False


def test_candidate_benchmark_regression_runner_cli_writes_report(tmp_path: Path) -> None:
    output_json = tmp_path / "p56.json"
    output_md = tmp_path / "p56.md"
    subprocess.run(
        [
            "python",
            "scripts/run_candidate_benchmark_regression_runner.py",
            "--cases",
            str(CASES),
            "--repeat-count",
            "3",
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    markdown = output_md.read_text(encoding="utf-8")
    assert payload["summary"]["passed"] is True
    assert "# OpsCat Candidate Benchmark Regression Runner" in markdown
    assert "Regression gates" in markdown
    assert "Stability" in markdown
    assert render_candidate_benchmark_regression_runner_markdown(payload).startswith("# OpsCat Candidate Benchmark Regression Runner")
