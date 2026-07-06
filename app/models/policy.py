from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class ApprovalDecision(Base):
    __tablename__ = "approval_decisions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    action_id: Mapped[str] = mapped_column(ForeignKey("action_proposals.id"), index=True)
    decision: Mapped[str] = mapped_column(String)
    actor: Mapped[str] = mapped_column(String, default="human")
    reason: Mapped[str | None] = mapped_column(Text)
    decision_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    action = relationship("ActionProposal", back_populates="approvals")
