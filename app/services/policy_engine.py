from dataclasses import dataclass

from app.services.risk_engine import get_action_definition, risk_at_most


@dataclass(frozen=True)
class PolicyResult:
    decision: str
    requires_approval: bool
    risk_level: str
    reasons: list[str]


@dataclass(frozen=True)
class PolicyContext:
    mode: str = "smart_approval"
    environment: str = "staging"
    service: str = "payment-api"
    approved: bool = False
    allowed_services: tuple[str, ...] = ("payment-api", "worker")
    allowed_environments: tuple[str, ...] = ("dev", "staging")
    max_automatic_risk: str = "low"
    allowlisted_actions: tuple[str, ...] = ("mock.create_incident_ticket", "mock.execute_restart_worker")


class PolicyEngine:
    def evaluate(self, action_type: str, context: PolicyContext) -> PolicyResult:
        definition = get_action_definition(action_type)
        reasons: list[str] = [f"base_risk={definition.base_risk}"]

        if definition.base_risk == "prohibited" or action_type.startswith("prohibited."):
            return PolicyResult("DENY", True, "prohibited", reasons + ["prohibited action"])

        if context.environment == "prod" and definition.mutates and definition.base_risk in {"medium", "high"}:
            return PolicyResult("DENY", True, definition.base_risk, reasons + ["production mutation denied"])

        if context.environment not in definition.allowed_environments:
            return PolicyResult("DENY", True, definition.base_risk, reasons + ["environment not allowed"])

        if definition.base_risk == "read_only":
            return PolicyResult("ALLOW", False, definition.base_risk, reasons + ["read-only auto allowed"])

        if context.mode == "dry_run":
            return PolicyResult("REQUIRE_APPROVAL", True, definition.base_risk, reasons + ["dry-run does not mutate"])

        if context.mode == "night_autopilot":
            if context.service not in context.allowed_services:
                return PolicyResult("ESCALATE", True, definition.base_risk, reasons + ["service not covered"])
            if context.environment not in context.allowed_environments:
                return PolicyResult("ESCALATE", True, definition.base_risk, reasons + ["environment not covered"])
            if action_type not in context.allowlisted_actions:
                return PolicyResult("REQUIRE_APPROVAL", True, definition.base_risk, reasons + ["not allowlisted"])
            if not risk_at_most(definition.base_risk, context.max_automatic_risk):
                return PolicyResult("REQUIRE_APPROVAL", True, definition.base_risk, reasons + ["above autopilot max risk"])
            return PolicyResult("ALLOW", False, definition.base_risk, reasons + ["night autopilot allowlist"])

        if context.approved:
            return PolicyResult("ALLOW", False, definition.base_risk, reasons + ["human approved"])

        if definition.default_requires_approval:
            return PolicyResult("REQUIRE_APPROVAL", True, definition.base_risk, reasons + ["default approval required"])

        return PolicyResult("ALLOW", False, definition.base_risk, reasons + ["default allowed"])
