from __future__ import annotations

import hashlib
import io
import json
import tarfile
from pathlib import Path
from typing import Any

import pytest

from app.services.p109_safe_acquisition import P109AcquisitionError, acquire_p109_source


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _tar_bytes(entries: list[tuple[str, bytes, str]]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, data, kind in entries:
            info = tarfile.TarInfo(name)
            if kind == "file":
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
            elif kind == "symlink":
                info.type = tarfile.SYMTYPE
                info.linkname = data.decode("utf-8")
                archive.addfile(info)
            else:
                raise AssertionError(kind)
    return buffer.getvalue()


def _manifest_for(archive_bytes: bytes, **artifact_overrides: Any) -> dict[str, Any]:
    artifact = {
        "schema_version": "p109.source_artifact.v1",
        "source_id": "rcaeval-immutable",
        "canonical_url": "https://example.org/rcaeval/archive/1111111111111111111111111111111111111111.tar.gz",
        "revision": "1111111111111111111111111111111111111111",
        "revision_type": "commit",
        "license": {"name": "fixture-only", "citation": "RCAEval fixture citation"},
        "expected_paths": ["cases/case-001/metrics.jsonl"],
        "dataset_schema": "p109.rcaeval_case.v1",
        "max_compressed_bytes": 4096,
        "max_decompressed_bytes": 8192,
        "max_file_count": 8,
        "redirect_allowlist": [{"host": "example.org", "path_prefix": "/rcaeval/archive/"}],
        "sha256": _sha256(archive_bytes),
        "provenance_hashes": {
            "schema_version": "p109.provenance_hashes.v1",
            "canonical_manifest_sha256": "0" * 64,
            "downloaded_bytes_sha256": _sha256(archive_bytes),
            "extracted_tree_sha256": "1" * 64,
            "normalized_corpus_sha256": "2" * 64,
        },
    }
    artifact.update(artifact_overrides)
    return {
        "schema_version": "p109.source_manifest.v1",
        "manifest_id": "p109-source-fixture",
        "generated_at": "2026-07-11T00:00:00Z",
        "allowed_signers": [{"signer_id": "fixture-reviewer", "key_id": "fixture-key"}],
        "artifacts": [artifact],
    }


def _write_manifest(path: Path, payload: dict[str, Any]) -> Path:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def test_p109_acquisition_default_network_zero(tmp_path: Path) -> None:
    archive = _tar_bytes([("cases/case-001/metrics.jsonl", b"{}\n", "file")])
    manifest_path = _write_manifest(tmp_path / "manifest.json", _manifest_for(archive))
    calls: list[str] = []

    result = acquire_p109_source(manifest_path, "rcaeval-immutable", tmp_path / "out", fetcher=lambda url: calls.append(url))

    assert calls == []
    assert result["status"] == "network_opt_in_required"
    assert result["network_calls"] == 0
    assert result["downloaded_bytes"] == 0


def test_p109_acquisition_requires_known_source_id(tmp_path: Path) -> None:
    archive = _tar_bytes([("cases/case-001/metrics.jsonl", b"{}\n", "file")])
    manifest_path = _write_manifest(tmp_path / "manifest.json", _manifest_for(archive))

    with pytest.raises(P109AcquisitionError, match="unknown_source"):
        acquire_p109_source(manifest_path, "missing-source", tmp_path / "out", allow_network=True, fetcher=lambda _url: archive)


def test_p109_acquisition_uses_injected_fetcher_and_extracts_safe_archive(tmp_path: Path) -> None:
    archive = _tar_bytes([("cases/case-001/metrics.jsonl", b'{"service":"api"}\n', "file")])
    manifest_path = _write_manifest(tmp_path / "manifest.json", _manifest_for(archive))

    result = acquire_p109_source(manifest_path, "rcaeval-immutable", tmp_path / "out", allow_network=True, fetcher=lambda _url: archive)

    extracted = tmp_path / "out" / "rcaeval-immutable" / "cases" / "case-001" / "metrics.jsonl"
    assert result["status"] == "acquired"
    assert result["network_calls"] == 1
    assert result["downloaded_sha256"] == _sha256(archive)
    assert extracted.read_text(encoding="utf-8") == '{"service":"api"}\n'


@pytest.mark.parametrize(
    ("entries", "manifest_overrides", "fetch_result", "match"),
    [
        ([("../escape.txt", b"bad", "file")], {}, None, "archive_traversal"),
        ([("cases/link", b"/etc/passwd", "symlink")], {}, None, "archive_symlink"),
        (
            [("cases/case-001/metrics.jsonl", b"0123456789", "file")],
            {"max_decompressed_bytes": 4},
            None,
            "archive_size_bomb",
        ),
        (
            [("cases/../metrics.jsonl", b"one", "file"), ("metrics.jsonl", b"two", "file")],
            {},
            None,
            "normalized_duplicate_path",
        ),
        (
            [("cases/case-001/metrics.jsonl", b"{}", "file")],
            {"sha256": "0" * 64},
            None,
            "checksum_mismatch",
        ),
    ],
)
def test_p109_acquisition_rejects_unsafe_archives(
    tmp_path: Path,
    entries: list[tuple[str, bytes, str]],
    manifest_overrides: dict[str, Any],
    fetch_result: Any,
    match: str,
) -> None:
    archive = _tar_bytes(entries)
    manifest_path = _write_manifest(tmp_path / "manifest.json", _manifest_for(archive, **manifest_overrides))
    fetched = archive if fetch_result is None else fetch_result

    with pytest.raises(P109AcquisitionError, match=match):
        acquire_p109_source(manifest_path, "rcaeval-immutable", tmp_path / "out", allow_network=True, fetcher=lambda _url: fetched)


def test_p109_acquisition_rejects_redirect_escape(tmp_path: Path) -> None:
    archive = _tar_bytes([("cases/case-001/metrics.jsonl", b"{}\n", "file")])
    manifest_path = _write_manifest(tmp_path / "manifest.json", _manifest_for(archive))

    with pytest.raises(P109AcquisitionError, match="redirect_escape"):
        acquire_p109_source(
            manifest_path,
            "rcaeval-immutable",
            tmp_path / "out",
            allow_network=True,
            fetcher=lambda _url: {"body": archive, "final_url": "https://evil.example/rcaeval/archive/file.tar.gz"},
        )


def test_p109_acquisition_rejects_archive_file_count_bomb(tmp_path: Path) -> None:
    archive = _tar_bytes([(f"cases/{index}.jsonl", b"{}\n", "file") for index in range(4)])
    manifest_path = _write_manifest(tmp_path / "manifest.json", _manifest_for(archive, max_file_count=2))

    with pytest.raises(P109AcquisitionError, match="archive_file_count_bomb"):
        acquire_p109_source(manifest_path, "rcaeval-immutable", tmp_path / "out", allow_network=True, fetcher=lambda _url: archive)
