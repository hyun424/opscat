#!/usr/bin/env python3
"""Run P87 supervisor run report artifact evaluation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.supervisor_run_report_artifact import (  # noqa: E402
    evaluate_supervisor_run_report_artifact_fixture,
    write_supervisor_run_report_artifact_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P87 supervisor run report artifact evaluation")
    parser.add_argument("--cases", default="evals/actions/p87_supervisor_run_report_artifact.json")
    parser.add_argument("--output-json", default="/tmp/opscat-supervisor-run-report-artifact-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-supervisor-run-report-artifact-latest.md")
    args = parser.parse_args()

    report = evaluate_supervisor_run_report_artifact_fixture(args.cases)
    payload = report.to_dict()
    write_supervisor_run_report_artifact_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    summary = payload["summary"]
    print(
        "OpsCat supervisor-run-report-artifact "
        f"scenarios={summary['scenario_count']} terminal={summary['terminal_count']} "
        f"resumable={summary['resumable_count']} needs_human={summary['needs_human_count']} "
        f"failed_guardrail={summary['failed_guardrail_count']} executions={summary['action_execution_count']}"
    )
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
