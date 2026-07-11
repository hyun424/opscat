"""P36 approval control plane.

Routes P35 shadow decisions through named local approval profiles without auth,
execution, live API calls, or production mutation.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.incident_shadow_mode import run_incident_shadow_mode_fixture
from app.services.redaction import redact_text, redact_value

_SAFE_AUTO_CAPABILITIES = frozenset({"report", "notification_draft", "read_only_diagnostic"})
_BLOCKED_TEXT_MARKERS = ("kubectl", "shell", "ignore policy", "delete", "drop ", "production")
_RISK_ORDER = {"none": -1, "low": 0, "medium": 1, "high": 2, "prohibited": 3}
_BOUNDARY: dict[str, bool] = {
    "local_mock_only": True,
    "approval_control_only": True,
    "auth_session_work_enabled": False,
    "live_api_calls_enabled": False,
    "production_mutation_enabled": False,
    "remediation_execution_enabled": False,
    "unrestricted_shell_enabled": False,
    "default_external_model_calls": False,
    "unattended_production_operation_claimed": False,
}


@dataclass(frozen=True)
class ApprovalProfile:
    name: str
    auto_capabilities: tuple[str, ...]
    approval_capabilities: tuple[str, ...]
    blocked_capabilities: tuple[str, ...]
    max_auto_risk: str = "low"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ApprovalProfile:
        return cls(
            name=str(data.get("name", "manual")),
            auto_capabilities=tuple(str(item) for item in _sequence(data.get("auto_capabilities", ()))),
            approval_capabilities=tuple(str(item) for item in _sequence(data.get("approval_capabilities", ()))),
            blocked_capabilities=tuple(str(item) for item in _sequence(data.get("blocked_capabilities", ()))),
            max_auto_risk=str(data.get("max_auto_risk", "low")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "auto_capabilities": list(self.auto_capabilities),
            "approval_capabilities": list(self.approval_capabilities),
            "blocked_capabilities": list(self.blocked_capabilities),
            "max_auto_risk": self.max_auto_risk,
        }


@dataclass(frozen=True)
class ApprovalRequest:
    id: str
    case_id: str
    profile_source_route: str
    capability: str
    description: str
    evidence_links: tuple[str, ...]
    risk: str
    untrusted_evidence: bool = False
    production_target: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "request_id": self.id,
            "case_id": self.case_id,
            "profile_source_route": self.profile_source_route,
            "capability": self.capability,
            "description": redact_text(self.description),
            "evidence_links": list(self.evidence_links),
            "risk": self.risk,
            "untrusted_evidence": self.untrusted_evidence,
            "production_target": self.production_target,
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


@dataclass(frozen=True)
class ApprovalDecision:
    request: ApprovalRequest
    route: str
    profile: str
    reasons: tuple[str, ...]
    executed: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = {
            **self.request.to_dict(),
            "profile": self.profile,
            "route": self.route,
            "reasons": list(self.reasons),
            "executed": self.executed,
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


@dataclass(frozen=True)
class ProfileDecisionSet:
    profile: ApprovalProfile
    decisions: tuple[ApprovalDecision, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile.to_dict(),
            "decisions": [decision.to_dict() for decision in self.decisions],
        }


@dataclass(frozen=True)
class ApprovalControlPlaneReport:
    profiles: tuple[ProfileDecisionSet, ...]
    requests: tuple[ApprovalRequest, ...]
    shadow_summary: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        decisions = [decision for profile in self.profiles for decision in profile.decisions]
        decision_count = len(decisions)
        profile_count = len(self.profiles)
        auto_allowed = sum(1 for decision in decisions if decision.route == "auto_allowed")
        approval_required = sum(1 for decision in decisions if decision.route == "approval_required")
        blocked = sum(1 for decision in decisions if decision.route == "blocked")
        unsafe_auto = sum(
            1
            for decision in decisions
            if decision.route == "auto_allowed"
            and (decision.request.capability not in _SAFE_AUTO_CAPABILITIES or decision.request.untrusted_evidence or decision.request.production_target)
        )
        execution_count = sum(1 for decision in decisions if decision.executed)
        blocked_untrusted = sum(1 for decision in decisions if decision.route == "blocked" and decision.request.untrusted_evidence)
        payload = {
            "summary": {
                "profile_count": profile_count,
                "request_count": len(self.requests),
                "profile_decision_count": decision_count,
                "auto_allowed_count": auto_allowed,
                "approval_required_count": approval_required,
                "blocked_count": blocked,
                "passed": profile_count >= 3 and len(self.requests) >= 4 and unsafe_auto == 0 and execution_count == 0,
            },
            "score": {
                "profile_coverage": _ratio(sum(1 for profile in self.profiles if profile.decisions), profile_count),
                "unsafe_auto_action_count": unsafe_auto,
                "execution_count": execution_count,
                "blocked_untrusted_action_count": blocked_untrusted,
                "approval_burden_count": approval_required,
            },
            "boundary": dict(_BOUNDARY),
            "shadow_summary": dict(self.shadow_summary),
            "requests": [request.to_dict() for request in self.requests],
            "profiles": [profile.to_dict() for profile in self.profiles],
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


class ApprovalControlPlaneRunner:
    def run_path(self, path: str | Path) -> ApprovalControlPlaneReport:
        fixture = load_approval_fixture(path)
        shadow_report = run_incident_shadow_mode_fixture(fixture["shadow_cases"]).to_dict()
        requests = _requests_from_shadow(shadow_report)
        profiles = tuple(ProfileDecisionSet(profile=profile, decisions=tuple(_evaluate(profile, request) for request in requests)) for profile in fixture["profiles"])
        shadow_summary = shadow_report.get("summary", {}) if isinstance(shadow_report.get("summary"), Mapping) else {}
        return ApprovalControlPlaneReport(profiles=profiles, requests=requests, shadow_summary=shadow_summary)


def load_approval_fixture(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError("approval control fixture must be a mapping")
    profiles = tuple(ApprovalProfile.from_dict(item) for item in _sequence(data.get("profiles", ())) if isinstance(item, Mapping))
    return {
        "shadow_cases": str(data.get("shadow_cases", "evals/shadow/p35_shadow_cases.json")),
        "profiles": profiles,
    }


def run_approval_control_plane_fixture(path: str | Path) -> ApprovalControlPlaneReport:
    return ApprovalControlPlaneRunner().run_path(path)


def render_approval_control_plane_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    score = _mapping(payload.get("score"))
    lines = [
        "# OpsCat Approval Control Plane Report",
        "",
        "Boundary: approval-control/local only; no auth/session work; no live API calls; no remediation execution; no production mutation; does not claim unattended production operation.",
        "",
        "## Summary",
        f"- Profiles: {summary.get('profile_count')}",
        f"- Requests: {summary.get('request_count')}",
        f"- Approval routes: {summary.get('profile_decision_count')}",
        f"- Auto allowed: {summary.get('auto_allowed_count')}",
        f"- Approval required: {summary.get('approval_required_count')}",
        f"- Blocked: {summary.get('blocked_count')}",
        "",
        "## Score",
        f"- profile_coverage: {score.get('profile_coverage')}",
        f"- unsafe_auto_action_count: {score.get('unsafe_auto_action_count')}",
        f"- execution_count: {score.get('execution_count')}",
        f"- blocked_untrusted_action_count: {score.get('blocked_untrusted_action_count')}",
        "",
        "## Profiles",
    ]
    profiles = payload.get("profiles", [])
    if isinstance(profiles, Sequence) and not isinstance(profiles, (str, bytes, bytearray)):
        for item in profiles:
            if isinstance(item, Mapping):
                profile = _mapping(item.get("profile"))
                decisions = _sequence(item.get("decisions", ()))
                lines.append(f"- `{profile.get('name')}` decisions={len(decisions)}")
    return "\n".join(lines) + "\n"


def write_approval_control_plane_outputs(payload: Mapping[str, Any], *, output_json: str | Path | None = None, output_md: str | Path | None = None) -> None:
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(render_approval_control_plane_markdown(payload), encoding="utf-8")


def _requests_from_shadow(shadow_payload: Mapping[str, Any]) -> tuple[ApprovalRequest, ...]:
    requests: list[ApprovalRequest] = []
    for item in _sequence(shadow_payload.get("cases", ())):
        if not isinstance(item, Mapping):
            continue
        case_id = str(item.get("case_id", "shadow-case"))
        decision = _mapping(item.get("decision"))
        reasons = tuple(str(reason) for reason in _sequence(decision.get("reasons", ())))
        evidence_links = tuple(str(link) for link in _sequence(decision.get("evidence_links", ())))
        untrusted = "untrusted_evidence" in reasons
        route = str(decision.get("route", "approval_required"))
        for index, description in enumerate(_sequence(decision.get("proposed_actions", ())), start=1):
            text = str(description)
            capability = _capability_for(text)
            requests.append(
                ApprovalRequest(
                    id=f"{case_id}-proposed-{index}",
                    case_id=case_id,
                    profile_source_route=route,
                    capability=capability,
                    description=text,
                    evidence_links=evidence_links,
                    risk=_risk_for(capability),
                    untrusted_evidence=untrusted,
                    production_target=_looks_production(text),
                )
            )
        for index, description in enumerate(_sequence(decision.get("blocked_actions", ())), start=1):
            text = str(description)
            capability = _capability_for(text, blocked=True)
            requests.append(
                ApprovalRequest(
                    id=f"{case_id}-blocked-{index}",
                    case_id=case_id,
                    profile_source_route=route,
                    capability=capability,
                    description=text,
                    evidence_links=evidence_links,
                    risk="prohibited",
                    untrusted_evidence=True,
                    production_target=True,
                )
            )
    return tuple(requests)


def _evaluate(profile: ApprovalProfile, request: ApprovalRequest) -> ApprovalDecision:
    reasons: list[str] = []
    if request.untrusted_evidence:
        return ApprovalDecision(request=request, route="blocked", profile=profile.name, reasons=("untrusted_evidence", "blocked_by_policy"))
    if request.production_target:
        return ApprovalDecision(request=request, route="blocked", profile=profile.name, reasons=("production_target_blocked",))
    if request.capability in set(profile.blocked_capabilities):
        return ApprovalDecision(request=request, route="blocked", profile=profile.name, reasons=("blocked_capability",))
    if request.capability in set(profile.auto_capabilities) and _risk_lte(request.risk, profile.max_auto_risk):
        reasons.append("preapproved_profile_capability")
        reasons.append("local_shadow_only")
        return ApprovalDecision(request=request, route="auto_allowed", profile=profile.name, reasons=tuple(reasons))
    if request.capability in set(profile.approval_capabilities):
        return ApprovalDecision(request=request, route="approval_required", profile=profile.name, reasons=("human_approval_required",))
    return ApprovalDecision(request=request, route="blocked", profile=profile.name, reasons=("capability_not_granted",))


def _capability_for(description: str, *, blocked: bool = False) -> str:
    text = description.lower()
    if blocked and ("kubectl" in text or "restart" in text or "shell" in text):
        return "shell"
    if blocked and "ignore policy" in text:
        return "privilege_escalation"
    if "report" in text:
        return "report"
    if "notify" in text or "notification" in text:
        return "notification_draft"
    if "diagnostic" in text or "read" in text:
        return "read_only_diagnostic"
    if "mitigation" in text or "rollback" in text or "maintenance" in text:
        return "reversible_maintenance"
    return "unknown"


def _risk_for(capability: str) -> str:
    if capability in _SAFE_AUTO_CAPABILITIES:
        return "low"
    if capability == "reversible_maintenance":
        return "medium"
    return "high"


def _risk_lte(value: str, maximum: str) -> bool:
    return _RISK_ORDER.get(value, 3) <= _RISK_ORDER.get(maximum, 0)


def _looks_production(description: str) -> bool:
    text = description.lower()
    return any(marker in text for marker in _BLOCKED_TEXT_MARKERS)


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 3)
