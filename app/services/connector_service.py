"""Policy-aware connector execution boundary."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, replace
from typing import Any, cast

from sqlalchemy.orm import Session

from app.connectors.base import ConnectorCallRequest, ConnectorCallResult
from app.connectors.fake import FakeObservabilityConnector
from app.connectors.github import GitHubDraftIssueConnector
from app.connectors.registry import ConnectorRegistry
from app.connectors.sentry import SentryReadOnlyConnector
from app.connectors.slack import SlackWakeUpConnector
from app.models import ConnectorCallRecord, Evidence, Incident
from app.services.audit_service import record_audit_event
from app.services.authorization import AuthorizationError
from app.services.escalation import build_escalation_payload, record_human_escalation
from app.services.identity_service import Principal
from app.services.redaction import redact_text, redact_value
from app.services.secret_service import LocalEncryptedSecretProvider, SecretNotFoundError, SecretProvider
from app.services.timeline_service import add_timeline_event

_ROLE_ORDER = {"viewer": 0, "operator": 1, "admin": 2, "owner": 3}


def default_connector_registry() -> ConnectorRegistry:
    registry = ConnectorRegistry()
    registry.register(FakeObservabilityConnector())
    registry.register(SentryReadOnlyConnector())
    registry.register(SlackWakeUpConnector())
    registry.register(GitHubDraftIssueConnector())
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
        if capability.requires_approval and request.dry_run is False and not request.approved:
            raise AuthorizationError(
                "approval is required before this connector mutation can execute",
                tenant_id=principal.tenant_id,
                workspace_id=principal.workspace_id,
            )
        if not capability.read_only and request.dry_run is False:
            raise AuthorizationError(
                "mutating connector calls are not enabled in the MVP",
                tenant_id=principal.tenant_id,
                workspace_id=principal.workspace_id,
            )
        request_hash = _connector_request_hash(request)
        replayed = self._replay_idempotent_call(db, principal, request, request_hash=request_hash, read_only=capability.read_only)
        if replayed is not None:
            return replayed
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
            self._record_result(db, principal, request, result, failed=True, request_hash=request_hash)
            return result

        connector = self.registry.get(request.connector_id)
        try:
            result = connector.call(connector_request)
            if not isinstance(result, ConnectorCallResult):
                raise TypeError("connector returned invalid result")
        except Exception as exc:
            result = ConnectorCallResult(
                connector_id=request.connector_id,
                capability=request.capability,
                ok=False,
                read_only=True,
                error=f"connector provider failure: {type(exc).__name__}",
                evidence_summary="Connector call failed closed inside the provider boundary.",
            )
            self._record_result(db, principal, request, result, failed=True, request_hash=request_hash)
            return result

        if not result.ok:
            result = _redacted_failure_result(result)
        if capability.read_only and not result.read_only:
            result = ConnectorCallResult(
                connector_id=request.connector_id,
                capability=request.capability,
                ok=False,
                read_only=True,
                error="connector read-only contract violation",
                evidence_summary="Connector result was rejected because it violated the registered read-only capability contract.",
            )
        self._record_result(db, principal, request, result, failed=not result.ok, request_hash=request_hash)
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
        provider_mode = str(request.payload.get("provider_mode") or request.payload.get("mode") or "fixture").strip().lower()
        if request.connector_id == "sentry.readonly" and provider_mode not in {"real", "live", "provider"}:
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
        request_hash: str,
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
        side_effects_emitted = False
        if failed:
            side_effects_emitted = self._record_failure_escalation(db, principal, request, result)
        self._record_idempotency_result(
            db,
            principal,
            request,
            result,
            request_hash=request_hash,
            failed=failed,
            side_effects_emitted=side_effects_emitted,
        )

    def _replay_idempotent_call(
        self,
        db: Session,
        principal: Principal,
        request: ConnectorCallRequest,
        *,
        request_hash: str,
        read_only: bool,
    ) -> ConnectorCallResult | None:
        if request.idempotency_key is None:
            return None
        existing = (
            db.query(ConnectorCallRecord)
            .filter(
                ConnectorCallRecord.tenant_id == principal.tenant_id,
                ConnectorCallRecord.workspace_id == principal.workspace_id,
                ConnectorCallRecord.connector_id == request.connector_id,
                ConnectorCallRecord.capability == request.capability,
                ConnectorCallRecord.idempotency_key == request.idempotency_key,
            )
            .one_or_none()
        )
        if existing is None:
            return None
        if existing.request_hash != request_hash:
            result = ConnectorCallResult(
                connector_id=request.connector_id,
                capability=request.capability,
                ok=False,
                read_only=read_only,
                error="conflicting idempotency key",
                evidence_summary="Connector call was rejected because the idempotency key was reused with a different request.",
            )
            record_audit_event(
                db,
                tenant_id=principal.tenant_id,
                workspace_id=principal.workspace_id,
                actor=principal.email,
                event_type="connector_idempotency_conflict",
                resource_type="connector",
                resource_id=request.connector_id,
                action_id=None,
                metadata={
                    "connector_id": request.connector_id,
                    "capability": request.capability,
                    "idempotency_key": request.idempotency_key,
                    "stored_request_hash": existing.request_hash,
                    "incoming_request_hash": request_hash,
                },
            )
            return result
        record_audit_event(
            db,
            tenant_id=principal.tenant_id,
            workspace_id=principal.workspace_id,
            actor=principal.email,
            event_type="connector_call_replayed",
            resource_type="connector",
            resource_id=request.connector_id,
            action_id=None,
            metadata={
                "connector_id": request.connector_id,
                "capability": request.capability,
                "idempotency_key": request.idempotency_key,
                "record_id": existing.id,
                "status": existing.status,
            },
        )
        return _connector_result_from_record(existing.result)

    def _record_idempotency_result(
        self,
        db: Session,
        principal: Principal,
        request: ConnectorCallRequest,
        result: ConnectorCallResult,
        *,
        request_hash: str,
        failed: bool,
        side_effects_emitted: bool,
    ) -> None:
        if request.idempotency_key is None:
            return
        record = ConnectorCallRecord(
            tenant_id=principal.tenant_id,
            workspace_id=principal.workspace_id,
            connector_id=request.connector_id,
            capability=request.capability,
            idempotency_key=request.idempotency_key,
            request_hash=request_hash,
            incident_id=request.incident_id,
            status="failed" if failed else "completed",
            result=cast(dict[str, Any], redact_value(asdict(result))),
            failure_class=_failure_trigger(result) if failed else None,
            side_effects_emitted=side_effects_emitted,
        )
        db.add(record)
        db.flush()

    def _record_failure_escalation(self, db: Session, principal: Principal, request: ConnectorCallRequest, result: ConnectorCallResult) -> bool:
        if request.incident_id is None:
            return False
        incident = (
            db.query(Incident)
            .filter(
                Incident.id == request.incident_id,
                Incident.tenant_id == principal.tenant_id,
                Incident.workspace_id == principal.workspace_id,
            )
            .one_or_none()
        )
        if incident is None:
            return False

        trigger = _failure_trigger(result)
        failure_metadata = _failure_metadata(request, result, trigger)
        summary = redact_text(result.evidence_summary or result.error or "Connector call failed closed.")
        evidence = Evidence(
            incident_id=incident.id,
            tenant_id=incident.tenant_id,
            workspace_id=incident.workspace_id,
            type="connector_failure",
            source=f"connector:{request.connector_id}",
            source_url=f"connector://{request.connector_id}/{request.capability}",
            content=summary,
            evidence_metadata=failure_metadata,
        )
        incident.evidence.append(evidence)
        add_timeline_event(
            db,
            incident.id,
            tenant_id=incident.tenant_id,
            workspace_id=incident.workspace_id,
            actor="connector",
            event_type="connector_call_failed",
            content=f"Connector {request.connector_id}.{request.capability} failed closed: {trigger}",
            metadata=failure_metadata,
        )
        db.flush()
        payload = build_escalation_payload(
            incident,
            trigger=trigger,
            triggers=[trigger, "connector_failure"] if trigger != "connector_failure" else [trigger],
            verification={"connector_failure": failure_metadata},
            recommended_next_action=None,
        )
        record_human_escalation(db, incident, payload, transition_to_escalated=True)
        return True


def _connector_request_hash(request: ConnectorCallRequest) -> str:
    canonical = {
        "connector_id": request.connector_id,
        "capability": request.capability,
        "tenant_id": request.tenant_id,
        "workspace_id": request.workspace_id,
        "incident_id": request.incident_id,
        "payload": request.payload,
        "dry_run": request.dry_run,
        "approved": request.approved,
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _secret_is_optional_for_fixture_mode(request: ConnectorCallRequest) -> bool:
    """Allow Sentry's recorded fixtures to remain the default no-secret path.

    Real-provider reads are still opt-in via ``provider_mode=real`` and keep the
    existing secret resolution gate. Other connectors continue to use their
    capability metadata exactly as before.
    """

    if request.connector_id != "sentry.readonly":
        return False
    mode = str(request.payload.get("provider_mode") or request.payload.get("mode") or "fixture").strip().lower()
    return mode not in {"real", "live", "provider"}


def _connector_result_from_record(payload: Mapping[str, Any]) -> ConnectorCallResult:
    return ConnectorCallResult(
        connector_id=str(payload["connector_id"]),
        capability=str(payload["capability"]),
        ok=bool(payload["ok"]),
        read_only=bool(payload["read_only"]),
        output=cast(Mapping[str, Any], payload.get("output") or {}),
        error=cast(str | None, payload.get("error")),
        evidence_summary=cast(str | None, payload.get("evidence_summary")),
    )


def _redacted_failure_result(result: ConnectorCallResult) -> ConnectorCallResult:
    redacted_output = cast(Mapping[str, Any], redact_value(dict(result.output)))
    return replace(
        result,
        output=redacted_output,
        error=redact_text(result.error) if result.error is not None else None,
        evidence_summary=redact_text(result.evidence_summary) if result.evidence_summary is not None else None,
    )


def _failure_trigger(result: ConnectorCallResult) -> str:
    detail = f"{result.error or ''} {result.evidence_summary or ''}".lower()
    if "timeout" in detail or "timed out" in detail:
        return "connector_timeout"
    if "read-only contract violation" in detail:
        return "connector_contract_violation"
    return "connector_failure"


def _failure_metadata(request: ConnectorCallRequest, result: ConnectorCallResult, trigger: str) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "trigger": trigger,
        "connector_id": request.connector_id,
        "capability": request.capability,
        "incident_id": request.incident_id,
        "idempotency_key": request.idempotency_key,
        "read_only": result.read_only,
        "ok": result.ok,
        "error": result.error,
        "evidence_summary": result.evidence_summary,
        "output": dict(result.output),
    }
    return cast(dict[str, Any], redact_value(raw))
