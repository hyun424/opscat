#!/usr/bin/env python3
"""Run P79 action sandbox hardening evaluation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.action_sandbox_hardening import (  # noqa: E402
    evaluate_action_sandbox_fixture,
    write_action_sandbox_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P79 action sandbox hardening evaluation")
    parser.add_argument("--cases", default="evals/actions/p79_action_sandbox_cases.json")
    parser.add_argument("--output-json", default="/tmp/opscat-action-sandbox-hardening-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-action-sandbox-hardening-latest.md")
    args = parser.parse_args()

    report = evaluate_action_sandbox_fixture(args.cases)
    payload = report.to_dict()
    write_action_sandbox_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    summary = payload["summary"]
    print(
        "OpsCat action-sandbox-hardening "
        f"proposals={summary['proposal_count']} allowed={summary['allowed_count']} "
        f"approval={summary['approval_required_count']} mock_only={summary['mock_only_count']} "
        f"blocked={summary['blocked_count']} executions={summary['action_execution_count']}"
    )
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
