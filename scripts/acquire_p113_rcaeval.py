#!/usr/bin/env python3
"""Validate the pinned P113 RCAEval RE1-TT archive already present on disk."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p113_acquisition import validate_re1_tt_archive  # noqa: E402

DEFAULT_MANIFEST = ROOT / "evals/real_datasets/external/p113/source-manifest-re1-tt.json"
DEFAULT_RAW = ROOT / "evals/real_datasets/external/p113/raw"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW)
    args = parser.parse_args()
    result = validate_re1_tt_archive(args.raw_dir / "RE1-TT.zip", args.manifest)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
