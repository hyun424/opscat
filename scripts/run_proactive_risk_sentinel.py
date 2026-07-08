#!/usr/bin/env python3
"""Run OpsCat P24 proactive risk sentinel."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.proactive_risk_sentinel import ProactiveRiskSentinel, load_proactive_fixtures, write_proactive_outputs  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat proactive risk sentinel")
    parser.add_argument("--fixtures", default="evals/proactive/seed/risk_windows.json")
    parser.add_argument("--max-windows", type=int, default=12)
    parser.add_argument("--output-json", default="")
    parser.add_argument("--output-md", default="")
    args = parser.parse_args()

    windows = load_proactive_fixtures(args.fixtures)
    result = ProactiveRiskSentinel().run(windows, max_windows=args.max_windows)
    payload = result.to_dict()
    write_proactive_outputs(payload, output_json=args.output_json or None, output_md=args.output_md or None)
    print(
        f"OpsCat proactive windows={payload['summary']['window_count']} forecasts={payload['summary']['forecast_count']} "
        f"unsafe_auto={payload['score']['unsafe_auto_action_count']} lead_time_min={payload['score']['lead_time_minutes_min']} "
        "action_execution_enabled=False"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
