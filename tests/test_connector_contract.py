from __future__ import annotations

from typing import Any

import pytest

from app.connectors.base import ConnectorCallRequest
from app.connectors.fake import FakeObservabilityConnector
from app.connectors.registry import ConnectorRegistry
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


def test_default_connector_registry_exposes_sentry_read_only_capabilities() -> None:
    registry = default_connector_registry()
    capabilities = registry.list_capabilities()["sentry.readonly"]

    assert {capability.name for capability in capabilities} == {"issues.read", "issue.events.read"}
    assert all(capability.read_only for capability in capabilities)
    assert all(capability.risk_level == "read_only" for capability in capabilities)
    assert all(capability.required_secret_name == "sentry.token" for capability in capabilities)


def test_sentry_connector_fails_closed_when_credential_missing(db_session: Any) -> None:
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

    assert result.ok is False
    assert result.read_only is True
    assert result.error == "missing credential: sentry.token"
    audit_events = db_session.query(AuditEvent).order_by(AuditEvent.created_at).all()
    assert [event.event_type for event in audit_events] == ["connector_call_requested", "secret_missing", "connector_call_failed"]
    assert audit_events[-1].event_metadata["result"]["error"] == "missing credential: sentry.token"


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
