#!/usr/bin/env python3
"""Run P39 runbook learning loop."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.runbook_learning_loop import run_runbook_learning_loop_fixture, write_runbook_learning_loop_outputs  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P39 runbook learning loop")
    parser.add_argument("--sources", default="evals/learning/p39_sources.json")
    parser.add_argument("--output-json", default="/tmp/opscat-runbook-learning-loop-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-runbook-learning-loop-latest.md")
    args = parser.parse_args()

    report = run_runbook_learning_loop_fixture(args.sources)
    payload = report.to_dict()
    write_runbook_learning_loop_outputs(payload, output_json=Path(args.output_json), output_md=Path(args.output_md))
    print(f"Wrote {args.output_md}")
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
