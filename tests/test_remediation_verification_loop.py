from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.remediation_verification_loop import (
    RemediationVerificationLoopReport,
    build_remediation_verification_loop_report,
    render_remediation_verification_loop_markdown,
)

CASES = Path("evals/investigator/p49_remediation_verification_cases.json")


def test_remediation_verification_loop_requires_precheck_and_postcheck() -> None:
    report = build_remediation_verification_loop_report(CASES)
    payload = report.to_dict()

    assert isinstance(report, RemediationVerificationLoopReport)
    assert payload["summary"]["case_count"] >= 2
    assert payload["summary"]["precheck_pass_count"] >= 1
    assert payload["summary"]["recovery_verified_count"] >= 1
    assert payload["summary"]["failed_verification_escalation_count"] >= 1
    assert payload["summary"]["production_execution_count"] == 0
    assert payload["summary"]["unsafe_action_count"] == 0
    for case in payload["cases"]:
        assert case["precheck"]
        assert case["postcheck"]
        assert case["verification_status"] in {"recovered", "not_recovered"}
        assert case["rollback_or_escalation"]
        assert case["execution_boundary"]["production_execution_allowed"] is False


def test_remediation_verification_loop_cli_writes_report(tmp_path: Path) -> None:
    output_json = tmp_path / "p49.json"
    output_md = tmp_path / "p49.md"
    subprocess.run(
        [
            "python",
            "scripts/run_remediation_verification_loop.py",
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
    assert "# OpsCat Remediation Verification Loop" in markdown
    assert "Pre-check" in markdown
    assert "Post-check" in markdown
    assert render_remediation_verification_loop_markdown(payload).startswith("# OpsCat Remediation Verification Loop")
