from datetime import UTC, datetime

from app.models import Incident, TimelineEvent

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "new": {"queued", "investigating", "failed"},
    "queued": {"investigating", "failed"},
    "investigating": {"needs_more_context", "action_proposed", "escalated", "failed"},
    "needs_more_context": {"investigating", "escalated", "failed"},
    "action_proposed": {"waiting_approval", "executing", "escalated", "failed"},
    "waiting_approval": {"executing", "escalated", "failed"},
    "executing": {"verifying", "escalated", "failed"},
    "verifying": {"resolved", "escalated", "failed"},
    "resolved": set(),
    "escalated": {"investigating", "failed"},
    "false_positive": set(),
    "failed": set(),
}


class InvalidStateTransition(ValueError):
    pass


def transition_incident(
    incident: Incident,
    target_state: str,
    *,
    actor: str = "system",
    reason: str | None = None,
) -> TimelineEvent:
    allowed = ALLOWED_TRANSITIONS.get(incident.status, set())
    if target_state != incident.status and target_state not in allowed:
        raise InvalidStateTransition(f"cannot transition incident {incident.status!r} -> {target_state!r}")
    previous = incident.status
    incident.status = target_state
    incident.updated_at = datetime.now(UTC)
    return TimelineEvent(
        incident_id=incident.id,
        actor=actor,
        event_type="state_transition",
        content=f"Incident moved from {previous} to {target_state}" + (f": {reason}" if reason else ""),
        event_metadata={"from": previous, "to": target_state, "reason": reason},
    )
