from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class TimelineEvent(Base):
    __tablename__ = "timeline_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    actor: Mapped[str] = mapped_column(String, default="system")
    event_type: Mapped[str] = mapped_column(String, index=True)
    content: Mapped[str] = mapped_column(Text)
    event_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    incident = relationship("Incident", back_populates="timeline")
