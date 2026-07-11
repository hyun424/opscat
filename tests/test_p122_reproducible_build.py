from __future__ import annotations

import json
from pathlib import Path

from scripts.verify_p122_reproducible_build import artifact_hashes, source_tree_hash, validate_evidence


def test_reproducible_build_evidence_is_source_and_artifact_bound(tmp_path: Path) -> None:
    tmp_path.joinpath("app").mkdir()
    tmp_path.joinpath("tests").mkdir()
    tmp_path.joinpath("app/example.py").write_text("VALUE = 1\n")
    for name in ("pyproject.toml", "uv.lock", "README.md", "LICENSE"):
        tmp_path.joinpath(name).write_text(name)
    dist = tmp_path / "dist"
    dist.mkdir()
    dist.joinpath("opscat-0.2.0-py3-none-any.whl").write_bytes(b"wheel")
    dist.joinpath("opscat-0.2.0.tar.gz").write_bytes(b"sdist")
    checksums = artifact_hashes(dist)
    evidence = {
        "schema_version": "p122.reproducible_build.v1",
        "byte_reproducible": True,
        "source_tree_hash": source_tree_hash(tmp_path),
        "checksums": checksums,
    }
    assert validate_evidence(evidence, root=tmp_path)
    tmp_path.joinpath("app/example.py").write_text("VALUE = 2\n")
    assert not validate_evidence(json.loads(json.dumps(evidence)), root=tmp_path)
