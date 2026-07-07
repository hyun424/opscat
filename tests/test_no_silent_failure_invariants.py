"""P0 no-silent-failure invariants for terminal and approval-waiting paths."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest

from app.config import get_settings

SECRET_MESSAGE = "api_key=plain_secret_value Bearer raw.jwt.token ops@example.com"
SECRET_VALUES = ("plain_secret_value", "raw.jwt.token", "ops@example.com")
WAITING_OR_TERMINAL_STATES = {"waiting_approval", "resolved", "escalated", "failed", "false_positive"}

PATH_CASES = [
    pytest.param(
        {
            "name": "resolved_executed",
            "alert": {"scenario": "payment_api_deploy_regression", "environment": "staging", "severity": "high"},
            "decision": "approve",
            "expected_incident_status": "resolved",
            "expected_action_status": "executed",
            "expected_policy_decision": "ALLOW",
            "expected_risk_level": "medium",
            "requires_escalation_payload": False,
            "expected_events": {"approval_granted", "action_executed", "recovery_verified"},
        },
        id="resolved-executed",
    ),
    pytest.param(
        {
            "name": "escalated_low_confidence",
            "alert": {"scenario": "low_confidence_ambiguous", "environment": "staging", "severity": "high"},
            "decision": None,
            "expected_incident_status": "escalated",
            "expected_action_status": "escalated",
            "expected_policy_decision": "ESCALATE",
            "expected_risk_level": "high",
            "requires_escalation_payload": True,
            "expected_escalation_trigger": "low_confidence",
            "expected_events": {"human_escalation_required", "policy_decision"},
        },
        id="escalated-low-confidence",
    ),
    pytest.param(
        {
            "name": "denied_prohibited",
            "alert": {
                "scenario": "protected_auth_incident",
                "service": "auth-api",
                "environment": "production",
                "severity": "critical",
            },
            "decision": None,
            "expected_incident_status": "escalated",
            "expected_action_status": "denied",
            "expected_policy_decision": "DENY",
            "expected_risk_level": "prohibited",
            "requires_escalation_payload": True,
            "expected_escalation_trigger": "policy_denied_action",
            "expected_events": {"human_escalation_required", "policy_decision"},
        },
        id="denied-prohibited",
    ),
    pytest.param(
        {
            "name": "approval_waiting",
            "alert": {"scenario": "payment_bad_deploy", "environment": "production", "severity": "high"},
            "decision": None,
            "expected_incident_status": "waiting_approval",
            "expected_action_status": "proposed",
            "expected_policy_decision": "REQUIRE_APPROVAL",
            "expected_risk_level": "medium",
            "requires_escalation_payload": True,
            "expected_escalation_trigger": "protected_domain_or_high_impact",
            "expected_events": {"human_escalation_required", "policy_decision"},
        },
        id="approval-waiting",
    ),
    pytest.param(
        {
            "name": "approval_rejected",
            "alert": {"scenario": "payment_api_deploy_regression", "environment": "staging", "severity": "high"},
            "decision": "reject",
            "expected_incident_status": "escalated",
            "expected_action_status": "rejected",
            "expected_policy_decision": "REQUIRE_APPROVAL",
            "expected_risk_level": "medium",
            "requires_escalation_payload": False,
            "expected_events": {"approval_rejected"},
        },
        id="approval-rejected",
    ),
    pytest.param(
        {
            "name": "verification_failed",
            "alert": {"scenario": "verification_failure", "environment": "production", "severity": "high"},
            "decision": "approve",
            "expected_incident_status": "escalated",
            "expected_action_status": "executed",
            "expected_policy_decision": "ALLOW",
            "expected_risk_level": "medium",
            "requires_escalation_payload": True,
            "expected_escalation_trigger": "post_check_failed",
            "expected_events": {"approval_granted", "action_executed", "recovery_verified", "human_escalation_required"},
        },
        id="verification-failed",
    ),
]


@pytest.fixture(autouse=True)
def isolated_report_dir(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Keep approval/report paths from writing into repository data fixtures."""

    monkeypatch.setenv("REPORT_DIR", str(tmp_path / "reports"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_waiting_or_terminal_paths_have_evidence_and_timeline(client: Any, path_case: dict[str, Any]) -> None:
    result = _exercise_path(client, path_case)
    incident = result["incident"]

    assert incident["status"] in WAITING_OR_TERMINAL_STATES
    assert incident["status"] == path_case["expected_incident_status"]
    assert len(incident["evidence"]) >= 2
    assert len(incident["timeline"]) >= 3

    event_types = {event["event_type"] for event in incident["timeline"]}
    assert path_case["expected_events"] <= event_types
    assert all(event["content"] for event in incident["timeline"])


@pytest.mark.parametrize("path_case", PATH_CASES)
def test_waiting_or_terminal_paths_have_report_or_escalation_payload(client: Any, path_case: dict[str, Any]) -> None:
    result = _exercise_path(client, path_case)
    incident = result["incident"]
    action = _first_action(incident)
    report_text = _fetch_report(client, incident["id"])

    assert "# Incident Report:" in report_text
    assert "## Evidence" in report_text
    assert "## Actions" in report_text
    assert "## Failure Mode Analysis" in report_text
    assert "## Timeline" in report_text
    assert action["action_type"] in report_text

    if path_case["requires_escalation_payload"]:
        payload = action["escalation_payload"]
        assert action["escalation_required"] is True
        assert payload["wake_human"] is True
        assert payload["escalation_decision"] == "wake_human"
        assert path_case["expected_escalation_trigger"] in payload["triggers"]
        assert payload["evidence_collected"]
        assert payload["links"]["incident"].endswith(incident["id"])


@pytest.mark.parametrize("path_case", PATH_CASES)
def test_path_action_statuses_are_consistent(client: Any, path_case: dict[str, Any]) -> None:
    result = _exercise_path(client, path_case)
    incident = result["incident"]
    action = _first_action(incident)

    assert action["status"] == path_case["expected_action_status"]
    assert action["policy_decision"] == path_case["expected_policy_decision"]
    assert action["risk_level"] == path_case["expected_risk_level"]
    assert set(action["evidence_ids"]).issubset({item["id"] for item in incident["evidence"]})

    if action["status"] == "executed":
        assert action["execution_result"]["ok"] is True
        assert action["execution_result"]["status"] == "executed"
        assert "verification" in action["execution_result"]
    else:
        assert action["execution_result"] is None

    if action["status"] == "proposed":
        assert action["requires_approval"] is True
        assert incident["status"] == "waiting_approval"
    if action["status"] == "denied":
        assert action["policy_decision"] == "DENY"
        assert action["risk_level"] == "prohibited"
    if action["status"] == "rejected":
        assert incident["status"] == "escalated"


@pytest.mark.parametrize("path_case", PATH_CASES)
def test_audit_outputs_redact_secret_material(client: Any, path_case: dict[str, Any]) -> None:
    result = _exercise_path(client, path_case)
    incident = result["incident"]
    report_text = _fetch_report(client, incident["id"])
    serialized_audit = json.dumps({"incident": incident, "report": report_text}, default=str, sort_keys=True)

    for secret in SECRET_VALUES:
        assert secret not in serialized_audit
    assert "[REDACTED]" in serialized_audit


@pytest.fixture(params=PATH_CASES)
def path_case(request: pytest.FixtureRequest) -> dict[str, Any]:
    return request.param


def _exercise_path(client: Any, path_case: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "idempotency_key": f"p0-002-{path_case['name']}",
        "message": f"P0-002 invariant probe {path_case['name']} {SECRET_MESSAGE}",
        **path_case["alert"],
    }
    created = client.post("/webhooks/alerts/mock?process_now=true", json=payload)
    assert created.status_code == 201, created.text
    incident = created.json()
    action = _first_action(incident)

    if path_case["decision"] is None:
        return {"incident": incident, "approval_response": None}

    decided = client.post(
        f"/approvals/{action['id']}",
        json={
            "decision": path_case["decision"],
            "actor": "p0-002-test-oncall",
            "reason": f"P0-002 exercise {path_case['name']} path",
        },
    )
    assert decided.status_code == 200, decided.text
    body = decided.json()
    return {"incident": body["incident"], "approval_response": body}


def _first_action(incident: dict[str, Any]) -> dict[str, Any]:
    assert incident["actions"], incident
    return incident["actions"][0]


def _fetch_report(client: Any, incident_id: str) -> str:
    response = client.get(f"/incidents/{incident_id}/report")
    assert response.status_code == 200, response.text
    return response.json()["report"]
