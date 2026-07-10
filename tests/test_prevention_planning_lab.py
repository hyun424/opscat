from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path
from typing import Any

import pytest

LAB_CASES = Path("evals/prevention/p106_treatment_control_cases.json")


def _api() -> Any:
    try:
        return importlib.import_module("app.services.prevention_planning_lab")
    except ModuleNotFoundError as exc:
        pytest.fail(f"P106 RED: missing prevention planning lab module ({exc}).", pytrace=False)


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _cases() -> list[dict[str, Any]]:
    return list(json.loads(LAB_CASES.read_text(encoding="utf-8"))["cases"])


def test_lab_fixture_has_no_scorer_choice_in_public_initial_state() -> None:
    payload = json.loads(LAB_CASES.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "p106.treatment_control_cases.v1"
    for case in payload["cases"]:
        public_text = json.dumps(case["public_initial_state"], sort_keys=True)
        assert "scorer_only" not in public_text
        assert "expected_operator_choice" not in public_text


def test_equivalent_arms_have_identical_recomputed_initial_fingerprint() -> None:
    api = _api()
    compute = getattr(api, "compute_initial_condition_fingerprint", None)
    if compute is None:
        pytest.fail("P106 RED: expose compute_initial_condition_fingerprint(public_initial_state, seed).", pytrace=False)
    case = next(item for item in _cases() if item["case_id"] == "equivalent_initial_fingerprints")

    fingerprints = [compute(case["public_initial_state"], deterministic_seed=case["deterministic_seed"], arm=arm["arm"]) for arm in case["arms"]]

    assert len(set(fingerprints)) == 1


@pytest.mark.parametrize("case", _cases(), ids=lambda case: case["case_id"])
def test_lab_rejects_non_comparable_cases_before_planner_or_scorer_execution(case: dict[str, Any]) -> None:
    api = _api()
    evaluate = getattr(api, "evaluate_treatment_control_case", None)
    if evaluate is None:
        pytest.fail("P106 RED: expose evaluate_treatment_control_case(case).", pytrace=False)

    result = evaluate(copy.deepcopy(case))

    assert _get(result, "comparable") is case["expected_comparable"]
    if not case["expected_comparable"]:
        assert _get(result, "planner_executed") is False
        assert _get(result, "scorer_executed") is False
        assert _get(result, "rejection_reason")


def test_recomputing_only_declared_fingerprint_cannot_mask_arm_specific_state_mutation() -> None:
    api = _api()
    evaluate = getattr(api, "evaluate_treatment_control_case", None)
    if evaluate is None:
        pytest.fail("P106 RED: expose evaluate_treatment_control_case(case).", pytrace=False)
    case = next(item for item in _cases() if item["case_id"] == "arm_specific_mutation_rejected")
    for arm in case["arms"]:
        arm["declared_initial_condition_fingerprint"] = "same-forged-value"

    result = evaluate(case)

    assert _get(result, "comparable") is False
    assert "fingerprint" in _get(result, "rejection_reason", "")
