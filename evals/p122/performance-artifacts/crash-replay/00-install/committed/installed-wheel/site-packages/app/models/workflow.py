"""Durable local workflow and connector replay records."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class WorkflowJob(Base):
    __tablename__ = "workflow_jobs"
    __table_args__ = (UniqueConstraint("tenant_id", "workspace_id", "queue_name", "dedupe_key", name="uq_workflow_job_scope_dedupe"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String, default="demo", index=True)
    workspace_id: Mapped[str] = mapped_column(String, default="demo", index=True)
    queue_name: Mapped[str] = mapped_column(String, index=True)
    job_type: Mapped[str] = mapped_column(String, index=True)
    dedupe_key: Mapped[str] = mapped_column(String, index=True)
    incident_id: Mapped[str | None] = mapped_column(ForeignKey("incidents.id"), index=True)
    status: Mapped[str] = mapped_column(String, default="pending", index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    lease_owner: Mapped[str | None] = mapped_column(String)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    incident = relationship("Incident")


class ConnectorCallRecord(Base):
    __tablename__ = "connector_call_records"
    __table_args__ = (UniqueConstraint("tenant_id", "workspace_id", "connector_id", "capability", "idempotency_key", name="uq_connector_call_idempotency"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String, default="demo", index=True)
    workspace_id: Mapped[str] = mapped_column(String, default="demo", index=True)
    connector_id: Mapped[str] = mapped_column(String, index=True)
    capability: Mapped[str] = mapped_column(String, index=True)
    idempotency_key: Mapped[str] = mapped_column(String, index=True)
    request_hash: Mapped[str] = mapped_column(String, index=True)
    incident_id: Mapped[str | None] = mapped_column(String, index=True)
    status: Mapped[str] = mapped_column(String, default="completed", index=True)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    failure_class: Mapped[str | None] = mapped_column(String)
    side_effects_emitted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
