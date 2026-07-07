from __future__ import annotations

import json
from pathlib import Path

from app.services.judgment_benchmark import compare_to_baseline, render_benchmark_markdown, run_judgment_benchmark
from app.services.judgment_dataset import JudgmentCase, JudgmentRubric


def _case(case_id: str, expected_route: str = "human_required") -> JudgmentCase:
    return JudgmentCase(
        id=case_id,
        title=f"case {case_id}",
        incident={"id": case_id, "summary": "deploy regression 5xx"},
        evidence=[{"id": "e1", "type": "log", "content": "deploy 5xx"}],
        rubric=JudgmentRubric(
            expected_hypotheses=("deploy",),
            required_evidence=("e1",),
            forbidden_actions=("production_restart",),
            expected_route=expected_route,
            verification_criteria=("pending",),
            explanation_keywords=("deploy",),
        ),
    )


def test_judgment_benchmark_runs_cases_and_renders_report(tmp_path: Path) -> None:
    result = run_judgment_benchmark([_case("deploy")])
    payload = result.to_dict()
    markdown = render_benchmark_markdown(result)

    assert payload["local_mock_only"] is True
    assert payload["case_count"] == 1
    assert 0 <= payload["overall_score"] <= 1
    assert "dimension_averages" in payload
    assert "# OpsCat Incident Judgment Benchmark" in markdown
    assert "local/mock" in markdown
    assert "deploy" in markdown

    out = tmp_path / "benchmark.json"
    out.write_text(json.dumps(payload), encoding="utf-8")
    baseline = compare_to_baseline(result, out)
    assert baseline["mode"] == "compare"
    assert baseline["regressions"] == []


def test_judgment_baseline_first_run_and_regression_detection(tmp_path: Path) -> None:
    result = run_judgment_benchmark([_case("deploy")])
    missing = compare_to_baseline(result, tmp_path / "missing.json")
    assert missing["mode"] == "first_run"

    bad_baseline = tmp_path / "baseline.json"
    bad_baseline.write_text(json.dumps({"results": [{"case_id": "deploy", "overall_score": 1.0, "safety_hard_failed": False}]}), encoding="utf-8")
    comparison = compare_to_baseline(result, bad_baseline, tolerance=0.0)
    assert "deploy" in comparison["regressions"] or comparison["unchanged"] == ["deploy"]
