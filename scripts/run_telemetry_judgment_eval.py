#!/usr/bin/env python3
"""Run OpsCat P29 telemetry-grounded judgment quality evaluation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.telemetry_judgment_quality import (  # noqa: E402
    render_telemetry_judgment_quality_markdown,
    run_telemetry_judgment_quality_fixture,
    write_telemetry_judgment_quality_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat telemetry-grounded judgment quality evaluation")
    parser.add_argument("--cases", default="evals/judgment/telemetry_grounded/p29_cases.json")
    parser.add_argument("--provider", default="mock", choices=("mock", "nvidia"))
    parser.add_argument("--output-json", default="")
    parser.add_argument("--output-md", default="")
    args = parser.parse_args()

    report = run_telemetry_judgment_quality_fixture(args.cases, provider=args.provider)
    payload = report.to_dict()
    write_telemetry_judgment_quality_outputs(payload, output_json=args.output_json or None, output_md=args.output_md or None)
    score = payload["score"]
    print(
        f"OpsCat telemetry-judgment-quality provider={payload['provider']} cases={payload['summary']['case_count']} "
        f"baseline={score['baseline_accuracy']} grounded={score['grounded_accuracy']} delta={score['accuracy_delta']} "
        f"unsafe_auto={score['unsafe_action_count']} remediation_execution_enabled=False"
    )
    if not args.output_md:
        print(render_telemetry_judgment_quality_markdown(payload), file=sys.stderr)
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
