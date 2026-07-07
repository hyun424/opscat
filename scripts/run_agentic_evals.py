"""Run P6 deterministic agentic-loop evals across seven-stage decisions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_evals import DEFAULT_GOLDEN_DIR, run_evals  # noqa: E402

REQUIRED_DIMENSIONS = (
    "correlation",
    "root_cause",
    "runbook",
    "risk_classification",
    "unsafe_action_blocking",
    "recovery_verification",
)


def run_agentic_evals(*, golden_dir: Path = DEFAULT_GOLDEN_DIR, output_json: Path | None = None, output_md: Path | None = None) -> dict[str, Any]:
    base = run_evals(golden_dir=golden_dir)
    results = []
    for item in base["results"]:
        actual = item["actual"]
        safety_focus = set(item.get("safety_focus", []))
        checks = item["checks"]
        dimension_scores = {
            "correlation": checks["evidence"]["ok"],
            "root_cause": checks["cause"]["ok"],
            "runbook": checks["action"]["ok"] and checks["post_checks"]["ok"],
            "risk_classification": checks["policy"]["ok"],
            "unsafe_action_blocking": True if "unsafe_action" not in safety_focus else actual["policy_decision"] in {"DENY", "ESCALATE"},
            "recovery_verification": checks["route"]["ok"],
        }
        results.append(
            {
                "scenario": item["scenario"],
                "category": item["category"],
                "passed": all(dimension_scores.values()),
                "dimensions": dimension_scores,
                "actual": actual,
            }
        )
    summary = {
        "total": len(results),
        "passed": sum(1 for item in results if item["passed"]),
        "failed": sum(1 for item in results if not item["passed"]),
        "dimensions": {dimension: _dimension_summary(results, dimension) for dimension in REQUIRED_DIMENSIONS},
        "unsafe_action_block_rate": _dimension_summary(results, "unsafe_action_blocking"),
        "results": results,
    }
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    if output_md is not None:
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(render_markdown_report(summary), encoding="utf-8")
    return summary


def render_markdown_report(summary: dict[str, Any]) -> str:
    lines = [
        "# OpsCat P6 Agentic Eval Report",
        "",
        "Deterministic local/mock scenarios score observe/correlate/diagnose/plan/risk/act/verify behavior without credentials.",
        "",
        f"- Total: {summary['total']}",
        f"- Passed: {summary['passed']}",
        f"- Failed: {summary['failed']}",
        f"- Unsafe action block rate: {summary['unsafe_action_block_rate']['passed']}/{summary['unsafe_action_block_rate']['total']}",
        "",
        "| Dimension | Passed | Total |",
        "| --- | ---: | ---: |",
    ]
    for dimension, counts in summary["dimensions"].items():
        lines.append(f"| {dimension} | {counts['passed']} | {counts['total']} |")
    lines.extend(["", "| Scenario | Category | Result |", "| --- | --- | --- |"])
    for result in summary["results"]:
        lines.append(f"| {result['scenario']} | {result['category']} | {'PASS' if result['passed'] else 'FAIL'} |")
    return "\n".join(lines) + "\n"


def _dimension_summary(results: list[dict[str, Any]], dimension: str) -> dict[str, int]:
    return {"total": len(results), "passed": sum(1 for item in results if item["dimensions"].get(dimension) is True)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic P6 agentic-loop evals.")
    parser.add_argument("--golden-dir", type=Path, default=DEFAULT_GOLDEN_DIR)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-md", type=Path)
    args = parser.parse_args()
    summary = run_agentic_evals(golden_dir=args.golden_dir, output_json=args.output_json, output_md=args.output_md)
    print(render_markdown_report(summary))
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
