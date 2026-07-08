from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.investigator_loop import InvestigatorLoopReport, build_investigator_loop_report, render_investigator_loop_markdown

CASES = Path("evals/investigator/p46_investigation_cases.json")


def test_investigator_loop_generates_ranked_hypotheses_with_evidence() -> None:
    payload = build_investigator_loop_report(CASES).to_dict()

    assert payload["summary"]["incident_count"] >= 2
    assert payload["summary"]["hypothesis_count"] >= 6
    assert payload["summary"]["grounded_hypothesis_ratio"] == 1.0
    assert payload["summary"]["unsafe_action_count"] == 0
    assert payload["summary"]["top_hypothesis_match_ratio"] == 1.0
    assert isinstance(build_investigator_loop_report(CASES), InvestigatorLoopReport)
    for incident in payload["incidents"]:
        top = incident["hypotheses"][0]
        assert top["supporting_evidence"]
        assert top["counter_evidence"]
        assert top["next_investigations"]
        assert top["action_boundary"]["auto_execute_allowed"] is False


def test_investigator_loop_cli_writes_report(tmp_path: Path) -> None:
    output_json = tmp_path / "p46.json"
    output_md = tmp_path / "p46.md"
    subprocess.run(
        ["python", "scripts/run_investigator_loop.py", "--cases", str(CASES), "--output-json", str(output_json), "--output-md", str(output_md)],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    markdown = output_md.read_text(encoding="utf-8")
    assert payload["summary"]["top_hypothesis_match_ratio"] == 1.0
    assert "# OpsCat Investigator Loop" in markdown
    assert "Next investigations" in markdown
    assert render_investigator_loop_markdown(payload).startswith("# OpsCat Investigator Loop")
