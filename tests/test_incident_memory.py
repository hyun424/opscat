from __future__ import annotations

from app.services.incident_memory import IncidentMemory, IncidentMemoryRecord


def test_incident_memory_retrieves_similar_successes_and_failed_warnings() -> None:
    memory = IncidentMemory()
    memory.add(IncidentMemoryRecord(id="old-ok", service="worker", environment="staging", fingerprint="queue", root_cause="queue backlog", runbook="restart", action_type="mock.execute_restart_worker", outcome="resolved"))
    memory.add(IncidentMemoryRecord(id="old-fail", service="worker", environment="staging", fingerprint="queue", root_cause="queue backlog", runbook="restart", action_type="mock.execute_restart_worker", outcome="failed"))

    matches = memory.search(service="worker", environment="staging", fingerprint="queue", root_cause="queue backlog", runbook="restart", action_type="mock.execute_restart_worker")

    assert matches[0].score >= 0.8
    assert any(match.failed_past_remediation for match in matches)
    assert matches[0].reasons
