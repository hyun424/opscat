"""P80 approval automation policy lab.

Evaluates local/mock incident action scenarios to decide when an action may be
auto-approved, must require a human, should remain mock-only, or must be
blocked. This module never executes actions or contacts external systems.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Self

from app.services.redaction import redact_value

_BOUNDARY: dict[str, bool] = {
    "local_mock_only": True,
    "live_api_calls_enabled": False,
    "credential_access_enabled": False,
    "network_calls_enabled": False,
    "production_mutation_enabled": False,
    "remediation_execution_enabled": False,
    "shell_execution_enabled": False,
    "action_execution_enabled": False,
    "default_external_model_calls": False,
    "unattended_production_operation_claimed": False,
}

_AUTO_APPROVE_CLASSES = {"cache", "read_only_diagnostic"}
_SENSITIVE_CLASSES = {"credential", "auth", "schema", "data_loss", "shell", "production_mutation"}
_SAFE_BLAST_RADIUS = {"none", "local"}
_BOUNDED_BLAST_RADIUS = {"none", "local", "service", "workspace"}


class ApprovalAutomationDecision(StrEnum):
    AUTO_APPROVE = "auto_approve"
    REQUIRE_HUMAN = "require_human"
    MOCK_ONLY = "mock_only"
    BLOCK = "block"


@dataclass(frozen=True)
class ApprovalScenario:
    id: str
    action_type: str
    action_class: str
    p79_sandbox_decision: str
    evidence_sufficiency: float
    evidence_confidence: float
    recovery_proof_strength: float
    blast_radius: str
    reversible: bool
    historical_approval_safety: float
    role: str
    policy_allows_auto_approval: bool
    maintenance_window: bool
    sleep_mode: bool

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        return cls(
            id=str(data.get("id", "scenario")),
            action_type=str(data.get("action_type", "unknown")),
            action_class=str(data.get("action_class", "unknown")).lower(),
            p79_sandbox_decision=str(data.get("p79_sandbox_decision", "block")).lower(),
            evidence_sufficiency=_float(data.get("evidence_sufficiency")),
            evidence_confidence=_float(data.get("evidence_confidence")),
            recovery_proof_strength=_float(data.get("recovery_proof_strength")),
            blast_radius=str(data.get("blast_radius", "unknown")).lower(),
            reversible=data.get("reversible") is True,
            historical_approval_safety=_float(data.get("historical_approval_safety")),
            role=str(data.get("role", "unknown")),
            policy_allows_auto_approval=data.get("policy_allows_auto_approval") is True,
            maintenance_window=data.get("maintenance_window") is True,
            sleep_mode=data.get("sleep_mode") is True,
        )


@dataclass(frozen=True)
class ApprovalAutomationEvaluation:
    scenario_id: str
    action_type: str
    action_class: str
    decision: ApprovalAutomationDecision
    reasons: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    guardrails: tuple[str, ...]
    audit_record: Mapping[str, Any]
    max_allowed_execution_mode: str

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "scenario_id": self.scenario_id,
            "action_type": self.action_type,
            "action_class": self.action_class,
            "decision": self.decision.value,
            "reasons": list(self.reasons),
            "missing_evidence": list(self.missing_evidence),
            "guardrails": list(self.guardrails),
            "audit_record": dict(self.audit_record),
            "max_allowed_execution_mode": self.max_allowed_execution_mode,
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


@dataclass(frozen=True)
class ApprovalAutomationReport:
    incident: Mapping[str, Any]
    scenarios: tuple[ApprovalScenario, ...]
    decisions: tuple[ApprovalAutomationEvaluation, ...]

    @classmethod
    def from_scenarios(cls, incident: Mapping[str, Any], scenarios: Sequence[ApprovalScenario]) -> Self:
        decisions = tuple(_evaluate_scenario(scenario) for scenario in scenarios)
        return cls(incident=incident, scenarios=tuple(scenarios), decisions=decisions)

    def to_dict(self) -> dict[str, Any]:
        auto_approve_count = _decision_count(self.decisions, ApprovalAutomationDecision.AUTO_APPROVE)
        require_human_count = _decision_count(self.decisions, ApprovalAutomationDecision.REQUIRE_HUMAN)
        mock_only_count = _decision_count(self.decisions, ApprovalAutomationDecision.MOCK_ONLY)
        blocked_count = _decision_count(self.decisions, ApprovalAutomationDecision.BLOCK)
        unsafe_auto_approval_count = sum(
            1
            for item in self.decisions
            if item.decision == ApprovalAutomationDecision.AUTO_APPROVE and item.action_class in _SENSITIVE_CLASSES
        )
        payload = {
            "summary": {
                "incident_id": str(self.incident.get("id", "p80-incident")),
                "scenario_count": len(self.scenarios),
                "auto_approve_count": auto_approve_count,
                "require_human_count": require_human_count,
                "mock_only_count": mock_only_count,
                "blocked_count": blocked_count,
                "unsafe_auto_approval_count": unsafe_auto_approval_count,
                "action_execution_count": 0,
                "live_api_call_count": 0,
                "credential_read_count": 0,
                "network_call_count": 0,
                "production_mutation_count": 0,
                "shell_execution_count": 0,
                "passed": len(self.scenarios) >= 9
                and auto_approve_count >= 1
                and require_human_count >= 1
                and mock_only_count >= 1
                and blocked_count >= 1
                and unsafe_auto_approval_count == 0,
            },
            "boundary": dict(_BOUNDARY),
            "incident": redact_value(dict(self.incident)),
            "decisions": [decision.to_dict() for decision in self.decisions],
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


def evaluate_approval_automation_fixture(path: str | Path) -> ApprovalAutomationReport:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    incident = _mapping(data.get("incident"))
    scenarios = tuple(
        ApprovalScenario.from_dict(item) for item in _sequence(data.get("scenarios", ())) if isinstance(item, Mapping)
    )
    return ApprovalAutomationReport.from_scenarios(incident, scenarios)


def render_approval_automation_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    lines = [
        "# OpsCat Approval Automation Policy Lab",
        "",
        "P80 evaluates approval automation policy with local/mock fixtures only.",
        "",
        "## Summary",
        "",
        f"- Incident: {summary.get('incident_id', 'unknown')}",
        f"- Scenarios: {summary.get('scenario_count', 0)}",
        f"- Auto-approved: {summary.get('auto_approve_count', 0)}",
        f"- Human required: {summary.get('require_human_count', 0)}",
        f"- Mock-only: {summary.get('mock_only_count', 0)}",
        f"- Blocked: {summary.get('blocked_count', 0)}",
        f"- Unsafe auto-approvals: {summary.get('unsafe_auto_approval_count', 0)}",
        f"- Passed: {summary.get('passed', False)}",
        "",
        "## Decisions",
        "",
    ]
    for decision in _sequence(payload.get("decisions", ())):
        if isinstance(decision, Mapping):
            reasons = ", ".join(str(item) for item in _sequence(decision.get("reasons", ()))) or "none"
            missing = ", ".join(str(item) for item in _sequence(decision.get("missing_evidence", ()))) or "none"
            lines.append(
                f"- `{decision.get('scenario_id')}` decision={decision.get('decision')} "
                f"max_mode={decision.get('max_allowed_execution_mode')} reasons={reasons} missing={missing}"
            )
    lines.extend(
        [
            "",
            "## Zero-execution boundary",
            "",
            "- Local/mock policy evaluation only.",
            "- No live APIs, credentials, network calls, production mutation, shell execution, or action execution.",
            "- Destructive, credential, auth, schema, data-loss, shell, and production-mutation actions cannot auto-approve.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_approval_automation_outputs(
    payload: Mapping[str, Any],
    *,
    output_json: str | Path | None = None,
    output_md: str | Path | None = None,
) -> None:
    if output_json:
        output_json_path = Path(output_json)
        output_json_path.parent.mkdir(parents=True, exist_ok=True)
        output_json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        output_md_path = Path(output_md)
        output_md_path.parent.mkdir(parents=True, exist_ok=True)
        output_md_path.write_text(render_approval_automation_markdown(payload), encoding="utf-8")


def _evaluate_scenario(scenario: ApprovalScenario) -> ApprovalAutomationEvaluation:
    missing_evidence = _missing_evidence(scenario)
    reasons = _base_reasons(scenario, missing_evidence)

    if scenario.p79_sandbox_decision == "block" or scenario.action_class in _SENSITIVE_CLASSES:
        decision = ApprovalAutomationDecision.BLOCK
        reasons.extend(["blocked_by_policy", "destructive_or_sensitive_action_class"])
        max_mode = "none"
    elif scenario.p79_sandbox_decision == "mock_only":
        decision = ApprovalAutomationDecision.MOCK_ONLY
        reasons.append("p79_mock_only")
        max_mode = "dry_run_only"
    elif _can_auto_approve(scenario, missing_evidence):
        decision = ApprovalAutomationDecision.AUTO_APPROVE
        reasons.extend(["low_blast_radius", "strong_evidence_and_recovery_proof"])
        max_mode = "local_mock"
    else:
        decision = ApprovalAutomationDecision.REQUIRE_HUMAN
        max_mode = "dry_run_only"

    guardrails = _guardrails(decision)
    return ApprovalAutomationEvaluation(
        scenario_id=scenario.id,
        action_type=scenario.action_type,
        action_class=scenario.action_class,
        decision=decision,
        reasons=tuple(dict.fromkeys(reasons)),
        missing_evidence=tuple(dict.fromkeys(missing_evidence)),
        guardrails=guardrails,
        audit_record=_audit_record(scenario, decision),
        max_allowed_execution_mode=max_mode,
    )


def _base_reasons(scenario: ApprovalScenario, missing_evidence: Sequence[str]) -> list[str]:
    reasons: list[str] = []
    if scenario.p79_sandbox_decision == "require_approval":
        reasons.append("p79_requires_approval")
    if scenario.blast_radius not in _SAFE_BLAST_RADIUS:
        reasons.append("higher_blast_radius")
    if not scenario.reversible:
        reasons.append("not_reversible")
    if scenario.sleep_mode:
        reasons.append("sleep_mode_blocks_auto_approval")
    if missing_evidence:
        reasons.append("missing_or_weak_evidence")
    if not scenario.policy_allows_auto_approval:
        reasons.append("role_or_policy_disallows_auto_approval")
    return reasons


def _missing_evidence(scenario: ApprovalScenario) -> list[str]:
    missing: list[str] = []
    if scenario.evidence_sufficiency < 0.8:
        missing.append("evidence_sufficiency_below_threshold")
    if scenario.evidence_confidence < 0.8:
        missing.append("evidence_confidence_below_threshold")
    if scenario.recovery_proof_strength < 0.8:
        missing.append("recovery_proof_not_strong_enough")
    if not scenario.maintenance_window:
        missing.append("maintenance_window_missing")
    if scenario.historical_approval_safety < 0.85:
        missing.append("historical_safety_profile_below_threshold")
    return missing


def _can_auto_approve(scenario: ApprovalScenario, missing_evidence: Sequence[str]) -> bool:
    return (
        scenario.p79_sandbox_decision == "allow"
        and scenario.action_class in _AUTO_APPROVE_CLASSES
        and scenario.blast_radius in _SAFE_BLAST_RADIUS
        and scenario.reversible
        and scenario.policy_allows_auto_approval
        and scenario.maintenance_window
        and not scenario.sleep_mode
        and not missing_evidence
    )


def _guardrails(decision: ApprovalAutomationDecision) -> tuple[str, ...]:
    base = ["local_mock_execution_only", "no_real_action_execution"]
    if decision == ApprovalAutomationDecision.AUTO_APPROVE:
        return tuple(base + ["audit_before_mock_execution", "operator_can_override"])
    if decision == ApprovalAutomationDecision.REQUIRE_HUMAN:
        return tuple(base + ["human_approval_required_before_any_real_execution"])
    if decision == ApprovalAutomationDecision.MOCK_ONLY:
        return tuple(base + ["do_not_promote_draft_to_execution"])
    return tuple(base + ["blocked_actions_cannot_execute"])


def _audit_record(scenario: ApprovalScenario, decision: ApprovalAutomationDecision) -> Mapping[str, Any]:
    return {
        "audit_id": f"p80:{scenario.id}",
        "scenario_id": scenario.id,
        "decision": decision.value,
        "role": scenario.role,
        "p79_sandbox_decision": scenario.p79_sandbox_decision,
        "local_mock_only": True,
    }


def _decision_count(decisions: Sequence[ApprovalAutomationEvaluation], decision: ApprovalAutomationDecision) -> int:
    return sum(1 for item in decisions if item.decision == decision)


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else ()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _float(value: Any) -> float:
    if isinstance(value, int | float):
        return float(value)
    return 0.0
