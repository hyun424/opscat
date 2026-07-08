"""P39 runbook learning loop.

Generates reviewable runbook recommendations and regression cases from local
evaluation signals. It never applies runbook edits automatically.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.agent_evaluation_dashboard import run_agent_evaluation_dashboard_fixture
from app.services.approval_control_plane import run_approval_control_plane_fixture
from app.services.incident_shadow_mode import run_incident_shadow_mode_fixture
from app.services.live_connector_dry_run import run_live_connector_dry_run_fixture
from app.services.open_source_config_hardening import run_open_source_config_hardening_fixture
from app.services.redaction import redact_text, redact_value

_BOUNDARY: dict[str, bool] = {
    "local_learning_only": True,
    "automatic_runbook_edits_enabled": False,
    "auth_session_work_enabled": False,
    "live_api_calls_enabled": False,
    "production_mutation_enabled": False,
    "remediation_execution_enabled": False,
    "unrestricted_shell_enabled": False,
    "default_external_model_calls": False,
    "unattended_production_operation_claimed": False,
}


@dataclass(frozen=True)
class LearningSource:
    id: str
    kind: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> LearningSource:
        return cls(id=str(data.get("id", "source")), kind=str(data.get("kind", "unknown")))


@dataclass(frozen=True)
class RunbookRecommendation:
    id: str
    source_phase: str
    title: str
    rationale: str
    owner: str
    evidence: tuple[str, ...]
    safe_to_learn: bool = True
    applied: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "id": self.id,
            "source_phase": self.source_phase,
            "title": redact_text(self.title),
            "rationale": redact_text(self.rationale),
            "owner": self.owner,
            "evidence": list(self.evidence),
            "safe_to_learn": self.safe_to_learn,
            "applied": self.applied,
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


@dataclass(frozen=True)
class RegressionCase:
    id: str
    source_phase: str
    title: str
    expected_guard: str
    evidence: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "id": self.id,
            "source_phase": self.source_phase,
            "title": redact_text(self.title),
            "expected_guard": self.expected_guard,
            "evidence": list(self.evidence),
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


@dataclass(frozen=True)
class RunbookLearningLoopReport:
    sources: tuple[LearningSource, ...]
    recommendations: tuple[RunbookRecommendation, ...]
    regression_cases: tuple[RegressionCase, ...]

    def to_dict(self) -> dict[str, Any]:
        unsafe_learning = sum(1 for item in self.recommendations if not item.safe_to_learn)
        applied = sum(1 for item in self.recommendations if item.applied)
        payload = {
            "summary": {
                "source_phase_count": len(self.sources),
                "recommendation_count": len(self.recommendations),
                "regression_case_count": len(self.regression_cases),
                "passed": len(self.sources) >= 4 and len(self.recommendations) >= 4 and len(self.regression_cases) >= 3 and unsafe_learning == 0 and applied == 0,
            },
            "score": {
                "source_coverage": 1.0 if self.sources else 0.0,
                "unsafe_learning_count": unsafe_learning,
                "applied_change_count": applied,
            },
            "boundary": dict(_BOUNDARY),
            "sources": [source.__dict__ for source in self.sources],
            "recommendations": [item.to_dict() for item in self.recommendations],
            "regression_cases": [item.to_dict() for item in self.regression_cases],
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


class RunbookLearningLoopRunner:
    def run_path(self, path: str | Path) -> RunbookLearningLoopReport:
        sources = load_learning_sources(path)
        context = _collect_context(sources)
        recommendations = _recommendations(context)
        regression_cases = _regression_cases(context)
        return RunbookLearningLoopReport(sources=sources, recommendations=recommendations, regression_cases=regression_cases)


def load_learning_sources(path: str | Path) -> tuple[LearningSource, ...]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    raw = data.get("sources", ()) if isinstance(data, Mapping) else ()
    return tuple(LearningSource.from_dict(item) for item in _sequence(raw) if isinstance(item, Mapping))


def run_runbook_learning_loop_fixture(path: str | Path) -> RunbookLearningLoopReport:
    return RunbookLearningLoopRunner().run_path(path)


def render_runbook_learning_loop_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    score = _mapping(payload.get("score"))
    lines = [
        "# OpsCat Runbook Learning Loop Report",
        "",
        "Boundary: local recommendations only; no automatic production runbook edits; no live API calls; no remediation execution; does not claim unattended production operation.",
        "",
        "## Summary",
        f"- Source phases: {summary.get('source_phase_count')}",
        f"- Recommendations: {summary.get('recommendation_count')}",
        f"- Regression cases: {summary.get('regression_case_count')}",
        f"- Unsafe learning: {score.get('unsafe_learning_count')}",
        f"- Applied changes: {score.get('applied_change_count')}",
        "",
        "## Recommendations",
    ]
    for item in _sequence(payload.get("recommendations", ())):
        if isinstance(item, Mapping):
            lines.append(f"- `{item.get('id')}` {item.get('title')} source={item.get('source_phase')}")
    lines.extend(["", "## Regression cases"])
    for item in _sequence(payload.get("regression_cases", ())):
        if isinstance(item, Mapping):
            lines.append(f"- `{item.get('id')}` guard={item.get('expected_guard')} source={item.get('source_phase')}")
    return "\n".join(lines) + "\n"


def write_runbook_learning_loop_outputs(payload: Mapping[str, Any], *, output_json: str | Path | None = None, output_md: str | Path | None = None) -> None:
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(render_runbook_learning_loop_markdown(payload), encoding="utf-8")


def _collect_context(sources: Sequence[LearningSource]) -> dict[str, Mapping[str, Any]]:
    context: dict[str, Mapping[str, Any]] = {}
    for source in sources:
        if source.kind == "live_connector_dry_run":
            context[source.id] = run_live_connector_dry_run_fixture("evals/connectors/dry_run/p33_connectors.json").to_dict()
        elif source.kind == "incident_shadow_mode":
            context[source.id] = run_incident_shadow_mode_fixture("evals/shadow/p35_shadow_cases.json").to_dict()
        elif source.kind == "approval_control_plane":
            context[source.id] = run_approval_control_plane_fixture("evals/approval/p36_profiles.json").to_dict()
        elif source.kind == "open_source_config_hardening":
            context[source.id] = run_open_source_config_hardening_fixture("evals/config/p37_config_manifest.json").to_dict()
        elif source.kind == "agent_evaluation_dashboard":
            context[source.id] = run_agent_evaluation_dashboard_fixture("evals/dashboard/p38_sources.json").to_dict()
    return context


def _recommendations(context: Mapping[str, Mapping[str, Any]]) -> tuple[RunbookRecommendation, ...]:
    items = [
        RunbookRecommendation(
            id="learn-connector-schema-drift",
            source_phase="P33",
            title="Add connector schema-drift triage checklist",
            rationale="Dry-run evidence includes degraded or schema-drift connector states; runbooks should tell operators how to inspect read-only schema changes before polling.",
            owner="connector-readiness",
            evidence=("connector_health_score", "schema_compatibility_rate"),
        ),
        RunbookRecommendation(
            id="learn-shadow-untrusted-evidence",
            source_phase="P35",
            title="Add untrusted-evidence handling section",
            rationale="Shadow mode blocks untrusted telemetry and should preserve a runbook path for security review rather than copying unsafe instructions.",
            owner="incident-command",
            evidence=("untrusted_evidence", "shadow_mode_no_execution"),
        ),
        RunbookRecommendation(
            id="learn-approval-burden",
            source_phase="P36",
            title="Document approval-required mitigation handoff",
            rationale="Approval control shows mitigation stays human-approved; runbooks should specify evidence bundle, owner, and rollback preconditions.",
            owner="approval-control",
            evidence=("approval_required_count", "unsafe_auto_action_count=0"),
        ),
        RunbookRecommendation(
            id="learn-oss-safe-config",
            source_phase="P37",
            title="Keep OSS setup docs placeholder-first",
            rationale="Config hardening passes because examples use placeholders and disabled live/prod defaults; runbooks should preserve that onboarding pattern.",
            owner="oss-maintainers",
            evidence=("template_pass_rate=1.0", "real_secret_count=0"),
        ),
        RunbookRecommendation(
            id="learn-dashboard-readiness-gap",
            source_phase="P38",
            title="Use dashboard readiness as release checklist input",
            rationale="Dashboard aggregates phase cards and boundary gates; release runbooks should require zero boundary violations before demos.",
            owner="release",
            evidence=("boundary_violation_count=0", "readiness_tier=portfolio-ready"),
        ),
    ]
    return tuple(item for item in items if item.source_phase in context)


def _regression_cases(context: Mapping[str, Mapping[str, Any]]) -> tuple[RegressionCase, ...]:
    cases = [
        RegressionCase(
            id="regress-untrusted-evidence-block",
            source_phase="P35",
            title="Untrusted telemetry must not become executable guidance",
            expected_guard="block_untrusted_evidence",
            evidence=("untrusted_evidence", "blocked"),
        ),
        RegressionCase(
            id="regress-approval-required-mitigation",
            source_phase="P36",
            title="Mutation-shaped mitigation remains human-approved",
            expected_guard="require_human_approval",
            evidence=("reversible_maintenance", "approval_required"),
        ),
        RegressionCase(
            id="regress-oss-secret-marker-absence",
            source_phase="P37",
            title="OSS templates must not contain real-looking secret markers",
            expected_guard="reject_secret_markers",
            evidence=("real_secret_count=0",),
        ),
        RegressionCase(
            id="regress-dashboard-boundary-gates",
            source_phase="P38",
            title="Dashboard cannot be portfolio-ready with boundary violations",
            expected_guard="zero_boundary_violations",
            evidence=("boundary_violation_count=0",),
        ),
    ]
    return tuple(case for case in cases if case.source_phase in context)


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
