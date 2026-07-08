#!/usr/bin/env python3
"""Prepare P42 external dataset acquisition report."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.external_dataset_acquisition import build_external_dataset_acquisition_report, write_external_dataset_acquisition_outputs  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare OpsCat P42 external dataset acquisition and holdout evaluation report")
    parser.add_argument("--manifest", default="evals/real_datasets/external/p42_manifest.json")
    parser.add_argument("--output-json", default="/tmp/opscat-external-dataset-acquisition-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-external-dataset-acquisition-latest.md")
    parser.add_argument("--allow-network", action="store_true", help="Opt in to external dataset sample downloads")
    parser.add_argument("--max-bytes", type=int, default=5_000_000)
    args = parser.parse_args()

    report = build_external_dataset_acquisition_report(args.manifest, allow_network=args.allow_network, max_bytes=args.max_bytes)
    payload = report.to_dict()
    write_external_dataset_acquisition_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    print(f"Wrote {args.output_md}")
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
