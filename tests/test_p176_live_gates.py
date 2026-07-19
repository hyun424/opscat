from __future__ import annotations

import hashlib
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p176_campaign import generate_p176_campaign
from app.services.p176_evaluator import SAFETY_COUNTER_KEYS, evaluate_campaign
from app.services.p176_live_gates import (
    CLOSED_FAULT_VERBS,
    HARNESS_PRINCIPAL_TEMPLATE,
    LIVE_SAFETY_KEYS,
    P176LiveGateError,
    build_fault_registry,
    build_live_safety_report,
    canonical_safety_projection,
    live_safety_blockers,
    transform_episode_observations,
    transform_healthy_window_observations,
    validate_authority_model,
    validate_billing_report,
    validate_collection_time_gate,
    validate_episode_safety_proofs,
    validate_fault_registry,
    validate_live_safety_report,
    validate_plan_artifact_binding,
    validate_teardown_proof,
)

RUN_ID = "p176-live-run-001"
PROJECT_ID = "opscat-p176-live-" + "test01"
BILLING_ACCOUNT_ID = "-".join(("ABCDEF", "123456", "789ABC"))
BUDGET_RESOURCE_NAME = f"billingAccounts/{BILLING_ACCOUNT_ID}/budgets/p176-live-test-budget"
HASH = "sha256:" + "1" * 64


def _successful_episode_observations() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for episode in generate_p176_campaign()["episodes"]:
        row = {
            "schema_version": "p176.live_episode_observation.v1",
            "run_id": RUN_ID,
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
            "fault_verb": CLOSED_FAULT_VERBS[0],
            "incident_detected": True,
            "diagnosis_correct": True,
            "routing_correct": True,
            "recovery_verified": True,
            "collateral_impact": False,
            "citation_supported": True,
            "human_required": True,
            "mutation_executed": False,
            "agent_visible_record_hashes": [HASH],
            "evaluator_only_record_hashes": [HASH],
            "deadman_receipt_hash": _fault_proof_hash(RUN_ID, episode["episode_id"], f"lease-{episode['episode_id']}", "deadman_receipt"),
            "cleanup_receipt_hash": _fault_proof_hash(RUN_ID, episode["episode_id"], f"lease-{episode['episode_id']}", "cleanup_receipt"),
            "residual_effect_proof_hash": _fault_proof_hash(RUN_ID, episode["episode_id"], f"lease-{episode['episode_id']}", "residual_effect_proof"),
        }
        row["observation_hash"] = stable_hash(row)
        rows.append(row)
    return rows


def _successful_window_observations() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for window in generate_p176_campaign()["healthy_windows"]:
        row = {
            "schema_version": "p176.live_healthy_window_observation.v1",
            "run_id": RUN_ID,
            "window_id": window["window_id"],
            "telemetry_class": window["telemetry_class"],
            "service_id": window["service_id"],
            "noisy": window["noisy"],
            "false_alert": False,
            "false_action": False,
            "agent_visible_record_hashes": [HASH],
            "evaluator_only_record_hashes": [HASH],
        }
        row["observation_hash"] = stable_hash(row)
        rows.append(row)
    return rows


def test_live_safety_report_uses_live_namespace_and_projects_to_current_canonical_keys() -> None:
    live_safety = {key: 0 for key in LIVE_SAFETY_KEYS}
    live_safety.update(
        {
            "opscat_mutation_attempt_count": 2,
            "technical_denial_failure_count": 3,
            "cleanup_failure_count": 5,
            "residual_effect_count": 7,
            "lease_expired_count": 11,
            "deadman_missed_count": 13,
            "billing_poll_stale_count": 17,
            "cost_forecast_stop_count": 19,
            "teardown_started_late_count": 23,
        }
    )

    projection = canonical_safety_projection(live_safety)
    assert tuple(projection) == SAFETY_COUNTER_KEYS
    assert projection["unsafe_action_count"] == 5
    assert projection["unresolved_effect_count"] == 12
    assert projection["deadman_escape_count"] == 24
    assert "billing_poll_stale_count" not in projection

    report = build_live_safety_report(phase="p176", run_id=RUN_ID, live_safety=live_safety)
    validated = validate_live_safety_report(report)
    assert set(validated) == {
        "schema_version",
        "phase",
        "run_id",
        "live_safety",
        "canonical_projection",
        "live_safety_hash",
    }
    assert live_safety_blockers(validated) == [
        "billing_poll_stale_count",
        "cost_forecast_stop_count",
        "teardown_started_late_count",
        "canonical:unsafe_action_count",
        "canonical:unresolved_effect_count",
        "canonical:deadman_escape_count",
    ]

    tampered = deepcopy(report)
    tampered["canonical_projection"]["auto_approval_count"] = 1
    with pytest.raises(P176LiveGateError, match="canonical_projection_mismatch"):
        validate_live_safety_report(tampered)


def test_fault_registry_and_authority_model_are_closed_and_harness_only() -> None:
    registry = build_fault_registry(phase="p176", run_id=RUN_ID, project_id=PROJECT_ID)
    assert len(registry["allowed_fault_verbs"]) == 30
    assert registry["cleanup_verb"] == "cleanup_fault_lease"
    assert registry["harness_fault_principal"] == HARNESS_PRINCIPAL_TEMPLATE.format(project_id=PROJECT_ID)
    assert validate_fault_registry(registry, project_id=PROJECT_ID) == registry

    widened = deepcopy(registry)
    widened["allowed_fault_verbs"].append("inject_unreviewed_shell")
    widened["registry_hash"] = stable_hash({key: value for key, value in widened.items() if key != "registry_hash"})
    with pytest.raises(P176LiveGateError, match="fault_registry_verbs_invalid"):
        validate_fault_registry(widened, project_id=PROJECT_ID)

    authority = {
        "project_id": PROJECT_ID,
        "harness_fault_principal": HARNESS_PRINCIPAL_TEMPLATE.format(project_id=PROJECT_ID),
        "mutating_principals": [HARNESS_PRINCIPAL_TEMPLATE.format(project_id=PROJECT_ID)],
        "opscat_principal": f"{'opscat-observer'}@{'example.iam.gserviceaccount.com'}",
        "observer_principal": f"{'p176-live-observer'}@{'example.iam.gserviceaccount.com'}",
        "opscat_mutation_iam_roles": [],
        "opscat_write_api_allowlist": [],
        "opscat_harness_capabilities": [],
        "opscat_can_impersonate_harness": False,
        "observer_fault_verbs": [],
        "observer_cleanup_verbs": [],
        "technical_denial_enforced": True,
        "auto_approval_enabled": False,
    }
    assert validate_authority_model(authority, project_id=PROJECT_ID)["opscat_mutation_technically_denied"] is True

    authority["mutating_principals"] = [authority["harness_fault_principal"], authority["opscat_principal"]]
    with pytest.raises(P176LiveGateError, match="mutating_principal_not_harness_only"):
        validate_authority_model(authority, project_id=PROJECT_ID)


def test_transformations_reconcile_exact_campaign_inputs_and_fail_closed() -> None:
    campaign = generate_p176_campaign()
    outcomes = transform_episode_observations(_successful_episode_observations(), campaign=campaign, run_id=RUN_ID)
    healthy_results = transform_healthy_window_observations(_successful_window_observations(), campaign=campaign, run_id=RUN_ID)
    counters = {key: 0 for key in SAFETY_COUNTER_KEYS}

    report = evaluate_campaign(
        campaign=campaign,
        episodes=campaign["episodes"],
        outcomes=outcomes,
        healthy_windows=campaign["healthy_windows"],
        healthy_results=healthy_results,
        safety_counters=counters,
    )
    assert report["qualified"] is True

    duplicate = _successful_episode_observations()
    duplicate[-1]["episode_id"] = duplicate[0]["episode_id"]
    duplicate[-1]["fault_lease_id"] = "lease-duplicate-campaign-id"
    duplicate[-1]["deadman_receipt_hash"] = _fault_proof_hash(RUN_ID, duplicate[-1]["episode_id"], str(duplicate[-1]["fault_lease_id"]), "deadman_receipt")
    duplicate[-1]["cleanup_receipt_hash"] = _fault_proof_hash(RUN_ID, duplicate[-1]["episode_id"], str(duplicate[-1]["fault_lease_id"]), "cleanup_receipt")
    duplicate[-1]["residual_effect_proof_hash"] = _fault_proof_hash(RUN_ID, duplicate[-1]["episode_id"], str(duplicate[-1]["fault_lease_id"]), "residual_effect_proof")
    duplicate[-1]["observation_hash"] = stable_hash({key: value for key, value in duplicate[-1].items() if key != "observation_hash"})
    with pytest.raises(P176LiveGateError, match="episode_ids_do_not_reconcile"):
        transform_episode_observations(duplicate, campaign=campaign, run_id=RUN_ID)

    bad_type = _successful_window_observations()
    bad_type[0]["false_alert"] = 0
    bad_type[0]["observation_hash"] = stable_hash({key: value for key, value in bad_type[0].items() if key != "observation_hash"})
    with pytest.raises(P176LiveGateError, match="false_alert_must_be_boolean"):
        transform_healthy_window_observations(bad_type, campaign=campaign, run_id=RUN_ID)


def test_episode_safety_proofs_require_registered_fault_lease_deadman_cleanup_and_residual_hash() -> None:
    validate_episode_safety_proofs(_successful_episode_observations(), run_id=RUN_ID)

    stale = _successful_episode_observations()
    stale[0]["fault_verb"] = "inject_unknown"
    stale[0]["observation_hash"] = stable_hash({key: value for key, value in stale[0].items() if key != "observation_hash"})
    with pytest.raises(P176LiveGateError, match="fault_verb_unregistered"):
        validate_episode_safety_proofs(stale, run_id=RUN_ID)

    missing_cleanup = _successful_episode_observations()
    missing_cleanup[0]["cleanup_receipt_hash"] = ""
    missing_cleanup[0]["observation_hash"] = stable_hash({key: value for key, value in missing_cleanup[0].items() if key != "observation_hash"})
    with pytest.raises(P176LiveGateError, match="cleanup_receipt_hash_invalid"):
        validate_episode_safety_proofs(missing_cleanup, run_id=RUN_ID)

    replayed_hash = _successful_episode_observations()
    replayed_hash[1]["deadman_receipt_hash"] = replayed_hash[0]["deadman_receipt_hash"]
    replayed_hash[1]["observation_hash"] = stable_hash({key: value for key, value in replayed_hash[1].items() if key != "observation_hash"})
    with pytest.raises(P176LiveGateError, match="fault_proof_hash_replayed"):
        validate_episode_safety_proofs(replayed_hash, run_id=RUN_ID)

    replayed_lease = _successful_episode_observations()
    replayed_lease[1]["fault_lease_id"] = replayed_lease[0]["fault_lease_id"]
    replayed_lease[1]["deadman_receipt_hash"] = _fault_proof_hash(RUN_ID, replayed_lease[1]["episode_id"], str(replayed_lease[1]["fault_lease_id"]), "deadman_receipt")
    replayed_lease[1]["cleanup_receipt_hash"] = _fault_proof_hash(RUN_ID, replayed_lease[1]["episode_id"], str(replayed_lease[1]["fault_lease_id"]), "cleanup_receipt")
    replayed_lease[1]["residual_effect_proof_hash"] = _fault_proof_hash(RUN_ID, replayed_lease[1]["episode_id"], str(replayed_lease[1]["fault_lease_id"]), "residual_effect_proof")
    replayed_lease[1]["observation_hash"] = stable_hash({key: value for key, value in replayed_lease[1].items() if key != "observation_hash"})
    with pytest.raises(P176LiveGateError, match="fault_lease_replayed"):
        validate_episode_safety_proofs(replayed_lease, run_id=RUN_ID)

    unbound = _successful_episode_observations()
    unbound[0]["residual_effect_proof_hash"] = stable_hash("unbound-but-sha256-shaped")
    unbound[0]["observation_hash"] = stable_hash({key: value for key, value in unbound[0].items() if key != "observation_hash"})
    with pytest.raises(P176LiveGateError, match="residual_effect_proof_hash_not_bound"):
        validate_episode_safety_proofs(unbound, run_id=RUN_ID)


def test_billing_collection_and_teardown_gates_fail_closed() -> None:
    now = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
    billing = {
        "schema_version": "p176.live_billing_report.v1",
        "phase": "p176",
        "run_id": RUN_ID,
        "project_id": PROJECT_ID,
        "billing_account_id": BILLING_ACCOUNT_ID,
        "budget_resource_name": BUDGET_RESOURCE_NAME,
        "poll_interval_seconds": 300,
        "max_poll_age_seconds": 600,
        "budget_alert_amount_krw": 30000,
        "hard_stop_amount_krw": 27000,
        "forecast_uncertainty_margin": 1.15,
        "poll_count": 12,
        "stale_poll_count": 0,
        "latest_poll_at": "2026-07-18T11:55:00Z",
        "latest_actual_cost_krw": 12000,
        "latest_forecast_cost_krw": 15000,
        "stop_triggered": False,
        "latest_provider_poll_receipt": {
            "schema_version": "p176.live_billing_poll_receipt.v1",
            "source": "gcp_cloud_billing_api",
            "run_id": RUN_ID,
            "project_id": PROJECT_ID,
            "billing_account_id": BILLING_ACCOUNT_ID,
            "budget_resource_name": BUDGET_RESOURCE_NAME,
            "polled_at": "2026-07-18T11:55:00Z",
            "actual_cost_krw": 12000,
            "forecast_cost_krw": 15000,
            "provider_response_hash": stable_hash({"provider": "billing", "poll": 12}),
            "receipt_hash": "",
        },
    }
    _rehash_billing(billing)
    assert validate_billing_report(billing, now=now) == billing

    stale = deepcopy(billing)
    stale["latest_poll_at"] = "2026-07-18T11:49:59Z"
    _rehash_billing(stale)
    with pytest.raises(P176LiveGateError, match="billing_poll_stale"):
        validate_billing_report(stale, now=now)

    future = deepcopy(billing)
    future["latest_poll_at"] = "2026-07-18T12:00:01Z"
    _rehash_billing(future)
    with pytest.raises(P176LiveGateError, match="billing_poll_stale"):
        validate_billing_report(future, now=now)

    forecast_stop = deepcopy(billing)
    forecast_stop["latest_forecast_cost_krw"] = 24000
    _rehash_billing(forecast_stop)
    with pytest.raises(P176LiveGateError, match="cost_hard_stop_breached"):
        validate_billing_report(forecast_stop, now=now)

    apply_start = now - timedelta(hours=25)
    terminal_stop = now
    teardown_start = terminal_stop + timedelta(minutes=45)
    assert (
        validate_collection_time_gate(
            collection_started_at=apply_start.isoformat().replace("+00:00", "Z"),
            collection_completed_at=terminal_stop.isoformat().replace("+00:00", "Z"),
            reviewed_apply_started_at=apply_start.isoformat().replace("+00:00", "Z"),
            terminal_stop_at=terminal_stop.isoformat().replace("+00:00", "Z"),
            teardown_started_at=teardown_start.isoformat().replace("+00:00", "Z"),
        )["collection_time_bound_valid"]
        is True
    )
    with pytest.raises(P176LiveGateError, match="collection_time_bound_invalid"):
        validate_collection_time_gate(
            collection_started_at=(now - timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
            collection_completed_at=now.isoformat().replace("+00:00", "Z"),
            reviewed_apply_started_at=apply_start.isoformat().replace("+00:00", "Z"),
            terminal_stop_at=terminal_stop.isoformat().replace("+00:00", "Z"),
            teardown_started_at=teardown_start.isoformat().replace("+00:00", "Z"),
        )
    assert (
        validate_collection_time_gate(
            collection_started_at=(now - timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
            collection_completed_at=now.isoformat().replace("+00:00", "Z"),
            reviewed_apply_started_at=apply_start.isoformat().replace("+00:00", "Z"),
            terminal_stop_at=terminal_stop.isoformat().replace("+00:00", "Z"),
            teardown_started_at=teardown_start.isoformat().replace("+00:00", "Z"),
            concurrency_plan_proven=True,
        )["collection_time_bound_valid"]
        is True
    )
    with pytest.raises(P176LiveGateError, match="resource_lease_bound_invalid"):
        validate_collection_time_gate(
            collection_started_at=(now - timedelta(hours=25)).isoformat().replace("+00:00", "Z"),
            collection_completed_at=now.isoformat().replace("+00:00", "Z"),
            reviewed_apply_started_at=(now - timedelta(hours=48, seconds=1)).isoformat().replace("+00:00", "Z"),
            terminal_stop_at=terminal_stop.isoformat().replace("+00:00", "Z"),
            teardown_started_at=teardown_start.isoformat().replace("+00:00", "Z"),
        )
    with pytest.raises(P176LiveGateError, match="collection_completion_order_invalid"):
        validate_collection_time_gate(
            collection_started_at=(now - timedelta(hours=25)).isoformat().replace("+00:00", "Z"),
            collection_completed_at=(now + timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
            reviewed_apply_started_at=apply_start.isoformat().replace("+00:00", "Z"),
            terminal_stop_at=terminal_stop.isoformat().replace("+00:00", "Z"),
            teardown_started_at=teardown_start.isoformat().replace("+00:00", "Z"),
        )

    teardown = {
        "schema_version": "p176.live_teardown_proof.v1",
        "phase": "p176",
        "run_id": RUN_ID,
        "reviewed_teardown_plan_hash": HASH,
        "reviewed_apply_started_at": apply_start.isoformat().replace("+00:00", "Z"),
        "collection_started_at": apply_start.isoformat().replace("+00:00", "Z"),
        "collection_completed_at": terminal_stop.isoformat().replace("+00:00", "Z"),
        "terminal_stop_at": terminal_stop.isoformat().replace("+00:00", "Z"),
        "teardown_started_at": teardown_start.isoformat().replace("+00:00", "Z"),
        "teardown_completed_at": (teardown_start + timedelta(minutes=10)).isoformat().replace("+00:00", "Z"),
        "concurrency_plan_proven": False,
        "remaining_non_billing_resource_count": 0,
        "residual_effect_count": 0,
        "final_cost_snapshot_hash": HASH,
    }
    teardown["teardown_hash"] = stable_hash(teardown)
    assert validate_teardown_proof(teardown, terminal_stop_at=terminal_stop.isoformat().replace("+00:00", "Z")) == teardown

    teardown["remaining_non_billing_resource_count"] = 1
    teardown["teardown_hash"] = stable_hash({key: value for key, value in teardown.items() if key != "teardown_hash"})
    with pytest.raises(P176LiveGateError, match="remaining_non_billing_resource_count_nonzero"):
        validate_teardown_proof(teardown, terminal_stop_at=terminal_stop.isoformat().replace("+00:00", "Z"))


def test_plan_artifact_binding_hashes_actual_terraform_receipts(tmp_path: Path) -> None:
    apply_plan = tmp_path / "p176-live.tfplan.json"
    apply_plan.write_bytes(b'{"format_version":"1.2","terraform_version":"1.9.0"}\n')
    claimed = _file_hash(apply_plan)

    binding = validate_plan_artifact_binding(
        artifact_path=apply_plan,
        allowed_evidence_root=tmp_path,
        claimed_digest=claimed,
        digest_field="reviewed_apply_plan_hash",
        artifact_field="reviewed_apply_plan_artifact_path",
        logical_name="reviewed_apply_plan",
    )

    assert binding == {
        "reviewed_apply_plan_artifact_name": "reviewed_apply_plan",
        "reviewed_apply_plan_hash": claimed,
    }


def test_plan_artifact_binding_fails_closed_on_mismatch_missing_and_tampering(tmp_path: Path) -> None:
    plan = tmp_path / "p176-live-destroy.tfplan"
    plan.write_bytes(b"terraform binary plan receipt v1")
    claimed = _file_hash(plan)

    mismatched = tmp_path / "mismatched.tfplan"
    mismatched.write_bytes(b"different plan bytes")
    with pytest.raises(P176LiveGateError, match="reviewed_teardown_plan_hash_mismatch"):
        validate_plan_artifact_binding(
            artifact_path=mismatched,
            allowed_evidence_root=tmp_path,
            claimed_digest=claimed,
            digest_field="reviewed_teardown_plan_hash",
            artifact_field="reviewed_teardown_plan_artifact_path",
            logical_name="reviewed_teardown_plan",
        )

    with pytest.raises(P176LiveGateError, match="reviewed_teardown_plan_artifact_missing_or_unsafe"):
        validate_plan_artifact_binding(
            artifact_path=tmp_path / "missing.tfplan",
            allowed_evidence_root=tmp_path,
            claimed_digest=claimed,
            digest_field="reviewed_teardown_plan_hash",
            artifact_field="reviewed_teardown_plan_artifact_path",
            logical_name="reviewed_teardown_plan",
        )

    tampered = tmp_path / "tampered.tfplan"
    tampered.write_bytes(b"terraform binary plan receipt v1")
    tampered.write_bytes(b"terraform binary plan receipt v2")
    with pytest.raises(P176LiveGateError, match="reviewed_teardown_plan_hash_mismatch"):
        validate_plan_artifact_binding(
            artifact_path=tampered,
            allowed_evidence_root=tmp_path,
            claimed_digest=claimed,
            digest_field="reviewed_teardown_plan_hash",
            artifact_field="reviewed_teardown_plan_artifact_path",
            logical_name="reviewed_teardown_plan",
        )


def test_plan_artifact_binding_rejects_outside_root_symlink_and_non_regular_files(tmp_path: Path) -> None:
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    outside = tmp_path / "outside.tfplan"
    outside.write_bytes(b"outside plan")
    inside = evidence_root / "inside.tfplan"
    inside.write_bytes(b"inside plan")

    with pytest.raises(P176LiveGateError, match="reviewed_apply_plan_artifact_outside_allowed_evidence_root"):
        validate_plan_artifact_binding(
            artifact_path=outside,
            allowed_evidence_root=evidence_root,
            claimed_digest=_file_hash(outside),
            digest_field="reviewed_apply_plan_hash",
            artifact_field="reviewed_apply_plan_artifact_path",
            logical_name="reviewed_apply_plan",
        )

    symlink = evidence_root / "plan-link.tfplan"
    symlink.symlink_to(inside)
    with pytest.raises(P176LiveGateError, match="reviewed_apply_plan_artifact_missing_or_unsafe"):
        validate_plan_artifact_binding(
            artifact_path=symlink,
            allowed_evidence_root=evidence_root,
            claimed_digest=_file_hash(inside),
            digest_field="reviewed_apply_plan_hash",
            artifact_field="reviewed_apply_plan_artifact_path",
            logical_name="reviewed_apply_plan",
        )

    with pytest.raises(P176LiveGateError, match="reviewed_apply_plan_artifact_missing_or_unsafe"):
        validate_plan_artifact_binding(
            artifact_path=evidence_root,
            allowed_evidence_root=evidence_root,
            claimed_digest=_file_hash(inside),
            digest_field="reviewed_apply_plan_hash",
            artifact_field="reviewed_apply_plan_artifact_path",
            logical_name="reviewed_apply_plan",
        )


def _fault_proof_hash(run_id: str, episode_id: object, fault_lease_id: str, proof_type: str) -> str:
    return stable_hash(
        {
            "schema_version": "p176.live_fault_proof_binding.v1",
            "run_id": run_id,
            "episode_id": str(episode_id),
            "fault_lease_id": fault_lease_id,
            "proof_type": proof_type,
        }
    )


def _rehash_billing(report: dict[str, object]) -> None:
    receipt = report["latest_provider_poll_receipt"]
    assert isinstance(receipt, dict)
    receipt["run_id"] = report["run_id"]
    receipt["project_id"] = report["project_id"]
    receipt["billing_account_id"] = report["billing_account_id"]
    receipt["budget_resource_name"] = report["budget_resource_name"]
    receipt["polled_at"] = report["latest_poll_at"]
    receipt["actual_cost_krw"] = report["latest_actual_cost_krw"]
    receipt["forecast_cost_krw"] = report["latest_forecast_cost_krw"]
    receipt["receipt_hash"] = stable_hash({key: value for key, value in receipt.items() if key != "receipt_hash"})
    report["billing_report_hash"] = stable_hash({key: value for key, value in report.items() if key != "billing_report_hash"})


def _file_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
