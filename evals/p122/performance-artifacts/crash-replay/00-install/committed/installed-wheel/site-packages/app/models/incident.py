from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String, default="demo", index=True)
    workspace_id: Mapped[str] = mapped_column(String, default="demo", index=True)
    alert_fingerprint: Mapped[str] = mapped_column(String, default=lambda: str(uuid4()), index=True)
    source: Mapped[str] = mapped_column(String, default="mock")
    status: Mapped[str] = mapped_column(String, default="new", index=True)
    service: Mapped[str] = mapped_column(String, index=True)
    environment: Mapped[str] = mapped_column(String, index=True)
    severity: Mapped[str] = mapped_column(String, index=True)
    alert_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    summary: Mapped[str | None] = mapped_column(Text)
    root_cause_candidate: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    evidence = relationship("Evidence", back_populates="incident", cascade="all, delete-orphan")
    actions = relationship("ActionProposal", back_populates="incident", cascade="all, delete-orphan")
    timeline = relationship(
        "TimelineEvent",
        back_populates="incident",
        cascade="all, delete-orphan",
        order_by="TimelineEvent.timestamp",
    )
