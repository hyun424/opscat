from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import approvals, health, incidents, mock_alerts, night_autopilot
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
app.include_router(health.router)
app.include_router(mock_alerts.router)
app.include_router(incidents.router)
app.include_router(approvals.router)
app.include_router(night_autopilot.router)
