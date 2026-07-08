#!/usr/bin/env python3
"""Run P43 public dataset benchmark scorecard."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.public_dataset_benchmark import build_public_dataset_benchmark_report, write_public_dataset_benchmark_outputs  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P43 public dataset benchmark scorecard")
    parser.add_argument("--manifest", default="evals/real_datasets/external/p43_public_benchmark_manifest.json")
    parser.add_argument("--artifact-root", default=None)
    parser.add_argument("--materialized-root", default=None)
    parser.add_argument("--output-json", default="/tmp/opscat-public-dataset-benchmark-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-public-dataset-benchmark-latest.md")
    parser.add_argument("--allow-network", action="store_true", help="Opt in to public dataset sample downloads")
    parser.add_argument("--max-bytes", type=int, default=5_000_000)
    args = parser.parse_args()

    report = build_public_dataset_benchmark_report(
        args.manifest,
        allow_network=args.allow_network,
        artifact_root=args.artifact_root,
        materialized_root=args.materialized_root,
        max_bytes=args.max_bytes,
    )
    payload = report.to_dict()
    write_public_dataset_benchmark_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    print(f"Wrote {args.output_md}")
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
