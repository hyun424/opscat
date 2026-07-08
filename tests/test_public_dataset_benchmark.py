from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from app.services.public_dataset_benchmark import (
    PublicDatasetBenchmarkReport,
    build_public_dataset_benchmark_report,
    render_public_dataset_benchmark_markdown,
)

MANIFEST = Path("evals/real_datasets/external/p43_public_benchmark_manifest.json")


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, _limit: int) -> bytes:
        return self.payload


def test_public_dataset_benchmark_offline_fallback_scores_without_downloads(tmp_path: Path) -> None:
    report = build_public_dataset_benchmark_report(MANIFEST, allow_network=False, artifact_root=tmp_path / "artifacts", materialized_root=tmp_path / "materialized")
    payload = report.to_dict()

    assert isinstance(report, PublicDatasetBenchmarkReport)
    assert payload["summary"]["source_count"] >= 2
    assert payload["summary"]["download_count"] == 0
    assert payload["summary"]["dataset_mode"] == "fixture_fallback"
    assert payload["summary"]["materialized_source_count"] >= 2
    assert payload["score"]["root_cause_accuracy"] >= 0.9
    assert payload["score"]["route_accuracy"] >= 0.9
    assert payload["boundary"]["network_allowed"] is False
    assert payload["boundary"]["external_downloads_performed"] is False


def test_public_dataset_benchmark_opt_in_download_materializes_public_samples(tmp_path: Path, monkeypatch: Any) -> None:
    log_payload = b"[Fri Dec 01 00:00:00 2023] [notice] Apache started\n[Fri Dec 01 00:01:00 2023] [error] deploy failed timeout\n"
    nab_payload = b"timestamp,value\n2013-12-10 00:00:00,20.1\n2013-12-10 00:05:00,20.2\n2013-12-10 00:10:00,85.4\n"
    label_payload = json.dumps({"realKnownCause/machine_temperature_system_failure.csv": [["2013-12-10 00:09:00", "2013-12-10 00:11:00"]]}).encode()

    def fake_urlopen(url: str, timeout: int = 20) -> _FakeResponse:  # noqa: ARG001
        if url.endswith("Apache_2k.log"):
            return _FakeResponse(log_payload)
        if url.endswith("machine_temperature_system_failure.csv"):
            return _FakeResponse(nab_payload)
        if url.endswith("combined_windows.json"):
            return _FakeResponse(label_payload)
        raise AssertionError(url)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    report = build_public_dataset_benchmark_report(MANIFEST, allow_network=True, artifact_root=tmp_path / "artifacts", materialized_root=tmp_path / "materialized")
    payload = report.to_dict()

    assert payload["summary"]["dataset_mode"] == "downloaded_public_sample"
    assert payload["summary"]["download_count"] == 3
    assert payload["summary"]["materialized_source_count"] == 2
    assert payload["score"]["label_coverage"] == 1.0
    assert payload["score"]["root_cause_accuracy"] == 1.0
    assert payload["boundary"]["network_allowed"] is True
    assert payload["boundary"]["external_downloads_performed"] is True
    assert all(Path(source["path"]).exists() for source in payload["materialized_manifest"]["sources"])


def test_public_dataset_benchmark_cli_writes_report(tmp_path: Path) -> None:
    output_json = tmp_path / "p43.json"
    output_md = tmp_path / "p43.md"

    subprocess.run(
        [
            "python",
            "scripts/run_public_dataset_benchmark.py",
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
    assert payload["score"]["root_cause_accuracy"] >= 0.9
    assert "# OpsCat Public Dataset Benchmark Scorecard" in markdown
    assert "Offline fixture fallback" in markdown
    assert render_public_dataset_benchmark_markdown(payload).startswith("# OpsCat Public Dataset Benchmark Scorecard")
