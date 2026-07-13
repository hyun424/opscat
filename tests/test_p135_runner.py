from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p135_release_evidence import (
    EXPECTED_PROVIDER_SUCCESSES,
    REQUIRED_CASES,
    build_independent_review_artifact,
    current_source_hashes,
    validate_p135_release_evidence,
)
from scripts import run_p135_provider_export_attachment as runner


def _profile() -> dict[str, Any]:
    return {
        "schema_version": "p135.provider_export_profile.v1",
        "case_matrix_version": 1,
        "authority_contract_id": "p135-local-export-attachment",
        "authority_host_label": "local-artifact.telemetry-read",
        "authority_request_id_prefix": "p135-local-",
        "root_ref_hash": stable_hash({"root": "tmp-p135-fixtures"}),
        "input_root": "evals/p135/input/exports",
        "output_artifacts": [
            "authority-ledger.json",
            "case-matrix.json",
            "execution-ledger.json",
            "normalized-bundles.json",
            "release-evidence.json",
        ],
        "required_cases": list(REQUIRED_CASES),
        "resource_limits": {
            "wall_limit_ms": 30_000,
            "cpu_limit_ms": 10_000,
            "peak_memory_limit_bytes": 100_663_296,
        },
    }


def test_runner_profile_rejects_case_drift_unknown_fields_and_resolves_input_from_repo_root(tmp_path: Path) -> None:
    assert runner._validate_profile(_profile())["required_cases"] == list(REQUIRED_CASES)

    unknown = _profile()
    unknown["optimistic_extension"] = True
    with pytest.raises(ValueError, match="unexpected_profile_field:optimistic_extension"):
        runner._validate_profile(unknown)

    drifted = _profile()
    drifted["required_cases"] = list(REQUIRED_CASES[:-1])
    with pytest.raises(ValueError, match="required_cases_mismatch"):
        runner._validate_profile(drifted)

    nested_profile = tmp_path / "evals/p135/input/provider-export-profile.json"
    nested_profile.parent.mkdir(parents=True)
    nested_profile.write_text(json.dumps(_profile()), encoding="utf-8")
    assert runner._profile_input_root(_profile(), profile_path=nested_profile) == (runner.ROOT / "evals/p135/input/exports").resolve()


def test_peak_memory_bytes_normalizes_macos_and_linux_units() -> None:
    assert runner._peak_memory_bytes(12_345, platform="darwin") == 12_345
    assert runner._peak_memory_bytes(12_345, platform="linux") == 12_345 * 1024


def test_forbidden_runtime_guard_measures_and_blocks_socket_access() -> None:
    guard = runner._ForbiddenRuntimeGuard()
    with pytest.raises(RuntimeError, match="forbidden_runtime_surface:socket_call_count"):
        with guard:
            runner.socket.socket()

    assert guard.counters["socket_call_count"] == 1


def test_runner_builds_exact_30_case_matrix_from_real_provider_execution() -> None:
    matrix, authority_ledger, execution_ledger, bundles = runner._run_case_matrix(
        _profile(),
        runner.ROOT / "evals/p135/input/exports",
    )

    assert matrix["totals"] == {
        "expected_cases": 30,
        "passed_cases": 30,
        "failed_cases": 0,
        "successful_provider_attachments": 5,
        "duplicate_cases": 1,
        "rejected_cases": 24,
        "denominator_scope": "principal_provider_export_assertions",
    }
    assert matrix["provider_successes"] == EXPECTED_PROVIDER_SUCCESSES
    assert list(matrix["required_cases"]) == list(REQUIRED_CASES)
    assert set(matrix["cases"]) == set(REQUIRED_CASES)
    assert all(case["passed"] is True for case in matrix["cases"].values())
    assert execution_ledger["schema_version"] == "p135.export_execution_ledger.v1"
    assert len(execution_ledger["receipts"]) == 5
    assert authority_ledger["observation_activity"]["local_file_read_count"] > execution_ledger["counters"]["local_file_read_count"]
    assert bundles["schema_version"] == "p135.canonical_normalized_bundles.v1"
    assert len(bundles["success_bundles"]) == 6
    assert len(bundles["failure_bundles"]) == 9
    runner._revalidate_provider_artifacts(execution_ledger, bundles)


def test_run_case_matrix_calls_provider_attachment_and_semantic_validators(monkeypatch: pytest.MonkeyPatch) -> None:
    real_provider = runner.importlib.import_module("app.services.p135_provider_export_attachment")
    calls: dict[str, int] = {
        "build_export_manifest": 0,
        "new_execution_ledger": 0,
        "attach_export": 0,
        "validate_execution_ledger": 0,
        "validate_normalized_bundle": 0,
        "validate_denominator_failure_bundle": 0,
    }

    class RecordingProvider:
        os = real_provider.os

        @staticmethod
        def zero_forbidden_authority() -> dict[str, int]:
            return real_provider.zero_forbidden_authority()

        @staticmethod
        def zero_observation_activity() -> dict[str, int]:
            return real_provider.zero_observation_activity()

        @staticmethod
        def build_export_manifest(*args: Any, **kwargs: Any) -> dict[str, Any]:
            calls["build_export_manifest"] += 1
            return real_provider.build_export_manifest(*args, **kwargs)

        @staticmethod
        def validate_export_manifest(*args: Any, **kwargs: Any) -> None:
            return real_provider.validate_export_manifest(*args, **kwargs)

        @staticmethod
        def new_execution_ledger(*args: Any, **kwargs: Any) -> dict[str, Any]:
            calls["new_execution_ledger"] += 1
            return real_provider.new_execution_ledger(*args, **kwargs)

        @staticmethod
        def attach_export(*args: Any, **kwargs: Any) -> Any:
            calls["attach_export"] += 1
            return real_provider.attach_export(*args, **kwargs)

        @staticmethod
        def validate_execution_ledger(*args: Any, **kwargs: Any) -> None:
            calls["validate_execution_ledger"] += 1
            return real_provider.validate_execution_ledger(*args, **kwargs)

        @staticmethod
        def validate_normalized_bundle(*args: Any, **kwargs: Any) -> None:
            calls["validate_normalized_bundle"] += 1
            return real_provider.validate_normalized_bundle(*args, **kwargs)

        @staticmethod
        def validate_denominator_failure_bundle(*args: Any, **kwargs: Any) -> None:
            calls["validate_denominator_failure_bundle"] += 1
            return real_provider.validate_denominator_failure_bundle(*args, **kwargs)

    monkeypatch.setattr(runner, "_provider_api", lambda: RecordingProvider)

    matrix, authority_ledger, execution_ledger, bundles = runner._run_case_matrix(
        _profile(),
        runner.ROOT / "evals/p135/input/exports",
    )

    assert matrix["totals"]["passed_cases"] == 30
    assert authority_ledger["observation_activity"]["duplicate_validation_read_count"] == 1
    assert execution_ledger["ledger_hash"] == bundles["validation_context"]["provider_success_ledger_hash"]
    assert calls["build_export_manifest"] >= 8
    assert calls["new_execution_ledger"] >= 5
    assert calls["attach_export"] >= 18
    assert calls["validate_execution_ledger"] >= 7
    assert calls["validate_normalized_bundle"] >= 6
    assert calls["validate_denominator_failure_bundle"] >= 9


def test_revalidation_rejects_forged_execution_ledger_and_bundle_artifacts() -> None:
    _, _, execution_ledger, bundles = runner._run_case_matrix(
        _profile(),
        runner.ROOT / "evals/p135/input/exports",
    )

    forged_ledger = deepcopy(execution_ledger)
    forged_ledger["authority_counters"]["network_call_count"] = 1
    forged_ledger["ledger_hash"] = stable_hash({key: value for key, value in forged_ledger.items() if key != "ledger_hash"})
    with pytest.raises(ValueError, match="network_call_count_nonzero"):
        runner._revalidate_provider_artifacts(forged_ledger, bundles)

    forged_bundles = deepcopy(bundles)
    forged_bundles["success_bundles"][0]["artifact_bytes"] += 1
    forged_bundles["success_bundles"][0]["bundle_hash"] = stable_hash(
        {key: value for key, value in forged_bundles["success_bundles"][0].items() if key != "bundle_hash"}
    )
    forged_bundles["bundles_hash"] = stable_hash({key: value for key, value in forged_bundles.items() if key != "bundles_hash"})
    with pytest.raises(ValueError, match="receipt_bundle_hash_mismatch|receipt_bundle_count_mismatch|bundle_hash_invalid"):
        runner._revalidate_provider_artifacts(execution_ledger, forged_bundles)

    synthetic_bundles = {
        "schema_version": "p135.canonical_normalized_bundles.v1",
        "bundle_refs": [{"case": "prometheus_matrix_success", "provider": "prometheus", "bundle_hash": stable_hash({"synthetic": True})}],
        "bundles_hash": stable_hash({"synthetic": True}),
    }
    with pytest.raises(ValueError, match="unexpected_normalized_bundles_field:bundle_refs|missing_normalized_bundles_field"):
        runner._revalidate_provider_artifacts(execution_ledger, synthetic_bundles)


def test_main_rejects_forged_runner_outputs_before_release_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    matrix, authority_ledger, execution_ledger, bundles = runner._run_case_matrix(
        _profile(),
        runner.ROOT / "evals/p135/input/exports",
    )
    forged_ledger = deepcopy(execution_ledger)
    forged_ledger["authority_counters"]["network_call_count"] = 1
    forged_ledger["ledger_hash"] = stable_hash({key: value for key, value in forged_ledger.items() if key != "ledger_hash"})
    monkeypatch.setattr(runner, "_run_case_matrix", lambda _profile, _input_root: (matrix, authority_ledger, forged_ledger, bundles))

    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(_profile()), encoding="utf-8")
    output_dir = tmp_path / "out"

    status = runner.main(["--profile", str(profile_path), "--output-dir", str(output_dir)])

    assert status == 1
    assert not output_dir.exists()
    error = json.loads(capsys.readouterr().err)
    assert error["release_status"] == "p135_blocked"
    assert error["error"] == "network_call_count_nonzero"


def test_runner_writes_only_exact_atomic_artifact_set(tmp_path: Path) -> None:
    payloads = {
        "case-matrix.json": {"artifact": "matrix"},
        "authority-ledger.json": {"artifact": "authority"},
        "release-evidence.json": {"artifact": "release"},
        "execution-ledger.json": {"artifact": "execution"},
        "normalized-bundles.json": {"artifact": "bundles"},
    }

    runner._write_exact_artifacts(tmp_path, payloads)

    assert sorted(path.name for path in tmp_path.iterdir()) == sorted(payloads)
    assert not list(tmp_path.glob(".*.tmp"))
    for name, payload in payloads.items():
        assert json.loads((tmp_path / name).read_text(encoding="utf-8")) == payload

    with pytest.raises(ValueError, match="artifact_set_invalid"):
        runner._write_exact_artifacts(tmp_path, {"release-evidence.json": {}})


def test_runner_fails_closed_when_provider_module_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def missing_provider() -> Any:
        raise ModuleNotFoundError("missing p135 provider")

    monkeypatch.setattr(runner, "_provider_api", missing_provider)
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(_profile()), encoding="utf-8")
    output_dir = tmp_path / "out"

    status = runner.main(["--profile", str(profile_path), "--output-dir", str(output_dir)])

    assert status == 1
    assert not output_dir.exists()
    error = json.loads(capsys.readouterr().err)
    assert error["release_status"] == "p135_blocked"
    assert error["error_type"] == "ModuleNotFoundError"


def test_runner_release_evidence_validates_with_real_matrix_and_review(tmp_path: Path) -> None:
    matrix, authority_ledger, _, _ = runner._run_case_matrix(_profile(), runner.ROOT / "evals/p135/input/exports")
    root = tmp_path / "project"
    expected_hashes = current_source_hashes(runner.ROOT)
    for relative in expected_hashes:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        source = runner.ROOT / relative
        path.write_bytes(source.read_bytes())
    assert current_source_hashes(root) == expected_hashes

    review = build_independent_review_artifact(
        reviewed_source_hashes=current_source_hashes(root),
        reviewer_context_hash=stable_hash({"context": "review"}),
        implementation_context_hash=stable_hash({"context": "impl"}),
        findings={"p0": 0, "p1": 0, "p2": 0, "p3": 0},
    )
    matrix["resource_usage"] = {
        "wall_time_ms": 1,
        "cpu_time_ms": 1,
        "peak_memory_bytes": 1,
        **runner.RESOURCE_LIMITS,
    }
    matrix["matrix_hash"] = stable_hash({key: value for key, value in matrix.items() if key != "matrix_hash"})
    release = runner.build_p135_release_evidence(matrix, authority_ledger, review, project_root=root)

    validate_p135_release_evidence(
        release,
        case_matrix=matrix,
        authority_ledger=authority_ledger,
        independent_review=review,
        project_root=root,
    )
