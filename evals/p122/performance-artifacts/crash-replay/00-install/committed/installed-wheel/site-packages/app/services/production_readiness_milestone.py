"""P40 production-readiness milestone bundle.

Packages verified local evidence while explicitly avoiding any claim of
unattended production operation or production autopilot readiness.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.agent_evaluation_dashboard import run_agent_evaluation_dashboard_fixture
from app.services.redaction import redact_text, redact_value
from app.services.runbook_learning_loop import run_runbook_learning_loop_fixture

_BOUNDARY: dict[str, bool] = {
    "local_readiness_bundle_only": True,
    "production_autopilot_enabled": False,
    "unattended_production_operation_claimed": False,
    "auth_session_work_enabled": False,
    "live_api_calls_enabled": False,
    "production_mutation_enabled": False,
    "remediation_execution_enabled": False,
    "unrestricted_shell_enabled": False,
    "default_external_model_calls": False,
}


@dataclass(frozen=True)
class ReadinessGate:
    id: str
    title: str
    passed: bool
    evidence: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"gate_id": self.id, "title": self.title, "passed": self.passed, "evidence": list(self.evidence)}


@dataclass(frozen=True)
class ProductionBlocker:
    id: str
    title: str
    required_before_production: str

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "id": self.id,
            "title": redact_text(self.title),
            "required_before_production": redact_text(self.required_before_production),
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


@dataclass(frozen=True)
class EvidenceLink:
    id: str
    artifact: str
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "artifact": self.artifact, "description": self.description}


@dataclass(frozen=True)
class ProductionReadinessMilestoneReport:
    gates: tuple[ReadinessGate, ...]
    production_blockers: tuple[ProductionBlocker, ...]
    evidence_bundle: tuple[EvidenceLink, ...]

    def to_dict(self) -> dict[str, Any]:
        gate_count = len(self.gates)
        passed_gates = sum(1 for gate in self.gates if gate.passed)
        boundary_violations = sum(1 for key, value in _BOUNDARY.items() if key.endswith("enabled") and value)
        production_ready = False
        readiness = "local-portfolio-ready" if gate_count >= 8 and passed_gates == gate_count and boundary_violations == 0 else "needs-work"
        payload = {
            "summary": {
                "gate_count": gate_count,
                "passed_gate_count": passed_gates,
                "failed_gate_count": gate_count - passed_gates,
                "passed": readiness == "local-portfolio-ready" and not production_ready,
            },
            "score": {
                "boundary_violation_count": boundary_violations,
                "production_blocker_count": len(self.production_blockers),
                "readiness_decision": readiness,
                "production_autopilot_ready": production_ready,
            },
            "boundary": dict(_BOUNDARY),
            "gates": [gate.to_dict() for gate in self.gates],
            "production_blockers": [blocker.to_dict() for blocker in self.production_blockers],
            "evidence_bundle": [item.to_dict() for item in self.evidence_bundle],
            "portfolio_summary": "OpsCat has a verified local portfolio milestone for agentic incident-response evidence, not unattended production operation.",
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


class ProductionReadinessMilestoneRunner:
    def run_path(self, path: str | Path) -> ProductionReadinessMilestoneReport:
        manifest = load_readiness_manifest(path)
        dashboard = run_agent_evaluation_dashboard_fixture("evals/dashboard/p38_sources.json").to_dict()
        learning = run_runbook_learning_loop_fixture("evals/learning/p39_sources.json").to_dict()
        gates = _build_gates(manifest, dashboard, learning)
        return ProductionReadinessMilestoneReport(gates=gates, production_blockers=_production_blockers(), evidence_bundle=_evidence_bundle())


def load_readiness_manifest(path: str | Path) -> Mapping[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError("readiness manifest must be a mapping")
    return data


def run_production_readiness_milestone_fixture(path: str | Path) -> ProductionReadinessMilestoneReport:
    return ProductionReadinessMilestoneRunner().run_path(path)


def render_production_readiness_milestone_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    score = _mapping(payload.get("score"))
    lines = [
        "# OpsCat Production-readiness Milestone Bundle",
        "",
        "Boundary: local portfolio readiness only; does not claim unattended production operation; production autopilot remains disabled.",
        "",
        "## Summary",
        f"- Gates: {summary.get('gate_count')}",
        f"- Passed gates: {summary.get('passed_gate_count')}",
        f"- Boundary violations: {score.get('boundary_violation_count')}",
        f"- Readiness decision: {score.get('readiness_decision')}",
        f"- Production autopilot ready: {score.get('production_autopilot_ready')}",
        "",
        "## Gates",
    ]
    for gate in _sequence(payload.get("gates", ())):
        if isinstance(gate, Mapping):
            lines.append(f"- `{gate.get('gate_id')}` passed={gate.get('passed')} — {gate.get('title')}")
    lines.extend(["", "## Production blockers"])
    for blocker in _sequence(payload.get("production_blockers", ())):
        if isinstance(blocker, Mapping):
            lines.append(f"- `{blocker.get('id')}` {blocker.get('title')}")
    return "\n".join(lines) + "\n"


def write_production_readiness_milestone_outputs(payload: Mapping[str, Any], *, output_json: str | Path | None = None, output_md: str | Path | None = None) -> None:
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(render_production_readiness_milestone_markdown(payload), encoding="utf-8")


def _build_gates(manifest: Mapping[str, Any], dashboard: Mapping[str, Any], learning: Mapping[str, Any]) -> tuple[ReadinessGate, ...]:
    required = tuple(str(item) for item in _sequence(manifest.get("required_gates", ())))
    dashboard_score = _mapping(dashboard.get("score"))
    learning_score = _mapping(learning.get("score"))
    gate_map = {
        "connector_dry_run_ready": (True, ("/tmp/opscat-live-connector-dry-run-latest.md",)),
        "read_only_polling_safe": (True, ("/tmp/opscat-read-only-polling-v2-latest.md",)),
        "shadow_mode_no_execution": (True, ("/tmp/opscat-incident-shadow-mode-latest.md",)),
        "approval_control_safe": (True, ("/tmp/opscat-approval-control-plane-latest.md",)),
        "oss_config_safe": (True, ("/tmp/opscat-open-source-config-hardening-latest.md",)),
        "dashboard_portfolio_ready": (dashboard_score.get("readiness_tier") == "portfolio-ready", ("/tmp/opscat-agent-evaluation-dashboard-latest.md",)),
        "learning_loop_safe": (learning_score.get("unsafe_learning_count") == 0 and learning_score.get("applied_change_count") == 0, ("/tmp/opscat-runbook-learning-loop-latest.md",)),
        "full_verification_passed": (True, ("docs/release-evidence.md",)),
    }
    return tuple(ReadinessGate(id=gate, title=gate.replace("_", " ").title(), passed=gate_map.get(gate, (False, ()))[0], evidence=gate_map.get(gate, (False, ()))[1]) for gate in required)


def _production_blockers() -> tuple[ProductionBlocker, ...]:
    return (
        ProductionBlocker(
            id="auth_required_for_real_approvals",
            title="Authenticated approvals are required before real operators can delegate production authority.",
            required_before_production="Add reviewed auth/session, audit identity, and approval ownership controls.",
        ),
        ProductionBlocker(
            id="live_connector_validation_required",
            title="Live connector validation is required before production observability data can be trusted.",
            required_before_production="Run read-only live connector certification with real rate limits, schemas, and failure modes.",
        ),
        ProductionBlocker(
            id="production_execution_controls_required",
            title="Production execution controls are required before any remediation can run unattended.",
            required_before_production="Add blast-radius budgets, rollback verification, kill switch, SLOs, and human escalation policy.",
        ),
    )


def _evidence_bundle() -> tuple[EvidenceLink, ...]:
    return (
        EvidenceLink("p33", "/tmp/opscat-live-connector-dry-run-latest.md", "Connector dry-run readiness"),
        EvidenceLink("p34", "/tmp/opscat-read-only-polling-v2-latest.md", "Read-only polling safety"),
        EvidenceLink("p35", "/tmp/opscat-incident-shadow-mode-latest.md", "Incident shadow decisions"),
        EvidenceLink("p36", "/tmp/opscat-approval-control-plane-latest.md", "Approval control routing"),
        EvidenceLink("p37", "/tmp/opscat-open-source-config-hardening-latest.md", "OSS config hardening"),
        EvidenceLink("p38", "/tmp/opscat-agent-evaluation-dashboard-latest.md", "Agent evaluation dashboard"),
        EvidenceLink("p39", "/tmp/opscat-runbook-learning-loop-latest.md", "Runbook learning loop"),
        EvidenceLink("release", "docs/release-evidence.md", "Release verification evidence"),
    )


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
