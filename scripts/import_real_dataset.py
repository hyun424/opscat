#!/usr/bin/env python3
"""Convert a local real-dataset-shaped sample into OpsCat judgment cases."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.judgment_dataset import write_judgment_cases  # noqa: E402
from app.services.real_dataset_evaluation import convert_dataset_sample  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Import local real-dataset-shaped samples into OpsCat judgment cases")
    parser.add_argument("--family", required=True, choices=("loghub", "nab", "aiops"))
    parser.add_argument("--input", required=True)
    parser.add_argument("--dataset-name", default=None)
    parser.add_argument("--output-cases", required=True)
    parser.add_argument("--output-quality", required=True)
    args = parser.parse_args()

    result = convert_dataset_sample(args.input, family=args.family, dataset_name=args.dataset_name)
    write_judgment_cases(args.output_cases, result.cases)
    Path(args.output_quality).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output_quality).write_text(json.dumps(result.quality.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {len(result.cases)} case(s) and import quality for {args.family}")
    return 0 if result.quality.unsupported_records == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
