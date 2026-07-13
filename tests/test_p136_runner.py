from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest

from scripts import run_p136_incremental_observer as canonical_runner
from tests.fixtures.p136.builders import (
    RELEASE_STATUS,
    TEST_SOURCE_BINDINGS,
    independent_review_artifact,
    release_evidence,
    runtime_inputs,
)


def _runner_api(*names: str) -> Any:
    try:
        module = importlib.import_module("app.services.p136_runner")
    except ModuleNotFoundError as exc:
        pytest.fail(f"missing P136 runner module/API: app.services.p136_runner ({exc})")
    missing = [name for name in names if not hasattr(module, name)]
    if missing:
        pytest.fail(f"missing P136 runner module/API: {', '.join(missing)}")
    return module


def _error() -> type[Exception]:
    module = _runner_api("P136RunnerError")
    return module.P136RunnerError


def _release_kwargs() -> dict[str, Any]:
    return {
        "source_bindings": TEST_SOURCE_BINDINGS,
        "independent_review": independent_review_artifact(),
    }


def test_runner_executes_fixed_50_case_matrix_instead_of_accepting_precomputed_success(tmp_path: Path) -> None:
    api = _runner_api("run_p136_release_matrix")

    result = api.run_p136_release_matrix(
        tmp_path,
        runtime_factory=lambda case_id: runtime_inputs(tmp_path / case_id),
        **_release_kwargs(),
    )

    assert result["status"] == RELEASE_STATUS
    assert result["totals"] == {"expected": 50, "passed": 50, "failed": 0}
    assert len(result["cases"]) == 50
    assert {case["case_id"] for case in result["cases"]} == {f"p136-case-{index:02d}" for index in range(1, 51)}
    provider_cases = result["cases"][:5]
    assert {case["evidence"]["provider"] for case in provider_cases} == {
        "grafana",
        "loki",
        "opentelemetry",
        "prometheus",
        "sentry",
    }
    assert all(case["provider_first_batch_promotion"] is True for case in provider_cases)
    assert all(case["evidence"]["probe"] == "real_p135_provider_bridge" for case in provider_cases)
    assert all(case["evidence"]["segment_file_read_count"] == 1 for case in provider_cases)


def test_runner_cannot_self_stamp_provider_coverage_when_real_bridge_input_is_missing(tmp_path: Path) -> None:
    api = _runner_api("run_p136_release_matrix")
    error = _error()

    def incomplete_runtime(case_id: str) -> dict[str, Any]:
        runtime = runtime_inputs(tmp_path / case_id)
        runtime.pop("provider_entries", None)
        return runtime

    with pytest.raises(error, match="p136_release_evidence_validation_failed"):
        api.run_p136_release_matrix(
            tmp_path,
            runtime_factory=incomplete_runtime,
            **_release_kwargs(),
        )


def test_runner_rejects_static_self_stamped_release_evidence_without_case_execution(tmp_path: Path) -> None:
    api = _runner_api("run_p136_release_matrix")
    error = _error()

    with pytest.raises(error, match="release_matrix_must_execute_cases"):
        api.run_p136_release_matrix(
            tmp_path,
            precomputed_evidence=release_evidence(50),
            **_release_kwargs(),
        )


def test_runner_case_matrix_contains_required_denominator_categories(tmp_path: Path) -> None:
    api = _runner_api("p136_release_case_matrix")

    cases = api.p136_release_case_matrix()
    categories = {case["category"] for case in cases}

    assert len(cases) == 50
    assert {
        "config_path_contract",
        "authority_reservation",
        "secure_index_partial_rotation",
        "duplicate_p135_bridge",
        "crash_durability_recovery",
        "lease_exhaustion_failure_signal",
        "runtime_guard_resource_schema",
    } <= categories
    for case in cases:
        assert bool(case.get("expected_label")) ^ bool(case.get("expected_error"))


def test_runner_cases_prove_exact_roadmap_labels_errors_and_real_evidence(tmp_path: Path) -> None:
    api = _runner_api("p136_release_case_matrix", "run_p136_release_matrix")

    expected = {case["case_id"]: case for case in api.p136_release_case_matrix()}
    result = api.run_p136_release_matrix(
        tmp_path,
        runtime_factory=lambda case_id: runtime_inputs(tmp_path / case_id),
        **_release_kwargs(),
    )

    assert [case["semantic"] for case in result["cases"]] == [
        "Prometheus first-batch promotion",
        "Loki first-batch promotion",
        "Grafana first-batch promotion",
        "Sentry first-batch promotion",
        "OTLP first-batch promotion",
        "second append batch promotion",
        "partial final line deferred with exact pending state",
        "completed same-identity partial line promoted",
        "deterministic duplicate resolved without segment read",
        "restart duplicate resolved without segment read",
        "valid rotation continuity",
        "rotated replay prefix resolved without segment read",
        "malformed complete index line rejected",
        "duplicate JSON key index line rejected",
        "non-finite index value rejected",
        "oversized index line rejected",
        "whole-index byte budget rejected",
        "whole-index complete-line budget rejected",
        "index symlink/hardlink/non-regular rejected",
        "same-identity consumed-prefix mutation rejected",
        "same-identity truncation rejected",
        "rotation sequence gap rejected",
        "rotation lineage mismatch rejected",
        "entry ID conflict rejected",
        "segment ID conflict rejected",
        "denied, stale, or expired index receipt rejected",
        "receipt reuse without matching durable reservation rejected",
        "index receipt byte estimate exceeded",
        "index receipt record estimate exceeded",
        "wrong index level/method/capability/source rejected",
        "segment content/size mismatch rejected through P135",
        "provider parser failure promoted only as denominator failure",
        "crash after index-read intent before read resumes same reservation",
        "crash after index read before P135 resumes same reservation",
        "crash after promotion intent recovers exactly one promotion",
        "crash after promotion before checkpoint recovers without P135",
        "checkpoint/index-intent/journal/promotion tamper rejected",
        "pre-replace durability failure preserves prior state",
        "post-replace directory-fsync uncertainty stops",
        "competing lease performs no state/index/segment read",
        "exact config key/path topology violation rejected",
        "excess wall-clock rollback rejected",
        "receipt-pool exhaustion emits fail-closed termination",
        "consecutive-failure threshold emits fail-closed termination",
        "SIGINT emits a hash-bound safe-boundary termination receipt",
        "SIGTERM emits a hash-bound safe-boundary termination receipt",
        "forbidden runtime authority probes are blocked and measured",
        "P135 bridge manifest/receipt/ledger semantic tamper rejected",
        "empty or replay-only rotated identity remains pending or proves exact replay",
        "rotation after an old-identity pending partial is rejected",
    ]
    for case in result["cases"]:
        spec = expected[case["case_id"]]
        evidence = case["evidence"]
        assert evidence["probe"] not in {"fixed-matrix", "category_probe", "self_stamped"}
        assert evidence["runtime_activity"].keys() == result["runtime_activity"].keys()
        assert evidence["output_boundary"]["mode"] == "in_memory_release_evidence"
        if spec.get("expected_label"):
            assert evidence["actual_label"] == spec["expected_label"]
            assert "actual_error" not in evidence
        else:
            assert evidence["actual_error"] == spec["expected_error"]
            assert evidence["error_type"] in {"P136ObservationError", "P136DurabilityUncertainError", "P135ExportError"}
        assert case["duplicate_segment_reads"] == evidence["measured_duplicate_segment_reads"] == 0
        assert case["duplicate_promotions"] == evidence["measured_duplicate_promotions"] == 0
    guard_evidence = result["cases"][46]["evidence"]
    assert set(guard_evidence["guard_blocked_attempts"]) == set(result["forbidden_authority"])
    assert set(guard_evidence["guard_blocked_attempts"].values()) == {1}
    assert set(guard_evidence["forbidden_authority"].values()) == {0}
    assert result["forbidden_authority"] == guard_evidence["forbidden_authority"]
    assert [case["evidence"]["probe"] for case in result["cases"][44:46]] == [
        "real_os_signal_safe_boundary",
        "real_os_signal_safe_boundary",
    ]
    assert result["evaluator_activity"]["signal_delivery_count"] == 2
    crash_cases = {case["case_id"]: case["evidence"] for case in result["cases"][32:36]}
    assert crash_cases["p136-case-33"]["durable_intent_count"] == 1
    assert crash_cases["p136-case-33"]["pre_resume_index_read_count"] == 0
    assert crash_cases["p136-case-34"]["pre_resume_index_read_count"] == 1
    assert crash_cases["p136-case-34"]["pre_resume_segment_read_count"] == 0
    assert crash_cases["p136-case-35"]["persisted_promotion_count"] == 1
    assert crash_cases["p136-case-35"]["segment_reads_during_recovery"] == 0
    assert crash_cases["p136-case-36"]["persisted_promotion_count"] == 1
    assert crash_cases["p136-case-36"]["persisted_checkpoint_count"] == 1
    assert crash_cases["p136-case-36"]["segment_reads_during_recovery"] == 0


def test_duplicate_counters_are_derived_from_repeated_entry_hash_events() -> None:
    module = _runner_api("_measured_duplicate_counts")

    class Probe:
        events = [
            "segment_entry_read:sha256:a",
            "segment_entry_read:sha256:a",
            "segment_entry_read:sha256:b",
            "promotion_created:sha256:a",
            "promotion_created:sha256:a",
        ]

    assert module._measured_duplicate_counts({"probe": Probe()}) == (1, 1)


def test_resource_usage_charges_only_peak_rss_growth_during_the_matrix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _runner_api("_resource_usage", "_normalized_peak_rss_bytes")

    class Usage:
        def __init__(self, *, user: float, system: float, peak: int) -> None:
            self.ru_utime = user
            self.ru_stime = system
            self.ru_maxrss = peak

    started_self = Usage(user=10.0, system=5.0, peak=200_000)
    started_children = Usage(user=3.0, system=2.0, peak=50_000)
    current_self = Usage(user=10.2, system=5.1, peak=220_000)
    current_children = Usage(user=3.1, system=2.1, peak=55_000)
    calls = iter((current_self, current_children))
    monkeypatch.setattr(module.resource, "getrusage", lambda _: next(calls))
    monkeypatch.setattr(module.time, "monotonic", lambda: 101.0)

    measured = module._resource_usage(100.0, started_self, started_children)

    assert measured["peak_memory_bytes"] == (
        module._normalized_peak_rss_bytes(current_self)
        - module._normalized_peak_rss_bytes(started_self)
    )
    assert measured["wall_time_ms"] == 1_000
    assert measured["cpu_time_ms"] == 299
    assert measured["child_cpu_time_ms"] == 200


def test_runtime_guard_fails_if_a_forbidden_operation_crosses_the_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _runner_api("_case_runtime_guard_schema")
    error = _error()

    def crossed(counter: str, blocked: dict[str, int], operation: Any) -> None:
        blocked[counter] += 1
        operation()
        raise error(f"forbidden_runtime_boundary_blocked:{counter}")

    monkeypatch.setattr(module, "_deny_forbidden_runtime_boundary", crossed)

    with pytest.raises(error, match="forbidden_runtime_operation_crossed_boundary"):
        module._case_runtime_guard_schema({})


def test_runner_reports_exact_status_only_after_release_evidence_validator_accepts(tmp_path: Path) -> None:
    api = _runner_api("run_p136_release_matrix")
    error = _error()

    with pytest.raises(error, match="p136_release_evidence_validation_failed"):
        api.run_p136_release_matrix(
            tmp_path,
            runtime_factory=lambda case_id: runtime_inputs(tmp_path / case_id),
            force_case_failure="p136-case-17",
            **_release_kwargs(),
        )


def test_runner_termination_receipts_bind_consumed_reserved_receipts_and_final_checkpoint(tmp_path: Path) -> None:
    api = _runner_api("run_p136_observer_foreground")

    result = api.run_p136_observer_foreground(runtime_inputs(tmp_path), max_cycles=1)

    receipt = result["termination_receipt"]
    assert receipt["schema_version"] == "p136.termination_receipt.v1"
    assert receipt["final_checkpoint_hash"] == result["checkpoint"]["checkpoint_hash"]
    assert receipt["consumed_index_read_receipt_hashes"] == result["checkpoint"]["consumed_index_read_receipt_hashes"]
    assert receipt["reserved_index_read_receipt_hashes"] == result["checkpoint"]["reserved_index_read_receipt_hashes"]
    assert receipt["forbidden_authority"] == result["checkpoint"]["forbidden_authority"]


def test_canonical_profile_and_runtime_factory_use_fixed_local_provider_exports(tmp_path: Path) -> None:
    profile = canonical_runner.validate_profile(canonical_runner._read_json(canonical_runner.ROOT / "evals/p136/input/incremental-observer-profile.json"))
    fixture_root = canonical_runner._fixture_root(profile)
    factory = canonical_runner.CanonicalRuntimeFactory(tmp_path, fixture_root)

    runtime = factory("p136-case-01")

    assert set(runtime["provider_entries"]) == {
        "grafana",
        "loki",
        "opentelemetry",
        "prometheus",
        "sentry",
    }
    assert len(runtime["authority"]["segment_receipts"]) == 5
    assert runtime["config"]["p134_contract_hash"] == runtime["authority"]["contract"]["contract_hash"]


def test_canonical_output_is_separate_and_cleanup_preserves_review_input(tmp_path: Path) -> None:
    assert canonical_runner.DEFAULT_OUTPUT_DIR.parent == canonical_runner.DEFAULT_INDEPENDENT_REVIEW.parent
    assert canonical_runner.DEFAULT_OUTPUT_DIR != canonical_runner.DEFAULT_INDEPENDENT_REVIEW.parent

    output_dir = tmp_path / "release"
    output_dir.mkdir()
    review = output_dir / "independent-review.json"
    review.write_text('{"review":"must-survive"}\n', encoding="utf-8")
    stale = output_dir / "stale.json"
    stale.write_text("{}\n", encoding="utf-8")

    canonical_runner._write_exact_artifacts(
        output_dir,
        {"release-evidence.json": {"status": "test"}},
        protected_paths=(review,),
    )

    assert review.read_text(encoding="utf-8") == '{"review":"must-survive"}\n'
    assert not stale.exists()
    assert (output_dir / "release-evidence.json").is_file()


def test_current_source_bindings_cover_canonical_script_profile_and_provider_fixtures() -> None:
    api = _runner_api("run_p136_release_matrix")
    del api
    from app.services.p136_release_evidence import current_source_hashes

    bindings = current_source_hashes(canonical_runner.ROOT)

    assert "scripts/run_p136_incremental_observer.py" in bindings
    assert "evals/p136/input/incremental-observer-profile.json" in bindings
    assert "evals/p135/input/exports/prometheus_matrix.json" in bindings
    assert all(value.startswith("sha256:") for value in bindings.values())
