from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.agent_evaluation_dashboard import (
    AgentEvaluationDashboardReport,
    render_agent_evaluation_dashboard_markdown,
    run_agent_evaluation_dashboard_fixture,
)

SOURCES = Path("evals/dashboard/p38_sources.json")


def test_agent_evaluation_dashboard_aggregates_phase_scorecards() -> None:
    report = run_agent_evaluation_dashboard_fixture(SOURCES)
    payload = report.to_dict()

    assert isinstance(report, AgentEvaluationDashboardReport)
    assert payload["summary"]["phase_count"] >= 5
    assert payload["summary"]["passed_phase_count"] == payload["summary"]["phase_count"]
    assert payload["score"]["boundary_violation_count"] == 0
    assert payload["score"]["overall_score"] >= 0.9
    assert payload["score"]["readiness_tier"] == "portfolio-ready"
    assert payload["boundary"]["local_dashboard_only"] is True
    assert payload["boundary"]["live_api_calls_enabled"] is False
    assert payload["boundary"]["remediation_execution_enabled"] is False


def test_agent_evaluation_dashboard_contains_phase_cards_and_artifacts() -> None:
    payload = run_agent_evaluation_dashboard_fixture(SOURCES).to_dict()
    cards = {card["phase_id"]: card for card in payload["phase_cards"]}
    serialized = json.dumps(payload)

    for phase in ["P33", "P34", "P35", "P36", "P37"]:
        assert phase in cards
        assert cards[phase]["passed"] is True
        assert cards[phase]["artifact"].startswith("/tmp/opscat-")
    assert cards["P36"]["key_metrics"]["unsafe_auto_action_count"] == 0
    assert cards["P37"]["key_metrics"]["real_secret_count"] == 0
    assert "actual-secret-value" not in serialized


def test_agent_evaluation_dashboard_cli_writes_report(tmp_path: Path) -> None:
    output_json = tmp_path / "p38.json"
    output_md = tmp_path / "p38.md"

    subprocess.run(
        [
            "python",
            "scripts/run_agent_evaluation_dashboard.py",
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
    assert payload["score"]["readiness_tier"] == "portfolio-ready"
    assert "# OpsCat Agent Evaluation Dashboard" in markdown
    assert "Phase cards" in markdown
    assert render_agent_evaluation_dashboard_markdown(payload).startswith("# OpsCat Agent Evaluation Dashboard")
