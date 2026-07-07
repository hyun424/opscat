from __future__ import annotations

import json
from typing import Any

import pytest

from app.services.judgment_dataset import load_judgment_cases
from app.services.llm_context_builder import build_context_from_judgment_case
from app.services.llm_judgment import (
    LLMJudgmentValidationError,
    MockLLMJudgmentProvider,
    apply_judgment_safety_gate,
    check_evidence_citations,
    run_llm_judgment_from_packet,
    validate_llm_judgment,
)


def _packet() -> dict[str, Any]:
    case = next(case for case in load_judgment_cases("evals/judgment/seed/cases.json") if case.id == "seed-loghub-injection-block")
    return build_context_from_judgment_case(case, max_evidence=8).to_dict()


def test_mock_provider_returns_schema_valid_local_mock_judgment_with_citations() -> None:
    packet = _packet()
    provider = MockLLMJudgmentProvider()
    raw = provider.judge(packet)
    judgment = validate_llm_judgment(raw)
    citation = check_evidence_citations(judgment, packet)

    assert provider.name == "mock"
    assert judgment.recommended_route in {"blocked", "human_required"}
    assert judgment.boundary["local_mock_only"] is True
    assert judgment.boundary["provider"] == "mock"
    assert judgment.boundary["model_calls_enabled"] is False
    assert judgment.hypotheses
    assert citation.valid is True
    assert set(judgment.evidence_citations).issubset({item["id"] for item in packet["evidence"]})
    assert any("kubectl" in action.lower() or "production" in action.lower() for action in judgment.forbidden_actions_detected)


def test_validation_rejects_bad_route_and_missing_required_fields() -> None:
    with pytest.raises(LLMJudgmentValidationError, match="recommended_route"):
        validate_llm_judgment({"recommended_route": "ship_it"})

    with pytest.raises(LLMJudgmentValidationError, match="hypotheses"):
        validate_llm_judgment(
            {
                "recommended_route": "blocked",
                "safe_actions": [],
                "forbidden_actions_detected": [],
                "missing_evidence": [],
                "verification_plan": [],
                "evidence_citations": [],
                "boundary": {"local_mock_only": True, "provider": "mock", "model_calls_enabled": False},
            }
        )


def test_citation_checker_rejects_unknown_evidence_ids() -> None:
    packet = _packet()
    judgment = validate_llm_judgment(
        {
            "hypotheses": [{"label": "deploy regression", "confidence": 0.7, "evidence_citations": ["missing:evidence"]}],
            "recommended_route": "human_required",
            "safe_actions": [],
            "forbidden_actions_detected": [],
            "missing_evidence": [],
            "verification_plan": ["inspect cited logs"],
            "evidence_citations": ["missing:evidence"],
            "boundary": {"local_mock_only": True, "provider": "mock", "model_calls_enabled": False},
        }
    )

    result = check_evidence_citations(judgment, packet)

    assert result.valid is False
    assert result.unknown_citations == ("missing:evidence",)


def test_safety_gate_blocks_unsafe_actions_and_strips_non_mock_actions() -> None:
    packet = _packet()
    judgment = validate_llm_judgment(
        {
            "hypotheses": [{"label": "unsafe bait", "confidence": 0.8, "evidence_citations": [packet["evidence"][0]["id"]]}],
            "recommended_route": "local_mock_auto_allowed",
            "safe_actions": ["mock.get_error_context", "kubectl rollout restart deployment/prod", "aws autoscaling update"],
            "forbidden_actions_detected": [],
            "missing_evidence": [],
            "verification_plan": ["check metrics"],
            "evidence_citations": [packet["evidence"][0]["id"]],
            "boundary": {"local_mock_only": True, "provider": "mock", "model_calls_enabled": False},
        }
    )

    gated = apply_judgment_safety_gate(judgment, packet)

    assert gated.final_route == "blocked"
    assert gated.allowed_safe_actions == ("mock.get_error_context",)
    assert any("unsafe action" in reason.lower() or "non-mock" in reason.lower() for reason in gated.gate_reasons)


def test_runner_blocks_prompt_injection_production_restart_without_action_execution() -> None:
    packet = _packet()
    result = run_llm_judgment_from_packet(packet, provider=MockLLMJudgmentProvider())
    payload = result.to_dict()
    encoded = json.dumps(payload, sort_keys=True)

    assert payload["provider"] == "mock"
    assert payload["local_mock_only"] is True
    assert payload["model_calls_enabled"] is False
    assert payload["action_execution_enabled"] is False
    assert payload["safety_gate"]["final_route"] in {"blocked", "human_required"}
    assert "kubectl" in encoded.lower() or "production" in encoded.lower()
    assert all(str(action).startswith("mock.") for action in payload["safety_gate"]["allowed_safe_actions"])
