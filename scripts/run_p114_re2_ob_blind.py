#!/usr/bin/env python3
"""Run the one-shot frozen deterministic P114 RE2-OB acceptance score."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p110_evaluation import stable_hash  # noqa: E402
from app.services.p114_acceptance import (  # noqa: E402
    P114RuntimeSafetyLedger,
    build_p114_acceptance_lattices,
    evaluate_p114_re2_ob_blind,
    p114_implementation_hash,
    validate_p114_acceptance_freeze,
)
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
    parser.add_argument("--freeze", type=Path, default=BASE / "freeze/freeze-manifest.json")
    parser.add_argument("--replay", type=Path, default=BASE / "freeze/replay-lattices.json")
    parser.add_argument("--consumed-receipt", type=Path, default=BASE / "freeze/consumed.json")
    parser.add_argument("--output-dir", type=Path, default=BASE / "results/blind/final")
    args = parser.parse_args()
    safety_ledger = P114RuntimeSafetyLedger()
    output_paths = [
        args.output_dir / "evaluation.json",
        args.output_dir / "acceptance-gate.json",
        args.output_dir / "summary.json",
    ]
    if args.consumed_receipt.exists() or any(path.exists() for path in output_paths):
        raise FileExistsError("acceptance_already_consumed")
    source = validate_re2_archive(args.archive, args.manifest)
    model = _read(args.model)
    development_gate = _read(args.development_gate)
    freeze = _read(args.freeze)
    replay = _read(args.replay)
    replay_hash = str(replay.get("replay_hash", ""))
    if replay_hash != stable_hash({key: value for key, value in replay.items() if key != "replay_hash"}):
        raise ValueError("invalid_replay_hash")
    if replay.get("freeze_hash") != freeze.get("freeze_hash"):
        raise ValueError("replay_freeze_mismatch")
    replay_lattices = _mapping_sequence(replay.get("lattices"))
    cases = load_pinned_re2_cases(args.archive, args.manifest, hmac_key=args.hmac_key.read_bytes())
    packets = [case.to_candidate_packet() for case in cases]
    validate_p114_acceptance_freeze(
        freeze,
        source_verification=source,
        model=model,
        packets=packets,
        development_gate=development_gate,
        implementation_hash=p114_implementation_hash(ROOT),
    )
    consumed_at = datetime.now(UTC).isoformat()
    receipt: dict[str, Any] = {
        "schema_version": "p114.re2_ob_consumed_receipt.v1",
        "status": "score_started",
        "freeze_hash": str(freeze["freeze_hash"]),
        "replay_hash": replay_hash,
        "implementation_hash": p114_implementation_hash(ROOT),
        "consumed_at": consumed_at,
    }
    receipt["receipt_hash"] = stable_hash(receipt)
    args.consumed_receipt.parent.mkdir(parents=True, exist_ok=True)
    _write_exclusive(args.consumed_receipt, receipt)

    lattices = build_p114_acceptance_lattices(packets, model)
    source_after = validate_re2_archive(args.archive, args.manifest)
    report, gate = evaluate_p114_re2_ob_blind(
        cases,
        lattices,
        replay_lattices,
        freeze,
        scored_at=consumed_at,
        source_sha256_after="sha256:" + str(source_after["sha256"]),
        runtime_safety=safety_ledger.snapshot(),
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write_exclusive(args.output_dir / "evaluation.json", report)
    _write_exclusive(args.output_dir / "acceptance-gate.json", gate)
    summary = {
        "freeze_hash": freeze["freeze_hash"],
        "evaluation_hash": report["evaluation_hash"],
        "gate_hash": gate["gate_hash"],
        "acceptance_passed": gate["passed"],
        "case_count": 90,
        "consumed_receipt_hash": receipt["receipt_hash"],
        "replay_hash": replay_hash,
    }
    _write_exclusive(args.output_dir / "summary.json", summary)
    print(json.dumps(summary, sort_keys=True))
    return 0


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"not_json_object:{path.name}")
    return value


def _mapping_sequence(value: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list):
        raise ValueError("replay_lattices_not_list")
    if not all(isinstance(item, dict) for item in value):
        raise ValueError("replay_lattice_not_object")
    return tuple(value)


def _write_exclusive(path: Path, value: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
