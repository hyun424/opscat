"""Policy-aware connector execution boundary."""

from __future__ import annotations

from dataclasses import asdict

from sqlalchemy.orm import Session

from app.connectors.base import ConnectorCallRequest, ConnectorCallResult
from app.connectors.fake import FakeObservabilityConnector
from app.connectors.registry import ConnectorRegistry
from app.services.audit_service import record_audit_event
from app.services.authorization import AuthorizationError
from app.services.identity_service import Principal

_ROLE_ORDER = {"viewer": 0, "operator": 1, "admin": 2, "owner": 3}


def default_connector_registry() -> ConnectorRegistry:
    registry = ConnectorRegistry()
    registry.register(FakeObservabilityConnector())
    return registry


class ConnectorService:
    def __init__(self, registry: ConnectorRegistry | None = None) -> None:
        self.registry = registry or default_connector_registry()

    def call(self, db: Session, principal: Principal, request: ConnectorCallRequest) -> ConnectorCallResult:
        if request.tenant_id != principal.tenant_id or request.workspace_id != principal.workspace_id:
            raise AuthorizationError(
                "connector call scope does not match principal scope",
                tenant_id=principal.tenant_id,
                workspace_id=principal.workspace_id,
            )
        capability = self.registry.capability(request.connector_id, request.capability)
        if _ROLE_ORDER.get(principal.role, -1) < _ROLE_ORDER[capability.required_role]:
            raise AuthorizationError(
                "principal lacks connector capability role",
                tenant_id=principal.tenant_id,
                workspace_id=principal.workspace_id,
            )
        if not capability.read_only and request.dry_run is False:
            raise AuthorizationError(
                "mutating connector calls are not enabled in the MVP",
                tenant_id=principal.tenant_id,
                workspace_id=principal.workspace_id,
            )
        record_audit_event(
            db,
            tenant_id=principal.tenant_id,
            workspace_id=principal.workspace_id,
            actor=principal.email,
            event_type="connector_call_requested",
            resource_type="connector",
            resource_id=request.connector_id,
            action_id=None,
            metadata={"request": asdict(request), "capability": asdict(capability)},
        )
        connector = self.registry.get(request.connector_id)
        result = connector.call(request)
        record_audit_event(
            db,
            tenant_id=principal.tenant_id,
            workspace_id=principal.workspace_id,
            actor=principal.email,
            event_type="connector_call_completed",
            resource_type="connector",
            resource_id=request.connector_id,
            action_id=None,
            metadata={"result": asdict(result)},
        )
        return result
