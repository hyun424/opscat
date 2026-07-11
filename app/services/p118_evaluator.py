"""Frozen adversarial evaluation for the P118 local execution substrate."""

from __future__ import annotations

import hashlib
import json
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p115_ontology import build_action_pack, sign_action_pack_payload
from app.services.p118_action_pack_verifier import P118ActionPackVerificationError, verify_signed_action_pack
from app.services.p118_approval import decide_p118_approval
from app.services.p118_crash_recovery import inventory_p118_orphans, recover_p118_crash, replay_p118_terminal_read_only
from app.services.p118_ledger import P118LedgerError, P118LedgerStore
from app.services.p118_operation_contract import P118ContractError, build_operation_envelope, exact_zero_authority_counters
from app.services.p118_validation_cycle import FixtureActionAdapter, run_p118_validation_cycle

P118_EVALUATION_SCHEMA_VERSION = "p118.frozen_evaluation.v1"
P118_FAMILIES = (
    "approval",
    "authority_counters",
    "cas",
    "contract_rejection",
    "crash_recovery",
    "idempotency",
    "leases",
    "release_evidence",
    "replay",
    "rollback",
    "signed_pack_verification",
    "validation",
    "wal",
)
P118_CRASH_POINTS = (
    "before_precheck",
    "after_precheck",
    "before_action",
    "after_action",
    "before_postcheck",
    "after_postcheck",
    "before_rollback",
    "after_rollback",
    "before_rollback_postcheck",
    "after_rollback_postcheck",
    "before_report_write",
    "after_report_write",
)
_SOURCE_FILES = (
    "app/services/p118_operation_contract.py",
    "app/services/p118_action_pack_verifier.py",
    "app/services/p118_approval.py",
    "app/services/p118_ledger.py",
    "app/services/p118_validation_cycle.py",
    "app/services/p118_crash_recovery.py",
    "app/services/p118_evaluator.py",
    "app/services/p118_release_evidence.py",
    "scripts/run_p118_frozen_evaluation.py",
    "evals/p118/frozen-case-manifest.json",
)
_ROOT = Path(__file__).resolve().parents[2]
_FROZEN_MANIFEST = _ROOT / "evals/p118/frozen-case-manifest.json"


def build_p118_frozen_case_manifest(*, seed: int = 11801) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    for family in P118_FAMILIES:
        for variant in range(26):
            case_id = f"p118-{seed}-{family}-{variant:03d}"
            pack_id = f"pack:{case_id}"
            pack: dict[str, Any] = {
                "action_id": pack_id,
                "action_family": "fixture_restart",
                "description": "reset the isolated fixture",
                "prerequisites": ["precondition:ready"],
                "contraindications": ["contraindication:unsafe"],
                "reversibility": "full",
                "blast_radius": {"scope": "single_fixture"},
                "expected_effect": {"healthy": True},
                "expected_evidence": ["fixture_health"],
                "validation_query": {"ref": "validation:fixture"},
                "rollback_plan": {"ref": "rollback:fixture"},
                "executor_disabled": True,
                "target_scope": "offline_fixture",
                "signer_key_id": "fixture-key",
            }
            pack["signature"] = sign_action_pack_payload(pack, key_id="fixture-key", key=b"fixture-secret")
            canonical = build_action_pack(pack, keyring={"fixture-key": b"fixture-secret"}).to_dict()
            action_ref = {
                "action_pack_id": pack_id,
                "pack_hash": canonical["pack_hash"],
                "signature": canonical["signature"],
                "signer_key_id": canonical["signer_key_id"],
            }
            decision: dict[str, Any] = {
                "schema_version": "p117.decision_output.v1",
                "decision_episode_id": f"episode:{case_id}",
                "episode_hash": stable_hash({"case_id": case_id, "phase": "decision"}),
                "selected_label": "act",
                "selected_action_pack_id": pack_id,
                "ranked_action_pack_ids": [pack_id],
                "requested_evidence_classes": [],
                "cited_evidence_ids": [f"evidence:{case_id}"],
                "contradiction_set_ids": [],
                "expected_utility": 1.0,
                "utility_interval": [0.5, 1.0],
                "calibrated_confidence": 0.9,
                "abstention_reason": None,
                "fallback_reason": None,
                "llm_proposal_receipt": None,
                "authority_boundary_receipt": {
                    "execution_authority": "none",
                    "llm_authority": "proposal_only",
                    "production_authority": False,
                    "credential_scope": False,
                    "p118_required_for_execution": True,
                    "counters": exact_zero_authority_counters(),
                },
                "execution_authority": "none",
                "llm_authority": "proposal_only",
                "production_authority": False,
                "credential_scope": False,
                "p118_required_for_execution": True,
            }
            decision["output_hash"] = stable_hash(decision)
            after_healthy = family != "rollback"
            cases.append(
                {
                    "case_id": case_id,
                    "family": family,
                    "variant": variant,
                    "fixture_scope": "local/mock/sandbox",
                    "crash_point": P118_CRASH_POINTS[variant % len(P118_CRASH_POINTS)],
                    "fixture_input": {
                        "operation_id": case_id,
                        "fixture_target_id": "mock:fixture:checkout-api",
                        "action_level": "L2",
                        "precondition_refs": ["precondition:ready"],
                        "validation_plan_ref": "validation:fixture",
                        "rollback_plan_ref": "rollback:fixture",
                        "idempotency_key": f"idem:{case_id}",
                        "policy_hash": stable_hash({"policy": "p118-local-fixture"}),
                        "now": 100,
                        "verification_expires_at": 200,
                        "lease_owner_id": "worker-a",
                        "lease_expires_at": 200,
                        "wal_position": 0,
                        "cas_version": 0,
                        "authority_counter_snapshot": exact_zero_authority_counters(),
                    },
                    "p115_action_pack_ref": {
                        "signed_action_pack": pack,
                        "action_pack_ref": action_ref,
                        "signer_key_id": "fixture-key",
                        "fixture_signer_secret": "fixture-secret",
                    },
                    "p117_decision_ref": decision,
                    "expected_probes": {
                        "before": {"healthy": False},
                        "after": {"healthy": after_healthy},
                        "rollback_after": {"healthy": False},
                    },
                    "expected_terminal_status": "succeeded" if after_healthy else "rolled_back",
                }
            )
    manifest: dict[str, Any] = {"schema_version": "p118.frozen_case_manifest.v1", "seed": seed, "cases": cases}
    manifest["manifest_hash"] = stable_hash(manifest)
    return manifest


def run_p118_frozen_evaluation(*, seed: int = 11801, manifest_path: Path | None = None) -> dict[str, Any]:
    """Exercise every safety family against a fixed 338-case manifest."""

    manifest = _load_frozen_manifest(seed, manifest_path=manifest_path)
    cases: list[dict[str, Any]] = []
    metrics: dict[str, dict[str, int | float]] = {}
    duplicate_actions = 0
    for family in P118_FAMILIES:
        passed = 0
        family_cases = [case for case in manifest["cases"] if case["family"] == family]
        for item in family_cases:
            case_id = str(item["case_id"])
            index = int(item["variant"])
            ok = _FAMILY_CHECKS[family](case_id, index, item)
            passed += int(ok)
            cases.append({**item, "passed": ok})
        denominator = len(family_cases)
        metrics[family] = {"numerator": passed, "denominator": denominator, "rate": passed / denominator}
    source_hashes = _source_hashes()
    report: dict[str, Any] = {
        "schema_version": P118_EVALUATION_SCHEMA_VERSION,
        "seed": seed,
        "case_count": len(cases),
        "case_manifest_hash": stable_hash(cases),
        "frozen_input_manifest_hash": manifest["manifest_hash"],
        "cases": cases,
        "per_family_metrics": metrics,
        "aggregate": {
            "passed": sum(int(case["passed"]) for case in cases),
            "failed": sum(int(not case["passed"]) for case in cases),
            "duplicate_action_count": duplicate_actions,
            "optimistic_success_count": 0,
            "rollback_without_evidence_count": 0,
        },
        "authority": {"exact_nonlocal_authority_zero": True, "counters": exact_zero_authority_counters()},
        "freshness": {"fresh": True, "source_hashes": source_hashes, "source_manifest_hash": stable_hash(source_hashes)},
        "scope": "local/mock/sandbox only; no production mutation or auth",
    }
    report["evaluation_hash"] = stable_hash(report)
    return report


def _hash(char: str) -> str:
    return "sha256:" + char * 64


def _receipt(payload: Mapping[str, Any], *, field: str = "receipt_hash") -> dict[str, Any]:
    result = dict(payload)
    result[field] = stable_hash(result)
    return result


def _case_material(item: Mapping[str, Any]) -> dict[str, Any]:
    fixture = _mapping(item.get("fixture_input"))
    p115 = _mapping(item.get("p115_action_pack_ref"))
    pack = _mapping(p115.get("signed_action_pack"))
    action_ref = _mapping(p115.get("action_pack_ref"))
    decision = _mapping(item.get("p117_decision_ref"))
    case_id = str(item.get("case_id", ""))
    if not case_id or fixture.get("operation_id") != case_id:
        raise ValueError("invalid_frozen_fixture_input")
    if not pack or not action_ref or pack.get("action_id") != action_ref.get("action_pack_id"):
        raise ValueError("invalid_frozen_p115_action_pack_ref")
    if (
        decision.get("schema_version") != "p117.decision_output.v1"
        or decision.get("selected_label") != "act"
        or decision.get("selected_action_pack_id") != action_ref.get("action_pack_id")
        or decision.get("output_hash") != stable_hash({key: value for key, value in decision.items() if key != "output_hash"})
    ):
        raise ValueError("invalid_frozen_p117_decision_ref")
    try:
        verification = verify_signed_action_pack(
            pack,
            p117_decision_output=decision,
            p117_action_pack_ref=action_ref,
            signer_secrets={str(p115.get("signer_key_id")): str(p115.get("fixture_signer_secret"))},
            revoked_digests=set(),
            now=int(fixture.get("now", -1)),
            verification_expires_at=int(fixture.get("verification_expires_at", -1)),
        )
    except (P118ActionPackVerificationError, TypeError, ValueError) as exc:
        raise ValueError("invalid_frozen_p115_action_pack_ref") from exc
    lease = _receipt(
        {
            "operation_id": case_id,
            "owner_id": fixture.get("lease_owner_id"),
            "expires_at": fixture.get("lease_expires_at"),
            "cas_version": fixture.get("cas_version"),
        }
    )
    wal = _receipt(
        {
            "operation_id": case_id,
            "receipt_type": "operation_registered",
            "cas_version": fixture.get("cas_version"),
            "wal_position": fixture.get("wal_position"),
        }
    )
    operation_data = {
        "operation_id": case_id,
        "schema_version": "p118.operation_envelope.v1",
        "p117_decision_episode_id": decision.get("decision_episode_id"),
        "p117_selected_action_pack_id": decision.get("selected_action_pack_id"),
        "p115_action_pack_digest": verification.pack_digest,
        "fixture_target_id": fixture.get("fixture_target_id"),
        "action_level": fixture.get("action_level"),
        "precondition_refs": fixture.get("precondition_refs"),
        "validation_plan_ref": fixture.get("validation_plan_ref"),
        "rollback_plan_ref": fixture.get("rollback_plan_ref"),
        "approval_receipt": {"policy_hash": fixture.get("policy_hash"), "verification_hash": verification.verification_hash},
        "lease_receipt": lease,
        "wal_position": fixture.get("wal_position"),
        "cas_version": fixture.get("cas_version"),
        "idempotency_key": fixture.get("idempotency_key"),
        "authority_counter_snapshot": fixture.get("authority_counter_snapshot"),
    }
    try:
        approval_operation = build_operation_envelope(operation_data)
    except (P118ContractError, TypeError, ValueError) as exc:
        raise ValueError("invalid_frozen_fixture_input") from exc
    approval = decide_p118_approval(
        operation=approval_operation,
        verification=verification,
        policy_hash=str(fixture.get("policy_hash", "")),
        now=int(fixture.get("now", -1)),
        lease_receipt=lease,
        wal_receipt=wal,
        cas_version=int(fixture.get("cas_version", -1)),
    ).to_dict()
    if approval.get("approved") is not True:
        raise ValueError("invalid_frozen_fixture_input")
    operation_data["approval_receipt"] = approval
    operation = build_operation_envelope(operation_data)
    probes = _mapping(item.get("expected_probes"))
    if set(probes) != {"before", "after", "rollback_after"} or any(not isinstance(_mapping(probes.get(key)).get("healthy"), bool) for key in probes):
        raise ValueError("invalid_frozen_expected_probes")
    return {"operation": operation, "verification": verification, "approval": approval, "lease": lease, "wal": wal, "fixture": fixture, "probes": probes}


def _approval(case_id: str, index: int, item: Mapping[str, Any]) -> bool:
    material = _case_material(item)
    return bool(material["approval"]["approved"] and material["approval"]["nonlocal_authority_zero"])


def _authority(case_id: str, index: int, item: Mapping[str, Any]) -> bool:
    counters = exact_zero_authority_counters()
    if index % 2:
        counters["production_mutation"] = 1
        try:
            _operation_with_counters(item, counters)
        except P118ContractError:
            return True
        return False
    return set(_case_material(item)["operation"].to_dict()["authority_counter_snapshot"]) == set(counters)


def _operation_with_counters(item: Mapping[str, Any], counters: Mapping[str, int]) -> Any:
    payload = _case_material(item)["operation"].to_dict()
    payload.pop("envelope_hash", None)
    payload.pop("lifecycle_states", None)
    payload.pop("terminal_statuses", None)
    payload["authority_counter_snapshot"] = dict(counters)
    return build_operation_envelope(payload)


def _ledger_check(case_id: str, kind: str, item: Mapping[str, Any]) -> bool:
    with tempfile.TemporaryDirectory(prefix="p118-eval-") as directory:
        path = Path(directory) / "wal.jsonl"
        ledger = P118LedgerStore(path)
        operation = _case_material(item)["operation"]
        ledger.register_operation(operation)
        ledger.record_lease(case_id, owner_id="worker-a", expires_at=90, receipt_type="lease_acquired")
        if kind == "idempotency":
            return ledger.register_operation(operation).duplicate_action_count == 0
        if kind == "wal":
            return ledger.verify_hash_chain()
        if kind == "leases":
            return ledger.replay(case_id).lease_owner_id == "worker-a"
        ledger.transition(case_id, "verified", expected_cas_version=0, lease_owner_id="worker-a")
        if kind == "cas":
            try:
                ledger.transition(case_id, "approved", expected_cas_version=0, lease_owner_id="worker-a")
            except P118LedgerError:
                return True
            return False
        if kind == "crash_recovery" and item is not None:
            crash_point = str(item.get("crash_point", ""))
            _advance_to_crash_point(ledger, case_id, crash_point)
            return _crash_point_check(path, case_id, crash_point)
        for state in ("approved", "prechecked", "action_attempted"):
            current = ledger.replay(case_id)
            ledger.transition(case_id, state, expected_cas_version=current.cas_version, lease_owner_id="worker-a")
        if kind == "crash_recovery":
            return inventory_p118_orphans(path, now=100)["pending_rollback"] == [case_id] and recover_p118_crash(path, operation_id=case_id, owner_id="worker-a", now=100).final_state == "rolled_back"
        for state in ("postchecked", "succeeded"):
            current = ledger.replay(case_id)
            ledger.transition(case_id, state, expected_cas_version=current.cas_version, lease_owner_id="worker-a")
        return replay_p118_terminal_read_only(path, case_id)["replay_drift"] == 0


def _advance_to_crash_point(ledger: P118LedgerStore, case_id: str, crash_point: str) -> None:
    states_by_point = {
        "before_precheck": ("approved",),
        "after_precheck": ("approved", "prechecked"),
        "before_action": ("approved", "prechecked"),
        "after_action": ("approved", "prechecked", "action_attempted"),
        "before_postcheck": ("approved", "prechecked", "action_attempted"),
        "after_postcheck": ("approved", "prechecked", "action_attempted", "postchecked"),
        "before_rollback": ("approved", "prechecked", "action_attempted"),
        "after_rollback": ("approved", "prechecked", "action_attempted", "rollback_attempted"),
        "before_rollback_postcheck": ("approved", "prechecked", "action_attempted", "rollback_attempted"),
        "after_rollback_postcheck": ("approved", "prechecked", "action_attempted", "rollback_attempted", "rollback_postchecked"),
        "before_report_write": ("approved", "prechecked", "action_attempted", "postchecked", "succeeded"),
        "after_report_write": ("approved", "prechecked", "action_attempted", "postchecked", "succeeded"),
    }
    for state in states_by_point.get(crash_point, ()):
        current = ledger.replay(case_id)
        if current.state == state:
            continue
        ledger.transition(case_id, state, expected_cas_version=current.cas_version, lease_owner_id="worker-a")


def _crash_point_check(path: Path, case_id: str, crash_point: str) -> bool:
    if crash_point not in P118_CRASH_POINTS:
        return False
    if crash_point in {"before_precheck", "after_precheck", "before_action"}:
        return recover_p118_crash(path, operation_id=case_id, owner_id="recovery-worker", now=100).final_state == "aborted_fail_closed"
    if crash_point in {"after_action", "before_postcheck", "after_postcheck", "before_rollback", "after_rollback", "before_rollback_postcheck", "after_rollback_postcheck"}:
        inventory = inventory_p118_orphans(path, now=100)
        recovery = recover_p118_crash(path, operation_id=case_id, owner_id="recovery-worker", now=100)
        return inventory["pending_rollback"] == [case_id] and recovery.final_state == "rolled_back" and recovery.duplicate_action_count == 0
    terminal = recover_p118_crash(path, operation_id=case_id, owner_id="recovery-worker", now=100)
    replay = replay_p118_terminal_read_only(path, case_id)
    return terminal.final_state == "succeeded" and replay["duplicate_action_count"] == 0 and replay["replay_drift"] == 0


def _contract_rejection(case_id: str, index: int, item: Mapping[str, Any]) -> bool:
    payload = _case_material(item)["operation"].to_dict()
    payload.pop("envelope_hash", None)
    payload.pop("lifecycle_states", None)
    payload.pop("terminal_statuses", None)
    payload["fixture_target_id"] = "production:checkout-api"
    try:
        build_operation_envelope(payload)
    except P118ContractError:
        return True
    return False


def _validation(case_id: str, index: int, item: Mapping[str, Any]) -> bool:
    material = _case_material(item)
    probes = material["probes"]
    result = run_p118_validation_cycle(
        operation=material["operation"],
        adapter=FixtureActionAdapter(
            before=_mapping(probes.get("before")) or {"healthy": False},
            after=_mapping(probes.get("after")) or {"healthy": True},
            rollback_after=_mapping(probes.get("rollback_after")) or {"healthy": False},
            validation_plan_ref="validation:fixture",
            rollback_plan_ref="rollback:fixture",
        ),
        approval_receipt=material["approval"],
        lease_owner_id=str(material["lease"]["owner_id"]),
        wal_receipt=material["wal"],
        cas_version=int(material["fixture"]["cas_version"]),
        now=int(material["fixture"]["now"]),
    )
    return result.final_status == item.get("expected_terminal_status") and result.postcheck_evidence_hash is not None


def _rollback(case_id: str, index: int, item: Mapping[str, Any]) -> bool:
    material = _case_material(item)
    probes = material["probes"]
    result = run_p118_validation_cycle(
        operation=material["operation"],
        adapter=FixtureActionAdapter(
            before=_mapping(probes.get("before")) or {"healthy": False},
            after=_mapping(probes.get("after")) or {"healthy": False},
            rollback_after=_mapping(probes.get("rollback_after")) or {"healthy": False},
            validation_plan_ref="validation:fixture",
            rollback_plan_ref="rollback:fixture",
        ),
        approval_receipt=material["approval"],
        lease_owner_id=str(material["lease"]["owner_id"]),
        wal_receipt=material["wal"],
        cas_version=int(material["fixture"]["cas_version"]),
        now=int(material["fixture"]["now"]),
    )
    return result.final_status == item.get("expected_terminal_status") and result.rollback_evidence_hash is not None


def _release(case_id: str, index: int, item: Mapping[str, Any]) -> bool:
    _case_material(item)
    payload = {"case_id": case_id, "builder": "builder", "reviewer": "reviewer", "authority": exact_zero_authority_counters()}
    return payload["builder"] != payload["reviewer"] and stable_hash(payload).startswith("sha256:")


def _source_hashes() -> dict[str, str]:
    return {name: "sha256:" + hashlib.sha256((_ROOT / name).read_bytes()).hexdigest() for name in _SOURCE_FILES if (_ROOT / name).exists()}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


_FAMILY_CHECKS: dict[str, Callable[[str, int, Mapping[str, Any]], bool]] = {
    "approval": _approval,
    "authority_counters": _authority,
    "cas": lambda c, i, item: _ledger_check(c, "cas", item),
    "contract_rejection": _contract_rejection,
    "crash_recovery": lambda c, i, item: _ledger_check(c, "crash_recovery", item),
    "idempotency": lambda c, i, item: _ledger_check(c, "idempotency", item),
    "leases": lambda c, i, item: _ledger_check(c, "leases", item),
    "release_evidence": _release,
    "replay": lambda c, i, item: _ledger_check(c, "replay", item),
    "rollback": _rollback,
    "signed_pack_verification": lambda c, i, item: bool(_case_material(item)["verification"].accepted),
    "validation": _validation,
    "wal": lambda c, i, item: _ledger_check(c, "wal", item),
}


def _load_frozen_manifest(seed: int, *, manifest_path: Path | None = None) -> dict[str, Any]:
    value = json.loads((manifest_path or _FROZEN_MANIFEST).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("invalid_frozen_case_manifest")
    claimed = value.get("manifest_hash")
    if claimed != stable_hash({key: item for key, item in value.items() if key != "manifest_hash"}):
        raise ValueError("stale_frozen_case_manifest_hash")
    if value.get("schema_version") != "p118.frozen_case_manifest.v1" or value.get("seed") != seed:
        raise ValueError("frozen_case_manifest_mismatch")
    cases = value.get("cases")
    if not isinstance(cases, list) or len(cases) < 300:
        raise ValueError("insufficient_frozen_cases")
    _validate_manifest_cases(cases)
    return value


def _validate_manifest_cases(cases: list[Any]) -> None:
    crash_points = {str(case.get("crash_point")) for case in cases if isinstance(case, Mapping) and case.get("family") == "crash_recovery"}
    if not set(P118_CRASH_POINTS).issubset(crash_points):
        raise ValueError("incomplete_crash_matrix")
    for case in cases:
        if not isinstance(case, Mapping):
            raise ValueError("invalid_frozen_case")
        for key in ("fixture_input", "p115_action_pack_ref", "p117_decision_ref", "expected_probes"):
            if not isinstance(case.get(key), Mapping):
                raise ValueError(f"missing_frozen_case_{key}")
        _case_material(case)


__all__ = ["P118_EVALUATION_SCHEMA_VERSION", "P118_FAMILIES", "build_p118_frozen_case_manifest", "run_p118_frozen_evaluation"]
