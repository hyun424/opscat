from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.schemas.incidents import MockAlertRequest
from app.services.incident_commander import COMMANDER_STAGES, build_incident_command
from app.services.incident_service import create_and_investigate


def test_incident_commander_outputs_complete_deterministic_lifecycle(db_session: Session) -> None:
    incident = create_and_investigate(
        db_session,
        MockAlertRequest(
            idempotency_key="p9-commander-loop",
            scenario="payment_bad_deploy",
            message="commander incident api_key=raw-secret ops@example.com deploy rollback",
        ),
    )

    first = build_incident_command(incident).to_dict()
    second = build_incident_command(incident).to_dict()

    assert json.dumps(first, sort_keys=True, default=str) == json.dumps(second, sort_keys=True, default=str)
    assert first["local_mock_only"] is True
    assert [stage["name"] for stage in first["stages"]] == list(COMMANDER_STAGES)
    for stage in first["stages"]:
        assert set(stage) >= {"name", "input_evidence", "decision", "confidence", "blockers", "next_step"}
    assert first["response_plan"]["steps"]
    assert first["readiness"]["route"] in {"local_mock_auto_allowed", "approval_required", "human_required", "blocked"}
    assert first["evidence_graph"]["nodes"]
    assert first["recovery_verification"]["status"]
    assert first["learning_signal"]["route"]
    assert first["next_action"]
    serialized = json.dumps(first, sort_keys=True, default=str)
    assert "raw-secret" not in serialized
    assert "ops@example.com" not in serialized
    assert "[REDACTED]" in serialized


def test_incident_commander_never_calls_network_or_shell(monkeypatch: Any) -> None:
    def forbidden_call(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("commander must stay pure local/mock")

    monkeypatch.setattr("socket.socket", forbidden_call)
    monkeypatch.setattr("subprocess.run", forbidden_call)

    command = build_incident_command({"id": "pure", "status": "new", "summary": "local evidence only", "evidence": []}).to_dict()

    assert command["local_mock_only"] is True
    assert command["readiness"]["route"] in {"human_required", "blocked"}
