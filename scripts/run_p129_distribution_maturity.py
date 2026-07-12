#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p129_distribution_maturity import produce_p129_distribution_report, produce_p129_release_evidence  # noqa: E402


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--distribution-output", type=Path, default=ROOT / "evals/p129/distribution-report.json")
    parser.add_argument("--release-output", type=Path, default=ROOT / "evals/p129/release-evidence.json")
    parser.add_argument("--reviewer-id", default="independent-p129-verifier")
    parser.add_argument("--builder-id", default="autonomous-builder")
    args = parser.parse_args(argv)

    report = produce_p129_distribution_report(root=ROOT, reviewer_id=args.reviewer_id, builder_id=args.builder_id)
    evidence = produce_p129_release_evidence(root=ROOT, reviewer_id=args.reviewer_id, builder_id=args.builder_id)
    _write_json_atomic(args.distribution_output, report)
    _write_json_atomic(args.release_output, evidence)
    print(
        json.dumps(
            {
                "status": report["status"],
                "report_hash": report["report_hash"],
                "release_evidence_hash": evidence["release_evidence_hash"],
            },
            sort_keys=True,
        )
    )
    return 0 if report["status"] == "p129_distribution_maturity_ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
