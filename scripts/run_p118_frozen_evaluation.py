#!/usr/bin/env python3
"""Run the frozen P118 local/mock/sandbox execution evaluation."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p118_evaluator import run_p118_frozen_evaluation  # noqa: E402


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=11801)
    args = parser.parse_args(argv)
    report = run_p118_frozen_evaluation(seed=args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp = args.output.with_name(f".{args.output.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(args.output)
    print(json.dumps({"case_count": report["case_count"], "evaluation_hash": report["evaluation_hash"]}, sort_keys=True))
    return 0 if report["aggregate"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
