"""P7 blast-radius classification for deterministic local/mock actions."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from app.models.action import ActionRequest, RiskLevel
from app.services.risk_engine import RiskEngine


@dataclass(frozen=True)
class BlastRadiusResult:
    scope: str
    reversible: bool
    rollback_available: bool
    approval_required: bool
    blocked: bool
    reasons: list[str]
    evidence: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class BlastRadiusEngine:
    def __init__(self, risk_engine: RiskEngine | None = None) -> None:
        self.risk_engine = risk_engine or RiskEngine()

    def classify(self, request: ActionRequest) -> BlastRadiusResult:
        action = self.risk_engine.get_action(request.action_type)
        if action is None:
            return BlastRadiusResult("unknown", False, False, True, True, ["unknown action has unbounded blast radius"], {"action_type": request.action_type})
        if action.base_risk == RiskLevel.PROHIBITED or action.prohibited_reason:
            return BlastRadiusResult("prohibited", False, False, True, True, [action.prohibited_reason or "prohibited action"], {"action_type": request.action_type, "environment": request.environment})
        scope = _normalize_scope(action.blast_radius, request.environment)
        reasons = [f"registry blast_radius={action.blast_radius}", f"scope={scope}"]
        blocked = scope in {"unknown", "global", "tenant"} and not action.is_read_only
        if blocked:
            reasons.append("unbounded or broad mutation scope is blocked")
        return BlastRadiusResult(
            scope=scope,
            reversible=action.reversible,
            rollback_available=action.reversible or action.is_read_only,
            approval_required=action.default_requires_approval or scope in {"workspace", "tenant", "global", "unknown"},
            blocked=blocked,
            reasons=reasons,
            evidence={"action_type": request.action_type, "target": request.target, "environment": request.environment, "read_only": action.is_read_only},
        )


def _normalize_scope(raw: str, environment: str) -> str:
    text = raw.lower()
    if "unbounded" in text or "unknown" in text:
        return "unknown"
    if "production" in text and environment == "production":
        return "global"
    if text in {"none", "read-only", "read_only"}:
        return "local"
    if "single" in text or "worker" in text or "service" in text:
        return "service"
    if "ticket" in text or "incident" in text or "repository" in text:
        return "workspace"
    if "tenant" in text:
        return "tenant"
    if "global" in text:
        return "global"
    return "unknown"
