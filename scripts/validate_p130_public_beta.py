#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p130_public_beta import validate_p130_release_evidence  # noqa: E402


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    evidence = json.loads(args.artifact.read_text(encoding="utf-8"))
    if not isinstance(evidence, Mapping):
        print(json.dumps({"valid": False, "reasons": ["artifact_not_mapping"]}, sort_keys=True))
        return 1
    result = validate_p130_release_evidence(evidence, root=args.root.resolve())
    print(json.dumps(result, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
