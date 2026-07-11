from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    tenant_id: Mapped[str] = mapped_column(String, default="demo", index=True)
    workspace_id: Mapped[str] = mapped_column(String, default="demo", index=True)
    type: Mapped[str] = mapped_column(String, index=True)
    source: Mapped[str] = mapped_column(String, default="mock")
    source_url: Mapped[str | None] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    evidence_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    incident = relationship("Incident", back_populates="evidence")
