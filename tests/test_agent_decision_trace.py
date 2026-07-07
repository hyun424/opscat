from __future__ import annotations

import json
from typing import Any


def test_full_fixture_incident_records_all_agentic_trace_stages_without_secrets(client: Any) -> None:
    created = client.post("/webhooks/alerts/mock?process_now=true", json={"scenario": "payment_api_deploy_regression", "message": "token=secret user@example.com"})
    assert created.status_code == 201, created.text
    incident_id = created.json()["id"]

    trace = client.get(f"/incidents/{incident_id}/trace")
    assert trace.status_code == 200, trace.text
    body = trace.json()
    payload = json.loads(body["json"])
    stages = {item["stage"] for item in payload}

    assert {"observe", "correlate", "diagnose", "plan", "risk", "act", "verify"}.issubset(stages)
    serialized = json.dumps(body)
    assert "secret" not in serialized
    assert "user@example.com" not in serialized
