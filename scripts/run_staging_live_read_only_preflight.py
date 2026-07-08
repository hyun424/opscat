#!/usr/bin/env python3
"""Run P63 staging live read-only preflight."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.staging_live_read_only_preflight import (  # noqa: E402
    MockStagingReadOnlyTransport,
    run_staging_live_read_only_preflight_fixture,
    write_staging_live_read_only_preflight_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P63 staging live read-only preflight")
    parser.add_argument("--manifest", default="evals/staging/p63_staging_live_preflight.json")
    parser.add_argument("--output-json", default="/tmp/opscat-staging-live-read-only-preflight-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-staging-live-read-only-preflight-latest.md")
    parser.add_argument("--live-staging", action="store_true", help="enable live staging preflight gates")
    parser.add_argument("--manual-approval", action="store_true", help="assert manual approval was granted for live staging preflight")
    parser.add_argument("--mock-transport", action="store_true", help="use mock transport for live-path validation without real network")
    args = parser.parse_args()

    transport = MockStagingReadOnlyTransport() if args.mock_transport else None
    report = run_staging_live_read_only_preflight_fixture(args.manifest, live_staging=args.live_staging, manual_approval=args.manual_approval, transport=transport)
    payload = report.to_dict()
    write_staging_live_read_only_preflight_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    summary = payload["summary"]
    score = payload["score"]
    print(
        "OpsCat staging-live-read-only-preflight "
        f"checks={summary['check_count']} eligible={summary['eligible_check_count']} attempted={summary['attempted_check_count']} "
        f"live_api_calls={score['live_api_call_count']}"
    )
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
