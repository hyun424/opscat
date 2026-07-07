from __future__ import annotations

from typing import Any

from tests.test_operator_dashboard import ALPHA_HEADERS
from tests.test_operator_dashboard_e2e import parse_dashboard


def test_operator_detail_exposes_p9_commander_without_mutation_forms(client: Any) -> None:
    created = client.post(
        "/webhooks/alerts/mock?process_now=true",
        headers=ALPHA_HEADERS,
        json={"idempotency_key": "p9-ui", "scenario": "payment_bad_deploy", "message": "p9 commander ui"},
    )
    assert created.status_code == 201
    incident_id = created.json()["id"]

    api = client.get(f"/incidents/{incident_id}/war-room", headers=ALPHA_HEADERS)
    assert api.status_code == 200
    war_room = api.json()["war_room"]
    assert "commander" in war_room
    assert war_room["commander"]["response_plan"]["steps"]
    assert war_room["commander"]["evidence_graph"]["nodes"]

    page = client.get(f"/operator/incidents/{incident_id}", headers=ALPHA_HEADERS)
    assert page.status_code == 200
    parsed = parse_dashboard(page.text)

    for testid in {
        "p9-commander-panel",
        "p9-commander-stages",
        "p9-response-plan",
        "p9-readiness",
        "p9-evidence-graph",
        "p9-recovery-verification",
        "p9-learning-signal",
    }:
        assert testid in parsed.testids
    assert "Autonomous Incident Commander" in parsed.text
    assert "local/mock only" in parsed.text
    assert "unattended production operation" in parsed.text
    assert "form" not in parsed.tags
