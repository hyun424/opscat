from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.services.judgment_dataset import JudgmentCase, load_judgment_cases
from app.services.llm_context_builder import build_context_from_judgment_case
from app.services.llm_judgment import LLMJudgmentProvider, run_llm_judgment_from_packet
from app.services.llm_provider_evaluation import evaluate_llm_judgment_case
from app.services.policy_calibrator import calibrate_llm_policy


class AggressiveProvider:
    name = "aggressive"
    model_calls_enabled = False
    model = "aggressive-fixture"

    def __init__(self, *, route: str, actions: tuple[str, ...], citations: tuple[str, ...], hypothesis: str) -> None:
        self.route = route
        self.actions = actions
        self.citations = citations
        self.hypothesis = hypothesis

    def judge(self, context_packet: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "hypotheses": [
                {"label": self.hypothesis, "confidence": 0.91, "evidence_citations": list(self.citations)},
            ],
            "recommended_route": self.route,
            "safe_actions": list(self.actions),
            "forbidden_actions_detected": [],
            "missing_evidence": [],
            "verification_plan": ["review cited evidence before action"],
            "evidence_citations": list(self.citations),
            "boundary": {
                "local_mock_only": True,
                "provider": "aggressive",
                "model": "aggressive-fixture",
                "model_calls_enabled": False,
                "action_execution_enabled": False,
            },
        }


def _case(case_id: str) -> JudgmentCase:
    return next(case for case in load_judgment_cases("evals/judgment/seed/cases.json") if case.id == case_id)


def test_calibrator_forces_no_data_restart_to_human_required() -> None:
    case = _case("seed-nab-no-data")
    context = build_context_from_judgment_case(case).to_dict()
    run_result = run_llm_judgment_from_packet(
        context,
        provider=AggressiveProvider(
            route="local_mock_auto_allowed",
            actions=("mock.get_error_context", "mock.execute_restart_worker"),
            citations=("metric:window",),
            hypothesis="no data metric gap",
        ),
    ).to_dict()

    calibration = calibrate_llm_policy(case, context, run_result)
    payload = calibration.to_dict()

    assert payload["provider_route"] == "local_mock_auto_allowed"
    assert payload["safety_gate_route"] == "local_mock_auto_allowed"
    assert payload["calibrated_route"] == "human_required"
    assert "mock.execute_restart_worker" in payload["removed_actions"]
    assert payload["retained_actions"] == []
    assert any("no_data" in reason or "insufficient_evidence" in reason for reason in payload["calibration_reasons"])
    assert payload["action_execution_enabled"] is False


def test_calibrator_prevents_deploy_regression_auto_rollback() -> None:
    case = _case("seed-loghub-deploy-regression")
    context = build_context_from_judgment_case(case).to_dict()
    run_result = run_llm_judgment_from_packet(
        context,
        provider=AggressiveProvider(
            route="local_mock_auto_allowed",
            actions=("mock.get_recent_deploys", "mock.create_rollback_pr"),
            citations=("log:1",),
            hypothesis="deploy regression",
        ),
    ).to_dict()

    calibration = calibrate_llm_policy(case, context, run_result)
    payload = calibration.to_dict()

    assert payload["calibrated_route"] == "human_required"
    assert "mock.create_rollback_pr" in payload["removed_actions"]
    assert payload["retained_actions"] == []
    assert any("rollback" in reason or "deploy" in reason for reason in payload["calibration_reasons"])


def test_calibrator_blocks_prompt_injection_even_if_provider_allows_auto() -> None:
    case = _case("seed-loghub-injection-block")
    context = build_context_from_judgment_case(case).to_dict()
    run_result = run_llm_judgment_from_packet(
        context,
        provider=AggressiveProvider(
            route="local_mock_auto_allowed",
            actions=("mock.get_error_context",),
            citations=("log:1",),
            hypothesis="injection attempt",
        ),
    ).to_dict()

    calibration = calibrate_llm_policy(case, context, run_result)
    payload = calibration.to_dict()

    assert payload["calibrated_route"] == "blocked"
    assert payload["retained_actions"] == []
    assert "prompt_injection" in payload["fatal_risk_flags"]
    assert any("prompt_injection" in reason for reason in payload["calibration_reasons"])


def test_provider_eval_scores_calibrated_route_and_removed_actions() -> None:
    case = _case("seed-loghub-deploy-regression")

    result = evaluate_llm_judgment_case(
        case,
        provider=AggressiveProvider(
            route="local_mock_auto_allowed",
            actions=("mock.get_recent_deploys", "mock.create_rollback_pr"),
            citations=("log:1",),
            hypothesis="deploy regression",
        ),
    )
    payload = result.to_dict()

    assert payload["provider_route"] == "local_mock_auto_allowed"
    assert payload["safety_gate_route"] == "local_mock_auto_allowed"
    assert payload["final_route"] == "human_required"
    assert payload["dimension_scores"]["route"] == 1.0
    assert payload["dimension_scores"]["forbidden_action"] == 1.0
    assert "mock.create_rollback_pr" in payload["removed_actions"]
    assert payload["passed"] is True


# Protocol conformance guard for static type checking.
_provider: LLMJudgmentProvider = AggressiveProvider(
    route="human_required",
    actions=("mock.get_error_context",),
    citations=("log:1",),
    hypothesis="diagnostic review",
)
