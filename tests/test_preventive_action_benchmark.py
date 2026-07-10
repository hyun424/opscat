from __future__ import annotations

import importlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from tests.fixtures.p106_p105_release_archive import (
    P105_REAL_DERIVED_ARCHIVE_MEMBERS,
    safe_extract_p105_release_archive,
)

BENCHMARK_CASES = Path("evals/prevention/p106_benchmark_cases.json")
SHARED_CASES = Path("tests/fixtures/p106_shared_fail_closed_cases.json")


def _api() -> Any:
    try:
        return importlib.import_module("app.services.preventive_action_benchmark")
    except ModuleNotFoundError as exc:
        pytest.fail(f"P106 RED: missing preventive action benchmark module ({exc}).", pytrace=False)


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def test_benchmark_fixture_requires_regret_harm_taxonomy_and_zero_authority() -> None:
    payload = json.loads(BENCHMARK_CASES.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "p106.benchmark_cases.v1"
    assert {"planner_regret", "harmful_action_rate", "safe_fallback_rate"} <= set(payload["required_metrics"])
    assert {
        "unregistered",
        "shell",
        "secret",
        "destructive",
        "irreversible",
        "production_global",
        "unknown_blast_radius",
        "failed_simulation",
        "prior_failed_memory_repeat",
        "low_confidence",
        "conflicting_evidence",
        "negative_ev",
        "cohort_interference",
    } == set(payload["harmful_taxonomy"])
    assert all(value in (False, 0) for value in payload["authority"].values())


def test_benchmark_consumes_the_shared_fail_closed_fixture() -> None:
    benchmark = json.loads(BENCHMARK_CASES.read_text(encoding="utf-8"))
    shared_case_ids = {case["case_id"] for case in json.loads(SHARED_CASES.read_text(encoding="utf-8"))["cases"]}

    shared_refs = [case for case in benchmark["cases"] if case.get("shared_fail_closed_fixture") == str(SHARED_CASES)]

    assert shared_refs
    assert shared_case_ids


def test_benchmark_fixture_declares_real_derived_p105_archive_and_override_contract() -> None:
    payload = json.loads(BENCHMARK_CASES.read_text(encoding="utf-8"))
    fixture = payload["p105_release_qualified_fixture"]

    assert fixture["archive_path"] == "evals/prevention/p105_release_qualified_real_derived.tar.gz"
    assert fixture["archive_sha256"] == "sha256:6aaf35285f03cc7fe68b036a8172dba1615d1e5131939b2d8ef26787dd5c7342"
    assert fixture["archive_size_bytes"] == 2_012_888
    assert fixture["artifact_relative_path"] == "p105-release-qualified-rows.json"
    assert fixture["content_list"] == list(P105_REAL_DERIVED_ARCHIVE_MEMBERS)
    assert fixture["provenance"]["raw_source_downloads_included"] is False
    assert fixture["provenance"]["credentials_included"] is False
    assert fixture["provenance"]["env_files_included"] is False
    assert fixture["scorer_boundary"] == {
        "repository_visible_for_reproducibility": True,
        "planner_access": False,
        "purpose": "P105 validator-only held-out scoring; never copied into P106 planner inputs or outputs",
    }
    assert fixture["planner_override_contract"] == {
        "placeholder": "__P105_RELEASE_ARTIFACT_PATH__",
        "override_field": "p105_artifact_path",
        "required_api_behavior": "benchmark runner must safely extract archive to tmp and replace placeholder with extracted artifact path before planner invocation",
        "current_status": "IMPLEMENTED: SHA-pinned archive override is validated without mutating source evidence",
    }


def test_benchmark_fixture_keeps_scorer_only_expected_outcome_out_of_planner_input() -> None:
    payload = json.loads(BENCHMARK_CASES.read_text(encoding="utf-8"))
    case = next(item for item in payload["cases"] if item["case_id"] == "real_derived_p105_deploy_mutation_simulation")

    assert case["planner_input"]["p104_evidence"]["sufficient_for_policy_handoff"] is True
    assert case["planner_input"]["p105_artifact_path"] == "__P105_RELEASE_ARTIFACT_PATH__"
    assert case["planner_input"]["advisory_capabilities"] == ["preventive.mock.rollback_pr"]
    assert case["expected_mutation_shaped_simulation_only"] is True
    assert case["scorer_only_expected_outcome"]["expected_capability"] == "preventive.mock.rollback_pr"
    assert "scorer_only" not in json.dumps(case["planner_input"], sort_keys=True)
    assert "expected_capability" not in json.dumps(case["planner_input"], sort_keys=True)


def test_benchmark_api_override_replaces_p105_artifact_placeholder_for_real_derived_cases(tmp_path: Path) -> None:
    run = getattr(_api(), "run_preventive_action_benchmark", None)
    if run is None:
        pytest.fail("P106 RED: expose run_preventive_action_benchmark(cases_path).", pytrace=False)
    payload = json.loads(BENCHMARK_CASES.read_text(encoding="utf-8"))
    payload["cases"] = [
        case
        for case in payload["cases"]
        if case.get("case_id") == "real_derived_p105_deploy_mutation_simulation"
    ]
    cases_path = tmp_path / "real-derived-benchmark.json"
    cases_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    artifact = safe_extract_p105_release_archive(Path(payload["p105_release_qualified_fixture"]["archive_path"]), tmp_path / "p105")

    before = artifact.stat().st_mtime_ns
    result = run(cases_path, p105_artifact_override=artifact)

    assert _get(result, "scored") is True
    assert _get(result, "mutation_shaped_simulation_only_count") == 1
    assert artifact.stat().st_mtime_ns == before
    assert _get(result, "p105_prerequisite_artifact")["artifact_identity"]["valid"] is True


def test_benchmark_fails_before_scoring_when_arm_fingerprints_are_not_comparable(tmp_path: Path) -> None:
    api = _api()
    run = getattr(api, "run_preventive_action_benchmark", None)
    if run is None:
        pytest.fail("P106 RED: expose run_preventive_action_benchmark(cases_path).", pytrace=False)
    payload = json.loads(BENCHMARK_CASES.read_text(encoding="utf-8"))
    payload["cases"][0]["arms"] = ["planner", "observe_only"]
    payload["cases"][0]["declared_initial_condition_fingerprint"] = {"planner": "a", "observe_only": "b"}
    path = tmp_path / "mismatched-benchmark.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    result = run(path)

    assert _get(result, "scored") is False
    assert "fingerprint" in json.dumps(_get(result, "reasons", []), sort_keys=True)


def test_benchmark_reports_zero_harm_and_simulation_only_mutation_boundaries() -> None:
    run = getattr(_api(), "run_preventive_action_benchmark", None)
    if run is None:
        pytest.fail("P106 RED: expose run_preventive_action_benchmark(cases_path).", pytrace=False)

    result = run(BENCHMARK_CASES)

    assert _get(result, "harmful_action_rate") == 0.0
    assert all(value == 0 for value in _get(result, "harmful_taxonomy_counts", {}).values())
    assert _get(result, "authority") == {
        "auth_enabled": False,
        "production_mutation_enabled": False,
        "action_authority": False,
        "remediation_execution_enabled": False,
        "default_external_model_calls": 0,
    }
    for plan in _get(result, "mutation_shaped_plans", []):
        assert plan["execution_enabled"] is False
        assert plan["simulation_only"] is True
        assert plan["p107_required_for_execution"] is True


def test_benchmark_derives_results_by_running_planner_for_each_planner_arm(monkeypatch: pytest.MonkeyPatch) -> None:
    api = _api()
    run = getattr(api, "run_preventive_action_benchmark", None)
    if run is None:
        pytest.fail("P106 RED: expose run_preventive_action_benchmark(cases_path).", pytrace=False)
    planner_arm_count = sum(
        1
        for case in json.loads(BENCHMARK_CASES.read_text(encoding="utf-8"))["cases"]
        for arm in case["arms"]
        if arm == "planner"
    )
    calls: list[dict[str, Any]] = []

    class PlannerSpy:
        def plan(self, case: dict[str, Any]) -> dict[str, Any]:
            calls.append(case)
            return {
                "route": "observe",
                "selected_candidate": None,
                "execution_enabled": False,
                "simulation_only": True,
                "p107_required_for_execution": True,
                "reasons": ["spy planner arm"],
            }

    monkeypatch.setattr(api, "PreventiveActionPlanner", PlannerSpy, raising=False)

    result = run(BENCHMARK_CASES)

    assert len(calls) == planner_arm_count
    assert "p106-mutation-sample" not in json.dumps(_get(result, "mutation_shaped_plans", []), sort_keys=True)


def test_benchmark_rates_are_bounded_and_top_level_metrics_match_nested_metrics() -> None:
    run = getattr(_api(), "run_preventive_action_benchmark", None)
    if run is None:
        pytest.fail("P106 RED: expose run_preventive_action_benchmark(cases_path).", pytrace=False)

    result = run(BENCHMARK_CASES)
    metrics = _get(result, "metrics", {})
    rate_keys = [
        "planner_regret",
        "harmful_action_rate",
        "unnecessary_intervention_rate",
        "safe_fallback_rate",
        "policy_fail_closed_rate",
    ]

    for key in rate_keys:
        assert key in metrics
        assert 0.0 <= float(_get(result, key)) <= 1.0
        assert 0.0 <= float(metrics[key]) <= 1.0
        assert _get(result, key) == metrics[key]


def test_benchmark_rejects_scored_true_when_planner_arm_only_fails_missing_prerequisites(tmp_path: Path) -> None:
    run = getattr(_api(), "run_preventive_action_benchmark", None)
    if run is None:
        pytest.fail("P106 RED: expose run_preventive_action_benchmark(cases_path).", pytrace=False)
    payload = json.loads(BENCHMARK_CASES.read_text(encoding="utf-8"))
    payload["cases"] = [
        {
            "case_id": "planner_missing_p104_p105_is_not_scoreable",
            "arms": ["planner", "observe_only"],
            "declared_initial_condition_fingerprint": {"planner": "same", "observe_only": "same"},
            "expected_zero_harm": True,
        }
    ]
    path = tmp_path / "planner-missing-prereqs.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result = run(path)

    assert _get(result, "scored") is False
    assert "p104" in json.dumps(_get(result, "reasons", []), sort_keys=True).lower()
    assert "p105" in json.dumps(_get(result, "reasons", []), sort_keys=True).lower()


def test_benchmark_rejects_scored_true_when_no_planner_arm_has_eligible_evaluation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    api = _api()
    run = getattr(api, "run_preventive_action_benchmark", None)
    if run is None:
        pytest.fail("P106 RED: expose run_preventive_action_benchmark(cases_path).", pytrace=False)
    payload = json.loads(BENCHMARK_CASES.read_text(encoding="utf-8"))
    payload["cases"] = [
        {
            "case_id": "zero_eligible_planner_eval",
            "arms": ["planner", "observe_only"],
            "declared_initial_condition_fingerprint": {"planner": "same", "observe_only": "same"},
            "expected_zero_harm": True,
        }
    ]
    path = tmp_path / "zero-eligible.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    class AlwaysIneligiblePlanner:
        def plan(self, _case: dict[str, Any]) -> dict[str, Any]:
            return {
                "route": "blocked_fail_closed",
                "selected_candidate": None,
                "execution_enabled": False,
                "simulation_only": True,
                "p107_required_for_execution": True,
                "reasons": ["p104 missing", "p105 missing"],
            }

    monkeypatch.setattr(api, "PreventiveActionPlanner", AlwaysIneligiblePlanner, raising=False)

    result = run(path)

    assert _get(result, "scored") is False
    assert "zero eligible planner" in json.dumps(_get(result, "reasons", []), sort_keys=True).lower()


def test_benchmark_freshness_is_derived_from_artifact_timestamp(tmp_path: Path) -> None:
    run = getattr(_api(), "run_preventive_action_benchmark", None)
    if run is None:
        pytest.fail("P106 RED: expose run_preventive_action_benchmark(cases_path).", pytrace=False)
    path = tmp_path / "stale-benchmark.json"
    path.write_text(BENCHMARK_CASES.read_text(encoding="utf-8"), encoding="utf-8")
    stale_epoch = datetime(2020, 1, 1, tzinfo=UTC).timestamp()
    os.utime(path, (stale_epoch, stale_epoch))

    result = run(path)

    assert _get(result, "scored") is False
    assert _get(result, "benchmark_fresh") is False
    assert "stale" in json.dumps(_get(result, "reasons", []), sort_keys=True).lower()


def test_benchmark_planner_input_strips_scorer_only_fields_and_ignores_treatment_selected_capability(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    api = _api()
    run = getattr(api, "run_preventive_action_benchmark", None)
    if run is None:
        pytest.fail("P106 RED: expose run_preventive_action_benchmark(cases_path).", pytrace=False)
    treatment_cases = {
        "schema_version": "p106.treatment_control_cases.v1",
        "cases": [
            {
                "case_id": "treatment_label_must_not_pick_planner_input",
                "public_initial_state": {
                    "evidence_ids": ["ev-database-1"],
                    "environment": "staging",
                    "telemetry_window": "2026-07-10T00:00:00Z/2026-07-10T02:00:00Z",
                },
                "arms": [
                    {"arm": "treatment", "selected_capability": "preventive.report.generate"},
                    {"arm": "control", "selected_capability": "observe"},
                ],
                "scorer_only_expected_operator_choice": "treatment",
            }
        ],
    }
    treatment_path = tmp_path / "treatment-control.json"
    treatment_path.write_text(json.dumps(treatment_cases, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    payload = json.loads(BENCHMARK_CASES.read_text(encoding="utf-8"))
    payload["cases"] = [
        {
            "case_id": "scorer_label_input_selection_probe",
            "public_initial_state_ref": f"{treatment_path}#treatment_label_must_not_pick_planner_input",
            "arms": ["planner", "observe_only"],
            "declared_initial_condition_fingerprint": {"planner": "same", "observe_only": "same"},
            "expected_zero_harm": True,
        }
    ]
    path = tmp_path / "benchmark.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    planner_inputs: list[dict[str, Any]] = []

    class PlannerSpy:
        def plan(self, case: dict[str, Any]) -> dict[str, Any]:
            planner_inputs.append(case)
            return {
                "route": "observe",
                "selected_candidate": None,
                "execution_enabled": False,
                "simulation_only": True,
                "p107_required_for_execution": True,
                "reasons": ["spy"],
            }

    monkeypatch.setattr(api, "PreventiveActionPlanner", PlannerSpy, raising=False)

    run(path)

    assert planner_inputs
    public_input = json.dumps(planner_inputs, sort_keys=True)
    assert "scorer_only" not in public_input
    assert "preventive.report.generate" not in public_input
