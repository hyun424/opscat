#!/usr/bin/env python3
"""Run OpsCat P20 closed-loop incident response."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.closed_loop_response import run_closed_loop_response, write_closed_loop_outputs  # noqa: E402
from app.services.judgment_dataset import load_judgment_cases  # noqa: E402
from app.services.llm_judgment import MockLLMJudgmentProvider  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat closed-loop incident response")
    parser.add_argument("--cases", default="evals/judgment/seed/cases.json")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--provider", default="mock", choices=("mock",))
    parser.add_argument("--output-json", default="")
    parser.add_argument("--output-md", default="")
    args = parser.parse_args()

    cases = load_judgment_cases(args.cases)
    case = next((item for item in cases if item.id == args.case_id), None)
    if case is None:
        raise SystemExit(f"case id not found: {args.case_id}")
    result = run_closed_loop_response(case, provider=MockLLMJudgmentProvider())
    write_closed_loop_outputs(result, output_json=args.output_json or None, output_md=args.output_md or None)
    print(
        f"OpsCat closed loop case={result.case_id} provider={result.provider} "
        f"final_route={result.final_decision.get('route')} fetched={len(result.fetched_evidence)} "
        "action_execution_enabled=False"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
