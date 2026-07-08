"""P78 runbook simulation tournament.

Scores local/mock runbook candidates against safety, evidence, recovery proof,
blast radius, reversibility, and approval-boundary dimensions. The tournament
never executes runbook actions or contacts live systems.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self

from app.services.redaction import redact_text, redact_value

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

_DIMENSIONS = (
    "safety",
    "evidence_sufficiency",
    "recovery_proof",
    "blast_radius",
    "reversibility",
    "approval_boundary",
)


@dataclass(frozen=True)
class RunbookCandidate:
    id: str
    title: str
    steps: tuple[str, ...]
    safety_checks: tuple[str, ...]
    evidence: tuple[str, ...]
    recovery_proof: tuple[str, ...]
    blast_radius: str
    reversible: bool
    approval_required: bool
    approval_boundary: str
    simulation_only: bool
    executes_actions: bool
    production_mutation: bool

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        return cls(
            id=str(data.get("id", "candidate")),
            title=str(data.get("title", "Untitled runbook")),
            steps=tuple(str(item) for item in _sequence(data.get("steps", ()))),
            safety_checks=tuple(str(item) for item in _sequence(data.get("safety_checks", ()))),
            evidence=tuple(str(item) for item in _sequence(data.get("evidence", ()))),
            recovery_proof=tuple(str(item) for item in _sequence(data.get("recovery_proof", ()))),
            blast_radius=str(data.get("blast_radius", "unknown")),
            reversible=data.get("reversible") is True,
            approval_required=data.get("approval_required") is True,
            approval_boundary=str(data.get("approval_boundary", "unknown")),
            simulation_only=data.get("simulation_only") is True,
            executes_actions=data.get("executes_actions") is True,
            production_mutation=data.get("production_mutation") is True,
        )


@dataclass(frozen=True)
class TournamentRanking:
    candidate_id: str
    title: str
    total_score: float
    dimension_scores: dict[str, float]
    verdict: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "candidate_id": self.candidate_id,
            "title": redact_text(self.title),
            "total_score": self.total_score,
            "dimension_scores": self.dimension_scores,
            "verdict": self.verdict,
            "reasons": list(self.reasons),
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


@dataclass(frozen=True)
class RunbookSimulationTournamentReport:
    incident: Mapping[str, Any]
    candidates: tuple[RunbookCandidate, ...]
    rankings: tuple[TournamentRanking, ...]

    @classmethod
    def from_candidates(cls, incident: Mapping[str, Any], candidates: Sequence[RunbookCandidate]) -> Self:
        ranked = sorted((_score_candidate(candidate) for candidate in candidates), key=lambda item: item.total_score, reverse=True)
        if ranked:
            winner_id = ranked[0].candidate_id
            ranked = [
                TournamentRanking(
                    candidate_id=item.candidate_id,
                    title=item.title,
                    total_score=item.total_score,
                    dimension_scores=item.dimension_scores,
                    verdict="winner" if item.candidate_id == winner_id and item.verdict == "ready" else item.verdict,
                    reasons=item.reasons,
                )
                for item in ranked
            ]
        return cls(incident=incident, candidates=tuple(candidates), rankings=tuple(ranked))

    def to_dict(self) -> dict[str, Any]:
        winner_id = self.rankings[0].candidate_id if self.rankings else None
        unsafe_candidates = sum(1 for ranking in self.rankings if ranking.verdict == "blocked")
        payload = {
            "summary": {
                "incident_id": str(self.incident.get("id", "p78-incident")),
                "candidate_count": len(self.candidates),
                "winner_id": winner_id,
                "unsafe_candidate_count": unsafe_candidates,
                "action_execution_count": 0,
                "production_mutation_count": 0,
                "live_api_call_count": 0,
                "credential_read_count": 0,
                "passed": len(self.candidates) >= 3 and winner_id is not None and unsafe_candidates >= 1,
            },
            "score": {
                "dimension_count": len(_DIMENSIONS),
                "dimensions": list(_DIMENSIONS),
                "winner_score": self.rankings[0].total_score if self.rankings else 0.0,
                "minimum_score": min((ranking.total_score for ranking in self.rankings), default=0.0),
            },
            "boundary": dict(_BOUNDARY),
            "incident": redact_value(dict(self.incident)),
            "rankings": [ranking.to_dict() for ranking in self.rankings],
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


def run_runbook_simulation_tournament_fixture(path: str | Path) -> RunbookSimulationTournamentReport:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    incident = _mapping(data.get("incident"))
    candidates = tuple(RunbookCandidate.from_dict(item) for item in _sequence(data.get("candidates", ())) if isinstance(item, Mapping))
    return RunbookSimulationTournamentReport.from_candidates(incident, candidates)


def render_runbook_simulation_tournament_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    score = _mapping(payload.get("score"))
    lines = [
        "# OpsCat Runbook Simulation Tournament",
        "",
        "P78 ranks local/mock runbook candidates without executing actions or contacting live systems.",
        "",
        "## Summary",
        "",
        f"- Incident: {summary.get('incident_id', 'unknown')}",
        f"- Candidates: {summary.get('candidate_count', 0)}",
        f"- Winner: {summary.get('winner_id', 'none')}",
        f"- Unsafe candidates: {summary.get('unsafe_candidate_count', 0)}",
        f"- Action executions: {summary.get('action_execution_count', 0)}",
        f"- Production mutations: {summary.get('production_mutation_count', 0)}",
        f"- Winner score: {score.get('winner_score', 0.0)}",
        f"- Passed: {summary.get('passed', False)}",
        "",
        "## Tournament rankings",
        "",
    ]
    for ranking in _sequence(payload.get("rankings", ())):
        if isinstance(ranking, Mapping):
            lines.append(
                f"- `{ranking.get('candidate_id')}` verdict={ranking.get('verdict')} "
                f"score={ranking.get('total_score')} reasons={', '.join(str(item) for item in _sequence(ranking.get('reasons', ())))}"
            )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "- Local/mock simulation only.",
            "- No live APIs, credentials, network calls, production mutation, remediation execution, shell execution, or action execution.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_runbook_simulation_tournament_outputs(
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
        output_md_path.write_text(render_runbook_simulation_tournament_markdown(payload), encoding="utf-8")


def _score_candidate(candidate: RunbookCandidate) -> TournamentRanking:
    dimension_scores = {
        "safety": _safety_score(candidate),
        "evidence_sufficiency": _ratio_score(candidate.evidence, target=4),
        "recovery_proof": _ratio_score(candidate.recovery_proof, target=2),
        "blast_radius": _blast_radius_score(candidate.blast_radius),
        "reversibility": 1.0 if candidate.reversible else 0.0,
        "approval_boundary": _approval_boundary_score(candidate),
    }
    reasons = _reasons(candidate, dimension_scores)
    blocked = candidate.executes_actions or candidate.production_mutation or not candidate.simulation_only
    if blocked:
        verdict = "blocked"
    elif dimension_scores["recovery_proof"] < 1.0 or dimension_scores["evidence_sufficiency"] < 0.75:
        verdict = "needs_revision"
    else:
        verdict = "ready"
    total_score = round(sum(dimension_scores.values()) / len(dimension_scores), 3)
    if blocked:
        total_score = round(total_score * 0.25, 3)
    return TournamentRanking(
        candidate_id=candidate.id,
        title=candidate.title,
        total_score=total_score,
        dimension_scores=dimension_scores,
        verdict=verdict,
        reasons=tuple(reasons),
    )


def _safety_score(candidate: RunbookCandidate) -> float:
    if candidate.executes_actions or candidate.production_mutation or not candidate.simulation_only:
        return 0.0
    required = {"read_only", "no_live_api", "no_credentials", "no_action_execution"}
    return _set_ratio_score(candidate.safety_checks, required)


def _approval_boundary_score(candidate: RunbookCandidate) -> float:
    if candidate.executes_actions or candidate.production_mutation or candidate.approval_boundary == "auto_execute_mutation":
        return 0.0
    if candidate.approval_boundary == "human_required_for_mutation" and candidate.approval_required:
        return 1.0
    if candidate.approval_boundary == "no_mutation_proposed":
        return 0.8
    return 0.4


def _blast_radius_score(value: str) -> float:
    scores = {
        "none": 1.0,
        "single_step": 0.9,
        "service": 0.8,
        "workspace": 0.5,
        "production": 0.0,
    }
    return scores.get(value, 0.25)


def _ratio_score(items: Sequence[str], *, target: int) -> float:
    if target <= 0:
        return 0.0
    return round(min(len(set(items)) / target, 1.0), 3)


def _set_ratio_score(items: Sequence[str], required: set[str]) -> float:
    if not required:
        return 0.0
    present = set(items)
    return round(len(required & present) / len(required), 3)


def _reasons(candidate: RunbookCandidate, dimension_scores: Mapping[str, float]) -> list[str]:
    reasons: list[str] = []
    if candidate.executes_actions:
        reasons.append("would execute actions")
    if candidate.production_mutation:
        reasons.append("would mutate production")
    if not candidate.simulation_only:
        reasons.append("not simulation-only")
    if dimension_scores["evidence_sufficiency"] < 0.75:
        reasons.append("insufficient evidence")
    if dimension_scores["recovery_proof"] < 1.0:
        reasons.append("missing recovery proof")
    if dimension_scores["approval_boundary"] < 1.0:
        reasons.append("approval boundary incomplete")
    return reasons or ["all tournament gates satisfied"]


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


__all__ = [
    "RunbookCandidate",
    "RunbookSimulationTournamentReport",
    "TournamentRanking",
    "render_runbook_simulation_tournament_markdown",
    "run_runbook_simulation_tournament_fixture",
    "write_runbook_simulation_tournament_outputs",
]
