"""Pinned, fail-closed acquisition checks for the P113 RCAEval RE1-TT archive."""

from __future__ import annotations

import hashlib
import json
import posixpath
import stat
import zipfile
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

P113_EXPECTED_SIZE = 279_663_965
P113_EXPECTED_MD5 = "48a26925ce47fd4bcfbedbae4f31475b"
P113_EXPECTED_SHA256 = "2b33b7ab07198e0d69f229e697bfcef794a656e8db73a1d732142effde17c595"

_EXPECTED_FILE_NAME = "RE1-TT.zip"
_EXPECTED_CASE_COUNT = 125
_EXPECTED_FAULTS = frozenset({"cpu", "delay", "disk", "loss", "mem"})
_EXPECTED_SERVICES = frozenset(
    {
        "ts-auth-service",
        "ts-order-service",
        "ts-route-service",
        "ts-train-service",
        "ts-travel-service",
    }
)
_MAX_FILES = 512
_MAX_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024


class P113AcquisitionError(ValueError):
    """Raised when the RE1-TT source archive violates the P113 acquisition contract."""


def read_source_manifest(path: str | Path) -> Mapping[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise P113AcquisitionError("source manifest must be an object")
    return value


def validate_re1_tt_archive(path: str | Path, manifest_path: str | Path) -> dict[str, Any]:
    """Validate pinned RE1-TT bytes and inspect the zip layout without extracting."""

    archive = Path(path)
    manifest = read_source_manifest(manifest_path)
    _validate_manifest(manifest)
    if archive.name != str(manifest.get("file_name", "")):
        raise P113AcquisitionError("archive file_name does not match manifest")
    expected_size = _positive_int(manifest, "compressed_bytes")
    try:
        actual_size = archive.stat().st_size
    except FileNotFoundError as exc:
        raise P113AcquisitionError(f"archive missing: {archive}") from exc
    if actual_size != expected_size:
        raise P113AcquisitionError(f"archive size mismatch: expected {expected_size}, got {actual_size}")
    md5, sha256 = _hash_file(archive)
    if md5 != str(manifest.get("upstream_md5", "")):
        raise P113AcquisitionError("archive MD5 mismatch")
    if sha256 != str(manifest.get("verified_sha256", "")):
        raise P113AcquisitionError("archive SHA-256 mismatch")
    case_count = _validate_zip_layout(archive, manifest)
    return {
        "verified": True,
        "path": str(archive),
        "bytes": actual_size,
        "md5": md5,
        "sha256": sha256,
        "case_count": case_count,
    }


def _validate_manifest(manifest: Mapping[str, Any]) -> None:
    if manifest.get("file_name") != _EXPECTED_FILE_NAME:
        raise P113AcquisitionError("manifest file_name must be RE1-TT.zip")
    if manifest.get("compressed_bytes") != P113_EXPECTED_SIZE:
        raise P113AcquisitionError("manifest compressed_bytes does not match P113 pin")
    if manifest.get("upstream_md5") != P113_EXPECTED_MD5:
        raise P113AcquisitionError("manifest MD5 does not match P113 pin")
    if manifest.get("verified_sha256") != P113_EXPECTED_SHA256:
        raise P113AcquisitionError("manifest SHA-256 does not match P113 pin")
    if manifest.get("expected_case_count") != _EXPECTED_CASE_COUNT:
        raise P113AcquisitionError("manifest expected_case_count does not match P113 pin")
    if _string_set(manifest.get("fault_families")) != _EXPECTED_FAULTS:
        raise P113AcquisitionError("manifest fault_families do not match P113 pin")
    if _string_set(manifest.get("root_services")) != _EXPECTED_SERVICES:
        raise P113AcquisitionError("manifest root_services do not match P113 pin")


def _validate_zip_layout(archive: Path, manifest: Mapping[str, Any]) -> int:
    services = _string_set(manifest.get("root_services"))
    expected_case_count = _positive_int(manifest, "expected_case_count")
    cases: dict[str, set[str]] = {}
    seen_paths: set[str] = set()
    total_size = 0
    file_count = 0
    try:
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                name = _normalize_name(info.filename)
                if name in seen_paths:
                    raise P113AcquisitionError("archive_duplicate_path")
                seen_paths.add(name)
                mode = (info.external_attr >> 16) & 0o170000
                if mode == stat.S_IFLNK:
                    raise P113AcquisitionError("archive_symlink")
                file_count += 1
                total_size += info.file_size
                if file_count > _MAX_FILES:
                    raise P113AcquisitionError("archive_file_count_exceeded")
                if total_size > _MAX_UNCOMPRESSED_BYTES:
                    raise P113AcquisitionError("archive_uncompressed_size_exceeded")
                parts = name.split("/")
                if len(parts) != 4:
                    raise P113AcquisitionError("invalid_archive_layout")
                root, group, repetition, file_name = parts
                if root != "RE1-TT":
                    raise P113AcquisitionError("invalid_archive_root")
                _validate_case_identity(group, repetition, services=services)
                if file_name not in {"data.csv", "inject_time.txt", "simple_data.csv"}:
                    raise P113AcquisitionError("unexpected_case_file")
                if file_name == "simple_data.csv":
                    continue
                case_key = f"{group}/{repetition}"
                members = cases.setdefault(case_key, set())
                if file_name in members:
                    raise P113AcquisitionError("duplicate_case_file")
                members.add(file_name)
    except zipfile.BadZipFile as exc:
        raise P113AcquisitionError("invalid_zip_archive") from exc
    for case_key, members in cases.items():
        if members != {"data.csv", "inject_time.txt"}:
            raise P113AcquisitionError(f"missing_case_file:{case_key}")
    if len(cases) != expected_case_count:
        raise P113AcquisitionError(f"case_count_mismatch:{len(cases)}")
    return len(cases)


def _normalize_name(name: str) -> str:
    raw = name.replace("\\", "/")
    if raw.startswith("/") or raw.startswith("../") or "/../" in raw:
        raise P113AcquisitionError("archive_traversal")
    normalized = posixpath.normpath(raw)
    if normalized.startswith("../") or normalized in {".", ".."} or posixpath.isabs(normalized):
        raise P113AcquisitionError("archive_traversal")
    return normalized


def _validate_case_identity(group: str, repetition: str, *, services: frozenset[str]) -> None:
    service, separator, fault = group.rpartition("_")
    if not separator or service not in services or fault not in _EXPECTED_FAULTS:
        raise P113AcquisitionError("invalid_case_identity")
    if not repetition.isdigit() or int(repetition) not in {1, 2, 3, 4, 5}:
        raise P113AcquisitionError("invalid_repetition")


def _hash_file(path: Path) -> tuple[str, str]:
    md5 = hashlib.md5(usedforsecurity=False)
    sha256 = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in _chunks(stream):
            md5.update(chunk)
            sha256.update(chunk)
    return md5.hexdigest(), sha256.hexdigest()


def _chunks(stream: Any, size: int = 1024 * 1024) -> Iterator[bytes]:
    while True:
        chunk = stream.read(size)
        if not chunk:
            return
        yield chunk


def _positive_int(manifest: Mapping[str, Any], key: str) -> int:
    value = manifest.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise P113AcquisitionError(f"manifest {key} must be a positive integer")
    return value


def _string_set(value: Any) -> frozenset[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return frozenset()
    return frozenset(str(item) for item in value if str(item))
