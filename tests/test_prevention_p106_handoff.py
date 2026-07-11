from __future__ import annotations

import copy
import hashlib
import importlib
import json
from pathlib import Path
from typing import Any

import pytest

SHARED_CASES = Path("tests/fixtures/p106_shared_fail_closed_cases.json")


def _api() -> Any:
    try:
        return importlib.import_module("app.services.prevention_p106_handoff")
    except ModuleNotFoundError as exc:
        pytest.fail(f"P107 RED: missing canonical P106 handoff implementation ({exc}).", pytrace=False)


def _benchmark_api() -> Any:
    return importlib.import_module("app.services.preventive_action_benchmark")


def _sha256_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()


def _complete_shared_fail_closed_results() -> list[dict[str, Any]]:
    safety_api = importlib.import_module("app.services.preventive_safety_gate")
    rows = []
    for case in json.loads(SHARED_CASES.read_text(encoding="utf-8"))["cases"]:
        result = safety_api.evaluate_preventive_safety_gate(case).to_dict()
        rows.append(
            {
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
        )
    return rows


def _complete_p106_evidence() -> dict[str, Any]:
    selected = {
        "candidate_id": "preventive.mock.rollback_pr",
        "capability_id": "preventive.mock.rollback_pr",
        "action_type": "mock.rollback_pr",
        "registry_hash": "sha256:registry-current",
        "safe_environment_allowlist": ["staging", "test"],
        "execution_enabled": False,
        "simulation_only": True,
        "p107_required_for_execution": True,
    }
    evidence = {
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
        "arm_outcomes": [
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
        ],
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
        "benchmark_id": "p106-benchmark-current",
        "benchmark_run_identity": "benchmark-run-current",
        "p105_p106_prerequisite_identity": "p105:p106:identity",
        "p107_unlocked": False,
    }
    gate = _benchmark_api().evaluate_p107_unlock_gate(evidence)
    evidence["benchmark_run_identity"] = gate.get("benchmark_run_identity", evidence["benchmark_run_identity"])
    return evidence


def _validate(evidence: dict[str, Any], **kwargs: Any) -> Any:
    validator = getattr(_api(), "validate_canonical_p106_handoff", None)
    if validator is None:
        pytest.fail("P107 RED: expose validate_canonical_p106_handoff(evidence, ...).", pytrace=False)
    return validator(evidence, **kwargs)


def test_recomputes_p107_gate_from_complete_canonical_p106_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    handoff_api = _api()
    calls: list[dict[str, Any]] = []

    def recompute_spy(evidence: dict[str, Any]) -> dict[str, Any]:
        calls.append(copy.deepcopy(evidence))
        return {"p107_gate_eligible": True, "p107_unlocked": False, "operands": {"spy": True}}

    monkeypatch.setattr(handoff_api, "evaluate_p107_unlock_gate", recompute_spy, raising=False)

    result = _validate(_complete_p106_evidence(), registry_hash="sha256:registry-current", environment="staging")

    assert calls
    assert result.canonical_p106_gate_recomputed is True
    assert result.caller_supplied_p107_gate_eligible_used is False
    assert result.accepted is True


def test_rejects_caller_supplied_p107_gate_eligible_without_complete_evidence() -> None:
    result = _validate({"p107_gate_eligible": True}, registry_hash="sha256:registry-current", environment="staging")

    assert result.accepted is False
    assert result.stale_or_forged_executed_count == 0
    assert result.caller_supplied_p107_gate_eligible_used is False


def test_rejects_mismatched_copied_p107_gate_eligible(monkeypatch: pytest.MonkeyPatch) -> None:
    handoff_api = _api()
    monkeypatch.setattr(
        handoff_api,
        "evaluate_p107_unlock_gate",
        lambda evidence: {"p107_gate_eligible": False, "p107_unlocked": False, "operands": {"zero_harmful_actions": False}},
        raising=False,
    )
    evidence = _complete_p106_evidence()
    evidence["p107_gate_eligible"] = True

    result = _validate(evidence, registry_hash="sha256:registry-current", environment="staging")

    assert result.accepted is False
    assert result.recomputed_p107_gate_eligible is False
    assert result.stale_or_forged_executed_count == 0


def test_rejects_matching_copied_p107_gate_eligible(monkeypatch: pytest.MonkeyPatch) -> None:
    handoff_api = _api()
    monkeypatch.setattr(
        handoff_api,
        "evaluate_p107_unlock_gate",
        lambda evidence: {"p107_gate_eligible": True, "p107_unlocked": False, "operands": {"all": True}},
        raising=False,
    )
    evidence = _complete_p106_evidence()
    evidence["p107_gate_eligible"] = True

    result = _validate(evidence, registry_hash="sha256:registry-current", environment="staging")

    assert result.accepted is False
    assert "caller supplied" in " ".join(result.reasons).lower()


def test_preserves_p106_unlocked_false(monkeypatch: pytest.MonkeyPatch) -> None:
    handoff_api = _api()
    monkeypatch.setattr(
        handoff_api,
        "evaluate_p107_unlock_gate",
        lambda evidence: {"p107_gate_eligible": True, "p107_unlocked": False, "operands": {"all": True}},
        raising=False,
    )
    accepted_evidence = _complete_p106_evidence()

    accepted = _validate(accepted_evidence, registry_hash="sha256:registry-current", environment="staging")

    forged_evidence = _complete_p106_evidence()
    forged_evidence["p107_unlocked"] = True
    rejected = _validate(forged_evidence, registry_hash="sha256:registry-current", environment="staging")

    assert accepted.accepted is True
    assert rejected.accepted is False
    assert "p107_unlocked" in " ".join(rejected.reasons)


@pytest.mark.parametrize(
    "missing_key",
    [
        "shared_fail_closed_results",
        "shared_fail_closed_fixture_path",
        "shared_fail_closed_fixture_hash",
        "arm_outcomes",
        "mutation_shaped_plans",
        "harmful_taxonomy_counts",
        "authority",
        "benchmark_fresh",
        "arm_fingerprint_comparable",
        "benchmark_run_identity",
    ],
)
def test_rejects_missing_canonical_p106_fields(missing_key: str) -> None:
    evidence = _complete_p106_evidence()
    evidence.pop(missing_key)

    result = _validate(evidence, registry_hash="sha256:registry-current", environment="staging")

    assert result.accepted is False
    assert result.stale_or_forged_executed_count == 0


@pytest.mark.parametrize(
    "mutate",
    [
        lambda evidence: evidence.__setitem__("benchmark_run_identity", "stale-run"),
        lambda evidence: evidence.__setitem__("shared_fail_closed_fixture_hash", "sha256:forged"),
        lambda evidence: evidence.__setitem__("arm_outcomes", []),
        lambda evidence: evidence.__setitem__("p105_p106_prerequisite_identity", "copied-boolean-only"),
        lambda evidence: evidence["arm_outcomes"][0]["result"]["selected_candidate"].__setitem__("execution_enabled", True),
        lambda evidence: evidence["arm_outcomes"][0]["result"]["selected_candidate"].__setitem__("simulation_only", False),
        lambda evidence: evidence["arm_outcomes"][0]["result"]["selected_candidate"].__setitem__("p107_required_for_execution", False),
        lambda evidence: evidence["arm_outcomes"][0]["result"]["selected_candidate"].__setitem__("registry_hash", "sha256:stale-registry"),
        lambda evidence: evidence["arm_outcomes"][0]["result"]["selected_candidate"].__setitem__("safe_environment_allowlist", ["prod"]),
    ],
)
def test_rejects_stale_or_forged_p105_p106_evidence(mutate: Any) -> None:
    evidence = _complete_p106_evidence()
    mutate(evidence)

    result = _validate(evidence, registry_hash="sha256:registry-current", environment="staging")

    assert result.accepted is False
    assert result.stale_or_forged_executed_count == 0
