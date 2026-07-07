"""Deterministic self-critique gate for P7 action proposals."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.models import Evidence, Incident


@dataclass(frozen=True)
class CritiqueResult:
    missing_evidence: list[str]
    alternate_causes: list[str]
    contradiction_flags: list[str]
    action_risk_objections: list[str]
    requires_human: bool
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def critique_diagnosis(
    incident: Incident,
    evidence: list[Evidence],
    *,
    alternate_causes: list[str] | None = None,
    action_type: str | None = None,
) -> CritiqueResult:
    confidence = float(incident.confidence or 0.0)
    missing: list[str] = []
    contradictions: list[str] = []
    objections: list[str] = []
    alternates = list(alternate_causes or [])

    if len(evidence) < 2:
        missing.append("at least two independent evidence records required")
    if not incident.root_cause_candidate:
        missing.append("root cause candidate missing")
    joined = "\n".join(item.content.lower() for item in evidence)
    for marker in ("conflict", "conflicting", "ambiguous", "unknown", "poison", "injection"):
        if marker in joined:
            contradictions.append(f"evidence contains {marker}")
    if confidence < 0.7:
        contradictions.append("confidence below 0.70 self-critique threshold")
    if action_type and (action_type.startswith(("production.", "database.", "cloud.", "shell.")) or action_type == "human.escalate"):
        objections.append(f"action {action_type} cannot be auto-executed")
    reasons = [*missing, *contradictions, *objections]
    requires_human = bool(reasons or alternates and confidence < 0.85)
    return CritiqueResult(missing, alternates, contradictions, objections, requires_human, reasons)
