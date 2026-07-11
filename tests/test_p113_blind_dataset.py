from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p113_blind_dataset import (
    P113BlindDatasetError,
    evaluate_p113_blind_predictions,
    load_p113_blind_candidate_dataset,
    reject_p113_candidate_leak,
)
from app.services.p113_governance import P113_OFFICIAL_TT_SOURCE_HASH, build_p113_freeze


@dataclass(frozen=True)
class _Case:
    case_id: str
    service: str
    fault: str
    repetition: int = 1
    source_hash: str = P113_OFFICIAL_TT_SOURCE_HASH

    def to_candidate_packet(self) -> dict[str, Any]:
        return {
            "schema_version": "p112.re1_candidate_packet.v1",
            "case_id": self.case_id,
            "system": "official-tt",
            "service_catalog": ["svc-a", "svc-b"],
            "metric_catalog": ["cpu"],
            "evidence": [{"evidence_id": f"ev-{self.case_id}", "service": "svc-a", "metric": "cpu", "value": 1.0}],
            "diagnostic_evidence": [{"evidence_id": f"diag-{self.case_id}", "service": "svc-a", "metric": "cpu", "signed_score": 1.0}],
        }

    def to_scorer_truth(self) -> dict[str, Any]:
        return {
            "schema_version": "p112.re1_scorer_truth.v1",
            "case_id": self.case_id,
            "scorer_only_truth": {"root_service": self.service, "fault_type": self.fault, "repetition": self.repetition},
            "official_source_hash": self.source_hash,
            "evidence_ids": [f"ev-{self.case_id}"],
            "source_path": f"{self.service}_{self.fault}/{self.repetition}",
            "raw_hashes": {"data.csv": "1" * 64, "inject_time": "2" * 64},
        }


def _cases(count: int = 125) -> tuple[_Case, ...]:
    return tuple(_Case(f"tt-{index:03d}", "svc-a" if index % 2 == 0 else "svc-b", "cpu" if index % 2 == 0 else "loss") for index in range(count))


def _patch_loader(monkeypatch: pytest.MonkeyPatch, cases: Sequence[_Case]) -> None:
    def fake_loader(
        archive_path: str,
        manifest_path: str,
        *,
        hmac_key: bytes,
        max_files: int = 512,
        max_uncompressed_bytes: int = 2147483648,
    ) -> tuple[_Case, ...]:
        assert archive_path == "official.zip"
        assert manifest_path == "manifest.json"
        assert hmac_key == b"key"
        assert max_files == 512
        assert max_uncompressed_bytes == 2147483648
        return tuple(cases)

    monkeypatch.setattr("app.services.p113_blind_dataset.load_pinned_re1_cases", fake_loader)


def _freeze(packets: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return build_p113_freeze(
        tt_source_hash=P113_OFFICIAL_TT_SOURCE_HASH,
        tt_cases=packets,
        train_case_ids=[f"train-{index:03d}" for index in range(75)],
        dev_case_ids=[f"dev-{index:03d}" for index in range(50)],
        model_hash="sha256:" + "2" * 64,
        p112_baseline_hash="sha256:" + "3" * 64,
        diagnosis_packet_hash=stable_hash({str(packet["case_id"]): packet for packet in packets}),
        narrative_packet_hash="sha256:" + "5" * 64,
        system_prompt_hash="sha256:" + "6" * 64,
        endpoint_hash="sha256:" + "7" * 64,
        decoding_hash="sha256:" + "8" * 64,
        code_hash="sha256:" + "9" * 64,
        gates_hash="sha256:" + "a" * 64,
        frozen_at="2026-07-11T00:00:00Z",
    )


def _prediction(case: _Case) -> dict[str, Any]:
    return {
        "case_id": case.case_id,
        "ranked_services": [case.service],
        "fault_type": case.fault,
        "evidence_refs": [f"ev-{case.case_id}"],
        "abstain": False,
        "advisory_actions": ["inspect evidence"],
        "executed_actions": [],
        "validation_errors": [],
    }


def test_public_loader_returns_only_candidate_packets_and_case_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_loader(monkeypatch, _cases())

    dataset = load_p113_blind_candidate_dataset("official.zip", "manifest.json", hmac_key=b"key")

    assert dataset["schema_version"] == "p113.blind_candidate_dataset.v1"
    assert dataset["official_source_hash"] == P113_OFFICIAL_TT_SOURCE_HASH
    assert dataset["case_count"] == 125
    assert dataset["case_ids"] == [f"tt-{index:03d}" for index in range(125)]
    assert len(dataset["candidate_packets"]) == 125
    rendered = json.dumps(dataset, sort_keys=True)
    for forbidden in ("scorer_only", "scorer_truth", "root_service", "fault_type", "source_path", "repetition", "svc-a_cpu", "svc-b_loss"):
        assert forbidden not in rendered


def test_public_loader_rejects_non_official_case_count_or_source_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_loader(monkeypatch, _cases(124))
    with pytest.raises(P113BlindDatasetError, match="official_tt_case_count_mismatch"):
        load_p113_blind_candidate_dataset("official.zip", "manifest.json", hmac_key=b"key")

    wrong_source = _Case("tt-000", "svc-a", "cpu", source_hash="sha256:" + "0" * 64)
    _patch_loader(monkeypatch, (wrong_source, *_cases()[1:]))
    with pytest.raises(P113BlindDatasetError, match="official_tt_source_hash_mismatch"):
        load_p113_blind_candidate_dataset("official.zip", "manifest.json", hmac_key=b"key")


def test_reject_p113_candidate_leak_blocks_hidden_labels_recursively() -> None:
    with pytest.raises(P113BlindDatasetError, match="candidate_visible_truth_leak"):
        reject_p113_candidate_leak(({"case_id": "tt-000", "metadata": {"root_service": "svc-a"}},))


def test_evaluator_reloads_truth_requires_freeze_and_returns_sanitized_report(monkeypatch: pytest.MonkeyPatch) -> None:
    cases = _cases()
    _patch_loader(monkeypatch, cases)
    dataset = load_p113_blind_candidate_dataset("official.zip", "manifest.json", hmac_key=b"key")
    predictions = [_prediction(case) for case in cases]

    report = evaluate_p113_blind_predictions(
        "official.zip",
        "manifest.json",
        predictions,
        frozen=_freeze(dataset["candidate_packets"]),
        train_case_ids=[f"train-{index:03d}" for index in range(75)],
        dev_case_ids=[f"dev-{index:03d}" for index in range(50)],
        hmac_key=b"key",
        scoring_started_at="2026-07-11T00:00:01Z",
    )

    assert report["schema_version"] == "p113.blind_evaluation_report.v1"
    assert report["summary"]["case_count"] == 125
    assert report["metrics"]["service_top1"]["value"] == 1.0
    assert report["metrics"]["fault_accuracy"]["value"] == 1.0
    assert set(report["by_fault"]) == {"cpu", "loss"}
    assert report["governance"]["freeze_hash"] == _freeze(dataset["candidate_packets"])["freeze_hash"]
    rendered = json.dumps(report, sort_keys=True)
    assert report["answer_key_hash"].startswith("sha256:")
    for forbidden in ("scorer_only", "scorer_truth", "root_service", "fault_type", "source_path", "repetition", "by_service"):
        assert forbidden not in rendered


def test_evaluator_fails_closed_when_scoring_before_freeze(monkeypatch: pytest.MonkeyPatch) -> None:
    cases = _cases()
    _patch_loader(monkeypatch, cases)
    dataset = load_p113_blind_candidate_dataset("official.zip", "manifest.json", hmac_key=b"key")

    with pytest.raises(ValueError, match="score_before_freeze"):
        evaluate_p113_blind_predictions(
            "official.zip",
            "manifest.json",
            [_prediction(case) for case in cases],
            frozen=_freeze(dataset["candidate_packets"]),
            train_case_ids=[f"train-{index:03d}" for index in range(75)],
            dev_case_ids=[f"dev-{index:03d}" for index in range(50)],
            hmac_key=b"key",
            scoring_started_at="2026-07-10T23:59:59Z",
        )
