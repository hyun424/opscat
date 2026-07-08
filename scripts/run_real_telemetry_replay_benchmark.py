#!/usr/bin/env python3
"""Run OpsCat P32 real telemetry replay benchmark."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.real_telemetry_replay_benchmark import (  # noqa: E402
    run_real_telemetry_replay_benchmark_fixture,
    write_real_telemetry_replay_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpsCat real telemetry replay benchmark")
    parser.add_argument("--replay-pack", default="evals/telemetry/replay/p32_replay_pack.json")
    parser.add_argument("--output-json", default="")
    parser.add_argument("--output-md", default="")
    args = parser.parse_args()

    report = run_real_telemetry_replay_benchmark_fixture(args.replay_pack)
    payload = report.to_dict()
    write_real_telemetry_replay_outputs(
        payload,
        output_json=args.output_json or None,
        output_md=args.output_md or None,
    )
    score = payload["score"]
    print(
        f"OpsCat real-telemetry-replay sources={payload['summary']['source_count']} "
        f"windows={payload['summary']['trend_window_count']} replay_score={score['replay_score']} "
        f"grounded={score['grounded_accuracy']} citation={score['evidence_citation_rate']} "
        f"simulation={score['simulation_coverage']} unsafe_auto={score['unsafe_auto_action_count']}"
    )
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
