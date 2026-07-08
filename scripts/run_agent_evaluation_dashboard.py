#!/usr/bin/env python3
"""Run P38 agent evaluation dashboard."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.agent_evaluation_dashboard import run_agent_evaluation_dashboard_fixture, write_agent_evaluation_dashboard_outputs  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P38 agent evaluation dashboard")
    parser.add_argument("--sources", default="evals/dashboard/p38_sources.json")
    parser.add_argument("--output-json", default="/tmp/opscat-agent-evaluation-dashboard-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-agent-evaluation-dashboard-latest.md")
    args = parser.parse_args()

    report = run_agent_evaluation_dashboard_fixture(args.sources)
    payload = report.to_dict()
    write_agent_evaluation_dashboard_outputs(payload, output_json=Path(args.output_json), output_md=Path(args.output_md))
    print(f"Wrote {args.output_md}")
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
