"""P7 deterministic self-critique before risk/action proposal."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SelfCritique:
    decision: str
    missing_evidence: tuple[str, ...]
    alternate_causes: tuple[str, ...]
    contradiction_flags: tuple[str, ...]
    action_risk_objections: tuple[str, ...]

    @property
    def blocks_auto_action(self) -> bool:
        return self.decision in {"escalate", "approval_required"} or bool(self.missing_evidence or self.contradiction_flags or self.action_risk_objections)

    def to_dict(self) -> dict[str, object]:
        return {
            "decision": self.decision,
            "missing_evidence": list(self.missing_evidence),
            "alternate_causes": list(self.alternate_causes),
            "contradiction_flags": list(self.contradiction_flags),
            "action_risk_objections": list(self.action_risk_objections),
            "blocks_auto_action": self.blocks_auto_action,
        }


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
            if h_conf >= max(score - 0.1, 0.0) and title:
                contradictions.append(f"competing hypothesis: {title}")
        if action_type in {"shell.execute", "database.mutate", "cloud.delete_resource", "production.rollback", "production.restart_service"}:
            objections.append("action type is prohibited or production/destructive")
        if memory_warnings:
            objections.extend(memory_warnings)
        decision = "proceed"
        if objections or contradictions or missing:
            decision = "approval_required" if score >= 0.7 and not any("prohibited" in item for item in objections) else "escalate"
        return SelfCritique(tuple_decision(decision), tuple(missing), tuple(alternates), tuple(contradictions), tuple(objections))


def tuple_decision(value: str) -> str:
    return value
