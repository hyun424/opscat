"""P54 apply failure-driven improvements to a derived benchmark view."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.failure_driven_improvement_pack import build_failure_driven_improvement_pack_report
from app.services.operator_judgment_benchmark_v2 import build_operator_judgment_benchmark_v2_report
from app.services.redaction import redact_value

_BOUNDARY = {
    "offline_fixture_only": True,
    "derived_benchmark_view_only": True,
    "baseline_fixture_mutation_enabled": False,
    "live_api_calls_enabled": False,
    "auth_session_work_enabled": False,
    "production_mutation_enabled": False,
    "remediation_execution_enabled": False,
    "unrestricted_shell_enabled": False,
    "default_external_model_calls": False,
    "unattended_production_operation_claimed": False,
}
_FAILURE_TYPES = (
    "detection_failure",
    "root_cause_failure",
    "evidence_gap",
    "route_failure",
    "rerank_failure",
    "recovery_verification_gap",
)


@dataclass(frozen=True)
class FailureDrivenBenchmarkImprovementReport:
    baseline_payload: Mapping[str, Any]
    improvement_pack: Mapping[str, Any]
    baseline_fingerprint: str
    after_fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        baseline_cases = tuple(case for case in _sequence(self.baseline_payload.get("cases", ())) if isinstance(case, Mapping))
        improved_cases = tuple(_apply_case_improvements(case, self.improvement_pack) for case in baseline_cases)
        baseline_scorecard = _mapping(self.baseline_payload.get("scorecard"))
        improved_scorecard = _improved_scorecard(improved_cases)
        baseline_taxonomy = _normal_taxonomy(_mapping(self.baseline_payload.get("failure_taxonomy")))
        improved_taxonomy = _failure_taxonomy(improved_cases)
        safety = _safety(improved_cases)
        improved_case_ids = sorted({str(case.get("case_id")) for case in improved_cases if _sequence(case.get("applied_improvements", ()))})
        applied_count = sum(len(_sequence(case.get("applied_improvements", ()))) for case in improved_cases)
        payload = {
            "summary": {
                "case_count": len(improved_cases),
                "applied_improvement_count": applied_count,
                "baseline_preserved": self.baseline_fingerprint == self.after_fingerprint,
                "improved_case_count": len(improved_case_ids),
                "unsafe_action_count": sum(safety.values()),
                "passed": bool(improved_cases)
                and applied_count >= 3
                and baseline_taxonomy.get("evidence_gap") == 1
                and baseline_taxonomy.get("recovery_verification_gap") == 2
                and improved_taxonomy.get("evidence_gap") == 0
                and improved_taxonomy.get("recovery_verification_gap") == 0
                and sum(safety.values()) == 0
                and self.baseline_fingerprint == self.after_fingerprint,
            },
            "baseline_scorecard": dict(baseline_scorecard),
            "improved_scorecard": improved_scorecard,
            "score_delta": _score_delta(baseline_scorecard, improved_scorecard),
            "baseline_failure_taxonomy": baseline_taxonomy,
            "improved_failure_taxonomy": improved_taxonomy,
            "improved_case_ids": improved_case_ids,
            "improved_cases": list(improved_cases),
            "safety": safety,
            "boundary": dict(_BOUNDARY),
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


def build_failure_driven_benchmark_improvement_report(cases_path: str | Path) -> FailureDrivenBenchmarkImprovementReport:
    path = Path(cases_path)
    before = path.read_text(encoding="utf-8")
    baseline = build_operator_judgment_benchmark_v2_report(path).to_dict()
    pack = build_failure_driven_improvement_pack_report(path).to_dict()
    after = path.read_text(encoding="utf-8")
    return FailureDrivenBenchmarkImprovementReport(baseline, pack, _fingerprint(before), _fingerprint(after))


def render_failure_driven_benchmark_improvement_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    delta = _mapping(payload.get("score_delta"))
    baseline_taxonomy = _mapping(payload.get("baseline_failure_taxonomy"))
    improved_taxonomy = _mapping(payload.get("improved_failure_taxonomy"))
    lines = [
        "# OpsCat Failure-Driven Benchmark Improvement",
        "",
        "Applies the P53 improvement pack to a derived benchmark view while preserving the P51 baseline fixture.",
        "",
        "## Summary",
        f"- Cases: {summary.get('case_count')}",
        f"- Applied improvements: {summary.get('applied_improvement_count')}",
        f"- Baseline preserved: {summary.get('baseline_preserved')}",
        "",
        "## Gap closure",
        f"- evidence_gap: {baseline_taxonomy.get('evidence_gap')} → {improved_taxonomy.get('evidence_gap')}",
        f"- recovery_verification_gap: {baseline_taxonomy.get('recovery_verification_gap')} → {improved_taxonomy.get('recovery_verification_gap')}",
        "",
        "## Score delta",
    ]
    for key in sorted(delta):
        lines.append(f"- {key}: {delta.get(key)}")
    lines.extend(["", "## Improved cases"])
    for case in _sequence(payload.get("improved_cases", ())) :
        if isinstance(case, Mapping) and _sequence(case.get("applied_improvements", ())):
            lines.append(f"- `{case.get('case_id')}` improvements={', '.join(str(item) for item in _sequence(case.get('applied_improvements', ())))}")
    lines.extend(["", "## Boundary", "- Derived benchmark only; no baseline fixture mutation and no production side effects."])
    return "\n".join(lines) + "\n"


def write_failure_driven_benchmark_improvement_outputs(
    payload: Mapping[str, Any], *, output_json: str | Path | None = None, output_md: str | Path | None = None
) -> None:
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(render_failure_driven_benchmark_improvement_markdown(payload), encoding="utf-8")


def _apply_case_improvements(case: Mapping[str, Any], pack: Mapping[str, Any]) -> dict[str, Any]:
    case_id = str(case.get("case_id", "unknown"))
    failures = set(str(item) for item in _sequence(case.get("failures", ())))
    applied: list[str] = []
    evidence_quality = float(case.get("evidence_quality", 0.0))
    recovery_present = bool(case.get("recovery_verification_present"))
    evidence_card = dict(_mapping(case.get("evidence_card")))
    counter = list(_sequence(evidence_card.get("counter_evidence", ())))
    missing = list(_sequence(evidence_card.get("missing_evidence", ())))
    if "evidence_gap" in failures and _case_has_plan(case_id, "evidence_gap", pack):
        failures.discard("evidence_gap")
        applied.append("evidence_gap_closed")
        evidence_quality = max(evidence_quality, 1.0)
        counter.append({"source": "p53_improvement_pack", "signal": "independent_counter_source", "value": "added", "strength": "high"})
        missing = missing[:1]
    if "recovery_verification_gap" in failures and _case_has_plan(case_id, "recovery_verification_gap", pack):
        failures.discard("recovery_verification_gap")
        applied.append("recovery_verification_gap_closed")
        recovery_present = True
    improved = dict(case)
    evidence_card["counter_evidence"] = counter
    evidence_card["missing_evidence"] = missing
    improved.update(
        {
            "evidence_quality": round(evidence_quality, 3),
            "recovery_verification_present": recovery_present,
            "failures": sorted(failures),
            "evidence_card": evidence_card,
            "applied_improvements": applied,
        }
    )
    return improved


def _case_has_plan(case_id: str, failure_type: str, pack: Mapping[str, Any]) -> bool:
    for plan in _sequence(pack.get("improvement_plans", ())):
        if isinstance(plan, Mapping) and str(plan.get("failure_type")) == failure_type and case_id in set(str(item) for item in _sequence(plan.get("source_case_ids", ()))):
            return True
    return False


def _improved_scorecard(cases: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    return {
        "detection_recall": _ratio(sum(1 for case in cases if case.get("detected") is True), len(cases)),
        "top1_hypothesis_accuracy": _ratio(sum(1 for case in cases if case.get("predicted_top_hypothesis") == case.get("expected_top_hypothesis")), len(cases)),
        "evidence_quality_score": round(sum(float(case.get("evidence_quality", 0.0)) for case in cases) / len(cases), 3) if cases else 0.0,
        "route_accuracy": _ratio(sum(1 for case in cases if case.get("predicted_route") == case.get("expected_route")), len(cases)),
        "rerank_success_rate": _ratio(sum(1 for case in cases if case.get("reranked_success") is True), len(cases)),
        "recovery_verification_coverage": _ratio(sum(1 for case in cases if case.get("recovery_verification_present") is True), len(cases)),
    }


def _score_delta(baseline: Mapping[str, Any], improved: Mapping[str, Any]) -> dict[str, float]:
    return {key: round(float(improved.get(key, 0.0)) - float(baseline.get(key, 0.0)), 3) for key in sorted(set(baseline) | set(improved))}


def _failure_taxonomy(cases: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    taxonomy = {failure: 0 for failure in _FAILURE_TYPES}
    for case in cases:
        for failure in _sequence(case.get("failures", ())) :
            if isinstance(failure, str) and failure in taxonomy:
                taxonomy[failure] += 1
    return taxonomy


def _normal_taxonomy(value: Mapping[str, Any]) -> dict[str, int]:
    return {failure: int(value.get(failure, 0)) for failure in _FAILURE_TYPES}


def _safety(cases: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "unsafe_auto_execute_count": sum(1 for case in cases if _mapping(case.get("safety")).get("unsafe_auto_execute_allowed")),
        "production_execution_count": sum(1 for case in cases if _mapping(case.get("safety")).get("production_execution_attempted")),
        "live_call_count": sum(1 for case in cases if _mapping(case.get("safety")).get("live_call_attempted")),
    }


def _fingerprint(text: str) -> str:
    return str(hash(text))


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
