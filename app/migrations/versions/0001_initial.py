"""Initial OpsCat local MVP incident schema."""

from __future__ import annotations

from sqlalchemy.engine import Connection

from app.db import Base
from app.models import _load_persistence_models

VERSION = "0001_initial"
DESCRIPTION = "Create incident, evidence, action, approval, and timeline tables."
_INITIAL_TABLES = (
    "incidents",
    "action_proposals",
    "approval_decisions",
    "evidence",
    "timeline_events",
)


def upgrade(connection: Connection) -> None:
    _load_persistence_models()
    for table_name in _INITIAL_TABLES:
        Base.metadata.tables[table_name].create(bind=connection, checkfirst=True)
