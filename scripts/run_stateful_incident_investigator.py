#!/usr/bin/env python3
"""Run the P100 stateful multi-step incident investigator benchmark."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.operational_scenario_catalog import (  # noqa: E402
    build_comprehensive_operational_catalog,
)
from app.services.stateful_incident_investigator import (  # noqa: E402
    MultiStepCausalBenchmark,
    write_stateful_benchmark_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-cases", type=int, default=None)
    parser.add_argument("--seeds", default="11", help="comma-separated deterministic integer seeds")
    parser.add_argument("--sample-size", type=int, default=20)
    parser.add_argument("--max-steps", type=int, default=3)
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args()

    catalog = build_comprehensive_operational_catalog()
    if args.max_cases is not None and args.max_cases < 1:
        parser.error("--max-cases must be positive")
    selected = catalog[: args.max_cases] if args.max_cases is not None else catalog
    try:
        seeds = tuple(int(value.strip()) for value in args.seeds.split(",") if value.strip())
    except ValueError as exc:
        parser.error(f"--seeds must contain integers: {exc}")
    if not seeds:
        parser.error("--seeds must contain at least one integer")

    payload = (
        MultiStepCausalBenchmark(
            sample_size=args.sample_size,
            max_steps=args.max_steps,
        )
        .run(cases=selected, seeds=seeds)
        .to_dict()
    )
    write_stateful_benchmark_outputs(
        payload,
        output_json=args.output_json,
        output_md=args.output_md,
    )
    print(json.dumps({"summary": payload["summary"], "safety": payload["safety"]}, sort_keys=True))
    return 0 if payload["summary"]["execution_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
