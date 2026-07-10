from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.failure_forecast_engine import run_failure_forecast_cli

if __name__ == "__main__":
    raise SystemExit(run_failure_forecast_cli())
