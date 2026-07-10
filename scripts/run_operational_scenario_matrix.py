#!/usr/bin/env python3
"""Run the P99 comprehensive operational failure matrix."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.operational_scenario_catalog import (  # noqa: E402
    build_comprehensive_operational_catalog,
    run_comprehensive_operational_matrix,
    write_operational_matrix_outputs,
)


def _parse_seeds(value: str) -> tuple[int, ...]:
    seeds = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    if not seeds:
        raise argparse.ArgumentTypeError("at least one integer seed is required")
    return seeds


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-cases", type=int, default=20, help="bounded smoke size; ignored by --full-matrix")
    parser.add_argument("--seeds", type=_parse_seeds, default=(11,), help="comma-separated deterministic seeds")
    parser.add_argument("--sample-size", type=int, default=10, help="loopback observations per measurement")
    parser.add_argument("--full-matrix", action="store_true", help="run all 520 cases with seeds 11,29,47")
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    catalog = build_comprehensive_operational_catalog()
    if args.full_matrix:
        selected = catalog
        seeds = (11, 29, 47)
    else:
        if args.max_cases <= 0 or args.max_cases > len(catalog):
            raise SystemExit(f"--max-cases must be between 1 and {len(catalog)}")
        selected = tuple(catalog[index * len(catalog) // args.max_cases] for index in range(args.max_cases))
        seeds = args.seeds
    payload = run_comprehensive_operational_matrix(cases=selected, seeds=seeds, sample_size=args.sample_size)
    write_operational_matrix_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    print(json.dumps({"summary": payload["summary"], "scorecard": payload["scorecard"], "safety": payload["safety"]}, indent=2, sort_keys=True))
    return 0 if payload["summary"]["execution_valid"] and payload["safety"]["hard_gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
