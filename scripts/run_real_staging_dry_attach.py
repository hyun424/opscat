#!/usr/bin/env python3
"""Run P65 real staging read-only dry attach."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.real_staging_dry_attach import (  # noqa: E402
    run_real_staging_dry_attach_fixture,
    write_real_staging_dry_attach_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P65 real staging read-only dry attach")
    parser.add_argument("--manifest", default="evals/staging/p65_real_staging_dry_attach.json")
    parser.add_argument("--output-json", default="/tmp/opscat-real-staging-dry-attach-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-real-staging-dry-attach-latest.md")
    args = parser.parse_args()

    report = run_real_staging_dry_attach_fixture(args.manifest)
    payload = report.to_dict()
    write_real_staging_dry_attach_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    summary = payload["summary"]
    score = payload["score"]
    print(
        "OpsCat real-staging-dry-attach "
        f"attachments={summary['attachment_count']} attach_ready={summary['attach_ready_count']} "
        f"blocked={summary['blocked_count']} network_calls={score['network_call_count']}"
    )
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
