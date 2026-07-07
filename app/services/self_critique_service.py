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


class SelfCritiqueService:
    def critique(
        self,
        *,
        confidence: float | None,
        evidence_count: int,
        action_type: str,
        hypotheses: Sequence[Mapping[str, Any]] | None = None,
        memory_warnings: Sequence[str] = (),
    ) -> SelfCritique:
        missing: list[str] = []
        contradictions: list[str] = []
        objections: list[str] = []
        alternates: list[str] = []
        score = float(confidence or 0.0)
        if evidence_count < 2:
            missing.append("at least two independent evidence records")
        if score < 0.7:
            missing.append("confidence above human-on-exception threshold")
        for hypothesis in hypotheses or []:
            status = str(hypothesis.get("status", ""))
            title = str(hypothesis.get("title", "alternate cause"))
            h_conf = float(hypothesis.get("confidence", 0.0) or 0.0)
            if status in {"weak", "unknown"}:
                alternates.append(title)
            if status in {"weak", "unknown"} and h_conf >= max(score - 0.1, 0.0) and title:
                contradictions.append(f"competing hypothesis: {title}")
        if action_type in {"shell.execute", "database.mutate", "cloud.delete_resource", "production.rollback", "production.restart_service"}:
            objections.append("action type is prohibited or production/destructive")
        if memory_warnings:
            objections.extend(memory_warnings)
        decision = "proceed"
        if objections or contradictions or missing:
            decision = "approval_required" if score >= 0.7 and not any("prohibited" in item for item in objections) else "escalate"
        return SelfCritique(tuple_decision(decision), tuple(missing), tuple(alternates), tuple(contradictions), tuple(objections))

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
