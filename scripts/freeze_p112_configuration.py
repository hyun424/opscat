#!/usr/bin/env python3
"""Fit the fixed P112 artifact and freeze paired OB repetition-4 requests."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p112_benchmark_runtime import (  # noqa: E402
    ACCEPTANCE_GATES,
    OB_HASH,
    SS_HASH,
    baseline_request,
    candidate_request,
    full_blind_packets,
    implementation_hash,
    load_p112_corpora,
    train_final_p112_model,
    train_p111_baseline_prior,
)
from app.services.p112_freeze_guard import build_p112_freeze  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    ss, ob = load_p112_corpora(ROOT)
    model = train_final_p112_model(ss, ob)
    baseline_prior = train_p111_baseline_prior(ob)
    baseline_packets, candidate_packets = full_blind_packets(ob, p112_model=model, p111_prior=baseline_prior)
    frozen = build_p112_freeze(
        model_artifact_hash=str(model["artifact_hash"]),
        implementation_hash=implementation_hash(ROOT),
        training_source_hashes=(SS_HASH, OB_HASH),
        blind_source_hash=OB_HASH,
        baseline_packets=baseline_packets,
        candidate_packets=candidate_packets,
        baseline_request=baseline_request(),
        candidate_request=candidate_request(),
        acceptance_gates=ACCEPTANCE_GATES,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write(args.output_dir / "p112-model.json", model)
    _write(args.output_dir / "p111-baseline-prior.json", baseline_prior)
    _write(args.output_dir / "freeze-manifest.json", frozen)
    print(json.dumps({"freeze_hash": frozen["freeze_hash"], "model_artifact_hash": model["artifact_hash"]}, sort_keys=True))
    return 0


def _write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
