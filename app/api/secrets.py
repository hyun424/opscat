"""Local connector secret lifecycle API.

This is not production auth. It exposes metadata-only local secret management
behind the existing local-header principal boundary for OSS/P5 demos.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.security.dependencies import get_current_principal
from app.services.audit_service import record_audit_event
from app.services.authorization import AuthorizationError
from app.services.identity_service import Principal
from app.services.redaction import redact_value
from app.services.secret_service import LocalEncryptedSecretProvider, SecretNotFoundError, SecretRef

router = APIRouter(prefix="/secrets", tags=["secrets"])


class SecretUpsertRequest(BaseModel):
    value: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.get("")
def list_secrets(principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)) -> dict[str, Any]:
    provider = LocalEncryptedSecretProvider()
    refs = provider.list_refs(db, principal)
    record_audit_event(
        db,
        tenant_id=principal.tenant_id,
        workspace_id=principal.workspace_id,
        actor=principal.email,
        event_type="secret_listed",
        resource_type="secret",
        resource_id="metadata-list",
        metadata={"count": len(refs)},
    )
    return {"secrets": [_ref_payload(ref) for ref in refs]}


@router.put("/{name}")
def put_secret(name: str, request: SecretUpsertRequest, principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)) -> dict[str, Any]:
    provider = LocalEncryptedSecretProvider()
    try:
        ref = provider.put_secret(db, principal, name, request.value, metadata=request.metadata)
    except AuthorizationError as exc:
        raise HTTPException(status_code=403, detail={"message": str(exc), "workspace_id": exc.workspace_id}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"message": str(exc)}) from exc
    return {"secret": _ref_payload(ref)}


@router.delete("/{name}")
def delete_secret(name: str, principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)) -> dict[str, str]:
    provider = LocalEncryptedSecretProvider()
    try:
        provider.delete_secret(db, principal, name)
    except AuthorizationError as exc:
        raise HTTPException(status_code=403, detail={"message": str(exc), "workspace_id": exc.workspace_id}) from exc
    except SecretNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"message": "secret not found", "name": str(exc).strip("'")}) from exc
    return {"deleted": name.strip().lower()}


def _ref_payload(ref: SecretRef) -> dict[str, Any]:
    return {
        "tenant_id": ref.tenant_id,
        "workspace_id": ref.workspace_id,
        "name": ref.name,
        "provider": ref.provider,
        "metadata": redact_value(ref.metadata),
    }
