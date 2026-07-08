from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.approval_control_plane import (
    ApprovalControlPlaneReport,
    render_approval_control_plane_markdown,
    run_approval_control_plane_fixture,
)

FIXTURE = Path("evals/approval/p36_profiles.json")


def test_approval_control_plane_routes_shadow_decisions_without_execution() -> None:
    report = run_approval_control_plane_fixture(FIXTURE)
    payload = report.to_dict()

    assert isinstance(report, ApprovalControlPlaneReport)
    assert payload["summary"]["profile_count"] >= 3
    assert payload["summary"]["request_count"] >= 4
    assert payload["summary"]["profile_decision_count"] >= payload["summary"]["request_count"] * 3
    assert payload["score"]["profile_coverage"] == 1.0
    assert payload["score"]["unsafe_auto_action_count"] == 0
    assert payload["score"]["execution_count"] == 0
    assert payload["summary"]["auto_allowed_count"] >= 1
    assert payload["summary"]["approval_required_count"] >= 1
    assert payload["summary"]["blocked_count"] >= 1
    assert payload["boundary"]["approval_control_only"] is True
    assert payload["boundary"]["auth_session_work_enabled"] is False
    assert payload["boundary"]["remediation_execution_enabled"] is False


def test_approval_control_plane_blocks_untrusted_and_shell_like_actions() -> None:
    payload = run_approval_control_plane_fixture(FIXTURE).to_dict()
    decisions = [decision for profile in payload["profiles"] for decision in profile["decisions"]]
    blocked = [decision for decision in decisions if decision["route"] == "blocked"]
    auto_allowed = [decision for decision in decisions if decision["route"] == "auto_allowed"]
    serialized = json.dumps(payload)

    assert any("untrusted_evidence" in decision["reasons"] for decision in blocked)
    assert any(decision["capability"] == "shell" for decision in blocked)
    assert all(decision["capability"] in {"report", "notification_draft", "read_only_diagnostic"} for decision in auto_allowed)
    assert all(decision["executed"] is False for decision in decisions)
    assert "actual-secret-value" not in serialized


def test_approval_control_plane_cli_writes_report(tmp_path: Path) -> None:
    output_json = tmp_path / "p36.json"
    output_md = tmp_path / "p36.md"

    subprocess.run(
        [
            "python",
            "scripts/run_approval_control_plane.py",
            "--fixture",
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
    assert payload["score"]["unsafe_auto_action_count"] == 0
    assert "# OpsCat Approval Control Plane Report" in markdown
    assert "Approval routes" in markdown
    assert render_approval_control_plane_markdown(payload).startswith("# OpsCat Approval Control Plane Report")
