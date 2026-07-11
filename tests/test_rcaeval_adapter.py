from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.services.rcaeval_adapter import (
    RCAEvalNormalizationError,
    candidate_context_jsonl,
    load_rcaeval_cases,
    normalize_rcaeval_cases,
    write_candidate_jsonl,
    write_scorer_truth_jsonl,
)

FIXTURE_ROOT = Path("tests/fixtures/p109/rcaeval")


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_normalizes_rcaeval_case_with_physical_truth_separation_and_raw_hashes(tmp_path: Path) -> None:
    cases = load_rcaeval_cases(FIXTURE_ROOT / "cases")

    assert [case.case_id for case in cases] == ["checkout-001"]
    case = cases[0]
    public = case.to_candidate_dict()
    assert public["schema_version"] == "p109.rcaeval_case.v1"
    assert "candidate_visible_evidence" in public
    assert "scorer_only_truth" not in public
    assert "truth_available" not in public
    assert "release_qualifying_truth" not in public
    assert "qualification" not in public
    assert "scorer_truth_ref" not in public
    assert "fault_family" not in public
    normalized = case.to_normalized_dict()
    assert normalized["truth_available"] is True
    assert normalized["release_qualifying_truth"] is False
    assert normalized["qualification"]["reason"] == "fixture_source_revision_not_release_qualified"
    assert normalized["scorer_truth_ref"] == {"truth_id": "checkout-001:truth", "sha256": case.scorer_truth_sha256}
    assert {obs["modality"] for obs in public["candidate_visible_evidence"]} == {"log", "metric", "trace"}
    assert all(obs["raw_sha256"] for obs in public["candidate_visible_evidence"])
    assert set(public["raw_hashes"]) == {"logs.jsonl", "metrics.csv", "topology.json", "traces.jsonl"}
    assert "truth.json" not in public["raw_hashes"]
    assert "truth.json" in normalized["raw_hashes"]

    candidate_path = tmp_path / "candidate.jsonl"
    truth_path = tmp_path / "truth.jsonl"
    write_candidate_jsonl(cases, candidate_path)
    write_scorer_truth_jsonl(cases, truth_path)

    candidate_rows = _jsonl(candidate_path)
    truth_rows = _jsonl(truth_path)
    assert set(candidate_rows[0]) == {"schema_version", "case_id", "candidate_visible_evidence"}
    assert "scorer_only_truth" not in candidate_rows[0]
    assert "scorer_truth_ref" not in candidate_rows[0]
    assert truth_rows[0]["scorer_only_truth"]["root_service"] == "checkout"


def test_candidate_context_is_deterministic_and_contains_no_truth_handle_resolution() -> None:
    cases = load_rcaeval_cases(FIXTURE_ROOT / "cases")
    first = candidate_context_jsonl(cases)
    second = candidate_context_jsonl(load_rcaeval_cases(FIXTURE_ROOT / "cases"))

    assert first == second
    assert "truth.json" not in first
    assert cases[0].raw_hashes["truth.json"] not in first
    assert '"scorer_only_truth"' not in first
    assert '"root_service"' not in first
    assert '"fault_type"' not in first
    assert first.endswith("\n")


def test_candidate_writer_strips_adversarial_scorer_metadata(tmp_path: Path) -> None:
    cases = load_rcaeval_cases(FIXTURE_ROOT / "cases")
    path = tmp_path / "candidate.jsonl"

    write_candidate_jsonl(cases, path)
    content = path.read_text(encoding="utf-8")
    row = json.loads(content)

    forbidden_tokens = (
        "truth_available",
        "release_qualifying_truth",
        "real_telemetry_smoke_only",
        "scorer_truth_ref",
        "scorer_truth_sha256",
        "qualification",
        "release_qualified",
        "fixture_source_revision_not_release_qualified",
        "fault_family",
        "checkout:truth",
        "root_service",
        "fault_type",
        "scorer_only_truth",
    )
    truth_hash = cases[0].raw_hashes["truth.json"]
    assert set(row) == {"schema_version", "case_id", "candidate_visible_evidence"}
    assert all(token not in content for token in forbidden_tokens)
    assert "truth.json" not in content
    assert "truth" not in content
    assert truth_hash not in content


def test_normalized_jsonl_and_corpus_hash_are_byte_stable(tmp_path: Path) -> None:
    first_path = tmp_path / "first.jsonl"
    second_path = tmp_path / "second.jsonl"

    first = normalize_rcaeval_cases(FIXTURE_ROOT / "cases", output_jsonl=first_path)
    second = normalize_rcaeval_cases(FIXTURE_ROOT / "cases", output_jsonl=second_path)

    assert first.normalized_corpus_sha256 == second.normalized_corpus_sha256
    assert first_path.read_bytes() == second_path.read_bytes()
    assert first.to_dict()["cases"][0]["raw_hashes"] == second.to_dict()["cases"][0]["raw_hashes"]


def test_rejects_nested_candidate_visible_truth_leak(tmp_path: Path) -> None:
    case_dir = tmp_path / "leaky-001"
    case_dir.mkdir()
    (case_dir / "metrics.csv").write_text("timestamp,service,metric,value\n2024-03-09T16:30:00Z,api,latency,100\n", encoding="utf-8")
    (case_dir / "traces.jsonl").write_text(
        json.dumps(
            {
                "timestamp": "2024-03-09T16:30:01Z",
                "service": "api",
                "trace_id": "t1",
                "span_id": "s1",
                "attributes": {"root_cause": "db_pool_exhaustion"},
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (case_dir / "truth.json").write_text(json.dumps({"case_id": "leaky-001", "root_service": "api", "fault_type": "db_pool_exhaustion"}), encoding="utf-8")

    with pytest.raises(RCAEvalNormalizationError, match="candidate_visible_truth_leak"):
        load_rcaeval_cases(tmp_path)


def test_simple_data_csv_is_real_telemetry_smoke_only_without_fabricated_truth() -> None:
    cases = load_rcaeval_cases(FIXTURE_ROOT / "simple_data")

    assert [case.case_id for case in cases] == ["simple_data"]
    case = cases[0]
    public = case.to_candidate_dict()
    assert public["source_id"] == "rcaeval.simple_data"
    assert "truth_available" not in public
    assert "release_qualifying_truth" not in public
    assert "real_telemetry_smoke_only" not in public
    assert "scorer_truth_ref" not in public
    normalized = case.to_normalized_dict()
    assert normalized["truth_available"] is False
    assert normalized["release_qualifying_truth"] is False
    assert normalized["real_telemetry_smoke_only"] is True
    assert normalized["scorer_truth_ref"] is None
    assert case.scorer_only_truth is None
    assert {obs["service"] for obs in public["candidate_visible_evidence"]} == {"inventory"}


def test_upstream_simple_data_wide_csv_is_smoke_only_with_epoch_utc_timestamps() -> None:
    cases = load_rcaeval_cases(Path("evals/real_datasets/external/p109/simple_data.csv"), source_revision="upstream-baro-rcaeval-simple-data")

    assert [case.case_id for case in cases] == ["simple_data"]
    case = cases[0]
    public = case.to_candidate_dict()
    observations = public["candidate_visible_evidence"]

    assert "truth_available" not in public
    assert "release_qualifying_truth" not in public
    assert "real_telemetry_smoke_only" not in public
    assert public["raw_hashes"]["simple_data.csv"]
    assert len(observations) > 1000
    assert observations[0]["timestamp"] == "2023-08-20T22:02:59Z"
    assert observations[0]["service"] == "adservice"
    assert observations[0]["metric"] == "cpu"
    assert observations[0]["raw_line"] == 2
    assert observations[0]["raw_column"] == "adservice_cpu"
    frontend_external = [obs for obs in observations if obs["raw_column"] == "frontend-external_workload"]
    assert frontend_external
    assert frontend_external[0]["service"] == "frontend-external"
    assert frontend_external[0]["metric"] == "workload"


def test_rejects_mismatched_truth_case_directory(tmp_path: Path) -> None:
    case_dir = tmp_path / "case-a"
    case_dir.mkdir()
    (case_dir / "metrics.csv").write_text("timestamp,service,metric,value\n2024-03-09T16:30:00Z,api,latency,100\n", encoding="utf-8")
    (case_dir / "truth.json").write_text(json.dumps({"case_id": "case-b", "root_service": "api", "fault_type": "timeout"}), encoding="utf-8")

    with pytest.raises(RCAEvalNormalizationError, match="mismatched_case_directory"):
        load_rcaeval_cases(tmp_path)
