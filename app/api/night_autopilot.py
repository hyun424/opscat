from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.incidents import NightAutopilotConfig, NightAutopilotResult
from app.services.night_autopilot import simulate_night_autopilot

router = APIRouter(prefix="/night-autopilot", tags=["night-autopilot"])


@router.post("/simulate", response_model=NightAutopilotResult)
def simulate(config: NightAutopilotConfig, db: Session = Depends(get_db)) -> NightAutopilotResult:
    return simulate_night_autopilot(db, config)
