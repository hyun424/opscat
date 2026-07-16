"""P149 one-target lab canary outcome control."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from statistics import mean, pstdev
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
    load_json,
    predecessor_from_path,
    validate_final_review,
    validate_freeze_manifest,
    validate_release_evidence,
    validate_report,
    write_preliminary_artifacts,
)

P149_CONTRACT = PhaseContract(
    phase="p149",
    status="p149_canary_outcome_control_qualified",
    claim="one-target canaries are SLO guarded and automatically rolled back",
    limitations=(
        "automatic_rollback_no_production_authority",
        "one_process_owned_lab_target_only",
        "synthetic_slo_observations",
    ),
    metric_keys=(
        "canary_count",
        "committed_count",
        "rolled_back_count",
        "harmful_count",
        "max_affected_targets",
        "rollback_success_rate",
        "canonical_input_verified",
    ),
    measurement_keys=(
        "decision",
        "affected_targets",
        "window_seconds",
        "sample_count",
        "mean_delta_basis_points",
        "relative_uncertainty_basis_points",
        "rollback_count",
        "commit_count",
        "duplicate_effect_count",
        "fail_closed",
    ),
    predecessors=(
        PredecessorSpec(
            phase="p148",
            path="evals/p148/output/release-evidence.json",
            schema_version="p148.release_evidence.v1",
            status="p148_reversible_lab_action_qualified",
        ),
    ),
)
ACTION_RECEIPT_KEYS = frozenset({"p148_receipt_hash", "target_id", "idempotency_key", "rollback_handler"})
ALLOWED_ROLLBACK_HANDLER = "restore_process_snapshot"
SHA256_PREFIX = "sha256:"
P148_COMMITMENT_SCHEMA = "p148.action_receipt_commitment.v1"
CANONICAL_CASES_PATH = Path("evals/p149/input/canary-cases.json")
P148_COMMITMENT_KEYS = frozenset(
    {
        "schema_version",
        "case_id",
        "target_id",
        "idempotency_key",
        "rollback_handler",
        "p148_receipt_hash",
    }
)

PROFILE: dict[str, Any] = {
    "schema_version": "p149.release_profile.v1",
    "phase": "p149",
    "case_ids": [f"P149-CASE-{index:02d}" for index in range(1, 9)],
    "limits": {
        "window_seconds": 60,
        "minimum_observations": 5,
        "improvement_basis_points": 1000,
        "harm_basis_points": 500,
        "relative_uncertainty_basis_points": 200,
        "max_affected_targets": 1,
    },
}


def run_p149_qualification(
    *,
    predecessor: Mapping[str, Any] | None = None,
    cases: Sequence[Mapping[str, Any]],
    output_dir: Path,
    kill_switch_engaged: bool = False,
    project_root: Path | None = None,
    evidence_mode: str = "canonical",
    cases_path: Path | None = None,
) -> dict[str, Any]:
    root = project_root or Path.cwd()
    if evidence_mode == "canonical":
        if predecessor is not None:
            raise ContractError("p149_predecessor_path_required")
        cases = _canonical_cases(root, cases=cases, cases_path=cases_path)
        predecessor_release = load_json(root / P149_CONTRACT.predecessors[0].path)
        predecessor_entry = predecessor_from_path(root, P149_CONTRACT.predecessors[0])
    elif evidence_mode == "isolated_test":
        predecessor_release = deepcopy(dict(predecessor)) if predecessor is not None else load_json(root / P149_CONTRACT.predecessors[0].path)
        predecessor_entry = (
            _isolated_predecessor_entry(predecessor_release)
            if predecessor is not None
            else predecessor_from_path(root, P149_CONTRACT.predecessors[0])
        )
    else:
        raise ContractError("p149_evidence_mode_invalid")
    _validate_case_set(cases)
    _validate_action_receipts(cases, predecessor_release=predecessor_release)
    rows = [_evaluate_case(case, kill_switch_engaged=kill_switch_engaged) for case in sorted(cases, key=lambda item: str(item.get("case_id", "")))]
    metrics = _metrics(rows, canonical_input_verified=evidence_mode == "canonical")
    counters = _counters(rows, metrics)
    report = build_report(
        contract=P149_CONTRACT,
        profile=PROFILE,
        predecessors=[predecessor_entry],
        source_hashes=current_source_hashes(root, "p149"),
        rows=rows,
        metrics=metrics,
        counters=counters,
    )
    freeze_manifest = build_freeze_manifest(project_root=root, contract=P149_CONTRACT, report=report)
    write_preliminary_artifacts(output_dir, report, freeze_manifest)
    return {"report": report, "freeze_manifest": freeze_manifest}


def validate_p149_report(report: Mapping[str, Any]) -> dict[str, Any]:
    validated = validate_report(report, P149_CONTRACT)
    _validate_profile_case_rows(validated)
    _validate_report_metrics_and_counters(validated)
    return validated


def validate_p149_freeze_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return validate_freeze_manifest(manifest, P149_CONTRACT)


def validate_p149_final_review(
    review: Mapping[str, Any], *, report: Mapping[str, Any] | None = None, freeze_manifest: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    return validate_final_review(review, contract=P149_CONTRACT, report=report, freeze_manifest=freeze_manifest)


def assemble_p149_release_evidence(
    *, report: Mapping[str, Any], freeze_manifest: Mapping[str, Any], final_review: Mapping[str, Any]
) -> dict[str, Any]:
    return assemble_release_evidence(contract=P149_CONTRACT, report=validate_p149_report(report), freeze_manifest=freeze_manifest, final_review=final_review)


def validate_p149_release_evidence(evidence: Mapping[str, Any], *, report: Mapping[str, Any] | None = None) -> dict[str, Any]:
    validated = validate_release_evidence(evidence, P149_CONTRACT)
    if validated["passed"] != len(PROFILE["case_ids"]) or validated["failed"] != 0:
        raise ContractError("p149_release_exact_8_of_8_required")
    if validated["metrics"].get("canary_count") != len(PROFILE["case_ids"]):
        raise ContractError("p149_release_canary_count_exact_8_required")
    if report is not None:
        validated_report = validate_p149_report(report)
        if validated["metrics"] != validated_report["metrics"] or validated["counters"] != validated_report["counters"]:
            raise ContractError("p149_release_metric_counter_rows_mismatch")
    _validate_release_metrics_and_counters(validated)
    return validated


def _canonical_cases(root: Path, *, cases: Sequence[Mapping[str, Any]], cases_path: Path | None) -> list[Mapping[str, Any]]:
    if cases_path is None:
        raise ContractError("p149_canonical_cases_path_required")
    expected_path = (root / CANONICAL_CASES_PATH).resolve(strict=True)
    supplied_path = cases_path.resolve(strict=True)
    if supplied_path != expected_path or cases_path.is_symlink():
        raise ContractError("p149_canonical_cases_path_invalid")
    try:
        loaded = json.loads(supplied_path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError("p149_canonical_cases_content_invalid") from exc
    loaded_cases = loaded.get("cases") if isinstance(loaded, dict) else loaded
    if not isinstance(loaded_cases, list):
        raise ContractError("p149_canonical_cases_content_invalid")
    if list(cases) != loaded_cases:
        raise ContractError("p149_canonical_cases_content_mismatch")
    return loaded_cases


def _isolated_predecessor_entry(predecessor_release: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(predecessor_release))
    if (
        value.get("schema_version") != P149_CONTRACT.predecessors[0].schema_version
        or value.get("phase") != P149_CONTRACT.predecessors[0].phase
        or value.get("status") != P149_CONTRACT.predecessors[0].status
    ):
        raise ContractError("p149_isolated_predecessor_release_status_or_schema_invalid")
    evidence_hash = value.get("evidence_hash")
    if not _is_sha256(evidence_hash):
        raise ContractError("p149_isolated_predecessor_evidence_hash_invalid")
    _validate_action_receipt_commitments(value)
    return {
        "phase": P149_CONTRACT.predecessors[0].phase,
        "path": P149_CONTRACT.predecessors[0].path,
        "schema_version": P149_CONTRACT.predecessors[0].schema_version,
        "required_status": P149_CONTRACT.predecessors[0].status,
        "file_hash": str(evidence_hash),
        "evidence_hash": str(evidence_hash),
    }


def _evaluate_case(case: Mapping[str, Any], *, kill_switch_engaged: bool) -> dict[str, Any]:
    value = deepcopy(dict(case))
    case_id = _required_str(value, "case_id")
    target = _mapping(value.get("target"), "target")
    slo = _mapping(value.get("slo"), "slo")
    expected_decision = _required_str(value, "expected_decision")
    outcome = _required_str(value, "injected_outcome")
    action_receipt = _mapping(value.get("action_receipt"), "action_receipt")
    _validate_target(target)
    if action_receipt.get("target_id") != target.get("target_id"):
        raise ContractError(f"action_receipt_target_binding_invalid:{case_id}")
    observations = _observations(slo)
    reasons: list[str] = []
    measurements = _slo_measurements(slo, observations)
    decision = _slo_decision(measurements)

    if kill_switch_engaged or outcome == "kill_switch":
        decision = "rollback"
        reasons.append("kill_switch")
        measurements["affected_targets"] = 0
        measurements["rollback_count"] = 1
    elif outcome == "timeout":
        decision = "rollback"
        reasons.append("window_timeout")
        measurements["affected_targets"] = 0
        measurements["rollback_count"] = 1
    elif outcome == "missing_evidence":
        decision = "rollback"
        reasons.append("missing_evidence")
        measurements["affected_targets"] = 0
        measurements["rollback_count"] = 1
    elif outcome == "replay":
        decision = "no_duplicate_effect"
        reasons.append("replay_suppressed")
        measurements["affected_targets"] = 0
        measurements["duplicate_effect_count"] = 0
    elif outcome == "rollback_failure":
        decision = "fail_closed"
        reasons.extend(("rollback_failure_fail_closed", "rollback_preflight_blocked_before_effect"))
        measurements["affected_targets"] = 0
        measurements["rollback_count"] = 0
        measurements["fail_closed"] = True
    elif decision == "commit":
        reasons.append("slo_improvement_met")
        measurements["commit_count"] = 1
    else:
        reasons.append(f"slo_{decision}")
        measurements["affected_targets"] = 0
        measurements["rollback_count"] = 1

    _validate_rollback_handler(action_receipt, decision)
    measurements["decision"] = decision
    expected = build_result(P149_CONTRACT.result_schema, expected_decision, [f"expected_{expected_decision}"], _blank_measurements(expected_decision))
    observed = build_result(P149_CONTRACT.result_schema, decision, sorted(reasons), measurements)
    return build_row(
        contract=P149_CONTRACT,
        case_id=case_id,
        expected=expected,
        observed=observed,
        passed=decision == expected_decision,
        failure_classes=() if decision == expected_decision else ("decision_mismatch",),
    )


def _validate_target(target: Mapping[str, Any]) -> None:
    target_id = target.get("target_id")
    if not isinstance(target_id, str) or not target_id:
        raise ContractError("target_id_required")
    if target.get("affected_target_count") != 1:
        raise ContractError("blast_radius_affected_one_target_required")
    if target.get("environment") != "process_owned_disposable_lab":
        raise ContractError("staging_production_target_authority_rejected")
    if target.get("cohort_hash") == target.get("control_hash"):
        raise ContractError("canary_cohort_control_hashes_must_be_disjoint")


def _validate_case_set(cases: Sequence[Mapping[str, Any]]) -> None:
    if not isinstance(cases, Sequence) or isinstance(cases, (str, bytes)):
        raise ContractError("p149_cases_sequence_required")
    expected = list(PROFILE["case_ids"])
    case_ids: list[str] = []
    for case in cases:
        if not isinstance(case, Mapping):
            raise ContractError("p149_case_object_required")
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            raise ContractError("p149_case_id_required")
        case_ids.append(case_id)
    duplicates = sorted({case_id for case_id in case_ids if case_ids.count(case_id) > 1})
    if duplicates:
        raise ContractError(f"p149_profile_case_id_duplicate:{','.join(duplicates)}")
    missing = sorted(set(expected) - set(case_ids))
    extra = sorted(set(case_ids) - set(expected))
    if missing or extra:
        raise ContractError(f"p149_profile_case_id_set_mismatch:missing={','.join(missing)}:extra={','.join(extra)}")


def _validate_profile_case_rows(report: Mapping[str, Any]) -> None:
    case_ids = [row["case_id"] for row in report["rows"]]
    if case_ids != list(PROFILE["case_ids"]):
        raise ContractError("p149_report_profile_case_ids_not_exact")


def _validate_report_metrics_and_counters(report: Mapping[str, Any]) -> None:
    rows = report["rows"]
    canonical_input_verified = report["metrics"].get("canonical_input_verified")
    if not isinstance(canonical_input_verified, bool):
        raise ContractError("p149_report_canonical_input_flag_required")
    metrics = _metrics(rows, canonical_input_verified=canonical_input_verified)
    if report["metrics"] != metrics:
        raise ContractError("p149_report_metric_rows_mismatch")
    counters = _counters(rows, metrics)
    if report["counters"] != counters:
        raise ContractError("p149_report_counter_rows_mismatch")


def _validate_release_metrics_and_counters(release: Mapping[str, Any]) -> None:
    metrics = release["metrics"]
    expected_canaries = len(PROFILE["case_ids"])
    expected_commits = 1
    expected_rollbacks = 5
    expected_metrics = {
        "canary_count": expected_canaries,
        "committed_count": expected_commits,
        "rolled_back_count": expected_rollbacks,
        "harmful_count": 2,
        "max_affected_targets": 1,
        "rollback_success_rate": 1.0,
        "canonical_input_verified": True,
    }
    if metrics != expected_metrics:
        raise ContractError("p149_release_metric_rows_mismatch")
    expected_counters = empty_counters(
        action_intent_count=expected_canaries,
        action_commit_count=expected_commits,
        action_execution_count=expected_commits + expected_rollbacks,
        rollback_count=expected_rollbacks,
        artifact_write_count=expected_canaries,
    )
    if release["counters"] != expected_counters:
        raise ContractError("p149_release_counter_rows_mismatch")


def _validate_action_receipts(cases: Sequence[Mapping[str, Any]], *, predecessor_release: Mapping[str, Any]) -> None:
    commitments = _validate_action_receipt_commitments(predecessor_release)
    seen_idempotency: set[str] = set()
    seen_receipts: set[str] = set()
    for case in cases:
        case_id = str(case.get("case_id", "unknown"))
        receipt = _mapping(case.get("action_receipt"), "action_receipt")
        if set(receipt) != ACTION_RECEIPT_KEYS:
            raise ContractError(f"action_receipt_keyset_invalid:{case_id}")
        receipt_hash = receipt.get("p148_receipt_hash")
        if not _is_sha256(receipt_hash):
            raise ContractError(f"action_receipt_hash_invalid:{case_id}")
        commitment = commitments.get(str(receipt_hash))
        if commitment is None:
            raise ContractError(f"action_receipt_not_committed_by_p148:{case_id}")
        if commitment["case_id"] != case_id:
            raise ContractError(f"action_receipt_case_binding_invalid:{case_id}")
        target = _mapping(case.get("target"), "target")
        if commitment["target_id"] != receipt.get("target_id") or receipt.get("target_id") != target.get("target_id"):
            raise ContractError(f"action_receipt_target_binding_invalid:{case_id}")
        idempotency_key = receipt.get("idempotency_key")
        if not isinstance(idempotency_key, str) or not idempotency_key:
            raise ContractError(f"action_receipt_idempotency_key_required:{case_id}")
        if idempotency_key != commitment["idempotency_key"]:
            raise ContractError(f"action_receipt_idempotency_binding_invalid:{case_id}")
        if idempotency_key in seen_idempotency:
            raise ContractError(f"action_receipt_idempotency_key_duplicate:{case_id}")
        seen_idempotency.add(idempotency_key)
        handler = receipt.get("rollback_handler")
        if not isinstance(handler, str) or not handler:
            raise ContractError(f"action_receipt_rollback_handler_required:{case_id}")
        if handler != commitment["rollback_handler"]:
            raise ContractError(f"action_receipt_rollback_handler_binding_invalid:{case_id}")
        if str(receipt_hash) in seen_receipts:
            raise ContractError(f"action_receipt_hash_duplicate:{case_id}")
        seen_receipts.add(str(receipt_hash))
    expected_hashes = {commitment["p148_receipt_hash"] for commitment in commitments.values()}
    if seen_receipts != expected_hashes:
        raise ContractError("action_receipt_committed_set_mismatch")


def _p148_commitments(predecessor_release: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    metrics = _mapping(predecessor_release.get("metrics"), "p148_metrics")
    raw_commitments = metrics.get("committed_action_receipts")
    if not isinstance(raw_commitments, list) or not raw_commitments:
        raise ContractError("p148_committed_action_receipts_required")
    commitments: dict[str, dict[str, Any]] = {}
    case_ids: set[str] = set()
    for raw in raw_commitments:
        if not isinstance(raw, Mapping):
            raise ContractError("p148_committed_action_receipt_object_required")
        receipt = deepcopy(dict(raw))
        if set(receipt) != P148_COMMITMENT_KEYS or receipt.get("schema_version") != P148_COMMITMENT_SCHEMA:
            raise ContractError("p148_committed_action_receipt_keyset_invalid")
        if not all(isinstance(receipt.get(field), str) and receipt[field] for field in ("case_id", "target_id", "idempotency_key", "rollback_handler")):
            raise ContractError("p148_committed_action_receipt_identity_invalid")
        receipt_hash = receipt.get("p148_receipt_hash")
        if not _is_sha256(receipt_hash):
            raise ContractError("p148_committed_action_receipt_hash_invalid")
        if receipt_hash != _commitment_hash(receipt):
            raise ContractError("p148_committed_action_receipt_hash_mismatch")
        if str(receipt_hash) in commitments:
            raise ContractError("p148_committed_action_receipt_hash_duplicate")
        if str(receipt["case_id"]) in case_ids:
            raise ContractError("p148_committed_action_receipt_case_duplicate")
        commitments[str(receipt_hash)] = receipt
        case_ids.add(str(receipt["case_id"]))
    expected_case_ids = set(PROFILE["case_ids"])
    if case_ids != expected_case_ids:
        missing = sorted(expected_case_ids - case_ids)
        extra = sorted(case_ids - expected_case_ids)
        raise ContractError(f"p148_committed_action_receipt_case_set_mismatch:missing={','.join(missing)}:extra={','.join(extra)}")
    return commitments


def _validate_action_receipt_commitments(predecessor_release: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return _p148_commitments(predecessor_release)


def _commitment_hash(receipt: Mapping[str, Any]) -> str:
    from app.services.p147_p152_contracts import stable_hash

    return stable_hash({key: receipt[key] for key in sorted(P148_COMMITMENT_KEYS - {"p148_receipt_hash"})})


def _validate_rollback_handler(receipt: Mapping[str, Any], decision: str) -> None:
    if decision in {"rollback", "fail_closed"} and receipt.get("rollback_handler") != ALLOWED_ROLLBACK_HANDLER:
        raise ContractError("action_receipt_rollback_handler_not_allowed")


def _slo_measurements(slo: Mapping[str, Any], observations: Sequence[int]) -> dict[str, Any]:
    limits = PROFILE["limits"]
    if slo.get("window_seconds") != limits["window_seconds"]:
        raise ContractError("slo_window_seconds_must_be_60")
    if slo.get("minimum_observations") != limits["minimum_observations"] or len(observations) < limits["minimum_observations"]:
        raise ContractError("slo_minimum_five_observations_required")
    if slo.get("improvement_basis_points") != limits["improvement_basis_points"]:
        raise ContractError("slo_improvement_10_percent_required")
    if slo.get("harm_basis_points") != limits["harm_basis_points"]:
        raise ContractError("slo_harm_5_percent_required")
    if slo.get("relative_uncertainty_basis_points") != limits["relative_uncertainty_basis_points"]:
        raise ContractError("slo_uncertainty_2_percent_required")
    uncertainty = int(round(pstdev(observations))) if len(observations) > 1 else 0
    return {
        "decision": "rollback",
        "affected_targets": 1,
        "window_seconds": 60,
        "sample_count": len(observations),
        "mean_delta_basis_points": int(round(mean(observations))),
        "relative_uncertainty_basis_points": uncertainty,
        "rollback_count": 0,
        "commit_count": 0,
        "duplicate_effect_count": 0,
        "fail_closed": False,
    }


def _slo_decision(measurements: Mapping[str, Any]) -> str:
    mean_delta = int(measurements["mean_delta_basis_points"])
    uncertainty = int(measurements["relative_uncertainty_basis_points"])
    limits = PROFILE["limits"]
    if uncertainty > limits["relative_uncertainty_basis_points"]:
        return "rollback"
    if mean_delta <= -limits["harm_basis_points"]:
        return "rollback"
    if mean_delta >= limits["improvement_basis_points"]:
        return "commit"
    return "rollback"


def _metrics(rows: Sequence[Mapping[str, Any]], *, canonical_input_verified: bool) -> dict[str, Any]:
    decisions = [row["observed"]["measurements"]["decision"] for row in rows]
    rollback_attempts = _rollback_attempt_count(rows)
    successful_rollbacks = _successful_verified_rollback_count(rows)
    fail_closed_effects_safe = all(
        row["observed"]["measurements"]["fail_closed"] is not True or int(row["observed"]["measurements"]["affected_targets"]) == 0
        for row in rows
    )
    rollback_success_rate = successful_rollbacks / rollback_attempts if rollback_attempts else 1.0
    if not fail_closed_effects_safe:
        rollback_success_rate = 0.0
    return {
        "canary_count": len(rows),
        "committed_count": decisions.count("commit"),
        "rolled_back_count": successful_rollbacks,
        "harmful_count": sum(
            1
            for row in rows
            if int(row["observed"]["measurements"]["mean_delta_basis_points"])
            <= -PROFILE["limits"]["harm_basis_points"]
        ),
        "max_affected_targets": max((int(row["observed"]["measurements"]["affected_targets"]) for row in rows), default=0),
        "rollback_success_rate": rollback_success_rate,
        "canonical_input_verified": canonical_input_verified,
    }


def _counters(rows: Sequence[Mapping[str, Any]], metrics: Mapping[str, Any]) -> dict[str, int]:
    rollback_attempts = _rollback_attempt_count(rows)
    return empty_counters(
        action_intent_count=len(rows),
        action_commit_count=int(metrics["committed_count"]),
        action_execution_count=int(metrics["committed_count"]) + rollback_attempts,
        rollback_count=rollback_attempts,
        artifact_write_count=len(rows),
    )


def _rollback_attempt_count(rows: Sequence[Mapping[str, Any]]) -> int:
    return sum(1 for row in rows if int(row["observed"]["measurements"]["rollback_count"]) > 0)


def _successful_verified_rollback_count(rows: Sequence[Mapping[str, Any]]) -> int:
    return sum(
        1
        for row in rows
        if int(row["observed"]["measurements"]["rollback_count"]) > 0
        and row["observed"]["measurements"]["fail_closed"] is not True
        and int(row["observed"]["measurements"]["affected_targets"]) == 0
    )


def _blank_measurements(decision: str) -> dict[str, Any]:
    return {
        "decision": decision,
        "affected_targets": 0,
        "window_seconds": 60,
        "sample_count": 0,
        "mean_delta_basis_points": 0,
        "relative_uncertainty_basis_points": 0,
        "rollback_count": 0,
        "commit_count": 0,
        "duplicate_effect_count": 0,
        "fail_closed": decision == "fail_closed",
    }


def _observations(slo: Mapping[str, Any]) -> list[int]:
    raw = slo.get("observations_basis_points")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or any(isinstance(item, bool) or not isinstance(item, int) for item in raw):
        raise ContractError("slo_observations_integer_list_required")
    return list(raw)


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{field}_object_required")
    return value


def _required_str(value: Mapping[str, Any], field: str) -> str:
    item = value.get(field)
    if not isinstance(item, str) or not item:
        raise ContractError(f"{field}_required")
    return item


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == len(SHA256_PREFIX) + 64 and value.startswith(SHA256_PREFIX) and all(
        character in "0123456789abcdef" for character in value[len(SHA256_PREFIX) :]
    )
