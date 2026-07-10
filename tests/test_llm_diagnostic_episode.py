from __future__ import annotations

import json
from typing import Any

from app.services.llm_diagnostic_episode import (
    LLMDiagnosticEpisodeAgent,
    LLMDiagnosticEpisodeBenchmark,
)
from app.services.llm_tool_planner_evaluation import MockToolPlanningProvider
from app.services.operational_scenario_catalog import build_comprehensive_operational_catalog


def _case(family: str, variant: str = "obvious"):  # type: ignore[no-untyped-def]
    return next(case for case in build_comprehensive_operational_catalog() if case.family == family and case.variant == variant)


class _ScriptedProvider:
    name = "scripted"
    model_calls_enabled = False

    def complete(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        packet = json.loads(messages[-1]["content"])["packet"]
        attempted = [entry["tool"] for entry in packet.get("tool_history", [])]
        tool = "logs.search_read_only" if not attempted else "database.inspect"
        return {"route": "inspect", "tool": tool, "rationale": "test the next hypothesis"}


class _RepeatingProvider:
    name = "repeating"
    model_calls_enabled = False

    def complete(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        return {"route": "inspect", "tool": "logs.search_read_only", "rationale": "repeat"}


class _FailingProvider:
    name = "failing"
    model_calls_enabled = False

    def complete(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        raise RuntimeError("provider unavailable")


def test_episode_replans_after_negative_tool_result_then_recovers() -> None:
    report = LLMDiagnosticEpisodeBenchmark(provider=_ScriptedProvider(), sample_size=10, max_tool_calls=3).run(cases=(_case("database"),), seeds=(11,))
    payload = report.to_dict()
    trial = next(item for item in payload["trials"] if item["arm"] == "llm_investigator")

    assert [item["tool"] for item in trial["tool_trace"]] == [
        "logs.search_read_only",
        "database.inspect",
    ]
    assert [item["status"] for item in trial["tool_trace"]] == [
        "no_correlated_anomaly",
        "correlated_anomaly",
    ]
    assert trial["final"]["recovered"] is True
    assert trial["action_count"] == 1


def test_repeated_tool_proposal_fails_closed_before_second_execution() -> None:
    report = LLMDiagnosticEpisodeBenchmark(provider=_RepeatingProvider(), sample_size=5, max_tool_calls=3).run(cases=(_case("database"),), seeds=(7,))
    payload = report.to_dict()
    trial = next(item for item in payload["trials"] if item["arm"] == "llm_investigator")

    assert [item["tool"] for item in trial["tool_trace"]] == ["logs.search_read_only"]
    assert trial["stop_reason"] == "escalated"
    assert trial["action_count"] == 0
    assert payload["safety"]["repeated_tool_execution_count"] == 0


def test_provider_failure_escalates_without_tool_or_action() -> None:
    report = LLMDiagnosticEpisodeBenchmark(provider=_FailingProvider(), sample_size=5).run(cases=(_case("database"),), seeds=(13,))
    payload = report.to_dict()
    trial = next(item for item in payload["trials"] if item["arm"] == "llm_investigator")

    assert trial["tool_trace"] == []
    assert trial["action_steps"] == []
    assert trial["stop_reason"] == "escalated"
    assert payload["safety"]["hard_gate_passed"] is True


def test_agent_context_hides_scorer_truth_and_enforces_budget() -> None:
    provider = _RecordingProvider()
    report = LLMDiagnosticEpisodeBenchmark(provider=provider, sample_size=5, max_tool_calls=1).run(cases=(_case("database"),), seeds=(17,))
    payload = report.to_dict()
    trial = next(item for item in payload["trials"] if item["arm"] == "llm_investigator")
    rendered = json.dumps(provider.messages, sort_keys=True)

    assert len(trial["tool_trace"]) == 1
    for forbidden in (
        '"family"',
        '"variant"',
        '"split"',
        "expected_tool",
        "required_actions",
        "harmful_actions",
        "runbook_actions",
        "db_pool_wait_high",
    ):
        assert forbidden not in rendered


def test_comparison_reports_strict_and_outcome_metrics_from_equal_states() -> None:
    cases = (_case("database"), _case("queue"), _case("data_corruption"))
    payload = LLMDiagnosticEpisodeBenchmark(provider=MockToolPlanningProvider(), sample_size=5).run(cases=cases, seeds=(19,)).to_dict()

    assert payload["summary"]["arm_count"] == 4
    assert payload["summary"]["trial_count"] == 12
    assert payload["summary"]["execution_valid"] is True
    assert payload["safety"]["hard_gate_passed"] is True
    assert 0.0 <= payload["scorecard"]["llm_top1_tool_accuracy"] <= 1.0
    assert 0.0 <= payload["scorecard"]["llm_relevant_tool_discovery_rate"] <= 1.0
    assert 0.0 <= payload["scorecard"]["llm_recovery_rate"] <= 1.0
    for case in cases:
        fingerprints = {trial["initial_fingerprint"] for trial in payload["trials"] if trial["case_id"] == case.case_id}
        assert len(fingerprints) == 1


class _RecordingProvider:
    name = "recording"
    model_calls_enabled = False

    def __init__(self) -> None:
        self.messages: list[list[dict[str, str]]] = []

    def complete(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        self.messages.append(messages)
        return {"route": "inspect", "tool": "logs.search_read_only", "rationale": "bounded"}


def test_agent_rejects_invalid_tool_budget() -> None:
    for invalid in (0, 11):
        try:
            LLMDiagnosticEpisodeAgent(MockToolPlanningProvider(), max_tool_calls=invalid)
        except ValueError as exc:
            assert "max_tool_calls" in str(exc)
        else:
            raise AssertionError("invalid budget must be rejected")
