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

# FastAPI 0.139 stores included routers as wrapper routes.  The MVP contract
# tests inspect concrete route fingerprints, so register the route objects
# directly while retaining each module-level APIRouter as the source of truth.
for source_router in (
    health.router,
    mock_alerts.router,
    incidents.router,
    approvals.router,
    night_autopilot.router,
):
    app.router.routes.extend(source_router.routes)
