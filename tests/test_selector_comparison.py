from __future__ import annotations

import json
from typing import Any

from app.services.causal_remediation_benchmark import CausalDecision, build_causal_scenario_catalog
from app.services.selector_comparison import (
    EvidenceOnlyLLMSelector,
    ObservationOnlySelector,
    build_causal_selector_prompt,
    build_default_selector_suite,
    run_selector_comparison,
)


class _RecordingProvider:
    name = "recording"
    model_calls_enabled = False

    def __init__(self, response: Any) -> None:
        self.response = response
        self.prompts: list[str] = []

    def complete(self, messages: list[dict[str, str]]) -> Any:
        self.prompts.extend(message["content"] for message in messages)
        return self.response


def test_causal_prompt_contains_public_observation_only() -> None:
    observation = {
        "case_id": "p97-visible",
        "symptom": "connection pool wait",
        "evidence": ["db_pool_wait_high"],
        "measurements": {"availability": 0.4, "telemetry_coverage": 0.95},
        "allowed_actions": ["recycle_connection_pool"],
        "boundary": {"loopback_only": True, "production_mutation_enabled": False},
    }

    messages = build_causal_selector_prompt(observation)
    rendered = "\n".join(message["content"] for message in messages)

    assert "required_actions" not in rendered
    assert "harmful_actions" not in rendered
    assert "root_cause" not in rendered
    assert "expected_outcome" not in rendered
    assert "db_pool_wait_high" in rendered


def test_malformed_or_unknown_llm_output_fails_closed() -> None:
    observation = {
        "case_id": "p97-visible",
        "symptom": "bad signal",
        "evidence": [],
        "measurements": {"telemetry_coverage": 0.95},
        "allowed_actions": ["restart_service"],
        "boundary": {"loopback_only": True},
    }

    malformed = EvidenceOnlyLLMSelector(_RecordingProvider("not json")).select(observation)
    unknown = EvidenceOnlyLLMSelector(_RecordingProvider(json.dumps({"route": "act", "actions": ["rm -rf /"]}))).select(observation)

    assert malformed == CausalDecision("escalate", (), "LLM output was malformed; fail closed")
    assert unknown.route == "escalate"
    assert unknown.actions == ()


def test_default_suite_has_distinct_baselines() -> None:
    suite = build_default_selector_suite()

    assert set(suite) == {"rule_based", "observation_only", "mock_llm"}
    assert isinstance(suite["observation_only"], ObservationOnlySelector)
    assert all(hasattr(selector, "select") for selector in suite.values())


def test_selector_comparison_reports_blind_metrics_and_safety() -> None:
    selected = tuple(
        case
        for case in build_causal_scenario_catalog()
        if (case.family, case.variant)
        in {
            ("deploy_config", "obvious"),
            ("natural_recovery", "natural_recovery"),
            ("security_auth", "human_required"),
            ("compound_failure", "compound"),
        }
    )

    payload = run_selector_comparison(build_default_selector_suite(), cases=selected, seeds=(11,), sample_size=5)

    assert payload["summary"]["selector_count"] == 3
    assert payload["summary"]["execution_valid"] is True
    assert set(payload["selectors"]) == {"rule_based", "observation_only", "mock_llm"}
    for result in payload["selectors"].values():
        assert "blind" in result["splits"]
        assert result["safety"]["hard_gate_passed"] is True
        assert "harmful_action_rate" in result["scorecard"]
        assert "mean_runbook_regret" in result["scorecard"]
