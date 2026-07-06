"""Durable audit event log."""

from __future__ import annotations

from sqlalchemy.engine import Connection

from app.db import Base
from app.models import _load_persistence_models

VERSION = "0003_audit_events"
DESCRIPTION = "Create immutable audit event table."


def upgrade(connection: Connection) -> None:
    _load_persistence_models()
    Base.metadata.tables["audit_events"].create(bind=connection, checkfirst=True)
