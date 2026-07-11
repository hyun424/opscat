"""P120 ontology mapping and identity normalization."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from app.services.p110_evaluation import stable_hash

ONTOLOGY_MAPPING_SCHEMA_VERSION = "p120.ontology_mapping.v1"
ENTITY_IDENTITY_SCHEMA_VERSION = "p120.entity_identity.v1"
MAPPING_METRICS_SCHEMA_VERSION = "p120.ontology_mapping_metrics.v1"
ALLOWED_EFFECTS = frozenset({"continue_with_penalty", "investigate_more", "abstain", "escalate", "fail_closed"})
MUTATION_TARGET_PATTERNS = (
    re.compile(r"\b(?:prod|production|staging)[-_. ]+(?:cluster|namespace|database|account|target|url)\b", re.I),
    re.compile(r"\b(?:write|mutate|delete|restart|scale|rollback|deploy|kubectl|terraform apply)\b", re.I),
)


class P120OntologyError(ValueError):
    """Raised when ontology mapping violates P120 identity or authority contracts."""


def normalize_entity_identity(*, system_id: str, source_entity_id: str, entity_kind: str, service_id: str | None = None, topology_refs: Sequence[str] = ()) -> dict[str, Any]:
    """Create a stable canonical entity identity without erasing source identity."""

    if not system_id or not source_entity_id or not entity_kind:
        raise P120OntologyError("missing_entity_identity")
    canonical_parts = [system_id, entity_kind, service_id or "", _slug(source_entity_id)]
    payload: dict[str, Any] = {
        "schema_version": ENTITY_IDENTITY_SCHEMA_VERSION,
        "system_id": system_id,
        "source_entity_id": source_entity_id,
        "entity_kind": entity_kind,
        "service_id": service_id,
        "topology_refs": [str(item) for item in topology_refs],
        "canonical_entity_ref": "opscat://" + "/".join(part for part in canonical_parts if part),
    }
    payload["identity_hash"] = stable_hash(payload)
    return payload


def build_mapping_record(data: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a P120 ontology mapping record."""

    payload = {
        "schema_version": ONTOLOGY_MAPPING_SCHEMA_VERSION,
        "mapping_id": _text(data, "mapping_id"),
        "source_label": _text(data, "source_label"),
        "source_context": dict(_required_mapping(data, "source_context")),
        "canonical_label": _text(data, "canonical_label"),
        "mapping_confidence": float(data.get("mapping_confidence", -1.0)),
        "ambiguity_set": _text_list(data, "ambiguity_set", allow_empty=True),
        "human_review_required": bool(data.get("human_review_required")),
        "evidence_refs": _text_list(data, "evidence_refs"),
        "ontology_version": _text(data, "ontology_version"),
        "split": _text(data, "split"),
        "system_id": _text(data, "system_id"),
        "source_hash": _text(data, "source_hash"),
        "source_id": str(data.get("source_id", "")),
        "incident_family": str(data.get("incident_family", "")),
        "action_family": str(data.get("action_family", "")),
        "outcome_label": data.get("outcome_label"),
        "decision_effect": str(data.get("decision_effect", "continue_with_penalty")),
    }
    _validate_mapping_payload(payload)
    payload["mapping_hash"] = stable_hash(payload)
    return payload


def validate_mapping_record(record: Mapping[str, Any]) -> None:
    """Reject ambiguous, hidden-answer, or authority-coercing mappings."""

    if record.get("schema_version") != ONTOLOGY_MAPPING_SCHEMA_VERSION:
        raise P120OntologyError("invalid_mapping_schema")
    _validate_mapping_payload(record)
    submitted = str(record.get("mapping_hash", ""))
    unhashed = {key: value for key, value in record.items() if key != "mapping_hash"}
    if submitted and submitted != stable_hash(unhashed):
        raise P120OntologyError("mapping_record_tampered")


def mapping_quality_metrics(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Report denominator-visible mapping quality per system/source/family."""

    if not records:
        raise P120OntologyError("missing_mapping_records")
    buckets: dict[str, dict[str, Any]] = {}
    for record in records:
        validate_mapping_record(record)
        key = "|".join(
            [
                str(record.get("system_id", "")),
                str(record.get("source_id", "")),
                str(record.get("incident_family", "")),
                str(record.get("action_family", "")),
            ]
        )
        bucket = buckets.setdefault(key, {"denominator": 0, "ambiguous": 0, "human_review_required": 0, "confidence_sum": 0.0})
        bucket["denominator"] += 1
        bucket["confidence_sum"] += float(record["mapping_confidence"])
        if record.get("ambiguity_set"):
            bucket["ambiguous"] += 1
        if record.get("human_review_required"):
            bucket["human_review_required"] += 1
    metrics = []
    for key, bucket in sorted(buckets.items()):
        system_id, source_id, incident_family, action_family = key.split("|")
        denominator = int(bucket["denominator"])
        metrics.append(
            {
                "system_id": system_id,
                "source_id": source_id,
                "incident_family": incident_family,
                "action_family": action_family,
                "denominator": denominator,
                "ambiguity_rate": bucket["ambiguous"] / denominator,
                "human_review_rate": bucket["human_review_required"] / denominator,
                "mean_confidence": bucket["confidence_sum"] / denominator,
            }
        )
    payload: dict[str, Any] = {"schema_version": MAPPING_METRICS_SCHEMA_VERSION, "metrics": metrics}
    payload["metrics_hash"] = stable_hash(payload)
    return payload


def _validate_mapping_payload(payload: Mapping[str, Any]) -> None:
    required = {
        "mapping_id",
        "source_label",
        "source_context",
        "canonical_label",
        "mapping_confidence",
        "ambiguity_set",
        "human_review_required",
        "evidence_refs",
        "ontology_version",
        "split",
        "system_id",
        "source_hash",
    }
    missing = sorted(required - set(str(key) for key in payload))
    if missing:
        raise P120OntologyError(f"missing_mapping_field:{missing[0]}")
    confidence = payload.get("mapping_confidence")
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0.0 <= float(confidence) <= 1.0:
        raise P120OntologyError("invalid_mapping_confidence")
    if not str(payload.get("source_hash", "")).startswith("sha256:"):
        raise P120OntologyError("invalid_source_hash")
    if str(payload.get("decision_effect")) not in ALLOWED_EFFECTS:
        raise P120OntologyError("invalid_decision_effect")
    ambiguity_set = _sequence(payload.get("ambiguity_set"))
    if ambiguity_set and (float(confidence) >= 0.9 or payload.get("decision_effect") == "continue_with_penalty"):
        raise P120OntologyError("ambiguous_mapping_forced")
    if ambiguity_set and payload.get("human_review_required") is not True:
        raise P120OntologyError("ambiguous_mapping_missing_review")
    if _contains_hidden_answer(payload.get("source_label")) or _contains_hidden_answer(payload.get("source_context")):
        raise P120OntologyError("source_label_hidden_answer_leak")
    if _contains_mutation_target(payload.get("source_label")) or _contains_mutation_target(payload.get("source_context")) or _contains_mutation_target(payload.get("canonical_label")):
        raise P120OntologyError("production_like_target_normalized_as_fixture")
    if not _sequence(payload.get("evidence_refs")):
        raise P120OntologyError("missing_mapping_evidence_refs")


def _contains_hidden_answer(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(_contains_hidden_answer(key) or _contains_hidden_answer(item) for key, item in value.items())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_hidden_answer(item) for item in value)
    if isinstance(value, str):
        normalized = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
        return any(token in normalized for token in ("hidden_answer", "answer_key", "ground_truth", "scorer_only_truth", "oracle_root_cause"))
    return False


def _contains_mutation_target(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(_contains_mutation_target(key) or _contains_mutation_target(item) for key, item in value.items())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_mutation_target(item) for item in value)
    if isinstance(value, str):
        return any(pattern.search(value) for pattern in MUTATION_TARGET_PATTERNS)
    return False


def _text(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise P120OntologyError(f"missing_{key}")
    return value


def _text_list(data: Mapping[str, Any], key: str, *, allow_empty: bool = False) -> list[str]:
    value = data.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)) or (not allow_empty and not value):
        raise P120OntologyError(f"missing_{key}")
    result = [str(item) for item in value]
    if any(not item.strip() for item in result):
        raise P120OntologyError(f"invalid_{key}")
    return result


def _required_mapping(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = data.get(key)
    if not isinstance(value, Mapping) or not value:
        raise P120OntologyError(f"missing_{key}")
    return value


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


__all__ = [
    "ENTITY_IDENTITY_SCHEMA_VERSION",
    "MAPPING_METRICS_SCHEMA_VERSION",
    "ONTOLOGY_MAPPING_SCHEMA_VERSION",
    "P120OntologyError",
    "build_mapping_record",
    "mapping_quality_metrics",
    "normalize_entity_identity",
    "validate_mapping_record",
]
