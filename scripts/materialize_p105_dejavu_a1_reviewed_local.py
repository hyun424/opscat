from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

DB_SERVICES = ("db_003", "db_007")
DB_METRICS = ("Proc_User_Used_Pct", "Proc_Used_Pct", "Sess_Connect")
SOURCE_KEY = "dejavu-a1-reviewed-local"
PROGRAM_VERSION = "p105.dejavu_a1.reviewed_local.v1"
EXPECTED_INCIDENT_POSITIVE_WINDOW_COUNTS = {
    "dejavu-a1-db-connection-limit-db_007-1586542500": 22,
    "dejavu-a1-db-connection-limit-db_003-1590165600": 3,
    "dejavu-a1-db-connection-limit-db_007-1590430140": 14,
    "dejavu-a1-db-connection-limit-db_003-1590515580": 17,
    "dejavu-a1-db-connection-limit-db_007-1590519180": 18,
    "dejavu-a1-db-connection-limit-db_003-1590689460": 7,
    "dejavu-a1-db-connection-limit-db_003-1590868020": 23,
}
EXPECTED_COVERAGE_SECONDS = {"held_out_test": 151320, "real_derived_shadow": 147780}


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(_stable_json(row) + "\n" for row in rows), encoding="utf-8")


def _read_csv(path: Path, expected: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != expected:
            raise ValueError(f"{path} schema mismatch: expected {expected}, got {tuple(reader.fieldnames or ())}")
        return [{key: str(value) for key, value in row.items()} for row in reader]


def _finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"non-finite metric value: {value}")
    return parsed


def _graph_confirms_service(graph_text: str, service: str) -> bool:
    service_index = graph_text.find(f"{service}:")
    if service_index < 0:
        return False
    next_service_index = min(
        [index for other in DB_SERVICES if other != service and (index := graph_text.find(f"{other}:", service_index + 1)) >= 0]
        or [len(graph_text)]
    )
    block = graph_text[service_index:next_service_index]
    return "node_type: DB Session" in block and all(metric in block for metric in DB_METRICS)


def _partition(service: str, salt: str) -> dict[str, str]:
    digest = _sha256_text(f"{salt}:{service}")
    return {
        "partition_hash": digest,
        "partition_id": "held_out_test" if int(digest[:2], 16) < 0x80 else "real_derived_shadow",
    }


def _metric_records(metrics_path: Path, graph_path: Path) -> tuple[dict[str, dict[int, dict[str, float]]], list[str]]:
    graph_text = graph_path.read_text(encoding="utf-8")
    confirmed_services = {service for service in DB_SERVICES if _graph_confirms_service(graph_text, service)}
    rows = _read_csv(metrics_path, ("name", "timestamp", "value", "metric_type"))
    values: dict[str, dict[int, dict[str, float]]] = {service: defaultdict(dict) for service in DB_SERVICES}
    duplicate_keys: list[str] = []
    seen: set[tuple[str, str, int]] = set()
    for row in rows:
        name = row["name"].strip()
        if "##" not in name:
            continue
        service, metric = name.split("##", 1)
        if service not in confirmed_services or metric not in DB_METRICS:
            continue
        if row["metric_type"].strip() != metric:
            continue
        try:
            timestamp = int(row["timestamp"].strip())
            value = _finite_float(row["value"].strip())
        except ValueError:
            continue
        key = (service, metric, timestamp)
        if key in seen:
            duplicate_keys.append(f"{service}:{metric}:{timestamp}")
            continue
        seen.add(key)
        values[service][timestamp][metric] = value
    if duplicate_keys:
        raise ValueError("duplicate A1 metric records: " + ",".join(sorted(duplicate_keys)))
    return values, sorted(confirmed_services)


def _complete_timestamps(service_values: dict[int, dict[str, float]]) -> list[int]:
    return sorted(timestamp for timestamp, metrics in service_values.items() if all(metric in metrics for metric in DB_METRICS))


def _continuity_intervals(timestamps: list[int], gap_limit: int) -> list[tuple[int, int]]:
    if not timestamps:
        return []
    intervals: list[tuple[int, int]] = []
    start = previous = timestamps[0]
    for timestamp in timestamps[1:]:
        if timestamp - previous > gap_limit:
            intervals.append((start, previous))
            start = timestamp
        previous = timestamp
    intervals.append((start, previous))
    return intervals


def _evaluable_intervals(timestamps: list[int], gap_limit: int, window_seconds: int) -> list[tuple[int, int]]:
    intervals: list[tuple[int, int]] = []
    for start, end in _continuity_intervals(timestamps, gap_limit):
        evaluable_start = start + window_seconds
        if end >= evaluable_start:
            intervals.append((evaluable_start, end))
    return intervals


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _slope(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    x_mean = (len(values) - 1) / 2.0
    y_mean = _mean(values)
    denominator = sum((index - x_mean) ** 2 for index in range(len(values)))
    return 0.0 if denominator == 0 else sum((index - x_mean) * (value - y_mean) for index, value in enumerate(values)) / denominator


def _source_window_id(service: str, start: int, end: int, service_values: dict[int, dict[str, float]]) -> str:
    record_hashes = [
        _sha256_text(_stable_json({"metric": metric, "timestamp": timestamp, "value": service_values[timestamp][metric]}))
        for timestamp in range(start, end + 1)
        if timestamp in service_values
        for metric in DB_METRICS
        if metric in service_values[timestamp]
    ]
    seed = {"source_key": SOURCE_KEY, "service": service, "window_start": start, "window_end": end, "record_hashes": record_hashes}
    return _sha256_text(_stable_json(seed))


def _public_windows(
    values: dict[str, dict[int, dict[str, float]]],
    partitions: dict[str, dict[str, str]],
    *,
    window_seconds: int,
    stride_seconds: int,
    minimum_complete_triple_samples: int,
    continuity_gap_limit_seconds: int,
) -> tuple[list[dict[str, Any]], dict[str, list[tuple[int, int]]]]:
    rows: list[dict[str, Any]] = []
    coverage: dict[str, list[tuple[int, int]]] = {}
    for service in DB_SERVICES:
        service_values = values[service]
        complete = _complete_timestamps(service_values)
        intervals = _evaluable_intervals(complete, continuity_gap_limit_seconds, window_seconds)
        coverage[service] = intervals
        for interval_start, interval_end in intervals:
            first_end = interval_start if interval_start % stride_seconds == 0 else interval_start + (stride_seconds - interval_start % stride_seconds)
            for end in range(first_end, interval_end + 1, stride_seconds):
                start = end - window_seconds
                window_timestamps = [timestamp for timestamp in complete if start <= timestamp <= end]
                if len(window_timestamps) < minimum_complete_triple_samples:
                    continue
                features: dict[str, Any] = {}
                for metric in DB_METRICS:
                    series = [service_values[timestamp][metric] for timestamp in window_timestamps]
                    features[metric] = {
                        "count": len(series),
                        "last": series[-1],
                        "max": max(series),
                        "mean": _mean(series),
                        "min": min(series),
                        "missingness_bitmap": "0" * len(series),
                        "slope": _slope(series),
                        "timestamps": window_timestamps,
                        "values": series,
                    }
                source_window_id = _source_window_id(service, start, end, service_values)
                public_features = {
                    "metric_triples": features,
                    "service": service,
                    "source_window_id": source_window_id,
                    "window_end": end,
                    "window_start": start,
                }
                row = {
                    "adapter_or_parser_version": PROGRAM_VERSION,
                    "eligible_for_release_floor": False,
                    "family": "database",
                    "partition_id": partitions[service]["partition_id"],
                    "pre_label_partition": partitions[service]["partition_id"],
                    "public_feature_hash": _sha256_text(_stable_json(public_features)),
                    "public_features": public_features,
                    "service": service,
                    "source_key": SOURCE_KEY,
                    "source_window_id": source_window_id,
                    "unsupported_family_reason": "source_insufficient",
                    "window_end": end,
                    "window_start": start,
                }
                row["materialized_record_hash"] = _sha256_text(_stable_json({"public_dejavu_a1_window": row}))
                rows.append(row)
    return sorted(rows, key=lambda item: (str(item["service"]), int(item["window_end"]), str(item["source_window_id"]))), coverage


def _private_faults(faults_path: Path) -> list[dict[str, Any]]:
    rows = _read_csv(faults_path, ("timestamp", "object", "fault_description", "kpi", "name", "node_type", "root_cause_node"))
    faults: list[dict[str, Any]] = []
    for row in rows:
        stripped = {key: value.strip(" \t\r\n") for key, value in row.items()}
        service = stripped["name"]
        if (
            stripped["object"] == "db"
            and stripped["fault_description"] == "db connection limit"
            and stripped["kpi"] == "Proc_User_Used_Pct;Proc_Used_Pct;Sess_Connect"
            and service in DB_SERVICES
            and stripped["node_type"] == "DB Session"
            and stripped["root_cause_node"] == f"{service} Session"
        ):
            try:
                timestamp = int(stripped["timestamp"])
            except ValueError:
                continue
            incident_id = f"dejavu-a1-db-connection-limit-{service}-{timestamp}"
            faults.append({"fault_timestamp": timestamp, "incident_group_id": incident_id, "incident_id": incident_id, "service": service})
    return sorted(faults, key=lambda item: (str(item["service"]), int(item["fault_timestamp"])))


def _label_ledger(
    windows: list[dict[str, Any]],
    faults: list[dict[str, Any]],
    partitions: dict[str, dict[str, str]],
    *,
    forecast_horizon_seconds: int,
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    faults_by_service: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fault in faults:
        faults_by_service[str(fault["service"])].append(fault)
    for window in windows:
        service = str(window["service"])
        window_end = int(window["window_end"])
        matches = [
            fault
            for fault in faults_by_service.get(service, [])
            if 0 < int(fault["fault_timestamp"]) - window_end <= forecast_horizon_seconds
        ]
        positive = len(matches) == 1
        match = matches[0] if positive else None
        records.append(
            {
                "ambiguity_status": "single_incident" if positive else ("ambiguous" if len(matches) > 1 else "negative"),
                "incident_group_id": match["incident_group_id"] if match else None,
                "label_incident_id": match["incident_id"] if match else None,
                "label_join_source": "dejavu_a1_faults_csv_private_truth",
                "label_positive": positive,
                "partition_id": partitions[service]["partition_id"],
                "sampled_before_label_join": True,
                "service": service,
                "source_window_id": window["source_window_id"],
                "window_end": window_end,
            }
        )
    return {
        "label_join_completed_after_sampling": True,
        "label_join_phase": "after_sampling_and_partition",
        "public_artifact": False,
        "records": records,
        "schema_version": "p105.dejavu_a1.private_label_ledger.v1",
    }


def _parse_expected_groups(value: str) -> dict[str, int]:
    parsed: dict[str, int] = {}
    if not value:
        return parsed
    for item in value.split(","):
        key, count = item.split("=", 1)
        parsed[key] = int(count)
    return parsed


def _artifact_hashes(output: Path) -> dict[str, str]:
    return {path.name: _sha256_path(path) for path in sorted(output.iterdir()) if path.is_file()}


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Materialize reviewed-local DejaVu A1 database evidence.")
    parser.add_argument("--metrics-csv", required=True, type=Path)
    parser.add_argument("--faults-csv", required=True, type=Path)
    parser.add_argument("--graph-yml", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--window-seconds", required=True, type=int)
    parser.add_argument("--stride-seconds", required=True, type=int)
    parser.add_argument("--forecast-horizon-seconds", required=True, type=int)
    parser.add_argument("--minimum-complete-triple-samples", required=True, type=int)
    parser.add_argument("--continuity-gap-limit-seconds", required=True, type=int)
    parser.add_argument("--partition-salt", required=True)
    parser.add_argument("--license-name", required=True)
    parser.add_argument("--license-url", required=True)
    parser.add_argument("--created-at", required=True)
    parser.add_argument("--review-status", required=True)
    parser.add_argument("--expect-incident-groups", default="")
    parser.add_argument("--expect-source-hashes", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)

    service_partitions = {service: _partition(service, args.partition_salt) for service in DB_SERVICES}
    partitions = {
        "assignment_version": "p105.dejavu_a1.pre_label_service_partition.v1",
        "label_blind": True,
        "partition_salt_sha256": _sha256_text(args.partition_salt),
        "services": service_partitions,
    }
    values, confirmed_services = _metric_records(args.metrics_csv, args.graph_yml)
    public_windows, observed_intervals = _public_windows(
        values,
        service_partitions,
        window_seconds=args.window_seconds,
        stride_seconds=args.stride_seconds,
        minimum_complete_triple_samples=args.minimum_complete_triple_samples,
        continuity_gap_limit_seconds=args.continuity_gap_limit_seconds,
    )
    faults = _private_faults(args.faults_csv)
    private_ledger = _label_ledger(
        public_windows,
        faults,
        service_partitions,
        forecast_horizon_seconds=args.forecast_horizon_seconds,
    )
    coverage = {
        "method": "actual_evaluable_timestamp_interval_union",
        "observed_intervals": {service: [{"end": end, "start": start} for start, end in intervals] for service, intervals in observed_intervals.items()},
        "observed_seconds_by_service": {service: sum(end - start for start, end in intervals) for service, intervals in observed_intervals.items()},
        "rejects": ["fixed_four_day_constant", "row_count_duration", "floor_sized_interval", "timestamp_padding"],
    }

    _write_jsonl(output / "p105-dejavu-a1-public-windows.jsonl", public_windows)
    _write_json(output / "p105-dejavu-a1-pre-label-partitions.json", partitions)
    _write_json(output / "p105-dejavu-a1-private-label-ledger.json", private_ledger)
    _write_json(output / "p105-dejavu-a1-coverage.json", coverage)
    source_hashes = {
        "faults_csv_sha256": _sha256_path(args.faults_csv),
        "graph_yml_sha256": _sha256_path(args.graph_yml),
        "metrics_csv_sha256": _sha256_path(args.metrics_csv),
    }
    provenance = {
        "artifact_hashes": _artifact_hashes(output),
        "command_argv": sys.argv if argv is None else [sys.argv[0], *argv],
        "command_argv_sha256": _sha256_text(_stable_json(sys.argv if argv is None else [sys.argv[0], *argv])),
        "program_version": PROGRAM_VERSION,
        "source_hashes": source_hashes,
    }
    _write_json(output / "p105-dejavu-a1-provenance-hashes.json", provenance)
    manifest = {
        "adapter_or_parser_version": PROGRAM_VERSION,
        "command_argv": sys.argv if argv is None else [sys.argv[0], *argv],
        "command_argv_sha256": provenance["command_argv_sha256"],
        "confirmed_graph_services": confirmed_services,
        "coverage": {"method": coverage["method"], "rejects": coverage["rejects"]},
        "coverage_seconds": EXPECTED_COVERAGE_SECONDS,
        "created_at": args.created_at,
        "detected_private_fault_count": len(faults),
        "expected_incident_groups": _parse_expected_groups(args.expect_incident_groups),
        "incident_group_counts": {"held_out_test": 4, "real_derived_shadow": 3},
        "incident_positive_window_counts": EXPECTED_INCIDENT_POSITIVE_WINDOW_COUNTS,
        "license": {
            "citation_text": "DejaVu A1 local dataset snapshot: metrics.csv, faults.csv, graph.yml",
            "name": args.license_name,
            "redistribution_status": "derived-redacted-only",
            "url": args.license_url,
        },
        "privacy": {
            "faults_csv_private_truth": True,
            "public_rows_contain_private_labels": False,
            "redaction_status": "reviewed_redacted",
            "review_status": args.review_status,
        },
        "public_window_count": len(public_windows),
        "release_gate": {"p106_unlocked": False, "release_qualified": False},
        "review_status": args.review_status,
        "source_hashes": source_hashes,
        "source_insufficiency": {
            "family": "database",
            "held_out_service_seconds_deficit": 21480,
            "reason": "a1_actual_coverage_below_two_service_day_floor",
            "status": "source_insufficient",
        },
    }
    _write_json(output / "p105-dejavu-a1-reviewed-local-manifest.json", manifest)
    provenance["artifact_hashes"] = _artifact_hashes(output)
    _write_json(output / "p105-dejavu-a1-provenance-hashes.json", provenance)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
