#!/usr/bin/env python3
"""Run OpsCat model judgment quality evaluation."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.judgment_dataset import JudgmentCase, load_judgment_cases  # noqa: E402
from app.services.llm_judgment import MockLLMJudgmentProvider, NvidiaLLMJudgmentProvider  # noqa: E402
from app.services.model_quality_lab import (  # noqa: E402
    load_realtime_snapshot_cases,
    render_model_quality_markdown,
    run_model_quality_lab,
    write_model_quality_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat model judgment quality evaluation")
    parser.add_argument("--cases", default="evals/judgment/seed/cases.json")
    parser.add_argument("--p18a-replay-json", default="", help="Optional P18A replay JSON containing snapshots.")
    parser.add_argument("--provider", default="mock", choices=("mock", "nvidia"))
    parser.add_argument("--model", default="")
    parser.add_argument("--env-file", default=".env", help="Optional local env file parsed safely; never sourced as shell.")
    parser.add_argument("--max-cases", type=int, default=0)
    parser.add_argument("--max-evidence", type=int, default=20)
    parser.add_argument("--output-json", default="")
    parser.add_argument("--output-md", default="")
    args = parser.parse_args()

    for key, value in _load_env_file(args.env_file).items():
        os.environ.setdefault(key, value)

    provider = NvidiaLLMJudgmentProvider(model=args.model or None) if args.provider == "nvidia" else MockLLMJudgmentProvider()
    cases: list[JudgmentCase] = load_judgment_cases(args.cases)
    if args.p18a_replay_json:
        cases.extend(load_realtime_snapshot_cases(args.p18a_replay_json))

    result = run_model_quality_lab(
        cases,
        provider=provider,
        provider_name=args.provider,
        max_cases=args.max_cases or None,
        max_evidence=args.max_evidence,
    )
    write_model_quality_outputs(result, output_json=args.output_json or None, output_md=args.output_md or None)
    print(
        f"OpsCat model quality provider={result.provider} model={result.model} cases={result.case_count} "
        f"raw={result.raw_provider_score} calibrated={result.calibrated_score} delta={result.calibration_delta} "
        f"action_execution_enabled={result.action_execution_enabled}"
    )
    if args.output_md:
        print(f"wrote markdown report to {args.output_md}", file=sys.stderr)
    else:
        print(render_model_quality_markdown(result), file=sys.stderr)
    return 0 if result.case_count else 1


def _load_env_file(path: str) -> dict[str, str]:
    env_path = Path(path)
    if not path or not env_path.exists():
        return {}
    values: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


if __name__ == "__main__":
    raise SystemExit(main())
