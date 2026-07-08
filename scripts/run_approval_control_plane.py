#!/usr/bin/env python3
"""Run P36 approval control plane fixture."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.approval_control_plane import run_approval_control_plane_fixture, write_approval_control_plane_outputs  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P36 approval control plane fixture")
    parser.add_argument("--fixture", default="evals/approval/p36_profiles.json")
    parser.add_argument("--output-json", default="/tmp/opscat-approval-control-plane-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-approval-control-plane-latest.md")
    args = parser.parse_args()

    report = run_approval_control_plane_fixture(args.fixture)
    payload = report.to_dict()
    write_approval_control_plane_outputs(payload, output_json=Path(args.output_json), output_md=Path(args.output_md))
    print(f"Wrote {args.output_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
