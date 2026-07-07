from __future__ import annotations

from sqlalchemy import create_engine, inspect, select

from app.migrations.runner import migration_status, run_migrations, schema_migrations


def test_run_migrations_creates_current_schema_and_records_version(tmp_path) -> None:  # type: ignore[no-untyped-def]
    engine = create_engine(f"sqlite:///{tmp_path / 'opscat.db'}", future=True)

    applied = run_migrations(engine)

    assert applied == [
        "0001_initial",
        "0002_identity_memberships",
        "0003_audit_events",
        "0004_secret_records",
        "0005_workflow_jobs",
        "0006_action_execution_attempts",
        "0007_connector_call_records",
    ]
    tables = set(inspect(engine).get_table_names())
    assert {
        "schema_migrations",
        "incidents",
        "evidence",
        "action_proposals",
        "approval_decisions",
        "timeline_events",
        "users",
        "workspace_memberships",
        "audit_events",
        "secret_records",
        "workflow_jobs",
        "action_execution_attempts",
        "connector_call_records",
    } <= tables
    with engine.connect() as connection:
        rows = connection.execute(select(schema_migrations.c.version)).all()
    assert [row[0] for row in rows] == [
        "0001_initial",
        "0002_identity_memberships",
        "0003_audit_events",
        "0004_secret_records",
        "0005_workflow_jobs",
        "0006_action_execution_attempts",
        "0007_connector_call_records",
    ]


def test_run_migrations_is_idempotent(tmp_path) -> None:  # type: ignore[no-untyped-def]
    engine = create_engine(f"sqlite:///{tmp_path / 'opscat.db'}", future=True)

    assert run_migrations(engine) == [
        "0001_initial",
        "0002_identity_memberships",
        "0003_audit_events",
        "0004_secret_records",
        "0005_workflow_jobs",
        "0006_action_execution_attempts",
        "0007_connector_call_records",
    ]
    assert run_migrations(engine) == []

    status = migration_status(engine)
    assert [(item.version, item.applied) for item in status] == [
        ("0001_initial", True),
        ("0002_identity_memberships", True),
        ("0003_audit_events", True),
        ("0004_secret_records", True),
        ("0005_workflow_jobs", True),
        ("0006_action_execution_attempts", True),
        ("0007_connector_call_records", True),
    ]
    with engine.connect() as connection:
        rows = connection.execute(select(schema_migrations.c.version)).all()
    assert len(rows) == 7
