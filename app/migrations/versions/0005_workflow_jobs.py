"""Durable local workflow job table."""

from __future__ import annotations

from sqlalchemy.engine import Connection

from app.db import Base
from app.models import _load_persistence_models

VERSION = "0005_workflow_jobs"
DESCRIPTION = "Create durable local workflow job table."


def upgrade(connection: Connection) -> None:
    _load_persistence_models()
    Base.metadata.tables["workflow_jobs"].create(bind=connection, checkfirst=True)
