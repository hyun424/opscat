#!/usr/bin/env python3
"""Run OpsCat P22 night-shift runtime drill."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.night_shift_drill import load_drill_scenarios, run_night_shift_drill, write_night_shift_outputs  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat night-shift runtime drill")
    parser.add_argument("--cases", default="evals/judgment/seed/cases.json")
    parser.add_argument("--max-cases", type=int, default=4)
    parser.add_argument("--max-ticks", type=int, default=4)
    parser.add_argument("--approval-mode", default="auto_readonly", choices=("locked", "manual", "enter_to_approve", "auto_readonly", "auto_safe_mock"))
    parser.add_argument("--output-json", default="")
    parser.add_argument("--output-md", default="")
    args = parser.parse_args()

    scenarios = load_drill_scenarios(args.cases, max_cases=args.max_cases)
    result = run_night_shift_drill(scenarios, approval_mode=args.approval_mode, max_ticks=args.max_ticks)
    payload = result.to_dict()
    write_night_shift_outputs(payload, output_json=args.output_json or None, output_md=args.output_md or None)
    score = payload["score"]
    summary = payload["summary"]
    print(
        f"OpsCat night-drill scenarios={summary['scenario_count']} processed={summary['processed_count']} "
        f"queue_depth={summary['queue_depth']} safety_violations={score['safety_violation_count']} "
        f"sla_pass_rate={score['sla_pass_rate']} action_execution_enabled=False"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
