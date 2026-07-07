"""Dependency-light migration runner for the local OpsCat control plane.

This is intentionally small while OpsCat is still a local/mock MVP. It gives the
project a production-shaped migration boundary without adding Alembic yet:
ordered version modules, a durable schema_migrations table, idempotent applies,
and a CLI-visible status surface. Later migrations can replace this with Alembic
without changing the application startup contract: call run_migrations(engine).
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, MetaData, String, Table, create_engine, select
from sqlalchemy.engine import Connection, Engine

from app.config import get_settings

MIGRATION_MODULES = (
    "app.migrations.versions.0001_initial",
    "app.migrations.versions.0002_identity_memberships",
    "app.migrations.versions.0003_audit_events",
    "app.migrations.versions.0004_secret_records",
)

metadata = MetaData()
schema_migrations = Table(
    "schema_migrations",
    metadata,
    Column("version", String, primary_key=True),
    Column("description", String, nullable=False),
    Column("applied_at", DateTime(timezone=True), nullable=False),
)


@dataclass(frozen=True)
class Migration:
    version: str
    description: str
    upgrade: Callable[[Connection], None]


@dataclass(frozen=True)
class MigrationStatus:
    version: str
    description: str
    applied: bool


def configured_engine() -> Engine:
    database_url = get_settings().database_url
    connect_args: dict[str, object] = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args, future=True)


def load_migrations() -> list[Migration]:
    migrations: list[Migration] = []
    seen: set[str] = set()
    for module_name in MIGRATION_MODULES:
        module = importlib.import_module(module_name)
        version = str(module.VERSION)
        if version in seen:
            raise RuntimeError(f"Duplicate migration version: {version}")
        seen.add(version)
        migrations.append(
            Migration(
                version=version,
                description=str(module.DESCRIPTION),
                upgrade=module.upgrade,
            )
        )
    return migrations


def applied_versions(connection: Connection) -> set[str]:
    metadata.create_all(bind=connection)
    rows = connection.execute(select(schema_migrations.c.version)).all()
    return {str(row[0]) for row in rows}


def migration_status(engine: Engine | None = None) -> list[MigrationStatus]:
    owned_engine = engine is None
    active_engine = engine or configured_engine()
    try:
        with active_engine.begin() as connection:
            applied = applied_versions(connection)
            return [
                MigrationStatus(version=item.version, description=item.description, applied=item.version in applied)
                for item in load_migrations()
            ]
    finally:
        if owned_engine:
            active_engine.dispose()


def run_migrations(engine: Engine | None = None) -> list[str]:
    owned_engine = engine is None
    active_engine = engine or configured_engine()
    applied_now: list[str] = []
    try:
        with active_engine.begin() as connection:
            applied = applied_versions(connection)
            for migration in load_migrations():
                if migration.version in applied:
                    continue
                migration.upgrade(connection)
                connection.execute(
                    schema_migrations.insert().values(
                        version=migration.version,
                        description=migration.description,
                        applied_at=datetime.now(UTC),
                    )
                )
                applied_now.append(migration.version)
        return applied_now
    finally:
        if owned_engine:
            active_engine.dispose()
