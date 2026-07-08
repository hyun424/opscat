#!/usr/bin/env python3
"""Run P67 autonomous loop executor."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.autonomous_loop_executor import (  # noqa: E402
    run_autonomous_loop_executor_fixture,
    write_autonomous_loop_executor_outputs,
)


def _completed_values(values: list[str]) -> set[str]:
    completed: set[str] = set()
    for value in values:
        completed.update(item.strip() for item in value.split(",") if item.strip())
    return completed


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P67 autonomous loop executor")
    parser.add_argument("--manifest", default="evals/planning/p66_autonomous_day_loop_backlog.json")
    parser.add_argument("--completed", action="append", default=[])
    parser.add_argument("--mode", default="local-auto", choices=("local-auto", "dry-run"))
    parser.add_argument("--max-tickets", type=int, default=3)
    parser.add_argument("--prompt-dir", default="/tmp/opscat-autonomous-loop-executor-prompts")
    parser.add_argument("--output-json", default="/tmp/opscat-autonomous-loop-executor-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-autonomous-loop-executor-latest.md")
    args = parser.parse_args()

    report = run_autonomous_loop_executor_fixture(
        args.manifest,
        completed=_completed_values(args.completed),
        max_tickets=args.max_tickets,
        mode=args.mode,
        prompt_dir=args.prompt_dir,
    )
    payload = report.to_dict()
    write_autonomous_loop_executor_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    summary = payload["summary"]
    score = payload["score"]
    print(
        "OpsCat autonomous-loop-executor "
        f"mode={summary['mode']} selected={summary['selected_ticket_count']} "
        f"completed={summary['completed_ticket_count']} blocked={summary['blocked_ticket_count']} "
        f"next={summary['next_runnable_ticket']} forbidden_side_effects="
        f"{score['live_api_call_count'] + score['credential_read_count'] + score['network_call_count'] + score['production_mutation_count'] + score['action_execution_count']}"
    )
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
