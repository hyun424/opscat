from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.failure_driven_benchmark_improvement import (
    FailureDrivenBenchmarkImprovementReport,
    build_failure_driven_benchmark_improvement_report,
    render_failure_driven_benchmark_improvement_markdown,
)

CASES = Path("evals/investigator/p51_operator_judgment_benchmark_v2_cases.json")


def test_failure_driven_benchmark_improvement_closes_projected_gaps_without_mutating_baseline() -> None:
    report = build_failure_driven_benchmark_improvement_report(CASES)
    payload = report.to_dict()

    assert isinstance(report, FailureDrivenBenchmarkImprovementReport)
    assert payload["summary"]["case_count"] == 4
    assert payload["summary"]["applied_improvement_count"] >= 3
    assert payload["summary"]["baseline_preserved"] is True
    assert payload["baseline_failure_taxonomy"]["evidence_gap"] == 1
    assert payload["baseline_failure_taxonomy"]["recovery_verification_gap"] == 2
    assert payload["improved_failure_taxonomy"]["evidence_gap"] == 0
    assert payload["improved_failure_taxonomy"]["recovery_verification_gap"] == 0
    assert payload["score_delta"]["evidence_quality_score"] > 0
    assert payload["score_delta"]["recovery_verification_coverage"] > 0
    assert payload["safety"]["unsafe_auto_execute_count"] == 0
    assert payload["safety"]["production_execution_count"] == 0
    assert payload["safety"]["live_call_count"] == 0
    assert all(case["applied_improvements"] for case in payload["improved_cases"] if case["case_id"] in payload["improved_case_ids"])


def test_failure_driven_benchmark_improvement_cli_writes_report(tmp_path: Path) -> None:
    output_json = tmp_path / "p54.json"
    output_md = tmp_path / "p54.md"
    subprocess.run(
        [
            "python",
            "scripts/run_failure_driven_benchmark_improvement.py",
            "--cases",
            str(CASES),
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
    assert "# OpsCat Failure-Driven Benchmark Improvement" in markdown
    assert "Gap closure" in markdown
    assert "Score delta" in markdown
    assert render_failure_driven_benchmark_improvement_markdown(payload).startswith("# OpsCat Failure-Driven Benchmark Improvement")
