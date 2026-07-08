#!/usr/bin/env python3
"""Run P64 audited staging credential + transport gate."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.audited_staging_transport_gate import (  # noqa: E402
    MockAuditedStagingTransport,
    run_audited_staging_transport_gate_fixture,
    write_audited_staging_transport_gate_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P64 audited staging transport gate")
    parser.add_argument("--manifest", default="evals/staging/p64_audited_credential_transport_gate.json")
    parser.add_argument("--output-json", default="/tmp/opscat-audited-staging-transport-gate-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-audited-staging-transport-gate-latest.md")
    parser.add_argument("--live-staging", action="store_true", help="enable audited live staging transport gate")
    parser.add_argument("--manual-approval", action="store_true", help="assert manual approval ID is present for live staging transport")
    parser.add_argument("--mock-transport", action="store_true", help="use mock transport for live-path validation without real network")
    args = parser.parse_args()

    transport = MockAuditedStagingTransport() if args.mock_transport else None
    report = run_audited_staging_transport_gate_fixture(args.manifest, live_staging=args.live_staging, manual_approval=args.manual_approval, transport=transport)
    payload = report.to_dict()
    write_audited_staging_transport_gate_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    summary = payload["summary"]
    score = payload["score"]
    print(
        "OpsCat audited-staging-transport-gate "
        f"requests={summary['request_count']} approved={summary['approved_request_count']} attempted={summary['attempted_request_count']} "
        f"transport_calls={score['transport_call_count']} live_api_calls={score['live_api_call_count']}"
    )
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
