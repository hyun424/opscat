"""P7 deterministic local incident memory and similarity search."""

from __future__ import annotations

from dataclasses import dataclass


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


@dataclass(frozen=True)
class IncidentMemoryMatch:
    record: IncidentMemoryRecord
    similarity: float
    reasons: tuple[str, ...]
    failed_remediation_warning: bool


class IncidentMemory:
    def __init__(self, records: list[IncidentMemoryRecord] | None = None) -> None:
        self._records = list(records or _default_records())

    def add(self, record: IncidentMemoryRecord) -> None:
        self._records.append(record)

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
        matches = [_score(record, service, environment, fingerprint, root_cause, runbook, action_type) for record in self._records]
        matches = [match for match in matches if match.similarity > 0.0]
        return sorted(matches, key=lambda item: item.similarity, reverse=True)[:limit]


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
    return IncidentMemoryMatch(record=record, similarity=round(min(1.0, score), 2), reasons=tuple(reasons), failed_remediation_warning=record.outcome == "failed" and score >= 0.5)


def _default_records() -> list[IncidentMemoryRecord]:
    return [
        IncidentMemoryRecord("mem-payment-rollback", "payment-api", "staging", "payment-api:deploy", "Recent payment-api deploy introduced timeout regression", "rollback_pr", "mock.create_rollback_pr", "success"),
        IncidentMemoryRecord("mem-worker-restart", "worker", "staging", "worker:queue", "Queue worker degradation after broker maintenance", "restart_worker", "mock.execute_restart_worker", "success"),
        IncidentMemoryRecord("mem-worker-failed", "worker", "staging", "worker:poison", "Queue worker degradation after poison message", "restart_worker", "mock.execute_restart_worker", "failed"),
    ]
