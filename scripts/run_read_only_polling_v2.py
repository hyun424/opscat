#!/usr/bin/env python3
"""Run OpsCat P34 read-only polling runtime v2."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.read_only_polling_v2 import run_read_only_polling_v2_fixture, write_read_only_polling_v2_outputs  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat read-only polling runtime v2")
    parser.add_argument("--jobs", default="evals/polling/v2/p34_polling_jobs.json")
    parser.add_argument("--dry-run-manifest", default="evals/connectors/dry_run/p33_connectors.json")
    parser.add_argument("--output-json", default="")
    parser.add_argument("--output-md", default="")
    args = parser.parse_args()

    report = run_read_only_polling_v2_fixture(args.jobs, args.dry_run_manifest)
    payload = report.to_dict()
    write_read_only_polling_v2_outputs(payload, output_json=args.output_json or None, output_md=args.output_md or None)
    summary = payload["summary"]
    score = payload["score"]
    print(
        f"OpsCat polling-v2 jobs={summary['job_count']} polled={summary['polled_count']} "
        f"skipped={summary['skipped_count']} blocked={summary['blocked_count']} windows={summary['trend_window_count']} "
        f"poll_success={score['poll_success_rate']} live_api_calls={score['live_api_call_count']}"
    )
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
