"""P117 measured utility, calibration, and abstention policy."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from app.services.p110_evaluation import stable_hash

P117_UTILITY_REPORT_SCHEMA_VERSION = "p117.utility_report.v1"
_SHA256_PREFIX = "sha256:"


class P117UtilityError(ValueError):
    """Raised when utility cannot be measured safely."""


@dataclass(frozen=True)
class P117UtilityReport:
    schema_version: str
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", _freeze(self.payload))

    def to_dict(self) -> dict[str, Any]:
        thawed = _thaw(self.payload)
        if not isinstance(thawed, dict):
            raise P117UtilityError("invalid_utility_payload")
        return thawed


def compute_expected_utility(
    *,
    measured_benefit_vs_no_action: Mapping[str, Any],
    expected_harm: Mapping[str, Any],
    uncertainty_penalty: Mapping[str, Any],
    contradiction_penalty: Mapping[str, Any],
    missing_evidence_penalty: Mapping[str, Any],
    authority_penalty: Mapping[str, Any],
    natural_recovery_dominates: bool,
) -> P117UtilityReport:
    """Compute measured expected utility and preserve every component."""

    if natural_recovery_dominates:
        raise P117UtilityError("natural_recovery_dominates")
    components = {
        "measured_benefit_vs_no_action": _component(measured_benefit_vs_no_action, "measured_benefit_vs_no_action"),
        "expected_harm": _component(expected_harm, "expected_harm"),
        "uncertainty_penalty": _component(uncertainty_penalty, "uncertainty_penalty"),
        "contradiction_penalty": _component(contradiction_penalty, "contradiction_penalty"),
        "missing_evidence_penalty": _component(missing_evidence_penalty, "missing_evidence_penalty"),
        "authority_penalty": _component(authority_penalty, "authority_penalty"),
    }
    expected = (
        components["measured_benefit_vs_no_action"]["value"]
        - components["expected_harm"]["value"]
        - components["uncertainty_penalty"]["value"]
        - components["contradiction_penalty"]["value"]
        - components["missing_evidence_penalty"]["value"]
        - components["authority_penalty"]["value"]
    )
    low = (
        components["measured_benefit_vs_no_action"]["interval"][0]
        - components["expected_harm"]["interval"][1]
        - components["uncertainty_penalty"]["interval"][1]
        - components["contradiction_penalty"]["interval"][1]
        - components["missing_evidence_penalty"]["interval"][1]
        - components["authority_penalty"]["interval"][1]
    )
    high = (
        components["measured_benefit_vs_no_action"]["interval"][1]
        - components["expected_harm"]["interval"][0]
        - components["uncertainty_penalty"]["interval"][0]
        - components["contradiction_penalty"]["interval"][0]
        - components["missing_evidence_penalty"]["interval"][0]
        - components["authority_penalty"]["interval"][0]
    )
    payload: dict[str, Any] = {
        "schema_version": P117_UTILITY_REPORT_SCHEMA_VERSION,
        "expected_utility": round(float(expected), 12),
        "utility_interval": [round(float(low), 12), round(float(high), 12)],
        "components": components,
        "natural_recovery_dominates": False,
    }
    payload["utility_hash"] = stable_hash(payload)
    return P117UtilityReport(P117_UTILITY_REPORT_SCHEMA_VERSION, payload)


def calibrate_confidence(rows: Sequence[Mapping[str, Any]], *, bin_count: int = 10) -> dict[str, Any]:
    if bin_count <= 0:
        raise P117UtilityError("invalid_bin_count")
    normalized = [_calibration_row(row) for row in rows]
    if not normalized:
        raise P117UtilityError("missing_calibration_rows")
    by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in normalized:
        by_family[str(row["scenario_family"])].append(row)
    report: dict[str, Any] = {
        "overall": _ece(normalized, bin_count=bin_count),
        "by_family": {family: _ece(family_rows, bin_count=bin_count) for family, family_rows in sorted(by_family.items())},
    }
    report["calibration_hash"] = stable_hash(report)
    return report


def select_label_from_utility(
    *,
    expected_utility: float,
    utility_interval: Sequence[float],
    confidence: float,
    confidence_threshold: float,
    prerequisites_complete: bool,
    contraindications_present: bool,
    missing_required_evidence: bool,
    measured_outcomes_present: bool,
    authority_counter_total: int,
    escalation_required: bool,
) -> dict[str, Any]:
    low, high = _utility_interval(utility_interval)
    if authority_counter_total != 0:
        return {"selected_label": "abstain", "reason": "authority_counter_nonzero"}
    if escalation_required:
        return {"selected_label": "escalate", "reason": "human_authority_required"}
    if not measured_outcomes_present:
        return {"selected_label": "abstain", "reason": "missing_measured_outcomes"}
    if not prerequisites_complete:
        return {"selected_label": "abstain", "reason": "prerequisites_incomplete"}
    if contraindications_present:
        return {"selected_label": "abstain", "reason": "contraindication_present"}
    if confidence < confidence_threshold:
        return {"selected_label": "abstain", "reason": "low_confidence"}
    if missing_required_evidence:
        return {"selected_label": "investigate_more", "reason": "missing_required_evidence"}
    if low <= 0 <= high:
        return {"selected_label": "abstain", "reason": "utility_interval_crosses_zero"}
    if expected_utility <= 0 or high <= 0:
        return {"selected_label": "no_action", "reason": "utility_not_positive"}
    return {"selected_label": "act", "reason": None}


def _component(data: Mapping[str, Any], expected_name: str) -> dict[str, Any]:
    name = _required_text(data, "name")
    if name != expected_name:
        raise P117UtilityError(f"unexpected_component:{name}")
    denominator = data.get("denominator")
    if not isinstance(denominator, int | float) or isinstance(denominator, bool) or denominator <= 0:
        raise P117UtilityError(f"missing_denominator:{name}")
    nullable = bool(data.get("nullable"))
    value = data.get("value")
    if value is None:
        if nullable:
            raise P117UtilityError(f"nullable_metric_unevaluable:{name}")
        raise P117UtilityError(f"missing_value:{name}")
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise P117UtilityError(f"invalid_value:{name}")
    numerator = data.get("numerator")
    if not isinstance(numerator, int | float) or isinstance(numerator, bool):
        raise P117UtilityError(f"missing_numerator:{name}")
    interval = _utility_interval(data.get("interval"))
    artifact_hash = _required_text(data, "artifact_hash")
    if not artifact_hash.startswith(_SHA256_PREFIX):
        raise P117UtilityError(f"invalid_artifact_hash:{name}")
    return {
        "name": name,
        "numerator": float(numerator),
        "denominator": float(denominator),
        "nullable": nullable,
        "value": float(value),
        "interval": [interval[0], interval[1]],
        "scenario_family": _required_text(data, "scenario_family"),
        "action_family": _required_text(data, "action_family"),
        "split": _required_text(data, "split"),
        "artifact_hash": artifact_hash,
    }


def _calibration_row(row: Mapping[str, Any]) -> dict[str, Any]:
    confidence = row.get("confidence")
    if not isinstance(confidence, int | float) or isinstance(confidence, bool) or not 0 <= float(confidence) <= 1:
        raise P117UtilityError("invalid_confidence")
    if not isinstance(row.get("correct"), bool):
        raise P117UtilityError("invalid_correct")
    return {
        "scenario_family": _required_text(row, "scenario_family"),
        "confidence": float(confidence),
        "correct": bool(row["correct"]),
    }


def _ece(rows: Sequence[Mapping[str, Any]], *, bin_count: int) -> dict[str, Any]:
    bins: list[dict[str, Any]] = []
    ece = 0.0
    for index in range(bin_count):
        low = index / bin_count
        high = (index + 1) / bin_count
        members = [
            row
            for row in rows
            if (low <= float(row["confidence"]) < high) or (index == bin_count - 1 and float(row["confidence"]) == 1.0)
        ]
        if not members:
            continue
        avg_confidence = sum(float(row["confidence"]) for row in members) / len(members)
        accuracy = sum(1 for row in members if bool(row["correct"])) / len(members)
        gap = abs(avg_confidence - accuracy)
        ece += (len(members) / len(rows)) * gap
        bins.append({"low": low, "high": high, "denominator": len(members), "avg_confidence": avg_confidence, "accuracy": accuracy, "gap": gap})
    return {"denominator": len(rows), "ece": ece, "bins": bins}


def _utility_interval(value: Any) -> tuple[float, float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)) or len(value) != 2:
        raise P117UtilityError("invalid_utility_interval")
    low, high = value
    if not isinstance(low, int | float) or isinstance(low, bool) or not isinstance(high, int | float) or isinstance(high, bool):
        raise P117UtilityError("invalid_utility_interval")
    if float(low) > float(high):
        raise P117UtilityError("invalid_utility_interval")
    return (float(low), float(high))


def _required_text(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise P117UtilityError(f"missing_{key}")
    return value.strip()


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
