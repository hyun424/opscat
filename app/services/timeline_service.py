from typing import Any

from sqlalchemy.orm import Session

from app.models import TimelineEvent


def add_timeline_event(
    db: Session,
    incident_id: str,
    *,
    actor: str,
    event_type: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> TimelineEvent:
    event = TimelineEvent(
        incident_id=incident_id,
        actor=actor,
        event_type=event_type,
        content=content,
        event_metadata=metadata or {},
    )
    db.add(event)
    return event
