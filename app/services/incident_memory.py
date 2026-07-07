"""Local deterministic incident memory with simple similarity scoring."""

from __future__ import annotations

from dataclasses import dataclass

from app.models import Incident


@dataclass(frozen=True)
class IncidentMemoryRecord:
    id: str
    service: str
    environment: str
    fingerprint: str
    root_cause: str
    runbook: str
    action_type: str
    outcome: str


@dataclass(frozen=True)
class SimilarIncident:
    record: IncidentMemoryRecord
    score: float
    reasons: list[str]
    failed_past_remediation: bool


class IncidentMemory:
    def __init__(self, records: list[IncidentMemoryRecord] | None = None) -> None:
        self._records = list(records or [])

    def add(self, record: IncidentMemoryRecord) -> None:
        self._records.append(record)

    def remember_incident(self, incident: Incident, *, runbook: str = "unknown", action_type: str = "unknown", outcome: str | None = None) -> None:
        self.add(
            IncidentMemoryRecord(
                id=incident.id,
                service=incident.service,
                environment=incident.environment,
                fingerprint=incident.alert_fingerprint,
                root_cause=incident.root_cause_candidate or "unknown",
                runbook=runbook,
                action_type=action_type,
                outcome=outcome or incident.status,
            )
        )

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
    ) -> list[SimilarIncident]:
        matches = [self._score(record, service, environment, fingerprint, root_cause, runbook, action_type) for record in self._records]
        return sorted((match for match in matches if match.score > 0.0), key=lambda item: item.score, reverse=True)[:limit]

    def _score(self, record: IncidentMemoryRecord, service: str, environment: str, fingerprint: str, root_cause: str, runbook: str, action_type: str) -> SimilarIncident:
        checks = [
            (record.service == service, 0.2, "same service"),
            (record.environment == environment, 0.1, "same environment"),
            (bool(record.fingerprint and fingerprint and record.fingerprint in fingerprint or fingerprint in record.fingerprint), 0.2, "similar fingerprint"),
            (_overlap(record.root_cause, root_cause), 0.2, "similar root cause"),
            (record.runbook == runbook, 0.15, "same runbook"),
            (record.action_type == action_type, 0.15, "same action"),
        ]
        score = sum(weight for ok, weight, _reason in checks if ok)
        reasons = [reason for ok, _weight, reason in checks if ok]
        return SimilarIncident(record, round(score, 3), reasons, record.outcome in {"failed", "escalated_after_failure", "verification_failed"})


def _overlap(left: str, right: str) -> bool:
    left_words = {word for word in left.lower().replace("-", " ").split() if len(word) > 3}
    right_words = {word for word in right.lower().replace("-", " ").split() if len(word) > 3}
    return bool(left_words & right_words)
