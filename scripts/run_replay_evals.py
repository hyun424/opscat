#!/usr/bin/env python3
"""Run P7 deterministic replay evals."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from app.services.replay_service import ReplayService, load_replay_scenarios

    parser = argparse.ArgumentParser(description="Run P7 deterministic replay evals.")
    parser.add_argument("--output-json", default="/tmp/opscat-replay-evals.json")
    parser.add_argument("--output-md", default="/tmp/opscat-replay-evals.md")
    args = parser.parse_args()
    report = ReplayService(args.replay_dir).run(output_json=args.output_json, output_md=args.output_md)
    print(render_replay_markdown(report))
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
