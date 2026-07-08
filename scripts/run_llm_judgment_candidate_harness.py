#!/usr/bin/env python3
"""Run P58 LLM judgment candidate harness report."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.llm_judgment_candidate_harness import (  # noqa: E402
    build_llm_judgment_candidate_harness_report,
    write_llm_judgment_candidate_harness_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat P58 LLM judgment candidate harness")
    parser.add_argument("--cases", default="evals/investigator/p51_operator_judgment_benchmark_v2_cases.json")
    parser.add_argument("--manifest", default="evals/real_datasets/external/p44_benchmark_matrix_manifest.json")
    parser.add_argument("--judgment-cases", default="evals/judgment/seed/cases.json")
    parser.add_argument("--provider", default="mock", choices=("mock",))
    parser.add_argument("--max-cases", type=int, default=4)
    parser.add_argument("--output-json", default="/tmp/opscat-llm-judgment-candidate-harness-latest.json")
    parser.add_argument("--output-md", default="/tmp/opscat-llm-judgment-candidate-harness-latest.md")
    args = parser.parse_args()
    report = build_llm_judgment_candidate_harness_report(
        args.cases,
        args.manifest,
        args.judgment_cases,
        provider_name=args.provider,
        max_cases=args.max_cases,
    )
    payload = report.to_dict()
    write_llm_judgment_candidate_harness_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    print(f"Wrote {args.output_md}")
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
