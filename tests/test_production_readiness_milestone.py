from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.production_readiness_milestone import (
    ProductionReadinessMilestoneReport,
    render_production_readiness_milestone_markdown,
    run_production_readiness_milestone_fixture,
)

SOURCES = Path("evals/readiness/p40_sources.json")


def test_production_readiness_milestone_separates_local_from_production_readiness() -> None:
    report = run_production_readiness_milestone_fixture(SOURCES)
    payload = report.to_dict()

    assert isinstance(report, ProductionReadinessMilestoneReport)
    assert payload["summary"]["gate_count"] >= 8
    assert payload["summary"]["passed_gate_count"] == payload["summary"]["gate_count"]
    assert payload["score"]["boundary_violation_count"] == 0
    assert payload["score"]["production_blocker_count"] >= 1
    assert payload["score"]["readiness_decision"] == "local-portfolio-ready"
    assert payload["score"]["production_autopilot_ready"] is False
    assert payload["boundary"]["unattended_production_operation_claimed"] is False
    assert payload["boundary"]["production_autopilot_enabled"] is False


def test_production_readiness_milestone_contains_gates_blockers_and_evidence() -> None:
    payload = run_production_readiness_milestone_fixture(SOURCES).to_dict()
    gates = {gate["gate_id"]: gate for gate in payload["gates"]}
    blocker_ids = {blocker["id"] for blocker in payload["production_blockers"]}
    serialized = json.dumps(payload)

    for required in [
        "connector_dry_run_ready",
        "read_only_polling_safe",
        "shadow_mode_no_execution",
        "approval_control_safe",
        "oss_config_safe",
        "dashboard_portfolio_ready",
        "learning_loop_safe",
        "full_verification_passed",
    ]:
        assert gates[required]["passed"] is True
    assert "auth_required_for_real_approvals" in blocker_ids
    assert "live_connector_validation_required" in blocker_ids
    assert all(item["artifact"].startswith("/tmp/opscat-") or item["artifact"].startswith("docs/") for item in payload["evidence_bundle"])
    assert "actual-secret-value" not in serialized


def test_production_readiness_milestone_cli_writes_report(tmp_path: Path) -> None:
    output_json = tmp_path / "p40.json"
    output_md = tmp_path / "p40.md"

    subprocess.run(
        [
            "python",
            "scripts/run_production_readiness_milestone.py",
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
    assert payload["score"]["readiness_decision"] == "local-portfolio-ready"
    assert "# OpsCat Production-readiness Milestone Bundle" in markdown
    assert "Production blockers" in markdown
    assert render_production_readiness_milestone_markdown(payload).startswith("# OpsCat Production-readiness Milestone Bundle")
