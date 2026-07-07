from __future__ import annotations

from typing import Any

import pytest

from app.connectors.base import ConnectorCallRequest
from app.connectors.fake import FakeObservabilityConnector
from app.connectors.github import GitHubDraftIssueConnector
from app.connectors.registry import ConnectorRegistry
from app.connectors.slack import SlackWakeUpConnector
from app.models import AuditEvent
from app.services.authorization import AuthorizationError
from app.services.connector_service import ConnectorService, default_connector_registry
from app.services.identity_service import get_or_create_local_principal
from app.services.secret_service import LocalEncryptedSecretProvider


def test_default_connector_registry_exposes_only_read_only_fake_capabilities() -> None:
    registry = default_connector_registry()
    capabilities = registry.list_capabilities()["fake.observability"]

    assert {capability.name for capability in capabilities} == {"events.read", "metrics.read"}
    assert all(capability.read_only for capability in capabilities)
    assert all(capability.risk_level == "read_only" for capability in capabilities)


@pytest.mark.parametrize("capability", ["events.read", "metrics.read"])
def test_fake_connector_call_is_typed_read_only_and_audited(db_session: Any, capability: str) -> None:
    principal = get_or_create_local_principal(db_session, email="operator@example.com", tenant_id="tenant-a", workspace_id="workspace-a", role="operator")
    request = ConnectorCallRequest(
        connector_id="fake.observability",
        capability=capability,
        tenant_id="tenant-a",
        workspace_id="workspace-a",
        actor=principal.email,
        incident_id="inc-123",
        idempotency_key="connector-test-1",
        payload={"service": "payment-api", "window": "10m"},
    )

    result = ConnectorService().call(db_session, principal, request)

    assert result.ok is True
    assert result.read_only is True
    assert result.connector_id == "fake.observability"
    assert result.capability == capability
    assert "payment-api" in (result.evidence_summary or "")
    audit_types = [event.event_type for event in db_session.query(AuditEvent).all()]
    assert audit_types == ["connector_call_requested", "connector_call_completed"]


def test_connector_scope_mismatch_fails_before_call_and_audit(db_session: Any) -> None:
    principal = get_or_create_local_principal(db_session, email="operator@example.com", tenant_id="tenant-a", workspace_id="workspace-a", role="operator")
    request = ConnectorCallRequest(
        connector_id="fake.observability",
        capability="events.read",
        tenant_id="tenant-a",
        workspace_id="workspace-b",
        actor=principal.email,
    )

    with pytest.raises(AuthorizationError):
        ConnectorService().call(db_session, principal, request)
    assert db_session.query(AuditEvent).count() == 0


def test_unknown_connector_or_capability_fails_closed(db_session: Any) -> None:
    principal = get_or_create_local_principal(db_session, email="operator@example.com", tenant_id="tenant-a", workspace_id="workspace-a", role="operator")
    service = ConnectorService()

    with pytest.raises(KeyError):
        service.call(
            db_session,
            principal,
            ConnectorCallRequest(connector_id="shell", capability="execute", tenant_id="tenant-a", workspace_id="workspace-a", actor=principal.email),
        )
    with pytest.raises(KeyError):
        service.call(
            db_session,
            principal,
            ConnectorCallRequest(connector_id="fake.observability", capability="shell.execute", tenant_id="tenant-a", workspace_id="workspace-a", actor=principal.email),
        )


def test_registry_rejects_duplicate_connector_ids() -> None:
    registry = ConnectorRegistry()
    registry.register(FakeObservabilityConnector())

    with pytest.raises(ValueError):
        registry.register(FakeObservabilityConnector())


def test_default_connector_registry_includes_dry_run_only_slack_wake_up() -> None:
    registry = default_connector_registry()
    capability = registry.capability("slack.wake_up", "messages.write")

    assert capability.read_only is False
    assert capability.required_role == "operator"
    assert capability.risk_level == "external_message"


def test_slack_wake_up_dry_run_preview_is_typed_redacted_and_audited(db_session: Any) -> None:
    principal = get_or_create_local_principal(db_session, email="operator@example.com", tenant_id="tenant-a", workspace_id="workspace-a", role="operator")
    request = ConnectorCallRequest(
        connector_id="slack.wake_up",
        capability="messages.write",
        tenant_id="tenant-a",
        workspace_id="workspace-a",
        actor=principal.email,
        incident_id="inc-456",
        idempotency_key="slack-wake-up-1",
        dry_run=True,
        payload={
            "channel": "#on-call",
            "wake_up_reason": "Checkout timeout error budget is still burning",
            "summary": "payment-api has elevated 5xxs; token=slack-secret operator alice@example.com paged",
            "severity": "high",
            "blocked_action": "rollback requires approval",
            "next_steps": ["review incident", "approve or reject rollback draft"],
            "slack_token": "xoxb-real-token",
        },
    )

    result = ConnectorService().call(db_session, principal, request)

    assert result.ok is True
    assert result.read_only is False
    assert result.output["dry_run"] is True
    assert result.output["sent"] is False
    preview = result.output["preview"]
    assert preview["channel"] == "#on-call"
    assert preview["incident_id"] == "inc-456"
    serialized = str(result.output)
    assert "xoxb-real-token" not in serialized
    assert "alice@example.com" not in serialized
    assert "[REDACTED]" in serialized
    events = db_session.query(AuditEvent).order_by(AuditEvent.created_at).all()
    assert [event.event_type for event in events] == ["connector_call_requested", "connector_call_completed"]
    assert all(event.tenant_id == "tenant-a" and event.workspace_id == "workspace-a" for event in events)
    completed_metadata = events[-1].event_metadata
    assert completed_metadata["result"]["output"]["dry_run"] is True
    assert completed_metadata["result"]["output"]["sent"] is False
    audit_blob = str([event.event_metadata for event in events])
    assert "xoxb-real-token" not in audit_blob
    assert "alice@example.com" not in audit_blob
    assert "[REDACTED]" in audit_blob


def test_slack_wake_up_requires_operator_role(db_session: Any) -> None:
    principal = get_or_create_local_principal(db_session, email="viewer@example.com", tenant_id="tenant-a", workspace_id="workspace-a", role="viewer")
    request = ConnectorCallRequest(
        connector_id="slack.wake_up",
        capability="messages.write",
        tenant_id="tenant-a",
        workspace_id="workspace-a",
        actor=principal.email,
        dry_run=True,
        payload={"channel": "#on-call", "wake_up_reason": "needs human", "summary": "manual review required"},
    )

    with pytest.raises(AuthorizationError, match="principal lacks connector capability role"):
        ConnectorService().call(db_session, principal, request)
    assert db_session.query(AuditEvent).count() == 0


def test_slack_wake_up_real_send_is_disabled_even_with_valid_payload(db_session: Any) -> None:
    principal = get_or_create_local_principal(db_session, email="operator@example.com", tenant_id="tenant-a", workspace_id="workspace-a", role="operator")
    request = ConnectorCallRequest(
        connector_id="slack.wake_up",
        capability="messages.write",
        tenant_id="tenant-a",
        workspace_id="workspace-a",
        actor=principal.email,
        incident_id="inc-789",
        dry_run=False,
        payload={"channel": "#on-call", "wake_up_reason": "needs human", "summary": "manual review required"},
    )

    with pytest.raises(AuthorizationError, match="mutating connector calls are not enabled"):
        ConnectorService().call(db_session, principal, request)
    assert db_session.query(AuditEvent).count() == 0


def test_slack_wake_up_adapter_direct_real_send_attempt_fails_closed() -> None:
    request = ConnectorCallRequest(
        connector_id="slack.wake_up",
        capability="messages.write",
        tenant_id="tenant-a",
        workspace_id="workspace-a",
        actor="operator@example.com",
        incident_id="inc-direct",
        dry_run=False,
        payload={"channel": "#on-call", "wake_up_reason": "needs human", "summary": "manual review required"},
    )

    result = SlackWakeUpConnector().call(request)

    assert result.ok is False
    assert result.read_only is False
    assert result.output == {"sent": False, "dry_run_required": True}
    assert "disabled" in (result.error or "")


def test_slack_wake_up_preview_fails_closed_without_required_fields(db_session: Any) -> None:
    principal = get_or_create_local_principal(db_session, email="operator@example.com", tenant_id="tenant-a", workspace_id="workspace-a", role="operator")
    request = ConnectorCallRequest(
        connector_id="slack.wake_up",
        capability="messages.write",
        tenant_id="tenant-a",
        workspace_id="workspace-a",
        actor=principal.email,
        dry_run=True,
        payload={"channel": "#on-call", "summary": "missing reason"},
    )

    result = ConnectorService().call(db_session, principal, request)

    assert result.ok is False
    assert result.output == {"sent": False, "dry_run": True}
    assert "required" in (result.error or "")
    assert [event.event_type for event in db_session.query(AuditEvent).all()] == ["connector_call_requested", "connector_call_completed"]


def test_default_connector_registry_includes_approval_gated_github_draft_issue() -> None:
    registry = default_connector_registry()
    capability = registry.capability("github.issues", "issues.write")

    assert capability.read_only is False
    assert capability.required_role == "operator"
    assert capability.requires_approval is True
    assert capability.risk_level == "external_write"


def test_github_draft_issue_dry_run_preview_is_typed_redacted_and_audited(db_session: Any) -> None:
    principal = get_or_create_local_principal(db_session, email="operator@example.com", tenant_id="tenant-a", workspace_id="workspace-a", role="operator")
    request = ConnectorCallRequest(
        connector_id="github.issues",
        capability="issues.write",
        tenant_id="tenant-a",
        workspace_id="workspace-a",
        actor=principal.email,
        incident_id="inc-gh-1",
        idempotency_key="github-draft-1",
        dry_run=True,
        payload={
            "repository": "opscat/app",
            "title": "Investigate checkout regression",
            "body": "Incident summary with token=github-secret and owner alice@example.com",
            "labels": ["incident", "needs-approval"],
            "assignees": ["oncall-user"],
            "github_token": "ghp_real_token",
        },
    )

    result = ConnectorService().call(db_session, principal, request)

    assert result.ok is True
    assert result.read_only is False
    assert result.output["dry_run"] is True
    assert result.output["created"] is False
    preview = result.output["preview"]
    assert preview["repository"] == "opscat/app"
    assert preview["incident_id"] == "inc-gh-1"
    assert preview["labels"] == ["incident", "needs-approval"]
    serialized = str(result.output)
    assert "ghp_real_token" not in serialized
    assert "alice@example.com" not in serialized
    assert "[REDACTED]" in serialized
    events = db_session.query(AuditEvent).order_by(AuditEvent.created_at).all()
    assert [event.event_type for event in events] == ["connector_call_requested", "connector_call_completed"]
    assert all(event.tenant_id == "tenant-a" and event.workspace_id == "workspace-a" for event in events)
    completed_metadata = events[-1].event_metadata
    assert completed_metadata["result"]["output"]["dry_run"] is True
    assert completed_metadata["result"]["output"]["created"] is False
    audit_blob = str([event.event_metadata for event in events])
    assert "ghp_real_token" not in audit_blob
    assert "alice@example.com" not in audit_blob
    assert "[REDACTED]" in audit_blob


def test_github_draft_issue_requires_operator_role(db_session: Any) -> None:
    principal = get_or_create_local_principal(db_session, email="viewer@example.com", tenant_id="tenant-a", workspace_id="workspace-a", role="viewer")
    request = ConnectorCallRequest(
        connector_id="github.issues",
        capability="issues.write",
        tenant_id="tenant-a",
        workspace_id="workspace-a",
        actor=principal.email,
        dry_run=True,
        payload={"repository": "opscat/app", "title": "Draft", "body": "Body"},
    )

    with pytest.raises(AuthorizationError, match="principal lacks connector capability role"):
        ConnectorService().call(db_session, principal, request)
    assert db_session.query(AuditEvent).count() == 0


def test_github_draft_issue_real_mutation_requires_approval_then_still_disabled(db_session: Any) -> None:
    principal = get_or_create_local_principal(db_session, email="operator@example.com", tenant_id="tenant-a", workspace_id="workspace-a", role="operator")
    unapproved_request = ConnectorCallRequest(
        connector_id="github.issues",
        capability="issues.write",
        tenant_id="tenant-a",
        workspace_id="workspace-a",
        actor=principal.email,
        incident_id="inc-gh-2",
        dry_run=False,
        payload={"repository": "opscat/app", "title": "Draft", "body": "Body"},
    )
    approved_request = ConnectorCallRequest(
        connector_id="github.issues",
        capability="issues.write",
        tenant_id="tenant-a",
        workspace_id="workspace-a",
        actor=principal.email,
        incident_id="inc-gh-2",
        dry_run=False,
        approved=True,
        payload={"repository": "opscat/app", "title": "Draft", "body": "Body"},
    )

    with pytest.raises(AuthorizationError, match="approval is required"):
        ConnectorService().call(db_session, principal, unapproved_request)
    with pytest.raises(AuthorizationError, match="mutating connector calls are not enabled"):
        ConnectorService().call(db_session, principal, approved_request)
    assert db_session.query(AuditEvent).count() == 0


def test_github_draft_issue_scope_mismatch_fails_before_call_and_audit(db_session: Any) -> None:
    principal = get_or_create_local_principal(db_session, email="operator@example.com", tenant_id="tenant-a", workspace_id="workspace-a", role="operator")
    request = ConnectorCallRequest(
        connector_id="github.issues",
        capability="issues.write",
        tenant_id="tenant-a",
        workspace_id="workspace-b",
        actor=principal.email,
        dry_run=True,
        payload={"repository": "opscat/app", "title": "Draft", "body": "Body"},
    )

    with pytest.raises(AuthorizationError, match="scope does not match"):
        ConnectorService().call(db_session, principal, request)
    assert db_session.query(AuditEvent).count() == 0


def test_github_draft_issue_adapter_direct_real_mutation_attempt_fails_closed() -> None:
    request = ConnectorCallRequest(
        connector_id="github.issues",
        capability="issues.write",
        tenant_id="tenant-a",
        workspace_id="workspace-a",
        actor="operator@example.com",
        incident_id="inc-gh-direct",
        dry_run=False,
        approved=True,
        payload={"repository": "opscat/app", "title": "Draft", "body": "Body"},
    )

    result = GitHubDraftIssueConnector().call(request)

    assert result.ok is False
    assert result.read_only is False
    assert result.output == {"created": False, "dry_run_required": True}
    assert "disabled" in (result.error or "")


def test_github_draft_issue_preview_fails_closed_for_invalid_payload(db_session: Any) -> None:
    principal = get_or_create_local_principal(db_session, email="operator@example.com", tenant_id="tenant-a", workspace_id="workspace-a", role="operator")
    request = ConnectorCallRequest(
        connector_id="github.issues",
        capability="issues.write",
        tenant_id="tenant-a",
        workspace_id="workspace-a",
        actor=principal.email,
        dry_run=True,
        payload={"repository": "not-a-repository", "title": "Draft", "body": "Body"},
    )

    result = ConnectorService().call(db_session, principal, request)

    assert result.ok is False
    assert result.output == {"created": False, "dry_run": True}
    assert "owner/name" in (result.error or "")
    assert [event.event_type for event in db_session.query(AuditEvent).all()] == ["connector_call_requested", "connector_call_completed"]
