#!/usr/bin/env python3
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
from app.services.p120_evaluator import run_p120_frozen_evaluation  # noqa: E402


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=12001)
    args = parser.parse_args(argv)
    report = run_p120_frozen_evaluation(seed=args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(f".{args.output.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    temporary.replace(args.output)
    print(json.dumps({"case_count": report["case_count"], "evaluation_hash": report["evaluation_hash"]}, sort_keys=True))
    return 0 if report["max_degradation"] <= 0.15 else 1


if __name__ == "__main__":
    raise SystemExit(main())
