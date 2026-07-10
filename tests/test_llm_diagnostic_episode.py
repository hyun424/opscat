from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest

from app.services.llm_diagnostic_episode import (
    LLMDiagnosticEpisodeAgent,
    LLMDiagnosticEpisodeBenchmark,
    render_llm_diagnostic_episode_markdown,
    run_llm_diagnostic_episode_suite,
    write_llm_diagnostic_episode_outputs,
)
from app.services.llm_tool_planner_evaluation import MockToolPlanningProvider
from app.services.operational_scenario_catalog import build_comprehensive_operational_catalog
from app.services.tool_using_hypothesis_investigator import build_diagnostic_tool_catalog


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


class _LiveShapedProvider(_ScriptedProvider):
    name = "live-shaped"
    model_calls_enabled = True


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
    assert payload["agent_metrics"]["repeated_tool_prevented_count"] == 1


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
    assert payload["summary"]["internal_executed_trial_count"] == 18
    assert payload["summary"]["execution_valid"] is True
    assert payload["safety"]["hard_gate_passed"] is True
    assert 0.0 <= payload["scorecard"]["llm_top1_tool_accuracy"] <= 1.0
    assert 0.0 <= payload["scorecard"]["llm_relevant_tool_discovery_rate"] <= 1.0
    assert 0.0 <= payload["scorecard"]["llm_recovery_rate"] <= 1.0
    for case in cases:
        fingerprints = {trial["initial_fingerprint"] for trial in payload["trials"] if trial["case_id"] == case.case_id}
        assert len(fingerprints) == 1


def test_live_shaped_provider_calls_are_counted_explicitly() -> None:
    payload = LLMDiagnosticEpisodeBenchmark(provider=_LiveShapedProvider(), sample_size=5).run(cases=(_case("database"),), seeds=(23,)).to_dict()

    assert payload["summary"]["model_calls_enabled"] is True
    assert payload["summary"]["external_model_call_count"] == 2
    assert payload["summary"]["default_external_network_call_count"] == 0


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


def test_agent_escalates_before_provider_on_low_telemetry_and_exhausted_budget() -> None:
    agent = LLMDiagnosticEpisodeAgent(_FailingProvider(), max_tool_calls=2)
    base = {
        "symptom": "database pool wait grows",
        "measurements": {"telemetry_coverage": 0.4, "recovered": False},
        "tool_catalog": [asdict(tool) for tool in build_diagnostic_tool_catalog().values()],
    }
    low_telemetry = agent.decide(base, ())
    assert low_telemetry.route == "escalate"
    assert agent.metrics == {}

    sufficient = {**base, "measurements": {"telemetry_coverage": 0.9, "recovered": False}}
    exhausted = agent.decide(
        sufficient,
        (
            {"kind": "tool", "tool": "logs.search_read_only", "status": "no_correlated_anomaly"},
            {"kind": "tool", "tool": "metrics.query", "status": "no_correlated_anomaly"},
        ),
    )
    assert exhausted.route == "escalate"
    assert agent.metrics["budget_exhaustion_count"] == 1


def test_benchmark_rejects_invalid_bounds_and_empty_work() -> None:
    for kwargs in ({"sample_size": 4}, {"sample_size": 101}, {"max_action_steps": 0}, {"max_action_steps": 11}):
        with pytest.raises(ValueError):
            LLMDiagnosticEpisodeBenchmark(provider=MockToolPlanningProvider(), **kwargs)

    benchmark = LLMDiagnosticEpisodeBenchmark(provider=MockToolPlanningProvider(), sample_size=5)
    with pytest.raises(ValueError):
        benchmark.run(cases=(), seeds=(11,))
    with pytest.raises(ValueError):
        benchmark.run(cases=(_case("database"),), seeds=())


def test_suite_markdown_and_output_writers(tmp_path: Path) -> None:
    payload = run_llm_diagnostic_episode_suite(
        {"mock": MockToolPlanningProvider()},
        cases=(_case("database"),),
        seeds=(29,),
        sample_size=5,
    )
    markdown = render_llm_diagnostic_episode_markdown(payload)
    output_json = tmp_path / "nested" / "p103.json"
    output_md = tmp_path / "nested" / "p103.md"
    write_llm_diagnostic_episode_outputs(
        payload,
        output_json=output_json,
        output_md=output_md,
    )

    assert payload["summary"]["execution_valid"] is True
    assert "top1=" in markdown
    assert json.loads(output_json.read_text(encoding="utf-8"))["summary"]["provider_count"] == 1
    assert output_md.read_text(encoding="utf-8") == markdown


def test_empty_provider_suite_fails_closed() -> None:
    payload = run_llm_diagnostic_episode_suite({}, cases=(_case("database"),), sample_size=5)
    assert payload["summary"]["execution_valid"] is False
    assert payload["summary"]["provider_count"] == 0


def test_episode_cli_writes_offline_reports(tmp_path: Path) -> None:
    output_json = tmp_path / "p103.json"
    output_md = tmp_path / "p103.md"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_llm_diagnostic_episode.py",
            "--max-cases",
            "4",
            "--obvious-only",
            "--sample-size",
            "5",
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["summary"]["execution_valid"] is True
    assert payload["providers"]["mock"]["summary"]["case_count"] == 4
    assert "Multi-step LLM Diagnostic Episode" in output_md.read_text(encoding="utf-8")
    assert '"execution_valid": true' in completed.stdout.lower()


def test_episode_cli_rejects_invalid_bounds_without_traceback() -> None:
    invalid_arguments = (
        ("--seeds", ""),
        ("--seeds", "not-an-integer"),
        ("--sample-size", "0"),
        ("--max-tool-calls", "0"),
        ("--max-action-steps", "11"),
    )
    for option, value in invalid_arguments:
        completed = subprocess.run(
            [sys.executable, "scripts/run_llm_diagnostic_episode.py", option, value],
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 2
        assert "error:" in completed.stderr
        assert "traceback" not in completed.stderr.lower()
