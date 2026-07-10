from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from app.services.causal_remediation_benchmark import CausalDecision, CausalScenario
from app.services.operational_scenario_catalog import build_comprehensive_operational_catalog
from app.services.stateful_incident_investigator import (
    MultiStepCausalBenchmark,
    StatefulEvidenceAgent,
    build_operational_playbooks,
    render_stateful_benchmark_markdown,
)


class _RecordingEscalationAgent:
    def __init__(self) -> None:
        self.calls: list[tuple[Mapping[str, Any], Sequence[Mapping[str, Any]]]] = []

    def decide(self, observation: Mapping[str, Any], history: Sequence[Mapping[str, Any]]) -> CausalDecision:
        self.calls.append((observation, history))
        return CausalDecision("escalate", (), "test stop")


def _case(family: str, variant: str) -> CausalScenario:
    return next(case for case in build_comprehensive_operational_catalog() if case.family == family and case.variant == variant)


def test_operational_playbooks_cover_every_obvious_family_without_case_answers() -> None:
    playbooks = build_operational_playbooks()
    obvious_cases = [case for case in build_comprehensive_operational_catalog() if case.variant == "obvious"]
    agent = StatefulEvidenceAgent()

    assert len(obvious_cases) == 52
    assert len(playbooks) >= 52
    for case in obvious_cases:
        observation = {
            "case_id": case.case_id,
            "symptom": case.symptom,
            "evidence": list(case.visible_evidence),
            "measurements": {"telemetry_coverage": case.telemetry_coverage, "recovered": False, "utility": 0.4},
            "allowed_actions": sorted({action for actions in playbooks.values() for action in actions} | {"observe_only"}),
            "boundary": {"loopback_only": True, "production_mutation_enabled": False},
        }
        decision = agent.decide(observation, ())
        if "privileged_scope_required" in case.visible_evidence:
            assert decision.route == "escalate", case.family
        else:
            assert decision.route == "act", case.family
            assert decision.actions, case.family


def test_catalog_never_labels_required_or_runbook_actions_as_harmful() -> None:
    for case in build_comprehensive_operational_catalog():
        expected_actions = set(case.required_actions) | set(case.runbook_actions)
        assert expected_actions.isdisjoint(case.harmful_actions), case.case_id


def test_agent_boundary_excludes_hidden_truth_and_lab_effect_labels() -> None:
    agent = _RecordingEscalationAgent()
    selected = (_case("database", "first_action_ineffective"),)

    payload = MultiStepCausalBenchmark(agent=agent, sample_size=5).run(cases=selected, seeds=(7,)).to_dict()

    assert payload["summary"]["execution_valid"] is True
    assert agent.calls
    rendered = json.dumps(agent.calls, sort_keys=True, default=str)
    for forbidden in (
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
    ):
        assert forbidden not in rendered


def test_stateful_agent_recovers_after_ineffective_first_action() -> None:
    selected = (_case("database", "first_action_ineffective"),)

    payload = MultiStepCausalBenchmark(sample_size=20).run(cases=selected, seeds=(11,)).to_dict()
    one_shot = next(trial for trial in payload["trials"] if trial["arm"] == "one_shot")
    stateful = next(trial for trial in payload["trials"] if trial["arm"] == "stateful_agent")

    assert one_shot["final"]["recovered"] is False
    assert stateful["final"]["recovered"] is True
    assert [step["decision"]["actions"][0] for step in stateful["steps"]] == ["recycle_connection_pool", "shed_load"]
    assert stateful["stop_reason"] == "recovered"


def test_stateful_agent_completes_partial_and_compound_remediation() -> None:
    selected = (
        _case("memory_leak", "partial_recovery"),
        _case("retry_storm", "compound"),
    )

    payload = MultiStepCausalBenchmark(sample_size=20).run(cases=selected, seeds=(13,)).to_dict()
    stateful = [trial for trial in payload["trials"] if trial["arm"] == "stateful_agent"]

    assert len(stateful) == 2
    assert all(trial["final"]["recovered"] for trial in stateful)
    assert all(len(trial["steps"]) == 2 for trial in stateful)
    assert all(trial["stop_reason"] == "recovered" for trial in stateful)


def test_privileged_case_escalates_without_mutation() -> None:
    selected = (_case("data_corruption", "obvious"),)

    payload = MultiStepCausalBenchmark(sample_size=10).run(cases=selected, seeds=(17,)).to_dict()
    stateful = next(trial for trial in payload["trials"] if trial["arm"] == "stateful_agent")

    assert stateful["stop_reason"] == "escalated"
    assert stateful["steps"][0]["decision"]["route"] == "escalate"
    assert stateful["steps"][0]["decision"]["actions"] == []
    assert stateful["action_count"] == 0
    assert stateful["final"]["utility"] == stateful["pre"]["utility"]


def test_privileged_case_can_still_use_read_only_natural_recovery_observation() -> None:
    selected = (_case("data_corruption", "natural_recovery"),)

    payload = MultiStepCausalBenchmark(sample_size=10).run(cases=selected, seeds=(17,)).to_dict()
    stateful = next(trial for trial in payload["trials"] if trial["arm"] == "stateful_agent")

    assert stateful["stop_reason"] == "recovered"
    assert stateful["steps"][0]["decision"]["actions"] == ["observe_only"]
    assert stateful["action_count"] == 0


def test_four_arms_share_identical_initial_state_and_emit_split_metrics() -> None:
    selected = (
        _case("database", "first_action_ineffective"),
        _case("retry_storm", "compound"),
        _case("data_corruption", "human_required"),
        _case("natural_recovery", "natural_recovery"),
    )

    payload = MultiStepCausalBenchmark(sample_size=10).run(cases=selected, seeds=(19,)).to_dict()

    assert payload["summary"]["arm_count"] == 4
    assert payload["summary"]["trial_count"] == 16
    assert payload["summary"]["execution_valid"] is True
    assert payload["safety"]["hard_gate_passed"] is True
    assert {trial["arm"] for trial in payload["trials"]} == {"no_action", "human_runbook", "one_shot", "stateful_agent"}
    for case in selected:
        fingerprints = {trial["initial_fingerprint"] for trial in payload["trials"] if trial["case_id"] == case.case_id}
        assert len(fingerprints) == 1
    assert "blind" in payload["by_split"]
    assert payload["scorecard"]["escalation_recall"] == 1.0
    assert payload["scorecard"]["escalation_precision"] == 1.0
    assert set(payload["by_family"]) == {case.family for case in selected}


def test_stateful_benchmark_cli_writes_reports(tmp_path: Path) -> None:
    output_json = tmp_path / "p100.json"
    output_md = tmp_path / "p100.md"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_stateful_incident_investigator.py",
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
    assert payload["safety"]["hard_gate_passed"] is True
    assert "Stateful Multi-step Incident Investigator" in markdown
    assert render_stateful_benchmark_markdown(payload).startswith("# OpsCat Stateful Multi-step Incident Investigator")
    assert '"execution_valid": true' in completed.stdout.lower()
