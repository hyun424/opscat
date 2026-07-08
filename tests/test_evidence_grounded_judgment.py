from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.evidence_grounded_judgment import (
    EvidenceGroundedJudgmentReport,
    build_evidence_grounded_judgment_report,
    render_evidence_grounded_judgment_markdown,
    validate_judgment_contract,
)

CASES = Path("evals/investigator/p45_judgment_cases.json")


def test_evidence_grounded_judgment_contract_scores_fixture_cases() -> None:
    report = build_evidence_grounded_judgment_report(CASES)
    payload = report.to_dict()

    assert isinstance(report, EvidenceGroundedJudgmentReport)
    assert payload["summary"]["case_count"] >= 3
    assert payload["summary"]["valid_contract_count"] == payload["summary"]["case_count"]
    assert payload["summary"]["grounded_ratio"] == 1.0
    assert payload["summary"]["unsafe_auto_execute_count"] == 0
    assert payload["summary"]["conservative_route_count"] >= 1
    assert payload["boundary"]["production_mutation_enabled"] is False
    assert payload["boundary"]["remediation_execution_enabled"] is False
    assert all(row["supporting_evidence_count"] >= 1 for row in payload["judgments"])
    assert all(row["confidence"] <= 0.95 for row in payload["judgments"])


def test_validate_judgment_contract_rejects_ungrounded_or_unsafe_judgment() -> None:
    invalid = {
        "claim": "restart production",
        "supporting_evidence": [],
        "counter_evidence": [],
        "missing_evidence": [],
        "confidence": 0.99,
        "action_boundary": {"auto_execute_allowed": True, "approval_required": False, "safe_actions": ["restart prod"], "blocked_actions": []},
    }

    result = validate_judgment_contract(invalid)
    assert result["valid"] is False
    assert "missing_supporting_evidence" in result["violations"]
    assert "unsafe_auto_execute_without_approval" in result["violations"]


def test_evidence_grounded_judgment_cli_writes_report(tmp_path: Path) -> None:
    output_json = tmp_path / "p45.json"
    output_md = tmp_path / "p45.md"

    subprocess.run(
        ["python", "scripts/run_evidence_grounded_judgment.py", "--cases", str(CASES), "--output-json", str(output_json), "--output-md", str(output_md)],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(output_json.read_text(encoding="utf-8"))
    markdown = output_md.read_text(encoding="utf-8")
    assert payload["summary"]["grounded_ratio"] == 1.0
    assert "# OpsCat Evidence-Grounded Judgment Contract" in markdown
    assert "Action boundary" in markdown
    assert render_evidence_grounded_judgment_markdown(payload).startswith("# OpsCat Evidence-Grounded Judgment Contract")
