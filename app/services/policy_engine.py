"""Policy evaluation for approval-gated OpsCat actions."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import time
from typing import Any

from app.models.action import ActionRequest, PolicyDecision, PolicyEvaluation, RiskLevel
from app.services.risk_engine import RiskEngine


@dataclass(frozen=True)
class NightAutopilotConfig:
    quiet_hours_start: time = time(22, 0)
    quiet_hours_end: time = time(7, 0)
    timezone: str = "UTC"
    max_automatic_risk: RiskLevel = RiskLevel.LOW
    max_attempts_per_incident: int = 1
    allowed_services: tuple[str, ...] = ("payment-api", "checkout-worker", "demo-service")
    allowed_environments: tuple[str, ...] = ("staging", "local", "test")
    allowed_actions: tuple[str, ...] = ("report.generate", "timeline.add_note")
    wake_up_conditions: tuple[str, ...] = (
        "critical severity",
        "production environment",
        "policy denied action",
        "verification failed",
    )


@dataclass(frozen=True)
class PolicyContext:
    capabilities: frozenset[str] = field(default_factory=frozenset)
    service: str = "demo-service"
    environment: str = "local"
    severity: str = "medium"
    night_autopilot: bool = False
    autopilot_attempts: int = 0
    autopilot: NightAutopilotConfig = field(default_factory=NightAutopilotConfig)
    approved: bool = False
    mode: str = "smart_approval"
    allowed_services: tuple[str, ...] | None = None
    allowed_environments: tuple[str, ...] | None = None
    max_automatic_risk: str | RiskLevel | None = None
    allowlisted_actions: tuple[str, ...] | None = None


class PolicyEngine:
    def __init__(self, risk_engine: RiskEngine | None = None) -> None:
        self.risk_engine = risk_engine or RiskEngine()

    def evaluate(
        self, request: ActionRequest | str, context: PolicyContext | None = None
    ) -> PolicyEvaluation:
        if isinstance(request, str):
            context = context or PolicyContext()
            request = ActionRequest(
                action_type=request,
                target=context.service,
                environment=context.environment,
                approved=context.approved,
            )
        context = context or PolicyContext(environment=request.environment)
        if context.mode == "night_autopilot":
            cfg = context.autopilot
            context = PolicyContext(
                capabilities=context.capabilities,
                service=context.service,
                environment=context.environment,
                severity=context.severity,
                night_autopilot=True,
                autopilot_attempts=context.autopilot_attempts,
                autopilot=NightAutopilotConfig(
                    quiet_hours_start=cfg.quiet_hours_start,
                    quiet_hours_end=cfg.quiet_hours_end,
                    timezone=cfg.timezone,
                    max_automatic_risk=RiskLevel(str(context.max_automatic_risk or cfg.max_automatic_risk)),
                    max_attempts_per_incident=cfg.max_attempts_per_incident,
                    allowed_services=context.allowed_services or cfg.allowed_services,
                    allowed_environments=context.allowed_environments or cfg.allowed_environments,
                    allowed_actions=context.allowlisted_actions or cfg.allowed_actions,
                    wake_up_conditions=cfg.wake_up_conditions,
                ),
                approved=context.approved,
                mode=context.mode,
            )
        action = self.risk_engine.get_action(request.action_type)
        if action is None:
            return PolicyEvaluation(
                decision=PolicyDecision.ESCALATE,
                risk_level=RiskLevel.HIGH,
                requires_approval=True,
                reason=f"Unknown action {request.action_type!r}; escalate for manual review.",
            )

        risk_level = self.risk_engine.classify(
            request.action_type,
            {**dict(request.payload), "environment": request.environment},
        )
        if risk_level == RiskLevel.PROHIBITED or action.prohibited_reason:
            return PolicyEvaluation(
                decision=PolicyDecision.DENY,
                risk_level=RiskLevel.PROHIBITED,
                requires_approval=False,
                reason=(
                    action.prohibited_reason
                    or "Production or prohibited mutation is denied by default policy."
                ),
                action=action,
                preconditions=action.required_preconditions,
                post_checks=action.post_checks,
            )

        if (
            action.allowed_environments
            and request.environment not in action.allowed_environments
            and not action.is_read_only
        ):
            return PolicyEvaluation(
                decision=PolicyDecision.DENY,
                risk_level=RiskLevel.PROHIBITED,
                requires_approval=False,
                reason=(
                    f"Action {request.action_type} is not allowed in "
                    f"environment {request.environment}."
                ),
                action=action,
                preconditions=action.required_preconditions,
                post_checks=action.post_checks,
            )

        effective_capabilities = context.capabilities or default_capabilities((
            "mock:tickets:write",
            "mock:pull_requests:write",
            "mock:workers:restart",
        ))
        missing = tuple(sorted(set(action.required_capabilities) - set(effective_capabilities)))
        if missing:
            return PolicyEvaluation(
                decision=PolicyDecision.ESCALATE,
                risk_level=risk_level,
                requires_approval=True,
                reason="Missing required capability grants.",
                action=action,
                missing_capabilities=missing,
                preconditions=action.required_preconditions,
                post_checks=action.post_checks,
            )

        if context.night_autopilot:
            autopilot_decision = self._evaluate_night_autopilot(request, context, risk_level)
            if autopilot_decision:
                return PolicyEvaluation(
                    decision=autopilot_decision,
                    risk_level=risk_level,
                    requires_approval=autopilot_decision != PolicyDecision.ALLOW,
                    reason="Night Autopilot policy applied.",
                    action=action,
                    preconditions=action.required_preconditions,
                    post_checks=action.post_checks,
                )

        if action.default_requires_approval or request.approved:
            if request.approved:
                return PolicyEvaluation(
                    decision=PolicyDecision.ALLOW,
                    risk_level=risk_level,
                    requires_approval=False,
                    reason="Human approval is present for approval-gated action.",
                    action=action,
                    preconditions=action.required_preconditions,
                    post_checks=action.post_checks,
                )
            return PolicyEvaluation(
                decision=PolicyDecision.REQUIRE_APPROVAL,
                risk_level=risk_level,
                requires_approval=True,
                reason="Default MVP policy requires approval for this write/mutation action.",
                action=action,
                preconditions=action.required_preconditions,
                post_checks=action.post_checks,
            )

        return PolicyEvaluation(
            decision=PolicyDecision.ALLOW,
            risk_level=risk_level,
            requires_approval=False,
            reason="Default MVP policy allows read-only, report, and timeline actions.",
            action=action,
            preconditions=action.required_preconditions,
            post_checks=action.post_checks,
        )

    def _evaluate_night_autopilot(
        self,
        request: ActionRequest,
        context: PolicyContext,
        risk_level: RiskLevel,
    ) -> PolicyDecision | None:
        cfg = context.autopilot
        if context.severity == "critical" or request.environment == "production":
            return PolicyDecision.ESCALATE
        if context.autopilot_attempts >= cfg.max_attempts_per_incident:
            return PolicyDecision.ESCALATE
        if (
            context.service not in cfg.allowed_services
            or request.environment not in cfg.allowed_environments
        ):
            return PolicyDecision.ESCALATE
        if request.action_type not in cfg.allowed_actions:
            return PolicyDecision.REQUIRE_APPROVAL
        if _risk_order(risk_level) > _risk_order(cfg.max_automatic_risk):
            return PolicyDecision.REQUIRE_APPROVAL
        return PolicyDecision.ALLOW


def _risk_order(risk: RiskLevel) -> int:
    return {
        RiskLevel.READ_ONLY: 0,
        RiskLevel.LOW: 1,
        RiskLevel.MEDIUM: 2,
        RiskLevel.HIGH: 3,
        RiskLevel.PROHIBITED: 4,
    }[risk]


def default_capabilities(extra: Iterable[str] = ()) -> frozenset[str]:
    return frozenset(
        {
            "mock:context:read",
            "mock:deploys:read",
            "mock:runbooks:read",
            "mock:incidents:read",
            "mock:verification:read",
            "timeline:write",
            "report:write",
            *extra,
        }
    )


DANGEROUS_ACTION_ALIASES = {
    "production_rollback": "production.rollback",
    "production_restart": "production.restart_service",
    "database_mutation": "database.mutate",
    "arbitrary_shell": "shell.execute",
    "cloud_delete": "cloud.delete_resource",
    "secret_access": "secret.read",
}


def evaluate_policy(action: Mapping[str, Any]) -> PolicyEvaluation:
    """Evaluate a dict-shaped action proposal before execution.

    This adapter keeps tests and API call sites fail-closed while the service
    layer still uses the typed ``PolicyEngine``/``PolicyContext`` contract.
    """

    payload = action.get("payload", {})
    if not isinstance(payload, Mapping):
        payload = {}
    raw_action_type = str(action.get("action_type", ""))
    action_type = DANGEROUS_ACTION_ALIASES.get(raw_action_type, raw_action_type)
    environment = str(action.get("environment", payload.get("environment", "staging")))
    service = str(action.get("service", payload.get("service", "payment-api")))
    request = ActionRequest(
        action_type=action_type,
        target=str(action.get("target", service)),
        environment=environment,
        payload=payload,
        approved=bool(action.get("approved", False)),
    )
    context = PolicyContext(
        capabilities=default_capabilities(
            (
                "mock:tickets:write",
                "mock:pull_requests:write",
                "mock:workers:restart",
            )
        ),
        service=service,
        environment=environment,
    )
    return PolicyEngine().evaluate(request, context)
