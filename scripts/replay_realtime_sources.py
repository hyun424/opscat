#!/usr/bin/env python3
"""Replay local log/metric sources through P18A realtime source reader."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.realtime_source_reader import replay_sources_to_snapshots  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay local source-native logs/metrics into OpsCat evidence snapshots")
    parser.add_argument("--log-file", default=None)
    parser.add_argument("--metric-csv", default=None)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-md", required=True)
    args = parser.parse_args()
    if not args.log_file and not args.metric_csv:
        parser.error("at least one of --log-file or --metric-csv is required")
    result = replay_sources_to_snapshots(log_file=args.log_file, metric_csv=args.metric_csv, output_json=args.output_json, output_md=args.output_md)
    print(json.dumps({"snapshot_count": result["snapshot_count"], "trigger_count": result["trigger_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
