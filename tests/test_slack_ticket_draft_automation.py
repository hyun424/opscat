from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.slack_ticket_draft_automation import (
    SlackTicketDraftDecision,
    SlackTicketDraftReport,
    evaluate_slack_ticket_draft_fixture,
    render_slack_ticket_draft_markdown,
)

FIXTURE = Path("evals/policy/p82_slack_ticket_draft_automation.json")


def test_slack_ticket_draft_builds_structured_grounded_drafts() -> None:
    report = evaluate_slack_ticket_draft_fixture(FIXTURE)
    payload = report.to_dict()
    drafts = {row["scenario_id"]: row for row in payload["drafts"]}

    assert isinstance(report, SlackTicketDraftReport)
    assert set(drafts) == {
        "confirmed-deploy-regression-update",
        "suspected-db-saturation-human-confirmation",
        "rollback-draft-ready-update",
        "blocked-credential-auth-issue",
        "insufficient-evidence-noisy-alert",
    }

    for row in drafts.values():
        assert row["decision"] in {item.value for item in SlackTicketDraftDecision}
        assert row["draft_only"] is True
        assert row["human_approval_required"] is True
        assert row["audit_metadata"]["local_mock_only"] is True
        assert row["execution_plan"]["message_send_count"] == 0
        assert row["execution_plan"]["ticket_creation_count"] == 0
        assert row["execution_plan"]["live_api_call_count"] == 0
        assert row["slack_incident_update_draft"]
        assert row["escalation_dm_draft"]
        assert row["status_update_draft"]
        assert row["ticket_draft"]["title"]
        assert row["ticket_draft"]["body"]
        assert row["ticket_draft"]["labels"]
        assert row["evidence_links"]
        assert row["approval_requirement"]["required"] is True
        assert row["audit_metadata"]["approval_gate"] in {"p80", "p81", "p82"}

    deploy = drafts["confirmed-deploy-regression-update"]
    assert deploy["decision"] == SlackTicketDraftDecision.DRAFT_READY.value
    assert deploy["slack_incident_update_draft"]["channel"] == "#incidents-local-mock"
    assert "confirmed deploy regression" in deploy["slack_incident_update_draft"]["text"]
    assert "p76:approval_ready:deploy-regression" in deploy["slack_incident_update_draft"]["cited_evidence_ids"]
    assert deploy["ticket_draft"]["priority"] == "P1"
    assert "deploy-regression" in deploy["ticket_draft"]["labels"]
    assert deploy["uncertainty"] == []


def test_slack_ticket_draft_models_human_confirmation_and_rollback_ready_paths() -> None:
    payload = evaluate_slack_ticket_draft_fixture(FIXTURE).to_dict()
    drafts = {row["scenario_id"]: row for row in payload["drafts"]}

    db = drafts["suspected-db-saturation-human-confirmation"]
    rollback = drafts["rollback-draft-ready-update"]

    assert db["decision"] == SlackTicketDraftDecision.INVESTIGATION_ONLY.value
    assert db["p76_gate"]["decision"] == "approval_ready"
    assert "suspected database saturation" in db["slack_incident_update_draft"]["text"]
    assert "human_confirmation_required" in db["uncertainty"]
    assert db["approval_requirement"]["approval_type"] == "database_owner_review"
    assert "confirm DB saturation with owner" in db["next_actions"]

    assert rollback["decision"] == SlackTicketDraftDecision.DRAFT_READY.value
    assert rollback["p81_rollback_draft"]["decision"] == "draft_ready"
    assert "rollback PR draft is ready for human review" in rollback["slack_incident_update_draft"]["text"]
    assert "p81:rollback-draft:checkout-api" in rollback["ticket_draft"]["body"]
    assert rollback["approval_requirement"]["approval_type"] == "release_manager_review"


def test_slack_ticket_draft_blocks_or_rejects_unsafe_and_noisy_scenarios() -> None:
    payload = evaluate_slack_ticket_draft_fixture(FIXTURE).to_dict()
    drafts = {row["scenario_id"]: row for row in payload["drafts"]}

    credential = drafts["blocked-credential-auth-issue"]
    noisy = drafts["insufficient-evidence-noisy-alert"]

    assert credential["decision"] == SlackTicketDraftDecision.BLOCKED.value
    assert credential["slack_incident_update_draft"]["text"].startswith("Draft blocked")
    assert credential["ticket_draft"]["priority"] == "P2"
    assert "credential_or_auth_issue_blocked" in credential["reasons"]
    assert credential["approval_requirement"]["approval_type"] == "security_owner_review"

    assert noisy["decision"] == SlackTicketDraftDecision.REJECTED.value
    assert noisy["slack_incident_update_draft"]["text"].startswith("Investigation-only draft")
    assert "insufficient_evidence_for_status_or_ticket_claims" in noisy["reasons"]
    assert "collect a second independent signal" in noisy["next_actions"]
    assert noisy["ticket_draft"]["labels"] == ["investigation-only", "insufficient-evidence"]


def test_slack_ticket_draft_summary_preserves_zero_external_side_effects() -> None:
    payload = evaluate_slack_ticket_draft_fixture(FIXTURE).to_dict()

    assert payload["summary"]["scenario_count"] == 5
    assert payload["summary"]["draft_ready_count"] == 2
    assert payload["summary"]["investigation_only_count"] == 1
    assert payload["summary"]["blocked_count"] == 1
    assert payload["summary"]["rejected_count"] == 1
    assert payload["summary"]["required_human_approval_count"] == 5
    assert payload["summary"]["message_send_count"] == 0
    assert payload["summary"]["ticket_creation_count"] == 0
    assert payload["summary"]["live_api_call_count"] == 0
    assert payload["summary"]["credential_read_count"] == 0
    assert payload["summary"]["network_call_count"] == 0
    assert payload["summary"]["production_mutation_count"] == 0
    assert payload["summary"]["passed"] is True
    assert payload["boundary"]["slack_api_calls_enabled"] is False
    assert payload["boundary"]["ticket_api_calls_enabled"] is False


def test_slack_ticket_draft_cli_writes_json_and_markdown(tmp_path: Path) -> None:
    output_json = tmp_path / "p82.json"
    output_md = tmp_path / "p82.md"

    subprocess.run(
        [
            "python",
            "scripts/run_slack_ticket_draft_automation.py",
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
    assert "# OpsCat Slack and Ticket Draft Automation" in markdown
    assert "Zero-external-side-effect boundary" in markdown
    assert "confirmed deploy regression" in markdown
    assert render_slack_ticket_draft_markdown(payload).startswith("# OpsCat Slack and Ticket Draft Automation")
