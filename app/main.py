from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import approvals, auth, connectors, health, incidents, mock_alerts, night_autopilot, operator, secrets
from app.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


app = FastAPI(
    title="OpsCat Local MVP",
    version="0.1.0",
    description="Mock AI on-call agent with policy-gated action execution and audit reports.",
    lifespan=lifespan,
)

for source_router in (
    health.router,
    auth.router,
    connectors.router,
    secrets.router,
    mock_alerts.router,
    incidents.router,
    approvals.router,
    night_autopilot.router,
    operator.router,
):
    app.include_router(source_router)
