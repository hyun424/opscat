from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.failure_mining_loop import FailureMiningLoopReport, build_failure_mining_loop_report, render_failure_mining_loop_markdown

CASES = Path("evals/investigator/p51_operator_judgment_benchmark_v2_cases.json")


def test_failure_mining_loop_generates_improvement_tickets_and_regression_cases() -> None:
    report = build_failure_mining_loop_report(CASES)
    payload = report.to_dict()

    assert isinstance(report, FailureMiningLoopReport)
    assert payload["summary"]["source_case_count"] == 4
    assert payload["summary"]["failure_cluster_count"] >= 2
    assert payload["summary"]["improvement_ticket_count"] >= 2
    assert payload["summary"]["regression_case_count"] >= 3
    assert payload["summary"]["highest_priority"] in {"P0", "P1", "P2"}
    assert payload["summary"]["unsafe_action_count"] == 0
    assert "evidence_gap" in payload["failure_clusters"]
    assert "recovery_verification_gap" in payload["failure_clusters"]
    assert all(ticket["acceptance_criteria"] for ticket in payload["improvement_tickets"])
    assert all(case["source_case_id"] for case in payload["regression_cases"])


def test_failure_mining_loop_cli_writes_report(tmp_path: Path) -> None:
    output_json = tmp_path / "p52.json"
    output_md = tmp_path / "p52.md"
    subprocess.run(
        [
            "python",
            "scripts/run_failure_mining_loop.py",
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
    assert "# OpsCat Failure Mining Loop" in markdown
    assert "Improvement tickets" in markdown
    assert "Regression cases" in markdown
    assert render_failure_mining_loop_markdown(payload).startswith("# OpsCat Failure Mining Loop")
