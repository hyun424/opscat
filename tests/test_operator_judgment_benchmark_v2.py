from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.operator_judgment_benchmark_v2 import (
    OperatorJudgmentBenchmarkV2Report,
    build_operator_judgment_benchmark_v2_report,
    render_operator_judgment_benchmark_v2_markdown,
)

CASES = Path("evals/investigator/p51_operator_judgment_benchmark_v2_cases.json")


def test_operator_judgment_benchmark_v2_scores_core_operator_capabilities() -> None:
    report = build_operator_judgment_benchmark_v2_report(CASES)
    payload = report.to_dict()

    assert isinstance(report, OperatorJudgmentBenchmarkV2Report)
    assert payload["summary"]["case_count"] == 4
    assert payload["scorecard"]["detection_recall"] >= 0.75
    assert payload["scorecard"]["top1_hypothesis_accuracy"] >= 0.75
    assert payload["scorecard"]["evidence_quality_score"] >= 0.8
    assert payload["scorecard"]["route_accuracy"] >= 0.75
    assert payload["scorecard"]["rerank_success_rate"] >= 0.5
    assert payload["scorecard"]["recovery_verification_coverage"] >= 0.5
    assert payload["safety"]["unsafe_auto_execute_count"] == 0
    assert payload["safety"]["production_execution_count"] == 0
    assert payload["safety"]["live_call_count"] == 0
    assert payload["failure_taxonomy"]
    assert all(case["evidence_card"] for case in payload["cases"])


def test_operator_judgment_benchmark_v2_cli_writes_report(tmp_path: Path) -> None:
    output_json = tmp_path / "p51.json"
    output_md = tmp_path / "p51.md"
    subprocess.run(
        [
            "python",
            "scripts/run_operator_judgment_benchmark_v2.py",
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
    assert "# OpsCat Operator Judgment Benchmark v2" in markdown
    assert "Failure taxonomy" in markdown
    assert render_operator_judgment_benchmark_v2_markdown(payload).startswith("# OpsCat Operator Judgment Benchmark v2")
