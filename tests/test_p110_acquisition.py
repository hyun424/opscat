from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.services.p110_acquisition import AcquisitionError, validate_local_archive


def _manifest(path: Path, payload: bytes) -> Path:
    target = path / "manifest.json"
    target.write_text(
        json.dumps(
            {
                "file_name": "RE1-OB.zip",
                "compressed_bytes": len(payload),
                "upstream_md5": hashlib.md5(payload, usedforsecurity=False).hexdigest(),
                "verified_sha256": hashlib.sha256(payload).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    return target


def test_validate_local_archive_binds_size_and_both_hashes(tmp_path: Path) -> None:
    payload = b"official-archive-bytes"
    archive = tmp_path / "RE1-OB.zip"
    archive.write_bytes(payload)

    result = validate_local_archive(archive, _manifest(tmp_path, payload))

    assert result["verified"] is True
    assert result["bytes"] == len(payload)
    assert result["sha256"] == hashlib.sha256(payload).hexdigest()


@pytest.mark.parametrize("mutation", [b"x", b"official-archive-bytez"])
def test_validate_local_archive_rejects_tamper_or_wrong_size(tmp_path: Path, mutation: bytes) -> None:
    expected = b"official-archive-bytes"
    archive = tmp_path / "RE1-OB.zip"
    archive.write_bytes(mutation)

    with pytest.raises(AcquisitionError):
        validate_local_archive(archive, _manifest(tmp_path, expected))


def test_validate_local_archive_rejects_wrong_file_name(tmp_path: Path) -> None:
    payload = b"official-archive-bytes"
    archive = tmp_path / "renamed.zip"
    archive.write_bytes(payload)

    with pytest.raises(AcquisitionError, match="file_name"):
        validate_local_archive(archive, _manifest(tmp_path, payload))
