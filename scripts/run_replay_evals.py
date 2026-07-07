from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.services.replay_service import ReplayService, load_replay_scenarios


def main() -> int:
    parser = argparse.ArgumentParser(description="Run P7 deterministic replay evals.")
    parser.add_argument("--output-json", default="/tmp/opscat-replay-evals.json")
    parser.add_argument("--output-md", default="/tmp/opscat-replay-evals.md")
    args = parser.parse_args()
    result = ReplayService().run_all(load_replay_scenarios())
    Path(args.output_json).write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    lines = [
        "# OpsCat P7 Replay Eval Summary",
        "",
        f"- Total: {result.total}",
        f"- Passed: {result.passed}",
        f"- Failed: {result.failed}",
    ]
    for key, value in sorted(result.metrics.items()):
        lines.append(f"- {key}: {value}")
    Path(args.output_md).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if result.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
