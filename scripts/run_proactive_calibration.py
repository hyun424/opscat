#!/usr/bin/env python3
"""Run OpsCat P25 proactive corpus calibration."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.proactive_risk_sentinel import (  # noqa: E402
    ProactiveRiskSentinel,
    evaluate_proactive_calibration,
    load_proactive_fixtures,
    write_proactive_calibration_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat proactive calibration")
    parser.add_argument("--fixtures", default="evals/proactive/seed/risk_windows.json")
    parser.add_argument("--output-json", default="")
    parser.add_argument("--output-md", default="")
    args = parser.parse_args()

    windows = load_proactive_fixtures(args.fixtures)
    result = ProactiveRiskSentinel().run(windows)
    report = evaluate_proactive_calibration(result)
    payload = report.to_dict()
    write_proactive_calibration_outputs(payload, output_json=args.output_json or None, output_md=args.output_md or None)
    print(
        f"OpsCat proactive-calibration windows={payload['summary']['window_count']} "
        f"risk_types={payload['summary']['risk_type_count']} passed={payload['passed']} "
        f"route_mismatch={payload['score']['route_mismatch_count']} eta_out={payload['score']['eta_out_of_range_count']} "
        f"unsafe_auto={payload['score']['unsafe_auto_action_count']} action_execution_enabled=False"
    )
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
