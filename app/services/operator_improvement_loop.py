"""Operator-grade improvement loop for P18B model judgment failures.

P19 consumes model-quality reports and produces non-mutating improvement
plans: prioritized failures, recommendations, missing-evidence plans,
regression packs, and before/after comparisons. It does not execute actions.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.redaction import redact_text, redact_value

_PRIORITY_TABLE: dict[str, tuple[str, int]] = {
    "schema_or_parse_failure": ("P0", 110),
    "unsafe_action_allowed": ("P0", 100),
    "route_over_auto": ("P1", 90),
    "missing_evidence_ignored": ("P1", 80),
    "hallucinated_citation": ("P1", 70),
    "route_too_conservative": ("P2", 60),
    "action_quality_low": ("P2", 50),
    "weak_hypothesis": ("P2", 40),
}
_SAFE_READ_ONLY_TOOLS = (
    "mock.search_logs",
    "mock.query_metrics",
    "mock.fetch_trace_context",
    "mock.get_service_health",
    "mock.get_recent_deploys",
    "mock.get_error_context",
)
_SECRET_MARKERS = ("nvapi-", "sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token")


@dataclass(frozen=True)
class ImprovementCandidate:
    case_id: str
    case_title: str
    failure_label: str
    priority: str
    priority_score: int
    provider_route: str
    final_route: str
    raw_provider_score: float
    calibrated_score: float
    calibration_delta: float
    affected_dimensions: tuple[str, ...]
    raw_model_failure: bool = True
    calibration_corrected: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "case_title": self.case_title,
            "failure_label": self.failure_label,
            "priority": self.priority,
            "priority_score": self.priority_score,
            "provider_route": self.provider_route,
            "final_route": self.final_route,
            "raw_provider_score": self.raw_provider_score,
            "calibrated_score": self.calibrated_score,
            "calibration_delta": self.calibration_delta,
            "affected_dimensions": list(self.affected_dimensions),
            "raw_model_failure": self.raw_model_failure,
            "calibration_corrected": self.calibration_corrected,
        }


@dataclass(frozen=True)
class ImprovementRecommendation:
    failure_label: str
    owner_area: str
    recommendation: str
    rationale: str
    expected_effect: str
    verification_command: str

    def to_dict(self) -> dict[str, str]:
        return {
            "failure_label": self.failure_label,
            "owner_area": self.owner_area,
            "recommendation": self.recommendation,
            "rationale": self.rationale,
            "expected_effect": self.expected_effect,
            "verification_command": self.verification_command,
        }


@dataclass(frozen=True)
class MissingEvidencePlan:
    case_id: str
    reason: str
    read_only_tools: tuple[str, ...]
    blocked_actions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "reason": self.reason,
            "read_only_tools": list(self.read_only_tools),
            "blocked_actions": list(self.blocked_actions),
        }


@dataclass(frozen=True)
class ImprovementPlan:
    provider: str
    model: str
    raw_provider_score: float
    calibrated_score: float
    calibration_delta: float
    taxonomy_counts: Mapping[str, int]
    top_candidates: tuple[ImprovementCandidate, ...]
    recommendations: tuple[ImprovementRecommendation, ...]
    missing_evidence_plans: tuple[MissingEvidencePlan, ...]
    regression_pack_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "raw_provider_score": self.raw_provider_score,
            "calibrated_score": self.calibrated_score,
            "calibration_delta": self.calibration_delta,
            "taxonomy_counts": dict(self.taxonomy_counts),
            "top_candidates": [candidate.to_dict() for candidate in self.top_candidates],
            "recommendations": [recommendation.to_dict() for recommendation in self.recommendations],
            "missing_evidence_plans": [plan.to_dict() for plan in self.missing_evidence_plans],
            "regression_pack_path": self.regression_pack_path,
            "boundary": {
                "local_mock_only": True,
                "action_execution_enabled": False,
                "production_mutation_enabled": False,
                "default_external_model_calls": False,
            },
        }


@dataclass(frozen=True)
class QualityComparison:
    provider: str
    model: str
    raw_provider_score_delta: float
    calibrated_score_delta: float
    taxonomy_deltas: Mapping[str, int]
    new_safety_failures: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "raw_provider_score_delta": self.raw_provider_score_delta,
            "calibrated_score_delta": self.calibrated_score_delta,
            "taxonomy_deltas": dict(self.taxonomy_deltas),
            "new_safety_failures": list(self.new_safety_failures),
            "note": "raw model improvement is reported separately from calibrated safety wins",
        }


def load_model_quality_report(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return _validate_report(data)


def build_improvement_plan(report: Mapping[str, Any], *, regression_pack_path: str | Path | None = None) -> ImprovementPlan:
    normalized = _validate_report(report)
    candidates = tuple(_candidate for row in _result_rows(normalized) for _candidate in _candidates_from_row(row))
    sorted_candidates = tuple(sorted(candidates, key=lambda item: (-item.priority_score, item.case_id, item.failure_label)))
    labels = tuple(dict.fromkeys(candidate.failure_label for candidate in sorted_candidates))
    evidence_plans = tuple(_plan for row in _result_rows(normalized) for _plan in _missing_evidence_plans_from_row(row))
    return ImprovementPlan(
        provider=str(normalized.get("provider", "unknown")),
        model=str(normalized.get("model", "unknown")),
        raw_provider_score=_float(normalized.get("raw_provider_score")),
        calibrated_score=_float(normalized.get("calibrated_score")),
        calibration_delta=_float(normalized.get("calibration_delta")),
        taxonomy_counts={str(key): int(value) for key, value in _mapping(normalized.get("failure_taxonomy_counts")).items()},
        top_candidates=sorted_candidates,
        recommendations=tuple(_recommendation_for_label(label) for label in labels),
        missing_evidence_plans=evidence_plans,
        regression_pack_path=str(regression_pack_path) if regression_pack_path else None,
    )


def compare_quality_reports(before: Mapping[str, Any], after: Mapping[str, Any]) -> QualityComparison:
    before_norm = _validate_report(before)
    after_norm = _validate_report(after)
    if str(before_norm.get("provider")) != str(after_norm.get("provider")):
        raise ValueError("P19 comparison requires compatible provider values")
    before_taxonomy = Counter({str(key): int(value) for key, value in _mapping(before_norm.get("failure_taxonomy_counts")).items()})
    after_taxonomy = Counter({str(key): int(value) for key, value in _mapping(after_norm.get("failure_taxonomy_counts")).items()})
    labels = sorted(set(before_taxonomy) | set(after_taxonomy))
    deltas = {label: after_taxonomy.get(label, 0) - before_taxonomy.get(label, 0) for label in labels}
    safety_labels = ("unsafe_action_allowed", "schema_or_parse_failure", "route_over_auto")
    new_safety = tuple(label for label in safety_labels if deltas.get(label, 0) > 0)
    return QualityComparison(
        provider=str(after_norm.get("provider", "unknown")),
        model=str(after_norm.get("model", "unknown")),
        raw_provider_score_delta=round(_float(after_norm.get("raw_provider_score")) - _float(before_norm.get("raw_provider_score")), 3),
        calibrated_score_delta=round(_float(after_norm.get("calibrated_score")) - _float(before_norm.get("calibrated_score")), 3),
        taxonomy_deltas=deltas,
        new_safety_failures=new_safety,
    )


def write_regression_pack(plan: ImprovementPlan, path: str | Path) -> None:
    payload = {
        "pack_id": f"p19-regression-{plan.provider}-{len(plan.top_candidates)}",
        "source_provider": plan.provider,
        "source_model": plan.model,
        "local_mock_only": True,
        "action_execution_enabled": False,
        "cases": [
            {
                "case_id": candidate.case_id,
                "case_title": candidate.case_title,
                "failure_taxonomy": [candidate.failure_label],
                "priority": candidate.priority,
                "expected_improvement": _recommendation_for_label(candidate.failure_label).expected_effect,
                "preserve_raw_failure_visibility": True,
            }
            for candidate in plan.top_candidates
        ],
    }
    sanitized = redact_value(payload)
    text = json.dumps(sanitized, indent=2, sort_keys=True) + "\n"
    if any(marker in text for marker in _SECRET_MARKERS):
        raise ValueError("regression pack contains secret marker")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")


def write_improvement_outputs(
    plan: ImprovementPlan,
    *,
    output_json: str | Path | None = None,
    output_md: str | Path | None = None,
) -> None:
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(json.dumps(redact_value(plan.to_dict()), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(render_improvement_plan_markdown(plan), encoding="utf-8")


def render_improvement_plan_markdown(plan: ImprovementPlan) -> str:
    payload = plan.to_dict()
    lines = [
        "# OpsCat Operator Judgment Improvement Loop",
        "",
        "Boundary: no-auth/local-mock by default; no default external model/API calls; no action execution; no production mutation; does not claim unattended production operation.",
        "",
        f"- Provider: {payload['provider']}",
        f"- Model: {payload['model']}",
        f"- Raw provider score: {payload['raw_provider_score']}",
        f"- Calibrated score: {payload['calibrated_score']}",
        f"- Calibration delta: {payload['calibration_delta']}",
        f"- Regression pack: {payload.get('regression_pack_path') or 'not written'}",
        "",
        "## Raw model improvement",
        "",
        "P19 tracks raw model improvement separately from calibrated safety wins so policy corrections do not hide model defects.",
        "",
        "## Failure priorities",
    ]
    if payload["top_candidates"]:
        for candidate in payload["top_candidates"]:
            lines.append(
                f"- {candidate['priority']} `{candidate['failure_label']}` case={candidate['case_id']} "
                f"raw={candidate['raw_provider_score']} calibrated={candidate['calibrated_score']} "
                f"corrected={candidate['calibration_corrected']}"
            )
    else:
        lines.append("- none")
    lines.extend(["", "## Recommendations"])
    for recommendation in payload["recommendations"]:
        lines.append(
            f"- `{recommendation['failure_label']}` owner={recommendation['owner_area']}: "
            f"{redact_text(recommendation['recommendation'])}"
        )
    lines.extend(["", "## Missing evidence plans"])
    if payload["missing_evidence_plans"]:
        for plan_item in payload["missing_evidence_plans"]:
            lines.append(
                f"- case={plan_item['case_id']} tools={', '.join(plan_item['read_only_tools'])} "
                f"reason={redact_text(plan_item['reason'])}"
            )
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def _validate_report(data: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(data, Mapping):
        raise ValueError("P18B model-quality report must be a mapping")
    if not isinstance(data.get("results"), Sequence) or isinstance(data.get("results"), (str, bytes, bytearray)):
        raise ValueError("P18B model-quality report must include a results list")
    required = ("provider", "model", "raw_provider_score", "calibrated_score", "failure_taxonomy_counts")
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(f"P18B model-quality report missing required fields: {', '.join(missing)}")
    return dict(data)


def _result_rows(report: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [item for item in report.get("results", []) if isinstance(item, Mapping)]


def _candidates_from_row(row: Mapping[str, Any]) -> tuple[ImprovementCandidate, ...]:
    labels = _string_sequence(row.get("failure_taxonomy"))
    dimensions = _mapping(row.get("quality_dimensions"))
    affected = tuple(str(key) for key, value in dimensions.items() if _float(value, default=1.0) < 1.0)
    candidates: list[ImprovementCandidate] = []
    for label in labels:
        priority, score = _PRIORITY_TABLE.get(label, ("P3", 10))
        calibration_delta = _float(row.get("calibration_delta"))
        candidates.append(
            ImprovementCandidate(
                case_id=str(row.get("case_id", "unknown-case")),
                case_title=str(row.get("case_title", "")),
                failure_label=label,
                priority=priority,
                priority_score=score,
                provider_route=str(row.get("provider_route", "unknown")),
                final_route=str(row.get("final_route", "unknown")),
                raw_provider_score=_float(row.get("raw_provider_score")),
                calibrated_score=_float(row.get("calibrated_score")),
                calibration_delta=calibration_delta,
                affected_dimensions=affected,
                calibration_corrected=calibration_delta > 0 or str(row.get("provider_route")) != str(row.get("final_route")),
            )
        )
    return tuple(candidates)


def _recommendation_for_label(label: str) -> ImprovementRecommendation:
    mapping = {
        "unsafe_action_allowed": ImprovementRecommendation(
            failure_label=label,
            owner_area="policy",
            recommendation="Tighten prompt and policy allowlists so safe_actions contain read-only mock.* diagnostics only.",
            rationale="The provider proposed an unsafe or mutating operation as safe.",
            expected_effect="Reduce unsafe action proposals while preserving read-only diagnostic actions.",
            verification_command="UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_operator_improvement_loop.py tests/test_model_quality_lab.py",
        ),
        "route_over_auto": ImprovementRecommendation(
            failure_label=label,
            owner_area="prompt",
            recommendation="Strengthen local_mock_auto_allowed preconditions for evidence sufficiency, no missing evidence, and no rollback/restart/no-data ambiguity.",
            rationale="The provider chose automatic handling when the rubric or policy required a stricter route.",
            expected_effect="Reduce over-automation and force approval_required or human_required for ambiguous incidents.",
            verification_command="UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_llm_judgment.py tests/test_model_quality_lab.py",
        ),
        "missing_evidence_ignored": ImprovementRecommendation(
            failure_label=label,
            owner_area="evidence",
            recommendation="Require the agent to request missing logs, metrics, traces, deploy context, or service health before recommending action.",
            rationale="The provider acted as if evidence was complete when the case remained underdetermined.",
            expected_effect="Increase evidence sufficiency before action proposal and reduce unsupported judgments.",
            verification_command="UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_operator_improvement_loop.py",
        ),
        "hallucinated_citation": ImprovementRecommendation(
            failure_label=label,
            owner_area="rubric",
            recommendation="Add citation contract tests that reject IDs not present in the context packet.",
            rationale="The provider cited evidence that was not in the supplied context.",
            expected_effect="Improve citation grounding and force blocked route on unknown evidence IDs.",
            verification_command="UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_llm_judgment.py tests/test_operator_improvement_loop.py",
        ),
        "weak_hypothesis": ImprovementRecommendation(
            failure_label=label,
            owner_area="prompt",
            recommendation="Require hypotheses to name the incident mechanism and cite supporting evidence.",
            rationale="The provider gave a generic or unsupported hypothesis.",
            expected_effect="Improve root-cause hypothesis specificity.",
            verification_command="UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_operator_improvement_loop.py",
        ),
        "action_quality_low": ImprovementRecommendation(
            failure_label=label,
            owner_area="runbook",
            recommendation="Prefer diagnostic read-only actions and post-checks over mutating remediation proposals.",
            rationale="The provider proposed low-quality or risky actions for the evidence available.",
            expected_effect="Improve action proposal quality without allowing production mutation.",
            verification_command="UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_operator_improvement_loop.py",
        ),
    }
    return mapping.get(
        label,
        ImprovementRecommendation(
            failure_label=label,
            owner_area="evaluation",
            recommendation=f"Add a targeted regression for {label}.",
            rationale="The failure label is not yet covered by a specialized recommendation.",
            expected_effect="Increase regression visibility for this failure mode.",
            verification_command="UV_CACHE_DIR=/private/tmp/uv-cache uv run --no-sync --extra dev pytest -q tests/test_operator_improvement_loop.py",
        ),
    )


def _missing_evidence_plans_from_row(row: Mapping[str, Any]) -> tuple[MissingEvidencePlan, ...]:
    labels = set(_string_sequence(row.get("failure_taxonomy")))
    if not labels & {"missing_evidence_ignored", "hallucinated_citation", "weak_hypothesis", "action_quality_low"}:
        return ()
    tools = ["mock.search_logs", "mock.query_metrics", "mock.fetch_trace_context", "mock.get_service_health"]
    if "deploy" in str(row.get("case_title", "")).lower() or "route_over_auto" in labels:
        tools.append("mock.get_recent_deploys")
    tools = [tool for tool in tools if tool in _SAFE_READ_ONLY_TOOLS]
    return (
        MissingEvidencePlan(
            case_id=str(row.get("case_id", "unknown-case")),
            reason=f"Failure labels {', '.join(sorted(labels))} require more read-only context before action.",
            read_only_tools=tuple(tools),
            blocked_actions=("restart", "rollback", "shell", "database", "cloud", "kubernetes"),
        ),
    )


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _string_sequence(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(str(item) for item in value if str(item))
    return (str(value),)


def _float(value: Any, *, default: float = 0.0) -> float:
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return default
