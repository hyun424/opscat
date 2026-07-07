from __future__ import annotations

from app.models import Evidence, Incident
from app.services.root_cause_service import generate_root_cause_candidates


def test_recent_deploy_regression_ranks_above_generic_traffic_spike_and_redacts() -> None:
    incident = Incident(service="payment-api", environment="staging", severity="high", source="mock", status="investigating", summary="Timeout spike after deploy v1.42 token=secret")
    evidence = [
        Evidence(id="ev-deploy", incident_id="inc", type="deploy", source="mock", content="Deploy v1.42 immediately preceded TimeoutError api_key=raw"),
        Evidence(id="ev-noise", incident_id="inc", type="log", source="mock", content="unrelated traffic spike noise"),
    ]

    candidates = generate_root_cause_candidates(incident, evidence)

    assert candidates[0].hypothesis == "Recent deploy regression"
    assert candidates[0].confidence > candidates[1].confidence
    assert "ev-deploy" in candidates[0].evidence
    assert candidates[0].recommended_next_diagnostic == "mock.get_recent_deploys"
