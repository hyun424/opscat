#!/usr/bin/env python3
"""Recompute sealed P112 paired blind evidence and fail-closed release status."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p110_candidate_runner import P110RunnerConfig, replay_p110_raw_response  # noqa: E402
from app.services.p112_benchmark_runtime import (  # noqa: E402
    OB_HASH,
    SS_HASH,
    baseline_request,
    blind_cases,
    candidate_request,
    full_blind_packets,
    implementation_hash,
    load_p112_corpora,
)
from app.services.p112_comparison import compare_p112_predictions, measure_repeat_agreement  # noqa: E402
from app.services.p112_freeze_guard import validate_p112_freeze  # noqa: E402
from app.services.p112_release_evidence import produce_p112_release_evidence, request_envelope_complete  # noqa: E402

_SEMANTIC_FIELDS = (
    "case_id",
    "ranked_services",
    "fault_type",
    "evidence_refs",
    "confidence",
    "abstain",
    "validation_status",
    "validation_errors",
    "advisory_actions",
    "advisory_action_risk",
    "executed_actions",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-dir", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--repeat", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cryptographic-review", type=Path)
    args = parser.parse_args()
    if args.candidate.resolve() == args.repeat.resolve():
        raise SystemExit("candidate and repeat reports must be distinct files")

    ss, ob = load_p112_corpora(ROOT)
    model = _read(args.freeze_dir / "p112-model.json")
    prior = _read(args.freeze_dir / "p111-baseline-prior.json")
    frozen = _read(args.freeze_dir / "freeze-manifest.json")
    baseline_packets, candidate_packets = full_blind_packets(ob, p112_model=model, p111_prior=prior)
    validate_p112_freeze(
        frozen,
        model_artifact_hash=str(model["artifact_hash"]),
        implementation_hash=implementation_hash(ROOT),
        training_source_hashes=(SS_HASH, OB_HASH),
        blind_source_hash=OB_HASH,
        baseline_packets=baseline_packets,
        candidate_packets=candidate_packets,
        baseline_request=baseline_request(),
        candidate_request=candidate_request(),
    )

    baseline_doc = _load_report(args.baseline, frozen, "baseline")
    candidate_doc = _load_report(args.candidate, frozen, "candidate")
    repeat_doc = _load_report(args.repeat, frozen, "candidate")
    candidate_run_id = str(candidate_doc["benchmark_provenance"].get("run_id", ""))
    repeat_run_id = str(repeat_doc["benchmark_provenance"].get("run_id", ""))
    if not candidate_run_id or not repeat_run_id or candidate_run_id == repeat_run_id:
        raise SystemExit("candidate and repeat reports must have distinct non-empty run IDs")
    baseline_predictions = baseline_doc["predictions"]
    candidate_predictions = candidate_doc["predictions"]
    repeat_predictions = repeat_doc["predictions"]
    selected = blind_cases(ob)
    truth = [case.to_scorer_truth() for case in selected]
    allowed_services = tuple(sorted({str(case.scorer_only_truth["root_service"]) for case in selected}))
    comparison = compare_p112_predictions(
        truth,
        baseline_predictions,
        candidate_predictions,
        expected_source_hash=OB_HASH,
        allowed_root_services=allowed_services,
        benchmark_role="blind",
    )
    agreement = measure_repeat_agreement(candidate_predictions, repeat_predictions)
    replay_integrity = {
        "baseline_request_complete": request_envelope_complete(baseline_doc["benchmark_provenance"].get("request")),
        "candidate_request_complete": request_envelope_complete(candidate_doc["benchmark_provenance"].get("request")),
        "baseline_raw_replay": _verify_raw_replay(baseline_predictions, baseline_request()),
        "candidate_raw_replay": _verify_raw_replay(candidate_predictions, candidate_request()),
        "candidate_repeat_raw_replay": _verify_raw_replay(repeat_predictions, candidate_request()),
    }
    review = _read(args.cryptographic_review) if args.cryptographic_review else None
    release = produce_p112_release_evidence(
        comparison=comparison,
        repeat_agreement=agreement,
        freeze_verified=True,
        replay_integrity=replay_integrity,
        cryptographic_review=review,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write(args.output_dir / "comparison.json", comparison)
    _write(args.output_dir / "repeat-agreement.json", agreement)
    _write(args.output_dir / "replay-integrity.json", replay_integrity)
    _write(args.output_dir / "release.json", release)
    print(
        json.dumps(
            {
                "deltas": comparison["metric_deltas"],
                "metrics": comparison["candidate_metrics"],
                "repeat": agreement,
                "replay_integrity": replay_integrity,
                "release_qualified": release["release_qualified"],
                "gates": release["gates"],
            },
            sort_keys=True,
        )
    )
    return 0


def _load_report(path: Path, frozen: Mapping[str, Any], arm: str) -> dict[str, Any]:
    report = _read(path)
    predictions = report.get("predictions")
    provenance = report.get("benchmark_provenance")
    if not isinstance(predictions, list) or len(predictions) != 25:
        raise SystemExit(f"expected 25 predictions: {path}")
    if not isinstance(provenance, Mapping):
        raise SystemExit(f"missing benchmark provenance: {path}")
    if provenance.get("arm") != arm or provenance.get("benchmark_role") != "blind":
        raise SystemExit(f"invalid benchmark role/arm: {path}")
    if provenance.get("freeze_hash") != frozen.get("freeze_hash"):
        raise SystemExit(f"freeze hash mismatch: {path}")
    if provenance.get("implementation_hash") != frozen.get("implementation_hash"):
        raise SystemExit(f"implementation hash mismatch: {path}")
    return report


def _verify_raw_replay(predictions: Sequence[Mapping[str, Any]], request: Mapping[str, Any]) -> bool:
    config = P110RunnerConfig(
        model=str(request["model"]),
        prompt_schema_version=str(request["prompt_schema_version"]),
        decoding_config=request["decoding_config"],
        max_cases=len(predictions),
        max_calls=len(predictions),
    )
    for prediction in predictions:
        packet = prediction.get("candidate_context")
        raw = prediction.get("raw_response")
        provider_stage = prediction.get("provider_stage")
        if not isinstance(packet, Mapping) or not isinstance(raw, (Mapping, str)) or not isinstance(provider_stage, Mapping):
            return False
        replayed = replay_p110_raw_response(packet, raw, config=config)
        if _projection(replayed) != _projection(prediction):
            return False
        if replayed.get("raw_response_sha256") != prediction.get("raw_response_sha256"):
            return False
        provider_raw = provider_stage.get("raw_response")
        if not isinstance(provider_raw, (Mapping, str)):
            return False
        provider_replayed = replay_p110_raw_response(packet, provider_raw, config=config)
        if provider_replayed.get("raw_response_sha256") != provider_stage.get("raw_response_sha256"):
            return False
        parsed = provider_stage.get("parsed_prediction")
        if isinstance(parsed, Mapping) and _projection(provider_replayed) != _projection(parsed):
            return False
        if "parsed_ranked_services" in provider_stage and provider_replayed.get("ranked_services") != provider_stage.get("parsed_ranked_services"):
            return False
        if "parsed_fault_type" in provider_stage and provider_replayed.get("fault_type") != provider_stage.get("parsed_fault_type"):
            return False
    return True


def _projection(value: Mapping[str, Any]) -> dict[str, Any]:
    return {field: value.get(field) for field in _SEMANTIC_FIELDS}


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
