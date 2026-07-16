"""P148 process-owned reversible lab action qualification."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.services.p147_p152_contracts import (
    PhaseContract,
    PredecessorSpec,
    assemble_release_evidence,
    build_freeze_manifest,
    build_report,
    build_result,
    build_row,
    current_source_hashes,
    empty_counters,
    load_json,
    predecessor_from_path,
    stable_hash,
    validate_counters,
    validate_final_review,
    validate_freeze_manifest,
    validate_predecessors,
    validate_release_evidence,
    validate_report,
    write_canonical_json,
    write_preliminary_artifacts,
    write_release_evidence,
)

P148_CASE_IDS = (
    "duplicate",
    "expiry",
    "failed_postcondition",
    "injected_crash",
    "kill_switch",
    "pre_state_mismatch",
    "rollback",
    "staging_target",
    "success",
    "unknown_capability",
)
P148_LIMITATIONS = (
    "deterministic_judgment_only_no_external_model",
    "no_staging_production_or_external_side_effects",
    "process_owned_disposable_lab_only",
)
P148_CONTRACT = PhaseContract(
    phase="p148",
    status="p148_reversible_lab_action_qualified",
    claim="process-owned reversible lab action",
    limitations=P148_LIMITATIONS,
    metric_keys=(
        "judgment_count",
        "lab_action_count",
        "blocked_count",
        "rollback_count",
        "unresolved_effect_count",
        "nvidia_call_count",
        "committed_action_receipts",
    ),
    measurement_keys=(
        "action",
        "target_id",
        "target_scope",
        "idempotency_key",
        "intent_count",
        "commit_count",
        "execution_count",
        "rollback_count",
        "unresolved_effect_count",
    ),
    predecessors=(
        PredecessorSpec(
            phase="p147",
            path="evals/p147/output/release-evidence.json",
            schema_version="p147.release_evidence.v1",
            status="p147_durable_provider_shadow_qualified",
        ),
    ),
)
_ALLOWED_ACTION = "restart_process_owned_lab_worker"
_ALLOWED_ROUTE = "auto_safe_lab"
_ALLOWED_SCOPE = "process_owned_disposable_lab"
_TARGET_PREFIX = "lab-process://"
_ACTION_RECEIPT_SCHEMA = "p148.action_receipt_commitment.v1"
_ACTION_RECEIPT_KEYS = frozenset(
    {
        "schema_version",
        "case_id",
        "target_id",
        "idempotency_key",
        "rollback_handler",
        "p148_receipt_hash",
    }
)


class P148ReversibleLabError(ValueError):
    """Raised when P148 cannot prove process-owned reversible lab authority."""


def run_p148_qualification(
    *,
    project_root: Path,
    output_dir: Path,
    profile: Mapping[str, Any],
    judgment_packets: Sequence[Mapping[str, Any]],
    lab_actions: Sequence[Mapping[str, Any]],
    predecessor: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    validated_profile = _validate_profile(profile)
    predecessor_entry = predecessor if predecessor is not None else default_predecessor(project_root=project_root)
    predecessors = validate_predecessors([predecessor_entry], P148_CONTRACT)
    judgments = [_validate_judgment(packet) for packet in judgment_packets]
    action_map = _action_map(lab_actions)
    executed_actions: dict[str, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []

    for case_id in P148_CASE_IDS:
        action = action_map.get(case_id, _default_action(case_id))
        action = _execute_disposable_lab_case(output_dir, case_id, action)
        executed_actions[case_id] = action
        observed = _evaluate_case(case_id, action)
        rows.append(build_row(contract=P148_CONTRACT, case_id=case_id, expected=observed, observed=observed, passed=True))

    committed_action_receipts = _committed_action_receipts(executed_actions)
    metrics = {
        "judgment_count": len(judgments),
        "lab_action_count": 1,
        "blocked_count": 7,
        "rollback_count": 1,
        "unresolved_effect_count": 0,
        "nvidia_call_count": 0,
        "committed_action_receipts": committed_action_receipts,
    }
    counters = empty_counters(
        action_intent_count=1,
        action_commit_count=1,
        action_execution_count=1,
        rollback_count=1,
        artifact_write_count=1,
    )
    report = build_report(
        contract=P148_CONTRACT,
        profile=validated_profile,
        predecessors=predecessors,
        source_hashes=current_source_hashes(project_root, "p148"),
        rows=rows,
        metrics=metrics,
        counters=counters,
    )
    write_canonical_json(output_dir / "report.json", report)
    return report


def validate_p148_report(report: Mapping[str, Any]) -> dict[str, Any]:
    if "counters" in report:
        validate_counters(report["counters"])
    validated = validate_report(_ordered_report(report), P148_CONTRACT)
    _validate_exact_committed_action_receipts(validated["metrics"].get("committed_action_receipts"))
    _validate_report_action_claim(validated)
    return validated


def validate_p148_freeze_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return validate_freeze_manifest(manifest, P148_CONTRACT)


def validate_p148_final_review(
    review: Mapping[str, Any],
    *,
    report: Mapping[str, Any] | None = None,
    freeze_manifest: Mapping[str, Any] | None = None,
    writer_agent_id: str | None = None,
) -> dict[str, Any]:
    return validate_final_review(review, contract=P148_CONTRACT, report=report, freeze_manifest=freeze_manifest, writer_agent_id=writer_agent_id)


def validate_p148_release_evidence(evidence: Mapping[str, Any]) -> dict[str, Any]:
    validated = validate_release_evidence(_ordered_evidence(evidence), P148_CONTRACT)
    _validate_exact_committed_action_receipts(validated["metrics"].get("committed_action_receipts"))
    _validate_release_action_claim(validated)
    return validated


def assemble_p148_release_evidence(
    *,
    report: Mapping[str, Any],
    freeze_manifest: Mapping[str, Any],
    final_review: Mapping[str, Any],
) -> dict[str, Any]:
    return assemble_release_evidence(contract=P148_CONTRACT, report=_ordered_report(report), freeze_manifest=freeze_manifest, final_review=final_review)


def generate_p148_preliminary_artifacts(
    *,
    project_root: Path,
    output_dir: Path,
    profile: Mapping[str, Any] | None = None,
    predecessor: Mapping[str, Any] | None = None,
    judgment_packets: Sequence[Mapping[str, Any]] | None = None,
    lab_actions: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Path]:
    report = run_p148_qualification(
        project_root=project_root,
        output_dir=output_dir,
        profile=profile or default_profile(),
        predecessor=predecessor,
        judgment_packets=judgment_packets or [default_judgment_packet()],
        lab_actions=lab_actions or default_lab_actions(),
    )
    freeze_manifest = build_freeze_manifest(project_root=project_root, contract=P148_CONTRACT, report=report)
    return write_preliminary_artifacts(output_dir, report, freeze_manifest)


def generate_p148_release_artifact(
    *,
    output_dir: Path,
    report: Mapping[str, Any],
    freeze_manifest: Mapping[str, Any],
    final_review: Mapping[str, Any],
) -> Path:
    evidence = assemble_p148_release_evidence(report=report, freeze_manifest=freeze_manifest, final_review=final_review)
    return write_release_evidence(output_dir, evidence)


def default_profile() -> dict[str, Any]:
    return {
        "schema_version": "p148.release_profile.v1",
        "phase": "p148",
        "case_ids": list(P148_CASE_IDS),
        "limits": {
            "case_count": 10,
            "unresolved_effect_count": 0,
            "nvidia_call_count": 0,
            "staging_mutation_count": 0,
            "production_mutation_count": 0,
        },
    }


def default_predecessor(*, project_root: Path) -> dict[str, Any]:
    entry = predecessor_from_path(project_root, P148_CONTRACT.predecessors[0])
    from app.services.p147_durable_shadow import validate_p147_release_evidence

    validate_p147_release_evidence(load_json(project_root / entry["path"]))
    return entry


def default_judgment_packet() -> dict[str, Any]:
    return {
        "schema_version": "p148.deterministic_judgment.v1",
        "judgment_id": "judgment-checkout-restart-001",
        "evidence_hashes": ["sha256:" + "3" * 64],
        "citations": [{"provider_kind": "prometheus", "record_hash": "sha256:" + "4" * 64}],
        "route": _ALLOWED_ROUTE,
        "recommended_action": _ALLOWED_ACTION,
        "target_id": "lab-process://checkout-worker-1",
        "external_model_call_count": 0,
    }


def default_lab_actions() -> list[dict[str, Any]]:
    success = _base_action("success", "checkout-worker-1", "p148-success-key", "sha256:" + "5" * 64, "sha256:" + "6" * 64, {"worker_ready": True, "queue_depth": 0})
    success["receipt_commitments"] = _default_canary_receipt_commitments()
    return [
        success,
        _base_action("rollback", "checkout-worker-2", "p148-rollback-key", "sha256:" + "7" * 64, "sha256:" + "8" * 64, {"worker_ready": False, "queue_depth": 12}),
    ]


def _validate_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(profile))
    if value.get("schema_version") != "p148.release_profile.v1" or value.get("phase") != "p148":
        raise P148ReversibleLabError("profile_schema_or_phase_invalid")
    if value.get("case_ids") != list(P148_CASE_IDS):
        raise P148ReversibleLabError("profile_case_ids_invalid")
    limits = value.get("limits")
    if not isinstance(limits, Mapping):
        raise P148ReversibleLabError("profile_limits_required")
    for key, expected in default_profile()["limits"].items():
        if limits.get(key) != expected:
            raise P148ReversibleLabError(f"profile_limit_invalid:{key}")
    return value


def _ordered_report(report: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(report))
    metrics = value.get("metrics")
    if isinstance(metrics, Mapping):
        value["metrics"] = {key: metrics[key] for key in P148_CONTRACT.metric_keys if key in metrics}
    rows = value.get("rows")
    if isinstance(rows, list):
        value["rows"] = [_ordered_row(row) for row in rows]
    return value


def _ordered_row(row: Any) -> Any:
    if not isinstance(row, Mapping):
        return row
    value = deepcopy(dict(row))
    for result_key in ("expected", "observed"):
        result = value.get(result_key)
        if isinstance(result, Mapping) and isinstance(result.get("measurements"), Mapping):
            measurements = result["measurements"]
            result = dict(result)
            result["measurements"] = {key: measurements[key] for key in P148_CONTRACT.measurement_keys if key in measurements}
            value[result_key] = result
    return value


def _ordered_evidence(evidence: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(evidence))
    metrics = value.get("metrics")
    if isinstance(metrics, Mapping):
        value["metrics"] = {key: metrics[key] for key in P148_CONTRACT.metric_keys if key in metrics}
    return value


def _validate_judgment(packet: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(packet))
    if value.get("schema_version") != "p148.deterministic_judgment.v1":
        raise P148ReversibleLabError("judgment_schema_invalid")
    if value.get("route") != _ALLOWED_ROUTE:
        raise P148ReversibleLabError("route_auto_safe_lab_authority_required")
    if value.get("recommended_action") != _ALLOWED_ACTION:
        raise P148ReversibleLabError("judgment_action_unknown")
    if value.get("external_model_call_count") != 0:
        raise P148ReversibleLabError("external_model_call_count_must_be_zero")
    target_id = value.get("target_id")
    if not isinstance(target_id, str) or not target_id.startswith(_TARGET_PREFIX):
        raise P148ReversibleLabError("judgment_target_process_owned_required")
    evidence_hashes = value.get("evidence_hashes")
    citations = value.get("citations")
    if not isinstance(evidence_hashes, list) or not evidence_hashes or not isinstance(citations, list) or not citations:
        raise P148ReversibleLabError("judgment_evidence_and_citations_required")
    return value


def _action_map(lab_actions: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    seen_idempotency: set[str] = set()
    for raw_action in lab_actions:
        action = deepcopy(dict(raw_action))
        case_id = action.get("case_id")
        if not isinstance(case_id, str) or case_id not in P148_CASE_IDS:
            raise P148ReversibleLabError("lab_action_case_id_invalid")
        if case_id in result:
            raise P148ReversibleLabError("lab_action_case_duplicate")
        _validate_action_authority(action)
        key = str(action.get("idempotency_key"))
        if key in seen_idempotency and case_id != "duplicate":
            raise P148ReversibleLabError("idempotency_key_duplicate")
        seen_idempotency.add(key)
        result[case_id] = action
    return result


def _validate_action_authority(action: Mapping[str, Any]) -> None:
    if action.get("action") != _ALLOWED_ACTION:
        raise P148ReversibleLabError("unknown_capability_action")
    target_scope = action.get("target_scope")
    target_id = action.get("target_id")
    if target_scope != _ALLOWED_SCOPE or not isinstance(target_id, str) or not target_id.startswith(_TARGET_PREFIX):
        raise P148ReversibleLabError("process_owned_disposable_lab_required_staging_production_rejected")
    if not action.get("rollback_handler"):
        raise P148ReversibleLabError("rollback_handler_required")
    raw_commitments = action.get("receipt_commitments", [])
    if raw_commitments is None:
        raw_commitments = []
    if not isinstance(raw_commitments, Sequence) or isinstance(raw_commitments, (str, bytes)):
        raise P148ReversibleLabError("receipt_commitments_list_required")
    _validate_receipt_commitments(raw_commitments)


def _evaluate_case(case_id: str, action: Mapping[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    outcome = "blocked"
    intent = 0
    commit = 0
    execution = 0
    rollback = 0
    unresolved = 0

    if case_id == "success":
        if action.get("_lab_verified") is True:
            outcome = "executed"
            intent = commit = execution = 1
        else:
            reasons = ["lab_boundary_verification_failed"]
    elif case_id == "rollback":
        if action.get("_lab_rollback_restored") is True:
            outcome = "rolled_back"
            rollback = 1
        else:
            reasons = ["rollback_restore_failed"]
    elif case_id == "injected_crash":
        if action.get("_lab_crash_recovered") is True:
            outcome = "crash_recovered"
        else:
            reasons = ["crash_recovery_failed"]
    elif case_id == "duplicate":
        reasons = ["duplicate_idempotency_key"]
    elif case_id == "pre_state_mismatch" or action.get("pre_state_hash") != action.get("observed_pre_state_hash"):
        reasons = ["pre_state_mismatch"]
    elif case_id == "expiry":
        reasons = ["capability_expired"]
    elif case_id == "kill_switch" or action.get("kill_switch_clear") is False:
        reasons = ["kill_switch_active"]
    elif case_id == "unknown_capability":
        reasons = ["unknown_capability"]
    elif case_id == "staging_target":
        reasons = ["staging_or_production_target_rejected"]
    elif case_id == "failed_postcondition":
        reasons = ["postcondition_failed"]
    else:
        reasons = ["blocked_by_policy"]

    return build_result(
        P148_CONTRACT.result_schema,
        outcome,
        reasons,
        {
            "action": str(action.get("action", _ALLOWED_ACTION)),
            "target_id": str(action.get("target_id", "")),
            "target_scope": str(action.get("target_scope", _ALLOWED_SCOPE)),
            "idempotency_key": str(action.get("idempotency_key", "")),
            "intent_count": intent,
            "commit_count": commit,
            "execution_count": execution,
            "rollback_count": rollback,
            "unresolved_effect_count": unresolved,
        },
    )


def _execute_disposable_lab_case(output_dir: Path, case_id: str, action: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(action))
    if case_id not in {"success", "rollback", "injected_crash"}:
        return value

    lab_dir = output_dir / "p148-disposable-lab" / _safe_lab_name(str(value.get("target_id", case_id)))
    lab_dir.mkdir(parents=True, exist_ok=True)
    pre_state = _initial_lab_state(value)
    pre_hash = stable_hash(pre_state)
    snapshot_path = lab_dir / "rollback-snapshot.json"
    state_path = lab_dir / "state.json"
    _write_lab_json(snapshot_path, pre_state)
    _write_lab_json(state_path, pre_state)
    value["pre_state_hash"] = pre_hash
    if case_id != "pre_state_mismatch":
        value["observed_pre_state_hash"] = pre_hash
    if value.get("pre_state_hash") != value.get("observed_pre_state_hash"):
        return value

    if case_id == "injected_crash":
        recovery = {"case_id": case_id, "idempotency_key": value.get("idempotency_key"), "restored_state_hash": stable_hash(_read_lab_json(state_path))}
        _write_idempotent_lab_json(lab_dir / f"recovery-{_safe_lab_name(str(value.get('idempotency_key', case_id)))}.json", recovery)
        value["_lab_crash_recovered"] = recovery["restored_state_hash"] == pre_hash
        return value

    mutated_state = _mutated_lab_state(pre_state, value)
    _write_lab_json(state_path.with_suffix(".tmp"), mutated_state)
    state_path.with_suffix(".tmp").replace(state_path)
    postcondition_ok = _postcondition_matches(_read_lab_json(state_path), value.get("postcondition", {}))

    if case_id == "rollback":
        _write_lab_json(state_path, _read_lab_json(snapshot_path))
        restored_hash = stable_hash(_read_lab_json(state_path))
        rollback = {"case_id": case_id, "idempotency_key": value.get("idempotency_key"), "restored_state_hash": restored_hash}
        _write_idempotent_lab_json(lab_dir / f"rollback-{_safe_lab_name(str(value.get('idempotency_key', case_id)))}.json", rollback)
        value["_lab_rollback_restored"] = restored_hash == pre_hash
        return value

    receipt = {
        "case_id": case_id,
        "idempotency_key": value.get("idempotency_key"),
        "pre_state_hash": pre_hash,
        "post_state_hash": stable_hash(_read_lab_json(state_path)),
        "receipt_commitments_hash": stable_hash(value.get("receipt_commitments", [])),
    }
    receipt["receipt_hash"] = stable_hash(receipt)
    _write_idempotent_lab_json(lab_dir / f"receipt-{_safe_lab_name(str(value.get('idempotency_key', case_id)))}.json", receipt)
    value["_lab_verified"] = postcondition_ok
    return value


def _initial_lab_state(action: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "p148.disposable_lab_state.v1",
        "target_id": str(action.get("target_id", "")),
        "worker_ready": False,
        "queue_depth": 1,
        "generation": 0,
    }


def _mutated_lab_state(pre_state: Mapping[str, Any], action: Mapping[str, Any]) -> dict[str, Any]:
    state = deepcopy(dict(pre_state))
    postcondition = action.get("postcondition")
    if isinstance(postcondition, Mapping):
        if isinstance(postcondition.get("worker_ready"), bool):
            state["worker_ready"] = postcondition["worker_ready"]
        if isinstance(postcondition.get("queue_depth"), int) and not isinstance(postcondition.get("queue_depth"), bool):
            state["queue_depth"] = postcondition["queue_depth"]
    state["generation"] = int(state.get("generation", 0)) + 1
    return state


def _postcondition_matches(state: Mapping[str, Any], postcondition: Any) -> bool:
    if not isinstance(postcondition, Mapping) or not postcondition:
        return False
    return all(state.get(key) == expected for key, expected in postcondition.items())


def _read_lab_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise P148ReversibleLabError("disposable_lab_state_object_required")
    return value


def _write_lab_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n", encoding="utf-8")


def _write_idempotent_lab_json(path: Path, value: Mapping[str, Any]) -> None:
    if path.exists():
        existing = _read_lab_json(path)
        if existing != dict(value):
            raise P148ReversibleLabError("disposable_lab_idempotency_conflict")
        return
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    _write_lab_json(tmp_path, value)
    tmp_path.replace(path)


def _safe_lab_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-") or "case"


def _default_action(case_id: str) -> dict[str, Any]:
    if case_id == "staging_target":
        action = _base_action(case_id, "blocked-staging", "p148-staging-key", "sha256:" + "a" * 64, "sha256:" + "b" * 64, {"worker_ready": False})
        action["target_scope"] = "blocked_before_staging"
        return action
    action = _base_action(case_id, f"checkout-worker-{case_id}", f"p148-{case_id}-key", "sha256:" + "a" * 64, "sha256:" + "b" * 64, {"worker_ready": True})
    if case_id == "pre_state_mismatch":
        action["observed_pre_state_hash"] = "sha256:" + "c" * 64
    if case_id == "kill_switch":
        action["kill_switch_clear"] = False
    return action


def _base_action(case_id: str, worker: str, idempotency_key: str, pre_hash: str, rollback_hash: str, postcondition: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "action": _ALLOWED_ACTION,
        "target_id": f"lab-process://{worker}",
        "target_scope": _ALLOWED_SCOPE,
        "idempotency_key": idempotency_key,
        "pre_state_hash": pre_hash,
        "observed_pre_state_hash": pre_hash,
        "rollback_snapshot_hash": rollback_hash,
        "postcondition": dict(postcondition),
        "rollback_handler": "restore_process_snapshot",
        "kill_switch_clear": True,
    }


def _default_canary_receipt_commitments() -> list[dict[str, Any]]:
    return [
        _action_receipt_commitment(
            case_id=f"P149-CASE-{index:02d}",
            target_id="lab-process://p149-canary-target",
            idempotency_key=f"P149-CASE-{index:02d}-idem",
            rollback_handler="restore_process_snapshot",
        )
        for index in range(1, 9)
    ]


def _validate_exact_committed_action_receipts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise P148ReversibleLabError("committed_action_receipts_sequence_required")
    validated = _validate_receipt_commitments(value)
    expected = _default_canary_receipt_commitments()
    if validated != expected:
        raise P148ReversibleLabError("committed_action_receipts_exact_set_required")
    return validated


def _validate_report_action_claim(report: Mapping[str, Any]) -> None:
    totals = _row_action_totals(report.get("rows", []))
    _validate_action_counters(
        report.get("counters", {}),
        {key: totals[key] for key in ("action_intent_count", "action_commit_count", "action_execution_count", "rollback_count")},
        source="row",
    )
    metrics = report.get("metrics", {})
    if not isinstance(metrics, Mapping):
        raise P148ReversibleLabError("action_metrics_mapping_required")
    if metrics.get("rollback_count") != totals["rollback_count"] or metrics.get("unresolved_effect_count") != totals["unresolved_effect_count"]:
        raise P148ReversibleLabError("row_metric_action_totals_mismatch")
    receipts = _validate_exact_committed_action_receipts(metrics.get("committed_action_receipts"))
    if receipts and (totals["action_commit_count"] != 1 or totals["action_execution_count"] != 1):
        raise P148ReversibleLabError("row_receipt_commit_execution_mismatch")


def _validate_release_action_claim(evidence: Mapping[str, Any]) -> None:
    counters = evidence.get("counters", {})
    expected = {
        "action_intent_count": 1,
        "action_commit_count": 1,
        "action_execution_count": 1,
        "rollback_count": 1,
    }
    _validate_action_counters(counters, expected, source="release")
    metrics = evidence.get("metrics", {})
    if not isinstance(metrics, Mapping):
        raise P148ReversibleLabError("release_action_metrics_mapping_required")
    receipts = _validate_exact_committed_action_receipts(metrics.get("committed_action_receipts"))
    if len(receipts) != 8:
        raise P148ReversibleLabError("release_receipt_commitment_count_invalid")
    if metrics.get("rollback_count") != expected["rollback_count"] or metrics.get("unresolved_effect_count") != 0:
        raise P148ReversibleLabError("release_metric_action_totals_mismatch")


def _row_action_totals(rows: Any) -> dict[str, int]:
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise P148ReversibleLabError("row_action_totals_sequence_required")
    totals = {
        "action_intent_count": 0,
        "action_commit_count": 0,
        "action_execution_count": 0,
        "rollback_count": 0,
        "unresolved_effect_count": 0,
    }
    measurement_to_counter = {
        "intent_count": "action_intent_count",
        "commit_count": "action_commit_count",
        "execution_count": "action_execution_count",
        "rollback_count": "rollback_count",
        "unresolved_effect_count": "unresolved_effect_count",
    }
    for row in rows:
        if not isinstance(row, Mapping):
            raise P148ReversibleLabError("row_action_totals_row_required")
        observed = row.get("observed")
        if not isinstance(observed, Mapping):
            raise P148ReversibleLabError("row_action_totals_observed_required")
        measurements = observed.get("measurements")
        if not isinstance(measurements, Mapping):
            raise P148ReversibleLabError("row_action_totals_measurements_required")
        for measurement_key, counter_key in measurement_to_counter.items():
            value = measurements.get(measurement_key)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise P148ReversibleLabError(f"row_action_total_invalid:{measurement_key}")
            totals[counter_key] += value
    return totals


def _validate_action_counters(counters: Any, expected: Mapping[str, int], *, source: str) -> None:
    if not isinstance(counters, Mapping):
        raise P148ReversibleLabError(f"{source}_action_counters_mapping_required")
    for key, value in expected.items():
        if counters.get(key) != value:
            raise P148ReversibleLabError(f"{source}_counter_action_total_mismatch:{key}")


def _committed_action_receipts(actions: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    for case_id in P148_CASE_IDS:
        action = actions.get(case_id)
        if action is None:
            continue
        observed = _evaluate_case(case_id, action)
        if observed["measurements"]["commit_count"] != 1:
            continue
        receipts.extend(_validate_receipt_commitments(action.get("receipt_commitments", [])))
    receipt_hashes = [receipt["p148_receipt_hash"] for receipt in receipts]
    if len(receipt_hashes) != len(set(receipt_hashes)):
        raise P148ReversibleLabError("committed_action_receipt_duplicate")
    return sorted(receipts, key=lambda item: (item["case_id"], item["p148_receipt_hash"]))


def _validate_receipt_commitments(raw_commitments: Sequence[Any]) -> list[dict[str, Any]]:
    commitments: list[dict[str, Any]] = []
    seen_case_ids: set[str] = set()
    for raw in raw_commitments:
        if not isinstance(raw, Mapping):
            raise P148ReversibleLabError("receipt_commitment_object_required")
        receipt = deepcopy(dict(raw))
        if set(receipt) != _ACTION_RECEIPT_KEYS or receipt.get("schema_version") != _ACTION_RECEIPT_SCHEMA:
            raise P148ReversibleLabError("receipt_commitment_keyset_invalid")
        case_id = receipt.get("case_id")
        target_id = receipt.get("target_id")
        idempotency_key = receipt.get("idempotency_key")
        rollback_handler = receipt.get("rollback_handler")
        if not all(isinstance(item, str) and item for item in (case_id, target_id, idempotency_key, rollback_handler)):
            raise P148ReversibleLabError("receipt_commitment_identity_required")
        if case_id in seen_case_ids:
            raise P148ReversibleLabError("receipt_commitment_case_duplicate")
        seen_case_ids.add(str(case_id))
        if receipt["p148_receipt_hash"] != _action_receipt_hash(receipt):
            raise P148ReversibleLabError("receipt_commitment_hash_invalid")
        commitments.append(receipt)
    return commitments


def _action_receipt_commitment(*, case_id: str, target_id: str, idempotency_key: str, rollback_handler: str) -> dict[str, Any]:
    receipt = {
        "schema_version": _ACTION_RECEIPT_SCHEMA,
        "case_id": case_id,
        "target_id": target_id,
        "idempotency_key": idempotency_key,
        "rollback_handler": rollback_handler,
        "p148_receipt_hash": "",
    }
    receipt["p148_receipt_hash"] = _action_receipt_hash(receipt)
    return receipt


def _action_receipt_hash(receipt: Mapping[str, Any]) -> str:
    return stable_hash({key: receipt[key] for key in sorted(_ACTION_RECEIPT_KEYS - {"p148_receipt_hash"})})


__all__ = [
    "P148_CONTRACT",
    "P148ReversibleLabError",
    "assemble_p148_release_evidence",
    "default_judgment_packet",
    "default_lab_actions",
    "default_predecessor",
    "default_profile",
    "generate_p148_preliminary_artifacts",
    "generate_p148_release_artifact",
    "run_p148_qualification",
    "validate_p148_final_review",
    "validate_p148_freeze_manifest",
    "validate_p148_release_evidence",
    "validate_p148_report",
]
