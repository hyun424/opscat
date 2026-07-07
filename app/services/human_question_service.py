"""Deterministic P8 human question generator.

Questions are safe local text artifacts tied to missing evidence or policy gate
failures. They deliberately avoid asking for credentials, tokens, passwords, or
raw secrets.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

from app.models import Incident
from app.services.escalation import MIN_AUTO_CONFIDENCE, protected_domain
from app.services.redaction import redact_text

_SENSITIVE_TERMS = ("password", "token", "secret", "credential", "api key", "authorization")


@dataclass(frozen=True)
class HumanQuestion:
    question: str
    why_it_matters: str
    source_gate: str
    safe_to_ask: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def generate_human_questions(
    incident: Incident,
    *,
    missing_evidence: Sequence[str] = (),
    conflicting_evidence: Sequence[str] = (),
    policy_reasons: Sequence[str] = (),
    simulation: Mapping[str, Any] | None = None,
    max_questions: int = 5,
) -> list[HumanQuestion]:
    questions: list[HumanQuestion] = []
    confidence = float(incident.confidence or 0.0)

    if confidence < MIN_AUTO_CONFIDENCE:
        missing = _safe_phrase(missing_evidence[0]) if missing_evidence else "the highest-signal evidence source"
        questions.append(
            _question(
                question=f"What additional evidence can confirm whether {incident.service} is affected before remediation?",
                why=f"Confidence is {confidence:.2f}; missing or weak evidence ({missing}) blocks safe autonomy.",
                source_gate="low_confidence",
            )
        )

    if missing_evidence and not any(item.source_gate == "low_confidence" for item in questions):
        questions.append(
            _question(
                question=f"Can the owner provide the missing non-sensitive evidence for {incident.service}?",
                why=f"Missing evidence: {_safe_phrase(missing_evidence[0])}.",
                source_gate="missing_required_context",
            )
        )

    if conflicting_evidence:
        questions.append(
            _question(
                question=f"Which signal should OpsCat trust for {incident.service}: the incident evidence or the conflicting evidence?",
                why=f"Conflict to resolve: {_safe_phrase(conflicting_evidence[0])}.",
                source_gate="conflicting_evidence",
            )
        )

    if protected_domain(incident.service) or incident.severity == "critical":
        questions.append(
            _question(
                question=f"Is it safe for a human operator to approve the proposed local/mock action for {incident.service} now?",
                why="Protected or high-impact services require accountable human approval before mutation.",
                source_gate="protected_domain_or_high_impact",
            )
        )

    failed_simulation = _simulation_failed(simulation)
    if failed_simulation:
        questions.append(
            _question(
                question=f"Can a human confirm the unmet precondition before retrying the local/mock action for {incident.service}?",
                why=f"Simulation failed or could not prove safety: {_safe_phrase(failed_simulation)}.",
                source_gate="simulation_failed",
            )
        )

    for reason in policy_reasons:
        gate = _policy_gate(reason)
        if gate is None:
            continue
        questions.append(
            _question(
                question=f"What safe, non-sensitive confirmation would let OpsCat resolve the {gate.replace('_', ' ')} gate for {incident.service}?",
                why=f"Policy gate reason: {_safe_phrase(reason)}.",
                source_gate=gate,
            )
        )

    return _dedupe_questions(questions)[:max_questions]


def questions_to_dicts(questions: Sequence[HumanQuestion]) -> list[dict[str, Any]]:
    return [question.to_dict() for question in questions]


def _question(*, question: str, why: str, source_gate: str) -> HumanQuestion:
    safe_question = _safe_question(redact_text(question))
    safe_why = redact_text(why)
    return HumanQuestion(question=safe_question, why_it_matters=safe_why, source_gate=source_gate, safe_to_ask=True)


def _policy_gate(reason: str) -> str | None:
    normalized = reason.lower()
    if any(term in normalized for term in ("deny", "denied", "prohibited")):
        return "policy_denied_action"
    if any(term in normalized for term in ("missing", "precondition", "context", "confidence")):
        return "missing_required_context"
    if any(term in normalized for term in ("protected", "approval", "human")):
        return "protected_domain_or_high_impact"
    return None


def _simulation_failed(simulation: Mapping[str, Any] | None) -> str:
    if not simulation:
        return ""
    status = str(simulation.get("status") or "")
    ok = simulation.get("ok")
    success = simulation.get("success")
    if status in {"failed", "fail", "blocked"} or ok is False or success is False:
        gaps = simulation.get("precondition_gaps") or simulation.get("reasons") or simulation.get("errors") or status
        if isinstance(gaps, Sequence) and not isinstance(gaps, (str, bytes, bytearray)):
            return str(gaps[0]) if gaps else status
        return str(gaps)
    return ""


def _safe_phrase(value: object) -> str:
    phrase = redact_text(str(value))
    lowered = phrase.lower()
    for term in _SENSITIVE_TERMS:
        lowered = lowered.replace(term, "sensitive configuration")
    return lowered


def _safe_question(question: str) -> str:
    sanitized = question
    for term in _SENSITIVE_TERMS:
        sanitized = sanitized.replace(term, "configuration")
        sanitized = sanitized.replace(term.title(), "configuration")
    return sanitized


def _dedupe_questions(questions: Sequence[HumanQuestion]) -> list[HumanQuestion]:
    seen: set[tuple[str, str]] = set()
    output: list[HumanQuestion] = []
    for question in questions:
        key = (question.source_gate, question.question)
        if key in seen:
            continue
        seen.add(key)
        output.append(question)
    return output
