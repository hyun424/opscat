from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import scripts.run_p138_observation_triage_supervisor as p138_script
from app.services.p110_evaluation import stable_hash
from app.services.p138_observation_triage_supervisor import (
    EVALUATOR_ACTIVITY_KEYS,
    FORBIDDEN_AUTHORITY_KEYS,
    RUNTIME_ACTIVITY_KEYS,
)
from app.services.p138_release_evidence import (
    APPROVED_PLAN_SHA256,
    build_p138_freeze_manifest,
    current_p138_source_hashes,
    p138_fixture_hash,
    p138_profile_hash,
    validate_observation_triage_supervisor_profile,
)
from app.services.p138_runner import (
    REAL_BOUNDARY_CASE_IDS,
    P138RunnerError,
    p138_release_case_matrix,
    run_p138_preliminary_matrix,
)
from scripts.run_p138_observation_triage_supervisor import (
    CanonicalCaseExecutor,
    CanonicalRuntimeFactory,
    P138ProfileError,
)

SCENARIOS = [
    "bootstrap",
    "new_promotion",
    "zero_promotion",
    "crash_cycle_started",
    "crash_p136_completed",
    "crash_handoff_selected",
    "publisher_intent_crash",
    "crash_handoff_published",
    "p137_commit_before_p138_finalize",
    "p137_lease_conflict_restart",
    "same_sequence_fork",
    "sequence_gap_previous_hash_break",
    "publisher_state_fixed_mismatch",
    "p138_lease_contention",
    "p136_lease_contention",
    "publisher_lease_contention",
    "stale_p137_readiness_version",
    "later_delta_only",
    "signals",
    "forbidden_secret_path_resource_guard",
    "p136_checkpoint_promotions_before_p138_phase",
    "p136_checkpoint_empty_before_p138_phase",
    "publisher_crash_after_fixed",
    "publisher_crash_after_state",
    "partial_non_genesis_bootstrap_reject",
    "receipt_exhaustion_failure_threshold",
    "max_cycle_heartbeat_cadence",
    "stale_readiness_deadman_safe_signal",
    "promotion_outcome_intent_before_checkpoint",
    "empty_outcome_intent_before_checkpoint",
]


def _zero(keys: tuple[str, ...]) -> dict[str, int]:
    return {key: 0 for key in keys}


def _resources() -> dict[str, int]:
    return {
        "wall_time_ms": 0,
        "cpu_time_ms": 0,
        "child_cpu_time_ms": 0,
        "peak_memory_bytes": 0,
        "wall_limit_ms": 30_000,
        "cpu_limit_ms": 15_000,
        "peak_memory_limit_bytes": 134_217_728,
    }


class _FakeExecutor:
    def __init__(self, row: dict[str, Any]) -> None:
        self.row = deepcopy(row)

    def __call__(self) -> dict[str, Any]:
        expected = deepcopy(self.row["expected"])
        return {
            "status": expected["status"],
            "error": expected["error"],
            "stop_reason": expected["stop_reason"],
            "phase_path": expected["phase_path"],
            "component_boundaries": expected["component_boundaries"],
            "durable_post_state": expected["durable_post_state"],
            "runtime_activity": _zero(RUNTIME_ACTIVITY_KEYS),
            "forbidden_authority": _zero(FORBIDDEN_AUTHORITY_KEYS),
            "evaluator_activity": _zero(EVALUATOR_ACTIVITY_KEYS),
            "resource_usage": _resources(),
            "execution_source": "tests.test_p138_runner._FakeExecutor",
        }


def _runtime_factory(case_id: str) -> dict[str, Any]:
    row = next(item for item in p138_release_case_matrix() if item["case_id"] == case_id)
    return {
        "schema_version": "p138.case_runtime.v1",
        "case_id": case_id,
        "input_profile": {"scenario": row["scenario"]},
        "expected_runtime_activity": _zero(RUNTIME_ACTIVITY_KEYS),
        "expected_forbidden_authority": _zero(FORBIDDEN_AUTHORITY_KEYS),
        "expected_evaluator_activity": _zero(EVALUATOR_ACTIVITY_KEYS),
        "expected_resource_usage": _resources(),
        "execute": _FakeExecutor(row),
    }


def test_case_matrix_is_exact_30_case_denominator_and_scenario_order() -> None:
    rows = p138_release_case_matrix()
    assert [row["case_id"] for row in rows] == [f"P138-CASE-{index:02d}" for index in range(1, 31)]
    assert [row["scenario"] for row in rows] == SCENARIOS
    assert REAL_BOUNDARY_CASE_IDS == frozenset(
        {
            "P138-CASE-02",
            "P138-CASE-03",
            "P138-CASE-07",
            "P138-CASE-09",
            "P138-CASE-10",
            "P138-CASE-16",
            "P138-CASE-18",
            "P138-CASE-21",
            "P138-CASE-22",
            "P138-CASE-23",
            "P138-CASE-24",
            "P138-CASE-25",
            "P138-CASE-29",
            "P138-CASE-30",
        }
    )


def test_preliminary_runner_executes_each_case_and_freezes_exact_maps(tmp_path: Path) -> None:
    matrix = run_p138_preliminary_matrix(
        tmp_path,
        runtime_factory=_runtime_factory,
        evaluator_overhead_activity={
            **_zero(EVALUATOR_ACTIVITY_KEYS),
            "runner_invocation_count": 1,
            "profile_read_count": 1,
            "artifact_write_count": 2,
        },
    )
    assert matrix["status"] == "p138_preliminary_matrix_frozen"
    assert matrix["totals"] == {"expected": 30, "passed": 30, "failed": 0}
    assert len(matrix["cases"]) == len(matrix["case_inputs"]) == 30
    assert matrix["matrix_hash"] == stable_hash(matrix["cases"])
    assert matrix["case_input_hash"] == stable_hash(matrix["case_inputs"])
    for case in matrix["cases"]:
        evidence = case["evidence"]
        assert evidence["executed"] is True
        assert evidence["forbidden_authority"] == _zero(FORBIDDEN_AUTHORITY_KEYS)
        assert evidence["expected_forbidden_authority"] == _zero(FORBIDDEN_AUTHORITY_KEYS)
        assert evidence["runtime_activity"] == evidence["expected_runtime_activity"]
        assert evidence["evaluator_activity"] == evidence["expected_evaluator_activity"]


def test_runner_rejects_precomputed_or_mismatched_observations(tmp_path: Path) -> None:
    def precomputed(case_id: str) -> dict[str, Any]:
        runtime = _runtime_factory(case_id)
        runtime["execute"] = runtime["execute"]()
        return runtime

    with pytest.raises(P138RunnerError, match="case_executor_must_be_callable"):
        run_p138_preliminary_matrix(tmp_path / "precomputed", runtime_factory=precomputed)

    def mismatched(case_id: str) -> dict[str, Any]:
        runtime = _runtime_factory(case_id)
        if case_id == "P138-CASE-02":
            executor = runtime["execute"]

            def wrong() -> dict[str, Any]:
                result = executor()
                result["phase_path"] = ["cycle_started"]
                return result

            runtime["execute"] = wrong
        return runtime

    with pytest.raises(P138RunnerError, match="observed_phase_path_mismatch:P138-CASE-02"):
        run_p138_preliminary_matrix(tmp_path / "mismatch", runtime_factory=mismatched)


def test_canonical_executor_does_not_echo_tampered_expected_status(tmp_path: Path) -> None:
    row = next(item for item in p138_release_case_matrix() if item["case_id"] == "P138-CASE-03")
    row["expected"]["status"] = "failed_closed"
    executor = CanonicalCaseExecutor(tmp_path, "P138-CASE-03", row)

    with pytest.raises(P138ProfileError, match="canonical_status_mismatch:P138-CASE-03"):
        executor()


def test_publisher_split_commit_case_requires_supervisor_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = next(item for item in p138_release_case_matrix() if item["case_id"] == "P138-CASE-23")
    executor = CanonicalCaseExecutor(tmp_path, "P138-CASE-23", row)
    fixture = SimpleNamespace(
        root=tmp_path,
        p136_runtime={"authority": {}, "now": "2026-07-13T00:10:04Z"},
        publisher_inputs={
            "canonical_entry_map": {},
            "p136_independent_review": {},
            "p136_release_evidence": {},
            "created_at": "2026-07-13T00:10:03Z",
        },
    )
    config: dict[str, Any] = {
        "publisher_state_path": "p137/publisher-state.json",
        "publisher_intent_path": "p137/publisher-intent.json",
        "p136_handoff_bundle_path": "handoff/p136-bundle.json",
        "publisher_lease_path": "p137/publisher.lease",
        "p136_config": {},
    }
    state_path = tmp_path / config["publisher_state_path"]
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        __import__("json").dumps(
            {"last_bundle_sequence": 1, "last_bundle_hash": "sha256:" + "1" * 64},
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    failed = {
        "status": "failed_closed",
        "p136_result": {"advanced_checkpoint": {}, "promotion_records": []},
    }
    monkeypatch.setattr(executor, "_accepted", lambda: (fixture, config))
    monkeypatch.setattr(executor, "_run", lambda *args, **kwargs: deepcopy(failed))
    monkeypatch.setattr(p138_script, "append_observation_entry", lambda value: None)
    direct_publisher_calls: list[dict[str, Any]] = []

    def record_direct_publisher_call(**kwargs: Any) -> dict[str, Any]:
        direct_publisher_calls.append(kwargs)
        return {}

    monkeypatch.setattr(p138_script, "publish_p136_handoff_bundle", record_direct_publisher_call)

    with pytest.raises(P138ProfileError, match="publisher_recovery_failed"):
        executor._publisher_crash_case(
            "publisher_fixed_replaced",
        )
    assert direct_publisher_calls == []


def test_canonical_factory_executes_all_real_boundary_rows(tmp_path: Path) -> None:
    factory = CanonicalRuntimeFactory(tmp_path)
    for case_id in sorted(REAL_BOUNDARY_CASE_IDS):
        runtime = factory(case_id)
        assert callable(runtime["execute"])
        result = runtime["execute"]()
        assert result["forbidden_authority"] == _zero(FORBIDDEN_AUTHORITY_KEYS)
        assert set(result["component_boundaries"]) >= set(next(row["expected"]["component_boundaries"] for row in p138_release_case_matrix() if row["case_id"] == case_id))


def test_profile_and_freeze_bind_plan_transitive_sources_and_fixture_tree() -> None:
    project_root = Path(__file__).resolve().parents[1]
    profile_path = project_root / "evals/p138/input/observation-triage-supervisor-profile.json"
    profile = validate_observation_triage_supervisor_profile(__import__("json").loads(profile_path.read_text(encoding="utf-8")))
    assert profile["approved_plan_sha256"] == APPROVED_PLAN_SHA256
    assert profile["required_case_ids"] == [f"P138-CASE-{index:02d}" for index in range(1, 31)]
    assert frozenset(profile["real_boundary_case_ids"]) == REAL_BOUNDARY_CASE_IDS

    sources = current_p138_source_hashes(project_root)
    required = {
        ".omx/plans/opscat-p138-observation-to-triage-supervisor.md",
        "app/services/p136_incremental_observer.py",
        "app/services/p136_runner.py",
        "app/services/p136_release_evidence.py",
        "app/services/p137_p136_handoff.py",
        "app/services/p137_runtime.py",
        "app/services/p137_runner.py",
        "app/services/p137_release_evidence.py",
        "app/services/p138_observation_triage_supervisor.py",
        "app/services/p138_runner.py",
        "app/services/p138_release_evidence.py",
        "scripts/run_p138_observation_triage_supervisor.py",
        "tests/test_p138_runner.py",
        "tests/test_p138_release_evidence.py",
        "tests/test_p137_authority_boundary.py",
        "tests/test_p137_classification.py",
        "tests/test_p137_contracts.py",
        "tests/test_p137_correlation.py",
        "tests/test_p137_hypotheses.py",
        "tests/test_p137_ledger.py",
        "tests/test_p137_requests.py",
        "evals/p136/input/incremental-observer-profile.json",
        "evals/p137/input/local-triage-profile.json",
        "evals/p138/input/observation-triage-supervisor-profile.json",
        "scripts/verify.sh",
    }
    assert required <= set(sources)
    assert sources[".omx/plans/opscat-p138-observation-to-triage-supervisor.md"] == ("sha256:" + APPROVED_PLAN_SHA256)

    matrix = run_p138_preliminary_matrix(Path("p138-test-output"), runtime_factory=_runtime_factory)
    manifest = build_p138_freeze_manifest(
        source_bindings=sources,
        profile=profile,
        canonical_matrix=matrix,
        dependency_bindings={
            "p136_status": "p136_incremental_local_observation_qualified",
            "p136_evidence_hash": stable_hash({"dependency": "p136-evidence"}),
            "p136_review_hash": stable_hash({"dependency": "p136-review"}),
            "p137_status": "p137_local_evidence_triage_qualified",
            "p137_evidence_hash": stable_hash({"dependency": "p137-evidence"}),
            "p137_review_hash": stable_hash({"dependency": "p137-review"}),
        },
        project_root=project_root,
    )
    assert manifest["profile_hash"] == p138_profile_hash(profile)
    assert manifest["fixture_hash"] == p138_fixture_hash(profile, project_root=project_root)
    assert manifest["approved_plan_sha256"] == APPROVED_PLAN_SHA256
