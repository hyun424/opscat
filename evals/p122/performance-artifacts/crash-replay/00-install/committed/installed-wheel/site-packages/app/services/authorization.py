"""Service-layer authorization guards for tenant/workspace scoped resources."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.services.identity_service import Principal


class ScopedResource(Protocol):
    tenant_id: str
    workspace_id: str


@dataclass(frozen=True)
class AuthorizationError(Exception):
    message: str
    tenant_id: str | None = None
    workspace_id: str | None = None

    def __str__(self) -> str:
        return self.message


def require_same_scope(principal: Principal, resource: ScopedResource, *, action: str) -> None:
    if principal.tenant_id != resource.tenant_id or principal.workspace_id != resource.workspace_id:
        raise AuthorizationError(
            f"principal is not authorized to {action} in this tenant/workspace",
            tenant_id=principal.tenant_id,
            workspace_id=principal.workspace_id,
        )


def require_signal_scope(principal: Principal, *, tenant_id: str, workspace_id: str) -> None:
    if tenant_id not in {"demo", principal.tenant_id} or workspace_id not in {"demo", principal.workspace_id}:
        raise AuthorizationError(
            "alert payload scope does not match authenticated principal scope",
            tenant_id=principal.tenant_id,
            workspace_id=principal.workspace_id,
        )


def require_action_approval_authority(principal: Principal) -> None:
    if not principal.can_approve_actions:
        raise AuthorizationError(
            "principal cannot approve or reject actions",
            tenant_id=principal.tenant_id,
            workspace_id=principal.workspace_id,
        )
