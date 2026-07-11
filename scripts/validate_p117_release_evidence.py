#!/usr/bin/env python3
"""Fail closed unless persisted P117 release evidence is current."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p117_release_evidence import validate_p117_release_evidence  # noqa: E402


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    args = parser.parse_args(argv)
    value = json.loads(args.artifact.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        return 1
    report = validate_p117_release_evidence(value)
    print(json.dumps(report, sort_keys=True))
    return 0 if report["valid"] is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
