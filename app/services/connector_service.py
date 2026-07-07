"""Policy-aware connector execution boundary."""

from __future__ import annotations

from dataclasses import asdict, replace
from typing import Any

from sqlalchemy.orm import Session

from app.connectors.base import ConnectorCallRequest, ConnectorCallResult
from app.connectors.fake import FakeObservabilityConnector
from app.connectors.registry import ConnectorRegistry
from app.connectors.sentry import SentryReadOnlyConnector
from app.services.audit_service import record_audit_event
from app.services.authorization import AuthorizationError
from app.services.identity_service import Principal
from app.services.secret_service import LocalEncryptedSecretProvider, SecretNotFoundError, SecretProvider

_ROLE_ORDER = {"viewer": 0, "operator": 1, "admin": 2, "owner": 3}


def default_connector_registry() -> ConnectorRegistry:
    registry = ConnectorRegistry()
    registry.register(FakeObservabilityConnector())
    registry.register(SentryReadOnlyConnector())
    return registry


class ConnectorService:
    def __init__(self, registry: ConnectorRegistry | None = None, secret_provider: SecretProvider | None = None) -> None:
        self.registry = registry or default_connector_registry()
        self.secret_provider = secret_provider or LocalEncryptedSecretProvider()

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
        connector_request = self._with_resolved_secret(db, principal, request, required_secret_name=capability.required_secret_name)
        if connector_request is None:
            result = ConnectorCallResult(
                connector_id=request.connector_id,
                capability=request.capability,
                ok=False,
                read_only=True,
                error=f"missing credential: {capability.required_secret_name}",
                evidence_summary="Connector call failed closed before provider fixture access because the required workspace secret was missing.",
            )
            self._record_result(db, principal, request, result, failed=True)
            return result

        connector = self.registry.get(request.connector_id)
        try:
            result = connector.call(connector_request)
        except Exception as exc:  # pragma: no cover - defensive connector boundary
            result = ConnectorCallResult(
                connector_id=request.connector_id,
                capability=request.capability,
                ok=False,
                read_only=True,
                error=f"connector provider failure: {type(exc).__name__}",
                evidence_summary="Connector call failed closed inside the provider boundary.",
            )
            self._record_result(db, principal, request, result, failed=True)
            return result

        if capability.read_only and not result.read_only:
            result = ConnectorCallResult(
                connector_id=request.connector_id,
                capability=request.capability,
                ok=False,
                read_only=True,
                error="connector read-only contract violation",
                evidence_summary="Connector result was rejected because it violated the registered read-only capability contract.",
            )
        self._record_result(db, principal, request, result, failed=not result.ok)
        return result

    def _with_resolved_secret(
        self,
        db: Session,
        principal: Principal,
        request: ConnectorCallRequest,
        *,
        required_secret_name: str | None,
    ) -> ConnectorCallRequest | None:
        if required_secret_name is None:
            return request
        try:
            secret_value = self.secret_provider.get_secret(db, principal, required_secret_name)
        except SecretNotFoundError:
            return None
        payload: dict[str, Any] = dict(request.payload)
        payload["auth_token"] = secret_value
        return replace(request, payload=payload)

    def _record_result(
        self,
        db: Session,
        principal: Principal,
        request: ConnectorCallRequest,
        result: ConnectorCallResult,
        *,
        failed: bool,
    ) -> None:
        record_audit_event(
            db,
            tenant_id=principal.tenant_id,
            workspace_id=principal.workspace_id,
            actor=principal.email,
            event_type="connector_call_failed" if failed else "connector_call_completed",
            resource_type="connector",
            resource_id=request.connector_id,
            action_id=None,
            metadata={"result": asdict(result)},
        )
