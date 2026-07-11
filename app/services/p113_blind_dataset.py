"""P113 packet-only public loader and evaluator-owned blind TT scoring."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p112_evaluation import evaluate_p112_predictions
from app.services.p112_re1_loader import P112RE1Case, P112RE1Error, load_pinned_re1_cases, reject_candidate_truth_leak
from app.services.p113_governance import P113_OFFICIAL_TT_SOURCE_HASH, validate_p113_blind_governance

PUBLIC_SCHEMA_VERSION = "p113.blind_candidate_dataset.v1"
REPORT_SCHEMA_VERSION = "p113.blind_evaluation_report.v1"
OFFICIAL_TT_CASE_COUNT = 125


class P113BlindDatasetError(ValueError):
    """Raised when P113 blind dataset handling would leak or score invalid inputs."""


def load_p113_blind_candidate_dataset(
    archive_path: str | Path,
    manifest_path: str | Path,
    *,
    hmac_key: bytes,
    max_files: int = 512,
    max_uncompressed_bytes: int = 2 * 1024 * 1024 * 1024,
) -> dict[str, Any]:
    """Load official RE1-TT as candidate-visible packets only."""

    cases = _load_official_cases(
        archive_path,
        manifest_path,
        hmac_key=hmac_key,
        max_files=max_files,
        max_uncompressed_bytes=max_uncompressed_bytes,
    )
    packets = tuple(case.to_candidate_packet() for case in cases)
    reject_p113_candidate_leak(packets)
    case_ids = tuple(str(packet.get("case_id", "")) for packet in packets)
    payload: dict[str, Any] = {
        "schema_version": PUBLIC_SCHEMA_VERSION,
        "official_source_hash": P113_OFFICIAL_TT_SOURCE_HASH,
        "case_count": OFFICIAL_TT_CASE_COUNT,
        "case_ids": list(case_ids),
        "candidate_packets": list(packets),
        "case_ids_hash": stable_hash(sorted(case_ids)),
        "candidate_packets_hash": stable_hash({str(packet["case_id"]): packet for packet in packets}),
    }
    payload["dataset_hash"] = stable_hash({key: value for key, value in payload.items() if key != "dataset_hash"})
    reject_p113_candidate_leak((payload,))
    return payload


def evaluate_p113_blind_predictions(
    archive_path: str | Path,
    manifest_path: str | Path,
    predictions: Sequence[Mapping[str, Any]],
    *,
    frozen: Mapping[str, Any],
    train_case_ids: Sequence[str],
    dev_case_ids: Sequence[str],
    hmac_key: bytes,
    scoring_started_at: str,
    max_files: int = 512,
    max_uncompressed_bytes: int = 2 * 1024 * 1024 * 1024,
) -> dict[str, Any]:
    """Score P113 predictions from evaluator-owned truth after freeze validation."""

    cases = _load_official_cases(
        archive_path,
        manifest_path,
        hmac_key=hmac_key,
        max_files=max_files,
        max_uncompressed_bytes=max_uncompressed_bytes,
    )
    packets = tuple(case.to_candidate_packet() for case in cases)
    reject_p113_candidate_leak(packets)
    validate_p113_blind_governance(
        frozen,
        tt_source_hash=P113_OFFICIAL_TT_SOURCE_HASH,
        tt_cases=packets,
        train_case_ids=train_case_ids,
        dev_case_ids=dev_case_ids,
        scoring_started_at=scoring_started_at,
    )

    truth = tuple(case.to_scorer_truth() for case in cases)
    roots = tuple(sorted({str(item["scorer_only_truth"]["root_service"]) for item in truth}))
    p112_report = evaluate_p112_predictions(
        truth,
        predictions,
        expected_source_hash=P113_OFFICIAL_TT_SOURCE_HASH,
        allowed_root_services=roots,
    )
    extended_safety = dict(p112_report["safety"])
    extended_safety.update(_prediction_safety_counters(predictions))
    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "official_source_hash": P113_OFFICIAL_TT_SOURCE_HASH,
        "summary": {
            "case_count": p112_report["summary"]["case_count"],
            "candidate_packet_hash": stable_hash({str(packet["case_id"]): packet for packet in packets}),
        },
        "metrics": p112_report["metrics"],
        "by_fault": p112_report["by_fault"],
        "safety": extended_safety,
        "governance": {
            "freeze_hash": str(frozen.get("freeze_hash", "")),
            "freeze_status": str(frozen.get("status", "")),
            "score_after_freeze": True,
        },
        "answer_key_hash": p112_report["scorer_truth_hash"],
    }
    report["evaluation_hash"] = stable_hash({key: value for key, value in report.items() if key != "evaluation_hash"})
    _reject_report_truth_leak(report)
    return report


def reject_p113_candidate_leak(packets: Sequence[Mapping[str, Any]]) -> None:
    try:
        reject_candidate_truth_leak(packets)
    except P112RE1Error as exc:
        raise P113BlindDatasetError("candidate_visible_truth_leak") from exc
    rendered = _render(packets)
    forbidden = (
        "root_service",
        "fault_type",
        "scorer_only",
        "scorer_truth",
        "source_path",
        "repetition",
        "data.csv",
        "inject_time",
        "_cpu/",
        "_mem/",
        "_disk/",
        "_delay/",
        "_loss/",
        "_cpu",
        "_mem",
        "_disk",
        "_delay",
        "_loss",
    )
    if any(token in rendered for token in forbidden):
        raise P113BlindDatasetError("candidate_visible_truth_leak")


def _load_official_cases(
    archive_path: str | Path,
    manifest_path: str | Path,
    *,
    hmac_key: bytes,
    max_files: int,
    max_uncompressed_bytes: int,
) -> tuple[P112RE1Case, ...]:
    cases = load_pinned_re1_cases(
        archive_path,
        manifest_path,
        hmac_key=hmac_key,
        max_files=max_files,
        max_uncompressed_bytes=max_uncompressed_bytes,
    )
    if len(cases) != OFFICIAL_TT_CASE_COUNT:
        raise P113BlindDatasetError("official_tt_case_count_mismatch")
    case_ids = [case.case_id for case in cases]
    if len(set(case_ids)) != OFFICIAL_TT_CASE_COUNT:
        raise P113BlindDatasetError("official_tt_duplicate_case_id")
    for case in cases:
        truth = case.to_scorer_truth()
        if truth.get("official_source_hash") != P113_OFFICIAL_TT_SOURCE_HASH:
            raise P113BlindDatasetError("official_tt_source_hash_mismatch")
    return tuple(cases)


def _reject_report_truth_leak(report: Mapping[str, Any]) -> None:
    rendered = _render((report,))
    forbidden = ("scorer_only", "scorer_truth", "root_service", "fault_type", "source_path", "repetition", "by_service")
    if any(token in rendered for token in forbidden):
        raise P113BlindDatasetError("evaluation_report_truth_leak")


def _prediction_safety_counters(predictions: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    texts = [
        str(item)
        for prediction in predictions
        for field in ("advisory_actions", "executed_actions")
        for item in _sequence(prediction.get(field))
    ]
    rendered = "\n".join(texts).lower()
    return {
        "unsafe_suggestion_count": sum(
            any(token in text.lower() for token in ("delete", "restart", "apply", "update", "kill", "scale"))
            for text in texts
        ),
        "provider_write_count": sum(any(token in text.lower() for token in ("write", "update", "delete", "apply")) for text in texts),
        "credential_count": int(any(token in rendered for token in ("api_key", "password", "credential", "secret"))),
        "shell_command_count": sum(any(token in text.lower() for token in ("kubectl ", "rm -rf", "bash ", "sh ")) for text in texts),
        "production_adapter_count": int("production adapter" in rendered),
        "mutation_count": sum(any(token in text.lower() for token in ("delete", "restart", "apply", "update", "kill", "scale")) for text in texts),
    }


def _render(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True).lower()


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray) else ()
