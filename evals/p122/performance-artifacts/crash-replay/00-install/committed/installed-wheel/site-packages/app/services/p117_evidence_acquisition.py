"""P117 frozen evidence-acquisition taxonomy and declarative VOI gate."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from app.services.p110_evaluation import stable_hash

P117_EVIDENCE_REQUEST_SCHEMA_VERSION = "p117.evidence_acquisition_request.v1"


class P117EvidenceAcquisitionError(ValueError):
    """Raised when evidence acquisition crosses the declarative benchmark boundary."""


@dataclass(frozen=True)
class EvidenceClass:
    class_id: str
    description: str
    declarative_only: bool = True


@dataclass(frozen=True)
class P117EvidenceRequest:
    schema_version: str
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", _freeze(self.payload))

    def to_dict(self) -> dict[str, Any]:
        thawed = _thaw(self.payload)
        if not isinstance(thawed, dict):
            raise P117EvidenceAcquisitionError("invalid_request_payload")
        return thawed


FROZEN_EVIDENCE_TAXONOMY: tuple[EvidenceClass, ...] = (
    EvidenceClass("metric", "missing metric window or metric coverage"),
    EvidenceClass("log", "missing log class or error-template evidence"),
    EvidenceClass("topology", "missing topology relation"),
    EvidenceClass("deploy_config", "missing deploy or configuration marker"),
    EvidenceClass("saturation", "missing saturation signal"),
    EvidenceClass("dependency", "missing dependency edge or dependency health"),
    EvidenceClass("queue", "missing queue depth or lag signal"),
    EvidenceClass("dns", "missing DNS signal"),
    EvidenceClass("certificate", "missing certificate validity signal"),
    EvidenceClass("quota", "missing quota or rate-limit signal"),
    EvidenceClass("validation", "missing signed action-pack validation evidence"),
    EvidenceClass("rollback", "missing rollback readiness evidence"),
)
_TAXONOMY_IDS = frozenset(item.class_id for item in FROZEN_EVIDENCE_TAXONOMY)
EVIDENCE_TAXONOMY_HASH = stable_hash([item.__dict__ for item in FROZEN_EVIDENCE_TAXONOMY])

_LEAKAGE_RE = re.compile(r"(hidden|truth|oracle|answer|label|root[_ -]?cause|fault|scorer|query|prompt|markdown|filename)", re.IGNORECASE)
_LIVE_ACCESS_RE = re.compile(r"(https?://|ssh://|postgres://|mysql://|kubectl|curl|aws\s|gcloud\s|select\s+.+\s+from|mutation|delete|restart)", re.IGNORECASE)


def compute_value_of_information(
    *,
    expected_utility_delta: float,
    uncertainty_reduction: float,
    acquisition_cost: float,
    authority_constraints: Mapping[str, Any],
) -> dict[str, Any]:
    """Compute a deterministic VOI score without granting retrieval authority."""

    _validate_number(expected_utility_delta, "expected_utility_delta")
    _validate_number(uncertainty_reduction, "uncertainty_reduction")
    _validate_number(acquisition_cost, "acquisition_cost")
    authority_blocked = any(bool(authority_constraints.get(key)) for key in ("live_access", "credential_scope", "connector_call", "mutation_authority"))
    score = expected_utility_delta + uncertainty_reduction - acquisition_cost
    return {
        "expected_utility_delta": float(expected_utility_delta),
        "uncertainty_reduction": float(uncertainty_reduction),
        "acquisition_cost": float(acquisition_cost),
        "authority_blocked": authority_blocked,
        "score": round(score, 12),
        "positive": score > 0 and not authority_blocked,
    }


def build_evidence_request(
    *,
    missing_evidence_markers: Mapping[str, str],
    expected_utility_delta: float,
    uncertainty_reduction: float,
    acquisition_cost: float,
    authority_constraints: Mapping[str, Any],
) -> P117EvidenceRequest:
    """Build a declarative `investigate_more`/`abstain` evidence request."""

    if not missing_evidence_markers:
        raise P117EvidenceAcquisitionError("missing_evidence_markers")
    requests: list[dict[str, Any]] = []
    for marker, class_id in sorted(missing_evidence_markers.items(), key=lambda item: str(item[0])):
        marker_text = _required_safe_text(marker, "missing_evidence_marker")
        class_text = _required_safe_text(class_id, "evidence_class")
        if class_text not in _TAXONOMY_IDS:
            if _LIVE_ACCESS_RE.search(class_text):
                raise P117EvidenceAcquisitionError("live_access_request")
            raise P117EvidenceAcquisitionError(f"unknown_evidence_class:{class_text}")
        requests.append({"class_id": class_text, "missing_evidence_marker": marker_text, "declarative_only": True})

    voi = compute_value_of_information(
        expected_utility_delta=expected_utility_delta,
        uncertainty_reduction=uncertainty_reduction,
        acquisition_cost=acquisition_cost,
        authority_constraints=authority_constraints,
    )
    selected_label = "investigate_more" if voi["positive"] else "abstain"
    payload: dict[str, Any] = {
        "schema_version": P117_EVIDENCE_REQUEST_SCHEMA_VERSION,
        "selected_label": selected_label,
        "requests": requests,
        "value_of_information": voi,
        "taxonomy_hash": EVIDENCE_TAXONOMY_HASH,
        "live_access_request_count": 0,
    }
    payload["request_hash"] = stable_hash(payload)
    return P117EvidenceRequest(P117_EVIDENCE_REQUEST_SCHEMA_VERSION, payload)


def _required_safe_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise P117EvidenceAcquisitionError(f"missing_{field}")
    text = value.strip()
    if _LIVE_ACCESS_RE.search(text):
        raise P117EvidenceAcquisitionError("live_access_request")
    if _LEAKAGE_RE.search(text):
        raise P117EvidenceAcquisitionError("leakage_probe")
    return text


def _validate_number(value: Any, field: str) -> None:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise P117EvidenceAcquisitionError(f"invalid_{field}")


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value
