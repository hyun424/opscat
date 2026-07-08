#!/usr/bin/env python3
"""Run OpsCat P26 telemetry fixture adapters."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.telemetry_adapter import TelemetryAdapterRegistry, build_telemetry_report, write_telemetry_outputs  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat read-only telemetry fixture adapters")
    parser.add_argument("--source", choices=("prometheus", "datadog", "sentry", "all"), default="all")
    parser.add_argument("--fixture-dir", default="evals/telemetry/fixtures")
    parser.add_argument("--output-json", default="")
    parser.add_argument("--output-md", default="")
    args = parser.parse_args()

    registry = TelemetryAdapterRegistry.default()
    fixture_dir = Path(args.fixture_dir)
    matrix = registry.fixture_matrix()
    sources = tuple(matrix) if args.source == "all" else (args.source,)
    snapshots = [registry.adapt(source, fixture_dir / matrix[source]) for source in sources]
    payload = build_telemetry_report(snapshots)
    write_telemetry_outputs(payload, output_json=args.output_json or None, output_md=args.output_md or None)
    print(
        f"OpsCat telemetry-adapter snapshots={payload['summary']['snapshot_count']} "
        f"series={payload['summary']['series_count']} events={payload['summary']['event_count']} "
        f"trend_windows={payload['summary']['trend_window_count']} live_api_calls_enabled=False action_execution_enabled=False"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
