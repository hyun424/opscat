"""Deterministic P8 agent reliability score read model.

The score is explainable and local/mock only. It never authorizes an action;
callers must still honor policy, blast-radius, approval, and simulation gates.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.services.redaction import redact_value

_COMPONENT_WEIGHTS: dict[str, int] = {
    "replay_pass_rate": 15,
    "dangerous_action_block_rate": 15,
    "confidence_calibration": 15,
    "evidence_count": 12,
    "signal_clarity": 10,
    "blast_radius": 12,
    "simulation": 10,
    "memory_prior_outcome": 6,
    "post_action_verification": 5,
}
_HARD_BLOCK_SCOPES = {"unknown", "prohibited"}
_HARD_BLOCK_DECISIONS = {"DENY", "ESCALATE"}


@dataclass(frozen=True)
class ReliabilityComponent:
    name: str
    weight: int
    factor: float
    points: int
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "weight": self.weight,
            "factor": self.factor,
            "points": self.points,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class AgentReliabilityScore:
    inputs: dict[str, Any]
    score: int
    band: str
    components: tuple[ReliabilityComponent, ...]
    hard_policy_blocked: bool
    action_route: str
    human_on_exception_reason: str | None
    local_mock_only: bool = True

    @property
    def total_score(self) -> int:
        return self.score

    def to_dict(self) -> dict[str, Any]:
        components = [component.to_dict() for component in self.components]
        return {
            "score": self.score,
            "total_score": self.score,
            "band": self.band,
            "components": components,
            "components_by_name": {component["name"]: component for component in components},
            "hard_policy_blocked": self.hard_policy_blocked,
            "action_route": self.action_route,
            "human_on_exception_reason": self.human_on_exception_reason,
            "local_mock_only": self.local_mock_only,
            "inputs": redact_value(self.inputs),
        }


def score_agent_reliability(inputs: Mapping[str, Any] | None = None) -> AgentReliabilityScore:
    """Return a deterministic explainable score for pre-action reliability.

    Inputs are intentionally primitive so API, replay, dashboard, and war-room
    read models can reuse the scorer without introducing provider calls.
    """

    data = dict(inputs or {})
    confidence = _float(data.get("confidence"), default=0.0)
    evidence_count = max(0, _int(data.get("evidence_count"), default=0))
    conflicting = _bool(data.get("conflicting_signals"))
    ambiguous = _bool(data.get("known_ambiguity", data.get("ambiguous")))
    blast_radius_scope = _normalized(data.get("blast_radius_scope") or data.get("blast_radius") or "unknown")
    simulation_status = _normalized(data.get("simulation_status") or data.get("simulation") or "unknown")
    memory_prior_outcome = _normalized(data.get("memory_prior_outcome") or data.get("memory_outcome") or "none")
    post_check = _normalized(data.get("post_action_verification") or data.get("post_check") or "pending")
    policy_decision = str(data.get("policy_decision") or "not_recorded").upper()

    components = (
        _component("replay_pass_rate", _bounded(_float(data.get("replay_pass_rate"), default=1.0)), "local replay pass rate"),
        _component("dangerous_action_block_rate", _bounded(_float(data.get("dangerous_action_block_rate"), default=1.0)), "dangerous local/mock actions blocked"),
        _component("confidence_calibration", _confidence_factor(confidence, evidence_count, conflicting, ambiguous), _confidence_reason(confidence, evidence_count, conflicting, ambiguous)),
        _component("evidence_count", _evidence_factor(evidence_count), f"{evidence_count} supporting evidence records"),
        _component(
            "signal_clarity",
            0.0 if conflicting else (0.45 if ambiguous else 1.0),
            "conflicting or ambiguous signals" if conflicting or ambiguous else "signals are clear enough for policy gate",
        ),
        _component("blast_radius", _blast_radius_factor(blast_radius_scope), f"blast radius scope={blast_radius_scope}"),
        _component("simulation", _simulation_factor(simulation_status), f"simulation status={simulation_status}"),
        _component("memory_prior_outcome", _memory_factor(memory_prior_outcome), f"memory prior outcome={memory_prior_outcome}"),
        _component("post_action_verification", _post_check_factor(post_check), f"post-action verification={post_check}"),
    )
    raw_score = sum(component.points for component in components)
    hard_policy_blocked = blast_radius_scope in _HARD_BLOCK_SCOPES or policy_decision in _HARD_BLOCK_DECISIONS
    if hard_policy_blocked:
        score = min(raw_score, 49)
        band = "blocked"
        action_route = "blocked_by_policy"
        human_reason = f"Hard policy gate requires human review: blast radius {blast_radius_scope}, policy {policy_decision}."
    else:
        score = raw_score
        band = _band(score)
        if score >= 80:
            action_route = "eligible_for_action_gate"
            human_reason = None
        elif score >= 60:
            action_route = "approval_required"
            human_reason = "Reliability is moderate; keep human approval before action."
        else:
            action_route = "human_required"
            human_reason = "Low reliability score requires human-on-exception review before action."
    return AgentReliabilityScore(
        inputs=data,
        score=score,
        band=band,
        components=components,
        hard_policy_blocked=hard_policy_blocked,
        action_route=action_route,
        human_on_exception_reason=human_reason,
    )


def _component(name: str, factor: float, reason: str) -> ReliabilityComponent:
    weight = _COMPONENT_WEIGHTS[name]
    bounded_factor = _bounded(factor)
    return ReliabilityComponent(name=name, weight=weight, factor=bounded_factor, points=round(weight * bounded_factor), reason=reason)


def _confidence_factor(confidence: float, evidence_count: int, conflicting: bool, ambiguous: bool) -> float:
    if conflicting or ambiguous:
        return 0.25 if confidence >= 0.85 else 0.45
    if confidence >= 0.85 and evidence_count >= 2:
        return 1.0
    if confidence >= 0.70 and evidence_count >= 2:
        return 0.8
    if confidence >= 0.50:
        return 0.55
    return 0.25


def _confidence_reason(confidence: float, evidence_count: int, conflicting: bool, ambiguous: bool) -> str:
    if conflicting or ambiguous:
        return f"confidence={confidence:.2f} but conflicting_or_ambiguous=True"
    return f"confidence={confidence:.2f}, evidence_count={evidence_count}"


def _evidence_factor(evidence_count: int) -> float:
    if evidence_count >= 4:
        return 1.0
    if evidence_count >= 2:
        return 0.7
    if evidence_count == 1:
        return 0.3
    return 0.0


def _blast_radius_factor(scope: str) -> float:
    if scope in {"local", "service"}:
        return 1.0
    if scope == "workspace":
        return 0.65
    if scope in {"tenant", "global"}:
        return 0.25
    return 0.0


def _simulation_factor(status: str) -> float:
    if status in {"passed", "pass", "ok", "success"}:
        return 1.0
    if status in {"escalate", "approval_required", "pending"}:
        return 0.4
    if status in {"not_recorded", "unknown", "none"}:
        return 0.2
    return 0.0


def _memory_factor(outcome: str) -> float:
    if outcome in {"success", "known_safe_local_mock_runbook", "safe"}:
        return 1.0
    if outcome in {"none", "unknown", "not_recorded"}:
        return 0.65
    if outcome in {"stale", "poisoned", "failed", "prior_failed_remediation"}:
        return 0.0
    return 0.5


def _post_check_factor(status: str) -> float:
    if status in {"passed", "pass", "recovered", "success"}:
        return 1.0
    if status in {"pending", "not_applicable", "not_recorded", "none", "unknown"}:
        return 0.65
    return 0.0


def _band(score: int) -> str:
    if score >= 80:
        return "high"
    if score >= 60:
        return "medium"
    return "low"


def _bounded(value: float) -> float:
    return max(0.0, min(1.0, round(value, 3)))


def _normalized(value: Any) -> str:
    if isinstance(value, Mapping):
        for key in ("scope", "level", "status", "outcome", "decision"):
            if key in value:
                return _normalized(value[key])
    return str(value or "unknown").lower()


def _float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "y"}
    return bool(value)
