"""Mock-by-default LLM judgment adapter with fail-closed safety gates.

P14 introduces LLM-shaped judgment without making external model calls. The
provider interface is intentionally narrow: providers return JSON-compatible
judgments; OpsCat validates schema, checks citations, and applies a safety gate
before any downstream use. This module never executes actions.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.services.redaction import redact_value

_ALLOWED_ROUTES = ("local_mock_auto_allowed", "approval_required", "human_required", "blocked")
_UNSAFE_ACTION_MARKERS = (
    "kubectl",
    "kubernetes",
    "rm -rf",
    "drop database",
    "terraform apply",
    "production restart",
    "restart production",
    "unrestricted shell",
    "aws ",
    "gcloud ",
    "database mutation",
)


class LLMJudgmentValidationError(ValueError):
    """Raised when provider output does not match the P14 judgment schema."""


class LLMJudgmentProvider(Protocol):
    """Provider interface for LLM-shaped judgment.

    Implementations may be deterministic mocks or future opt-in external model
    adapters. Normal verification uses only the mock provider.
    """

    name: str
    model_calls_enabled: bool

    def judge(self, context_packet: Mapping[str, Any]) -> Mapping[str, Any]:
        """Return JSON-compatible judgment for a P13 context packet."""


@dataclass(frozen=True)
class JudgmentHypothesis:
    label: str
    confidence: float
    evidence_citations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "confidence": self.confidence,
            "evidence_citations": list(self.evidence_citations),
        }


@dataclass(frozen=True)
class LLMJudgment:
    hypotheses: tuple[JudgmentHypothesis, ...]
    recommended_route: str
    safe_actions: tuple[str, ...]
    forbidden_actions_detected: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    verification_plan: tuple[str, ...]
    evidence_citations: tuple[str, ...]
    boundary: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypotheses": [item.to_dict() for item in self.hypotheses],
            "recommended_route": self.recommended_route,
            "safe_actions": list(self.safe_actions),
            "forbidden_actions_detected": list(self.forbidden_actions_detected),
            "missing_evidence": list(self.missing_evidence),
            "verification_plan": list(self.verification_plan),
            "evidence_citations": list(self.evidence_citations),
            "boundary": redact_value(dict(self.boundary)),
        }


@dataclass(frozen=True)
class CitationCheckResult:
    valid: bool
    known_citations: tuple[str, ...]
    unknown_citations: tuple[str, ...]
    missing_citations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "known_citations": list(self.known_citations),
            "unknown_citations": list(self.unknown_citations),
            "missing_citations": list(self.missing_citations),
        }


@dataclass(frozen=True)
class SafetyGateResult:
    final_route: str
    allowed_safe_actions: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    gate_reasons: tuple[str, ...]
    executed_actions: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "final_route": self.final_route,
            "allowed_safe_actions": list(self.allowed_safe_actions),
            "blocked_actions": list(self.blocked_actions),
            "gate_reasons": list(self.gate_reasons),
            "executed_actions": list(self.executed_actions),
        }


@dataclass(frozen=True)
class LLMJudgmentRunResult:
    provider: str
    raw_judgment: Mapping[str, Any]
    judgment: LLMJudgment | None
    validation: Mapping[str, Any]
    citation_check: CitationCheckResult
    safety_gate: SafetyGateResult
    context: Mapping[str, Any]
    local_mock_only: bool = True
    model_calls_enabled: bool = False
    action_execution_enabled: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "raw_judgment": redact_value(dict(self.raw_judgment)),
            "judgment": self.judgment.to_dict() if self.judgment is not None else None,
            "validation": redact_value(dict(self.validation)),
            "citation_check": self.citation_check.to_dict(),
            "safety_gate": self.safety_gate.to_dict(),
            "context": redact_value(dict(self.context)),
            "local_mock_only": self.local_mock_only,
            "model_calls_enabled": self.model_calls_enabled,
            "action_execution_enabled": self.action_execution_enabled,
        }


class MockLLMJudgmentProvider:
    """Deterministic local/mock provider that emulates an LLM judgment shape."""

    name = "mock"
    model_calls_enabled = False

    def judge(self, context_packet: Mapping[str, Any]) -> Mapping[str, Any]:
        evidence = _mapping_sequence(context_packet.get("evidence"))
        hypotheses = _mapping_sequence(context_packet.get("candidate_hypotheses"))
        runbooks = _mapping_sequence(context_packet.get("candidate_runbooks"))
        risky_evidence = [item for item in evidence if _string_sequence(item.get("risk_flags"))]
        cited = _unique(
            [
                *[str(item.get("id")) for item in evidence[:3] if item.get("id")],
                *[str(item.get("id")) for item in risky_evidence if item.get("id")],
            ]
        )
        hypothesis_payload = _hypotheses_from_context(hypotheses, cited)
        allowed_actions = _runbook_allowed_actions(runbooks)
        verification = _runbook_verification_checks(runbooks)
        forbidden = _forbidden_from_evidence(risky_evidence)
        route = "blocked" if forbidden else _route_from_context(context_packet)
        if route == "local_mock_auto_allowed" and not allowed_actions:
            route = "human_required"
        return {
            "hypotheses": hypothesis_payload,
            "recommended_route": route,
            "safe_actions": allowed_actions,
            "forbidden_actions_detected": forbidden,
            "missing_evidence": _missing_evidence_from_context(hypotheses),
            "verification_plan": verification or ["review cited evidence before action"],
            "evidence_citations": cited,
            "boundary": {
                "local_mock_only": True,
                "provider": self.name,
                "model_calls_enabled": self.model_calls_enabled,
                "action_execution_enabled": False,
                "note": "mock provider only; no external model/API call; no action execution",
            },
        }


def validate_llm_judgment(raw: Mapping[str, Any]) -> LLMJudgment:
    if "recommended_route" not in raw:
        raise LLMJudgmentValidationError("missing required field: recommended_route")
    route = str(raw.get("recommended_route", ""))
    if route not in _ALLOWED_ROUTES:
        raise LLMJudgmentValidationError(f"recommended_route must be one of {_ALLOWED_ROUTES}")
    required = (
        "hypotheses",
        "safe_actions",
        "forbidden_actions_detected",
        "missing_evidence",
        "verification_plan",
        "evidence_citations",
        "boundary",
    )
    for field_name in required:
        if field_name not in raw:
            raise LLMJudgmentValidationError(f"missing required field: {field_name}")
    hypotheses_raw = raw.get("hypotheses")
    if not isinstance(hypotheses_raw, Sequence) or isinstance(hypotheses_raw, (str, bytes, bytearray)) or not hypotheses_raw:
        raise LLMJudgmentValidationError("hypotheses must be a non-empty array")
    hypotheses = tuple(_validate_hypothesis(item) for item in hypotheses_raw)
    boundary = raw.get("boundary")
    if not isinstance(boundary, Mapping):
        raise LLMJudgmentValidationError("boundary must be an object")
    if boundary.get("local_mock_only") is not True:
        raise LLMJudgmentValidationError("boundary.local_mock_only must be true")
    if boundary.get("model_calls_enabled") is not False:
        raise LLMJudgmentValidationError("boundary.model_calls_enabled must be false for P14 default verification")
    return LLMJudgment(
        hypotheses=hypotheses,
        recommended_route=route,
        safe_actions=_string_sequence(raw.get("safe_actions")),
        forbidden_actions_detected=_string_sequence(raw.get("forbidden_actions_detected")),
        missing_evidence=_string_sequence(raw.get("missing_evidence")),
        verification_plan=_string_sequence(raw.get("verification_plan")),
        evidence_citations=_string_sequence(raw.get("evidence_citations")),
        boundary=dict(boundary),
    )


def check_evidence_citations(judgment: LLMJudgment, context_packet: Mapping[str, Any]) -> CitationCheckResult:
    known_ids = {str(item.get("id")) for item in _mapping_sequence(context_packet.get("evidence")) if item.get("id")}
    cited = _unique([
        *judgment.evidence_citations,
        *[citation for hypothesis in judgment.hypotheses for citation in hypothesis.evidence_citations],
    ])
    unknown = tuple(citation for citation in cited if citation not in known_ids)
    missing = ("evidence_citations",) if not cited else ()
    return CitationCheckResult(
        valid=not unknown and not missing,
        known_citations=tuple(citation for citation in cited if citation in known_ids),
        unknown_citations=unknown,
        missing_citations=missing,
    )


def apply_judgment_safety_gate(judgment: LLMJudgment, context_packet: Mapping[str, Any]) -> SafetyGateResult:
    allowed: list[str] = []
    blocked: list[str] = []
    reasons: list[str] = []
    for action in judgment.safe_actions:
        lowered = action.lower()
        if action.startswith("mock.") and not any(marker in lowered for marker in _UNSAFE_ACTION_MARKERS):
            allowed.append(action)
        else:
            blocked.append(action)
            reasons.append(f"Blocked non-mock or unsafe action: {action}")
    for forbidden in judgment.forbidden_actions_detected:
        if forbidden:
            blocked.append(forbidden)
            reasons.append(f"Forbidden action detected by provider: {forbidden}")
    risk_flags = _context_risk_flags(context_packet)
    if risk_flags:
        reasons.append(f"Unsafe evidence present: {', '.join(risk_flags)}")
    final_route = judgment.recommended_route
    if blocked or any(flag in risk_flags for flag in ("prompt_injection", "unsafe_action_request")):
        final_route = "blocked"
    elif final_route == "local_mock_auto_allowed" and not allowed:
        final_route = "human_required"
        reasons.append("No safe local/mock actions available for automatic route")
    return SafetyGateResult(
        final_route=final_route,
        allowed_safe_actions=tuple(_unique(allowed)),
        blocked_actions=tuple(_unique(blocked)),
        gate_reasons=tuple(_unique(reasons)) or ("judgment passed local/mock safety gate",),
        executed_actions=(),
    )


def run_llm_judgment_from_packet(
    context_packet: Mapping[str, Any],
    provider: LLMJudgmentProvider | None = None,
) -> LLMJudgmentRunResult:
    selected_provider = provider or MockLLMJudgmentProvider()
    raw = selected_provider.judge(context_packet)
    try:
        judgment = validate_llm_judgment(raw)
    except LLMJudgmentValidationError as exc:
        invalid_citation = CitationCheckResult(False, (), (), ("validation_failed",))
        blocked_gate = SafetyGateResult("blocked", (), (), (f"Validation failed: {exc}",), ())
        return LLMJudgmentRunResult(
            provider=selected_provider.name,
            raw_judgment=raw,
            judgment=None,
            validation={"valid": False, "errors": [str(exc)]},
            citation_check=invalid_citation,
            safety_gate=blocked_gate,
            context=context_packet,
            model_calls_enabled=selected_provider.model_calls_enabled,
        )
    citation = check_evidence_citations(judgment, context_packet)
    gate = apply_judgment_safety_gate(judgment, context_packet)
    if not citation.valid:
        gate = SafetyGateResult(
            final_route="blocked",
            allowed_safe_actions=(),
            blocked_actions=gate.blocked_actions,
            gate_reasons=tuple([*gate.gate_reasons, "Unknown or missing evidence citations force blocked route"]),
            executed_actions=(),
        )
    return LLMJudgmentRunResult(
        provider=selected_provider.name,
        raw_judgment=raw,
        judgment=judgment,
        validation={"valid": True, "errors": []},
        citation_check=citation,
        safety_gate=gate,
        context=context_packet,
        model_calls_enabled=selected_provider.model_calls_enabled,
    )


def render_llm_judgment_markdown(result: LLMJudgmentRunResult) -> str:
    payload = result.to_dict()
    lines = [
        "# OpsCat LLM Judgment Report",
        "",
        f"Provider: {result.provider} provider",
        "",
        "Boundary: local/mock; no external model/API calls in mock mode; no action execution.",
        "",
        "## Validation",
        "",
        f"- schema valid: {payload['validation']['valid']}",
        f"- citation valid: {payload['citation_check']['valid']}",
        f"- final route: {payload['safety_gate']['final_route']}",
        "",
        "## Safety Gate Reasons",
        "",
    ]
    lines.extend(f"- {reason}" for reason in payload["safety_gate"]["gate_reasons"])
    lines.extend(
        [
            "",
            "## Judgment JSON",
            "",
            "```json",
            json.dumps(payload["judgment"], indent=2, sort_keys=True),
            "```",
        ]
    )
    return "\n".join(lines) + "\n"


def write_llm_judgment_outputs(
    result: LLMJudgmentRunResult,
    output_json: str | Path | None = None,
    output_md: str | Path | None = None,
) -> None:
    if output_json is not None:
        json_path = Path(output_json)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md is not None:
        md_path = Path(output_md)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(render_llm_judgment_markdown(result), encoding="utf-8")


def _validate_hypothesis(raw: Any) -> JudgmentHypothesis:
    if not isinstance(raw, Mapping):
        raise LLMJudgmentValidationError("hypotheses entries must be objects")
    label = str(raw.get("label") or "")
    if not label:
        raise LLMJudgmentValidationError("hypotheses[].label is required")
    return JudgmentHypothesis(
        label=label,
        confidence=_bounded_float(raw.get("confidence"), default=0.5),
        evidence_citations=_string_sequence(raw.get("evidence_citations")),
    )


def _mapping_sequence(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [item for item in value if isinstance(item, Mapping)]
    return []


def _string_sequence(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(str(item) for item in value if str(item))
    return (str(value),)


def _hypotheses_from_context(hypotheses: Sequence[Mapping[str, Any]], citations: Sequence[str]) -> list[dict[str, Any]]:
    if not hypotheses:
        return [{"label": "diagnostic review required", "confidence": 0.5, "evidence_citations": list(citations)}]
    output: list[dict[str, Any]] = []
    for item in hypotheses:
        label = str(item.get("label") or "diagnostic review required")
        confidence = _bounded_float(item.get("confidence"), default=0.5)
        item_citations = _string_sequence(item.get("supporting_evidence")) or tuple(citations)
        output.append({"label": label, "confidence": confidence, "evidence_citations": list(item_citations)})
    return output


def _runbook_allowed_actions(runbooks: Sequence[Mapping[str, Any]]) -> list[str]:
    actions: list[str] = []
    for runbook in runbooks:
        actions.extend(_string_sequence(runbook.get("allowed_actions")))
    if not actions:
        actions.append("mock.get_error_context")
    return _unique(action for action in actions if action.startswith("mock."))


def _runbook_verification_checks(runbooks: Sequence[Mapping[str, Any]]) -> list[str]:
    checks: list[str] = []
    for runbook in runbooks:
        checks.extend(_string_sequence(runbook.get("verification_checks")))
    return _unique(checks)


def _missing_evidence_from_context(hypotheses: Sequence[Mapping[str, Any]]) -> list[str]:
    missing: list[str] = []
    for item in hypotheses:
        missing.extend(_string_sequence(item.get("missing_evidence")))
    return _unique(missing)


def _forbidden_from_evidence(risky_evidence: Sequence[Mapping[str, Any]]) -> list[str]:
    forbidden: list[str] = []
    for item in risky_evidence:
        content = str(item.get("content") or "")
        lowered = content.lower()
        for marker in _UNSAFE_ACTION_MARKERS:
            if marker in lowered:
                forbidden.append(marker.strip())
        if "prompt_injection" in _string_sequence(item.get("risk_flags")):
            forbidden.append(f"log instruction ignored from {item.get('id')}")
    return _unique(forbidden)


def _route_from_context(context_packet: Mapping[str, Any]) -> str:
    schema = context_packet.get("required_output_schema")
    if isinstance(schema, Mapping):
        routes = _string_sequence(schema.get("allowed_routes"))
        if "human_required" in routes:
            return "human_required"
    return "human_required"


def _context_risk_flags(context_packet: Mapping[str, Any]) -> tuple[str, ...]:
    flags: list[str] = []
    for item in _mapping_sequence(context_packet.get("evidence")):
        flags.extend(_string_sequence(item.get("risk_flags")))
    return tuple(_unique(flags))


def _unique(values: Sequence[str] | Any) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        text = str(value)
        if text and text not in seen:
            seen.add(text)
            unique.append(text)
    return unique


def _bounded_float(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return min(1.0, max(0.0, number))
