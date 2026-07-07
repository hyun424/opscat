"""Run P7 deterministic replay and adversarial evals."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.replay_service import DEFAULT_REPLAY_DIR, render_replay_markdown, run_replay_scenarios  # noqa: E402


def run_replay_evals(
    *,
    replay_dir: Path = DEFAULT_REPLAY_DIR,
    output_json: Path | None = None,
    output_md: Path | None = None,
    scenarios: list[str] | None = None,
) -> dict[str, Any]:
    summary = run_replay_scenarios(replay_dir=replay_dir, scenarios=scenarios)
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    if output_md is not None:
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(render_replay_markdown(summary), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic P7 replay evals.")
    parser.add_argument("--replay-dir", type=Path, default=DEFAULT_REPLAY_DIR)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-md", type=Path)
    parser.add_argument("--scenario", action="append", dest="scenarios")
    args = parser.parse_args()
    summary = run_replay_evals(replay_dir=args.replay_dir, output_json=args.output_json, output_md=args.output_md, scenarios=args.scenarios)
    print(render_replay_markdown(summary))
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
