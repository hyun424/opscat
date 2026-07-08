"""P30 controlled auto-remediation policy and simulation.

This module routes proposed actions through a conservative local/mock policy. It
simulates every action before returning a final route and never mutates
production systems.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.redaction import redact_text, redact_value

_AUTO_CAPABILITIES = frozenset({"read_only_diagnostic", "report", "notification_draft"})
_APPROVAL_CAPABILITIES = frozenset({"reversible_maintenance", "scaling", "rollback"})
_BLOCKED_CAPABILITIES = frozenset({"shell", "data_mutation", "destructive_cleanup", "privilege_escalation"})
_CONDITIONALLY_BLOCKED = frozenset({"restart"})
_BOUNDARY: dict[str, bool] = {
    "local_mock_only": True,
    "simulation_first": True,
    "remediation_execution_enabled": False,
    "production_mutation_enabled": False,
    "unrestricted_shell_enabled": False,
    "default_external_model_calls": False,
    "unattended_production_operation_claimed": False,
}


@dataclass(frozen=True)
class PolicyProfile:
    name: str
    auto_capabilities: tuple[str, ...]
    approval_capabilities: tuple[str, ...]
    blocked_capabilities: tuple[str, ...]

    @classmethod
    def conservative(cls) -> PolicyProfile:
        return cls(
            name="conservative",
            auto_capabilities=tuple(sorted(_AUTO_CAPABILITIES)),
            approval_capabilities=tuple(sorted(_APPROVAL_CAPABILITIES)),
            blocked_capabilities=tuple(sorted(_BLOCKED_CAPABILITIES | _CONDITIONALLY_BLOCKED)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "auto_capabilities": list(self.auto_capabilities),
            "approval_capabilities": list(self.approval_capabilities),
            "blocked_capabilities": list(self.blocked_capabilities),
        }


@dataclass(frozen=True)
class ProposedAction:
    id: str
    capability: str
    description: str
    evidence_ids: tuple[str, ...]
    llm_route_hint: str = ""

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], *, index: int) -> ProposedAction:
        return cls(
            id=str(data.get("id", f"action-{index}")),
            capability=str(data.get("capability", "unknown")),
            description=str(data.get("description", "")),
            evidence_ids=tuple(str(item) for item in _sequence(data.get("evidence_ids", ()))),
            llm_route_hint=str(data.get("llm_route_hint", "")),
        )


@dataclass(frozen=True)
class SimulationResult:
    action_id: str
    dry_run: bool
    mutation_performed: bool
    would_mutate: bool
    summary: str

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "action_id": self.action_id,
            "dry_run": self.dry_run,
            "mutation_performed": self.mutation_performed,
            "would_mutate": self.would_mutate,
            "summary": redact_text(self.summary),
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


@dataclass(frozen=True)
class RoutedAction:
    action: ProposedAction
    route: str
    reasons: tuple[str, ...]
    simulation: SimulationResult

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "action_id": self.action.id,
            "capability": self.action.capability,
            "description": redact_text(self.action.description),
            "evidence_ids": list(self.action.evidence_ids),
            "llm_route_hint": self.action.llm_route_hint,
            "route": self.route,
            "reasons": list(self.reasons),
            "simulation": self.simulation.to_dict(),
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


@dataclass(frozen=True)
class RemediationDrill:
    id: str
    title: str
    profile: PolicyProfile
    risk_type: str
    untrusted_evidence: bool
    insufficient_evidence: bool
    actions: tuple[ProposedAction, ...]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RemediationDrill:
        profile_name = str(data.get("profile", "conservative"))
        profile = PolicyProfile.conservative() if profile_name == "conservative" else PolicyProfile.conservative()
        return cls(
            id=str(data.get("id", "drill-unknown")),
            title=str(data.get("title", "Controlled remediation drill")),
            profile=profile,
            risk_type=str(data.get("risk_type", "unknown")),
            untrusted_evidence=bool(data.get("untrusted_evidence", False)),
            insufficient_evidence=bool(data.get("insufficient_evidence", False)),
            actions=tuple(ProposedAction.from_dict(item, index=index) for index, item in enumerate(_sequence(data.get("actions", ())), start=1) if isinstance(item, Mapping)),
        )


@dataclass(frozen=True)
class RemediationDrillResult:
    drill: RemediationDrill
    actions: tuple[RoutedAction, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "drill_id": self.drill.id,
            "title": self.drill.title,
            "risk_type": self.drill.risk_type,
            "profile": self.drill.profile.to_dict(),
            "untrusted_evidence": self.drill.untrusted_evidence,
            "insufficient_evidence": self.drill.insufficient_evidence,
            "actions": [action.to_dict() for action in self.actions],
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


@dataclass(frozen=True)
class ControlledRemediationReport:
    drills: tuple[RemediationDrillResult, ...]

    def to_dict(self) -> dict[str, Any]:
        actions = [action for drill in self.drills for action in drill.actions]
        action_count = len(actions)
        auto_allowed = sum(1 for action in actions if action.route == "auto_allowed")
        approval_required = sum(1 for action in actions if action.route == "approval_required")
        blocked = sum(1 for action in actions if action.route == "blocked")
        unsafe_auto = sum(1 for action in actions if action.route == "auto_allowed" and action.action.capability not in _AUTO_CAPABILITIES)
        payload = {
            "summary": {
                "drill_count": len(self.drills),
                "action_count": action_count,
                "auto_allowed_count": auto_allowed,
                "approval_required_count": approval_required,
                "blocked_count": blocked,
            },
            "score": {
                "unsafe_auto_action_count": unsafe_auto,
                "simulation_before_decision_count": sum(1 for action in actions if action.simulation.dry_run),
                "approval_burden_count": approval_required,
                "blocked_safety_count": blocked,
            },
            "boundary": dict(_BOUNDARY),
            "drills": [drill.to_dict() for drill in self.drills],
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


class ControlledRemediationEngine:
    def run_path(self, path: str | Path) -> ControlledRemediationReport:
        return self.run(load_remediation_drills(path))

    def run(self, drills: Sequence[RemediationDrill]) -> ControlledRemediationReport:
        return ControlledRemediationReport(drills=tuple(self._run_drill(drill) for drill in drills))

    def _run_drill(self, drill: RemediationDrill) -> RemediationDrillResult:
        return RemediationDrillResult(drill=drill, actions=tuple(self._route_action(drill, action) for action in drill.actions))

    def _route_action(self, drill: RemediationDrill, action: ProposedAction) -> RoutedAction:
        simulation = _simulate(action)
        reasons: list[str] = []
        capability = action.capability
        if capability in _BLOCKED_CAPABILITIES:
            route = "blocked"
            reasons.append("blocked_by_policy")
        elif drill.untrusted_evidence and capability not in _AUTO_CAPABILITIES:
            route = "blocked"
            reasons.append("untrusted_evidence")
        elif drill.insufficient_evidence and capability in _CONDITIONALLY_BLOCKED | _APPROVAL_CAPABILITIES:
            route = "blocked"
            reasons.extend(["insufficient_evidence", "blocked_by_policy"])
        elif capability in _AUTO_CAPABILITIES:
            route = "auto_allowed"
            reasons.append("preapproved_low_risk")
        elif capability in _APPROVAL_CAPABILITIES:
            route = "approval_required"
            reasons.append("human_approval_required")
        elif capability in _CONDITIONALLY_BLOCKED:
            route = "approval_required"
            reasons.append("human_approval_required")
        else:
            route = "blocked"
            reasons.append("unknown_capability")
        return RoutedAction(action=action, route=route, reasons=tuple(reasons), simulation=simulation)


def load_remediation_drills(path: str | Path) -> tuple[RemediationDrill, ...]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    raw_drills: Any = data.get("drills", ()) if isinstance(data, Mapping) else data
    if not isinstance(raw_drills, Sequence) or isinstance(raw_drills, (str, bytes, bytearray)):
        raise ValueError("controlled remediation fixture must contain drills")
    return tuple(RemediationDrill.from_dict(item) for item in raw_drills if isinstance(item, Mapping))


def run_controlled_remediation_fixture(path: str | Path) -> ControlledRemediationReport:
    return ControlledRemediationEngine().run_path(path)


def render_controlled_remediation_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary", {}) if isinstance(payload.get("summary"), Mapping) else {}
    score = payload.get("score", {}) if isinstance(payload.get("score"), Mapping) else {}
    lines = [
        "# OpsCat Controlled Auto-remediation Simulation Report",
        "",
        "Boundary: simulation-first controlled auto-remediation; local/mock by default; "
        "no production mutation; no remediation execution; no unrestricted shell; "
        "does not claim unattended production operation.",
        "",
        "## Summary",
        f"- Drills: {summary.get('drill_count')}",
        f"- Actions: {summary.get('action_count')}",
        f"- Auto allowed: {summary.get('auto_allowed_count')}",
        f"- Approval required: {summary.get('approval_required_count')}",
        f"- Blocked: {summary.get('blocked_count')}",
        "",
        "## Score",
        f"- unsafe_auto_action_count: {score.get('unsafe_auto_action_count')}",
        f"- simulation_before_decision_count: {score.get('simulation_before_decision_count')}",
        "",
        "## Drills",
    ]
    drills = payload.get("drills", [])
    if isinstance(drills, Sequence) and not isinstance(drills, (str, bytes, bytearray)):
        for drill in drills:
            if isinstance(drill, Mapping):
                lines.append(f"- `{drill.get('drill_id')}` risk={drill.get('risk_type')} actions={len(_sequence(drill.get('actions', ())))}")
    return "\n".join(lines) + "\n"


def write_controlled_remediation_outputs(payload: Mapping[str, Any], *, output_json: str | Path | None = None, output_md: str | Path | None = None) -> None:
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(render_controlled_remediation_markdown(payload), encoding="utf-8")


def _simulate(action: ProposedAction) -> SimulationResult:
    would_mutate = action.capability in _BLOCKED_CAPABILITIES or action.capability in _APPROVAL_CAPABILITIES or action.capability in _CONDITIONALLY_BLOCKED
    return SimulationResult(
        action_id=action.id,
        dry_run=True,
        mutation_performed=False,
        would_mutate=would_mutate,
        summary=f"Dry-run simulation for {action.capability}: no production mutation performed.",
    )


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()
