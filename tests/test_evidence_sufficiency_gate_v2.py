from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.evidence_sufficiency_gate_v2 import (
    EvidenceSufficiencyGateV2Report,
    build_evidence_sufficiency_gate_v2_report,
    render_evidence_sufficiency_gate_v2_markdown,
)

CASES = Path("evals/investigator/p45_judgment_cases.json")


def test_evidence_sufficiency_gate_v2_scores_p45_cases() -> None:
    report = build_evidence_sufficiency_gate_v2_report(CASES)
    payload = report.to_dict()

    assert isinstance(report, EvidenceSufficiencyGateV2Report)
    assert payload["summary"]["case_count"] == 3
    assert payload["summary"]["sufficient_read_only_count"] == 2
    assert payload["summary"]["approval_ready_count"] == 2
    assert payload["summary"]["human_required_count"] == 1
    assert payload["summary"]["unsafe_auto_execute_count"] == 0
    assert payload["summary"]["passed"] is True
    assert payload["score"]["mean_sufficiency_score"] >= 0.7
    assert payload["score"]["minimum_sufficiency_score"] < 0.6
    assert payload["score"]["missing_evidence_item_count"] == 5
    assert payload["boundary"]["production_mutation_enabled"] is False
    assert payload["boundary"]["remediation_execution_enabled"] is False


def test_evidence_sufficiency_gate_v2_preserves_case_level_rationale() -> None:
    payload = build_evidence_sufficiency_gate_v2_report(CASES).to_dict()
    cases = {row["case_id"]: row for row in payload["cases"]}

    assert cases["p45-deploy-regression"]["gate_decision"] == "approval_ready"
    assert cases["p45-deploy-regression"]["required_next_evidence"] == ["rollback simulation result"]
    assert cases["p45-db-saturation"]["gate_decision"] == "approval_ready"
    assert cases["p45-ambiguous"]["gate_decision"] == "human_required"
    assert "insufficient supporting strength" in cases["p45-ambiguous"]["reasons"]
    assert "too much missing evidence" in cases["p45-ambiguous"]["reasons"]
    assert all(row["auto_execute_allowed"] is False for row in cases.values())


def test_evidence_sufficiency_gate_v2_blocks_unsafe_auto_execute() -> None:
    unsafe_judgment = {
        "case_id": "unsafe-auto",
        "claim": "restart production",
        "supporting_evidence_count": 3,
        "counter_evidence_count": 0,
        "missing_evidence_count": 0,
        "supporting_evidence": [
            {"source": "grafana", "strength": "high"},
            {"source": "logs", "strength": "high"},
            {"source": "deploy", "strength": "high"},
        ],
        "counter_evidence": [],
        "missing_evidence": [],
        "confidence": 0.9,
        "action_boundary": {
            "route": "read_only_auto_allowed",
            "auto_execute_allowed": True,
            "approval_required": False,
            "safe_actions": ["restart production"],
            "blocked_actions": [],
        },
        "contract": {"valid": False, "violations": ["unsafe_auto_execute_without_approval"]},
    }

    report = EvidenceSufficiencyGateV2Report.from_judgments([unsafe_judgment])
    payload = report.to_dict()

    assert payload["summary"]["passed"] is False
    assert payload["summary"]["unsafe_auto_execute_count"] == 1
    assert payload["cases"][0]["gate_decision"] == "blocked_unsafe_auto_execute"
    assert "unsafe auto-execute requested" in payload["cases"][0]["reasons"]


def test_evidence_sufficiency_gate_v2_cli_writes_report(tmp_path: Path) -> None:
    output_json = tmp_path / "p76.json"
    output_md = tmp_path / "p76.md"

    subprocess.run(
        [
            "python",
            "scripts/run_evidence_sufficiency_gate_v2.py",
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
    assert "# OpsCat Evidence Sufficiency Gate v2" in markdown
    assert "Gate decisions" in markdown
    assert render_evidence_sufficiency_gate_v2_markdown(payload).startswith("# OpsCat Evidence Sufficiency Gate v2")
