from __future__ import annotations

import hashlib
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest

from app.services.p147_p152_contracts import canonical_json_bytes, stable_hash
from app.services.p179_readiness import (
    P179ReadinessError,
    acquire_leader_lease,
    build_p179_readiness_artifact,
    evaluate_self_monitoring_readiness,
    make_integrity_receipt,
    record_checkpoint,
    replay_checkpoints_exactly_once,
    run_chaos_drill,
    validate_integrity_receipt,
    validate_p179_readiness_artifact,
)

ROOT = Path(__file__).resolve().parents[1]


def _signed_release_evidence(*, schema_version: str, claim: str, receipt_key: str = "independent_reviewer_receipt") -> dict[str, object]:
    evidence: dict[str, object] = {
        "schema_version": schema_version,
        "qualified": True,
        "claim": claim,
        "artifact_path": f"evals/{schema_version[:4]}/release-evidence.json",
        "artifact_file_hash": stable_hash({"artifact": schema_version}),
        "report_hash": stable_hash({"report": schema_version}),
        "freeze_hash": stable_hash({"freeze": schema_version}),
        "final_review_hash": stable_hash({"review": schema_version}),
    }
    evidence["evidence_hash"] = hashlib.sha256(canonical_json_bytes(evidence)).hexdigest()
    evidence[receipt_key] = {
        "schema_version": "independent.receipt.v1",
        "signer_id": "independent-reviewer",
        "payload_hash": evidence["evidence_hash"],
        "signature_hash": stable_hash({"payload_hash": evidence["evidence_hash"], "signer_id": "independent-reviewer"}),
    }
    return evidence


def test_integrity_receipts_are_hash_bound_and_do_not_embed_secrets() -> None:
    receipt = make_integrity_receipt(
        payload={"generation": "p179-gen-0001", "decision_id": "decision-1"},
        signer_id="p179-supervisor",
        key_ref="local-test-key-ref",
    )

    assert receipt["payload_hash"] == stable_hash({"generation": "p179-gen-0001", "decision_id": "decision-1"})
    assert receipt["key_ref_hash"] == stable_hash({"key_ref": "local-test-key-ref"})
    assert "local-test-key-ref" not in str(receipt)
    assert validate_integrity_receipt(receipt, payload={"generation": "p179-gen-0001", "decision_id": "decision-1"})["valid"] is True

    forged = deepcopy(receipt)
    forged["payload_hash"] = stable_hash({"generation": "p179-gen-0001", "decision_id": "forged"})
    with pytest.raises(P179ReadinessError, match="receipt_hash_invalid"):
        validate_integrity_receipt(forged, payload={"generation": "p179-gen-0001", "decision_id": "decision-1"})

    with pytest.raises(P179ReadinessError, match="secret_material_forbidden"):
        make_integrity_receipt(payload={"ok": True}, signer_id="p179-supervisor", key_ref="secret-inline-token")


def test_generation_checkpoints_replay_exactly_once_and_reject_duplicates_or_forgery() -> None:
    first = record_checkpoint(
        generation_id="p179-gen-0001",
        request_id="req-1",
        decision_id="decision-1",
        effect_key="notify:incident-1",
        previous_checkpoint_hash=None,
    )
    duplicate = record_checkpoint(
        generation_id="p179-gen-0002",
        request_id="req-1",
        decision_id="decision-1",
        effect_key="notify:incident-1",
        previous_checkpoint_hash=first["checkpoint_hash"],
    )
    second = record_checkpoint(
        generation_id="p179-gen-0002",
        request_id="req-2",
        decision_id="decision-2",
        effect_key="notify:incident-2",
        previous_checkpoint_hash=first["checkpoint_hash"],
    )

    replay = replay_checkpoints_exactly_once([first, duplicate, second])
    assert replay["resumed_generation_id"] == "p179-gen-0002"
    assert replay["accepted_decision_ids"] == ["decision-1", "decision-2"]
    assert replay["duplicate_request_ids"] == ["req-1"]
    assert replay["duplicate_decision_count"] == 0
    assert replay["resume_exactly_once"] is True

    forged = deepcopy(second)
    forged["effect_key"] = "notify:changed"
    with pytest.raises(P179ReadinessError, match="checkpoint_hash_invalid"):
        replay_checkpoints_exactly_once([first, forged])

    conflicting_duplicate = record_checkpoint(
        generation_id="p179-gen-0003",
        request_id="req-1",
        decision_id="decision-conflict",
        effect_key="notify:incident-conflict",
        previous_checkpoint_hash=first["checkpoint_hash"],
    )
    conflict = replay_checkpoints_exactly_once([first, conflicting_duplicate])
    assert conflict["resume_exactly_once"] is False
    assert conflict["duplicate_decision_count"] == 1


def test_leader_lease_prevents_split_brain_and_allows_expired_takeover() -> None:
    lease = acquire_leader_lease(
        current_lease=None,
        candidate_id="agent-a",
        generation_id="p179-gen-0001",
        now_seconds=100,
        ttl_seconds=30,
    )
    assert lease["acquired"] is True
    assert lease["read_only"] is False

    conflict = acquire_leader_lease(
        current_lease=lease,
        candidate_id="agent-b",
        generation_id="p179-gen-0002",
        now_seconds=120,
        ttl_seconds=30,
    )
    assert conflict["acquired"] is False
    assert conflict["read_only"] is True
    assert conflict["reason"] == "leader_lease_conflict"

    takeover = acquire_leader_lease(
        current_lease=lease,
        candidate_id="agent-b",
        generation_id="p179-gen-0002",
        now_seconds=131,
        ttl_seconds=30,
    )
    assert takeover["acquired"] is True
    assert takeover["holder_id"] == "agent-b"


def test_self_monitoring_readiness_demotes_on_stale_health_evidence_receipt_uncertainty_or_lease_conflict() -> None:
    receipt_payload = {"generation_id": "p179-gen-0001", "health_epoch": 100}
    healthy = {
        "agent_id": "agent-a",
        "generation_id": "p179-gen-0001",
        "observed_at_seconds": 100,
        "heartbeat_at_seconds": 100,
        "health_signals": {
            "leader": "ok",
            "worker": "ok",
            "queue": "ok",
            "evidence": "ok",
            "clock": "ok",
            "storage": "ok",
            "model": "ok",
            "provider": "ok",
            "kill_switch": "ok",
            "deadman": "ok",
        },
        "evidence_latest_at_seconds": 98,
        "uncertainty": False,
        "integrity_receipt_payload": receipt_payload,
        "integrity_receipt": make_integrity_receipt(payload=receipt_payload, signer_id="p179-health-custodian", key_ref="p179-health-key-ref"),
        "leader_lease": {"acquired": True, "read_only": False},
        "p178_qualified": True,
    }
    result = evaluate_self_monitoring_readiness(healthy, now_seconds=105, heartbeat_interval_seconds=10, evidence_freshness_seconds=15)
    assert result["mode"] == "active_shadow"
    assert result["demoted"] is False

    degraded_cases: dict[str, dict[str, object]] = {
        "stale_health": {"heartbeat_at_seconds": 70},
        "stale_evidence": {"evidence_latest_at_seconds": 80},
        "receipt_failure": {
            "integrity_receipt": {
                **cast(Mapping[str, Any], healthy["integrity_receipt"]),
                "payload_hash": stable_hash({"forged": True}),
            }
        },
        "monitor_uncertainty": {"uncertainty": True},
        "lease_conflict": {"leader_lease": {"acquired": False, "read_only": True, "reason": "leader_lease_conflict"}},
        "p178_not_qualified": {"p178_qualified": False},
    }
    for key, value in degraded_cases.items():
        degraded = deepcopy(healthy)
        degraded.update(value)
        demoted = evaluate_self_monitoring_readiness(degraded, now_seconds=105, heartbeat_interval_seconds=10, evidence_freshness_seconds=15)
        assert demoted["mode"] == "read_only_human_required", key
        assert key in demoted["demotion_reasons"], key

    self_asserted = deepcopy(healthy)
    self_asserted["integrity_receipt_valid"] = True
    with pytest.raises(P179ReadinessError, match="self_asserted_integrity_receipt"):
        evaluate_self_monitoring_readiness(self_asserted, now_seconds=105, heartbeat_interval_seconds=10, evidence_freshness_seconds=15)


def test_chaos_drill_injects_failures_and_fails_closed_without_mutation() -> None:
    report = run_chaos_drill(
        scenarios=["process_crash", "clock_skew", "provider_timeout", "storage_corruption", "kill_switch"],
        p178_qualified=True,
    )
    assert report["scenario_count"] == 5
    assert report["failed_demote_count"] == 0
    assert report["duplicate_decision_count"] == 0
    assert report["monitor_blind_interval_count"] == 0
    assert report["kill_switch_drill_pass_rate"] == 1.0
    assert report["safety_counters"]["production_mutation_count"] == 0
    assert all(row["mode"] == "read_only_human_required" for row in report["rows"])
    assert report["report_hash"] == stable_hash({key: value for key, value in report.items() if key != "report_hash"})


def test_p179_readiness_artifact_is_blocked_until_qualified_p178_release_evidence_exists() -> None:
    artifact = build_p179_readiness_artifact(project_root=ROOT, p178_release_evidence=None)
    assert artifact["qualified"] is False
    assert artifact["maximum_claim"] == "readiness_offline_substrate_only"
    assert "ha_self_monitoring_staging_qualified" in artifact["forbidden_claims"]
    assert artifact["p178_release_evidence"]["valid"] is False
    assert validate_p179_readiness_artifact(artifact, project_root=ROOT)["qualified"] is False

    fabricated = deepcopy(artifact)
    fabricated["qualified"] = True
    fabricated["maximum_claim"] = "ha_self_monitoring_staging_qualified"
    fabricated["readiness_hash"] = stable_hash({key: value for key, value in fabricated.items() if key != "readiness_hash"})
    with pytest.raises(P179ReadinessError, match="qualification_forbidden"):
        validate_p179_readiness_artifact(fabricated, project_root=ROOT)

    p178_release = {
        "schema_version": "p178.release_evidence.v1",
        "qualified": True,
        "claim": "bounded_prevention_shadow_qualified",
        "evidence_hash": "sha256:" + "1" * 64,
    }
    still_blocked = build_p179_readiness_artifact(project_root=ROOT, p178_release_evidence=p178_release)
    assert still_blocked["qualified"] is False
    assert still_blocked["p178_release_evidence"]["valid"] is False
    assert "missing_ha_soak_independent_review" in still_blocked["stop_reasons"]

    nonexistent_predecessor = _signed_release_evidence(schema_version="p178.release_evidence.v1", claim="bounded_prevention_shadow_qualified")
    still_offline = build_p179_readiness_artifact(project_root=ROOT, p178_release_evidence=nonexistent_predecessor)
    assert still_offline["qualified"] is False
    assert still_offline["p178_release_evidence"]["valid"] is False
    assert "missing_qualified_p178_release_evidence" in still_offline["stop_reasons"]
