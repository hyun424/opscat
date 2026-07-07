from __future__ import annotations

from sqlalchemy.orm import Session

from app.schemas.incidents import MockAlertRequest
from app.services.incident_service import create_and_investigate
from app.services.response_planner import build_response_plan


def test_response_planner_emits_multistep_safe_local_mock_plan(db_session: Session) -> None:
    incident = create_and_investigate(
        db_session,
        MockAlertRequest(
            idempotency_key="p9-planner-safe",
            scenario="payment_bad_deploy",
            service="payment-api",
            environment="staging",
            message="5xx spike after deploy v1.42 rollback candidate",
        ),
    )

    plan = build_response_plan(incident)
    body = plan.to_dict()

    assert body["local_mock_only"] is True
    assert body["route"] in {"approval_required", "local_mock_auto_allowed", "human_required"}
    assert len(body["steps"]) >= 2
    for step in body["steps"]:
        assert set(step) >= {
            "id",
            "type",
            "goal",
            "preconditions",
            "required_evidence",
            "risk",
            "expected_output",
            "rollback_expectation",
            "verification_check",
            "requires_human",
        }
        assert step["action_type"].startswith("mock.")
    assert any(step["type"] == "safe_local_mock_action" for step in body["steps"])


def test_response_planner_stops_unknown_or_high_risk_at_human_gate(db_session: Session) -> None:
    incident = create_and_investigate(
        db_session,
        MockAlertRequest(
            idempotency_key="p9-planner-unknown",
            scenario="ambiguous",
            service="unknown-service",
            environment="prod",
            message="ambiguous provider issue with unknown blast radius",
        ),
    )

    plan = build_response_plan(incident)
    body = plan.to_dict()

    assert body["route"] == "human_required"
    assert body["blocking_reasons"]
    assert all(step["type"] != "safe_local_mock_action" or step["requires_human"] for step in body["steps"])
