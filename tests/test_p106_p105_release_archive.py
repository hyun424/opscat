from __future__ import annotations

import gzip
import hashlib
import importlib
import io
import json
import subprocess
import sys
import tarfile
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from tests.fixtures.p106_p105_release_archive import (
    P105_REAL_DERIVED_ARCHIVE,
    P105_REAL_DERIVED_ARCHIVE_MEMBERS,
    P105_REAL_DERIVED_ARTIFACT,
    safe_extract_p105_release_archive,
)

EXPECTED_ARCHIVE_SHA256 = "6aaf35285f03cc7fe68b036a8172dba1615d1e5131939b2d8ef26787dd5c7342"
EXPECTED_ARCHIVE_SIZE_BYTES = 2_012_888
EXTRACTOR_CLI = Path("scripts/extract_p105_release_fixture.py")


def _forecast_api() -> Any:
    return importlib.import_module("app.services.failure_forecast_engine")


def _prerequisite_api() -> Any:
    return importlib.import_module("app.services.p105_release_prerequisite")


def _archive_path() -> Path:
    return P105_REAL_DERIVED_ARCHIVE


def _archive_sha256() -> str:
    return hashlib.sha256(_archive_path().read_bytes()).hexdigest()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_extractor(archive: Path, sha256: str, output_dir: Path) -> subprocess.CompletedProcess[str]:
    if not EXTRACTOR_CLI.exists():
        pytest.skip(f"P106 RED blocked by missing public extractor utility: {EXTRACTOR_CLI}")
    return subprocess.run(
        [sys.executable, str(EXTRACTOR_CLI), str(archive), sha256, str(output_dir)],
        check=False,
        capture_output=True,
        text=True,
    )


def _json_payload(name: str) -> bytes:
    return json.dumps({"fixture_member": name}, sort_keys=True).encode("utf-8")


def _write_archive(path: Path, members: dict[str, bytes], *, member_type: str | None = None) -> None:
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w") as tar:
        for name, payload in members.items():
            info = tarfile.TarInfo(name)
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mode = 0o644
            if member_type == "symlink":
                info.type = tarfile.SYMTYPE
                info.linkname = P105_REAL_DERIVED_ARTIFACT
                tar.addfile(info)
            elif member_type == "hardlink":
                info.type = tarfile.LNKTYPE
                info.linkname = P105_REAL_DERIVED_ARTIFACT
                tar.addfile(info)
            else:
                info.size = len(payload)
                tar.addfile(info, io.BytesIO(payload))
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
            gz.write(tar_buffer.getvalue())


def _allowlisted_members() -> dict[str, bytes]:
    return {name: _json_payload(name) for name in P105_REAL_DERIVED_ARCHIVE_MEMBERS}


def test_real_derived_p105_archive_is_deterministic_sorted_and_metadata_normalized() -> None:
    archive = _archive_path()

    assert archive.stat().st_size == EXPECTED_ARCHIVE_SIZE_BYTES
    assert _archive_sha256() == EXPECTED_ARCHIVE_SHA256

    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()

    assert [member.name for member in members] == list(P105_REAL_DERIVED_ARCHIVE_MEMBERS)
    assert [member.name for member in members] == sorted(member.name for member in members)
    for member in members:
        assert member.isfile()
        assert member.mtime == 0
        assert member.uid == 0
        assert member.gid == 0
        assert member.uname == ""
        assert member.gname == ""
        assert member.mode == 0o644
        assert not Path(member.name).is_absolute()
        assert ".." not in Path(member.name).parts


@pytest.mark.parametrize("unsafe_name", ["../escape.json", "/tmp/escape.json"])
def test_real_derived_p105_archive_extractor_rejects_traversal(tmp_path: Path, unsafe_name: str) -> None:
    malicious_archive = tmp_path / "malicious.tar.gz"
    payload = b"{}"
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w") as tar:
        info = tarfile.TarInfo(unsafe_name)
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    with malicious_archive.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
            gz.write(tar_buffer.getvalue())

    with pytest.raises(ValueError, match="unsafe archive member path"):
        safe_extract_p105_release_archive(malicious_archive, tmp_path / "extract")


def test_real_derived_p105_archive_extracts_and_unlocks_with_actual_validator(tmp_path: Path) -> None:
    artifact = safe_extract_p105_release_archive(_archive_path(), tmp_path / "release")

    report = _forecast_api().validate_p105_release_qualified_artifact(artifact)

    assert report["release_gate"]["release_qualified"] is True
    assert report["release_gate"]["p106_unlocked"] is True
    assert report["release_gate"]["validation_error_codes"] == []
    assert report["artifact_identity"]["sha256"] == hashlib.sha256(artifact.read_bytes()).hexdigest()

    prerequisite = _prerequisite_api().P106ReleasePrerequisite(maximum_age=timedelta(days=30_000)).validate(artifact)
    assert prerequisite.release_qualified is True
    assert prerequisite.p106_unlocked is True
    assert prerequisite.downstream_allowed is True


def test_real_derived_p105_archive_tamper_is_rejected_by_actual_validator(tmp_path: Path) -> None:
    artifact = safe_extract_p105_release_archive(_archive_path(), tmp_path / "release")
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    payload["rows"][0]["public_features"]["tamper_probe"] = "changed-after-archive-extract"
    artifact.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    report = _forecast_api().validate_p105_release_qualified_artifact(artifact)

    assert report["release_gate"]["release_qualified"] is False
    assert report["release_gate"]["p106_unlocked"] is False
    assert report["release_gate"]["validation_error_codes"]


def test_release_fixture_extractor_cli_exists_as_public_utility() -> None:
    assert EXTRACTOR_CLI.is_file(), f"P106 RED: missing public extractor utility {EXTRACTOR_CLI}"


def test_release_fixture_extractor_cli_requires_matching_archive_sha256(tmp_path: Path) -> None:
    result = _run_extractor(_archive_path(), "0" * 64, tmp_path / "release")

    assert result.returncode != 0
    assert "sha256" in result.stderr.lower()
    assert not (tmp_path / "release").exists()


def test_release_fixture_extractor_cli_extracts_atomically_prints_rows_path_and_unlocks(tmp_path: Path) -> None:
    output_dir = tmp_path / "release"

    result = _run_extractor(_archive_path(), EXPECTED_ARCHIVE_SHA256, output_dir)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    artifact = Path(result.stdout.strip())
    assert artifact == output_dir / P105_REAL_DERIVED_ARTIFACT
    assert artifact.is_file()
    assert sorted(path.name for path in output_dir.iterdir()) == list(P105_REAL_DERIVED_ARCHIVE_MEMBERS)

    report = _forecast_api().validate_p105_release_qualified_artifact(artifact)
    assert report["release_gate"]["release_qualified"] is True
    assert report["release_gate"]["p106_unlocked"] is True

    prerequisite = _prerequisite_api().P106ReleasePrerequisite(maximum_age=timedelta(days=30_000)).validate(artifact)
    assert prerequisite.downstream_allowed is True


def test_release_fixture_extractor_cli_rejects_extra_archive_member(tmp_path: Path) -> None:
    archive = tmp_path / "extra.tar.gz"
    members = _allowlisted_members()
    members["unexpected.json"] = b"{}"
    _write_archive(archive, members)

    result = _run_extractor(archive, _sha256(archive), tmp_path / "release")

    assert result.returncode != 0
    assert "unexpected.json" in result.stderr
    assert not (tmp_path / "release").exists()


def test_release_fixture_extractor_cli_rejects_missing_archive_member(tmp_path: Path) -> None:
    archive = tmp_path / "missing.tar.gz"
    members = _allowlisted_members()
    members.pop(P105_REAL_DERIVED_ARTIFACT)
    _write_archive(archive, members)

    result = _run_extractor(archive, _sha256(archive), tmp_path / "release")

    assert result.returncode != 0
    assert P105_REAL_DERIVED_ARTIFACT in result.stderr
    assert not (tmp_path / "release").exists()


def test_release_fixture_extractor_cli_rejects_traversal_member(tmp_path: Path) -> None:
    archive = tmp_path / "traversal.tar.gz"
    members = _allowlisted_members()
    members["../escape.json"] = b"{}"
    _write_archive(archive, members)

    result = _run_extractor(archive, _sha256(archive), tmp_path / "release")

    assert result.returncode != 0
    assert "traversal" in result.stderr.lower() or "unsafe" in result.stderr.lower()
    assert not (tmp_path / "release").exists()


def test_release_fixture_extractor_cli_rejects_symlink_member(tmp_path: Path) -> None:
    archive = tmp_path / "symlink.tar.gz"
    _write_archive(archive, {P105_REAL_DERIVED_ARTIFACT: b""}, member_type="symlink")

    result = _run_extractor(archive, _sha256(archive), tmp_path / "release")

    assert result.returncode != 0
    assert "symlink" in result.stderr.lower() or "regular" in result.stderr.lower()
    assert not (tmp_path / "release").exists()


def test_release_fixture_extractor_cli_rejects_hardlink_member(tmp_path: Path) -> None:
    archive = tmp_path / "hardlink.tar.gz"
    _write_archive(archive, {P105_REAL_DERIVED_ARTIFACT: b""}, member_type="hardlink")

    result = _run_extractor(archive, _sha256(archive), tmp_path / "release")

    assert result.returncode != 0
    assert "hardlink" in result.stderr.lower() or "regular" in result.stderr.lower()
    assert not (tmp_path / "release").exists()


def test_release_fixture_extractor_cli_refuses_non_empty_output_directory(tmp_path: Path) -> None:
    output_dir = tmp_path / "release"
    output_dir.mkdir()
    marker = output_dir / "existing.json"
    marker.write_text('{"keep": true}\n', encoding="utf-8")

    result = _run_extractor(_archive_path(), EXPECTED_ARCHIVE_SHA256, output_dir)

    assert result.returncode != 0
    assert "non-empty" in result.stderr.lower()
    assert marker.read_text(encoding="utf-8") == '{"keep": true}\n'


def test_release_fixture_extractor_cli_refuses_to_overwrite_existing_artifact(tmp_path: Path) -> None:
    output_dir = tmp_path / "release"
    output_dir.mkdir()
    artifact = output_dir / P105_REAL_DERIVED_ARTIFACT
    artifact.write_text('{"preexisting": true}\n', encoding="utf-8")

    result = _run_extractor(_archive_path(), EXPECTED_ARCHIVE_SHA256, output_dir)

    assert result.returncode != 0
    assert "overwrite" in result.stderr.lower() or "non-empty" in result.stderr.lower()
    assert artifact.read_text(encoding="utf-8") == '{"preexisting": true}\n'
