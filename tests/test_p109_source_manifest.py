from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from app.services.p109_source_manifest import (
    P109SourceManifest,
    P109SourceManifestError,
    load_p109_source_manifest,
)

IMMUTABLE_COMMIT = "0123456789abcdef0123456789abcdef01234567"


def _artifact(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "p109.source_artifact.v1",
        "source_id": "rcaeval-fixture",
        "canonical_url": "https://example.org/rcaeval/archive.zip",
        "revision": IMMUTABLE_COMMIT,
        "revision_kind": "commit",
        "license": "fixture-only",
        "citation": "RCAEval fixture citation",
        "expected_paths": ["cases/case-001/metrics.jsonl"],
        "dataset_schema": "p109.rcaeval_case.v1",
        "max_compressed_bytes": 4096,
        "max_decompressed_bytes": 8192,
        "max_file_count": 8,
        "redirect_allowlist": [{"host": "example.org", "path_prefix": "/rcaeval/"}],
        "sha256": "0" * 64,
        "provenance_hashes": {
            "schema_version": "p109.provenance_hashes.v1",
            "canonical_manifest": "1" * 64,
            "downloaded_bytes": "2" * 64,
            "extracted_tree": "3" * 64,
            "normalized_corpus": "4" * 64,
        },
    }
    payload.update(overrides)
    return payload


def _manifest(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "p109.source_manifest.v1",
        "manifest_id": "p109-fixture-manifest",
        "generated_at": "2024-03-09T16:33:20Z",
        "allowed_signers": [{"signer_id": "reviewer-a", "key_id": "key-a"}],
        "artifacts": [_artifact()],
    }
    payload.update(overrides)
    return payload


def _write_json(path: Path, payload: Any) -> Path:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def test_source_manifest_requires_versioned_manifest_and_artifact_contract(tmp_path: Path) -> None:
    manifest_path = _write_json(tmp_path / "manifest.json", _manifest())

    manifest = load_p109_source_manifest(manifest_path)

    assert isinstance(manifest, P109SourceManifest)
    assert manifest.schema_version == "p109.source_manifest.v1"
    assert manifest.artifact_ids == ("rcaeval-fixture",)
    assert manifest.get_artifact("rcaeval-fixture").dataset_schema == "p109.rcaeval_case.v1"
    assert manifest.to_dict()["manifest_sha256"] == hashlib.sha256(
        json.dumps(_manifest(), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    ).hexdigest()


@pytest.mark.parametrize(
    "mutator,match",
    [
        (lambda payload: payload.__setitem__("schema_version", "p109.source_manifest.v2"), "schema_version"),
        (lambda payload: payload.__setitem__("allowed_signers", []), "allowed_signers"),
        (lambda payload: payload["artifacts"][0].__setitem__("canonical_url", "http://example.org/archive.zip"), "canonical_url"),
        (lambda payload: payload["artifacts"][0].__setitem__("license", ""), "license"),
        (lambda payload: payload["artifacts"][0].__setitem__("expected_paths", []), "expected_paths"),
        (lambda payload: payload["artifacts"][0].__setitem__("sha256", "not-a-sha"), "sha256"),
        (lambda payload: payload["artifacts"][0].__setitem__("dataset_schema", "p109.unknown.v1"), "dataset_schema"),
    ],
)
def test_source_manifest_rejects_missing_required_provenance_fields(
    tmp_path: Path,
    mutator: Any,
    match: str,
) -> None:
    payload = _manifest()
    mutator(payload)

    with pytest.raises(P109SourceManifestError, match=match):
        load_p109_source_manifest(_write_json(tmp_path / "manifest.json", payload))


@pytest.mark.parametrize("moving_revision", ["main", "master", "HEAD", "latest", "v1.2.3", "release"])
def test_moving_revision_is_rejected(tmp_path: Path, moving_revision: str) -> None:
    payload = _manifest(artifacts=[_artifact(revision=moving_revision, revision_kind="tag")])

    with pytest.raises(P109SourceManifestError, match="moving_revision"):
        load_p109_source_manifest(_write_json(tmp_path / "manifest.json", payload))


def test_duplicate_and_unknown_source_ids_fail_closed(tmp_path: Path) -> None:
    duplicate = _manifest(artifacts=[_artifact(), _artifact()])

    with pytest.raises(P109SourceManifestError, match="duplicate"):
        load_p109_source_manifest(_write_json(tmp_path / "manifest.json", duplicate))

    manifest = load_p109_source_manifest(_write_json(tmp_path / "valid.json", _manifest()))
    with pytest.raises(P109SourceManifestError, match="unknown_source"):
        manifest.get_artifact("missing-source")
