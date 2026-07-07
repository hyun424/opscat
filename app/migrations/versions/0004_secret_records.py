"""Encrypted secret records."""

from __future__ import annotations

from sqlalchemy.engine import Connection

from app.db import Base
from app.models import _load_persistence_models

VERSION = "0004_secret_records"
DESCRIPTION = "Create encrypted secret record table."


def upgrade(connection: Connection) -> None:
    _load_persistence_models()
    Base.metadata.tables["secret_records"].create(bind=connection, checkfirst=True)
