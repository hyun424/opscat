"""Pinned, system-generic RCAEval RE1 archive loader for P112."""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import posixpath
import stat
import statistics
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.p110_acquisition import validate_local_archive
from app.services.p110_rcaeval import P110EvidenceFeature, _extract_features, _read_metric_rows

CASE_SCHEMA_VERSION = "p112.re1_case.v1"
CANDIDATE_SCHEMA_VERSION = "p112.re1_candidate_packet.v1"
TRUTH_SCHEMA_VERSION = "p112.re1_scorer_truth.v1"
ALLOWED_FAULTS = frozenset({"cpu", "mem", "disk", "delay", "loss"})
ALLOWED_REPETITIONS = frozenset({1, 2, 3, 4, 5})
_CASE_ID_DOMAIN = "p112.re1.case-id.v1"
_MAX_FILES = 512
_MAX_UNCOMPRESSED_BYTES = 768 * 1024 * 1024


class P112RE1Error(ValueError):
    """Raised when a pinned RE1 archive violates the P112 contract."""


@dataclass(frozen=True)
class P112RE1Case:
    case_id: str
    system: str
    source_path: str
    inject_time: str
    official_source_hash: str
    raw_hashes: Mapping[str, str]
    scorer_only_truth: Mapping[str, Any]
    features: tuple[P110EvidenceFeature, ...]
    diagnostic_features: tuple[Mapping[str, Any], ...]
    schema_version: str = CASE_SCHEMA_VERSION

    @property
    def service_catalog(self) -> tuple[str, ...]:
        return tuple(sorted({item.service for item in self.features}))

    @property
    def metric_catalog(self) -> tuple[str, ...]:
        return tuple(sorted({item.metric for item in self.features}))

    def to_candidate_packet(self) -> dict[str, Any]:
        packet = {
            "schema_version": CANDIDATE_SCHEMA_VERSION,
            "case_id": self.case_id,
            "system": self.system,
            "injection_timestamp": self.inject_time,
            "service_catalog": list(self.service_catalog),
            "metric_catalog": list(self.metric_catalog),
            "evidence": [item.to_candidate_dict() for item in self.features],
            "diagnostic_evidence": [dict(item) for item in self.diagnostic_features],
        }
        reject_candidate_truth_leak((packet,))
        return packet

    def to_scorer_truth(self) -> dict[str, Any]:
        return {
            "schema_version": TRUTH_SCHEMA_VERSION,
            "case_id": self.case_id,
            "scorer_only_truth": dict(self.scorer_only_truth),
            "official_source_hash": self.official_source_hash,
            "evidence_ids": [item.evidence_id for item in self.features],
            "source_path": self.source_path,
            "raw_hashes": dict(sorted(self.raw_hashes.items())),
        }


def load_pinned_re1_cases(
    archive_path: str | Path,
    manifest_path: str | Path,
    *,
    hmac_key: bytes,
    max_files: int = _MAX_FILES,
    max_uncompressed_bytes: int = _MAX_UNCOMPRESSED_BYTES,
) -> tuple[P112RE1Case, ...]:
    if not hmac_key:
        raise P112RE1Error("hmac_key_required")
    archive = Path(archive_path)
    manifest_file = Path(manifest_path)
    source = validate_local_archive(archive, manifest_file)
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    services = _string_set(manifest.get("root_services"))
    faults = _string_set(manifest.get("fault_families"))
    expected_case_count = _positive_int(manifest.get("expected_case_count"), "expected_case_count")
    if not services or faults != ALLOWED_FAULTS:
        raise P112RE1Error("invalid_manifest_taxonomy")
    system = str(manifest.get("system", "")).strip()
    if not system:
        raise P112RE1Error("missing_manifest_system")
    source_hash = f"sha256:{source['sha256']}"

    with zipfile.ZipFile(archive) as zf:
        groups = _index_archive(
            zf,
            services=services,
            max_files=max_files,
            max_uncompressed_bytes=max_uncompressed_bytes,
        )
        if len(groups) != expected_case_count:
            raise P112RE1Error(f"case_count_mismatch:{len(groups)}")
        cases = [
            _read_case(
                zf,
                case_path,
                members,
                system=system,
                source_hash=source_hash,
                services=services,
                hmac_key=hmac_key,
            )
            for case_path, members in sorted(groups.items())
        ]
    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise P112RE1Error("duplicate_case_id")
    return tuple(cases)


def reject_candidate_truth_leak(packets: Sequence[Mapping[str, Any]]) -> None:
    rendered = json.dumps(list(packets), sort_keys=True, ensure_ascii=True, default=str).lower()
    forbidden = (
        "root_service",
        "fault_type",
        "scorer_only",
        "source_path",
        "repetition",
        "data.csv",
        "inject_time",
        "_cpu/",
        "_mem/",
        "_disk/",
        "_delay/",
        "_loss/",
    )
    if any(token in rendered for token in forbidden):
        raise P112RE1Error("candidate_visible_truth_leak")


def _index_archive(
    zf: zipfile.ZipFile,
    *,
    services: frozenset[str],
    max_files: int,
    max_uncompressed_bytes: int,
) -> dict[str, dict[str, zipfile.ZipInfo]]:
    groups: dict[str, dict[str, zipfile.ZipInfo]] = {}
    seen_paths: set[str] = set()
    total_size = 0
    file_count = 0
    for info in zf.infolist():
        if info.is_dir():
            continue
        name = _normalize_name(info.filename)
        if name in seen_paths:
            raise P112RE1Error("archive_duplicate_path")
        seen_paths.add(name)
        mode = (info.external_attr >> 16) & 0o170000
        if mode == stat.S_IFLNK:
            raise P112RE1Error("archive_symlink")
        file_count += 1
        total_size += info.file_size
        if file_count > max_files:
            raise P112RE1Error("archive_file_count_exceeded")
        if total_size > max_uncompressed_bytes:
            raise P112RE1Error("archive_uncompressed_size_exceeded")
        parts = name.split("/")
        if len(parts) != 4:
            raise P112RE1Error("invalid_archive_layout")
        _root, group, repetition_text, file_name = parts
        service, fault = _parse_group(group, services=services)
        repetition = _repetition(repetition_text)
        if file_name == "simple_data.csv":
            continue
        logical_name = "inject_time" if file_name in {"inject_time", "inject_time.txt"} else file_name
        if logical_name not in {"data.csv", "inject_time"}:
            raise P112RE1Error("unexpected_case_file")
        case_path = f"{service}_{fault}/{repetition}"
        members = groups.setdefault(case_path, {})
        if logical_name in members:
            raise P112RE1Error("duplicate_case_file")
        members[logical_name] = info
    for case_path, members in groups.items():
        if set(members) != {"data.csv", "inject_time"}:
            raise P112RE1Error(f"missing_case_file:{case_path}")
    return groups


def _read_case(
    zf: zipfile.ZipFile,
    case_path: str,
    members: Mapping[str, zipfile.ZipInfo],
    *,
    system: str,
    source_hash: str,
    services: frozenset[str],
    hmac_key: bytes,
) -> P112RE1Case:
    group, repetition_text = case_path.split("/", 1)
    service, fault = _parse_group(group, services=services)
    repetition = _repetition(repetition_text)
    data = zf.read(members["data.csv"])
    inject = zf.read(members["inject_time"])
    raw_hashes = {
        "data.csv": hashlib.sha256(data).hexdigest(),
        "inject_time": hashlib.sha256(inject).hexdigest(),
    }
    inject_time = inject.decode("utf-8").strip()
    if not inject_time:
        raise P112RE1Error("missing_inject_time")
    rows = _finite_metric_rows(_read_metric_rows(data, source_hash=raw_hashes["data.csv"], inject_time=inject_time))
    features = _extract_features(rows, inject_time=inject_time, source_hash=raw_hashes["data.csv"])
    diagnostic_features = _extract_robust_diagnostics(rows, source_hash=raw_hashes["data.csv"])
    if not features:
        raise P112RE1Error("missing_metric_features")
    case = P112RE1Case(
        case_id=_case_id(f"{system}:{case_path}", hmac_key=hmac_key),
        system=system,
        source_path=case_path,
        inject_time=inject_time,
        official_source_hash=source_hash,
        raw_hashes=raw_hashes,
        scorer_only_truth={"root_service": service, "fault_type": fault, "repetition": repetition},
        features=features,
        diagnostic_features=diagnostic_features,
    )
    reject_candidate_truth_leak((case.to_candidate_packet(),))
    return case


def _finite_metric_rows(rows: Sequence[Mapping[str, Any]]) -> tuple[Mapping[str, Any], ...]:
    """Exclude unusable non-finite observations before feature extraction and hashing."""

    finite: list[Mapping[str, Any]] = []
    for row in rows:
        try:
            values = (float(row["timestamp_value"]), float(row["inject_value"]), float(row["value"]))
        except (KeyError, TypeError, ValueError):
            continue
        if all(math.isfinite(value) for value in values):
            finite.append(row)
    return tuple(finite)


def _normalize_name(name: str) -> str:
    raw = name.replace("\\", "/")
    if raw.startswith("/") or raw.startswith("../") or "/../" in raw:
        raise P112RE1Error("archive_traversal")
    normalized = posixpath.normpath(raw)
    if normalized.startswith("../") or normalized in {".", ".."} or posixpath.isabs(normalized):
        raise P112RE1Error("archive_traversal")
    return normalized


def _parse_group(group: str, *, services: frozenset[str]) -> tuple[str, str]:
    service, separator, fault = group.rpartition("_")
    if not separator or service not in services or fault not in ALLOWED_FAULTS:
        raise P112RE1Error("invalid_case_identity")
    return service, fault


def _repetition(value: str) -> int:
    if not value.isdigit() or int(value) not in ALLOWED_REPETITIONS:
        raise P112RE1Error("invalid_repetition")
    return int(value)


def _case_id(value: str, *, hmac_key: bytes) -> str:
    digest = hmac.new(hmac_key, f"{_CASE_ID_DOMAIN}:{value}".encode(), hashlib.sha256).hexdigest()
    return f"p112_{digest[:24]}"


def _string_set(value: Any) -> frozenset[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return frozenset()
    return frozenset(str(item) for item in value if str(item))


def _positive_int(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise P112RE1Error(f"invalid_{name}")
    return value


def _extract_robust_diagnostics(rows: Sequence[Mapping[str, Any]], *, source_hash: str) -> tuple[Mapping[str, Any], ...]:
    grouped: dict[tuple[str, str], dict[str, list[tuple[float, float]]]] = {}
    for row in rows:
        service = str(row["service"])
        metric = str(row["metric"])
        window = "pre" if float(row["timestamp_value"]) < float(row["inject_value"]) else "post"
        grouped.setdefault((service, metric), {"pre": [], "post": []})[window].append((float(row["timestamp_value"]), float(row["value"])))
    features: list[Mapping[str, Any]] = []
    for (service, metric), windows in sorted(grouped.items()):
        pre = _diagnostic_series(metric, windows["pre"])
        post = _diagnostic_series(metric, windows["post"])
        if not pre or not post:
            continue
        pre_center = statistics.median(pre)
        post_center = statistics.median(post)
        deviations = [abs(value - pre_center) for value in pre]
        mad = statistics.median(deviations) if deviations else 0.0
        scale = max(1.4826 * mad, abs(pre_center) * 0.01, 1e-9)
        signed_score = max(-100.0, min(100.0, (post_center - pre_center) / scale))
        evidence_id = "ev_" + hashlib.sha256(f"p112.robust-shift.v1|{source_hash}|{service}|{metric}".encode()).hexdigest()[:24]
        features.append(
            {
                "evidence_id": evidence_id,
                "service": service,
                "metric": metric,
                "statistic": "robust_post_shift" if not _counter_metric(metric) else "robust_rate_shift",
                "signed_score": round(signed_score, 12),
                "absolute_score": round(abs(signed_score), 12),
                "pre_center": round(pre_center, 12),
                "post_center": round(post_center, 12),
                "sample_count": len(pre) + len(post),
                "source_binding": {"raw_sha256": source_hash, "raw_path_token": "metric_source"},
            }
        )
    return tuple(features)


def _diagnostic_series(metric: str, points: Sequence[tuple[float, float]]) -> list[float]:
    ordered = sorted(points)
    if not _counter_metric(metric):
        return [value for _timestamp, value in ordered]
    rates: list[float] = []
    for (left_time, left_value), (right_time, right_value) in zip(ordered, ordered[1:], strict=False):
        elapsed = right_time - left_time
        delta = right_value - left_value
        if elapsed > 0 and delta >= 0:
            rates.append(delta / elapsed)
    return rates


def _counter_metric(metric: str) -> bool:
    lower = metric.lower().replace("_", "-")
    return lower.endswith("-total") or any(
        token in lower
        for token in (
            "seconds-total",
            "bytes-total",
            "packets-total",
            "reads-total",
            "writes-total",
            "completed-total",
            "drop-total",
            "errs-total",
            "failures-total",
        )
    )
