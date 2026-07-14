from __future__ import annotations

import importlib
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from app.services.p110_evaluation import stable_hash
from tests.fixtures.p137.builders import (
    TEST_SOURCE_BINDINGS,
    final_implementation_review,
    local_triage_profile,
    runtime_inputs,
)


def _release_api(*names: str) -> Any:
    try:
        module = importlib.import_module("app.services.p137_release_evidence")
    except ModuleNotFoundError as exc:
        pytest.fail(f"missing P137 release module/API: app.services.p137_release_evidence ({exc})")
    missing = [name for name in names if not hasattr(module, name)]
    if missing:
        pytest.fail(f"missing P137 release module/API: {', '.join(missing)}")
    return module


def _runner_api(*names: str) -> Any:
    module = importlib.import_module("app.services.p137_runner")
    missing = [name for name in names if not hasattr(module, name)]
    if missing:
        pytest.fail(f"missing P137 runner module/API: {', '.join(missing)}")
    return module


def _error() -> type[Exception]:
    return _release_api("P137ReleaseEvidenceError").P137ReleaseEvidenceError


def _matrix(tmp_path: Path) -> dict[str, Any]:
    runner = _runner_api("run_p137_release_matrix")
    _, canonical_matrix, manifest, review, profile_hash, fixture_hash = _freeze_bundle(tmp_path)
    return runner.run_p137_release_matrix(
        tmp_path,
        canonical_matrix=canonical_matrix,
        freeze_manifest=manifest,
        source_bindings=TEST_SOURCE_BINDINGS,
        final_implementation_review=review,
        expected_profile_hash=profile_hash,
        expected_fixture_hash=fixture_hash,
    )


def _preliminary_matrix(tmp_path: Path) -> dict[str, Any]:
    runner = _runner_api("run_p137_preliminary_matrix")
    return runner.run_p137_preliminary_matrix(
        tmp_path,
        runtime_factory=lambda case_id: runtime_inputs(tmp_path / case_id, case_id),
    )


def _review_for(
    *,
    matrix_hash: str,
    profile_hash: str,
    fixture_hash: str,
    source_bindings: dict[str, str] | None = None,
) -> dict[str, Any]:
    review = final_implementation_review(source_bindings or TEST_SOURCE_BINDINGS)
    review["reviewed_profile_hash"] = profile_hash
    review["reviewed_fixture_hash"] = fixture_hash
    review["reviewed_matrix_hash"] = matrix_hash
    review["implementation_review_hash"] = stable_hash({key: item for key, item in review.items() if key != "implementation_review_hash"})
    return review


def _bind_review(evidence: dict[str, Any], review: dict[str, Any]) -> dict[str, Any]:
    rebound = deepcopy(evidence)
    rebound["final_implementation_review_hash"] = review["implementation_review_hash"]
    rebound["evidence_hash"] = stable_hash({key: item for key, item in rebound.items() if key != "evidence_hash"})
    return rebound


def _freeze_bundle(tmp_path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], str, str]:
    api = _release_api("build_p137_freeze_manifest", "p137_profile_hash", "p137_fixture_hash")
    canonical_matrix = _preliminary_matrix(tmp_path)
    evidence = {"cases": canonical_matrix["cases"], "matrix_hash": canonical_matrix["matrix_hash"]}
    profile = local_triage_profile()
    profile_hash = api.p137_profile_hash(profile)
    fixture_hash = api.p137_fixture_hash(profile)
    manifest = api.build_p137_freeze_manifest(
        source_bindings=TEST_SOURCE_BINDINGS,
        profile=profile,
        matrix_hash=evidence["matrix_hash"],
        case_input_hash=canonical_matrix["case_input_hash"],
        case_config_hash=canonical_matrix["case_config_hash"],
        case_evidence_hash=canonical_matrix["case_evidence_hash"],
    )
    review = _review_for(matrix_hash=evidence["matrix_hash"], profile_hash=profile_hash, fixture_hash=fixture_hash)
    return evidence, canonical_matrix, manifest, review, profile_hash, fixture_hash


def test_release_evidence_validation_requires_final_frozen_implementation_review(tmp_path: Path) -> None:
    api = _release_api("validate_p137_release_evidence")
    evidence = _matrix(tmp_path)

    with pytest.raises(_error(), match="final_implementation_review_required"):
        api.validate_p137_release_evidence(evidence, expected_source_hashes=TEST_SOURCE_BINDINGS)


def test_fixture_hash_binds_fixture_tree_bytes_and_rejects_symlinks(tmp_path: Path) -> None:
    api = _release_api("p137_fixture_hash")
    fixture = tmp_path / "evals/p137/input"
    fixture.mkdir(parents=True)
    profile = local_triage_profile()
    profile_path = fixture / "local-triage-profile.json"
    profile_path.write_text("one", encoding="utf-8")
    first = api.p137_fixture_hash(profile, project_root=tmp_path)
    profile_path.write_text("two", encoding="utf-8")
    second = api.p137_fixture_hash(profile, project_root=tmp_path)

    assert first != second
    link = fixture / "linked"
    link.symlink_to(profile_path)
    with pytest.raises(_error(), match="fixture_tree_symlink_forbidden"):
        api.p137_fixture_hash(profile, project_root=tmp_path)


def test_frozen_matrix_rejects_tampered_complete_case_input_binding(tmp_path: Path) -> None:
    api = _release_api("assemble_p137_release_evidence_from_frozen_matrix")
    _, canonical_matrix, manifest, review, profile_hash, fixture_hash = _freeze_bundle(tmp_path)
    tampered = deepcopy(canonical_matrix)
    tampered["case_inputs"][0]["bindings"]["request_budget"]["max_output_records"] = 1

    with pytest.raises(_error(), match="case_input_binding_hash_invalid"):
        api.assemble_p137_release_evidence_from_frozen_matrix(
            tampered,
            freeze_manifest=manifest,
            final_implementation_review=review,
            expected_source_hashes=TEST_SOURCE_BINDINGS,
            expected_profile_hash=profile_hash,
            expected_fixture_hash=fixture_hash,
        )


def test_release_evidence_consumes_frozen_matrix_and_review_without_regeneration(tmp_path: Path) -> None:
    api = _release_api("validate_p137_release_evidence")
    evidence = _matrix(tmp_path)
    profile = local_triage_profile()
    profile_hash = _release_api("p137_profile_hash").p137_profile_hash(profile)
    fixture_hash = _release_api("p137_fixture_hash").p137_fixture_hash(profile)
    review = _review_for(matrix_hash=evidence["matrix_hash"], profile_hash=profile_hash, fixture_hash=fixture_hash)
    evidence = _bind_review(evidence, review)

    validated = api.validate_p137_release_evidence(
        evidence,
        expected_source_hashes=TEST_SOURCE_BINDINGS,
        final_implementation_review=review,
        expected_profile_hash=profile_hash,
        expected_fixture_hash=fixture_hash,
        expected_matrix_hash=evidence["matrix_hash"],
    )

    assert validated["status"] == "p137_local_evidence_triage_qualified"
    assert validated["totals"] == {"expected": 60, "passed": 60, "failed": 0}
    assert validated["final_implementation_review_hash"] == review["implementation_review_hash"]


def test_release_evidence_rejects_stale_source_or_matrix_after_review(tmp_path: Path) -> None:
    api = _release_api("validate_p137_release_evidence")
    evidence = _matrix(tmp_path)
    profile = local_triage_profile()
    profile_hash = _release_api("p137_profile_hash").p137_profile_hash(profile)
    fixture_hash = _release_api("p137_fixture_hash").p137_fixture_hash(profile)
    review = _review_for(matrix_hash=evidence["matrix_hash"], profile_hash=profile_hash, fixture_hash=fixture_hash)
    evidence = _bind_review(evidence, review)

    stale_source = dict(TEST_SOURCE_BINDINGS)
    stale_source["app/services/p137_runner.py"] = "sha256:" + "1" * 64
    with pytest.raises(_error(), match="release_evidence_source_stale"):
        api.validate_p137_release_evidence(
            evidence,
            expected_source_hashes=stale_source,
            final_implementation_review=review,
            expected_profile_hash=profile_hash,
            expected_fixture_hash=fixture_hash,
            expected_matrix_hash=evidence["matrix_hash"],
        )

    tampered = deepcopy(evidence)
    tampered["cases"][0]["status"] = "failed"
    with pytest.raises(_error(), match="case_actual_expected_mismatch|evidence_hash_invalid|rebuilt_totals_mismatch"):
        api.validate_p137_release_evidence(
            tampered,
            expected_source_hashes=TEST_SOURCE_BINDINGS,
            final_implementation_review=review,
            expected_profile_hash=profile_hash,
            expected_fixture_hash=fixture_hash,
            expected_matrix_hash=evidence["matrix_hash"],
        )

    stale_review = _review_for(matrix_hash="sha256:" + "2" * 64, profile_hash=profile_hash, fixture_hash=fixture_hash)
    stale_review_evidence = _bind_review(evidence, stale_review)
    with pytest.raises(_error(), match="implementation_review_matrix_stale"):
        api.validate_p137_release_evidence(
            stale_review_evidence,
            expected_source_hashes=TEST_SOURCE_BINDINGS,
            final_implementation_review=stale_review,
            expected_profile_hash=profile_hash,
            expected_fixture_hash=fixture_hash,
            expected_matrix_hash=evidence["matrix_hash"],
        )


@pytest.mark.parametrize("counter_map", ["runtime_activity", "expected_runtime_activity"])
def test_release_evidence_rejects_tampered_case_delta_profile(tmp_path: Path, counter_map: str) -> None:
    api = _release_api("validate_p137_release_evidence")
    evidence = _matrix(tmp_path)
    tampered = deepcopy(evidence)
    case_evidence = tampered["cases"][0]["evidence"]
    case_evidence[counter_map]["lease_acquire_count"] += 1

    with pytest.raises(_error(), match="case_runtime_activity_delta_profile_mismatch"):
        api.validate_p137_release_evidence(
            tampered,
            expected_source_hashes=TEST_SOURCE_BINDINGS,
            final_implementation_review=final_implementation_review(TEST_SOURCE_BINDINGS),
        )


def test_frozen_release_workflow_preliminary_does_not_need_review(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    script = importlib.import_module("scripts.run_p137_local_triage")
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(stable_json(local_triage_profile()), encoding="utf-8")
    output_dir = tmp_path / "out"

    monkeypatch.setattr(script, "current_p137_source_hashes", lambda _root: TEST_SOURCE_BINDINGS)
    monkeypatch.setattr(
        script,
        "run_p137_preliminary_matrix",
        lambda *_args, **_kwargs: _preliminary_matrix(tmp_path),
    )

    status = script.main(
        [
            "--mode",
            "preliminary",
            "--profile",
            profile_path.as_posix(),
            "--output-dir",
            output_dir.as_posix(),
            "--canonical-matrix",
            (output_dir / "canonical-matrix.json").as_posix(),
            "--freeze-manifest",
            (output_dir / "freeze-manifest.json").as_posix(),
            "--final-implementation-review",
            (tmp_path / "missing-review.json").as_posix(),
        ]
    )

    assert status == 0
    assert (output_dir / "canonical-matrix.json").is_file()
    assert (output_dir / "freeze-manifest.json").is_file()
    assert not (output_dir / "release-evidence.json").exists()


def test_frozen_release_workflow_final_does_not_regenerate_cases(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    script = importlib.import_module("scripts.run_p137_local_triage")
    _, canonical_matrix, manifest, review, _, _ = _freeze_bundle(tmp_path)
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(stable_json(local_triage_profile()), encoding="utf-8")
    matrix_path = tmp_path / "canonical-matrix.json"
    manifest_path = tmp_path / "freeze-manifest.json"
    review_path = tmp_path / "review.json"
    matrix_path.write_text(stable_json(canonical_matrix), encoding="utf-8")
    manifest_path.write_text(stable_json(manifest), encoding="utf-8")
    review_path.write_text(stable_json(review), encoding="utf-8")

    def fail_runner(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("final mode must not regenerate cases")

    monkeypatch.setattr(script, "current_p137_source_hashes", lambda _root: TEST_SOURCE_BINDINGS)
    monkeypatch.setattr(script, "run_p137_preliminary_matrix", fail_runner)

    status = script.main(
        [
            "--mode",
            "final",
            "--profile",
            profile_path.as_posix(),
            "--output-dir",
            (tmp_path / "out").as_posix(),
            "--canonical-matrix",
            matrix_path.as_posix(),
            "--freeze-manifest",
            manifest_path.as_posix(),
            "--final-implementation-review",
            review_path.as_posix(),
        ]
    )

    assert status == 0


def test_frozen_release_workflow_rejects_stale_matrix_profile_fixture_or_source(tmp_path: Path) -> None:
    api = _release_api("assemble_p137_release_evidence_from_frozen_matrix")
    _, canonical_matrix, manifest, review, profile_hash, fixture_hash = _freeze_bundle(tmp_path)

    stale_source = dict(TEST_SOURCE_BINDINGS)
    stale_source["app/services/p137_runner.py"] = "sha256:" + "3" * 64
    with pytest.raises(_error(), match="freeze_manifest_source_stale"):
        api.assemble_p137_release_evidence_from_frozen_matrix(
            canonical_matrix,
            freeze_manifest=manifest,
            final_implementation_review=review,
            expected_source_hashes=stale_source,
            expected_profile_hash=profile_hash,
            expected_fixture_hash=fixture_hash,
        )

    with pytest.raises(_error(), match="freeze_manifest_profile_stale"):
        api.assemble_p137_release_evidence_from_frozen_matrix(
            canonical_matrix,
            freeze_manifest=manifest,
            final_implementation_review=review,
            expected_source_hashes=TEST_SOURCE_BINDINGS,
            expected_profile_hash="sha256:" + "4" * 64,
            expected_fixture_hash=fixture_hash,
        )

    with pytest.raises(_error(), match="freeze_manifest_fixture_stale"):
        api.assemble_p137_release_evidence_from_frozen_matrix(
            canonical_matrix,
            freeze_manifest=manifest,
            final_implementation_review=review,
            expected_source_hashes=TEST_SOURCE_BINDINGS,
            expected_profile_hash=profile_hash,
            expected_fixture_hash="sha256:" + "5" * 64,
        )

    tampered_matrix = deepcopy(canonical_matrix)
    tampered_matrix["cases"][0]["status"] = "failed"
    with pytest.raises(_error(), match="frozen_matrix_hash_invalid"):
        api.assemble_p137_release_evidence_from_frozen_matrix(
            tampered_matrix,
            freeze_manifest=manifest,
            final_implementation_review=review,
            expected_source_hashes=TEST_SOURCE_BINDINGS,
            expected_profile_hash=profile_hash,
            expected_fixture_hash=fixture_hash,
        )

    stale_manifest = deepcopy(manifest)
    stale_manifest["case_input_hash"] = "sha256:" + "6" * 64
    stale_manifest["freeze_manifest_hash"] = stable_hash({key: item for key, item in stale_manifest.items() if key != "freeze_manifest_hash"})
    with pytest.raises(_error(), match="freeze_manifest_case_input_stale"):
        api.assemble_p137_release_evidence_from_frozen_matrix(
            canonical_matrix,
            freeze_manifest=stale_manifest,
            final_implementation_review=review,
            expected_source_hashes=TEST_SOURCE_BINDINGS,
            expected_profile_hash=profile_hash,
            expected_fixture_hash=fixture_hash,
        )


def test_frozen_release_rejects_unbound_evaluator_or_resource_overhead(tmp_path: Path) -> None:
    api = _release_api("assemble_p137_release_evidence_from_frozen_matrix")
    _, canonical_matrix, manifest, review, profile_hash, fixture_hash = _freeze_bundle(tmp_path)

    tampered_evaluator = deepcopy(canonical_matrix)
    tampered_evaluator["expected_evaluator_overhead_activity"]["runner_invocation_count"] += 1
    with pytest.raises(_error(), match="matrix_evaluator_overhead_delta_profile_mismatch"):
        api.assemble_p137_release_evidence_from_frozen_matrix(
            tampered_evaluator,
            freeze_manifest=manifest,
            final_implementation_review=review,
            expected_source_hashes=TEST_SOURCE_BINDINGS,
            expected_profile_hash=profile_hash,
            expected_fixture_hash=fixture_hash,
        )

    tampered_resource = deepcopy(canonical_matrix)
    tampered_resource["resource_overhead_usage"]["wall_time_ms"] += 1
    with pytest.raises(_error(), match="matrix_resource_usage_totals_mismatch"):
        api.assemble_p137_release_evidence_from_frozen_matrix(
            tampered_resource,
            freeze_manifest=manifest,
            final_implementation_review=review,
            expected_source_hashes=TEST_SOURCE_BINDINGS,
            expected_profile_hash=profile_hash,
            expected_fixture_hash=fixture_hash,
        )


def test_frozen_release_rederives_evaluator_expectations_from_case_input_oracle(tmp_path: Path) -> None:
    api = _release_api("assemble_p137_release_evidence_from_frozen_matrix")
    _, matrix, manifest, review, profile_hash, fixture_hash = _freeze_bundle(tmp_path)
    tampered = deepcopy(matrix)
    case = tampered["cases"][0]
    for field in ("evaluator_activity", "expected_evaluator_activity"):
        case["evidence"][field]["handoff_fixture_write_count"] += 1
    case["case_evidence_hash"] = stable_hash({key: item for key, item in case.items() if key != "case_evidence_hash"})
    tampered["evaluator_activity"]["handoff_fixture_write_count"] += 1
    tampered["matrix_hash"] = stable_hash(tampered["cases"])
    tampered["case_evidence_hash"] = stable_hash([item["case_evidence_hash"] for item in tampered["cases"]])

    rebound_manifest = deepcopy(manifest)
    rebound_manifest["matrix_hash"] = tampered["matrix_hash"]
    rebound_manifest["case_evidence_hash"] = tampered["case_evidence_hash"]
    rebound_manifest["freeze_manifest_hash"] = stable_hash(
        {key: item for key, item in rebound_manifest.items() if key != "freeze_manifest_hash"}
    )
    rebound_review = _review_for(
        matrix_hash=tampered["matrix_hash"],
        profile_hash=profile_hash,
        fixture_hash=fixture_hash,
    )

    with pytest.raises(_error(), match="case_expected_evaluator_oracle_mismatch"):
        api.assemble_p137_release_evidence_from_frozen_matrix(
            tampered,
            freeze_manifest=rebound_manifest,
            final_implementation_review=rebound_review,
            expected_source_hashes=TEST_SOURCE_BINDINGS,
            expected_profile_hash=profile_hash,
            expected_fixture_hash=fixture_hash,
        )


def test_frozen_release_rederives_runtime_expectations_from_case_input_oracle(tmp_path: Path) -> None:
    api = _release_api("assemble_p137_release_evidence_from_frozen_matrix")
    _, matrix, manifest, review, profile_hash, fixture_hash = _freeze_bundle(tmp_path)
    tampered = deepcopy(matrix)
    case = tampered["cases"][57]
    for field in ("runtime_activity", "expected_runtime_activity"):
        case["evidence"][field]["lease_acquire_count"] += 1
    case["case_evidence_hash"] = stable_hash({key: item for key, item in case.items() if key != "case_evidence_hash"})
    tampered["matrix_hash"] = stable_hash(tampered["cases"])
    tampered["case_evidence_hash"] = stable_hash([item["case_evidence_hash"] for item in tampered["cases"]])

    rebound_manifest = deepcopy(manifest)
    rebound_manifest["matrix_hash"] = tampered["matrix_hash"]
    rebound_manifest["case_evidence_hash"] = tampered["case_evidence_hash"]
    rebound_manifest["freeze_manifest_hash"] = stable_hash(
        {key: item for key, item in rebound_manifest.items() if key != "freeze_manifest_hash"}
    )
    rebound_review = _review_for(
        matrix_hash=tampered["matrix_hash"],
        profile_hash=profile_hash,
        fixture_hash=fixture_hash,
    )

    with pytest.raises(_error(), match="case_expected_runtime_oracle_mismatch"):
        api.assemble_p137_release_evidence_from_frozen_matrix(
            tampered,
            freeze_manifest=rebound_manifest,
            final_implementation_review=rebound_review,
            expected_source_hashes=TEST_SOURCE_BINDINGS,
            expected_profile_hash=profile_hash,
            expected_fixture_hash=fixture_hash,
        )


def test_freeze_manifest_binds_full_effective_p137_config_for_every_case(tmp_path: Path) -> None:
    api = _release_api("assemble_p137_release_evidence_from_frozen_matrix")
    _, matrix, manifest, review, profile_hash, fixture_hash = _freeze_bundle(tmp_path)
    tampered = deepcopy(matrix)
    binding = tampered["case_inputs"][0]
    config = binding["bindings"]["effective_p137_config"]
    config["limits"]["max_correlation_window_ms"] += 1
    config["config_hash"] = stable_hash({key: item for key, item in config.items() if key != "config_hash"})
    binding["runtime_input_hash"] = stable_hash(binding["bindings"])
    tampered["case_input_hash"] = stable_hash(tampered["case_inputs"])
    tampered["case_config_hash"] = stable_hash(
        [
            {
                "case_id": item["case_id"],
                "config_hash": item["bindings"]["effective_p137_config"]["config_hash"],
            }
            for item in tampered["case_inputs"]
        ]
    )
    rebound_manifest = deepcopy(manifest)
    rebound_manifest["case_input_hash"] = tampered["case_input_hash"]
    rebound_manifest["freeze_manifest_hash"] = stable_hash(
        {key: item for key, item in rebound_manifest.items() if key != "freeze_manifest_hash"}
    )

    with pytest.raises(_error(), match="freeze_manifest_case_config_stale"):
        api.assemble_p137_release_evidence_from_frozen_matrix(
            tampered,
            freeze_manifest=rebound_manifest,
            final_implementation_review=review,
            expected_source_hashes=TEST_SOURCE_BINDINGS,
            expected_profile_hash=profile_hash,
            expected_fixture_hash=fixture_hash,
        )


def test_final_review_rejects_unresolved_p0_p1_p2_findings() -> None:
    api = _release_api("validate_final_implementation_review")
    review = final_implementation_review(TEST_SOURCE_BINDINGS)
    review["findings"]["p2"] = 1
    review["implementation_review_hash"] = "sha256:" + "0" * 64

    with pytest.raises(_error(), match="implementation_review_blocking_findings"):
        api.validate_final_implementation_review(review, expected_source_hashes=TEST_SOURCE_BINDINGS)


def test_local_triage_profile_schema_is_exact_and_source_bound() -> None:
    api = _release_api("validate_local_triage_profile")
    profile = local_triage_profile()

    assert api.validate_local_triage_profile(profile)["required_case_ids"] == [f"p137-case-{index:02d}" for index in range(1, 61)]

    bad = deepcopy(profile)
    bad["required_case_ids"] = bad["required_case_ids"][:-1]
    with pytest.raises(_error(), match="required_case_ids_mismatch"):
        api.validate_local_triage_profile(bad)


def stable_json(value: dict[str, Any]) -> str:
    import json

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
