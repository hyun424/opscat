"""Deterministic fault-family prior trained only on governed P111 splits."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any

SCHEMA_VERSION = "p111.fault_prior.v1"
FEATURES = ("cpu", "mem", "load", "latency", "error")
FAULTS = ("cpu", "mem", "disk", "delay", "loss")


class P111FaultPriorError(ValueError):
    """Raised when a learned fault prior violates its contract."""


def train_fault_prior(samples: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]], *, training_repetitions: Sequence[int]) -> dict[str, Any]:
    service_catalog = sorted(
        {
            str(entry.get("service", ""))
            for digest, _truth in samples
            for entry in digest.get("entries", [])
            if isinstance(entry, Mapping) and entry.get("service")
        }
    )
    prototypes: list[dict[str, Any]] = []
    seen_faults: set[str] = set()
    for digest, truth in samples:
        root_service = str(truth.get("root_service", ""))
        fault = str(truth.get("fault_type", ""))
        if fault not in FAULTS or root_service not in service_catalog:
            raise P111FaultPriorError("invalid_training_fault")
        seen_faults.add(fault)
        prototypes.append(
            {
                "root_service": root_service,
                "fault": fault,
                "vector": _global_vector(digest, service_catalog),
            }
        )
    if seen_faults != set(FAULTS) or not prototypes:
        raise P111FaultPriorError("incomplete_training_fault_set")
    artifact: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": "nearest_governed_prototype_unstandardized.v1",
        "feature_schema": [f"{service}:{metric}:signed_log_relative" for service in service_catalog for metric in FEATURES],
        "service_catalog": service_catalog,
        "root_service_catalog": sorted({str(item["root_service"]) for item in prototypes}),
        "training_repetitions": sorted(set(int(item) for item in training_repetitions)),
        "training_case_count": len(samples),
        "prototypes": prototypes,
    }
    artifact["artifact_hash"] = stable_hash(artifact)
    return artifact


def score_fault_priors(digest: Mapping[str, Any], services: Sequence[str], artifact: Mapping[str, Any]) -> dict[str, Any]:
    validate_fault_prior(artifact)
    catalog = [str(item) for item in artifact["service_catalog"]]
    vector = _global_vector(digest, catalog)
    prototypes = artifact["prototypes"]
    prototype_distances = [
        (
            str(item["root_service"]),
            str(item["fault"]),
            _round(_distance(vector, item["vector"])),
        )
        for item in prototypes
    ]
    allowed_services = set(str(item) for item in services)
    service_distances = {
        service: min(distance for root, _fault, distance in prototype_distances if root == service)
        for service in artifact["root_service_catalog"]
        if service in allowed_services
    }
    fault_distances = {
        fault: min(distance for _root, candidate_fault, distance in prototype_distances if candidate_fault == fault)
        for fault in FAULTS
    }
    return {
        "schema_version": "p111.fault_prior_scores.v1",
        "artifact_hash": artifact["artifact_hash"],
        "ranked_services": sorted(service_distances, key=lambda service: (service_distances[service], service)),
        "ranked_faults": sorted(FAULTS, key=lambda fault: (fault_distances[fault], fault)),
        "service_distances": service_distances,
        "fault_distances": fault_distances,
    }


def validate_fault_prior(artifact: Mapping[str, Any]) -> None:
    if artifact.get("schema_version") != SCHEMA_VERSION:
        raise P111FaultPriorError("invalid_fault_prior_schema")
    submitted = str(artifact.get("artifact_hash", ""))
    unhashed = {key: value for key, value in artifact.items() if key != "artifact_hash"}
    if submitted != stable_hash(unhashed):
        raise P111FaultPriorError("fault_prior_tampered")
    prototypes = artifact.get("prototypes")
    service_catalog = artifact.get("service_catalog")
    if not isinstance(prototypes, Sequence) or not prototypes or not isinstance(service_catalog, Sequence):
        raise P111FaultPriorError("invalid_fault_prior_shape")


def _global_vector(digest: Mapping[str, Any], services: Sequence[str]) -> list[float]:
    entries = {
        (str(item.get("service", "")), str(item.get("metric", ""))): item
        for item in digest.get("entries", [])
        if isinstance(item, Mapping)
    }
    vector: list[float] = []
    for service in services:
        for metric in FEATURES:
            entry = entries.get((service, metric), {})
            relative = float(entry.get("relative_change", 0.0))
            signed_log = math.copysign(math.log1p(abs(relative)), relative) if relative else 0.0
            vector.append(_round(signed_log))
    return vector


def _distance(left: Sequence[float], right: Sequence[float]) -> float:
    return sum((float(a) - float(b)) ** 2 for a, b in zip(left, right, strict=True))


def stable_hash(value: Any) -> str:
    return f"sha256:{hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()}"


def _round(value: float) -> float:
    return round(float(value), 12)
