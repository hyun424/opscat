from fastapi import APIRouter, Depends

from app.security.dependencies import get_current_principal
from app.services.identity_service import Principal

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/whoami")
def whoami(principal: Principal = Depends(get_current_principal)) -> dict[str, object]:
    return {
        "user_id": principal.user_id,
        "email": principal.email,
        "tenant_id": principal.tenant_id,
        "workspace_id": principal.workspace_id,
        "role": principal.role,
        "auth_mode": principal.auth_mode,
        "capabilities": {
            "can_approve_actions": principal.can_approve_actions,
            "can_admin_workspace": principal.can_admin_workspace,
        },
        "known_gap": "local-header identity is a demo-mode bootstrap, not production authentication",
    }
