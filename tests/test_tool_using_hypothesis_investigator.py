from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from app.services.causal_remediation_benchmark import CausalScenario
from app.services.operational_scenario_catalog import build_comprehensive_operational_catalog
from app.services.tool_using_hypothesis_investigator import (
    HypothesisToolAgent,
    ToolInvestigationBenchmark,
    build_diagnostic_tool_catalog,
    expected_diagnostic_tool,
    render_tool_investigation_markdown,
)


def _case(family: str, variant: str) -> CausalScenario:
    return next(case for case in build_comprehensive_operational_catalog() if case.family == family and case.variant == variant)


class _RecordingAgent(HypothesisToolAgent):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[Mapping[str, Any], Sequence[Mapping[str, Any]]]] = []

    def decide(self, observation: Mapping[str, Any], history: Sequence[Mapping[str, Any]]):  # type: ignore[no-untyped-def]
        self.calls.append((observation, history))
        return super().decide(observation, history)


def test_tool_catalog_is_closed_read_only_and_covers_all_families() -> None:
    catalog = build_diagnostic_tool_catalog()
    obvious = [case for case in build_comprehensive_operational_catalog() if case.variant == "obvious"]

    assert len(obvious) == 52
    assert len(catalog) >= 12
    assert all(tool.mode == "read_only" and tool.side_effects is False for tool in catalog.values())
    assert all(expected_diagnostic_tool(case) in catalog for case in obvious)


def test_initial_agent_boundary_hides_evidence_and_scorer_truth() -> None:
    agent = _RecordingAgent()
    payload = ToolInvestigationBenchmark(agent=agent, sample_size=5).run(cases=(_case("database", "first_action_ineffective"),), seeds=(7,)).to_dict()

    assert payload["summary"]["execution_valid"] is True
    assert agent.calls
    initial = agent.calls[0]
    rendered = json.dumps(initial, sort_keys=True, default=str)
    for forbidden in (
        "visible_evidence",
        "required_actions",
        "harmful_actions",
        "runbook_actions",
        "expected_outcome",
        "required remediation completed",
        "partial remediation",
        "collateral regression",
        '"family"',
        '"variant"',
        '"split"',
        "db_pool_wait_high",
    ):
        assert forbidden not in rendered


def test_investigator_uses_database_tool_then_recovers_after_failed_action() -> None:
    payload = ToolInvestigationBenchmark(sample_size=20).run(cases=(_case("database", "first_action_ineffective"),), seeds=(11,)).to_dict()
    trial = next(item for item in payload["trials"] if item["arm"] == "tool_investigator")

    assert trial["tool_trace"][0]["tool"] == "database.inspect"
    assert trial["tool_trace"][0]["status"] == "correlated_anomaly"
    assert [step["decision"]["actions"][0] for step in trial["action_steps"]] == [
        "recycle_connection_pool",
        "shed_load",
    ]
    assert trial["final"]["recovered"] is True


def test_negative_tool_result_demotes_anchor_and_selects_another_tool() -> None:
    agent = HypothesisToolAgent(tool_priority_override=("logs.search_read_only", "database.inspect"))
    payload = ToolInvestigationBenchmark(agent=agent, sample_size=10).run(cases=(_case("database", "obvious"),), seeds=(13,)).to_dict()
    trial = next(item for item in payload["trials"] if item["arm"] == "tool_investigator")

    assert [item["tool"] for item in trial["tool_trace"]] == ["logs.search_read_only", "database.inspect"]
    assert [item["status"] for item in trial["tool_trace"]] == ["no_correlated_anomaly", "correlated_anomaly"]
    assert trial["final"]["recovered"] is True


def test_privileged_case_escalates_without_action_after_diagnosis() -> None:
    payload = ToolInvestigationBenchmark(sample_size=10).run(cases=(_case("data_corruption", "obvious"),), seeds=(17,)).to_dict()
    trial = next(item for item in payload["trials"] if item["arm"] == "tool_investigator")

    assert trial["tool_trace"]
    assert trial["stop_reason"] == "escalated"
    assert trial["action_count"] == 0
    assert trial["final"]["utility"] == trial["pre"]["utility"]


def test_comparison_has_equal_fingerprints_and_tool_metrics() -> None:
    selected = (
        _case("database", "first_action_ineffective"),
        _case("retry_storm", "compound"),
        _case("data_corruption", "human_required"),
        _case("natural_recovery", "natural_recovery"),
    )
    payload = ToolInvestigationBenchmark(sample_size=10).run(cases=selected, seeds=(19,)).to_dict()

    assert payload["summary"]["arm_count"] == 3
    assert payload["summary"]["trial_count"] == 12
    assert payload["summary"]["execution_valid"] is True
    assert payload["safety"]["hard_gate_passed"] is True
    assert payload["scorecard"]["relevant_tool_discovery_rate"] >= 0.75
    for case in selected:
        fingerprints = {trial["initial_fingerprint"] for trial in payload["trials"] if trial["case_id"] == case.case_id}
        assert len(fingerprints) == 1


def test_tool_investigation_cli_writes_reports(tmp_path: Path) -> None:
    output_json = tmp_path / "p101.json"
    output_md = tmp_path / "p101.md"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_tool_investigation_benchmark.py",
            "--max-cases",
            "16",
            "--seeds",
            "7",
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
    markdown = output_md.read_text(encoding="utf-8")
    assert payload["summary"]["catalog_case_count"] == 520
    assert payload["summary"]["case_count"] == 16
    assert payload["summary"]["execution_valid"] is True
    assert "Tool-Using Hypothesis Investigator" in markdown
    assert render_tool_investigation_markdown(payload).startswith("# OpsCat Tool-Using Hypothesis Investigator")
    assert '"execution_valid": true' in completed.stdout.lower()
