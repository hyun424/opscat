"""P10 judgment benchmark runner and reporting."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.models import Evidence, Incident
from app.services.incident_commander import build_incident_command
from app.services.judgment_dataset import JudgmentCase, load_judgment_cases
from app.services.judgment_evaluator import JudgmentScore, evaluate_commander_judgment
from app.services.redaction import redact_text, redact_value

DEFAULT_CASE_PATH = Path("evals/judgment/seed/cases.json")


@dataclass(frozen=True)
class JudgmentBenchmarkCaseResult:
    case: JudgmentCase
    commander: dict[str, Any]
    score: JudgmentScore

    def to_dict(self) -> dict[str, Any]:
        return {"case_id": self.case.id, "case_title": self.case.title, **self.score.to_dict(), "commander": redact_value(self.commander)}


@dataclass(frozen=True)
class JudgmentBenchmarkResult:
    results: tuple[JudgmentBenchmarkCaseResult, ...]
    baseline_comparison: Mapping[str, Any] | None = None
    local_mock_only: bool = True

    @property
    def case_count(self) -> int:
        return len(self.results)

    @property
    def overall_score(self) -> float:
        if not self.results:
            return 0.0
        return round(sum(result.score.overall_score for result in self.results) / len(self.results), 3)

    @property
    def passed(self) -> bool:
        return bool(self.results) and all(result.score.passed for result in self.results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "local_mock_only": self.local_mock_only,
            "case_count": self.case_count,
            "overall_score": self.overall_score,
            "passed": self.passed,
            "dimension_averages": _dimension_averages([result.score for result in self.results]),
            "safety_regressions": [result.case.id for result in self.results if result.score.safety_hard_failed],
            "results": [result.to_dict() for result in self.results],
            "baseline_comparison": dict(self.baseline_comparison or {}),
        }


def run_judgment_benchmark(cases: Sequence[JudgmentCase] | None = None, *, baseline_path: str | Path | None = None) -> JudgmentBenchmarkResult:
    loaded_cases = tuple(cases if cases is not None else load_judgment_cases(DEFAULT_CASE_PATH))
    results = tuple(_run_case(case) for case in loaded_cases)
    result = JudgmentBenchmarkResult(results=results)
    comparison = compare_to_baseline(result, baseline_path) if baseline_path is not None else None
    return JudgmentBenchmarkResult(results=results, baseline_comparison=comparison)


def compare_to_baseline(result: JudgmentBenchmarkResult, baseline_path: str | Path, *, tolerance: float = 0.02) -> dict[str, Any]:
    path = Path(baseline_path)
    if not path.exists():
        return {"mode": "first_run", "improved": [], "unchanged": [], "regressions": [], "safety_regressions": []}
    baseline = json.loads(path.read_text(encoding="utf-8"))
    old_results = {str(item.get("case_id")): item for item in baseline.get("results", []) if isinstance(item, Mapping)} if isinstance(baseline, Mapping) else {}
    improved: list[str] = []
    unchanged: list[str] = []
    regressions: list[str] = []
    safety_regressions: list[str] = []
    for row in result.results:
        old = old_results.get(row.case.id, {})
        old_score = float(old.get("overall_score", 0.0) or 0.0)
        new_score = row.score.overall_score
        if bool(old.get("safety_hard_failed")) is False and row.score.safety_hard_failed:
            safety_regressions.append(row.case.id)
        if new_score > old_score + tolerance:
            improved.append(row.case.id)
        elif new_score < old_score - tolerance:
            regressions.append(row.case.id)
        else:
            unchanged.append(row.case.id)
    return {
        "mode": "compare",
        "improved": improved,
        "unchanged": unchanged,
        "regressions": regressions,
        "safety_regressions": safety_regressions,
    }


def render_benchmark_markdown(result: JudgmentBenchmarkResult) -> str:
    data = result.to_dict()
    lines = [
        "# OpsCat Incident Judgment Benchmark",
        "",
        "Boundary: local/mock only; no auth/session work; no external dataset download; does not claim unattended production operation.",
        "",
        f"- Cases: {data['case_count']}",
        f"- Overall score: {data['overall_score']}",
        f"- Passed: {data['passed']}",
        "",
        "## Dimension Averages",
    ]
    for name, score in data["dimension_averages"].items():
        lines.append(f"- {name}: {score}")
    lines.extend(["", "## Case Results"])
    for row in data["results"]:
        reasons = "; ".join(str(reason) for reason in row.get("reasons", [])) or "none"
        lines.append(f"- `{row['case_id']}` {redact_text(str(row['case_title']))}: score={row['overall_score']} passed={row['passed']} reasons={redact_text(reasons)}")
    if result.baseline_comparison:
        lines.extend(["", "## Baseline Comparison", f"```json\n{json.dumps(result.baseline_comparison, indent=2, sort_keys=True)}\n```"])
    return "\n".join(lines) + "\n"


def write_benchmark_outputs(result: JudgmentBenchmarkResult, *, output_json: str | Path | None = None, output_md: str | Path | None = None) -> None:
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(render_benchmark_markdown(result), encoding="utf-8")


def _run_case(case: JudgmentCase) -> JudgmentBenchmarkCaseResult:
    incident = _incident_from_case(case)
    commander = build_incident_command(incident).to_dict()
    score = evaluate_commander_judgment(case, commander)
    return JudgmentBenchmarkCaseResult(case=case, commander=commander, score=score)


def _incident_from_case(case: JudgmentCase) -> Incident:
    incident = dict(case.incident)
    incident_model = Incident(
        id=str(incident.get("id") or case.id),
        tenant_id=str(incident.get("tenant_id", "demo")),
        workspace_id=str(incident.get("workspace_id", "demo")),
        alert_fingerprint=str(incident.get("alert_fingerprint", case.id)),
        source=str(incident.get("source", case.source)),
        status=str(incident.get("status", "investigating")),
        service=str(incident.get("service", "benchmark-service")),
        environment=str(incident.get("environment", "staging")),
        severity=str(incident.get("severity", "high")),
        alert_payload=dict(incident.get("alert_payload", {})) if isinstance(incident.get("alert_payload", {}), Mapping) else {},
        summary=str(incident.get("summary", case.title)),
        root_cause_candidate=str(incident.get("root_cause_candidate", "unknown")),
        confidence=float(incident.get("confidence", 0.72) or 0.0),
    )
    incident_model.evidence = _evidence_from_case(case, incident_model)
    return incident_model


def _evidence_from_case(case: JudgmentCase, incident: Incident) -> list[Evidence]:
    evidence: list[Evidence] = []
    for index, item in enumerate(case.evidence, start=1):
        if not isinstance(item, Mapping):
            continue
        metadata = item.get("metadata", {})
        evidence.append(
            Evidence(
                id=str(item.get("id") or f"{case.id}-evidence-{index}"),
                incident_id=incident.id,
                tenant_id=incident.tenant_id,
                workspace_id=incident.workspace_id,
                type=str(item.get("type", "log")),
                source=str(item.get("source", case.source)),
                source_url=None,
                content=str(item.get("content", "")),
                evidence_metadata=dict(metadata) if isinstance(metadata, Mapping) else {},
            )
        )
    return evidence


def _dimension_averages(scores: Sequence[JudgmentScore]) -> dict[str, float]:
    if not scores:
        return {}
    names = sorted(scores[0].dimension_scores)
    return {name: round(sum(score.dimension_scores.get(name, 0.0) for score in scores) / len(scores), 3) for name in names}
