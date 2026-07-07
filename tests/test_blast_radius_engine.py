from __future__ import annotations

from app.models.action import ActionRequest
from app.services.blast_radius import BlastRadiusEngine


def test_blast_radius_blocks_unknown_shell_cloud_and_database_actions() -> None:
    engine = BlastRadiusEngine()
    for action_type in ("shell.execute", "cloud.delete_resource", "database.mutate", "made.up.action"):
        result = engine.classify(ActionRequest(action_type=action_type, target="prod", environment="production"))
        assert result.blocked is True
        assert result.scope in {"unknown", "prohibited", "global"}


def test_low_risk_auto_actions_are_bounded_and_rollback_available() -> None:
    result = BlastRadiusEngine().classify(ActionRequest(action_type="mock.execute_restart_worker", target="worker:staging", environment="staging"))

    assert result.scope == "service"
    assert result.rollback_available is True
    assert result.reversible is True
    assert result.blocked is False
