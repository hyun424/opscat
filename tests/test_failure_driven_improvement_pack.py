from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.failure_driven_improvement_pack import (
    FailureDrivenImprovementPackReport,
    build_failure_driven_improvement_pack_report,
    render_failure_driven_improvement_pack_markdown,
)

CASES = Path("evals/investigator/p51_operator_judgment_benchmark_v2_cases.json")


def test_failure_driven_improvement_pack_closes_mined_gap_types_in_projection() -> None:
    report = build_failure_driven_improvement_pack_report(CASES)
    payload = report.to_dict()

    assert isinstance(report, FailureDrivenImprovementPackReport)
    assert payload["summary"]["source_failure_cluster_count"] == 2
    assert payload["summary"]["improvement_plan_count"] == 2
    assert payload["summary"]["evidence_probe_count"] >= 3
    assert payload["summary"]["recovery_check_count"] >= 4
    assert payload["summary"]["regression_case_count"] == 3
    assert payload["summary"]["unsafe_action_count"] == 0
    assert payload["projected_score_impact"]["evidence_gap"]["before"] == 1
    assert payload["projected_score_impact"]["evidence_gap"]["after"] == 0
    assert payload["projected_score_impact"]["recovery_verification_gap"]["before"] == 2
    assert payload["projected_score_impact"]["recovery_verification_gap"]["after"] == 0
    assert all(plan["acceptance_criteria"] for plan in payload["improvement_plans"])
    assert all(plan["validation_command"] for plan in payload["improvement_plans"])


def test_failure_driven_improvement_pack_cli_writes_report(tmp_path: Path) -> None:
    output_json = tmp_path / "p53.json"
    output_md = tmp_path / "p53.md"
    subprocess.run(
        [
            "python",
            "scripts/run_failure_driven_improvement_pack.py",
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
    assert "# OpsCat Failure-Driven Improvement Pack" in markdown
    assert "Evidence probes" in markdown
    assert "Recovery checks" in markdown
    assert render_failure_driven_improvement_pack_markdown(payload).startswith("# OpsCat Failure-Driven Improvement Pack")
