#!/usr/bin/env python3
"""Run P59 hybrid commander comparator report."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.hybrid_commander_comparator import (  # noqa: E402
    build_hybrid_commander_comparator_report,
    write_hybrid_commander_comparator_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P59 hybrid commander comparator")
    parser.add_argument("--cases", default="evals/investigator/p51_operator_judgment_benchmark_v2_cases.json")
    parser.add_argument("--manifest", default="evals/real_datasets/external/p44_benchmark_matrix_manifest.json")
    parser.add_argument("--judgment-cases", default="evals/judgment/seed/cases.json")
    parser.add_argument("--max-cases", type=int, default=4)
    parser.add_argument("--output-json", default="/tmp/opscat-hybrid-commander-comparator-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-hybrid-commander-comparator-latest.md")
    args = parser.parse_args()
    report = build_hybrid_commander_comparator_report(args.cases, args.manifest, args.judgment_cases, max_cases=args.max_cases)
    payload = report.to_dict()
    write_hybrid_commander_comparator_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    print(f"Wrote {args.output_md}")
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
