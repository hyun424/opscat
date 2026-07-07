"""Connector idempotency replay records."""

from __future__ import annotations

from sqlalchemy.engine import Connection

from app.db import Base
from app.models import _load_persistence_models

VERSION = "0007_connector_call_records"
DESCRIPTION = "Create connector idempotency replay records table."


def upgrade(connection: Connection) -> None:
    _load_persistence_models()
    Base.metadata.tables["connector_call_records"].create(bind=connection, checkfirst=True)
