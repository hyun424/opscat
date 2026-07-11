#!/usr/bin/env python3
"""Verify, replay, merge, and score five P111 NVIDIA benchmark batches."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p110_acquisition import validate_local_archive  # noqa: E402
from app.services.p110_candidate_runner import P110RunnerConfig, build_p110_candidate_packet, compute_p110_cache_key, replay_p110_raw_response  # noqa: E402
from app.services.p110_evaluation import evaluate_p110_predictions, stable_hash  # noqa: E402
from app.services.p110_rcaeval import load_re1_ob_cases  # noqa: E402
from app.services.p111_benchmark_guard import benchmark_role  # noqa: E402
from app.services.p111_multistage_rca import build_p111_packet  # noqa: E402
from scripts.run_p111_labeled_benchmark import _implementation_hash, _train_prior  # noqa: E402

_REPLAY_FIELDS = (
    "case_id", "ranked_services", "fault_type", "evidence_refs", "confidence", "abstain",
    "validation_status", "validation_errors", "advisory_actions", "advisory_action_risk", "executed_actions",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=ROOT / "evals/real_datasets/external/p110/raw/RE1-OB.zip")
    parser.add_argument("--source-manifest", type=Path, default=ROOT / "evals/real_datasets/external/p110/source-manifest.json")
    parser.add_argument("--batch-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repetition", type=int, choices=range(1, 6), required=True)
    args = parser.parse_args()

    source = validate_local_archive(args.archive, args.source_manifest)
    key = (args.archive.parent / ".p110-case-id-key").read_bytes()
    all_cases = load_re1_ob_cases(args.archive, hmac_key=key)
    role = benchmark_role(args.repetition)
    if role == "reserve":
        raise SystemExit("reserve repetition is protected")
    cases = [case for case in all_cases if int(case.scorer_only_truth["repetition"]) == args.repetition]
    training_repetitions = tuple(range(1, args.repetition)) if role in {"validation", "blind"} else ()
    fault_prior = _train_prior(all_cases, training_repetitions) if training_repetitions else None
    expected_packets = {
        case.case_id: build_p111_packet(
            build_p110_candidate_packet(case.to_candidate_packet()), fault_prior_artifact=fault_prior
        )
        for case in cases
    }
    truth = [case.to_scorer_truth() for case in cases]
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(args.batch_root.glob("batch-*/candidate-nvidia.json"))]
    if len(reports) != 5:
        raise SystemExit("expected exactly five P111 batch reports")
    provenance = reports[0].get("provenance", {})
    config = P110RunnerConfig(
        model=str(reports[0].get("model", "")),
        prompt_schema_version=str(provenance.get("prompt_schema_version", "")),
        decoding_config=provenance.get("decoding_config", {}),
    )
    predictions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, report in enumerate(reports):
        _validate_report(
            report,
            expected_offset=index * 5,
            expected_packets=expected_packets,
            truth=truth,
            official_source=f"sha256:{source['sha256']}",
            repetition=args.repetition,
            config=config,
            seen=seen,
        )
        predictions.extend(dict(item) for item in report["predictions"])
    if seen != set(expected_packets):
        raise SystemExit("P111 batches do not exactly cover the repetition")
    predictions.sort(key=lambda item: str(item["case_id"]))
    evaluation = evaluate_p110_predictions(truth, predictions)
    merged = {
        "schema_version": "p111.multistage_rca_merged_report.v1",
        "mode": "nvidia",
        "provider": "nvidia",
        "model": config.model,
        "summary": {
            "case_count": len(predictions),
            "valid_count": sum(int(report["summary"]["valid_count"]) for report in reports),
            "fail_closed_count": sum(int(report["summary"]["fail_closed_count"]) for report in reports),
            "action_execution_enabled": False,
        },
        "budget": {"provider_call_count": sum(int(report["budget"]["provider_call_count"]) for report in reports)},
        "safety": {key: sum(int(report["safety"].get(key, 0)) for report in reports) for key in ("truth_leak_count", "harmful_action_count", "executed_action_count")},
        "predictions": predictions,
        "batch_report_hashes": [stable_hash(report) for report in reports],
        "provenance": {
            "official_source": f"sha256:{source['sha256']}",
            "benchmark_role": role,
            "repetition": args.repetition,
            "candidate_packets_hash": stable_hash(expected_packets),
            "scorer_truth_hash": stable_hash(truth),
            "model": config.model,
            "prompt_schema_version": config.prompt_schema_version,
            "decoding_config": dict(config.decoding_config),
        },
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write(args.output_dir / "candidate-nvidia.json", merged)
    _write(args.output_dir / "evaluation-nvidia.json", evaluation)
    if fault_prior is not None:
        _write(args.output_dir / "fault-prior.json", fault_prior)
    print(json.dumps({"role": role, "metrics": evaluation["metrics"], "safety": evaluation["safety"]}, sort_keys=True))
    return 0


def _validate_report(
    report: dict[str, Any], *, expected_offset: int, expected_packets: dict[str, dict[str, Any]], truth: list[dict[str, Any]],
    official_source: str, repetition: int, config: P110RunnerConfig, seen: set[str]
) -> None:
    if report.get("schema_version") != "p111.multistage_rca_report.v1" or report.get("mode") != "nvidia":
        raise SystemExit("invalid P111 runner identity")
    if report.get("model") != config.model or report.get("summary", {}).get("action_execution_enabled") is not False:
        raise SystemExit("inconsistent P111 model or authority")
    if report.get("summary", {}).get("network_calls_enabled") is not True or report.get("safety", {}).get("executed_action_count") != 0:
        raise SystemExit("P111 live-call or authority evidence invalid")
    benchmark = report.get("benchmark_provenance", {})
    if benchmark.get("official_source") != official_source or benchmark.get("repetition") != repetition or benchmark.get("case_offset") != expected_offset:
        raise SystemExit("P111 benchmark provenance mismatch")
    if benchmark.get("implementation_hash") != _implementation_hash():
        raise SystemExit("P111 implementation hash mismatch")
    predictions = report.get("predictions")
    if not isinstance(predictions, list) or len(predictions) != 5:
        raise SystemExit("each P111 batch must contain five predictions")
    ids = [str(item.get("case_id", "")) for item in predictions]
    if len(ids) != len(set(ids)) or seen.intersection(ids) or any(case_id not in expected_packets for case_id in ids):
        raise SystemExit("duplicate or unknown P111 prediction")
    subset_packets = {case_id: expected_packets[case_id] for case_id in ids}
    subset_truth = {str(item["case_id"]): item for item in truth if str(item["case_id"]) in ids}
    if benchmark.get("candidate_packets_hash") != stable_hash(subset_packets) or benchmark.get("scorer_truth_hash") != stable_hash(subset_truth):
        raise SystemExit("P111 packet or truth hash mismatch")
    for prediction in predictions:
        case_id = str(prediction["case_id"])
        packet = expected_packets[case_id]
        if prediction.get("candidate_context") != packet:
            raise SystemExit("P111 candidate context mismatch")
        expected_key = compute_p110_cache_key(model=config.model, packet=packet, prompt_schema_version=config.prompt_schema_version, decoding_config=config.decoding_config)
        if prediction.get("cache_key") != expected_key:
            raise SystemExit("P111 cache key mismatch")
        raw = prediction.get("raw_response")
        if not isinstance(raw, str):
            raise SystemExit("P111 raw response missing")
        if prediction.get("raw_response_sha256") != hashlib.sha256(raw.encode()).hexdigest():
            raise SystemExit("P111 raw response hash mismatch")
        replayed = replay_p110_raw_response(packet, raw, config=config)
        if any(replayed.get(field) != prediction.get(field) for field in _REPLAY_FIELDS):
            raise SystemExit("P111 raw response replay mismatch")
        if prediction.get("executed_actions") != []:
            raise SystemExit("P111 executed action detected")
        provider_stage = prediction.get("provider_stage")
        if provider_stage is not None:
            if not isinstance(provider_stage, dict) or not isinstance(provider_stage.get("raw_response"), str):
                raise SystemExit("P111 provider stage missing")
            provider_raw = provider_stage["raw_response"]
            if provider_stage.get("raw_response_sha256") != hashlib.sha256(provider_raw.encode()).hexdigest():
                raise SystemExit("P111 provider stage hash mismatch")
            provider_replay = replay_p110_raw_response(packet, provider_raw, config=config)
            parsed = provider_stage.get("parsed_prediction")
            if not isinstance(parsed, dict) or any(provider_replay.get(field) != parsed.get(field) for field in _REPLAY_FIELDS):
                raise SystemExit("P111 provider stage replay mismatch")
    seen.update(ids)


def _write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
