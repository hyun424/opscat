from __future__ import annotations

import hashlib
import json
import stat
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

import app.services.p114_acquisition as p114_acquisition
from app.services.p114_acquisition import P114_SOURCE_PINS, P114AcquisitionError, validate_re2_archive


def _pin_fixture(monkeypatch: pytest.MonkeyPatch, source_id: str, payload: bytes, *, case_count: int = 1) -> None:
    pins = dict(P114_SOURCE_PINS)
    pins[source_id] = replace(
        pins[source_id],
        compressed_bytes=len(payload),
        upstream_md5=hashlib.md5(payload, usedforsecurity=False).hexdigest(),
        verified_sha256=hashlib.sha256(payload).hexdigest(),
        expected_case_count=case_count,
    )
    monkeypatch.setattr(p114_acquisition, "P114_SOURCE_PINS", pins)


def _manifest(path: Path, payload: bytes, *, source_id: str = "rcaeval-re2-ss") -> Path:
    pin = P114_SOURCE_PINS[source_id]
    target = path / f"source-manifest-{source_id}.json"
    target.write_text(
        json.dumps(
            {
                "schema_version": "p114.source_manifest.v1",
                "source_id": source_id,
                "canonical_record": "https://zenodo.org/records/14590730",
                "canonical_download_url": pin.canonical_download_url,
                "file_name": pin.file_name,
                "compressed_bytes": len(payload),
                "expected_case_count": 1,
                "upstream_md5": hashlib.md5(payload, usedforsecurity=False).hexdigest(),
                "verified_sha256": hashlib.sha256(payload).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    return target


def _archive(path: Path, *, file_name: str = "RE2-SS.zip", member_name: str | None = None) -> Path:
    archive = path / file_name
    root = file_name.removesuffix(".zip")
    name = member_name or f"{root}/checkout_cpu/1/data.csv"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(name, "time,value\n1,1\n")
    return archive


def _symlink_archive(path: Path) -> Path:
    archive = path / "RE2-SS.zip"
    info = zipfile.ZipInfo("RE2-SS/checkout_cpu/1/data.csv")
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(info, "target")
    return archive


def test_manifests_pin_official_zenodo_re2_resources() -> None:
    ss = json.loads(Path("evals/real_datasets/external/p114/source-manifest-re2-ss.json").read_text(encoding="utf-8"))
    ob = json.loads(Path("evals/real_datasets/external/p114/source-manifest-re2-ob.json").read_text(encoding="utf-8"))

    assert ss["canonical_record"] == ob["canonical_record"] == "https://zenodo.org/records/14590730"
    assert ss["file_name"] == "RE2-SS.zip"
    assert ss["canonical_download_url"] == "https://zenodo.org/api/records/14590730/files/RE2-SS.zip/content"
    assert ss["compressed_bytes"] == 245_629_018
    assert ss["upstream_md5"] == "bd747a8fc7c5be00c613e13fbf9dd74b"
    assert ss["expected_case_count"] == 90
    assert ss["verified_sha256"] == "7aff9a3a0df7e2febbce4f75f0b7ba332da943aacadbffe6d5113a588ef6e295"
    assert ob["file_name"] == "RE2-OB.zip"
    assert ob["canonical_download_url"] == "https://zenodo.org/api/records/14590730/files/RE2-OB.zip/content"
    assert ob["compressed_bytes"] == 1_191_025_569
    assert ob["upstream_md5"] == "b9e23f8842c404b396ffd2becff15de4"
    assert ob["expected_case_count"] == 90
    assert ob["verified_sha256"] == "0605a36cdcad8a6ae0107f2357c9c91ecee2c4ab5d72579bffea0372d9747513"


def test_validate_re2_archive_ignores_pinned_upstream_non_case_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = tmp_path / "RE2-SS.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("RE2-SS/.DS_Store", "metadata")
        zf.writestr("RE2-SS/checkout_cpu/multi-source-data.zip", "upstream-bundle")
        zf.writestr("RE2-SS/checkout_cpu/1/data.csv", "time,value\n1,1\n")
    payload = archive.read_bytes()
    _pin_fixture(monkeypatch, "rcaeval-re2-ss", payload)

    result = validate_re2_archive(archive, _manifest(tmp_path, payload))

    assert result["case_count"] == 1


def test_validate_re2_archive_binds_size_md5_computes_sha256_and_counts_cases(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = _archive(tmp_path)
    payload = archive.read_bytes()
    _pin_fixture(monkeypatch, "rcaeval-re2-ss", payload)

    result = validate_re2_archive(archive, _manifest(tmp_path, payload))

    assert result["verified"] is True
    assert result["bytes"] == len(payload)
    assert result["case_count"] == 1
    assert result["md5"] == hashlib.md5(payload, usedforsecurity=False).hexdigest()
    assert result["sha256"] == hashlib.sha256(payload).hexdigest()


@pytest.mark.parametrize("mutation", [b"x", b"official-archive-bytez"])
def test_validate_re2_archive_rejects_tamper_or_wrong_size(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: bytes) -> None:
    archive = tmp_path / "RE2-SS.zip"
    archive.write_bytes(mutation)
    _pin_fixture(monkeypatch, "rcaeval-re2-ss", b"official-archive-bytes")

    with pytest.raises(P114AcquisitionError):
        validate_re2_archive(archive, _manifest(tmp_path, b"official-archive-bytes"))


def test_validate_re2_archive_rejects_wrong_file_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = _archive(tmp_path)
    payload = archive.read_bytes()
    _pin_fixture(monkeypatch, "rcaeval-re2-ss", payload)

    with pytest.raises(P114AcquisitionError, match="file_name"):
        validate_re2_archive(tmp_path / "renamed.zip", _manifest(tmp_path, payload))


def test_validate_re2_archive_rejects_zip_traversal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = _archive(tmp_path, member_name="../escape/checkout_cpu/1/data.csv")
    payload = archive.read_bytes()
    _pin_fixture(monkeypatch, "rcaeval-re2-ss", payload)

    with pytest.raises(P114AcquisitionError, match="archive_traversal"):
        validate_re2_archive(archive, _manifest(tmp_path, payload))


def test_validate_re2_archive_rejects_symlink_entries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = _symlink_archive(tmp_path)
    payload = archive.read_bytes()
    _pin_fixture(monkeypatch, "rcaeval-re2-ss", payload)

    with pytest.raises(P114AcquisitionError, match="archive_symlink"):
        validate_re2_archive(archive, _manifest(tmp_path, payload))


def test_validate_re2_archive_rejects_duplicate_entries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = tmp_path / "RE2-SS.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("RE2-SS/checkout_cpu/1/data.csv", "first")
        zf.writestr("RE2-SS/checkout_cpu/1/data.csv", "second")
    payload = archive.read_bytes()
    _pin_fixture(monkeypatch, "rcaeval-re2-ss", payload)

    with pytest.raises(P114AcquisitionError, match="archive_duplicate_path"):
        validate_re2_archive(archive, _manifest(tmp_path, payload))


def test_validate_re2_archive_rejects_decompression_budget_before_layout_parse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = _archive(tmp_path, member_name="bad-layout.csv")
    payload = archive.read_bytes()
    _pin_fixture(monkeypatch, "rcaeval-re2-ss", payload)
    monkeypatch.setattr(p114_acquisition, "_MAX_UNCOMPRESSED_BYTES", 1)

    with pytest.raises(P114AcquisitionError, match="archive_uncompressed_size_exceeded"):
        validate_re2_archive(archive, _manifest(tmp_path, payload))
