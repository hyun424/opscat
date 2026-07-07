"""P7 deterministic self-critique gate for agent diagnoses."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CritiqueResult:
    missing_evidence: tuple[str, ...]
    alternate_causes: tuple[str, ...]
    contradiction_flags: tuple[str, ...]
    action_risk_objections: tuple[str, ...]
    ambiguity: str
    blocks_auto_action: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "missing_evidence": list(self.missing_evidence),
            "alternate_causes": list(self.alternate_causes),
            "contradiction_flags": list(self.contradiction_flags),
            "action_risk_objections": list(self.action_risk_objections),
            "ambiguity": self.ambiguity,
            "blocks_auto_action": self.blocks_auto_action,
        }


class SelfCritiqueService:
    def critique(
        self,
        *,
        confidence: float | None,
        evidence_count: int,
        alternate_causes: list[str] | tuple[str, ...] = (),
        contradictions: list[str] | tuple[str, ...] = (),
        action_type: str = "",
    ) -> CritiqueResult:
        missing: list[str] = []
        objections: list[str] = []
        score = confidence or 0.0
        if evidence_count < 2:
            missing.append("at_least_two_independent_evidence_items")
        if score >= 0.85 and evidence_count < 3:
            missing.append("high_confidence_requires_three_supporting_items")
        if score < 0.70:
            objections.append("confidence_below_auto_action_threshold")
        if action_type in {"production.rollback", "production.restart_service", "database.mutate", "shell.execute"}:
            objections.append("requested_action_is_prohibited_or_production_mutation")
        if action_type == "mock.create_rollback_pr" and alternate_causes:
            objections.append("rollback_pr_has_plausible_alternate_cause")
        ambiguity = "high" if missing or contradictions or score < 0.70 else ("medium" if alternate_causes else "low")
        blocks = ambiguity == "high" or bool(objections)
        return CritiqueResult(
            missing_evidence=tuple(missing),
            alternate_causes=tuple(alternate_causes),
            contradiction_flags=tuple(contradictions),
            action_risk_objections=tuple(objections),
            ambiguity=ambiguity,
            blocks_auto_action=blocks,
        )
