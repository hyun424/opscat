#!/usr/bin/env python3
"""Run the P104 evidence-gap investigator benchmark."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.evidence_gap_investigator import build_evidence_gap_cli_parser, run_evidence_gap_cli  # noqa: E402


def main() -> int:
    parser = build_evidence_gap_cli_parser()
    args = parser.parse_args()
    try:
        payload = run_evidence_gap_cli(args)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(payload["summary"], sort_keys=True))
    return 0 if payload["summary"]["execution_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
