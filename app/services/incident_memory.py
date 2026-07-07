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
    summary: str


@dataclass(frozen=True)
class IncidentMemoryMatch:
    record: IncidentMemoryRecord
    score: float
    reasons: tuple[str, ...]

    @property
    def failed_prior_action(self) -> bool:
        return self.record.outcome in {"failed", "escalated_after_action"}

    @property
    def warning(self) -> str:
        if self.failed_prior_action:
            return f"Prior similar incident {self.record.incident_id} failed after {self.record.action_type}."
        return f"Prior similar incident {self.record.incident_id} outcome={self.record.outcome}."

    def to_dict(self) -> dict[str, object]:
        return {
            "incident_id": self.record.incident_id,
            "score": self.score,
            "reasons": list(self.reasons),
            "action_type": self.record.action_type,
            "outcome": self.record.outcome,
            "failed_prior_action": self.failed_prior_action,
            "warning": self.warning,
            "summary": self.record.summary,
        }


DEFAULT_MEMORY: tuple[IncidentMemoryRecord, ...] = (
    IncidentMemoryRecord("mem-worker-ok", "worker", "staging", "worker_queue_backlog", "Queue worker degradation after broker maintenance", "restart-worker", "mock.execute_restart_worker", "resolved", "Restart recovered queue backlog in staging."),
    IncidentMemoryRecord("mem-payment-pr", "payment-api", "staging", "payment_api_deploy_regression", "Recent payment-api deploy introduced timeout regression", "rollback-pr", "mock.create_rollback_pr", "resolved", "Rollback PR draft restored prior version in mock eval."),
    IncidentMemoryRecord("mem-worker-poison", "worker", "staging", "worker_poison_message", "Queue worker degradation after broker maintenance", "restart-worker", "mock.execute_restart_worker", "failed", "Restart did not clear poisoned message; human drained queue."),
)


class IncidentMemory:
    def __init__(self, records: list[IncidentMemoryRecord] | tuple[IncidentMemoryRecord, ...] | None = None) -> None:
        self.records = tuple(records or DEFAULT_MEMORY)

    def find_similar(
        self,
        *,
        service: str,
        environment: str,
        fingerprint: str,
        root_cause: str,
        runbook: str,
        action_type: str,
        limit: int = 3,
    ) -> list[IncidentMemoryMatch]:
        matches: list[IncidentMemoryMatch] = []
        for record in self.records:
            score = 0.0
            reasons: list[str] = []
            for label, query, value, weight in (
                ("service", service, record.service, 0.22),
                ("environment", environment, record.environment, 0.12),
                ("fingerprint", fingerprint, record.fingerprint, 0.18),
                ("root_cause", root_cause, record.root_cause, 0.2),
                ("runbook", runbook, record.runbook, 0.14),
                ("action_type", action_type, record.action_type, 0.14),
            ):
                if _similar(query, value):
                    score += weight
                    reasons.append(label)
            if score > 0:
                matches.append(IncidentMemoryMatch(record=record, score=round(score, 3), reasons=tuple(reasons)))
        return sorted(matches, key=lambda item: item.score, reverse=True)[:limit]


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
        IncidentMemoryRecord("mem-payment-rollback", "payment-api", "staging", "payment-api:deploy", "Recent payment-api deploy introduced timeout regression", "rollback_pr", "mock.create_rollback_pr", "success"),
        IncidentMemoryRecord("mem-worker-restart", "worker", "staging", "worker:queue", "Queue worker degradation after broker maintenance", "restart_worker", "mock.execute_restart_worker", "success"),
        IncidentMemoryRecord("mem-worker-failed", "worker", "staging", "worker:poison", "Queue worker degradation after poison message", "restart_worker", "mock.execute_restart_worker", "failed"),
    ]
