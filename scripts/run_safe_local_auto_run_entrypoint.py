#!/usr/bin/env python3
"""Run P89 safe local auto-run entrypoint evaluation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.safe_local_auto_run_entrypoint import (  # noqa: E402
    evaluate_safe_local_auto_run_entrypoint_fixture,
    write_safe_local_auto_run_entrypoint_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P89 safe local auto-run entrypoint evaluation")
    parser.add_argument("--cases", default="evals/actions/p89_safe_local_auto_run_entrypoint.json")
    parser.add_argument("--output-json", default="/tmp/opscat-safe-local-auto-run-entrypoint-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-safe-local-auto-run-entrypoint-latest.md")
    parser.add_argument("--dry-run", action="store_true", help="Record operator dry-run intent as CLI metadata only.")
    parser.add_argument("--resume", action="store_true", help="Record operator resume intent as CLI metadata only.")
    args = parser.parse_args()

    report = evaluate_safe_local_auto_run_entrypoint_fixture(args.cases)
    payload = report.to_dict()
    payload["cli"] = {"dry_run_flag": args.dry_run, "resume_flag": args.resume}
    write_safe_local_auto_run_entrypoint_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    summary = payload["summary"]
    print(
        "OpsCat safe-local-auto-run-entrypoint "
        f"scenarios={summary['scenario_count']} dry_run={summary['dry_run_count']} resumed={summary['resumed_count']} "
        f"completed={summary['completed_count']} needs_human={summary['needs_human_count']} "
        f"failed_guardrail={summary['failed_guardrail_count']} max_cycles={summary['max_cycles_count']} "
        f"executions={summary['executions']}"
    )
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
