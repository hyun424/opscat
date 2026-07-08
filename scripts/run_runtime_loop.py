#!/usr/bin/env python3
"""Run OpsCat P21 local/mock runtime loop."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.judgment_dataset import load_judgment_cases  # noqa: E402
from app.services.runtime_loop_control import run_runtime_for_cases, write_runtime_outputs  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat runtime loop")
    parser.add_argument("--cases", default="evals/judgment/seed/cases.json")
    parser.add_argument("--max-cases", type=int, default=2)
    parser.add_argument("--max-ticks", type=int, default=1)
    parser.add_argument("--approval-mode", default="manual", choices=("locked", "manual", "enter_to_approve", "auto_readonly", "auto_safe_mock"))
    parser.add_argument("--pause-after", type=int, default=-1)
    parser.add_argument("--output-json", default="")
    parser.add_argument("--output-md", default="")
    args = parser.parse_args()

    cases = load_judgment_cases(args.cases)[: args.max_cases]
    snapshot = run_runtime_for_cases(
        cases,
        approval_mode=args.approval_mode,
        max_ticks=args.max_ticks,
        pause_after=args.pause_after if args.pause_after >= 0 else None,
    )
    write_runtime_outputs(snapshot, output_json=args.output_json or None, output_md=args.output_md or None)
    print(
        f"OpsCat runtime status={snapshot['status']} queue_depth={snapshot['queue_depth']} "
        f"processed={snapshot['processed_count']} approval_mode={snapshot['approval_profile']['mode']} "
        "action_execution_enabled=False"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
