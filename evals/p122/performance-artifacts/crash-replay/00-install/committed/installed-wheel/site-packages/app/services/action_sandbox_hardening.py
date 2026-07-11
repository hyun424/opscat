"""P79 action sandbox hardening evaluator.

Evaluates proposed actions against local/mock sandbox boundaries and returns
allow, approval-required, mock-only, or block decisions. This module never
executes actions or contacts external systems.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Self

from app.services.redaction import redact_value
from app.services.risk_engine import RiskEngine

_BOUNDARY: dict[str, bool] = {
    "local_mock_only": True,
    "live_api_calls_enabled": False,
    "credential_access_enabled": False,
    "network_calls_enabled": False,
    "production_mutation_enabled": False,
    "remediation_execution_enabled": False,
    "shell_execution_enabled": False,
    "action_execution_enabled": False,
    "default_external_model_calls": False,
    "unattended_production_operation_claimed": False,
}

_SAFE_BLAST_RADIUS = {"none", "local", "service", "workspace"}
_APPROVED_STATES = {"approved"}
_PENDING_APPROVAL_STATES = {"pending", "requested"}
_NO_APPROVAL_STATES = {"not_required", "not_requested", "missing", "none", ""}


class SandboxDecision(StrEnum):
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    MOCK_ONLY = "mock_only"
    BLOCK = "block"


@dataclass(frozen=True)
class ProposedAction:
    id: str
    action_type: str
    target: str
    environment: str
    blast_radius: str
    reversible: bool
    approval_state: str
    dry_run_capable: bool
    dry_run_only: bool
    uses_credentials: bool
    uses_network: bool
    mutates_production: bool
    executes_shell: bool

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        return cls(
            id=str(data.get("id", "proposal")),
            action_type=str(data.get("action_type", "unknown")),
            target=str(data.get("target", "unknown")),
            environment=str(data.get("environment", "local")).lower(),
            blast_radius=str(data.get("blast_radius", "unknown")).lower(),
            reversible=data.get("reversible") is True,
            approval_state=str(data.get("approval_state", "missing")).lower(),
            dry_run_capable=data.get("dry_run_capable") is True,
            dry_run_only=data.get("dry_run_only") is True,
            uses_credentials=data.get("uses_credentials") is True,
            uses_network=data.get("uses_network") is True,
            mutates_production=data.get("mutates_production") is True,
            executes_shell=data.get("executes_shell") is True,
        )


@dataclass(frozen=True)
class SandboxEvaluation:
    proposal_id: str
    action_type: str
    decision: SandboxDecision
    requires_approval: bool
    mock_only: bool
    checks: dict[str, bool]
    blocked_reasons: tuple[str, ...]
    approval_reasons: tuple[str, ...]
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "proposal_id": self.proposal_id,
            "action_type": self.action_type,
            "decision": self.decision.value,
            "requires_approval": self.requires_approval,
            "mock_only": self.mock_only,
            "checks": self.checks,
            "blocked_reasons": list(self.blocked_reasons),
            "approval_reasons": list(self.approval_reasons),
            "notes": list(self.notes),
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


@dataclass(frozen=True)
class SandboxReport:
    incident: Mapping[str, Any]
    proposals: tuple[ProposedAction, ...]
    decisions: tuple[SandboxEvaluation, ...]

    @classmethod
    def from_proposals(cls, incident: Mapping[str, Any], proposals: Sequence[ProposedAction]) -> Self:
        risk_engine = RiskEngine()
        decisions = tuple(_evaluate_proposal(proposal, risk_engine) for proposal in proposals)
        return cls(incident=incident, proposals=tuple(proposals), decisions=decisions)

    def to_dict(self) -> dict[str, Any]:
        allowed_count = _decision_count(self.decisions, SandboxDecision.ALLOW)
        approval_count = _decision_count(self.decisions, SandboxDecision.REQUIRE_APPROVAL)
        mock_only_count = _decision_count(self.decisions, SandboxDecision.MOCK_ONLY)
        blocked_count = _decision_count(self.decisions, SandboxDecision.BLOCK)
        payload = {
            "summary": {
                "incident_id": str(self.incident.get("id", "p79-incident")),
                "proposal_count": len(self.proposals),
                "allowed_count": allowed_count,
                "approval_required_count": approval_count,
                "mock_only_count": mock_only_count,
                "blocked_count": blocked_count,
                "action_execution_count": 0,
                "live_api_call_count": 0,
                "credential_read_count": 0,
                "network_call_count": 0,
                "production_mutation_count": 0,
                "shell_execution_count": 0,
                "passed": len(self.proposals) >= 5
                and allowed_count >= 1
                and approval_count >= 1
                and mock_only_count >= 1
                and blocked_count >= 2,
            },
            "boundary": dict(_BOUNDARY),
            "incident": redact_value(dict(self.incident)),
            "decisions": [decision.to_dict() for decision in self.decisions],
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


def evaluate_action_sandbox_fixture(path: str | Path) -> SandboxReport:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    incident = _mapping(data.get("incident"))
    proposals = tuple(ProposedAction.from_dict(item) for item in _sequence(data.get("proposals", ())) if isinstance(item, Mapping))
    return SandboxReport.from_proposals(incident, proposals)


def render_action_sandbox_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    lines = [
        "# OpsCat Action Sandbox Hardening",
        "",
        "P79 evaluates proposed actions without executing them or contacting live systems.",
        "",
        "## Summary",
        "",
        f"- Incident: {summary.get('incident_id', 'unknown')}",
        f"- Proposals: {summary.get('proposal_count', 0)}",
        f"- Allowed: {summary.get('allowed_count', 0)}",
        f"- Approval required: {summary.get('approval_required_count', 0)}",
        f"- Mock-only: {summary.get('mock_only_count', 0)}",
        f"- Blocked: {summary.get('blocked_count', 0)}",
        f"- Passed: {summary.get('passed', False)}",
        "",
        "## Decisions",
        "",
    ]
    for decision in _sequence(payload.get("decisions", ())):
        if isinstance(decision, Mapping):
            reasons = ", ".join(str(item) for item in _sequence(decision.get("blocked_reasons", ()))) or "none"
            approval = ", ".join(str(item) for item in _sequence(decision.get("approval_reasons", ()))) or "none"
            lines.append(
                f"- `{decision.get('proposal_id')}` decision={decision.get('decision')} "
                f"approval={decision.get('requires_approval')} blocked={reasons} approval_reasons={approval}"
            )
    lines.extend(
        [
            "",
            "## Zero-execution boundary",
            "",
            "- Local/mock evaluation only.",
            "- No live APIs, credentials, network calls, production mutation, shell execution, or action execution.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_action_sandbox_outputs(
    payload: Mapping[str, Any],
    *,
    output_json: str | Path | None = None,
    output_md: str | Path | None = None,
) -> None:
    if output_json:
        output_json_path = Path(output_json)
        output_json_path.parent.mkdir(parents=True, exist_ok=True)
        output_json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        output_md_path = Path(output_md)
        output_md_path.parent.mkdir(parents=True, exist_ok=True)
        output_md_path.write_text(render_action_sandbox_markdown(payload), encoding="utf-8")


def _evaluate_proposal(proposal: ProposedAction, risk_engine: RiskEngine) -> SandboxEvaluation:
    action = risk_engine.get_action(proposal.action_type)
    checks = {
        "allowlisted": action is not None and action.prohibited_reason is None,
        "blast_radius_bounded": proposal.blast_radius in _SAFE_BLAST_RADIUS,
        "reversible": proposal.reversible,
        "dry_run_capable": proposal.dry_run_capable,
        "credential_boundary_clear": not proposal.uses_credentials,
        "network_boundary_clear": not proposal.uses_network,
        "production_mutation_boundary_clear": not proposal.mutates_production and proposal.environment != "production-mutation",
        "shell_boundary_clear": not proposal.executes_shell,
    }
    blocked_reasons = _blocked_reasons(checks, dry_run_required=bool(action and not action.is_read_only))
    approval_reasons = _approval_reasons(proposal, action_requires_approval=bool(action and action.default_requires_approval))

    if blocked_reasons:
        decision = SandboxDecision.BLOCK
        requires_approval = False
    elif proposal.dry_run_only and proposal.approval_state in _NO_APPROVAL_STATES:
        decision = SandboxDecision.MOCK_ONLY
        requires_approval = True
    elif approval_reasons:
        decision = SandboxDecision.REQUIRE_APPROVAL
        requires_approval = True
    else:
        decision = SandboxDecision.ALLOW
        requires_approval = False

    return SandboxEvaluation(
        proposal_id=proposal.id,
        action_type=proposal.action_type,
        decision=decision,
        requires_approval=requires_approval,
        mock_only=True,
        checks=checks,
        blocked_reasons=tuple(blocked_reasons),
        approval_reasons=tuple(approval_reasons),
        notes=_notes(proposal, decision),
    )


def _blocked_reasons(checks: Mapping[str, bool], *, dry_run_required: bool) -> list[str]:
    reasons: list[str] = []
    if not checks["allowlisted"]:
        reasons.append("not_allowlisted")
    if not checks["blast_radius_bounded"]:
        reasons.append("unbounded_blast_radius")
    if not checks["reversible"]:
        reasons.append("not_reversible")
    if dry_run_required and not checks["dry_run_capable"]:
        reasons.append("dry_run_unavailable")
    if not checks["credential_boundary_clear"]:
        reasons.append("credential_boundary")
    if not checks["network_boundary_clear"]:
        reasons.append("network_boundary")
    if not checks["production_mutation_boundary_clear"]:
        reasons.append("production_mutation_boundary")
    if not checks["shell_boundary_clear"]:
        reasons.append("shell_execution_boundary")
    return reasons


def _approval_reasons(proposal: ProposedAction, *, action_requires_approval: bool) -> list[str]:
    if proposal.approval_state in _APPROVED_STATES:
        return []
    if proposal.dry_run_only and proposal.approval_state in _NO_APPROVAL_STATES:
        return ["dry_run_only_without_approval"]
    if action_requires_approval or proposal.approval_state in _PENDING_APPROVAL_STATES:
        return ["bounded_mutation_requires_human_approval"]
    return []


def _notes(proposal: ProposedAction, decision: SandboxDecision) -> tuple[str, ...]:
    base = ["local_mock_evaluation_only", "no_real_action_execution"]
    if decision == SandboxDecision.ALLOW:
        base.append("allowed_for_local_mock_read_only")
    if decision == SandboxDecision.MOCK_ONLY:
        base.append("dry_run_result_must_not_be_promoted_to_execution")
    if proposal.environment == "production":
        base.append("production_context_read_only_or_blocked")
    return tuple(base)


def _decision_count(decisions: Sequence[SandboxEvaluation], decision: SandboxDecision) -> int:
    return sum(1 for item in decisions if item.decision == decision)


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else ()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
