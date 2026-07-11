#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from app.services.p121_release_evidence import produce_p121_release_evidence  # noqa: E402


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evaluation", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--builder-id", default="autonomous-builder")
    parser.add_argument("--reviewer-id", default="independent-verifier")
    args = parser.parse_args(argv)
    report = json.loads(args.evaluation.read_text())
    if not isinstance(report, Mapping):
        return 1
    evidence = produce_p121_release_evidence(report=report, reviewer_id=args.reviewer_id, builder_id=args.builder_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(f".{args.output.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    temporary.replace(args.output)
    print(json.dumps({"release_status": evidence["release_status"], "release_evidence_hash": evidence["release_evidence_hash"]}, sort_keys=True))
    return 0 if evidence["release_status"] == "p121_local_proactive_prevention_ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
