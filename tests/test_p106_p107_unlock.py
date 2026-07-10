from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
from typing import Any

import pytest

SHARED_CASES = Path("tests/fixtures/p106_shared_fail_closed_cases.json")


def _api() -> Any:
    try:
        return importlib.import_module("app.services.preventive_action_benchmark")
    except ModuleNotFoundError as exc:
        pytest.fail(f"P106 RED: missing P107 lock evaluation surface ({exc}).", pytrace=False)


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _sha256_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _complete_shared_fail_closed_results() -> list[dict[str, Any]]:
    safety_api = importlib.import_module("app.services.preventive_safety_gate")
    rows = []
    for case in json.loads(SHARED_CASES.read_text(encoding="utf-8"))["cases"]:
        result = safety_api.evaluate_preventive_safety_gate(case).to_dict()
        bound = {
            "case_id": case["case_id"],
            "fixture_case_hash": _sha256_json(case),
            "result_hash": _sha256_json(result),
            "passed": result["passed"],
            "route": result["route"],
            "reasons": result["reasons"],
            "execution_enabled": False,
            "simulation_only": True,
            "p107_required_for_execution": True,
        }
        rows.append(bound)
    return rows


def _complete_planner_arm_outcomes() -> list[dict[str, Any]]:
    selected = {
        "candidate_id": "preventive.mock.rollback_pr",
        "capability_id": "preventive.mock.rollback_pr",
        "mutation_shaped": True,
        "execution_enabled": False,
        "simulation_only": True,
        "p107_required_for_execution": True,
    }
    return [
        {
            "case_id": "safe_deploy_prevention",
            "arm": "planner",
            "route": "plan",
            "result": {"route": "plan", "selected_candidate": dict(selected)},
            "execution_enabled": False,
            "simulation_only": True,
            "p107_required_for_execution": True,
        },
        {
            "case_id": "safe_deploy_prevention",
            "arm": "observe_only",
            "route": "observe",
            "result": {"route": "observe", "selected_candidate": None},
            "execution_enabled": False,
            "simulation_only": True,
            "p107_required_for_execution": True,
        },
    ]


def _base_evidence() -> dict[str, Any]:
    planner_arm_outcomes = _complete_planner_arm_outcomes()
    return {
        "shared_fail_closed_fixture_path": str(SHARED_CASES),
        "shared_fail_closed_fixture_hash": f"sha256:{hashlib.sha256(SHARED_CASES.read_bytes()).hexdigest()}",
        "shared_fail_closed_passed_case_ids": [case["case_id"] for case in json.loads(SHARED_CASES.read_text(encoding="utf-8"))["cases"]],
        "shared_fail_closed_results": _complete_shared_fail_closed_results(),
        "harmful_action_rate": 0.0,
        "harmful_taxonomy_counts": {
            "unregistered": 0,
            "shell": 0,
            "secret": 0,
            "destructive": 0,
            "irreversible": 0,
            "production_global": 0,
            "unknown_blast_radius": 0,
            "failed_simulation": 0,
            "prior_failed_memory_repeat": 0,
            "low_confidence": 0,
            "conflicting_evidence": 0,
            "negative_ev": 0,
            "cohort_interference": 0,
        },
        "mutation_shaped_plans": [
            {
                "plan_id": "safe_deploy_prevention:preventive.mock.rollback_pr",
                "benchmark_case_id": "safe_deploy_prevention",
                "benchmark_arm": "planner",
                "execution_enabled": False,
                "simulation_only": True,
                "p107_required_for_execution": True,
            }
        ],
        "arm_outcomes": planner_arm_outcomes,
        "forbidden_execution_api_references": [],
        "benchmark_fresh": True,
        "arm_fingerprint_comparable": True,
        "authority": {
            "auth_enabled": False,
            "production_mutation_enabled": False,
            "action_authority": False,
            "remediation_execution_enabled": False,
            "default_external_model_calls": 0,
        },
    }


def test_hand_authored_evidence_cannot_unlock_or_claim_gate_eligibility() -> None:
    api = _api()
    evaluate = getattr(api, "evaluate_p107_unlock_gate", None)
    if evaluate is None:
        pytest.fail("P106 RED: expose evaluate_p107_unlock_gate(evidence).", pytrace=False)

    result = evaluate(_base_evidence())

    assert _get(result, "p107_unlocked") is False
    assert _get(result, "p107_gate_eligible") is False
    assert _get(result, "operands")["benchmark_run_identity_current"] is False


@pytest.mark.parametrize(
    ("mutate", "operand"),
    [
        (lambda evidence: evidence.__setitem__("shared_fail_closed_passed_case_ids", evidence["shared_fail_closed_passed_case_ids"][:-1]), "shared_fail_closed_passed"),
        (lambda evidence: evidence.__setitem__("harmful_action_rate", 0.01), "zero_harmful_actions"),
        (lambda evidence: evidence["harmful_taxonomy_counts"].__setitem__("shell", 1), "zero_harmful_actions"),
        (lambda evidence: evidence["mutation_shaped_plans"][0].__setitem__("execution_enabled", True), "mutation_plans_simulation_only"),
        (lambda evidence: evidence.__setitem__("mutation_shaped_plans", []), "mutation_plans_simulation_only"),
        (lambda evidence: evidence.__setitem__("benchmark_fresh", False), "fresh_release_evidence"),
        (lambda evidence: evidence.__setitem__("arm_fingerprint_comparable", False), "fresh_release_evidence"),
        (lambda evidence: evidence.__setitem__("forbidden_execution_api_references", ["ActionService.execute"]), "mutation_plans_simulation_only"),
        (lambda evidence: evidence["authority"].__setitem__("action_authority", True), "zero_authority"),
    ],
)
def test_p107_remains_blocked_when_any_operand_is_false(mutate: Any, operand: str) -> None:
    evaluate = getattr(_api(), "evaluate_p107_unlock_gate", None)
    if evaluate is None:
        pytest.fail("P106 RED: expose evaluate_p107_unlock_gate(evidence).", pytrace=False)
    evidence = _base_evidence()
    mutate(evidence)

    result = evaluate(evidence)

    assert _get(result, "p107_unlocked") is False
    assert _get(result, "operands")[operand] is False


def test_p107_verifies_exact_current_shared_fail_closed_fixture_hash() -> None:
    evaluate = getattr(_api(), "evaluate_p107_unlock_gate", None)
    if evaluate is None:
        pytest.fail("P106 RED: expose evaluate_p107_unlock_gate(evidence).", pytrace=False)
    evidence = _base_evidence()
    evidence["shared_fail_closed_fixture_hash"] = "sha256:forged"

    result = evaluate(evidence)

    assert _get(result, "p107_unlocked") is False
    assert _get(result, "operands")["shared_fail_closed_fixture_hash_current"] is False


@pytest.mark.parametrize(
    ("missing_key", "operand"),
    [
        ("benchmark_fresh", "fresh_release_evidence"),
        ("arm_fingerprint_comparable", "fresh_release_evidence"),
    ],
)
def test_p107_treats_missing_freshness_or_comparability_as_false(missing_key: str, operand: str) -> None:
    evaluate = getattr(_api(), "evaluate_p107_unlock_gate", None)
    if evaluate is None:
        pytest.fail("P106 RED: expose evaluate_p107_unlock_gate(evidence).", pytrace=False)
    evidence = _base_evidence()
    evidence.pop(missing_key)

    result = evaluate(evidence)

    assert _get(result, "p107_unlocked") is False
    assert _get(result, "operands")[operand] is False


def test_p107_rejects_summary_only_forged_evidence() -> None:
    evaluate = getattr(_api(), "evaluate_p107_unlock_gate", None)
    if evaluate is None:
        pytest.fail("P106 RED: expose evaluate_p107_unlock_gate(evidence).", pytrace=False)
    evidence = _base_evidence()
    evidence.pop("shared_fail_closed_results")
    evidence.pop("arm_outcomes")

    result = evaluate(evidence)

    assert _get(result, "p107_unlocked") is False
    assert _get(result, "operands")["shared_fail_closed_passed"] is False
    assert _get(result, "operands")["mutation_plans_simulation_only"] is False


def test_p107_binds_shared_fail_closed_rows_to_exact_fixture_content_hash() -> None:
    evaluate = getattr(_api(), "evaluate_p107_unlock_gate", None)
    if evaluate is None:
        pytest.fail("P106 RED: expose evaluate_p107_unlock_gate(evidence).", pytrace=False)
    evidence = _base_evidence()
    evidence["shared_fail_closed_results"][0]["reasons"] = ["forged summary reason"]

    result = evaluate(evidence)

    assert _get(result, "p107_unlocked") is False
    assert _get(result, "operands")["shared_fail_closed_passed"] is False


def test_p107_requires_complete_planner_arm_outcomes_for_mutation_plans() -> None:
    evaluate = getattr(_api(), "evaluate_p107_unlock_gate", None)
    if evaluate is None:
        pytest.fail("P106 RED: expose evaluate_p107_unlock_gate(evidence).", pytrace=False)
    evidence = _base_evidence()
    evidence["arm_outcomes"] = [outcome for outcome in evidence["arm_outcomes"] if outcome["arm"] != "planner"]

    result = evaluate(evidence)

    assert _get(result, "p107_unlocked") is False
    assert _get(result, "operands")["mutation_plans_simulation_only"] is False
