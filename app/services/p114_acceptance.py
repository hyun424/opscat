"""Freeze and one-shot aggregate evaluation contracts for P114 RE2-OB."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p114_fault_knn import (
    MODEL_SCHEMA_VERSION,
    rerank_p114_lattice_with_fault_knn,
)
from app.services.p114_hypothesis_lattice import (
    FAULTS,
    LATTICE_SCHEMA_VERSION,
    build_p114_hypothesis_lattice,
)
from app.services.p114_re2_loader import CANDIDATE_SCHEMA_VERSION, P114RE2Case, reject_candidate_truth_leak

FREEZE_SCHEMA_VERSION = "p114.deterministic_acceptance_freeze.v1"
EVALUATION_SCHEMA_VERSION = "p114.re2_ob_blind_evaluation.v1"
ACCEPTANCE_GATES = {
    "service_top1_min": 0.60,
    "service_top3_min": 0.80,
    "fault_accuracy_min": 0.60,
    "per_fault_accuracy_min": 0.45,
    "joint_top1_min": 0.50,
    "joint_candidate_recall_min": 0.75,
    "evidence_precision_min": 0.95,
    "replay_consistency_min": 1.0,
    "diagnosis_preservation_min": 1.0,
}
P114_RUNTIME_SAFETY_COUNTERS = (
    "llm_call_count",
    "credential_access_count",
    "shell_execution_count",
    "external_write_count",
    "remediation_adapter_call_count",
)
P114_REQUIRED_SAFETY_COUNTERS = (
    "truth_leak_count",
    *P114_RUNTIME_SAFETY_COUNTERS,
    "executed_action_count",
    "artifact_authority_violation_count",
    "source_mutation_count",
)


class P114AcceptanceError(ValueError):
    """Raised when acceptance freeze or scoring evidence drifts."""


class P114RuntimeSafetyLedger:
    """Fail-closed ledger for forbidden capabilities in the blind runner."""

    def __init__(self) -> None:
        self._counters = {name: 0 for name in P114_RUNTIME_SAFETY_COUNTERS}

    def snapshot(self) -> dict[str, int]:
        return dict(self._counters)

    def record_forbidden(self, counter: str) -> None:
        if counter not in self._counters:
            raise P114AcceptanceError(f"unknown_safety_counter:{counter}")
        self._counters[counter] += 1
        raise P114AcceptanceError(f"forbidden_runtime_capability:{counter}")


def p114_implementation_hash(root: str | Path) -> str:
    base = Path(root)
    paths = sorted(
        [*base.glob("app/services/p114_*.py"), *base.glob("scripts/*p114*.py")],
        key=lambda path: path.relative_to(base).as_posix(),
    )
    if not paths:
        raise P114AcceptanceError("missing_implementation_files")
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.relative_to(base).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def build_p114_acceptance_freeze(
    *,
    source_verification: Mapping[str, Any],
    model: Mapping[str, Any],
    packets: Sequence[Mapping[str, Any]],
    development_gate: Mapping[str, Any],
    implementation_hash: str,
    frozen_at: str,
) -> dict[str, Any]:
    _parse_time(frozen_at)
    if source_verification.get("verified") is not True or int(source_verification.get("case_count", 0)) != 90:
        raise P114AcceptanceError("invalid_source_verification")
    if model.get("schema_version") != MODEL_SCHEMA_VERSION or not _hash_matches(model, "model_hash"):
        raise P114AcceptanceError("invalid_fault_model")
    if development_gate.get("passed") is not True or not _hash_matches(development_gate, "gate_hash"):
        raise P114AcceptanceError("development_gate_not_passed")
    if len(packets) != 90:
        raise P114AcceptanceError("acceptance_case_count_mismatch")
    reject_candidate_truth_leak(packets)
    lattices = build_p114_acceptance_lattices(packets, model)
    packet_ids = [str(packet.get("case_id", "")) for packet in packets]
    lattice_ids = [str(lattice.get("case_id", "")) for lattice in lattices]
    if len(set(packet_ids)) != 90 or packet_ids != lattice_ids:
        raise P114AcceptanceError("acceptance_case_identity_mismatch")
    for packet, lattice in zip(packets, lattices, strict=True):
        if packet.get("schema_version") != CANDIDATE_SCHEMA_VERSION:
            raise P114AcceptanceError("invalid_candidate_packet")
        if lattice.get("schema_version") != LATTICE_SCHEMA_VERSION or not _hash_matches(lattice, "lattice_hash"):
            raise P114AcceptanceError("invalid_acceptance_lattice")
    payload: dict[str, Any] = {
        "schema_version": FREEZE_SCHEMA_VERSION,
        "status": "frozen",
        "benchmark_role": "fresh_case_multimodal_acceptance",
        "source_id": str(source_verification.get("source_id", "")),
        "source_sha256": "sha256:" + str(source_verification.get("sha256", "")),
        "source_bytes": int(source_verification.get("bytes", 0)),
        "case_count": 90,
        "case_ids": packet_ids,
        "case_packet_hashes": {case_id: str(lattice.get("source_packet_hash", "")) for case_id, lattice in zip(packet_ids, lattices, strict=True)},
        "candidate_packet_set_hash": stable_hash(list(packets)),
        "lattice_set_hash": stable_hash(list(lattices)),
        "fault_model_hash": str(model["model_hash"]),
        "development_gate_hash": str(development_gate["gate_hash"]),
        "implementation_hash": implementation_hash,
        "acceptance_gates": dict(ACCEPTANCE_GATES),
        "authoritative_diagnosis": "deterministic_service_localization_plus_fault_knn",
        "llm_adjudication_enabled": False,
        "candidate_truth_validation": "passed",
        "action_contract_status": "disabled",
        "frozen_at": frozen_at,
        "scoring_not_before": frozen_at,
    }
    payload["freeze_hash"] = stable_hash(payload)
    return payload


def validate_p114_acceptance_freeze(
    freeze: Mapping[str, Any],
    *,
    source_verification: Mapping[str, Any],
    model: Mapping[str, Any],
    packets: Sequence[Mapping[str, Any]],
    development_gate: Mapping[str, Any],
    implementation_hash: str,
) -> None:
    if freeze.get("schema_version") != FREEZE_SCHEMA_VERSION or not _hash_matches(freeze, "freeze_hash"):
        raise P114AcceptanceError("invalid_freeze")
    rebuilt = build_p114_acceptance_freeze(
        source_verification=source_verification,
        model=model,
        packets=packets,
        development_gate=development_gate,
        implementation_hash=implementation_hash,
        frozen_at=str(freeze.get("frozen_at", "")),
    )
    if dict(freeze) != rebuilt:
        raise P114AcceptanceError("freeze_drift")


def evaluate_p114_re2_ob_blind(
    cases: Sequence[P114RE2Case],
    lattices: Sequence[Mapping[str, Any]],
    replay_lattices: Sequence[Mapping[str, Any]],
    freeze: Mapping[str, Any],
    *,
    scored_at: str,
    source_sha256_after: str,
    runtime_safety: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if freeze.get("schema_version") != FREEZE_SCHEMA_VERSION or not _hash_matches(freeze, "freeze_hash"):
        raise P114AcceptanceError("invalid_freeze")
    if _parse_time(scored_at) < _parse_time(str(freeze.get("scoring_not_before", ""))):
        raise P114AcceptanceError("scoring_before_freeze")
    if len(cases) != 90 or len(lattices) != 90 or len(replay_lattices) != 90:
        raise P114AcceptanceError("blind_case_count_mismatch")
    expected_case_ids = [case.case_id for case in cases]
    frozen_packet_hashes = _mapping(freeze.get("case_packet_hashes"))
    expected_packet_hashes = [str(frozen_packet_hashes.get(case_id, "")) for case_id in expected_case_ids]
    _validate_lattice_set(
        lattices,
        expected_case_ids=expected_case_ids,
        expected_packet_hashes=expected_packet_hashes,
    )
    _validate_lattice_set(
        replay_lattices,
        expected_case_ids=expected_case_ids,
        expected_packet_hashes=expected_packet_hashes,
    )
    replay_matches = sum(dict(first) == dict(second) for first, second in zip(lattices, replay_lattices, strict=True))
    diagnosis_preserved = int(stable_hash(list(lattices)) == str(freeze.get("lattice_set_hash", "")))
    lattice_by_id = {str(item.get("case_id", "")): item for item in lattices}
    rows: list[dict[str, Any]] = []
    for case in cases:
        lattice = lattice_by_id.get(case.case_id)
        if lattice is None or not _hash_matches(lattice, "lattice_hash"):
            raise P114AcceptanceError("missing_or_invalid_blind_lattice")
        truth_service = str(case.scorer_only_truth["root_service"])
        truth_fault = str(case.scorer_only_truth["fault_type"])
        ranked_services = [str(item) for item in _sequence(lattice.get("ranked_services"))]
        hypotheses = _mapping_sequence(lattice.get("hypotheses"))
        top = hypotheses[0]
        evidence_ids = [str(item) for item in _sequence(top.get("supporting_evidence_ids"))]
        known_ids = {str(item) for item in _sequence(lattice.get("evidence_node_ids"))}
        rows.append(
            {
                "fault": truth_fault,
                "service_top1": int(bool(ranked_services) and ranked_services[0] == truth_service),
                "service_top3": int(truth_service in ranked_services[:3]),
                "fault_correct": int(str(top.get("fault", "")) == truth_fault),
                "joint_top1": int(str(top.get("service", "")) == truth_service and str(top.get("fault", "")) == truth_fault),
                "joint_candidate": int(any(str(item.get("service", "")) == truth_service and str(item.get("fault", "")) == truth_fault for item in hypotheses)),
                "valid_evidence": sum(item in known_ids for item in evidence_ids),
                "evidence_count": len(evidence_ids),
            }
        )
    metrics = _aggregate(rows)
    metrics["replay_consistency"] = _rate(replay_matches, len(lattices))
    metrics["diagnosis_preservation"] = _rate(diagnosis_preserved, 1)
    by_fault = {fault: _aggregate([row for row in rows if row["fault"] == fault]) for fault in FAULTS}
    report: dict[str, Any] = {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "benchmark_role": "fresh_case_multimodal_acceptance_consumed_after_score",
        "freeze_hash": str(freeze["freeze_hash"]),
        "scored_at": scored_at,
        "metrics": metrics,
        "by_fault": by_fault,
        "safety": _artifact_safety(
            lattices,
            source_sha256_after=source_sha256_after,
            frozen_source_sha256=str(freeze.get("source_sha256", "")),
            runtime_safety=runtime_safety,
            candidate_truth_validation=str(freeze.get("candidate_truth_validation", "")),
        ),
    }
    report["evaluation_hash"] = stable_hash(report)
    gate = _acceptance_gate(report)
    return report, gate


def _aggregate(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    count = len(rows)
    return {
        "case_count": count,
        "service_top1": _rate(sum(int(row["service_top1"]) for row in rows), count),
        "service_top3": _rate(sum(int(row["service_top3"]) for row in rows), count),
        "fault_accuracy": _rate(sum(int(row["fault_correct"]) for row in rows), count),
        "joint_top1": _rate(sum(int(row["joint_top1"]) for row in rows), count),
        "joint_candidate_recall": _rate(sum(int(row["joint_candidate"]) for row in rows), count),
        "evidence_precision": _rate(sum(int(row["valid_evidence"]) for row in rows), sum(int(row["evidence_count"]) for row in rows)),
    }


def _acceptance_gate(report: Mapping[str, Any]) -> dict[str, Any]:
    metrics = _mapping(report.get("metrics"))
    by_fault = _mapping(report.get("by_fault"))
    safety = _mapping(report.get("safety"))
    checks = {
        "service_top1": _value(metrics, "service_top1") >= ACCEPTANCE_GATES["service_top1_min"],
        "service_top3": _value(metrics, "service_top3") >= ACCEPTANCE_GATES["service_top3_min"],
        "fault_accuracy": _value(metrics, "fault_accuracy") >= ACCEPTANCE_GATES["fault_accuracy_min"],
        "joint_top1": _value(metrics, "joint_top1") >= ACCEPTANCE_GATES["joint_top1_min"],
        "joint_candidate_recall": _value(metrics, "joint_candidate_recall") >= ACCEPTANCE_GATES["joint_candidate_recall_min"],
        "evidence_precision": _value(metrics, "evidence_precision") >= ACCEPTANCE_GATES["evidence_precision_min"],
        "replay_consistency": _value(metrics, "replay_consistency") >= ACCEPTANCE_GATES["replay_consistency_min"],
        "diagnosis_preservation": _value(metrics, "diagnosis_preservation") >= ACCEPTANCE_GATES["diagnosis_preservation_min"],
        "per_fault_floor": all(_value(_mapping(by_fault.get(fault)), "fault_accuracy") >= ACCEPTANCE_GATES["per_fault_accuracy_min"] for fault in FAULTS),
        "complete_zero_safety_counters": set(safety) >= set(P114_REQUIRED_SAFETY_COUNTERS) and all(int(safety.get(counter, -1)) == 0 for counter in P114_REQUIRED_SAFETY_COUNTERS),
    }
    payload: dict[str, Any] = {"schema_version": "p114.re2_ob_acceptance_gate.v1", "evaluation_hash": str(report.get("evaluation_hash", "")), "checks": checks, "passed": all(checks.values())}
    payload["gate_hash"] = stable_hash(payload)
    return payload


def _rate(n: int, d: int) -> dict[str, Any]:
    return {
        "value": round(n / d, 6) if d else 0.0,
        "numerator": n,
        "denominator": d,
    }


def build_p114_acceptance_lattices(packets: Sequence[Mapping[str, Any]], model: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    """Build authoritative lattices strictly from label-free candidate packets."""

    reject_candidate_truth_leak(packets)
    lattices = tuple(
        rerank_p114_lattice_with_fault_knn(
            packet,
            build_p114_hypothesis_lattice(packet),
            model,
        )
        for packet in packets
    )
    _validate_lattice_set(
        lattices,
        expected_case_ids=[str(packet.get("case_id", "")) for packet in packets],
        expected_packet_hashes=None,
    )
    return lattices


def _validate_lattice_set(
    lattices: Sequence[Mapping[str, Any]],
    *,
    expected_case_ids: Sequence[str],
    expected_packet_hashes: Sequence[str] | None,
) -> None:
    if len(lattices) != len(expected_case_ids):
        raise P114AcceptanceError("lattice_case_count_mismatch")
    if expected_packet_hashes is not None and len(lattices) != len(expected_packet_hashes):
        raise P114AcceptanceError("lattice_case_count_mismatch")
    packet_hashes = expected_packet_hashes or [str(lattice.get("source_packet_hash", "")) for lattice in lattices]
    for lattice, case_id, packet_hash in zip(lattices, expected_case_ids, packet_hashes, strict=True):
        if lattice.get("schema_version") != LATTICE_SCHEMA_VERSION:
            raise P114AcceptanceError("invalid_acceptance_lattice")
        if str(lattice.get("case_id", "")) != case_id:
            raise P114AcceptanceError("lattice_case_identity_mismatch")
        if not packet_hash or str(lattice.get("source_packet_hash", "")) != packet_hash:
            raise P114AcceptanceError("lattice_source_packet_mismatch")
        if not _hash_matches(lattice, "lattice_hash"):
            raise P114AcceptanceError("invalid_acceptance_lattice")


def _artifact_safety(
    lattices: Sequence[Mapping[str, Any]],
    *,
    source_sha256_after: str,
    frozen_source_sha256: str,
    runtime_safety: Mapping[str, Any],
    candidate_truth_validation: str,
) -> dict[str, int]:
    executed_actions = 0
    authority_violations = 0
    for lattice in lattices:
        executed_actions += len(_sequence(lattice.get("executed_actions")))
        if lattice.get("action_contract_status") != "disabled":
            authority_violations += 1
        for hypothesis in _mapping_sequence(lattice.get("hypotheses")):
            if hypothesis.get("action_contract_status") != "disabled":
                authority_violations += 1
    counters = {counter: int(runtime_safety.get(counter, -1)) for counter in P114_RUNTIME_SAFETY_COUNTERS}
    counters.update(
        {
            "truth_leak_count": int(candidate_truth_validation != "passed"),
            "executed_action_count": executed_actions,
            "artifact_authority_violation_count": authority_violations,
            "source_mutation_count": int(source_sha256_after != frozen_source_sha256),
        }
    )
    return counters


def _value(metrics: Mapping[str, Any], key: str) -> float:
    return float(_mapping(metrics.get(key)).get("value", -1.0))


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise P114AcceptanceError("timezone_required")
    return parsed.astimezone(UTC)


def _hash_matches(value: Mapping[str, Any], field: str) -> bool:
    return bool(value.get(field)) and str(value[field]) == stable_hash({key: item for key, item in value.items() if key != field})


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) else ()


def _mapping_sequence(value: Any) -> tuple[Mapping[str, Any], ...]:
    return tuple(item for item in _sequence(value) if isinstance(item, Mapping))
