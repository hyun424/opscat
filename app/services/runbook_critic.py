"""Deterministic P8 runbook fit critic.

The critic produces local text artifacts only. It never mutates runbooks or
calls external systems; downstream war-room/report surfaces can render the
returned reasons and suggestions.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from typing import Any, Literal

from app.models import Evidence, Incident
from app.services.escalation import protected_domain
from app.services.incident_memory import IncidentMemoryMatch
from app.services.redaction import redact_text
from app.services.runbook_service import Runbook

RunbookFit = Literal["good_fit", "weak_fit", "unsafe", "insufficient_evidence"]

_PROHIBITED_ACTION_PREFIXES = ("production.", "database.", "cloud.", "shell.")


@dataclass(frozen=True)
class RunbookCritique:
    runbook_key: str
    fit: RunbookFit
    reasons: list[str]
    suggestions: list[str]
    blocks_auto_action: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def critique_runbook(
    incident: Incident,
    runbook: Runbook,
    evidence: Sequence[Evidence],
    *,
    memory_matches: Iterable[IncidentMemoryMatch] = (),
    action_type: str = "",
    policy_reasons: Sequence[str] = (),
) -> RunbookCritique:
    """Critique selected runbook fit before action.

    Fit precedence is intentionally conservative:
    unsafe > insufficient_evidence > weak_fit > good_fit.
    """

    reasons: list[str] = []
    suggestions: list[str] = []
    evidence_count = len(evidence)
    confidence = float(incident.confidence or 0.0)
    prior_failed = any(match.failed_prior_action for match in memory_matches)

    unsafe_reasons = _unsafe_reasons(incident, runbook, action_type=action_type, policy_reasons=policy_reasons)
    if unsafe_reasons:
        reasons.extend(unsafe_reasons)
        suggestions.extend(
            [
                "require explicit human approval before any mutating step",
                "prefer a diagnostic-only or read-only runbook until safety constraints are resolved",
            ]
        )
        return _result(runbook.key, "unsafe", reasons, suggestions, blocks=True)

    if evidence_count < 2:
        reasons.append("insufficient evidence: fewer than two independent evidence records")
        suggestions.append("collect at least two independent evidence records")
    if confidence < 0.55:
        reasons.append("insufficient evidence: confidence below 0.55 runbook-fit threshold")
        suggestions.append("collect stronger root-cause evidence before selecting a mutating runbook")
    if reasons:
        return _result(runbook.key, "insufficient_evidence", reasons, suggestions, blocks=True)

    if prior_failed:
        reasons.append("prior failed remediation found for a similar incident and action")
        suggestions.append("compare the failed prior before repeating this runbook")
    if confidence < 0.75:
        reasons.append("weak fit: confidence below 0.75 for autonomous runbook use")
        suggestions.append("ask a human to confirm the selected runbook before action")
    if _runbook_missing_required_context(runbook, evidence):
        reasons.append("weak fit: runbook preconditions are not fully supported by evidence")
        suggestions.append("collect evidence for the runbook preconditions before action")
    if reasons:
        return _result(runbook.key, "weak_fit", reasons, suggestions, blocks=True)

    return RunbookCritique(runbook_key=runbook.key, fit="good_fit", reasons=["runbook fit supported by evidence and local safety gates"], suggestions=[], blocks_auto_action=False)


def _unsafe_reasons(
    incident: Incident,
    runbook: Runbook,
    *,
    action_type: str,
    policy_reasons: Sequence[str],
) -> list[str]:
    reasons: list[str] = []
    if action_type.startswith(_PROHIBITED_ACTION_PREFIXES):
        reasons.append(f"prohibited action type selected: {action_type}")
    if any(step.risk_hint == "prohibited" for step in runbook.steps):
        reasons.append("runbook contains a prohibited step")
    if any("deny" in reason.lower() or "prohibited" in reason.lower() for reason in policy_reasons):
        reasons.append("policy gate reports denied or prohibited action")
    if protected_domain(incident.service) and any(step.risk_hint in {"low", "medium", "high", "prohibited"} for step in runbook.steps):
        reasons.append(f"protected service {incident.service} requires human review before mutating runbook steps")
    return reasons


def _runbook_missing_required_context(runbook: Runbook, evidence: Sequence[Evidence]) -> bool:
    evidence_text = " ".join(f"{item.type} {item.content}" for item in evidence).lower()
    for step in runbook.steps:
        for precondition in step.preconditions:
            tokens = {token for token in precondition.replace("_", " ").split() if len(token) > 3}
            if tokens and not any(token in evidence_text for token in tokens):
                return True
    return False


def _result(runbook_key: str, fit: RunbookFit, reasons: list[str], suggestions: list[str], *, blocks: bool) -> RunbookCritique:
    return RunbookCritique(
        runbook_key=runbook_key,
        fit=fit,
        reasons=[redact_text(reason) for reason in _dedupe(reasons)],
        suggestions=[redact_text(suggestion) for suggestion in _dedupe(suggestions)],
        blocks_auto_action=blocks,
    )


def _dedupe(items: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            output.append(item)
    return output
