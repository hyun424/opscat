from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.schemas.incidents import MockAlertRequest
from app.services.evidence_graph import build_evidence_graph
from app.services.incident_service import create_and_investigate
from app.services.response_planner import build_response_plan


def test_evidence_graph_links_incident_evidence_hypotheses_plan_and_action_deterministically(db_session: Session) -> None:
    incident = create_and_investigate(
        db_session,
        MockAlertRequest(idempotency_key="p9-graph", scenario="payment_bad_deploy", message="deploy regression with timeout evidence"),
    )
    plan = build_response_plan(incident)

    first = build_evidence_graph(incident, plan=plan).to_dict()
    second = build_evidence_graph(incident, plan=plan).to_dict()

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert first["local_mock_only"] is True
    assert first["nodes"]
    assert first["edges"]
    node_types = {node["type"] for node in first["nodes"]}
    assert {"incident", "evidence", "hypothesis", "plan_step"} <= node_types
    assert all(set(node) >= {"id", "type", "label", "status", "metadata"} for node in first["nodes"])
    assert all(set(edge) >= {"source", "target", "relationship"} for edge in first["edges"])
