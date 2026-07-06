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
