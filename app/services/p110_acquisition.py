"""Pinned, bounded acquisition helpers for the P110 RCAEval archive."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import urllib.request
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any, BinaryIO
from urllib.parse import urlparse


class AcquisitionError(ValueError):
    """Raised when source bytes do not match the pinned P110 manifest."""


def read_source_manifest(path: str | Path) -> Mapping[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise AcquisitionError("source manifest must be an object")
    return value


def validate_local_archive(path: str | Path, manifest_path: str | Path) -> dict[str, Any]:
    archive = Path(path)
    manifest = read_source_manifest(manifest_path)
    if archive.name != str(manifest.get("file_name", "")):
        raise AcquisitionError("archive file_name does not match manifest")
    expected_size = _positive_int(manifest, "compressed_bytes")
    actual_size = archive.stat().st_size
    if actual_size != expected_size:
        raise AcquisitionError(f"archive size mismatch: expected {expected_size}, got {actual_size}")
    md5, sha256 = _hash_file(archive)
    if md5 != str(manifest.get("upstream_md5", "")):
        raise AcquisitionError("archive MD5 mismatch")
    if sha256 != str(manifest.get("verified_sha256", "")):
        raise AcquisitionError("archive SHA-256 mismatch")
    return {"verified": True, "path": str(archive), "bytes": actual_size, "md5": md5, "sha256": sha256}


def acquire_pinned_archive(
    manifest_path: str | Path,
    destination_dir: str | Path,
    *,
    allow_network: bool = False,
    opener: Callable[..., BinaryIO] = urllib.request.urlopen,
) -> dict[str, Any]:
    """Download the one pinned source; network is disabled unless explicit."""

    if not allow_network:
        raise AcquisitionError("network acquisition requires allow_network=True")
    manifest = read_source_manifest(manifest_path)
    url = str(manifest.get("canonical_download_url", ""))
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "zenodo.org":
        raise AcquisitionError("canonical download URL must be pinned HTTPS zenodo.org")
    expected_size = _positive_int(manifest, "compressed_bytes")
    destination = Path(destination_dir) / str(manifest.get("file_name", ""))
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "OpsCat-P110/1"})
    fd, temp_name = tempfile.mkstemp(prefix=".p110-", suffix=".part", dir=destination.parent)
    os.close(fd)
    temp = Path(temp_name)
    try:
        with opener(request, timeout=60) as response, temp.open("wb") as output:
            final_url = str(getattr(response, "url", url))
            final = urlparse(final_url)
            if final.scheme != "https" or final.hostname != "zenodo.org":
                raise AcquisitionError("download redirect escaped pinned zenodo.org host")
            total = 0
            for chunk in _chunks(response):
                total += len(chunk)
                if total > expected_size:
                    raise AcquisitionError("download exceeded pinned byte size")
                output.write(chunk)
        if total != expected_size:
            raise AcquisitionError("download ended before pinned byte size")
        temp.replace(destination)
        return validate_local_archive(destination, manifest_path)
    finally:
        temp.unlink(missing_ok=True)


def _chunks(stream: BinaryIO, size: int = 1024 * 1024) -> Iterator[bytes]:
    while True:
        chunk = stream.read(size)
        if not chunk:
            return
        yield chunk


def _hash_file(path: Path) -> tuple[str, str]:
    md5 = hashlib.md5(usedforsecurity=False)
    sha256 = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in _chunks(stream):
            md5.update(chunk)
            sha256.update(chunk)
    return md5.hexdigest(), sha256.hexdigest()


def _positive_int(manifest: Mapping[str, Any], key: str) -> int:
    value = manifest.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise AcquisitionError(f"manifest {key} must be a positive integer")
    return value
