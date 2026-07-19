"""Deterministic P177 citation, evidence, contradiction, and safety policy."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from app.services.p147_p152_contracts import stable_hash
from app.services.p177_tools import ToolRegistry

DECISION_SCHEMA_VERSION = "p177.final_decision.v1"
_UNSAFE_ADVICE_RE = re.compile(
    r"\b(kubectl|terraform|gcloud|aws|az|delete|restart|scale|apply|exec|rm\s+-rf|drop\s+database|production)\b",
    re.IGNORECASE,
)


class P177PolicyError(ValueError):
    """Raised when a final diagnosis cannot be supported by evidence."""


def validate_final_decision(
    decision: Mapping[str, Any],
    *,
    evidence_records: Sequence[Mapping[str, Any]],
    registry: ToolRegistry,
) -> dict[str, Any]:
    decision_type = _text(decision.get("decision_type"), "decision_type")
    if decision_type not in {"diagnosis", "abstain", "escalate"}:
        raise P177PolicyError("invalid_decision_type")
    uncertainty = _probability(decision.get("uncertainty"), "uncertainty")
    citations = _text_list(decision.get("cited_evidence_ids"), "cited_evidence_ids")
    if len(citations) != len(set(citations)):
        raise P177PolicyError("duplicate_citation")
    records = {_text(record.get("evidence_id"), "evidence_id"): record for record in evidence_records}
    cited_records = []
    for citation in citations:
        record = records.get(citation)
        if record is None:
            raise P177PolicyError("unsupported_citation")
        if record.get("fresh") is not True:
            raise P177PolicyError("stale_citation")
        if record.get("read_only") is not True:
            raise P177PolicyError("non_read_only_citation")
        cited_records.append(record)
    source_classes = {registry.tool_source_class(_text(record.get("tool_id"), "tool_id")) for record in cited_records}
    if decision_type == "diagnosis" and len(source_classes) < 2:
        raise P177PolicyError("source_diversity_required")
    contradictions = decision.get("contradictions_considered")
    if not isinstance(contradictions, Sequence) or isinstance(contradictions, (str, bytes, bytearray)) or not contradictions:
        raise P177PolicyError("contradictions_required")
    for item in contradictions:
        if not isinstance(item, Mapping) or not item.get("contradiction_id") or not item.get("resolution"):
            raise P177PolicyError("invalid_contradiction")
    advice = _text(decision.get("advice", ""), "advice")
    unsafe = bool(_UNSAFE_ADVICE_RE.search(advice))
    if unsafe:
        raise P177PolicyError("unsafe_action_advice")
    result: dict[str, Any] = {
        "schema_version": DECISION_SCHEMA_VERSION,
        "decision_type": decision_type,
        "root_cause": decision.get("root_cause"),
        "cited_evidence_ids": citations,
        "source_classes": sorted(source_classes),
        "citation_validity": 1.0,
        "unsupported_final_diagnosis": False,
        "unsafe_action_advice": False,
        "uncertainty": uncertainty,
        "contradiction_count": len(contradictions),
        "stop_reason": "final_diagnosis" if decision_type == "diagnosis" else decision_type,
    }
    result["decision_hash"] = stable_hash({key: value for key, value in result.items() if key != "decision_hash"})
    return result


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise P177PolicyError(f"invalid_{field}")
    return value


def _text_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)) or not value:
        raise P177PolicyError(f"invalid_{field}")
    result = [item for item in value if isinstance(item, str) and item]
    if len(result) != len(value):
        raise P177PolicyError(f"invalid_{field}")
    return result


def _probability(value: Any, field: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool) or not 0 <= float(value) <= 1:
        raise P177PolicyError(f"invalid_{field}")
    return float(value)
