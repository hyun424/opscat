"""Decision trace read-model gates for P6 operator review."""

from __future__ import annotations

import json
from typing import Any

from app.services.decision_trace_service import DECISION_TRACE_STAGES, build_decision_trace
from tests.test_operator_dashboard import ALPHA_HEADERS, BETA_HEADERS


def test_decision_trace_covers_agentic_stages_and_redacts_sensitive_payloads(client: Any) -> None:
    created = client.post(
        "/webhooks/alerts/mock?process_now=true",
        headers=ALPHA_HEADERS,
        json={
            "idempotency_key": "trace-redaction",
            "scenario": "payment_bad_deploy",
            "message": "deploy failed api_key=plain-secret Bearer raw.jwt.token ops@example.com",
        },
    )
    assert created.status_code == 201, created.text
    incident = created.json()
    action = incident["actions"][0]
    approved = client.post(
        f"/approvals/{action['id']}",
        headers=ALPHA_HEADERS,
        json={"decision": "approve", "reason": "trace coverage"},
    )
    assert approved.status_code == 200, approved.text

    fetched = client.get(f"/incidents/{incident['id']}", headers=ALPHA_HEADERS)
    assert fetched.status_code == 200
    trace = build_decision_trace(fetched.json())

    assert [entry.stage for entry in trace] == list(DECISION_TRACE_STAGES)
    assert all(entry.tenant_id == "tenant-a" and entry.workspace_id == "alpha" for entry in trace)
    assert any(entry.action_id == action["id"] for entry in trace)
    assert any(entry.policy_decision in {"ALLOW", "REQUIRE_APPROVAL"} for entry in trace)
    risk_entry = next(entry for entry in trace if entry.stage == "risk")
    assert risk_entry.details["blast_radius"]["level"] == "workspace"
    assert risk_entry.details["simulation"]["status"] == "pass"
    serialized = json.dumps([entry.to_dict() for entry in trace], sort_keys=True)
    assert "plain-secret" not in serialized
    assert "raw.jwt.token" not in serialized
    assert "ops@example.com" not in serialized
    assert "[REDACTED]" in serialized


def test_decision_trace_endpoint_respects_workspace_scope(client: Any) -> None:
    created = client.post(
        "/webhooks/alerts/mock?process_now=true",
        headers=ALPHA_HEADERS,
        json={"idempotency_key": "trace-scope", "scenario": "payment_bad_deploy"},
    )
    assert created.status_code == 201

    visible = client.get(f"/incidents/{created.json()['id']}/decision-trace", headers=ALPHA_HEADERS)
    hidden = client.get(f"/incidents/{created.json()['id']}/decision-trace", headers=BETA_HEADERS)

    assert visible.status_code == 200
    assert [entry["stage"] for entry in visible.json()["decision_trace"]] == list(DECISION_TRACE_STAGES)
    assert hidden.status_code == 404
