#!/usr/bin/env python3
"""Run P77 recovery proof engine."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.recovery_proof_engine import (  # noqa: E402
    build_recovery_proof_engine_report,
    write_recovery_proof_engine_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P77 recovery proof engine report")
    parser.add_argument("--cases", default="evals/investigator/p49_remediation_verification_cases.json")
    parser.add_argument("--output-json", default="/tmp/opscat-recovery-proof-engine-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-recovery-proof-engine-latest.md")
    args = parser.parse_args()

    report = build_recovery_proof_engine_report(args.cases)
    payload = report.to_dict()
    write_recovery_proof_engine_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    summary = payload["summary"]
    print(
        "OpsCat recovery-proof-engine "
        f"cases={summary['case_count']} proven={summary['recovery_proven_count']} "
        f"not_proven={summary['recovery_not_proven_count']} escalations={summary['escalation_required_count']}"
    )
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
