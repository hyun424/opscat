"""Deterministic blast-radius classification for local/mock OpsCat actions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

from app.models.action import ActionMetadata, ActionRequest
from app.services.risk_engine import RiskEngine


class BlastRadiusLevel(StrEnum):
    LOCAL = "local"
    SERVICE = "service"
    WORKSPACE = "workspace"
    TENANT = "tenant"
    GLOBAL = "global"
    UNKNOWN = "unknown"
    PROHIBITED = "prohibited"


@dataclass(frozen=True)
class BlastRadiusResult:
    level: BlastRadiusLevel
    reason: str
    rollback_available: bool
    approval_required: bool
    touched_resources: tuple[str, ...]
    allowed: bool = True
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["level"] = self.level.value
        data["touched_resources"] = list(self.touched_resources)
        data["evidence"] = list(self.evidence)
        return data


class BlastRadiusService:
    def __init__(self, risk_engine: RiskEngine | None = None) -> None:
        self.risk_engine = risk_engine or RiskEngine()

    def evaluate(self, request: ActionRequest | str, payload: Mapping[str, Any] | None = None) -> BlastRadiusResult:
        if isinstance(request, str):
            request = ActionRequest(action_type=request, target=str((payload or {}).get("target", "unknown")), payload=payload or {})
        action = self.risk_engine.get_action(request.action_type)
        if action is None:
            return BlastRadiusResult(
                level=BlastRadiusLevel.UNKNOWN,
                reason=f"Unknown action {request.action_type!r} has unbounded blast radius.",
                rollback_available=False,
                approval_required=True,
                touched_resources=_resources(request),
                allowed=False,
                evidence=("unknown_action",),
            )
        level = _level_for(action, request)
        allowed = level not in {BlastRadiusLevel.UNKNOWN, BlastRadiusLevel.PROHIBITED}
        return BlastRadiusResult(
            level=level,
            reason=_reason(action, level),
            rollback_available=bool(action.reversible and level not in {BlastRadiusLevel.UNKNOWN, BlastRadiusLevel.PROHIBITED, BlastRadiusLevel.GLOBAL}),
            approval_required=bool(action.default_requires_approval or level in {BlastRadiusLevel.WORKSPACE, BlastRadiusLevel.TENANT, BlastRadiusLevel.GLOBAL, BlastRadiusLevel.UNKNOWN, BlastRadiusLevel.PROHIBITED}),
            touched_resources=_resources(request),
            allowed=allowed,
            evidence=(f"action_metadata:{action.name}", f"blast_radius:{action.blast_radius}"),
        )


def _level_for(action: ActionMetadata, request: ActionRequest) -> BlastRadiusLevel:
    if action.prohibited_reason:
        return BlastRadiusLevel.PROHIBITED
    raw = " ".join(
        str(value).lower().replace("non-production", "nonproduction")
        for value in (
            action.blast_radius,
            request.payload.get("blast_radius", "") if isinstance(request.payload, Mapping) else "",
            request.environment,
        )
    )
    if any(token in raw for token in ("prohibited", "unbounded", "shell", "database", "cloud", "secret")):
        return BlastRadiusLevel.PROHIBITED if action.prohibited_reason else BlastRadiusLevel.UNKNOWN
    if "global" in raw:
        return BlastRadiusLevel.GLOBAL
    if "tenant" in raw:
        return BlastRadiusLevel.TENANT
    if any(token in raw for token in ("workspace", "repository", "ticket", "pull request", "mock ticket")):
        return BlastRadiusLevel.WORKSPACE
    if any(token in raw for token in ("service", "worker", "single non-production worker")):
        return BlastRadiusLevel.SERVICE
    if any(token in raw for token in ("local", "incident", "timeline", "report", "none")) or action.is_read_only:
        return BlastRadiusLevel.LOCAL
    return BlastRadiusLevel.UNKNOWN


def _reason(action: ActionMetadata, level: BlastRadiusLevel) -> str:
    if action.prohibited_reason:
        return action.prohibited_reason
    return f"Action metadata blast radius {action.blast_radius!r} maps to {level.value} scope."


def _resources(request: ActionRequest) -> tuple[str, ...]:
    resources = [request.target]
    for key in ("service", "worker", "repository", "ticket", "incident_id"):
        value = request.payload.get(key) if isinstance(request.payload, Mapping) else None
        if value and str(value) not in resources:
            resources.append(str(value))
    return tuple(item for item in resources if item)
