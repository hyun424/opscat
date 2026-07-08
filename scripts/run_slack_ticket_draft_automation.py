#!/usr/bin/env python3
"""Run P82 Slack and ticket draft automation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.slack_ticket_draft_automation import (  # noqa: E402
    evaluate_slack_ticket_draft_fixture,
    write_slack_ticket_draft_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P82 Slack and ticket draft automation")
    parser.add_argument("--cases", default="evals/policy/p82_slack_ticket_draft_automation.json")
    parser.add_argument("--output-json", default="/tmp/opscat-slack-ticket-draft-automation-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-slack-ticket-draft-automation-latest.md")
    args = parser.parse_args()

    report = evaluate_slack_ticket_draft_fixture(args.cases)
    payload = report.to_dict()
    write_slack_ticket_draft_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    summary = payload["summary"]
    print(
        "OpsCat slack-ticket-draft-automation "
        f"scenarios={summary['scenario_count']} draft_ready={summary['draft_ready_count']} "
        f"investigation={summary['investigation_only_count']} blocked={summary['blocked_count']} "
        f"rejected={summary['rejected_count']} approvals={summary['required_human_approval_count']} "
        f"messages={summary['message_send_count']} tickets={summary['ticket_creation_count']}"
    )
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
