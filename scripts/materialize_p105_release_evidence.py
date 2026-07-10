from __future__ import annotations

# ruff: noqa: E402, I001

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.failure_forecast_engine import run_p105_materializer_cli  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(run_p105_materializer_cli())
