from __future__ import annotations

import subprocess
import sys
from typing import Any

from tests.test_operator_dashboard import ALPHA_HEADERS
from tests.test_operator_dashboard_e2e import parse_dashboard


def test_p8_operator_detail_exposes_war_room_demo_flow_without_production_claims(client: Any) -> None:
    created = client.post(
        "/webhooks/alerts/mock?process_now=true",
        headers=ALPHA_HEADERS,
        json={"idempotency_key": "p8-demo-war-room", "scenario": "payment_bad_deploy", "message": "P8 war room demo incident"},
    )
    assert created.status_code == 201
    incident = created.json()

    detail_response = client.get(f"/operator/incidents/{incident['id']}", headers=ALPHA_HEADERS)

    assert detail_response.status_code == 200
    detail = parse_dashboard(detail_response.text)
    for required_testid in {
        "p8-war-room",
        "p8-reliability-score",
        "p8-runbook-critique",
        "p8-action-gate",
        "p8-human-questions",
        "p8-report-export",
    }:
        assert required_testid in detail.testids
    assert "alert -> war room -> score -> runbook critique -> action gate -> report" in detail.text
    assert "local/mock" in detail.text
    assert "unattended production operation" in detail.text
    assert "does not claim" in detail.text
    assert "form" not in detail.tags


def test_p8_demo_command_prints_war_room_url_and_local_mock_boundary() -> None:
    result = subprocess.run([sys.executable, "scripts/demo.py"], check=True, capture_output=True, text=True)

    assert "P8 flow: alert -> war room -> score -> runbook critique -> action gate -> report" in result.stdout
    assert "P8 War Room URL: /operator/incidents/" in result.stdout
    assert "P8 boundary: local/mock only; does not claim unattended production operation" in result.stdout
