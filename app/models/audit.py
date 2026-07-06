"""Immutable audit event persistence model."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String, default="demo", index=True)
    workspace_id: Mapped[str] = mapped_column(String, default="demo", index=True)
    actor: Mapped[str] = mapped_column(String, default="system", index=True)
    event_type: Mapped[str] = mapped_column(String, index=True)
    resource_type: Mapped[str] = mapped_column(String, index=True)
    resource_id: Mapped[str] = mapped_column(String, index=True)
    action_id: Mapped[str | None] = mapped_column(String, index=True)
    event_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
