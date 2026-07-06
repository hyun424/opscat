"""Optional FastAPI approval routes for OpsCat.

from app.db import get_db
from app.schemas.incidents import ActionRead, ApprovalRequest, ApprovalResponse, IncidentRead
from app.services.incident_service import decide_action

from __future__ import annotations

from typing import Any

from app.models.action import ActionRequest
from app.services.action_service import ActionService
from app.services.policy_engine import PolicyContext, default_capabilities

try:  # pragma: no cover - exercised in integration once FastAPI scaffold exists.
    from fastapi import APIRouter, HTTPException  # type: ignore[import-not-found]
    from pydantic import BaseModel, Field  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover
    APIRouter = None  # type: ignore[assignment]
    HTTPException = None  # type: ignore[assignment]
    BaseModel = object  # type: ignore[assignment,misc]
    Field = None  # type: ignore[assignment]


class ApprovalProposalPayload(BaseModel):  # type: ignore[misc]
    action_type: str
    target: str
    environment: str = "local"
    incident_id: str | None = None
    payload: dict[str, Any] = {} if Field is None else Field(default_factory=dict)
    capabilities: list[str] = [] if Field is None else Field(default_factory=list)


class ApprovalDecisionPayload(BaseModel):  # type: ignore[misc]
    actor: str = "human"
    reason: str = "approved"


service = ActionService()


def create_router(action_service: ActionService | None = None):
    if APIRouter is None:  # pragma: no cover
        raise RuntimeError(
            "FastAPI is not installed; install app dependencies to enable approval routes."
        )
    except Exception as exc:  # pragma: no cover - FastAPI boundary
        raise HTTPException(status_code=404, detail="action not found or invalid") from exc
    return ApprovalResponse(
        action=ActionRead.model_validate(action),
        incident=IncidentRead.model_validate(incident),
        report=report,
    )
