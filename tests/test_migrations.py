from __future__ import annotations

from sqlalchemy import create_engine, inspect, select

from app.migrations.runner import migration_status, run_migrations, schema_migrations


def test_run_migrations_creates_current_schema_and_records_version(tmp_path) -> None:  # type: ignore[no-untyped-def]
    engine = create_engine(f"sqlite:///{tmp_path / 'opscat.db'}", future=True)

    applied = run_migrations(engine)

    assert applied == ["0001_initial", "0002_identity_memberships"]
    tables = set(inspect(engine).get_table_names())
    assert {
        "schema_migrations",
        "incidents",
        "evidence",
        "action_proposals",
        "approval_decisions",
        "timeline_events",
    } <= tables
    with engine.connect() as connection:
        rows = connection.execute(select(schema_migrations.c.version)).all()
    assert [row[0] for row in rows] == ["0001_initial", "0002_identity_memberships"]


def test_run_migrations_is_idempotent(tmp_path) -> None:  # type: ignore[no-untyped-def]
    engine = create_engine(f"sqlite:///{tmp_path / 'opscat.db'}", future=True)

    assert run_migrations(engine) == ["0001_initial", "0002_identity_memberships"]
    assert run_migrations(engine) == []

    status = migration_status(engine)
    assert [(item.version, item.applied) for item in status] == [("0001_initial", True), ("0002_identity_memberships", True)]
    with engine.connect() as connection:
        rows = connection.execute(select(schema_migrations.c.version)).all()
    assert len(rows) == 2
