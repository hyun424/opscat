from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.rollback_pr_draft_automation import (
    RollbackDraftDecision,
    RollbackPrDraftReport,
    evaluate_rollback_pr_draft_fixture,
    render_rollback_pr_draft_markdown,
)

FIXTURE = Path("evals/policy/p81_rollback_pr_draft_automation.json")


def test_rollback_pr_draft_builds_structured_artifacts_for_safe_scenarios() -> None:
    report = evaluate_rollback_pr_draft_fixture(FIXTURE)
    payload = report.to_dict()
    drafts = {row["scenario_id"]: row for row in payload["drafts"]}

    assert isinstance(report, RollbackPrDraftReport)
    assert set(drafts) == {
        "safe-config-rollback",
        "deploy-revert-draft",
        "migration-rollback-human",
        "credential-auth-rollback-blocked",
        "insufficient-evidence-rejected",
    }

    for row in drafts.values():
        assert row["decision"] in {item.value for item in RollbackDraftDecision}
        assert row["draft_only"] is True
        assert row["human_approval_required"] is True
        assert row["audit_metadata"]["local_mock_only"] is True
        assert row["execution_plan"]["execution_count"] == 0
        assert row["execution_plan"]["shell_execution_count"] == 0
        assert row["required_human_approval"]
        assert row["verification_checklist"]
        assert row["rollback_abort_plan"]
        assert row["evidence_references"]
        assert row["risk"]

    config = drafts["safe-config-rollback"]
    assert config["decision"] == RollbackDraftDecision.DRAFT_READY.value
    assert config["title"] == "Draft rollback PR: restore checkout-api feature flag defaults"
    assert config["summary"].startswith("Prepare a human-reviewed rollback PR")
    assert config["proposed_file_changes"] == [
        {
            "path": "config/checkout-api/local-mock.yaml",
            "change": "Set enable_new_checkout=false and restore timeout_ms=2500 in the proposed PR text.",
        }
    ]
    assert config["command_plan"] == []
    assert "p80_auto_approve_downgraded_to_draft_only" in config["reasons"]
    assert "p81_draft_only_no_external_execution_configured" in config["guardrails"]


def test_rollback_pr_draft_handles_deploy_and_migration_human_review_paths() -> None:
    payload = evaluate_rollback_pr_draft_fixture(FIXTURE).to_dict()
    drafts = {row["scenario_id"]: row for row in payload["drafts"]}

    deploy = drafts["deploy-revert-draft"]
    migration = drafts["migration-rollback-human"]

    assert deploy["decision"] == RollbackDraftDecision.DRAFT_READY.value
    assert deploy["approval_source"]["p80_decision"] == "mock_only"
    assert deploy["command_plan"] == [
        "Draft-only text: propose reverting deploy checkout-api@2026.07.08.3 to checkout-api@2026.07.08.2.",
        "Draft-only text: request reviewer to run provider-specific deployment checks after approval.",
    ]
    assert deploy["proposed_file_changes"] == []
    assert "p80_mock_only_requires_draft_boundary" in deploy["reasons"]

    assert migration["decision"] == RollbackDraftDecision.HUMAN_REVIEW_REQUIRED.value
    assert migration["approval_source"]["p80_decision"] == "require_human"
    assert migration["required_human_approval"]["approval_type"] == "database_owner_review"
    assert "schema_or_migration_requires_human_review" in migration["reasons"]
    assert "migration backup verified" in migration["verification_checklist"]


def test_rollback_pr_draft_blocks_or_rejects_unsafe_and_unsupported_scenarios() -> None:
    payload = evaluate_rollback_pr_draft_fixture(FIXTURE).to_dict()
    drafts = {row["scenario_id"]: row for row in payload["drafts"]}

    credential = drafts["credential-auth-rollback-blocked"]
    insufficient = drafts["insufficient-evidence-rejected"]

    assert credential["decision"] == RollbackDraftDecision.BLOCKED.value
    assert credential["approval_source"]["p80_decision"] == "block"
    assert credential["proposed_file_changes"] == []
    assert credential["command_plan"] == []
    assert "credential_or_auth_rollback_blocked" in credential["reasons"]
    assert "blocked_items_cannot_be_promoted_to_pr" in credential["guardrails"]

    assert insufficient["decision"] == RollbackDraftDecision.REJECTED.value
    assert "insufficient_evidence_for_safe_draft" in insufficient["reasons"]
    assert "collect deploy diff, recovery proof, and blast radius evidence" in insufficient["rollback_abort_plan"]
    assert insufficient["required_human_approval"]["approval_type"] == "evidence_owner_review"


def test_rollback_pr_draft_summary_preserves_zero_execution_boundary() -> None:
    payload = evaluate_rollback_pr_draft_fixture(FIXTURE).to_dict()

    assert payload["summary"]["scenario_count"] == 5
    assert payload["summary"]["draft_ready_count"] == 2
    assert payload["summary"]["human_review_required_count"] == 1
    assert payload["summary"]["blocked_count"] == 1
    assert payload["summary"]["rejected_count"] == 1
    assert payload["summary"]["required_human_approval_count"] == 5
    assert payload["summary"]["action_execution_count"] == 0
    assert payload["summary"]["live_api_call_count"] == 0
    assert payload["summary"]["credential_read_count"] == 0
    assert payload["summary"]["network_call_count"] == 0
    assert payload["summary"]["production_mutation_count"] == 0
    assert payload["summary"]["shell_execution_count"] == 0
    assert payload["summary"]["branch_creation_count"] == 0
    assert payload["summary"]["git_push_count"] == 0
    assert payload["summary"]["passed"] is True
    assert payload["boundary"]["draft_only"] is True
    assert payload["boundary"]["github_api_calls_enabled"] is False
    assert payload["boundary"]["git_branch_creation_enabled"] is False


def test_rollback_pr_draft_cli_writes_json_and_markdown(tmp_path: Path) -> None:
    output_json = tmp_path / "p81.json"
    output_md = tmp_path / "p81.md"

    subprocess.run(
        [
            "python",
            "scripts/run_rollback_pr_draft_automation.py",
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
    assert payload["summary"]["required_human_approval_count"] == 5
    assert "# OpsCat Rollback PR Draft Automation" in markdown
    assert "Zero-execution boundary" in markdown
    assert "Draft rollback PR: restore checkout-api feature flag defaults" in markdown
    assert render_rollback_pr_draft_markdown(payload).startswith("# OpsCat Rollback PR Draft Automation")
