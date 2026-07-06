"""Safety policy primitives for OpsCat action execution.

The MVP must never perform dangerous production mutations.  This module is
intentionally pure: it classifies proposed actions before any executor or tool
runner can perform side effects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Mapping, Sequence


class PolicyDecision(StrEnum):
    """Possible policy outcomes for a proposed action."""

    ALLOW = "ALLOW"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    DENY = "DENY"
    ESCALATE = "ESCALATE"


class RiskLevel(StrEnum):
    """Action risk levels from the product decision record."""

    READ_ONLY = "read_only"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    PROHIBITED = "prohibited"


class MutationKind(StrEnum):
    """Mutation traits used by action/tool registry entries."""

    READ_ONLY = "read_only"
    TIMELINE_WRITE = "timeline_write"
    EXTERNAL_WRITE = "external_write"
    PRODUCTION_MUTATION = "production_mutation"
    DATABASE_MUTATION = "database_mutation"
    INFRASTRUCTURE_MUTATION = "infrastructure_mutation"
    DATA_DELETION = "data_deletion"
    SECRET_ACCESS = "secret_access"
    ARBITRARY_SHELL = "arbitrary_shell"


PRODUCTION_ENVIRONMENTS = frozenset({"prod", "production", "live"})
PROHIBITED_MUTATIONS = frozenset(
    {
        MutationKind.PRODUCTION_MUTATION,
        MutationKind.DATABASE_MUTATION,
        MutationKind.INFRASTRUCTURE_MUTATION,
        MutationKind.DATA_DELETION,
        MutationKind.SECRET_ACCESS,
        MutationKind.ARBITRARY_SHELL,
    }
)


@dataclass(frozen=True)
class ActionRequest:
    """A side-effecting action proposal before execution."""

    name: str
    environment: str
    risk_level: RiskLevel
    mutation_kind: MutationKind = MutationKind.READ_ONLY
    requires_approval: bool = False
    approved: bool = False
    post_checks: Sequence[str] = field(default_factory=tuple)
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class PolicyResult:
    """Policy decision with auditable reasons."""

    decision: PolicyDecision
    reasons: tuple[str, ...]

    @property
    def allowed(self) -> bool:
        return self.decision is PolicyDecision.ALLOW


def _normalized_environment(environment: str) -> str:
    return environment.strip().lower().replace("_", "-")


def is_production_environment(environment: str) -> bool:
    """Return true for production aliases used by operators and integrations."""

    normalized = _normalized_environment(environment)
    return normalized in PRODUCTION_ENVIRONMENTS


def evaluate_action_policy(request: ActionRequest) -> PolicyResult:
    """Evaluate an action proposal before any side effect is attempted.

    The policy intentionally fails closed.  Production mutations, database
    mutation, cloud/infra mutation, data deletion, secret access, and arbitrary
    shell execution are denied even when an approval flag is present.
    """

    reasons: list[str] = []

    if request.risk_level is RiskLevel.PROHIBITED:
        reasons.append("risk level is prohibited")

    if request.mutation_kind in PROHIBITED_MUTATIONS:
        reasons.append(f"mutation kind is prohibited: {request.mutation_kind.value}")

    if is_production_environment(request.environment) and request.mutation_kind is not MutationKind.READ_ONLY:
        reasons.append("production mutations are disabled in the MVP")

    if request.risk_level in {RiskLevel.MEDIUM, RiskLevel.HIGH} and not request.post_checks:
        reasons.append("medium/high risk actions require post-checks")

    if reasons:
        return PolicyResult(PolicyDecision.DENY, tuple(reasons))

    if request.requires_approval and not request.approved:
        return PolicyResult(
            PolicyDecision.REQUIRE_APPROVAL,
            ("approval is required before this action can execute",),
        )

    return PolicyResult(PolicyDecision.ALLOW, ("action satisfies MVP safety policy",))
