"""Identity and workspace membership foundation."""

from __future__ import annotations

from sqlalchemy.engine import Connection

from app.db import Base
from app.models import _load_persistence_models

VERSION = "0002_identity_memberships"
DESCRIPTION = "Create users and workspace membership tables."
_IDENTITY_TABLES = ("users", "workspace_memberships")


def upgrade(connection: Connection) -> None:
    _load_persistence_models()
    for table_name in _IDENTITY_TABLES:
        Base.metadata.tables[table_name].create(bind=connection, checkfirst=True)
