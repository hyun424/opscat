#!/usr/bin/env python3
"""Run P85 local autonomous supervisor loop evaluation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.local_autonomous_supervisor_loop import (  # noqa: E402
    evaluate_local_autonomous_supervisor_fixture,
    write_local_autonomous_supervisor_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P85 local autonomous supervisor loop evaluation")
    parser.add_argument("--cases", default="evals/actions/p85_local_autonomous_supervisor_loop.json")
    parser.add_argument("--output-json", default="/tmp/opscat-local-autonomous-supervisor-loop-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-local-autonomous-supervisor-loop-latest.md")
    args = parser.parse_args()

    report = evaluate_local_autonomous_supervisor_fixture(args.cases)
    payload = report.to_dict()
    write_local_autonomous_supervisor_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    summary = payload["summary"]
    print(
        "OpsCat local-autonomous-supervisor-loop "
        f"scenarios={summary['scenario_count']} completed_batches={summary['completed_batch_count']} "
        f"needs_human={summary['needs_human_count']} failed_guardrail={summary['failed_guardrail_count']} "
        f"budget_exhausted={summary['budget_exhausted_count']} executions={summary['action_execution_count']}"
    )
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
