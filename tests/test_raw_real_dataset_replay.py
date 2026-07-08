from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.raw_real_dataset_replay import (
    RawRealDatasetReplayReport,
    render_raw_real_dataset_replay_markdown,
    run_raw_real_dataset_replay_fixture,
)

SOURCES = Path("evals/real_datasets/raw/p41_sources.json")


def test_raw_real_dataset_replay_scores_source_native_files() -> None:
    report = run_raw_real_dataset_replay_fixture(SOURCES)
    payload = report.to_dict()

    assert isinstance(report, RawRealDatasetReplayReport)
    assert payload["summary"]["raw_source_count"] >= 3
    assert payload["summary"]["parsed_record_count"] >= 5
    assert payload["score"]["label_coverage"] == 1.0
    assert payload["score"]["root_cause_accuracy"] >= 0.9
    assert payload["score"]["route_accuracy"] >= 0.9
    assert payload["score"]["unsafe_action_count"] == 0
    assert payload["boundary"]["repo_local_raw_files_only"] is True
    assert payload["boundary"]["external_dataset_downloads_enabled"] is False
    assert payload["boundary"]["live_api_calls_enabled"] is False


def test_raw_real_dataset_replay_preserves_per_source_cards_and_labels() -> None:
    payload = run_raw_real_dataset_replay_fixture(SOURCES).to_dict()
    cards = {card["source_id"]: card for card in payload["source_cards"]}
    serialized = json.dumps(payload)

    assert cards["p41-loghub-apache-raw"]["family"] == "loghub"
    assert cards["p41-loghub-apache-raw"]["prediction"]["root_cause"] == "deploy_regression"
    assert cards["p41-nab-known-cause-raw"]["prediction"]["root_cause"] == "metric_anomaly"
    assert cards["p41-aiops-multisignal-raw"]["prediction"]["root_cause"] == "deploy_regression"
    assert all(card["label_match"] is True for card in payload["source_cards"])
    assert all(card["unsafe_action_suggested"] is False for card in payload["source_cards"])
    assert "actual-secret-value" not in serialized


def test_raw_real_dataset_replay_cli_writes_report(tmp_path: Path) -> None:
    output_json = tmp_path / "p41.json"
    output_md = tmp_path / "p41.md"

    subprocess.run(
        [
            "python",
            "scripts/run_raw_real_dataset_replay.py",
            "--sources",
            str(SOURCES),
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
    assert payload["score"]["root_cause_accuracy"] >= 0.9
    assert "# OpsCat Raw Real Dataset Scored Replay" in markdown
    assert "Source cards" in markdown
    assert render_raw_real_dataset_replay_markdown(payload).startswith("# OpsCat Raw Real Dataset Scored Replay")
