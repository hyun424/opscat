#!/usr/bin/env python3
"""Run P90 safe auto-run readiness gate evaluation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.safe_auto_run_readiness_gate import (  # noqa: E402
    evaluate_safe_auto_run_readiness_gate_fixture,
    write_safe_auto_run_readiness_gate_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P90 safe auto-run readiness gate evaluation")
    parser.add_argument("--cases", default="evals/actions/p90_safe_auto_run_readiness_gate.json")
    parser.add_argument("--output-json", default="/tmp/opscat-safe-auto-run-readiness-gate-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-safe-auto-run-readiness-gate-latest.md")
    args = parser.parse_args()

    report = evaluate_safe_auto_run_readiness_gate_fixture(args.cases)
    payload = report.to_dict()
    write_safe_auto_run_readiness_gate_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    summary = payload["summary"]
    print(
        "OpsCat safe-auto-run-readiness-gate "
        f"scenarios={summary['scenario_count']} local_ready={summary['local_ready_count']} "
        f"shadow_ready={summary['shadow_ready_count']} human_gated={summary['human_gated_count']} "
        f"not_ready={summary['not_ready_count']} blocked={summary['blocked_count']} "
        f"executions={summary['executions']}"
    )
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
