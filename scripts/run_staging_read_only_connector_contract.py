#!/usr/bin/env python3
"""Run P62 staging read-only connector contract validation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.staging_read_only_connector_contract import (  # noqa: E402
    run_staging_read_only_connector_contract_fixture,
    write_staging_read_only_connector_contract_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P62 staging read-only connector contract")
    parser.add_argument("--manifest", default="evals/staging/p62_staging_connector_contract.json")
    parser.add_argument("--output-json", default="/tmp/opscat-staging-read-only-connector-contract-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-staging-read-only-connector-contract-latest.md")
    args = parser.parse_args()

    report = run_staging_read_only_connector_contract_fixture(args.manifest)
    payload = report.to_dict()
    write_staging_read_only_connector_contract_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    summary = payload["summary"]
    score = payload["score"]
    print(
        "OpsCat staging-read-only-contract "
        f"connectors={summary['connector_count']} ready={summary['ready_count']} blocked={summary['blocked_count']} "
        f"provider_coverage={score['provider_coverage_rate']} live_api_calls={score['live_api_call_count']}"
    )
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
