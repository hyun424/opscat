#!/usr/bin/env python3
"""Validate or explicitly acquire the pinned P114 RCAEval RE2 archives."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p114_acquisition import acquire_pinned_archive, validate_re2_archive  # noqa: E402

DEFAULT_BASE = ROOT / "evals/real_datasets/external/p114"
DEFAULT_RAW = DEFAULT_BASE / "raw"
DEFAULT_MANIFESTS = {
    "re2-ss": DEFAULT_BASE / "source-manifest-re2-ss.json",
    "re2-ob": DEFAULT_BASE / "source-manifest-re2-ob.json",
}
DEFAULT_ARCHIVES = {
    "re2-ss": DEFAULT_RAW / "RE2-SS.zip",
    "re2-ob": DEFAULT_RAW / "RE2-OB.zip",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=sorted(DEFAULT_MANIFESTS), action="append")
    parser.add_argument("--manifest", type=Path, help="Validate/acquire a single custom manifest.")
    parser.add_argument("--archive", type=Path, help="Validate a single local archive path.")
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--allow-network", action="store_true", help="Explicitly permit pinned HTTPS downloads.")
    args = parser.parse_args()

    if args.manifest:
        if args.allow_network:
            result: object = acquire_pinned_archive(args.manifest, args.raw_dir, allow_network=True)
        else:
            if args.archive is None:
                parser.error("--archive is required with --manifest unless --allow-network is set")
            result = validate_re2_archive(args.archive, args.manifest)
    else:
        sources = args.source or sorted(DEFAULT_MANIFESTS)
        results = []
        for source in sources:
            manifest = DEFAULT_MANIFESTS[source]
            if args.allow_network:
                results.append(acquire_pinned_archive(manifest, args.raw_dir, allow_network=True))
            else:
                results.append(validate_re2_archive(DEFAULT_ARCHIVES[source], manifest))
        result = results

    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
