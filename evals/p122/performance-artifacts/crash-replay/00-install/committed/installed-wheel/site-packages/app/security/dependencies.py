"""FastAPI dependencies for the local identity foundation."""

from __future__ import annotations

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.api.workspace import get_workspace_id
from app.db import get_db
from app.services.identity_service import Principal, get_or_create_local_principal


def get_current_principal(
    x_opscat_actor: str | None = Header(default=None),
    x_opscat_role: str | None = Header(default=None),
    x_opscat_tenant: str | None = Header(default=None),
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
) -> Principal:
    tenant_id = (x_opscat_tenant or "demo").strip() or "demo"
    return get_or_create_local_principal(
        db,
        email=x_opscat_actor,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        role=x_opscat_role,
    )
