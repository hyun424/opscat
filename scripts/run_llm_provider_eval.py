#!/usr/bin/env python3
"""Run OpsCat LLM provider evaluation across judgment cases."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.judgment_dataset import load_judgment_cases  # noqa: E402
from app.services.llm_judgment import MockLLMJudgmentProvider, NvidiaLLMJudgmentProvider  # noqa: E402
from app.services.llm_provider_evaluation import (  # noqa: E402
    render_llm_provider_eval_markdown,
    run_llm_provider_evaluation,
    write_llm_provider_eval_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat LLM provider evaluation")
    parser.add_argument("--cases", default="evals/judgment/seed/cases.json")
    parser.add_argument("--provider", default="mock", choices=("mock", "nvidia"))
    parser.add_argument("--model", default="")
    parser.add_argument("--env-file", default=".env", help="Optional local env file parsed safely; never sourced as shell.")
    parser.add_argument("--max-cases", type=int, default=0, help="Limit evaluated cases; useful for live provider cost/latency control.")
    parser.add_argument("--max-evidence", type=int, default=20)
    parser.add_argument("--output-json", default="")
    parser.add_argument("--output-md", default="")
    args = parser.parse_args()

    env_values = _load_env_file(args.env_file)
    for key, value in env_values.items():
        os.environ.setdefault(key, value)

    provider = NvidiaLLMJudgmentProvider(model=args.model or None) if args.provider == "nvidia" else MockLLMJudgmentProvider()
    cases = load_judgment_cases(args.cases)
    result = run_llm_provider_evaluation(
        cases,
        provider=provider,
        provider_name=args.provider,
        max_cases=args.max_cases or None,
        max_evidence=args.max_evidence,
    )
    write_llm_provider_eval_outputs(result, output_json=args.output_json or None, output_md=args.output_md or None)
    print(
        f"OpsCat LLM provider eval provider={result.provider} model={result.model} "
        f"cases={result.case_count} passed={result.passed_count}/{result.case_count} "
        f"overall={result.overall_score} action_execution_enabled={result.action_execution_enabled}"
    )
    if args.output_md:
        print(f"wrote markdown report to {args.output_md}", file=sys.stderr)
    else:
        print(render_llm_provider_eval_markdown(result), file=sys.stderr)
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
