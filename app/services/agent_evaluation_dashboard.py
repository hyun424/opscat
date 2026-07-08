"""P38 agent evaluation dashboard.

Aggregates recent local OpsCat evaluation phases into one reproducible JSON and
Markdown scorecard without hosting a UI or touching live systems.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.approval_control_plane import run_approval_control_plane_fixture
from app.services.incident_shadow_mode import run_incident_shadow_mode_fixture
from app.services.live_connector_dry_run import run_live_connector_dry_run_fixture
from app.services.open_source_config_hardening import run_open_source_config_hardening_fixture
from app.services.read_only_polling_v2 import run_read_only_polling_v2_fixture
from app.services.redaction import redact_value

_BOUNDARY: dict[str, bool] = {
    "local_dashboard_only": True,
    "hosted_dashboard_enabled": False,
    "auth_session_work_enabled": False,
    "live_api_calls_enabled": False,
    "production_mutation_enabled": False,
    "remediation_execution_enabled": False,
    "unrestricted_shell_enabled": False,
    "default_external_model_calls": False,
    "unattended_production_operation_claimed": False,
}
_VIOLATION_FLAGS = (
    "hosted_dashboard_enabled",
    "auth_session_work_enabled",
    "live_api_calls_enabled",
    "production_mutation_enabled",
    "remediation_execution_enabled",
    "unrestricted_shell_enabled",
    "default_external_model_calls",
    "unattended_production_operation_claimed",
)


@dataclass(frozen=True)
class DashboardSource:
    id: str
    name: str
    kind: str
    artifact: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DashboardSource:
        return cls(
            id=str(data.get("id", "phase")),
            name=str(data.get("name", "Evaluation phase")),
            kind=str(data.get("kind", "unknown")),
            artifact=str(data.get("artifact", "")),
        )


@dataclass(frozen=True)
class PhaseCard:
    source: DashboardSource
    passed: bool
    score: float
    key_metrics: Mapping[str, Any]
    boundary_violations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "phase_id": self.source.id,
            "name": self.source.name,
            "kind": self.source.kind,
            "artifact": self.source.artifact,
            "passed": self.passed,
            "score": self.score,
            "key_metrics": dict(self.key_metrics),
            "boundary_violations": list(self.boundary_violations),
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


@dataclass(frozen=True)
class AgentEvaluationDashboardReport:
    phase_cards: tuple[PhaseCard, ...]

    def to_dict(self) -> dict[str, Any]:
        count = len(self.phase_cards)
        passed = sum(1 for card in self.phase_cards if card.passed)
        violations = sum(len(card.boundary_violations) for card in self.phase_cards)
        overall = round(sum(card.score for card in self.phase_cards) / count, 3) if count else 0.0
        readiness = "portfolio-ready" if count >= 5 and passed == count and violations == 0 and overall >= 0.9 else "needs-work"
        payload = {
            "summary": {
                "phase_count": count,
                "passed_phase_count": passed,
                "failed_phase_count": count - passed,
                "passed": readiness == "portfolio-ready",
            },
            "score": {
                "overall_score": overall,
                "boundary_violation_count": violations,
                "readiness_tier": readiness,
            },
            "boundary": dict(_BOUNDARY),
            "phase_cards": [card.to_dict() for card in self.phase_cards],
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


class AgentEvaluationDashboardRunner:
    def run_path(self, path: str | Path) -> AgentEvaluationDashboardReport:
        sources = load_dashboard_sources(path)
        return AgentEvaluationDashboardReport(phase_cards=tuple(_build_card(source) for source in sources))


def load_dashboard_sources(path: str | Path) -> tuple[DashboardSource, ...]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    raw = data.get("phases", ()) if isinstance(data, Mapping) else ()
    return tuple(DashboardSource.from_dict(item) for item in _sequence(raw) if isinstance(item, Mapping))


def run_agent_evaluation_dashboard_fixture(path: str | Path) -> AgentEvaluationDashboardReport:
    return AgentEvaluationDashboardRunner().run_path(path)


def render_agent_evaluation_dashboard_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    score = _mapping(payload.get("score"))
    lines = [
        "# OpsCat Agent Evaluation Dashboard",
        "",
        "Boundary: local dashboard artifact only; no hosted UI; no live API calls; no remediation execution; no production mutation; does not claim unattended production operation.",
        "",
        "## Summary",
        f"- Phases: {summary.get('phase_count')}",
        f"- Passed phases: {summary.get('passed_phase_count')}",
        f"- Overall score: {score.get('overall_score')}",
        f"- Boundary violations: {score.get('boundary_violation_count')}",
        f"- Readiness tier: {score.get('readiness_tier')}",
        "",
        "## Phase cards",
    ]
    for card in _sequence(payload.get("phase_cards", ())):
        if isinstance(card, Mapping):
            lines.append(f"- `{card.get('phase_id')}` {card.get('name')} score={card.get('score')} passed={card.get('passed')} artifact={card.get('artifact')}")
    return "\n".join(lines) + "\n"


def write_agent_evaluation_dashboard_outputs(payload: Mapping[str, Any], *, output_json: str | Path | None = None, output_md: str | Path | None = None) -> None:
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(render_agent_evaluation_dashboard_markdown(payload), encoding="utf-8")


def _build_card(source: DashboardSource) -> PhaseCard:
    payload = _payload_for(source.kind)
    summary = _mapping(payload.get("summary"))
    score_payload = _mapping(payload.get("score"))
    passed = bool(summary.get("passed", False))
    boundary = _mapping(payload.get("boundary"))
    violations = tuple(flag for flag in _VIOLATION_FLAGS if bool(boundary.get(flag, False)))
    metrics, score = _metrics_and_score(source.kind, summary, score_payload)
    return PhaseCard(source=source, passed=passed and not violations, score=score, key_metrics=metrics, boundary_violations=violations)


def _payload_for(kind: str) -> Mapping[str, Any]:
    if kind == "live_connector_dry_run":
        return run_live_connector_dry_run_fixture("evals/connectors/dry_run/p33_connectors.json").to_dict()
    if kind == "read_only_polling_v2":
        return run_read_only_polling_v2_fixture("evals/polling/v2/p34_polling_jobs.json", "evals/connectors/dry_run/p33_connectors.json").to_dict()
    if kind == "incident_shadow_mode":
        return run_incident_shadow_mode_fixture("evals/shadow/p35_shadow_cases.json").to_dict()
    if kind == "approval_control_plane":
        return run_approval_control_plane_fixture("evals/approval/p36_profiles.json").to_dict()
    if kind == "open_source_config_hardening":
        return run_open_source_config_hardening_fixture("evals/config/p37_config_manifest.json").to_dict()
    return {"summary": {"passed": False}, "score": {}, "boundary": {"unknown_source": True}}


def _metrics_and_score(kind: str, summary: Mapping[str, Any], score: Mapping[str, Any]) -> tuple[Mapping[str, Any], float]:
    if kind == "live_connector_dry_run":
        value = float(score.get("connector_health_score", 0.0))
        return {"connector_health_score": value, "live_api_call_count": score.get("live_api_call_count", 0)}, value
    if kind == "read_only_polling_v2":
        value = float(score.get("poll_success_rate", 0.0))
        return {"poll_success_rate": value, "unsafe_poll_count": score.get("unsafe_poll_count", 0)}, value
    if kind == "incident_shadow_mode":
        value = float(score.get("expected_route_match_rate", 0.0))
        return {"expected_route_match_rate": value, "execution_count": score.get("execution_count", 0)}, value
    if kind == "approval_control_plane":
        unsafe = int(score.get("unsafe_auto_action_count", 0))
        value = 1.0 if unsafe == 0 and int(score.get("execution_count", 0)) == 0 else 0.0
        return {"unsafe_auto_action_count": unsafe, "execution_count": score.get("execution_count", 0)}, value
    if kind == "open_source_config_hardening":
        value = float(score.get("template_pass_rate", 0.0))
        return {"template_pass_rate": value, "real_secret_count": score.get("real_secret_count", 0)}, value
    return {"passed": summary.get("passed", False)}, 0.0


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
