from typing import Any

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.models import Incident, TimelineEvent


def add_timeline_event(
    db: Session,
    incident_id: str,
    *,
    tenant_id: str = "demo",
    workspace_id: str = "demo",
    actor: str,
    event_type: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> TimelineEvent:
    event = TimelineEvent(
        incident_id=incident_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        actor=actor,
        event_type=event_type,
        content=content,
        event_metadata=metadata or {},
    )
    incident = db.get(Incident, incident_id)
    if incident is not None and "timeline" not in inspect(incident).unloaded:
        incident.timeline.append(event)
    else:
        db.add(event)
    return event
