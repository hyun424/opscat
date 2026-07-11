#!/usr/bin/env python3
"""Build P122 twice from clean copies and persist byte-reproducibility proof."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.normalize_p122_sdist import DEFAULT_EPOCH, normalize_sdist  # noqa: E402, I001
PACKAGE_ROOT_FILES = ("pyproject.toml", "uv.lock", "README.md", "LICENSE")


def file_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def source_tree_hash(root: Path) -> str:
    selected = [root / name for name in PACKAGE_ROOT_FILES]
    selected.extend(sorted((root / "app").rglob("*.py")))
    selected.extend(sorted((root / "tests").rglob("*.py")))
    digest = hashlib.sha256()
    for path in selected:
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode() + b"\0" + path.read_bytes() + b"\0")
    return "sha256:" + digest.hexdigest()


def artifact_hashes(directory: Path) -> dict[str, str]:
    return {path.name: file_hash(path) for path in sorted(directory.glob("opscat-0.2.0*")) if path.is_file()}


def validate_evidence(evidence: dict[str, Any], *, root: Path = ROOT) -> bool:
    checksums = evidence.get("checksums")
    return (
        evidence.get("schema_version") == "p122.reproducible_build.v1"
        and evidence.get("byte_reproducible") is True
        and evidence.get("source_tree_hash") == source_tree_hash(root)
        and isinstance(checksums, dict)
        and len(checksums) == 2
        and all((root / "dist" / name).is_file() and digest == file_hash(root / "dist" / name) for name, digest in checksums.items())
    )


def _build_copy(source: Path, destination: Path, *, epoch: int) -> dict[str, str]:
    destination.mkdir(parents=True)
    for name in PACKAGE_ROOT_FILES:
        shutil.copy2(source / name, destination / name)
    shutil.copytree(source / "app", destination / "app", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(source / "tests", destination / "tests", ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"))
    output = destination / "dist"
    environment = dict(os.environ, SOURCE_DATE_EPOCH=str(epoch))
    subprocess.run(["uv", "build", "--out-dir", str(output), "--project", str(destination)], check=True, capture_output=True, text=True, env=environment)
    normalize_sdist(output / "opscat-0.2.0.tar.gz", output / "opscat-0.2.0.tar.gz", epoch=epoch)
    return artifact_hashes(output)


def build_and_verify(*, root: Path, epoch: int = DEFAULT_EPOCH) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="opscat-p122-build-") as temp_dir:
        first = Path(temp_dir) / "first"
        second = Path(temp_dir) / "second"
        first_hashes = _build_copy(root, first, epoch=epoch)
        second_hashes = _build_copy(root, second, epoch=epoch)
        reproducible = first_hashes == second_hashes and len(first_hashes) == 2
        if not reproducible:
            raise SystemExit(f"P122 package build is not byte reproducible: {first_hashes!r} != {second_hashes!r}")
        output = root / "dist"
        shutil.rmtree(output, ignore_errors=True)
        shutil.copytree(first / "dist", output)
    evidence: dict[str, Any] = {
        "schema_version": "p122.reproducible_build.v1",
        "source_date_epoch": epoch,
        "source_tree_hash": source_tree_hash(root),
        "clean_build_count": 2,
        "byte_reproducible": True,
        "checksums": first_hashes,
    }
    evidence["report_hash"] = "sha256:" + hashlib.sha256(json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    evidence_dir = root / "evals" / "p122"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.joinpath("package-checksums.json").write_text(json.dumps(first_hashes, indent=2, sort_keys=True) + "\n")
    evidence_dir.joinpath("reproducible-build.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        evidence = json.loads((args.root / "evals" / "p122" / "reproducible-build.json").read_text())
        if not isinstance(evidence, dict) or not validate_evidence(evidence, root=args.root):
            raise SystemExit("P122 reproducible-build evidence is missing, stale, or invalid")
    else:
        evidence = build_and_verify(root=args.root)
    print(json.dumps({"byte_reproducible": evidence.get("byte_reproducible"), "checksums": evidence.get("checksums")}, sort_keys=True))


if __name__ == "__main__":
    main()
