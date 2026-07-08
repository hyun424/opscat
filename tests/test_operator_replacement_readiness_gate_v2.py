from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.operator_replacement_readiness_gate_v2 import (
    OperatorReplacementReadinessGateV2Report,
    build_operator_replacement_readiness_gate_v2_report,
    render_operator_replacement_readiness_gate_v2_markdown,
)

CASES = Path("evals/investigator/p51_operator_judgment_benchmark_v2_cases.json")
MANIFEST = Path("evals/real_datasets/external/p44_benchmark_matrix_manifest.json")
JUDGMENT_CASES = Path("evals/judgment/seed/cases.json")


def test_operator_replacement_readiness_gate_marks_local_ready_but_production_blocked() -> None:
    report = build_operator_replacement_readiness_gate_v2_report(CASES, MANIFEST, JUDGMENT_CASES, max_cases=4)
    payload = report.to_dict()

    assert isinstance(report, OperatorReplacementReadinessGateV2Report)
    assert payload["summary"]["passed"] is True
    assert payload["summary"]["hybrid_comparator_passed"] is True
    assert payload["summary"]["local_operator_replacement_ready"] is True
    assert payload["summary"]["unattended_production_ready"] is False
    assert payload["summary"]["recommended_mode"] == "local_shadow_operator_replacement"
    assert payload["summary"]["readiness_level"] == "shadow_ready_production_blocked"
    assert payload["summary"]["safety_regression_count"] == 0
    assert payload["summary"]["action_execution_count"] == 0
    assert set(payload["production_blockers"]) >= {
        "live_connector_validation_required",
        "auth_session_controls_required",
        "production_execution_controls_required",
        "human_escalation_contract_required",
    }
    assert payload["readiness_scorecard"]["candidate_regression"] is True
    assert payload["readiness_scorecard"]["real_dataset_bridge"] is True
    assert payload["readiness_scorecard"]["llm_harness"] is True
    assert payload["readiness_scorecard"]["hybrid_comparator"] is True
    assert all(gate["passed"] is True for gate in payload["readiness_gates"])
    assert payload["boundary"]["operator_replacement_readiness_gate_only"] is True
    assert payload["boundary"]["unattended_production_operation_claimed"] is False


def test_operator_replacement_readiness_gate_cli_writes_report(tmp_path: Path) -> None:
    output_json = tmp_path / "p60.json"
    output_md = tmp_path / "p60.md"
    subprocess.run(
        [
            "python",
            "scripts/run_operator_replacement_readiness_gate_v2.py",
            "--cases",
            str(CASES),
            "--manifest",
            str(MANIFEST),
            "--judgment-cases",
            str(JUDGMENT_CASES),
            "--max-cases",
            "4",
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
    assert "# OpsCat Operator Replacement Readiness Gate v2" in markdown
    assert "Production blockers" in markdown
    assert "Readiness gates" in markdown
    assert render_operator_replacement_readiness_gate_v2_markdown(payload).startswith("# OpsCat Operator Replacement Readiness Gate v2")
