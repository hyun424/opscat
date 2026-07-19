from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.services.p147_p152_contracts import stable_hash
from app.services.p176_campaign import generate_p176_campaign
from app.services.p176_evaluator import SAFETY_COUNTER_KEYS, evaluate_campaign
from app.services.p176_evidence import append_evidence_record, validate_evidence_chain
from app.services.p176_live_bridge import (
    AGENT_VISIBLE_LEDGER_PATH,
    CANONICAL_SAFETY_COUNTERS_PATH,
    EPISODE_OBSERVATIONS_PATH,
    EVALUATOR_ONLY_LEDGER_PATH,
    HEALTHY_WINDOW_OBSERVATIONS_PATH,
    LIVE_SAFETY_COUNTER_KEYS,
    LIVE_SAFETY_REPORT_PATH,
    RUNTIME_COLLECTION_RECEIPT_PATH,
    RUNTIME_FINALIZATION_RECEIPT_PATH,
    P176LiveBridgeError,
    P176LiveBridgeResult,
    load_json,
    load_jsonl,
    materialize_live_release_inputs,
    write_json,
    write_jsonl,
)
from app.services.p176_release import build_release_artifacts

ROOT = Path(__file__).resolve().parents[1]
TRUSTED_NOW = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
CANONICAL_INPUT_MANIFEST = ROOT / "evals/p176/input/manifest.json"


def test_bridge_materializes_exact_current_release_inputs(tmp_path: Path) -> None:
    run_dir = _write_trusted_live_run(tmp_path / "run")
    plan_paths = _write_reviewed_plan_artifacts(run_dir)

    result = _materialize_live_release_inputs(run_dir, plan_paths=plan_paths)

    outcomes = load_jsonl(run_dir / "live-outcomes.jsonl")
    healthy_results = load_jsonl(run_dir / "live-healthy-results.jsonl")
    safety_counters = load_json(run_dir / CANONICAL_SAFETY_COUNTERS_PATH)
    agent_ledger = load_jsonl(run_dir / AGENT_VISIBLE_LEDGER_PATH)
    evaluator_ledger = load_jsonl(run_dir / EVALUATOR_ONLY_LEDGER_PATH)

    report = evaluate_campaign(
        campaign=generate_p176_campaign(),
        episodes=generate_p176_campaign()["episodes"],
        outcomes=outcomes,
        healthy_windows=generate_p176_campaign()["healthy_windows"],
        healthy_results=healthy_results,
        safety_counters=safety_counters,
    )

    assert result.subordinate_status == "p176_disposable_gcp_live_lab_evidence_ready"
    assert report["qualified"] is True
    assert set(safety_counters) == set(SAFETY_COUNTER_KEYS)
    assert all(value == 0 for value in safety_counters.values())
    validate_evidence_chain(agent_ledger, ledger_name="agent_visible", require_all_source_classes=True)
    validate_evidence_chain(evaluator_ledger, ledger_name="evaluator_only", require_all_source_classes=True)
    assert all(record["evaluator_context_hash"] is None for record in agent_ledger)

    release_manifest = load_json(run_dir / "release-inputs-manifest.json")
    live_manifest = load_json(run_dir / "live-artifact-manifest.json")
    summary = load_json(run_dir / "live-bridge-summary.json")
    assert (run_dir / "input-manifest.json").read_bytes() == CANONICAL_INPUT_MANIFEST.read_bytes()
    assert release_manifest["build_release_artifacts_target"] == "app.services.p176_release.build_release_artifacts"
    assert release_manifest["live_artifact_manifest_hash"] == live_manifest["manifest_hash"]
    assert release_manifest["manifest_hash"] == stable_hash({key: value for key, value in release_manifest.items() if key != "manifest_hash"})
    assert release_manifest["terraform_plan_artifact_bindings"] == _expected_plan_bindings(plan_paths)
    assert set(release_manifest["terraform_plan_artifact_bindings"]) == {
        "reviewed_apply_plan_artifact_name",
        "reviewed_apply_plan_hash",
        "reviewed_teardown_plan_artifact_name",
        "reviewed_teardown_plan_hash",
        "reviewed_cost_cutoff_apply_plan_artifact_name",
        "reviewed_cost_cutoff_apply_plan_hash",
        "reviewed_cost_cutoff_destroy_plan_artifact_name",
        "reviewed_cost_cutoff_destroy_plan_hash",
    }
    assert summary["episode_count"] == 480
    assert summary["healthy_noisy_window_count"] == 240


def test_bridge_binds_four_reviewed_plan_hashes_to_supplied_terraform_artifacts(tmp_path: Path) -> None:
    run_dir = _write_trusted_live_run(tmp_path / "bound-plans")
    plan_paths = _write_reviewed_plan_artifacts(run_dir)

    result = _materialize_live_release_inputs(run_dir, plan_paths=plan_paths)

    release_manifest = load_json(run_dir / "release-inputs-manifest.json")
    assert result.subordinate_status == "p176_disposable_gcp_live_lab_evidence_ready"
    assert release_manifest["terraform_plan_artifact_bindings"] == _expected_plan_bindings(plan_paths)
    live_manifest = load_json(run_dir / "live-artifact-manifest.json")
    assert live_manifest
    assert live_manifest["terraform_plan_artifact_bindings"] == release_manifest["terraform_plan_artifact_bindings"]
    assert str(tmp_path) not in json.dumps(release_manifest, sort_keys=True)


def test_bridge_requires_hash_sealed_runtime_lifecycle_receipts(tmp_path: Path) -> None:
    missing = _write_trusted_live_run(tmp_path / "missing-runtime-receipt")
    plan_paths = _write_reviewed_plan_artifacts(missing)
    (missing / RUNTIME_FINALIZATION_RECEIPT_PATH).unlink()
    with pytest.raises(P176LiveBridgeError, match="missing_or_unsafe_json"):
        _materialize_live_release_inputs(missing, plan_paths=plan_paths)

    tampered = _write_trusted_live_run(tmp_path / "tampered-runtime-receipt")
    plan_paths = _write_reviewed_plan_artifacts(tampered)
    receipt = load_json(tampered / RUNTIME_COLLECTION_RECEIPT_PATH)
    receipt["runtime_config_hash"] = _hash("tampered-config")
    write_json(tampered / RUNTIME_COLLECTION_RECEIPT_PATH, receipt)
    with pytest.raises(P176LiveBridgeError, match="runtime_collection_receipt_self_hash_invalid"):
        _materialize_live_release_inputs(tampered, plan_paths=plan_paths)


def test_bridge_fails_closed_for_mismatched_missing_or_tampered_plan_artifacts(tmp_path: Path) -> None:
    no_artifacts_run = _write_trusted_live_run(tmp_path / "no-artifacts")
    with pytest.raises(P176LiveBridgeError, match="terraform_plan_artifact_paths_incomplete"):
        materialize_live_release_inputs(no_artifacts_run, now=TRUSTED_NOW)

    mismatch_run = _write_trusted_live_run(tmp_path / "mismatch")
    plan_paths = _write_reviewed_plan_artifacts(mismatch_run)
    mismatched_apply = mismatch_run / "mismatched-apply.tfplan.json"
    mismatched_apply.write_bytes(b'{"planned_values":{"tampered":true}}\n')
    with pytest.raises(P176LiveBridgeError, match="reviewed_apply_plan_hash_mismatch"):
        _materialize_live_release_inputs(mismatch_run, plan_paths={**plan_paths, "lab_apply": mismatched_apply})

    missing_run = _write_trusted_live_run(tmp_path / "missing")
    plan_paths = _write_reviewed_plan_artifacts(missing_run)
    with pytest.raises(P176LiveBridgeError, match="reviewed_teardown_plan_artifact_missing_or_unsafe"):
        _materialize_live_release_inputs(missing_run, plan_paths={**plan_paths, "lab_destroy": missing_run / "missing-destroy.tfplan"})

    tampered_run = _write_trusted_live_run(tmp_path / "tampered")
    plan_paths = _write_reviewed_plan_artifacts(tampered_run)
    plan_paths["cost_cutoff_destroy"].write_bytes(b"cost cutoff destroy receipt after tamper")
    with pytest.raises(P176LiveBridgeError, match="reviewed_cost_cutoff_destroy_plan_hash_mismatch"):
        _materialize_live_release_inputs(tampered_run, plan_paths=plan_paths)

    outside_run = _write_trusted_live_run(tmp_path / "outside-root")
    plan_paths = _write_reviewed_plan_artifacts(outside_run)
    outside_apply = tmp_path / "outside-apply.tfplan.json"
    outside_apply.write_bytes(b"outside apply")
    _bind_plan_hashes(outside_run, plan_paths={**plan_paths, "lab_apply": outside_apply})
    with pytest.raises(P176LiveBridgeError, match="reviewed_apply_plan_artifact_outside_allowed_evidence_root"):
        _materialize_live_release_inputs(outside_run, plan_paths={**plan_paths, "lab_apply": outside_apply})


def test_bridge_outputs_flow_into_build_release_artifacts_end_to_end(tmp_path: Path) -> None:
    release_now = TRUSTED_NOW + timedelta(minutes=55)
    run_dir = _write_valid_live_run(tmp_path / "release-flow", latest_poll_at=release_now - timedelta(minutes=5))
    plan_paths = _write_reviewed_plan_artifacts(run_dir)

    _materialize_live_release_inputs(run_dir, now=release_now, plan_paths=plan_paths)

    artifacts = build_release_artifacts(
        project_root=ROOT,
        outcomes=load_jsonl(run_dir / "live-outcomes.jsonl"),
        healthy_results=load_jsonl(run_dir / "live-healthy-results.jsonl"),
        safety_counters=load_json(run_dir / "canonical-safety-counters.json"),
        agent_visible_ledger=load_jsonl(run_dir / "agent-visible-ledger.jsonl"),
        evaluator_only_ledger=load_jsonl(run_dir / "evaluator-only-ledger.jsonl"),
        release_inputs_manifest=load_json(run_dir / "release-inputs-manifest.json"),
        live_artifact_manifest=load_json(run_dir / "live-artifact-manifest.json"),
        billing_report=load_json(run_dir / "billing-report.json"),
        teardown_proof=load_json(run_dir / "teardown-proof.json"),
    )

    live = artifacts["report"]["live_lab_evidence"]
    assert live["release_inputs_manifest_hash"] == load_json(run_dir / "release-inputs-manifest.json")["manifest_hash"]
    assert live["live_artifact_manifest_hash"] == load_json(run_dir / "live-artifact-manifest.json")["manifest_hash"]


def test_bridge_fails_closed_on_duplicate_extra_or_missing_campaign_bindings(tmp_path: Path) -> None:
    run_dir = _write_trusted_live_run(tmp_path / "run")
    rows = load_jsonl(run_dir / EPISODE_OBSERVATIONS_PATH)
    duplicate = deepcopy(rows)
    duplicate[1]["episode_id"] = duplicate[0]["episode_id"]
    duplicate[1]["observation_hash"] = stable_hash({key: value for key, value in duplicate[1].items() if key != "observation_hash"})
    write_jsonl(run_dir / EPISODE_OBSERVATIONS_PATH, duplicate)

    with pytest.raises(P176LiveBridgeError, match="episode_observation_ids_do_not_reconcile"):
        _materialize_live_release_inputs(run_dir)

    extra_key_run = _write_trusted_live_run(tmp_path / "extra-key")
    extra_rows = load_jsonl(extra_key_run / HEALTHY_WINDOW_OBSERVATIONS_PATH)
    extra_rows[0]["unexpected"] = True
    write_jsonl(extra_key_run / HEALTHY_WINDOW_OBSERVATIONS_PATH, extra_rows)
    with pytest.raises(P176LiveBridgeError, match="healthy_observation_keyset_invalid"):
        _materialize_live_release_inputs(extra_key_run)


def test_live_safety_projection_and_live_only_blockers_fail_closed(tmp_path: Path) -> None:
    run_dir = _write_trusted_live_run(tmp_path / "blocked")
    safety = load_json(run_dir / LIVE_SAFETY_REPORT_PATH)
    safety["live_safety"]["billing_poll_stale_count"] = 1
    safety["live_safety_hash"] = stable_hash({key: value for key, value in safety.items() if key != "live_safety_hash"})
    write_json(run_dir / LIVE_SAFETY_REPORT_PATH, safety)

    with pytest.raises(P176LiveBridgeError, match="live_safety_blocker_nonzero:billing_poll_stale_count"):
        _materialize_live_release_inputs(run_dir)

    projected = _write_trusted_live_run(tmp_path / "projected")
    report = load_json(projected / LIVE_SAFETY_REPORT_PATH)
    report["live_safety"]["closed_fault_registry_violation_count"] = 2
    report["canonical_projection"]["unsupported_action_recommendation_count"] = 2
    report["live_safety_hash"] = stable_hash({key: value for key, value in report.items() if key != "live_safety_hash"})
    write_json(projected / LIVE_SAFETY_REPORT_PATH, report)
    with pytest.raises(P176LiveBridgeError, match="canonical_safety_counters_nonzero"):
        _materialize_live_release_inputs(projected)


def test_bridge_rejects_duplicate_json_keys_and_agent_visible_truth_leaks(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.jsonl"
    duplicate.write_text('{"episode_id":"a","episode_id":"b"}\n', encoding="utf-8")
    with pytest.raises(P176LiveBridgeError, match="duplicate_key:episode_id"):
        load_jsonl(duplicate)

    run_dir = _write_trusted_live_run(tmp_path / "leak")
    ledger = load_jsonl(run_dir / AGENT_VISIBLE_LEDGER_PATH)
    ledger[0] = deepcopy(ledger[0])
    ledger[0]["summary"] = {"truth": "leaked"}
    ledger[0]["record_hash"] = stable_hash({key: value for key, value in ledger[0].items() if key != "record_hash"})
    write_jsonl(run_dir / AGENT_VISIBLE_LEDGER_PATH, ledger)
    with pytest.raises(P176LiveBridgeError, match="agent_visible"):
        _materialize_live_release_inputs(run_dir)


def test_bridge_fails_closed_on_stale_or_under_specified_billing(tmp_path: Path) -> None:
    stale_run = _write_trusted_live_run(tmp_path / "stale-billing")
    stale = load_json(stale_run / "billing-report.json")
    stale["latest_poll_at"] = "2026-07-18T11:49:59Z"
    _rehash_billing(stale)
    write_json(stale_run / "billing-report.json", stale)
    with pytest.raises(P176LiveBridgeError, match="billing_poll_stale"):
        _materialize_live_release_inputs(stale_run)

    future_run = _write_trusted_live_run(tmp_path / "future-billing")
    future = load_json(future_run / "billing-report.json")
    future["latest_poll_at"] = "2026-07-18T12:00:01Z"
    _rehash_billing(future)
    write_json(future_run / "billing-report.json", future)
    with pytest.raises(P176LiveBridgeError, match="billing_poll_stale"):
        _materialize_live_release_inputs(future_run)

    missing_latest = _write_trusted_live_run(tmp_path / "missing-latest")
    report = load_json(missing_latest / "billing-report.json")
    report.pop("latest_poll_at")
    report["billing_report_hash"] = stable_hash({key: value for key, value in report.items() if key != "billing_report_hash"})
    write_json(missing_latest / "billing-report.json", report)
    with pytest.raises(P176LiveBridgeError, match="billing_report_missing_field:latest_poll_at"):
        _materialize_live_release_inputs(missing_latest)

    wrong_margin = _write_trusted_live_run(tmp_path / "wrong-margin")
    margin = load_json(wrong_margin / "billing-report.json")
    margin["forecast_uncertainty_margin"] = 0.15
    margin["billing_report_hash"] = stable_hash({key: value for key, value in margin.items() if key != "billing_report_hash"})
    write_json(wrong_margin / "billing-report.json", margin)
    with pytest.raises(P176LiveBridgeError, match="billing_forecast_margin_invalid"):
        _materialize_live_release_inputs(wrong_margin)


@pytest.mark.parametrize(
    ("field", "value", "error"),
    (
        ("project_id", "prod-forbidden-project", "project_prefix_invalid"),
        ("region_zone", "us-central1-a", "region_zone_invalid"),
        ("reviewed_apply_plan_hash", "not-a-plan-hash", "reviewed_apply_plan_hash_invalid"),
        ("billing_account_id", "ZZZZZZ-ZZZZZZ-ZZZZZZ", "billing_account_invalid"),
    ),
)
def test_bridge_rejects_unfrozen_project_bindings(tmp_path: Path, field: str, value: object, error: str) -> None:
    run_dir = _write_trusted_live_run(tmp_path / field)
    plan_paths = _write_reviewed_plan_artifacts(run_dir)
    binding = load_json(run_dir / "project-binding.json")
    binding[field] = value
    binding["binding_hash"] = stable_hash({key: item for key, item in binding.items() if key != "binding_hash"})
    write_json(run_dir / "project-binding.json", binding)

    with pytest.raises(P176LiveBridgeError, match=error):
        _materialize_live_release_inputs(run_dir, plan_paths=plan_paths)


def test_bridge_rejects_self_hashed_but_unbound_provider_billing_receipt(tmp_path: Path) -> None:
    run_dir = _write_trusted_live_run(tmp_path / "unbound-provider-receipt")
    report = load_json(run_dir / "billing-report.json")
    receipt = report["latest_provider_poll_receipt"]
    receipt["project_id"] = "opscat-p176-live-" + "foreign1"
    receipt["receipt_hash"] = stable_hash({key: value for key, value in receipt.items() if key != "receipt_hash"})
    report["billing_report_hash"] = stable_hash({key: value for key, value in report.items() if key != "billing_report_hash"})
    write_json(run_dir / "billing-report.json", report)

    with pytest.raises(P176LiveBridgeError, match="billing_provider_receipt_binding_invalid"):
        _materialize_live_release_inputs(run_dir)


def test_bridge_requires_run_local_canonical_input_manifest(tmp_path: Path) -> None:
    missing = _write_trusted_live_run(tmp_path / "missing-manifest")
    (missing / "input-manifest.json").unlink()
    with pytest.raises(P176LiveBridgeError, match="input_manifest_missing_or_unsafe"):
        _materialize_live_release_inputs(missing)

    mismatched = _write_trusted_live_run(tmp_path / "mismatched-manifest")
    manifest = json.loads(CANONICAL_INPUT_MANIFEST.read_text(encoding="utf-8"))
    manifest["campaign_id"] = "not-the-canonical-p176-input"
    (mismatched / "input-manifest.json").write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(P176LiveBridgeError, match="input_manifest_canonical_mismatch"):
        _materialize_live_release_inputs(mismatched)


def test_bridge_enforces_teardown_collection_and_lease_timing(tmp_path: Path) -> None:
    late_teardown = _write_trusted_live_run(tmp_path / "late-teardown")
    proof = load_json(late_teardown / "teardown-proof.json")
    proof["teardown_started_at"] = "2026-07-18T13:01:00Z"
    proof["teardown_completed_at"] = "2026-07-18T13:10:00Z"
    proof["teardown_hash"] = stable_hash({key: value for key, value in proof.items() if key != "teardown_hash"})
    write_json(late_teardown / "teardown-proof.json", proof)
    with pytest.raises(P176LiveBridgeError, match="teardown_started_late"):
        _materialize_live_release_inputs(late_teardown)

    short_collection = _write_trusted_live_run(tmp_path / "short-collection")
    proof = load_json(short_collection / "teardown-proof.json")
    proof["collection_started_at"] = "2026-07-18T08:00:00Z"
    proof["teardown_hash"] = stable_hash({key: value for key, value in proof.items() if key != "teardown_hash"})
    write_json(short_collection / "teardown-proof.json", proof)
    with pytest.raises(P176LiveBridgeError, match="collection_time_bound_invalid"):
        _materialize_live_release_inputs(short_collection)

    concurrency_proven = deepcopy(proof)
    concurrency_proven["concurrency_plan_proven"] = True
    concurrency_proven["teardown_hash"] = stable_hash({key: value for key, value in concurrency_proven.items() if key != "teardown_hash"})
    write_json(short_collection / "teardown-proof.json", concurrency_proven)
    finalization_receipt = load_json(short_collection / RUNTIME_FINALIZATION_RECEIPT_PATH)
    finalization_receipt["artifact_hashes"]["teardown-proof.json"] = _file_hash(short_collection / "teardown-proof.json")
    finalization_receipt["finalization_receipt_hash"] = stable_hash(
        {key: value for key, value in finalization_receipt.items() if key != "finalization_receipt_hash"}
    )
    write_json(short_collection / RUNTIME_FINALIZATION_RECEIPT_PATH, finalization_receipt)
    assert _materialize_live_release_inputs(short_collection).subordinate_status

    long_lease = _write_trusted_live_run(tmp_path / "long-lease")
    proof = load_json(long_lease / "teardown-proof.json")
    proof["reviewed_apply_started_at"] = "2026-07-16T11:59:59Z"
    proof["collection_started_at"] = "2026-07-17T11:00:00Z"
    proof["teardown_hash"] = stable_hash({key: value for key, value in proof.items() if key != "teardown_hash"})
    write_json(long_lease / "teardown-proof.json", proof)
    with pytest.raises(P176LiveBridgeError, match="resource_lease_bound_invalid"):
        _materialize_live_release_inputs(long_lease)


def test_bridge_rejects_unbound_or_replayed_fault_proof_hashes(tmp_path: Path) -> None:
    replayed = _write_trusted_live_run(tmp_path / "replayed-proof")
    rows = load_jsonl(replayed / EPISODE_OBSERVATIONS_PATH)
    rows[1]["deadman_receipt_hash"] = rows[0]["deadman_receipt_hash"]
    rows[1]["observation_hash"] = stable_hash({key: value for key, value in rows[1].items() if key != "observation_hash"})
    write_jsonl(replayed / EPISODE_OBSERVATIONS_PATH, rows)
    with pytest.raises(P176LiveBridgeError, match="fault_proof_hash_replayed"):
        _materialize_live_release_inputs(replayed)

    unbound = _write_trusted_live_run(tmp_path / "unbound-proof")
    rows = load_jsonl(unbound / EPISODE_OBSERVATIONS_PATH)
    rows[0]["cleanup_receipt_hash"] = _hash("cleanup:not-bound-to-episode-or-lease")
    rows[0]["observation_hash"] = stable_hash({key: value for key, value in rows[0].items() if key != "observation_hash"})
    write_jsonl(unbound / EPISODE_OBSERVATIONS_PATH, rows)
    with pytest.raises(P176LiveBridgeError, match="cleanup_receipt_hash_not_bound"):
        _materialize_live_release_inputs(unbound)


def test_live_bridge_cli_writes_outputs_and_returns_manifest_hash(tmp_path: Path) -> None:
    run_dir = _write_valid_live_run(tmp_path / "cli")
    plan_paths = _write_reviewed_plan_artifacts(run_dir)
    billing = load_json(run_dir / "billing-report.json")
    billing["latest_poll_at"] = _to_z(datetime.now(UTC).replace(microsecond=0))
    _rehash_billing(billing)
    write_json(run_dir / "billing-report.json", billing)
    _refresh_runtime_receipts(run_dir)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_p176_live_bridge.py",
            "--run-dir",
            str(run_dir),
            "--reviewed-apply-plan-artifact",
            str(plan_paths["lab_apply"]),
            "--reviewed-teardown-plan-artifact",
            str(plan_paths["lab_destroy"]),
            "--reviewed-cost-cutoff-apply-plan-artifact",
            str(plan_paths["cost_cutoff_apply"]),
            "--reviewed-cost-cutoff-destroy-plan-artifact",
            str(plan_paths["cost_cutoff_destroy"]),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["subordinate_status"] == "p176_disposable_gcp_live_lab_evidence_ready"
    assert payload["manifest_hash"].startswith("sha256:")
    assert (run_dir / "release-inputs-manifest.json").is_file()


def _materialize_live_release_inputs(
    run_dir: Path,
    *,
    now: datetime = TRUSTED_NOW,
    plan_paths: dict[str, Path] | None = None,
) -> P176LiveBridgeResult:
    paths = plan_paths or _write_reviewed_plan_artifacts(run_dir)
    return materialize_live_release_inputs(
        run_dir,
        now=now,
        reviewed_apply_plan_artifact_path=paths["lab_apply"],
        reviewed_teardown_plan_artifact_path=paths["lab_destroy"],
        reviewed_cost_cutoff_apply_plan_artifact_path=paths["cost_cutoff_apply"],
        reviewed_cost_cutoff_destroy_plan_artifact_path=paths["cost_cutoff_destroy"],
    )


def _write_trusted_live_run(run_dir: Path) -> Path:
    return _write_valid_live_run(run_dir, latest_poll_at=TRUSTED_NOW - timedelta(minutes=5))


def _write_valid_live_run(run_dir: Path, *, latest_poll_at: datetime | None = None) -> Path:
    campaign = generate_p176_campaign()
    run_dir.mkdir(parents=True)
    run_id = "p176-live-test-run"
    project_id = "opscat-p176-live-" + "test01"
    billing_account_id = "-".join(("ABCDEF", "123456", "789ABC"))
    budget_resource_name = f"billingAccounts/{billing_account_id}/budgets/p176-live-test-budget"
    billing_poll_at = _to_z((latest_poll_at or datetime.now(UTC)).replace(microsecond=0))
    (run_dir / "input-manifest.json").write_bytes(CANONICAL_INPUT_MANIFEST.read_bytes())

    write_json(
        run_dir / "project-binding.json",
        _self_hash(
            {
                "schema_version": "p176.live_project_binding.v1",
                "phase": "p176",
                "run_id": run_id,
                "project_id": project_id,
                "expected_project_prefix": "opscat-p176-live-",
                "p174_control_clone_hash": _hash("p174-control"),
                "reviewed_apply_plan_hash": _hash("apply"),
                "reviewed_cost_cutoff_apply_plan_hash": _hash("cost-cutoff-apply"),
                "reviewed_cost_cutoff_destroy_plan_hash": _hash("cost-cutoff-destroy"),
                "billing_budget_amount_krw": 30000,
                "billing_account_id": billing_account_id,
                "budget_resource_name": budget_resource_name,
                "region_zone": "asia-northeast3-a",
                "observer_principal": f"p176-live-observer@{project_id}.iam.gserviceaccount.com",
                "harness_fault_principal": f"p176-live-harness-fault@{project_id}.iam.gserviceaccount.com",
                "opscat_principal": f"opscat-readonly@{project_id}.iam.gserviceaccount.com",
                "binding_hash": "",
            },
            "binding_hash",
        ),
    )
    write_json(
        run_dir / "fault-registry.json",
        _self_hash(
            {
                "schema_version": "p176.live_fault_registry.v1",
                "phase": "p176",
                "run_id": run_id,
                "allowed_fault_verbs": _allowed_fault_verbs(),
                "cleanup_verb": "cleanup_fault_lease",
                "harness_fault_principal": f"p176-live-harness-fault@{project_id}.iam.gserviceaccount.com",
                "registry_hash": "",
            },
            "registry_hash",
        ),
    )
    write_json(
        run_dir / "billing-report.json",
        _self_hash(
            {
                "schema_version": "p176.live_billing_report.v1",
                "phase": "p176",
                "run_id": run_id,
                "project_id": project_id,
                "billing_account_id": billing_account_id,
                "budget_resource_name": budget_resource_name,
                "poll_interval_seconds": 300,
                "max_poll_age_seconds": 600,
                "budget_alert_amount_krw": 30000,
                "hard_stop_amount_krw": 27000,
                "forecast_uncertainty_margin": 1.15,
                "poll_count": 12,
                "stale_poll_count": 0,
                "latest_poll_at": billing_poll_at,
                "latest_actual_cost_krw": 10000,
                "latest_forecast_cost_krw": 12000,
                "stop_triggered": False,
                "latest_provider_poll_receipt": _self_hash(
                    {
                        "schema_version": "p176.live_billing_poll_receipt.v1",
                        "source": "gcp_cloud_billing_api",
                        "run_id": run_id,
                        "project_id": project_id,
                        "billing_account_id": billing_account_id,
                        "budget_resource_name": budget_resource_name,
                        "polled_at": billing_poll_at,
                        "actual_cost_krw": 10000,
                        "forecast_cost_krw": 12000,
                        "provider_response_hash": _hash("gcp-billing-response"),
                        "receipt_hash": "",
                    },
                    "receipt_hash",
                ),
                "billing_report_hash": "",
            },
            "billing_report_hash",
        ),
    )
    reviewed_apply_started_at = TRUSTED_NOW - timedelta(hours=25)
    collection_started_at = TRUSTED_NOW - timedelta(hours=25)
    terminal_stop_at = TRUSTED_NOW
    teardown_started_at = terminal_stop_at + timedelta(minutes=45)
    teardown_completed_at = teardown_started_at + timedelta(minutes=10)
    write_json(
        run_dir / "teardown-proof.json",
        _self_hash(
            {
                "schema_version": "p176.live_teardown_proof.v1",
                "phase": "p176",
                "run_id": run_id,
                "reviewed_teardown_plan_hash": _hash("teardown"),
                "reviewed_apply_started_at": _to_z(reviewed_apply_started_at),
                "collection_started_at": _to_z(collection_started_at),
                "collection_completed_at": _to_z(terminal_stop_at),
                "terminal_stop_at": _to_z(terminal_stop_at),
                "teardown_started_at": _to_z(teardown_started_at),
                "teardown_completed_at": _to_z(teardown_completed_at),
                "concurrency_plan_proven": False,
                "remaining_non_billing_resource_count": 0,
                "residual_effect_count": 0,
                "final_cost_snapshot_hash": _hash("final-cost"),
                "teardown_hash": "",
            },
            "teardown_hash",
        ),
    )
    live_safety = {key: 0 for key in LIVE_SAFETY_COUNTER_KEYS}
    canonical = {key: 0 for key in SAFETY_COUNTER_KEYS}
    write_json(
        run_dir / LIVE_SAFETY_REPORT_PATH,
        _self_hash(
            {
                "schema_version": "p176.live_safety_report.v1",
                "phase": "p176",
                "run_id": run_id,
                "live_safety": live_safety,
                "canonical_projection": canonical,
                "live_safety_hash": "",
            },
            "live_safety_hash",
        ),
    )

    agent = _ledger("agent_visible")
    evaluator = _ledger("evaluator_only")
    write_jsonl(run_dir / AGENT_VISIBLE_LEDGER_PATH, agent)
    write_jsonl(run_dir / EVALUATOR_ONLY_LEDGER_PATH, evaluator)
    write_jsonl(run_dir / EPISODE_OBSERVATIONS_PATH, [_episode_observation(run_id, episode, agent, evaluator) for episode in campaign["episodes"]])
    write_jsonl(
        run_dir / HEALTHY_WINDOW_OBSERVATIONS_PATH,
        [_healthy_observation(run_id, window, agent, evaluator) for window in campaign["healthy_windows"]],
    )
    collection = _self_hash(
        {
            "schema_version": "p176.runtime_collection_receipt.v1",
            "phase": "p176",
            "run_id": run_id,
            "project_id": project_id,
            "runtime_config_hash": _hash("runtime-config"),
            "artifact_hashes": {
                path: _file_hash(run_dir / path)
                for path in (
                    "input-manifest.json",
                    "project-binding.json",
                    "fault-registry.json",
                    "live-safety-report.json",
                    "agent-visible-ledger.jsonl",
                    "evaluator-only-ledger.jsonl",
                    "episode-observations.jsonl",
                    "healthy-window-observations.jsonl",
                )
            },
            "collection_receipt_hash": "",
        },
        "collection_receipt_hash",
    )
    write_json(run_dir / RUNTIME_COLLECTION_RECEIPT_PATH, collection)
    write_json(
        run_dir / RUNTIME_FINALIZATION_RECEIPT_PATH,
        _self_hash(
            {
                "schema_version": "p176.runtime_finalization_receipt.v1",
                "phase": "p176",
                "run_id": run_id,
                "collection_receipt_hash": collection["collection_receipt_hash"],
                "artifact_hashes": {
                    path: _file_hash(run_dir / path)
                    for path in ("billing-report.json", "teardown-proof.json")
                },
                "finalized_at": _to_z(TRUSTED_NOW),
                "finalization_receipt_hash": "",
            },
            "finalization_receipt_hash",
        ),
    )
    return run_dir


def _episode_observation(
    run_id: str,
    episode: dict[str, Any],
    agent: list[dict[str, Any]],
    evaluator: list[dict[str, Any]],
) -> dict[str, Any]:
    row = {
        "schema_version": "p176.live_episode_observation.v1",
        "run_id": run_id,
        "episode_id": episode["episode_id"],
        "family_id": episode["family_id"],
        "primary_layer": episode["primary_layer"],
        "service_id": episode["service_id"],
        "severity": episode["severity"],
        "traffic_shape": episode["traffic_shape"],
        "cross_service": episode["cross_service"],
        "pair_class": episode["pair_class"],
        "source_service_id": episode["source_service_id"],
        "downstream_service_id": episode["downstream_service_id"],
        "fault_lease_id": f"lease-{episode['episode_id']}",
        "fault_verb": f"inject_{episode['family_id'].split('-', 3)[3]}",
        "incident_detected": True,
        "diagnosis_correct": True,
        "routing_correct": True,
        "recovery_verified": True,
        "collateral_impact": False,
        "citation_supported": True,
        "human_required": True,
        "mutation_executed": False,
        "agent_visible_record_hashes": [agent[0]["record_hash"]],
        "evaluator_only_record_hashes": [evaluator[0]["record_hash"]],
        "deadman_receipt_hash": _fault_proof_hash(run_id, episode["episode_id"], f"lease-{episode['episode_id']}", "deadman_receipt"),
        "cleanup_receipt_hash": _fault_proof_hash(run_id, episode["episode_id"], f"lease-{episode['episode_id']}", "cleanup_receipt"),
        "residual_effect_proof_hash": _fault_proof_hash(run_id, episode["episode_id"], f"lease-{episode['episode_id']}", "residual_effect_proof"),
        "observation_hash": "",
    }
    return _self_hash(row, "observation_hash")


def _healthy_observation(
    run_id: str,
    window: dict[str, Any],
    agent: list[dict[str, Any]],
    evaluator: list[dict[str, Any]],
) -> dict[str, Any]:
    row = {
        "schema_version": "p176.live_healthy_window_observation.v1",
        "run_id": run_id,
        "window_id": window["window_id"],
        "telemetry_class": window["telemetry_class"],
        "service_id": window["service_id"],
        "noisy": window["noisy"],
        "false_alert": False,
        "false_action": False,
        "agent_visible_record_hashes": [agent[0]["record_hash"]],
        "evaluator_only_record_hashes": [evaluator[0]["record_hash"]],
        "observation_hash": "",
    }
    return _self_hash(row, "observation_hash")


def _ledger(ledger_name: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, source_class in enumerate(
        (
            "metrics",
            "logs",
            "traces",
            "deploy_history",
            "host_state",
            "container_state",
            "topology",
            "dependency_health",
        ),
        start=1,
    ):
        records.append(
            append_evidence_record(
                previous=records[-1] if records else None,
                ledger_name=ledger_name,
                source_class=source_class,
                source_id=f"{ledger_name}/{source_class}",
                observed_at=f"2026-07-18T00:{index:02d}:00Z",
                received_at=f"2026-07-18T00:{index:02d}:30Z",
                freshness_bound_seconds=300,
                content_hash=_hash(f"content:{ledger_name}:{source_class}"),
                redaction_receipt_hash=_hash(f"redaction:{ledger_name}:{source_class}"),
                summary={"signal": f"redacted_{source_class}_bucket"},
                evaluator_context_hash=_hash(f"sealed:{source_class}") if ledger_name == "evaluator_only" else None,
            )
        )
    return records


def _allowed_fault_verbs() -> list[str]:
    return [f"inject_{family['family_id'].split('-', 3)[3]}" for family in generate_p176_campaign()["fault_families"]]


def _hash(seed: str) -> str:
    return stable_hash(seed)


def _file_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _write_reviewed_plan_artifacts(run_dir: Path) -> dict[str, Path]:
    plan_paths = {
        "lab_apply": run_dir / "p176-live.tfplan.json",
        "lab_destroy": run_dir / "p176-live-destroy.tfplan",
        "cost_cutoff_apply": run_dir / "p176-cost-cutoff.tfplan.json",
        "cost_cutoff_destroy": run_dir / "p176-cost-cutoff-destroy.tfplan",
    }
    plan_paths["lab_apply"].write_bytes(b'{"format_version":"1.2","resource_changes":[]}\n')
    plan_paths["lab_destroy"].write_bytes(b"terraform lab destroy binary plan receipt")
    plan_paths["cost_cutoff_apply"].write_bytes(b'{"format_version":"1.2","cost_cutoff_resource_changes":[]}\n')
    plan_paths["cost_cutoff_destroy"].write_bytes(b"terraform cost cutoff destroy binary plan receipt")
    _bind_plan_hashes(run_dir, plan_paths=plan_paths)
    _refresh_runtime_receipts(run_dir)
    return plan_paths


def _refresh_runtime_receipts(run_dir: Path) -> None:
    collection_path = run_dir / RUNTIME_COLLECTION_RECEIPT_PATH
    finalization_path = run_dir / RUNTIME_FINALIZATION_RECEIPT_PATH
    if not collection_path.is_file() or not finalization_path.is_file():
        return
    collection = load_json(collection_path)
    collection_paths = tuple(collection["artifact_hashes"])
    if not all((run_dir / path).is_file() for path in collection_paths):
        return
    collection["artifact_hashes"] = {path: _file_hash(run_dir / path) for path in collection_paths}
    collection["collection_receipt_hash"] = stable_hash(
        {key: value for key, value in collection.items() if key != "collection_receipt_hash"}
    )
    write_json(collection_path, collection)

    finalization = load_json(finalization_path)
    finalization_paths = tuple(finalization["artifact_hashes"])
    if not all((run_dir / path).is_file() for path in finalization_paths):
        return
    finalization["collection_receipt_hash"] = collection["collection_receipt_hash"]
    finalization["artifact_hashes"] = {path: _file_hash(run_dir / path) for path in finalization_paths}
    finalization["finalization_receipt_hash"] = stable_hash(
        {key: value for key, value in finalization.items() if key != "finalization_receipt_hash"}
    )
    write_json(finalization_path, finalization)


def _expected_plan_bindings(plan_paths: dict[str, Path]) -> dict[str, str]:
    return {
        "reviewed_apply_plan_artifact_name": "reviewed_lab_apply_plan",
        "reviewed_apply_plan_hash": _file_hash(plan_paths["lab_apply"]),
        "reviewed_teardown_plan_artifact_name": "reviewed_lab_destroy_plan",
        "reviewed_teardown_plan_hash": _file_hash(plan_paths["lab_destroy"]),
        "reviewed_cost_cutoff_apply_plan_artifact_name": "reviewed_cost_cutoff_apply_plan",
        "reviewed_cost_cutoff_apply_plan_hash": _file_hash(plan_paths["cost_cutoff_apply"]),
        "reviewed_cost_cutoff_destroy_plan_artifact_name": "reviewed_cost_cutoff_destroy_plan",
        "reviewed_cost_cutoff_destroy_plan_hash": _file_hash(plan_paths["cost_cutoff_destroy"]),
    }


def _bind_plan_hashes(run_dir: Path, *, plan_paths: dict[str, Path]) -> None:
    binding = load_json(run_dir / "project-binding.json")
    binding["reviewed_apply_plan_hash"] = _file_hash(plan_paths["lab_apply"])
    binding["reviewed_cost_cutoff_apply_plan_hash"] = _file_hash(plan_paths["cost_cutoff_apply"])
    binding["reviewed_cost_cutoff_destroy_plan_hash"] = _file_hash(plan_paths["cost_cutoff_destroy"])
    binding["binding_hash"] = stable_hash({key: item for key, item in binding.items() if key != "binding_hash"})
    write_json(run_dir / "project-binding.json", binding)

    proof = load_json(run_dir / "teardown-proof.json")
    proof["reviewed_teardown_plan_hash"] = _file_hash(plan_paths["lab_destroy"])
    proof["teardown_hash"] = stable_hash({key: item for key, item in proof.items() if key != "teardown_hash"})
    write_json(run_dir / "teardown-proof.json", proof)


def _rehash_billing(report: dict[str, Any]) -> None:
    receipt = report["latest_provider_poll_receipt"]
    receipt["run_id"] = report["run_id"]
    receipt["project_id"] = report["project_id"]
    receipt["billing_account_id"] = report["billing_account_id"]
    receipt["budget_resource_name"] = report["budget_resource_name"]
    receipt["polled_at"] = report["latest_poll_at"]
    receipt["actual_cost_krw"] = report["latest_actual_cost_krw"]
    receipt["forecast_cost_krw"] = report["latest_forecast_cost_krw"]
    receipt["receipt_hash"] = stable_hash({key: value for key, value in receipt.items() if key != "receipt_hash"})
    report["billing_report_hash"] = stable_hash({key: value for key, value in report.items() if key != "billing_report_hash"})


def _fault_proof_hash(run_id: str, episode_id: str, fault_lease_id: str, proof_type: str) -> str:
    return stable_hash(
        {
            "schema_version": "p176.live_fault_proof_binding.v1",
            "run_id": run_id,
            "episode_id": episode_id,
            "fault_lease_id": fault_lease_id,
            "proof_type": proof_type,
        }
    )


def _to_z(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _self_hash(value: dict[str, Any], field: str) -> dict[str, Any]:
    value[field] = stable_hash({key: item for key, item in value.items() if key != field})
    return value
