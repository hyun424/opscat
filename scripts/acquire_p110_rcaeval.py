#!/usr/bin/env python3
"""Validate or explicitly acquire the pinned P110 RCAEval RE1-OB archive."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p110_acquisition import acquire_pinned_archive, validate_local_archive  # noqa: E402

DEFAULT_MANIFEST = ROOT / "evals/real_datasets/external/p110/source-manifest.json"
DEFAULT_RAW = ROOT / "evals/real_datasets/external/p110/raw"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--allow-network", action="store_true", help="Explicitly permit the one pinned HTTPS download.")
    args = parser.parse_args()
    archive = args.raw_dir / "RE1-OB.zip"
    result = (
        acquire_pinned_archive(args.manifest, args.raw_dir, allow_network=True)
        if args.allow_network
        else validate_local_archive(archive, args.manifest)
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
