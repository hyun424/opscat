#!/usr/bin/env python3
"""Merge and replay P110 single-pass baseline batches for P111 comparison."""

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

_FIELDS = ("case_id", "ranked_services", "fault_type", "evidence_refs", "confidence", "abstain", "advisory_actions", "validation_status", "validation_errors", "raw_response_sha256")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=ROOT / "evals/real_datasets/external/p110/raw/RE1-OB.zip")
    parser.add_argument("--source-manifest", type=Path, default=ROOT / "evals/real_datasets/external/p110/source-manifest.json")
    parser.add_argument("--batch-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repetition", type=int, choices=range(1, 6), required=True)
    args = parser.parse_args()
    if benchmark_role(args.repetition) == "reserve":
        raise SystemExit("reserve repetition is protected")

    source = validate_local_archive(args.archive, args.source_manifest)
    key = (args.archive.parent / ".p110-case-id-key").read_bytes()
    cases = [case for case in load_re1_ob_cases(args.archive, hmac_key=key) if int(case.scorer_only_truth["repetition"]) == args.repetition]
    packets = {case.case_id: build_p110_candidate_packet(case.to_candidate_packet()) for case in cases}
    truth = [case.to_scorer_truth() for case in cases]
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(args.batch_root.glob("batch-*/candidate-nvidia.json"))]
    if len(reports) != 5:
        raise SystemExit("expected exactly five P110 baseline batches")
    provenance = reports[0].get("provenance", {})
    config = P110RunnerConfig(
        model=str(reports[0].get("model", "")), prompt_schema_version=str(provenance.get("prompt_schema_version", "")),
        decoding_config=provenance.get("decoding_config", {}),
    )
    predictions: list[dict[str, Any]] = []
    seen: set[str] = set()
    truth_by_id = {str(item["case_id"]): item for item in truth}
    for index, report in enumerate(reports):
        if report.get("schema_version") != "p110.candidate_runner_report.v1" or report.get("mode") != "nvidia":
            raise SystemExit("invalid P110 baseline report")
        benchmark = report.get("benchmark_provenance", {})
        if benchmark.get("official_source") != f"sha256:{source['sha256']}" or benchmark.get("repetition") != args.repetition or benchmark.get("case_offset") != index * 5:
            raise SystemExit("P110 baseline benchmark provenance mismatch")
        batch = report.get("predictions")
        if not isinstance(batch, list) or len(batch) != 5:
            raise SystemExit("P110 baseline batch size mismatch")
        ids = [str(item.get("case_id", "")) for item in batch]
        if seen.intersection(ids) or any(case_id not in packets for case_id in ids):
            raise SystemExit("duplicate or unknown P110 baseline case")
        if benchmark.get("candidate_packets_hash") != stable_hash({case_id: packets[case_id] for case_id in ids}):
            raise SystemExit("P110 baseline packet hash mismatch")
        if benchmark.get("scorer_truth_hash") != stable_hash({case_id: truth_by_id[case_id] for case_id in ids}):
            raise SystemExit("P110 baseline truth hash mismatch")
        for prediction in batch:
            case_id = str(prediction["case_id"])
            packet = packets[case_id]
            raw = prediction.get("raw_response")
            if not isinstance(raw, str) or hashlib.sha256(raw.encode()).hexdigest() != prediction.get("raw_response_sha256"):
                raise SystemExit("P110 baseline raw response hash mismatch")
            cache_key = compute_p110_cache_key(model=config.model, packet=packet, prompt_schema_version=config.prompt_schema_version, decoding_config=config.decoding_config)
            if prediction.get("cache_key") != cache_key or prediction.get("candidate_context") != packet or prediction.get("executed_actions") != []:
                raise SystemExit("P110 baseline provenance mismatch")
            replay = replay_p110_raw_response(packet, raw, config=config)
            if any(replay.get(field) != prediction.get(field) for field in _FIELDS):
                raise SystemExit("P110 baseline replay mismatch")
            predictions.append(dict(prediction))
        seen.update(ids)
    if seen != set(packets):
        raise SystemExit("P110 baseline does not cover the full repetition")
    predictions.sort(key=lambda item: str(item["case_id"]))
    evaluation = evaluate_p110_predictions(truth, predictions)
    merged = {
        "schema_version": "p111.p110_baseline_merged.v1", "model": config.model,
        "predictions": predictions, "batch_report_hashes": [stable_hash(report) for report in reports],
        "provenance": {"official_source": f"sha256:{source['sha256']}", "repetition": args.repetition, "candidate_packets_hash": stable_hash(packets), "scorer_truth_hash": stable_hash(truth)},
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write(args.output_dir / "candidate-nvidia.json", merged)
    _write(args.output_dir / "evaluation-nvidia.json", evaluation)
    print(json.dumps({"metrics": evaluation["metrics"], "safety": evaluation["safety"]}, sort_keys=True))
    return 0


def _write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
