from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

LLM_CASES = Path("evals/prevention/p106_llm_advisory_cases.json")
REGISTRY = Path("evals/prevention/p106_capability_registry.json")


def _api() -> Any:
    try:
        return importlib.import_module("app.services.preventive_action_llm_adapter")
    except ModuleNotFoundError as exc:
        pytest.fail(f"P106 RED: missing preventive action LLM adapter module ({exc}).", pytrace=False)


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _cases() -> list[dict[str, Any]]:
    return list(json.loads(LLM_CASES.read_text(encoding="utf-8"))["cases"])


def test_llm_fixture_declares_mock_provider_and_contains_no_secrets() -> None:
    payload = json.loads(LLM_CASES.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "p106.llm_advisory_cases.v1"
    assert payload["provider_mode"] == "mock_by_default"
    assert "secret" not in json.dumps(payload, sort_keys=True).lower().replace("secret request", "")


@pytest.mark.parametrize("case", _cases(), ids=lambda case: case["case_id"])
def test_llm_advisory_schema_accepts_only_registered_non_authoritative_capabilities(case: dict[str, Any]) -> None:
    api = _api()
    validate = getattr(api, "validate_llm_advisory_packet", None)
    if validate is None:
        pytest.fail("P106 RED: expose validate_llm_advisory_packet(packet, registry_path).", pytrace=False)

    result = validate(case["provider_output"], registry_path=REGISTRY)

    assert _get(result, "valid") is case["expected_valid"]
    assert _get(result, "can_override_policy", False) is False
    assert _get(result, "can_set_expected_value", False) is False
    assert _get(result, "can_unlock_p107", False) is False
    assert _get(result, "default_external_model_calls", 0) == 0


@pytest.mark.parametrize(
    "provider_output",
    [
        {"schema_version": "p106.llm_advisory.v1", "proposals": [{"capability_id": "preventive.report.generate", "raw_action_type": "database.mutate"}]},
        {"schema_version": "p106.llm_advisory.v1", "proposals": [{"capability_id": "preventive.report.generate", "target_environment": "production"}]},
        {"schema_version": "p106.llm_advisory.v1", "proposals": [{"capability_id": "preventive.report.generate", "forecast_probability": 0.99}]},
        {"schema_version": "p106.llm_advisory.v1", "proposals": [{"capability_id": "preventive.report.generate"}, {"capability_id": "preventive.report.generate"}]},
    ],
)
def test_llm_adapter_rejects_raw_actions_production_confidence_override_and_duplicates(provider_output: dict[str, Any]) -> None:
    validate = getattr(_api(), "validate_llm_advisory_packet", None)
    if validate is None:
        pytest.fail("P106 RED: expose validate_llm_advisory_packet(packet, registry_path).", pytrace=False)

    result = validate(provider_output, registry_path=REGISTRY)

    assert _get(result, "valid") is False
    assert _get(result, "route") in {"deterministic_fallback", "blocked_fail_closed"}
