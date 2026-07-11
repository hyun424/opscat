"""Pinned, fail-closed acquisition checks for P114 RCAEval RE2 archives."""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import stat
import tempfile
import urllib.request
import zipfile
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO
from urllib.parse import urlparse


@dataclass(frozen=True)
class P114SourcePin:
    source_id: str
    file_name: str
    compressed_bytes: int
    upstream_md5: str
    verified_sha256: str | None
    expected_case_count: int
    canonical_download_url: str


P114_SOURCE_PINS: dict[str, P114SourcePin] = {
    "rcaeval-re2-ss": P114SourcePin(
        source_id="rcaeval-re2-ss",
        file_name="RE2-SS.zip",
        compressed_bytes=245_629_018,
        upstream_md5="bd747a8fc7c5be00c613e13fbf9dd74b",
        verified_sha256="7aff9a3a0df7e2febbce4f75f0b7ba332da943aacadbffe6d5113a588ef6e295",
        expected_case_count=90,
        canonical_download_url="https://zenodo.org/api/records/14590730/files/RE2-SS.zip/content",
    ),
    "rcaeval-re2-ob": P114SourcePin(
        source_id="rcaeval-re2-ob",
        file_name="RE2-OB.zip",
        compressed_bytes=1_191_025_569,
        upstream_md5="b9e23f8842c404b396ffd2becff15de4",
        verified_sha256="0605a36cdcad8a6ae0107f2357c9c91ecee2c4ab5d72579bffea0372d9747513",
        expected_case_count=90,
        canonical_download_url="https://zenodo.org/api/records/14590730/files/RE2-OB.zip/content",
    ),
}

_CANONICAL_RECORD = "https://zenodo.org/records/14590730"
_MAX_FILES = 100_000
_MAX_UNCOMPRESSED_BYTES = 20 * 1024 * 1024 * 1024


class P114AcquisitionError(ValueError):
    """Raised when an RE2 source archive violates the P114 acquisition contract."""


def read_source_manifest(path: str | Path) -> Mapping[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise P114AcquisitionError("source manifest must be an object")
    return value


def validate_re2_archive(path: str | Path, manifest_path: str | Path) -> dict[str, Any]:
    """Validate pinned RE2 bytes and inspect zip metadata without extracting."""

    archive = Path(path)
    manifest = read_source_manifest(manifest_path)
    pin = _validate_manifest(manifest)
    if archive.name != pin.file_name:
        raise P114AcquisitionError("archive file_name does not match manifest")
    try:
        actual_size = archive.stat().st_size
    except FileNotFoundError as exc:
        raise P114AcquisitionError(f"archive missing: {archive}") from exc
    if actual_size != pin.compressed_bytes:
        raise P114AcquisitionError(f"archive size mismatch: expected {pin.compressed_bytes}, got {actual_size}")
    md5, sha256 = _hash_file(archive)
    if md5 != pin.upstream_md5:
        raise P114AcquisitionError("archive MD5 mismatch")
    if pin.verified_sha256 is not None and sha256 != pin.verified_sha256:
        raise P114AcquisitionError("archive SHA-256 mismatch")
    case_count = _validate_zip_metadata(archive, expected_root=pin.file_name.removesuffix(".zip"))
    if case_count != pin.expected_case_count:
        raise P114AcquisitionError(f"case_count_mismatch:{case_count}")
    return {
        "verified": True,
        "source_id": pin.source_id,
        "path": str(archive),
        "bytes": actual_size,
        "md5": md5,
        "sha256": sha256,
        "case_count": case_count,
    }


def acquire_pinned_archive(
    manifest_path: str | Path,
    destination_dir: str | Path,
    *,
    allow_network: bool = False,
    opener: Callable[..., BinaryIO] = urllib.request.urlopen,
) -> dict[str, Any]:
    """Download one pinned RE2 source only when explicitly allowed."""

    if not allow_network:
        raise P114AcquisitionError("network acquisition requires allow_network=True")
    manifest = read_source_manifest(manifest_path)
    pin = _validate_manifest(manifest)
    _validate_zenodo_url(pin.canonical_download_url)
    destination = Path(destination_dir) / pin.file_name
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(pin.canonical_download_url, headers={"User-Agent": "OpsCat-P114/1"})
    fd, temp_name = tempfile.mkstemp(prefix=".p114-", suffix=".part", dir=destination.parent)
    os.close(fd)
    temp = Path(temp_name)
    try:
        with opener(request, timeout=60) as response, temp.open("wb") as output:
            final_url = str(getattr(response, "url", pin.canonical_download_url))
            _validate_zenodo_url(final_url)
            total = 0
            for chunk in _chunks(response):
                total += len(chunk)
                if total > pin.compressed_bytes:
                    raise P114AcquisitionError("download exceeded pinned byte size")
                output.write(chunk)
        if total != pin.compressed_bytes:
            raise P114AcquisitionError("download ended before pinned byte size")
        temp.replace(destination)
        return validate_re2_archive(destination, manifest_path)
    finally:
        temp.unlink(missing_ok=True)


def _validate_manifest(manifest: Mapping[str, Any]) -> P114SourcePin:
    source_id = str(manifest.get("source_id", ""))
    pin = P114_SOURCE_PINS.get(source_id)
    if pin is None:
        raise P114AcquisitionError("manifest source_id is not a pinned P114 source")
    if manifest.get("schema_version") != "p114.source_manifest.v1":
        raise P114AcquisitionError("manifest schema_version must be p114.source_manifest.v1")
    if manifest.get("canonical_record") != _CANONICAL_RECORD:
        raise P114AcquisitionError("manifest canonical_record does not match Zenodo record 14590730")
    if manifest.get("canonical_download_url") != pin.canonical_download_url:
        raise P114AcquisitionError("manifest canonical_download_url does not match P114 pin")
    if manifest.get("file_name") != pin.file_name:
        raise P114AcquisitionError("manifest file_name does not match P114 pin")
    if manifest.get("compressed_bytes") != pin.compressed_bytes:
        raise P114AcquisitionError("manifest compressed_bytes does not match P114 pin")
    if manifest.get("upstream_md5") != pin.upstream_md5:
        raise P114AcquisitionError("manifest MD5 does not match P114 pin")
    if manifest.get("verified_sha256") != pin.verified_sha256:
        raise P114AcquisitionError("manifest SHA-256 does not match P114 pin")
    if manifest.get("expected_case_count") != pin.expected_case_count:
        raise P114AcquisitionError("manifest expected_case_count does not match P114 pin")
    return pin


def _validate_zip_metadata(archive: Path, *, expected_root: str) -> int:
    try:
        with zipfile.ZipFile(archive) as zf:
            entries = [info for info in zf.infolist() if not info.is_dir()]
    except zipfile.BadZipFile as exc:
        raise P114AcquisitionError("invalid_zip_archive") from exc

    seen_paths: set[str] = set()
    total_uncompressed = 0
    for info in entries:
        name = _normalize_name(info.filename)
        if name in seen_paths:
            raise P114AcquisitionError("archive_duplicate_path")
        seen_paths.add(name)
        mode = (info.external_attr >> 16) & 0o170000
        if mode == stat.S_IFLNK:
            raise P114AcquisitionError("archive_symlink")
        total_uncompressed += info.file_size
        if len(seen_paths) > _MAX_FILES:
            raise P114AcquisitionError("archive_file_count_exceeded")
        if total_uncompressed > _MAX_UNCOMPRESSED_BYTES:
            raise P114AcquisitionError("archive_uncompressed_size_exceeded")

    cases: set[str] = set()
    for name in seen_paths:
        parts = name.split("/")
        root = parts[0]
        if root != expected_root:
            raise P114AcquisitionError("invalid_archive_root")
        # The pinned RE2-OB release contains upstream metadata and a
        # non-benchmark multi-source-data bundle. Only numeric repetition
        # directories are official benchmark cases; the loader applies the
        # strict per-case file contract after this archive-level inventory.
        if len(parts) < 4 or not parts[2].isdigit():
            continue
        group, repetition = parts[1], parts[2]
        if not group:
            raise P114AcquisitionError("invalid_case_identity")
        cases.add(f"{group}/{repetition}")
    return len(cases)


def _normalize_name(name: str) -> str:
    raw = name.replace("\\", "/")
    if raw.startswith("/") or raw.startswith("../") or "/../" in raw:
        raise P114AcquisitionError("archive_traversal")
    normalized = posixpath.normpath(raw)
    if normalized.startswith("../") or normalized in {".", ".."} or posixpath.isabs(normalized):
        raise P114AcquisitionError("archive_traversal")
    return normalized


def _validate_zenodo_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "zenodo.org":
        raise P114AcquisitionError("canonical download URL must be pinned HTTPS zenodo.org")


def _hash_file(path: Path) -> tuple[str, str]:
    md5 = hashlib.md5(usedforsecurity=False)
    sha256 = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in _chunks(stream):
            md5.update(chunk)
            sha256.update(chunk)
    return md5.hexdigest(), sha256.hexdigest()


def _chunks(stream: BinaryIO, size: int = 1024 * 1024) -> Iterator[bytes]:
    while True:
        chunk = stream.read(size)
        if not chunk:
            return
        yield chunk
