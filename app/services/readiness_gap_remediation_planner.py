"""P91 readiness gap remediation planner.

Turns P90 readiness blockers into a prioritized local/mock remediation backlog.
It is a roadmap/planning artifact only: no live APIs, credentials, network,
shell execution, production mutation, remediation execution, or action execution.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self

from app.services.redaction import redact_value

_ZERO_SIDE_EFFECT_COUNTERS: dict[str, int] = {
    "action_execution_count": 0,
    "live_api_call_count": 0,
    "credential_read_count": 0,
    "network_call_count": 0,
    "production_mutation_count": 0,
    "shell_execution_count": 0,
    "process_spawn_count": 0,
    "agent_spawn_count": 0,
    "sleep_call_count": 0,
}
_BOUNDARY: dict[str, bool] = {
    "local_mock_only": True,
    "readiness_gap_remediation_planner_only": True,
    "models_p90_readiness_result": True,
    "live_api_calls_enabled": False,
    "credential_access_enabled": False,
    "network_calls_enabled": False,
    "production_mutation_enabled": False,
    "remediation_execution_enabled": False,
    "shell_execution_enabled": False,
    "action_execution_enabled": False,
    "process_spawn_enabled": False,
    "agent_spawn_enabled": False,
    "sleep_enabled": False,
    "default_external_model_calls": False,
    "production_autonomy_claimed": False,
}
_DEFAULT_FORBIDDEN_CLAIMS = (
    "unattended_production_ready",
    "operator_replacement_approved",
    "production_mutation_safe",
    "live_api_operation_approved",
)


@dataclass(frozen=True)
class P90ReadinessSnapshot:
    scenario_id: str
    readiness_id: str
    readiness_level: str
    score: int
    component_scores: Mapping[str, int]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    allowed_operating_mode: str
    forbidden_claims: tuple[str, ...]
    zero_side_effect_counters: Mapping[str, int]
    human_severity: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        scenario_id = str(data.get("scenario_id", "scenario"))
        forbidden = tuple(str(item) for item in _sequence(data.get("forbidden_claims"))) or _DEFAULT_FORBIDDEN_CLAIMS
        return cls(
            scenario_id=scenario_id,
            readiness_id=str(data.get("readiness_id", f"p90:{scenario_id}")),
            readiness_level=str(data.get("readiness_level", "not_ready")),
            score=int(_float(data.get("score"), 0.0)),
            component_scores={
                str(key): int(_float(value)) for key, value in _mapping(data.get("component_scores")).items()
            },
            blockers=tuple(str(item) for item in _sequence(data.get("blockers"))),
            warnings=tuple(str(item) for item in _sequence(data.get("warnings"))),
            allowed_operating_mode=str(data.get("allowed_operating_mode", "no_auto_run")),
            forbidden_claims=forbidden,
            zero_side_effect_counters=_side_effect_counters(data),
            human_severity=str(data.get("human_severity", "none")).lower(),
        )


@dataclass(frozen=True)
class ReadinessGapRemediationPlan:
    source: P90ReadinessSnapshot
    remediation_items: tuple[Mapping[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        human_gated = [str(item["id"]) for item in self.remediation_items if item.get("human_gated")]
        blocking = any(item.get("blocking") is True for item in self.remediation_items)
        payload = {
            "plan_id": f"p91:{self.source.scenario_id}",
            "source_readiness_id": self.source.readiness_id,
            "source_scenario_id": self.source.scenario_id,
            "source_readiness_level": self.source.readiness_level,
            "source_score": self.source.score,
            "source_allowed_operating_mode": self.source.allowed_operating_mode,
            "has_blocking_remediation": blocking,
            "remediation_items": [dict(item) for item in self.remediation_items],
            "claims_remain_forbidden_until_resolved": list(
                dict.fromkeys([*self.source.forbidden_claims, *self.source.blockers])
            ),
            "blocked_human_gated_items": human_gated,
            "audit_metadata": {
                "audit_id": f"p91:{self.source.scenario_id}",
                "p91_readiness_gap_remediation_planner": True,
                "source_is_p90_readiness_result": True,
                "local_mock_only": True,
                "roadmap_planning_artifact": True,
                "side_effect_free": all(value == 0 for value in _ZERO_SIDE_EFFECT_COUNTERS.values()),
                "not_production_autonomy": True,
            },
            "zero_side_effect_counters": dict(_ZERO_SIDE_EFFECT_COUNTERS),
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


@dataclass(frozen=True)
class ReadinessGapRemediationPlannerReport:
    suite: Mapping[str, Any]
    snapshots: tuple[P90ReadinessSnapshot, ...]
    plans: tuple[ReadinessGapRemediationPlan, ...]

    @classmethod
    def from_snapshots(cls, suite: Mapping[str, Any], snapshots: Sequence[P90ReadinessSnapshot]) -> Self:
        plans = tuple(ReadinessGapRemediationPlan(source=item, remediation_items=tuple(_plan_items(item))) for item in snapshots)
        return cls(suite=suite, snapshots=tuple(snapshots), plans=plans)

    def to_dict(self) -> dict[str, Any]:
        plans = [plan.to_dict() for plan in self.plans]
        summary: dict[str, Any] = {
            "suite_id": str(self.suite.get("id", "p91-readiness-gap-remediation-planner")),
            "scenario_count": len(plans),
            "blocking_plans": sum(1 for plan in plans if plan["has_blocking_remediation"]),
            "emergency_items": _item_count(plans, "emergency"),
            "human_gated_items": sum(
                1 for plan in plans for item in _sequence(plan.get("remediation_items")) if _mapping(item).get("human_gated")
            ),
            "maturity_items": _item_count(plans, "maturity"),
            "executions": 0,
            **_ZERO_SIDE_EFFECT_COUNTERS,
        }
        summary["passed"] = (
            summary["scenario_count"] >= 6
            and summary["blocking_plans"] >= 4
            and summary["emergency_items"] >= 1
            and summary["human_gated_items"] >= 1
            and summary["maturity_items"] >= 2
            and summary["executions"] == 0
        )
        payload = {
            "summary": summary,
            "boundary": dict(_BOUNDARY),
            "suite": redact_value(dict(self.suite)),
            "remediation_plans": plans,
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


def evaluate_readiness_gap_remediation_planner_fixture(path: str | Path) -> ReadinessGapRemediationPlannerReport:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    suite = _mapping(data.get("suite"))
    snapshots = tuple(
        P90ReadinessSnapshot.from_dict(item)
        for item in _sequence(data.get("readiness_results", ()))
        if isinstance(item, Mapping)
    )
    return ReadinessGapRemediationPlannerReport.from_snapshots(suite, snapshots)


def render_readiness_gap_remediation_planner_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    lines = [
        "# OpsCat P91 Readiness Gap Remediation Planner",
        "",
        (
            "P91 converts P90 readiness blockers into a prioritized remediation backlog. "
            "It is a roadmap/planning artifact, not production autonomy."
        ),
        "",
        "## Summary",
        "",
        f"- Scenarios: {summary.get('scenario_count', 0)}",
        f"- Blocking plans: {summary.get('blocking_plans', 0)}",
        f"- Emergency items: {summary.get('emergency_items', 0)}",
        f"- Human-gated items: {summary.get('human_gated_items', 0)}",
        f"- Maturity items: {summary.get('maturity_items', 0)}",
        f"- Executions: {summary.get('executions', 0)}",
        f"- Passed: {summary.get('passed', False)}",
        "",
        "## Remediation plans",
        "",
    ]
    for plan in _sequence(payload.get("remediation_plans", ())):
        if not isinstance(plan, Mapping):
            continue
        lines.extend(
            [
                f"### {plan.get('source_scenario_id', 'scenario')}",
                "",
                f"- Plan: {plan.get('plan_id')}",
                f"- Source readiness: {plan.get('source_readiness_id')}",
                f"- Blocking remediation: {plan.get('has_blocking_remediation')}",
                f"- Forbidden claims: {', '.join(str(item) for item in _sequence(plan.get('claims_remain_forbidden_until_resolved'))) or 'none'}",
                "",
            ]
        )
        for item in _sequence(plan.get("remediation_items")):
            if not isinstance(item, Mapping):
                continue
            lines.append(
                f"- {item.get('id')}: {item.get('severity')} / {item.get('owner_lane')} / "
                f"next mode {item.get('next_safe_operating_mode')}"
            )
        lines.append("")
    lines.extend(
        [
            "## Boundary",
            "",
            "- Local/mock planning only.",
            "- Consumes modeled P90 readiness results with blockers, gates, scores, operating mode, and forbidden claims.",
            "- No live APIs, credentials, network, shell execution, sleeping, process spawning, agents, actions, remediation execution, or production mutation.",
            "- This is a roadmap/planning artifact, not production autonomy or unattended production approval.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_readiness_gap_remediation_planner_outputs(
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
        output_md_path.write_text(render_readiness_gap_remediation_planner_markdown(payload), encoding="utf-8")


def _plan_items(source: P90ReadinessSnapshot) -> list[Mapping[str, Any]]:
    items: list[Mapping[str, Any]] = []
    blockers = set(source.blockers)
    if "side_effect_counter_non_zero" in blockers:
        items.append(_side_effect_item(source))
    if "guardrail_failure_requires_fix_before_auto_run" in blockers:
        items.append(_guardrail_item())
    if "p76_evidence_sufficiency_missing" in blockers:
        items.append(_evidence_item())
    if "p87_report_missing" in blockers:
        items.append(_reportability_item())
    if "human_high_severity_approval_policy_missing" in blockers or source.human_severity == "high":
        items.append(_human_handoff_item())
    if "incomplete_run_requires_supervised_resume" in source.warnings:
        items.append(_resume_hardening_item())
    if not items or source.readiness_level == "local_dry_run_ready":
        items.append(_maturity_item(source))
    return _sort_items(items)


def _side_effect_item(source: P90ReadinessSnapshot) -> Mapping[str, Any]:
    non_zero = [f"{key}={value}" for key, value in source.zero_side_effect_counters.items() if value]
    return _item(
        "P91-EMERGENCY-ZERO-SIDE-EFFECTS",
        "emergency",
        35,
        ["tests/test_safe_auto_run_readiness_gate.py::test_any_side_effect_counter_blocks_readiness"],
        "safety",
        [],
        f"Nonzero side-effect counter detected: {', '.join(non_zero) or 'unknown counter'}",
        "All P90 side-effect counters are zero in fixture and regression tests.",
        "no_auto_run",
        blocking=True,
    )


def _guardrail_item() -> Mapping[str, Any]:
    return _item(
        "P91-GUARDRAIL-ROLLBACK-DRILL",
        "high",
        25,
        [
            "tests/test_safe_auto_run_readiness_gate.py::test_failed_guardrail_blocks_auto_run_readiness",
            "rollback drill regression fixture",
        ],
        "failure-handling",
        [],
        "Failed guardrail means failure handling and rollback proof are not trusted.",
        "Guardrail failure fixture produces failure report plus rollback drill pass evidence.",
        "no_auto_run",
        blocking=True,
    )


def _evidence_item() -> Mapping[str, Any]:
    return _item(
        "P91-EVIDENCE-SUFFICIENCY",
        "high",
        16,
        ["p76_evidence_sufficiency_missing", "tests/test_evidence_sufficiency_gate_v2.py"],
        "evidence",
        [],
        "P90 cannot justify readiness without sufficient prior evidence.",
        "P76 evidence sufficiency gate passes and P90 evidence component is nonzero.",
        "no_auto_run",
        blocking=True,
    )


def _reportability_item() -> Mapping[str, Any]:
    return _item(
        "P91-REPORTABILITY",
        "medium",
        12,
        ["p87_report_missing", "tests/test_supervisor_run_report_artifact.py"],
        "evidence",
        ["P91-EVIDENCE-SUFFICIENCY"],
        "Operators cannot upgrade mode without a durable report artifact.",
        "P87 report artifact exists and P90 reportability component is nonzero.",
        "no_auto_run",
        blocking=True,
    )


def _human_handoff_item() -> Mapping[str, Any]:
    return _item(
        "P91-HUMAN-HANDOFF-APPROVAL",
        "high",
        18,
        ["human_review_required_before_continue", "approval policy handoff fixture"],
        "human-ops",
        [],
        "High-severity human handoff requires explicit approval policy before any upgrade.",
        "Human approval policy fixture proves high-severity handoff remains human-gated.",
        "human_gated_staging_dry_run",
        blocking=True,
        human_gated=True,
    )


def _resume_hardening_item() -> Mapping[str, Any]:
    return _item(
        "P91-HARDEN-RESUME-WARNING",
        "low",
        6,
        ["incomplete_run_requires_supervised_resume", "resumable supervisor regression"],
        "platform",
        [],
        "Minor resume warning should stay supervised until duplicate protection is re-proven.",
        "Resumable run fixture shows no duplicate item execution and safe supervised resume.",
        "local_dry_run_only",
    )


def _maturity_item(source: P90ReadinessSnapshot) -> Mapping[str, Any]:
    next_mode = "supervised_shadow_only" if source.readiness_level == "local_dry_run_ready" else source.allowed_operating_mode
    return _item(
        "P91-MATURITY-SHADOW-SOAK",
        "maturity",
        8,
        ["long_duration_local_soak_evidence", "supervised shadow readiness smoke"],
        "maturity",
        [],
        "Readiness is clean enough for the next local/shadow maturity evidence step, not production autonomy.",
        "Shadow soak plan has bounded duration, operator review, and zero side-effect counters.",
        next_mode,
    )


def _item(
    item_id: str,
    severity: str,
    expected_readiness_lift: int,
    required_evidence_tests: Sequence[str],
    owner_lane: str,
    dependency_ids: Sequence[str],
    risk: str,
    stop_condition: str,
    next_safe_operating_mode: str,
    *,
    blocking: bool = False,
    human_gated: bool = False,
) -> Mapping[str, Any]:
    return {
        "id": item_id,
        "severity": severity,
        "expected_readiness_lift": expected_readiness_lift,
        "required_evidence_tests": list(required_evidence_tests),
        "owner_lane": owner_lane,
        "dependency_ids": list(dependency_ids),
        "risk": risk,
        "stop_condition": stop_condition,
        "next_safe_operating_mode": next_safe_operating_mode,
        "blocking": blocking,
        "human_gated": human_gated,
    }


def _sort_items(items: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    order = {"emergency": 0, "high": 1, "medium": 2, "low": 3, "maturity": 4}
    return sorted(items, key=lambda item: (order.get(str(item.get("severity")), 99), str(item.get("id"))))


def _item_count(plans: Sequence[Mapping[str, Any]], severity: str) -> int:
    return sum(
        1
        for plan in plans
        for item in _sequence(plan.get("remediation_items"))
        if _mapping(item).get("severity") == severity
    )


def _side_effect_counters(data: Mapping[str, Any]) -> dict[str, int]:
    raw = _mapping(data.get("zero_side_effect_counters"))
    return {key: max(0, int(_float(raw.get(key), 0.0))) for key in _ZERO_SIDE_EFFECT_COUNTERS}


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


__all__ = [
    "ReadinessGapRemediationPlannerReport",
    "evaluate_readiness_gap_remediation_planner_fixture",
    "render_readiness_gap_remediation_planner_markdown",
    "write_readiness_gap_remediation_planner_outputs",
]
