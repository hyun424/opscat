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

from app.services.p124_judgment_quality import build_release_evidence, run_judgment_quality, write_default_cases  # noqa: E402


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--release-evidence", required=True, type=Path)
    args = parser.parse_args(argv)

    if not args.cases.exists():
        write_default_cases(args.cases)
    report = run_judgment_quality(cases_path=args.cases)
    evidence = build_release_evidence(report)
    _atomic_write(args.output, report)
    _atomic_write(args.release_evidence, evidence)
    print(json.dumps({"case_count": report["case_count"], "quality_report_hash": report["quality_report_hash"], "release_status": evidence["release_status"]}, sort_keys=True))
    return 0 if evidence["release_status"] == "p124_judgment_quality_promoted" else 1


def _atomic_write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
