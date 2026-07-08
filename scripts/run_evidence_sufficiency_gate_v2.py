#!/usr/bin/env python3
"""Run P76 evidence sufficiency gate v2."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.evidence_sufficiency_gate_v2 import (  # noqa: E402
    build_evidence_sufficiency_gate_v2_report,
    write_evidence_sufficiency_gate_v2_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P76 evidence sufficiency gate v2 report")
    parser.add_argument("--cases", default="evals/investigator/p45_judgment_cases.json")
    parser.add_argument("--output-json", default="/tmp/opscat-evidence-sufficiency-gate-v2-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-evidence-sufficiency-gate-v2-latest.md")
    args = parser.parse_args()

    report = build_evidence_sufficiency_gate_v2_report(args.cases)
    payload = report.to_dict()
    write_evidence_sufficiency_gate_v2_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    summary = payload["summary"]
    print(
        "OpsCat evidence-sufficiency-gate-v2 "
        f"cases={summary['case_count']} sufficient={summary['sufficient_read_only_count']} "
        f"approval_ready={summary['approval_ready_count']} human_required={summary['human_required_count']}"
    )
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
