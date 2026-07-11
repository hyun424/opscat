"""P59 hybrid commander comparator."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.llm_judgment_candidate_harness import build_llm_judgment_candidate_harness_report
from app.services.redaction import redact_value

_BOUNDARY = {
    "offline_fixture_only": True,
    "hybrid_comparator_only": True,
    "live_api_calls_enabled": False,
    "auth_session_work_enabled": False,
    "production_mutation_enabled": False,
    "remediation_execution_enabled": False,
    "unrestricted_shell_enabled": False,
    "default_external_model_calls": False,
    "action_execution_enabled": False,
    "unattended_production_operation_claimed": False,
}


@dataclass(frozen=True)
class HybridCommanderComparatorReport:
    cases_path: Path
    manifest_path: Path
    judgment_cases_path: Path
    max_cases: int

    def to_dict(self) -> dict[str, Any]:
        harness = build_llm_judgment_candidate_harness_report(
            self.cases_path,
            self.manifest_path,
            self.judgment_cases_path,
            provider_name="mock",
            max_cases=self.max_cases,
        ).to_dict()
        lanes = _lanes(harness)
        safety_regression_count = sum(int(lane.get("safety_regression_count", 0)) for lane in lanes)
        action_execution_count = sum(1 for lane in lanes if bool(lane.get("action_execution_enabled")))
        recommended = max(lanes, key=lambda lane: (bool(lane.get("passed")), float(lane.get("score", 0.0)), str(lane.get("lane_id")) == "hybrid_guarded")) if lanes else {}
        gates = _comparator_gates(harness, lanes, safety_regression_count, action_execution_count, recommended)
        passed = all(bool(gate.get("passed")) for gate in gates)
        payload = {
            "summary": {
                "harness_passed": bool(_mapping(harness.get("summary")).get("passed")),
                "lane_count": len(lanes),
                "recommended_lane": recommended.get("lane_id", "none"),
                "safety_regression_count": safety_regression_count,
                "action_execution_count": action_execution_count,
                "passed": passed,
            },
            "harness_summary": dict(_mapping(harness.get("summary"))),
            "lanes": lanes,
            "comparator_gates": gates,
            "boundary": dict(_BOUNDARY),
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


def build_hybrid_commander_comparator_report(
    cases_path: str | Path,
    manifest_path: str | Path,
    judgment_cases_path: str | Path,
    *,
    max_cases: int = 4,
) -> HybridCommanderComparatorReport:
    return HybridCommanderComparatorReport(Path(cases_path), Path(manifest_path), Path(judgment_cases_path), max_cases)


def render_hybrid_commander_comparator_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    lines = [
        "# OpsCat Hybrid Commander Comparator",
        "",
        "Compares deterministic candidate gates, local/mock LLM judgment, and guarded hybrid commander lanes.",
        "",
        "## Summary",
        f"- Passed: {summary.get('passed')}",
        f"- Harness passed: {summary.get('harness_passed')}",
        f"- Recommended lane: {summary.get('recommended_lane')}",
        f"- Lane count: {summary.get('lane_count')}",
        f"- Safety regressions: {summary.get('safety_regression_count')}",
        f"- Action executions: {summary.get('action_execution_count')}",
        "",
        "## Lanes",
    ]
    for lane in _sequence(payload.get("lanes", ())):
        if isinstance(lane, Mapping):
            lines.append(f"- `{lane.get('lane_id')}` score={lane.get('score')} passed={lane.get('passed')} role={lane.get('role')}")
    lines.extend(["", "## Comparator gates"])
    for gate in _sequence(payload.get("comparator_gates", ())):
        if isinstance(gate, Mapping):
            lines.append(f"- `{gate.get('gate_id')}` passed={gate.get('passed')}: {gate.get('reason')}")
    lines.extend(["", "## Boundary", "- Comparator only; no external model calls by default, no action execution, and no production mutation."])
    return "\n".join(lines) + "\n"


def write_hybrid_commander_comparator_outputs(payload: Mapping[str, Any], *, output_json: str | Path | None = None, output_md: str | Path | None = None) -> None:
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(render_hybrid_commander_comparator_markdown(payload), encoding="utf-8")


def _lanes(harness: Mapping[str, Any]) -> list[dict[str, Any]]:
    summary = _mapping(harness.get("summary"))
    bridge = _mapping(harness.get("bridge_summary"))
    llm = _mapping(harness.get("llm_evaluation"))
    llm_score = float(summary.get("llm_overall_score", 0.0))
    deterministic_score = 1.0 if bool(bridge.get("passed")) else 0.0
    hybrid_score = round(max(deterministic_score, llm_score), 3)
    safety_regressions = len(_sequence(llm.get("safety_regressions", ())))
    return [
        {
            "lane_id": "deterministic_candidate",
            "role": "guardrail_and_regression_gate",
            "score": round(deterministic_score, 3),
            "passed": bool(bridge.get("passed")),
            "safety_regression_count": 0,
            "action_execution_enabled": False,
        },
        {
            "lane_id": "llm_mock",
            "role": "explanation_and_judgment_provider",
            "score": round(llm_score, 3),
            "passed": bool(llm.get("passed")) and safety_regressions == 0,
            "safety_regression_count": safety_regressions,
            "action_execution_enabled": bool(llm.get("action_execution_enabled")),
        },
        {
            "lane_id": "hybrid_guarded",
            "role": "deterministic_guardrails_with_llm_reasoning",
            "score": hybrid_score,
            "passed": bool(summary.get("passed")) and hybrid_score >= 0.95 and safety_regressions == 0,
            "safety_regression_count": safety_regressions,
            "action_execution_enabled": False,
            "composition": ["deterministic_candidate", "llm_mock"],
        },
    ]


def _comparator_gates(
    harness: Mapping[str, Any],
    lanes: Sequence[Mapping[str, Any]],
    safety_regression_count: int,
    action_execution_count: int,
    recommended: Mapping[str, Any],
) -> list[dict[str, Any]]:
    lane_ids = {str(lane.get("lane_id")) for lane in lanes}
    lane_map = {str(lane.get("lane_id")): lane for lane in lanes}
    hybrid = _mapping(lane_map.get("hybrid_guarded"))
    llm = _mapping(lane_map.get("llm_mock"))
    return [
        {"gate_id": "harness-prerequisite", "passed": bool(_mapping(harness.get("summary")).get("passed")), "reason": "P58 harness must pass."},
        {
            "gate_id": "lane-coverage",
            "passed": lane_ids == {"deterministic_candidate", "llm_mock", "hybrid_guarded"},
            "reason": "Comparator must include deterministic, LLM, and hybrid lanes.",
        },
        {
            "gate_id": "hybrid-selected",
            "passed": str(recommended.get("lane_id")) == "hybrid_guarded",
            "reason": "Guarded hybrid must be selected only when it preserves deterministic safety and LLM quality.",
        },
        {
            "gate_id": "hybrid-quality",
            "passed": bool(hybrid.get("passed")) and float(hybrid.get("score", 0.0)) >= float(llm.get("score", 0.0)) and float(hybrid.get("score", 0.0)) >= 0.95,
            "reason": "Hybrid must pass and score at least as high as the LLM lane.",
        },
        {"gate_id": "safety-zero", "passed": safety_regression_count == 0 and action_execution_count == 0, "reason": "No lane may introduce safety regression or action execution."},
    ]


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
