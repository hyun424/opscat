#!/usr/bin/env python3
"""Run P68 autonomous agent dispatcher."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.autonomous_agent_dispatcher import (  # noqa: E402
    run_autonomous_agent_dispatcher_fixture,
    write_autonomous_agent_dispatcher_outputs,
)


def _completed_values(values: list[str]) -> set[str]:
    completed: set[str] = set()
    for value in values:
        completed.update(item.strip() for item in value.split(",") if item.strip())
    return completed


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P68 autonomous agent dispatcher")
    parser.add_argument("--manifest", default="evals/planning/p66_autonomous_day_loop_backlog.json")
    parser.add_argument("--completed", action="append", default=[])
    parser.add_argument("--max-tickets", type=int, default=3)
    parser.add_argument("--max-parallel", type=int, default=2)
    parser.add_argument("--dispatch-dir", default="/tmp/opscat-autonomous-agent-dispatcher-packets")
    parser.add_argument("--output-json", default="/tmp/opscat-autonomous-agent-dispatcher-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-autonomous-agent-dispatcher-latest.md")
    args = parser.parse_args()

    report = run_autonomous_agent_dispatcher_fixture(
        args.manifest,
        completed=_completed_values(args.completed),
        max_tickets=args.max_tickets,
        max_parallel=args.max_parallel,
        dispatch_dir=args.dispatch_dir,
    )
    payload = report.to_dict()
    write_autonomous_agent_dispatcher_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    summary = payload["summary"]
    score = payload["score"]
    print(
        "OpsCat autonomous-agent-dispatcher "
        f"packets={summary['dispatch_packet_count']} queued={summary['queued_packet_count']} "
        f"blocked={summary['blocked_dispatch_count']} next={summary['next_runnable_ticket']} "
        f"spawned={score['spawned_process_count']} shell_exec={score['shell_command_execution_count']}"
    )
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
