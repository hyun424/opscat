from __future__ import annotations

from app.models import Evidence, Incident
from app.services.incident_memory import IncidentMemoryMatch, IncidentMemoryRecord
from app.services.runbook_critic import critique_runbook
from app.services.runbook_service import get_runbook


def _incident(*, service: str = "worker", confidence: float = 0.86, environment: str = "staging") -> Incident:
    return Incident(
        service=service,
        environment=environment,
        severity="medium",
        confidence=confidence,
        root_cause_candidate="Worker queue degradation",
        alert_payload={"scenario": "queue_backlog_worker"},
        summary="queue backlog with worker heartbeat loss",
    )


def _evidence() -> list[Evidence]:
    return [
        Evidence(type="metric", content="queue depth rising and heartbeat missing"),
        Evidence(type="runbook", content="restart worker is reversible in staging"),
        Evidence(type="log", content="worker timeout errors"),
    ]


def test_runbook_critic_reports_good_fit_for_bounded_evidence() -> None:
    critique = critique_runbook(_incident(), get_runbook("queue_backlog"), _evidence(), action_type="mock.execute_restart_worker")

    assert critique.fit == "good_fit"
    assert critique.blocks_auto_action is False
    assert critique.suggestions == []
    assert critique.to_dict()["fit"] == "good_fit"


def test_runbook_critic_failed_prior_reduces_fit_and_blocks_auto_action() -> None:
    failed_match = IncidentMemoryMatch(
        record=IncidentMemoryRecord(
            incident_id="prior-1",
            service="worker",
            environment="staging",
            fingerprint="queue_backlog_worker",
            root_cause="Worker queue degradation",
            runbook="queue_backlog",
            action_type="mock.execute_restart_worker",
            outcome="failed",
            action_status="failed",
        ),
        score=0.9,
        reasons=("same_service", "same_action_type"),
        warnings=("prior_failed_remediation",),
    )

    critique = critique_runbook(_incident(), get_runbook("queue_backlog"), _evidence(), memory_matches=[failed_match], action_type="mock.execute_restart_worker")

    assert critique.fit == "weak_fit"
    assert critique.blocks_auto_action is True
    assert any("prior failed remediation" in reason for reason in critique.reasons)
    assert any("compare the failed prior" in suggestion for suggestion in critique.suggestions)


def test_runbook_critic_insufficient_evidence_blocks_action() -> None:
    critique = critique_runbook(_incident(confidence=0.51), get_runbook("deploy_regression"), [Evidence(type="metric", content="5xx spike")], action_type="mock.create_rollback_pr")

    assert critique.fit == "insufficient_evidence"
    assert critique.blocks_auto_action is True
    assert "collect at least two independent evidence records" in critique.suggestions


def test_runbook_critic_protected_service_mutation_is_unsafe() -> None:
    critique = critique_runbook(_incident(service="payment-api"), get_runbook("deploy_regression"), _evidence(), action_type="mock.create_rollback_pr")

    assert critique.fit == "unsafe"
    assert critique.blocks_auto_action is True
    assert any("protected service" in reason for reason in critique.reasons)
    assert any("human approval" in suggestion for suggestion in critique.suggestions)


def test_runbook_critic_prohibited_action_is_unsafe_and_redacted() -> None:
    critique = critique_runbook(_incident(service="worker"), get_runbook("queue_backlog"), _evidence(), action_type="shell.run token=abc123")

    assert critique.fit == "unsafe"
    assert critique.blocks_auto_action is True
    assert "abc123" not in " ".join(critique.reasons + critique.suggestions)
