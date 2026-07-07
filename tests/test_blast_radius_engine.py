from __future__ import annotations

from app.models.action import ActionMetadata, ActionRequest, RiskLevel
from app.services.blast_radius import BlastRadiusLevel, BlastRadiusService
from app.services.policy_engine import PolicyContext, PolicyEngine
from app.services.risk_engine import RiskEngine


def test_blast_radius_classifies_registered_mock_actions() -> None:
    service = BlastRadiusService()

    report = service.evaluate(ActionRequest(action_type="report.generate", target="incident-1"))
    rollback = service.evaluate(ActionRequest(action_type="mock.create_rollback_pr", target="payment-api", environment="staging"))
    restart = service.evaluate(ActionRequest(action_type="mock.execute_restart_worker", target="worker-1", environment="staging"))

    assert report.level == BlastRadiusLevel.LOCAL
    assert report.rollback_available is True
    assert report.approval_required is False
    assert rollback.level == BlastRadiusLevel.WORKSPACE
    assert rollback.rollback_available is True
    assert rollback.approval_required is True
    assert "mock repository draft" in rollback.reason
    assert restart.level == BlastRadiusLevel.SERVICE
    assert restart.touched_resources == ("worker-1",)


def test_blast_radius_blocks_unknown_unbounded_and_prohibited_scopes() -> None:
    service = BlastRadiusService()

    unknown = service.evaluate(ActionRequest(action_type="unknown.provider.mutate", target="payment-api"))
    prohibited = service.evaluate(ActionRequest(action_type="shell.execute", target="prod-shell", environment="production"))

    assert unknown.level == BlastRadiusLevel.UNKNOWN
    assert unknown.allowed is False
    assert unknown.approval_required is True
    assert prohibited.level == BlastRadiusLevel.PROHIBITED
    assert prohibited.allowed is False
    assert prohibited.rollback_available is False


def test_policy_denies_action_with_unbounded_blast_radius_even_if_registered() -> None:
    unsafe_action = ActionMetadata(
        name="mock.unbounded_write",
        description="Bad test action",
        base_risk=RiskLevel.LOW,
        is_read_only=False,
        is_mutation=True,
        reversible=True,
        blast_radius="unknown external fleet",
        default_requires_approval=False,
        required_capabilities=("mock:workers:restart",),
    )
    engine = PolicyEngine(RiskEngine({"mock.unbounded_write": unsafe_action}))

    result = engine.evaluate(
        ActionRequest(action_type="mock.unbounded_write", target="fleet", environment="staging", approved=True),
        PolicyContext(environment="staging"),
    )

    assert result.decision.value == "DENY"
    assert result.blast_radius is not None
    assert result.blast_radius.level == BlastRadiusLevel.UNKNOWN
    assert "blast radius" in result.reason
