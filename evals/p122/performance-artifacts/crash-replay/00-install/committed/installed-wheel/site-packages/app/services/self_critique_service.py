"""Deterministic self-critique gate for P7 action proposals."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

from app.models import Evidence, Incident


@dataclass(frozen=True)
class CritiqueResult:
    decision: str
    missing_evidence: list[str]
    alternate_causes: list[str]
    contradiction_flags: list[str]
    action_risk_objections: list[str]
    requires_human: bool
    reasons: list[str]
    blocks_auto_action: bool
    ambiguity: str

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
        alternate_causes: Sequence[str] = (),
        contradictions: Sequence[str] = (),
        memory_warnings: Sequence[str] = (),
    ) -> CritiqueResult:
        missing: list[str] = []
        contradiction_flags: list[str] = [str(item) for item in contradictions]
        objections: list[str] = []
        alternates: list[str] = [str(item) for item in alternate_causes]
        score = float(confidence or 0.0)

        if evidence_count < 2:
            missing.append("at least two independent evidence records required")
        if score < 0.70:
            missing.append("confidence below 0.70 self-critique threshold")

        for hypothesis in hypotheses or []:
            title = str(hypothesis.get("title") or hypothesis.get("hypothesis") or "alternate cause")
            status = str(hypothesis.get("status", ""))
            h_conf = float(hypothesis.get("confidence", 0.0) or 0.0)
            if status in {"weak", "unknown"} and title not in alternates:
                alternates.append(title)
            if status in {"weak", "unknown"} and h_conf >= max(score - 0.1, 0.0) and title:
                contradiction_flags.append(f"competing hypothesis: {title}")

        if action_type and (action_type.startswith(("production.", "database.", "cloud.", "shell.")) or action_type == "human.escalate"):
            objections.append(f"action {action_type} cannot be auto-executed")
        objections.extend(str(item) for item in memory_warnings)

        reasons = [*missing, *contradiction_flags, *objections]
        ambiguity = "high" if contradiction_flags or alternates or len(missing) >= 2 else "low"
        requires_human = bool(reasons or (alternates and score < 0.85))
        prohibited = any("cannot be auto-executed" in item or "prohibited" in item for item in objections)
        decision = "proceed"
        if requires_human:
            decision = "escalate" if prohibited or score < 0.70 else "approval_required"
        return CritiqueResult(
            decision=decision,
            missing_evidence=missing,
            alternate_causes=alternates,
            contradiction_flags=contradiction_flags,
            action_risk_objections=objections,
            requires_human=requires_human,
            reasons=reasons,
            blocks_auto_action=requires_human,
            ambiguity=ambiguity,
        )


def critique_diagnosis(
    incident: Incident,
    evidence: Sequence[Evidence],
    *,
    alternate_causes: Sequence[str] = (),
    action_type: str = "",
) -> CritiqueResult:
    contradictions: list[str] = []
    joined = "\n".join(str(item.content).lower() for item in evidence)
    for marker in ("conflict", "conflicting", "ambiguous", "unknown", "poison", "injection"):
        if marker in joined:
            contradictions.append(f"evidence contains {marker}")
    return SelfCritiqueService().critique(
        confidence=incident.confidence,
        evidence_count=len(evidence),
        action_type=action_type,
        alternate_causes=alternate_causes,
        contradictions=contradictions,
    )
