"""Local identity and workspace membership helpers."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import User, WorkspaceMembership

ADMIN_ROLES = {"owner", "admin"}
APPROVER_ROLES = {"owner", "admin", "operator"}
VALID_ROLES = ADMIN_ROLES | APPROVER_ROLES | {"viewer"}


@dataclass(frozen=True)
class Principal:
    user_id: str
    email: str
    tenant_id: str
    workspace_id: str
    role: str
    auth_mode: str = "local-header"

    @property
    def can_approve_actions(self) -> bool:
        return self.role in APPROVER_ROLES

    @property
    def can_admin_workspace(self) -> bool:
        return self.role in ADMIN_ROLES


def normalize_role(role: str | None) -> str:
    value = (role or "admin").strip().lower()
    return value if value in VALID_ROLES else "viewer"


def get_or_create_local_principal(
    db: Session,
    *,
    email: str | None,
    tenant_id: str,
    workspace_id: str,
    role: str | None = None,
) -> Principal:
    normalized_email = (email or "demo-user@opscat.local").strip().lower() or "demo-user@opscat.local"
    normalized_role = normalize_role(role)
    user = db.query(User).filter(User.email == normalized_email).one_or_none()
    if user is None:
        user = User(email=normalized_email, display_name=normalized_email.split("@")[0])
        db.add(user)
        db.flush()
    membership = (
        db.query(WorkspaceMembership)
        .filter(
            WorkspaceMembership.user_id == user.id,
            WorkspaceMembership.tenant_id == tenant_id,
            WorkspaceMembership.workspace_id == workspace_id,
        )
        .one_or_none()
    )
    if membership is None:
        membership = WorkspaceMembership(user_id=user.id, tenant_id=tenant_id, workspace_id=workspace_id, role=normalized_role)
        db.add(membership)
        db.flush()
    elif membership.role != normalized_role:
        membership.role = normalized_role
        db.add(membership)
        db.flush()
    return Principal(
        user_id=user.id,
        email=user.email,
        tenant_id=membership.tenant_id,
        workspace_id=membership.workspace_id,
        role=membership.role,
    )


def require_membership(db: Session, *, email: str, tenant_id: str, workspace_id: str) -> Principal | None:
    membership = (
        db.query(WorkspaceMembership)
        .join(User, WorkspaceMembership.user_id == User.id)
        .filter(
            User.email == email.strip().lower(),
            User.status == "active",
            WorkspaceMembership.tenant_id == tenant_id,
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.status == "active",
        )
        .one_or_none()
    )
    if membership is None:
        return None
    return Principal(
        user_id=membership.user.id,
        email=membership.user.email,
        tenant_id=membership.tenant_id,
        workspace_id=membership.workspace_id,
        role=membership.role,
    )
