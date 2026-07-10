from __future__ import annotations

import tarfile
from pathlib import Path

P105_REAL_DERIVED_ARCHIVE = Path("evals/prevention/p105_release_qualified_real_derived.tar.gz")
P105_REAL_DERIVED_ARTIFACT = "p105-release-qualified-rows.json"
P105_REAL_DERIVED_ARCHIVE_MEMBERS = (
    "p105-citation-manifest.json",
    "p105-coverage.json",
    "p105-license-manifest.json",
    "p105-p24-parity.json",
    "p105-partitions.json",
    "p105-privacy-redaction-manifest.json",
    "p105-private-scorer-label-ledger.json",
    "p105-provenance-hash-manifest.json",
    "p105-release-qualified-benchmark.json",
    "p105-release-qualified-rows.json",
    "p105-review.json",
    "p105-source-availability-preflight.json",
    "p105-source-manifest.json",
)


def safe_extract_p105_release_archive(archive_path: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        for member in members:
            member_path = Path(member.name)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise ValueError(f"unsafe archive member path: {member.name}")
            if not member.isfile():
                raise ValueError(f"unsupported archive member type: {member.name}")
            target = (destination / member.name).resolve()
            if root not in (target, *target.parents):
                raise ValueError(f"archive member escapes destination: {member.name}")
        archive.extractall(destination, members=members)
    return destination / P105_REAL_DERIVED_ARTIFACT
