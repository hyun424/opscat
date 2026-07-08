#!/usr/bin/env python3
"""Run P40 production-readiness milestone bundle."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.production_readiness_milestone import run_production_readiness_milestone_fixture, write_production_readiness_milestone_outputs  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P40 production-readiness milestone")
    parser.add_argument("--sources", default="evals/readiness/p40_sources.json")
    parser.add_argument("--output-json", default="/tmp/opscat-production-readiness-milestone-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-production-readiness-milestone-latest.md")
    args = parser.parse_args()

    report = run_production_readiness_milestone_fixture(args.sources)
    payload = report.to_dict()
    write_production_readiness_milestone_outputs(payload, output_json=Path(args.output_json), output_md=Path(args.output_md))
    print(f"Wrote {args.output_md}")
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
