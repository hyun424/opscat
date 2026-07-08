#!/usr/bin/env python3
"""Run OpsCat P31 end-to-end operator replacement drill."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.operator_replacement_drill import (  # noqa: E402
    run_operator_replacement_drill_fixture,
    write_operator_replacement_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat end-to-end operator replacement drill")
    parser.add_argument("--scenarios", default="evals/operator_replacement/p31_scenarios.json")
    parser.add_argument("--output-json", default="")
    parser.add_argument("--output-md", default="")
    args = parser.parse_args()

    report = run_operator_replacement_drill_fixture(args.scenarios)
    payload = report.to_dict()
    write_operator_replacement_outputs(
        payload,
        output_json=args.output_json or None,
        output_md=args.output_md or None,
    )
    score = payload["score"]
    print(
        f"OpsCat operator-replacement scenarios={payload['summary']['scenario_count']} "
        f"score={score['operator_replacement_score']} "
        f"detection={score['detection_success_rate']} "
        f"citation={score['evidence_citation_rate']} "
        f"simulation={score['simulation_coverage']} "
        f"unsafe_auto={score['unsafe_auto_action_count']} "
        "remediation_execution_enabled=False"
    )
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
