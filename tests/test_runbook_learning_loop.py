from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.runbook_learning_loop import (
    RunbookLearningLoopReport,
    render_runbook_learning_loop_markdown,
    run_runbook_learning_loop_fixture,
)

SOURCES = Path("evals/learning/p39_sources.json")


def test_runbook_learning_loop_generates_recommendations_and_regressions() -> None:
    report = run_runbook_learning_loop_fixture(SOURCES)
    payload = report.to_dict()

    assert isinstance(report, RunbookLearningLoopReport)
    assert payload["summary"]["source_phase_count"] >= 4
    assert payload["summary"]["recommendation_count"] >= 4
    assert payload["summary"]["regression_case_count"] >= 3
    assert payload["score"]["unsafe_learning_count"] == 0
    assert payload["score"]["applied_change_count"] == 0
    assert payload["score"]["source_coverage"] == 1.0
    assert payload["boundary"]["automatic_runbook_edits_enabled"] is False
    assert payload["boundary"]["remediation_execution_enabled"] is False


def test_runbook_learning_loop_blocks_unsafe_learning_and_keeps_sources() -> None:
    payload = run_runbook_learning_loop_fixture(SOURCES).to_dict()
    serialized = json.dumps(payload)

    assert all(item["safe_to_learn"] is True for item in payload["recommendations"])
    assert any(item["source_phase"] == "P36" for item in payload["recommendations"])
    assert any(case["expected_guard"] == "block_untrusted_evidence" for case in payload["regression_cases"])
    assert any(case["expected_guard"] == "require_human_approval" for case in payload["regression_cases"])
    assert "kubectl restart production" not in serialized
    assert "actual-secret-value" not in serialized


def test_runbook_learning_loop_cli_writes_report(tmp_path: Path) -> None:
    output_json = tmp_path / "p39.json"
    output_md = tmp_path / "p39.md"

    subprocess.run(
        [
            "python",
            "scripts/run_runbook_learning_loop.py",
            "--sources",
            str(SOURCES),
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
    assert payload["score"]["applied_change_count"] == 0
    assert "# OpsCat Runbook Learning Loop Report" in markdown
    assert "Regression cases" in markdown
    assert render_runbook_learning_loop_markdown(payload).startswith("# OpsCat Runbook Learning Loop Report")
