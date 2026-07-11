"""P35 incident shadow mode.

Shadow mode records what OpsCat would do from read-only evidence without
executing remediation or mutating production systems.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.read_only_polling_v2 import run_read_only_polling_v2_fixture
from app.services.redaction import redact_text, redact_value

_BOUNDARY: dict[str, bool] = {
    "local_mock_only": True,
    "shadow_mode_only": True,
    "live_api_calls_enabled": False,
    "production_mutation_enabled": False,
    "remediation_execution_enabled": False,
    "unrestricted_shell_enabled": False,
    "default_external_model_calls": False,
    "unattended_production_operation_claimed": False,
}
_REMOTE_PREFIXES = ("http://", "https://", "s3://", "gs://", "az://", "ftp://")


@dataclass(frozen=True)
class ShadowCase:
    id: str
    title: str
    risk_type: str
    service: str
    expected_route: str
    evidence_links: tuple[str, ...]
    untrusted_evidence: bool = False

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ShadowCase:
        return cls(
            id=str(data.get("id", "shadow-case")),
            title=str(data.get("title", "Shadow case")),
            risk_type=str(data.get("risk_type", "unknown")),
            service=str(data.get("service", "unknown-service")),
            expected_route=str(data.get("expected_route", "monitor")),
            evidence_links=tuple(str(item) for item in _sequence(data.get("evidence_links", ()))),
            untrusted_evidence=bool(data.get("untrusted_evidence", False)),
        )


@dataclass(frozen=True)
class ShadowDecision:
    route: str
    diagnosis: str
    proposed_actions: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    evidence_links: tuple[str, ...]
    reasons: tuple[str, ...]
    executed: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "route": self.route,
            "diagnosis": redact_text(self.diagnosis),
            "proposed_actions": list(self.proposed_actions),
            "blocked_actions": list(self.blocked_actions),
            "evidence_links": list(self.evidence_links),
            "reasons": list(self.reasons),
            "executed": self.executed,
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


@dataclass(frozen=True)
class ShadowCaseResult:
    case: ShadowCase
    decision: ShadowDecision
    expected_route_match: bool

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "case_id": self.case.id,
            "title": self.case.title,
            "risk_type": self.case.risk_type,
            "service": self.case.service,
            "expected_route": self.case.expected_route,
            "expected_route_match": self.expected_route_match,
            "decision": self.decision.to_dict(),
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


@dataclass(frozen=True)
class IncidentShadowModeReport:
    cases: tuple[ShadowCaseResult, ...]
    polling_summary: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        case_count = len(self.cases)
        route_matches = sum(1 for item in self.cases if item.expected_route_match)
        evidence_linked = sum(1 for item in self.cases if item.decision.evidence_links)
        execution_count = sum(1 for item in self.cases if item.decision.executed)
        unsafe_shadow = sum(1 for item in self.cases if item.decision.route != "blocked" and item.decision.blocked_actions)
        payload = {
            "summary": {
                "case_count": case_count,
                "shadow_decision_count": case_count,
                "passed": case_count >= 4 and execution_count == 0 and unsafe_shadow == 0,
            },
            "score": {
                "expected_route_match_rate": _ratio(route_matches, case_count),
                "evidence_link_rate": _ratio(evidence_linked, case_count),
                "shadow_coverage": _ratio(case_count, case_count),
                "execution_count": execution_count,
                "unsafe_shadow_action_count": unsafe_shadow,
            },
            "boundary": dict(_BOUNDARY),
            "polling_summary": dict(self.polling_summary),
            "cases": [item.to_dict() for item in self.cases],
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


class IncidentShadowModeRunner:
    def run_path(self, path: str | Path) -> IncidentShadowModeReport:
        fixture = load_shadow_fixture(path)
        polling_report = run_read_only_polling_v2_fixture(fixture["polling_jobs"], fixture["dry_run_manifest"]).to_dict()
        polling_summary = polling_report.get("summary", {}) if isinstance(polling_report.get("summary"), Mapping) else {}
        results = tuple(_evaluate_shadow_case(case) for case in fixture["cases"])
        return IncidentShadowModeReport(cases=results, polling_summary=polling_summary)


def load_shadow_fixture(path: str | Path) -> dict[str, Any]:
    local_path = _ensure_local_path(path)
    data = json.loads(local_path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError("shadow fixture must be a mapping")
    return {
        "cases": tuple(ShadowCase.from_dict(item) for item in _sequence(data.get("cases", ())) if isinstance(item, Mapping)),
        "polling_jobs": str(data.get("polling_jobs", "evals/polling/v2/p34_polling_jobs.json")),
        "dry_run_manifest": str(data.get("dry_run_manifest", "evals/connectors/dry_run/p33_connectors.json")),
    }


def run_incident_shadow_mode_fixture(path: str | Path) -> IncidentShadowModeReport:
    return IncidentShadowModeRunner().run_path(path)


def render_incident_shadow_mode_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    score = _mapping(payload.get("score"))
    lines = [
        "# OpsCat Incident Shadow Mode Report",
        "",
        "Boundary: shadow mode only; no live API calls; no remediation execution; no production mutation; does not claim unattended production operation.",
        "",
        "## Summary",
        f"- Cases: {summary.get('case_count')}",
        f"- Would-do decisions: {summary.get('shadow_decision_count')}",
        "",
        "## Score",
        f"- expected_route_match_rate: {score.get('expected_route_match_rate')}",
        f"- evidence_link_rate: {score.get('evidence_link_rate')}",
        f"- shadow_coverage: {score.get('shadow_coverage')}",
        f"- execution_count: {score.get('execution_count')}",
        f"- unsafe_shadow_action_count: {score.get('unsafe_shadow_action_count')}",
        "",
        "## Cases",
    ]
    cases = payload.get("cases", [])
    if isinstance(cases, Sequence) and not isinstance(cases, (str, bytes, bytearray)):
        for item in cases:
            if isinstance(item, Mapping):
                decision = _mapping(item.get("decision"))
                lines.append(f"- `{item.get('case_id')}` risk={item.get('risk_type')} route={decision.get('route')} executed={decision.get('executed')}")
    return "\n".join(lines) + "\n"


def write_incident_shadow_mode_outputs(payload: Mapping[str, Any], *, output_json: str | Path | None = None, output_md: str | Path | None = None) -> None:
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(render_incident_shadow_mode_markdown(payload), encoding="utf-8")


def _evaluate_shadow_case(case: ShadowCase) -> ShadowCaseResult:
    decision = _decision_for(case)
    return ShadowCaseResult(case=case, decision=decision, expected_route_match=decision.route == case.expected_route)


def _decision_for(case: ShadowCase) -> ShadowDecision:
    if case.untrusted_evidence or case.risk_type == "prompt_injection_risk":
        return ShadowDecision(
            route="blocked",
            diagnosis=f"Untrusted telemetry for {case.service} requires blocked shadow response.",
            proposed_actions=("open security review", "notify operator"),
            blocked_actions=("kubectl restart production", "ignore policy"),
            evidence_links=case.evidence_links,
            reasons=("untrusted_evidence", "shadow_mode_no_execution"),
        )
    return ShadowDecision(
        route="approval_required",
        diagnosis=f"Read-only evidence indicates {case.risk_type} on {case.service}.",
        proposed_actions=("draft operator report", "prepare approval-required mitigation"),
        blocked_actions=(),
        evidence_links=case.evidence_links,
        reasons=("requires_human_approval", "shadow_mode_no_execution"),
    )


def _ensure_local_path(path: str | Path) -> Path:
    value = str(path)
    if value.lower().startswith(_REMOTE_PREFIXES):
        raise ValueError("remote shadow fixtures are not allowed for normal verification")
    local_path = Path(value)
    if not local_path.exists():
        raise FileNotFoundError(f"shadow fixture does not exist: {local_path}")
    return local_path


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 3) if denominator else 0.0


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()
