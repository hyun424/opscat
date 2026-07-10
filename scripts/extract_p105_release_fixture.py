#!/usr/bin/env python3
"""Verify and atomically extract the allowlisted P105 release fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

ROWS_ARTIFACT = "p105-release-qualified-rows.json"
ALLOWED_MEMBERS = (
    "p105-citation-manifest.json",
    "p105-coverage.json",
    "p105-license-manifest.json",
    "p105-p24-parity.json",
    "p105-partitions.json",
    "p105-privacy-redaction-manifest.json",
    "p105-private-scorer-label-ledger.json",
    "p105-provenance-hash-manifest.json",
    "p105-release-qualified-benchmark.json",
    ROWS_ARTIFACT,
    "p105-review.json",
    "p105-source-availability-preflight.json",
    "p105-source-manifest.json",
)
ALLOWED_MEMBER_SET = frozenset(ALLOWED_MEMBERS)


class ExtractionError(Exception):
    """Raised when an archive cannot be safely extracted."""


def _parse_sha256(value: str) -> str:
    digest = value.removeprefix("sha256:").lower()
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise argparse.ArgumentTypeError("sha256 must be exactly 64 hexadecimal characters")
    return digest


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_output(output_dir: Path) -> bool:
    if output_dir.is_symlink() or (output_dir.exists() and not output_dir.is_dir()):
        raise ExtractionError(f"refusing to overwrite existing output path: {output_dir}")
    if not output_dir.exists():
        return False
    if any(output_dir.iterdir()):
        raise ExtractionError(f"output directory is non-empty; refusing overwrite: {output_dir}")
    return True


def _validate_members(archive: tarfile.TarFile) -> list[tarfile.TarInfo]:
    members = archive.getmembers()
    seen: set[str] = set()

    for member in members:
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts or len(path.parts) != 1:
            raise ExtractionError(f"unsafe traversal or nested archive member: {member.name}")
        if member.issym():
            raise ExtractionError(f"symlink member is not a regular JSON file: {member.name}")
        if member.islnk():
            raise ExtractionError(f"hardlink member is not a regular JSON file: {member.name}")
        if not member.isfile():
            raise ExtractionError(f"archive member is not a regular JSON file: {member.name}")
        if member.name in seen:
            raise ExtractionError(f"duplicate archive member: {member.name}")
        seen.add(member.name)

    missing = ALLOWED_MEMBER_SET - seen
    extra = seen - ALLOWED_MEMBER_SET
    if missing:
        raise ExtractionError(f"missing archive member(s): {', '.join(sorted(missing))}")
    if extra:
        raise ExtractionError(f"unexpected archive member(s): {', '.join(sorted(extra))}")
    return members


def _extract_members(
    archive: tarfile.TarFile,
    members: list[tarfile.TarInfo],
    staging_dir: Path,
) -> None:
    for member in members:
        source = archive.extractfile(member)
        if source is None:
            raise ExtractionError(f"unable to read archive member: {member.name}")
        destination = staging_dir / member.name
        with source, destination.open("xb") as target:
            shutil.copyfileobj(source, target)
        # Preserve the archive's deterministic timestamp. Extraction time must
        # never masquerade as P105 evidence-generation freshness.
        os.utime(destination, (member.mtime, member.mtime), follow_symlinks=False)
        try:
            with destination.open("rb") as extracted:
                json.load(extracted)
        except json.JSONDecodeError as exc:
            raise ExtractionError(f"archive member is not valid JSON: {member.name}") from exc


def extract_release_fixture(
    archive_path: Path,
    expected_sha256: str,
    output_dir: Path,
) -> Path:
    actual_sha256 = _sha256(archive_path)
    if actual_sha256 != expected_sha256:
        raise ExtractionError(
            f"sha256 mismatch for {archive_path}: expected {expected_sha256}, got {actual_sha256}"
        )

    output_existed_empty = _validate_output(output_dir)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.tmp-", dir=output_dir.parent)
    )
    installed = False
    try:
        with tarfile.open(archive_path, mode="r:*") as archive:
            members = _validate_members(archive)
            _extract_members(archive, members, staging_dir)

        if output_existed_empty:
            try:
                output_dir.rmdir()
            except OSError as exc:
                raise ExtractionError(
                    f"output directory became non-empty; refusing overwrite: {output_dir}"
                ) from exc
        os.replace(staging_dir, output_dir)
        installed = True
    finally:
        if not installed and staging_dir.exists():
            shutil.rmtree(staging_dir)

    return output_dir / ROWS_ARTIFACT


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify and extract the exact P105 release fixture archive."
    )
    parser.add_argument("archive", type=Path)
    parser.add_argument("sha256", type=_parse_sha256)
    parser.add_argument("output_dir", type=Path)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        rows_path = extract_release_fixture(args.archive, args.sha256, args.output_dir)
    except (ExtractionError, OSError, tarfile.TarError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(rows_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
