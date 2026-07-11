"""Fail-closed P113 release evidence assembly."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p113_benchmark_runtime import ACCEPTANCE_GATES, TT_CASE_COUNT
from app.services.p113_governance import P113_OFFICIAL_TT_SOURCE_HASH

SCHEMA_VERSION = "p113.release_evidence.v1"
CRYPTO_REVIEW_SCHEMA_VERSION = "p113.cryptographic_review.v1"
_SOURCE_SHA256 = P113_OFFICIAL_TT_SOURCE_HASH.removeprefix("sha256:")
_FAULTS = ("cpu", "mem", "disk", "delay", "loss")
_DIAGNOSIS_ZERO_COUNTERS = {
    "truth_leak_count": "zero_truth_leaks",
    "unsafe_suggestion_count": "zero_unsafe_suggestions",
    "executed_action_count": "zero_executed_actions",
    "provider_write_count": "zero_provider_writes",
    "credential_count": "zero_credentials",
    "shell_command_count": "zero_shell_commands",
    "production_adapter_count": "zero_production_adapters",
    "mutation_count": "zero_mutations",
}
_NARRATIVE_ZERO_COUNTERS = {
    "harmful_raw_action_count": "zero_unsafe_suggestions",
    "unsafe_normalized_suggestion_count": "zero_unsafe_suggestions",
    "executed_action_count": "zero_executed_actions",
    "action_authority_enabled_count": "zero_provider_writes",
}


def produce_p113_release_evidence(
    *,
    acquisition_verification: Mapping[str, Any],
    freeze_manifest: Mapping[str, Any],
    packet_manifest: Mapping[str, Any],
    p112_baseline_evaluation: Mapping[str, Any],
    diagnosis_evaluation: Mapping[str, Any],
    diagnosis_contract_evaluation: Mapping[str, Any],
    narrative_evaluations: Sequence[Mapping[str, Any]] = (),
    repeat_evaluation: Mapping[str, Any] | None = None,
    cryptographic_review: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a concise, aggregate-only P113 release decision."""

    baseline_metrics = _mapping(p112_baseline_evaluation.get("metrics"))
    diagnosis_metrics = _mapping(diagnosis_evaluation.get("metrics"))
    baseline_service_top1 = _metric(baseline_metrics, "service_top1")
    baseline_fault_accuracy = _metric(baseline_metrics, "fault_accuracy")
    diagnosis_service_top1 = _metric(diagnosis_metrics, "service_top1")
    diagnosis_fault_accuracy = _metric(diagnosis_metrics, "fault_accuracy")
    diagnosis_contract_metrics = _mapping(diagnosis_contract_evaluation.get("metrics"))
    service_delta = round(diagnosis_service_top1 - baseline_service_top1, 6)
    fault_delta = round(diagnosis_fault_accuracy - baseline_fault_accuracy, 6)

    gates: dict[str, bool] = {
        "acquisition_verified": acquisition_verification.get("verified") is True,
        "acquisition_source_hash": _source_hash(acquisition_verification) == P113_OFFICIAL_TT_SOURCE_HASH,
        "acquisition_case_count": _case_count(acquisition_verification) == TT_CASE_COUNT,
        "freeze_manifest_hash": _stable_hash_matches(freeze_manifest, "freeze_hash"),
        "freeze_status": freeze_manifest.get("schema_version") == "p113.fresh_blind_freeze.v1" and freeze_manifest.get("status") == "frozen" and freeze_manifest.get("benchmark_role") == "fresh_blind",
        "freeze_source_hash": freeze_manifest.get("tt_source_hash") == P113_OFFICIAL_TT_SOURCE_HASH,
        "freeze_case_count": _case_count(freeze_manifest, "tt_case_count") == TT_CASE_COUNT,
        "freeze_gates_hash": freeze_manifest.get("gates_hash") == stable_hash(ACCEPTANCE_GATES),
        "freeze_no_action_authority": freeze_manifest.get("action_contract_status") == "disabled"
        and freeze_manifest.get("action_execution_enabled") is False
        and freeze_manifest.get("credential_access_enabled") is False
        and freeze_manifest.get("auth_authority") == "none",
        "packet_manifest_complete": packet_manifest.get("schema_version") == "p113.packet_hash_manifest.v1"
        and _case_count(packet_manifest) == TT_CASE_COUNT
        and len(_mapping(packet_manifest.get("p112_baseline_packet_hashes"))) == TT_CASE_COUNT
        and len(_mapping(packet_manifest.get("p113_packet_hashes"))) == TT_CASE_COUNT,
        "case_ids_hash_match": packet_manifest.get("case_ids_hash") == freeze_manifest.get("tt_case_ids_hash"),
        "p112_baseline_hash_match": packet_manifest.get("p112_baseline_prediction_hash") == freeze_manifest.get("p112_baseline_hash"),
        "diagnosis_packet_hash_match": packet_manifest.get("diagnosis_packet_hash") == freeze_manifest.get("diagnosis_packet_hash"),
        "narrative_packet_hash_match": packet_manifest.get("narrative_packet_hash") == freeze_manifest.get("narrative_packet_hash"),
        "baseline_blind_evaluation": _blind_report_valid(p112_baseline_evaluation, freeze_manifest),
        "baseline_evaluation_hash": _stable_hash_matches(p112_baseline_evaluation, "evaluation_hash"),
        "diagnosis_blind_evaluation": _blind_report_valid(diagnosis_evaluation, freeze_manifest),
        "diagnosis_evaluation_hash": _stable_hash_matches(diagnosis_evaluation, "evaluation_hash"),
        "service_top1": diagnosis_service_top1 >= float(ACCEPTANCE_GATES["service_top1_min"]),
        "service_top3": _metric(diagnosis_metrics, "service_top3") >= float(ACCEPTANCE_GATES["service_top3_min"]),
        "fault_accuracy": diagnosis_fault_accuracy >= float(ACCEPTANCE_GATES["fault_accuracy_min"]),
        "evidence_precision": _metric(diagnosis_metrics, "evidence_precision") >= float(ACCEPTANCE_GATES["evidence_precision_min"]),
        "diagnostic_abstention": _metric(diagnosis_metrics, "abstention_rate", default=1.0) <= float(ACCEPTANCE_GATES["diagnostic_abstention_max"]),
        "nonnegative_service_top1_delta_vs_p112": service_delta >= 0.0,
        "nonnegative_fault_accuracy_delta_vs_p112": fault_delta >= 0.0,
        "diagnosis_contract_evaluation_hash": _stable_hash_matches(diagnosis_contract_evaluation, "evaluation_hash"),
        "diagnosis_preservation": _metric(diagnosis_contract_metrics, "diagnosis_preservation_rate") >= float(ACCEPTANCE_GATES["diagnosis_preservation"]),
        "diagnosis_replay_hash_consistency": _metric(diagnosis_contract_metrics, "replay_hash_consistency_rate") >= float(ACCEPTANCE_GATES["provider_synthesis_raw_replay"]),
        "diagnosis_action_authority_disabled": _metric(diagnosis_contract_metrics, "action_authority_disabled_rate") >= 1.0,
    }
    _merge_gates(gates, _fault_gates(diagnosis_evaluation))
    _merge_gates(gates, _zero_counter_gates(diagnosis_evaluation, _DIAGNOSIS_ZERO_COUNTERS))
    _merge_gates(gates, _narrative_gates(narrative_evaluations, repeat_evaluation))
    gates["cryptographic_review"] = _crypto_review_valid(cryptographic_review)

    stop_reason = _stop_reason(gates)
    release: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "release_qualified": all(gates.values()),
        "stop_reason": stop_reason,
        "gates": gates,
        "metrics": {
            "diagnosis": {
                "service_top1": diagnosis_service_top1,
                "service_top3": _metric(diagnosis_metrics, "service_top3"),
                "fault_accuracy": diagnosis_fault_accuracy,
                "evidence_precision": _metric(diagnosis_metrics, "evidence_precision"),
                "diagnostic_abstention_rate": _metric(diagnosis_metrics, "abstention_rate", default=1.0),
            },
            "p112_baseline": {
                "service_top1": baseline_service_top1,
                "fault_accuracy": baseline_fault_accuracy,
            },
            "deltas_vs_p112": {
                "service_top1": service_delta,
                "fault_accuracy": fault_delta,
            },
            "narrative": _narrative_summary(narrative_evaluations, repeat_evaluation),
        },
        "evidence": {
            "source_hash": P113_OFFICIAL_TT_SOURCE_HASH,
            "case_count": TT_CASE_COUNT,
            "freeze_hash": str(freeze_manifest.get("freeze_hash", "")),
            "packet_manifest_hash": stable_hash(_sanitized_packet_manifest(packet_manifest)),
            "p112_baseline_evaluation_hash": str(p112_baseline_evaluation.get("evaluation_hash", "")),
            "diagnosis_evaluation_hash": str(diagnosis_evaluation.get("evaluation_hash", "")),
            "diagnosis_contract_evaluation_hash": str(diagnosis_contract_evaluation.get("evaluation_hash", "")),
            "narrative_evaluation_hashes": [str(item.get("evaluation_hash", "")) for item in narrative_evaluations],
            "repeat_evaluation_hash": str(_mapping(repeat_evaluation).get("repeat_evaluation_hash", "")),
            "crypto_review_hash": stable_hash(_mapping(cryptographic_review)) if cryptographic_review else None,
        },
        "reasons": [f"{name} failed closed" for name, passed in gates.items() if not passed],
        "action_execution_enabled": False,
    }
    binding = stable_hash({key: value for key, value in release.items() if key not in {"release_evidence_hash", "markdown_summary"}})
    release["release_evidence_hash"] = binding
    return release


def render_p113_release_markdown(release: Mapping[str, Any]) -> str:
    status = "true" if release.get("release_qualified") is True else "false"
    gates = _mapping(release.get("gates"))
    metrics = _mapping(release.get("metrics"))
    diagnosis = _mapping(metrics.get("diagnosis"))
    deltas = _mapping(metrics.get("deltas_vs_p112"))
    lines = [
        "# P113 Release Evidence",
        "",
        f"- release_qualified: {status}",
        f"- stop_reason: {release.get('stop_reason') or 'none'}",
        f"- release_evidence_hash: {release.get('release_evidence_hash', '')}",
        f"- diagnosis_service_top1: {diagnosis.get('service_top1')}",
        f"- diagnosis_fault_accuracy: {diagnosis.get('fault_accuracy')}",
        f"- delta_service_top1_vs_p112: {deltas.get('service_top1')}",
        f"- delta_fault_accuracy_vs_p112: {deltas.get('fault_accuracy')}",
        "",
        "## Failed Gates",
    ]
    failed = [name for name, passed in gates.items() if passed is not True]
    lines.extend(f"- {name}" for name in failed)
    if not failed:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def _blind_report_valid(report: Mapping[str, Any], freeze_manifest: Mapping[str, Any]) -> bool:
    return (
        report.get("schema_version") == "p113.blind_evaluation_report.v1"
        and report.get("official_source_hash") == P113_OFFICIAL_TT_SOURCE_HASH
        and _case_count(_mapping(report.get("summary"))) == TT_CASE_COUNT
        and _mapping(report.get("governance")).get("freeze_hash") == freeze_manifest.get("freeze_hash")
        and _mapping(report.get("governance")).get("score_after_freeze") is True
        and _stable_hash_matches(report, "evaluation_hash")
    )


def _fault_gates(report: Mapping[str, Any]) -> dict[str, bool]:
    by_fault = _mapping(report.get("by_fault"))
    return {f"{fault}_accuracy": _metric(_mapping(_mapping(by_fault.get(fault)).get("metrics")), "fault_accuracy") >= float(ACCEPTANCE_GATES[f"{fault}_accuracy_min"]) for fault in _FAULTS}


def _narrative_gates(
    narrative_evaluations: Sequence[Mapping[str, Any]],
    repeat_evaluation: Mapping[str, Any] | None,
) -> dict[str, bool]:
    reports = list(narrative_evaluations)
    run_ids = [str(report.get("run_id", "")) for report in reports]
    metrics_by_report = [_mapping(report.get("metrics")) for report in reports]
    narrative_present = len(reports) == 2
    repeat = _mapping(repeat_evaluation)
    repeat_run_ids_match = (
        bool(repeat)
        and narrative_present
        and repeat.get("first_run_id") == reports[0].get("run_id")
        and repeat.get("second_run_id") == reports[1].get("run_id")
        and repeat.get("first_run_id") != repeat.get("second_run_id")
    )
    gates = {
        "narrative_evidence_present": narrative_present,
        "run_independence": narrative_present and len(set(run_ids)) == len(run_ids) and all(run_ids) and (not repeat or repeat_run_ids_match),
        "narrative_case_counts": narrative_present and all(_case_count(_mapping(report.get("summary"))) == 25 for report in reports),
        "narrative_raw_contract_valid_rate": narrative_present
        and all(_metric(metrics, "raw_contract_valid_rate") >= float(ACCEPTANCE_GATES["raw_provider_contract_valid_rate_min"]) for metrics in metrics_by_report),
        "narrative_normalized_contract_valid_rate": narrative_present
        and all(_metric(metrics, "normalized_contract_valid_rate") >= float(ACCEPTANCE_GATES["normalized_contract_valid_rate_min"]) for metrics in metrics_by_report),
        "narrative_valid_rate": narrative_present and all(_metric(metrics, "narrative_valid_rate") >= float(ACCEPTANCE_GATES["narrative_valid_rate_min"]) for metrics in metrics_by_report),
        "diagnosis_preservation": narrative_present and all(_metric(metrics, "diagnosis_preservation_rate") >= float(ACCEPTANCE_GATES["diagnosis_preservation"]) for metrics in metrics_by_report),
        "provider_synthesis_raw_replay": narrative_present
        and all(_metric(metrics, "replay_hash_consistency_rate") >= float(ACCEPTANCE_GATES["provider_synthesis_raw_replay"]) for metrics in metrics_by_report),
        "repeat_evaluation_present": bool(repeat),
        "repeat_evaluation_hash": bool(repeat) and _stable_hash_matches(repeat, "repeat_evaluation_hash"),
        "repeat_run_ids_match": repeat_run_ids_match,
        "repeat_hashes_match": bool(repeat)
        and narrative_present
        and repeat.get("first_evaluation_hash") == reports[0].get("evaluation_hash")
        and repeat.get("second_evaluation_hash") == reports[1].get("evaluation_hash"),
        "diagnosis_repeat_agreement": bool(repeat) and _metric(_mapping(repeat.get("metrics")), "diagnosis_agreement_rate") >= float(ACCEPTANCE_GATES["diagnosis_repeat_agreement"]),
    }
    gates.update(_zero_counter_gates_for_reports(reports))
    gates["narrative_evaluation_hashes"] = narrative_present and all(_stable_hash_matches(report, "evaluation_hash") for report in reports)
    return gates


def _zero_counter_gates_for_reports(reports: Sequence[Mapping[str, Any]]) -> dict[str, bool]:
    grouped: dict[str, bool] = {
        "zero_unsafe_suggestions": bool(reports),
        "zero_executed_actions": bool(reports),
        "zero_provider_writes": bool(reports),
    }
    for report in reports:
        report_gates = _zero_counter_gates(report, _NARRATIVE_ZERO_COUNTERS)
        for gate, passed in report_gates.items():
            grouped[gate] = grouped.get(gate, True) and passed
    return grouped


def _zero_counter_gates(report: Mapping[str, Any], counters: Mapping[str, str]) -> dict[str, bool]:
    safety = _mapping(report.get("safety"))
    gates = {gate: True for gate in set(counters.values())}
    for counter, gate in counters.items():
        gates[gate] = gates[gate] and counter in safety and int(safety.get(counter, 0) or 0) == 0
    return gates


def _narrative_summary(
    narrative_evaluations: Sequence[Mapping[str, Any]],
    repeat_evaluation: Mapping[str, Any] | None,
) -> dict[str, Any]:
    return {
        "run_ids": [str(item.get("run_id", "")) for item in narrative_evaluations],
        "raw_contract_valid_rates": [_metric(_mapping(item.get("metrics")), "raw_contract_valid_rate") for item in narrative_evaluations],
        "normalized_contract_valid_rates": [_metric(_mapping(item.get("metrics")), "normalized_contract_valid_rate") for item in narrative_evaluations],
        "narrative_valid_rates": [_metric(_mapping(item.get("metrics")), "narrative_valid_rate") for item in narrative_evaluations],
        "diagnosis_agreement_rate": _metric(_mapping(_mapping(repeat_evaluation).get("metrics")), "diagnosis_agreement_rate") if repeat_evaluation else None,
    }


def _crypto_review_valid(review: Mapping[str, Any] | None) -> bool:
    if not review:
        return False
    reviewer_id = str(review.get("reviewer_id", ""))
    return (
        review.get("schema_version") == CRYPTO_REVIEW_SCHEMA_VERSION
        and bool(reviewer_id)
        and reviewer_id != "opscat-release-builder"
        and review.get("reviewer_independent") is True
        and review.get("self_attested") is False
        and review.get("signature_verified") is True
        and review.get("provider_receipts_verified") is True
        and review.get("artifact_hashes_verified") is True
        and _hashish(review.get("release_binding_hash"))
    )


def _merge_gates(target: dict[str, bool], incoming: Mapping[str, bool]) -> None:
    for name, passed in incoming.items():
        target[name] = target.get(name, True) and passed


def _stop_reason(gates: Mapping[str, bool]) -> str | None:
    if all(gates.values()):
        return None
    diagnosis_gate_names = {
        "diagnosis_blind_evaluation",
        "service_top1",
        "service_top3",
        "fault_accuracy",
        "evidence_precision",
        "diagnostic_abstention",
        "nonnegative_service_top1_delta_vs_p112",
        "nonnegative_fault_accuracy_delta_vs_p112",
        "diagnosis_replay_hash_consistency",
        "diagnosis_contract_evaluation_hash",
        "diagnosis_preservation",
        "diagnosis_action_authority_disabled",
        *{f"{fault}_accuracy" for fault in _FAULTS},
    }
    if any(gates.get(name) is False for name in diagnosis_gate_names):
        return "diagnosis_gates_failed"
    return "release_evidence_incomplete"


def _stable_hash_matches(value: Mapping[str, Any], field: str) -> bool:
    submitted = str(value.get(field, ""))
    if not submitted:
        return False
    unhashed = {key: item for key, item in value.items() if key != field}
    return submitted == stable_hash(unhashed)


def _hashish(value: Any) -> bool:
    text = str(value)
    if not text.startswith("sha256:") or len(text) != 71:
        return False
    return all(char in "0123456789abcdef" for char in text.removeprefix("sha256:"))


def _sanitized_packet_manifest(packet_manifest: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": packet_manifest.get("schema_version"),
        "case_count": packet_manifest.get("case_count"),
        "case_ids_hash": packet_manifest.get("case_ids_hash"),
        "p112_baseline_prediction_hash": packet_manifest.get("p112_baseline_prediction_hash"),
        "diagnosis_packet_hash": packet_manifest.get("diagnosis_packet_hash"),
        "narrative_packet_hash": packet_manifest.get("narrative_packet_hash"),
        "p112_baseline_packet_count": len(_mapping(packet_manifest.get("p112_baseline_packet_hashes"))),
        "p113_packet_count": len(_mapping(packet_manifest.get("p113_packet_hashes"))),
    }


def _metric(metrics: Mapping[str, Any], name: str, *, default: float = 0.0) -> float:
    item = _mapping(metrics.get(name))
    value = item.get("value", default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _case_count(value: Mapping[str, Any], key: str = "case_count") -> int:
    raw = value.get(key)
    return raw if isinstance(raw, int) and not isinstance(raw, bool) else -1


def _source_hash(acquisition_verification: Mapping[str, Any]) -> str:
    value = str(acquisition_verification.get("sha256", ""))
    return value if value.startswith("sha256:") else f"sha256:{value}"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
