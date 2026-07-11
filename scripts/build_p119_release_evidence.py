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
from app.services.p119_release_evidence import empty_p119_release_authority_counters, produce_p119_release_evidence  # noqa: E402


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--evaluation", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--builder-id", default="autonomous-builder")
    p.add_argument("--reviewer-id", default="independent-verifier")
    a = p.parse_args(argv)
    report = json.loads(a.evaluation.read_text())
    if not isinstance(report, Mapping):
        return 1
    evidence = produce_p119_release_evidence(
        frozen_evaluation_report=report, reviewer_identity={"id": a.reviewer_id}, builder_identity={"id": a.builder_id}, authority_counters=empty_p119_release_authority_counters()
    )
    a.output.parent.mkdir(parents=True, exist_ok=True)
    tmp = a.output.with_name(f".{a.output.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    tmp.replace(a.output)
    print(json.dumps({"release_status": evidence["release_status"], "release_evidence_hash": evidence["release_evidence_hash"]}, sort_keys=True))
    return 0 if evidence["release_status"] == "p119_local_closed_loop_ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
