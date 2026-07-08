#!/usr/bin/env python3
"""Run P73 bounded long-run autonomous loop controller."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.long_run_loop_controller import (  # noqa: E402
    RealSubprocessSupervisedTransport,
    SimulatedSupervisedProcessTransport,
    run_long_run_loop_controller_fixture,
    write_long_run_loop_controller_outputs,
)


def _completed_values(values: list[str]) -> set[str]:
    completed: set[str] = set()
    for value in values:
        completed.update(item.strip() for item in value.split(",") if item.strip())
    return completed


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P73 bounded long-run loop controller")
    parser.add_argument("--manifest", default="evals/planning/p66_autonomous_day_loop_backlog.json")
    parser.add_argument("--completed", action="append", default=[])
    parser.add_argument("--max-windows", type=int, default=2)
    parser.add_argument("--p72-cycles-per-window", type=int, default=2)
    parser.add_argument("--max-tickets-per-cycle", type=int, default=3)
    parser.add_argument("--max-parallel", type=int, default=2)
    parser.add_argument("--duration-seconds", type=int, default=10 * 60 * 60)
    parser.add_argument("--sleep-seconds", type=int, default=60)
    parser.add_argument("--simulated-window-seconds", type=int, default=20 * 60)
    parser.add_argument("--enable-process-execution", action="store_true")
    parser.add_argument("--transport", choices=("simulated", "real-subprocess"), default="simulated")
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    parser.add_argument("--dispatch-dir", default="/tmp/opscat-long-run-loop-dispatch")
    parser.add_argument("--state-path", default="/tmp/opscat-long-run-loop-state.json")
    parser.add_argument("--artifact-dir", default="/tmp/opscat-long-run-loop-artifacts")
    parser.add_argument("--output-json", default="/tmp/opscat-long-run-loop-controller-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-long-run-loop-controller-latest.md")
    args = parser.parse_args()

    transport = RealSubprocessSupervisedTransport() if args.transport == "real-subprocess" else SimulatedSupervisedProcessTransport()
    report = run_long_run_loop_controller_fixture(
        args.manifest,
        completed=_completed_values(args.completed),
        max_windows=args.max_windows,
        p72_cycles_per_window=args.p72_cycles_per_window,
        max_tickets_per_cycle=args.max_tickets_per_cycle,
        max_parallel=args.max_parallel,
        duration_seconds=args.duration_seconds,
        sleep_seconds=args.sleep_seconds,
        simulated_window_seconds=args.simulated_window_seconds,
        dispatch_dir=args.dispatch_dir,
        state_path=args.state_path,
        artifact_dir=args.artifact_dir,
        enable_process_execution=args.enable_process_execution,
        transport=transport,
        timeout_seconds=args.timeout_seconds,
    )
    payload = report.to_dict()
    write_long_run_loop_controller_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    summary = payload["summary"]
    print(
        "OpsCat long-run-loop-controller "
        f"windows={summary['window_count']} completed={summary['completed_ticket_count']} "
        f"retry={summary['retry_queue_count']} elapsed={summary['elapsed_seconds']} stop={summary['stop_reason']}"
    )
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
