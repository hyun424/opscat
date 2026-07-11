from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.p109_holdout_guard import (
    evaluate_p109_holdout_guard,
    render_p109_holdout_markdown,
    stable_json,
    write_p109_holdout_outputs,
)


def _row(
    row_id: str,
    *,
    split: str,
    group_id: str,
    observed_at: str,
    text: str,
    source_kind: str = "real_import",
    source_id: str = "rcaeval-reviewed",
    provenance_hash: str = "sha256:" + "1" * 64,
) -> dict[str, Any]:
    return {
        "row_id": row_id,
        "split": split,
        "group_id": group_id,
        "observed_at": observed_at,
        "evidence_text": text,
        "source_kind": source_kind,
        "source_id": source_id,
        "provenance_hash": provenance_hash,
    }


def test_holdout_guard_accepts_disjoint_group_time_split_and_is_deterministic(tmp_path: Path) -> None:
    rows = [
        _row("train-a", split="train", group_id="checkout", observed_at="2026-01-01T00:00:00Z", text="checkout timeout from pool exhaustion"),
        _row("train-b", split="train", group_id="billing", observed_at="2026-01-02T00:00:00Z", text="billing queue delay after deploy"),
        _row("holdout-a", split="holdout", group_id="inventory", observed_at="2026-02-01T00:00:00Z", text="inventory cpu throttling on worker"),
        _row("holdout-b", split="holdout", group_id="search", observed_at="2026-02-02T00:00:00Z", text="search cache saturation causes latency"),
    ]

    report = evaluate_p109_holdout_guard(rows, cutoff_at="2026-01-15T00:00:00Z", allowed_source_ids=["rcaeval-reviewed"])

    assert report["schema_version"] == "p109.holdout_guard.v1"
    assert report["accepted"] is True
    assert report["release_eligible"] is True
    assert report["group_split"]["overlap_group_ids"] == []
    assert report["time_split"]["violations"] == []
    assert report["duplicate_detection"]["exact_duplicates"] == []
    assert report["duplicate_detection"]["near_duplicates"] == []
    assert report["source_kind_counts"] == {"real_import": 4}
    assert report["source_provenance"]["source_id_counts"] == {"rcaeval-reviewed": 4}
    assert report["source_provenance"]["missing_source_row_ids"] == []
    assert report["source_provenance"]["missing_provenance_row_ids"] == []
    assert report["source_provenance"]["disallowed_source_ids"] == []
    assert report["holdout_report_hash"].startswith("sha256:")

    second = evaluate_p109_holdout_guard(list(reversed(rows)), cutoff_at="2026-01-15T00:00:00Z", allowed_source_ids=["rcaeval-reviewed"])
    assert stable_json(report) == stable_json(second)

    output_json = tmp_path / "holdout.json"
    output_md = tmp_path / "holdout.md"
    write_p109_holdout_outputs(report, output_json=output_json, output_md=output_md)
    assert json.loads(output_json.read_text(encoding="utf-8")) == report
    assert output_md.read_text(encoding="utf-8") == render_p109_holdout_markdown(report)


def test_holdout_guard_rejects_group_time_exact_near_duplicate_and_authored_fixture() -> None:
    rows = [
        _row("train-a", split="train", group_id="checkout", observed_at="2026-01-20T00:00:00Z", text="checkout timeout from pool exhaustion"),
        _row("holdout-a", split="holdout", group_id="checkout", observed_at="2026-02-01T00:00:00Z", text="checkout timeout from pool exhaustion"),
        _row("train-b", split="train", group_id="billing", observed_at="2026-01-01T00:00:00Z", text="billing deploy caused elevated payment queue latency"),
        _row("holdout-b", split="holdout", group_id="search", observed_at="2026-02-02T00:00:00Z", text="billing deploy caused payment queue latency elevated"),
        _row("holdout-authored", split="holdout", group_id="inventory", observed_at="2026-02-03T00:00:00Z", text="authored local smoke row", source_kind="authored_fixture"),
        _row(
            "holdout-disguised",
            split="holdout",
            group_id="workers",
            observed_at="2026-02-04T00:00:00Z",
            text="disguised fixture row",
            source_kind="real_import",
            source_id="external-synthetic-fixture",
        ),
    ]

    report = evaluate_p109_holdout_guard(rows, cutoff_at="2026-01-15T00:00:00Z", allowed_source_ids=["rcaeval-reviewed"])

    assert report["accepted"] is False
    assert report["release_eligible"] is False
    assert report["group_split"]["overlap_group_ids"] == ["checkout"]
    assert report["time_split"]["violations"] == [{"row_id": "train-a", "split": "train", "observed_at": "2026-01-20T00:00:00Z"}]
    assert report["duplicate_detection"]["exact_duplicates"] == [{"train_row_id": "train-a", "holdout_row_id": "holdout-a"}]
    assert report["duplicate_detection"]["near_duplicates"][0]["train_row_id"] == "train-b"
    assert report["duplicate_detection"]["near_duplicates"][0]["holdout_row_id"] == "holdout-b"
    assert report["authored_fixture_present"] is True
    assert report["source_provenance"]["fixture_source_ids"] == ["external-synthetic-fixture"]
    assert report["source_provenance"]["disallowed_source_ids"] == ["external-synthetic-fixture"]
    assert any("fixture-like source IDs cannot qualify" in reason for reason in report["reasons"])


def test_holdout_guard_rejects_missing_provenance_even_for_real_source_kind() -> None:
    rows = [
        _row("train-a", split="train", group_id="checkout", observed_at="2026-01-01T00:00:00Z", text="checkout timeout"),
        _row("holdout-a", split="holdout", group_id="billing", observed_at="2026-02-01T00:00:00Z", text="billing delay", provenance_hash=""),
    ]

    report = evaluate_p109_holdout_guard(rows, cutoff_at="2026-01-15T00:00:00Z", allowed_source_ids=["rcaeval-reviewed"])

    assert report["accepted"] is False
    assert report["release_eligible"] is False
    assert report["source_provenance"]["missing_provenance_row_ids"] == ["holdout-a"]
    assert any("provenance_hash is required" in reason for reason in report["reasons"])
