#!/usr/bin/env python3
"""Run P84 outcome-driven next action planner evaluation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.outcome_driven_next_action_planner import (  # noqa: E402
    evaluate_outcome_driven_next_action_fixture,
    write_outcome_driven_next_action_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P84 outcome-driven next action planner evaluation")
    parser.add_argument("--cases", default="evals/actions/p84_outcome_driven_next_action_planner.json")
    parser.add_argument("--output-json", default="/tmp/opscat-outcome-driven-next-action-planner-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-outcome-driven-next-action-planner-latest.md")
    args = parser.parse_args()

    report = evaluate_outcome_driven_next_action_fixture(args.cases)
    payload = report.to_dict()
    write_outcome_driven_next_action_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    summary = payload["summary"]
    print(
        "OpsCat outcome-driven-next-action-planner "
        f"scenarios={summary['scenario_count']} stop_resolved={summary['stop_resolved_count']} "
        f"keep_watching={summary['keep_watching_count']} gather={summary['gather_more_evidence_count']} "
        f"rollback_review={summary['prepare_rollback_review_count']} blocked={summary['block_unsafe_path_count']} "
        f"executions={summary['action_execution_count']}"
    )
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
