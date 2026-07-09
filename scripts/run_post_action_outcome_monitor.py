#!/usr/bin/env python3
"""Run P83 post-action outcome monitor evaluation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.post_action_outcome_monitor import (  # noqa: E402
    evaluate_post_action_outcome_fixture,
    write_post_action_outcome_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P83 post-action outcome monitor evaluation")
    parser.add_argument("--cases", default="evals/actions/p83_post_action_outcome_monitor.json")
    parser.add_argument("--output-json", default="/tmp/opscat-post-action-outcome-monitor-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-post-action-outcome-monitor-latest.md")
    args = parser.parse_args()

    report = evaluate_post_action_outcome_fixture(args.cases)
    payload = report.to_dict()
    write_post_action_outcome_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    summary = payload["summary"]
    print(
        "OpsCat post-action-outcome-monitor "
        f"scenarios={summary['scenario_count']} resolved={summary['resolved_count']} "
        f"improving={summary['improving_keep_watching_count']} unchanged={summary['unchanged_investigate_count']} "
        f"worsened={summary['worsened_rollback_or_escalate_count']} inconclusive={summary['inconclusive_need_more_evidence_count']} "
        f"blocked={summary['blocked_unsafe_to_continue_count']} executions={summary['action_execution_count']}"
    )
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
