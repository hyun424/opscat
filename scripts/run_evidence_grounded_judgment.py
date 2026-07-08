#!/usr/bin/env python3
"""Run P45 evidence-grounded judgment contract report."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.evidence_grounded_judgment import build_evidence_grounded_judgment_report, write_evidence_grounded_judgment_outputs  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P45 evidence-grounded judgment contract report")
    parser.add_argument("--cases", default="evals/investigator/p45_judgment_cases.json")
    parser.add_argument("--output-json", default="/tmp/opscat-evidence-grounded-judgment-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-evidence-grounded-judgment-latest.md")
    args = parser.parse_args()
    report = build_evidence_grounded_judgment_report(args.cases)
    payload = report.to_dict()
    write_evidence_grounded_judgment_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    print(f"Wrote {args.output_md}")
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
