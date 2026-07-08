#!/usr/bin/env python3
"""Run P80 approval automation policy lab."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.approval_automation_policy_lab import (  # noqa: E402
    evaluate_approval_automation_fixture,
    write_approval_automation_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P80 approval automation policy lab")
    parser.add_argument("--cases", default="evals/policy/p80_approval_automation_policy_lab.json")
    parser.add_argument("--output-json", default="/tmp/opscat-approval-automation-policy-lab-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-approval-automation-policy-lab-latest.md")
    args = parser.parse_args()

    report = evaluate_approval_automation_fixture(args.cases)
    payload = report.to_dict()
    write_approval_automation_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    summary = payload["summary"]
    print(
        "OpsCat approval-automation-policy-lab "
        f"scenarios={summary['scenario_count']} auto={summary['auto_approve_count']} "
        f"human={summary['require_human_count']} mock_only={summary['mock_only_count']} "
        f"blocked={summary['blocked_count']} unsafe_auto={summary['unsafe_auto_approval_count']} "
        f"executions={summary['action_execution_count']}"
    )
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
