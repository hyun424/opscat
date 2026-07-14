from __future__ import annotations

import importlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from app.services.p137_contracts import (
    ALLOWED_REQUEST_CATALOG,
    EVALUATOR_ACTIVITY_KEYS,
    FORBIDDEN_AUTHORITY_KEYS,
    RESOURCE_USAGE_KEYS,
    RUNTIME_ACTIVITY_KEYS,
    zero_forbidden_authority,
    zero_runtime_activity,
)
from scripts.run_p137_local_triage import P137ProfileError, _validate_external_final_review, current_p137_source_hashes
from tests.fixtures.p137.builders import P137_SOURCE_SCOPE, TEST_SOURCE_BINDINGS, final_implementation_review, local_triage_profile, release_evidence_stub, runtime_inputs


def _runner_api(*names: str) -> Any:
    try:
        module = importlib.import_module("app.services.p137_runner")
    except ModuleNotFoundError as exc:
        pytest.fail(f"missing P137 runner module/API: app.services.p137_runner ({exc})")
    missing = [name for name in names if not hasattr(module, name)]
    if missing:
        pytest.fail(f"missing P137 runner module/API: {', '.join(missing)}")
    return module


def _error() -> type[Exception]:
    return _runner_api("P137RunnerError").P137RunnerError


def _frozen_release(tmp_path: Path, *, runtime_factory: Any | None = None) -> dict[str, Any]:
    runner = _runner_api("run_p137_preliminary_matrix", "run_p137_release_matrix")
    release = importlib.import_module("app.services.p137_release_evidence")
    profile = local_triage_profile()
    profile_hash = release.p137_profile_hash(profile)
    fixture_hash = release.p137_fixture_hash(profile)
    matrix = runner.run_p137_preliminary_matrix(
        tmp_path,
        runtime_factory=runtime_factory or (lambda case_id: runtime_inputs(tmp_path / case_id, case_id)),
    )
    manifest = release.build_p137_freeze_manifest(
        source_bindings=TEST_SOURCE_BINDINGS,
        profile=profile,
        matrix_hash=matrix["matrix_hash"],
        case_input_hash=matrix["case_input_hash"],
        case_config_hash=matrix["case_config_hash"],
        case_evidence_hash=matrix["case_evidence_hash"],
    )
    review = final_implementation_review(TEST_SOURCE_BINDINGS)
    review["reviewed_profile_hash"] = profile_hash
    review["reviewed_fixture_hash"] = fixture_hash
    review["reviewed_matrix_hash"] = matrix["matrix_hash"]
    from app.services.p110_evaluation import stable_hash

    review["implementation_review_hash"] = stable_hash({key: item for key, item in review.items() if key != "implementation_review_hash"})
    return runner.run_p137_release_matrix(
        tmp_path,
        canonical_matrix=matrix,
        freeze_manifest=manifest,
        source_bindings=TEST_SOURCE_BINDINGS,
        final_implementation_review=review,
        expected_profile_hash=profile_hash,
        expected_fixture_hash=fixture_hash,
    )


def test_runner_executes_fixed_60_case_matrix_from_runtime_inputs(tmp_path: Path) -> None:
    api = _runner_api("run_p137_preliminary_matrix")
    calls: list[str] = []

    def factory(case_id: str) -> dict[str, Any]:
        calls.append(case_id)
        return runtime_inputs(tmp_path / case_id, case_id)

    result = api.run_p137_preliminary_matrix(
        tmp_path,
        runtime_factory=factory,
    )

    assert calls == [f"p137-case-{index:02d}" for index in range(1, 61)]
    assert result["status"] == "p137_preliminary_matrix_frozen"
    assert len(result["cases"]) == 60
    assert {case["expected_label"] for case in result["cases"] if case["expected_label"] != "none"} >= {
        "confirmed_incident",
        "insufficient_evidence",
        "benign_anomaly",
        "aborted_fail_closed",
    }
    assert {case["provider_profile"] for case in result["cases"][:5]} == {
        "prometheus",
        "loki",
        "grafana",
        "sentry",
        "opentelemetry",
    }
    assert "provider_profiles" not in result
    assert "original_provider_artifact_reads" not in result
    assert result["case_config_hash"].startswith("sha256:")
    assert result["case_config_hash"] != result["case_input_hash"]


def test_real_p136_ingest_cases_process_exact_validator_atoms(tmp_path: Path) -> None:
    from app.services.p137_p136_handoff import validate_p136_handoff_bundle

    for case_id in ("p137-case-02", "p137-case-03"):
        runtime = runtime_inputs(tmp_path / case_id, case_id)
        validated = validate_p136_handoff_bundle(
            runtime["canonical_handoff_bundle_bytes"],
            config=runtime["validated_p136_config"],
        )

        assert runtime["input_authenticity"] == "p136_validator_exact"
        assert runtime["classification_atoms"] == validated["evidence_atoms"]
        assert runtime["atoms"] == validated["evidence_atoms"]
        assert not any(str(key).startswith("_p136_validation_") for key in runtime)

    synthetic = runtime_inputs(tmp_path / "p137-case-01", "p137-case-01")
    assert synthetic["input_authenticity"] == "component_fixture"
    assert "validated_p136_config" not in synthetic


def test_case_input_freeze_binds_complete_runtime_contract_and_probe_identity(tmp_path: Path) -> None:
    api = _runner_api("run_p137_preliminary_matrix", "_case_input_binding")
    runtime = runtime_inputs(tmp_path / "case", "p137-case-01")
    binding = api._case_input_binding("p137-case-01", runtime)

    assert {
        "canonical_handoff_bundle_bytes",
        "canonical_promotion_bytes",
        "atoms",
        "classification_atoms",
        "request_budget",
        "request_parameters_by_catalog",
        "expected_runtime_activity",
        "expected_evaluator_activity",
        "expected_resource_usage",
        "effective_p137_config",
        "runtime_probe",
    } <= set(binding["bindings"])
    assert binding["bindings"]["runtime_probe"]["kind"] == "callable"

    tampered = dict(runtime)
    tampered["request_budget"] = {**runtime["request_budget"], "max_output_records": 1}
    assert api._case_input_binding("p137-case-01", tampered)["runtime_input_hash"] != binding["runtime_input_hash"]

    from app.services.p137_contracts import build_triage_agent_config

    config_input = {
        key: deepcopy(value)
        for key, value in runtime["effective_p137_config"].items()
        if key not in {"schema_version", "config_hash"}
    }
    config_input["limits"]["max_correlation_window_ms"] += 1
    tampered["effective_p137_config"] = build_triage_agent_config(config_input)
    tampered_binding = api._case_input_binding("p137-case-01", tampered)
    assert tampered_binding["bindings"]["effective_p137_config"]["config_hash"] != binding["bindings"]["effective_p137_config"]["config_hash"]
    assert tampered_binding["runtime_input_hash"] != binding["runtime_input_hash"]


def test_runner_rejects_observation_when_independent_evaluator_contract_is_wrong(tmp_path: Path) -> None:
    api = _runner_api("run_p137_preliminary_matrix")

    def factory(case_id: str) -> dict[str, Any]:
        runtime = runtime_inputs(tmp_path / case_id, case_id)
        if case_id == "p137-case-01":
            runtime["expected_evaluator_activity"] = {key: 0 for key in EVALUATOR_ACTIVITY_KEYS}
        return runtime

    with pytest.raises(_error(), match="observed_evaluator_activity_delta_mismatch:p137-case-01"):
        api.run_p137_preliminary_matrix(tmp_path, runtime_factory=factory)


def test_runner_final_release_is_frozen_only_and_rebuilds_qualified_evidence(tmp_path: Path) -> None:
    result = _frozen_release(tmp_path)

    assert result["status"] == "p137_local_evidence_triage_qualified"
    assert result["totals"] == {"expected": 60, "passed": 60, "failed": 0}
    assert result["provider_profiles"] == ["prometheus", "loki", "grafana", "sentry", "opentelemetry"]
    assert all(value == 0 for value in result["forbidden_authority"].values())
    assert result["forbidden_authority"] == result["expected_forbidden_authority"]
    assert result["runtime_activity"] == result["expected_runtime_activity"]
    assert result["evaluator_activity"] == result["expected_evaluator_activity"]
    for key in ("wall_time_ms", "cpu_time_ms", "child_cpu_time_ms", "peak_memory_bytes"):
        assert result["resource_usage"][key] <= result["expected_resource_usage"][key]
    for key in ("wall_limit_ms", "cpu_limit_ms", "peak_memory_limit_bytes"):
        assert result["resource_usage"][key] == result["expected_resource_usage"][key]
    assert result["original_provider_artifact_reads"] == 0


def test_runner_rejects_precomputed_release_evidence_without_case_execution(tmp_path: Path) -> None:
    api = _runner_api("run_p137_release_matrix")

    with pytest.raises(_error(), match="release_matrix_final_path_is_frozen_only"):
        api.run_p137_release_matrix(
            tmp_path,
            precomputed_evidence=release_evidence_stub(),
            source_bindings=TEST_SOURCE_BINDINGS,
            final_implementation_review=final_implementation_review(),
        )


def test_cli_source_freeze_scope_covers_p137_dependencies_and_rejects_self_review() -> None:
    project_root = Path(__file__).resolve().parents[1]

    bindings = current_p137_source_hashes(project_root)

    assert tuple(bindings) == tuple(sorted(P137_SOURCE_SCOPE))
    for required in (
        "app/services/p137_contracts.py",
        "app/services/p137_p136_handoff.py",
        "app/services/p137_correlation.py",
        "app/services/p137_hypotheses.py",
        "app/services/p137_requests.py",
        "app/services/p137_classification.py",
        "app/services/p137_ledger.py",
        "app/services/p137_runtime.py",
        "app/services/p137_runner.py",
        "app/services/p137_release_evidence.py",
        "app/services/p134_observation_authority.py",
        "app/services/p135_provider_export_attachment.py",
        "app/services/p136_incremental_observer.py",
        "scripts/run_p137_local_triage.py",
        "scripts/verify.sh",
        "tests/test_p137_runner.py",
        "evals/p137/input/local-triage-profile.json",
        "docs/operations/p137-evidence-to-incident-roadmap.md",
        "docs/operations/p137-test-spec.md",
        "docs/tickets/p137/P137-008-canonical-runner-cli.md",
    ):
        assert required in bindings
    assert all(value.startswith("sha256:") for value in bindings.values())

    review = final_implementation_review(bindings)
    assert _validate_external_final_review(review, expected_source_hashes=bindings)["reviewed_source_hashes"] == bindings
    with pytest.raises(P137ProfileError, match="final_review_must_be_external_to_implementation"):
        _validate_external_final_review(
            {**review, "reviewer_role": review["implementation_role"]},
            expected_source_hashes=bindings,
        )


def test_runner_fails_release_when_observed_label_differs_from_expected(tmp_path: Path) -> None:
    api = _runner_api("run_p137_preliminary_matrix")

    def factory(case_id: str) -> dict[str, Any]:
        runtime = runtime_inputs(tmp_path / case_id, case_id)
        if case_id == "p137-case-01":
            runtime["classification_atoms"] = runtime_inputs(tmp_path / case_id, "p137-case-47")["classification_atoms"]
        return runtime

    with pytest.raises(_error(), match="case_observed_label_mismatch:p137-case-01"):
        api.run_p137_preliminary_matrix(
            tmp_path,
            runtime_factory=factory,
        )


def test_request_scenarios_invoke_execute_evidence_request(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    api = _runner_api("run_p137_preliminary_matrix")
    original = api.execute_evidence_request
    calls: list[str] = []

    def spy_execute_evidence_request(**kwargs: Any) -> Any:
        calls.append(str(kwargs["catalog_name"]))
        return original(**kwargs)

    monkeypatch.setattr(api, "execute_evidence_request", spy_execute_evidence_request)

    result = api.run_p137_preliminary_matrix(
        tmp_path,
        runtime_factory=lambda case_id: runtime_inputs(tmp_path / case_id, case_id),
    )

    assert calls == list(ALLOWED_REQUEST_CATALOG)
    request_cases = result["cases"][29:44]
    assert all("p137_requests.execute_evidence_request" in case["evidence"]["api_calls"] for case in request_cases)
    assert all(case["evidence"]["request_record_hashes"] for case in request_cases)


def test_control_scenarios_invoke_real_probe_callables(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    api = _runner_api("run_p137_preliminary_matrix")
    from tests.fixtures.p137 import builders as p137_builders

    original_validate = p137_builders.validate_p136_handoff_bundle
    original_runtime = p137_builders.run_p137_runtime_once
    calls: list[str] = []

    def spy_validate_p136_handoff_bundle(*args: Any, **kwargs: Any) -> Any:
        calls.append("validate_p136_handoff_bundle")
        return original_validate(*args, **kwargs)

    def spy_run_p137_runtime_once(*args: Any, **kwargs: Any) -> Any:
        calls.append(f"run_p137_runtime_once:{kwargs['base_path']}")
        return original_runtime(*args, **kwargs)

    monkeypatch.setattr(p137_builders, "validate_p136_handoff_bundle", spy_validate_p136_handoff_bundle)
    monkeypatch.setattr(p137_builders, "run_p137_runtime_once", spy_run_p137_runtime_once)

    result = api.run_p137_preliminary_matrix(
        tmp_path,
        runtime_factory=lambda case_id: runtime_inputs(tmp_path / case_id, case_id),
    )

    assert "validate_p136_handoff_bundle" in calls
    assert any("p137-case-50" in call for call in calls)
    case_06 = result["cases"][5]["evidence"]
    assert case_06["probe_invocation"]["callable"] == "tests.fixtures.p137.builders._ControlProbe"
    assert case_06["probe_exception"]["type"] == "P137HandoffError"
    assert case_06["probe_exception"]["message"] == "invalid_p136_release_status"


def test_runner_rejects_precomputed_control_probe_dict(tmp_path: Path) -> None:
    api = _runner_api("run_p137_preliminary_matrix")

    def factory(case_id: str) -> dict[str, Any]:
        runtime = runtime_inputs(tmp_path / case_id, case_id)
        if case_id == "p137-case-06":
            runtime["probe"] = {
                "source": "precomputed",
                "actual_label": "none",
                "actual_error": "p136_release_status_unqualified",
                "termination_reason": "pre_ingest_rejected",
                "api_calls": ["p137_p136_handoff.validate_p136_handoff_bundle"],
            }
        return runtime

    with pytest.raises(_error(), match="observed_probe_must_be_callable"):
        api.run_p137_preliminary_matrix(
            tmp_path,
            runtime_factory=factory,
        )


def test_runner_rejects_missing_runtime_evidence_probe_instead_of_materializing_expected_deltas(tmp_path: Path) -> None:
    api = _runner_api("run_p137_preliminary_matrix")

    def factory(case_id: str) -> dict[str, Any]:
        runtime = runtime_inputs(tmp_path / case_id, case_id)
        if case_id == "p137-case-01":
            runtime.pop("runtime_probe")
        return runtime

    with pytest.raises(_error(), match="runtime_evidence_probe_required"):
        api.run_p137_preliminary_matrix(
            tmp_path,
            runtime_factory=factory,
        )


def test_runner_rejects_missing_observed_runtime_activity_instead_of_using_delta_profile(tmp_path: Path) -> None:
    api = _runner_api("run_p137_preliminary_matrix")

    def factory(case_id: str) -> dict[str, Any]:
        runtime = runtime_inputs(tmp_path / case_id, case_id)
        if case_id == "p137-case-01":
            original_probe = runtime["runtime_probe"]

            def missing_activity_probe(**kwargs: Any) -> dict[str, Any]:
                result = dict(original_probe(**kwargs))
                result.pop("runtime_activity")
                return result

            runtime["runtime_probe"] = missing_activity_probe
        return runtime

    with pytest.raises(_error(), match="invalid_runtime_activity_schema"):
        api.run_p137_preliminary_matrix(
            tmp_path,
            runtime_factory=factory,
        )


def test_guard_and_aborted_recovery_matrix_rows_use_real_production_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    api = _runner_api("run_p137_preliminary_matrix")
    from tests.fixtures.p137 import builders as p137_builders

    original_guard = p137_builders.reject_evaluator_guard_callables
    original_runtime = p137_builders.run_p137_runtime_once
    guard_calls = 0
    recovery_calls: list[str | None] = []
    case_58_config: dict[str, Any] = {}

    def guard_spy(callables: dict[str, Any]) -> None:
        nonlocal guard_calls
        guard_calls += 1
        original_guard(callables)

    def runtime_spy(*args: Any, **kwargs: Any) -> dict[str, Any]:
        if "p137-case-58" in str(kwargs["base_path"]):
            recovery_calls.append(kwargs.get("crash_after"))
        return original_runtime(*args, **kwargs)

    def factory(case_id: str) -> dict[str, Any]:
        runtime = runtime_inputs(tmp_path / case_id, case_id)
        if case_id == "p137-case-58":
            case_58_config.update(deepcopy(runtime["effective_p137_config"]))
        return runtime

    monkeypatch.setattr(p137_builders, "reject_evaluator_guard_callables", guard_spy)
    monkeypatch.setattr(p137_builders, "run_p137_runtime_once", runtime_spy)

    result = api.run_p137_preliminary_matrix(tmp_path, runtime_factory=factory)
    guard_case = result["cases"][14]["evidence"]
    recovery_case = result["cases"][57]["evidence"]

    assert guard_calls == 1
    assert guard_case["actual_error"] == "guard_probe_blocked_before_boundary"
    assert guard_case["termination_reason"] == "evaluator_only"
    assert guard_case["api_calls"] == ["p137_contracts.reject_evaluator_guard_callables"]
    assert guard_case["runtime_activity"] == zero_runtime_activity()
    assert guard_case["expected_runtime_activity"] == zero_runtime_activity()
    assert guard_case["forbidden_authority"] == zero_forbidden_authority()
    assert guard_case["evaluator_activity"]["fake_guard_callable_count"] > 0

    assert recovery_calls == ["classification_write", None, None]
    assert recovery_case["actual_label"] == "aborted_fail_closed"
    assert recovery_case["termination_reason"] == "aborted_fail_closed"
    assert recovery_case["api_calls"] == ["p137_runtime.run_p137_runtime_once"]
    assert recovery_case["runtime_activity"]["classification_write_count"] == 1
    assert recovery_case["runtime_activity"]["ledger_write_count"] == 1
    assert recovery_case["runtime_activity"]["recovery_replay_count"] == 1

    root = tmp_path / "p137-case-58" / "control-probe"
    classification_files = list((root / case_58_config["classification_dir"]).glob("*.json"))
    ledger = json.loads((root / case_58_config["ledger_path"]).read_text())
    classification = json.loads(classification_files[0].read_text())
    assert len(classification_files) == 1
    assert classification["classification"] == "aborted_fail_closed"
    assert len(ledger["classification_hashes"]) == 1


def test_runner_fails_when_control_probe_raw_runtime_outcome_is_wrong(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    api = _runner_api("run_p137_preliminary_matrix")
    from tests.fixtures.p137 import builders as p137_builders

    original_runtime = p137_builders.run_p137_runtime_once

    def wrong_lease_result(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = dict(original_runtime(*args, **kwargs))
        if "p137-case-50" in str(kwargs["base_path"]):
            result["expected_error"] = "not_lease_conflict"
        return result

    monkeypatch.setattr(p137_builders, "run_p137_runtime_once", wrong_lease_result)

    with pytest.raises(_error(), match="case_observed_error_mismatch:p137-case-50:not_lease_conflict!=lease_conflict"):
        api.run_p137_preliminary_matrix(
            tmp_path,
            runtime_factory=lambda case_id: runtime_inputs(tmp_path / case_id, case_id),
        )


def test_case_matrix_matches_roadmap_rows_and_request_catalog_order() -> None:
    api = _runner_api("p137_release_case_matrix")

    cases = api.p137_release_case_matrix()

    assert len(cases) == 60
    assert [case["case_id"] for case in cases] == [f"p137-case-{index:02d}" for index in range(1, 61)]
    assert [case["request_catalog_entry"] for case in cases[29:44]] == list(ALLOWED_REQUEST_CATALOG)
    assert [case["category"] for case in cases[29:44]] == ["request"] * 15
    for case in cases:
        assert case["delta_profile"].startswith("dp_")
        assert case["expected_label"] or case["expected_error"]
        if case["expected_error"]:
            assert case["expected_label"] == "none"
        assert case["scope"] in {"accepted incident", "accepted incidents", "pre-ingest", "evaluator-only", "runtime termination", "state rejection"}


def test_observed_runtime_activity_is_full_and_bound_to_fixture_bytes(tmp_path: Path) -> None:
    api = _runner_api("run_p137_preliminary_matrix")

    result = api.run_p137_preliminary_matrix(
        tmp_path,
        runtime_factory=lambda case_id: runtime_inputs(tmp_path / case_id, case_id),
    )

    first = result["cases"][0]
    evidence = first["evidence"]
    assert set(evidence["runtime_activity"]) == set(RUNTIME_ACTIVITY_KEYS)
    assert set(evidence["expected_runtime_activity"]) == set(RUNTIME_ACTIVITY_KEYS)
    assert set(evidence["forbidden_authority"]) == set(FORBIDDEN_AUTHORITY_KEYS)
    assert set(evidence["expected_forbidden_authority"]) == set(FORBIDDEN_AUTHORITY_KEYS)
    assert set(evidence["evaluator_activity"]) == set(EVALUATOR_ACTIVITY_KEYS)
    assert set(evidence["expected_evaluator_activity"]) == set(EVALUATOR_ACTIVITY_KEYS)
    assert set(evidence["resource_usage"]) == set(RESOURCE_USAGE_KEYS)
    assert set(evidence["expected_resource_usage"]) == set(RESOURCE_USAGE_KEYS)
    assert evidence["runtime_activity"] == evidence["expected_runtime_activity"]
    assert evidence["forbidden_authority"] == evidence["expected_forbidden_authority"]
    assert evidence["evaluator_activity"] == evidence["expected_evaluator_activity"]
    assert evidence["resource_usage"] == evidence["expected_resource_usage"]
    assert evidence["runtime_activity"]["handoff_bundle_bytes_read"] == len(
        runtime_inputs(tmp_path / "p137-case-01", "p137-case-01")["canonical_handoff_bundle_bytes"]
    ) + 1
    assert evidence["runtime_activity"]["promotion_bytes_validated"] == sum(
        len(raw) for raw in runtime_inputs(tmp_path / "p137-case-01", "p137-case-01")["canonical_promotion_bytes"]
    )
    assert isinstance(evidence["runtime_activity"]["handoff_bundle_bytes_read"], int)
    assert "handoff_bytes" not in evidence["runtime_activity"]
    assert set(evidence["forbidden_authority"].values()) == {0}


def test_denominator_contains_required_control_failure_cases() -> None:
    api = _runner_api("p137_release_case_matrix")
    cases = api.p137_release_case_matrix()
    text = "\n".join(case["semantic"] for case in cases)

    for required in (
        "SIGINT",
        "SIGTERM",
        "Corrupt durable state",
        "CAS predecessor conflict",
        "bundle sequence rollback",
        "same-sequence fork",
        "previous-hash discontinuity",
        "torn fixed-path replacement",
        "Crash after ingest intent",
        "Crash after incident write",
        "Crash after request write",
        "classification write before ledger CAS",
        "Bounded continuous mode",
        "Stale readiness",
        "Stale handoff version",
        "resource limit",
    ):
        assert required in text
