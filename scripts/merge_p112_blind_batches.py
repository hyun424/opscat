#!/usr/bin/env python3
"""Merge frozen P112 blind batches and recompute full-corpus evaluation."""

from __future__ import annotations

import argparse
import json
import sys
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
)
from app.services.p112_cross_system_model import stable_hash  # noqa: E402
from app.services.p112_evaluation import evaluate_p112_predictions  # noqa: E402
from app.services.p112_freeze_guard import validate_p112_freeze  # noqa: E402
from app.services.p112_re1_loader import load_pinned_re1_cases  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, action="append", required=True)
    parser.add_argument("--freeze-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    reports = [_read(path / "candidate-nvidia.json") for path in args.batch]
    freeze_hashes = {str(item["benchmark_provenance"]["freeze_hash"]) for item in reports}
    arms = {str(item["benchmark_provenance"]["arm"]) for item in reports}
    run_ids = {str(item["benchmark_provenance"]["run_id"]) for item in reports}
    if len(freeze_hashes) != 1 or len(arms) != 1 or len(run_ids) != 1:
        raise SystemExit("batch provenance mismatch")
    predictions = [prediction for report in reports for prediction in report["predictions"]]
    by_id = {str(item["case_id"]): item for item in predictions}
    if len(by_id) != len(predictions) or len(by_id) != 25:
        raise SystemExit("merged prediction set must contain 25 unique cases")
    key = (ROOT / "evals/real_datasets/external/p110/raw/.p110-case-id-key").read_bytes()
    ob = load_pinned_re1_cases(
        ROOT / "evals/real_datasets/external/p110/raw/RE1-OB.zip",
        ROOT / "evals/real_datasets/external/p112/source-manifest-re1-ob.json",
        hmac_key=key,
    )
    selected = blind_cases(ob)
    expected_ids = {case.case_id for case in selected}
    if set(by_id) != expected_ids:
        raise SystemExit("merged prediction IDs do not match frozen blind set")
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
    arm = next(iter(arms))
    expected_packets = baseline_packets if arm == "baseline" else candidate_packets
    expected_request = baseline_request() if arm == "baseline" else candidate_request()
    packet_by_id = {str(item["case_id"]): item for item in expected_packets}
    _validate_batches(reports, frozen, packet_by_id, expected_request)
    merged = dict(reports[0])
    merged["predictions"] = [by_id[case_id] for case_id in sorted(by_id)]
    merged["provenance"] = {
        **merged.get("provenance", {}),
        "prediction_count": len(predictions),
        "prediction_cache_keys": [
            key
            for report in reports
            for key in report.get("provenance", {}).get("prediction_cache_keys", [])
        ],
        "prediction_provenance": [
            item
            for report in reports
            for item in report.get("provenance", {}).get("prediction_provenance", [])
        ],
    }
    merged["budget"] = {
        **merged.get("budget", {}),
        "max_cases": sum(int(report.get("budget", {}).get("max_cases", 0)) for report in reports),
        "max_calls": sum(int(report.get("budget", {}).get("max_calls", 0)) for report in reports),
        "provider_call_count": sum(
            int(report.get("budget", {}).get("provider_call_count", 0)) for report in reports
        ),
    }
    merged["safety"] = _sum_numeric_mappings(report.get("safety", {}) for report in reports)
    merged["summary"] = {
        **merged["summary"],
        "case_count": 25,
        "prediction_count": 25,
        "valid_count": sum(item.get("validation_status") == "valid" for item in predictions),
        "fail_closed_count": sum(item.get("validation_status") != "valid" for item in predictions),
    }
    merged["benchmark_provenance"] = {
        **merged["benchmark_provenance"],
        "case_offset": 0,
        "selected_case_count": 25,
        "selected_case_ids": sorted(expected_ids),
        "merged_batch_count": len(reports),
        "batch_provenance": [report["benchmark_provenance"] for report in reports],
    }
    evaluation = evaluate_p112_predictions(
        [case.to_scorer_truth() for case in selected],
        merged["predictions"],
        expected_source_hash=OB_HASH,
        allowed_root_services=("adservice", "cartservice", "checkoutservice", "currencyservice", "productcatalogservice"),
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write(args.output_dir / "candidate-nvidia.json", merged)
    _write(args.output_dir / "evaluation-nvidia.json", evaluation)
    print(json.dumps({"arm": next(iter(arms)), "run_id": next(iter(run_ids)), "metrics": evaluation["metrics"]}, sort_keys=True))
    return 0


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _validate_batches(
    reports: list[dict[str, Any]],
    frozen: dict[str, Any],
    packet_by_id: dict[str, dict[str, Any]],
    expected_request: dict[str, Any],
) -> None:
    spans: list[tuple[int, int]] = []
    seen: set[str] = set()
    for report in reports:
        provenance = report.get("benchmark_provenance", {})
        predictions = report.get("predictions", [])
        offset = int(provenance.get("case_offset", -1))
        count = int(provenance.get("selected_case_count", -1))
        ids = [str(item) for item in provenance.get("selected_case_ids", [])]
        prediction_ids = [str(item.get("case_id", "")) for item in predictions]
        if offset < 0 or count <= 0 or count != len(predictions) or ids != prediction_ids:
            raise SystemExit("invalid batch slice provenance")
        if provenance.get("freeze_hash") != frozen.get("freeze_hash"):
            raise SystemExit("batch freeze hash mismatch")
        if provenance.get("implementation_hash") != frozen.get("implementation_hash"):
            raise SystemExit("batch implementation hash mismatch")
        if provenance.get("blind_source_hash") != OB_HASH or provenance.get("request") != expected_request:
            raise SystemExit("batch source/request mismatch")
        config = P110RunnerConfig(
            model=str(expected_request["model"]),
            prompt_schema_version=str(expected_request["prompt_schema_version"]),
            decoding_config=expected_request["decoding_config"],
            max_cases=count,
            max_calls=count,
        )
        for prediction in predictions:
            case_id = str(prediction.get("case_id", ""))
            expected_packet = packet_by_id.get(case_id)
            context = prediction.get("candidate_context")
            expected_packet_sha = stable_hash(expected_packet).removeprefix("sha256:") if expected_packet else ""
            if case_id in seen or expected_packet is None or prediction.get("packet_sha256") != expected_packet_sha:
                raise SystemExit("batch packet hash mismatch or duplicate")
            if isinstance(context, dict) and stable_hash(context) != stable_hash(expected_packet):
                raise SystemExit("batch candidate context mismatch")
            raw = prediction.get("raw_response")
            if not isinstance(raw, (str, dict)):
                raise SystemExit("batch raw response missing")
            replayed = replay_p110_raw_response(expected_packet, raw, config=config)
            if replayed.get("raw_response_sha256") != prediction.get("raw_response_sha256"):
                raise SystemExit("batch raw response hash mismatch")
            seen.add(case_id)
        spans.append((offset, offset + count))
    if sorted(spans) != [(offset, offset + 5) for offset in range(0, 25, 5)]:
        raise SystemExit("batches must be five complete non-overlapping slices")


def _sum_numeric_mappings(values: Any) -> dict[str, int]:
    totals: dict[str, int] = {}
    for value in values:
        for key, item in value.items():
            if isinstance(item, (int, float)) and not isinstance(item, bool):
                totals[str(key)] = totals.get(str(key), 0) + int(item)
    return totals


if __name__ == "__main__":
    raise SystemExit(main())
