"""Deterministic, evidence-bound service/fault hypothesis generation for P114."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p114_re2_loader import CANDIDATE_SCHEMA_VERSION

LATTICE_SCHEMA_VERSION = "p114.hypothesis_lattice.v1"
HYPOTHESIS_SCHEMA_VERSION = "p114.hypothesis.v1"
FAULTS = ("cpu", "mem", "disk", "delay", "loss", "socket")
_MAX_HYPOTHESES = 60


class P114HypothesisError(ValueError):
    """Raised when a candidate packet cannot produce a safe hypothesis lattice."""


def build_p114_hypothesis_lattice(packet: Mapping[str, Any], *, max_hypotheses: int = 30) -> dict[str, Any]:
    if packet.get("schema_version") != CANDIDATE_SCHEMA_VERSION:
        raise P114HypothesisError("invalid_candidate_schema")
    if max_hypotheses < 1 or max_hypotheses > _MAX_HYPOTHESES:
        raise P114HypothesisError("invalid_hypothesis_budget")
    case_id = str(packet.get("case_id", ""))
    if not case_id:
        raise P114HypothesisError("missing_case_id")
    graph = _mapping(packet.get("evidence_graph"))
    nodes = [_validate_node(item) for item in _sequence(graph.get("nodes"))]
    if not nodes:
        raise P114HypothesisError("missing_evidence_nodes")
    node_ids = [str(node["node_id"]) for node in nodes]
    if len(node_ids) != len(set(node_ids)):
        raise P114HypothesisError("duplicate_evidence_node")
    ordered_nodes = sorted(nodes, key=lambda node: str(node["node_id"]))
    services = sorted({str(node["subject"]) for node in ordered_nodes if str(node["subject"])})
    if not services:
        raise P114HypothesisError("missing_service_candidates")

    hypotheses = [_hypothesis(case_id, service, fault, ordered_nodes) for service in services for fault in FAULTS]
    service_scores = {service: _service_anomaly_strength(ordered_nodes, service) for service in services}
    ranked_services = sorted(
        services,
        key=lambda service: (-service_scores[service], service),
    )
    service_rank = {service: index for index, service in enumerate(ranked_services)}
    hypotheses.sort(
        key=lambda item: (
            service_rank[str(item["service"])],
            -float(item["score"]),
            str(item["fault"]),
        )
    )
    selected = hypotheses[:max_hypotheses]
    top_service = ranked_services[0]
    ranked_faults = sorted(
        FAULTS,
        key=lambda fault: (
            -next(float(item["score"]) for item in hypotheses if item["service"] == top_service and item["fault"] == fault),
            fault,
        ),
    )
    payload: dict[str, Any] = {
        "schema_version": LATTICE_SCHEMA_VERSION,
        "case_id": case_id,
        "source_packet_hash": stable_hash(_packet_identity(packet, ordered_nodes)),
        "ranked_services": ranked_services,
        "ranked_faults": ranked_faults,
        "hypotheses": selected,
        "candidate_counts": {
            "services": len(services),
            "faults": len(FAULTS),
            "generated": len(hypotheses),
            "retained": len(selected),
        },
        "evidence_node_ids": sorted(node_ids),
        "action_contract_status": "disabled",
        "executed_actions": [],
    }
    payload["lattice_hash"] = stable_hash(payload)
    return payload


def _hypothesis(
    case_id: str,
    service: str,
    fault: str,
    nodes: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    local = [node for node in nodes if node["subject"] == service]
    typed = [node for node in local if _fault_for_signal(str(node["signal"])) == fault]
    typed_scored = sorted(
        ((_oriented_strength(node, fault), node) for node in typed),
        key=lambda item: (-item[0], str(item[1]["node_id"])),
    )
    supporting = [node for score, node in typed_scored if score > 0][:5]
    contradicting = [node for score, node in typed_scored if score < 0][:3]
    logs = sorted(
        (node for node in local if node["modality"] == "log_template"),
        key=lambda node: (-_absolute_strength(node), str(node["node_id"])),
    )[:3]
    typed_score = sum(max(score, 0.0) for score, _node in typed_scored[:3])
    contradiction_penalty = sum(abs(min(score, 0.0)) for score, _node in typed_scored[:3])
    locality_score = sum(_absolute_strength(node) for node in logs) * 0.08
    score = round(max(0.0, typed_score + locality_score - contradiction_penalty * 0.5), 12)
    support_ids = sorted({str(node["node_id"]) for node in (*supporting, *logs)})
    contradiction_ids = sorted({str(node["node_id"]) for node in contradicting})
    missing = [] if typed else ["typed_metric_evidence"]
    identity = {
        "case_id": case_id,
        "service": service,
        "fault": fault,
        "supporting_evidence_ids": support_ids,
        "contradicting_evidence_ids": contradiction_ids,
        "missing_evidence": missing,
    }
    return {
        "schema_version": HYPOTHESIS_SCHEMA_VERSION,
        "hypothesis_id": "hyp_" + hashlib.sha256(stable_hash(identity).encode()).hexdigest()[:24],
        "service": service,
        "fault": fault,
        "score": score,
        "supporting_evidence_ids": support_ids,
        "contradicting_evidence_ids": contradiction_ids,
        "missing_evidence": missing,
        "action_contract_status": "disabled",
    }


def _fault_for_signal(signal: str) -> str | None:
    normalized = signal.lower().replace("_", "-")
    if "cpu" in normalized:
        return "cpu"
    if "mem" in normalized or "memory" in normalized:
        return "mem"
    if "disk" in normalized or "io" in normalized:
        return "disk"
    if "socket" in normalized or "connection" in normalized:
        return "socket"
    if "latency" in normalized or "duration" in normalized:
        return "delay"
    if "error" in normalized or "loss" in normalized or "drop" in normalized or "workload" in normalized:
        return "loss"
    return None


def _oriented_strength(node: Mapping[str, Any], fault: str) -> float:
    delta = float(node["delta"])
    pre = abs(float(node["pre_value"]))
    ratio = max(-1_000_000.0, min(1_000_000.0, delta / max(pre, 1.0)))
    if fault == "loss" and "workload" in str(node["signal"]).lower():
        ratio *= -1.0
    strength = math.copysign(math.log1p(abs(ratio)), ratio)
    signal = str(node["signal"]).lower()
    if fault == "socket" and ("socket" in signal or "connection" in signal):
        strength = math.copysign(abs(strength) ** 2 * 6.0, strength)
    elif fault == "loss" and "workload" in signal:
        strength *= 10.0
    elif fault == "loss" and ("error" in signal or "drop" in signal or "loss" in signal):
        strength *= 3.0
    elif fault == "mem":
        strength *= 1.25
    return round(strength, 12)


def _absolute_strength(node: Mapping[str, Any]) -> float:
    return min(20.0, abs(float(node["delta"])) / max(abs(float(node["pre_value"])), 1.0))


def _service_anomaly_strength(nodes: Sequence[Mapping[str, Any]], service: str) -> float:
    local = [node for node in nodes if node["subject"] == service]
    metric_strengths: list[float] = []
    for node in local:
        if node["modality"] != "metric":
            continue
        ratio = float(node["delta"]) / max(abs(float(node["pre_value"])), 1.0)
        if "workload" in str(node["signal"]).lower() and ratio < 0:
            ratio *= -1.0
        metric_strengths.append(max(0.0, min(100.0, ratio)))
    log_strengths = sorted(
        (_absolute_strength(node) for node in local if node["modality"] == "log_template"),
        reverse=True,
    )[:3]
    return round((max(metric_strengths) if metric_strengths else 0.0) + sum(log_strengths) * 0.08, 12)


def _validate_node(value: Any) -> Mapping[str, Any]:
    node = _mapping(value)
    required = {"node_id", "modality", "subject", "signal", "pre_value", "post_value", "delta"}
    if not required <= set(node) or not all(str(node.get(key, "")) for key in ("node_id", "modality", "subject", "signal")):
        raise P114HypothesisError("invalid_evidence_node")
    for key in ("pre_value", "post_value", "delta"):
        number = node.get(key)
        if not isinstance(number, int | float) or isinstance(number, bool) or not math.isfinite(float(number)):
            raise P114HypothesisError("nonfinite_evidence_value")
    return node


def _packet_identity(packet: Mapping[str, Any], nodes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    graph = _mapping(packet.get("evidence_graph"))
    edges = sorted(
        (_mapping(edge) for edge in _sequence(graph.get("edges"))),
        key=lambda edge: str(edge.get("edge_id", "")),
    )
    return {
        "schema_version": packet.get("schema_version"),
        "case_id": packet.get("case_id"),
        "system": packet.get("system"),
        "injection_timestamp": packet.get("injection_timestamp"),
        "evidence_graph": {"nodes": list(nodes), "edges": edges},
        "source_integrity": _mapping(packet.get("source_integrity")),
    }


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) else ()
