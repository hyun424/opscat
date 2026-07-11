from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest

from app.services.p110_evaluation import stable_hash
from scripts.run_p122_performance_soak import (
    CRASH_EXIT_CODE,
    PROMOTED_ARTIFACTS_RELATIVE,
    RELEASE_STAGE_ADAPTER_NAMES,
    RELEASE_STAGE_CRASH_POINTS,
    RELEASE_STAGE_OPERATIONS,
    RELEASE_STAGE_OUTPUT_SCHEMAS,
    compare_performance_reports,
    main,
    performance_semantic_projection,
    prepare_release_stage_crash,
    promote_performance_artifacts,
    recover_release_stage_crash,
    run_soak,
    validate_promoted_performance_artifacts,
)


def test_local_soak_preserves_every_record_and_zero_authority(tmp_path: Path) -> None:
    report = cast(dict[str, Any], run_soak(iterations=10, workdir=tmp_path))
    validation_proof_fields = {
        "install": "installed_file_count",
        "demo_startup": "event_count",
        "incident_ingest": "case_id",
        "evidence_request": "evidence_id",
        "decision": "route",
        "approval": "approved",
        "validation": "validation_passed",
        "rollback": "rollback_attempted",
        "replay_write": "point_count",
        "eval_write": "case_count",
        "release_evidence_write": "contract_validation_executed",
        "report_write": "checked_doc_count",
    }
    assert report["schema_version"] == "p122.performance_soak.v2"
    assert report["expected_records"]["replay_records"] == 10
    assert report["observed_records"]["replay_records"] == 10
    assert report["unique_replay_files"] == 10
    assert report["lost_replay_records"] == 0
    assert report["lost_incident_records"] == 0
    assert report["lost_audit_records"] == 0
    assert report["lost_timeline_records"] == 0
    assert report["lost_authority_records"] == 0
    crash_replay = report["release_stage_crash_replay"]
    assert crash_replay["point_count"] == 12
    assert crash_replay["injected_count"] == 12
    assert crash_replay["recovered_count"] == 12
    assert crash_replay["verified"] is True
    assert crash_replay["protocol"] == "multiprocessing-spawn-exit-restart"
    assert set(RELEASE_STAGE_OPERATIONS) == set(report["release_stage_crash_inventory"])
    assert {point["stage"] for point in crash_replay["points"]} == set(report["release_stage_crash_inventory"])
    assert {point["operation"] for point in crash_replay["points"]} == set(RELEASE_STAGE_OPERATIONS.values())
    for point in crash_replay["points"]:
        assert point["crash_exit_code"] == CRASH_EXIT_CODE
        assert point["recovery_exit_code"] == 0
        assert point["crash_worker_pid"] > 0
        assert point["recovery_worker_pid"] > 0
        assert point["crash_worker_pid"] != point["recovery_worker_pid"]
        assert point["restart_verified"] is True
        assert point["operation_adapter"] == RELEASE_STAGE_ADAPTER_NAMES[point["stage"]]
        assert point["output_schema"] == RELEASE_STAGE_OUTPUT_SCHEMAS[point["stage"]]
        assert point["adapter_invoked"] is True
        assert point["precommit_hash"].startswith("sha256:")
        assert point["output_hash"] == point["precommit_hash"]
        assert point["post_restart_validation"] is True
        assert Path(point["output_ref"]).exists()
        receipt = json.loads(Path(point["restart_receipt_ref"]).read_text(encoding="utf-8"))
        assert receipt["schema_version"] == "p122.release_stage_restart_receipt.v1"
        assert receipt["stage"] == point["stage"]
        assert receipt["operation"] == point["operation"]
        assert receipt["pending_worker_pid"] == point["crash_worker_pid"]
        assert receipt["recovery_worker_pid"] == point["recovery_worker_pid"]
        assert receipt["restart_count"] == 1
        assert point["restart_count"] == 1
        assert point["pending_record_hash"] == receipt["pending_record_hash"]
        assert point["restart_receipt_hash"] == receipt["record_hash"]
        assert receipt["operation_adapter"] == point["operation_adapter"]
        assert receipt["precommit_hash"] == point["precommit_hash"]
        assert receipt["output_hash"] == point["output_hash"]
        assert receipt["post_restart_validation"] is True
        assert validation_proof_fields[point["stage"]] in receipt["output_validation"]
    install_output = Path(crash_replay["points"][0]["output_ref"])
    install_manifest = json.loads((install_output / "install-manifest.json").read_text(encoding="utf-8"))
    wheel = next((Path(__file__).parents[1] / "dist").glob("opscat-*.whl"))
    assert install_manifest["wheel_checksum"] == "sha256:" + hashlib.sha256(wheel.read_bytes()).hexdigest()
    assert not list(install_output.glob("site-packages/*.dist-info/RECORD"))
    assert all(value == 0 for value in report["authority_counters"].values())
    assert len(report["release_stage_crash_inventory"]) == 12
    assert report["upstream_executed_crash_replay"]["point_count"] >= 15
    assert report["upstream_executed_crash_replay"]["replayed_count"] >= 15
    assert report["upstream_executed_crash_replay"]["pending_rollback_replayed"] is True
    timings = report["timings_seconds"]
    assert timings["install"] >= 0
    assert timings["cold_start"] >= 0
    assert timings["demo_total"] >= 0
    assert timings["demo_samples"] == 10
    assert report["storage_envelope"]["total_bytes"] > 0
    assert report["duration_seconds"] > 0
    observability = report["observability"]
    assert observability["health"]["status"] == "healthy"
    assert observability["readiness"]["ready"] is True
    assert observability["metrics"]["authority_rejections_total"] == 1
    assert observability["authority_rejection"]["reason"] == "production_like_demo_configuration_denied"
    assert observability["diagnostics"]["redaction_verified"] is True
    assert all(log["correlation_id"] for log in observability["correlated_logs"])
    assert "p122-secret-fixture" not in str(observability)
    assert report["semantic_binding"] == performance_semantic_projection(report)["projection_hash"]


def test_semantic_comparison_ignores_measurement_noise_but_rejects_record_loss(tmp_path: Path) -> None:
    report = cast(dict[str, Any], run_soak(iterations=10, workdir=tmp_path / "first"))
    release_path = Path(__file__).parents[1] / "evals/p122/release-evidence.json"
    original_release = release_path.read_bytes()
    mutated_release = json.loads(original_release)
    mutated_release["release_status"] = "p122_review_status_changed"
    mutated_release["review"] = {"reviewer_id": "replacement-reviewer", "builder_id": "replacement-builder"}
    mutated_release["release_evidence_hash"] = stable_hash(
        {key: value for key, value in mutated_release.items() if key != "release_evidence_hash"}
    )
    try:
        release_path.write_text(json.dumps(mutated_release, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        candidate = cast(dict[str, Any], run_soak(iterations=10, workdir=tmp_path / "second"))
    finally:
        release_path.write_bytes(original_release)
    assert compare_performance_reports(report, candidate)["matches"] is True
    assert [point["precommit_hash"] for point in report["release_stage_crash_replay"]["points"]] == [
        point["precommit_hash"] for point in candidate["release_stage_crash_replay"]["points"]
    ]
    release_index = RELEASE_STAGE_CRASH_POINTS.index("release_evidence_write")
    assert report["release_stage_crash_replay"]["points"][release_index]["precommit_hash"] == candidate[
        "release_stage_crash_replay"
    ]["points"][release_index]["precommit_hash"]
    candidate["elapsed_seconds"] = float(report["elapsed_seconds"]) + 100.0
    candidate["timings_seconds"]["cold_start"] = float(report["timings_seconds"]["cold_start"]) + 10.0
    candidate["report_hash"] = "sha256:different"
    assert compare_performance_reports(report, candidate)["matches"] is True

    candidate["lost_replay_records"] = 1
    assert compare_performance_reports(report, candidate)["matches"] is False


def test_promoted_artifacts_atomically_replace_stale_tree_with_repo_relative_refs(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    artifact_dir = repo_root / PROMOTED_ARTIFACTS_RELATIVE
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "stale.txt").write_text("stale", encoding="utf-8")
    report = cast(dict[str, Any], run_soak(iterations=10, workdir=tmp_path / "work"))
    fresh_projection = performance_semantic_projection(report)

    promote_performance_artifacts(report, artifact_dir=artifact_dir, repo_root=repo_root)

    diagnostics = report["observability"]["diagnostics"]
    assert diagnostics["crash_replay_artifact_root"] == "evals/p122/performance-artifacts/crash-replay"
    assert diagnostics["record_artifact_root"] == "evals/p122/performance-artifacts/records"
    assert not (artifact_dir / "stale.txt").exists()
    assert (artifact_dir / "records/manifest.json").is_file()
    bundle_path = artifact_dir / "records/observed-records.jsonl"
    assert bundle_path.is_file()
    assert len(bundle_path.read_text(encoding="utf-8").splitlines()) == 10
    assert len(list((artifact_dir / "records").iterdir())) == 2
    manifest = json.loads((artifact_dir / "records/manifest.json").read_text(encoding="utf-8"))
    assert manifest["classes"]["incident_records"]["count"] == 10
    assert manifest["classes"]["audit_records"]["count"] == report["observed_records"]["audit_records"]
    assert manifest["classes"]["timeline_records"]["count"] == report["observed_records"]["timeline_records"]
    assert manifest["classes"]["replay_records"]["count"] == 10
    assert manifest["classes"]["authority_records"]["count"] == 10
    assert all(value["hash"].startswith("sha256:") for value in manifest["classes"].values())
    assert not list(artifact_dir.parent.glob(".performance-artifacts.*.tmp"))
    assert not list(artifact_dir.parent.glob(".performance-artifacts.*.backup"))
    for point in report["release_stage_crash_replay"]["points"]:
        assert not Path(point["pending_ref"]).is_absolute()
        assert (repo_root / point["pending_ref"]).is_file()
        assert (repo_root / point["restart_receipt_ref"]).is_file()
        assert (repo_root / point["output_ref"]).exists()
    assert validate_promoted_performance_artifacts(report, repo_root=repo_root) is True
    assert performance_semantic_projection(report) == fresh_projection

    original_bundle = bundle_path.read_bytes()
    bundle_path.write_bytes(original_bundle + b"{}\n")
    assert validate_promoted_performance_artifacts(report, repo_root=repo_root) is False
    bundle_path.write_bytes(original_bundle)
    assert validate_promoted_performance_artifacts(report, repo_root=repo_root) is True

    output_ref = report["release_stage_crash_replay"]["points"][1]["output_ref"]
    output_path = repo_root / output_ref
    output_path.write_text(output_path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    assert validate_promoted_performance_artifacts(report, repo_root=repo_root) is False


def test_recovery_rejects_semantically_tampered_pending_adapter(tmp_path: Path) -> None:
    prepared = cast(dict[str, Any], prepare_release_stage_crash(tmp_path / "decision-stage", stage="decision", ordinal=4))
    pending_path = Path(prepared["stage_root"]) / "pending.json"
    pending = json.loads(pending_path.read_text(encoding="utf-8"))
    pending["operation_adapter"] = RELEASE_STAGE_ADAPTER_NAMES["demo_startup"]
    pending["record_hash"] = stable_hash({key: value for key, value in pending.items() if key != "record_hash"})
    pending_path.write_text(json.dumps(pending, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="release_stage_recovery_worker_failed:decision"):
        recover_release_stage_crash(prepared)
    assert not (Path(prepared["stage_root"]) / "restart-receipt.json").exists()


def test_recovery_rejects_tampered_real_precommit_artifact(tmp_path: Path) -> None:
    prepared = cast(dict[str, Any], prepare_release_stage_crash(tmp_path / "demo-stage", stage="demo_startup", ordinal=1))
    stage_root = Path(prepared["stage_root"])
    precommit = stage_root / "precommit/local-demo.json"
    payload = json.loads(precommit.read_text(encoding="utf-8"))
    payload["network_calls"] = 1
    precommit.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="release_stage_recovery_worker_failed:demo_startup"):
        recover_release_stage_crash(prepared)
    assert not (stage_root / "restart-receipt.json").exists()


def test_release_evidence_recovery_rejects_tampered_deterministic_fixture(tmp_path: Path) -> None:
    prepared = cast(
        dict[str, Any],
        prepare_release_stage_crash(
            tmp_path / "release-evidence-stage",
            stage="release_evidence_write",
            ordinal=10,
        ),
    )
    stage_root = Path(prepared["stage_root"])
    precommit = stage_root / "precommit/release-evidence.json"
    payload = json.loads(precommit.read_text(encoding="utf-8"))
    payload["producer_contract"]["release_id"] = "tampered"
    payload["release_evidence_hash"] = stable_hash(
        {key: value for key, value in payload.items() if key != "release_evidence_hash"}
    )
    precommit.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    pending_path = stage_root / "pending.json"
    pending = json.loads(pending_path.read_text(encoding="utf-8"))
    pending["precommit_hash"] = "sha256:" + hashlib.sha256(precommit.read_bytes()).hexdigest()
    pending["record_hash"] = stable_hash({key: value for key, value in pending.items() if key != "record_hash"})
    pending_path.write_text(json.dumps(pending, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="release_stage_recovery_worker_failed:release_evidence_write"):
        recover_release_stage_crash(prepared)
    assert not (stage_root / "restart-receipt.json").exists()


def test_release_cli_requires_1000_iterations(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--iterations", "999", "--workdir", str(tmp_path / "work"), "--output", str(tmp_path / "out.json")])
    assert exc.value.code == 2


def test_p122_release_profile_reruns_and_compares_promoted_soak() -> None:
    verify_script = (Path(__file__).parents[1] / "scripts/verify.sh").read_text(encoding="utf-8")
    profile = verify_script.split("p122_release_profile_tests() {", 1)[1].split("\n}", 1)[0]
    assert "run_p122_performance_soak.py" in profile
    assert "--iterations 1000" in profile
    assert '--workdir "$VERIFY_TMPDIR/p122-performance-soak"' in profile
    assert '--output "$VERIFY_TMPDIR/p122-performance-soak.json"' in profile
    assert "--compare-report evals/p122/performance-soak.json" in profile
