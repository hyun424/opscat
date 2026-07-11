from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

import app.services.p113_acquisition as p113_acquisition
from app.services.p113_acquisition import (
    P113_EXPECTED_MD5,
    P113_EXPECTED_SHA256,
    P113_EXPECTED_SIZE,
    P113AcquisitionError,
    validate_re1_tt_archive,
)


def _pin_fixture(monkeypatch: pytest.MonkeyPatch, payload: bytes, *, case_count: int = 1) -> None:
    monkeypatch.setattr(p113_acquisition, "P113_EXPECTED_SIZE", len(payload))
    monkeypatch.setattr(
        p113_acquisition,
        "P113_EXPECTED_MD5",
        hashlib.md5(payload, usedforsecurity=False).hexdigest(),
    )
    monkeypatch.setattr(p113_acquisition, "P113_EXPECTED_SHA256", hashlib.sha256(payload).hexdigest())
    monkeypatch.setattr(p113_acquisition, "_EXPECTED_CASE_COUNT", case_count)
    monkeypatch.setattr(p113_acquisition, "_EXPECTED_SERVICES", frozenset({"ts-auth-service"}))


def _manifest(path: Path, payload: bytes, *, file_name: str = "RE1-TT.zip") -> Path:
    target = path / "source-manifest-re1-tt.json"
    target.write_text(
        json.dumps(
            {
                "schema_version": "p113.source_manifest.v1",
                "source_id": "rcaeval-re1-tt",
                "dataset": "RCAEval RE1-TT",
                "system": "train_ticket",
                "file_name": file_name,
                "compressed_bytes": len(payload),
                "expected_case_count": 1,
                "upstream_md5": hashlib.md5(payload, usedforsecurity=False).hexdigest(),
                "verified_sha256": hashlib.sha256(payload).hexdigest(),
                "fault_families": ["cpu", "delay", "disk", "loss", "mem"],
                "root_services": ["ts-auth-service"],
            }
        ),
        encoding="utf-8",
    )
    return target


def _archive(path: Path, *, traversal: bool = False) -> Path:
    archive = path / "RE1-TT.zip"
    prefix = "../escape" if traversal else "RE1-TT"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(f"{prefix}/ts-auth-service_cpu/1/inject_time.txt", "2\n")
        zf.writestr(f"{prefix}/ts-auth-service_cpu/1/data.csv", "time,ts-auth-service_cpu\n1,1\n2,2\n")
        zf.writestr(f"{prefix}/ts-auth-service_cpu/1/simple_data.csv", "ignored\n")
    return archive


def test_manifest_pins_official_re1_tt_bytes() -> None:
    manifest = json.loads(
        Path("evals/real_datasets/external/p113/source-manifest-re1-tt.json").read_text(encoding="utf-8")
    )

    assert manifest["file_name"] == "RE1-TT.zip"
    assert manifest["compressed_bytes"] == P113_EXPECTED_SIZE == 279_663_965
    assert manifest["upstream_md5"] == P113_EXPECTED_MD5 == "48a26925ce47fd4bcfbedbae4f31475b"
    assert manifest["verified_sha256"] == P113_EXPECTED_SHA256 == (
        "2b33b7ab07198e0d69f229e697bfcef794a656e8db73a1d732142effde17c595"
    )


def test_validate_re1_tt_archive_binds_size_hashes_and_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = _archive(tmp_path)
    payload = archive.read_bytes()
    _pin_fixture(monkeypatch, payload)

    result = validate_re1_tt_archive(archive, _manifest(tmp_path, payload))

    assert result["verified"] is True
    assert result["bytes"] == len(payload)
    assert result["case_count"] == 1
    assert result["md5"] == hashlib.md5(payload, usedforsecurity=False).hexdigest()
    assert result["sha256"] == hashlib.sha256(payload).hexdigest()


@pytest.mark.parametrize("mutation", [b"x", b"official-archive-bytez"])
def test_validate_re1_tt_archive_rejects_tamper_or_wrong_size(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: bytes
) -> None:
    archive = tmp_path / "RE1-TT.zip"
    archive.write_bytes(mutation)
    _pin_fixture(monkeypatch, b"official-archive-bytes")

    with pytest.raises(P113AcquisitionError):
        validate_re1_tt_archive(archive, _manifest(tmp_path, b"official-archive-bytes"))


def test_validate_re1_tt_archive_rejects_wrong_file_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = _archive(tmp_path)
    payload = archive.read_bytes()
    _pin_fixture(monkeypatch, payload)

    with pytest.raises(P113AcquisitionError, match="file_name"):
        validate_re1_tt_archive(tmp_path / "renamed.zip", _manifest(tmp_path, payload))


def test_validate_re1_tt_archive_rejects_zip_traversal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = _archive(tmp_path, traversal=True)
    payload = archive.read_bytes()
    _pin_fixture(monkeypatch, payload)

    with pytest.raises(P113AcquisitionError, match="archive_traversal"):
        validate_re1_tt_archive(archive, _manifest(tmp_path, payload))
