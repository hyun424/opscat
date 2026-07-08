#!/usr/bin/env python3
"""Run P69 autonomous worker runner."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.autonomous_worker_runner import (  # noqa: E402
    RecordingWorkerTransport,
    run_autonomous_worker_runner_fixture,
    write_autonomous_worker_runner_outputs,
)


def _completed_values(values: list[str]) -> set[str]:
    completed: set[str] = set()
    for value in values:
        completed.update(item.strip() for item in value.split(",") if item.strip())
    return completed


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P69 autonomous worker runner")
    parser.add_argument("--manifest", default="evals/planning/p66_autonomous_day_loop_backlog.json")
    parser.add_argument("--completed", action="append", default=[])
    parser.add_argument("--max-tickets", type=int, default=3)
    parser.add_argument("--max-parallel", type=int, default=2)
    parser.add_argument("--dispatch-dir", default="/tmp/opscat-autonomous-worker-runner-dispatch")
    parser.add_argument("--state-path", default="/tmp/opscat-autonomous-worker-runner-state.json")
    parser.add_argument("--output-json", default="/tmp/opscat-autonomous-worker-runner-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-autonomous-worker-runner-latest.md")
    args = parser.parse_args()

    report = run_autonomous_worker_runner_fixture(
        args.manifest,
        completed=_completed_values(args.completed),
        max_tickets=args.max_tickets,
        max_parallel=args.max_parallel,
        dispatch_dir=args.dispatch_dir,
        state_path=args.state_path,
        transport=RecordingWorkerTransport(),
    )
    payload = report.to_dict()
    write_autonomous_worker_runner_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    summary = payload["summary"]
    score = payload["score"]
    print(
        "OpsCat autonomous-worker-runner "
        f"claimed={summary['claimed_packet_count']} succeeded={summary['succeeded_run_count']} "
        f"failed={summary['failed_run_count']} retry={summary['retry_queue_count']} "
        f"spawned={score['spawned_process_count']} shell_exec={score['shell_command_execution_count']}"
    )
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
