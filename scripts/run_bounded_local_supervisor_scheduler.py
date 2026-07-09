#!/usr/bin/env python3
"""Run P88 bounded local supervisor scheduler contract evaluation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.bounded_local_supervisor_scheduler import (  # noqa: E402
    evaluate_bounded_local_supervisor_scheduler_fixture,
    write_bounded_local_supervisor_scheduler_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P88 bounded local supervisor scheduler contract evaluation")
    parser.add_argument("--cases", default="evals/actions/p88_bounded_local_supervisor_scheduler.json")
    parser.add_argument("--output-json", default="/tmp/opscat-bounded-local-supervisor-scheduler-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-bounded-local-supervisor-scheduler-latest.md")
    args = parser.parse_args()

    report = evaluate_bounded_local_supervisor_scheduler_fixture(args.cases)
    payload = report.to_dict()
    write_bounded_local_supervisor_scheduler_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    summary = payload["summary"]
    print(
        "OpsCat bounded-local-supervisor-scheduler "
        f"scenarios={summary['scenario_count']} completed_all={summary['completed_all_count']} "
        f"max_cycles={summary['max_cycles_count']} needs_human={summary['needs_human_count']} "
        f"failed_guardrail={summary['failed_guardrail_count']} budget_exhausted={summary['budget_exhausted_count']} "
        f"executions={summary['executions']}"
    )
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
