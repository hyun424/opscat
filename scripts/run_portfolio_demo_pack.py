#!/usr/bin/env python3
"""Run P93 portfolio demo pack generation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.portfolio_demo_pack import build_portfolio_demo_pack, write_portfolio_demo_pack_outputs  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P93 portfolio demo pack")
    parser.add_argument("--input", default="evals/actions/p93_portfolio_demo_pack.json")
    parser.add_argument("--output-json", default="/tmp/opscat-portfolio-demo-pack-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-portfolio-demo-pack-latest.md")
    args = parser.parse_args()

    payload = build_portfolio_demo_pack(args.input)
    write_portfolio_demo_pack_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    summary = payload["summary"]
    print(
        "OpsCat portfolio-demo-pack "
        "walkthrough_steps>=8 proof_points>=6 commands>=3 "
        f"executions={summary['executions']}"
    )
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
