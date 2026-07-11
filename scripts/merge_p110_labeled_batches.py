#!/usr/bin/env python3
"""Merge isolated P110 candidate batches and recompute the full holdout score."""

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
from app.services.p110_candidate_runner import (  # noqa: E402
    P110RunnerConfig,
    build_p110_candidate_packet,
    compute_p110_cache_key,
    replay_p110_raw_response,
)
from app.services.p110_evaluation import evaluate_p110_predictions, stable_hash  # noqa: E402
from app.services.p110_rcaeval import load_re1_ob_cases  # noqa: E402
from app.services.p110_release_evidence import produce_p110_release_evidence  # noqa: E402

DEFAULT_ROOT = ROOT / "evals/real_datasets/external/p110"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ROOT / "raw/RE1-OB.zip")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_ROOT / "source-manifest.json")
    parser.add_argument("--batch-root", type=Path, default=DEFAULT_ROOT / "results")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_ROOT / "results/final")
    parser.add_argument("--review-json", type=Path)
    args = parser.parse_args()

    source = validate_local_archive(args.archive, args.manifest)
    key = (args.archive.parent / ".p110-case-id-key").read_bytes()
    cases = [case for case in load_re1_ob_cases(args.archive, hmac_key=key) if int(case.scorer_only_truth["repetition"]) == 5]
    expected_packets = {case.case_id: build_p110_candidate_packet(case.to_candidate_packet()) for case in cases}
    truth_cases = [case.to_scorer_truth() for case in cases]
    predictions, candidate_report = _merge_candidate_reports(
        args.batch_root,
        expected_packets=expected_packets,
        expected_truth=truth_cases,
        official_source=f"sha256:{source['sha256']}",
    )
    if len(predictions) != 25 or len({str(item.get("case_id", "")) for item in predictions}) != 25:
        raise SystemExit("merged P110 batches must contain exactly 25 unique predictions")
    evaluation = evaluate_p110_predictions(truth_cases, predictions)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    candidate_path = args.output_dir / "candidate-nvidia.json"
    evaluation_path = args.output_dir / "evaluation-nvidia.json"
    _write_json(candidate_path, candidate_report)
    _write_json(evaluation_path, evaluation)
    artifacts = {
        "official_source": f"sha256:{source['sha256']}",
        "labeled_cases": stable_hash(truth_cases),
        "scorer_truth": evaluation["scorer_truth_hash"],
        "candidate_outputs": f"sha256:{_sha256_file(candidate_path)}",
        "evaluation_report": evaluation["evaluation_hash"],
        "implementation_revision": _implementation_hash(),
    }
    review = json.loads(args.review_json.read_text(encoding="utf-8")) if args.review_json else None
    release = produce_p110_release_evidence(
        producer_id="opscat-p110-cli",
        evaluation_report=evaluation,
        official_source_hash_verified=True,
        bound_artifact_hashes=artifacts,
        independent_review=review,
    )
    _write_json(args.output_dir / "release-nvidia.json", release)
    _write_json(args.output_dir / "artifact-hashes.json", artifacts)
    print(json.dumps({"metrics": evaluation["metrics"], "safety": evaluation["safety"], "release_qualified": release["release_qualified"]}, sort_keys=True))
    return 0


def _merge_candidate_reports(
    root: Path,
    *,
    expected_packets: dict[str, dict[str, Any]],
    expected_truth: list[dict[str, Any]],
    official_source: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    report_paths = sorted(root.glob("batch-*/candidate-nvidia.json"))
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in report_paths]
    if len(reports) != 5:
        raise SystemExit("expected exactly five P110 batch reports")
    model = str(reports[0].get("model", ""))
    provenance = reports[0].get("provenance")
    if not model or not isinstance(provenance, dict):
        raise SystemExit("P110 batch report is missing runner provenance")
    prompt_schema_version = str(provenance.get("prompt_schema_version", ""))
    decoding_config = provenance.get("decoding_config")
    if not prompt_schema_version or not isinstance(decoding_config, dict):
        raise SystemExit("P110 batch report is missing prompt/decoding provenance")
    config = P110RunnerConfig(model=model, prompt_schema_version=prompt_schema_version, decoding_config=decoding_config)
    expected_ids = set(expected_packets)
    expected_truth_by_id = {str(item["case_id"]): item for item in expected_truth}
    seen_ids: set[str] = set()
    expected_offsets = list(range(0, 25, 5))
    for index, (path, report) in enumerate(zip(report_paths, reports, strict=True)):
        _validate_batch_report(
            path,
            report,
            expected_offset=expected_offsets[index],
            expected_packets=expected_packets,
            expected_truth_by_id=expected_truth_by_id,
            official_source=official_source,
            config=config,
            seen_ids=seen_ids,
        )
    if seen_ids != expected_ids:
        raise SystemExit("P110 batch reports do not exactly cover the sealed holdout")
    predictions = [dict(item) for report in reports for item in report.get("predictions", [])]
    predictions.sort(key=lambda item: str(item.get("case_id", "")))
    return predictions, {
        "schema_version": "p110.candidate_runner_merged_report.v1",
        "mode": "nvidia",
        "provider": "nvidia",
        "model": model,
        "summary": {
            "case_count": len(predictions),
            "valid_count": sum(int(report["summary"]["valid_count"]) for report in reports),
            "fail_closed_count": sum(int(report["summary"]["fail_closed_count"]) for report in reports),
            "action_execution_enabled": False,
        },
        "budget": {"provider_call_count": sum(int(report["budget"]["provider_call_count"]) for report in reports)},
        "safety": {
            key: sum(int(report["safety"].get(key, 0)) for report in reports)
            for key in ("truth_leak_count", "harmful_action_count", "executed_action_count")
        },
        "predictions": predictions,
        "batch_report_hashes": [stable_hash(report) for report in reports],
        "provenance": {
            "official_source": official_source,
            "scorer_truth_hash": stable_hash(expected_truth),
            "candidate_packets_hash": stable_hash(expected_packets),
            "model": model,
            "prompt_schema_version": prompt_schema_version,
            "decoding_config": decoding_config,
            "batch_paths": [path.relative_to(root).as_posix() for path in report_paths],
        },
    }


def _validate_batch_report(
    path: Path,
    report: dict[str, Any],
    *,
    expected_offset: int,
    expected_packets: dict[str, dict[str, Any]],
    expected_truth_by_id: dict[str, dict[str, Any]],
    official_source: str,
    config: P110RunnerConfig,
    seen_ids: set[str],
) -> None:
    if report.get("schema_version") != "p110.candidate_runner_report.v1" or report.get("mode") != "nvidia" or report.get("provider") != "nvidia":
        raise SystemExit(f"invalid P110 batch runner identity: {path}")
    if report.get("model") != config.model or report.get("summary", {}).get("action_execution_enabled") is not False:
        raise SystemExit(f"inconsistent P110 batch model/authority: {path}")
    if report.get("summary", {}).get("network_calls_enabled") is not True:
        raise SystemExit(f"P110 NVIDIA batch lacks live-call evidence: {path}")
    if report.get("safety", {}).get("executed_action_count") != 0:
        raise SystemExit(f"P110 batch contains executed actions: {path}")
    runner_provenance = report.get("provenance")
    if not isinstance(runner_provenance, dict) or runner_provenance.get("model") != config.model:
        raise SystemExit(f"invalid P110 runner provenance: {path}")
    if runner_provenance.get("prompt_schema_version") != config.prompt_schema_version or runner_provenance.get("decoding_config") != dict(config.decoding_config):
        raise SystemExit(f"inconsistent P110 prompt/decoding provenance: {path}")
    benchmark = report.get("benchmark_provenance")
    if not isinstance(benchmark, dict):
        raise SystemExit(f"missing P110 benchmark provenance: {path}")
    predictions = report.get("predictions")
    if not isinstance(predictions, list) or len(predictions) != 5:
        raise SystemExit(f"P110 batch must contain five predictions: {path}")
    batch_ids = sorted(str(item.get("case_id", "")) for item in predictions if isinstance(item, dict))
    if (
        benchmark.get("official_source") != official_source
        or benchmark.get("repetition") != 5
        or benchmark.get("case_offset") != expected_offset
        or benchmark.get("selected_case_count") != 5
        or benchmark.get("selected_case_ids") != batch_ids
        or benchmark.get("model") != config.model
        or benchmark.get("prompt_schema_version") != config.prompt_schema_version
        or benchmark.get("decoding_config") != dict(config.decoding_config)
    ):
        raise SystemExit(f"P110 batch benchmark provenance mismatch: {path}")
    packets = [expected_packets[case_id] for case_id in batch_ids if case_id in expected_packets]
    truths = [expected_truth_by_id[case_id] for case_id in batch_ids if case_id in expected_truth_by_id]
    if len(packets) != 5 or benchmark.get("candidate_packets_hash") != stable_hash({case_id: expected_packets[case_id] for case_id in batch_ids}):
        raise SystemExit(f"P110 batch packet binding mismatch: {path}")
    if benchmark.get("scorer_truth_hash") != stable_hash({str(item["case_id"]): item for item in truths}):
        raise SystemExit(f"P110 batch scorer-truth binding mismatch: {path}")
    for prediction in predictions:
        if not isinstance(prediction, dict):
            raise SystemExit(f"invalid P110 prediction object: {path}")
        case_id = str(prediction.get("case_id", ""))
        if case_id in seen_ids or case_id not in expected_packets:
            raise SystemExit(f"duplicate or unknown P110 case id: {case_id}")
        seen_ids.add(case_id)
        packet = expected_packets[case_id]
        expected_cache_key = compute_p110_cache_key(
            model=config.model,
            packet=packet,
            prompt_schema_version=config.prompt_schema_version,
            decoding_config=config.decoding_config,
        )
        raw_hash = str(prediction.get("raw_response_sha256", ""))
        raw_response = prediction.get("raw_response")
        if (
            prediction.get("validation_status") != "valid"
            or prediction.get("candidate_context") != packet
            or prediction.get("cache_key") != expected_cache_key
            or prediction.get("model") != config.model
            or prediction.get("prompt_schema_version") != config.prompt_schema_version
            or prediction.get("decoding_config") != dict(config.decoding_config)
            or len(raw_hash) != 64
            or any(char not in "0123456789abcdef" for char in raw_hash)
            or not isinstance(raw_response, (str, dict))
            or _raw_response_hash(raw_response) != raw_hash
            or prediction.get("executed_actions") != []
        ):
            raise SystemExit(f"P110 prediction provenance mismatch: {case_id}")
        replay = replay_p110_raw_response(packet, raw_response, config=config)
        replay_fields = (
            "case_id",
            "ranked_services",
            "fault_type",
            "evidence_refs",
            "confidence",
            "abstain",
            "advisory_actions",
            "validation_status",
            "validation_errors",
            "raw_response_sha256",
        )
        if any(replay.get(field) != prediction.get(field) for field in replay_fields):
            raise SystemExit(f"P110 prediction does not replay from sealed raw response: {case_id}")


def _raw_response_hash(value: str | dict[str, Any]) -> str:
    if isinstance(value, str):
        encoded = value
    else:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _implementation_hash() -> str:
    paths = sorted((ROOT / "app/services").glob("p110_*.py")) + [Path(__file__), ROOT / "scripts/run_p110_labeled_benchmark.py"]
    return stable_hash({path.relative_to(ROOT).as_posix(): _sha256_file(path) for path in paths})


if __name__ == "__main__":
    raise SystemExit(main())
