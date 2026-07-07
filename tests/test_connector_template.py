"""Connector SDK guide and fixture connector template gates for P5."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.connectors.base import ConnectorCallRequest
from app.connectors.registry import ConnectorRegistry
from app.models import AuditEvent
from app.services.connector_service import ConnectorService
from app.services.identity_service import get_or_create_local_principal
from app.services.secret_service import LocalEncryptedSecretProvider
from examples.connectors.example_connector import ExampleStatusConnector


def test_connector_sdk_doc_explains_safe_authoring_contract() -> None:
    doc = Path("docs/connector-sdk.md")

    assert doc.exists()
    text = doc.read_text()
    for required in [
        "# Connector SDK Guide",
        "ConnectorCapability",
        "required_secret_name",
        "dry-run",
        "idempotency",
        "redaction",
        "connector eval",
        "No broad token",
        "No live mutation by default",
        "examples/connectors/example_connector.py",
    ]:
        assert required in text


def test_example_connector_template_supports_success_missing_secret_and_failure(db_session: Any) -> None:
    registry = ConnectorRegistry()
    registry.register(ExampleStatusConnector())
    secret_provider = LocalEncryptedSecretProvider(master_key="connector-template-test-key")
    admin = get_or_create_local_principal(db_session, email="admin@example.com", tenant_id="tenant-a", workspace_id="alpha", role="admin")
    viewer = get_or_create_local_principal(db_session, email="viewer@example.com", tenant_id="tenant-a", workspace_id="alpha", role="viewer")
    service = ConnectorService(registry=registry, secret_provider=secret_provider)

    missing = service.call(
        db_session,
        viewer,
        ConnectorCallRequest(
            connector_id="example.status",
            capability="status.read",
            tenant_id="tenant-a",
            workspace_id="alpha",
            actor=viewer.email,
            idempotency_key="example-missing-secret",
            payload={"service": "checkout-api"},
        ),
    )
    assert missing.ok is False
    assert missing.error == "missing credential: example.token"

    secret_provider.put_secret(db_session, admin, "example.token", "example-secret-value")
    success = service.call(
        db_session,
        viewer,
        ConnectorCallRequest(
            connector_id="example.status",
            capability="status.read",
            tenant_id="tenant-a",
            workspace_id="alpha",
            actor=viewer.email,
            idempotency_key="example-success",
            payload={"service": "checkout-api"},
        ),
    )
    assert success.ok is True
    assert success.read_only is True
    assert success.output["provider"] == "example-fixture"
    assert success.output["service"] == "checkout-api"
    assert "example-secret-value" not in repr(success)

    failure = service.call(
        db_session,
        viewer,
        ConnectorCallRequest(
            connector_id="example.status",
            capability="status.read",
            tenant_id="tenant-a",
            workspace_id="alpha",
            actor=viewer.email,
            idempotency_key="example-provider-failure",
            payload={"service": "checkout-api", "force_failure": True},
        ),
    )
    assert failure.ok is False
    assert "provider failure" in (failure.error or "")
    assert "example-secret-value" not in repr([event.event_metadata for event in db_session.query(AuditEvent).all()])
