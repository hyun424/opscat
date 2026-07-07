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


def _score(record: IncidentMemoryRecord, service: str, environment: str, fingerprint: str, root_cause: str, runbook: str, action_type: str) -> IncidentMemoryMatch:
    reasons: list[str] = []
    score = 0.0
    comparisons = (
        (record.service, service, 0.20, "same_service"),
        (record.environment, environment, 0.10, "same_environment"),
        (record.fingerprint, fingerprint, 0.20, "same_fingerprint"),
        (record.root_cause, root_cause, 0.20, "same_root_cause"),
        (record.runbook, runbook, 0.15, "same_runbook"),
        (record.action_type, action_type, 0.15, "same_action_type"),
    )
    for left, right, weight, reason in comparisons:
        if left and right and left.lower() == right.lower():
            score += weight
            reasons.append(reason)
        elif left and right and (left.lower() in right.lower() or right.lower() in left.lower()):
            score += weight / 2
            reasons.append(f"partial_{reason}")
    return IncidentMemoryMatch(record=record, similarity=round(min(1.0, score), 2), reasons=tuple(reasons), failed_remediation_warning=record.outcome == "failed" and score >= 0.75)


def _default_records() -> list[IncidentMemoryRecord]:
    return [
        IncidentMemoryRecord(
            "mem-payment-rollback",
            "payment-api",
            "staging",
            "payment-api:deploy",
            "Recent payment-api deploy introduced timeout regression",
            "rollback_pr",
            "mock.create_rollback_pr",
            "success",
        ),
        IncidentMemoryRecord(
            "mem-worker-restart",
            "worker",
            "staging",
            "worker:queue",
            "Queue worker degradation after broker maintenance",
            "restart_worker",
            "mock.execute_restart_worker",
            "success",
        ),
        IncidentMemoryRecord(
            "mem-worker-failed",
            "worker",
            "staging",
            "worker:poison",
            "Queue worker degradation after poison message",
            "restart_worker",
            "mock.execute_restart_worker",
            "failed",
        ),
    ]
