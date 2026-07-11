"""Service-name-independent RCA prototype model for P112."""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

SCHEMA_VERSION = "p112.cross_system_model.v1"
SCORE_SCHEMA_VERSION = "p112.cross_system_scores.v1"
FAULTS = ("cpu", "mem", "disk", "delay", "loss")
FAMILIES = ("cpu", "mem", "disk", "net_drop", "net_error", "throughput", "request", "error", "latency")
_PAIR_WEIGHTS = (0.5, 1.0, 2.0)


class P112ModelError(ValueError):
    """Raised when a P112 model artifact or sample violates governance."""


def train_cross_system_model(
    samples: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]],
    *,
    training_source_hash: str,
    training_repetitions: Sequence[int],
    pair_weight: float = 1.0,
) -> dict[str, Any]:
    repetitions = sorted(set(int(item) for item in training_repetitions))
    if not repetitions or any(item not in {1, 2, 3} for item in repetitions):
        raise P112ModelError("invalid_training_repetitions")
    if pair_weight not in _PAIR_WEIGHTS:
        raise P112ModelError("unsupported_pair_weight")
    if not training_source_hash.startswith("sha256:"):
        raise P112ModelError("invalid_training_source_hash")

    positive: list[tuple[str, list[float]]] = []
    negative: list[list[float]] = []
    feature_names: tuple[str, ...] | None = None
    seen_faults: set[str] = set()
    for packet, truth in samples:
        vectors = service_feature_vectors(packet)
        root_service = str(truth.get("root_service", ""))
        fault = str(truth.get("fault_type", ""))
        if fault not in FAULTS or root_service not in vectors:
            raise P112ModelError("invalid_training_truth")
        seen_faults.add(fault)
        if feature_names is None:
            feature_names = tuple(vectors[root_service]["feature_names"])
        for service, payload in vectors.items():
            vector = [float(item) for item in payload["vector"]]
            if service == root_service:
                positive.append((fault, vector))
            else:
                negative.append(vector)
    if seen_faults != set(FAULTS) or feature_names is None:
        raise P112ModelError("incomplete_training_fault_set")

    all_vectors = [vector for _fault, vector in positive] + negative
    means, scales = _fit_scaler(all_vectors)
    prototypes = [
        {"fault": fault, "vector": _scale(vector, means, scales)} for fault, vector in positive
    ]
    negative_prototype = _mean_vector([_scale(vector, means, scales) for vector in negative])
    artifact: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": "service_agnostic_scaled_nearest_prototype.v1",
        "feature_schema": list(feature_names),
        "training_source_hash": training_source_hash,
        "training_repetitions": repetitions,
        "training_case_count": len(samples),
        "positive_prototype_count": len(prototypes),
        "negative_sample_count": len(negative),
        "pair_weight": pair_weight,
        "scaler": {"means": means, "scales": scales},
        "fault_prototypes": prototypes,
        "negative_prototype": negative_prototype,
    }
    artifact["artifact_hash"] = stable_hash(artifact)
    validate_model(artifact)
    return artifact


def score_cross_system_model(packet: Mapping[str, Any], artifact: Mapping[str, Any]) -> dict[str, Any]:
    validate_model(artifact)
    vectors = service_feature_vectors(packet)
    means = [float(item) for item in artifact["scaler"]["means"]]
    scales = [float(item) for item in artifact["scaler"]["scales"]]
    prototypes = artifact["fault_prototypes"]
    negative = [float(item) for item in artifact["negative_prototype"]]
    pair_weight = float(artifact["pair_weight"])
    pair_scores: dict[str, dict[str, float]] = {}
    service_scores: dict[str, float] = {}
    fault_scores: dict[str, float] = {fault: math.inf for fault in FAULTS}
    for service, payload in vectors.items():
        vector = _scale([float(item) for item in payload["vector"]], means, scales)
        negative_distance = _distance(vector, negative)
        pair_scores[service] = {}
        for fault in FAULTS:
            fault_distance = min(
                _distance(vector, prototype["vector"])
                for prototype in prototypes
                if prototype["fault"] == fault
            )
            # Prefer a vector that is closer to a root/fault prototype than to
            # the aggregate non-root prototype. This is entirely feature based.
            score = fault_distance + pair_weight * max(0.0, fault_distance - negative_distance)
            score = _round(score)
            pair_scores[service][fault] = score
            fault_scores[fault] = min(fault_scores[fault], score)
        service_scores[service] = min(pair_scores[service].values())
    ranked_pairs = sorted(
        ((score, service, fault) for service, faults in pair_scores.items() for fault, score in faults.items()),
        key=lambda item: (item[0], item[1], item[2]),
    )
    return {
        "schema_version": SCORE_SCHEMA_VERSION,
        "artifact_hash": artifact["artifact_hash"],
        "ranked_services": sorted(service_scores, key=lambda item: (service_scores[item], item)),
        "ranked_faults": sorted(FAULTS, key=lambda item: (fault_scores[item], item)),
        "ranked_pairs": [
            {"service": service, "fault": fault, "score": score}
            for score, service, fault in ranked_pairs[:15]
        ],
        "service_scores": {key: _round(value) for key, value in sorted(service_scores.items())},
        "fault_scores": {key: _round(value) for key, value in sorted(fault_scores.items())},
    }


def service_feature_vectors(packet: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows = [item for item in _sequence(packet.get("evidence")) if isinstance(item, Mapping)]
    diagnostics = [item for item in _sequence(packet.get("diagnostic_evidence")) if isinstance(item, Mapping)]
    grouped: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
    application_services: set[str] = set()
    for row in rows:
        service = str(row.get("service", ""))
        metric = str(row.get("metric", ""))
        window = str(row.get("window", ""))
        if not service or window not in {"pre", "post", "delta"}:
            continue
        family = canonical_metric_family(metric)
        if family:
            if family in {"latency", "error", "request"}:
                application_services.add(service)
            grouped[(service, family)][window] = _finite(row.get("value"))
    services = sorted(application_services or {service for service, _family in grouped})
    raw: dict[str, dict[str, list[float]]] = {
        service: {family: [] for family in FAMILIES} for service in services
    }
    for (service, family), windows in grouped.items():
        if service not in raw:
            continue
        pre = windows.get("pre", 0.0)
        post = windows.get("post", pre + windows.get("delta", 0.0))
        delta = windows.get("delta", post - pre)
        relative = delta / max(abs(pre), 1.0)
        raw[service][family].append(math.copysign(math.log1p(abs(relative)), relative) if relative else 0.0)

    if diagnostics:
        diagnostic_services = {
            str(item.get("service", ""))
            for item in diagnostics
            if canonical_metric_family(str(item.get("metric", ""))) in {"latency", "error", "request"}
        }
        if diagnostic_services:
            services = sorted(diagnostic_services)
            raw = {service: {family: [] for family in FAMILIES} for service in services}
            for item in diagnostics:
                service = str(item.get("service", ""))
                family = canonical_metric_family(str(item.get("metric", "")))
                if service in raw and family:
                    score = max(-100.0, min(100.0, _finite(item.get("signed_score"))))
                    raw[service][family].append(math.copysign(math.log1p(abs(score)), score) if score else 0.0)

    family_abs: dict[str, dict[str, float]] = {family: {} for family in FAMILIES}
    family_signed: dict[str, dict[str, float]] = {family: {} for family in FAMILIES}
    for service in services:
        for family in FAMILIES:
            values = raw[service][family]
            selected = max(values, key=lambda item: (abs(item), item)) if values else 0.0
            family_signed[family][service] = selected
            family_abs[family][service] = abs(selected)

    names: list[str] = []
    vectors: dict[str, list[float]] = {service: [] for service in services}
    for family in FAMILIES:
        total = sum(family_abs[family].values())
        median = statistics.median(family_abs[family].values()) if services else 0.0
        ordered = sorted(services, key=lambda item: (family_abs[family][item], item))
        ranks = {service: index / max(len(ordered) - 1, 1) for index, service in enumerate(ordered)}
        family_names = (
            f"{family}:signed_max",
            f"{family}:absolute_max",
            f"{family}:share",
            f"{family}:rank_percentile",
            f"{family}:median_contrast",
            f"{family}:active_metric_count",
        )
        names.extend(family_names)
        for service in services:
            absolute = family_abs[family][service]
            vectors[service].extend(
                (
                    family_signed[family][service],
                    absolute,
                    absolute / total if total else 0.0,
                    ranks[service],
                    absolute - median,
                    float(sum(1 for item in raw[service][family] if abs(item) > 1e-12)),
                )
            )
    interaction_names = (
        "coupling:loss_minus_delay",
        "coupling:delay_minus_loss",
        "coupling:error_plus_drop",
        "coupling:latency_without_error",
        "coupling:throughput_with_error",
    )
    names.extend(interaction_names)
    for service in services:
        loss = family_abs["net_drop"][service] + family_abs["net_error"][service] + family_abs["error"][service]
        delay = family_abs["latency"][service]
        throughput = family_abs["throughput"][service] + family_abs["request"][service]
        vectors[service].extend(
            (
                loss - delay,
                delay - loss,
                loss,
                max(0.0, delay - loss),
                throughput + loss,
            )
        )
    return {
        service: {"feature_names": list(names), "vector": [_round(item) for item in vector]}
        for service, vector in vectors.items()
    }


def canonical_metric_family(metric: str) -> str | None:
    lower = metric.lower().replace("_", "-")
    if "latency" in lower or "duration" in lower:
        return "latency"
    if "packets-dropped" in lower or "drop-total" in lower or "packet-loss" in lower:
        return "net_drop"
    if "network" in lower and ("error" in lower or "errs" in lower):
        return "net_error"
    if "istio-error" in lower or "error-rate" in lower:
        return "error"
    if "request" in lower:
        return "request"
    if "network" in lower and any(token in lower for token in ("bytes", "packets")):
        return "throughput"
    if "istio-bytes" in lower:
        return "throughput"
    if "cpu" in lower or "load" in lower:
        return "cpu"
    if "memory" in lower or "mem-" in lower:
        return "mem"
    if any(token in lower for token in ("disk", "filesystem", "fs-reads", "fs-writes")):
        return "disk"
    return None


def validate_model(artifact: Mapping[str, Any]) -> None:
    if artifact.get("schema_version") != SCHEMA_VERSION:
        raise P112ModelError("invalid_model_schema")
    submitted = str(artifact.get("artifact_hash", ""))
    unhashed = {key: value for key, value in artifact.items() if key != "artifact_hash"}
    if submitted != stable_hash(unhashed):
        raise P112ModelError("model_artifact_tampered")
    rendered = json.dumps(artifact, sort_keys=True, ensure_ascii=True).lower()
    forbidden = ("case_id", "root_service", "source_path", "carts", "catalogue", "orders", "payment", "user")
    if any(token in rendered for token in forbidden):
        raise P112ModelError("training_identity_leak")
    if sorted(set(int(item) for item in _sequence(artifact.get("training_repetitions")))) != [1, 2, 3]:
        raise P112ModelError("invalid_training_repetitions")
    prototypes = artifact.get("fault_prototypes")
    if not isinstance(prototypes, Sequence) or not prototypes:
        raise P112ModelError("missing_fault_prototypes")
    if {str(item.get("fault")) for item in prototypes if isinstance(item, Mapping)} != set(FAULTS):
        raise P112ModelError("incomplete_fault_prototypes")


def stable_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _fit_scaler(vectors: Sequence[Sequence[float]]) -> tuple[list[float], list[float]]:
    if not vectors:
        raise P112ModelError("missing_training_vectors")
    width = len(vectors[0])
    if width == 0 or any(len(vector) != width for vector in vectors):
        raise P112ModelError("inconsistent_feature_width")
    means = [sum(float(vector[index]) for vector in vectors) / len(vectors) for index in range(width)]
    scales = []
    for index, mean in enumerate(means):
        variance = sum((float(vector[index]) - mean) ** 2 for vector in vectors) / len(vectors)
        scales.append(max(math.sqrt(variance), 1e-9))
    return [_round(item) for item in means], [_round(item) for item in scales]


def _scale(vector: Sequence[float], means: Sequence[float], scales: Sequence[float]) -> list[float]:
    if len(vector) != len(means) or len(means) != len(scales):
        raise P112ModelError("feature_schema_mismatch")
    return [_round((float(value) - float(mean)) / float(scale)) for value, mean, scale in zip(vector, means, scales, strict=True)]


def _mean_vector(vectors: Sequence[Sequence[float]]) -> list[float]:
    if not vectors:
        raise P112ModelError("missing_negative_vectors")
    return [_round(sum(float(vector[index]) for vector in vectors) / len(vectors)) for index in range(len(vectors[0]))]


def _distance(left: Sequence[float], right: Sequence[float]) -> float:
    return sum((float(a) - float(b)) ** 2 for a, b in zip(left, right, strict=True))


def _finite(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) else ()


def _round(value: float) -> float:
    return round(float(value), 12)
