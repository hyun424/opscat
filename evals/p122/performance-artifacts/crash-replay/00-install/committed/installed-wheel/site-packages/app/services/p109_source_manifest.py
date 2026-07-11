"""P109 source provenance manifest validation.

The manifest is metadata only. Loading it never downloads, shells out, or opens
remote resources.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SOURCE_MANIFEST_SCHEMA = "p109.source_manifest.v1"
SOURCE_ARTIFACT_SCHEMA = "p109.source_artifact.v1"
PROVENANCE_HASHES_SCHEMA = "p109.provenance_hashes.v1"
SUPPORTED_DATASET_SCHEMAS = {"p109.rcaeval_case.v1", "p109.microremed_bundle.v1"}

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_MOVING_REVISIONS = {"head", "main", "master", "trunk", "dev", "develop", "latest", "release", "stable"}


class P109SourceManifestError(ValueError):
    """Raised when a P109 source manifest fails closed."""


SourceManifestError = P109SourceManifestError


@dataclass(frozen=True)
class P109RedirectRule:
    host: str
    path_prefix: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], *, context: str) -> P109RedirectRule:
        host = _required_str(data, "host", context)
        path_prefix = _required_str(data, "path_prefix", context)
        if not path_prefix.startswith("/"):
            raise P109SourceManifestError(f"{context}.path_prefix must start with /")
        return cls(host=host.lower(), path_prefix=path_prefix)

    def to_dict(self) -> dict[str, str]:
        return {"host": self.host, "path_prefix": self.path_prefix}


@dataclass(frozen=True)
class P109ProvenanceHashes:
    canonical_manifest: str
    downloaded_bytes: str
    extracted_tree: str
    normalized_corpus: str
    public_attestation: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], *, context: str) -> P109ProvenanceHashes:
        if data.get("schema_version") != PROVENANCE_HASHES_SCHEMA:
            raise P109SourceManifestError(f"{context}.schema_version must be {PROVENANCE_HASHES_SCHEMA}")
        canonical_manifest = _optional_sha256_any(data, ("canonical_manifest", "canonical_manifest_sha256"), context)
        downloaded_bytes = _optional_sha256_any(data, ("downloaded_bytes", "downloaded_bytes_sha256"), context)
        extracted_tree = _optional_sha256_any(data, ("extracted_tree", "extracted_tree_sha256"), context)
        normalized_corpus = _optional_sha256_any(data, ("normalized_corpus", "normalized_corpus_sha256"), context)
        public_attestation = data.get("public_attestation", data.get("public_attestation_sha256"))
        if public_attestation is not None and not _is_sha256(str(public_attestation)):
            raise P109SourceManifestError(f"{context}.public_attestation must be sha256 hex")
        return cls(
            canonical_manifest=canonical_manifest,
            downloaded_bytes=downloaded_bytes,
            extracted_tree=extracted_tree,
            normalized_corpus=normalized_corpus,
            public_attestation=str(public_attestation) if public_attestation is not None else None,
        )

    def to_dict(self) -> dict[str, str]:
        payload = {
            "schema_version": PROVENANCE_HASHES_SCHEMA,
            "canonical_manifest": self.canonical_manifest,
            "downloaded_bytes": self.downloaded_bytes,
            "extracted_tree": self.extracted_tree,
            "normalized_corpus": self.normalized_corpus,
        }
        if self.public_attestation is not None:
            payload["public_attestation"] = self.public_attestation
        return payload


@dataclass(frozen=True)
class P109SourceArtifact:
    source_id: str
    canonical_url: str
    revision: str
    revision_kind: str
    license: str
    citation: str
    expected_paths: tuple[str, ...]
    dataset_schema: str
    max_compressed_bytes: int
    max_decompressed_bytes: int
    max_file_count: int
    redirect_allowlist: tuple[P109RedirectRule, ...]
    sha256: str
    provenance_hashes: P109ProvenanceHashes

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], *, index: int) -> P109SourceArtifact:
        context = f"artifacts[{index}]"
        if data.get("schema_version") != SOURCE_ARTIFACT_SCHEMA:
            raise P109SourceManifestError(f"{context}.schema_version must be {SOURCE_ARTIFACT_SCHEMA}")
        source_id = _required_str(data, "source_id", context)
        canonical_url = _required_https_url(data, "canonical_url", context)
        revision = _required_str(data, "revision", context)
        revision_kind = _required_str_any(data, ("revision_kind", "revision_type"), context)
        _validate_revision(revision, revision_kind, context)
        license_note, citation = _license_and_citation(data, context)
        expected_paths = _required_string_tuple(data, "expected_paths", context)
        normalized_expected_paths: list[str] = []
        seen_expected_paths: set[str] = set()
        for item in expected_paths:
            _validate_relative_path(item, f"{context}.expected_paths")
            normalized = _normalized_relative_path(item)
            if normalized in seen_expected_paths:
                raise P109SourceManifestError(f"{context}.expected_paths duplicate path: {item}")
            seen_expected_paths.add(normalized)
            normalized_expected_paths.append(normalized)
        dataset_schema = _required_str(data, "dataset_schema", context)
        if dataset_schema not in SUPPORTED_DATASET_SCHEMAS:
            raise P109SourceManifestError(f"{context}.dataset_schema unsupported: {dataset_schema}")
        max_compressed_bytes = _positive_int(data, "max_compressed_bytes", context)
        max_decompressed_bytes = _positive_int(data, "max_decompressed_bytes", context)
        max_file_count = _positive_int(data, "max_file_count", context)
        sha256 = _required_sha256(data, "sha256", context)
        redirect_allowlist = _parse_redirect_allowlist(data.get("redirect_allowlist"), context)
        if not redirect_allowlist:
            raise P109SourceManifestError(f"{context}.redirect_allowlist must not be empty")
        provenance_hashes = P109ProvenanceHashes.from_dict(
            _required_mapping(data, "provenance_hashes", context),
            context=f"{context}.provenance_hashes",
        )
        return cls(
            source_id=source_id,
            canonical_url=canonical_url,
            revision=revision,
            revision_kind=revision_kind,
            license=license_note,
            citation=citation,
            expected_paths=tuple(normalized_expected_paths),
            dataset_schema=dataset_schema,
            max_compressed_bytes=max_compressed_bytes,
            max_decompressed_bytes=max_decompressed_bytes,
            max_file_count=max_file_count,
            redirect_allowlist=redirect_allowlist,
            sha256=sha256,
            provenance_hashes=provenance_hashes,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SOURCE_ARTIFACT_SCHEMA,
            "source_id": self.source_id,
            "canonical_url": self.canonical_url,
            "revision": self.revision,
            "revision_kind": self.revision_kind,
            "license": self.license,
            "citation": self.citation,
            "expected_paths": list(self.expected_paths),
            "dataset_schema": self.dataset_schema,
            "max_compressed_bytes": self.max_compressed_bytes,
            "max_decompressed_bytes": self.max_decompressed_bytes,
            "max_file_count": self.max_file_count,
            "redirect_allowlist": [rule.to_dict() for rule in self.redirect_allowlist],
            "sha256": self.sha256,
            "provenance_hashes": self.provenance_hashes.to_dict(),
        }


@dataclass(frozen=True)
class P109SourceManifest:
    manifest_id: str
    generated_at: str
    allowed_signers: tuple[Mapping[str, str], ...]
    artifacts: tuple[P109SourceArtifact, ...]
    manifest_sha256: str
    schema_version: str = SOURCE_MANIFEST_SCHEMA

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> P109SourceManifest:
        if data.get("schema_version") != SOURCE_MANIFEST_SCHEMA:
            raise P109SourceManifestError(f"schema_version must be {SOURCE_MANIFEST_SCHEMA}")
        manifest_id = _required_str(data, "manifest_id", "manifest")
        generated_at = _required_str(data, "generated_at", "manifest")
        allowed_signers_raw = _required_sequence(data, "allowed_signers", "manifest")
        allowed_signers: list[Mapping[str, str]] = []
        for idx, item in enumerate(allowed_signers_raw):
            signer = _required_mapping({"item": item}, "item", f"allowed_signers[{idx}]")
            signer_id = _required_str(signer, "signer_id", f"allowed_signers[{idx}]")
            key_id = _required_str(signer, "key_id", f"allowed_signers[{idx}]")
            allowed_signers.append({"signer_id": signer_id, "key_id": key_id})
        if not allowed_signers:
            raise P109SourceManifestError("allowed_signers must not be empty")
        artifacts_raw = _required_sequence(data, "artifacts", "manifest")
        artifacts = tuple(
            P109SourceArtifact.from_dict(item, index=idx)
            for idx, item in enumerate(artifacts_raw)
            if _ensure_mapping(item, f"artifacts[{idx}]")
        )
        if not artifacts:
            raise P109SourceManifestError("artifacts must not be empty")
        source_ids = [artifact.source_id for artifact in artifacts]
        duplicates = sorted({item for item in source_ids if source_ids.count(item) > 1})
        if duplicates:
            raise P109SourceManifestError(f"duplicate source_id: {', '.join(duplicates)}")
        manifest_sha256 = _canonical_sha256(data)
        return cls(
            manifest_id=manifest_id,
            generated_at=generated_at,
            allowed_signers=tuple(allowed_signers),
            artifacts=artifacts,
            manifest_sha256=manifest_sha256,
        )

    @property
    def artifact_ids(self) -> tuple[str, ...]:
        return tuple(artifact.source_id for artifact in self.artifacts)

    def get_artifact(self, source_id: str) -> P109SourceArtifact:
        for artifact in self.artifacts:
            if artifact.source_id == source_id:
                return artifact
        raise P109SourceManifestError(f"unknown_source: {source_id}")

    def require_artifact(self, source_id: str) -> P109SourceArtifact:
        return self.get_artifact(source_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "manifest_id": self.manifest_id,
            "generated_at": self.generated_at,
            "allowed_signers": [dict(item) for item in self.allowed_signers],
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "manifest_sha256": self.manifest_sha256,
        }


def load_p109_source_manifest(path: str | Path) -> P109SourceManifest:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise P109SourceManifestError("manifest must be a JSON object")
    return P109SourceManifest.from_dict(data)


def validate_p109_source_manifest(payload: Mapping[str, Any]) -> P109SourceManifest:
    return P109SourceManifest.from_dict(payload)


def parse_p109_source_manifest(payload: Mapping[str, Any]) -> P109SourceManifest:
    return validate_p109_source_manifest(payload)


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _required_str(data: Mapping[str, Any], key: str, context: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise P109SourceManifestError(f"{context}.{key} is required")
    return value


def _required_str_any(data: Mapping[str, Any], keys: tuple[str, ...], context: str) -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    raise P109SourceManifestError(f"{context}.{keys[0]} is required")


def _optional_sha256_any(data: Mapping[str, Any], keys: tuple[str, ...], context: str) -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and _is_sha256(value):
            return value
    raise P109SourceManifestError(f"{context}.{keys[0]} must be sha256 hex")


def _license_and_citation(data: Mapping[str, Any], context: str) -> tuple[str, str]:
    license_value = data.get("license")
    if isinstance(license_value, Mapping):
        license_note = _required_str(license_value, "name", f"{context}.license")
        citation = str(license_value.get("citation") or data.get("citation") or "")
        if not citation:
            raise P109SourceManifestError(f"{context}.citation is required")
        return license_note, citation
    return _required_str(data, "license", context), _required_str(data, "citation", context)


def _parse_redirect_allowlist(value: Any, context: str) -> tuple[P109RedirectRule, ...]:
    if isinstance(value, Mapping):
        hosts = _required_sequence(value, "hosts", f"{context}.redirect_allowlist")
        prefixes = _required_sequence(value, "path_prefixes", f"{context}.redirect_allowlist")
        rules = tuple(
            P109RedirectRule.from_dict({"host": host, "path_prefix": prefix}, context=f"{context}.redirect_allowlist")
            for host in hosts
            for prefix in prefixes
        )
    else:
        redirect_rules_raw = _required_sequence({"redirect_allowlist": value}, "redirect_allowlist", context)
        rules = tuple(
            P109RedirectRule.from_dict(item, context=f"{context}.redirect_allowlist[{idx}]")
            for idx, item in enumerate(redirect_rules_raw)
            if _ensure_mapping(item, f"{context}.redirect_allowlist[{idx}]")
        )
    if not rules:
        raise P109SourceManifestError(f"{context}.redirect_allowlist must not be empty")
    return rules


def _required_https_url(data: Mapping[str, Any], key: str, context: str) -> str:
    value = _required_str(data, key, context)
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or not parsed.path:
        raise P109SourceManifestError(f"{context}.{key} must be canonical HTTPS URL")
    if parsed.username or parsed.password or parsed.fragment:
        raise P109SourceManifestError(f"{context}.{key} must not contain credentials or fragment")
    return value


def _required_mapping(data: Mapping[str, Any], key: str, context: str) -> Mapping[str, Any]:
    value = data.get(key)
    if not isinstance(value, Mapping):
        raise P109SourceManifestError(f"{context}.{key} must be an object")
    return value


def _required_sequence(data: Mapping[str, Any], key: str, context: str) -> Sequence[Any]:
    value = data.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise P109SourceManifestError(f"{context}.{key} must be a list")
    return value


def _required_string_tuple(data: Mapping[str, Any], key: str, context: str) -> tuple[str, ...]:
    values = _required_sequence(data, key, context)
    if not values:
        raise P109SourceManifestError(f"{context}.{key} must not be empty")
    result = tuple(str(item) for item in values if isinstance(item, str) and item)
    if len(result) != len(values):
        raise P109SourceManifestError(f"{context}.{key} must contain only non-empty strings")
    return result


def _ensure_mapping(value: Any, context: str) -> bool:
    if not isinstance(value, Mapping):
        raise P109SourceManifestError(f"{context} must be an object")
    return True


def _positive_int(data: Mapping[str, Any], key: str, context: str) -> int:
    value = data.get(key)
    if not isinstance(value, int) or value <= 0:
        raise P109SourceManifestError(f"{context}.{key} must be a positive integer")
    return value


def _required_sha256(data: Mapping[str, Any], key: str, context: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not _is_sha256(value):
        raise P109SourceManifestError(f"{context}.{key} must be sha256 hex")
    return value


def _is_sha256(value: str) -> bool:
    return bool(_SHA256_RE.fullmatch(value))


def _validate_revision(revision: str, revision_kind: str, context: str) -> None:
    normalized = revision.strip().lower()
    if revision_kind == "tag":
        raise P109SourceManifestError(f"{context}.moving_revision rejected")
    if normalized in _MOVING_REVISIONS or normalized.startswith(("refs/heads/", "refs/tags/")):
        raise P109SourceManifestError(f"{context}.moving_revision rejected")
    if revision_kind == "commit":
        if not _COMMIT_RE.fullmatch(revision):
            raise P109SourceManifestError(f"{context}.revision must be immutable commit hash")
        return
    if revision_kind == "release":
        if normalized.startswith("v") or normalized in _MOVING_REVISIONS:
            raise P109SourceManifestError(f"{context}.moving_revision rejected")
        if not (revision.startswith("release-sha256:") and _is_sha256(revision.removeprefix("release-sha256:"))):
            raise P109SourceManifestError(f"{context}.revision release must be content-addressed")
        return
    raise P109SourceManifestError(f"{context}.revision_kind unsupported")


def _validate_relative_path(path: str, context: str) -> None:
    normalized = path.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part not in ("", ".")]
    if normalized.startswith("/") or ".." in parts or not parts:
        raise P109SourceManifestError(f"{context} must contain safe relative paths")


def _normalized_relative_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part != "."]
    if normalized.startswith("/") or ".." in parts or not parts or any(part == "" for part in parts):
        raise P109SourceManifestError("relative path must be safe and normalized")
    return "/".join(parts).lower()
