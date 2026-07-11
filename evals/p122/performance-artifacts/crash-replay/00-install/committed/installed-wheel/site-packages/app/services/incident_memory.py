"""Deterministic local incident memory for P7 reliability gates.

The memory store is derived from local/mock database records only. It performs no
network calls and uses transparent weighted matching instead of vector services.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from sqlalchemy.orm import Session, selectinload

from app.models import ActionProposal, Incident

SUCCESS_ACTION_STATUSES = {"executed", "approved"}
FAILED_ACTION_STATUSES = {"failed", "denied", "escalated", "rejected"}


@dataclass(frozen=True)
class IncidentMemoryRecord:
    incident_id: str
    service: str
    environment: str
    fingerprint: str
    root_cause: str
    runbook: str
    action_type: str
    outcome: str
    action_status: str = "unknown"
    confidence: float | None = None
    summary: str = ""


@dataclass(frozen=True)
class IncidentMemoryMatch:
    record: IncidentMemoryRecord
    score: float
    reasons: tuple[str, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def similarity(self) -> float:
        return self.score

    @property
    def failed_remediation_warning(self) -> bool:
        return "prior_failed_remediation" in self.warnings

    @property
    def failed_prior_action(self) -> bool:
        return self.failed_remediation_warning

    @property
    def warning(self) -> str:
        return "; ".join(self.warnings)

    def to_dict(self) -> dict[str, object]:
        return {
            "incident_id": self.record.incident_id,
            "score": self.score,
            "reasons": list(self.reasons),
            "warnings": list(self.warnings),
            "failed_prior_action": self.failed_prior_action,
            "action_type": self.record.action_type,
            "outcome": self.record.outcome,
        }


@dataclass(frozen=True)
class IncidentMemory:
    records: tuple[IncidentMemoryRecord, ...] = ()

    def __init__(self, records: Iterable[IncidentMemoryRecord] = ()) -> None:
        object.__setattr__(self, "records", tuple(records))

    def add(self, record: IncidentMemoryRecord) -> None:
        object.__setattr__(self, "records", (*self.records, record))

    def search(
        self,
        *,
        service: str,
        environment: str,
        fingerprint: str,
        root_cause: str,
        runbook: str,
        action_type: str,
        limit: int = 5,
    ) -> list[IncidentMemoryMatch]:
        return self.find_similar(
            service=service,
            environment=environment,
            fingerprint=fingerprint,
            root_cause=root_cause,
            runbook=runbook,
            action_type=action_type,
            limit=limit,
        )

    def find_similar(
        self,
        *,
        service: str,
        environment: str,
        fingerprint: str,
        root_cause: str,
        runbook: str,
        action_type: str,
        limit: int = 5,
    ) -> list[IncidentMemoryMatch]:
        probe = Incident(
            tenant_id="demo",
            workspace_id="demo",
            alert_fingerprint=fingerprint,
            source="memory-probe",
            status="investigating",
            service=service,
            environment=environment,
            severity="medium",
            alert_payload={"scenario": runbook},
            root_cause_candidate=root_cause,
        )
        return search_similar_incidents(self, probe, action_type=action_type, limit=limit)


def build_incident_memory(
    db: Session,
    *,
    tenant_id: str = "demo",
    workspace_id: str = "demo",
    exclude_incident_id: str | None = None,
) -> IncidentMemory:
    incidents = (
        db.query(Incident)
        .options(selectinload(Incident.actions))
        .filter(Incident.tenant_id == tenant_id, Incident.workspace_id == workspace_id)
        .all()
    )
    records: list[IncidentMemoryRecord] = []
    for incident in incidents:
        if incident.id == exclude_incident_id:
            continue
        records.extend(_records_from_incident(incident))
    return IncidentMemory(records=tuple(records))


def search_similar_incidents(
    memory: IncidentMemory,
    incident: Incident,
    *,
    action_type: str | None = None,
    limit: int = 5,
) -> list[IncidentMemoryMatch]:
    matches = [_score_record(record, incident, action_type=action_type) for record in memory.records]
    matches = [match for match in matches if match.score > 0.0]
    return sorted(matches, key=lambda item: item.score, reverse=True)[:limit]


def failed_remediation_warning(matches: Iterable[IncidentMemoryMatch]) -> bool:
    return any("prior_failed_remediation" in match.warnings for match in matches)


def summarize_matches(matches: Iterable[IncidentMemoryMatch]) -> list[dict[str, object]]:
    return [
        {
            "incident_id": match.record.incident_id,
            "score": match.score,
            "service": match.record.service,
            "environment": match.record.environment,
            "root_cause": match.record.root_cause,
            "action_type": match.record.action_type,
            "outcome": match.record.outcome,
            "reasons": list(match.reasons),
            "warnings": list(match.warnings),
        }
        for match in matches
    ]


def _records_from_incident(incident: Incident) -> list[IncidentMemoryRecord]:
    if not incident.actions:
        return [
            IncidentMemoryRecord(
                incident_id=incident.id,
                service=incident.service,
                environment=incident.environment,
                fingerprint=incident.alert_fingerprint,
                root_cause=incident.root_cause_candidate or _scenario(incident),
                runbook=_scenario(incident),
                action_type="none",
                outcome=_incident_outcome(incident.status),
                action_status=incident.status,
                confidence=incident.confidence,
                summary=incident.summary or "",
            )
        ]
    return [_record_for_action(incident, action) for action in incident.actions]


def _record_for_action(incident: Incident, action: ActionProposal) -> IncidentMemoryRecord:
    return IncidentMemoryRecord(
        incident_id=incident.id,
        service=incident.service,
        environment=incident.environment,
        fingerprint=incident.alert_fingerprint,
        root_cause=incident.root_cause_candidate or _scenario(incident),
        runbook=str((action.payload or {}).get("runbook") or _scenario(incident)),
        action_type=action.action_type,
        outcome=_action_outcome(action.status, incident.status),
        action_status=action.status,
        confidence=action.confidence if action.confidence is not None else incident.confidence,
        summary=incident.summary or "",
    )


def _score_record(record: IncidentMemoryRecord, incident: Incident, *, action_type: str | None) -> IncidentMemoryMatch:
    score = 0.0
    reasons: list[str] = []
    if record.service == incident.service:
        score += 0.35
        reasons.append("same_service")
    if record.environment == incident.environment:
        score += 0.15
        reasons.append("same_environment")
    if record.fingerprint and record.fingerprint == incident.alert_fingerprint:
        score += 0.10
        reasons.append("same_fingerprint")
    if action_type is not None and record.action_type == action_type:
        score += 0.20
        reasons.append("same_action_type")
    if _token_overlap(record.root_cause, incident.root_cause_candidate or _scenario(incident)):
        score += 0.20
        reasons.append("similar_root_cause")
    warnings: list[str] = []
    if record.outcome == "failed" and (action_type is None or record.action_type == action_type) and score >= 0.55:
        warnings.append("prior_failed_remediation")
    return IncidentMemoryMatch(record=record, score=round(min(score, 1.0), 2), reasons=tuple(reasons), warnings=tuple(warnings))


def _token_overlap(left: str, right: str) -> bool:
    left_tokens = {token for token in left.lower().replace("_", " ").split() if len(token) > 3}
    right_tokens = {token for token in right.lower().replace("_", " ").split() if len(token) > 3}
    return bool(left_tokens & right_tokens)


def _scenario(incident: Incident) -> str:
    payload = incident.alert_payload or {}
    return str(payload.get("scenario") or "unknown")


def _action_outcome(action_status: str, incident_status: str) -> str:
    if action_status in SUCCESS_ACTION_STATUSES and incident_status == "resolved":
        return "success"
    if action_status in FAILED_ACTION_STATUSES or incident_status in {"escalated", "failed"}:
        return "failed"
    return "unknown"


def _incident_outcome(status: str) -> str:
    if status == "resolved":
        return "success"
    if status in {"escalated", "failed"}:
        return "failed"
    return "unknown"
