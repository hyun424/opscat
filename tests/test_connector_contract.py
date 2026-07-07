from __future__ import annotations

from typing import Any

import pytest

from app.connectors.base import ConnectorCallRequest, ConnectorCallResult, ConnectorCapability
from app.connectors.fake import FakeObservabilityConnector
from app.connectors.github import GitHubDraftIssueConnector
from app.connectors.registry import ConnectorRegistry
from app.models import AuditEvent, Incident
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
    assert result.output["recorded"] is True
    assert result.output["events"][0]["user"]["email"] == "[REDACTED]"
    assert result.output["events"][0]["request"]["headers"]["Authorization"] == "[REDACTED]"
    assert "recorded-fixture-token" not in repr(result.output)
    assert "tok_recorded_fixture" not in repr(result.output)
    assert "abc123" not in repr(result.output)
    assert "public:secret" not in repr(result.output)


class _TimeoutConnector:
    connector_id = "test.timeout"
    capabilities = {
        "events.read": ConnectorCapability(
            name="events.read",
            description="Test timeout connector.",
            read_only=True,
            required_role="viewer",
        )
    }

    def call(self, request: ConnectorCallRequest) -> ConnectorCallResult:
        raise TimeoutError("provider timed out")


class _FailedResultConnector:
    connector_id = "test.failure"
    capabilities = {
        "events.read": ConnectorCapability(
            name="events.read",
            description="Test failed connector result.",
            read_only=True,
            required_role="viewer",
        )
    }

    def call(self, request: ConnectorCallRequest) -> ConnectorCallResult:
        return ConnectorCallResult(
            connector_id=self.connector_id,
            capability=request.capability,
            ok=False,
            read_only=True,
            error="provider failure token=raw-token for owner@example.com",
            evidence_summary="Provider returned malformed payload api_key=raw-key",
            output={"api_key": "raw-key", "owner_email": "owner@example.com"},
        )


class _MalformedConnector:
    connector_id = "test.malformed"
    capabilities = {
        "events.read": ConnectorCapability(
            name="events.read",
            description="Test malformed connector result.",
            read_only=True,
            required_role="viewer",
        )
    }

    def call(self, request: ConnectorCallRequest) -> Any:
        return {"ok": False, "error": "not a ConnectorCallResult"}


class _ContractViolationConnector:
    connector_id = "test.contract"
    capabilities = {
        "events.read": ConnectorCapability(
            name="events.read",
            description="Test connector contract violation.",
            read_only=True,
            required_role="viewer",
        )
    }

    def call(self, request: ConnectorCallRequest) -> ConnectorCallResult:
        return ConnectorCallResult(
            connector_id=self.connector_id,
            capability=request.capability,
            ok=True,
            read_only=False,
            output={"mutation": "attempted"},
        )


def _register_only(connector: Any) -> ConnectorRegistry:
    registry = ConnectorRegistry()
    registry.register(connector)
    return registry


def _incident_for_connector_failure(db_session: Any) -> Incident:
    incident = Incident(
        tenant_id="tenant-a",
        workspace_id="workspace-a",
        source="connector-test",
        status="investigating",
        service="checkout-api",
        environment="staging",
        severity="high",
        alert_payload={"message": "connector failure regression"},
        summary="Connector failure regression",
    )
    db_session.add(incident)
    db_session.flush()
    return incident


def _assert_connector_failure_escalated(db_session: Any, incident_id: str, *, connector_id: str, trigger: str) -> Incident:
    db_session.flush()
    db_session.expire_all()
    updated = db_session.query(Incident).filter(Incident.id == incident_id).one()
    assert updated.status == "escalated"

    failure_evidence = [item for item in updated.evidence if item.type == "connector_failure"]
    assert len(failure_evidence) == 1
    assert failure_evidence[0].tenant_id == "tenant-a"
    assert failure_evidence[0].workspace_id == "workspace-a"
    assert failure_evidence[0].source == f"connector:{connector_id}"
    assert failure_evidence[0].evidence_metadata["trigger"] == trigger

    timeline_types = [event.event_type for event in updated.timeline]
    assert "connector_call_failed" in timeline_types
    assert "human_escalation_required" in timeline_types
    escalation_event = [event for event in updated.timeline if event.event_type == "human_escalation_required"][-1]
    assert escalation_event.event_metadata["trigger"] == trigger
    assert trigger in escalation_event.event_metadata["triggers"]
    assert escalation_event.event_metadata["evidence_collected"]
    assert escalation_event.event_metadata["verification"]["connector_failure"]["trigger"] == trigger

    audit_types = [event.event_type for event in db_session.query(AuditEvent).all()]
    assert "connector_call_requested" in audit_types
    assert "connector_call_failed" in audit_types
    assert "human_escalation_required" in audit_types
    return updated


def test_connector_timeout_failure_records_evidence_timeline_audit_and_escalation(db_session: Any) -> None:
    principal = get_or_create_local_principal(db_session, email="viewer@example.com", tenant_id="tenant-a", workspace_id="workspace-a", role="viewer")
    incident = _incident_for_connector_failure(db_session)

    result = ConnectorService(registry=_register_only(_TimeoutConnector())).call(
        db_session,
        principal,
        ConnectorCallRequest(
            connector_id="test.timeout",
            capability="events.read",
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            actor=principal.email,
            incident_id=incident.id,
            idempotency_key="timeout-1",
        ),
    )

    assert result.ok is False
    assert result.error == "connector provider failure: TimeoutError"
    _assert_connector_failure_escalated(db_session, incident.id, connector_id="test.timeout", trigger="connector_timeout")


def test_connector_failed_result_is_redacted_and_escalated(db_session: Any) -> None:
    principal = get_or_create_local_principal(db_session, email="viewer@example.com", tenant_id="tenant-a", workspace_id="workspace-a", role="viewer")
    incident = _incident_for_connector_failure(db_session)

    result = ConnectorService(registry=_register_only(_FailedResultConnector())).call(
        db_session,
        principal,
        ConnectorCallRequest(
            connector_id="test.failure",
            capability="events.read",
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            actor=principal.email,
            incident_id=incident.id,
        ),
    )

    assert result.ok is False
    rendered_result = repr(result)
    assert "raw-token" not in rendered_result
    assert "raw-key" not in rendered_result
    assert "owner@example.com" not in rendered_result
    updated = _assert_connector_failure_escalated(db_session, incident.id, connector_id="test.failure", trigger="connector_failure")
    rendered_incident = repr([item.evidence_metadata for item in updated.evidence]) + repr([event.event_metadata for event in updated.timeline])
    assert "raw-token" not in rendered_incident
    assert "raw-key" not in rendered_incident
    assert "owner@example.com" not in rendered_incident


def test_malformed_connector_result_fails_closed_and_escalates(db_session: Any) -> None:
    principal = get_or_create_local_principal(db_session, email="viewer@example.com", tenant_id="tenant-a", workspace_id="workspace-a", role="viewer")
    incident = _incident_for_connector_failure(db_session)

    result = ConnectorService(registry=_register_only(_MalformedConnector())).call(
        db_session,
        principal,
        ConnectorCallRequest(
            connector_id="test.malformed",
            capability="events.read",
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            actor=principal.email,
            incident_id=incident.id,
        ),
    )

    assert result.ok is False
    assert result.error == "connector provider failure: TypeError"
    _assert_connector_failure_escalated(db_session, incident.id, connector_id="test.malformed", trigger="connector_failure")


def test_read_only_contract_violation_fails_closed_and_escalates(db_session: Any) -> None:
    principal = get_or_create_local_principal(db_session, email="viewer@example.com", tenant_id="tenant-a", workspace_id="workspace-a", role="viewer")
    incident = _incident_for_connector_failure(db_session)

    result = ConnectorService(registry=_register_only(_ContractViolationConnector())).call(
        db_session,
        principal,
        ConnectorCallRequest(
            connector_id="test.contract",
            capability="events.read",
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            actor=principal.email,
            incident_id=incident.id,
        ),
    )

    assert result.ok is False
    assert result.error == "connector read-only contract violation"
    _assert_connector_failure_escalated(db_session, incident.id, connector_id="test.contract", trigger="connector_contract_violation")
