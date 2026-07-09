#!/usr/bin/env python3
"""Run P94 operator transcript demo generation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.operator_transcript_demo import (  # noqa: E402
    build_operator_transcript_demo,
    write_operator_transcript_demo_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P94 operator transcript demo")
    parser.add_argument("--input", default="evals/actions/p94_operator_transcript_demo.json")
    parser.add_argument("--output-json", default="/tmp/opscat-operator-transcript-demo-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-operator-transcript-demo-latest.md")
    args = parser.parse_args()

    payload = build_operator_transcript_demo(args.input)
    write_operator_transcript_demo_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    summary = payload["summary"]
    print(
        "OpsCat operator-transcript-demo "
        f"scenarios={summary['scenarios']} "
        f"transcript_steps>={summary['transcript_steps']} "
        f"hypotheses>={summary['hypotheses']} "
        f"executions={summary['executions']} "
        f"recovery_proven={summary['recovery_proven']} "
        f"blocked={summary['blocked']} "
        f"human_gated={summary['human_gated']}"
    )
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
