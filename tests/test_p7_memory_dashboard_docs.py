from __future__ import annotations

from typing import Any

from app.services.incident_memory import IncidentMemory, IncidentMemoryRecord
from tests.test_operator_dashboard import ALPHA_HEADERS


def test_incident_memory_retrieves_failed_prior_remediation_warning() -> None:
    memory = IncidentMemory()
    memory.add(
        IncidentMemoryRecord(
            incident_id="old-1",
            service="worker",
            environment="staging",
            fingerprint="queue-backlog",
            root_cause="worker queue degradation",
            runbook="restart_worker",
            action_type="mock.execute_restart_worker",
            outcome="failed",
        )
    )

    matches = memory.search(service="worker", environment="staging", fingerprint="queue-backlog", root_cause="worker queue degradation", runbook="restart_worker", action_type="mock.execute_restart_worker")

    assert matches
    assert matches[0].similarity >= 0.75
    assert matches[0].failed_remediation_warning is True


def test_operator_reliability_dashboard_api_exposes_p7_metrics(client: Any) -> None:
    response = client.get("/operator/reliability", headers=ALPHA_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["local_mock_only"] is True
    assert "accuracy" in body
    assert "blocked_dangerous_actions" in body
    assert "auto_remediation_success" in body


def test_p7_security_and_release_docs_state_boundaries() -> None:
    security = open("docs/security-review-p7.md", encoding="utf-8").read().lower()
    threat_model = open("docs/threat-model.md", encoding="utf-8").read().lower()
    summary = open("docs/operations/p7-final-summary.md", encoding="utf-8").read().lower()
    release = open("docs/release-evidence.md", encoding="utf-8").read().lower()

    for text in (security, threat_model, summary, release):
        assert "p7" in text
        assert "auth" in text and "deferred" in text
        assert "local/mock" in text
    assert "memory poisoning" in security
    assert "run_replay_evals" in release
