"""P43 opt-in public dataset download and benchmark scorecard.

Default mode is offline fixture fallback. Explicit allow-network mode downloads
small public samples, materializes them into P41 raw replay format, and scores
those materialized files without committing generated data.
"""

from __future__ import annotations

import csv
import json
import re
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from app.services.raw_real_dataset_replay import run_raw_real_dataset_replay_fixture
from app.services.redaction import redact_text, redact_value

_REMOTE_PREFIXES = ("http://", "https://")
_SEVERITY_MARKERS = ("error", "fail", "fatal", "crit", "exception", "timeout", "denied")
_BOUNDARY_BASE: dict[str, bool] = {
    "live_api_calls_enabled": False,
    "auth_session_work_enabled": False,
    "production_mutation_enabled": False,
    "remediation_execution_enabled": False,
    "unrestricted_shell_enabled": False,
    "default_external_model_calls": False,
    "unattended_production_operation_claimed": False,
}


@dataclass(frozen=True)
class PublicBenchmarkSource:
    id: str
    family: str
    data_url: str
    official_url: str
    local_fixture: str
    expected_root_cause: str
    expected_route: str
    expected_labels: tuple[str, ...]
    labels_url: str | None = None
    nab_label_key: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PublicBenchmarkSource:
        labels_url = data.get("labels_url")
        nab_label_key = data.get("nab_label_key")
        return cls(
            id=str(data.get("id", "public-source")),
            family=str(data.get("family", "unknown")),
            data_url=str(data.get("data_url", "")),
            official_url=str(data.get("official_url", "")),
            local_fixture=str(data.get("local_fixture", "")),
            expected_root_cause=str(data.get("expected_root_cause", "unknown")),
            expected_route=str(data.get("expected_route", "human_required")),
            expected_labels=tuple(str(item) for item in _sequence(data.get("expected_labels", ()))),
            labels_url=str(labels_url) if labels_url is not None else None,
            nab_label_key=str(nab_label_key) if nab_label_key is not None else None,
        )


@dataclass(frozen=True)
class PublicBenchmarkManifest:
    version: str
    artifact_root: str
    materialized_root: str
    max_records_per_source: int
    sources: tuple[PublicBenchmarkSource, ...]

    @classmethod
    def from_path(cls, path: str | Path) -> PublicBenchmarkManifest:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, Mapping):
            raise ValueError("P43 public benchmark manifest must be a mapping")
        sources = tuple(PublicBenchmarkSource.from_dict(item) for item in _sequence(data.get("sources", ())) if isinstance(item, Mapping))
        return cls(
            version=str(data.get("version", "p43")),
            artifact_root=str(data.get("artifact_root", "/tmp/opscat-public-datasets")),
            materialized_root=str(data.get("materialized_root", "/tmp/opscat-public-materialized")),
            max_records_per_source=int(data.get("max_records_per_source", 2000)),
            sources=sources,
        )


@dataclass(frozen=True)
class PublicArtifactCard:
    source_id: str
    artifact_type: str
    url: str
    path: str
    status: str
    bytes_written: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "source_id": self.source_id,
            "artifact_type": self.artifact_type,
            "url": self.url,
            "path": self.path,
            "status": self.status,
            "bytes_written": self.bytes_written,
            "error": self.error,
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


@dataclass(frozen=True)
class MaterializedSourceCard:
    source_id: str
    family: str
    path: str
    record_count: int
    label_counts: Mapping[str, int]
    mode: str

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "source_id": self.source_id,
            "family": self.family,
            "path": self.path,
            "record_count": self.record_count,
            "label_counts": dict(self.label_counts),
            "mode": self.mode,
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


@dataclass(frozen=True)
class PublicDatasetBenchmarkReport:
    manifest: PublicBenchmarkManifest
    artifact_cards: tuple[PublicArtifactCard, ...]
    materialized_cards: tuple[MaterializedSourceCard, ...]
    materialized_manifest: Mapping[str, Any]
    score: Mapping[str, Any]
    allow_network: bool
    dataset_mode: str

    def to_dict(self) -> dict[str, Any]:
        download_count = sum(1 for card in self.artifact_cards if card.bytes_written > 0)
        parsed_records = int(self.score.get("parsed_record_count", 0))
        payload = {
            "summary": {
                "source_count": len(self.manifest.sources),
                "download_count": download_count,
                "materialized_source_count": len(self.materialized_cards),
                "parsed_record_count": parsed_records,
                "dataset_mode": self.dataset_mode,
                "passed": len(self.materialized_cards) >= 2 and float(self.score.get("root_cause_accuracy", 0.0)) >= 0.9 and float(self.score.get("route_accuracy", 0.0)) >= 0.9,
            },
            "boundary": {
                "network_allowed": self.allow_network,
                "external_downloads_performed": download_count > 0,
                "generated_artifacts_committed": False,
                **_BOUNDARY_BASE,
            },
            "artifact_cards": [card.to_dict() for card in self.artifact_cards],
            "materialized_cards": [card.to_dict() for card in self.materialized_cards],
            "materialized_manifest": self.materialized_manifest,
            "score": dict(self.score),
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


def build_public_dataset_benchmark_report(
    manifest_path: str | Path,
    *,
    allow_network: bool = False,
    artifact_root: str | Path | None = None,
    materialized_root: str | Path | None = None,
    max_bytes: int = 5_000_000,
) -> PublicDatasetBenchmarkReport:
    manifest = PublicBenchmarkManifest.from_path(manifest_path)
    resolved_artifact_root = Path(artifact_root) if artifact_root is not None else Path(manifest.artifact_root)
    resolved_materialized_root = Path(materialized_root) if materialized_root is not None else Path(manifest.materialized_root)
    artifact_cards = _download_artifacts(manifest.sources, resolved_artifact_root, allow_network=allow_network, max_bytes=max_bytes)
    dataset_mode = "downloaded_public_sample" if allow_network and any(card.bytes_written > 0 for card in artifact_cards) else "fixture_fallback"
    materialized_manifest, materialized_cards = _materialize_manifest(
        manifest,
        artifact_cards,
        resolved_artifact_root,
        resolved_materialized_root,
        mode=dataset_mode,
    )
    score = _score_materialized_manifest(materialized_manifest)
    return PublicDatasetBenchmarkReport(
        manifest=manifest,
        artifact_cards=tuple(artifact_cards),
        materialized_cards=tuple(materialized_cards),
        materialized_manifest=materialized_manifest,
        score=score,
        allow_network=allow_network,
        dataset_mode=dataset_mode,
    )


def render_public_dataset_benchmark_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    score = _mapping(payload.get("score"))
    boundary = _mapping(payload.get("boundary"))
    mode = str(summary.get("dataset_mode", "unknown"))
    headline = "Downloaded public sample benchmark" if mode == "downloaded_public_sample" else "Offline fixture fallback benchmark"
    lines = [
        "# OpsCat Public Dataset Benchmark Scorecard",
        "",
        headline,
        "",
        "## Summary",
        f"- Dataset mode: {mode}",
        f"- Source count: {summary.get('source_count')}",
        f"- Download count: {summary.get('download_count')}",
        f"- Materialized sources: {summary.get('materialized_source_count')}",
        f"- Parsed records: {summary.get('parsed_record_count')}",
        f"- Network allowed: {boundary.get('network_allowed')}",
        f"- External downloads performed: {boundary.get('external_downloads_performed')}",
        "",
        "## Score",
        f"- Label coverage: {score.get('label_coverage')}",
        f"- Root-cause accuracy: {score.get('root_cause_accuracy')}",
        f"- Route accuracy: {score.get('route_accuracy')}",
        f"- Unsafe actions: {score.get('unsafe_action_count')}",
        "",
        "## Materialized sources",
    ]
    for card in _sequence(payload.get("materialized_cards", ())):
        if isinstance(card, Mapping):
            lines.append(f"- `{card.get('source_id')}` family={card.get('family')} records={card.get('record_count')} mode={card.get('mode')} path={card.get('path')}")
    return "\n".join(lines) + "\n"


def write_public_dataset_benchmark_outputs(payload: Mapping[str, Any], *, output_json: str | Path | None = None, output_md: str | Path | None = None) -> None:
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(render_public_dataset_benchmark_markdown(payload), encoding="utf-8")


def _download_artifacts(sources: Sequence[PublicBenchmarkSource], artifact_root: Path, *, allow_network: bool, max_bytes: int) -> list[PublicArtifactCard]:
    cards: list[PublicArtifactCard] = []
    for source in sources:
        cards.append(_artifact_card(source, "data", source.data_url, artifact_root, allow_network=allow_network, max_bytes=max_bytes))
        if source.labels_url:
            cards.append(_artifact_card(source, "labels", source.labels_url, artifact_root, allow_network=allow_network, max_bytes=max_bytes))
    return cards


def _artifact_card(source: PublicBenchmarkSource, artifact_type: str, url: str, artifact_root: Path, *, allow_network: bool, max_bytes: int) -> PublicArtifactCard:
    path = _artifact_path(artifact_root, source.id, artifact_type, url)
    if not url.startswith(_REMOTE_PREFIXES):
        return PublicArtifactCard(source.id, artifact_type, url, str(path), "unsupported_url")
    if not allow_network:
        return PublicArtifactCard(source.id, artifact_type, url, str(path), "network_opt_in_required")
    try:
        bytes_written = _download(url, path, max_bytes=max_bytes)
    except OSError as exc:
        return PublicArtifactCard(source.id, artifact_type, url, str(path), "download_failed", error=str(exc))
    return PublicArtifactCard(source.id, artifact_type, url, str(path), "downloaded", bytes_written=bytes_written)


def _download(url: str, path: Path, *, max_bytes: int) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=20) as response:  # noqa: S310 - explicit user opt-in public dataset download.
        payload = response.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise OSError(f"public dataset artifact exceeds max_bytes={max_bytes}")
    path.write_bytes(payload)
    return len(payload)


def _materialize_manifest(
    manifest: PublicBenchmarkManifest,
    artifact_cards: Sequence[PublicArtifactCard],
    artifact_root: Path,
    materialized_root: Path,
    *,
    mode: str,
) -> tuple[dict[str, Any], list[MaterializedSourceCard]]:
    sources: list[dict[str, Any]] = []
    cards: list[MaterializedSourceCard] = []
    card_lookup = {(card.source_id, card.artifact_type): card for card in artifact_cards}
    for source in manifest.sources:
        source_mode = mode
        if mode == "downloaded_public_sample" and card_lookup.get((source.id, "data"), PublicArtifactCard(source.id, "data", "", "", "missing")).status == "downloaded":
            data_path = Path(card_lookup[(source.id, "data")].path)
            label_card = card_lookup.get((source.id, "labels"))
            labels_path = Path(label_card.path) if label_card is not None and label_card.status == "downloaded" else None
            output_path, record_count, label_counts, family = _materialize_downloaded_source(
                source,
                data_path,
                labels_path,
                materialized_root,
                max_records=manifest.max_records_per_source,
            )
        else:
            source_mode = "fixture_fallback"
            output_path = Path(source.local_fixture)
            record_count, label_counts, family = _count_existing_fixture(source, output_path)
        cards.append(MaterializedSourceCard(source.id, family, str(output_path), record_count, label_counts, source_mode))
        sources.append(
            {
                "id": f"p43-{source.id}",
                "family": family,
                "path": str(output_path),
                "expected_root_cause": source.expected_root_cause,
                "expected_route": source.expected_route,
                "expected_labels": list(source.expected_labels),
            }
        )
    return {"version": "p43-materialized", "sources": sources}, cards


def _materialize_downloaded_source(source: PublicBenchmarkSource, data_path: Path, labels_path: Path | None, materialized_root: Path, *, max_records: int) -> tuple[Path, int, dict[str, int], str]:
    materialized_root.mkdir(parents=True, exist_ok=True)
    if source.family == "loghub_raw":
        output = materialized_root / f"{source.id}.jsonl"
        return _materialize_loghub_raw(data_path, output, max_records=max_records)
    if source.family == "nab_csv":
        output = materialized_root / f"{source.id}.csv"
        return _materialize_nab_csv(source, data_path, labels_path, output, max_records=max_records)
    raise ValueError(f"unsupported P43 source family: {source.family}")


def _materialize_loghub_raw(data_path: Path, output_path: Path, *, max_records: int) -> tuple[Path, int, dict[str, int], str]:
    counts: dict[str, int] = {}
    record_count = 0
    with data_path.open(encoding="utf-8", errors="replace") as source, output_path.open("w", encoding="utf-8") as target:
        for line in source:
            if record_count >= max_records:
                break
            message = redact_text(line.strip())
            if not message:
                continue
            label = "deploy_error" if _looks_like_error(message) else "normal"
            counts[label] = counts.get(label, 0) + 1
            target.write(json.dumps({"message": message, "label": label}, sort_keys=True) + "\n")
            record_count += 1
    return output_path, record_count, counts, "loghub"


def _materialize_nab_csv(source: PublicBenchmarkSource, data_path: Path, labels_path: Path | None, output_path: Path, *, max_records: int) -> tuple[Path, int, dict[str, int], str]:
    windows = _load_nab_windows(labels_path, source.nab_label_key) if labels_path else []
    rows: list[dict[str, str]] = []
    with data_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for index, row in enumerate(reader):
            if index >= max_records:
                break
            rows.append({"timestamp": str(row.get("timestamp", "")), "value": str(row.get("value", ""))})
    anomaly_indexes = _window_anomaly_indexes(rows, windows)
    if not anomaly_indexes and rows:
        anomaly_indexes = {_max_value_index(rows)}
    counts = {"normal": 0, "anomaly": 0}
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["timestamp", "value", "is_anomaly"])
        writer.writeheader()
        for index, row in enumerate(rows):
            label = "anomaly" if index in anomaly_indexes else "normal"
            counts[label] += 1
            writer.writerow({"timestamp": row["timestamp"], "value": row["value"], "is_anomaly": str(index in anomaly_indexes).lower()})
    return output_path, len(rows), {key: value for key, value in counts.items() if value > 0}, "nab"


def _load_nab_windows(labels_path: Path | None, key: str | None) -> list[tuple[datetime, datetime]]:
    if labels_path is None or key is None:
        return []
    data = json.loads(labels_path.read_text(encoding="utf-8"))
    raw_windows = data.get(key, []) if isinstance(data, Mapping) else []
    windows: list[tuple[datetime, datetime]] = []
    for item in _sequence(raw_windows):
        if isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)) and len(item) >= 2:
            try:
                windows.append((_parse_dt(str(item[0])), _parse_dt(str(item[1]))))
            except ValueError:
                continue
    return windows


def _window_anomaly_indexes(rows: Sequence[Mapping[str, str]], windows: Sequence[tuple[datetime, datetime]]) -> set[int]:
    indexes: set[int] = set()
    for index, row in enumerate(rows):
        try:
            timestamp = _parse_dt(str(row.get("timestamp", "")))
        except ValueError:
            continue
        if any(start <= timestamp <= end for start, end in windows):
            indexes.add(index)
    return indexes


def _count_existing_fixture(source: PublicBenchmarkSource, path: Path) -> tuple[int, dict[str, int], str]:
    if source.family == "loghub_raw":
        counts: dict[str, int] = {}
        rows = 0
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            label = str(item.get("label", "unknown")) if isinstance(item, Mapping) else "unknown"
            counts[label] = counts.get(label, 0) + 1
            rows += 1
        return rows, counts, "loghub"
    if source.family == "nab_csv":
        counts = {}
        rows = 0
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                label = "anomaly" if str(row.get("is_anomaly", "false")).lower() == "true" else "normal"
                counts[label] = counts.get(label, 0) + 1
                rows += 1
        return rows, counts, "nab"
    raise ValueError(f"unsupported fixture family: {source.family}")


def _score_materialized_manifest(materialized_manifest: Mapping[str, Any]) -> dict[str, Any]:
    with NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
        json.dump(materialized_manifest, handle)
        handle.write("\n")
        path = Path(handle.name)
    try:
        payload = run_raw_real_dataset_replay_fixture(path).to_dict()
    finally:
        path.unlink(missing_ok=True)
    score = _mapping(payload.get("score"))
    summary = _mapping(payload.get("summary"))
    return {
        "raw_source_count": summary.get("raw_source_count", 0),
        "parsed_record_count": summary.get("parsed_record_count", 0),
        "label_coverage": score.get("label_coverage", 0.0),
        "root_cause_accuracy": score.get("root_cause_accuracy", 0.0),
        "route_accuracy": score.get("route_accuracy", 0.0),
        "unsafe_action_count": score.get("unsafe_action_count", 0),
    }


def _artifact_path(root: Path, source_id: str, artifact_type: str, url: str) -> Path:
    name = Path(url).name or f"{artifact_type}.dat"
    return root / source_id / artifact_type / _safe_filename(name)


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", value)


def _looks_like_error(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in _SEVERITY_MARKERS)


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _max_value_index(rows: Sequence[Mapping[str, str]]) -> int:
    best_index = 0
    best_value = float("-inf")
    for index, row in enumerate(rows):
        try:
            value = float(str(row.get("value", "nan")))
        except ValueError:
            value = float("-inf")
        if value > best_value:
            best_index = index
            best_value = value
    return best_index


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
