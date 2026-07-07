from __future__ import annotations

from app.models import Incident
from app.services.root_cause_service import RootCauseCandidate
from app.services.runbook_service import RUNBOOKS, select_runbook


def test_recent_deploy_regression_selects_deploy_runbook_with_declared_step_contract() -> None:
    incident = Incident(service="payment-api", environment="staging", severity="high", source="mock", status="investigating", summary="deploy regression")
    runbook = select_runbook(incident, [RootCauseCandidate("Recent deploy regression", 0.91)])

    assert runbook.key == "deploy_regression"
    assert any(step.action_type == "mock.create_rollback_pr" for step in runbook.steps)
    for runbook_item in RUNBOOKS:
        for step in runbook_item.steps:
            assert step.required_permission
            assert step.risk_hint in {"read_only", "low", "medium", "high", "prohibited"}
            assert isinstance(step.dry_run_supported, bool)
            assert step.rollback_expectation
            assert step.verification_check


def test_low_confidence_selects_diagnostic_only_runbook() -> None:
    incident = Incident(service="unknown", environment="staging", severity="high", source="mock", status="investigating", summary="unknown symptom")

    runbook = select_runbook(incident, [RootCauseCandidate("Ambiguous", 0.31)])

    assert runbook.key == "diagnostic_only"
    assert all(step.risk_hint == "read_only" for step in runbook.steps)
