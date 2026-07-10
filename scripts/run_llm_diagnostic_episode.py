#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.llm_diagnostic_episode import (  # noqa: E402
    run_llm_diagnostic_episode_suite,
    write_llm_diagnostic_episode_outputs,
)
from app.services.llm_tool_planner_evaluation import (  # noqa: E402
    MockToolPlanningProvider,
    ToolPlanningProvider,
    build_nvidia_tool_provider,
)
from app.services.operational_scenario_catalog import (  # noqa: E402
    build_comprehensive_operational_catalog,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-cases", type=int, default=16)
    parser.add_argument("--seeds", default="11")
    parser.add_argument("--sample-size", type=int, default=10)
    parser.add_argument("--max-tool-calls", type=int, default=3)
    parser.add_argument("--max-action-steps", type=int, default=3)
    parser.add_argument("--include-nvidia", action="store_true")
    parser.add_argument("--obvious-only", action="store_true")
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args()
    if args.max_cases < 1:
        parser.error("--max-cases must be at least 1")
    if args.sample_size < 5 or args.sample_size > 100:
        parser.error("--sample-size must be between 5 and 100")
    if args.max_tool_calls < 1 or args.max_tool_calls > 10:
        parser.error("--max-tool-calls must be between 1 and 10")
    if args.max_action_steps < 1 or args.max_action_steps > 10:
        parser.error("--max-action-steps must be between 1 and 10")

    catalog = list(build_comprehensive_operational_catalog())
    if args.obvious_only:
        catalog = [case for case in catalog if case.variant == "obvious"]
    cases = catalog[: args.max_cases]
    try:
        seeds = tuple(int(item.strip()) for item in args.seeds.split(",") if item.strip())
    except ValueError:
        parser.error("--seeds must contain comma-separated integers")
    if not seeds:
        parser.error("--seeds must contain at least one integer")
    providers: dict[str, ToolPlanningProvider] = {"mock": MockToolPlanningProvider()}
    if args.include_nvidia:
        providers["nvidia"] = build_nvidia_tool_provider()
    payload = run_llm_diagnostic_episode_suite(
        providers,
        cases=cases,
        seeds=seeds,
        sample_size=args.sample_size,
        max_tool_calls=args.max_tool_calls,
        max_action_steps=args.max_action_steps,
    )
    write_llm_diagnostic_episode_outputs(
        payload,
        output_json=args.output_json,
        output_md=args.output_md,
    )
    print(json.dumps(payload["summary"], sort_keys=True))
    return 0 if payload["summary"]["execution_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
