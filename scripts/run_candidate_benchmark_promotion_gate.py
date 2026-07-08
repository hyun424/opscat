#!/usr/bin/env python3
"""Run P55 candidate benchmark promotion gate report."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.candidate_benchmark_promotion_gate import (  # noqa: E402
    build_candidate_benchmark_promotion_gate_report,
    write_candidate_benchmark_promotion_gate_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P55 candidate benchmark promotion gate")
    parser.add_argument("--cases", default="evals/investigator/p51_operator_judgment_benchmark_v2_cases.json")
    parser.add_argument("--output-json", default="/tmp/opscat-candidate-benchmark-promotion-gate-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-candidate-benchmark-promotion-gate-latest.md")
    args = parser.parse_args()
    report = build_candidate_benchmark_promotion_gate_report(args.cases)
    payload = report.to_dict()
    write_candidate_benchmark_promotion_gate_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    print(f"Wrote {args.output_md}")
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
