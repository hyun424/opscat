"""Approval-aware action orchestration service for the OpsCat MVP."""

from __future__ import annotations

from dataclasses import asdict

from app.models.action import (
    ActionExecutionResult,
    ActionRequest,
    ActionStatus,
    ApprovalRecord,
    PolicyDecision,
)
from app.services.action_simulator import ActionSimulator
from app.services.policy_engine import PolicyContext, PolicyEngine
from app.tools.mock_actions import MockActionExecutor


class ActionService:
    def __init__(
        self,
        policy_engine: PolicyEngine | None = None,
        executor: MockActionExecutor | None = None,
        simulator: ActionSimulator | None = None,
    ) -> None:
        self.policy_engine = policy_engine or PolicyEngine()
        self.executor = executor or MockActionExecutor()
        self.simulator = simulator or ActionSimulator()
        self.approvals: dict[str, ApprovalRecord] = {}

    def propose(self, request: ActionRequest, context: PolicyContext | None = None) -> ApprovalRecord:
        evaluation = self.policy_engine.evaluate(request, context)
        record = ApprovalRecord(action_request=request, evaluation=evaluation)
        if evaluation.decision == PolicyDecision.DENY:
            record.status = ActionStatus.DENIED
        self.approvals[record.id] = record
        return record

    def approve(self, approval_id: str, actor: str, reason: str = "approved") -> ApprovalRecord:
        record = self._get(approval_id)
        if record.status != ActionStatus.PROPOSED:
            raise ValueError(f"Approval {approval_id} is not pending; current status={record.status}.")
        record.approve(actor, reason)
        return record

    def reject(self, approval_id: str, actor: str, reason: str = "rejected") -> ApprovalRecord:
        record = self._get(approval_id)
        if record.status != ActionStatus.PROPOSED:
            raise ValueError(f"Approval {approval_id} is not pending; current status={record.status}.")
        record.reject(actor, reason)
        return record

    def execute(self, approval_id: str, context: PolicyContext | None = None) -> ActionExecutionResult:
        record = self._get(approval_id)
        request = record.action_request
        if record.evaluation.decision == PolicyDecision.REQUIRE_APPROVAL:
            if record.status != ActionStatus.APPROVED:
                return ActionExecutionResult(
                    action_type=request.action_type,
                    target=request.target,
                    status=ActionStatus.FAILED,
                    message="Action requires approval before execution.",
                )
            request = ActionRequest(
                action_type=request.action_type,
                target=request.target,
                environment=request.environment,
                tenant_id=request.tenant_id,
                workspace_id=request.workspace_id,
                payload=request.payload,
                requester=request.requester,
                incident_id=request.incident_id,
                approved=True,
                approval_id=approval_id,
            )
            evaluation = self.policy_engine.evaluate(request, context)
            if not evaluation.executable_now:
                return ActionExecutionResult(
                    action_type=request.action_type,
                    target=request.target,
                    status=ActionStatus.FAILED,
                    message=f"Approved action still failed policy: {evaluation.reason}",
                )
        elif not record.evaluation.executable_now:
            return ActionExecutionResult(
                action_type=request.action_type,
                target=request.target,
                status=ActionStatus.FAILED,
                message=f"Action is not executable: {record.evaluation.reason}",
            )

        simulation = self.simulator.simulate(request)
        if not simulation.success:
            return ActionExecutionResult(
                action_type=request.action_type,
                target=request.target,
                status=ActionStatus.FAILED,
                message="Action simulation failed: " + "; ".join(simulation.precondition_gaps or simulation.residual_risks),
                output={"simulation": simulation.to_dict()},
            )

        result = self.executor.execute(request)
        result = ActionExecutionResult(
            action_type=result.action_type,
            target=result.target,
            status=result.status,
            message=result.message,
            output={**dict(result.output), "simulation": simulation.to_dict()},
            verification=result.verification,
        )
        if result.status == ActionStatus.EXECUTED:
            record.status = ActionStatus.EXECUTED
        elif result.status == ActionStatus.FAILED:
            record.status = ActionStatus.FAILED
        return result

    def serialize_record(self, record: ApprovalRecord) -> dict:
        data = asdict(record)
        data["status"] = record.status.value
        data["evaluation"]["decision"] = record.evaluation.decision.value
        data["evaluation"]["risk_level"] = record.evaluation.risk_level.value
        data["audit_context"] = {
            "tenant_id": record.action_request.tenant_id,
            "workspace_id": record.action_request.workspace_id,
            "incident_id": record.action_request.incident_id,
            "action_type": record.action_request.action_type,
            "decision": record.evaluation.decision.value,
            "risk_level": record.evaluation.risk_level.value,
            "requires_approval": record.evaluation.requires_approval,
            "policy_route": record.evaluation.route.value,
            "preconditions": list(record.evaluation.preconditions),
            "post_checks": list(record.evaluation.post_checks),
        }
        if record.evaluation.action:
            data["evaluation"]["action"]["base_risk"] = record.evaluation.action.base_risk.value
        return data

    def _get(self, approval_id: str) -> ApprovalRecord:
        try:
            return self.approvals[approval_id]
        except KeyError as exc:
            raise KeyError(f"Unknown approval id {approval_id!r}.") from exc
