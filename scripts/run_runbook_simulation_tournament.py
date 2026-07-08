#!/usr/bin/env python3
"""Run P78 runbook simulation tournament."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.runbook_simulation_tournament import (  # noqa: E402
    run_runbook_simulation_tournament_fixture,
    write_runbook_simulation_tournament_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P78 runbook simulation tournament")
    parser.add_argument("--candidates", default="evals/runbooks/p78_runbook_candidates.json")
    parser.add_argument("--output-json", default="/tmp/opscat-runbook-simulation-tournament-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-runbook-simulation-tournament-latest.md")
    args = parser.parse_args()

    report = run_runbook_simulation_tournament_fixture(args.candidates)
    payload = report.to_dict()
    write_runbook_simulation_tournament_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    summary = payload["summary"]
    print(
        "OpsCat runbook-simulation-tournament "
        f"candidates={summary['candidate_count']} winner={summary['winner_id']} "
        f"unsafe={summary['unsafe_candidate_count']} executions={summary['action_execution_count']}"
    )
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
