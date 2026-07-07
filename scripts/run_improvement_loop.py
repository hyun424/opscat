#!/usr/bin/env python3
"""Run OpsCat P19 operator judgment improvement loop."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.operator_improvement_loop import (  # noqa: E402
    build_improvement_plan,
    load_model_quality_report,
    render_improvement_plan_markdown,
    write_improvement_outputs,
    write_regression_pack,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat operator judgment improvement loop")
    parser.add_argument("--input-json", required=True, help="P18B model-quality JSON report")
    parser.add_argument("--output-json", default="")
    parser.add_argument("--output-md", default="")
    parser.add_argument("--regression-pack", default="")
    args = parser.parse_args()

    report = load_model_quality_report(args.input_json)
    plan = build_improvement_plan(report, regression_pack_path=args.regression_pack or None)
    if args.regression_pack:
        write_regression_pack(plan, args.regression_pack)
    write_improvement_outputs(plan, output_json=args.output_json or None, output_md=args.output_md or None)
    print(
        f"OpsCat improvement loop provider={plan.provider} model={plan.model} "
        f"candidates={len(plan.top_candidates)} recommendations={len(plan.recommendations)} action_execution_enabled=False"
    )
    if args.output_md:
        print(f"wrote markdown report to {args.output_md}", file=sys.stderr)
    else:
        print(render_improvement_plan_markdown(plan), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
