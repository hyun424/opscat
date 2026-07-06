"""Action, risk, policy, and approval domain models for OpsCat MVP."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class RiskLevel(StrEnum):
    READ_ONLY = "read_only"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    PROHIBITED = "prohibited"


class PolicyDecision(StrEnum):
    ALLOW = "ALLOW"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    DENY = "DENY"
    ESCALATE = "ESCALATE"


class ActionStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    FAILED = "failed"
    DENIED = "denied"


@dataclass(frozen=True)
class ActionMetadata:
    name: str
    description: str
    base_risk: RiskLevel
    is_read_only: bool
    is_mutation: bool
    reversible: bool
    blast_radius: str
    default_requires_approval: bool
    allowed_environments: tuple[str, ...] = ("dev", "staging", "test", "local")
    required_capabilities: tuple[str, ...] = ()
    required_preconditions: tuple[str, ...] = ()
    post_checks: tuple[str, ...] = ()
    prohibited_reason: str | None = None


@dataclass(frozen=True)
class ActionRequest:
    action_type: str
    target: str
    environment: str = "local"
    payload: Mapping[str, Any] = field(default_factory=dict)
    requester: str = "agent"
    incident_id: str | None = None
    approved: bool = False
    approval_id: str | None = None


@dataclass(frozen=True)
class PolicyEvaluation:
    decision: PolicyDecision
    risk_level: RiskLevel
    requires_approval: bool
    reason: str
    action: ActionMetadata | None = None
    missing_capabilities: tuple[str, ...] = ()
    preconditions: tuple[str, ...] = ()
    post_checks: tuple[str, ...] = ()

    @property
    def executable_now(self) -> bool:
        return self.decision == PolicyDecision.ALLOW and not self.requires_approval

    @property
    def reasons(self) -> list[str]:
        details = [self.reason]
        if self.missing_capabilities:
            details.append("missing capabilities: " + ", ".join(self.missing_capabilities))
        return details


@dataclass
class ApprovalRecord:
    action_request: ActionRequest
    evaluation: PolicyEvaluation
    id: str = field(default_factory=lambda: str(uuid4()))
    status: ActionStatus = ActionStatus.PROPOSED
    decided_by: str | None = None
    decision_reason: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    decided_at: datetime | None = None

    def approve(self, actor: str, reason: str = "approved") -> None:
        self.status = ActionStatus.APPROVED
        self.decided_by = actor
        self.decision_reason = reason
        self.decided_at = datetime.now(UTC)

    def reject(self, actor: str, reason: str = "rejected") -> None:
        self.status = ActionStatus.REJECTED
        self.decided_by = actor
        self.decision_reason = reason
        self.decided_at = datetime.now(UTC)


@dataclass(frozen=True)
class ActionExecutionResult:
    action_type: str
    target: str
    status: ActionStatus
    message: str
    output: Mapping[str, Any] = field(default_factory=dict)
    verification: Mapping[str, Any] = field(default_factory=dict)


# SQLAlchemy persistence model used by the incident API. The dataclass
# action-policy types above remain dependency-light for policy/action services.
class ActionProposal(Base):
    __tablename__ = "action_proposals"

        incident = relationship("Incident", back_populates="actions")
        approvals = relationship(
            "ApprovalDecision", back_populates="action", cascade="all, delete-orphan"
        )
