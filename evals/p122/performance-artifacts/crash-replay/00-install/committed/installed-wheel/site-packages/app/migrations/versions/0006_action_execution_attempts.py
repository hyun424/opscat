"""Immutable action execution attempts."""

from __future__ import annotations

from sqlalchemy.engine import Connection

from app.db import Base
from app.models import _load_persistence_models

VERSION = "0006_action_execution_attempts"
DESCRIPTION = "Create immutable action execution attempts table."


def upgrade(connection: Connection) -> None:
    _load_persistence_models()
    Base.metadata.tables["action_execution_attempts"].create(bind=connection, checkfirst=True)
