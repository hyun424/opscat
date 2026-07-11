#!/usr/bin/env python3
"""Fit the fixed P113 artifact and freeze the fresh RE1-TT packet set."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services import p113_benchmark_runtime as runtime  # noqa: E402


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--tt-archive", type=Path, default=ROOT / "evals/real_datasets/external/p113/raw/RE1-TT.zip")
    parser.add_argument(
        "--tt-manifest",
        type=Path,
        default=ROOT / "evals/real_datasets/external/p113/source-manifest-re1-tt.json",
    )
    parser.add_argument("--hmac-key", type=Path, default=ROOT / "evals/real_datasets/external/p110/raw/.p110-case-id-key")
    parser.add_argument("--frozen-at", default=None)
    args = parser.parse_args(argv)

    ss, ob = runtime.load_p113_training_corpora(ROOT)
    model = runtime.train_final_p113_model(ss, ob)
    tt_dataset = runtime.load_p113_tt_packet_dataset(
        args.tt_archive,
        args.tt_manifest,
        hmac_key=args.hmac_key.read_bytes(),
    )
    packet_build = runtime.build_all_p113_diagnosis_packets(tt_dataset["candidate_packets"], model)
    frozen = runtime.build_p113_freeze(
        root=ROOT,
        tt_dataset=tt_dataset,
        model_artifact=model,
        diagnosis_packets=packet_build,
        train_case_ids=[case.case_id for case in (*ss, *ob)],
        dev_case_ids=(),
        frozen_at=args.frozen_at,
    )
    taint_ledger = runtime.build_default_taint_ledger()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write(args.output_dir / "p113-model.json", model)
    _write(args.output_dir / "taint-ledger.json", taint_ledger)
    _write(args.output_dir / "freeze-manifest.json", frozen)
    _write(args.output_dir / "packet-hash-manifest.json", packet_build.to_manifest())
    print(
        json.dumps(
            {
                "freeze_hash": frozen["freeze_hash"],
                "model_artifact_hash": frozen["model_hash"],
                "diagnosis_packet_hash": frozen["diagnosis_packet_hash"],
            },
            sort_keys=True,
        )
    )
    return 0


def _write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
