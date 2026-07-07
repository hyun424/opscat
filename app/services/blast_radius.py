"""P7 deterministic blast-radius classification for local/mock actions."""

from __future__ import annotations

from dataclasses import dataclass

from app.models.action import ActionRequest, RiskLevel
from app.services.risk_engine import RiskEngine

BLAST_SCOPES = ("local", "service", "workspace", "tenant", "global", "unknown", "prohibited")


@dataclass(frozen=True)
class BlastRadiusEvaluation:
    action_type: str
    scope: str
    allowed: bool
    rollback_available: bool
    requires_human_approval: bool
    reasons: tuple[str, ...]
    touched_resources: tuple[str, ...] = ()


class BlastRadiusEngine:
    """Classify action impact without live provider access."""

    def __init__(self, risk_engine: RiskEngine | None = None) -> None:
        self.risk_engine = risk_engine or RiskEngine()

    def evaluate(self, request: ActionRequest) -> BlastRadiusEvaluation:
        action = self.risk_engine.get_action(request.action_type)
        target = request.target or request.payload.get("target") or request.action_type
        if action is None:
            return BlastRadiusEvaluation(
                action_type=request.action_type,
                scope="unknown",
                allowed=False,
                rollback_available=False,
                requires_human_approval=True,
                reasons=("Unknown action has unbounded blast radius.",),
                touched_resources=(str(target),),
            )
        if action.base_risk == RiskLevel.PROHIBITED or action.prohibited_reason:
            return BlastRadiusEvaluation(
                action_type=request.action_type,
                scope="prohibited",
                allowed=False,
                rollback_available=False,
                requires_human_approval=True,
                reasons=(action.prohibited_reason or "Prohibited action cannot be bounded.",),
                touched_resources=(str(target),),
            )
        scope = _normalize_scope(action.blast_radius)
        allowed = scope in {"local", "service"} and action.reversible
        reasons: list[str] = []
        if not allowed:
            reasons.append(f"Blast radius {scope!r} is not eligible for automatic execution.")
        if not action.reversible:
            reasons.append("Action is not reversible.")
        if not reasons:
            reasons.append("Blast radius is bounded and rollback is available.")
        return BlastRadiusEvaluation(
            action_type=request.action_type,
            scope=scope,
            allowed=allowed,
            rollback_available=action.reversible,
            requires_human_approval=not allowed or action.default_requires_approval,
            reasons=tuple(reasons),
            touched_resources=(str(target), action.blast_radius),
        )


def _normalize_scope(raw: str) -> str:
    text = raw.lower()
    if "prohibited" in text or "unbounded" in text or "production" in text:
        return "prohibited"
    if "tenant" in text:
        return "tenant"
    if "workspace" in text or "repository" in text:
        return "workspace"
    if "service" in text or "worker" in text or "ticket" in text:
        return "service"
    if "local" in text or "incident" in text or "none" in text:
        return "local"
    return "unknown"
