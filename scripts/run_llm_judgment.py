#!/usr/bin/env python3
"""Run P14 mock LLM judgment against a P13 context packet or case file."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.judgment_dataset import load_judgment_cases  # noqa: E402
from app.services.llm_context_builder import build_context_from_judgment_case  # noqa: E402
from app.services.llm_judgment import (  # noqa: E402
    MockLLMJudgmentProvider,
    run_llm_judgment_from_packet,
    write_llm_judgment_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run P14 local/mock LLM judgment without external model calls.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--context-json", help="Prebuilt P13 context packet JSON.")
    source.add_argument("--cases", help="Judgment cases JSON to convert into a context packet first.")
    parser.add_argument("--case-id", help="Case ID when using --cases. Defaults to first case.")
    parser.add_argument("--provider", default="mock", choices=("mock",), help="Judgment provider. P14 supports mock only by default.")
    parser.add_argument("--max-evidence", type=int, default=20, help="Maximum evidence items when building context from cases.")
    parser.add_argument("--output-json", help="Path for judgment JSON report.")
    parser.add_argument("--output-md", help="Path for judgment Markdown report.")
    args = parser.parse_args()

    if args.context_json:
        context = json.loads(Path(args.context_json).read_text(encoding="utf-8"))
    else:
        cases = load_judgment_cases(args.cases)
        if not cases:
            raise SystemExit("no judgment cases found")
        selected = next((case for case in cases if case.id == args.case_id), cases[0]) if args.case_id else cases[0]
        if args.case_id and selected.id != args.case_id:
            raise SystemExit(f"case not found: {args.case_id}")
        context = build_context_from_judgment_case(selected, max_evidence=args.max_evidence).to_dict()

    provider = MockLLMJudgmentProvider()
    result = run_llm_judgment_from_packet(context, provider=provider)
    write_llm_judgment_outputs(result, output_json=args.output_json, output_md=args.output_md)
    print(
        "Ran P14 LLM judgment "
        f"provider={result.provider} final_route={result.safety_gate.final_route} "
        f"validation={result.validation.get('valid')} citation={result.citation_check.valid} "
        f"action_execution_enabled={result.action_execution_enabled}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
