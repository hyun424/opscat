#!/usr/bin/env python3
"""Run P81 rollback PR draft automation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.rollback_pr_draft_automation import (  # noqa: E402
    evaluate_rollback_pr_draft_fixture,
    write_rollback_pr_draft_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P81 rollback PR draft automation")
    parser.add_argument("--cases", default="evals/policy/p81_rollback_pr_draft_automation.json")
    parser.add_argument("--output-json", default="/tmp/opscat-rollback-pr-draft-automation-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-rollback-pr-draft-automation-latest.md")
    args = parser.parse_args()

    report = evaluate_rollback_pr_draft_fixture(args.cases)
    payload = report.to_dict()
    write_rollback_pr_draft_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    summary = payload["summary"]
    print(
        "OpsCat rollback-pr-draft-automation "
        f"scenarios={summary['scenario_count']} draft_ready={summary['draft_ready_count']} "
        f"human={summary['human_review_required_count']} blocked={summary['blocked_count']} "
        f"rejected={summary['rejected_count']} approvals={summary['required_human_approval_count']} "
        f"executions={summary['action_execution_count']}"
    )
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
