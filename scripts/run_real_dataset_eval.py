#!/usr/bin/env python3
"""Run P12 real-dataset-shaped fixture evaluation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.real_dataset_evaluation import (  # noqa: E402
    DEFAULT_FIXTURE_SAMPLES,
    render_real_dataset_evaluation_markdown,
    run_real_dataset_evaluation,
    write_real_dataset_evaluation_outputs,
)


def _sample_arg(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("sample must use FAMILY=PATH")
    family, path = value.split("=", 1)
    return family, path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P12 real dataset evaluation")
    parser.add_argument("--fixture-pack", action="store_true", help="Use bundled tiny fixture samples")
    parser.add_argument("--sample", action="append", type=_sample_arg, default=[], help="Additional or alternate FAMILY=PATH local sample")
    parser.add_argument("--output-json", default="")
    parser.add_argument("--output-md", default="")
    parser.add_argument("--output-cases", default="")
    args = parser.parse_args()

    samples = DEFAULT_FIXTURE_SAMPLES if args.fixture_pack or not args.sample else tuple(args.sample)
    result = run_real_dataset_evaluation(samples, output_cases=args.output_cases or None)
    write_real_dataset_evaluation_outputs(result, output_json=args.output_json or None, output_md=args.output_md or None)
    if args.output_md:
        print(f"wrote markdown report to {args.output_md}", file=sys.stderr)
    else:
        print(render_real_dataset_evaluation_markdown(result), file=sys.stderr)
    print(f"cases={len(result.cases)} passed={result.passed}")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
