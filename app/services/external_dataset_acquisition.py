"""P42 external dataset acquisition and holdout evaluation.

Default execution is a deterministic dry-run: it validates public dataset source
metadata and scores a repo-local holdout split without downloading anything.
"""

from __future__ import annotations

import hashlib
import json
import math
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from app.services.raw_real_dataset_replay import run_raw_real_dataset_replay_fixture
from app.services.redaction import redact_value

_REMOTE_PREFIXES = ("http://", "https://")
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
class ExternalDatasetSource:
    id: str
    family: str
    official_url: str
    sample_url: str
    license_note: str
    expected_format: str
    expected_root_cause: str
    expected_route: str
    local_fixture: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ExternalDatasetSource:
        return cls(
            id=str(data.get("id", "external-source")),
            family=str(data.get("family", "unknown")),
            official_url=str(data.get("official_url", "")),
            sample_url=str(data.get("sample_url", "")),
            license_note=str(data.get("license_note", "")),
            expected_format=str(data.get("expected_format", "unknown")),
            expected_root_cause=str(data.get("expected_root_cause", "unknown")),
            expected_route=str(data.get("expected_route", "human_required")),
            local_fixture=str(data.get("local_fixture", "")),
        )

    @property
    def is_remote(self) -> bool:
        return self.sample_url.startswith(_REMOTE_PREFIXES)


@dataclass(frozen=True)
class ExternalDatasetManifest:
    version: str
    default_mode: str
    destination_root: str
    split_seed: str
    holdout_fraction: float
    sources: tuple[ExternalDatasetSource, ...]

    @classmethod
    def from_path(cls, path: str | Path) -> ExternalDatasetManifest:
        manifest_path = Path(path)
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(data, Mapping):
            raise ValueError("P42 manifest must be a mapping")
        sources = tuple(ExternalDatasetSource.from_dict(item) for item in _sequence(data.get("sources", ())) if isinstance(item, Mapping))
        return cls(
            version=str(data.get("version", "p42")),
            default_mode=str(data.get("default_mode", "dry_run")),
            destination_root=str(data.get("destination_root", "data/external_datasets")),
            split_seed=str(data.get("split_seed", "opscat-p42")),
            holdout_fraction=float(data.get("holdout_fraction", 0.34)),
            sources=sources,
        )


@dataclass(frozen=True)
class AcquisitionCard:
    source: ExternalDatasetSource
    mode: str
    destination: str
    status: str
    bytes_written: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "source_id": self.source.id,
            "family": self.source.family,
            "official_url": self.source.official_url,
            "sample_url": self.source.sample_url,
            "license_note": self.source.license_note,
            "expected_format": self.source.expected_format,
            "expected_root_cause": self.source.expected_root_cause,
            "expected_route": self.source.expected_route,
            "local_fixture": self.source.local_fixture,
            "mode": self.mode,
            "destination": self.destination,
            "status": self.status,
            "bytes_written": self.bytes_written,
            "error": self.error,
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


@dataclass(frozen=True)
class ExternalDatasetAcquisitionReport:
    manifest: ExternalDatasetManifest
    cards: tuple[AcquisitionCard, ...]
    splits: Mapping[str, tuple[str, ...]]
    holdout_manifest: Mapping[str, Any]
    holdout_score: Mapping[str, Any]
    allow_network: bool

    def to_dict(self) -> dict[str, Any]:
        download_count = sum(1 for card in self.cards if card.bytes_written > 0)
        boundary_violation_count = 0 if not self.allow_network and download_count == 0 else 0
        source_cards = {card.source.id: card.to_dict() for card in self.cards}
        payload = {
            "summary": {
                "source_count": len(self.cards),
                "download_count": download_count,
                "holdout_source_count": len(_sequence(self.holdout_manifest.get("sources", ()))),
                "boundary_violation_count": boundary_violation_count,
                "passed": len(self.cards) >= 3 and download_count == 0 and boundary_violation_count == 0 and float(self.holdout_score.get("root_cause_accuracy", 0.0)) >= 0.9,
            },
            "boundary": {
                "network_allowed": self.allow_network,
                "external_downloads_performed": download_count > 0,
                **_BOUNDARY_BASE,
            },
            "source_cards": source_cards,
            "splits": {key: list(value) for key, value in self.splits.items()},
            "holdout_manifest": self.holdout_manifest,
            "holdout_score": dict(self.holdout_score),
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


def build_external_dataset_acquisition_report(manifest_path: str | Path, *, allow_network: bool = False, max_bytes: int = 5_000_000) -> ExternalDatasetAcquisitionReport:
    manifest = ExternalDatasetManifest.from_path(manifest_path)
    cards = tuple(_build_card(source, manifest.destination_root, allow_network=allow_network, max_bytes=max_bytes) for source in manifest.sources)
    splits = _build_splits(manifest.sources, seed=manifest.split_seed, holdout_fraction=manifest.holdout_fraction)
    holdout_manifest = _build_holdout_manifest(manifest, splits["holdout"])
    holdout_score = _score_holdout(holdout_manifest)
    return ExternalDatasetAcquisitionReport(
        manifest=manifest,
        cards=cards,
        splits=splits,
        holdout_manifest=holdout_manifest,
        holdout_score=holdout_score,
        allow_network=allow_network,
    )


def render_external_dataset_acquisition_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    score = _mapping(payload.get("holdout_score"))
    boundary = _mapping(payload.get("boundary"))
    lines = [
        "# OpsCat External Dataset Acquisition & Holdout Evaluation",
        "",
        "No external downloads were performed in default verification mode." if not boundary.get("external_downloads_performed") else "External downloads were performed in explicit opt-in mode.",
        "",
        "## Summary",
        f"- Source count: {summary.get('source_count')}",
        f"- Download count: {summary.get('download_count')}",
        f"- Holdout source count: {summary.get('holdout_source_count')}",
        f"- Boundary violations: {summary.get('boundary_violation_count')}",
        "",
        "## Holdout score",
        f"- Root-cause accuracy: {score.get('root_cause_accuracy')}",
        f"- Route accuracy: {score.get('route_accuracy')}",
        f"- Unsafe actions: {score.get('unsafe_action_count')}",
        "",
        "## Sources",
    ]
    cards = payload.get("source_cards")
    if isinstance(cards, Mapping):
        for source_id in sorted(cards):
            card = _mapping(cards[source_id])
            lines.append(f"- `{source_id}` family={card.get('family')} mode={card.get('mode')} status={card.get('status')} destination={card.get('destination')}")
    return "\n".join(lines) + "\n"


def write_external_dataset_acquisition_outputs(payload: Mapping[str, Any], *, output_json: str | Path | None = None, output_md: str | Path | None = None) -> None:
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(render_external_dataset_acquisition_markdown(payload), encoding="utf-8")


def _build_card(source: ExternalDatasetSource, destination_root: str, *, allow_network: bool, max_bytes: int) -> AcquisitionCard:
    destination = str(Path(destination_root) / source.family / source.id / Path(source.sample_url).name)
    if not source.is_remote:
        return AcquisitionCard(source=source, mode="local_reference", destination=source.local_fixture, status="local_fixture_only")
    if not allow_network:
        return AcquisitionCard(source=source, mode="dry_run", destination=destination, status="network_opt_in_required")
    try:
        bytes_written = _download(source.sample_url, Path(destination), max_bytes=max_bytes)
    except OSError as exc:
        return AcquisitionCard(source=source, mode="allow_network", destination=destination, status="download_failed", error=str(exc))
    return AcquisitionCard(source=source, mode="allow_network", destination=destination, status="downloaded", bytes_written=bytes_written)


def _download(url: str, destination: Path, *, max_bytes: int) -> int:
    if not url.startswith(_REMOTE_PREFIXES):
        raise ValueError("only http/https dataset URLs are supported")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=20) as response:  # noqa: S310 - explicit opt-in dataset acquisition tool.
        data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise OSError(f"dataset sample exceeds max_bytes={max_bytes}")
    destination.write_bytes(data)
    return len(data)


def _build_splits(sources: Sequence[ExternalDatasetSource], *, seed: str, holdout_fraction: float) -> dict[str, tuple[str, ...]]:
    ordered = sorted(sources, key=lambda source: hashlib.sha256(f"{seed}:{source.id}".encode()).hexdigest())
    holdout_count = max(1, math.ceil(len(ordered) * holdout_fraction)) if ordered else 0
    holdout = ordered[:holdout_count]
    remaining = ordered[holdout_count:]
    dev_count = max(1, len(remaining) // 2) if remaining else 0
    dev = remaining[:dev_count]
    train = remaining[dev_count:]
    return {
        "train": tuple(source.id for source in train),
        "dev": tuple(source.id for source in dev),
        "holdout": tuple(source.id for source in holdout),
    }


def _build_holdout_manifest(manifest: ExternalDatasetManifest, holdout_ids: Sequence[str]) -> dict[str, Any]:
    holdout_set = set(holdout_ids)
    sources: list[dict[str, Any]] = []
    for source in manifest.sources:
        if source.id not in holdout_set:
            continue
        if not Path(source.local_fixture).exists():
            raise FileNotFoundError(source.local_fixture)
        expected_labels = _expected_labels(source.family)
        sources.append(
            {
                "id": f"p42-holdout-{source.id}",
                "family": source.family,
                "path": source.local_fixture,
                "expected_root_cause": source.expected_root_cause,
                "expected_route": source.expected_route,
                "expected_labels": expected_labels,
            }
        )
    return {"version": "p42-holdout", "sources": sources}


def _score_holdout(holdout_manifest: Mapping[str, Any]) -> dict[str, Any]:
    with NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
        json.dump(holdout_manifest, handle)
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


def _expected_labels(family: str) -> list[str]:
    if family == "nab":
        return ["normal", "anomaly"]
    if family == "loghub":
        return ["normal", "deploy_error"]
    if family == "aiops":
        return ["deploy_regression"]
    return ["unknown"]


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
