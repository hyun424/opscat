from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class ActionProposal(Base):
    __tablename__ = "action_proposals"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
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
    status: Mapped[str] = mapped_column(String, default="proposed", index=True)
    execution_result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    incident = relationship("Incident", back_populates="actions")
    approvals = relationship("ApprovalDecision", back_populates="action", cascade="all, delete-orphan")
