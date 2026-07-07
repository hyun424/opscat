"""P7 reliability and safety lab contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.schemas.incidents import NightAutopilotConfig
from app.services.blast_radius import BlastRadiusScope, BlastRadiusService
from app.services.confidence_calibration import ConfidenceCalibrator
from app.services.incident_memory import IncidentMemory, IncidentMemoryRecord
from app.services.incident_service import create_and_investigate
from app.services.night_autopilot import simulate_night_autopilot
from app.services.reliability_dashboard import build_reliability_dashboard
from app.services.replay_service import ReplayService, load_replay_scenarios
from app.services.self_critique_service import SelfCritiqueService
from app.services.action_simulator import ActionSimulator
from app.schemas.incidents import MockAlertRequest


def test_p7_replay_harness_loads_30_scenarios_and_blocks_adversarial_actions() -> None:
    scenarios = load_replay_scenarios()
    assert len(scenarios) >= 30
    assert sum(1 for scenario in scenarios if scenario.adversarial) >= 12

    result = ReplayService().run_all(scenarios)

    assert result.total >= 30
    assert result.failed == 0
    assert result.metrics["dangerous_actions_blocked"] >= 12
    assert result.metrics["ambiguous_escalations"] >= 1
    assert result.metrics["false_positive_suppressed"] >= 1
    assert all(item.observed["provider_calls"] == [] for item in result.results)


def test_p7_confidence_calibration_reports_buckets_and_fail_closed_thresholds() -> None:
    result = ReplayService().run_all(load_replay_scenarios())
    report = ConfidenceCalibrator().calibrate([item.to_calibration_sample() for item in result.results])

    assert report.buckets
    assert report.recommended_auto_threshold >= 0.8
    assert report.overconfidence_count >= 1
    assert report.fail_closed({"confidence": 0.95, "evidence_count": 1, "conflicting_signals": 0, "ambiguous": False})
    assert report.fail_closed({"confidence": 0.86, "evidence_count": 4, "conflicting_signals": 1, "ambiguous": False})
    assert not report.fail_closed({"confidence": 0.9, "evidence_count": 4, "conflicting_signals": 0, "ambiguous": False})


def test_p7_action_proposal_contains_critique_blast_radius_simulation_and_memory(db_session: Session) -> None:
    incident = create_and_investigate(
        db_session,
        MockAlertRequest(
            idempotency_key="p7-metadata",
            scenario="worker_queue_backlog",
            service="worker",
            environment="staging",
        ),
    )

    action = incident.actions[0]
    assert "self_critique" in action.payload
    assert action.payload["self_critique"]["decision"] in {"proceed", "approval_required", "escalate"}
    assert action.payload["self_critique"]["missing_evidence"] == []
    assert "blast_radius" in action.payload
    assert action.payload["blast_radius"]["scope"] == "service"
    assert action.payload["blast_radius"]["rollback_available"] is True
    assert "simulation" in action.payload
    assert action.payload["simulation"]["status"] == "passed"
    assert action.payload["simulation"]["touched_resources"]
    assert "incident_memory" in action.payload
    assert action.payload["incident_memory"]["similar_incidents"]
    assert "failed prior" not in " ".join(action.policy_reasons).lower()

    stages = [event.event_type for event in incident.timeline]
    assert "decision_trace.critique" in stages
    assert "decision_trace.risk" in stages
    assert stages.index("decision_trace.critique") < stages.index("decision_trace.risk")


def test_p7_blast_radius_and_simulator_fail_closed() -> None:
    blast = BlastRadiusService().classify({"action_type": "shell.execute", "payload": {"cmd": "kubectl delete ns prod"}})
    assert blast.scope == BlastRadiusScope.PROHIBITED
    assert blast.allowed_for_auto is False

    simulation = ActionSimulator().simulate({"action_type": "unknown.mutate", "target": "prod", "environment": "production", "payload": {}})
    assert simulation.status == "blocked"
    assert simulation.precondition_gaps


def test_p7_incident_memory_returns_failed_prior_warnings() -> None:
    memory = IncidentMemory(
        records=[
            IncidentMemoryRecord(
                incident_id="old-1",
                service="worker",
                environment="staging",
                fingerprint="queue-backlog",
                root_cause="Queue worker degradation after broker maintenance",
                runbook="restart-worker",
                action_type="mock.execute_restart_worker",
                outcome="failed",
                summary="Restart made backlog worse",
            )
        ]
    )

    matches = memory.find_similar(
        service="worker",
        environment="staging",
        fingerprint="queue-backlog",
        root_cause="Queue worker degradation after broker maintenance",
        runbook="restart-worker",
        action_type="mock.execute_restart_worker",
    )

    assert matches[0].score >= 0.8
    assert matches[0].failed_prior_action is True
    assert "failed" in matches[0].warning.lower()


def test_p7_night_autopilot_v2_requires_confidence_blast_radius_simulation_and_memory(db_session: Session) -> None:
    allowed = simulate_night_autopilot(
        db_session,
        NightAutopilotConfig(
            allowed_services=["worker"],
            allowed_environments=["staging"],
            max_automatic_risk="low",
            max_attempts_per_incident=1,
        ),
    )
    assert allowed.actions_taken
    assert "Reliability gates: passed" in allowed.morning_report
    assert "Simulation: passed" in allowed.morning_report
    assert "Blast radius: service" in allowed.morning_report

    blocked = simulate_night_autopilot(
        db_session,
        NightAutopilotConfig(
            scenario="low_confidence_ambiguous",
            service="worker",
            environment="staging",
            allowed_services=["worker"],
            allowed_environments=["staging"],
            max_automatic_risk="low",
            max_attempts_per_incident=1,
        ),
    )
    assert blocked.actions_taken == []
    assert blocked.escalations
    assert "blocked action rationale" in blocked.morning_report.lower()


def test_p7_reliability_dashboard_metrics_from_replay_and_local_outcomes(db_session: Session) -> None:
    replay_result = ReplayService().run_all(load_replay_scenarios())
    dashboard = build_reliability_dashboard(db_session, replay_result)

    assert dashboard["replay_total"] >= 30
    assert dashboard["dangerous_actions_blocked"] >= 12
    assert "false_positive_suppression_rate" in dashboard
    assert "overconfidence_count" in dashboard
    assert "auto_remediation_success_rate" in dashboard
    assert dashboard["source"] == "local_mock_replay"


def test_p7_safety_and_release_docs_are_explicit_about_local_mock_boundary() -> None:
    security = Path("docs/security-review-p7.md").read_text(encoding="utf-8")
    summary = Path("docs/operations/p7-final-summary.md").read_text(encoding="utf-8")
    release = Path("docs/release-evidence.md").read_text(encoding="utf-8")

    required = [
        "replay",
        "adversarial",
        "confidence calibration",
        "self-critique",
        "blast radius",
        "action simulation",
        "incident memory",
        "Night Autopilot v2",
        "auth remains deferred",
        "local/mock",
    ]
    for term in required:
        assert term.lower() in security.lower()
    assert "P7-001" in summary and "P7-012" in summary
    assert "unattended production operation" in summary.lower()
    assert "scripts/run_replay_evals.py" in release
