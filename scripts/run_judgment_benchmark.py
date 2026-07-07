from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.judgment_benchmark import DEFAULT_CASE_PATH, render_benchmark_markdown, run_judgment_benchmark, write_benchmark_outputs  # noqa: E402
from app.services.judgment_dataset import load_judgment_cases  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P10 incident judgment benchmark")
    parser.add_argument("--cases", default=str(DEFAULT_CASE_PATH))
    parser.add_argument("--baseline", default="")
    parser.add_argument("--output-json", default="")
    parser.add_argument("--output-md", default="")
    args = parser.parse_args()

    result = run_judgment_benchmark(load_judgment_cases(args.cases), baseline_path=args.baseline or None)
    write_benchmark_outputs(result, output_json=args.output_json or None, output_md=args.output_md or None)
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    if args.output_md:
        print(f"wrote markdown report to {args.output_md}", file=sys.stderr)
    else:
        print(render_benchmark_markdown(result), file=sys.stderr)
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
