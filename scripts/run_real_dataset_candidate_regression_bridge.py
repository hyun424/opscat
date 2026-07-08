#!/usr/bin/env python3
"""Run P57 real dataset candidate regression bridge report."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.real_dataset_candidate_regression_bridge import (  # noqa: E402
    build_real_dataset_candidate_regression_bridge_report,
    write_real_dataset_candidate_regression_bridge_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P57 real dataset candidate regression bridge")
    parser.add_argument("--cases", default="evals/investigator/p51_operator_judgment_benchmark_v2_cases.json")
    parser.add_argument("--manifest", default="evals/real_datasets/external/p44_benchmark_matrix_manifest.json")
    parser.add_argument("--repeat-count", type=int, default=3)
    parser.add_argument("--output-json", default="/tmp/opscat-real-dataset-candidate-regression-bridge-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-real-dataset-candidate-regression-bridge-latest.md")
    args = parser.parse_args()
    report = build_real_dataset_candidate_regression_bridge_report(args.cases, args.manifest, repeat_count=args.repeat_count)
    payload = report.to_dict()
    write_real_dataset_candidate_regression_bridge_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    print(f"Wrote {args.output_md}")
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
