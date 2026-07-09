#!/usr/bin/env python3
"""Run P91 readiness gap remediation planner."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.readiness_gap_remediation_planner import (  # noqa: E402
    evaluate_readiness_gap_remediation_planner_fixture,
    write_readiness_gap_remediation_planner_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P91 readiness gap remediation planner")
    parser.add_argument("--cases", default="evals/actions/p91_readiness_gap_remediation_planner.json")
    parser.add_argument("--output-json", default="/tmp/opscat-readiness-gap-remediation-planner-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-readiness-gap-remediation-planner-latest.md")
    args = parser.parse_args()

    report = evaluate_readiness_gap_remediation_planner_fixture(args.cases)
    payload = report.to_dict()
    write_readiness_gap_remediation_planner_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    summary = payload["summary"]
    print(
        "OpsCat readiness-gap-remediation-planner "
        f"scenarios={summary['scenario_count']} blocking_plans={summary['blocking_plans']} "
        f"emergency_items={summary['emergency_items']} human_gated_items={summary['human_gated_items']} "
        f"maturity_items={summary['maturity_items']} executions={summary['executions']}"
    )
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
