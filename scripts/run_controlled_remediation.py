#!/usr/bin/env python3
"""Run OpsCat P30 controlled auto-remediation simulation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.controlled_remediation import run_controlled_remediation_fixture, write_controlled_remediation_outputs  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat controlled auto-remediation simulation")
    parser.add_argument("--drills", default="evals/remediation/p30_drills.json")
    parser.add_argument("--output-json", default="")
    parser.add_argument("--output-md", default="")
    args = parser.parse_args()

    report = run_controlled_remediation_fixture(args.drills)
    payload = report.to_dict()
    write_controlled_remediation_outputs(payload, output_json=args.output_json or None, output_md=args.output_md or None)
    print(
        f"OpsCat controlled-remediation drills={payload['summary']['drill_count']} actions={payload['summary']['action_count']} "
        f"auto={payload['summary']['auto_allowed_count']} approval={payload['summary']['approval_required_count']} blocked={payload['summary']['blocked_count']} "
        f"unsafe_auto={payload['score']['unsafe_auto_action_count']} remediation_execution_enabled=False"
    )
    return 0 if payload["score"]["unsafe_auto_action_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
