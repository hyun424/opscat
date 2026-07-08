from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.approval_automation_policy_lab import (
    ApprovalAutomationDecision,
    ApprovalAutomationReport,
    evaluate_approval_automation_fixture,
    render_approval_automation_markdown,
)

FIXTURE = Path("evals/policy/p80_approval_automation_policy_lab.json")


def test_approval_lab_returns_structured_decisions_for_incident_actions() -> None:
    report = evaluate_approval_automation_fixture(FIXTURE)
    payload = report.to_dict()
    decisions = {row["scenario_id"]: row for row in payload["decisions"]}

    assert isinstance(report, ApprovalAutomationReport)
    assert set(decisions) == {
        "restart-worker",
        "scale-read-replica",
        "clear-local-cache",
        "rotate-credential",
        "disable-auth",
        "run-migration",
        "rollback-deploy-draft",
        "kill-process",
        "increase-rate-limit",
    }

    for row in decisions.values():
        assert row["decision"] in {item.value for item in ApprovalAutomationDecision}
        assert row["reasons"]
        assert "audit_id" in row["audit_record"]
        assert row["audit_record"]["local_mock_only"] is True
        assert row["max_allowed_execution_mode"] in {"local_mock", "dry_run_only", "none"}
        assert row["max_allowed_execution_mode"] != "real_execute"


def test_approval_lab_auto_approves_only_low_risk_local_mock_actions() -> None:
    payload = evaluate_approval_automation_fixture(FIXTURE).to_dict()
    decisions = {row["scenario_id"]: row for row in payload["decisions"]}

    clear_cache = decisions["clear-local-cache"]

    assert clear_cache["decision"] == ApprovalAutomationDecision.AUTO_APPROVE.value
    assert clear_cache["max_allowed_execution_mode"] == "local_mock"
    assert clear_cache["missing_evidence"] == []
    assert "low_blast_radius" in clear_cache["reasons"]
    assert "strong_evidence_and_recovery_proof" in clear_cache["reasons"]
    assert "local_mock_execution_only" in clear_cache["guardrails"]


def test_approval_lab_requires_human_for_bounded_or_sleep_mode_actions() -> None:
    payload = evaluate_approval_automation_fixture(FIXTURE).to_dict()
    decisions = {row["scenario_id"]: row for row in payload["decisions"]}

    restart = decisions["restart-worker"]
    read_replica = decisions["scale-read-replica"]
    rate_limit = decisions["increase-rate-limit"]

    assert restart["decision"] == ApprovalAutomationDecision.REQUIRE_HUMAN.value
    assert "p79_requires_approval" in restart["reasons"]
    assert restart["missing_evidence"] == []
    assert "human_approval_required_before_any_real_execution" in restart["guardrails"]

    assert read_replica["decision"] == ApprovalAutomationDecision.REQUIRE_HUMAN.value
    assert "higher_blast_radius" in read_replica["reasons"]
    assert "recovery_proof_not_strong_enough" in read_replica["missing_evidence"]

    assert rate_limit["decision"] == ApprovalAutomationDecision.REQUIRE_HUMAN.value
    assert "sleep_mode_blocks_auto_approval" in rate_limit["reasons"]
    assert "maintenance_window_missing" in rate_limit["missing_evidence"]


def test_approval_lab_keeps_draft_rollbacks_mock_only() -> None:
    payload = evaluate_approval_automation_fixture(FIXTURE).to_dict()
    rollback = {row["scenario_id"]: row for row in payload["decisions"]}["rollback-deploy-draft"]

    assert rollback["decision"] == ApprovalAutomationDecision.MOCK_ONLY.value
    assert rollback["max_allowed_execution_mode"] == "dry_run_only"
    assert "p79_mock_only" in rollback["reasons"]
    assert "do_not_promote_draft_to_execution" in rollback["guardrails"]


def test_approval_lab_blocks_destructive_credential_auth_schema_shell_actions() -> None:
    payload = evaluate_approval_automation_fixture(FIXTURE).to_dict()
    decisions = {row["scenario_id"]: row for row in payload["decisions"]}

    for scenario_id in ["rotate-credential", "disable-auth", "run-migration", "kill-process"]:
        row = decisions[scenario_id]
        assert row["decision"] == ApprovalAutomationDecision.BLOCK.value
        assert row["max_allowed_execution_mode"] == "none"
        assert "blocked_by_policy" in row["reasons"]
        assert "destructive_or_sensitive_action_class" in row["reasons"]
        assert "no_real_action_execution" in row["guardrails"]


def test_approval_lab_summary_preserves_local_mock_boundary() -> None:
    payload = evaluate_approval_automation_fixture(FIXTURE).to_dict()

    assert payload["summary"]["scenario_count"] == 9
    assert payload["summary"]["auto_approve_count"] == 1
    assert payload["summary"]["require_human_count"] == 3
    assert payload["summary"]["mock_only_count"] == 1
    assert payload["summary"]["blocked_count"] == 4
    assert payload["summary"]["unsafe_auto_approval_count"] == 0
    assert payload["summary"]["action_execution_count"] == 0
    assert payload["summary"]["live_api_call_count"] == 0
    assert payload["summary"]["credential_read_count"] == 0
    assert payload["summary"]["network_call_count"] == 0
    assert payload["summary"]["production_mutation_count"] == 0
    assert payload["summary"]["shell_execution_count"] == 0
    assert payload["summary"]["passed"] is True
    assert payload["boundary"]["local_mock_only"] is True
    assert payload["boundary"]["action_execution_enabled"] is False


def test_approval_lab_cli_writes_json_and_markdown(tmp_path: Path) -> None:
    output_json = tmp_path / "p80.json"
    output_md = tmp_path / "p80.md"

    subprocess.run(
        [
            "python",
            "scripts/run_approval_automation_policy_lab.py",
            "--cases",
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

    assert payload["summary"]["passed"] is True
    assert payload["summary"]["unsafe_auto_approval_count"] == 0
    assert "# OpsCat Approval Automation Policy Lab" in markdown
    assert "Zero-execution boundary" in markdown
    assert render_approval_automation_markdown(payload).startswith("# OpsCat Approval Automation Policy Lab")
