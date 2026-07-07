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


def _similar(left: str, right: str) -> bool:
    if not left or not right:
        return False
    left_l = left.lower()
    right_l = right.lower()
    return left_l == right_l or left_l in right_l or right_l in left_l
