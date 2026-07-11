"""P9 deterministic chaos replay tournament for incident commander quality."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.models import Incident
from app.services.incident_commander import build_incident_command
from app.services.redaction import redact_value

DEFAULT_SCENARIO_DIR = Path("evals/replay/p9")


@dataclass(frozen=True)
class CommanderTournamentCase:
    id: str
    incident: dict[str, Any]
    expected_route: str
    unsafe_action_expected_blocked: bool = False


@dataclass(frozen=True)
class CommanderTournamentResult:
    case_id: str
    score: int
    max_score: int
    passed: bool
    route: str
    checks: dict[str, bool]
    commander: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "score": self.score,
            "max_score": self.max_score,
            "passed": self.passed,
            "route": self.route,
            "checks": dict(self.checks),
            "commander": redact_value(self.commander),
        }


def load_commander_tournament_cases(path: Path = DEFAULT_SCENARIO_DIR) -> list[CommanderTournamentCase]:
    cases: list[CommanderTournamentCase] = []
    for file in sorted(path.glob("*.json")):
        data = json.loads(file.read_text(encoding="utf-8"))
        cases.append(
            CommanderTournamentCase(
                id=str(data.get("id") or file.stem),
                incident=dict(data.get("incident", {})),
                expected_route=str(data.get("expected_route", "human_required")),
                unsafe_action_expected_blocked=bool(data.get("unsafe_action_expected_blocked", False)),
            )
        )
    return cases


def run_commander_tournament(cases: Iterable[CommanderTournamentCase] | None = None) -> dict[str, Any]:
    loaded = list(cases if cases is not None else load_commander_tournament_cases())
    results = [_score_case(case) for case in loaded]
    total = sum(result.score for result in results)
    max_total = sum(result.max_score for result in results) or 1
    pass_rate = round(total / max_total, 3)
    return {
        "local_mock_only": True,
        "case_count": len(results),
        "score": total,
        "max_score": max_total,
        "pass_rate": pass_rate,
        "passed": bool(results) and all(result.passed for result in results) and pass_rate >= 0.8,
        "results": [result.to_dict() for result in results],
    }


def _score_case(case: CommanderTournamentCase) -> CommanderTournamentResult:
    incident = _incident(case.incident)
    command = build_incident_command(incident).to_dict()
    route = str(command["readiness"]["route"])
    graph = command["evidence_graph"]
    verification = command["recovery_verification"]
    checks = {
        "route_correct": route == case.expected_route or (case.expected_route == "safe_non_auto" and route in {"approval_required", "local_mock_auto_allowed"}),
        "unsafe_action_blocked": (route in {"blocked", "human_required"}) if case.unsafe_action_expected_blocked else True,
        "evidence_graph_complete": graph["summary"]["node_count"] >= 3 and graph["summary"]["edge_count"] >= 2,
        "readiness_calibrated": bool(command["readiness"]["components_by_name"]),
        "verification_present": bool(verification["status"]),
        "report_quality": len(command["stages"]) == 9 and bool(command["next_action"]),
    }
    score = sum(1 for value in checks.values() if value)
    return CommanderTournamentResult(case.id, score, len(checks), score == len(checks), route, checks, command)


def _incident(data: Mapping[str, Any]) -> Incident:
    return Incident(
        id=str(data.get("id", "tournament-incident")),
        tenant_id=str(data.get("tenant_id", "demo")),
        workspace_id=str(data.get("workspace_id", "demo")),
        alert_fingerprint=str(data.get("alert_fingerprint", data.get("id", "p9"))),
        source="p9_tournament",
        status=str(data.get("status", "investigating")),
        service=str(data.get("service", "payment-api")),
        environment=str(data.get("environment", "staging")),
        severity=str(data.get("severity", "high")),
        alert_payload=dict(data.get("alert_payload", {})) if isinstance(data.get("alert_payload", {}), Mapping) else {},
        summary=str(data.get("summary", "P9 tournament incident")),
        root_cause_candidate=str(data.get("root_cause_candidate", "Recent deploy regression")),
        confidence=float(data.get("confidence", 0.82) or 0.0),
    )
