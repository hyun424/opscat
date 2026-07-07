from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.real_dataset_evaluation import (
    convert_dataset_sample,
    load_dataset_source_manifest,
    map_external_label,
    render_real_dataset_evaluation_markdown,
    run_real_dataset_evaluation,
)


def test_p12_manifest_declares_sources_without_downloads() -> None:
    manifest = load_dataset_source_manifest("evals/real_datasets/fixtures/manifest.json")
    payload = manifest.to_dict()

    assert payload["normal_verification_downloads"] is False
    assert {item["family"] for item in payload["sources"]} >= {"loghub", "nab", "aiops"}
    assert all(item["expected_local_path"] for item in payload["sources"])
    assert all("license" in item for item in payload["sources"])
    assert "local path import" in payload["boundary"].lower()


def test_p12_import_contract_rejects_remote_paths_and_reports_missing_local_path(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="remote paths are not allowed"):
        convert_dataset_sample("https://example.com/logs.jsonl", family="loghub")
    with pytest.raises(FileNotFoundError, match="dataset path does not exist"):
        convert_dataset_sample(tmp_path / "missing.jsonl", family="loghub")


def test_p12_label_mapping_keeps_unmapped_labels_visible() -> None:
    mapped = map_external_label("deploy_error", family="loghub")
    unknown = map_external_label("vendor-specific-weird-label", family="aiops")

    assert mapped.incident_class == "deploy_regression"
    assert mapped.expected_route == "human_required"
    assert mapped.unmapped is False
    assert unknown.incident_class == "unknown_external_label"
    assert unknown.unmapped is True


def test_p12_converts_fixture_samples_into_judgment_cases() -> None:
    loghub = convert_dataset_sample("evals/real_datasets/fixtures/loghub/apache_sample.jsonl", family="loghub")
    nab = convert_dataset_sample("evals/real_datasets/fixtures/nab/real_known_cause_sample.csv", family="nab")
    aiops = convert_dataset_sample("evals/real_datasets/fixtures/aiops/multisignal_sample.jsonl", family="aiops")

    assert loghub.quality.accepted_records >= 3
    assert nab.quality.accepted_records >= 4
    assert aiops.quality.accepted_records >= 1
    assert all(case.local_mock_only for case in [*loghub.cases, *nab.cases, *aiops.cases])
    assert any("loghub" in case.tags for case in loghub.cases)
    assert any("nab" in case.tags for case in nab.cases)
    assert any("aiops" in case.tags for case in aiops.cases)
    assert any(case.rubric.required_evidence for case in aiops.cases)


def test_p12_real_dataset_evaluation_runs_benchmark_and_reports_quality(tmp_path: Path) -> None:
    output_cases = tmp_path / "real-dataset-cases.json"
    result = run_real_dataset_evaluation(
        [
            ("loghub", "evals/real_datasets/fixtures/loghub/apache_sample.jsonl"),
            ("nab", "evals/real_datasets/fixtures/nab/real_known_cause_sample.csv"),
            ("aiops", "evals/real_datasets/fixtures/aiops/multisignal_sample.jsonl"),
        ],
        output_cases=output_cases,
    )
    payload = result.to_dict()
    markdown = render_real_dataset_evaluation_markdown(result)

    assert payload["local_mock_only"] is True
    assert payload["case_count"] >= 3
    assert payload["benchmark"]["passed"] is True
    assert payload["import_quality"]["accepted_records"] >= 8
    assert "anomaly detection" in markdown.lower()
    assert "incident classification" in markdown.lower()
    assert "response judgment" in markdown.lower()
    assert "no external dataset download" in markdown
    assert output_cases.exists()
    assert len(json.loads(output_cases.read_text(encoding="utf-8"))) == payload["case_count"]
