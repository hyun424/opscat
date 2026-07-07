"""P9 autonomy-readiness scoring for local/mock incident command."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

ReadinessRoute = Literal["local_mock_auto_allowed", "approval_required", "human_required", "blocked"]

_WEIGHTS: dict[str, int] = {
    "evidence_sufficiency": 16,
    "confidence": 14,
    "blast_radius": 16,
    "reversibility": 12,
    "simulation": 14,
    "policy": 14,
    "memory": 7,
    "verification_readiness": 7,
}
_HARD_BLAST = {"unknown", "prohibited", "global", "tenant"}
_HARD_POLICY = {"DENY", "ESCALATE"}
_BAD_MEMORY = {"failed", "stale", "poisoned", "rejected", "prior_failed_remediation"}
_BAD_VERIFICATION = {"failed", "false_recovery"}


@dataclass(frozen=True)
class ReadinessComponent:
    name: str
    weight: int
    factor: float
    points: int
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "weight": self.weight, "factor": self.factor, "points": self.points, "reason": self.reason}


@dataclass(frozen=True)
class AutonomyReadiness:
    score: int
    route: ReadinessRoute
    components: tuple[ReadinessComponent, ...]
    blockers: tuple[str, ...]
    required_human_answers: tuple[str, ...]
    hard_blocked: bool
    local_mock_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        components = [component.to_dict() for component in self.components]
        return {
            "score": self.score,
            "route": self.route,
            "components": components,
            "components_by_name": {component["name"]: component for component in components},
            "blockers": list(self.blockers),
            "required_human_answers": list(self.required_human_answers),
            "hard_blocked": self.hard_blocked,
            "local_mock_only": self.local_mock_only,
        }


def score_autonomy_readiness(inputs: Mapping[str, Any] | None = None) -> AutonomyReadiness:
    data = dict(inputs or {})
    evidence_count = _int(data.get("evidence_count"), 0)
    confidence = _float(data.get("confidence"), 0.0)
    blast = _norm(data.get("blast_radius_scope") or data.get("blast_radius") or "unknown")
    reversible = _bool(data.get("reversible", data.get("rollback_available", False)))
    simulation = _norm(data.get("simulation_status") or data.get("simulation") or "unknown")
    policy = str(data.get("policy_decision") or data.get("policy") or "not_recorded").upper()
    memory = _norm(data.get("memory_outcome") or data.get("memory_prior_outcome") or "none")
    verification = _norm(data.get("verification_status") or data.get("post_action_verification") or "pending")

    components = (
        _component("evidence_sufficiency", _evidence_factor(evidence_count), f"{evidence_count} local/mock evidence records"),
        _component("confidence", _confidence_factor(confidence, evidence_count), f"confidence={confidence:.2f}"),
        _component("blast_radius", _blast_factor(blast), f"blast radius={blast}"),
        _component("reversibility", 1.0 if reversible else 0.25, "rollback/reversal path recorded" if reversible else "rollback/reversal path missing"),
        _component("simulation", _simulation_factor(simulation), f"simulation={simulation}"),
        _component("policy", _policy_factor(policy), f"policy={policy}"),
        _component("memory", _memory_factor(memory), f"memory={memory}"),
        _component("verification_readiness", _verification_factor(verification), f"verification={verification}"),
    )
    raw_score = sum(component.points for component in components)
    blockers = _blockers(evidence_count, confidence, blast, reversible, simulation, policy, memory, verification)
    hard_blocked = blast in _HARD_BLAST or policy in _HARD_POLICY or memory == "poisoned" or verification in _BAD_VERIFICATION
    score = min(raw_score, 49) if hard_blocked else raw_score
    route = _route(score, blockers, hard_blocked, policy)
    questions = tuple(_questions(blockers, route))
    return AutonomyReadiness(score=score, route=route, components=components, blockers=tuple(blockers), required_human_answers=questions, hard_blocked=hard_blocked)


def _component(name: str, factor: float, reason: str) -> ReadinessComponent:
    weight = _WEIGHTS[name]
    bounded = max(0.0, min(1.0, round(factor, 3)))
    return ReadinessComponent(name=name, weight=weight, factor=bounded, points=round(weight * bounded), reason=reason)


def _blockers(evidence_count: int, confidence: float, blast: str, reversible: bool, simulation: str, policy: str, memory: str, verification: str) -> list[str]:
    blockers: list[str] = []
    if evidence_count < 2:
        blockers.append("insufficient_evidence")
    if confidence < 0.55:
        blockers.append("low_confidence")
    if blast in _HARD_BLAST:
        blockers.append(f"blast_radius_{blast}")
    if not reversible:
        blockers.append("missing_reversal_path")
    if simulation not in {"passed", "pass", "ok", "success"}:
        blockers.append(f"simulation_{simulation}")
    if policy in _HARD_POLICY or policy == "NOT_RECORDED":
        blockers.append(f"policy_{policy.lower()}")
    if memory in _BAD_MEMORY:
        blockers.append(f"memory_{memory}")
    if verification in _BAD_VERIFICATION:
        blockers.append(f"verification_{verification}")
    return sorted(set(blockers))


def _route(score: int, blockers: list[str], hard_blocked: bool, policy: str) -> ReadinessRoute:
    if hard_blocked:
        return "blocked"
    if blockers:
        return "human_required"
    if policy == "REQUIRE_APPROVAL" or score < 90:
        return "approval_required" if score >= 60 else "human_required"
    return "local_mock_auto_allowed"


def _questions(blockers: list[str], route: ReadinessRoute) -> list[str]:
    if route == "local_mock_auto_allowed":
        return []
    return [f"Resolve readiness blocker: {blocker}" for blocker in blockers] or ["Confirm operator context before local/mock action."]


def _evidence_factor(count: int) -> float:
    if count >= 4:
        return 1.0
    if count >= 2:
        return 0.7
    if count == 1:
        return 0.35
    return 0.0


def _confidence_factor(confidence: float, evidence_count: int) -> float:
    if confidence >= 0.85 and evidence_count >= 2:
        return 1.0
    if confidence >= 0.7:
        return 0.8
    if confidence >= 0.55:
        return 0.55
    return 0.2


def _blast_factor(value: str) -> float:
    if value in {"local", "service"}:
        return 1.0
    if value == "workspace":
        return 0.55
    return 0.0


def _simulation_factor(value: str) -> float:
    if value in {"passed", "pass", "ok", "success"}:
        return 1.0
    if value in {"pending", "approval_required"}:
        return 0.35
    return 0.0


def _policy_factor(value: str) -> float:
    if value == "ALLOW":
        return 1.0
    if value == "REQUIRE_APPROVAL":
        return 0.65
    return 0.0


def _memory_factor(value: str) -> float:
    if value in {"success", "safe", "known_safe_local_mock_runbook"}:
        return 1.0
    if value in {"none", "unknown", "not_recorded"}:
        return 0.65
    return 0.0


def _verification_factor(value: str) -> float:
    if value in {"passed", "pass", "recovered", "success"}:
        return 1.0
    if value in {"pending", "not_applicable", "none", "unknown"}:
        return 0.55
    return 0.0


def _norm(value: Any) -> str:
    if isinstance(value, Mapping):
        for key in ("scope", "level", "status", "outcome", "decision"):
            if key in value:
                return _norm(value[key])
    return str(value or "unknown").lower()


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool(value: Any) -> bool:
    return bool(value)
