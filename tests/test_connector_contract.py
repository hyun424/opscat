from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from app.connectors.base import ConnectorCallRequest, ConnectorCallResult, ConnectorCapability
from app.connectors.fake import FakeObservabilityConnector
from app.connectors.registry import ConnectorRegistry
from app.connectors.sentry import SentryProviderResponse, SentryReadOnlyConnector
from app.connectors.slack import SlackWakeUpConnector
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




def test_default_connector_registry_exposes_sentry_read_only_capabilities() -> None:
    registry = default_connector_registry()
    capabilities = registry.list_capabilities()["sentry.readonly"]

    assert {capability.name for capability in capabilities} == {"health.check", "issues.read", "issue.events.read"}
    assert all(capability.read_only for capability in capabilities)
    assert all(capability.risk_level == "read_only" for capability in capabilities)
    assert {capability.required_secret_name for capability in capabilities} == {None, "sentry.token"}


def test_sentry_connector_fixture_mode_is_default_without_credential(db_session: Any) -> None:
    principal = get_or_create_local_principal(db_session, email="viewer@example.com", tenant_id="tenant-a", workspace_id="workspace-a", role="viewer")
    secret_provider = LocalEncryptedSecretProvider(master_key="unit-test-master-key")
    request = ConnectorCallRequest(
        connector_id="sentry.readonly",
        capability="issues.read",
        tenant_id="tenant-a",
        workspace_id="workspace-a",
        actor=principal.email,
        incident_id="inc-456",
        payload={"project": "checkout-api", "query": "timeout"},
    )

    result = ConnectorService(secret_provider=secret_provider).call(db_session, principal, request)

    assert result.ok is True
    assert result.read_only is True
    assert result.output["mode"] == "fixture"
    assert result.output["recorded"] is True
    assert result.output["issues"][0]["id"] == "SENTRY-123"
    assert result.output["pagination"]["has_more"] is False
    audit_events = db_session.query(AuditEvent).order_by(AuditEvent.created_at).all()
    assert [event.event_type for event in audit_events] == ["connector_call_requested", "connector_call_completed"]


def test_sentry_connector_real_mode_fails_closed_when_credential_missing(db_session: Any) -> None:
    principal = get_or_create_local_principal(db_session, email="viewer@example.com", tenant_id="tenant-a", workspace_id="workspace-a", role="viewer")
    secret_provider = LocalEncryptedSecretProvider(master_key="unit-test-master-key")
    request = ConnectorCallRequest(
        connector_id="sentry.readonly",
        capability="issues.read",
        tenant_id="tenant-a",
        workspace_id="workspace-a",
        actor=principal.email,
        incident_id="inc-456",
        payload={"provider_mode": "real", "project": "checkout-api", "query": "timeout"},
    )

    result = ConnectorService(secret_provider=secret_provider).call(db_session, principal, request)

    assert result.ok is False
    assert result.read_only is True
    assert result.error == "missing credential: sentry.token"
    audit_events = db_session.query(AuditEvent).order_by(AuditEvent.created_at).all()
    assert [event.event_type for event in audit_events] == ["connector_call_requested", "secret_missing", "connector_call_failed"]
    assert audit_events[-1].event_metadata["result"]["error"] == "missing credential: sentry.token"


def test_sentry_health_reports_fixture_and_real_failure_states_without_leaking_secrets() -> None:
    connector = SentryReadOnlyConnector()
    fixture = connector.call(
        ConnectorCallRequest(
            connector_id="sentry.readonly",
            capability="health.check",
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            actor="viewer@example.com",
        )
    )
    missing_secret = connector.call(
        ConnectorCallRequest(
            connector_id="sentry.readonly",
            capability="health.check",
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            actor="viewer@example.com",
            payload={"provider_mode": "real"},
        )
    )
    invalid_config = connector.call(
        ConnectorCallRequest(
            connector_id="sentry.readonly",
            capability="health.check",
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            actor="viewer@example.com",
            payload={"provider_mode": "real", "auth_token": "sntrys_secret", "base_url": "http://sentry.example.invalid"},
        )
    )
    rate_limited = connector.call(
        ConnectorCallRequest(
            connector_id="sentry.readonly",
            capability="health.check",
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            actor="viewer@example.com",
            payload={"provider_mode": "real", "auth_token": "sntrys_secret", "simulate_health": "rate_limited", "retry_after": "30"},
        )
    )
    provider_error = connector.call(
        ConnectorCallRequest(
            connector_id="sentry.readonly",
            capability="health.check",
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            actor="viewer@example.com",
            payload={"provider_mode": "real", "auth_token": "sntrys_secret", "simulate_health": "provider_error"},
        )
    )

    assert fixture.output["health_state"] == "fixture_ok"
    assert missing_secret.output["health_state"] == "missing_secret"
    assert invalid_config.output["health_state"] == "invalid_config"
    assert rate_limited.output["health_state"] == "rate_limited"
    assert rate_limited.output["retry_after_seconds"] == 30
    assert provider_error.output["health_state"] == "provider_error"
    rendered = repr([fixture, missing_secret, invalid_config, rate_limited, provider_error])
    assert "sntrys_secret" not in rendered


def test_sentry_fixture_pagination_is_bounded_without_network() -> None:
    result = SentryReadOnlyConnector().call(
        ConnectorCallRequest(
            connector_id="sentry.readonly",
            capability="issues.read",
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            actor="viewer@example.com",
            payload={"per_page": 1},
        )
    )

    assert result.ok is True
    assert len(result.output["issues"]) == 1
    assert result.output["pagination"] == {"page": 1, "per_page": 1, "next_cursor": "2", "has_more": True}
    assert result.output["rate_limit"] == {"bounded": True, "retry_after_seconds": 0}


def test_sentry_real_provider_rate_limit_is_normalized_and_redacted() -> None:
    class RateLimitedTransport:
        def get(self, url: str, *, token: str, params: Any) -> SentryProviderResponse:
            assert token == "sntrys_secret"
            assert "Authorization" not in params
            return SentryProviderResponse(status_code=429, payload={"detail": "token=sntrys_secret"}, headers={"Retry-After": "45"})

    result = SentryReadOnlyConnector(transport=RateLimitedTransport()).call(
        ConnectorCallRequest(
            connector_id="sentry.readonly",
            capability="issues.read",
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            actor="viewer@example.com",
            payload={"provider_mode": "real", "auth_token": "sntrys_secret", "project": "checkout-api"},
        )
    )

    assert result.ok is False
    assert result.output["normalized_error"] == "rate_limited"
    assert result.output["retry_after_seconds"] == 45
    assert "sntrys_secret" not in repr(result)


def test_sentry_connector_returns_recorded_sanitized_issue_fixtures_and_redacts_audit(db_session: Any) -> None:
    admin = get_or_create_local_principal(db_session, email="admin@example.com", tenant_id="tenant-a", workspace_id="workspace-a", role="admin")
    principal = get_or_create_local_principal(db_session, email="viewer@example.com", tenant_id="tenant-a", workspace_id="workspace-a", role="viewer")
    secret_provider = LocalEncryptedSecretProvider(master_key="unit-test-master-key")
    secret_provider.put_secret(db_session, admin, "sentry.token", "sntrys_very_secret_token")
    request = ConnectorCallRequest(
        connector_id="sentry.readonly",
        capability="issues.read",
        tenant_id="tenant-a",
        workspace_id="workspace-a",
        actor=principal.email,
        incident_id="inc-456",
        idempotency_key="sentry-fixture-read-1",
        payload={"project": "checkout-api", "query": "timeout"},
    )

    result = ConnectorService(secret_provider=secret_provider).call(db_session, principal, request)

    assert result.ok is True
    assert result.read_only is True
    assert result.output["recorded"] is True
    assert result.output["provider"] == "sentry-fixture"
    assert result.output["issues"][0]["id"] == "SENTRY-123"
    assert result.output["issues"][0]["assigned_to"] == "[REDACTED]"
    rendered_output = repr(result.output)
    assert "sntrys_very_secret_token" not in rendered_output
    assert "@example.com" not in rendered_output

    audit_events = db_session.query(AuditEvent).order_by(AuditEvent.created_at).all()
    connector_request_event = next(event for event in audit_events if event.event_type == "connector_call_requested")
    connector_result_event = next(event for event in audit_events if event.event_type == "connector_call_completed")
    request_metadata = connector_request_event.event_metadata["request"]
    result_metadata = connector_result_event.event_metadata["result"]
    assert "auth_token" not in request_metadata["payload"]
    assert "sntrys_very_secret_token" not in repr([event.event_metadata for event in audit_events])
    assert "@example.com" not in repr(result_metadata)


def test_sentry_connector_reads_recorded_sanitized_events(db_session: Any) -> None:
    admin = get_or_create_local_principal(db_session, email="admin@example.com", tenant_id="tenant-a", workspace_id="workspace-a", role="admin")
    principal = get_or_create_local_principal(db_session, email="viewer@example.com", tenant_id="tenant-a", workspace_id="workspace-a", role="viewer")
    secret_provider = LocalEncryptedSecretProvider(master_key="unit-test-master-key")
    secret_provider.put_secret(db_session, admin, "sentry.token", "sntrys_very_secret_token")
    request = ConnectorCallRequest(
        connector_id="sentry.readonly",
        capability="issue.events.read",
        tenant_id="tenant-a",
        workspace_id="workspace-a",
        actor=principal.email,
        incident_id="inc-456",
        payload={"issue_id": "SENTRY-123"},
    )

    result = ConnectorService(secret_provider=secret_provider).call(db_session, principal, request)

    assert result.ok is True
    assert result.output["recorded"] is True
    assert result.output["events"][0]["user"]["email"] == "[REDACTED]"
    assert result.output["events"][0]["request"]["headers"]["Authorization"] == "[REDACTED]"
    assert "recorded-fixture-token" not in repr(result.output)
    assert "tok_recorded_fixture" not in repr(result.output)
    assert "abc123" not in repr(result.output)
    assert "public:secret" not in repr(result.output)


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
    assert [event.event_type for event in db_session.query(AuditEvent).all()] == ["connector_call_requested", "connector_call_failed"]


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
    assert preview["body"] == "Incident summary with token=[REDACTED] and owner [REDACTED]"
    rendered_output = repr(result.output)
    assert "ghp_real_token" not in rendered_output
    assert "github-secret" not in rendered_output
    assert "alice@example.com" not in rendered_output
    assert "[REDACTED]" in rendered_output
    events = db_session.query(AuditEvent).order_by(AuditEvent.created_at).all()
    assert [event.event_type for event in events] == ["connector_call_requested", "connector_call_completed"]
    audit_blob = repr([event.event_metadata for event in events])
    assert "ghp_real_token" not in audit_blob
    assert "github-secret" not in audit_blob
    assert "alice@example.com" not in audit_blob
    assert "[REDACTED]" in audit_blob


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


def _incident_for_connector_failure(db_session: Any, *, status: str = "investigating") -> Incident:
    incident = Incident(
        tenant_id="tenant-a",
        workspace_id="workspace-a",
        source="connector-test",
        status=status,
        service="checkout-api",
        environment="staging",
        severity="high",
        alert_payload={"message": "connector failure regression token=alert-secret owner@example.com"},
        summary="Connector failure regression token=summary-secret owner@example.com",
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
    assert "alert-secret" not in repr(escalation_event.event_metadata)
    assert "summary-secret" not in repr(escalation_event.event_metadata)
    assert "owner@example.com" not in repr(escalation_event.event_metadata)

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


def test_missing_credential_escalates_queued_incident_with_failure_context(db_session: Any) -> None:
    principal = get_or_create_local_principal(db_session, email="viewer@example.com", tenant_id="tenant-a", workspace_id="workspace-a", role="viewer")
    secret_provider = LocalEncryptedSecretProvider(master_key="unit-test-master-key")
    incident = _incident_for_connector_failure(db_session, status="queued")

    result = ConnectorService(secret_provider=secret_provider).call(
        db_session,
        principal,
        ConnectorCallRequest(
            connector_id="sentry.readonly",
            capability="issues.read",
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            actor=principal.email,
            incident_id=incident.id,
            payload={"provider_mode": "real", "project": "checkout-api"},
        ),
    )

    assert result.ok is False
    assert result.error == "missing credential: sentry.token"
    updated = _assert_connector_failure_escalated(db_session, incident.id, connector_id="sentry.readonly", trigger="connector_failure")
    assert all(event.event_type != "escalation_state_transition_blocked" for event in updated.timeline)


def test_connector_idempotency_replays_failure_without_duplicate_escalation(db_session: Any) -> None:
    principal = get_or_create_local_principal(db_session, email="viewer@example.com", tenant_id="tenant-a", workspace_id="workspace-a", role="viewer")
    incident = _incident_for_connector_failure(db_session)
    service = ConnectorService(registry=_register_only(_TimeoutConnector()))
    request = ConnectorCallRequest(
        connector_id="test.timeout",
        capability="events.read",
        tenant_id="tenant-a",
        workspace_id="workspace-a",
        actor=principal.email,
        incident_id=incident.id,
        idempotency_key="timeout-replay-1",
    )

    first = service.call(db_session, principal, request)
    second = service.call(db_session, principal, request)

    assert first == second
    db_session.flush()
    db_session.expire_all()
    updated = db_session.query(Incident).filter(Incident.id == incident.id).one()
    assert len([item for item in updated.evidence if item.type == "connector_failure"]) == 1
    assert len([event for event in updated.timeline if event.event_type == "human_escalation_required"]) == 1
    audit_types = [event.event_type for event in db_session.query(AuditEvent).all()]
    assert audit_types.count("connector_call_failed") == 1
    assert "connector_call_replayed" in audit_types


def test_connector_idempotency_conflict_fails_closed_without_provider_call(db_session: Any) -> None:
    principal = get_or_create_local_principal(db_session, email="viewer@example.com", tenant_id="tenant-a", workspace_id="workspace-a", role="viewer")
    service = ConnectorService()
    base = ConnectorCallRequest(
        connector_id="fake.observability",
        capability="events.read",
        tenant_id="tenant-a",
        workspace_id="workspace-a",
        actor=principal.email,
        idempotency_key="fake-conflict-1",
        payload={"service": "payment-api", "window": "5m"},
    )
    first = service.call(db_session, principal, base)
    conflicting = ConnectorCallRequest(
        connector_id="fake.observability",
        capability="events.read",
        tenant_id="tenant-a",
        workspace_id="workspace-a",
        actor=principal.email,
        idempotency_key="fake-conflict-1",
        payload={"service": "checkout-api", "window": "5m"},
    )

    second = service.call(db_session, principal, conflicting)

    assert first.ok is True
    assert second.ok is False
    assert second.error == "conflicting idempotency key"
    assert "connector_idempotency_conflict" in [event.event_type for event in db_session.query(AuditEvent).all()]


def test_sentry_fixture_mode_is_default_safe_without_credentials(db_session: Any) -> None:
    principal = get_or_create_local_principal(db_session, email="viewer@example.com", tenant_id="tenant-a", workspace_id="workspace-a", role="viewer")
    request = ConnectorCallRequest(
        connector_id="sentry.readonly",
        capability="issues.read",
        tenant_id="tenant-a",
        workspace_id="workspace-a",
        actor=principal.email,
        payload={"fixture_mode": True, "project": "checkout-api"},
    )

    result = ConnectorService().call(db_session, principal, request)

    assert result.ok is True
    assert result.output["provider"] == "sentry-fixture"
    assert result.output["pagination"]["bounded"] is True


def test_sentry_health_check_reports_fixture_ok_without_secret(db_session: Any) -> None:
    principal = get_or_create_local_principal(db_session, email="viewer@example.com", tenant_id="tenant-a", workspace_id="workspace-a", role="viewer")

    result = ConnectorService().call(
        db_session,
        principal,
        ConnectorCallRequest(
            connector_id="sentry.readonly",
            capability="health.check",
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            actor=principal.email,
        ),
    )

    assert result.ok is True
    assert result.output["state"] == "fixture-ok"


def test_sentry_provider_transport_pagination_and_rate_limit_are_bounded() -> None:
    from app.connectors.sentry import SentryProviderResponse, SentryRateLimitedError, SentryReadOnlyConnector

    calls: list[int] = []

    def transport(path: str, params: Mapping[str, Any]) -> SentryProviderResponse:
        calls.append(int(params["page"]))
        return SentryProviderResponse(
            status_code=200,
            payload={"issues": [{"id": f"SENTRY-{params['page']}", "assigned_to": "user@example.com"}], "next_cursor": "next" if params["page"] < 2 else ""},
        )

    result = SentryReadOnlyConnector(transport=transport).call(
        ConnectorCallRequest(connector_id="sentry.readonly", capability="issues.read", tenant_id="t", workspace_id="w", actor="a", payload={"auth_token": "sntrys_secret"})
    )

    assert result.ok is True
    assert calls == [1, 2]
    assert "user@example.com" not in repr(result.output)

    def limited(path: str, params: Mapping[str, Any]) -> SentryProviderResponse:
        raise SentryRateLimitedError("slow down")

    limited_result = SentryReadOnlyConnector(transport=limited).call(
        ConnectorCallRequest(connector_id="sentry.readonly", capability="issues.read", tenant_id="t", workspace_id="w", actor="a", payload={"auth_token": "sntrys_secret"})
    )
    assert limited_result.ok is False
    assert limited_result.error == "rate-limited"
