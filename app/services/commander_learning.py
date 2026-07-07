"""P9 learning signal summarizer for prior local/mock outcomes."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from app.services.redaction import redact_value

LearningRoute = Literal["use_with_caution", "human_required", "no_prior_signal"]
_OUTCOMES = ("success", "failed", "rejected", "stale", "poisoned", "unknown")


@dataclass(frozen=True)
class CommanderLearningSignal:
    counts: dict[str, int]
    warnings: tuple[str, ...]
    usable_memory_ids: tuple[str, ...]
    route: LearningRoute
    local_mock_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "counts": dict(self.counts),
            "warnings": list(self.warnings),
            "usable_memory_ids": list(self.usable_memory_ids),
            "route": self.route,
            "local_mock_only": self.local_mock_only,
        }


def summarize_learning_signals(matches: Iterable[Any] | None = None) -> CommanderLearningSignal:
    safe_matches = list(redact_value(list(matches or [])))
    counts = {key: 0 for key in _OUTCOMES}
    warnings: list[str] = []
    usable: list[str] = []
    for item in safe_matches:
        row = _as_mapping(item)
        outcome = _classify(row)
        counts[outcome] += 1
        memory_id = str(row.get("incident_id") or row.get("id") or "")
        if outcome == "success" and memory_id:
            usable.append(memory_id)
        row_warnings = [str(value) for value in _as_list(row.get("warnings", []))]
        warnings.extend(row_warnings)
        if outcome == "failed":
            warnings.append("prior_failed_remediation")
        elif outcome == "rejected":
            warnings.append("prior_human_rejection")
        elif outcome == "stale":
            warnings.append("stale_memory")
        elif outcome == "poisoned":
            warnings.append("poisoned_memory")
    warnings_tuple = tuple(sorted(set(warnings)))
    if not safe_matches:
        route: LearningRoute = "no_prior_signal"
    elif any(key in warnings_tuple for key in ("prior_failed_remediation", "prior_human_rejection", "stale_memory", "poisoned_memory")):
        route = "human_required"
    else:
        route = "use_with_caution"
    return CommanderLearningSignal(counts=counts, warnings=warnings_tuple, usable_memory_ids=tuple(sorted(set(usable))), route=route)


def _classify(row: Mapping[str, Any]) -> str:
    outcome = str(row.get("outcome") or "unknown").lower()
    warnings = {str(value) for value in _as_list(row.get("warnings", []))}
    if outcome in _OUTCOMES:
        return outcome
    if row.get("failed_prior_action") or "prior_failed_remediation" in warnings:
        return "failed"
    return "unknown"


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        result = to_dict()
        if isinstance(result, Mapping):
            return result
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []
