#!/usr/bin/env python3
"""Run P41 raw real dataset scored replay."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.raw_real_dataset_replay import run_raw_real_dataset_replay_fixture, write_raw_real_dataset_replay_outputs  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P41 raw real dataset scored replay")
    parser.add_argument("--sources", default="evals/real_datasets/raw/p41_sources.json")
    parser.add_argument("--output-json", default="/tmp/opscat-raw-real-dataset-replay-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-raw-real-dataset-replay-latest.md")
    args = parser.parse_args()

    report = run_raw_real_dataset_replay_fixture(args.sources)
    payload = report.to_dict()
    write_raw_real_dataset_replay_outputs(payload, output_json=Path(args.output_json), output_md=Path(args.output_md))
    print(f"Wrote {args.output_md}")
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
