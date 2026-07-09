"""P83 post-action outcome monitor.

Evaluates local/mock post-action evidence windows and decides whether an
incident action appears resolved, improving, unchanged, worsened, inconclusive,
or blocked by safety guardrails. This module never executes actions, contacts
external systems, reads credentials, runs shell commands, or mutates production.
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
    "post_action_monitoring_only": True,
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

_MIN_SUFFICIENT_EVIDENCE = 0.6
_STRONG_EVIDENCE = 0.8
_UNCHANGED_TOLERANCE = 0.05


class OutcomeDecision(StrEnum):
    RESOLVED = "resolved"
    IMPROVING_KEEP_WATCHING = "improving_keep_watching"
    UNCHANGED_INVESTIGATE = "unchanged_investigate"
    WORSENED_ROLLBACK_OR_ESCALATE = "worsened_rollback_or_escalate"
    INCONCLUSIVE_NEED_MORE_EVIDENCE = "inconclusive_need_more_evidence"
    BLOCKED_UNSAFE_TO_CONTINUE = "blocked_unsafe_to_continue"


@dataclass(frozen=True)
class SignalWindow:
    metrics: Mapping[str, float]
    logs: Mapping[str, float]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        return cls(
            metrics=_number_mapping(_mapping(data.get("metrics"))),
            logs=_number_mapping(_mapping(data.get("logs"))),
        )


@dataclass(frozen=True)
class RecoveryProof:
    metrics: Mapping[str, float]
    required_evidence: tuple[str, ...]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        return cls(
            metrics=_number_mapping(_mapping(data.get("metrics"))),
            required_evidence=tuple(str(item) for item in _sequence(data.get("required_evidence", ()))),
        )


@dataclass(frozen=True)
class OutcomeScenario:
    id: str
    incident_id: str
    action_draft_id: str
    action_type: str
    pre_action_signals: SignalWindow
    post_action_signals: SignalWindow
    expected_recovery_proof: RecoveryProof
    evidence_sufficiency: float
    rollback_pr_draft_status: str
    slack_ticket_draft_status: str
    elapsed_minutes: int
    window_minutes: int
    guardrails: Mapping[str, Any]
    evidence_references: tuple[str, ...]
    verification_checklist: tuple[str, ...]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        return cls(
            id=str(data.get("id", "scenario")),
            incident_id=str(data.get("incident_id", "incident")),
            action_draft_id=str(data.get("action_draft_id", "draft")),
            action_type=str(data.get("action_type", "unknown")),
            pre_action_signals=SignalWindow.from_dict(_mapping(data.get("pre_action_signals"))),
            post_action_signals=SignalWindow.from_dict(_mapping(data.get("post_action_signals"))),
            expected_recovery_proof=RecoveryProof.from_dict(_mapping(data.get("expected_recovery_proof"))),
            evidence_sufficiency=_float(data.get("evidence_sufficiency")),
            rollback_pr_draft_status=str(data.get("rollback_pr_draft_status", "missing")).lower(),
            slack_ticket_draft_status=str(data.get("slack_ticket_draft_status", "missing")).lower(),
            elapsed_minutes=int(_float(data.get("elapsed_minutes"))),
            window_minutes=max(1, int(_float(data.get("window_minutes")))),
            guardrails=_mapping(data.get("guardrails")),
            evidence_references=tuple(str(item) for item in _sequence(data.get("evidence_references", ()))),
            verification_checklist=tuple(str(item) for item in _sequence(data.get("verification_checklist", ()))),
        )


@dataclass(frozen=True)
class OutcomeEvaluation:
    scenario_id: str
    incident_id: str
    action_draft_id: str
    action_type: str
    decision: OutcomeDecision
    confidence: float
    evidence_references: tuple[str, ...]
    metric_deltas: Mapping[str, Mapping[str, Any]]
    log_deltas: Mapping[str, Mapping[str, Any]]
    missing_evidence: tuple[str, ...]
    next_recommended_step: str
    communication_draft_should_be_updated: bool
    rollback_draft_should_be_promoted_for_human_review: bool
    rollback_pr_draft_status: str
    slack_ticket_draft_status: str
    verification_checklist: tuple[str, ...]
    guardrails: Mapping[str, Any]
    audit_metadata: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "scenario_id": self.scenario_id,
            "incident_id": self.incident_id,
            "action_draft_id": self.action_draft_id,
            "action_type": self.action_type,
            "decision": self.decision.value,
            "confidence": self.confidence,
            "evidence_references": list(self.evidence_references),
            "metric_deltas": {key: dict(value) for key, value in self.metric_deltas.items()},
            "log_deltas": {key: dict(value) for key, value in self.log_deltas.items()},
            "missing_evidence": list(self.missing_evidence),
            "next_recommended_step": self.next_recommended_step,
            "communication_draft_should_be_updated": self.communication_draft_should_be_updated,
            "rollback_draft_should_be_promoted_for_human_review": self.rollback_draft_should_be_promoted_for_human_review,
            "rollback_pr_draft_status": self.rollback_pr_draft_status,
            "slack_ticket_draft_status": self.slack_ticket_draft_status,
            "verification_checklist": list(self.verification_checklist),
            "guardrails": dict(self.guardrails),
            "audit_metadata": dict(self.audit_metadata),
            "execution_plan": {
                "mode": "monitor_only",
                "action_execution_count": 0,
                "live_api_call_count": 0,
                "credential_read_count": 0,
                "network_call_count": 0,
                "production_mutation_count": 0,
                "shell_execution_count": 0,
                "rollback_execution_count": 0,
                "message_send_count": 0,
                "ticket_creation_count": 0,
            },
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


@dataclass(frozen=True)
class PostActionOutcomeReport:
    incident: Mapping[str, Any]
    scenarios: tuple[OutcomeScenario, ...]
    outcomes: tuple[OutcomeEvaluation, ...]

    @classmethod
    def from_scenarios(cls, incident: Mapping[str, Any], scenarios: Sequence[OutcomeScenario]) -> Self:
        outcomes = tuple(_evaluate_scenario(scenario) for scenario in scenarios)
        return cls(incident=incident, scenarios=tuple(scenarios), outcomes=outcomes)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "summary": {
                "incident_id": str(self.incident.get("id", "p83-incident")),
                "scenario_count": len(self.scenarios),
                "resolved_count": _decision_count(self.outcomes, OutcomeDecision.RESOLVED),
                "improving_keep_watching_count": _decision_count(self.outcomes, OutcomeDecision.IMPROVING_KEEP_WATCHING),
                "unchanged_investigate_count": _decision_count(self.outcomes, OutcomeDecision.UNCHANGED_INVESTIGATE),
                "worsened_rollback_or_escalate_count": _decision_count(self.outcomes, OutcomeDecision.WORSENED_ROLLBACK_OR_ESCALATE),
                "inconclusive_need_more_evidence_count": _decision_count(self.outcomes, OutcomeDecision.INCONCLUSIVE_NEED_MORE_EVIDENCE),
                "blocked_unsafe_to_continue_count": _decision_count(self.outcomes, OutcomeDecision.BLOCKED_UNSAFE_TO_CONTINUE),
                "communication_update_count": sum(1 for outcome in self.outcomes if outcome.communication_draft_should_be_updated),
                "rollback_human_review_promotion_count": sum(
                    1 for outcome in self.outcomes if outcome.rollback_draft_should_be_promoted_for_human_review
                ),
                "action_execution_count": 0,
                "live_api_call_count": 0,
                "credential_read_count": 0,
                "network_call_count": 0,
                "production_mutation_count": 0,
                "shell_execution_count": 0,
                "passed": _passed(self.outcomes, len(self.scenarios)),
            },
            "boundary": dict(_BOUNDARY),
            "incident": redact_value(dict(self.incident)),
            "outcomes": [outcome.to_dict() for outcome in self.outcomes],
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


def evaluate_post_action_outcome_fixture(path: str | Path) -> PostActionOutcomeReport:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    incident = _mapping(data.get("incident"))
    scenarios = tuple(OutcomeScenario.from_dict(item) for item in _sequence(data.get("scenarios", ())) if isinstance(item, Mapping))
    return PostActionOutcomeReport.from_scenarios(incident, scenarios)


def render_post_action_outcome_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    lines = [
        "# OpsCat Post-Action Outcome Monitor",
        "",
        "P83 judges local/mock post-action evidence windows without applying, rolling back, or escalating anything automatically.",
        "",
        "## Summary",
        "",
        f"- Incident: {summary.get('incident_id', 'unknown')}",
        f"- Scenarios: {summary.get('scenario_count', 0)}",
        f"- Resolved: {summary.get('resolved_count', 0)}",
        f"- Improving keep watching: {summary.get('improving_keep_watching_count', 0)}",
        f"- Unchanged investigate: {summary.get('unchanged_investigate_count', 0)}",
        f"- Worsened rollback or escalate: {summary.get('worsened_rollback_or_escalate_count', 0)}",
        f"- Inconclusive need more evidence: {summary.get('inconclusive_need_more_evidence_count', 0)}",
        f"- Blocked unsafe to continue: {summary.get('blocked_unsafe_to_continue_count', 0)}",
        f"- Communication updates: {summary.get('communication_update_count', 0)}",
        f"- Rollback human-review promotions: {summary.get('rollback_human_review_promotion_count', 0)}",
        f"- Passed: {summary.get('passed', False)}",
        "",
        "## Outcome decisions",
        "",
    ]
    for outcome in _sequence(payload.get("outcomes", ())):
        if isinstance(outcome, Mapping):
            evidence_ids = ", ".join(str(item) for item in _sequence(outcome.get("evidence_references", ()))) or "none"
            lines.extend(
                [
                    f"### {outcome.get('scenario_id', 'scenario')}",
                    "",
                    f"- Decision: {outcome.get('decision')}",
                    f"- Confidence: {outcome.get('confidence')}",
                    f"- Evidence: {evidence_ids}",
                    f"- Next step: {outcome.get('next_recommended_step')}",
                    f"- Update communication draft: {outcome.get('communication_draft_should_be_updated')}",
                    f"- Promote rollback draft for human review: {outcome.get('rollback_draft_should_be_promoted_for_human_review')}",
                    "",
                ]
            )
    lines.extend(
        [
            "## Zero-side-effect boundary",
            "",
            "- Local/mock monitoring and judgment only.",
            "- No live APIs, credentials, network calls, shell execution, production mutation, remediation execution, rollback execution, message sending, ticket creation, or action execution.",
            "- Rollback and communication outputs are recommendations for human review, not unattended production operation.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_post_action_outcome_outputs(
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
        output_md_path.write_text(render_post_action_outcome_markdown(payload), encoding="utf-8")


def _evaluate_scenario(scenario: OutcomeScenario) -> OutcomeEvaluation:
    metric_deltas = _deltas(scenario.pre_action_signals.metrics, scenario.post_action_signals.metrics)
    log_deltas = _deltas(scenario.pre_action_signals.logs, scenario.post_action_signals.logs)
    missing_evidence = _missing_evidence(scenario)
    improved_count = _direction_count(metric_deltas, "improved")
    worsened_count = _direction_count(metric_deltas, "worsened") + _direction_count(log_deltas, "worsened")
    recovered = _recovery_proof_satisfied(scenario, missing_evidence)

    if scenario.guardrails.get("unsafe_to_continue") is True:
        decision = OutcomeDecision.BLOCKED_UNSAFE_TO_CONTINUE
    elif scenario.evidence_sufficiency < _MIN_SUFFICIENT_EVIDENCE or missing_evidence:
        decision = OutcomeDecision.INCONCLUSIVE_NEED_MORE_EVIDENCE
    elif worsened_count > 0:
        decision = OutcomeDecision.WORSENED_ROLLBACK_OR_ESCALATE
    elif recovered and (scenario.rollback_pr_draft_status == "mock_applied" or scenario.elapsed_minutes >= scenario.window_minutes):
        decision = OutcomeDecision.RESOLVED
    elif improved_count > 0:
        decision = OutcomeDecision.IMPROVING_KEEP_WATCHING
    else:
        decision = OutcomeDecision.UNCHANGED_INVESTIGATE

    return OutcomeEvaluation(
        scenario_id=scenario.id,
        incident_id=scenario.incident_id,
        action_draft_id=scenario.action_draft_id,
        action_type=scenario.action_type,
        decision=decision,
        confidence=_confidence(scenario, decision, missing_evidence, improved_count, worsened_count, recovered),
        evidence_references=scenario.evidence_references,
        metric_deltas=metric_deltas,
        log_deltas=log_deltas,
        missing_evidence=missing_evidence,
        next_recommended_step=_next_step(decision),
        communication_draft_should_be_updated=_communication_update(decision),
        rollback_draft_should_be_promoted_for_human_review=_promote_rollback(decision, scenario),
        rollback_pr_draft_status=scenario.rollback_pr_draft_status,
        slack_ticket_draft_status=scenario.slack_ticket_draft_status,
        verification_checklist=_verification_checklist(scenario, decision),
        guardrails=scenario.guardrails,
        audit_metadata={
            "audit_id": f"p83:{scenario.id}",
            "local_mock_only": True,
            "monitor_only": True,
            "elapsed_minutes": scenario.elapsed_minutes,
            "window_minutes": scenario.window_minutes,
            "evidence_sufficiency": scenario.evidence_sufficiency,
            "unattended_production_operation_claimed": False,
        },
    )


def _deltas(pre: Mapping[str, float], post: Mapping[str, float]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for key in sorted(set(pre) | set(post)):
        before = pre.get(key)
        after = post.get(key)
        direction = "missing"
        delta = None
        percent_change = None
        if before is not None and after is not None:
            delta = after - before
            percent_change = 0.0 if before == 0 else delta / abs(before)
            if after < before * (1 - _UNCHANGED_TOLERANCE):
                direction = "improved"
            elif after > before * (1 + _UNCHANGED_TOLERANCE):
                direction = "worsened"
            else:
                direction = "unchanged"
        rows[key] = {
            "pre": before,
            "post": after,
            "delta": delta,
            "percent_change": percent_change,
            "direction": direction,
        }
    return rows


def _missing_evidence(scenario: OutcomeScenario) -> tuple[str, ...]:
    available = set(scenario.evidence_references)
    available.update(f"metric:{key}" for key in scenario.pre_action_signals.metrics)
    available.update(f"metric:{key}" for key in scenario.post_action_signals.metrics)
    available.update(f"log:{key}" for key in scenario.pre_action_signals.logs)
    available.update(f"log:{key}" for key in scenario.post_action_signals.logs)
    return tuple(item for item in scenario.expected_recovery_proof.required_evidence if item not in available)


def _recovery_proof_satisfied(scenario: OutcomeScenario, missing_evidence: Sequence[str]) -> bool:
    if missing_evidence or scenario.evidence_sufficiency < _STRONG_EVIDENCE:
        return False
    return all(scenario.post_action_signals.metrics.get(metric, float("inf")) <= target for metric, target in scenario.expected_recovery_proof.metrics.items())


def _confidence(
    scenario: OutcomeScenario,
    decision: OutcomeDecision,
    missing_evidence: Sequence[str],
    improved_count: int,
    worsened_count: int,
    recovered: bool,
) -> float:
    base = scenario.evidence_sufficiency
    if decision is OutcomeDecision.BLOCKED_UNSAFE_TO_CONTINUE:
        return round(max(base, 0.88), 2)
    if missing_evidence:
        return round(min(base, 0.55), 2)
    if recovered:
        return round(min(0.98, base + 0.04), 2)
    if worsened_count:
        return round(min(0.94, base + 0.03), 2)
    if improved_count:
        return round(min(0.9, base), 2)
    return round(min(0.82, base), 2)


def _next_step(decision: OutcomeDecision) -> str:
    if decision is OutcomeDecision.RESOLVED:
        return "mark resolved after human review confirms verification checklist satisfied"
    if decision is OutcomeDecision.IMPROVING_KEEP_WATCHING:
        return "continue monitoring through the remaining evidence window"
    if decision is OutcomeDecision.UNCHANGED_INVESTIGATE:
        return "investigate alternate causes and collect owner confirmation"
    if decision is OutcomeDecision.WORSENED_ROLLBACK_OR_ESCALATE:
        return "promote rollback draft for human review and escalate to incident commander"
    if decision is OutcomeDecision.INCONCLUSIVE_NEED_MORE_EVIDENCE:
        return "collect more evidence before changing incident status"
    return "stop automated follow-up and escalate unsafe boundary to a human owner"


def _communication_update(decision: OutcomeDecision) -> bool:
    return decision is not OutcomeDecision.INCONCLUSIVE_NEED_MORE_EVIDENCE


def _promote_rollback(decision: OutcomeDecision, scenario: OutcomeScenario) -> bool:
    if decision in {OutcomeDecision.WORSENED_ROLLBACK_OR_ESCALATE, OutcomeDecision.BLOCKED_UNSAFE_TO_CONTINUE}:
        return scenario.rollback_pr_draft_status in {"draft_ready", "mock_ready", "not_applicable"}
    return False


def _verification_checklist(scenario: OutcomeScenario, decision: OutcomeDecision) -> tuple[str, ...]:
    if scenario.verification_checklist:
        return scenario.verification_checklist
    if decision is OutcomeDecision.RESOLVED:
        return tuple(f"{metric} at or below target {target}" for metric, target in scenario.expected_recovery_proof.metrics.items())
    return ()


def _decision_count(outcomes: Sequence[OutcomeEvaluation], decision: OutcomeDecision) -> int:
    return sum(1 for outcome in outcomes if outcome.decision is decision)


def _direction_count(deltas: Mapping[str, Mapping[str, Any]], direction: str) -> int:
    return sum(1 for row in deltas.values() if row.get("direction") == direction)


def _passed(outcomes: Sequence[OutcomeEvaluation], scenario_count: int) -> bool:
    return (
        scenario_count >= 6
        and _decision_count(outcomes, OutcomeDecision.RESOLVED) >= 1
        and _decision_count(outcomes, OutcomeDecision.IMPROVING_KEEP_WATCHING) >= 1
        and _decision_count(outcomes, OutcomeDecision.UNCHANGED_INVESTIGATE) >= 1
        and _decision_count(outcomes, OutcomeDecision.WORSENED_ROLLBACK_OR_ESCALATE) >= 1
        and _decision_count(outcomes, OutcomeDecision.INCONCLUSIVE_NEED_MORE_EVIDENCE) >= 1
        and _decision_count(outcomes, OutcomeDecision.BLOCKED_UNSAFE_TO_CONTINUE) >= 1
    )


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, str) else ()


def _number_mapping(value: Mapping[str, Any]) -> dict[str, float]:
    return {str(key): _float(item) for key, item in value.items()}


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
    "OutcomeDecision",
    "PostActionOutcomeReport",
    "evaluate_post_action_outcome_fixture",
    "render_post_action_outcome_markdown",
    "write_post_action_outcome_outputs",
]
