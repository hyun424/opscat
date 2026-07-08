#!/usr/bin/env python3
"""Run OpsCat P35 incident shadow mode."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.incident_shadow_mode import run_incident_shadow_mode_fixture, write_incident_shadow_mode_outputs  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat incident shadow mode")
    parser.add_argument("--cases", default="evals/shadow/p35_shadow_cases.json")
    parser.add_argument("--output-json", default="")
    parser.add_argument("--output-md", default="")
    args = parser.parse_args()

    report = run_incident_shadow_mode_fixture(args.cases)
    payload = report.to_dict()
    write_incident_shadow_mode_outputs(payload, output_json=args.output_json or None, output_md=args.output_md or None)
    summary = payload["summary"]
    score = payload["score"]
    print(
        f"OpsCat shadow-mode cases={summary['case_count']} route_match={score['expected_route_match_rate']} "
        f"evidence={score['evidence_link_rate']} executions={score['execution_count']} unsafe={score['unsafe_shadow_action_count']}"
    )
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
