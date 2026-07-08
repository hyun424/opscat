#!/usr/bin/env python3
"""Run P74 real subprocess execution dry-run gate."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.real_subprocess_execution_dry_run_gate import (  # noqa: E402
    StaticGitWorktreeStatusProvider,
    run_real_subprocess_execution_dry_run_gate_fixture,
    write_real_subprocess_execution_dry_run_gate_outputs,
)


def _completed_values(values: list[str]) -> set[str]:
    completed: set[str] = set()
    for value in values:
        completed.update(item.strip() for item in value.split(",") if item.strip())
    return completed


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P74 real subprocess execution dry-run gate")
    parser.add_argument("--manifest", default="evals/planning/p66_autonomous_day_loop_backlog.json")
    parser.add_argument("--completed", action="append", default=[])
    parser.add_argument("--max-tickets", type=int, default=3)
    parser.add_argument("--max-parallel", type=int, default=2)
    parser.add_argument("--max-processes", type=int, default=2)
    parser.add_argument("--enable-real-subprocess", action="store_true")
    parser.add_argument("--git-status", choices=("clean", "dirty"), default="clean")
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    parser.add_argument("--dispatch-dir", default="/tmp/opscat-real-subprocess-dry-run-dispatch")
    parser.add_argument("--state-path", default="/tmp/opscat-real-subprocess-dry-run-state.json")
    parser.add_argument("--artifact-dir", default="/tmp/opscat-real-subprocess-dry-run-artifacts")
    parser.add_argument("--output-json", default="/tmp/opscat-real-subprocess-dry-run-gate-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-real-subprocess-dry-run-gate-latest.md")
    args = parser.parse_args()

    git_status_provider = StaticGitWorktreeStatusProvider(
        clean=args.git_status == "clean",
        entries=() if args.git_status == "clean" else ("M app/services/example.py",),
    )
    report = run_real_subprocess_execution_dry_run_gate_fixture(
        args.manifest,
        completed=_completed_values(args.completed),
        max_tickets=args.max_tickets,
        max_parallel=args.max_parallel,
        max_processes=args.max_processes,
        dispatch_dir=args.dispatch_dir,
        state_path=args.state_path,
        artifact_dir=args.artifact_dir,
        enable_real_subprocess=args.enable_real_subprocess,
        timeout_seconds=args.timeout_seconds,
        git_status_provider=git_status_provider,
    )
    payload = report.to_dict()
    write_real_subprocess_execution_dry_run_gate_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    summary = payload["summary"]
    print(
        "OpsCat real-subprocess-dry-run-gate "
        f"validated={summary['validated_command_count']} ready={summary['dry_run_ready_count']} "
        f"blocked={summary['dirty_git_block_count'] + summary['enablement_blocked_count'] + summary['command_gate_blocked_count']} "
        f"actual_spawns={summary['actual_spawn_count']}"
    )
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
