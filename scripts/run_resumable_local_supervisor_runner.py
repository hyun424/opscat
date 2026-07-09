#!/usr/bin/env python3
"""Run P86 resumable local supervisor runner evaluation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.resumable_local_supervisor_runner import (  # noqa: E402
    evaluate_resumable_local_supervisor_fixture,
    write_resumable_local_supervisor_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P86 resumable local supervisor runner evaluation")
    parser.add_argument("--cases", default="evals/actions/p86_resumable_local_supervisor_runner.json")
    parser.add_argument("--output-json", default="/tmp/opscat-resumable-local-supervisor-runner-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-resumable-local-supervisor-runner-latest.md")
    args = parser.parse_args()

    report = evaluate_resumable_local_supervisor_fixture(args.cases)
    payload = report.to_dict()
    write_resumable_local_supervisor_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    summary = payload["summary"]
    print(
        "OpsCat resumable-local-supervisor-runner "
        f"scenarios={summary['scenario_count']} resumed={summary['resumed_count']} "
        f"completed_all={summary['completed_all_count']} max_iteration={summary['max_iteration_count']} "
        f"needs_human={summary['needs_human_count']} failed_guardrail={summary['failed_guardrail_count']} "
        f"executions={summary['action_execution_count']}"
    )
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
