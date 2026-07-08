#!/usr/bin/env python3
"""Run OpsCat P33 live connector dry-run harness."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.live_connector_dry_run import run_live_connector_dry_run_fixture, write_live_connector_dry_run_outputs  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat live connector dry-run harness")
    parser.add_argument("--manifest", default="evals/connectors/dry_run/p33_connectors.json")
    parser.add_argument("--output-json", default="")
    parser.add_argument("--output-md", default="")
    args = parser.parse_args()

    report = run_live_connector_dry_run_fixture(args.manifest)
    payload = report.to_dict()
    write_live_connector_dry_run_outputs(payload, output_json=args.output_json or None, output_md=args.output_md or None)
    score = payload["score"]
    summary = payload["summary"]
    print(
        f"OpsCat connector-dry-run connectors={summary['connector_count']} ready={summary['ready_count']} "
        f"blocked={summary['blocked_count']} health={score['connector_health_score']} live_api_calls={score['live_api_call_count']}"
    )
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
