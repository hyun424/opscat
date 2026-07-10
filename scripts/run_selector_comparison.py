#!/usr/bin/env python3
"""Run the P98 multi-selector blind causal comparison."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.causal_remediation_benchmark import build_causal_scenario_catalog  # noqa: E402
from app.services.selector_comparison import (  # noqa: E402
    EvidenceOnlyLLMSelector,
    NvidiaCausalDecisionProvider,
    build_default_selector_suite,
    run_selector_comparison,
)


def _parse_seeds(value: str) -> tuple[int, ...]:
    seeds = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    if not seeds:
        raise argparse.ArgumentTypeError("at least one integer seed is required")
    return seeds


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-cases", type=int, default=12, help="bounded smoke size; ignored by --full-matrix")
    parser.add_argument("--seeds", type=_parse_seeds, default=(11,), help="comma-separated deterministic seeds")
    parser.add_argument("--full-matrix", action="store_true", help="run all 120 cases with seeds 11,29,47")
    parser.add_argument("--selectors", default="rule_based,observation_only,mock_llm", help="comma-separated default selector names")
    parser.add_argument("--include-nvidia", action="store_true", help="explicitly enable the key-gated NVIDIA selector")
    parser.add_argument("--output-json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    catalog = build_causal_scenario_catalog()
    if args.full_matrix:
        cases = catalog
        seeds = (11, 29, 47)
    else:
        if args.max_cases <= 0 or args.max_cases > len(catalog):
            raise SystemExit(f"--max-cases must be between 1 and {len(catalog)}")
        cases = catalog[: args.max_cases]
        seeds = args.seeds

    suite = build_default_selector_suite()
    requested = tuple(item.strip() for item in args.selectors.split(",") if item.strip())
    unknown = sorted(set(requested) - set(suite))
    if unknown:
        raise SystemExit(f"unknown selectors: {', '.join(unknown)}")
    selected = {name: suite[name] for name in requested}
    if args.include_nvidia:
        selected["nvidia_llm"] = EvidenceOnlyLLMSelector(NvidiaCausalDecisionProvider())

    payload = run_selector_comparison(selected, cases=cases, seeds=seeds)
    if args.output_json:
        output = Path(args.output_json)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"summary": payload["summary"], "ranking_by_blind_causal_lift": payload["ranking_by_blind_causal_lift"]}, indent=2, sort_keys=True))
    return 0 if payload["summary"]["execution_valid"] and payload["summary"]["hard_safety_gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
