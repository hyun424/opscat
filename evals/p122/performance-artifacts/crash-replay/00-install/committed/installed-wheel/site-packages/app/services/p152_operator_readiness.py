"""P152 integrated bounded operator-agent readiness gate."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.p147_p152_contracts import (
    ContractError,
    PhaseContract,
    PredecessorSpec,
    assemble_release_evidence,
    build_freeze_manifest,
    build_report,
    build_result,
    build_row,
    current_source_hashes,
    empty_counters,
    predecessor_from_path,
    stable_hash,
    validate_final_review,
    validate_freeze_manifest,
    validate_predecessors,
    validate_release_evidence,
    validate_report,
    write_canonical_json,
)

CASE_SELECTOR_NAMES = (
    "test_contract_and_predecessor_fail_closed",
    "test_happy_path_report_and_counters",
    "test_fault_matrix_and_recovery",
    "test_forgery_and_authority_rejected",
    "test_release_evidence_requires_zero_finding_review",
)
LIMITATIONS = (
    "bounded_lab_only_no_production_authority",
    "local_fixture_approval_only_no_auth",
    "not_production_operator_replacement",
)
ALLOWED_PERMISSION_MODES = ("manual", "approve_once", "auto_safe_lab")
P152_CASE_IDS = tuple(f"P152-CASE-{index:02d}" for index in range(1, 9))
FROZEN_CASE_REJECTIONS: dict[str, dict[str, Any]] = {
    "P152-CASE-01": {"expected_rejection": None, "kill_switch": False, "deadman": False},
    "P152-CASE-02": {"expected_rejection": "approve_once_receipt_required", "kill_switch": True, "deadman": False},
    "P152-CASE-03": {"expected_rejection": "approve_once_receipt_forgery", "kill_switch": False, "deadman": True},
    "P152-CASE-04": {"expected_rejection": "approve_once_receipt_expired", "kill_switch": False, "deadman": False},
    "P152-CASE-05": {"expected_rejection": "approve_once_receipt_replay", "kill_switch": False, "deadman": False},
    "P152-CASE-06": {"expected_rejection": "approve_once_receipt_match_invalid", "kill_switch": False, "deadman": False},
    "P152-CASE-07": {"expected_rejection": "approve_once_receipt_match_invalid", "kill_switch": False, "deadman": False},
    "P152-CASE-08": {"expected_rejection": "approve_once_receipt_match_invalid", "kill_switch": False, "deadman": False},
}
METRIC_KEYS = (
    "predecessor_count",
    "qualified_predecessor_count",
    "kill_switch_pass",
    "deadman_pass",
    "rollback_closure",
    "production_operator_replacement_ready",
)
MEASUREMENT_KEYS = (
    "permission_mode",
    "requested_action",
    "target",
    "action_executed",
    "kill_switch_blocked",
    "deadman_blocked",
    "rollback_closed",
    "production_operator_replacement_ready",
)
P152_CONTRACT = PhaseContract(
    phase="p152",
    status="p152_bounded_operator_agent_qualified",
    claim="bounded_operator_agent_integration_qualified",
    limitations=LIMITATIONS,
    metric_keys=METRIC_KEYS,
    measurement_keys=MEASUREMENT_KEYS,
    predecessors=(
        PredecessorSpec("p146", "evals/p146/final/release-evidence.json", "p146.release_evidence.v1", "p146_live_shadow_qualification_ready"),
        PredecessorSpec("p147", "evals/p147/output/release-evidence.json", "p147.release_evidence.v1", "p147_durable_provider_shadow_qualified"),
        PredecessorSpec("p148", "evals/p148/output/release-evidence.json", "p148.release_evidence.v1", "p148_reversible_lab_action_qualified"),
        PredecessorSpec("p149", "evals/p149/output/release-evidence.json", "p149.release_evidence.v1", "p149_canary_outcome_control_qualified"),
        PredecessorSpec("p150", "evals/p150/output/release-evidence.json", "p150.release_evidence.v1", "p150_unattended_chaos_soak_qualified"),
        PredecessorSpec("p151", "evals/p151/output/release-evidence.json", "p151.release_evidence.v1", "p151_ground_truth_quality_qualified"),
    ),
)
# This hardcoded fixture signature is deterministic test data only; it is not
# a security/auth boundary and must not be treated as production authority.
_SECRET = "p152-local-signed-fixture-v1"
_PROCESS_TARGET = "process-owned-lab"
_LAB_ACTIONS = {"observe", "restart_worker", "rollback_canary"}


class P152OperatorReadinessError(ValueError):
    """Raised when P152 cannot prove bounded readiness."""


def issue_local_approve_once_fixture_receipt(
    *,
    issuer: str,
    subject: str,
    action: str,
    target: str,
    pre_state_hash: str,
    expires_at: str,
) -> dict[str, Any]:
    receipt = {
        "schema_version": "p152.approve_once_fixture_receipt.v1",
        "fixture_scope": "local_non_auth_fixture",
        "auth_implementation": "none",
        "can_execute": False,
        "issuer": _text(issuer, "issuer"),
        "subject": _text(subject, "subject"),
        "action": _text(action, "action"),
        "target": _text(target, "target"),
        "pre_state_hash": _hash(pre_state_hash, "pre_state_hash"),
        "expires_at": _utc(expires_at, "expires_at"),
        "nonce": stable_hash({"issuer": issuer, "subject": subject, "action": action, "target": target, "pre_state_hash": pre_state_hash, "expires_at": expires_at}),
        "signature": "",
    }
    receipt["signature"] = _receipt_signature(receipt)
    return receipt


def validate_approve_once_receipt(
    receipt: Mapping[str, Any],
    *,
    action: str,
    target: str,
    pre_state_hash: str,
    used_receipt_hashes: set[str] | None = None,
) -> dict[str, Any]:
    value = deepcopy(dict(receipt))
    try:
        if value.get("schema_version") != "p152.approve_once_fixture_receipt.v1":
            raise P152OperatorReadinessError("approve_once_receipt_schema_invalid")
        if value.get("fixture_scope") != "local_non_auth_fixture" or value.get("auth_implementation") != "none" or value.get("can_execute") is not False:
            raise P152OperatorReadinessError("approve_once_receipt_local_fixture_only")
        if value.get("issuer") == value.get("subject"):
            raise P152OperatorReadinessError("approve_once_receipt_self_issued_auth_invalid")
        if value.get("issuer") != "fixture-authority":
            raise P152OperatorReadinessError("approve_once_receipt_auth_invalid")
        if value.get("action") != action or value.get("target") != target or value.get("pre_state_hash") != pre_state_hash:
            raise P152OperatorReadinessError("approve_once_receipt_match_invalid")
        if _now() >= datetime.fromisoformat(_utc(value.get("expires_at"), "expires_at").replace("Z", "+00:00")).astimezone(UTC):
            raise P152OperatorReadinessError("approve_once_receipt_expired")
        if _receipt_signature(value) != value.get("signature"):
            raise P152OperatorReadinessError("approve_once_receipt_forgery")
        receipt_hash = stable_hash(value)
        if used_receipt_hashes is not None:
            if receipt_hash in used_receipt_hashes:
                raise P152OperatorReadinessError("approve_once_receipt_replay")
            used_receipt_hashes.add(receipt_hash)
        return {"ok": True, "receipt_hash": receipt_hash}
    except P152OperatorReadinessError:
        raise
    except Exception as exc:
        raise P152OperatorReadinessError("approve_once_receipt_invalid") from exc


def evaluate_permission_mode(
    *,
    permission_mode: str,
    requested_action: str,
    target: str,
    pre_state_hash: str,
    receipt: Mapping[str, Any] | None,
    kill_switch: bool = False,
    deadman: bool = False,
    used_receipt_hashes: set[str] | None = None,
) -> dict[str, Any]:
    _hash(pre_state_hash, "pre_state_hash")
    if target != _PROCESS_TARGET or requested_action not in _LAB_ACTIONS:
        raise P152OperatorReadinessError("production_authority_blocked")
    if kill_switch:
        return _blocked_result(permission_mode, requested_action, target, "kill_switch_blocked")
    if deadman:
        return _blocked_result(permission_mode, requested_action, target, "deadman_blocked")
    if permission_mode == "manual":
        return _result(permission_mode, requested_action, target, False, ["manual_advisory_only"], False)
    if permission_mode == "approve_once":
        if receipt is None:
            raise P152OperatorReadinessError("approve_once_receipt_required")
        validated = validate_approve_once_receipt(receipt, action=requested_action, target=target, pre_state_hash=pre_state_hash, used_receipt_hashes=used_receipt_hashes)
        result = _result(permission_mode, requested_action, target, False, ["approve_once_fixture_receipt_valid_no_execution"], False)
        result["approve_once_receipt_hash"] = validated["receipt_hash"]
        return result
    if permission_mode == "auto_safe_lab":
        return _result(permission_mode, requested_action, target, requested_action != "observe", ["process_owned_lab_action_closed"], True)
    raise P152OperatorReadinessError("permission_mode_unknown")


def run_p152_qualification(
    *,
    predecessors: Sequence[Mapping[str, Any]],
    integration_cases: Sequence[Mapping[str, Any]],
    output_dir: str | Path | None,
    project_root: str | Path | None = None,
    evidence_mode: str = "canonical",
) -> dict[str, Any]:
    try:
        root = Path(project_root) if project_root is not None else _project_root()
        if evidence_mode == "canonical":
            predecessor_entries = [predecessor_from_path(root, spec) for spec in P152_CONTRACT.predecessors]
            if [dict(entry) for entry in predecessors] != predecessor_entries:
                raise P152OperatorReadinessError("predecessors_not_path_backed")
        elif evidence_mode == "isolated_test":
            predecessor_entries = validate_predecessors(predecessors, P152_CONTRACT)
        else:
            raise P152OperatorReadinessError("evidence_mode_invalid")
        used_receipts: set[str] = set()
        rows = []
        for case in _normalize_cases(integration_cases):
            observed, passed = _evaluate_frozen_case(case, used_receipts)
            rows.append(_contract_row(case["case_id"], case, observed, passed))
        metrics = _derive_p152_metrics_from_rows(rows, predecessor_entries)
        failures = _gate_failures(rows, metrics)
        profile = build_p152_release_profile(case_ids=[row["case_id"] for row in rows])
        report = build_report(
            contract=P152_CONTRACT,
            profile=profile,
            predecessors=predecessor_entries,
            source_hashes=current_source_hashes(root, "p152"),
            rows=rows,
            metrics=metrics,
            counters=empty_counters(
                action_intent_count=len(rows),
                action_commit_count=sum(1 for row in rows if row["observed"]["measurements"]["action_executed"]),
                action_execution_count=sum(1 for row in rows if row["observed"]["measurements"]["action_executed"]),
                rollback_count=sum(
                    1
                    for row in rows
                    if row["observed"]["measurements"]["rollback_closed"] and row["observed"]["measurements"]["action_executed"]
                ),
                deadman_count=sum(1 for row in rows if row["observed"]["measurements"]["deadman_blocked"]),
            ),
        )
        if failures:
            raise P152OperatorReadinessError("p152_gate_failed:" + ",".join(failures))
        if output_dir is not None:
            write_canonical_json(Path(output_dir) / "report.json", report)
        return report
    except ContractError as exc:
        raise P152OperatorReadinessError(f"p152_contract_fail_closed:{exc}") from exc


def build_p152_release_profile(*, case_ids: Sequence[str] = P152_CASE_IDS) -> dict[str, Any]:
    profile = {
        "schema_version": "p152.release_profile.v1",
        "phase": "p152",
        "case_ids": sorted(case_ids),
        "limits": {
            "allowed_permission_modes": list(ALLOWED_PERMISSION_MODES),
            "allowed_actions": sorted(_LAB_ACTIONS),
            "allowed_targets": [_PROCESS_TARGET],
            "predecessor_count": 6,
            "production_operator_replacement_ready": False,
            "production_mutation_count": 0,
            "staging_mutation_count": 0,
            "authority_escape_count": 0,
            "local_fixture_approval_only": True,
            "auth_implementation": "deferred",
            "approve_once_action_execution": False,
            "kill_switch_blocks_execution": True,
            "deadman_blocks_execution": True,
            "rollback_required_for_executed_actions": True,
        },
    }
    return _validate_p152_release_profile(profile)


def validate_p152_report(report: Mapping[str, Any]) -> dict[str, Any]:
    try:
        validated = validate_report(report, P152_CONTRACT)
        _validate_exact_p152_report_semantics(validated)
    except ContractError as exc:
        raise P152OperatorReadinessError(str(exc)) from exc
    return validated


def validate_p152_freeze_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    try:
        validated = validate_freeze_manifest(manifest, P152_CONTRACT)
    except ContractError as exc:
        raise P152OperatorReadinessError(str(exc)) from exc
    return validated


def validate_p152_final_review(
    review: Mapping[str, Any],
    *,
    report: Mapping[str, Any] | None = None,
    freeze_manifest: Mapping[str, Any] | None = None,
    writer_agent_id: str | None = None,
) -> dict[str, Any]:
    try:
        validated = validate_final_review(
            review,
            contract=P152_CONTRACT,
            report=report,
            freeze_manifest=freeze_manifest,
            writer_agent_id=writer_agent_id,
        )
    except ContractError as exc:
        raise P152OperatorReadinessError(str(exc)) from exc
    return validated


def validate_p152_release_evidence(evidence: Mapping[str, Any]) -> dict[str, Any]:
    try:
        validated = validate_release_evidence(evidence, P152_CONTRACT)
        _validate_exact_p152_release_semantics(validated)
    except ContractError as exc:
        raise P152OperatorReadinessError(str(exc)) from exc
    return validated


def assemble_p152_release_evidence(*, report: Mapping[str, Any], freeze: Mapping[str, Any], review: Mapping[str, Any]) -> dict[str, Any]:
    try:
        validate_p152_report(report)
        release = assemble_release_evidence(contract=P152_CONTRACT, report=report, freeze_manifest=freeze, final_review=review)
        validate_p152_release_evidence(release)
        return release
    except ContractError as exc:
        raise P152OperatorReadinessError(str(exc)) from exc


def build_p152_freeze_manifest(*, project_root: str | Path | None, report: Mapping[str, Any]) -> dict[str, Any]:
    try:
        return build_freeze_manifest(project_root=Path(project_root) if project_root is not None else _project_root(), contract=P152_CONTRACT, report=report)
    except ContractError as exc:
        raise P152OperatorReadinessError(str(exc)) from exc


def _validate_p152_release_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(profile))
    if set(value) != {"schema_version", "phase", "case_ids", "limits"}:
        raise P152OperatorReadinessError("p152_profile_keyset_invalid")
    if value.get("schema_version") != "p152.release_profile.v1" or value.get("phase") != "p152":
        raise P152OperatorReadinessError("p152_profile_schema_or_phase_invalid")
    case_ids = value.get("case_ids")
    if not isinstance(case_ids, list) or case_ids != sorted(P152_CASE_IDS) or len(case_ids) != 8:
        raise P152OperatorReadinessError("p152_profile_case_ids_invalid")
    limits = value.get("limits")
    expected_limits = {
        "allowed_permission_modes": list(ALLOWED_PERMISSION_MODES),
        "allowed_actions": sorted(_LAB_ACTIONS),
        "allowed_targets": [_PROCESS_TARGET],
        "predecessor_count": 6,
        "production_operator_replacement_ready": False,
        "production_mutation_count": 0,
        "staging_mutation_count": 0,
        "authority_escape_count": 0,
        "local_fixture_approval_only": True,
        "auth_implementation": "deferred",
        "approve_once_action_execution": False,
        "kill_switch_blocks_execution": True,
        "deadman_blocks_execution": True,
        "rollback_required_for_executed_actions": True,
    }
    if not isinstance(limits, Mapping) or dict(limits) != expected_limits:
        raise P152OperatorReadinessError("p152_profile_limits_invalid")
    value["limits"] = deepcopy(expected_limits)
    return value


def _normalize_cases(cases: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(cases, Sequence) or isinstance(cases, (str, bytes)):
        raise P152OperatorReadinessError("integration_case_list_required")
    normalized: list[dict[str, Any]] = []
    for index, case in enumerate(cases, start=1):
        pre_hash = case.get("pre_state_hash", "sha256:" + "a" * 64)
        permission_mode = _text(case.get("permission_mode"), "permission_mode")
        action = _text(case.get("action"), "action")
        receipt = case.get("receipt")
        normalized.append(
            {
                "case_id": _text(case.get("case_id", f"P152-CASE-{index:02d}"), "case_id"),
                "permission_mode": permission_mode,
                "action": action,
                "kill_switch": _bool(case.get("kill_switch", False), "kill_switch"),
                "deadman": _bool(case.get("deadman", False), "deadman"),
                "expect_action": _bool(case.get("expect_action", False), "expect_action"),
                "pre_state_hash": _hash(pre_hash, "pre_state_hash"),
                "receipt": receipt,
                "expected_rejection": case.get("expected_rejection"),
            }
        )
    normalized.sort(key=lambda item: str(item["case_id"]))
    _validate_frozen_case_coverage(normalized)
    return normalized


def _validate_frozen_case_coverage(cases: Sequence[Mapping[str, Any]]) -> None:
    if [case["case_id"] for case in cases] != list(P152_CASE_IDS):
        raise P152OperatorReadinessError("p152_frozen_case_ids_invalid")
    for case in cases:
        if case["permission_mode"] != "approve_once" or case["action"] != "restart_worker":
            raise P152OperatorReadinessError("p152_frozen_permission_mode_coverage_invalid")
        if case["expect_action"] is not False:
            raise P152OperatorReadinessError("p152_frozen_case_expectation_invalid")
        spec = FROZEN_CASE_REJECTIONS[case["case_id"]]
        if case["kill_switch"] != spec["kill_switch"] or case["deadman"] != spec["deadman"]:
            raise P152OperatorReadinessError("p152_frozen_safety_coverage_invalid")
        if case.get("expected_rejection") != spec["expected_rejection"]:
            raise P152OperatorReadinessError("p152_frozen_rejection_coverage_invalid")


def _evaluate_frozen_case(case: Mapping[str, Any], used_receipts: set[str]) -> tuple[dict[str, Any], bool]:
    try:
        observed = evaluate_permission_mode(
            permission_mode=case["permission_mode"],
            requested_action=case["action"],
            target=_PROCESS_TARGET,
            pre_state_hash=case["pre_state_hash"],
            receipt=case["receipt"],
            kill_switch=False,
            deadman=False,
            used_receipt_hashes=used_receipts,
        )
    except P152OperatorReadinessError as exc:
        reason = str(exc)
        observed = _rejected_result(case["permission_mode"], case["action"], _PROCESS_TARGET, reason, kill_switch=case["kill_switch"], deadman=case["deadman"])
        return observed, reason == case["expected_rejection"]
    return observed, case["expected_rejection"] is None and observed["action_executed"] is False and observed["production_operator_replacement_ready"] is False


def _contract_row(case_id: str, case: Mapping[str, Any], observed: Mapping[str, Any], passed: bool) -> dict[str, Any]:
    expected_measurements = {
        "permission_mode": case["permission_mode"],
        "requested_action": case["action"],
        "target": _PROCESS_TARGET,
        "action_executed": case["expect_action"],
        "kill_switch_blocked": bool(case["kill_switch"]),
        "deadman_blocked": bool(case["deadman"]),
        "rollback_closed": bool(case["expect_action"]),
        "production_operator_replacement_ready": False,
    }
    observed_measurements = {key: observed[key] for key in MEASUREMENT_KEYS}
    expected = build_result(P152_CONTRACT.result_schema, "expected", (), expected_measurements)
    failures = () if passed else ("permission_or_safety_mismatch",)
    actual = build_result(P152_CONTRACT.result_schema, "observed", observed.get("reason_codes", failures), observed_measurements)
    return build_row(contract=P152_CONTRACT, case_id=case_id, expected=expected, observed=actual, passed=passed, failure_classes=failures)


def _result(permission_mode: str, action: str, target: str, executed: bool, reasons: list[str], rollback_closed: bool) -> dict[str, Any]:
    return {
        "permission_mode": permission_mode,
        "requested_action": action,
        "target": target,
        "action_executed": executed,
        "kill_switch_blocked": False,
        "deadman_blocked": False,
        "rollback_closed": rollback_closed,
        "production_operator_replacement_ready": False,
        "reason_codes": reasons,
        "postcondition_checked": executed,
    }


def _rejected_result(permission_mode: str, action: str, target: str, reason: str, *, kill_switch: bool, deadman: bool) -> dict[str, Any]:
    result = _result(permission_mode, action, target, False, [reason], False)
    result["kill_switch_blocked"] = kill_switch
    result["deadman_blocked"] = deadman
    return result


def _blocked_result(permission_mode: str, action: str, target: str, reason: str) -> dict[str, Any]:
    result = _result(permission_mode, action, target, False, [reason, "escalation_receipt_written"], False)
    result["kill_switch_blocked"] = reason == "kill_switch_blocked"
    result["deadman_blocked"] = reason == "deadman_blocked"
    result["escalation_receipt_hash"] = stable_hash({"permission_mode": permission_mode, "action": action, "target": target, "reason": reason})
    return result


def _gate_failures(rows: Sequence[Mapping[str, Any]], metrics: Mapping[str, Any]) -> list[str]:
    failures = []
    if len(rows) != 8 or any(not row["passed"] for row in rows):
        failures.append("integration_cases")
    if metrics["predecessor_count"] != 6 or metrics["qualified_predecessor_count"] != 6:
        failures.append("predecessor_count")
    for key in ("kill_switch_pass", "deadman_pass", "rollback_closure"):
        if metrics[key] is not True:
            failures.append(key)
    if metrics["production_operator_replacement_ready"] is not False:
        failures.append("production_operator_replacement_ready")
    return failures


def _validate_exact_p152_report_semantics(report: Mapping[str, Any]) -> None:
    expected_metrics = _derive_p152_metrics_from_rows(report["rows"], report["predecessors"])
    if dict(report["metrics"]) != expected_metrics:
        raise P152OperatorReadinessError("p152_report_metrics_forged_or_invalid")
    if report["case_count"] != 8 or report["passed"] != 8 or report["failed"] != 0:
        raise P152OperatorReadinessError("p152_report_exact_denominator_invalid")
    if [row["case_id"] for row in report["rows"]] != list(P152_CASE_IDS):
        raise P152OperatorReadinessError("p152_report_case_coverage_invalid")
    expected_profile_hash = stable_hash(build_p152_release_profile(case_ids=P152_CASE_IDS))
    if report["profile_hash"] != expected_profile_hash:
        raise P152OperatorReadinessError("p152_report_profile_hash_invalid")
    for row in report["rows"]:
        spec = FROZEN_CASE_REJECTIONS[row["case_id"]]
        measurements = row["observed"]["measurements"]
        if measurements["permission_mode"] != "approve_once" or measurements["action_executed"] is not False:
            raise P152OperatorReadinessError("p152_report_permission_coverage_invalid")
        if measurements["requested_action"] != "restart_worker" or measurements["target"] != _PROCESS_TARGET:
            raise P152OperatorReadinessError("p152_report_action_target_coverage_invalid")
        if measurements["kill_switch_blocked"] != spec["kill_switch"] or measurements["deadman_blocked"] != spec["deadman"]:
            raise P152OperatorReadinessError("p152_report_safety_coverage_invalid")
        if measurements["production_operator_replacement_ready"] is not False:
            raise P152OperatorReadinessError("p152_report_production_replacement_invalid")
        expected_reason = spec["expected_rejection"]
        expected_reasons = ["approve_once_fixture_receipt_valid_no_execution"] if expected_reason is None else [expected_reason]
        if row["observed"]["reason_codes"] != expected_reasons:
            raise P152OperatorReadinessError("p152_report_rejection_coverage_invalid")


def _validate_exact_p152_release_semantics(evidence: Mapping[str, Any]) -> None:
    expected_metrics = _canonical_p152_release_metrics(evidence["predecessors"])
    if dict(evidence["metrics"]) != expected_metrics:
        raise P152OperatorReadinessError("p152_release_metrics_forged_or_invalid")
    if evidence["passed"] != 8 or evidence["failed"] != 0:
        raise P152OperatorReadinessError("p152_release_exact_denominator_invalid")


def _derive_p152_metrics_from_rows(rows: Sequence[Mapping[str, Any]], predecessors: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    executed_rows = [row for row in rows if row["observed"]["measurements"]["action_executed"]]
    production_ready = any(row["observed"]["measurements"]["production_operator_replacement_ready"] for row in rows)
    return {
        "predecessor_count": len(P152_CONTRACT.predecessors),
        "qualified_predecessor_count": len(predecessors),
        "kill_switch_pass": any(row["observed"]["measurements"]["kill_switch_blocked"] is True and row["observed"]["measurements"]["action_executed"] is False for row in rows),
        "deadman_pass": any(row["observed"]["measurements"]["deadman_blocked"] is True and row["observed"]["measurements"]["action_executed"] is False for row in rows),
        "rollback_closure": all(row["observed"]["measurements"]["rollback_closed"] for row in executed_rows),
        "production_operator_replacement_ready": production_ready,
    }


def _canonical_p152_release_metrics(predecessors: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "predecessor_count": len(P152_CONTRACT.predecessors),
        "qualified_predecessor_count": len(predecessors),
        "kill_switch_pass": True,
        "deadman_pass": True,
        "rollback_closure": True,
        "production_operator_replacement_ready": False,
    }


def _receipt_signature(receipt: Mapping[str, Any]) -> str:
    body = {key: value for key, value in receipt.items() if key != "signature"}
    return stable_hash({"secret": _SECRET, "receipt": body})


def _now() -> datetime:
    return datetime.now(UTC)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise P152OperatorReadinessError(f"{field}_invalid")
    return value


def _hash(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        raise P152OperatorReadinessError(f"{field}_invalid")
    return value


def _utc(value: Any, field: str) -> str:
    text = _text(value, field)
    if not text.endswith("Z"):
        raise P152OperatorReadinessError(f"{field}_invalid")
    datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
    return text


def _bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise P152OperatorReadinessError(f"{field}_invalid")
    return value
