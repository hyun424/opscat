from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.external_dataset_acquisition import (
    ExternalDatasetAcquisitionReport,
    build_external_dataset_acquisition_report,
    render_external_dataset_acquisition_markdown,
)

MANIFEST = Path("evals/real_datasets/external/p42_manifest.json")


def test_external_dataset_acquisition_defaults_to_no_network_dry_run() -> None:
    report = build_external_dataset_acquisition_report(MANIFEST, allow_network=False)
    payload = report.to_dict()

    assert isinstance(report, ExternalDatasetAcquisitionReport)
    assert payload["summary"]["source_count"] >= 3
    assert payload["summary"]["download_count"] == 0
    assert payload["summary"]["boundary_violation_count"] == 0
    assert payload["boundary"]["network_allowed"] is False
    assert payload["boundary"]["external_downloads_performed"] is False
    assert payload["boundary"]["live_api_calls_enabled"] is False
    assert payload["source_cards"]["loghub-apache"]["mode"] == "dry_run"
    assert payload["source_cards"]["nab-real-known-cause"]["mode"] == "dry_run"


def test_external_dataset_holdout_split_and_score_are_deterministic() -> None:
    first = build_external_dataset_acquisition_report(MANIFEST, allow_network=False).to_dict()
    second = build_external_dataset_acquisition_report(MANIFEST, allow_network=False).to_dict()

    assert first["holdout_manifest"] == second["holdout_manifest"]
    assert first["holdout_score"] == second["holdout_score"]
    assert first["summary"]["holdout_source_count"] >= 1
    assert first["holdout_score"]["root_cause_accuracy"] >= 0.9
    assert first["holdout_score"]["route_accuracy"] >= 0.9
    assert first["holdout_score"]["unsafe_action_count"] == 0
    assert first["splits"]["holdout"]
    assert not (set(first["splits"]["train"]) & set(first["splits"]["holdout"]))


def test_external_dataset_cli_writes_report(tmp_path: Path) -> None:
    output_json = tmp_path / "p42.json"
    output_md = tmp_path / "p42.md"

    subprocess.run(
        [
            "python",
            "scripts/prepare_external_datasets.py",
            "--manifest",
            str(MANIFEST),
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
    assert payload["summary"]["holdout_source_count"] >= 1
    assert "# OpsCat External Dataset Acquisition & Holdout Evaluation" in markdown
    assert "No external downloads were performed" in markdown
    assert render_external_dataset_acquisition_markdown(payload).startswith("# OpsCat External Dataset Acquisition")
