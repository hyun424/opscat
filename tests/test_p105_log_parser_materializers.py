from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest


def _api() -> Any:
    return importlib.import_module("app.services.failure_forecast_engine")


def _parser_api() -> Any:
    parser = getattr(_api(), "materialize_p105_log_parser_source", None)
    if parser is None:
        pytest.fail("P105-025 RED: expose materialize_p105_log_parser_source for Apache/Hadoop/Zookeeper reviewed parsers.", pytrace=False)
    return parser


@pytest.mark.parametrize(
    ("parser_name", "line"),
    [
        ("apache", '127.0.0.1 - - [09/Mar/2024:16:00:00 +0000] "GET /health HTTP/1.1" 200 2'),
        ("hadoop", "2024-03-09 16:00:00,000 INFO org.apache.hadoop.hdfs.server.namenode.FSNamesystem: safe mode is OFF"),
        ("zookeeper", "2024-03-09 16:00:00,000 [myid:1] - INFO  [main:QuorumPeer@100] - LOOKING"),
    ],
)
def test_actual_log_parsers_emit_offsets_timestamps_redacted_payload_and_hash_binding(tmp_path: Path, parser_name: str, line: str) -> None:
    source = tmp_path / f"{parser_name}.log"
    source.write_text(line + "\n", encoding="utf-8")

    result = _parser_api()(parser_name=parser_name, source_path=source, reviewed_predicate=None)

    row = result["public_rows"][0]
    assert row["parser_name"] == parser_name
    assert row["parser_version"]
    assert row["source_byte_sha256"]
    assert row["line_offset"] == 0
    assert row["byte_offset"] == 0
    assert row["parsed_timestamp"]
    assert row["parse_status"] == "parsed"
    assert row["redacted_public_payload"]
    assert row["public_event_hash"]
    assert row["family"] == "unsupported_family"
    assert row["eligible_for_release_floor"] is False


def test_parser_failure_is_unsupported_family_and_contributes_no_floor_credit(tmp_path: Path) -> None:
    source = tmp_path / "broken-apache.log"
    source.write_text("\x00not an apache line\n", encoding="utf-8")

    result = _parser_api()(parser_name="apache", source_path=source, reviewed_predicate=None)

    assert result["public_rows"][0]["parse_status"] == "parser_failed"
    assert result["public_rows"][0]["family"] == "unsupported_family"
    assert result["floor_credit"] == {"rows": 0, "positives": 0, "incident_groups": 0, "coverage_seconds": 0}


def test_parser_success_requires_reviewed_deploy_config_predicate_not_filename_or_labels(tmp_path: Path) -> None:
    source = tmp_path / "deploy-outage-database-floor-deficit.log"
    source.write_text("2024-03-09 16:00:00,000 ERROR deploy failed after config push\n", encoding="utf-8")

    result = _parser_api()(
        parser_name="zookeeper",
        source_path=source,
        reviewed_predicate={"authority_source": "filename", "family": "deploy", "private_label": "deploy"},
    )

    assert "predicate_authority_not_reviewed" in result["validation_error_codes"]
    assert result["public_rows"][0]["family"] == "unsupported_family"
    assert result["public_rows"][0]["eligible_for_release_floor"] is False
