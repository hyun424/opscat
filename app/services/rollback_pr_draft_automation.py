"""P81 rollback PR draft automation.

Builds local/mock rollback PR draft artifacts from P80 approval decisions. This
module never creates branches, pushes commits, calls GitHub, executes shell
commands, reads credentials, or mutates production.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Self

from app.services.redaction import redact_value

_BOUNDARY: dict[str, bool] = {
    "local_mock_only": True,
    "draft_only": True,
    "github_api_calls_enabled": False,
    "credential_access_enabled": False,
    "network_calls_enabled": False,
    "production_mutation_enabled": False,
    "remediation_execution_enabled": False,
    "shell_execution_enabled": False,
    "action_execution_enabled": False,
    "git_branch_creation_enabled": False,
    "git_push_enabled": False,
    "default_external_model_calls": False,
    "unattended_production_operation_claimed": False,
}

_BLOCKED_CLASSES = {"credential", "auth", "secret", "identity", "shell"}
_HUMAN_REVIEW_CLASSES = {"schema", "migration", "data"}


class RollbackDraftDecision(StrEnum):
    DRAFT_READY = "draft_ready"
    HUMAN_REVIEW_REQUIRED = "human_review_required"
    BLOCKED = "blocked"
    REJECTED = "rejected"


@dataclass(frozen=True)
class RollbackDraftScenario:
    id: str
    title: str
    rollback_type: str
    action_class: str
    service: str
    p80_decision: str
    p80_max_allowed_execution_mode: str
    evidence_sufficiency: float
    recovery_proof_strength: float
    blast_radius: str
    reversible: bool
    explicit_external_execution_configured: bool
    evidence_references: tuple[str, ...]
    proposed_file_changes: tuple[Mapping[str, str], ...]
    command_plan: tuple[str, ...]
    verification_checklist: tuple[str, ...]
    rollback_abort_plan: tuple[str, ...]
    approval_type: str
    risk: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        return cls(
            id=str(data.get("id", "scenario")),
            title=str(data.get("title", "Draft rollback PR")),
            rollback_type=str(data.get("rollback_type", "unknown")).lower(),
            action_class=str(data.get("action_class", "unknown")).lower(),
            service=str(data.get("service", "unknown")),
            p80_decision=str(data.get("p80_decision", "require_human")).lower(),
            p80_max_allowed_execution_mode=str(data.get("p80_max_allowed_execution_mode", "dry_run_only")).lower(),
            evidence_sufficiency=_float(data.get("evidence_sufficiency")),
            recovery_proof_strength=_float(data.get("recovery_proof_strength")),
            blast_radius=str(data.get("blast_radius", "unknown")).lower(),
            reversible=data.get("reversible") is True,
            explicit_external_execution_configured=data.get("explicit_external_execution_configured") is True,
            evidence_references=tuple(str(item) for item in _sequence(data.get("evidence_references", ()))),
            proposed_file_changes=tuple(_string_mapping(item) for item in _sequence(data.get("proposed_file_changes", ()))),
            command_plan=tuple(str(item) for item in _sequence(data.get("command_plan", ()))),
            verification_checklist=tuple(str(item) for item in _sequence(data.get("verification_checklist", ()))),
            rollback_abort_plan=tuple(str(item) for item in _sequence(data.get("rollback_abort_plan", ()))),
            approval_type=str(data.get("approval_type", "incident_commander_review")),
            risk=str(data.get("risk", "Human review required before any rollback PR can be opened.")),
        )


@dataclass(frozen=True)
class RollbackDraftArtifact:
    scenario_id: str
    title: str
    summary: str
    decision: RollbackDraftDecision
    reasons: tuple[str, ...]
    guardrails: tuple[str, ...]
    proposed_file_changes: tuple[Mapping[str, str], ...]
    command_plan: tuple[str, ...]
    risk: str
    evidence_references: tuple[str, ...]
    required_human_approval: Mapping[str, Any]
    verification_checklist: tuple[str, ...]
    rollback_abort_plan: tuple[str, ...]
    approval_source: Mapping[str, Any]
    audit_metadata: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "scenario_id": self.scenario_id,
            "title": self.title,
            "summary": self.summary,
            "decision": self.decision.value,
            "reasons": list(self.reasons),
            "guardrails": list(self.guardrails),
            "draft_only": True,
            "human_approval_required": True,
            "proposed_file_changes": [dict(item) for item in self.proposed_file_changes],
            "command_plan": list(self.command_plan),
            "risk": self.risk,
            "evidence_references": list(self.evidence_references),
            "required_human_approval": dict(self.required_human_approval),
            "verification_checklist": list(self.verification_checklist),
            "rollback_abort_plan": list(self.rollback_abort_plan),
            "approval_source": dict(self.approval_source),
            "audit_metadata": dict(self.audit_metadata),
            "execution_plan": {
                "mode": "draft_only",
                "execution_count": 0,
                "shell_execution_count": 0,
                "github_api_call_count": 0,
                "branch_creation_count": 0,
                "git_push_count": 0,
            },
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


@dataclass(frozen=True)
class RollbackPrDraftReport:
    incident: Mapping[str, Any]
    scenarios: tuple[RollbackDraftScenario, ...]
    drafts: tuple[RollbackDraftArtifact, ...]

    @classmethod
    def from_scenarios(cls, incident: Mapping[str, Any], scenarios: Sequence[RollbackDraftScenario]) -> Self:
        drafts = tuple(_build_draft(scenario) for scenario in scenarios)
        return cls(incident=incident, scenarios=tuple(scenarios), drafts=drafts)

    def to_dict(self) -> dict[str, Any]:
        draft_ready_count = _decision_count(self.drafts, RollbackDraftDecision.DRAFT_READY)
        human_review_required_count = _decision_count(self.drafts, RollbackDraftDecision.HUMAN_REVIEW_REQUIRED)
        blocked_count = _decision_count(self.drafts, RollbackDraftDecision.BLOCKED)
        rejected_count = _decision_count(self.drafts, RollbackDraftDecision.REJECTED)
        payload = {
            "summary": {
                "incident_id": str(self.incident.get("id", "p81-incident")),
                "scenario_count": len(self.scenarios),
                "draft_ready_count": draft_ready_count,
                "human_review_required_count": human_review_required_count,
                "blocked_count": blocked_count,
                "rejected_count": rejected_count,
                "required_human_approval_count": len(self.drafts),
                "action_execution_count": 0,
                "live_api_call_count": 0,
                "credential_read_count": 0,
                "network_call_count": 0,
                "production_mutation_count": 0,
                "shell_execution_count": 0,
                "branch_creation_count": 0,
                "git_push_count": 0,
                "passed": len(self.scenarios) >= 5
                and draft_ready_count >= 2
                and human_review_required_count >= 1
                and blocked_count >= 1
                and rejected_count >= 1,
            },
            "boundary": dict(_BOUNDARY),
            "incident": redact_value(dict(self.incident)),
            "drafts": [draft.to_dict() for draft in self.drafts],
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


def evaluate_rollback_pr_draft_fixture(path: str | Path) -> RollbackPrDraftReport:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    incident = _mapping(data.get("incident"))
    scenarios = tuple(
        RollbackDraftScenario.from_dict(item) for item in _sequence(data.get("scenarios", ())) if isinstance(item, Mapping)
    )
    return RollbackPrDraftReport.from_scenarios(incident, scenarios)


def render_rollback_pr_draft_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    lines = [
        "# OpsCat Rollback PR Draft Automation",
        "",
        "P81 prepares rollback PR draft artifacts from local/mock P80 approval decisions only.",
        "",
        "## Summary",
        "",
        f"- Incident: {summary.get('incident_id', 'unknown')}",
        f"- Scenarios: {summary.get('scenario_count', 0)}",
        f"- Draft ready: {summary.get('draft_ready_count', 0)}",
        f"- Human review required: {summary.get('human_review_required_count', 0)}",
        f"- Blocked: {summary.get('blocked_count', 0)}",
        f"- Rejected: {summary.get('rejected_count', 0)}",
        f"- Required human approvals: {summary.get('required_human_approval_count', 0)}",
        f"- Passed: {summary.get('passed', False)}",
        "",
        "## Draft artifacts",
        "",
    ]
    for draft in _sequence(payload.get("drafts", ())):
        if isinstance(draft, Mapping):
            reasons = ", ".join(str(item) for item in _sequence(draft.get("reasons", ()))) or "none"
            approval = _mapping(draft.get("required_human_approval"))
            lines.extend(
                [
                    f"### {draft.get('title', 'Rollback draft')}",
                    "",
                    f"- Scenario: `{draft.get('scenario_id')}`",
                    f"- Decision: {draft.get('decision')}",
                    f"- Approval: {approval.get('approval_type', 'human_review')}",
                    f"- Reasons: {reasons}",
                    f"- Risk: {draft.get('risk', 'human review required')}",
                    "",
                ]
            )
    lines.extend(
        [
            "## Zero-execution boundary",
            "",
            "- Draft artifact generation only.",
            "- No live GitHub API calls, credentials, network calls, branch creation, git push, production mutation, shell execution, or rollback command execution.",
            "- P80 auto-approval is downgraded to draft-only unless an external execution system is explicitly configured; normal verification keeps it disabled.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_rollback_pr_draft_outputs(
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
        output_md_path.write_text(render_rollback_pr_draft_markdown(payload), encoding="utf-8")


def _build_draft(scenario: RollbackDraftScenario) -> RollbackDraftArtifact:
    decision = _decision(scenario)
    reasons = _reasons(scenario, decision)
    proposed_file_changes = scenario.proposed_file_changes if decision in {RollbackDraftDecision.DRAFT_READY, RollbackDraftDecision.HUMAN_REVIEW_REQUIRED} else ()
    command_plan = scenario.command_plan if decision in {RollbackDraftDecision.DRAFT_READY, RollbackDraftDecision.HUMAN_REVIEW_REQUIRED} else ()
    verification = scenario.verification_checklist or ("human reviewer verifies local/mock evidence bundle",)
    abort_plan = scenario.rollback_abort_plan or ("abort draft and collect missing evidence",)
    if decision == RollbackDraftDecision.REJECTED:
        abort_plan = tuple(dict.fromkeys((*abort_plan, "collect deploy diff, recovery proof, and blast radius evidence")))
    evidence_references = scenario.evidence_references or ("missing:evidence_references",)
    return RollbackDraftArtifact(
        scenario_id=scenario.id,
        title=scenario.title,
        summary=_summary(scenario, decision),
        decision=decision,
        reasons=tuple(dict.fromkeys(reasons)),
        guardrails=_guardrails(decision),
        proposed_file_changes=proposed_file_changes,
        command_plan=command_plan,
        risk=scenario.risk,
        evidence_references=evidence_references,
        required_human_approval={
            "approval_type": scenario.approval_type,
            "required": True,
            "reason": "P81 emits draft artifacts only; humans must approve before any external PR or rollback work.",
        },
        verification_checklist=verification,
        rollback_abort_plan=abort_plan,
        approval_source={
            "source": "p80_approval_automation_policy_lab",
            "p80_decision": scenario.p80_decision,
            "p80_max_allowed_execution_mode": scenario.p80_max_allowed_execution_mode,
            "p81_external_execution_configured": scenario.explicit_external_execution_configured,
        },
        audit_metadata={
            "audit_id": f"p81:{scenario.id}",
            "scenario_id": scenario.id,
            "service": scenario.service,
            "local_mock_only": True,
            "draft_only": True,
        },
    )


def _decision(scenario: RollbackDraftScenario) -> RollbackDraftDecision:
    if scenario.p80_decision == "block" or scenario.action_class in _BLOCKED_CLASSES:
        return RollbackDraftDecision.BLOCKED
    if scenario.evidence_sufficiency < 0.8 or scenario.recovery_proof_strength < 0.75 or not scenario.evidence_references:
        return RollbackDraftDecision.REJECTED
    if scenario.p80_decision == "require_human" or scenario.action_class in _HUMAN_REVIEW_CLASSES:
        return RollbackDraftDecision.HUMAN_REVIEW_REQUIRED
    return RollbackDraftDecision.DRAFT_READY


def _reasons(scenario: RollbackDraftScenario, decision: RollbackDraftDecision) -> list[str]:
    reasons = ["p81_draft_only_no_execution"]
    if scenario.p80_decision == "auto_approve":
        reasons.append("p80_auto_approve_downgraded_to_draft_only")
    if scenario.p80_decision == "mock_only":
        reasons.append("p80_mock_only_requires_draft_boundary")
    if scenario.p80_decision == "require_human":
        reasons.append("p80_requires_human_review")
    if scenario.p80_decision == "block":
        reasons.append("p80_blocks_external_action")
    if scenario.action_class in _BLOCKED_CLASSES:
        reasons.append("credential_or_auth_rollback_blocked")
    if scenario.action_class in _HUMAN_REVIEW_CLASSES:
        reasons.append("schema_or_migration_requires_human_review")
    if scenario.evidence_sufficiency < 0.8 or scenario.recovery_proof_strength < 0.75 or not scenario.evidence_references:
        reasons.append("insufficient_evidence_for_safe_draft")
    if decision == RollbackDraftDecision.DRAFT_READY:
        reasons.append("draft_artifact_ready_for_human_review")
    return reasons


def _guardrails(decision: RollbackDraftDecision) -> tuple[str, ...]:
    base = (
        "p81_draft_only_no_external_execution_configured",
        "no_live_github_api_calls",
        "no_git_branch_creation_or_push",
        "no_shell_or_rollback_command_execution",
        "human_approval_required_before_external_pr",
    )
    if decision == RollbackDraftDecision.BLOCKED:
        return (*base, "blocked_items_cannot_be_promoted_to_pr")
    if decision == RollbackDraftDecision.REJECTED:
        return (*base, "rejected_drafts_require_more_evidence")
    return base


def _summary(scenario: RollbackDraftScenario, decision: RollbackDraftDecision) -> str:
    if decision == RollbackDraftDecision.BLOCKED:
        return f"Do not prepare an external rollback PR for {scenario.service}; sensitive rollback class is blocked."
    if decision == RollbackDraftDecision.REJECTED:
        return f"Reject rollback PR draft for {scenario.service} until evidence and recovery proof are sufficient."
    return f"Prepare a human-reviewed rollback PR draft for {scenario.service}; no external PR, branch, push, or command execution is performed."


def _decision_count(drafts: Sequence[RollbackDraftArtifact], decision: RollbackDraftDecision) -> int:
    return sum(1 for item in drafts if item.decision == decision)


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else ()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _string_mapping(value: Any) -> Mapping[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): str(item) for key, item in value.items()}


def _float(value: Any) -> float:
    if isinstance(value, int | float):
        return float(value)
    return 0.0
