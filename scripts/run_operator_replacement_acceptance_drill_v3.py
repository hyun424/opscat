#!/usr/bin/env python3
"""Run P92 operator replacement acceptance drill v3."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.operator_replacement_acceptance_drill_v3 import (  # noqa: E402
    evaluate_operator_replacement_acceptance_drill_v3_fixture,
    write_operator_replacement_acceptance_drill_v3_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P92 operator replacement acceptance drill v3")
    parser.add_argument("--cases", default="evals/actions/p92_operator_replacement_acceptance_drill_v3.json")
    parser.add_argument("--output-json", default="/tmp/opscat-operator-replacement-acceptance-drill-v3-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-operator-replacement-acceptance-drill-v3-latest.md")
    args = parser.parse_args()

    report = evaluate_operator_replacement_acceptance_drill_v3_fixture(args.cases)
    payload = report.to_dict()
    write_operator_replacement_acceptance_drill_v3_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    summary = payload["summary"]
    print(
        "OpsCat operator-replacement-acceptance-drill-v3 "
        f"scenarios={summary['scenario_count']} local_demo_ready={summary['local_demo_ready_count']} "
        f"shadow_candidate={summary['shadow_candidate_count']} human_gated={summary['human_gated_count']} "
        f"blocked={summary['blocked_count']} executions={summary['executions']}"
    )
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
