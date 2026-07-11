#!/usr/bin/env python3
"""Run the full local P115/P116 measured benchmark and atomically persist artifacts."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p115_outcome_benchmark import run_p115_outcome_benchmark  # noqa: E402


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, action="append", default=[])
    parser.add_argument("--sample-size", type=int, default=20)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    run = run_p115_outcome_benchmark(seeds=tuple(args.seed or [11501]), sample_size=args.sample_size)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for key, filename in (
        ("safe_null_baseline", "safe-null-baseline.json"),
        ("deterministic_baseline", "deterministic-baseline.json"),
        ("evaluator_report", "evaluator-report.json"),
        ("p116_release_evidence", "p116-release-evidence.json"),
    ):
        _atomic_json(args.output_dir / filename, run[key])
    print(json.dumps({"evaluator": run["evaluator_report"]["metrics"], "p116_outcome_qualified": run["p116_release_evidence"]["outcome_qualified"]}, sort_keys=True))
    return 0


def _atomic_json(path: Path, value: Any) -> None:
    payload = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
