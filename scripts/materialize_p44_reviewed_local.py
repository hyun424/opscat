from __future__ import annotations

# ruff: noqa: E402, I001

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any
from datetime import UTC, datetime, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parsed = json.loads(line)
        if isinstance(parsed, dict):
            rows.append(parsed)
    return rows


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _parse_timestamp(value: str) -> datetime:
    text = str(value).strip()
    if not text:
        raise ValueError("empty timestamp")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%y%m%d %H%M%S"):
        try:
            parsed = datetime.strptime(text, fmt).replace(tzinfo=UTC)
            return parsed
        except ValueError:
            pass
    parsed = datetime.fromisoformat(text)
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _format_ts(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _raw_manifest_fail(code: str, details: list[str]) -> None:
    payload = {"error": "p44_raw_manifest_fail_closed", "reason_code": code, "details": details}
    raise ValueError(json.dumps(payload, sort_keys=True))


def _resolve_path(base: Path, value: Any) -> Path:
    path = Path(str(value or ""))
    if not path.is_absolute():
        path = base / path
    return path


def _required_mapping(source: dict[str, Any]) -> dict[str, Any]:
    mapping = source.get("family_proxy_mapping")
    return dict(mapping) if isinstance(mapping, dict) else {}


def _validate_raw_manifest_source(source: dict[str, Any], manifest_path: Path) -> list[str]:
    codes: list[str] = []
    source_type = str(source.get("source_type") or "")
    source_path = _resolve_path(manifest_path.parent, source.get("path"))
    if not source_path.is_file():
        codes.append("raw_source_path_missing")
    if not source.get("expected_sha256"):
        codes.append("source_hash_missing")
    elif source_path.is_file() and source.get("expected_sha256") != _sha256_path(source_path):
        codes.append("source_hash_mismatch")
    if not source.get("license_name") or not source.get("license_url") or not source.get("citation_text"):
        codes.append("source_license_missing")
    if not source.get("privacy_review_status") or not source.get("redaction_decisions"):
        codes.append("privacy_review_missing")
    mapping = _required_mapping(source)
    if not mapping.get("mapping_review_status") or not mapping.get("evidence"):
        codes.append("family_mapping_review_missing")
    if source_type == "nab_csv":
        if not source.get("timestamp_field"):
            codes.append("source_timestamp_missing")
        labels_path_value = source.get("labels_json_path")
        if not labels_path_value:
            codes.append("nab_labels_json_missing")
        else:
            labels_path = _resolve_path(manifest_path.parent, labels_path_value)
            if not labels_path.is_file():
                codes.append("nab_labels_json_missing")
            elif not source.get("labels_json_hash"):
                codes.append("nab_labels_json_hash_missing")
            elif source.get("labels_json_hash") != _sha256_path(labels_path):
                codes.append("nab_labels_json_hash_mismatch")
    return codes


def _partition_for(record_seed: dict[str, Any]) -> str:
    digest = _sha256_text(_stable_json(record_seed))
    return "held_out" if int(digest[:2], 16) % 2 == 0 else "real_derived_shadow"


def _materialized_hash(record: dict[str, Any]) -> str:
    return _sha256_text(_stable_json({"reviewed_public_record": record}))


def _p24_input(*, window_id: str, family: str, start: str, end: str, value: float | None, metric: str) -> dict[str, Any]:
    risk_type = {
        "database": "connection_pool_saturation",
        "queue": "queue_sla_breach",
        "deploy": "error_budget_burn",
    }.get(family, "connection_pool_saturation")
    current = float(value if value is not None else 1.0)
    baseline = max(1.0, current / 4.0)
    threshold = max(10.0, current * 1.1)
    return {
        "id": window_id,
        "window_id": window_id,
        "window_start_timestamp": start,
        "window_end_timestamp": end,
        "service": f"{family}-service",
        "metric": metric,
        "risk_type": risk_type,
        "window_minutes": 15,
        "baseline": baseline,
        "threshold": threshold,
        "values": [baseline, baseline * 1.2, baseline * 1.5, baseline * 1.8, current],
        "evidence": [{"id": f"metric:{window_id}", "type": "metric", "content": "reviewed local P44 public metric"}],
        "suggested_approval_actions": ["report"],
        "blocked_actions": ["kubectl_restart", "shell_execute"],
        "local_mock_only": True,
    }


def _load_nab_windows(labels_path: Path, manifest_key: str) -> list[tuple[datetime, datetime, str]]:
    payload = json.loads(labels_path.read_text(encoding="utf-8"))
    windows = payload.get(manifest_key, []) if isinstance(payload, dict) else []
    parsed: list[tuple[datetime, datetime, str]] = []
    for index, item in enumerate(windows):
        if isinstance(item, list) and len(item) >= 2:
            start = _parse_timestamp(str(item[0]))
            end = _parse_timestamp(str(item[1]))
            parsed.append((start, end, f"{manifest_key}#{index}"))
    return parsed


def _nab_public_records(source: dict[str, Any], manifest_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source_path = _resolve_path(manifest_path.parent, source.get("path"))
    source_hash = _sha256_path(source_path)
    timestamp_field = str(source["timestamp_field"])
    rows = list(csv.DictReader(source_path.read_text(encoding="utf-8").splitlines()))
    timestamps: list[datetime] = []
    records: list[dict[str, Any]] = []
    mapping = _required_mapping(source)
    family = str(mapping.get("family") or "unsupported_family")
    for row_index, row in enumerate(rows):
        ts = _parse_timestamp(str(row.get(timestamp_field) or ""))
        timestamps.append(ts)
        start = _format_ts(ts)
        end = _format_ts(ts + timedelta(minutes=5))
        value = float(row["value"]) if str(row.get("value", "")).strip() else None
        source_window_id = f"{source['source_key']}:row:{row_index}"
        seed = {
            "canonical_raw_bytes": _stable_json(row),
            "record_offset_or_row_index": row_index,
            "source_manifest_key": source.get("source_manifest_key"),
            "source_timestamp": start,
            "versioned_salt": "p44-reviewed-local-sampler-v1",
        }
        partition = _partition_for(seed)
        metric_name = Path(str(source.get("source_manifest_key") or source_path.name)).stem
        public_features = {
            "source_window_id": source_window_id,
            "metric": metric_name,
            "value": value,
            "timestamp": start,
            "window_start_timestamp": start,
            "window_end_timestamp": end,
            "source_content_hash": source_hash,
        }
        record = {
            "reviewed_record_id": f"p44-reviewed-{_sha256_text(_stable_json(seed))[:16]}",
            "record_id": f"p44-reviewed-{_sha256_text(_stable_json(seed))[:16]}",
            "source_key": source["source_key"],
            "source_dataset": source.get("source_dataset"),
            "source_manifest_key": source.get("source_manifest_key"),
            "source_window_id": source_window_id,
            "source_timestamp": start,
            "timestamp": start,
            "window_start_timestamp": start,
            "window_end_timestamp": end,
            "row_index": row_index,
            "pre_label_partition": partition,
            "partition": partition,
            "family": family,
            "family_proxy_mapping": mapping,
            "countable_for_release_floors": mapping.get("mapping_review_status") == "reviewed_supported" and family != "unsupported_family",
            "public_features": public_features,
            "p24_input": _p24_input(window_id=source_window_id, family=family, start=start, end=end, value=value, metric=metric_name),
        }
        record["public_feature_hash"] = _sha256_text(_stable_json(public_features))
        record["p24_input_hash"] = _sha256_text(_stable_json(record["p24_input"]))
        record["materialized_record_hash"] = _materialized_hash(record)
        records.append(record)
    summary = {
        **source,
        "local_path": str(source_path),
        "source_content_hash": source_hash,
        "source_content_hash_algorithm": "sha256",
        "source_byte_count": source_path.stat().st_size,
        "record_count": len(records),
        "timestamp_min": _format_ts(min(timestamps)) if timestamps else None,
        "timestamp_max": _format_ts(max(timestamps)) if timestamps else None,
    }
    return records, summary


def _parse_loghub_timestamp(line: str) -> datetime:
    parts = line.split()
    if len(parts) >= 2:
        return _parse_timestamp(f"{parts[0]} {parts[1]}")
    raise ValueError("loghub timestamp missing")


def _loghub_public_records(source: dict[str, Any], manifest_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source_path = _resolve_path(manifest_path.parent, source.get("path"))
    source_hash = _sha256_path(source_path)
    lines = source_path.read_text(encoding="utf-8").splitlines()
    mapping = _required_mapping(source)
    family = str(mapping.get("family") or "unsupported_family")
    records: list[dict[str, Any]] = []
    timestamps: list[datetime] = []
    for line_index, line in enumerate(lines):
        if not line.strip():
            continue
        ts = _parse_loghub_timestamp(line)
        timestamps.append(ts)
        start = _format_ts(ts)
        end = _format_ts(ts + timedelta(seconds=1))
        level = line.split()[3] if len(line.split()) > 3 else "INFO"
        source_window_id = f"{source['source_key']}:line:{line_index}"
        seed = {
            "canonical_raw_bytes": line,
            "record_offset_or_row_index": line_index,
            "source_manifest_key": source.get("source_manifest_key"),
            "source_timestamp": start,
            "versioned_salt": "p44-reviewed-local-sampler-v1",
        }
        partition = _partition_for(seed)
        public_features = {
            "source_window_id": source_window_id,
            "log_level": level,
            "message_template": line.split(":", 1)[0],
            "timestamp": start,
            "window_start_timestamp": start,
            "window_end_timestamp": end,
            "source_content_hash": source_hash,
        }
        record = {
            "reviewed_record_id": f"p44-reviewed-{_sha256_text(_stable_json(seed))[:16]}",
            "record_id": f"p44-reviewed-{_sha256_text(_stable_json(seed))[:16]}",
            "source_key": source["source_key"],
            "source_dataset": source.get("source_dataset"),
            "source_manifest_key": source.get("source_manifest_key"),
            "source_window_id": source_window_id,
            "source_timestamp": start,
            "timestamp": start,
            "window_start_timestamp": start,
            "window_end_timestamp": end,
            "line_start_offset": line_index,
            "line_end_offset": line_index,
            "pre_label_partition": partition,
            "partition": partition,
            "family": family,
            "family_proxy_mapping": mapping,
            "countable_for_release_floors": mapping.get("mapping_review_status") == "reviewed_supported" and family != "unsupported_family",
            "public_features": public_features,
            "p24_input": _p24_input(window_id=source_window_id, family=family, start=start, end=end, value=8.0 if level == "ERROR" else 2.0, metric="loghub.error_rate"),
        }
        record["public_feature_hash"] = _sha256_text(_stable_json(public_features))
        record["p24_input_hash"] = _sha256_text(_stable_json(record["p24_input"]))
        record["materialized_record_hash"] = _materialized_hash(record)
        records.append(record)
    summary = {
        **source,
        "local_path": str(source_path),
        "source_content_hash": source_hash,
        "source_content_hash_algorithm": "sha256",
        "source_byte_count": source_path.stat().st_size,
        "record_count": len(records),
        "timestamp_min": _format_ts(min(timestamps)) if timestamps else None,
        "timestamp_max": _format_ts(max(timestamps)) if timestamps else None,
    }
    return records, summary


def _join_private_labels(sampled: list[dict[str, Any]], raw_sources: list[dict[str, Any]], manifest_path: Path) -> dict[str, Any]:
    source_by_key = {str(source.get("source_key")): source for source in raw_sources}
    ledger_records: list[dict[str, Any]] = []
    for record in sampled:
        source = source_by_key[str(record["source_key"])]
        source_type = str(source.get("source_type") or "")
        if source_type == "nab_csv":
            labels_path = _resolve_path(manifest_path.parent, source["labels_json_path"])
            windows = _load_nab_windows(labels_path, str(source.get("source_manifest_key")))
            source_ts = _parse_timestamp(str(record["source_timestamp"]))
            matched = next(((start, end, key) for start, end, key in windows if start <= source_ts <= end), None)
            positive = matched is not None
            incident_group = f"nab-window-{_sha256_text(matched[2])[:12]}" if matched else None
            label = {
                "record_id": record["record_id"],
                "reviewed_record_id": record["reviewed_record_id"],
                "label_join_source": "official_nab_windows",
                "nab_label_key": matched[2] if matched else str(source.get("source_manifest_key")),
                "labels_json_hash": source.get("labels_json_hash"),
                "official_window_start": _format_ts(matched[0]) if matched else None,
                "official_window_end": _format_ts(matched[1]) if matched else None,
                "source_window_id": record["source_window_id"],
                "source_timestamp": record["source_timestamp"],
                "matched_official_window": matched is not None,
                "label_positive": positive,
                "label_incident_id": incident_group,
                "incident_group_id": incident_group,
                "label_family": record["family"],
                "label_failure_mode": f"{record['family']}_failure",
                "lead_time_label_minutes": 60 if positive else None,
                "unevaluable_reason": None if matched else "outside_official_nab_window",
            }
        elif source_type == "loghub_raw":
            level = str(record["public_features"].get("log_level") or "")
            positive = level == "ERROR"
            incident_group = f"loghub-hdfs-burst-{record['line_start_offset']:04d}"
            label = {
                "record_id": record["record_id"],
                "reviewed_record_id": record["reviewed_record_id"],
                "label_join_source": "deterministic_loghub_error_burst_ledger",
                "parser_version": source.get("parser_version"),
                "burst_predicate_version": source.get("burst_predicate_version"),
                "line_start_offset": record.get("line_start_offset"),
                "line_end_offset": record.get("line_end_offset"),
                "line_offset_start": record.get("line_start_offset"),
                "line_offset_end": record.get("line_end_offset"),
                "window_start_timestamp": record["window_start_timestamp"],
                "window_end_timestamp": record["window_end_timestamp"],
                "source_window_id": record["source_window_id"],
                "source_timestamp": record["source_timestamp"],
                "source_hash": source.get("source_content_hash"),
                "label_positive": positive,
                "label_incident_id": incident_group,
                "incident_group_id": incident_group,
                "label_family": record["family"],
                "label_failure_mode": f"{record['family']}_failure",
                "lead_time_label_minutes": 45 if positive else None,
            }
        else:
            label = {
                "record_id": record["record_id"],
                "reviewed_record_id": record["reviewed_record_id"],
                "label_join_source": "unsupported_source",
                "source_window_id": record["source_window_id"],
                "source_timestamp": record["source_timestamp"],
                "label_positive": False,
                "label_incident_id": None,
                "incident_group_id": None,
                "label_family": record["family"],
                "label_failure_mode": f"{record['family']}_failure",
                "lead_time_label_minutes": None,
            }
        label["canonical_source_tuple"] = {
            "source_system": "p44",
            "source_dataset": record["source_dataset"],
            "source_manifest_key": record["source_manifest_key"],
            "source_content_hash": source.get("source_content_hash"),
            "materialized_record_hash": record["materialized_record_hash"],
            "materialization_version": "p44-reviewed-local-raw-intake-v1",
        }
        label["pre_label_partition_id"] = record["pre_label_partition"]
        label["derivation_id"] = f"derive-{record['reviewed_record_id']}"
        label["label_hash"] = _sha256_text(_stable_json({
            "record_id": label["record_id"],
            "canonical_source_tuple": label["canonical_source_tuple"],
            "incident_group_id": label["incident_group_id"],
            "derivation_id": label["derivation_id"],
            "label_positive": label["label_positive"],
        }))
        ledger_records.append(label)
    return {
        "schema_version": "p105.private_scorer_label_ledger.v1",
        "public_artifact": False,
        "label_join_phase": "after_sampling_and_pre_label_partitioning",
        "label_join_completed_after_sampling": True,
        "max_value_fallback_allowed": False,
        "records": ledger_records,
    }


def _load_raw_manifest_records(raw_manifest: str, source_cap: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[Path]]:
    manifest_path = Path(raw_manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sources = [dict(source) for source in manifest.get("raw_sources") or manifest.get("sources") or [] if isinstance(source, dict)]
    codes: list[str] = []
    for source in sources:
        codes.extend(_validate_raw_manifest_source(source, manifest_path))
    if codes:
        _raw_manifest_fail(sorted(set(codes))[0], sorted(set(codes)))

    records: list[dict[str, Any]] = []
    raw_summaries: list[dict[str, Any]] = []
    source_paths: list[Path] = []
    for source in sources:
        source_path = _resolve_path(manifest_path.parent, source.get("path"))
        source_paths.append(source_path)
        if source.get("source_type") == "nab_csv":
            parsed, summary = _nab_public_records(source, manifest_path)
        elif source.get("source_type") == "loghub_raw":
            parsed, summary = _loghub_public_records(source, manifest_path)
        else:
            continue
        records.extend(parsed)
        raw_summaries.append(summary)

    sampled = sorted(
        records,
        key=lambda row: _stable_json(
            {
                "source_key": row["source_key"],
                "source_manifest_key": row["source_manifest_key"],
                "source_timestamp": row["source_timestamp"],
                "source_window_id": row["source_window_id"],
                "versioned_salt": "p44-reviewed-local-sampler-v1",
            }
        ),
    )[:source_cap]
    return sampled, raw_summaries, source_paths


def _load_raw_records(raw_p44: str | None, raw_manifest: str | None) -> tuple[list[dict[str, Any]], list[Path]]:
    if raw_p44:
        path = Path(raw_p44)
        return _read_jsonl(path), [path]
    if not raw_manifest:
        raise ValueError("one of --raw-p44 or --raw-manifest is required")
    manifest_path = Path(raw_manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records: list[dict[str, Any]] = []
    paths: list[Path] = []
    for source in manifest.get("sources", []):
        if not isinstance(source, dict):
            continue
        source_path = Path(str(source.get("path") or source.get("local_path") or source.get("local_materialized_path") or ""))
        if not source_path.is_absolute():
            source_path = manifest_path.parent / source_path
        paths.append(source_path)
        records.extend(_read_jsonl(source_path))
    return records, paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Materialize reviewed-local P44 public records and sidecars.")
    parser.add_argument("--raw-p44", default=None, help="Test-mode raw P44 JSONL input.")
    parser.add_argument("--raw-manifest", default=None, help="Production flat manifest listing raw P44 JSONL inputs.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--reviewed-by", required=True)
    parser.add_argument("--license-id", required=True)
    parser.add_argument("--citation-id", required=True)
    parser.add_argument("--source-cap", type=int, default=2000)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    if args.raw_manifest and not args.raw_p44:
        try:
            public_records, raw_sources, source_paths = _load_raw_manifest_records(args.raw_manifest, args.source_cap)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

        records_path = output / "p44-reviewed-local-public-records.jsonl"
        records_path.write_text("\n".join(json.dumps(record, sort_keys=True) for record in public_records) + "\n", encoding="utf-8")
        records_hash = hashlib.sha256(records_path.read_bytes()).hexdigest()

        manifest_path = Path(args.raw_manifest)
        ledger = _join_private_labels(public_records, raw_sources, manifest_path)
        partition_payload = {
            "schema_version": "p105.p44_pre_label_partitions.v1",
            "assignment_version": "p44-reviewed-local-pre-label-partition-v1",
            "assignment_inputs": [
                "canonical_raw_bytes",
                "record_offset_or_row_index",
                "source_manifest_key",
                "source_timestamp",
                "versioned_salt",
            ],
            "pre_label_partitions": [
                {
                    "reviewed_record_id": record["reviewed_record_id"],
                    "source_key": record["source_key"],
                    "source_window_id": record["source_window_id"],
                    "partition_id": record["pre_label_partition"],
                    "source_timestamp": record["source_timestamp"],
                }
                for record in public_records
            ],
        }
        pre_label_name = "p44-reviewed-local-pre-label-partitions.json"
        _write_json(output / pre_label_name, partition_payload)
        partition_hash = _sha256_path(output / pre_label_name)
        ledger["pre_label_partition_manifest_hash"] = partition_hash
        ledger_name = "p105-private-scorer-label-ledger.json"
        _write_json(output / ledger_name, ledger)
        ledger_hash = _sha256_path(output / ledger_name)

        privacy_name = "p105-privacy-redaction-manifest.json"
        license_name = "p105-license-manifest.json"
        citation_name = "p105-citation-manifest.json"
        provenance_name = "p105-provenance-hash-manifest.json"
        _write_json(
            output / privacy_name,
            {
                "schema_version": "p105.privacy_redaction.v1",
                "review_status": "reviewed_redacted",
                "reviewed_by": args.reviewed_by,
                "raw_private_labels_embedded": False,
                "sources": [
                    {
                        "source_key": source.get("source_key"),
                        "privacy_review_status": source.get("privacy_review_status"),
                        "redaction_decisions": source.get("redaction_decisions"),
                        "redistribution_status": source.get("redistribution_status"),
                    }
                    for source in raw_sources
                ],
            },
        )
        _write_json(
            output / license_name,
            {
                "schema_version": "p105.license.v1",
                "sources": [
                    {
                        "source_key": source.get("source_key"),
                        "license_name": source.get("license_name"),
                        "license_url": source.get("license_url"),
                        "redistribution_status": source.get("redistribution_status"),
                    }
                    for source in raw_sources
                ],
            },
        )
        _write_json(
            output / citation_name,
            {
                "schema_version": "p105.citation.v1",
                "citations": [
                    {
                        "source_key": source.get("source_key"),
                        "citation_text": source.get("citation_text"),
                    }
                    for source in raw_sources
                ],
            },
        )
        unsupported_count = sum(1 for record in public_records if record.get("family_proxy_mapping", {}).get("mapping_review_status") == "unsupported")
        manifest = {
            "schema_version": "p105.reviewed_p44_local_manifest.v3",
            "materialization_version": "p44-reviewed-local-raw-intake-v1",
            "review_status": "reviewed-local",
            "review_redaction_status": "reviewed_redacted",
            "source_cap": args.source_cap,
            "sampling_policy": {
                "sampled_before_label_join": True,
                "sampler_version": "p44-reviewed-local-sampler-v1",
                "salt_id": "p44-reviewed-local-sampler-v1",
                "max_records": args.source_cap,
                "allowed_sampler_inputs": [
                    "canonical_raw_bytes",
                    "record_offset_or_row_index",
                    "source_manifest_key",
                    "source_timestamp",
                    "versioned_salt",
                ],
            },
            "privacy_manifest_path": privacy_name,
            "license_manifest_path": license_name,
            "citation_manifest_path": citation_name,
            "provenance_hash_manifest_path": provenance_name,
            "private_label_ledger_path": ledger_name,
            "private_ledger_ref": {"path": ledger_name, "sha256": ledger_hash, "public_artifact": False},
            "pre_label_partitions_path": {"path": pre_label_name, "sha256": partition_hash},
            "raw_sources": raw_sources,
            "reviewed_records": [
                {
                    "reviewed_record_id": record["reviewed_record_id"],
                    "source_key": record["source_key"],
                    "source_window_id": record["source_window_id"],
                    "source_timestamp": record["source_timestamp"],
                    "window_start_timestamp": record["window_start_timestamp"],
                    "window_end_timestamp": record["window_end_timestamp"],
                    "public_feature_hash": record["public_feature_hash"],
                    "p24_input_hash": record["p24_input_hash"],
                    "materialized_record_hash": record["materialized_record_hash"],
                    "pre_label_partition_id": record["pre_label_partition"],
                }
                for record in public_records
            ],
            "family_mapping_review_status": {
                "unsupported_family_count": unsupported_count,
                "reviewed_supported_count": len(public_records) - unsupported_count,
            },
            "sources": [
                {
                    "source_id": "p44:reviewed-local",
                    "source_key": "p44:reviewed-local",
                    "family": "multi",
                    "local_materialized_path": str(records_path),
                    "local_source_hash": records_hash,
                    "record_count": len(public_records),
                    "private_label_format": "separate_private_ledger",
                    "partition_format": "pre_label_partition",
                }
            ],
        }
        _write_json(output / "p44-reviewed-local-manifest.json", manifest)
        reviewed_manifest_hash = _sha256_path(output / "p44-reviewed-local-manifest.json")
        ledger["reviewed_local_manifest_hash"] = reviewed_manifest_hash
        _write_json(output / ledger_name, ledger)
        ledger_hash = _sha256_path(output / ledger_name)
        manifest["private_ledger_ref"] = {"path": ledger_name, "sha256": ledger_hash, "public_artifact": False}
        _write_json(output / "p44-reviewed-local-manifest.json", manifest)
        _write_json(
            output / provenance_name,
            {
                "schema_version": "p105.provenance_hash.v1",
                "raw_source_hashes": {str(source.get("source_key")): source.get("source_content_hash") for source in raw_sources},
                "source_paths": [str(path) for path in source_paths],
                "public_records_hash": records_hash,
                "public_records_sha256": records_hash,
                "private_ledger_hash": ledger_hash,
                "private_ledger_sha256": ledger_hash,
                "pre_label_partitions_hash": partition_hash,
                "reviewed_local_manifest_hash": _sha256_path(output / "p44-reviewed-local-manifest.json"),
                "privacy_manifest_hash": _sha256_path(output / privacy_name),
                "license_manifest_hash": _sha256_path(output / license_name),
                "citation_manifest_hash": _sha256_path(output / citation_name),
            },
        )
        print(json.dumps({"manifest_path": str(output / "p44-reviewed-local-manifest.json"), "record_count": len(public_records)}, sort_keys=True))
        return 0

    records, source_paths = _load_raw_records(args.raw_p44, args.raw_manifest)
    sampled = sorted(records, key=lambda row: _stable_json({key: value for key, value in row.items() if key != "private_label"}))[: args.source_cap]
    public_records = []
    for record in sampled:
        copied = dict(record)
        copied.pop("private_label", None)
        public_records.append(copied)

    records_path = output / "p44-reviewed-local-public-records.jsonl"
    records_path.write_text("\n".join(json.dumps(record, sort_keys=True) for record in public_records) + "\n", encoding="utf-8")
    records_hash = hashlib.sha256(records_path.read_bytes()).hexdigest()

    privacy_name = "p105-privacy-redaction-manifest.json"
    license_name = "p105-license-manifest.json"
    citation_name = "p105-citation-manifest.json"
    provenance_name = "p105-provenance-hash-manifest.json"
    _write_json(
        output / privacy_name,
        {
            "schema_version": "p105.privacy_redaction.v1",
            "review_status": "reviewed_redacted",
            "reviewed_by": args.reviewed_by,
            "raw_private_labels_embedded": False,
        },
    )
    _write_json(
        output / license_name,
        {
            "schema_version": "p105.license.v1",
            "sources": [{"source_id": "p44:reviewed-local", "license_id": args.license_id}],
        },
    )
    _write_json(
        output / citation_name,
        {
            "schema_version": "p105.citation.v1",
            "citations": [{"citation_id": args.citation_id, "source_id": "p44:reviewed-local"}],
        },
    )
    _write_json(
        output / provenance_name,
        {
            "schema_version": "p105.provenance_hash.v1",
            "public_records_sha256": records_hash,
            "source_paths": [str(path) for path in source_paths],
        },
    )
    manifest = {
        "schema_version": "p105.reviewed_p44_local_manifest.v3",
        "review_redaction_status": "reviewed_redacted",
        "source_cap": args.source_cap,
        "privacy_manifest_path": privacy_name,
        "license_manifest_path": license_name,
        "citation_manifest_path": citation_name,
        "provenance_hash_manifest_path": provenance_name,
        "sources": [
            {
                "source_id": "p44:reviewed-local",
                "family": "multi",
                "local_materialized_path": str(records_path),
                "local_source_hash": records_hash,
                "record_count": len(public_records),
                "private_label_format": "separate_private_ledger_required",
                "partition_format": "pre_label_partition",
            }
        ],
    }
    _write_json(output / "p44-reviewed-local-manifest.json", manifest)
    print(json.dumps({"manifest_path": str(output / "p44-reviewed-local-manifest.json"), "record_count": len(public_records)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
