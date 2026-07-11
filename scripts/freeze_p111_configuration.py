#!/usr/bin/env python3
"""Freeze the selected P111 configuration before blind scoring."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p110_acquisition import validate_local_archive  # noqa: E402
from app.services.p110_candidate_runner import P110RunnerConfig, build_p110_candidate_packet  # noqa: E402
from app.services.p110_rcaeval import load_re1_ob_cases  # noqa: E402
from app.services.p111_benchmark_guard import create_freeze_manifest  # noqa: E402
from app.services.p111_multistage_rca import P111_PROMPT_SCHEMA_VERSION, build_p111_packet  # noqa: E402
from scripts.run_p111_labeled_benchmark import DEFAULT_DECODING, _implementation_hash, _train_prior  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=ROOT / "evals/real_datasets/external/p110/raw/RE1-OB.zip")
    parser.add_argument("--source-manifest", type=Path, default=ROOT / "evals/real_datasets/external/p110/source-manifest.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="nvidia/nemotron-3-ultra-550b-a55b")
    parser.add_argument("--selected-on-repetition", type=int, default=2)
    parser.add_argument("--target-repetition", type=int, default=3)
    args = parser.parse_args()

    source = validate_local_archive(args.archive, args.source_manifest)
    key = (args.archive.parent / ".p110-case-id-key").read_bytes()
    all_cases = load_re1_ob_cases(args.archive, hmac_key=key)
    cases = [case for case in all_cases if int(case.scorer_only_truth["repetition"]) == args.target_repetition]
    training_repetitions = tuple(range(1, args.target_repetition))
    fault_prior = _train_prior(all_cases, training_repetitions)
    packets = [
        build_p111_packet(build_p110_candidate_packet(case.to_candidate_packet()), fault_prior_artifact=fault_prior)
        for case in cases
    ]
    config = P110RunnerConfig(model=args.model, prompt_schema_version=P111_PROMPT_SCHEMA_VERSION, decoding_config=DEFAULT_DECODING)
    manifest = create_freeze_manifest(
        selected_on_repetition=args.selected_on_repetition,
        model=config.model,
        prompt_schema_version=config.prompt_schema_version,
        decoding_config=config.decoding_config,
        implementation_hash=_implementation_hash(),
        official_source_hash=f"sha256:{source['sha256']}",
        candidate_packets=packets,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"freeze_hash": manifest["freeze_hash"], "target_repetition": args.target_repetition}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
