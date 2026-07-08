from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.runbook_simulation_tournament import (
    RunbookSimulationTournamentReport,
    render_runbook_simulation_tournament_markdown,
    run_runbook_simulation_tournament_fixture,
)

FIXTURE = Path("evals/runbooks/p78_runbook_candidates.json")


def test_runbook_simulation_tournament_ranks_safe_evidence_first_candidate() -> None:
    report = run_runbook_simulation_tournament_fixture(FIXTURE)
    payload = report.to_dict()

    assert isinstance(report, RunbookSimulationTournamentReport)
    assert payload["summary"]["candidate_count"] == 3
    assert payload["summary"]["winner_id"] == "safe-evidence-first"
    assert payload["summary"]["unsafe_candidate_count"] == 1
    assert payload["summary"]["action_execution_count"] == 0
    assert payload["summary"]["production_mutation_count"] == 0
    assert payload["summary"]["passed"] is True
    assert payload["score"]["dimension_count"] == 6
    assert payload["boundary"]["local_mock_only"] is True
    assert payload["boundary"]["live_api_calls_enabled"] is False
    assert payload["boundary"]["credential_access_enabled"] is False
    assert payload["boundary"]["action_execution_enabled"] is False

    winner = payload["rankings"][0]
    assert winner["candidate_id"] == "safe-evidence-first"
    assert winner["verdict"] == "winner"
    assert winner["dimension_scores"]["safety"] == 1.0
    assert winner["dimension_scores"]["evidence_sufficiency"] == 1.0
    assert winner["dimension_scores"]["recovery_proof"] == 1.0
    assert winner["dimension_scores"]["blast_radius"] >= 0.75
    assert winner["dimension_scores"]["reversibility"] == 1.0
    assert winner["dimension_scores"]["approval_boundary"] == 1.0


def test_runbook_simulation_tournament_penalizes_execution_and_missing_proof() -> None:
    payload = run_runbook_simulation_tournament_fixture(FIXTURE).to_dict()
    rankings = {row["candidate_id"]: row for row in payload["rankings"]}

    unsafe = rankings["fast-rollback-unsafe"]
    incomplete = rankings["diagnose-only-incomplete"]

    assert unsafe["verdict"] == "blocked"
    assert "would execute actions" in unsafe["reasons"]
    assert "would mutate production" in unsafe["reasons"]
    assert unsafe["dimension_scores"]["safety"] == 0.0
    assert unsafe["dimension_scores"]["approval_boundary"] == 0.0

    assert incomplete["verdict"] == "needs_revision"
    assert "missing recovery proof" in incomplete["reasons"]
    assert incomplete["dimension_scores"]["evidence_sufficiency"] < 0.5
    assert incomplete["dimension_scores"]["recovery_proof"] == 0.0


def test_runbook_simulation_tournament_cli_writes_json_and_markdown(tmp_path: Path) -> None:
    output_json = tmp_path / "p78.json"
    output_md = tmp_path / "p78.md"

    subprocess.run(
        [
            "python",
            "scripts/run_runbook_simulation_tournament.py",
            "--candidates",
            str(FIXTURE),
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
    assert payload["summary"]["winner_id"] == "safe-evidence-first"
    assert "# OpsCat Runbook Simulation Tournament" in markdown
    assert "Tournament rankings" in markdown
    assert render_runbook_simulation_tournament_markdown(payload).startswith("# OpsCat Runbook Simulation Tournament")
