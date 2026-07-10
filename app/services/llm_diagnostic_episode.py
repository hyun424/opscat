"""P103 bounded, history-aware LLM diagnostic episodes."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.causal_remediation_benchmark import CausalScenario, IsolatedFaultLab
from app.services.llm_tool_planner_evaluation import LLMToolPlanner, ToolPlanningProvider
from app.services.operational_scenario_catalog import build_comprehensive_operational_catalog
from app.services.redaction import redact_value
from app.services.tool_using_hypothesis_investigator import (
    HypothesisToolAgent,
    InvestigationDecision,
    ToolInvestigationBenchmark,
    expected_diagnostic_tool,
)


class LLMDiagnosticEpisodeAgent(HypothesisToolAgent):
    """Adapt strict LLM tool plans to P101's evidence/action boundary."""

    def __init__(self, provider: ToolPlanningProvider, *, max_tool_calls: int = 3) -> None:
        if max_tool_calls < 1 or max_tool_calls > 10:
            raise ValueError("max_tool_calls must be between 1 and 10")
        super().__init__(max_tool_calls=max_tool_calls)
        self.provider = provider
        self.max_tool_calls = max_tool_calls
        self._planner = LLMToolPlanner(provider)
        self._metrics: Counter[str] = Counter()

    @property
    def metrics(self) -> dict[str, int]:
        return dict(self._metrics)

    def reset_metrics(self) -> None:
        self._metrics.clear()

    def decide(
        self,
        observation: Mapping[str, Any],
        history: Sequence[Mapping[str, Any]],
    ) -> InvestigationDecision:
        tool_history = tuple(entry for entry in history if entry.get("kind") == "tool")
        if any(_sequence(entry.get("evidence")) for entry in tool_history):
            return super().decide(observation, history)

        measurements = _mapping(observation.get("measurements"))
        if float(measurements.get("telemetry_coverage", 0.0)) < 0.6:
            return InvestigationDecision(
                "escalate",
                None,
                (),
                "telemetry is insufficient for safe LLM investigation",
                (),
            )

        attempted = {str(entry.get("tool")) for entry in tool_history}
        if len(attempted) >= self.max_tool_calls:
            self._metrics["budget_exhaustion_count"] += 1
            return InvestigationDecision(
                "escalate",
                None,
                (),
                "diagnostic budget exhausted without correlated evidence",
                (),
            )

        available_tools = [dict(_mapping(item)) for item in _sequence(observation.get("tool_catalog")) if str(_mapping(item).get("tool_id")) not in attempted]
        packet = {
            "case_id": observation.get("case_id"),
            "symptom": observation.get("symptom"),
            "measurements": {
                "telemetry_coverage": measurements.get("telemetry_coverage"),
                "recovered": measurements.get("recovered"),
            },
            "tool_catalog": available_tools,
            "tool_history": [{"kind": "tool", "tool": entry.get("tool"), "status": entry.get("status")} for entry in tool_history],
            "remaining_tool_budget": self.max_tool_calls - len(attempted),
            "boundary": {
                "read_only_tools_only": True,
                "production_mutation_enabled": False,
                "action_authority": False,
            },
        }
        self._metrics["planner_decision_count"] += 1
        plan = self._planner.select(packet)
        if plan.valid and plan.route == "inspect" and plan.tool is not None:
            return InvestigationDecision(
                "inspect",
                plan.tool,
                (),
                plan.rationale,
                ({"name": "llm_proposal", "tool": plan.tool, "confidence": None},),
            )
        self._metrics["planner_escalation_count"] += 1
        if plan.failure_reason:
            self._metrics[f"planner_failure_{plan.failure_reason}"] += 1
        if plan.proposed_tool in attempted:
            self._metrics["repeated_tool_prevented_count"] += 1
        if plan.failure_reason not in {None, "invalid_plan", "unknown_tool"}:
            self._metrics["provider_failure_fail_closed_count"] += 1
        return InvestigationDecision("escalate", None, (), plan.rationale, ())


@dataclass(frozen=True)
class LLMDiagnosticEpisodeReport:
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        redacted = redact_value(self.payload)
        return dict(redacted) if isinstance(redacted, Mapping) else dict(self.payload)


class LLMDiagnosticEpisodeBenchmark:
    """Compare LLM diagnosis to P101 heuristic and fixed-tool baselines."""

    def __init__(
        self,
        *,
        provider: ToolPlanningProvider,
        sample_size: int = 20,
        max_tool_calls: int = 3,
        max_action_steps: int = 3,
    ) -> None:
        if sample_size < 5 or sample_size > 100:
            raise ValueError("sample_size must be between 5 and 100")
        if max_action_steps < 1 or max_action_steps > 10:
            raise ValueError("max_action_steps must be between 1 and 10")
        self.provider = provider
        self.sample_size = sample_size
        self.max_tool_calls = max_tool_calls
        self.max_action_steps = max_action_steps
        self.agent = LLMDiagnosticEpisodeAgent(provider, max_tool_calls=max_tool_calls)

    def run(
        self,
        *,
        cases: Sequence[CausalScenario] | None = None,
        seeds: Sequence[int] = (11,),
    ) -> LLMDiagnosticEpisodeReport:
        catalog = build_comprehensive_operational_catalog()
        selected = tuple(cases) if cases is not None else catalog
        normalized_seeds = tuple(int(seed) for seed in seeds)
        if not selected or not normalized_seeds:
            raise ValueError("cases and seeds must not be empty")

        self.agent.reset_metrics()
        heuristic_payload = (
            ToolInvestigationBenchmark(
                sample_size=self.sample_size,
                max_action_steps=self.max_action_steps,
            )
            .run(cases=selected, seeds=normalized_seeds)
            .to_dict()
        )
        llm_payload = (
            ToolInvestigationBenchmark(
                agent=self.agent,
                sample_size=self.sample_size,
                max_action_steps=self.max_action_steps,
            )
            .run(cases=selected, seeds=normalized_seeds)
            .to_dict()
        )
        return LLMDiagnosticEpisodeReport(
            _combine_reports(
                catalog,
                selected,
                normalized_seeds,
                heuristic_payload,
                llm_payload,
                self.agent,
            )
        )


def run_llm_diagnostic_episode_suite(
    providers: Mapping[str, ToolPlanningProvider],
    *,
    cases: Sequence[CausalScenario] | None = None,
    seeds: Sequence[int] = (11,),
    sample_size: int = 20,
    max_tool_calls: int = 3,
    max_action_steps: int = 3,
) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for name, provider in providers.items():
        results[name] = (
            LLMDiagnosticEpisodeBenchmark(
                provider=provider,
                sample_size=sample_size,
                max_tool_calls=max_tool_calls,
                max_action_steps=max_action_steps,
            )
            .run(cases=cases, seeds=seeds)
            .to_dict()
        )
    return {
        "summary": {
            "provider_count": len(results),
            "execution_valid": bool(results) and all(bool(_mapping(result.get("summary")).get("execution_valid")) for result in results.values()),
            "action_authority": False,
            "production_mutation_enabled": False,
        },
        "providers": results,
    }


def render_llm_diagnostic_episode_markdown(payload: Mapping[str, Any]) -> str:
    lines = ["# OpsCat Multi-step LLM Diagnostic Episode", "", "## Providers"]
    for name, result in _mapping(payload.get("providers")).items():
        score = _mapping(_mapping(result).get("scorecard"))
        summary = _mapping(_mapping(result).get("summary"))
        lines.append(
            f"- `{name}` valid={summary.get('execution_valid')} "
            f"top1={score.get('llm_top1_tool_accuracy')} "
            f"discovery={score.get('llm_relevant_tool_discovery_rate')} "
            f"recovery={score.get('llm_recovery_rate')}"
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "- The provider chooses closed read-only diagnostics only.",
            "- P100 retains all action selection and execution authority.",
            "- Default fixture mode is deterministic and network-free.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_llm_diagnostic_episode_outputs(
    payload: Mapping[str, Any],
    *,
    output_json: str | Path | None = None,
    output_md: str | Path | None = None,
) -> None:
    if output_json:
        path = Path(output_json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        path = Path(output_md)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_llm_diagnostic_episode_markdown(payload), encoding="utf-8")


def _combine_reports(
    catalog: Sequence[CausalScenario],
    cases: Sequence[CausalScenario],
    seeds: tuple[int, ...],
    heuristic_payload: Mapping[str, Any],
    llm_payload: Mapping[str, Any],
    agent: LLMDiagnosticEpisodeAgent,
) -> dict[str, Any]:
    heuristic_trials = [dict(_mapping(item)) for item in _sequence(heuristic_payload.get("trials"))]
    llm_trials = [dict(_mapping(item)) for item in _sequence(llm_payload.get("trials"))]
    trials: list[dict[str, Any]] = []
    arm_map = {
        "direct_visible": "direct_visible",
        "fixed_tool": "fixed_tool",
        "tool_investigator": "heuristic_investigator",
    }
    for trial in heuristic_trials:
        arm = str(trial.get("arm"))
        if arm in arm_map:
            trial["arm"] = arm_map[arm]
            trials.append(trial)
    for trial in llm_trials:
        if trial.get("arm") == "tool_investigator":
            trial["arm"] = "llm_investigator"
            trials.append(trial)

    arms = ("direct_visible", "fixed_tool", "heuristic_investigator", "llm_investigator")
    grouped = {arm: [trial for trial in trials if trial.get("arm") == arm] for arm in arms}
    case_by_id = {case.case_id: case for case in cases}
    safety = _merge_safety(heuristic_payload, llm_payload)
    safety["repeated_tool_execution_count"] = sum(
        len(tools) != len(set(tools)) for trial in grouped["llm_investigator"] for tools in [[str(_mapping(item).get("tool")) for item in _sequence(trial.get("tool_trace"))]]
    )
    safety["tool_budget_violation_count"] = sum(len(_sequence(trial.get("tool_trace"))) > agent.max_tool_calls for trial in grouped["llm_investigator"])
    safety["initial_state_mismatch_count"] = _fingerprint_mismatches(trials, cases, seeds)
    safety["hard_gate_passed"] = (
        bool(_mapping(heuristic_payload.get("safety")).get("hard_gate_passed"))
        and bool(_mapping(llm_payload.get("safety")).get("hard_gate_passed"))
        and all(
            safety[key] == 0
            for key in (
                "repeated_tool_execution_count",
                "tool_budget_violation_count",
                "initial_state_mismatch_count",
            )
        )
    )

    heuristic = grouped["heuristic_investigator"]
    llm = grouped["llm_investigator"]
    heuristic_eligible = _eligible_tool_trials(heuristic)
    llm_eligible = _eligible_tool_trials(llm)
    heuristic_recovery = _recovery_rate(heuristic)
    llm_recovery = _recovery_rate(llm)
    wrong_top1 = [trial for trial in llm_eligible if not _top1_correct(trial, case_by_id)]
    expected_trials = len(cases) * len(seeds) * len(arms)
    return {
        "schema_version": "p103-v1",
        "summary": {
            "catalog_case_count": len(catalog),
            "catalog_family_count": len({case.family for case in catalog}),
            "case_count": len(cases),
            "seed_count": len(seeds),
            "arm_count": len(arms),
            "trial_count": len(trials),
            "internal_executed_trial_count": int(_mapping(heuristic_payload.get("summary")).get("trial_count", 0)) + int(_mapping(llm_payload.get("summary")).get("trial_count", 0)),
            "execution_valid": bool(safety["hard_gate_passed"]) and len(trials) == expected_trials,
            "provider": agent.provider.name,
            "model_calls_enabled": agent.provider.model_calls_enabled,
            "planner_decision_count": agent.metrics.get("planner_decision_count", 0),
            "external_model_call_count": agent.metrics.get("planner_decision_count", 0) if agent.provider.model_calls_enabled else 0,
            "default_external_network_call_count": 0,
            "provider_action_execution_count": 0,
            "boundary": dict(IsolatedFaultLab.boundary),
        },
        "scorecard": {
            **{f"{arm}_recovery_rate": _recovery_rate(grouped[arm]) for arm in arms},
            "heuristic_top1_tool_accuracy": _top1_rate(heuristic_eligible, case_by_id),
            "heuristic_relevant_tool_discovery_rate": _discovery_rate(heuristic_eligible, case_by_id),
            "llm_top1_tool_accuracy": _top1_rate(llm_eligible, case_by_id),
            "llm_relevant_tool_discovery_rate": _discovery_rate(llm_eligible, case_by_id),
            "llm_recovery_rate": llm_recovery,
            "llm_recovery_lift_over_fixed_tool": round(llm_recovery - _recovery_rate(grouped["fixed_tool"]), 4),
            "llm_recovery_retention_vs_heuristic": _ratio(llm_recovery, heuristic_recovery),
            "llm_wrong_top1_recovery_rate": _recovery_rate(wrong_top1),
            "llm_average_tool_calls": _ratio(sum(len(_sequence(trial.get("tool_trace"))) for trial in llm), len(llm)),
        },
        "agent_metrics": agent.metrics,
        "safety": safety,
        "trials": trials,
    }


def _fingerprint_mismatches(
    trials: Sequence[Mapping[str, Any]],
    cases: Sequence[CausalScenario],
    seeds: Sequence[int],
) -> int:
    mismatches = 0
    for case in cases:
        for seed in seeds:
            fingerprints = {str(trial.get("initial_fingerprint")) for trial in trials if trial.get("case_id") == case.case_id and trial.get("seed") == seed}
            mismatches += int(len(fingerprints) != 1)
    return mismatches


def _merge_safety(*payloads: Mapping[str, Any]) -> dict[str, int | bool]:
    merged: Counter[str] = Counter()
    for payload in payloads:
        for key, value in _mapping(payload.get("safety")).items():
            if key != "hard_gate_passed" and isinstance(value, int):
                merged[str(key)] += value
    return dict(merged)


def _top1_correct(
    trial: Mapping[str, Any],
    case_by_id: Mapping[str, CausalScenario],
) -> bool:
    trace = _sequence(trial.get("tool_trace"))
    return bool(trace) and str(_mapping(trace[0]).get("tool")) == expected_diagnostic_tool(case_by_id[str(trial["case_id"])])


def _top1_rate(
    trials: Sequence[Mapping[str, Any]],
    case_by_id: Mapping[str, CausalScenario],
) -> float:
    return _ratio(sum(_top1_correct(trial, case_by_id) for trial in trials), len(trials))


def _discovery_rate(
    trials: Sequence[Mapping[str, Any]],
    case_by_id: Mapping[str, CausalScenario],
) -> float:
    discovered = sum(expected_diagnostic_tool(case_by_id[str(trial["case_id"])]) in {str(_mapping(item).get("tool")) for item in _sequence(trial.get("tool_trace"))} for trial in trials)
    return _ratio(discovered, len(trials))


def _recovery_rate(trials: Sequence[Mapping[str, Any]]) -> float:
    return _ratio(
        sum(bool(_mapping(trial.get("final")).get("recovered")) for trial in trials),
        len(trials),
    )


def _eligible_tool_trials(
    trials: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    return [trial for trial in trials if float(_mapping(trial.get("pre")).get("telemetry_coverage", 0.0)) >= 0.6]


def _ratio(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) else ()


__all__ = [
    "LLMDiagnosticEpisodeAgent",
    "LLMDiagnosticEpisodeBenchmark",
    "LLMDiagnosticEpisodeReport",
    "render_llm_diagnostic_episode_markdown",
    "run_llm_diagnostic_episode_suite",
    "write_llm_diagnostic_episode_outputs",
]
