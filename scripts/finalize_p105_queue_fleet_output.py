#!/usr/bin/env python3
"""Finalize an existing P105 queue fleet run without replaying RabbitMQ."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from run_p105_queue_fleet_harness import finalize_existing_output


def main() -> int:
    parser = argparse.ArgumentParser(description="Bind a completed queue fleet run to its closed artifact contract.")
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    manifest = finalize_existing_output(args.output_dir)
    print(
        json.dumps(
            {
                "manifest_path": str(args.output_dir / "p105-queue-fleet-harness-manifest.json"),
                "source_key": manifest["source_key"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
