"""Append-only audit event helpers."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditEvent
from app.services.redaction import redact_value


def record_audit_event(
    db: Session,
    *,
    tenant_id: str,
    workspace_id: str,
    actor: str,
    event_type: str,
    resource_type: str,
    resource_id: str,
    action_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        actor=actor,
        event_type=event_type,
        resource_type=resource_type,
        resource_id=resource_id,
        action_id=action_id,
        event_metadata=redact_value(metadata or {}),
    )
    db.add(event)
    db.flush()
    return event
