"""Initial OpsCat local MVP schema."""

from __future__ import annotations

from sqlalchemy.engine import Connection

from app.db import Base
from app.models import _load_persistence_models

VERSION = "0001_initial"
DESCRIPTION = "Create incident, evidence, action, approval, and timeline tables."


def upgrade(connection: Connection) -> None:
    _load_persistence_models()
    Base.metadata.create_all(bind=connection)
