#!/usr/bin/env python3
"""Run P50 night operator drill v2 report."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.night_operator_drill_v2 import build_night_operator_drill_v2_report, write_night_operator_drill_v2_outputs  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P50 night operator drill v2 report")
    parser.add_argument("--drills", default="evals/investigator/p50_night_operator_cases.json")
    parser.add_argument("--output-json", default="/tmp/opscat-night-operator-drill-v2-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-night-operator-drill-v2-latest.md")
    args = parser.parse_args()
    report = build_night_operator_drill_v2_report(args.drills)
    payload = report.to_dict()
    write_night_operator_drill_v2_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    print(f"Wrote {args.output_md}")
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
