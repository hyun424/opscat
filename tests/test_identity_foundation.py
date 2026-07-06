from __future__ import annotations

from typing import Any

from sqlalchemy import create_engine, inspect

from app.migrations.runner import run_migrations
from app.models import User, WorkspaceMembership
from app.services.identity_service import get_or_create_local_principal, require_membership


def test_identity_migration_creates_user_and_membership_tables(tmp_path) -> None:  # type: ignore[no-untyped-def]
    engine = create_engine(f"sqlite:///{tmp_path / 'opscat.db'}", future=True)

    assert run_migrations(engine) == ["0001_initial", "0002_identity_memberships"]

    tables = set(inspect(engine).get_table_names())
    assert {"users", "workspace_memberships"} <= tables


def test_local_principal_creates_active_membership(db_session: Any) -> None:
    principal = get_or_create_local_principal(
        db_session,
        email="OnCall@Example.com",
        tenant_id="tenant-a",
        workspace_id="workspace-a",
        role="operator",
    )

    assert principal.email == "oncall@example.com"
    assert principal.tenant_id == "tenant-a"
    assert principal.workspace_id == "workspace-a"
    assert principal.role == "operator"
    assert principal.can_approve_actions is True
    assert db_session.query(User).filter(User.email == "oncall@example.com").count() == 1
    assert db_session.query(WorkspaceMembership).filter(WorkspaceMembership.workspace_id == "workspace-a").count() == 1


def test_membership_lookup_fails_closed_for_unjoined_workspace(db_session: Any) -> None:
    get_or_create_local_principal(
        db_session,
        email="member@example.com",
        tenant_id="tenant-a",
        workspace_id="workspace-a",
        role="viewer",
    )

    assert require_membership(db_session, email="member@example.com", tenant_id="tenant-a", workspace_id="workspace-a") is not None
    assert require_membership(db_session, email="member@example.com", tenant_id="tenant-a", workspace_id="workspace-b") is None


def test_whoami_exposes_demo_identity_boundary(client: Any) -> None:
    response = client.get(
        "/auth/whoami",
        headers={
            "X-OpsCat-Actor": "operator@example.com",
            "X-OpsCat-Tenant": "tenant-paid-beta",
            "X-OpsCat-Workspace": "workspace-oncall",
            "X-OpsCat-Role": "operator",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["email"] == "operator@example.com"
    assert body["tenant_id"] == "tenant-paid-beta"
    assert body["workspace_id"] == "workspace-oncall"
    assert body["role"] == "operator"
    assert body["capabilities"]["can_approve_actions"] is True
    assert "demo-mode" in body["known_gap"]
