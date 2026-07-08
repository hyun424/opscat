#!/usr/bin/env python3
"""Run OpsCat P27 connector readiness evaluation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.connector_readiness import evaluate_connector_readiness_fixture, write_connector_readiness_outputs  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat read-only connector readiness checks")
    parser.add_argument("--manifests", default="evals/connectors/readiness/read_only_sources.json")
    parser.add_argument("--output-json", default="")
    parser.add_argument("--output-md", default="")
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()

    report = evaluate_connector_readiness_fixture(args.manifests)
    payload = report.to_dict()
    write_connector_readiness_outputs(payload, output_json=args.output_json or None, output_md=args.output_md or None)
    print(
        f"OpsCat connector-readiness sources={payload['summary']['source_count']} ready={payload['summary']['ready_count']} "
        f"degraded={payload['summary']['degraded_count']} blocked={payload['summary']['blocked_count']} "
        f"live_writes_enabled=False remediation_execution_enabled=False"
    )
    return 2 if args.fail_on_blocked and payload["summary"]["blocked_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
