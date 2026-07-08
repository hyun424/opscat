#!/usr/bin/env python3
"""Run P46 investigator loop report."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.investigator_loop import build_investigator_loop_report, write_investigator_loop_outputs  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P46 investigator loop report")
    parser.add_argument("--cases", default="evals/investigator/p46_investigation_cases.json")
    parser.add_argument("--output-json", default="/tmp/opscat-investigator-loop-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-investigator-loop-latest.md")
    args = parser.parse_args()
    report = build_investigator_loop_report(args.cases)
    payload = report.to_dict()
    write_investigator_loop_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    print(f"Wrote {args.output_md}")
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
