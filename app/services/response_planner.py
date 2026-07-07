"""P9 deterministic multi-step response planner.

The planner is intentionally pure and local/mock only. It converts existing
runbook steps into an auditable response plan and stops high-risk or ambiguous
paths at a human gate.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from app.models import Incident
from app.services.redaction import redact_text, redact_value
from app.services.root_cause_service import RootCauseCandidate, generate_root_cause_candidates
from app.services.runbook_service import Runbook, RunbookStep, get_runbook, select_runbook

PlanStepType = Literal["diagnostic", "safe_local_mock_action", "human_required"]
PlanRoute = Literal["local_mock_auto_allowed", "approval_required", "human_required", "blocked"]

_HIGH_RISK_ENVIRONMENTS = {"prod", "production"}
_HUMAN_RISK_HINTS = {"high", "prohibited"}


@dataclass(frozen=True)
class ResponsePlanStep:
    id: str
    type: PlanStepType
    goal: str
    action_type: str
    preconditions: tuple[str, ...]
    required_evidence: tuple[str, ...]
    risk: str
    expected_output: str
    rollback_expectation: str
    verification_check: str
    requires_human: bool
    blockers: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "goal": redact_text(self.goal),
            "action_type": self.action_type,
            "preconditions": list(self.preconditions),
            "required_evidence": list(self.required_evidence),
            "risk": self.risk,
            "expected_output": redact_text(self.expected_output),
            "rollback_expectation": redact_text(self.rollback_expectation),
            "verification_check": redact_text(self.verification_check),
            "requires_human": self.requires_human,
            "blockers": list(self.blockers),
        }


@dataclass(frozen=True)
class ResponsePlan:
    runbook_key: str
    runbook_title: str
    route: PlanRoute
    steps: tuple[ResponsePlanStep, ...]
    blocking_reasons: tuple[str, ...]
    next_step: str
    local_mock_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "runbook_key": self.runbook_key,
            "runbook_title": redact_text(self.runbook_title),
            "route": self.route,
            "steps": [step.to_dict() for step in self.steps],
            "blocking_reasons": list(self.blocking_reasons),
            "next_step": redact_text(self.next_step),
            "local_mock_only": self.local_mock_only,
        }


def build_response_plan(incident: Incident | Mapping[str, Any]) -> ResponsePlan:
    """Build an ordered local/mock response plan for an incident."""

    candidates = _candidates(incident)
    runbook = _select_runbook(incident, candidates)
    blocking_reasons = _global_blockers(incident, candidates)
    steps = tuple(_step_from_runbook(index, item, incident, candidates, bool(blocking_reasons)) for index, item in enumerate(runbook.steps, start=1))
    if not steps:
        steps = (
            ResponsePlanStep(
                id="step-1",
                type="human_required",
                goal="Collect more local/mock evidence before planning remediation",
                action_type="mock.get_error_context",
                preconditions=("incident_summary_present",),
                required_evidence=("operator_context",),
                risk="read_only",
                expected_output="Evidence package for human review",
                rollback_expectation="none",
                verification_check="evidence package exists",
                requires_human=True,
                blockers=("no_runbook_steps",),
            ),
        )
    route = _route(steps, blocking_reasons)
    next_step = _next_step(route, steps, blocking_reasons)
    return ResponsePlan(runbook.key, runbook.title, route, steps, tuple(sorted(set(blocking_reasons))), next_step)


def _select_runbook(incident: Incident | Mapping[str, Any], candidates: list[RootCauseCandidate]) -> Runbook:
    if isinstance(incident, Incident):
        return select_runbook(incident, candidates)
    text = _haystack(incident)
    if _confidence(incident, candidates) < 0.55:
        return get_runbook("diagnostic_only")
    for key in ("deploy_regression", "api_5xx_spike", "queue_backlog", "connector_outage"):
        runbook = get_runbook(key)
        if any(token in text for token in runbook.incident_classes):
            return runbook
    return get_runbook("diagnostic_only")


def _step_from_runbook(index: int, step: RunbookStep, incident: Incident | Mapping[str, Any], candidates: list[RootCauseCandidate], global_blocked: bool) -> ResponsePlanStep:
    blockers = list(_step_blockers(step, incident, candidates))
    if global_blocked:
        blockers.append("global_human_gate")
    requires_human = bool(blockers) or step.risk_hint in _HUMAN_RISK_HINTS
    step_type: PlanStepType = "diagnostic" if step.risk_hint == "read_only" else "safe_local_mock_action"
    if requires_human and step_type == "safe_local_mock_action":
        step_type = "human_required"
    return ResponsePlanStep(
        id=f"step-{index}",
        type=step_type,
        goal=step.name,
        action_type=step.action_type,
        preconditions=tuple(step.preconditions),
        required_evidence=_required_evidence(step, candidates),
        risk=step.risk_hint,
        expected_output=_expected_output(step),
        rollback_expectation=step.rollback_expectation,
        verification_check=step.verification_check,
        requires_human=requires_human,
        blockers=tuple(sorted(set(blockers))),
    )


def _required_evidence(step: RunbookStep, candidates: list[RootCauseCandidate]) -> tuple[str, ...]:
    evidence = ["incident_summary", *step.preconditions]
    for candidate in candidates[:2]:
        evidence.extend(candidate.missing_evidence)
        evidence.extend(candidate.evidence)
    return tuple(sorted({item for item in evidence if item}))


def _expected_output(step: RunbookStep) -> str:
    if step.risk_hint == "read_only":
        return "Local/mock diagnostic evidence; no external mutation."
    return f"Local/mock {step.action_type} result with audit-ready rollback and verification metadata."


def _global_blockers(incident: Incident | Mapping[str, Any], candidates: list[RootCauseCandidate]) -> list[str]:
    text = _haystack(incident)
    blockers: list[str] = []
    if _environment(incident) in _HIGH_RISK_ENVIRONMENTS and any(token in text for token in ("unknown", "ambiguous", "blast radius", "provider")):
        blockers.append("unknown_or_production_blast_radius")
    if _confidence(incident, candidates) < 0.55:
        blockers.append("low_confidence")
    if any(token in text for token in ("kubectl", "terraform apply", "drop database", "rm -rf", "real production")):
        blockers.append("unsafe_real_mutation_request")
    return blockers


def _step_blockers(step: RunbookStep, incident: Incident | Mapping[str, Any], candidates: list[RootCauseCandidate]) -> tuple[str, ...]:
    blockers: list[str] = []
    if step.risk_hint in _HUMAN_RISK_HINTS:
        blockers.append(f"risk_{step.risk_hint}")
    if _environment(incident) in _HIGH_RISK_ENVIRONMENTS and step.risk_hint != "read_only":
        blockers.append("production_action_requires_human")
    if not step.dry_run_supported:
        blockers.append("missing_simulation")
    if candidates and candidates[0].missing_evidence and step.risk_hint != "read_only":
        blockers.append("missing_supporting_evidence")
    return tuple(blockers)


def _route(steps: tuple[ResponsePlanStep, ...], blockers: list[str]) -> PlanRoute:
    if any("unsafe_real_mutation_request" == blocker for blocker in blockers):
        return "blocked"
    if blockers or any(step.type == "human_required" for step in steps):
        return "human_required"
    if any(step.requires_human for step in steps):
        return "approval_required"
    if any(step.type == "safe_local_mock_action" for step in steps):
        return "approval_required"
    return "human_required"


def _next_step(route: PlanRoute, steps: tuple[ResponsePlanStep, ...], blockers: list[str]) -> str:
    if route == "blocked":
        return "Stop and ask a human to replace unsafe production mutation with a local/mock diagnostic."
    if blockers:
        return f"Ask human for: {', '.join(sorted(set(blockers)))}."
    for step in steps:
        if step.requires_human:
            return f"Human approval required before {step.id}: {step.goal}."
    return f"Prepare local/mock execution gate for {steps[0].id}." if steps else "Collect local/mock evidence."


def _candidates(incident: Incident | Mapping[str, Any]) -> list[RootCauseCandidate]:
    if isinstance(incident, Incident):
        try:
            return generate_root_cause_candidates(incident, list(incident.evidence))
        except Exception:
            return []
    evidence_ids = tuple(str(_get(item, "id", f"evidence-{index}")) for index, item in enumerate(_evidence(incident), start=1))
    confidence = float(_get(incident, "confidence", 0.3) or 0.3)
    missing = () if evidence_ids else ("local_mock_evidence",)
    return [RootCauseCandidate(hypothesis=redact_text(str(_get(incident, "root_cause_candidate", "Unknown cause"))), confidence=confidence, evidence=evidence_ids, missing_evidence=missing)]


def _confidence(incident: Incident | Mapping[str, Any], candidates: list[RootCauseCandidate]) -> float:
    if candidates:
        return candidates[0].confidence
    try:
        return float(_get(incident, "confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _environment(incident: Incident | Mapping[str, Any]) -> str:
    return str(_get(incident, "environment", "unknown") or "unknown").lower()


def _haystack(incident: Incident | Mapping[str, Any]) -> str:
    parts = [
        _get(incident, "service", ""),
        _get(incident, "environment", ""),
        _get(incident, "summary", ""),
        _get(incident, "root_cause_candidate", ""),
        redact_value(_get(incident, "alert_payload", {})),
    ]
    parts.extend(_get(item, "content", "") for item in _evidence(incident))
    return " ".join(str(part) for part in parts).lower()


def _evidence(incident: Incident | Mapping[str, Any]) -> list[Any]:
    value = _get(incident, "evidence", [])
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)
