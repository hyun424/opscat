#!/usr/bin/env python3
"""Freeze deterministic P114 RE2-OB packets and gates before scoring."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p114_acceptance import build_p114_acceptance_freeze, p114_implementation_hash  # noqa: E402
from app.services.p114_acquisition import validate_re2_archive  # noqa: E402
from app.services.p114_re2_loader import load_pinned_re2_cases  # noqa: E402

BASE = ROOT / "evals/real_datasets/external/p114"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=BASE / "raw/RE2-OB.zip")
    parser.add_argument("--manifest", type=Path, default=BASE / "source-manifest-re2-ob.json")
    parser.add_argument("--hmac-key", type=Path, default=ROOT / "evals/real_datasets/external/p110/raw/.p110-case-id-key")
    parser.add_argument("--model", type=Path, default=BASE / "results/development/fault-knn/full-model.json")
    parser.add_argument("--development-gate", type=Path, default=BASE / "results/development/fault-knn/development-gate.json")
    parser.add_argument("--output", type=Path, default=BASE / "freeze/freeze-manifest.json")
    parser.add_argument("--consumed-receipt", type=Path, default=BASE / "freeze/consumed.json")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"freeze_already_exists:{args.output}")
    if args.consumed_receipt.exists():
        raise FileExistsError(f"acceptance_already_consumed:{args.consumed_receipt}")
    source = validate_re2_archive(args.archive, args.manifest)
    model = _read(args.model)
    development_gate = _read(args.development_gate)
    cases = load_pinned_re2_cases(args.archive, args.manifest, hmac_key=args.hmac_key.read_bytes())
    packets = [case.to_candidate_packet() for case in cases]
    freeze = build_p114_acceptance_freeze(
        source_verification=source,
        model=model,
        packets=packets,
        development_gate=development_gate,
        implementation_hash=p114_implementation_hash(ROOT),
        frozen_at=datetime.now(UTC).isoformat(),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    _write_exclusive(args.output, freeze)
    print(json.dumps({"freeze_hash": freeze["freeze_hash"], "case_count": 90, "scoring_started": False}, sort_keys=True))
    return 0


def _read(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"not_json_object:{path.name}")
    return value


def _write_exclusive(path: Path, value: dict[str, object]) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
