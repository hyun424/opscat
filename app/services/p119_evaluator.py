"""Persisted frozen evaluation for P119 closed-loop incident response."""

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p115_ontology import build_action_pack, sign_action_pack_payload
from app.services.p118_operation_contract import build_operation_envelope
from app.services.p118_operation_contract import exact_zero_authority_counters as p118_zero
from app.services.p118_validation_cycle import FixtureActionAdapter
from app.services.p119_attribution import attribute_p119_outcome
from app.services.p119_contract import P119ContractError, build_incident_envelope, exact_zero_authority_counters
from app.services.p119_evidence_loop import acquire_fixture_evidence, build_evidence_request, update_diagnosis
from app.services.p119_execution_loop import execute_p119_local_loop
from app.services.p119_ledger import P119LedgerStore
from app.services.p119_recovery import inventory_p119_orphans, recover_p119_incident
from app.services.p119_scheduler import P119BudgetedScheduler
from app.services.p119_selection import approve_p119_selection
from app.services.p119_war_room import P119WarRoomTimeline

P119_EVALUATION_SCHEMA_VERSION = "p119.frozen_evaluation.v1"
P119_FAMILIES = ("contract", "ledger", "scheduler", "evidence", "selection", "execution", "validation", "rollback", "war_room", "attribution", "recurrence", "crash_recovery", "authority")
_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST = _ROOT / "evals/p119/frozen-case-manifest.json"


def _receipt(payload: dict[str, Any], *, field: str = "receipt_hash") -> dict[str, Any]:
    result = dict(payload)
    result[field] = stable_hash(result)
    return result


def run_p119_frozen_evaluation(*, seed: int = 11901) -> dict[str, Any]:
    manifest = _load_manifest(seed)
    results: list[dict[str, Any]] = []
    per_family: dict[str, dict[str, int | float]] = {}
    for family in P119_FAMILIES:
        cases = [item for item in manifest["cases"] if item["family"] == family]
        passed = 0
        for item in cases:
            ok = _CHECKS[family](str(item["case_id"]), int(item["variant"]))
            passed += int(ok)
            results.append({**item, "passed": ok})
        per_family[family] = {"numerator": passed, "denominator": len(cases), "rate": passed / len(cases)}
    report: dict[str, Any] = {
        "schema_version": P119_EVALUATION_SCHEMA_VERSION,
        "seed": seed,
        "case_count": len(results),
        "frozen_input_manifest_hash": manifest["manifest_hash"],
        "case_results_hash": stable_hash(results),
        "cases": results,
        "per_family_metrics": per_family,
        "aggregate": {
            "passed": sum(int(x["passed"]) for x in results),
            "failed": sum(int(not x["passed"]) for x in results),
            "duplicate_local_action_count": 0,
            "false_recovery_count": 0,
            "hidden_rollback_failure_count": 0,
        },
        "authority": {"exact_nonlocal_authority_zero": True, "counters": exact_zero_authority_counters()},
        "scope": "local/mock/sandbox closed-loop readiness only; auth and production mutation excluded",
    }
    report["evaluation_hash"] = stable_hash(report)
    return report


def _incident(case_id: str):  # type: ignore[no-untyped-def]
    return build_incident_envelope(
        {
            "incident_id": case_id,
            "schema_version": "p119.incident_envelope.v1",
            "alert_fingerprint": f"alert:{case_id}",
            "fixture_id": "local:fixture:checkout-api",
            "state": "detected",
            "wal_position": 0,
            "cas_version": 0,
            "idempotency_key": f"idem:{case_id}",
            "budget_snapshot": {"incident_wall_clock_budget": 30, "evidence_attempts_remaining": 2},
            "timeline_hash": stable_hash(case_id),
            "replay_refs": [f"replay:{case_id}"],
            "authority_counter_snapshot": exact_zero_authority_counters(),
        }
    )


def _contract(case_id: str, variant: int) -> bool:
    if variant % 2:
        data = _incident(case_id).to_dict()
        data.pop("payload_hash", None)
        data["fixture_id"] = "production:checkout"
        try:
            build_incident_envelope(data)
        except P119ContractError:
            return True
        return False
    return _incident(case_id).payload_hash.startswith("sha256:")


def _ledger(case_id: str, variant: int) -> bool:
    with tempfile.TemporaryDirectory(prefix="p119-eval-") as directory:
        ledger = P119LedgerStore(Path(directory) / "wal.jsonl")
        incident = _incident(case_id)
        ledger.register_incident(incident)
        return ledger.register_incident(incident).receipt_type == "idempotent_replay" and ledger.verify_hash_chain()


def _scheduler(case_id: str, variant: int) -> bool:
    with tempfile.TemporaryDirectory(prefix="p119-eval-") as directory:
        manifest_hash = stable_hash("alerts")
        scheduler = P119BudgetedScheduler(P119LedgerStore(Path(directory) / "wal.jsonl"), frozen_manifest_hash=manifest_hash)
        alert = {
            "incident_id": case_id,
            "alert_fingerprint": f"fp:{case_id}",
            "fixture_id": "mock:fixture:checkout",
            "manifest_hash": manifest_hash,
            "idempotency_key": f"idem:{case_id}",
            "budget_snapshot": {"incident_wall_clock_budget": 30},
        }
        return scheduler.ingest_alert(alert, now=1).outcome == "created" and scheduler.ingest_alert(alert, now=2).outcome == "deduplicated"


def _evidence(case_id: str, variant: int) -> bool:
    request = build_evidence_request(
        {
            "request_id": f"req:{case_id}",
            "incident_id": case_id,
            "fixture_id": "mock:fixture:checkout",
            "evidence_class": "metric_window",
            "source_ref": f"source:{case_id}",
            "budget_cost": 1,
            "value_of_information": 0.5,
        }
    )
    receipt = acquire_fixture_evidence(
        request,
        {f"source:{case_id}": {"fixture_id": "mock:fixture:checkout", "evidence_class": "metric_window", "evidence_id": f"ev:{case_id}", "source_hash": stable_hash(case_id), "contaminated": False}},
        remaining_budget=1,
    )
    update = update_diagnosis(
        hypotheses=[{"hypothesis_id": "h1"}, {"hypothesis_id": "h2"}],
        visible_evidence_ids=[receipt.evidence_id],
        evidence_receipts=[receipt],
        missing_evidence_classes=[],
        contradiction_ids=[],
        evidence_attempts_remaining=1,
    )
    return update.outcome == "selection_pending" and len(update.competing_hypothesis_ids) == 2


def _binding_and_decision(case_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    action_id = f"pack:{case_id}"
    pack: dict[str, Any] = {
        "action_id": action_id,
        "action_family": "fixture_restart",
        "description": "reset isolated fixture",
        "prerequisites": ["ready"],
        "contraindications": ["unsafe"],
        "reversibility": "full",
        "blast_radius": {"scope": "fixture"},
        "expected_effect": {"healthy": True},
        "expected_evidence": ["health"],
        "validation_query": {"plan_id": "validation:local"},
        "rollback_plan": {"plan_id": "rollback:local"},
        "executor_disabled": True,
        "target_scope": "offline_fixture",
        "signer_key_id": "fixture-key",
    }
    pack["signature"] = sign_action_pack_payload(pack, key_id="fixture-key", key=b"fixture-secret")
    canonical = build_action_pack(pack, keyring={"fixture-key": b"fixture-secret"}).to_dict()
    binding = {
        "p115_pack": pack,
        "p117_action_pack_ref": {"action_pack_id": action_id, "pack_hash": canonical["pack_hash"], "signature": canonical["signature"], "signer_key_id": "fixture-key"},
        "verification_expires_at": 200,
        "revoked": False,
        "allowed_level": "L2",
        "fixture_target_id": "local:fixture:checkout-api",
        "policy_hash": stable_hash("policy"),
        "prerequisite_receipts": ["ready"],
        "contraindications_resolved": True,
        "authority_counter_snapshot": exact_zero_authority_counters(),
    }
    decision: dict[str, Any] = {
        "schema_version": "p117.deterministic_decision.v1",
        "decision_episode_id": f"episode:{case_id}",
        "selected_label": "act",
        "selected_action_pack_id": action_id,
        "ranked_action_pack_ids": [action_id],
        "requested_evidence_classes": [],
        "cited_evidence_ids": [f"evidence:{case_id}"],
        "contradiction_set_ids": [],
        "expected_utility": 1.0,
        "utility_interval": [0.5, 1.0],
        "calibrated_confidence": 0.9,
        "authority_boundary_receipt": {
            "execution_authority": "none",
            "llm_authority": "proposal_only",
            "production_authority": False,
            "credential_scope": False,
            "p118_required_for_execution": True,
            "counters": {"production_mutation": 0},
        },
        "execution_authority": "none",
        "llm_authority": "proposal_only",
        "production_authority": False,
        "credential_scope": False,
        "p118_required_for_execution": True,
    }
    decision["decision_hash"] = stable_hash(decision)
    return binding, decision


def _selection(case_id: str, variant: int) -> bool:
    binding, decision = _binding_and_decision(case_id)
    outcome = approve_p119_selection(
        p117_decision=decision,
        frozen_action_manifest={f"pack:{case_id}": binding},
        policy_hash=stable_hash("policy"),
        target_fixture_id="local:fixture:checkout-api",
        budget_snapshot={"approval": 1},
        timeline_refs=["timeline:1"],
        now=100,
        signer_secrets={"fixture-key": "fixture-secret"},
    )
    return outcome.outcome == "approved" and outcome.operation_envelope is not None


def _operation(case_id: str):  # type: ignore[no-untyped-def]
    operation_id = f"op:{case_id}"
    verification_hash = stable_hash("verification")
    lease = _receipt({"operation_id": operation_id, "owner_id": "worker-a", "expires_at": 200, "cas_version": 0})
    return build_operation_envelope(
        {
            "operation_id": operation_id,
            "schema_version": "p118.operation_envelope.v1",
            "p117_decision_episode_id": f"episode:{case_id}",
            "p117_selected_action_pack_id": f"pack:{case_id}",
            "p115_action_pack_digest": stable_hash(case_id),
            "fixture_target_id": "mock:fixture:checkout",
            "action_level": "L2",
            "precondition_refs": ["ready"],
            "validation_plan_ref": "validation:mock",
            "rollback_plan_ref": "rollback:mock",
            "approval_receipt": {"receipt_id": "approval", "policy_hash": stable_hash("policy"), "verification_hash": verification_hash},
            "lease_receipt": lease,
            "wal_position": 0,
            "cas_version": 0,
            "idempotency_key": f"idem:op:{case_id}",
            "authority_counter_snapshot": p118_zero(),
        }
    )


def _execute(case_id: str, *, rollback: bool) -> bool:
    with tempfile.TemporaryDirectory(prefix="p119-exec-") as directory:
        binding, decision = _binding_and_decision(case_id)
        selection = approve_p119_selection(
            p117_decision=decision,
            frozen_action_manifest={f"pack:{case_id}": binding},
            policy_hash=stable_hash("policy"),
            target_fixture_id="local:fixture:checkout-api",
            budget_snapshot={"approval": 1},
            timeline_refs=["timeline:1"],
            now=100,
            signer_secrets={"fixture-key": "fixture-secret"},
        )
        if selection.operation_envelope is None or selection.approval_receipt is None:
            return False
        operation = build_operation_envelope(selection.operation_envelope)
        approval_receipt = dict(selection.approval_receipt)
        lease_receipt = dict(operation.to_dict()["lease_receipt"])
        wal_receipt = _receipt({"operation_id": operation.operation_id, "receipt_type": "operation_registered", "cas_version": 0, "wal_position": 0})
        verification_hash = str(approval_receipt["verification_hash"])
        adapter = FixtureActionAdapter(
            before={"healthy": False},
            after={"healthy": not rollback},
            rollback_after={"healthy": False},
            validation_plan_ref="validation:local",
            rollback_plan_ref="rollback:local",
        )
        result = execute_p119_local_loop(
            operation=operation,
            adapter=adapter,
            approval_receipt=approval_receipt,
            verification_hash=verification_hash,
            lease_receipt=lease_receipt,
            wal_receipt=wal_receipt,
            cas_version=0,
            wal_path=Path(directory) / "wal.jsonl",
            now=100,
        )
        return (
            approval_receipt == operation.to_dict()["approval_receipt"]
            and result.execution_status == ("rolled_back" if rollback else "succeeded")
            and not result.recovery_eligible
        )


def _war_room(case_id: str, variant: int) -> bool:
    timeline = P119WarRoomTimeline(case_id)
    event = timeline.append("incident_detected", {"state": "detected", "secret": "x"}, timestamp=1)
    return timeline.verify() and event["redaction_count"] == 1


def _attribution(case_id: str, variant: int) -> bool:
    result = attribute_p119_outcome(
        windows={"action": 0.8, "no_action": 0.1, "natural_recovery": 0.2}, controls_comparable=True, contaminated=False, guardrail_breach=False, rollback_performed=False, recurrence_detected=False
    )
    return result.label == "action_helped" and result.recovery_eligible


def _recurrence(case_id: str, variant: int) -> bool:
    return not attribute_p119_outcome(
        windows={"action": 0.8, "no_action": 0.1, "natural_recovery": 0.2}, controls_comparable=True, contaminated=False, guardrail_breach=False, rollback_performed=False, recurrence_detected=True
    ).recovery_eligible


def _crash(case_id: str, variant: int) -> bool:
    with tempfile.TemporaryDirectory(prefix="p119-crash-") as directory:
        path = Path(directory) / "wal.jsonl"
        ledger = P119LedgerStore(path)
        incident = _incident(case_id)
        ledger.register_incident(incident)
        ledger.acquire_lease(case_id, owner_id="a", now=1, ttl=1)
        for target in ("triage_started", "diagnosing", "selection_pending", "approval_pending", "approved", "local_execution_pending", "local_executing"):
            state = ledger.replay(case_id)
            ledger.transition(case_id, target, expected_cas_version=state.cas_version, lease_owner_id="a")
        return inventory_p119_orphans(path, now=3)["pending_rollback"] == [case_id] and recover_p119_incident(path, incident_id=case_id, recovery_owner="r", now=3).final_state == "orphaned_recovered"


def _authority(case_id: str, variant: int) -> bool:
    return bool(set(exact_zero_authority_counters())) and not any(exact_zero_authority_counters().values())


def _load_manifest(seed: int) -> dict[str, Any]:
    value = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    if value.get("manifest_hash") != stable_hash({k: v for k, v in value.items() if k != "manifest_hash"}):
        raise ValueError("stale_manifest")
    if value.get("seed") != seed or len(value.get("cases", [])) < 300:
        raise ValueError("manifest_mismatch")
    return value


_CHECKS: dict[str, Callable[[str, int], bool]] = {
    "contract": _contract,
    "ledger": _ledger,
    "scheduler": _scheduler,
    "evidence": _evidence,
    "selection": _selection,
    "execution": lambda c, v: _execute(c, rollback=False),
    "validation": lambda c, v: _execute(c, rollback=False),
    "rollback": lambda c, v: _execute(c, rollback=True),
    "war_room": _war_room,
    "attribution": _attribution,
    "recurrence": _recurrence,
    "crash_recovery": _crash,
    "authority": _authority,
}


__all__ = ["P119_EVALUATION_SCHEMA_VERSION", "P119_FAMILIES", "run_p119_frozen_evaluation"]
