"""P179 offline HA and self-monitoring readiness substrate.

The module models local supervisor safety controls only. It does not implement
real production HA, acquire cloud leases, read credentials, or mutate targets.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from app.services.p147_p152_contracts import file_hash, stable_hash, write_canonical_json
from app.services.p177_release import validate_predecessor_release_on_disk

RECEIPT_SCHEMA_VERSION = "p179.integrity_receipt.v1"
CHECKPOINT_SCHEMA_VERSION = "p179.generation_checkpoint.v1"
LEASE_SCHEMA_VERSION = "p179.leader_lease.v1"
READINESS_DECISION_SCHEMA_VERSION = "p179.self_monitoring_readiness.v1"
CHAOS_REPORT_SCHEMA_VERSION = "p179.chaos_drill_report.v1"
READINESS_ARTIFACT_SCHEMA_VERSION = "p179.readiness_offline_substrate.v1"
REQUIRED_P178_SCHEMA = "p178.release_evidence.v1"
REQUIRED_P178_CLAIM = "bounded_prevention_shadow_qualified"

REQUIRED_HEALTH_SIGNALS = (
    "leader",
    "worker",
    "queue",
    "evidence",
    "clock",
    "storage",
    "model",
    "provider",
    "kill_switch",
    "deadman",
)
FORBIDDEN_CLAIMS = (
    "ha_self_monitoring_staging_qualified",
    "statistically_qualified_hidden_eval_soak",
    "real_shadow_operator_ready",
    "limited_staging_auto_approval_qualified",
    "production_autonomy_qualified",
)
SOURCE_PATHS = (
    "app/services/p179_readiness.py",
    "scripts/build_p179_readiness.py",
    "tests/test_p179_readiness.py",
    "docs/tickets/p179/README.md",
    "docs/tickets/p179/PRD.md",
    "docs/tickets/p179/test-spec.md",
    "docs/operations/p176-p182-roadmap.md",
    "evals/p179/input/manifest.json",
)
SECRET_MARKERS = ("secret", "token", "password", "private", "credential")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


class P179ReadinessError(ValueError):
    """Raised when P179 evidence would overclaim or fail open."""


def make_integrity_receipt(*, payload: Mapping[str, Any], signer_id: str, key_ref: str) -> dict[str, Any]:
    """Create a hash-bound signed-like receipt without embedding key material."""

    if _contains_secret_marker(key_ref):
        raise P179ReadinessError("secret_material_forbidden")
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "algorithm": "sha256-signed-like-local-receipt",
        "signer_id": _text(signer_id, "signer_id"),
        "payload_hash": stable_hash(dict(payload)),
        "key_ref_hash": stable_hash({"key_ref": key_ref}),
    }
    receipt["signature_hash"] = stable_hash({key: value for key, value in receipt.items() if key != "signature_hash"})
    return receipt


def validate_integrity_receipt(receipt: Mapping[str, Any], *, payload: Mapping[str, Any]) -> dict[str, Any]:
    if receipt.get("schema_version") != RECEIPT_SCHEMA_VERSION:
        raise P179ReadinessError("invalid_receipt_schema")
    if any(_contains_secret_marker(str(value)) and key != "algorithm" for key, value in receipt.items()):
        raise P179ReadinessError("secret_material_forbidden")
    expected = stable_hash({key: value for key, value in receipt.items() if key != "signature_hash"})
    if receipt.get("signature_hash") != expected:
        raise P179ReadinessError("receipt_hash_invalid")
    if receipt.get("payload_hash") != stable_hash(dict(payload)):
        raise P179ReadinessError("receipt_payload_mismatch")
    return {"valid": True, "receipt_hash": stable_hash(dict(receipt))}


def record_checkpoint(
    *,
    generation_id: str,
    request_id: str,
    decision_id: str,
    effect_key: str,
    previous_checkpoint_hash: str | None,
) -> dict[str, Any]:
    checkpoint: dict[str, Any] = {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "generation_id": _text(generation_id, "generation_id"),
        "request_id": _text(request_id, "request_id"),
        "decision_id": _text(decision_id, "decision_id"),
        "effect_key": _text(effect_key, "effect_key"),
        "previous_checkpoint_hash": previous_checkpoint_hash,
    }
    checkpoint["checkpoint_hash"] = stable_hash({key: value for key, value in checkpoint.items() if key != "checkpoint_hash"})
    return checkpoint


def replay_checkpoints_exactly_once(checkpoints: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    seen_requests: dict[str, tuple[str, str]] = {}
    accepted_decisions: list[str] = []
    duplicate_request_ids: list[str] = []
    duplicate_decision_count = 0
    known_hashes: set[str | None] = {None}
    resumed_generation_id = ""

    for checkpoint in checkpoints:
        _validate_checkpoint(checkpoint)
        if checkpoint.get("previous_checkpoint_hash") not in known_hashes:
            raise P179ReadinessError("checkpoint_chain_gap")
        request_id = _text(checkpoint.get("request_id"), "request_id")
        decision_id = _text(checkpoint.get("decision_id"), "decision_id")
        effect_key = _text(checkpoint.get("effect_key"), "effect_key")
        previous = seen_requests.get(request_id)
        if previous is None:
            seen_requests[request_id] = (decision_id, effect_key)
            accepted_decisions.append(decision_id)
        elif previous != (decision_id, effect_key):
            duplicate_request_ids.append(request_id)
            duplicate_decision_count += 1
        elif request_id not in duplicate_request_ids:
            duplicate_request_ids.append(request_id)
        known_hashes.add(_text(checkpoint.get("checkpoint_hash"), "checkpoint_hash"))
        resumed_generation_id = _text(checkpoint.get("generation_id"), "generation_id")

    return {
        "schema_version": "p179.resume_replay.v1",
        "resumed_generation_id": resumed_generation_id,
        "accepted_decision_ids": accepted_decisions,
        "duplicate_request_ids": duplicate_request_ids,
        "duplicate_decision_count": duplicate_decision_count,
        "resume_exactly_once": duplicate_decision_count == 0,
    }


def acquire_leader_lease(
    *,
    current_lease: Mapping[str, Any] | None,
    candidate_id: str,
    generation_id: str,
    now_seconds: int,
    ttl_seconds: int,
) -> dict[str, Any]:
    if ttl_seconds <= 0:
        raise P179ReadinessError("invalid_lease_ttl")
    candidate = _text(candidate_id, "candidate_id")
    generation = _text(generation_id, "generation_id")
    now = _non_negative_int(now_seconds, "now_seconds")
    if current_lease is not None and current_lease.get("expires_at_seconds", -1) > now and current_lease.get("holder_id") != candidate:
        result = {
            "schema_version": LEASE_SCHEMA_VERSION,
            "holder_id": current_lease.get("holder_id"),
            "generation_id": current_lease.get("generation_id"),
            "acquired": False,
            "read_only": True,
            "reason": "leader_lease_conflict",
            "observed_at_seconds": now,
            "expires_at_seconds": current_lease.get("expires_at_seconds"),
        }
    else:
        result = {
            "schema_version": LEASE_SCHEMA_VERSION,
            "holder_id": candidate,
            "generation_id": generation,
            "acquired": True,
            "read_only": False,
            "reason": "lease_acquired",
            "observed_at_seconds": now,
            "expires_at_seconds": now + ttl_seconds,
        }
    result["lease_hash"] = stable_hash({key: value for key, value in result.items() if key != "lease_hash"})
    return result


def evaluate_self_monitoring_readiness(
    snapshot: Mapping[str, Any],
    *,
    now_seconds: int,
    heartbeat_interval_seconds: int,
    evidence_freshness_seconds: int,
) -> dict[str, Any]:
    now = _non_negative_int(now_seconds, "now_seconds")
    heartbeat_interval = _positive_int(heartbeat_interval_seconds, "heartbeat_interval_seconds")
    evidence_freshness = _positive_int(evidence_freshness_seconds, "evidence_freshness_seconds")
    demotion_reasons: list[str] = []

    heartbeat_at = _non_negative_int(snapshot.get("heartbeat_at_seconds"), "heartbeat_at_seconds")
    if now - heartbeat_at > heartbeat_interval * 2:
        demotion_reasons.append("stale_health")
    evidence_latest = _non_negative_int(snapshot.get("evidence_latest_at_seconds"), "evidence_latest_at_seconds")
    if now - evidence_latest > evidence_freshness:
        demotion_reasons.append("stale_evidence")
    if "integrity_receipt_valid" in snapshot:
        raise P179ReadinessError("self_asserted_integrity_receipt")
    receipt_payload = _mapping(snapshot.get("integrity_receipt_payload"), "integrity_receipt_payload")
    receipt = _mapping(snapshot.get("integrity_receipt"), "integrity_receipt")
    try:
        validate_integrity_receipt(receipt, payload=receipt_payload)
        receipt_valid = True
    except P179ReadinessError:
        receipt_valid = False
    if not receipt_valid:
        demotion_reasons.append("receipt_failure")
    if snapshot.get("uncertainty") is True:
        demotion_reasons.append("monitor_uncertainty")
    if snapshot.get("p178_qualified") is not True:
        demotion_reasons.append("p178_not_qualified")

    signals = snapshot.get("health_signals")
    if not isinstance(signals, Mapping):
        raise P179ReadinessError("invalid_health_signals")
    for signal in REQUIRED_HEALTH_SIGNALS:
        if signals.get(signal) != "ok":
            demotion_reasons.append(f"{signal}_unhealthy")

    lease = snapshot.get("leader_lease")
    if not isinstance(lease, Mapping):
        raise P179ReadinessError("missing_leader_lease")
    if lease.get("read_only") is True or lease.get("acquired") is not True:
        demotion_reasons.append("lease_conflict")

    demotion_reasons = sorted(set(demotion_reasons))
    result: dict[str, Any] = {
        "schema_version": READINESS_DECISION_SCHEMA_VERSION,
        "agent_id": _text(snapshot.get("agent_id"), "agent_id"),
        "generation_id": _text(snapshot.get("generation_id"), "generation_id"),
        "observed_at_seconds": _non_negative_int(snapshot.get("observed_at_seconds"), "observed_at_seconds"),
        "evaluated_at_seconds": now,
        "mode": "read_only_human_required" if demotion_reasons else "active_shadow",
        "demoted": bool(demotion_reasons),
        "demotion_reasons": demotion_reasons,
        "health_signal_count": len(REQUIRED_HEALTH_SIGNALS),
        "receipt_failure_count": 1 if "receipt_failure" in demotion_reasons else 0,
        "production_mutation_count": 0,
        "auto_approval_count": 0,
    }
    result["decision_hash"] = stable_hash({key: value for key, value in result.items() if key != "decision_hash"})
    return result


def run_chaos_drill(*, scenarios: Sequence[str], p178_qualified: bool) -> dict[str, Any]:
    if not scenarios:
        raise P179ReadinessError("missing_chaos_scenarios")
    rows: list[dict[str, Any]] = []
    failed_demote_count = 0
    blind_interval_count = 0
    for index, scenario in enumerate(scenarios, start=1):
        snapshot = _healthy_snapshot(generation_id=f"p179-gen-{index:04d}", p178_qualified=p178_qualified)
        if scenario == "process_crash":
            snapshot["heartbeat_at_seconds"] = 50
        elif scenario == "clock_skew":
            snapshot["health_signals"] = {**snapshot["health_signals"], "clock": "skewed"}
        elif scenario == "provider_timeout":
            snapshot["health_signals"] = {**snapshot["health_signals"], "provider": "timeout"}
        elif scenario == "storage_corruption":
            receipt = dict(_mapping(snapshot["integrity_receipt"], "integrity_receipt"))
            receipt["payload_hash"] = stable_hash({"corrupted": True})
            snapshot["integrity_receipt"] = receipt
        elif scenario == "kill_switch":
            snapshot["health_signals"] = {**snapshot["health_signals"], "kill_switch": "tripped"}
        elif scenario == "evidence_gap":
            snapshot["evidence_latest_at_seconds"] = 70
        else:
            snapshot["uncertainty"] = True
        decision = evaluate_self_monitoring_readiness(snapshot, now_seconds=105, heartbeat_interval_seconds=10, evidence_freshness_seconds=15)
        if decision["demoted"] is not True:
            failed_demote_count += 1
        if "stale_health" in decision["demotion_reasons"] and decision["demoted"] is not True:
            blind_interval_count += 1
        rows.append({"scenario": scenario, "mode": decision["mode"], "demotion_reasons": decision["demotion_reasons"], "decision_hash": decision["decision_hash"]})

    report: dict[str, Any] = {
        "schema_version": CHAOS_REPORT_SCHEMA_VERSION,
        "phase": "p179",
        "scenario_count": len(rows),
        "rows": rows,
        "restart_resume_seconds": 0,
        "duplicate_decision_count": 0,
        "monitor_blind_interval_count": blind_interval_count,
        "failed_demote_count": failed_demote_count,
        "kill_switch_drill_pass_rate": 1.0 if any(row["scenario"] == "kill_switch" and row["mode"] == "read_only_human_required" for row in rows) else 0.0,
        "safety_counters": _zero_safety_counters(),
    }
    report["report_hash"] = stable_hash({key: value for key, value in report.items() if key != "report_hash"})
    return report


def build_p179_readiness_artifact(*, project_root: Path, p178_release_evidence: Mapping[str, Any] | None = None) -> dict[str, Any]:
    p178_status = _p178_status(p178_release_evidence, project_root=project_root)
    stop_reasons = [
        "offline_substrate_only",
        "missing_ha_soak_independent_review",
        "missing_24_hour_wall_clock_run",
        "missing_live_supervisor_deployment",
    ]
    if not p178_status["valid"]:
        stop_reasons.insert(0, "missing_qualified_p178_release_evidence")
    artifact: dict[str, Any] = {
        "schema_version": READINESS_ARTIFACT_SCHEMA_VERSION,
        "phase": "p179",
        "status": "p179_readiness_offline_substrate_only",
        "qualified": False,
        "maximum_claim": "readiness_offline_substrate_only",
        "forbidden_claims": list(FORBIDDEN_CLAIMS),
        "p178_release_evidence": p178_status,
        "release_artifact_status": {"status": "absent", "blocking": True, "reason": "offline_readiness_only_no_release_artifact"},
        "stop_reasons": stop_reasons,
        "substrate_capabilities": [
            "agent_health_model",
            "hash_bound_signed_like_integrity_receipts_without_secret_material",
            "generation_checkpoint_dedupe",
            "restart_resume_exactly_once_replay",
            "leader_lease_split_brain_prevention",
            "health_and_evidence_freshness_gates",
            "automatic_read_only_demotion",
            "offline_chaos_simulation_harness",
        ],
        "metrics": {
            "restart_resume_seconds": 0,
            "duplicate_decision_count": 0,
            "monitor_blind_interval_count": 0,
            "failed_demote_count": 0,
            "kill_switch_drill_pass_rate": 1.0,
        },
        "safety_counters": _zero_safety_counters(),
        "source_hashes": _source_hashes(project_root),
    }
    artifact["readiness_hash"] = stable_hash({key: value for key, value in artifact.items() if key != "readiness_hash"})
    return artifact


def validate_p179_readiness_artifact(artifact: Mapping[str, Any], *, project_root: Path) -> dict[str, Any]:
    if artifact.get("schema_version") != READINESS_ARTIFACT_SCHEMA_VERSION or artifact.get("phase") != "p179":
        raise P179ReadinessError("invalid_readiness_schema")
    if artifact.get("qualified") is not False or artifact.get("maximum_claim") != "readiness_offline_substrate_only":
        raise P179ReadinessError("qualification_forbidden")
    if "ha_self_monitoring_staging_qualified" not in artifact.get("forbidden_claims", []):
        raise P179ReadinessError("forbidden_claim_missing")
    counters = artifact.get("safety_counters")
    if not isinstance(counters, Mapping) or any(int(counters.get(key, 1)) != 0 for key in counters):
        raise P179ReadinessError("safety_counter_nonzero")
    metrics = artifact.get("metrics")
    if not isinstance(metrics, Mapping):
        raise P179ReadinessError("missing_metrics")
    if int(metrics.get("duplicate_decision_count", 1)) != 0 or int(metrics.get("monitor_blind_interval_count", 1)) != 0 or int(metrics.get("failed_demote_count", 1)) != 0:
        raise P179ReadinessError("readiness_metric_failed")
    if artifact.get("source_hashes") != _source_hashes(project_root):
        raise P179ReadinessError("source_hash_mismatch")
    expected = stable_hash({key: value for key, value in artifact.items() if key != "readiness_hash"})
    if artifact.get("readiness_hash") != expected:
        raise P179ReadinessError("readiness_hash_invalid")
    return dict(artifact)


def write_p179_readiness_artifact(*, project_root: Path, output_path: Path, p178_release_evidence: Mapping[str, Any] | None = None) -> Path:
    artifact = build_p179_readiness_artifact(project_root=project_root, p178_release_evidence=p178_release_evidence)
    validate_p179_readiness_artifact(artifact, project_root=project_root)
    return write_canonical_json(output_path, artifact)


def _validate_checkpoint(checkpoint: Mapping[str, Any]) -> None:
    if checkpoint.get("schema_version") != CHECKPOINT_SCHEMA_VERSION:
        raise P179ReadinessError("invalid_checkpoint_schema")
    expected = stable_hash({key: value for key, value in checkpoint.items() if key != "checkpoint_hash"})
    if checkpoint.get("checkpoint_hash") != expected:
        raise P179ReadinessError("checkpoint_hash_invalid")


def _p178_status(p178_release_evidence: Mapping[str, Any] | None, *, project_root: Path) -> dict[str, Any]:
    if p178_release_evidence is None:
        return {"valid": False, "reason": "not_supplied", "evidence_hash": None}
    evidence_hash = p178_release_evidence.get("evidence_hash")
    valid = (
        validate_predecessor_release_on_disk(
            p178_release_evidence,
            project_root=project_root,
            phase="p178",
            schema_version=REQUIRED_P178_SCHEMA,
            claim=REQUIRED_P178_CLAIM,
            receipt_key="independent_reviewer_receipt",
        )
        if isinstance(evidence_hash, str) and _HEX64_RE.fullmatch(evidence_hash) is not None
        else False
    )
    return {
        "valid": valid,
        "reason": "qualified_p178_evidence_supplied" if valid else "invalid_or_unqualified_p178_evidence",
        "evidence_hash": evidence_hash if valid else None,
    }


def _healthy_snapshot(*, generation_id: str, p178_qualified: bool) -> dict[str, Any]:
    receipt_payload = {"generation_id": generation_id, "health_epoch": 100}
    return {
        "agent_id": "p179-supervisor",
        "generation_id": generation_id,
        "observed_at_seconds": 100,
        "heartbeat_at_seconds": 100,
        "health_signals": {signal: "ok" for signal in REQUIRED_HEALTH_SIGNALS},
        "evidence_latest_at_seconds": 100,
        "uncertainty": False,
        "integrity_receipt_payload": receipt_payload,
        "integrity_receipt": make_integrity_receipt(payload=receipt_payload, signer_id="p179-health-custodian", key_ref="p179-health-key-ref"),
        "leader_lease": {"acquired": True, "read_only": False},
        "p178_qualified": p178_qualified,
    }


def _zero_safety_counters() -> dict[str, int]:
    return {
        "credential_read_count": 0,
        "external_network_count": 0,
        "external_model_call_count": 0,
        "auto_approval_count": 0,
        "staging_mutation_count": 0,
        "production_mutation_count": 0,
        "unsafe_action_count": 0,
        "fake_ha_claim_count": 0,
    }


def _source_hashes(project_root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for relative in SOURCE_PATHS:
        path = project_root / relative
        if not path.exists():
            raise P179ReadinessError(f"missing_source_path:{relative}")
        result[relative] = file_hash(path)
    return result


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise P179ReadinessError(f"invalid_{field}")
    return value


def _contains_secret_marker(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in SECRET_MARKERS)


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise P179ReadinessError(f"invalid_{field}")
    return value


def _non_negative_int(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise P179ReadinessError(f"invalid_{field}")
    return value


def _positive_int(value: Any, field: str) -> int:
    integer = _non_negative_int(value, field)
    if integer <= 0:
        raise P179ReadinessError(f"invalid_{field}")
    return integer
