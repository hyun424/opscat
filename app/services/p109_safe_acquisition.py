"""P109 bounded source acquisition.

Network access is intentionally not implemented here. Callers that need the
CLI opt-in lane must inject a fetcher, making tests and default verification
offline by construction.
"""

from __future__ import annotations

import hashlib
import io
import posixpath
import stat
import tarfile
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.services.p109_source_manifest import P109SourceArtifact, P109SourceManifest, P109SourceManifestError, load_p109_source_manifest


class P109AcquisitionError(ValueError):
    """Raised when P109 acquisition fails closed."""


@dataclass(frozen=True)
class P109FetchResult:
    url: str
    final_url: str
    content: bytes


@dataclass(frozen=True)
class P109AcquisitionPlanItem:
    source_id: str
    canonical_url: str
    destination: str
    status: str

    def to_dict(self) -> dict[str, str]:
        return {
            "source_id": self.source_id,
            "canonical_url": self.canonical_url,
            "destination": self.destination,
            "status": self.status,
        }


@dataclass(frozen=True)
class P109AcquisitionPlan:
    artifacts: tuple[P109AcquisitionPlanItem, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": {
                "source_count": len(self.artifacts),
                "network_call_count": 0,
                "download_count": 0,
            },
            "artifacts": [item.to_dict() for item in self.artifacts],
            "authority": {
                "network_default": False,
                "fetcher_required_for_download": True,
                "shell_enabled": False,
                "subprocess_enabled": False,
            },
        }


@dataclass(frozen=True)
class P109AcquisitionResult:
    source_id: str
    destination: str
    downloaded_sha256: str
    extracted_tree_sha256: str
    extracted_files: tuple[str, ...]
    status: str = "acquired"

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "destination": self.destination,
            "downloaded_sha256": self.downloaded_sha256,
            "extracted_tree_sha256": self.extracted_tree_sha256,
            "extracted_files": list(self.extracted_files),
            "status": self.status,
        }


Fetcher = Callable[[str], Any]


def plan_p109_source_acquisition(
    manifest: P109SourceManifest,
    *,
    destination_root: str | Path,
    fetcher: Fetcher | None = None,
) -> P109AcquisitionPlan:
    del fetcher
    root = Path(destination_root)
    return P109AcquisitionPlan(
        artifacts=tuple(
            P109AcquisitionPlanItem(
                source_id=artifact.source_id,
                canonical_url=artifact.canonical_url,
                destination=str(root / artifact.source_id),
                status="network_opt_in_required",
            )
            for artifact in manifest.artifacts
        )
    )


def acquire_p109_source_artifact(
    manifest: P109SourceManifest,
    source_id: str,
    *,
    destination_root: str | Path,
    fetcher: Fetcher | None = None,
) -> P109AcquisitionResult:
    if fetcher is None:
        raise P109AcquisitionError("fetcher_required: P109 acquisition requires an explicitly injected fetcher")
    try:
        artifact = manifest.get_artifact(source_id)
    except P109SourceManifestError as exc:
        raise P109AcquisitionError(str(exc)) from exc
    fetched = _coerce_fetch_result(fetcher(artifact.canonical_url), artifact.canonical_url)
    _validate_redirect(artifact, fetched.final_url)
    content = fetched.content
    if len(content) > artifact.max_compressed_bytes:
        raise P109AcquisitionError("archive_size_bomb: compressed byte ceiling exceeded")
    downloaded_sha256 = hashlib.sha256(content).hexdigest()
    if downloaded_sha256 != artifact.sha256:
        raise P109AcquisitionError("checksum_mismatch: downloaded bytes do not match source manifest")
    destination = Path(destination_root) / artifact.source_id
    files = _safe_extract_archive(content, destination, artifact)
    extracted_tree_sha256 = _tree_sha256(destination, files)
    return P109AcquisitionResult(
        source_id=artifact.source_id,
        destination=str(destination),
        downloaded_sha256=downloaded_sha256,
        extracted_tree_sha256=extracted_tree_sha256,
        extracted_files=tuple(files),
    )


def acquire_p109_source(
    manifest_path: str | Path,
    source_id: str,
    destination_root: str | Path,
    *,
    allow_network: bool = False,
    fetcher: Fetcher | None = None,
) -> dict[str, Any]:
    manifest = load_p109_source_manifest(manifest_path)
    try:
        artifact = manifest.get_artifact(source_id)
    except P109SourceManifestError as exc:
        raise P109AcquisitionError(str(exc)) from exc
    if not allow_network:
        return {
            "source_id": source_id,
            "destination": str(Path(destination_root) / source_id),
            "status": "network_opt_in_required",
            "network_calls": 0,
            "downloaded_bytes": 0,
        }
    if fetcher is None:
        raise P109AcquisitionError("fetcher_required: P109 acquisition requires an explicitly injected fetcher")

    network_calls = 0
    downloaded_bytes = 0

    def counted_fetcher(url: str) -> P109FetchResult:
        nonlocal network_calls, downloaded_bytes
        network_calls += 1
        result = _coerce_fetch_result(fetcher(url), artifact.canonical_url)
        downloaded_bytes = len(result.content)
        return result

    result = acquire_p109_source_artifact(manifest, source_id, destination_root=destination_root, fetcher=counted_fetcher)
    payload = result.to_dict()
    payload["network_calls"] = network_calls
    payload["downloaded_bytes"] = downloaded_bytes
    return payload


def _coerce_fetch_result(value: Any, canonical_url: str) -> P109FetchResult:
    if isinstance(value, P109FetchResult):
        return value
    if isinstance(value, bytes):
        return P109FetchResult(url=canonical_url, final_url=canonical_url, content=value)
    if isinstance(value, dict):
        body = value.get("body", value.get("content"))
        final_url = str(value.get("final_url") or canonical_url)
        if isinstance(body, bytes):
            return P109FetchResult(url=canonical_url, final_url=final_url, content=body)
    raise P109AcquisitionError("fetcher_result_invalid: expected bytes, P109FetchResult, or mapping body")


def _validate_redirect(artifact: P109SourceArtifact, final_url: str) -> None:
    parsed = urlparse(final_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise P109AcquisitionError("redirect_escape: final URL must remain HTTPS")
    host = parsed.hostname.lower() if parsed.hostname else ""
    path = parsed.path or "/"
    if not any(rule.host == host and path.startswith(rule.path_prefix) for rule in artifact.redirect_allowlist):
        raise P109AcquisitionError("redirect_escape: final URL escaped host/path allowlist")


def _safe_extract_archive(content: bytes, destination: Path, artifact: P109SourceArtifact) -> list[str]:
    entries = _read_archive_entries(content)
    if len(entries) > artifact.max_file_count:
        raise P109AcquisitionError("archive_file_count_bomb: file-count ceiling exceeded")
    total_size = sum(size for _, _, size in entries)
    if total_size > artifact.max_decompressed_bytes:
        raise P109AcquisitionError("archive_size_bomb: decompressed byte ceiling exceeded")
    normalized_paths: set[str] = set()
    for raw_name, _, _ in entries:
        normalized = _normalized_member_path(raw_name)
        if normalized in normalized_paths:
            raise P109AcquisitionError("normalized_duplicate_path: archive member normalizes to duplicate path")
        normalized_paths.add(normalized)
    missing = sorted(set(artifact.expected_paths) - normalized_paths)
    if missing:
        raise P109AcquisitionError(f"expected_paths_missing: {', '.join(missing)}")

    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    written: list[str] = []
    for raw_name, data, _ in entries:
        normalized = _normalized_member_path(raw_name)
        target = destination / normalized
        target_parent = target.parent
        target_parent.mkdir(parents=True, exist_ok=True)
        resolved_target = target.resolve(strict=False)
        if root != resolved_target and root not in resolved_target.parents:
            raise P109AcquisitionError("archive_traversal: member escapes destination")
        target.write_bytes(data)
        written.append(normalized)
    return sorted(written)


def _read_archive_entries(content: bytes) -> list[tuple[str, bytes, int]]:
    buffer = io.BytesIO(content)
    if zipfile.is_zipfile(buffer):
        buffer.seek(0)
        return _read_zip_entries(buffer)
    buffer.seek(0)
    try:
        return _read_tar_entries(buffer)
    except tarfile.TarError as exc:
        raise P109AcquisitionError(f"unsupported_archive: {exc}") from exc


def _read_zip_entries(buffer: io.BytesIO) -> list[tuple[str, bytes, int]]:
    entries: list[tuple[str, bytes, int]] = []
    with zipfile.ZipFile(buffer) as archive:
        for info in archive.infolist():
            mode = (info.external_attr >> 16) & 0o170000
            if mode == stat.S_IFLNK:
                raise P109AcquisitionError("archive_symlink: symlink members are rejected")
            if info.is_dir():
                continue
            normalized = _normalized_member_path(info.filename)
            with archive.open(info) as member:
                data = member.read()
            entries.append((normalized, data, info.file_size))
    return entries


def _read_tar_entries(buffer: io.BytesIO) -> list[tuple[str, bytes, int]]:
    entries: list[tuple[str, bytes, int]] = []
    with tarfile.open(fileobj=buffer, mode="r:*") as archive:
        for member in archive.getmembers():
            if member.issym() or member.islnk():
                raise P109AcquisitionError("archive_symlink: link members are rejected")
            if member.isdir():
                continue
            if not member.isfile():
                raise P109AcquisitionError("archive_symlink: only regular file members are accepted")
            normalized = _normalized_member_path(member.name)
            fileobj = archive.extractfile(member)
            if fileobj is None:
                raise P109AcquisitionError("unsupported_archive: unreadable tar member")
            entries.append((normalized, fileobj.read(), int(member.size)))
    return entries


def _normalized_member_path(name: str) -> str:
    candidate = name.replace("\\", "/")
    normalized = posixpath.normpath(candidate)
    parts = [part for part in normalized.split("/") if part not in ("", ".")]
    if candidate.startswith("/") or normalized.startswith("../") or normalized == ".." or ".." in parts:
        raise P109AcquisitionError("archive_traversal: member path escapes archive root")
    if not parts:
        raise P109AcquisitionError("archive_traversal: empty member path")
    return "/".join(parts)


def _tree_sha256(destination: Path, files: list[str]) -> str:
    digest = hashlib.sha256()
    for relative in sorted(files):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update((destination / relative).read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()
