#!/usr/bin/env python3
"""Run OpsCat P28 read-only polling runtime."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.read_only_polling_runtime import run_polling_fixture, write_polling_runtime_outputs  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat read-only fixture polling runtime")
    parser.add_argument("--jobs", default="evals/polling/jobs/p28_polling_jobs.json")
    parser.add_argument("--readiness", default="evals/connectors/readiness/read_only_sources.json")
    parser.add_argument("--ticks", type=int, default=1)
    parser.add_argument("--output-json", default="")
    parser.add_argument("--output-md", default="")
    args = parser.parse_args()

    report = run_polling_fixture(args.jobs, args.readiness, ticks=args.ticks)
    payload = report.to_dict()
    write_polling_runtime_outputs(payload, output_json=args.output_json or None, output_md=args.output_md or None)
    print(
        f"OpsCat read-only-polling jobs={payload['summary']['job_count']} polled={payload['summary']['polled_count']} "
        f"skipped={payload['summary']['skipped_count']} blocked={payload['summary']['blocked_count']} "
        f"trend_windows={payload['summary']['trend_window_count']} live_api_calls_enabled=False remediation_execution_enabled=False"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
