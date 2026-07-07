"""Action, risk, policy, and approval domain models for OpsCat MVP."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
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
    ESCALATED = "escalated"


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
    tenant_id: str = "demo"
    workspace_id: str = "demo"
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

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    tenant_id: Mapped[str] = mapped_column(String, default="demo", index=True)
    workspace_id: Mapped[str] = mapped_column(String, default="demo", index=True)
    action_type: Mapped[str] = mapped_column(String, index=True)
    target: Mapped[str] = mapped_column(String)
    environment: Mapped[str] = mapped_column(String)
    risk_level: Mapped[str] = mapped_column(String)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    rationale: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    preconditions: Mapped[list[str]] = mapped_column(JSON, default=list)
    post_checks: Mapped[list[str]] = mapped_column(JSON, default=list)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    policy_decision: Mapped[str] = mapped_column(String, default="REQUIRE_APPROVAL")
    policy_reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    confidence: Mapped[float | None] = mapped_column(Float)
    escalation_required: Mapped[bool] = mapped_column(Boolean, default=False)
    escalation_decision: Mapped[str | None] = mapped_column(String)
    escalation_reason: Mapped[str | None] = mapped_column(Text)
    escalation_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String, default="proposed", index=True)
    execution_result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    incident = relationship("Incident", back_populates="actions")
    approvals = relationship("ApprovalDecision", back_populates="action", cascade="all, delete-orphan")
    execution_attempts = relationship("ActionExecutionAttempt", back_populates="action", cascade="all, delete-orphan", order_by="ActionExecutionAttempt.started_at")


class ActionExecutionAttempt(Base):
    __tablename__ = "action_execution_attempts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    action_id: Mapped[str] = mapped_column(ForeignKey("action_proposals.id"), index=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    tenant_id: Mapped[str] = mapped_column(String, default="demo", index=True)
    workspace_id: Mapped[str] = mapped_column(String, default="demo", index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)
    idempotency_key: Mapped[str] = mapped_column(String, index=True)
    status: Mapped[str] = mapped_column(String, default="running", index=True)
    precondition_result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    execution_result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    post_check_result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    retry_eligible: Mapped[bool] = mapped_column(Boolean, default=False)
    failure_class: Mapped[str | None] = mapped_column(String)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    action = relationship("ActionProposal", back_populates="execution_attempts")
    incident = relationship("Incident")
