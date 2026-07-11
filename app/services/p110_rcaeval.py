"""P110 RCAEval RE1-OB local importer and candidate packet builder."""

from __future__ import annotations

import csv
import hashlib
import hmac
import io
import posixpath
import stat
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "p110.rcaeval_case.v1"
CANDIDATE_PACKET_SCHEMA_VERSION = "p110.rcaeval_candidate_packet.v1"

OFFICIAL_RE1_OB_RECORD_URL = "https://zenodo.org/records/14590730"
OFFICIAL_RE1_OB_FILE_NAME = "RE1-OB.zip"
OFFICIAL_RE1_OB_SIZE_BYTES = 30966778
OFFICIAL_RE1_OB_MD5 = "47cce26ed24140e8974e68f9db2a5e9c"
OFFICIAL_RE1_OB_SHA256 = "4a709297e0a829f0f2ee8a7792a6d74da32d663c600565b7fffc860963b840c4"
OFFICIAL_RE1_OB_LICENSE = "CC-BY-4.0"

DEFAULT_EXPECTED_CASE_COUNT = 125
DEFAULT_MAX_ARCHIVE_FILES = 512
DEFAULT_MAX_ARCHIVE_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
CASE_ID_DOMAIN = "p110.rcaeval.case-id.v1"
EVIDENCE_ID_DOMAIN = "p110.rcaeval.evidence-id.v1"

ALLOWED_FAULTS = frozenset({"cpu", "mem", "disk", "delay", "loss"})
ALLOWED_REPETITIONS = frozenset({"1", "2", "3", "4", "5"})
ALLOWED_ONLINE_BOUTIQUE_SERVICES = frozenset(
    {
        "adservice",
        "cartservice",
        "checkoutservice",
        "currencyservice",
        "emailservice",
        "frontend",
        "frontend-external",
        "paymentservice",
        "productcatalogservice",
        "recommendationservice",
        "redis-cart",
        "shippingservice",
    }
)
REQUIRED_CASE_FILES = ("data.csv", "inject_time")
CASE_FILE_ALIASES = {"data.csv": "data.csv", "inject_time": "inject_time", "inject_time.txt": "inject_time"}


class P110RCAEvalError(ValueError):
    """Raised when local RCAEval RE1-OB input violates the P110 contract."""


@dataclass(frozen=True)
class P110EvidenceFeature:
    evidence_id: str
    service: str
    metric: str
    window: str
    statistic: str
    value: float
    sample_count: int
    source_hash: str

    def to_candidate_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "service": self.service,
            "metric": self.metric,
            "window": self.window,
            "statistic": self.statistic,
            "value": self.value,
            "sample_count": self.sample_count,
            "source_binding": {"raw_sha256": self.source_hash, "raw_path_token": "metric_source"},
        }


@dataclass(frozen=True)
class P110RCAEvalCase:
    case_id: str
    source_path: str
    inject_time: str
    raw_hashes: Mapping[str, str]
    scorer_only_truth: Mapping[str, Any]
    features: tuple[P110EvidenceFeature, ...]
    schema_version: str = SCHEMA_VERSION

    @property
    def service_catalog(self) -> tuple[str, ...]:
        return tuple(sorted({feature.service for feature in self.features}))

    @property
    def metric_catalog(self) -> tuple[str, ...]:
        return tuple(sorted({feature.metric for feature in self.features}))

    def to_candidate_packet(self) -> dict[str, Any]:
        return {
            "schema_version": CANDIDATE_PACKET_SCHEMA_VERSION,
            "case_id": self.case_id,
            "system": "online_boutique",
            "injection_timestamp": self.inject_time,
            "service_catalog": list(self.service_catalog),
            "metric_catalog": list(self.metric_catalog),
            "evidence": [feature.to_candidate_dict() for feature in self.features],
        }

    def to_scorer_truth(self) -> dict[str, Any]:
        return {
            "schema_version": "p110.rcaeval_scorer_truth.v1",
            "case_id": self.case_id,
            "scorer_only_truth": dict(self.scorer_only_truth),
            "official_source_hash": f"sha256:{OFFICIAL_RE1_OB_SHA256}",
            "evidence_ids": [feature.evidence_id for feature in self.features],
            "source_path": self.source_path,
            "raw_hashes": dict(sorted(self.raw_hashes.items())),
        }


def validate_official_archive(path: str | Path) -> Mapping[str, Any]:
    archive = Path(path)
    if archive.name != OFFICIAL_RE1_OB_FILE_NAME:
        raise P110RCAEvalError("archive_name_mismatch")
    data = archive.read_bytes()
    size = len(data)
    md5 = hashlib.md5(data, usedforsecurity=False).hexdigest()
    sha256 = hashlib.sha256(data).hexdigest()
    if size != OFFICIAL_RE1_OB_SIZE_BYTES:
        raise P110RCAEvalError("archive_size_mismatch")
    if md5 != OFFICIAL_RE1_OB_MD5:
        raise P110RCAEvalError("archive_md5_mismatch")
    if sha256 != OFFICIAL_RE1_OB_SHA256:
        raise P110RCAEvalError("archive_sha256_mismatch")
    return {
        "file_name": archive.name,
        "size_bytes": size,
        "md5": md5,
        "sha256": sha256,
        "record_url": OFFICIAL_RE1_OB_RECORD_URL,
        "license": OFFICIAL_RE1_OB_LICENSE,
    }


def load_re1_ob_cases(
    source: str | Path,
    *,
    hmac_key: bytes,
    expected_case_count: int = DEFAULT_EXPECTED_CASE_COUNT,
    strict_archive: bool = True,
    max_archive_files: int = DEFAULT_MAX_ARCHIVE_FILES,
    max_archive_uncompressed_bytes: int = DEFAULT_MAX_ARCHIVE_UNCOMPRESSED_BYTES,
) -> tuple[P110RCAEvalCase, ...]:
    if not hmac_key:
        raise P110RCAEvalError("hmac_key_required")
    path = Path(source)
    if path.is_file():
        if strict_archive:
            validate_official_archive(path)
        files = _read_zip_files(path, max_files=max_archive_files, max_uncompressed_bytes=max_archive_uncompressed_bytes)
    elif path.is_dir():
        files = _read_extracted_files(path, max_files=max_archive_files, max_uncompressed_bytes=max_archive_uncompressed_bytes)
    else:
        raise FileNotFoundError(f"RCAEval RE1-OB source does not exist: {path}")

    grouped = _group_case_files(files)
    if len(grouped) != expected_case_count:
        raise P110RCAEvalError(f"case_count_mismatch:{len(grouped)}")

    cases = [_case_from_group(case_path, members, hmac_key=hmac_key) for case_path, members in sorted(grouped.items())]
    _reject_duplicate_case_ids(cases)
    return tuple(cases)


def build_candidate_packets(cases: Sequence[P110RCAEvalCase]) -> tuple[Mapping[str, Any], ...]:
    packets = tuple(case.to_candidate_packet() for case in sorted(cases, key=lambda item: item.case_id))
    _reject_candidate_truth_leak(packets)
    return packets


def build_scorer_truth(cases: Sequence[P110RCAEvalCase]) -> tuple[Mapping[str, Any], ...]:
    return tuple(case.to_scorer_truth() for case in sorted(cases, key=lambda item: item.case_id))


def _read_zip_files(path: Path, *, max_files: int, max_uncompressed_bytes: int) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    total_size = 0
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            normalized = _normalize_archive_name(info.filename)
            mode = (info.external_attr >> 16) & 0o170000
            if mode == stat.S_IFLNK:
                raise P110RCAEvalError("archive_symlink")
            if normalized in files:
                raise P110RCAEvalError("archive_duplicate_path")
            if len(files) + 1 > max_files:
                raise P110RCAEvalError("archive_file_count_exceeded")
            total_size += info.file_size
            if total_size > max_uncompressed_bytes:
                raise P110RCAEvalError("archive_uncompressed_size_exceeded")
            files[normalized] = zf.read(info)
    return files


def _read_extracted_files(root: Path, *, max_files: int, max_uncompressed_bytes: int) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    total_size = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise P110RCAEvalError("extracted_symlink")
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        normalized = _normalize_archive_name(rel)
        if normalized in files:
            raise P110RCAEvalError("archive_duplicate_path")
        if len(files) + 1 > max_files:
            raise P110RCAEvalError("archive_file_count_exceeded")
        data = path.read_bytes()
        total_size += len(data)
        if total_size > max_uncompressed_bytes:
            raise P110RCAEvalError("archive_uncompressed_size_exceeded")
        files[normalized] = data
    return files


def _normalize_archive_name(name: str) -> str:
    raw = name.replace("\\", "/")
    if raw.startswith("/") or raw.startswith("../") or "/../" in raw or raw in {"", ".", ".."}:
        raise P110RCAEvalError("archive_traversal")
    normalized = posixpath.normpath(raw)
    if normalized.startswith("../") or normalized in {".", ".."} or posixpath.isabs(normalized):
        raise P110RCAEvalError("archive_traversal")
    return normalized


def _group_case_files(files: Mapping[str, bytes]) -> dict[str, dict[str, bytes]]:
    groups: dict[str, dict[str, bytes]] = {}
    for path, content in files.items():
        case_path, file_name = _split_case_file(path)
        if file_name in groups.setdefault(case_path, {}):
            raise P110RCAEvalError("duplicate_case_identity")
        groups.setdefault(case_path, {})[file_name] = content
    for case_path, members in groups.items():
        missing = [name for name in REQUIRED_CASE_FILES if name not in members]
        if missing:
            raise P110RCAEvalError(f"missing_case_file:{case_path}:{','.join(missing)}")
    return groups


def _split_case_file(path: str) -> tuple[str, str]:
    parts = path.split("/")
    if len(parts) < 3:
        raise P110RCAEvalError("invalid_case_path")
    group, repetition, file_name = parts[-3], parts[-2], parts[-1]
    if "/" in file_name or file_name not in CASE_FILE_ALIASES:
        raise P110RCAEvalError("unexpected_case_file")
    service, fault = _parse_group(group)
    if repetition not in ALLOWED_REPETITIONS:
        raise P110RCAEvalError("invalid_repetition")
    return f"{service}_{fault}/{repetition}", CASE_FILE_ALIASES[file_name]


def _parse_group(group: str) -> tuple[str, str]:
    service, separator, fault = group.rpartition("_")
    if not separator or not service or not fault:
        raise P110RCAEvalError("invalid_case_identity")
    if service not in ALLOWED_ONLINE_BOUTIQUE_SERVICES:
        raise P110RCAEvalError("unknown_service")
    if fault not in ALLOWED_FAULTS:
        raise P110RCAEvalError("unknown_fault")
    return service, fault


def _case_from_group(case_path: str, members: Mapping[str, bytes], *, hmac_key: bytes) -> P110RCAEvalCase:
    group, repetition_text = case_path.split("/", 1)
    service, fault = _parse_group(group)
    raw_hashes = {name: hashlib.sha256(members[name]).hexdigest() for name in REQUIRED_CASE_FILES}
    inject_time = members["inject_time"].decode("utf-8").strip()
    if not inject_time:
        raise P110RCAEvalError("missing_inject_time")
    rows = _read_metric_rows(members["data.csv"], source_hash=raw_hashes["data.csv"], inject_time=inject_time)
    features = _extract_features(rows, inject_time=inject_time, source_hash=raw_hashes["data.csv"])
    if not features:
        raise P110RCAEvalError("missing_metric_features")
    case = P110RCAEvalCase(
        case_id=_pseudonymous_case_id(case_path, hmac_key=hmac_key),
        source_path=case_path,
        inject_time=inject_time,
        raw_hashes=raw_hashes,
        scorer_only_truth={"root_service": service, "fault_type": fault, "repetition": int(repetition_text)},
        features=features,
    )
    _reject_candidate_truth_leak((case.to_candidate_packet(),))
    return case


def _read_metric_rows(content: bytes, *, source_hash: str, inject_time: str) -> tuple[Mapping[str, Any], ...]:
    text = content.decode("utf-8-sig")
    with io.StringIO(text) as handle:
        reader = csv.DictReader(handle)
        fieldnames = tuple(reader.fieldnames or ())
        if not fieldnames:
            raise P110RCAEvalError("missing_metric_header")
        time_column = "time" if "time" in fieldnames else "timestamp" if "timestamp" in fieldnames else ""
        if not time_column:
            raise P110RCAEvalError("missing_time_column")
        _reject_truth_leak_columns(fieldnames)
        rows: list[Mapping[str, Any]] = []
        for line_number, row in enumerate(reader, start=2):
            timestamp = str(row.get(time_column, "")).strip()
            if not timestamp:
                continue
            for column in fieldnames:
                if column == time_column:
                    continue
                raw_value = row.get(column)
                if raw_value in (None, ""):
                    continue
                service, metric = _split_metric_column(column)
                rows.append(
                    {
                        "timestamp": timestamp,
                        "timestamp_value": _numeric_time(timestamp, field="data.csv time"),
                        "inject_value": _numeric_time(inject_time, field="inject_time"),
                        "service": service,
                        "metric": metric,
                        "value": _float_value(raw_value),
                        "raw_line": line_number,
                        "raw_column": column,
                        "source_hash": source_hash,
                    }
                )
    return tuple(rows)


def _reject_truth_leak_columns(fieldnames: Sequence[str]) -> None:
    leak_tokens = ("root_service", "root_cause", "fault_type", "truth", "label", "answer", "scorer")
    for field in fieldnames:
        lower = field.lower()
        if any(token in lower for token in leak_tokens):
            raise P110RCAEvalError("candidate_visible_truth_leak")


def _split_metric_column(column: str) -> tuple[str, str]:
    service, separator, metric = column.rpartition("_")
    if not separator or not service or not metric:
        raise P110RCAEvalError("invalid_metric_column")
    return service, metric


def _extract_features(rows: Sequence[Mapping[str, Any]], *, inject_time: str, source_hash: str) -> tuple[P110EvidenceFeature, ...]:
    grouped: dict[tuple[str, str], dict[str, list[float]]] = {}
    for row in rows:
        key = (str(row["service"]), str(row["metric"]))
        window = "pre" if float(row["timestamp_value"]) < float(row["inject_value"]) else "post"
        grouped.setdefault(key, {"pre": [], "post": []})[window].append(float(row["value"]))

    features: list[P110EvidenceFeature] = []
    for service_metric, windows in sorted(grouped.items()):
        service, metric = service_metric
        means: dict[str, float] = {}
        counts: dict[str, int] = {}
        for window in ("pre", "post"):
            values = windows[window]
            if not values:
                continue
            means[window] = round(sum(values) / len(values), 6)
            counts[window] = len(values)
            features.append(
                _feature(
                    service=service,
                    metric=metric,
                    window=window,
                    statistic="mean",
                    value=means[window],
                    sample_count=counts[window],
                    source_hash=source_hash,
                )
            )
        if "pre" in means and "post" in means:
            features.append(
                _feature(
                    service=service,
                    metric=metric,
                    window="delta",
                    statistic="post_minus_pre_mean",
                    value=round(means["post"] - means["pre"], 6),
                    sample_count=counts["pre"] + counts["post"],
                    source_hash=source_hash,
                )
            )
    return tuple(sorted(features, key=lambda item: item.evidence_id))


def _feature(*, service: str, metric: str, window: str, statistic: str, value: float, sample_count: int, source_hash: str) -> P110EvidenceFeature:
    evidence_id = _stable_evidence_id(
        {
            "service": service,
            "metric": metric,
            "window": window,
            "statistic": statistic,
            "source_hash": source_hash,
        }
    )
    return P110EvidenceFeature(
        evidence_id=evidence_id,
        service=service,
        metric=metric,
        window=window,
        statistic=statistic,
        value=value,
        sample_count=sample_count,
        source_hash=source_hash,
    )


def _pseudonymous_case_id(source_path: str, *, hmac_key: bytes) -> str:
    digest = hmac.new(hmac_key, f"{CASE_ID_DOMAIN}:{source_path}".encode(), hashlib.sha256).hexdigest()
    return f"p110_{digest[:24]}"


def _stable_evidence_id(parts: Mapping[str, Any]) -> str:
    payload = "|".join(f"{key}={parts[key]}" for key in sorted(parts))
    digest = hashlib.sha256(f"{EVIDENCE_ID_DOMAIN}:{payload}".encode()).hexdigest()
    return f"ev_{digest[:24]}"


def _reject_duplicate_case_ids(cases: Sequence[P110RCAEvalCase]) -> None:
    seen: set[str] = set()
    for case in cases:
        if case.case_id in seen:
            raise P110RCAEvalError("duplicate_case_id")
        seen.add(case.case_id)


def _reject_candidate_truth_leak(packets: Sequence[Mapping[str, Any]]) -> None:
    rendered = repr(packets).lower()
    forbidden = ("root_service", "fault_type", "scorer", "truth", "repetition", "data.csv", "_cpu/", "_mem/", "_disk/", "_delay/", "_loss/")
    if any(token in rendered for token in forbidden):
        raise P110RCAEvalError("candidate_visible_truth_leak")


def _numeric_time(value: str, *, field: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise P110RCAEvalError(f"invalid_numeric_time:{field}") from exc


def _float_value(value: Any) -> float:
    try:
        return float(str(value))
    except ValueError as exc:
        raise P110RCAEvalError("invalid_metric_value") from exc
