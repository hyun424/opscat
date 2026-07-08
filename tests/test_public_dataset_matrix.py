from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from app.services.public_dataset_matrix import (
    PublicDatasetMatrixReport,
    build_public_dataset_matrix_report,
    render_public_dataset_matrix_markdown,
)

MANIFEST = Path("evals/real_datasets/external/p44_benchmark_matrix_manifest.json")


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, _limit: int) -> bytes:
        return self.payload


def test_public_dataset_matrix_offline_builds_source_and_family_scores(tmp_path: Path) -> None:
    report = build_public_dataset_matrix_report(MANIFEST, allow_network=False, artifact_root=tmp_path / "artifacts", materialized_root=tmp_path / "materialized")
    payload = report.to_dict()

    assert isinstance(report, PublicDatasetMatrixReport)
    assert payload["summary"]["dataset_mode"] == "fixture_fallback"
    assert payload["summary"]["source_count"] >= 5
    assert payload["summary"]["download_count"] == 0
    assert payload["summary"]["matrix_row_count"] == payload["summary"]["source_count"]
    assert payload["summary"]["family_count"] >= 2
    assert payload["aggregate_score"]["root_cause_accuracy"] >= 0.9
    assert payload["aggregate_score"]["route_accuracy"] >= 0.9
    assert "loghub" in payload["family_matrix"]
    assert "nab" in payload["family_matrix"]
    assert all(row["root_cause_match"] for row in payload["source_matrix"])
    assert payload["weak_spots"]["false_positive_count"] >= 0
    assert payload["boundary"]["external_downloads_performed"] is False


def test_public_dataset_matrix_opt_in_downloads_multiple_public_sources(tmp_path: Path, monkeypatch: Any) -> None:
    log_payload = b"notice service started\nerror deploy failed timeout\nnormal heartbeat\n"
    nab_payload = b"timestamp,value\n2013-12-10 00:00:00,20.1\n2013-12-10 00:05:00,20.2\n2013-12-10 00:10:00,91.4\n"
    labels = {
        "realKnownCause/machine_temperature_system_failure.csv": [["2013-12-10 00:09:00", "2013-12-10 00:11:00"]],
        "realKnownCause/ambient_temperature_system_failure.csv": [["2013-12-10 00:09:00", "2013-12-10 00:11:00"]],
        "realAWSCloudwatch/ec2_cpu_utilization_24ae8d.csv": [["2013-12-10 00:09:00", "2013-12-10 00:11:00"]],
    }
    label_payload = json.dumps(labels).encode()

    def fake_urlopen(url: str, timeout: int = 20) -> _FakeResponse:  # noqa: ARG001
        if url.endswith(".log"):
            return _FakeResponse(log_payload)
        if url.endswith(".csv"):
            return _FakeResponse(nab_payload)
        if url.endswith("combined_windows.json"):
            return _FakeResponse(label_payload)
        raise AssertionError(url)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    report = build_public_dataset_matrix_report(MANIFEST, allow_network=True, artifact_root=tmp_path / "artifacts", materialized_root=tmp_path / "materialized")
    payload = report.to_dict()

    assert payload["summary"]["dataset_mode"] == "downloaded_public_sample"
    assert payload["summary"]["download_count"] >= 5
    assert payload["summary"]["matrix_row_count"] >= 5
    assert payload["summary"]["parsed_record_count"] >= 15
    assert payload["aggregate_score"]["label_coverage"] == 1.0
    assert payload["aggregate_score"]["root_cause_accuracy"] == 1.0
    assert payload["boundary"]["network_allowed"] is True
    assert payload["boundary"]["external_downloads_performed"] is True


def test_public_dataset_matrix_cli_writes_report(tmp_path: Path) -> None:
    output_json = tmp_path / "p44.json"
    output_md = tmp_path / "p44.md"

    subprocess.run(
        [
            "python",
            "scripts/run_public_dataset_matrix.py",
            "--manifest",
            str(MANIFEST),
            "--artifact-root",
            str(tmp_path / "artifacts"),
            "--materialized-root",
            str(tmp_path / "materialized"),
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(output_json.read_text(encoding="utf-8"))
    markdown = output_md.read_text(encoding="utf-8")
    assert payload["summary"]["download_count"] == 0
    assert payload["summary"]["matrix_row_count"] >= 5
    assert "# OpsCat Public Dataset Benchmark Matrix" in markdown
    assert "Family matrix" in markdown
    assert render_public_dataset_matrix_markdown(payload).startswith("# OpsCat Public Dataset Benchmark Matrix")
