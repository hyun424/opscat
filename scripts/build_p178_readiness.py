#!/usr/bin/env python3
"""Build the P178 offline readiness artifact without qualification."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p178_release import write_readiness_artifact  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "evals/p178/output/readiness-offline-substrate.json")
    args = parser.parse_args(argv)
    try:
        path = write_readiness_artifact(project_root=ROOT, output_path=args.output)
        print(json.dumps({"phase": "p178", "qualified": False, "artifact": str(path)}, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"phase": "p178", "status": "blocked", "error_type": type(exc).__name__, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
