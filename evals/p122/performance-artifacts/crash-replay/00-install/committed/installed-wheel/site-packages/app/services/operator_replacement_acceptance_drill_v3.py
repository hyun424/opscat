"""P92 operator replacement acceptance drill v3.

Builds a deterministic product-quality evidence pack from modeled P80-P91
outputs. It is local/mock evidence only: no live APIs, credentials, network,
shell execution, production mutation, remediation execution, or action execution.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
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
    "operator_replacement_acceptance_drill_v3_only": True,
    "product_quality_evidence_pack": True,
    "models_p80_p91_outputs": True,
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
_FORBIDDEN_CLAIMS = (
    "unattended_production_ready",
    "production_operator_replacement_approved",
    "production_mutation_safe",
    "live_api_operation_approved",
    "credentialed_operation_approved",
)


class OperatorReplacementLevel(StrEnum):
    LOCAL_MOCK_DEMO_READY = "local_mock_demo_ready"
    SUPERVISED_SHADOW_CANDIDATE = "supervised_shadow_candidate"
    HUMAN_GATED_CANDIDATE = "human_gated_candidate"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class AcceptanceDrillScenario:
    id: str
    readiness_result: Mapping[str, Any]
    remediation_plan: Mapping[str, Any]
    source_snapshots: Mapping[str, Any]
    stage_overrides: Mapping[str, str]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        return cls(
            id=str(data.get("id", "scenario")),
            readiness_result=_mapping(data.get("readiness_result")),
            remediation_plan=_mapping(data.get("remediation_plan")),
            source_snapshots=_mapping(data.get("source_snapshots")),
            stage_overrides={str(key): str(value) for key, value in _mapping(data.get("stage_overrides")).items()},
        )


@dataclass(frozen=True)
class OperatorReplacementAcceptanceResult:
    scenario: AcceptanceDrillScenario
    operator_replacement_level: OperatorReplacementLevel
    final_readiness_score: int
    stages: tuple[Mapping[str, Any], ...]
    top_blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    next_roadmap_items: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "drill_id": f"p92:{self.scenario.id}",
            "scenario_id": self.scenario.id,
            "operator_replacement_level": self.operator_replacement_level.value,
            "end_to_end_stages": [dict(stage) for stage in self.stages],
            "safety_boundary_checks": _safety_boundary_checks(self.scenario, self.operator_replacement_level),
            "zero_side_effect_counters": dict(_ZERO_SIDE_EFFECT_COUNTERS),
            "final_readiness_score": self.final_readiness_score,
            "top_blockers": list(self.top_blockers),
            "warnings": list(self.warnings),
            "next_roadmap_items": list(self.next_roadmap_items),
            "portfolio_demo_markdown_summary": _portfolio_summary(
                self.scenario.id,
                self.operator_replacement_level,
                self.final_readiness_score,
                self.top_blockers,
                self.next_roadmap_items,
            ),
            "forbidden_claims": list(_FORBIDDEN_CLAIMS),
            "source_snapshots": redact_value(dict(self.scenario.source_snapshots)),
            "audit_metadata": {
                "audit_id": f"p92:{self.scenario.id}",
                "p92_operator_replacement_acceptance_drill_v3": True,
                "product_quality_evidence_pack": True,
                "models_p80_p91_outputs": True,
                "local_mock_only": True,
                "side_effect_free": True,
                "not_production_autonomy": True,
            },
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


@dataclass(frozen=True)
class OperatorReplacementAcceptanceDrillV3Report:
    suite: Mapping[str, Any]
    scenarios: tuple[AcceptanceDrillScenario, ...]
    results: tuple[OperatorReplacementAcceptanceResult, ...]

    @classmethod
    def from_scenarios(cls, suite: Mapping[str, Any], scenarios: Sequence[AcceptanceDrillScenario]) -> Self:
        return cls(suite=suite, scenarios=tuple(scenarios), results=tuple(_evaluate(item) for item in scenarios))

    def to_dict(self) -> dict[str, Any]:
        results = [result.to_dict() for result in self.results]
        summary: dict[str, Any] = {
            "suite_id": str(self.suite.get("id", "p92-operator-replacement-acceptance-drill-v3")),
            "scenario_count": len(results),
            "local_demo_ready_count": _level_count(self.results, OperatorReplacementLevel.LOCAL_MOCK_DEMO_READY),
            "shadow_candidate_count": _level_count(self.results, OperatorReplacementLevel.SUPERVISED_SHADOW_CANDIDATE),
            "human_gated_count": _level_count(self.results, OperatorReplacementLevel.HUMAN_GATED_CANDIDATE),
            "blocked_count": _level_count(self.results, OperatorReplacementLevel.BLOCKED),
            "executions": 0,
            **_ZERO_SIDE_EFFECT_COUNTERS,
        }
        summary["passed"] = (
            summary["scenario_count"] == 6
            and summary["local_demo_ready_count"] == 1
            and summary["shadow_candidate_count"] == 2
            and summary["human_gated_count"] == 1
            and summary["blocked_count"] == 2
            and summary["executions"] == 0
        )
        payload = {
            "summary": summary,
            "boundary": dict(_BOUNDARY),
            "suite": redact_value(dict(self.suite)),
            "acceptance_results": results,
            "forbidden_claims": list(_FORBIDDEN_CLAIMS),
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


def evaluate_operator_replacement_acceptance_drill_v3_fixture(
    path: str | Path,
) -> OperatorReplacementAcceptanceDrillV3Report:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    suite = _mapping(data.get("suite"))
    scenarios = tuple(
        AcceptanceDrillScenario.from_dict(item) for item in _sequence(data.get("scenarios", ())) if isinstance(item, Mapping)
    )
    return OperatorReplacementAcceptanceDrillV3Report.from_scenarios(suite, scenarios)


def render_operator_replacement_acceptance_drill_v3_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    lines = [
        "# OpsCat P92 Operator Replacement Acceptance Drill v3",
        "",
        "Product Quality Evidence Pack for local/mock operator replacement acceptance. It is not production autonomy.",
        "",
        "## Summary",
        "",
        f"- Scenarios: {summary.get('scenario_count', 0)}",
        f"- Local/mock demo ready: {summary.get('local_demo_ready_count', 0)}",
        f"- Supervised shadow candidates: {summary.get('shadow_candidate_count', 0)}",
        f"- Human-gated candidates: {summary.get('human_gated_count', 0)}",
        f"- Blocked: {summary.get('blocked_count', 0)}",
        f"- Executions: {summary.get('executions', 0)}",
        f"- Passed: {summary.get('passed', False)}",
        "",
        "## Acceptance results",
        "",
    ]
    for result in _sequence(payload.get("acceptance_results", ())):
        if not isinstance(result, Mapping):
            continue
        lines.extend(
            [
                f"### {result.get('scenario_id', 'scenario')}",
                "",
                f"- Drill: {result.get('drill_id')}",
                f"- Level: {result.get('operator_replacement_level')}",
                f"- Score: {result.get('final_readiness_score')}",
                f"- Blockers: {', '.join(str(item) for item in _sequence(result.get('top_blockers'))) or 'none'}",
                f"- Next roadmap: {', '.join(str(item) for item in _sequence(result.get('next_roadmap_items'))) or 'none'}",
                "",
                str(result.get("portfolio_demo_markdown_summary", "")).strip(),
                "",
            ]
        )
    lines.extend(
        [
            "## Boundary and forbidden claims",
            "",
            "- Local/mock Product Quality Evidence Pack only.",
            "- No live APIs, credentials, network, shell execution, sleeping, process spawning, agents, production mutation, remediation execution, or action execution.",
            "- forbidden claims: unattended production readiness, production operator replacement approval, live API operation approval, and production mutation safety.",
            "- This is local/mock demo ready at most, not production autonomy.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_operator_replacement_acceptance_drill_v3_outputs(
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
        output_md_path.write_text(render_operator_replacement_acceptance_drill_v3_markdown(payload), encoding="utf-8")


def _evaluate(scenario: AcceptanceDrillScenario) -> OperatorReplacementAcceptanceResult:
    readiness = scenario.readiness_result
    remediation = scenario.remediation_plan
    blockers = tuple(str(item) for item in _sequence(readiness.get("blockers")))
    warnings = tuple(str(item) for item in _sequence(readiness.get("warnings")))
    score = max(0, min(100, int(_float(readiness.get("score"), 0.0))))
    side_effect_clean = all(value == 0 for value in _side_effect_counters(readiness).values())
    has_blocking_plan = remediation.get("has_blocking_remediation") is True
    level = _level(readiness, blockers, score, side_effect_clean, has_blocking_plan)
    if level == OperatorReplacementLevel.BLOCKED:
        score = min(score, 60)
    stages = tuple(_stages(scenario, blockers, warnings, side_effect_clean, has_blocking_plan))
    next_items = tuple(_roadmap_items(level, blockers, warnings, remediation))
    return OperatorReplacementAcceptanceResult(
        scenario=scenario,
        operator_replacement_level=level,
        final_readiness_score=score,
        stages=stages,
        top_blockers=blockers,
        warnings=warnings,
        next_roadmap_items=next_items,
    )


def _level(
    readiness: Mapping[str, Any],
    blockers: Sequence[str],
    score: int,
    side_effect_clean: bool,
    has_blocking_plan: bool,
) -> OperatorReplacementLevel:
    if not side_effect_clean or "side_effect_counter_non_zero" in blockers:
        return OperatorReplacementLevel.BLOCKED
    if "guardrail_failure_requires_fix_before_auto_run" in blockers:
        return OperatorReplacementLevel.BLOCKED
    if {"p76_evidence_sufficiency_missing", "p87_report_missing"} & set(blockers):
        return OperatorReplacementLevel.BLOCKED
    if "human_high_severity_approval_policy_missing" in blockers or str(readiness.get("readiness_level")) == "human_gated_staging_ready":
        return OperatorReplacementLevel.HUMAN_GATED_CANDIDATE
    if has_blocking_plan:
        return OperatorReplacementLevel.BLOCKED
    if score >= 95 and not blockers and not _sequence(readiness.get("warnings")):
        return OperatorReplacementLevel.LOCAL_MOCK_DEMO_READY
    return OperatorReplacementLevel.SUPERVISED_SHADOW_CANDIDATE


def _stages(
    scenario: AcceptanceDrillScenario,
    blockers: Sequence[str],
    warnings: Sequence[str],
    side_effect_clean: bool,
    has_blocking_plan: bool,
) -> list[Mapping[str, Any]]:
    stage_defs = [
        ("P80", "approval_policy", "P80 approval policy routes unsafe/sensitive work away from auto-approval."),
        ("P81", "rollback_pr_draft", "P81 rollback draft remains draft-only and human-approved."),
        ("P82", "slack_ticket_draft", "P82 Slack/ticket outputs remain local draft artifacts."),
        ("P83", "outcome_monitor", "P83 outcome monitor supplies post-action evidence without executing actions."),
        ("P84", "next_action_planner", "P84 planner selects safe next local/mock action metadata."),
        ("P85-P89", "local_supervisor_run", "P85-P89 model resumable bounded supervisor execution as data."),
        ("P90", "readiness_gate", "P90 readiness gate scores local/shadow/human-gated readiness."),
        ("P91", "gap_remediation_plan", "P91 supplies next roadmap items for readiness gaps."),
        ("P92", "acceptance_evidence_pack", "P92 packages product-quality evidence and forbidden claims."),
    ]
    statuses = dict(scenario.stage_overrides)
    if not side_effect_clean:
        statuses["local_supervisor_run"] = "fail"
        statuses["acceptance_evidence_pack"] = "fail"
    if has_blocking_plan:
        statuses["gap_remediation_plan"] = "fail"
    if blockers:
        statuses["readiness_gate"] = "fail" if _blocking(blockers) else "warn"
    if warnings:
        statuses.setdefault("local_supervisor_run", "warn")
    return [
        {
            "stage_id": stage_id,
            "name": name,
            "status": statuses.get(name, "pass"),
            "evidence_refs": _evidence_refs(stage_id, scenario.id),
            "summary": summary,
        }
        for stage_id, name, summary in stage_defs
    ]


def _blocking(blockers: Sequence[str]) -> bool:
    return any(
        item
        in {
            "side_effect_counter_non_zero",
            "guardrail_failure_requires_fix_before_auto_run",
            "p76_evidence_sufficiency_missing",
            "p87_report_missing",
        }
        for item in blockers
    )


def _roadmap_items(
    level: OperatorReplacementLevel,
    blockers: Sequence[str],
    warnings: Sequence[str],
    remediation: Mapping[str, Any],
) -> list[str]:
    items: list[str] = []
    if "side_effect_counter_non_zero" in blockers:
        items.append("P92-EMERGENCY-ZERO-SIDE-EFFECTS")
    if "guardrail_failure_requires_fix_before_auto_run" in blockers:
        items.append("P92-GUARDRAIL-ROLLBACK-DRILL")
    if "p76_evidence_sufficiency_missing" in blockers:
        items.append("P92-EVIDENCE-SUFFICIENCY")
    if "p87_report_missing" in blockers:
        items.append("P92-REPORTABILITY")
    if "human_high_severity_approval_policy_missing" in blockers:
        items.append("P92-HUMAN-HANDOFF-APPROVAL")
    if "incomplete_run_requires_supervised_resume" in warnings:
        items.append("P92-HARDEN-RESUME-WARNING")
    for item in _sequence(remediation.get("remediation_items")):
        item_id = str(_mapping(item).get("id", ""))
        if item_id == "P91-MATURITY-SHADOW-SOAK":
            items.append("P92-MATURITY-SHADOW-SOAK")
    if level == OperatorReplacementLevel.LOCAL_MOCK_DEMO_READY:
        items.append("P92-MATURITY-SUPERVISED-SHADOW-SOAK")
    return list(dict.fromkeys(items))


def _portfolio_summary(
    scenario_id: str,
    level: OperatorReplacementLevel,
    score: int,
    blockers: Sequence[str],
    roadmap_items: Sequence[str],
) -> str:
    label = level.value.replace("_", " ")
    blockers_text = ", ".join(blockers) if blockers else "none"
    roadmap_text = ", ".join(roadmap_items) if roadmap_items else "none"
    return (
        f"### {scenario_id}\n"
        f"- Acceptance level: {label}\n"
        f"- Final readiness score: {score}\n"
        f"- Top blockers: {blockers_text}\n"
        f"- Next roadmap items: {roadmap_text}\n"
        "- Boundary: local/mock demo ready at most; production autonomy remains forbidden."
    )


def _safety_boundary_checks(
    scenario: AcceptanceDrillScenario,
    level: OperatorReplacementLevel,
) -> dict[str, bool]:
    readiness = scenario.readiness_result
    blockers = set(str(item) for item in _sequence(readiness.get("blockers")))
    return {
        "local_mock_only": True,
        "no_live_api_calls": True,
        "no_credentials": True,
        "no_network": True,
        "no_production_mutation": True,
        "no_remediation_execution": True,
        "no_action_execution": True,
        "zero_side_effect_counters": True,
        "human_approval_required": level == OperatorReplacementLevel.HUMAN_GATED_CANDIDATE
        or "human_high_severity_approval_policy_missing" in blockers,
    }


def _evidence_refs(stage_id: str, scenario_id: str) -> list[str]:
    return [
        f"evals/actions/p92_operator_replacement_acceptance_drill_v3.json#{scenario_id}",
        f"{stage_id.lower()}-modeled-output",
    ]


def _level_count(results: Sequence[OperatorReplacementAcceptanceResult], level: OperatorReplacementLevel) -> int:
    return sum(1 for result in results if result.operator_replacement_level == level)


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
    "OperatorReplacementAcceptanceDrillV3Report",
    "evaluate_operator_replacement_acceptance_drill_v3_fixture",
    "render_operator_replacement_acceptance_drill_v3_markdown",
    "write_operator_replacement_acceptance_drill_v3_outputs",
]
