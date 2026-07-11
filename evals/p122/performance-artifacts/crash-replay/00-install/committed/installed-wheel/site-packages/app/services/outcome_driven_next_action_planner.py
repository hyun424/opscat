"""P84 outcome-driven next action planner.

Converts P83 post-action outcome decisions plus adjacent safety/evidence
signals into the next safest local/mock operator action. This module never
executes actions, contacts external systems, reads credentials, runs shell
commands, sends messages, creates tickets, or mutates production.
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
    "planning_only": True,
    "live_api_calls_enabled": False,
    "credential_access_enabled": False,
    "network_calls_enabled": False,
    "production_mutation_enabled": False,
    "remediation_execution_enabled": False,
    "shell_execution_enabled": False,
    "action_execution_enabled": False,
    "rollback_execution_enabled": False,
    "message_sending_enabled": False,
    "ticket_creation_enabled": False,
    "default_external_model_calls": False,
    "unattended_production_operation_claimed": False,
}

_ZERO_SIDE_EFFECT_COUNTERS: dict[str, int] = {
    "action_execution_count": 0,
    "live_api_call_count": 0,
    "credential_read_count": 0,
    "network_call_count": 0,
    "production_mutation_count": 0,
    "shell_execution_count": 0,
    "rollback_execution_count": 0,
    "message_send_count": 0,
    "ticket_creation_count": 0,
}

_P83_RESOLVED = "resolved"
_P83_IMPROVING = "improving_keep_watching"
_P83_UNCHANGED = "unchanged_investigate"
_P83_WORSENED = "worsened_rollback_or_escalate"
_P83_INCONCLUSIVE = "inconclusive_need_more_evidence"
_P83_BLOCKED = "blocked_unsafe_to_continue"


class NextActionDecision(StrEnum):
    STOP_RESOLVED = "stop_resolved"
    KEEP_WATCHING = "keep_watching"
    GATHER_MORE_EVIDENCE = "gather_more_evidence"
    ESCALATE_TO_HUMAN = "escalate_to_human"
    PREPARE_ROLLBACK_REVIEW = "prepare_rollback_review"
    UPDATE_COMMS_DRAFT = "update_comms_draft"
    BLOCK_UNSAFE_PATH = "block_unsafe_path"


@dataclass(frozen=True)
class NextActionScenario:
    id: str
    incident_id: str
    p83_outcome_decision: str
    p83_confidence: float
    p83_missing_evidence: tuple[str, ...]
    p83_communication_update_recommended: bool
    p83_rollback_review_recommended: bool
    p76_evidence_sufficiency: Mapping[str, Any]
    p80_approval_decision: Mapping[str, Any]
    p81_rollback_draft_state: Mapping[str, Any]
    p82_communication_draft_state: Mapping[str, Any]
    p77_recovery_proof: Mapping[str, Any]
    blast_radius: str
    reversible: bool
    elapsed_minutes: int
    window_minutes: int
    guardrails: Mapping[str, Any]
    evidence_references: tuple[str, ...]
    required_evidence: tuple[str, ...]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        return cls(
            id=str(data.get("id", "scenario")),
            incident_id=str(data.get("incident_id", "incident")),
            p83_outcome_decision=str(data.get("p83_outcome_decision", "")).lower(),
            p83_confidence=_float(data.get("p83_confidence")),
            p83_missing_evidence=tuple(str(item) for item in _sequence(data.get("p83_missing_evidence", ()))),
            p83_communication_update_recommended=bool(data.get("p83_communication_update_recommended", False)),
            p83_rollback_review_recommended=bool(data.get("p83_rollback_review_recommended", False)),
            p76_evidence_sufficiency=_mapping(data.get("p76_evidence_sufficiency")),
            p80_approval_decision=_mapping(data.get("p80_approval_decision")),
            p81_rollback_draft_state=_mapping(data.get("p81_rollback_draft_state")),
            p82_communication_draft_state=_mapping(data.get("p82_communication_draft_state")),
            p77_recovery_proof=_mapping(data.get("p77_recovery_proof")),
            blast_radius=str(data.get("blast_radius", "unknown")).lower(),
            reversible=bool(data.get("reversible", False)),
            elapsed_minutes=int(_float(data.get("elapsed_minutes"))),
            window_minutes=max(1, int(_float(data.get("window_minutes")))),
            guardrails=_mapping(data.get("guardrails")),
            evidence_references=tuple(str(item) for item in _sequence(data.get("evidence_references", ()))),
            required_evidence=tuple(str(item) for item in _sequence(data.get("required_evidence", ()))),
        )


@dataclass(frozen=True)
class NextActionPlan:
    scenario_id: str
    incident_id: str
    selected_next_action: NextActionDecision
    rationale: str
    required_evidence: tuple[str, ...]
    human_approval_required: bool
    communication_update_required: bool
    rollback_promotion_required: bool
    wait_recheck_window: Mapping[str, int]
    guardrails: Mapping[str, Any]
    audit_metadata: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "scenario_id": self.scenario_id,
            "incident_id": self.incident_id,
            "selected_next_action": self.selected_next_action.value,
            "rationale": self.rationale,
            "required_evidence": list(self.required_evidence),
            "human_approval_required": self.human_approval_required,
            "communication_update_required": self.communication_update_required,
            "rollback_promotion_required": self.rollback_promotion_required,
            "wait_recheck_window": dict(self.wait_recheck_window),
            "guardrails": dict(self.guardrails),
            "audit_metadata": dict(self.audit_metadata),
            "zero_side_effect_counters": dict(_ZERO_SIDE_EFFECT_COUNTERS),
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


@dataclass(frozen=True)
class OutcomeDrivenNextActionReport:
    incident: Mapping[str, Any]
    scenarios: tuple[NextActionScenario, ...]
    next_action_plans: tuple[NextActionPlan, ...]

    @classmethod
    def from_scenarios(cls, incident: Mapping[str, Any], scenarios: Sequence[NextActionScenario]) -> Self:
        plans = tuple(_plan_next_action(scenario) for scenario in scenarios)
        return cls(incident=incident, scenarios=tuple(scenarios), next_action_plans=plans)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "summary": {
                "incident_id": str(self.incident.get("id", "p84-incident")),
                "scenario_count": len(self.scenarios),
                "stop_resolved_count": _decision_count(self.next_action_plans, NextActionDecision.STOP_RESOLVED),
                "keep_watching_count": _decision_count(self.next_action_plans, NextActionDecision.KEEP_WATCHING),
                "gather_more_evidence_count": _decision_count(
                    self.next_action_plans, NextActionDecision.GATHER_MORE_EVIDENCE
                ),
                "escalate_to_human_count": _decision_count(self.next_action_plans, NextActionDecision.ESCALATE_TO_HUMAN),
                "prepare_rollback_review_count": _decision_count(
                    self.next_action_plans, NextActionDecision.PREPARE_ROLLBACK_REVIEW
                ),
                "update_comms_draft_count": _decision_count(
                    self.next_action_plans, NextActionDecision.UPDATE_COMMS_DRAFT
                ),
                "block_unsafe_path_count": _decision_count(self.next_action_plans, NextActionDecision.BLOCK_UNSAFE_PATH),
                "human_approval_required_count": sum(1 for plan in self.next_action_plans if plan.human_approval_required),
                "communication_update_required_count": sum(
                    1 for plan in self.next_action_plans if plan.communication_update_required
                ),
                "rollback_promotion_required_count": sum(
                    1 for plan in self.next_action_plans if plan.rollback_promotion_required
                ),
                **_ZERO_SIDE_EFFECT_COUNTERS,
                "passed": _passed(self.next_action_plans, len(self.scenarios)),
            },
            "boundary": dict(_BOUNDARY),
            "incident": redact_value(dict(self.incident)),
            "next_action_plans": [plan.to_dict() for plan in self.next_action_plans],
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


def evaluate_outcome_driven_next_action_fixture(path: str | Path) -> OutcomeDrivenNextActionReport:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    incident = _mapping(data.get("incident"))
    scenarios = tuple(
        NextActionScenario.from_dict(item) for item in _sequence(data.get("scenarios", ())) if isinstance(item, Mapping)
    )
    return OutcomeDrivenNextActionReport.from_scenarios(incident, scenarios)


def render_outcome_driven_next_action_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    lines = [
        "# OpsCat Outcome-Driven Next Action Planner",
        "",
        "P84 converts local/mock P83 post-action outcomes into the next safest planner decision without executing anything.",
        "",
        "## Summary",
        "",
        f"- Incident: {summary.get('incident_id', 'unknown')}",
        f"- Scenarios: {summary.get('scenario_count', 0)}",
        f"- Stop resolved: {summary.get('stop_resolved_count', 0)}",
        f"- Keep watching: {summary.get('keep_watching_count', 0)}",
        f"- Gather more evidence: {summary.get('gather_more_evidence_count', 0)}",
        f"- Escalate to human: {summary.get('escalate_to_human_count', 0)}",
        f"- Prepare rollback review: {summary.get('prepare_rollback_review_count', 0)}",
        f"- Update comms draft: {summary.get('update_comms_draft_count', 0)}",
        f"- Block unsafe path: {summary.get('block_unsafe_path_count', 0)}",
        f"- Human approval required: {summary.get('human_approval_required_count', 0)}",
        f"- Communication update required: {summary.get('communication_update_required_count', 0)}",
        f"- Rollback promotion required: {summary.get('rollback_promotion_required_count', 0)}",
        f"- Passed: {summary.get('passed', False)}",
        "",
        "## Next action plans",
        "",
    ]
    for plan in _sequence(payload.get("next_action_plans", ())):
        if isinstance(plan, Mapping):
            evidence = ", ".join(str(item) for item in _sequence(plan.get("required_evidence", ()))) or "none"
            window = _mapping(plan.get("wait_recheck_window"))
            lines.extend(
                [
                    f"### {plan.get('scenario_id', 'scenario')}",
                    "",
                    f"- Selected next action: {plan.get('selected_next_action')}",
                    f"- Rationale: {plan.get('rationale')}",
                    f"- Required evidence: {evidence}",
                    f"- Human approval required: {plan.get('human_approval_required')}",
                    f"- Communication update required: {plan.get('communication_update_required')}",
                    f"- Rollback promotion required: {plan.get('rollback_promotion_required')}",
                    f"- Wait minutes: {window.get('wait_minutes', 0)}",
                    "",
                ]
            )
    lines.extend(
        [
            "## Zero-side-effect boundary",
            "",
            "- Local/mock planning only.",
            "- No live APIs, credentials, network calls, shell execution, production mutation, remediation execution, rollback execution, message sending, ticket creation, or action execution.",
            "- Planner outputs are recommendations, drafts, or human-review gates; they are not unattended production operation.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_outcome_driven_next_action_outputs(
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
        output_md_path.write_text(render_outcome_driven_next_action_markdown(payload), encoding="utf-8")


def _plan_next_action(scenario: NextActionScenario) -> NextActionPlan:
    decision = _select_decision(scenario)
    return NextActionPlan(
        scenario_id=scenario.id,
        incident_id=scenario.incident_id,
        selected_next_action=decision,
        rationale=_rationale(scenario, decision),
        required_evidence=_required_evidence(scenario, decision),
        human_approval_required=_human_approval_required(scenario, decision),
        communication_update_required=_communication_update_required(scenario, decision),
        rollback_promotion_required=_rollback_promotion_required(scenario, decision),
        wait_recheck_window=_wait_window(scenario, decision),
        guardrails={
            **dict(scenario.guardrails),
            "local_mock_only": True,
            "no_action_execution": True,
            "blast_radius": scenario.blast_radius,
            "reversible": scenario.reversible,
        },
        audit_metadata={
            "audit_id": f"p84:{scenario.id}",
            "local_mock_only": True,
            "planner_only": True,
            "p83_outcome_decision": scenario.p83_outcome_decision,
            "p83_confidence": scenario.p83_confidence,
            "p76_decision": str(scenario.p76_evidence_sufficiency.get("decision", "")),
            "p80_decision": str(scenario.p80_approval_decision.get("decision", "")),
            "p81_status": str(scenario.p81_rollback_draft_state.get("status", "")),
            "p82_status": str(scenario.p82_communication_draft_state.get("status", "")),
            "p77_decision": str(scenario.p77_recovery_proof.get("decision", "")),
            "elapsed_minutes": scenario.elapsed_minutes,
            "window_minutes": scenario.window_minutes,
            "unattended_production_operation_claimed": False,
        },
    )


def _select_decision(scenario: NextActionScenario) -> NextActionDecision:
    if _unsafe_path(scenario):
        return NextActionDecision.BLOCK_UNSAFE_PATH
    if scenario.p83_outcome_decision == _P83_RESOLVED and _recovery_proven(scenario):
        if _communication_missing(scenario):
            return NextActionDecision.UPDATE_COMMS_DRAFT
        return NextActionDecision.STOP_RESOLVED
    if scenario.p83_outcome_decision == _P83_IMPROVING:
        return NextActionDecision.KEEP_WATCHING
    if scenario.p83_outcome_decision == _P83_WORSENED:
        if _rollback_ready_or_reversible(scenario):
            return NextActionDecision.PREPARE_ROLLBACK_REVIEW
        return NextActionDecision.ESCALATE_TO_HUMAN
    if scenario.p83_outcome_decision == _P83_UNCHANGED:
        if scenario.elapsed_minutes >= scenario.window_minutes and scenario.blast_radius in {"medium", "high", "broad"}:
            return NextActionDecision.GATHER_MORE_EVIDENCE
        return NextActionDecision.KEEP_WATCHING
    if scenario.p83_outcome_decision == _P83_INCONCLUSIVE:
        return NextActionDecision.GATHER_MORE_EVIDENCE
    return NextActionDecision.ESCALATE_TO_HUMAN


def _rationale(scenario: NextActionScenario, decision: NextActionDecision) -> str:
    if decision is NextActionDecision.STOP_RESOLVED:
        return "P83 resolved the incident, P77 recovery proof is proven, and the final report/update draft is ready."
    if decision is NextActionDecision.KEEP_WATCHING:
        remaining = max(0, scenario.window_minutes - scenario.elapsed_minutes)
        return f"P83 shows improvement; keep watching and recheck in {remaining} minutes before changing status."
    if decision is NextActionDecision.GATHER_MORE_EVIDENCE:
        suffix = " window exceeded; escalate for owner input." if scenario.elapsed_minutes >= scenario.window_minutes else " no action execution."
        return f"P83 does not prove recovery, so gather more evidence with{suffix}"
    if decision is NextActionDecision.PREPARE_ROLLBACK_REVIEW:
        return "P83 worsened after mitigation and a rollback draft/reversible path exists; prepare rollback draft for human review."
    if decision is NextActionDecision.UPDATE_COMMS_DRAFT:
        return "P83 is resolved but communication artifacts are missing or stale; update comms draft before stopping."
    if decision is NextActionDecision.BLOCK_UNSAFE_PATH:
        return "unsafe boundary detected; block unsafe path and escalate to a human without executing actions."
    return "Planner cannot choose a safe automated next step; escalate to a human owner."


def _required_evidence(scenario: NextActionScenario, decision: NextActionDecision) -> tuple[str, ...]:
    if scenario.required_evidence:
        return scenario.required_evidence
    evidence: list[str] = list(scenario.p83_missing_evidence)
    if decision is NextActionDecision.GATHER_MORE_EVIDENCE and "owner confirmation" not in evidence:
        evidence.append("owner confirmation")
    if decision is NextActionDecision.PREPARE_ROLLBACK_REVIEW:
        evidence.extend(["rollback draft human approval", "post-rollback verification checklist"])
    if decision is NextActionDecision.BLOCK_UNSAFE_PATH:
        evidence.append("human safety review")
    return tuple(dict.fromkeys(evidence))


def _human_approval_required(scenario: NextActionScenario, decision: NextActionDecision) -> bool:
    if decision in {
        NextActionDecision.ESCALATE_TO_HUMAN,
        NextActionDecision.PREPARE_ROLLBACK_REVIEW,
        NextActionDecision.BLOCK_UNSAFE_PATH,
    }:
        return True
    if decision is NextActionDecision.GATHER_MORE_EVIDENCE:
        return scenario.elapsed_minutes >= scenario.window_minutes or _approval_human_required(scenario)
    return False


def _communication_update_required(scenario: NextActionScenario, decision: NextActionDecision) -> bool:
    if decision in {
        NextActionDecision.STOP_RESOLVED,
        NextActionDecision.UPDATE_COMMS_DRAFT,
        NextActionDecision.PREPARE_ROLLBACK_REVIEW,
        NextActionDecision.BLOCK_UNSAFE_PATH,
    }:
        return True
    return decision is NextActionDecision.ESCALATE_TO_HUMAN and scenario.p83_communication_update_recommended


def _rollback_promotion_required(scenario: NextActionScenario, decision: NextActionDecision) -> bool:
    return decision is NextActionDecision.PREPARE_ROLLBACK_REVIEW and scenario.p83_rollback_review_recommended


def _wait_window(scenario: NextActionScenario, decision: NextActionDecision) -> dict[str, int]:
    if decision is NextActionDecision.KEEP_WATCHING:
        wait_minutes = max(1, scenario.window_minutes - scenario.elapsed_minutes)
    elif decision is NextActionDecision.GATHER_MORE_EVIDENCE and scenario.elapsed_minutes < scenario.window_minutes:
        wait_minutes = max(1, min(10, scenario.window_minutes - scenario.elapsed_minutes))
    else:
        wait_minutes = 0
    return {
        "wait_minutes": wait_minutes,
        "recheck_by_minute": scenario.elapsed_minutes + wait_minutes,
        "window_minutes": scenario.window_minutes,
    }


def _unsafe_path(scenario: NextActionScenario) -> bool:
    if scenario.p83_outcome_decision == _P83_BLOCKED:
        return True
    if scenario.guardrails.get("unsafe_to_continue") is True:
        return True
    return str(scenario.p80_approval_decision.get("decision", "")).lower() == "blocked"


def _recovery_proven(scenario: NextActionScenario) -> bool:
    return str(scenario.p77_recovery_proof.get("decision", "")).lower() in {"proven", "recovered", "passed"}


def _communication_missing(scenario: NextActionScenario) -> bool:
    return str(scenario.p82_communication_draft_state.get("status", "")).lower() in {"missing", "stale", "not_ready"}


def _rollback_ready_or_reversible(scenario: NextActionScenario) -> bool:
    status = str(scenario.p81_rollback_draft_state.get("status", "")).lower()
    return status in {"draft_ready", "mock_ready", "human_review_ready"} or scenario.reversible


def _approval_human_required(scenario: NextActionScenario) -> bool:
    return str(scenario.p80_approval_decision.get("decision", "")).lower() in {
        "human_required",
        "approval_required",
        "require_human",
    }


def _decision_count(plans: Sequence[NextActionPlan], decision: NextActionDecision) -> int:
    return sum(1 for plan in plans if plan.selected_next_action is decision)


def _passed(plans: Sequence[NextActionPlan], scenario_count: int) -> bool:
    return (
        scenario_count >= 6
        and _decision_count(plans, NextActionDecision.STOP_RESOLVED) >= 1
        and _decision_count(plans, NextActionDecision.KEEP_WATCHING) >= 1
        and _decision_count(plans, NextActionDecision.GATHER_MORE_EVIDENCE) >= 1
        and _decision_count(plans, NextActionDecision.PREPARE_ROLLBACK_REVIEW) >= 1
        and _decision_count(plans, NextActionDecision.BLOCK_UNSAFE_PATH) >= 1
    )


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, str) else ()


def _float(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


__all__ = [
    "NextActionDecision",
    "OutcomeDrivenNextActionReport",
    "evaluate_outcome_driven_next_action_fixture",
    "render_outcome_driven_next_action_markdown",
    "write_outcome_driven_next_action_outputs",
]
