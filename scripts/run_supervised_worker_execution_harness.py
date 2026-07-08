#!/usr/bin/env python3
"""Run P71 supervised worker execution harness."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.supervised_worker_execution_harness import (  # noqa: E402
    RealSubprocessSupervisedTransport,
    SimulatedSupervisedProcessTransport,
    run_supervised_worker_execution_harness_fixture,
    write_supervised_worker_execution_harness_outputs,
)


def _completed_values(values: list[str]) -> set[str]:
    completed: set[str] = set()
    for value in values:
        completed.update(item.strip() for item in value.split(",") if item.strip())
    return completed


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P71 supervised worker execution harness")
    parser.add_argument("--manifest", default="evals/planning/p66_autonomous_day_loop_backlog.json")
    parser.add_argument("--completed", action="append", default=[])
    parser.add_argument("--max-tickets", type=int, default=3)
    parser.add_argument("--max-parallel", type=int, default=2)
    parser.add_argument("--enable-process-execution", action="store_true")
    parser.add_argument("--transport", choices=("simulated", "real-subprocess"), default="simulated")
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    parser.add_argument("--dispatch-dir", default="/tmp/opscat-supervised-worker-execution-dispatch")
    parser.add_argument("--state-path", default="/tmp/opscat-supervised-worker-execution-state.json")
    parser.add_argument("--artifact-dir", default="/tmp/opscat-supervised-worker-execution-artifacts")
    parser.add_argument("--output-json", default="/tmp/opscat-supervised-worker-execution-harness-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-supervised-worker-execution-harness-latest.md")
    args = parser.parse_args()

    transport = RealSubprocessSupervisedTransport() if args.transport == "real-subprocess" else SimulatedSupervisedProcessTransport()
    report = run_supervised_worker_execution_harness_fixture(
        args.manifest,
        completed=_completed_values(args.completed),
        max_tickets=args.max_tickets,
        max_parallel=args.max_parallel,
        dispatch_dir=args.dispatch_dir,
        state_path=args.state_path,
        artifact_dir=args.artifact_dir,
        enable_process_execution=args.enable_process_execution,
        transport=transport,
        timeout_seconds=args.timeout_seconds,
    )
    payload = report.to_dict()
    write_supervised_worker_execution_harness_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    summary = payload["summary"]
    print(
        "OpsCat supervised-worker-execution-harness "
        f"eligible={summary['eligible_command_count']} started={summary['started_run_count']} "
        f"succeeded={summary['succeeded_run_count']} failed={summary['failed_run_count']} retry={summary['retry_queue_count']}"
    )
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
