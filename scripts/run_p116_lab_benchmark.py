#!/usr/bin/env python3
"""Run frozen P116 local loopback benchmark evidence and write JSON atomically."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p116_release_evidence import run_p116_release_evidence  # noqa: E402


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario-id", action="append", default=[])
    parser.add_argument("--family", action="append", default=[])
    parser.add_argument("--seed", type=int, action="append", default=[])
    parser.add_argument("--max-cases", type=int, default=3)
    parser.add_argument("--sample-size", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    evidence = run_p116_release_evidence(
        scenario_ids=args.scenario_id or None,
        families=args.family or None,
        seeds=tuple(args.seed or [11601, 11602]),
        max_cases=args.max_cases,
        sample_size=args.sample_size,
    )
    _atomic_write_json(args.output, evidence)
    print(
        json.dumps(
            {
                "contract_ready": evidence["contract_ready"],
                "outcome_qualified": evidence["outcome_qualified"],
                "release_evidence_hash": evidence["release_evidence_hash"],
                "failed_gates": [name for name, passed in evidence["gates"].items() if passed is not True],
            },
            sort_keys=True,
        )
    )
    return 0


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
