from __future__ import annotations

from app.models import Evidence, Incident
from app.services.self_critique_service import critique_diagnosis


def test_self_critique_flags_missing_evidence_and_alternate_causes() -> None:
    incident = Incident(service="payment-api", environment="staging", severity="high", confidence=0.64, root_cause_candidate="deploy regression", alert_payload={})
    evidence = [Evidence(type="log", content="timeout spike but conflicting provider errors")]

    critique = critique_diagnosis(incident, evidence, alternate_causes=["provider outage"], action_type="mock.create_rollback_pr")

    assert critique.requires_human is True
    assert critique.missing_evidence
    assert critique.alternate_causes == ["provider outage"]
    assert critique.contradiction_flags


def test_self_critique_passes_strong_bounded_mock_action() -> None:
    incident = Incident(service="worker", environment="staging", severity="medium", confidence=0.86, root_cause_candidate="queue backlog", alert_payload={})
    evidence = [Evidence(type="metric", content="queue latency high"), Evidence(type="runbook", content="restart reversible"), Evidence(type="deploy", content="no deploy")]

    critique = critique_diagnosis(incident, evidence, alternate_causes=[], action_type="mock.execute_restart_worker")

    assert critique.requires_human is False
    assert not critique.missing_evidence
