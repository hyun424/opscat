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
from app.services.p122_release_evidence import produce_p122_release_evidence  # noqa: E402


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reviewer-id", default="independent-p122-verifier")
    parser.add_argument("--builder-id", default="autonomous-builder")
    args = parser.parse_args(argv)
    evidence = produce_p122_release_evidence(reviewer_id=args.reviewer_id, builder_id=args.builder_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(f".{args.output.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    temporary.replace(args.output)
    print(json.dumps({"release_status": evidence["release_status"], "release_evidence_hash": evidence["release_evidence_hash"]}, sort_keys=True))
    return 0 if evidence["release_status"] == "p122_open_source_local_rc" else 1


if __name__ == "__main__":
    raise SystemExit(main())
