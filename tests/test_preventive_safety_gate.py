from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

SHARED_CASES = Path("tests/fixtures/p106_shared_fail_closed_cases.json")


def _api() -> Any:
    try:
        return importlib.import_module("app.services.preventive_safety_gate")
    except ModuleNotFoundError as exc:
        pytest.fail(f"P106 RED: missing shared preventive safety gate module ({exc}).", pytrace=False)


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _cases() -> list[dict[str, Any]]:
    payload = json.loads(SHARED_CASES.read_text(encoding="utf-8"))
    return list(payload["cases"])


def test_shared_fail_closed_fixture_has_unique_required_categories() -> None:
    payload = json.loads(SHARED_CASES.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "p106.shared_fail_closed_cases.v1"
    case_ids = [case["case_id"] for case in payload["cases"]]
    assert len(case_ids) == len(set(case_ids))
    assert {
        "production",
        "critical_severity",
        "low_confidence",
        "conflicting_evidence",
        "ambiguity",
        "failed_simulation",
        "non_local_blast_radius",
        "rollback",
        "unknown_action",
        "prohibited_action",
        "secret",
        "registry_hash",
        "incident_memory",
    } <= {case["category"] for case in payload["cases"]}


@pytest.mark.parametrize("case", _cases(), ids=lambda case: case["case_id"])
def test_every_shared_fail_closed_case_blocks_with_typed_gate_result(case: dict[str, Any]) -> None:
    api = _api()
    evaluator = getattr(api, "evaluate_preventive_safety_gate", None)
    result_type = getattr(api, "PreventiveSafetyGateResult", None)
    if evaluator is None or result_type is None:
        pytest.fail("P106 RED: expose PreventiveSafetyGateResult and evaluate_preventive_safety_gate(case).", pytrace=False)

    result = evaluator(case)

    assert isinstance(result, result_type)
    assert _get(result, "passed") is False
    assert _get(result, "route") in {"observe", "escalate", "blocked_fail_closed"}
    assert _get(result, "execution_enabled") is False
    assert _get(result, "simulation_only") is True
    assert _get(result, "p107_required_for_execution") is True
    assert case["expected_reason"] in json.dumps(_get(result, "reasons", []), sort_keys=True)


def test_positive_caller_booleans_cannot_forge_authoritative_engine_allow() -> None:
    result = _api().evaluate_preventive_safety_gate(
        {
            "action_type": "unknown",
            "environment": "staging",
            "confidence": 0.99,
            "policy_allowed": True,
            "simulation_allowed": True,
            "simulation_status": "passed",
            "blast_radius_scope": "local",
            "rollback_available": True,
        }
    )

    assert _get(result, "passed") is False
    assert "unknown action" in json.dumps(_get(result, "reasons", []), sort_keys=True)
