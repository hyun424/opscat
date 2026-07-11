"""Encrypted connector secret persistence model."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class SecretRecord(Base):
    __tablename__ = "secret_records"
    __table_args__ = (UniqueConstraint("tenant_id", "workspace_id", "name", name="uq_secret_records_scope_name"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String, default="demo", index=True)
    workspace_id: Mapped[str] = mapped_column(String, default="demo", index=True)
    name: Mapped[str] = mapped_column(String, index=True)
    provider: Mapped[str] = mapped_column(String, default="local-envelope")
    ciphertext: Mapped[str] = mapped_column(String)
    salt: Mapped[str] = mapped_column(String)
    nonce: Mapped[str] = mapped_column(String)
    tag: Mapped[str] = mapped_column(String)
    secret_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
