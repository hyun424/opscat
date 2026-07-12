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

from app.services.p130_public_beta import P130_READY_STATUS, build_p130_public_beta  # noqa: E402


def _write_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--reviewer-id", default="independent-p130-verifier")
    parser.add_argument("--builder-id", default="autonomous-builder")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    output_dir = args.output_dir or root / "evals/p130"
    bundle = build_p130_public_beta(root=root, builder_id=args.builder_id, reviewer_id=args.reviewer_id)
    _write_atomic(output_dir / "claim-ledger.json", bundle["claim_ledger"])
    _write_atomic(output_dir / "risk-register.json", bundle["risk_register"])
    _write_atomic(output_dir / "beta-evidence.json", bundle["beta_evidence"])
    _write_atomic(output_dir / "release-evidence.json", bundle["release_evidence"])
    release = bundle["release_evidence"]
    print(
        json.dumps(
            {
                "release_status": release["release_status"],
                "release_evidence_hash": release["release_evidence_hash"],
                "reasons": release["reasons"],
            },
            sort_keys=True,
        )
    )
    return 0 if release["release_status"] == P130_READY_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
