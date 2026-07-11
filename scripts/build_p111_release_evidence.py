#!/usr/bin/env python3
"""Recompute paired P111 blind evidence from sealed merged artifacts."""

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
from app.services.p111_benchmark_guard import validate_frozen_run  # noqa: E402
from app.services.p111_comparison import compare_p111_predictions, measure_repeat_agreement  # noqa: E402
from app.services.p111_multistage_rca import build_p111_packet  # noqa: E402
from app.services.p111_release_evidence import produce_p111_release_evidence  # noqa: E402
from scripts.run_p111_labeled_benchmark import _implementation_hash, _train_prior  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=ROOT / "evals/real_datasets/external/p110/raw/RE1-OB.zip")
    parser.add_argument("--source-manifest", type=Path, default=ROOT / "evals/real_datasets/external/p110/source-manifest.json")
    parser.add_argument("--freeze-manifest", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--repeat", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    source = validate_local_archive(args.archive, args.source_manifest)
    key = (args.archive.parent / ".p110-case-id-key").read_bytes()
    all_cases = load_re1_ob_cases(args.archive, hmac_key=key)
    blind = [case for case in all_cases if int(case.scorer_only_truth["repetition"]) == 3]
    truth = [case.to_scorer_truth() for case in blind]
    prior = _train_prior(all_cases, (1, 2))
    packets = [
        build_p111_packet(build_p110_candidate_packet(case.to_candidate_packet()), fault_prior_artifact=prior)
        for case in blind
    ]
    candidate = _load_predictions(args.candidate)
    repeat = _load_predictions(args.repeat)
    baseline = _load_predictions(args.baseline)
    candidate_doc = json.loads(args.candidate.read_text(encoding="utf-8"))
    provenance = candidate_doc.get("provenance", {})
    config = P110RunnerConfig(
        model=str(candidate_doc.get("model", "")),
        prompt_schema_version=str(provenance.get("prompt_schema_version", "")),
        decoding_config=provenance.get("decoding_config", {}),
    )
    manifest = json.loads(args.freeze_manifest.read_text(encoding="utf-8"))
    validate_frozen_run(
        manifest, target_repetition=3, model=config.model, prompt_schema_version=config.prompt_schema_version,
        decoding_config=config.decoding_config, implementation_hash=_implementation_hash(),
        official_source_hash=f"sha256:{source['sha256']}", candidate_packets=packets,
    )
    comparison = compare_p111_predictions(truth, baseline, candidate, benchmark_role="blind")
    agreement = measure_repeat_agreement(candidate, repeat)
    release = produce_p111_release_evidence(
        comparison=comparison, repeat_agreement=agreement, freeze_verified=True, cryptographic_review=None
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write(args.output_dir / "comparison.json", comparison)
    _write(args.output_dir / "repeat-agreement.json", agreement)
    _write(args.output_dir / "release.json", release)
    print(json.dumps({"deltas": comparison["metric_deltas"], "repeat": agreement, "release_qualified": release["release_qualified"], "gates": release["gates"]}, sort_keys=True))
    return 0


def _load_predictions(path: Path) -> list[dict[str, object]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    predictions = value.get("predictions")
    if not isinstance(predictions, list) or len(predictions) != 25:
        raise SystemExit(f"expected 25 predictions: {path}")
    return predictions


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
