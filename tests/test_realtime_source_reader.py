from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.services.judgment_dataset import JudgmentCase
from app.services.realtime_source_reader import (
    FileTailCursor,
    FileTailReader,
    RollingIncidentWindow,
    build_judgment_case_from_trigger,
    detect_realtime_triggers,
    parse_log_line,
    parse_metric_csv_rows,
    replay_sources_to_snapshots,
)


def test_file_tail_reader_reads_only_appended_lines_and_tracks_cursor(tmp_path: Path) -> None:
    source = tmp_path / "app.log"
    source.write_text("line one\nline two\n", encoding="utf-8")

    reader = FileTailReader(source, cursor=FileTailCursor.start_of_file(source))
    first = reader.read_new_lines()
    assert first.lines == ["line one", "line two"]
    assert first.cursor.offset == source.stat().st_size
    assert first.cursor.path == str(source)

    source.write_text("line one\nline two\nline three\n", encoding="utf-8")
    second = FileTailReader(source, cursor=first.cursor).read_new_lines()
    assert second.lines == ["line three"]
    assert second.cursor.offset == source.stat().st_size

    source.write_text("rotated first\n", encoding="utf-8")
    rotated = FileTailReader(source, cursor=second.cursor).read_new_lines()
    assert rotated.lines == ["rotated first"]
    assert rotated.cursor.offset == source.stat().st_size
    assert any("truncated_or_rotated" in reason for reason in rotated.reasons)


def test_log_parser_handles_plain_json_logfmt_and_loghub_structured_rows() -> None:
    plain = parse_log_line("2026-07-08T01:02:03Z ERROR payment-api timeout talking to db", source="plain.log")
    json_event = parse_log_line('{"timestamp":"2026-07-08T01:02:04Z","level":"warn","service":"api","message":"latency spike"}', source="json.log")
    logfmt = parse_log_line("ts=2026-07-08T01:02:05Z level=error service=worker msg=queue_backlog count=99", source="worker.log")
    loghub = parse_log_line(
        "LineId=2 Time='Sun Dec 04 04:47:44 2005' Level=error Content='mod_jk child workerEnv in error state 6' EventId=E3",
        source="Apache_2k.log_structured.csv",
    )

    assert plain.severity == "error"
    assert plain.message.endswith("timeout talking to db")
    assert json_event.service == "api"
    assert json_event.severity == "warn"
    assert logfmt.service == "worker"
    assert "queue_backlog" in logfmt.message
    assert loghub.severity == "error"
    assert "workerEnv" in loghub.message
    assert all(event.raw for event in [plain, json_event, logfmt, loghub])


def test_metric_parser_builds_points_and_skips_invalid_rows() -> None:
    rows = [
        {"timestamp": "2026-07-08T01:00:00Z", "value": "10"},
        {"timestamp": "2026-07-08T01:01:00Z", "value": "50", "metric": "latency_ms"},
        {"timestamp": "2026-07-08T01:02:00Z", "value": "not-a-number"},
    ]

    result = parse_metric_csv_rows(rows, source="nab.csv", default_metric="temperature")

    assert [point.value for point in result.points] == [10.0, 50.0]
    assert result.points[0].metric == "temperature"
    assert result.points[1].metric == "latency_ms"
    assert result.skipped_rows == 1
    assert any("invalid_numeric_value" in reason for reason in result.skip_reasons)


def test_rolling_window_detects_triggers_and_builds_snapshot() -> None:
    window = RollingIncidentWindow(max_events=10)
    for index in range(5):
        window.add_log(parse_log_line(f"2026-07-08T01:0{index}:00Z ERROR api failure {index}", source="app.log"))
    metric_result = parse_metric_csv_rows(
        [
            {"timestamp": "2026-07-08T01:00:00Z", "value": "10"},
            {"timestamp": "2026-07-08T01:01:00Z", "value": "55"},
        ],
        source="metric.csv",
        default_metric="error_rate",
    )
    for point in metric_result.points:
        window.add_metric(point)

    triggers = detect_realtime_triggers(window)
    trigger_types = {trigger.type for trigger in triggers}
    assert "error_spike" in trigger_types
    assert "metric_spike" in trigger_types

    case = build_judgment_case_from_trigger(window, triggers[0], case_id="p18a-snapshot-001")
    assert isinstance(case, JudgmentCase)
    assert case.id == "p18a-snapshot-001"
    assert case.local_mock_only is True
    assert case.rubric.required_evidence
    assert any(item.get("content") for item in case.evidence)


def test_replay_sources_to_snapshots_uses_source_native_inputs(tmp_path: Path) -> None:
    log_file = tmp_path / "app.log"
    metric_file = tmp_path / "metric.csv"
    output_json = tmp_path / "snapshots.json"
    output_md = tmp_path / "report.md"
    log_file.write_text("ERROR api failed\nERROR api failed again\nERROR api failed third\n", encoding="utf-8")
    metric_file.write_text("timestamp,value\n2026-07-08T01:00:00Z,10\n2026-07-08T01:01:00Z,50\n", encoding="utf-8")

    result = replay_sources_to_snapshots(log_file=log_file, metric_csv=metric_file, output_json=output_json, output_md=output_md)

    assert result["log_lines_read"] == 3
    assert result["metric_points_read"] == 2
    assert result["snapshot_count"] >= 1
    assert output_json.exists()
    assert output_md.exists()
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["snapshots"]
    assert "source-native incremental" in output_md.read_text(encoding="utf-8")


def test_realtime_replay_cli_writes_snapshots(tmp_path: Path) -> None:
    log_file = tmp_path / "app.log"
    output_json = tmp_path / "snapshots.json"
    output_md = tmp_path / "report.md"
    log_file.write_text("ERROR api failed\nERROR api failed again\nERROR api failed third\n", encoding="utf-8")

    completed = subprocess.run(
        [
            "python",
            "scripts/replay_realtime_sources.py",
            "--log-file",
            str(log_file),
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "snapshot_count" in completed.stdout
    assert json.loads(output_json.read_text(encoding="utf-8"))["snapshot_count"] >= 1
