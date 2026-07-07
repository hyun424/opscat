"""P7 blast-radius classification for local/mock actions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.services.risk_engine import RiskEngine


class BlastRadiusScope(StrEnum):
    LOCAL = "local"
    SERVICE = "service"
    WORKSPACE = "workspace"
    TENANT = "tenant"
    GLOBAL = "global"
    UNKNOWN = "unknown"
    PROHIBITED = "prohibited"


@dataclass(frozen=True)
class BlastRadiusAssessment:
    scope: BlastRadiusScope
    rollback_available: bool
    approval_required: bool
    allowed_for_auto: bool
    touched_resources: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "scope": self.scope.value,
            "rollback_available": self.rollback_available,
            "approval_required": self.approval_required,
            "allowed_for_auto": self.allowed_for_auto,
            "touched_resources": list(self.touched_resources),
            "reason": self.reason,
        }


class BlastRadiusService:
    """Classify action impact before execution.

    This service is deterministic and local-only. Unknown, production, shell,
    database, cloud, and secret actions fail closed.
    """

    def __init__(self, risk_engine: RiskEngine | None = None) -> None:
        self.risk_engine = risk_engine or RiskEngine()

    def classify(self, action: Mapping[str, Any]) -> BlastRadiusAssessment:
        action_type = str(action.get("action_type", ""))
        payload = action.get("payload", {})
        if not isinstance(payload, Mapping):
            payload = {}
        environment = str(action.get("environment", payload.get("environment", "local")))
        target = str(action.get("target", payload.get("service", "unknown")))
        metadata = self.risk_engine.get_action(action_type)
        lowered = f"{action_type} {target} {payload}".lower()
        if metadata is None:
            return BlastRadiusAssessment(
                scope=BlastRadiusScope.UNKNOWN,
                rollback_available=False,
                approval_required=True,
                allowed_for_auto=False,
                touched_resources=(target,),
                reason="Unknown action metadata; fail closed.",
            )
        if metadata.prohibited_reason or any(term in lowered for term in ("shell", "kubectl", "delete", "database", "secret", "cloud")):
            return BlastRadiusAssessment(
                scope=BlastRadiusScope.PROHIBITED,
                rollback_available=False,
                approval_required=True,
                allowed_for_auto=False,
                touched_resources=(target,),
                reason=metadata.prohibited_reason or "Unbounded/destructive action is prohibited.",
            )
        if environment == "production" and not metadata.is_read_only:
            return BlastRadiusAssessment(
                scope=BlastRadiusScope.GLOBAL,
                rollback_available=False,
                approval_required=True,
                allowed_for_auto=False,
                touched_resources=(target, environment),
                reason="Production mutation is outside the local/mock P7 boundary.",
            )
        scope = _scope_from_metadata(metadata.blast_radius)
        rollback = metadata.reversible and scope in {BlastRadiusScope.LOCAL, BlastRadiusScope.SERVICE, BlastRadiusScope.WORKSPACE}
        approval = metadata.default_requires_approval or scope not in {BlastRadiusScope.LOCAL, BlastRadiusScope.SERVICE}
        return BlastRadiusAssessment(
            scope=scope,
            rollback_available=rollback,
            approval_required=approval,
            allowed_for_auto=rollback and scope in {BlastRadiusScope.LOCAL, BlastRadiusScope.SERVICE} and not approval,
            touched_resources=_touched_resources(action_type, target, environment),
            reason=f"Action is bounded to {scope.value} within local/mock registry.",
        )


def _normalize_scope(raw: str) -> str:
    text = raw.lower()
    if "worker" in text:
        return "service"
    if "prohibited" in text or "unbounded" in text:
        return "prohibited"
    if "tenant" in text:
        return "tenant"
    if "workspace" in text or "repository" in text:
        return "workspace"
    if "service" in text or "ticket" in text:
        return "service"
    if "local" in text or "incident" in text or "none" in text:
        return "local"
    return "unknown"
