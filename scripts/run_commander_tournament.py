from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.commander_tournament import DEFAULT_SCENARIO_DIR, load_commander_tournament_cases, run_commander_tournament  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run P9 commander replay tournament")
    parser.add_argument("--scenario-dir", default=str(DEFAULT_SCENARIO_DIR))
    parser.add_argument("--output-json", default="")
    args = parser.parse_args()

    result = run_commander_tournament(load_commander_tournament_cases(Path(args.scenario_dir)))
    payload = json.dumps(result, indent=2, sort_keys=True)
    if args.output_json:
        Path(args.output_json).write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
