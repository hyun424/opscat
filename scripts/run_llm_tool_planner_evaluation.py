#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.llm_tool_planner_evaluation import (  # noqa: E402
    MockToolPlanningProvider,
    ToolPlanningProvider,
    build_nvidia_tool_provider,
    run_llm_tool_planner_evaluation,
    write_llm_tool_planner_outputs,
)
from app.services.operational_scenario_catalog import build_comprehensive_operational_catalog  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-cases", type=int, default=52)
    parser.add_argument("--include-nvidia", action="store_true")
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args()
    if args.max_cases < 1:
        parser.error("--max-cases must be at least 1")
    cases = [case for case in build_comprehensive_operational_catalog() if case.variant == "obvious"][: args.max_cases]
    providers: dict[str, ToolPlanningProvider] = {"mock": MockToolPlanningProvider()}
    if args.include_nvidia:
        providers["nvidia"] = build_nvidia_tool_provider()
    payload = run_llm_tool_planner_evaluation(providers, cases=cases)
    write_llm_tool_planner_outputs(payload, output_json=args.output_json, output_md=args.output_md)
    print(json.dumps(payload["summary"], sort_keys=True))
    return 0 if payload["summary"]["execution_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
