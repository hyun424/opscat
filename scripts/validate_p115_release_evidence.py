#!/usr/bin/env python3
"""Fail closed unless persisted P115 and imported P116 evidence are current."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p115_release_evidence import validate_p115_release_evidence  # noqa: E402


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--p116-import", type=Path, required=True)
    args = parser.parse_args(argv)
    artifact = json.loads(args.artifact.read_text(encoding="utf-8"))
    imported = json.loads(args.p116_import.read_text(encoding="utf-8"))
    if not isinstance(artifact, Mapping) or not isinstance(imported, Mapping):
        print(json.dumps({"valid": False, "reasons": ["artifact_not_object"]}, sort_keys=True))
        return 1
    report = validate_p115_release_evidence(artifact, imported_p116_evidence=imported)
    print(json.dumps(report, sort_keys=True))
    return 0 if report["valid"] is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
