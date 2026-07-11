"""Service-name-agnostic 3-NN fault classifier for P114 evidence lattices."""

from __future__ import annotations

import json
import math
import statistics
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p114_hypothesis_lattice import FAULTS, LATTICE_SCHEMA_VERSION, build_p114_hypothesis_lattice
from app.services.p114_re2_loader import CANDIDATE_SCHEMA_VERSION, P114RE2Case

MODEL_SCHEMA_VERSION = "p114.fault_knn.v1"
PREDICTION_SCHEMA_VERSION = "p114.fault_knn_prediction.v1"
CV_SCHEMA_VERSION = "p114.fault_knn_loso.v1"
FEATURES = ("cpu", "mem", "diskio", "latency-50", "latency-90", "workload", "socket", "error")
K_NEIGHBORS = 3


class P114FaultKNNError(ValueError):
    """Raised when a fault model or candidate packet violates the contract."""


def train_p114_fault_knn(cases: Sequence[P114RE2Case]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for case in cases:
        fault = str(case.scorer_only_truth.get("fault_type", ""))
        service = str(case.scorer_only_truth.get("root_service", ""))
        if fault not in FAULTS or not service:
            raise P114FaultKNNError("invalid_training_truth")
        rows.append({"fault": fault, "features": list(extract_p114_fault_features(case.to_candidate_packet(), service))})
    if len(rows) < len(FAULTS) * K_NEIGHBORS:
        raise P114FaultKNNError("insufficient_training_cases")
    counts = Counter(str(row["fault"]) for row in rows)
    if any(counts[fault] < K_NEIGHBORS for fault in FAULTS):
        raise P114FaultKNNError("insufficient_fault_coverage")
    scales = []
    for index in range(len(FEATURES)):
        values = [float(row["features"][index]) for row in rows]
        center = statistics.median(values)
        mad = statistics.median(abs(value - center) for value in values)
        scales.append(round(max(mad, 0.15), 12))
    payload: dict[str, Any] = {
        "schema_version": MODEL_SCHEMA_VERSION,
        "algorithm": "service_agnostic_robust_l1_knn",
        "k": K_NEIGHBORS,
        "features": list(FEATURES),
        "scales": scales,
        "training_rows": sorted(rows, key=lambda row: (str(row["fault"]), tuple(row["features"]))),
        "training_summary": {"case_count": len(rows), "fault_counts": dict(sorted(counts.items()))},
        "contains_service_names": False,
        "contains_case_ids": False,
        "action_contract_status": "disabled",
    }
    payload["model_hash"] = stable_hash(payload)
    return payload


def predict_p114_fault(packet: Mapping[str, Any], service: str, model: Mapping[str, Any]) -> dict[str, Any]:
    _validate_model(model)
    vector = extract_p114_fault_features(packet, service)
    scales = [float(item) for item in _sequence(model.get("scales"))]
    neighbors: list[tuple[float, str, int]] = []
    for index, row in enumerate(_mapping_sequence(model.get("training_rows"))):
        fault = str(row.get("fault", ""))
        training = [float(item) for item in _sequence(row.get("features"))]
        distance = sum(abs(vector[position] - training[position]) / scales[position] for position in range(len(FEATURES)))
        neighbors.append((round(distance, 12), fault, index))
    nearest = sorted(neighbors)[:K_NEIGHBORS]
    votes = Counter(fault for _distance, fault, _index in nearest)
    distance_sums = {fault: sum(distance for distance, neighbor_fault, _index in nearest if neighbor_fault == fault) for fault in FAULTS}
    ranked = sorted(FAULTS, key=lambda fault: (-votes[fault], distance_sums[fault], fault))
    payload: dict[str, Any] = {
        "schema_version": PREDICTION_SCHEMA_VERSION,
        "model_hash": str(model["model_hash"]),
        "ranked_faults": ranked,
        "top_neighbor_votes": dict(sorted(votes.items())),
        "action_contract_status": "disabled",
    }
    payload["prediction_hash"] = stable_hash(payload)
    return payload


def rerank_p114_lattice_with_fault_knn(packet: Mapping[str, Any], lattice: Mapping[str, Any], model: Mapping[str, Any]) -> dict[str, Any]:
    if lattice.get("schema_version") != LATTICE_SCHEMA_VERSION or not _hash_matches(lattice, "lattice_hash"):
        raise P114FaultKNNError("invalid_lattice")
    ranked_services = [str(item) for item in _sequence(lattice.get("ranked_services"))]
    if not ranked_services:
        raise P114FaultKNNError("missing_ranked_services")
    fault_ranks = {service: predict_p114_fault(packet, service, model)["ranked_faults"] for service in ranked_services}
    service_order = {service: index for index, service in enumerate(ranked_services)}
    hypotheses = [dict(item) for item in _mapping_sequence(lattice.get("hypotheses"))]
    hypotheses.sort(
        key=lambda item: (
            service_order[str(item.get("service", ""))],
            fault_ranks[str(item.get("service", ""))].index(str(item.get("fault", ""))),
        )
    )
    payload = json.loads(json.dumps(lattice, sort_keys=True, allow_nan=False))
    payload["hypotheses"] = hypotheses
    payload["ranked_faults"] = fault_ranks[ranked_services[0]]
    payload["fault_model_schema_version"] = MODEL_SCHEMA_VERSION
    payload["fault_model_hash"] = str(model["model_hash"])
    payload["lattice_hash"] = stable_hash({key: value for key, value in payload.items() if key != "lattice_hash"})
    return payload


def evaluate_p114_fault_knn_loso(cases: Sequence[P114RE2Case]) -> dict[str, Any]:
    services = sorted({str(case.scorer_only_truth.get("root_service", "")) for case in cases})
    if len(services) < 3:
        raise P114FaultKNNError("insufficient_service_groups")
    rows: list[dict[str, Any]] = []
    for held_service in services:
        training = [case for case in cases if case.scorer_only_truth.get("root_service") != held_service]
        validation = [case for case in cases if case.scorer_only_truth.get("root_service") == held_service]
        model = train_p114_fault_knn(training)
        for case in validation:
            packet = case.to_candidate_packet()
            lattice = rerank_p114_lattice_with_fault_knn(packet, build_p114_hypothesis_lattice(packet), model)
            top = _mapping_sequence(lattice.get("hypotheses"))[0]
            truth_service = str(case.scorer_only_truth["root_service"])
            truth_fault = str(case.scorer_only_truth["fault_type"])
            rows.append(
                {
                    "fault": truth_fault,
                    "service_correct": int(str(top.get("service", "")) == truth_service),
                    "fault_correct": int(str(top.get("fault", "")) == truth_fault),
                    "joint_correct": int(str(top.get("service", "")) == truth_service and str(top.get("fault", "")) == truth_fault),
                }
            )
    by_fault = {fault: _aggregate([row for row in rows if row["fault"] == fault]) for fault in FAULTS}
    payload: dict[str, Any] = {
        "schema_version": CV_SCHEMA_VERSION,
        "benchmark_role": "consumed_development_grouped_cross_validation",
        "grouping": "leave_one_root_service_out",
        "service_group_count": len(services),
        "metrics": _aggregate(rows),
        "by_fault": by_fault,
        "safety": {"executed_action_count": 0, "action_authority_enabled_count": 0},
    }
    payload["evaluation_hash"] = stable_hash(payload)
    return payload


def extract_p114_fault_features(packet: Mapping[str, Any], service: str) -> tuple[float, ...]:
    if packet.get("schema_version") != CANDIDATE_SCHEMA_VERSION or not service:
        raise P114FaultKNNError("invalid_candidate_packet")
    values: dict[str, list[float]] = {feature: [] for feature in FEATURES}
    nodes = _mapping_sequence(_mapping(packet.get("evidence_graph")).get("nodes"))
    for node in nodes:
        if str(node.get("subject", "")) != service or node.get("modality") != "metric":
            continue
        signal = str(node.get("signal", ""))
        if signal not in values:
            continue
        pre = float(node.get("pre_value", 0.0))
        delta = float(node.get("delta", 0.0))
        if not math.isfinite(pre) or not math.isfinite(delta):
            raise P114FaultKNNError("nonfinite_feature")
        ratio = delta / max(abs(pre), 1.0)
        values[signal].append(math.copysign(math.log1p(abs(ratio)), ratio))
    return tuple(round(statistics.median(values[feature]), 12) if values[feature] else 0.0 for feature in FEATURES)


def _validate_model(model: Mapping[str, Any]) -> None:
    if model.get("schema_version") != MODEL_SCHEMA_VERSION or not _hash_matches(model, "model_hash"):
        raise P114FaultKNNError("invalid_model")
    if tuple(_sequence(model.get("features"))) != FEATURES or int(model.get("k", 0)) != K_NEIGHBORS:
        raise P114FaultKNNError("model_contract_mismatch")
    if len(_sequence(model.get("scales"))) != len(FEATURES):
        raise P114FaultKNNError("model_scale_mismatch")


def _aggregate(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    count = len(rows)
    return {
        "case_count": count,
        "service_top1": _rate(sum(int(row["service_correct"]) for row in rows), count),
        "fault_accuracy": _rate(sum(int(row["fault_correct"]) for row in rows), count),
        "joint_top1": _rate(sum(int(row["joint_correct"]) for row in rows), count),
    }


def _rate(numerator: int, denominator: int) -> dict[str, Any]:
    return {"value": round(numerator / denominator, 6) if denominator else 0.0, "numerator": numerator, "denominator": denominator}


def _hash_matches(value: Mapping[str, Any], field: str) -> bool:
    submitted = str(value.get(field, ""))
    return bool(submitted) and submitted == stable_hash({key: item for key, item in value.items() if key != field})


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) else ()


def _mapping_sequence(value: Any) -> tuple[Mapping[str, Any], ...]:
    return tuple(item for item in _sequence(value) if isinstance(item, Mapping))
