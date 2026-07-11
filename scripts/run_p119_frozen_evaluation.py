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
from app.services.p119_evaluator import run_p119_frozen_evaluation  # noqa: E402


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--seed", type=int, default=11901)
    a = p.parse_args(argv)
    report = run_p119_frozen_evaluation(seed=a.seed)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    tmp = a.output.with_name(f".{a.output.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    tmp.replace(a.output)
    print(json.dumps({"case_count": report["case_count"], "evaluation_hash": report["evaluation_hash"]}, sort_keys=True))
    return 0 if report["aggregate"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
