from __future__ import annotations

from typing import Any

from app.services.llm_tool_planner_evaluation import (
    LLMToolPlanner,
    MockToolPlanningProvider,
    run_llm_tool_planner_evaluation,
)
from app.services.operational_scenario_catalog import build_comprehensive_operational_catalog
from app.services.tool_using_hypothesis_investigator import build_diagnostic_tool_catalog


class _Provider:
    name = "test"
    model_calls_enabled = False

    def __init__(self, value: Any) -> None:
        self.value = value

    def complete(self, messages: list[dict[str, str]]) -> Any:
        return self.value


def _packet() -> dict[str, Any]:
    return {
        "symptom": "database pool wait grows",
        "measurements": {"telemetry_coverage": 0.95},
        "tool_catalog": [tool.__dict__ for tool in build_diagnostic_tool_catalog().values()],
        "boundary": {"production_mutation_enabled": False},
    }


def test_invalid_and_unknown_tool_outputs_fail_closed() -> None:
    for raw in (
        "not json",
        {"route": "inspect", "tool": "shell.exec"},
        {"route": "escalate", "tool": "database.inspect"},
        {"route": "inspect", "tool": "database.inspect", "arguments": {"query": "DROP TABLE"}},
        {"route": "inspect", "tool": "database.inspect", "actions": ["restart"]},
    ):
        plan = LLMToolPlanner(_Provider(raw)).select(_packet())
        assert plan.route == "escalate"
        assert plan.tool is None
        assert plan.valid is False

    failed_provider_plan = LLMToolPlanner(_RaisingProvider()).select(_packet())
    assert failed_provider_plan.route == "escalate"
    assert failed_provider_plan.valid is False
    assert failed_provider_plan.failure_reason == "RuntimeError"


def test_mock_evaluation_covers_four_perturbations_without_unsafe_tools() -> None:
    cases = tuple(case for case in build_comprehensive_operational_catalog() if case.variant == "obvious")[:12]
    payload = run_llm_tool_planner_evaluation({"mock": MockToolPlanningProvider()}, cases=cases)
    result = payload["providers"]["mock"]

    assert payload["summary"]["execution_valid"] is True
    assert payload["summary"]["default_network_calls"] == 0
    assert payload["summary"]["action_execution_count"] == 0
    assert result["decision_count"] == 48
    assert result["unsafe_tool_count"] == 0
    assert result["model_call_count"] == 0
    assert set(result["by_perturbation"]) == {"original", "paraphrased", "opaque_topology", "distractor_injection"}


class _RaisingProvider:
    name = "raising"
    model_calls_enabled = False

    def complete(self, messages: list[dict[str, str]]) -> Any:
        raise RuntimeError("provider unavailable")
