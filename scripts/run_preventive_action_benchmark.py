#!/usr/bin/env python3
"""Run the offline P106 preventive-action benchmark."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.preventive_action_benchmark import render_benchmark_markdown, run_preventive_action_benchmark  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", default="evals/prevention/p106_benchmark_cases.json")
    parser.add_argument(
        "--p105-artifact",
        help="Path to an already extracted, canonical P105 release-qualified artifact required for scored runs.",
    )
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-md", required=True)
    args = parser.parse_args()

    result = run_preventive_action_benchmark(
        Path(args.cases),
        p105_artifact_path=Path(args.p105_artifact) if args.p105_artifact else None,
    )
    output_json = Path(args.output_json)
    output_md = Path(args.output_md)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    output_md.write_text(render_benchmark_markdown(result), encoding="utf-8")
    summary = {
        "scored": result.get("scored"),
        "benchmark_fresh": result.get("benchmark_fresh"),
        "harmful_action_rate": result.get("harmful_action_rate"),
        "reasons": result.get("reasons", []),
    }
    print(json.dumps(summary, sort_keys=True))
    return 0 if result.get("scored") else 1


if __name__ == "__main__":
    raise SystemExit(main())
