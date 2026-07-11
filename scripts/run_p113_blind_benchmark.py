#!/usr/bin/env python3
"""Run the frozen P113 blind benchmark in diagnosis or narrative mode."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services import p113_benchmark_runtime as runtime  # noqa: E402
from app.services.p110_candidate_runner import NvidiaP110CandidateProvider  # noqa: E402
from app.services.p110_evaluation import stable_hash  # noqa: E402
from app.services.p113_blind_dataset import evaluate_p113_blind_predictions  # noqa: E402
from app.services.p113_decoupled_rca import P113_SYSTEM_PROMPT, P113Config, replay_p113_raw_response, run_p113_decoupled_rca  # noqa: E402
from app.services.p113_evaluation import evaluate_p113_results  # noqa: E402
from app.services.p113_governance import select_p113_narrative_subset  # noqa: E402

DEFAULT_TT_ARCHIVE = ROOT / "evals/real_datasets/external/p113/raw/RE1-TT.zip"
DEFAULT_TT_MANIFEST = ROOT / "evals/real_datasets/external/p113/source-manifest-re1-tt.json"
DEFAULT_HMAC_KEY = ROOT / "evals/real_datasets/external/p110/raw/.p110-case-id-key"


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    _load_env(args.env_file)
    try:
        if args.mode == "diagnosis":
            summary = _run_diagnosis(args)
        else:
            summary = _run_narrative(args)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f"p113_blind_benchmark_failed:{exc}\n")
    print(json.dumps(summary, sort_keys=True))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("diagnosis", "narrative"))
    parser.add_argument("--freeze-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--tt-archive", type=Path, default=DEFAULT_TT_ARCHIVE)
    parser.add_argument("--tt-manifest", type=Path, default=DEFAULT_TT_MANIFEST)
    parser.add_argument("--hmac-key", type=Path, default=DEFAULT_HMAC_KEY)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--scoring-started-at", default=None)
    parser.add_argument("--diagnosis-gate-report", type=Path)
    parser.add_argument("--case-offset", type=int, default=0)
    parser.add_argument("--max-cases", type=int, default=25)
    return parser


def _run_diagnosis(args: argparse.Namespace) -> dict[str, Any]:
    ctx = _build_and_validate_context(args)
    scoring_started_at = str(args.scoring_started_at or datetime.now(UTC).isoformat())
    p112_predictions = [_prediction_from_p112_packet(packet) for packet in ctx["packet_build"].p112_baseline_packets]
    p113_results = [
        replay_p113_raw_response(packet, {"__provider_error__": "narrative_disabled"}, config=P113Config(model=runtime.MODEL, decoding_config=runtime.DECODING), latency_ms=0)
        for packet in ctx["packet_build"].p113_packets
    ]
    p113_predictions = [_prediction_from_p113_result(result) for result in p113_results]

    baseline_eval = evaluate_p113_blind_predictions(
        args.tt_archive,
        args.tt_manifest,
        p112_predictions,
        frozen=ctx["frozen"],
        train_case_ids=ctx["train_case_ids"],
        dev_case_ids=(),
        hmac_key=ctx["hmac_key"],
        scoring_started_at=scoring_started_at,
    )
    diagnosis_eval = evaluate_p113_blind_predictions(
        args.tt_archive,
        args.tt_manifest,
        p113_predictions,
        frozen=ctx["frozen"],
        train_case_ids=ctx["train_case_ids"],
        dev_case_ids=(),
        hmac_key=ctx["hmac_key"],
        scoring_started_at=scoring_started_at,
    )
    diagnosis_contract_eval = evaluate_p113_results(
        ctx["packet_build"].p113_packets,
        p113_results,
        run_id=stable_hash(
            {
                "freeze_hash": ctx["frozen"]["freeze_hash"],
                "mode": "diagnosis-contract",
                "case_count": len(p113_results),
            }
        ),
    )
    comparison = _comparison(baseline_eval, diagnosis_eval, frozen=ctx["frozen"])
    gate_report = _diagnosis_gate_report(
        diagnosis_eval,
        diagnosis_contract_eval=diagnosis_contract_eval,
        frozen=ctx["frozen"],
        comparison=comparison,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write(args.output_dir / "p112-baseline-predictions.json", {"predictions": p112_predictions})
    _write(args.output_dir / "p113-diagnosis-results.json", {"results": p113_results})
    _write(args.output_dir / "p113-diagnosis-predictions.json", {"predictions": p113_predictions})
    _write(args.output_dir / "p112-baseline-evaluation.json", baseline_eval)
    _write(args.output_dir / "p113-diagnosis-evaluation.json", diagnosis_eval)
    _write(args.output_dir / "p113-diagnosis-contract-evaluation.json", diagnosis_contract_eval)
    _write(args.output_dir / "diagnosis-comparison.json", comparison)
    _write(args.output_dir / "diagnosis-gate-report.json", gate_report)
    return {
        "mode": "diagnosis",
        "freeze_hash": ctx["frozen"]["freeze_hash"],
        "case_count": len(p113_predictions),
        "diagnosis_gates_passed": gate_report["passed"],
    }


def _run_narrative(args: argparse.Namespace) -> dict[str, Any]:
    if args.diagnosis_gate_report is None:
        raise ValueError("diagnosis_gate_report_required")
    gate = _read(args.diagnosis_gate_report)
    ctx = _build_and_validate_context(args)
    if gate.get("passed") is not True or str(gate.get("freeze_hash", "")) != str(ctx["frozen"].get("freeze_hash", "")):
        raise ValueError("diagnosis_gate_not_passed")

    subset_ids = _validated_narrative_subset(ctx["frozen"], ctx["packet_build"].case_ids)
    if args.case_offset < 0 or args.max_cases < 1:
        raise ValueError("invalid_batch_bounds")
    batch_ids = subset_ids[args.case_offset : args.case_offset + args.max_cases]
    packets_by_id = {str(packet["case_id"]): packet for packet in ctx["packet_build"].p113_packets}
    selected_packets = [packets_by_id[case_id] for case_id in batch_ids]

    provider = NvidiaP110CandidateProvider(model=runtime.MODEL, system_prompt=P113_SYSTEM_PROMPT)
    config = P113Config(model=runtime.MODEL, decoding_config=runtime.DECODING)
    results = [run_p113_decoupled_rca(packet, provider=provider, config=config) for packet in selected_packets]
    evaluation = evaluate_p113_results(selected_packets, results, run_id=_narrative_run_id(ctx["frozen"], args.case_offset, len(results)))
    _validate_zero_actions(evaluation, results)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"offset-{args.case_offset}-count-{len(results)}"
    _write(args.output_dir / f"narrative-results-{suffix}.json", {"results": results})
    _write(args.output_dir / f"narrative-evaluation-{suffix}.json", evaluation)
    return {
        "mode": "narrative",
        "freeze_hash": ctx["frozen"]["freeze_hash"],
        "case_offset": args.case_offset,
        "case_count": len(results),
        "selected_case_ids": batch_ids,
    }


def _build_and_validate_context(args: argparse.Namespace) -> dict[str, Any]:
    hmac_key = args.hmac_key.read_bytes()
    ss, ob = runtime.load_p113_training_corpora(ROOT)
    train_case_ids = tuple(case.case_id for case in (*ss, *ob))
    rebuilt_model = runtime.train_final_p113_model(ss, ob)
    tt_dataset = runtime.load_p113_tt_packet_dataset(args.tt_archive, args.tt_manifest, hmac_key=hmac_key)
    packet_build = runtime.build_all_p113_diagnosis_packets(tt_dataset["candidate_packets"], rebuilt_model)
    frozen = _read(args.freeze_dir / "freeze-manifest.json")
    _validate_freeze(frozen, rebuilt_model=rebuilt_model, packet_build=packet_build)
    return {
        "hmac_key": hmac_key,
        "train_case_ids": train_case_ids,
        "rebuilt_model": rebuilt_model,
        "tt_dataset": tt_dataset,
        "packet_build": packet_build,
        "frozen": frozen,
    }


def _validate_freeze(frozen: Mapping[str, Any], *, rebuilt_model: Mapping[str, Any], packet_build: Any) -> None:
    if frozen.get("schema_version") != "p113.fresh_blind_freeze.v1" or frozen.get("status") != "frozen":
        raise ValueError("invalid_freeze_manifest")
    if str(frozen.get("freeze_hash", "")) != stable_hash({key: value for key, value in frozen.items() if key != "freeze_hash"}):
        raise ValueError("freeze_hash_drift")
    expected = {
        "model_hash": _model_hash(rebuilt_model),
        "p112_baseline_hash": packet_build.p112_baseline_prediction_hash,
        "diagnosis_packet_hash": packet_build.diagnosis_packet_hash,
        "narrative_packet_hash": packet_build.narrative_packet_hash,
        "system_prompt_hash": runtime.system_prompt_hash(),
        "endpoint_hash": runtime.endpoint_request_hash(),
        "decoding_hash": runtime.decoding_hash(),
        "code_hash": runtime.implementation_hash(ROOT),
    }
    for key, value in expected.items():
        if str(frozen.get(key, "")) != str(value):
            raise ValueError(f"freeze_drift:{key}")
    frozen_case_ids = tuple(str(item) for item in _sequence(frozen.get("tt_case_ids", packet_build.case_ids)))
    if frozen_case_ids != tuple(packet_build.case_ids):
        raise ValueError("freeze_drift:tt_case_ids")
    if len(packet_build.case_ids) != 125 or len(set(packet_build.case_ids)) != 125:
        raise ValueError("p113_tt_case_completeness")


def _prediction_from_p112_packet(packet: Mapping[str, Any]) -> dict[str, Any]:
    scores = _mapping(packet.get("model_scores"))
    services = [str(item) for item in _sequence(scores.get("ranked_services"))]
    faults = [str(item) for item in _sequence(scores.get("ranked_faults"))]
    if not services or not faults:
        raise ValueError("missing_p112_model_scores")
    return {
        "case_id": str(packet["case_id"]),
        "ranked_services": services[:5],
        "fault_type": faults[0],
        "evidence_refs": [str(item) for item in _sequence(packet.get("evidence_ids"))],
        "confidence": 0.0,
        "abstain": False,
        "advisory_actions": [],
        "executed_actions": [],
        "validation_errors": [],
        "prediction_origin": "p112_frozen_baseline_model_scores",
        "packet_hash": str(packet.get("packet_hash", "")),
    }


def _prediction_from_p113_result(result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "case_id": str(result["case_id"]),
        "ranked_services": [str(item) for item in _sequence(result.get("ranked_services"))],
        "fault_type": str(result.get("fault_type", "")),
        "evidence_refs": [str(item) for item in _sequence(result.get("evidence_refs"))],
        "confidence": float(result.get("confidence", 0.0) or 0.0),
        "abstain": bool(result.get("abstain", False)),
        "advisory_actions": [],
        "executed_actions": [],
        "validation_errors": [],
        "prediction_origin": "p113_frozen_deterministic_diagnosis",
        "result_hash": str(result.get("result_hash", "")),
        "packet_hash": str(result.get("packet_hash", "")),
    }


def _comparison(baseline_eval: Mapping[str, Any], diagnosis_eval: Mapping[str, Any], *, frozen: Mapping[str, Any]) -> dict[str, Any]:
    baseline_metrics = _mapping(baseline_eval.get("metrics"))
    diagnosis_metrics = _mapping(diagnosis_eval.get("metrics"))
    shared = sorted(set(baseline_metrics) & set(diagnosis_metrics))
    deltas = {
        key: _metric_value(diagnosis_metrics[key]) - _metric_value(baseline_metrics[key]) for key in shared if _metric_has_value(baseline_metrics[key]) and _metric_has_value(diagnosis_metrics[key])
    }
    payload = {
        "schema_version": "p113.diagnosis_comparison.v1",
        "freeze_hash": str(frozen.get("freeze_hash", "")),
        "baseline_evaluation_hash": str(baseline_eval.get("evaluation_hash", "")),
        "diagnosis_evaluation_hash": str(diagnosis_eval.get("evaluation_hash", "")),
        "metric_deltas": deltas,
    }
    return {**payload, "comparison_hash": stable_hash(payload)}


def _diagnosis_gate_report(
    diagnosis_eval: Mapping[str, Any],
    *,
    diagnosis_contract_eval: Mapping[str, Any],
    frozen: Mapping[str, Any],
    comparison: Mapping[str, Any],
) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    metrics = _mapping(diagnosis_eval.get("metrics"))
    safety = _mapping(diagnosis_eval.get("safety"))
    contract_metrics = _mapping(diagnosis_contract_eval.get("metrics"))
    contract_safety = _mapping(diagnosis_contract_eval.get("safety"))
    gates = _mapping(runtime.ACCEPTANCE_GATES)
    _min_gate(checks, metrics, gates, "service_top1_min", "service_top1")
    _min_gate(checks, metrics, gates, "service_top3_min", "service_top3")
    _min_gate(checks, metrics, gates, "fault_accuracy_min", "fault_accuracy")
    _min_gate(checks, metrics, gates, "evidence_precision_min", "evidence_precision")
    if "diagnostic_abstention_max" in gates:
        checks["diagnostic_abstention_max"] = "abstention_rate" in metrics and _metric_value(metrics["abstention_rate"]) <= float(gates["diagnostic_abstention_max"])
    by_fault = _mapping(diagnosis_eval.get("by_fault"))
    for fault in ("cpu", "mem", "disk", "delay", "loss"):
        gate_key = f"{fault}_accuracy_min"
        if gate_key not in gates:
            continue
        fault_metrics = _mapping(_mapping(by_fault.get(fault)).get("metrics"))
        checks[gate_key] = "fault_accuracy" in fault_metrics and _metric_value(fault_metrics["fault_accuracy"]) >= float(gates[gate_key])
    deltas = _mapping(comparison.get("metric_deltas"))
    if gates.get("nonnegative_service_top1_delta_vs_p112") is True:
        checks["nonnegative_service_top1_delta_vs_p112"] = float(deltas.get("service_top1", float("-inf"))) >= 0.0
    if gates.get("nonnegative_fault_accuracy_delta_vs_p112") is True:
        checks["nonnegative_fault_accuracy_delta_vs_p112"] = float(deltas.get("fault_accuracy", float("-inf"))) >= 0.0
    if gates.get("zero_executed_actions") is True:
        checks["zero_executed_actions"] = int(safety.get("executed_action_count", 0) or 0) == 0
    if gates.get("zero_unsafe_suggestions") is True:
        checks["zero_harmful_actions"] = int(safety.get("harmful_action_count", 0) or 0) == 0
    if gates.get("zero_truth_leaks") is True:
        checks["zero_truth_leaks"] = int(safety.get("truth_leak_count", 0) or 0) == 0
    if "diagnosis_preservation" in gates:
        checks["diagnosis_preservation"] = "diagnosis_preservation_rate" in contract_metrics and _metric_value(contract_metrics["diagnosis_preservation_rate"]) >= float(
            gates["diagnosis_preservation"]
        )
    if "provider_synthesis_raw_replay" in gates:
        checks["diagnosis_replay_hash_consistency"] = "replay_hash_consistency_rate" in contract_metrics and _metric_value(contract_metrics["replay_hash_consistency_rate"]) >= float(
            gates["provider_synthesis_raw_replay"]
        )
    checks["diagnosis_action_authority_disabled"] = (
        _metric_value(contract_metrics.get("action_authority_disabled_rate")) == 1.0
        and int(contract_safety.get("executed_action_count", -1)) == 0
        and int(contract_safety.get("action_authority_enabled_count", -1)) == 0
    )
    payload = {
        "schema_version": "p113.diagnosis_gate_report.v1",
        "freeze_hash": str(frozen.get("freeze_hash", "")),
        "evaluation_hash": str(diagnosis_eval.get("evaluation_hash", "")),
        "contract_evaluation_hash": str(diagnosis_contract_eval.get("evaluation_hash", "")),
        "comparison_hash": str(comparison.get("comparison_hash", "")),
        "checks": checks,
        "passed": bool(checks) and all(checks.values()),
    }
    return {**payload, "gate_report_hash": stable_hash(payload)}


def _min_gate(checks: dict[str, bool], metrics: Mapping[str, Any], gates: Mapping[str, Any], gate_key: str, metric_key: str) -> None:
    if gate_key in gates:
        checks[gate_key] = metric_key in metrics and _metric_value(metrics[metric_key]) >= float(gates[gate_key])


def _validated_narrative_subset(frozen: Mapping[str, Any], all_case_ids: Sequence[str]) -> list[str]:
    subset = [str(item) for item in _sequence(frozen.get("narrative_subset_case_ids"))]
    if len(subset) != 25 or len(set(subset)) != 25:
        raise ValueError("invalid_narrative_subset")
    all_ids = set(str(item) for item in all_case_ids)
    if any(case_id not in all_ids for case_id in subset):
        raise ValueError("narrative_subset_case_drift")
    expected = list(select_p113_narrative_subset([{"case_id": case_id} for case_id in all_case_ids]))
    if subset != expected:
        raise ValueError("narrative_subset_selection_drift")
    return subset


def _validate_zero_actions(evaluation: Mapping[str, Any], results: Sequence[Mapping[str, Any]]) -> None:
    safety = _mapping(evaluation.get("safety"))
    if int(safety.get("executed_action_count", 0) or 0) != 0 or int(safety.get("action_authority_enabled_count", 0) or 0) != 0:
        raise ValueError("narrative_action_contract_violation")
    if any(_sequence(result.get("executed_actions")) for result in results):
        raise ValueError("narrative_executed_actions")


def _narrative_run_id(frozen: Mapping[str, Any], offset: int, count: int) -> str:
    return stable_hash({"freeze_hash": str(frozen.get("freeze_hash", "")), "mode": "narrative", "offset": offset, "count": count})


def _model_hash(model_artifact: Mapping[str, Any]) -> str:
    artifact_hash = str(model_artifact.get("artifact_hash", ""))
    return artifact_hash if artifact_hash.startswith("sha256:") else stable_hash(model_artifact)


def _metric_has_value(value: Any) -> bool:
    return isinstance(value, Mapping) and isinstance(value.get("value"), int | float)


def _metric_value(value: Any) -> float:
    if not isinstance(value, Mapping) or not isinstance(value.get("value"), int | float):
        raise ValueError("missing_metric_value")
    return float(value["value"])


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8")


def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        normalized = key.strip()
        if normalized == "NVIDIA_API_KEY" and normalized not in os.environ:
            os.environ[normalized] = value.strip().strip("\"'")


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else ()


if __name__ == "__main__":
    raise SystemExit(main())
