#!/usr/bin/env python3
"""Build a deterministic local/mock LLM context packet from judgment cases."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.judgment_dataset import load_judgment_cases  # noqa: E402
from app.services.llm_context_builder import build_context_from_judgment_case, write_context_outputs  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a P13 local/mock LLM context packet without model calls.")
    parser.add_argument("--cases", required=True, help="Path to judgment cases JSON.")
    parser.add_argument("--case-id", help="Case ID to render. Defaults to the first case.")
    parser.add_argument("--max-evidence", type=int, default=20, help="Maximum evidence items to include.")
    parser.add_argument("--output-json", help="Path for context packet JSON.")
    parser.add_argument("--output-md", help="Path for context packet Markdown.")
    args = parser.parse_args()

    cases = load_judgment_cases(args.cases)
    if not cases:
        raise SystemExit("no judgment cases found")
    selected = next((case for case in cases if case.id == args.case_id), cases[0]) if args.case_id else cases[0]
    if args.case_id and selected.id != args.case_id:
        raise SystemExit(f"case not found: {args.case_id}")

    packet = build_context_from_judgment_case(selected, max_evidence=args.max_evidence)
    write_context_outputs(packet, output_json=args.output_json, output_md=args.output_md)
    print(
        "Built P13 LLM context packet "
        f"case={selected.id} evidence={len(packet.evidence)} local_mock_only={packet.local_mock_only} "
        f"model_calls_enabled={packet.model_calls_enabled}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
