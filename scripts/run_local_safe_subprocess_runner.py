#!/usr/bin/env python3
"""Run P75 local safe subprocess runner."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.local_safe_subprocess_runner import (  # noqa: E402
    ActualLocalSubprocessTransport,
    SimulatedLocalSubprocessTransport,
    StaticGitWorktreeStatusProvider,
    run_local_safe_subprocess_runner_fixture,
    write_local_safe_subprocess_runner_outputs,
)


def _completed_values(values: list[str]) -> set[str]:
    completed: set[str] = set()
    for value in values:
        completed.update(item.strip() for item in value.split(",") if item.strip())
    return completed


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P75 local safe subprocess runner")
    parser.add_argument("--manifest", default="evals/planning/p66_autonomous_day_loop_backlog.json")
    parser.add_argument("--completed", action="append", default=[])
    parser.add_argument("--max-tickets", type=int, default=3)
    parser.add_argument("--max-parallel", type=int, default=2)
    parser.add_argument("--max-processes", type=int, default=2)
    parser.add_argument("--enable-real-subprocess", action="store_true")
    parser.add_argument("--enable-local-subprocess", action="store_true")
    parser.add_argument("--confirm-actual-local-spawn", action="store_true")
    parser.add_argument("--git-status", choices=("clean", "dirty"), default="clean")
    parser.add_argument("--transport", choices=("simulated", "actual-local"), default="simulated")
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    parser.add_argument("--dispatch-dir", default="/tmp/opscat-local-safe-subprocess-dispatch")
    parser.add_argument("--state-path", default="/tmp/opscat-local-safe-subprocess-state.json")
    parser.add_argument("--artifact-dir", default="/tmp/opscat-local-safe-subprocess-artifacts")
    parser.add_argument("--output-json", default="/tmp/opscat-local-safe-subprocess-runner-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-local-safe-subprocess-runner-latest.md")
    args = parser.parse_args()

    transport = ActualLocalSubprocessTransport() if args.transport == "actual-local" else SimulatedLocalSubprocessTransport()
    git_status_provider = StaticGitWorktreeStatusProvider(clean=args.git_status == "clean", entries=() if args.git_status == "clean" else ("M app/services/example.py",))
    report = run_local_safe_subprocess_runner_fixture(
        args.manifest,
        completed=_completed_values(args.completed),
        max_tickets=args.max_tickets,
        max_parallel=args.max_parallel,
        max_processes=args.max_processes,
        dispatch_dir=args.dispatch_dir,
        state_path=args.state_path,
        artifact_dir=args.artifact_dir,
        enable_real_subprocess=args.enable_real_subprocess,
        enable_local_subprocess=args.enable_local_subprocess,
        actual_spawn_confirmed=args.confirm_actual_local_spawn,
        timeout_seconds=args.timeout_seconds,
        git_status_provider=git_status_provider,
        transport=transport,
    )
    payload = report.to_dict()
    write_local_safe_subprocess_runner_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    summary = payload["summary"]
    print(
        "OpsCat local-safe-subprocess-runner "
        f"ready={summary['dry_run_ready_count']} started={summary['started_run_count']} "
        f"succeeded={summary['succeeded_run_count']} failed={summary['failed_run_count']} actual_spawns={summary['actual_spawn_count']}"
    )
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
