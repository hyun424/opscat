#!/usr/bin/env python3
"""Run P66 autonomous day loop backlog planner."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.autonomous_day_loop_backlog import (  # noqa: E402
    run_autonomous_day_loop_backlog_fixture,
    write_autonomous_day_loop_backlog_outputs,
)


def _completed_values(values: list[str]) -> set[str]:
    completed: set[str] = set()
    for value in values:
        completed.update(item.strip() for item in value.split(",") if item.strip())
    return completed


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P66 autonomous day loop backlog planner")
    parser.add_argument("--manifest", default="evals/planning/p66_autonomous_day_loop_backlog.json")
    parser.add_argument("--completed", action="append", default=[])
    parser.add_argument("--output-json", default="/tmp/opscat-autonomous-day-loop-backlog-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-autonomous-day-loop-backlog-latest.md")
    args = parser.parse_args()

    report = run_autonomous_day_loop_backlog_fixture(args.manifest, completed=_completed_values(args.completed))
    payload = report.to_dict()
    write_autonomous_day_loop_backlog_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    summary = payload["summary"]
    score = payload["score"]
    print(
        "OpsCat autonomous-day-loop-backlog "
        f"tickets={summary['ticket_count']} runnable_now={summary['runnable_now_count']} "
        f"planned_batches={summary['planned_batch_count']} cycles={summary['day_loop_cycle_count']} "
        f"side_effects={sum(int(value) for value in score.values())}"
    )
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
