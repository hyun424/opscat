"""P151 sealed ground-truth quality qualification."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
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
    file_hash,
    load_json,
    predecessor_from_path,
    predecessor_from_release_evidence,
    stable_hash,
    validate_final_review,
    validate_freeze_manifest,
    validate_predecessor_entry,
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
METRIC_KEYS = (
    "detection_recall",
    "false_positive_rate",
    "top1_accuracy",
    "top3_accuracy",
    "citation_valid_rate",
    "abstention_accuracy",
    "lead_time_seconds",
    "tool_efficiency",
    "action_utility",
    "rollback_correctness",
    "unsafe_action_rate",
)
MEASUREMENT_KEYS = (
    "truth_label",
    "predicted_label",
    "top3_match",
    "citation_valid",
    "abstained",
    "lead_time_seconds",
    "tool_call_count",
    "action_utility_bps",
    "rollback_correct",
    "unsafe_action",
)
LIMITATIONS = (
    "no_actions_or_mutations",
    "nvidia_optional_nonrelease",
    "sealed_48_case_offline_corpus_not_general_accuracy",
)
P151_CONTRACT = PhaseContract(
    phase="p151",
    status="p151_ground_truth_quality_qualified",
    claim="sealed_48_case_ground_truth_quality_qualified",
    limitations=LIMITATIONS,
    metric_keys=METRIC_KEYS,
    measurement_keys=MEASUREMENT_KEYS,
    predecessors=(
        PredecessorSpec(
            phase="p150",
            path="evals/p150/output/release-evidence.json",
            schema_version="p150.release_evidence.v1",
            status="p150_unattended_chaos_soak_qualified",
        ),
    ),
)
_REQUIRED_FIELDS = {
    "case_id",
    "truth_label",
    "provenance",
}
_TRUTH_FORBIDDEN_FIELDS = {
    "predicted_label",
    "top3_labels",
    "citation_valid",
    "abstained",
    "lead_time_seconds",
    "tool_call_count",
    "action_utility_bps",
    "rollback_correct",
    "unsafe_action",
    "prediction_source",
    "action_recommendation",
}
_PREDICTION_ROW_FIELDS = frozenset(
    {
        "case_id",
        "predicted_label",
        "top3_labels",
        "citation_valid",
        "abstained",
        "lead_time_seconds",
        "tool_call_count",
        "action_utility_bps",
        "rollback_correct",
        "unsafe_action",
        "action_recommendation",
    }
)
_PREDICTION_PACKET_KEYS = frozenset({"schema_version", "phase", "predictions", "prediction_packet_hash"})
_PREDICTION_CONTAMINATION_MARKERS = (
    "truth_label",
    "provenance",
    "source_sha256",
    "source_raw_sha256",
    "source_case_id",
    "source_scenario",
    "origin_kind",
    "dataset_split",
    "split_identity",
)
_PREDICTION_COMMIT_KEYS = frozenset(
    {
        "schema_version",
        "phase",
        "case_ids",
        "prediction_packet_hash",
        "prediction_packet_raw_file_hash",
        "action_recommendation_hashes",
        "truth_seal_hash",
        "commit_hash",
    }
)
_PROVENANCE_KEYS = frozenset(
    {
        "source_path",
        "source_sha256",
        "source_raw_sha256",
        "source_case_id",
        "source_scenario",
        "origin_kind",
        "license_ref",
        "license_id",
        "license_class",
        "dataset_split",
        "split_identity",
        "contamination_guard",
        "contamination_proof",
    }
)
_ORIGIN_KINDS = {"golden", "agentic", "judgment_seed"}
_LICENSE_REF = "LICENSE"
_LICENSE_ID = "LicenseRef-OPSCAT-Repository"
_LICENSE_CLASS = "repository-local-fixture"
_DATASET_SPLIT = "p151-sealed-eval"
_CONTAMINATION_GUARD = "recorded-offline-fixture-baseline"
_CONTAMINATION_PROOF = "prediction-commit-before-truth-unseal"
PREDICTION_SOURCE = "recorded_fixture_baseline"
CANONICAL_TRUTH_PATH = Path("evals/p151/input/sealed-corpus.json")
CANONICAL_PACKET_PATH = Path("evals/p151/input/prediction-packet.json")
CANONICAL_COMMIT_PATH = Path("evals/p151/input/prediction-commit.json")
_KNOWN_LABELS = {
    "incident",
    "no_incident",
    "deploy_regression",
    "queue_backlog",
    "db_pool_exhaustion",
    "downstream_timeout",
    "cpu_saturation",
    "memory_pressure",
    "retry_storm",
    "slow_query",
    "insufficient_evidence",
}


class P151GroundTruthQualityError(ValueError):
    """Raised when P151 evidence cannot prove the sealed quality contract."""


GATE_LIMITS = {
    "exactly_48_rows": 48,
    "unsafe_action_rate": 0,
    "citation_valid_rate": 1.0,
    "rollback_correctness": 1.0,
    "detection_recall_min": 0.90,
    "false_positive_rate_max": 0.05,
    "top3_accuracy_min": 0.90,
    "abstention_accuracy_min": 0.95,
    "action_utility_min": 0.80,
}


def seal_truth_packet(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    sealed_rows = _normalize_truth_rows(rows)
    for row in sealed_rows:
        if row["truth_label"] not in _KNOWN_LABELS:
            raise P151GroundTruthQualityError("truth_label_invalid")
    seal = {
        "schema_version": "p151.truth_seal.v1",
        "case_ids": [row["case_id"] for row in sealed_rows],
        "truth_packet_hash": stable_hash(
            [{"case_id": row["case_id"], "truth_label": row["truth_label"]} for row in sealed_rows]
        ),
        "truth_seal_hash": "",
    }
    seal["truth_seal_hash"] = stable_hash({key: value for key, value in seal.items() if key != "truth_seal_hash"})
    return seal


def normalize_prediction_packet(predictions: Sequence[Mapping[str, Any]] | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(predictions, Mapping):
        packet = deepcopy(dict(predictions))
        _reject_prediction_contamination(packet)
        if set(packet) != _PREDICTION_PACKET_KEYS or packet.get("schema_version") != "p151.prediction_packet.v1" or packet.get("phase") != "p151":
            raise P151GroundTruthQualityError("prediction_packet_keyset_invalid")
        rows = packet.get("predictions")
        if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
            raise P151GroundTruthQualityError("prediction_packet_rows_invalid")
        normalized_rows = _normalize_prediction_rows(rows)
        expected_hash = stable_hash(normalized_rows)
        if packet.get("prediction_packet_hash") != expected_hash:
            raise P151GroundTruthQualityError("prediction_packet_hash_invalid")
        return {
            "schema_version": "p151.prediction_packet.v1",
            "phase": "p151",
            "predictions": normalized_rows,
            "prediction_packet_hash": expected_hash,
        }
    _reject_prediction_contamination(predictions)
    normalized_rows = _normalize_prediction_rows(predictions)
    return {
        "schema_version": "p151.prediction_packet.v1",
        "phase": "p151",
        "predictions": normalized_rows,
        "prediction_packet_hash": stable_hash(normalized_rows),
    }


def commit_prediction_packet(
    predictions: Sequence[Mapping[str, Any]] | Mapping[str, Any],
    *,
    truth_seal_hash: str,
    prediction_packet_raw_file_hash: str,
) -> dict[str, Any]:
    _validate_hash(truth_seal_hash, "truth_seal_hash")
    _validate_hash(prediction_packet_raw_file_hash, "prediction_packet_raw_file_hash")
    packet = normalize_prediction_packet(predictions)
    commit = {
        "schema_version": "p151.prediction_commit.v1",
        "phase": "p151",
        "case_ids": [item["case_id"] for item in packet["predictions"]],
        "prediction_packet_hash": packet["prediction_packet_hash"],
        "prediction_packet_raw_file_hash": prediction_packet_raw_file_hash,
        "action_recommendation_hashes": _action_recommendation_hashes(packet["predictions"]),
        "truth_seal_hash": truth_seal_hash,
    }
    commit["commit_hash"] = stable_hash(commit)
    return commit


def validate_prediction_commit(
    commit: Mapping[str, Any],
    *,
    prediction_packet: Mapping[str, Any],
    prediction_packet_raw_file_hash: str,
) -> dict[str, Any]:
    packet = normalize_prediction_packet(prediction_packet)
    _validate_prediction_commit(
        commit,
        prediction_packet=packet,
        prediction_packet_raw_file_hash=prediction_packet_raw_file_hash,
    )
    return deepcopy(dict(commit))


def unseal_truth_after_commit(
    rows: Sequence[Mapping[str, Any]],
    *,
    prediction_commit: Mapping[str, Any],
    prediction_packet: Mapping[str, Any],
    prediction_packet_raw_file_hash: str,
) -> list[dict[str, Any]]:
    packet = normalize_prediction_packet(prediction_packet)
    _validate_prediction_commit(
        prediction_commit,
        prediction_packet=packet,
        prediction_packet_raw_file_hash=prediction_packet_raw_file_hash,
    )
    sealed = _normalize_truth_rows(rows)
    case_ids = [row["case_id"] for row in sealed]
    if case_ids != list(prediction_commit["case_ids"]):
        raise P151GroundTruthQualityError("sealed_truth_case_order_or_commit_mismatch")
    truth_seal = seal_truth_packet(sealed)
    if truth_seal["truth_seal_hash"] != prediction_commit["truth_seal_hash"]:
        raise P151GroundTruthQualityError("truth_seal_commit_hash_forgery_rejected")
    for row in sealed:
        if row["truth_label"] not in _KNOWN_LABELS:
            raise P151GroundTruthQualityError("truth_hash_forgery_rejected")
    return sealed


def score_sealed_truth_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    prediction_packet: Mapping[str, Any],
    prediction_commit: Mapping[str, Any] | None,
    prediction_packet_raw_file_hash: str,
) -> dict[str, Any]:
    if prediction_commit is None:
        raise P151GroundTruthQualityError("sealed_truth_requires_prediction_commit")
    packet = normalize_prediction_packet(prediction_packet)
    unsealed = unseal_truth_after_commit(
        rows,
        prediction_commit=prediction_commit,
        prediction_packet=packet,
        prediction_packet_raw_file_hash=prediction_packet_raw_file_hash,
    )
    joined = _join_truth_and_predictions(unsealed, packet["predictions"])
    metrics = _metrics(joined)
    rows_out = [_score_row(row) for row in joined]
    return {"row_count": len(joined), "metrics": metrics, "rows": rows_out}


def run_p151_qualification(
    *,
    rows: Sequence[Mapping[str, Any]],
    prediction_packet: Mapping[str, Any],
    prediction_commit: Mapping[str, Any],
    prediction_packet_raw_file_hash: str,
    prediction_commit_raw_file_hash: str,
    predecessor: Mapping[str, Any],
    output_dir: str | Path | None,
    include_nvidia: bool = False,
    nvidia_results: Mapping[str, Any] | None = None,
    project_root: str | Path | None = None,
    evidence_mode: str = "canonical",
    truth_path: str | Path = CANONICAL_TRUTH_PATH,
    prediction_packet_path: str | Path = CANONICAL_PACKET_PATH,
    prediction_commit_path: str | Path = CANONICAL_COMMIT_PATH,
) -> dict[str, Any]:
    try:
        root = Path(project_root) if project_root is not None else _project_root()
        if evidence_mode not in {"canonical", "isolated_test"}:
            raise P151GroundTruthQualityError("evidence_mode_invalid")
        if evidence_mode == "canonical":
            predecessor_entry = predecessor_from_path(root, P151_CONTRACT.predecessors[0])
            if dict(predecessor) != predecessor_entry:
                raise P151GroundTruthQualityError("predecessor_not_path_backed")
            _validate_canonical_input_bindings(
                root=root,
                rows=rows,
                prediction_packet=prediction_packet,
                prediction_commit=prediction_commit,
                prediction_packet_raw_file_hash=prediction_packet_raw_file_hash,
                prediction_commit_raw_file_hash=prediction_commit_raw_file_hash,
                truth_path=Path(truth_path),
                prediction_packet_path=Path(prediction_packet_path),
                prediction_commit_path=Path(prediction_commit_path),
            )
        else:
            predecessor_entry = (
                predecessor_from_release_evidence(predecessor, P151_CONTRACT.predecessors[0])
                if "status" in predecessor
                else validate_predecessor_entry(predecessor, P151_CONTRACT.predecessors[0])
            )
        _validate_hash(prediction_commit_raw_file_hash, "prediction_commit_raw_file_hash")
        packet = normalize_prediction_packet(prediction_packet)
        commit = validate_prediction_commit(
            prediction_commit,
            prediction_packet=packet,
            prediction_packet_raw_file_hash=prediction_packet_raw_file_hash,
        )
        normalized = _normalize_truth_rows(rows)
        truth_seal = seal_truth_packet(normalized)
        if commit["truth_seal_hash"] != truth_seal["truth_seal_hash"]:
            raise P151GroundTruthQualityError("truth_seal_commit_hash_forgery_rejected")
        scored = score_sealed_truth_rows(
            normalized,
            prediction_packet=packet,
            prediction_commit=commit,
            prediction_packet_raw_file_hash=prediction_packet_raw_file_hash,
        )
        metrics = scored["metrics"]
        failures = _gate_failures(metrics, int(scored["row_count"]))
        contract_rows = [_contract_row(row) for row in scored["rows"]]
        source_hashes = current_source_hashes(root, "p151")
        profile = _release_profile(
            case_ids=[row["case_id"] for row in normalized],
            prediction_commit_raw_file_hash=prediction_commit_raw_file_hash,
            prediction_packet_raw_file_hash=prediction_packet_raw_file_hash,
            truth_seal_hash=truth_seal["truth_seal_hash"],
        )
        report = build_report(
            contract=P151_CONTRACT,
            profile=profile,
            predecessors=[predecessor_entry],
            source_hashes=source_hashes,
            rows=contract_rows,
            metrics=metrics,
            counters=empty_counters(read_attempt_count=48, read_success_count=48, investigation_tool_call_count=sum(row["tool_call_count"] for row in packet["predictions"])),
        )
        if failures:
            raise P151GroundTruthQualityError("metric_gate_failed:" + ",".join(failures))
        if output_dir is not None:
            output = Path(output_dir)
            write_canonical_json(output / "report.json", report)
            if include_nvidia:
                write_canonical_json(
                    output / "nvidia-non-release-report.json",
                    build_p151_nvidia_non_release_report(canonical_report=report, nvidia_results=nvidia_results or {}),
                )
        return report
    except ContractError as exc:
        raise P151GroundTruthQualityError(f"p151_contract_fail_closed:{exc}") from exc


def _validate_canonical_input_bindings(
    *,
    root: Path,
    rows: Sequence[Mapping[str, Any]],
    prediction_packet: Mapping[str, Any],
    prediction_commit: Mapping[str, Any],
    prediction_packet_raw_file_hash: str,
    prediction_commit_raw_file_hash: str,
    truth_path: Path,
    prediction_packet_path: Path,
    prediction_commit_path: Path,
) -> None:
    expected_paths = (CANONICAL_TRUTH_PATH, CANONICAL_PACKET_PATH, CANONICAL_COMMIT_PATH)
    supplied_paths = (truth_path, prediction_packet_path, prediction_commit_path)
    if tuple(path.as_posix() for path in supplied_paths) != tuple(path.as_posix() for path in expected_paths):
        raise P151GroundTruthQualityError("canonical_input_path_invalid")
    packet_path = root / prediction_packet_path
    commit_path = root / prediction_commit_path
    truth_file = root / truth_path
    if file_hash(packet_path) != prediction_packet_raw_file_hash:
        raise P151GroundTruthQualityError("prediction_packet_raw_file_hash_mismatch")
    if file_hash(commit_path) != prediction_commit_raw_file_hash:
        raise P151GroundTruthQualityError("prediction_commit_raw_file_hash_mismatch")
    if normalize_prediction_packet(load_json(packet_path)) != normalize_prediction_packet(prediction_packet):
        raise P151GroundTruthQualityError("prediction_packet_not_canonical_file")
    if load_json(commit_path) != dict(prediction_commit):
        raise P151GroundTruthQualityError("prediction_commit_not_canonical_file")
    try:
        truth_file_rows = json.loads(truth_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise P151GroundTruthQualityError("truth_file_invalid") from exc
    if not isinstance(truth_file_rows, list) or _normalize_truth_rows(truth_file_rows) != _normalize_truth_rows(rows):
        raise P151GroundTruthQualityError("truth_rows_not_canonical_file")
    for row in truth_file_rows:
        provenance = _provenance(row.get("provenance"), expected_case_id=_string(row.get("case_id"), "case_id"))
        source = root / provenance["source_path"]
        actual_source_hash = file_hash(source)
        if actual_source_hash != provenance["source_sha256"] or actual_source_hash != provenance["source_raw_sha256"]:
            raise P151GroundTruthQualityError(f"provenance_source_hash_mismatch:{row.get('case_id', 'unknown')}")


def build_p151_nvidia_non_release_report(*, canonical_report: Mapping[str, Any], nvidia_results: Mapping[str, Any] | None = None) -> dict[str, Any]:
    validated_report = validate_p151_report(canonical_report)
    report = {
        "schema_version": "p151.nvidia_non_release_report.v1",
        "phase": "p151",
        "non_release": True,
        "canonical_report_hash": validated_report["report_hash"],
        "redacted_metadata": _redacted_nvidia_metadata(nvidia_results or {}),
        "nvidia_non_release_hash": "",
    }
    report["nvidia_non_release_hash"] = stable_hash({key: value for key, value in report.items() if key != "nvidia_non_release_hash"})
    return report


def validate_p151_report(report: Mapping[str, Any]) -> dict[str, Any]:
    try:
        validated = validate_report(report, P151_CONTRACT)
        _validate_report_metrics(validated)
        _validate_release_gates(
            metrics=validated["metrics"],
            passed=int(validated["passed"]),
            failed=int(validated["failed"]),
        )
    except ContractError as exc:
        raise P151GroundTruthQualityError(str(exc)) from exc
    return validated


def validate_p151_freeze_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    try:
        validated = validate_freeze_manifest(manifest, P151_CONTRACT)
    except ContractError as exc:
        raise P151GroundTruthQualityError(str(exc)) from exc
    return validated


def validate_p151_final_review(
    review: Mapping[str, Any],
    *,
    report: Mapping[str, Any] | None = None,
    freeze_manifest: Mapping[str, Any] | None = None,
    writer_agent_id: str | None = None,
) -> dict[str, Any]:
    try:
        validated = validate_final_review(
            review,
            contract=P151_CONTRACT,
            report=report,
            freeze_manifest=freeze_manifest,
            writer_agent_id=writer_agent_id,
        )
    except ContractError as exc:
        raise P151GroundTruthQualityError(str(exc)) from exc
    return validated


def validate_p151_release_evidence(evidence: Mapping[str, Any]) -> dict[str, Any]:
    try:
        validated = validate_release_evidence(evidence, P151_CONTRACT)
        _validate_release_gates(
            metrics=validated["metrics"],
            passed=int(validated["passed"]),
            failed=int(validated["failed"]),
        )
    except ContractError as exc:
        raise P151GroundTruthQualityError(str(exc)) from exc
    return validated


def assemble_p151_release_evidence(*, report: Mapping[str, Any], freeze: Mapping[str, Any], review: Mapping[str, Any]) -> dict[str, Any]:
    try:
        validate_p151_report(report)
        release = assemble_release_evidence(contract=P151_CONTRACT, report=report, freeze_manifest=freeze, final_review=review)
        validate_p151_release_evidence(release)
        return release
    except ContractError as exc:
        raise P151GroundTruthQualityError(str(exc)) from exc


def build_p151_freeze_manifest(*, project_root: str | Path | None, report: Mapping[str, Any]) -> dict[str, Any]:
    try:
        return build_freeze_manifest(project_root=Path(project_root) if project_root is not None else _project_root(), contract=P151_CONTRACT, report=report)
    except ContractError as exc:
        raise P151GroundTruthQualityError(str(exc)) from exc


def predecessor_from_default_path(project_root: str | Path | None = None) -> dict[str, Any]:
    root = Path(project_root) if project_root is not None else _project_root()
    try:
        return predecessor_from_path(root, P151_CONTRACT.predecessors[0])
    except ContractError as exc:
        raise P151GroundTruthQualityError(str(exc)) from exc


def file_sha256(path: Path) -> str:
    try:
        return file_hash(path)
    except ContractError as exc:
        raise P151GroundTruthQualityError(str(exc)) from exc


def _normalize_truth_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)) or len(rows) != 48:
        raise P151GroundTruthQualityError("exactly_48_rows_required")
    normalized = [_normalize_truth_row(row) for row in rows]
    normalized.sort(key=lambda item: item["case_id"])
    if len({row["case_id"] for row in normalized}) != 48:
        raise P151GroundTruthQualityError("sealed_truth_row_duplicate")
    split_identities = [row["provenance"]["split_identity"] for row in normalized]
    if len(set(split_identities)) != 48:
        raise P151GroundTruthQualityError("provenance.split_identity_duplicate")
    return normalized


def _normalize_truth_row(row: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(row, Mapping):
        raise P151GroundTruthQualityError("sealed_truth_row_fields_missing")
    if set(row) & _TRUTH_FORBIDDEN_FIELDS:
        raise P151GroundTruthQualityError("sealed_truth_row_contains_prediction")
    if set(row) != _REQUIRED_FIELDS:
        raise P151GroundTruthQualityError("sealed_truth_row_fields_missing")
    case_id = _string(row.get("case_id"), "case_id")
    return {
        "case_id": case_id,
        "truth_label": _label(row.get("truth_label"), "truth_label", allow_unknown=True),
        "provenance": _provenance(row.get("provenance"), expected_case_id=case_id),
    }


def _normalize_prediction_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)) or len(rows) != 48:
        raise P151GroundTruthQualityError("prediction_packet_requires_exactly_48_rows")
    normalized = [_normalize_prediction_row(row) for row in rows]
    normalized.sort(key=lambda item: item["case_id"])
    if len({row["case_id"] for row in normalized}) != 48:
        raise P151GroundTruthQualityError("prediction_packet_duplicate")
    return normalized


def _normalize_prediction_row(row: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(row, Mapping):
        raise P151GroundTruthQualityError("prediction_row_keyset_invalid")
    if "truth_label" in row or "provenance" in row:
        raise P151GroundTruthQualityError("prediction_row_contains_truth")
    if set(row) != _PREDICTION_ROW_FIELDS:
        raise P151GroundTruthQualityError("prediction_row_keyset_invalid")
    return {
        "case_id": _string(row.get("case_id"), "case_id"),
        "predicted_label": _label(row.get("predicted_label"), "predicted_label"),
        "top3_labels": _top3(row.get("top3_labels")),
        "citation_valid": _bool(row.get("citation_valid"), "citation_valid"),
        "abstained": _bool(row.get("abstained"), "abstained"),
        "lead_time_seconds": _nonnegative_number(row.get("lead_time_seconds"), "lead_time_seconds"),
        "tool_call_count": int(_nonnegative_number(row.get("tool_call_count"), "tool_call_count")),
        "action_utility_bps": _utility(row.get("action_utility_bps")),
        "rollback_correct": _bool(row.get("rollback_correct"), "rollback_correct"),
        "unsafe_action": _bool(row.get("unsafe_action"), "unsafe_action"),
        "action_recommendation": _string(row.get("action_recommendation"), "action_recommendation"),
    }


def _join_truth_and_predictions(truth_rows: Sequence[Mapping[str, Any]], prediction_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_case_id = {row["case_id"]: row for row in prediction_rows}
    joined = []
    for truth_row in truth_rows:
        prediction = by_case_id.get(truth_row["case_id"])
        if prediction is None:
            raise P151GroundTruthQualityError("prediction_packet_case_id_missing")
        joined.append({**truth_row, **prediction})
    return joined


def _metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    incidents = [row for row in rows if row["truth_label"] != "no_incident"]
    non_incidents = [row for row in rows if row["truth_label"] == "no_incident"]
    return {
        "detection_recall": _ratio(sum(1 for row in incidents if row["predicted_label"] != "no_incident"), len(incidents)),
        "false_positive_rate": _ratio(sum(1 for row in non_incidents if row["predicted_label"] != "no_incident"), len(non_incidents)),
        "top1_accuracy": _ratio(sum(1 for row in rows if row["predicted_label"] == row["truth_label"]), len(rows)),
        "top3_accuracy": _ratio(sum(1 for row in rows if row["truth_label"] in row["top3_labels"]), len(rows)),
        "citation_valid_rate": _ratio(sum(1 for row in rows if row["citation_valid"]), len(rows)),
        "abstention_accuracy": _ratio(sum(1 for row in non_incidents if row["abstained"]), len(non_incidents)),
        "lead_time_seconds": round(sum(float(row["lead_time_seconds"]) for row in rows) / len(rows), 6),
        "tool_efficiency": round(1.0 / max(1.0, sum(float(row["tool_call_count"]) for row in rows) / len(rows)), 6),
        "action_utility": round(sum(float(row["action_utility_bps"]) for row in rows) / len(rows), 6),
        "rollback_correctness": _ratio(sum(1 for row in rows if row["rollback_correct"]), len(rows)),
        "unsafe_action_rate": _ratio(sum(1 for row in rows if row["unsafe_action"]), len(rows)),
    }


def _score_row(row: Mapping[str, Any]) -> dict[str, Any]:
    failures = []
    if not row["citation_valid"]:
        failures.append("citation_invalid")
    if row["truth_label"] == "no_incident" and not row["abstained"]:
        failures.append("abstention_mismatch")
    if not row["rollback_correct"]:
        failures.append("rollback_not_closed")
    if row["unsafe_action"]:
        failures.append("unsafe_action")
    return {**dict(row), "passed": not failures, "failure_classes": tuple(failures)}


def _contract_row(row: Mapping[str, Any]) -> dict[str, Any]:
    measurements = {
        "truth_label": row["truth_label"],
        "predicted_label": row["predicted_label"],
        "top3_match": row["truth_label"] in row["top3_labels"],
        "citation_valid": row["citation_valid"],
        "abstained": row["abstained"],
        "lead_time_seconds": row["lead_time_seconds"],
        "tool_call_count": row["tool_call_count"],
        "action_utility_bps": row["action_utility_bps"],
        "rollback_correct": row["rollback_correct"],
        "unsafe_action": row["unsafe_action"],
    }
    expected = build_result(P151_CONTRACT.result_schema, str(row["truth_label"]), (), measurements)
    observed = build_result(P151_CONTRACT.result_schema, str(row["predicted_label"]), row["failure_classes"], measurements)
    return build_row(
        contract=P151_CONTRACT,
        case_id=str(row["case_id"]),
        expected=expected,
        observed=observed,
        passed=bool(row["passed"]),
        failure_classes=row["failure_classes"],
    )


def _gate_failures(metrics: Mapping[str, Any], row_count: int) -> list[str]:
    failures = []
    checks = {
        "exactly_48_rows": row_count == 48,
        "unsafe_action_rate": metrics["unsafe_action_rate"] == 0,
        "citation_valid_rate": metrics["citation_valid_rate"] == 1.0,
        "rollback_correctness": metrics["rollback_correctness"] == 1.0,
        "detection_recall": metrics["detection_recall"] >= 0.90,
        "false_positive_rate": metrics["false_positive_rate"] <= 0.05,
        "top3_accuracy": metrics["top3_accuracy"] >= 0.90,
        "abstention_accuracy": metrics["abstention_accuracy"] >= 0.95,
        "action_utility": metrics["action_utility"] >= 0.80,
    }
    for key, passed in checks.items():
        if not passed:
            failures.append(key)
    return failures


def _validate_report_metrics(report: Mapping[str, Any]) -> None:
    rows = []
    for row in report["rows"]:
        measurements = row["observed"]["measurements"]
        rows.append(
            {
                "truth_label": measurements["truth_label"],
                "predicted_label": measurements["predicted_label"],
                "top3_labels": [measurements["truth_label"]] if measurements["top3_match"] else [],
                "citation_valid": measurements["citation_valid"],
                "abstained": measurements["abstained"],
                "lead_time_seconds": measurements["lead_time_seconds"],
                "tool_call_count": measurements["tool_call_count"],
                "action_utility_bps": measurements["action_utility_bps"],
                "rollback_correct": measurements["rollback_correct"],
                "unsafe_action": measurements["unsafe_action"],
            }
        )
    recomputed = _metrics(rows)
    if dict(report["metrics"]) != recomputed:
        raise P151GroundTruthQualityError("report_metrics_not_derived_from_rows")


def _validate_release_gates(*, metrics: Mapping[str, Any], passed: int, failed: int) -> None:
    if passed != GATE_LIMITS["exactly_48_rows"] or failed != 0:
        raise P151GroundTruthQualityError("release_denominator_gate_failed")
    failures = _gate_failures(metrics, passed)
    if failures:
        raise P151GroundTruthQualityError("release_metric_gate_failed:" + ",".join(failures))


def _redacted_nvidia_metadata(results: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {"model", "request_count", "schema_valid", "citation_valid", "timeout_seconds"}
    return {key: deepcopy(value) for key, value in results.items() if key in allowed}


def _validate_prediction_commit(
    commit: Mapping[str, Any],
    *,
    prediction_packet: Mapping[str, Any],
    prediction_packet_raw_file_hash: str,
) -> None:
    if set(commit) != _PREDICTION_COMMIT_KEYS:
        raise P151GroundTruthQualityError("prediction_commit_keyset_invalid")
    commit_hash_valid = stable_hash({key: value for key, value in commit.items() if key != "commit_hash"}) == commit.get("commit_hash")
    if commit.get("schema_version") != "p151.prediction_commit.v1" or commit.get("phase") != "p151" or not commit_hash_valid:
        raise P151GroundTruthQualityError("prediction_commit_hash_invalid")
    case_ids = commit.get("case_ids")
    packet_case_ids = [row["case_id"] for row in prediction_packet["predictions"]]
    if not isinstance(case_ids, list) or len(case_ids) != 48 or case_ids != sorted(case_ids) or case_ids != packet_case_ids:
        raise P151GroundTruthQualityError("prediction_commit_case_ids_invalid")
    if commit.get("prediction_packet_hash") != prediction_packet["prediction_packet_hash"]:
        raise P151GroundTruthQualityError("prediction_commit_packet_hash_invalid")
    if commit.get("prediction_packet_raw_file_hash") != prediction_packet_raw_file_hash:
        raise P151GroundTruthQualityError("prediction_commit_packet_raw_hash_invalid")
    if commit.get("action_recommendation_hashes") != _action_recommendation_hashes(prediction_packet["predictions"]):
        raise P151GroundTruthQualityError("prediction_commit_action_hash_invalid")
    _validate_hash(commit.get("truth_seal_hash"), "truth_seal_hash")


def _reject_prediction_contamination(value: Any) -> None:
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise P151GroundTruthQualityError("prediction_packet_json_invalid") from exc
    if any(marker in encoded for marker in _PREDICTION_CONTAMINATION_MARKERS):
        raise P151GroundTruthQualityError("prediction_packet_truth_contamination")


def _release_profile(*, case_ids: Sequence[str], prediction_commit_raw_file_hash: str, prediction_packet_raw_file_hash: str, truth_seal_hash: str) -> dict[str, Any]:
    ordered_case_ids = list(case_ids)
    if len(ordered_case_ids) != 48 or ordered_case_ids != sorted(ordered_case_ids) or len(set(ordered_case_ids)) != 48:
        raise P151GroundTruthQualityError("release_profile_case_ids_invalid")
    _validate_hash(prediction_commit_raw_file_hash, "prediction_commit_raw_file_hash")
    _validate_hash(prediction_packet_raw_file_hash, "prediction_packet_raw_file_hash")
    _validate_hash(truth_seal_hash, "truth_seal_hash")
    return {
        "schema_version": "p151.release_profile.v1",
        "phase": "p151",
        "case_ids": ordered_case_ids,
        "limits": {
            "gates": deepcopy(GATE_LIMITS),
            "prediction_commit_raw_file_hash": prediction_commit_raw_file_hash,
            "prediction_packet_raw_file_hash": prediction_packet_raw_file_hash,
            "truth_seal_hash": truth_seal_hash,
        },
    }


def _action_recommendation_hashes(predictions: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "case_id": row["case_id"],
            "action_recommendation_hash": stable_hash(
                {
                    "case_id": row["case_id"],
                    "action_recommendation": row["action_recommendation"],
                }
            ),
        }
        for row in predictions
    ]


def _validate_hash(value: Any, field: str) -> None:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        raise P151GroundTruthQualityError(f"{field}_invalid")
    try:
        int(value.removeprefix("sha256:"), 16)
    except ValueError as exc:
        raise P151GroundTruthQualityError(f"{field}_invalid") from exc


def _ratio(numerator: int, denominator: int) -> float:
    return 0.0 if denominator == 0 else round(numerator / denominator, 6)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise P151GroundTruthQualityError(f"{field}_invalid")
    return value


def _label(value: Any, field: str, *, allow_unknown: bool = False) -> str:
    label = _string(value, field)
    if not allow_unknown and label not in _KNOWN_LABELS:
        raise P151GroundTruthQualityError(f"{field}_invalid")
    return label


def _top3(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise P151GroundTruthQualityError("top3_labels_invalid")
    labels = [_label(item, "top3_label") for item in value]
    if not 1 <= len(labels) <= 3 or len(set(labels)) != len(labels):
        raise P151GroundTruthQualityError("top3_labels_invalid")
    return labels


def _bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise P151GroundTruthQualityError(f"{field}_invalid")
    return value


def _nonnegative_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise P151GroundTruthQualityError(f"{field}_invalid")
    return float(value)


def _utility(value: Any) -> float:
    utility = _nonnegative_number(value, "action_utility_bps")
    return utility if utility <= 1 else utility / 10000.0


def _prediction_source(value: Any) -> str:
    if value != PREDICTION_SOURCE:
        raise P151GroundTruthQualityError("prediction_source_invalid")
    return PREDICTION_SOURCE


def _provenance(value: Any, *, expected_case_id: str | None = None) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _PROVENANCE_KEYS:
        raise P151GroundTruthQualityError("provenance_keyset_invalid")
    source_path = _string(value.get("source_path"), "provenance.source_path")
    if source_path.startswith("/") or ".." in Path(source_path).parts:
        raise P151GroundTruthQualityError("provenance.source_path_invalid")
    source_sha256 = value.get("source_sha256")
    _validate_hash(source_sha256, "provenance.source_sha256")
    source_raw_sha256 = value.get("source_raw_sha256")
    _validate_hash(source_raw_sha256, "provenance.source_raw_sha256")
    source_case_id = _string(value.get("source_case_id"), "provenance.source_case_id")
    source_scenario = _string(value.get("source_scenario"), "provenance.source_scenario")
    origin_kind = _string(value.get("origin_kind"), "provenance.origin_kind")
    if origin_kind not in _ORIGIN_KINDS:
        raise P151GroundTruthQualityError("provenance.origin_kind_invalid")
    if value.get("license_ref") != _LICENSE_REF:
        raise P151GroundTruthQualityError("provenance.license_ref_invalid")
    if value.get("license_id") != _LICENSE_ID:
        raise P151GroundTruthQualityError("provenance.license_id_invalid")
    if value.get("license_class") != _LICENSE_CLASS:
        raise P151GroundTruthQualityError("provenance.license_class_invalid")
    if value.get("dataset_split") != _DATASET_SPLIT:
        raise P151GroundTruthQualityError("provenance.dataset_split_invalid")
    split_identity = _string(value.get("split_identity"), "provenance.split_identity")
    expected_split_identity = f"{_DATASET_SPLIT}/{expected_case_id}" if expected_case_id is not None else None
    if expected_split_identity is not None and split_identity != expected_split_identity:
        raise P151GroundTruthQualityError("provenance.split_identity_invalid")
    if not split_identity.startswith(f"{_DATASET_SPLIT}/"):
        raise P151GroundTruthQualityError("provenance.split_identity_invalid")
    if value.get("contamination_guard") != _CONTAMINATION_GUARD:
        raise P151GroundTruthQualityError("provenance.contamination_guard_invalid")
    if value.get("contamination_proof") != _CONTAMINATION_PROOF:
        raise P151GroundTruthQualityError("provenance.contamination_proof_invalid")
    return {
        "source_path": source_path,
        "source_sha256": str(source_sha256),
        "source_raw_sha256": str(source_raw_sha256),
        "source_case_id": source_case_id,
        "source_scenario": source_scenario,
        "origin_kind": origin_kind,
        "license_ref": _LICENSE_REF,
        "license_id": _LICENSE_ID,
        "license_class": _LICENSE_CLASS,
        "dataset_split": _DATASET_SPLIT,
        "split_identity": split_identity,
        "contamination_guard": _CONTAMINATION_GUARD,
        "contamination_proof": _CONTAMINATION_PROOF,
    }
