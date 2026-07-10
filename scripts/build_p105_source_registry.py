#!/usr/bin/env python3
"""Build the P105 reviewed source registry and eligibility manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

SUPPORTED_FAMILIES = {"database", "deploy", "queue"}
UNSUPPORTED_FAMILY = "unsupported_family"
REGISTRY_SCHEMA_VERSION = "p105.source-registry.v1"
ELIGIBILITY_SCHEMA_VERSION = "p105.source-eligibility.v1"
LEDGER_SCHEMA_VERSION = "p105.source-review-ledger.v1"
SOURCE_MANIFEST_SCHEMA_VERSION = "p105.reviewed-local-source.v1"
REQUIRED_SCHEMA_ADAPTERS = {
    "p32": "p105.adapter.p32-replay.v1",
    "p41": "p105.adapter.p41-sources.v1",
    "p44": "p105.adapter.p44-reviewed-local.v1",
    "dejavu_a1": "p105.adapter.dejavu-a1-reviewed-local.v1",
    "db_pool": "p105.adapter.database-pool-harness.v1",
    "queue": "p105.adapter.rabbitmq-harness.v1",
    "deploy": "p105.adapter.threading-http-deploy-harness.v1",
    "database_fleet": "p105.adapter.sqlite-pool-fleet-harness.v1",
    "queue_fleet": "p105.adapter.rabbitmq-fleet-harness.v1",
    "deploy_fleet": "p105.adapter.threading-http-deploy-fleet-harness.v1",
}
FLEET_PROFILE = "p105.actual-fleet-soak.256x1h.v1"
FLEET_DIAGNOSTIC_PROFILES = {
    "database_fleet": "p105.database-fleet.diagnostic.fast.v1",
    "queue_fleet": "p105.queue-fleet.diagnostic.fast.v1",
    "deploy_fleet": "p105.deploy-fleet.diagnostic.fast.v1",
}
FLEET_ROOT_SCHEMAS = {
    "database_fleet": "p105.database.fleet_harness.v1",
    "queue_fleet": "p105.queue.fleet_harness.v1",
    "deploy_fleet": "p105.deploy.fleet_harness.v1",
}
RUNTIME_FAMILY_BY_ADAPTER = {
    "db_pool": "database",
    "queue": "queue",
    "deploy": "deploy",
    "database_fleet": "database",
    "queue_fleet": "queue",
    "deploy_fleet": "deploy",
}
FLEET_ADAPTER_BY_ROOT_SCHEMA = {schema: adapter_key for adapter_key, schema in FLEET_ROOT_SCHEMAS.items()}
LEGACY_RUNTIME_ROOT_SCHEMAS = {
    "db_pool": {"p105.database.pool.harness_manifest.v1", "p105.database.pool.harness.manifest.v1"},
    "queue": {"p105.queue.harness_manifest.v1", "p105.queue.harness.manifest.v1"},
    "deploy": {"p105.deploy.harness_manifest.v1", "p105.deploy.harness.manifest.v1"},
}
LEGACY_RUNTIME_ADAPTER_BY_FLEET_ADAPTER = {
    "database_fleet": "db_pool",
    "queue_fleet": "queue",
    "deploy_fleet": "deploy",
}
KNOWN_ROOT_SCHEMAS = {
    SOURCE_MANIFEST_SCHEMA_VERSION,
    "p105.reviewed_p44_local_manifest.v1",
    "p105.reviewed_p44_local_manifest.v2",
    "p105.reviewed_p44_local_manifest.v3",
    "p105.dejavu_a1.reviewed_local_manifest.v1",
    "p105.database.pool.harness_manifest.v1",
    "p105.database.pool.harness.manifest.v1",
    "p105.queue.harness_manifest.v1",
    "p105.queue.harness.manifest.v1",
    "p105.deploy.harness_manifest.v1",
    "p105.deploy.harness.manifest.v1",
    *FLEET_ROOT_SCHEMAS.values(),
    "p32-replay-pack.v1",
    "p41-raw-sources-v1",
}
ALLOWED_UNSUPPORTED_REASONS = {
    "unreviewed_source",
    "license_rejected",
    "privacy_rejected",
    "parser_failed",
    "predicate_unmapped",
    "missing_private_ledger",
    "missing_partition",
    "missing_actual_coverage",
    "provenance_mismatch",
    "source_insufficient",
}


class RegistryError(ValueError):
    """Raised when source registry inputs fail closed validation."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _json_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RegistryError(f"{label} unreadable: {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RegistryError(f"{label} invalid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RegistryError(f"{label} must be a JSON object: {path}")
    return payload


def _require_string(payload: dict[str, Any], key: str, *, context: str, allow_empty: bool = False) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or (not allow_empty and not value):
        raise RegistryError(f"{context} requires string {key}")
    return value


def _require_list(payload: dict[str, Any], key: str, *, context: str) -> list[Any]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise RegistryError(f"{context} requires list {key}")
    return value


def _normalize_path(path: str | Path) -> str:
    return str(Path(path))


def _validate_command_argv(value: Any, *, context: str) -> list[str]:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise RegistryError(f"{context} requires non-empty command_argv")
    return list(value)


def _validate_content_hashes(value: Any, *, context: str) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise RegistryError(f"{context} requires non-empty source_content_hashes")
    hashes: list[dict[str, str]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise RegistryError(f"{context} source_content_hashes[{index}] must be an object")
        raw_path = _require_string(item, "path", context=f"{context} source_content_hashes[{index}]")
        expected_sha = _require_string(item, "sha256", context=f"{context} source_content_hashes[{index}]")
        path = Path(raw_path)
        if not path.exists():
            raise RegistryError(f"{context} source_content_hashes[{index}] path is missing: {raw_path}")
        actual_sha = _file_sha256(path)
        if actual_sha != expected_sha:
            raise RegistryError(f"{context} source_content_hashes[{index}] sha256 mismatch for {raw_path}")
        hashes.append({"path": _normalize_path(raw_path), "sha256": expected_sha})
    return sorted(hashes, key=lambda item: (item["path"], item["sha256"]))


def _validate_adapter(value: Any, *, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RegistryError(f"{context} requires adapter_or_harness object")
    command_argv = _validate_command_argv(value.get("command_argv"), context=f"{context} adapter_or_harness")
    adapter = {
        "name": _require_string(value, "name", context=f"{context} adapter_or_harness"),
        "version": _require_string(value, "version", context=f"{context} adapter_or_harness"),
        "command_argv": command_argv,
        "command_argv_sha256": _json_sha256(command_argv),
    }
    return adapter


def _parse_schema_adapters(values: list[str] | None) -> dict[str, str]:
    adapters: dict[str, str] = {}
    for value in values or []:
        if "=" not in value:
            raise RegistryError("unknown_source_schema: schema adapters must be source=adapter_version")
        key, version = value.split("=", 1)
        if not key or not version:
            raise RegistryError("unknown_source_schema: schema adapters must be source=adapter_version")
        adapters[key] = version
    return adapters


def _validate_schema_adapters(
    adapters: dict[str, str],
    *,
    fail_on_unknown_source_schema: bool,
    required_keys: set[str] | None = None,
) -> None:
    if not fail_on_unknown_source_schema:
        return
    required = required_keys or set(REQUIRED_SCHEMA_ADAPTERS)
    missing = [key for key, expected in REQUIRED_SCHEMA_ADAPTERS.items() if key in required and adapters.get(key) != expected]
    unknown = [key for key in adapters if key not in REQUIRED_SCHEMA_ADAPTERS]
    if missing or unknown:
        raise RegistryError(f"unknown_source_schema: missing={','.join(missing)} unknown={','.join(unknown)}")


def _root_schema(manifest: dict[str, Any]) -> str:
    if manifest.get("id") == "p32-real-telemetry-replay-pack":
        return "p32-replay-pack.v1"
    if manifest.get("adapter_or_parser_version") == "p105.dejavu_a1.reviewed_local.v1":
        return "p105.dejavu_a1.reviewed_local_manifest.v1"
    verifier_compatibility = manifest.get("verifier_compatibility")
    if isinstance(verifier_compatibility, dict) and isinstance(verifier_compatibility.get("manifest_schema"), str):
        return str(verifier_compatibility["manifest_schema"])
    schema = manifest.get("schema_version") or manifest.get("version")
    if isinstance(schema, str) and schema:
        return schema
    public_config = manifest.get("public_config")
    if isinstance(public_config, dict) and isinstance(public_config.get("schema_version"), str):
        return str(public_config["schema_version"])
    return ""


def _validate_known_root_schema(manifest_path: Path, manifest: dict[str, Any], *, fail_on_unknown_source_schema: bool) -> None:
    if not fail_on_unknown_source_schema:
        return
    schema = _root_schema(manifest)
    if schema not in KNOWN_ROOT_SCHEMAS:
        raise RegistryError(f"unknown_source_schema: {manifest_path}: {schema or 'missing'}")


def _fleet_declaration_payload(manifest: dict[str, Any]) -> dict[str, Any]:
    public_config = manifest.get("public_config")
    return public_config if isinstance(public_config, dict) else manifest


def _fleet_declared_root_schema(manifest: dict[str, Any]) -> str:
    declaration = _fleet_declaration_payload(manifest)
    schema = declaration.get("schema_version")
    if isinstance(schema, str) and schema:
        return schema
    return _root_schema(manifest)


def _manifest_declared_adapter_key(manifest: dict[str, Any]) -> str | None:
    declaration = _fleet_declaration_payload(manifest)
    adapter_key = declaration.get("adapter_key")
    if isinstance(adapter_key, str) and adapter_key:
        return adapter_key
    adapter = declaration.get("adapter_or_harness")
    if isinstance(adapter, dict) and isinstance(adapter.get("name"), str) and adapter["name"]:
        return str(adapter["name"])
    return None


def _manifest_declared_adapter_version(manifest: dict[str, Any]) -> str | None:
    declaration = _fleet_declaration_payload(manifest)
    adapter_version = declaration.get("adapter_version")
    if isinstance(adapter_version, str) and adapter_version:
        return adapter_version
    adapter = declaration.get("adapter_or_harness")
    if isinstance(adapter, dict) and isinstance(adapter.get("version"), str) and adapter["version"]:
        return str(adapter["version"])
    return None


def _manifest_declared_profile(manifest: dict[str, Any]) -> str | None:
    profile = _fleet_declaration_payload(manifest).get("profile")
    if isinstance(profile, str) and profile:
        return profile
    if isinstance(profile, dict) and isinstance(profile.get("id"), str) and profile["id"]:
        return str(profile["id"])
    return None


def _legacy_runtime_adapter_for_schema(schema: str) -> str | None:
    for adapter_key, schemas in LEGACY_RUNTIME_ROOT_SCHEMAS.items():
        if schema in schemas:
            return adapter_key
    return None


def _validate_closed_adapter_profile(
    manifest_path: Path,
    manifest: dict[str, Any],
    adapters: dict[str, str],
    *,
    fail_on_unknown_source_schema: bool,
) -> None:
    if not fail_on_unknown_source_schema:
        return
    schema = _fleet_declared_root_schema(manifest)
    declared_adapter_key = _manifest_declared_adapter_key(manifest)
    declared_adapter_version = _manifest_declared_adapter_version(manifest)
    profile = _manifest_declared_profile(manifest)

    expected_fleet_adapter = FLEET_ADAPTER_BY_ROOT_SCHEMA.get(schema)
    if expected_fleet_adapter is not None:
        expected_version = adapters.get(expected_fleet_adapter) or REQUIRED_SCHEMA_ADAPTERS[expected_fleet_adapter]
        allowed_profiles = {FLEET_PROFILE, FLEET_DIAGNOSTIC_PROFILES[expected_fleet_adapter]}
        if (
            declared_adapter_key != expected_fleet_adapter
            or declared_adapter_version != expected_version
            or profile not in allowed_profiles
        ):
            raise RegistryError(
                "cross_profile_schema_adapter_mismatch: "
                f"{manifest_path}: root_schema={schema} expected_adapter={expected_fleet_adapter}"
            )
        return

    if declared_adapter_key in FLEET_ROOT_SCHEMAS:
        fleet_legacy_adapter = LEGACY_RUNTIME_ADAPTER_BY_FLEET_ADAPTER[declared_adapter_key]
        if schema in LEGACY_RUNTIME_ROOT_SCHEMAS[fleet_legacy_adapter]:
            family = "database" if declared_adapter_key == "database_fleet" else declared_adapter_key.removesuffix("_fleet")
            raise RegistryError(f"fleet_adapter_rejects_legacy_{family}_root: {manifest_path}: {schema}")
        raise RegistryError(f"cross_profile_schema_adapter_mismatch: {manifest_path}: {declared_adapter_key} cannot parse {schema or 'missing'}")

    legacy_root_adapter = _legacy_runtime_adapter_for_schema(schema)
    if legacy_root_adapter is not None and f"{legacy_root_adapter if legacy_root_adapter != 'db_pool' else 'database'}_fleet" in adapters:
        if declared_adapter_key == legacy_root_adapter and declared_adapter_version == adapters.get(legacy_root_adapter):
            if legacy_root_adapter == "deploy" and not isinstance(manifest.get("artifact_paths") or manifest.get("artifacts"), dict):
                raise RegistryError(f"fleet_adapter_rejects_legacy_deploy_root: {manifest_path}: {schema}")
            return
        if legacy_root_adapter == "deploy":
            raise RegistryError(f"fleet_adapter_rejects_legacy_deploy_root: {manifest_path}: {schema}")


def _validate_license(value: Any, *, context: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise RegistryError(f"{context} requires license object")
    return {
        "name": _require_string(value, "name", context=f"{context} license"),
        "url": _require_string(value, "url", context=f"{context} license"),
        "citation_text": _require_string(value, "citation_text", context=f"{context} license"),
        "redistribution_status": _require_string(value, "redistribution_status", context=f"{context} license"),
    }


def _validate_privacy(value: Any, *, context: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise RegistryError(f"{context} requires privacy object")
    review_status = _require_string(value, "review_status", context=f"{context} privacy")
    if review_status == "reviewed-local":
        reviewer_id = _require_string(value, "reviewer_id", context=f"{context} privacy")
        reviewed_at = _require_string(value, "reviewed_at", context=f"{context} privacy")
        redaction_status = _require_string(value, "redaction_status", context=f"{context} privacy")
    else:
        reviewer_id = str(value.get("reviewer_id") or "")
        reviewed_at = str(value.get("reviewed_at") or "")
        redaction_status = str(value.get("redaction_status") or "")
    return {
        "review_status": review_status,
        "reviewer_id": reviewer_id,
        "reviewed_at": reviewed_at,
        "redaction_status": redaction_status,
        "notes": _require_string(value, "notes", context=f"{context} privacy", allow_empty=True),
    }


def _resolve_ref(manifest_path: Path, value: Any) -> Path:
    raw_path = value.get("path") if isinstance(value, dict) else value
    path = Path(str(raw_path or ""))
    if not path.is_absolute():
        path = manifest_path.parent / path
    return path


def _artifact_entry(path: Path, *, expected_sha256: str | None = None, public_artifact: bool | None = None) -> dict[str, Any]:
    if not path.exists():
        raise RegistryError(f"artifact path is missing: {path}")
    actual_sha256 = _file_sha256(path)
    if expected_sha256 and expected_sha256 != actual_sha256:
        raise RegistryError(f"artifact sha256 mismatch for {path}")
    entry: dict[str, Any] = {"path": _normalize_path(path), "sha256": actual_sha256}
    if public_artifact is not None:
        entry["public_artifact"] = public_artifact
    return entry


def _artifact_hash_for_path(manifest: dict[str, Any], path: Path) -> str | None:
    hashes = manifest.get("artifact_hashes")
    if not isinstance(hashes, dict):
        return None
    value = hashes.get(path.name)
    return str(value) if isinstance(value, str) and value else None


def _artifact_paths(manifest_path: Path, manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_paths = manifest.get("artifact_paths") or manifest.get("artifacts") or {}
    if not isinstance(raw_paths, dict):
        return {}
    artifacts: dict[str, dict[str, Any]] = {}
    for key, value in raw_paths.items():
        if key in {"harness_manifest", "runtime_attestation"}:
            continue
        path = _resolve_ref(manifest_path, value)
        if not path.exists():
            raise RegistryError(f"artifact path is missing: {path}")
        public_artifact = False if "private" in str(key) or "ledger" in str(key) else None
        artifacts[str(key)] = _artifact_entry(path, expected_sha256=_artifact_hash_for_path(manifest, path), public_artifact=public_artifact)
        if str(key) in {"coverage", "actual_coverage"}:
            artifacts[str(key)]["actual_coverage"] = True
    return artifacts


def _content_hashes_from_artifacts(artifacts: dict[str, dict[str, Any]], manifest_path: Path) -> list[dict[str, str]]:
    ordered_keys = ["public_telemetry", "public_records", "coverage", "actual_coverage", "partitions", "pre_label_partitions"]
    hashes: list[dict[str, str]] = []
    seen: set[str] = set()
    for key in [*ordered_keys, *sorted(artifacts)]:
        artifact = artifacts.get(key)
        if not artifact:
            continue
        path = str(artifact["path"])
        if path in seen:
            continue
        seen.add(path)
        hashes.append({"path": path, "sha256": str(artifact["sha256"])})
    if hashes:
        return hashes
    return [{"path": _normalize_path(manifest_path), "sha256": _file_sha256(manifest_path)}]


def _license_from_metadata(manifest: dict[str, Any], source: dict[str, Any] | None, *, context: str) -> dict[str, Any]:
    value = manifest.get("license")
    if isinstance(value, dict):
        license_payload = dict(value)
    else:
        source = source or {}
        license_payload = {
            "name": str(source.get("license_name") or manifest.get("license_name") or "review-required"),
            "url": str(source.get("license_url") or manifest.get("license_url") or "https://example.invalid/review-required"),
            "citation_text": str(source.get("citation_text") or manifest.get("citation_text") or "review required before release counting"),
            "redistribution_status": str(source.get("redistribution_status") or manifest.get("redistribution_status") or "review-required"),
        }
    for key, fallback in (
        ("name", "review-required"),
        ("url", "https://example.invalid/review-required"),
        ("citation_text", "review required before release counting"),
        ("redistribution_status", "review-required"),
    ):
        if not license_payload.get(key):
            license_payload[key] = fallback
    return license_payload


def _privacy_from_metadata(manifest: dict[str, Any], source: dict[str, Any] | None, *, context: str) -> dict[str, Any]:
    value = manifest.get("privacy")
    if isinstance(value, dict):
        privacy_payload = dict(value)
    else:
        source = source or {}
        privacy_payload = {
            "review_status": str(source.get("privacy_review_status") or manifest.get("review_status") or "unreviewed"),
            "reviewer_id": str(source.get("reviewer_id") or manifest.get("reviewer_id") or ""),
            "reviewed_at": str(source.get("reviewed_at") or manifest.get("reviewed_at") or ""),
            "redaction_status": str(source.get("redaction_status") or manifest.get("review_redaction_status") or ""),
            "notes": str(source.get("privacy_notes") or ""),
        }
    privacy_payload.setdefault("review_status", "unreviewed")
    privacy_payload.setdefault("reviewer_id", "")
    privacy_payload.setdefault("reviewed_at", "")
    privacy_payload.setdefault("redaction_status", "")
    privacy_payload.setdefault("notes", "")
    if source and isinstance(source.get("redaction_decisions"), list):
        privacy_payload["redaction_decisions"] = list(source["redaction_decisions"])
    return privacy_payload


def _command_from_manifest(adapter_key: str, manifest_path: Path, manifest: dict[str, Any]) -> list[str]:
    command = manifest.get("canonical_command_argv") or manifest.get("command_argv")
    if isinstance(command, list) and command and all(isinstance(item, str) and item for item in command):
        return list(command)
    return [adapter_key, str(manifest_path)]


def _source_with_hash(source: dict[str, Any]) -> dict[str, Any]:
    source["provenance_sha256"] = _json_sha256(source)
    return source


def _read_jsonl_objects(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parsed = json.loads(line)
        if isinstance(parsed, dict):
            rows.append(parsed)
    return rows


def _coverage_interval_ids(artifacts: dict[str, dict[str, Any]], source_key: str) -> list[str]:
    coverage = artifacts.get("coverage") or artifacts.get("actual_coverage")
    if not coverage:
        return []
    path = Path(str(coverage["path"]))
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return [f"{source_key}:coverage:{coverage['sha256']}"]
    intervals = payload.get("observed_intervals") or payload.get("coverage_intervals")
    if isinstance(intervals, dict):
        return [f"{source_key}:{service}:{index}" for service, values in sorted(intervals.items()) if isinstance(values, list) for index, _ in enumerate(values)]
    if isinstance(intervals, list):
        return [f"{source_key}:coverage:{index}" for index, _ in enumerate(intervals)]
    return [f"{source_key}:coverage:{coverage['sha256']}"]


def _source_bindings(artifacts: dict[str, dict[str, Any]], source_key: str) -> dict[str, Any]:
    ledger = (
        artifacts.get("private_injection_ledger")
        or artifacts.get("private_saturation_ledger")
        or artifacts.get("private_label_ledger")
        or artifacts.get("private_ledger")
    )
    partitions = artifacts.get("partitions") or artifacts.get("pre_label_partitions")
    coverage = artifacts.get("coverage") or artifacts.get("actual_coverage")
    bindings: dict[str, Any] = {
        "coverage_interval_ids": _coverage_interval_ids(artifacts, source_key),
    }
    if ledger:
        bindings["private_ledger_ref"] = {"path": ledger["path"], "sha256": ledger["sha256"], "public_artifact": bool(ledger.get("public_artifact", False))}
    if partitions:
        bindings["pre_label_partitions_ref"] = {"path": partitions["path"], "sha256": partitions["sha256"]}
    if coverage:
        bindings["coverage_ref"] = {"path": coverage["path"], "sha256": coverage["sha256"], "actual_coverage": True}
    return bindings


def _p32_sources(manifest_path: Path, manifest: dict[str, Any], adapter_version: str) -> list[dict[str, Any]]:
    sources = _require_list(manifest, "sources", context=f"source manifest {manifest_path}")
    normalized: list[dict[str, Any]] = []
    command_argv = _command_from_manifest("p32", manifest_path, manifest)
    for index, raw in enumerate(sources):
        if not isinstance(raw, dict):
            raise RegistryError(f"source manifest {manifest_path} sources[{index}] must be an object")
        source_key = _require_string(raw, "id", context=f"source manifest {manifest_path} sources[{index}]")
        source_path = _resolve_ref(manifest_path, raw.get("path"))
        content_hashes = [_artifact_entry(source_path)] if source_path.exists() else [{"path": _normalize_path(manifest_path), "sha256": _file_sha256(manifest_path)}]
        normalized.append(
            _source_with_hash(
                {
                    "source_key": source_key,
                    "source_system": str(raw.get("source") or "p32"),
                    "source_dataset": str(manifest.get("title") or source_key),
                    "source_family": UNSUPPORTED_FAMILY,
                    "source_family_candidate": UNSUPPORTED_FAMILY,
                    "source_manifest_path": _normalize_path(manifest_path),
                    "source_manifest_sha256": _file_sha256(manifest_path),
                    "source_content_hashes": [{"path": item["path"], "sha256": item["sha256"]} for item in content_hashes],
                    "adapter_or_harness": {"name": "p32", "version": adapter_version, "command_argv": command_argv, "command_argv_sha256": _json_sha256(command_argv)},
                    "created_at": str(manifest.get("created_at") or ""),
                    "license": _license_from_metadata(manifest, raw, context=f"source manifest {manifest_path}"),
                    "privacy": _privacy_from_metadata({"review_status": "unreviewed"}, raw, context=f"source manifest {manifest_path}"),
                    "root_schema_version": "p32-replay-pack.v1",
                    "producer_metadata": {"expected_risks": raw.get("expected_risks", [])},
                }
            )
        )
    return normalized


def _p41_sources(manifest_path: Path, manifest: dict[str, Any], adapter_version: str) -> list[dict[str, Any]]:
    sources = _require_list(manifest, "sources", context=f"source manifest {manifest_path}")
    normalized: list[dict[str, Any]] = []
    command_argv = _command_from_manifest("p41", manifest_path, manifest)
    for index, raw in enumerate(sources):
        if not isinstance(raw, dict):
            raise RegistryError(f"source manifest {manifest_path} sources[{index}] must be an object")
        source_key = _require_string(raw, "id", context=f"source manifest {manifest_path} sources[{index}]")
        source_path = _resolve_ref(manifest_path, raw.get("path"))
        content_hashes = [_artifact_entry(source_path)] if source_path.exists() else [{"path": _normalize_path(manifest_path), "sha256": _file_sha256(manifest_path)}]
        normalized.append(
            _source_with_hash(
                {
                    "source_key": source_key,
                    "source_system": "p41",
                    "source_dataset": str(raw.get("family") or source_key),
                    "source_family": UNSUPPORTED_FAMILY,
                    "source_family_candidate": UNSUPPORTED_FAMILY,
                    "source_manifest_path": _normalize_path(manifest_path),
                    "source_manifest_sha256": _file_sha256(manifest_path),
                    "source_content_hashes": [{"path": item["path"], "sha256": item["sha256"]} for item in content_hashes],
                    "adapter_or_harness": {"name": "p41", "version": adapter_version, "command_argv": command_argv, "command_argv_sha256": _json_sha256(command_argv)},
                    "created_at": str(manifest.get("created_at") or ""),
                    "license": _license_from_metadata(manifest, raw, context=f"source manifest {manifest_path}"),
                    "privacy": _privacy_from_metadata({"review_status": "unreviewed"}, raw, context=f"source manifest {manifest_path}"),
                    "root_schema_version": "p41-raw-sources-v1",
                    "producer_metadata": {"expected_labels": raw.get("expected_labels", []), "raw_family": raw.get("family")},
                }
            )
        )
    return normalized


def _p44_sources(manifest_path: Path, manifest: dict[str, Any], adapter_version: str) -> list[dict[str, Any]]:
    raw_sources = manifest.get("raw_sources") if isinstance(manifest.get("raw_sources"), list) else manifest.get("sources")
    if not isinstance(raw_sources, list):
        raise RegistryError(f"source manifest {manifest_path} requires raw_sources or sources")
    reviewed_records = [item for item in manifest.get("reviewed_records", []) if isinstance(item, dict)]
    command_argv = _command_from_manifest("p44", manifest_path, manifest)
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_sources):
        if not isinstance(raw, dict):
            raise RegistryError(f"source manifest {manifest_path} raw_sources[{index}] must be an object")
        source_key = str(raw.get("source_key") or raw.get("source_id") or f"p44:source:{index}")
        mapping_raw = raw.get("family_proxy_mapping")
        mapping: dict[str, Any] = dict(mapping_raw) if isinstance(mapping_raw, dict) else {}
        family = str(mapping.get("family") or raw.get("family") or UNSUPPORTED_FAMILY)
        if mapping.get("mapping_review_status") not in {None, "reviewed_supported"}:
            family = UNSUPPORTED_FAMILY
        if family not in SUPPORTED_FAMILIES:
            family = UNSUPPORTED_FAMILY
        content_hashes: list[dict[str, str]] = []
        local_path_value = raw.get("local_materialized_path") or raw.get("path")
        if local_path_value:
            local_path = _resolve_ref(manifest_path, local_path_value)
            if local_path.exists():
                expected_hash = str(raw.get("local_source_hash") or raw.get("source_content_hash") or raw.get("expected_sha256") or "")
                entry = _artifact_entry(local_path, expected_sha256=expected_hash or None)
                content_hashes.append({"path": entry["path"], "sha256": entry["sha256"]})
        if not content_hashes:
            content_hashes = [{"path": _normalize_path(manifest_path), "sha256": _file_sha256(manifest_path)}]
        windows = [
            {
                "source_window_id": str(record.get("source_window_id") or source_key),
                "pre_label_partition_id": str(record.get("pre_label_partition_id") or record.get("pre_label_partition") or "unpartitioned"),
                "materialized_record_sha256": str(record.get("materialized_record_hash") or ""),
            }
            for record in reviewed_records
            if str(record.get("source_key") or source_key) == source_key
        ]
        private_ref = manifest.get("private_ledger_ref") if isinstance(manifest.get("private_ledger_ref"), dict) else None
        partition_ref = manifest.get("pre_label_partitions_path") if isinstance(manifest.get("pre_label_partitions_path"), dict) else None
        source = {
            "source_key": source_key,
            "source_system": "p44",
            "source_dataset": str(raw.get("source_dataset") or raw.get("source_id") or "p44-reviewed-local"),
            "source_family": family,
            "source_family_candidate": family,
            "source_manifest_path": _normalize_path(manifest_path),
            "source_manifest_sha256": _file_sha256(manifest_path),
            "source_content_hashes": sorted(content_hashes, key=lambda item: (item["path"], item["sha256"])),
            "adapter_or_harness": {"name": "p44", "version": adapter_version, "command_argv": command_argv, "command_argv_sha256": _json_sha256(command_argv)},
            "created_at": str(manifest.get("created_at") or ""),
            "license": _license_from_metadata(manifest, raw, context=f"source manifest {manifest_path}"),
            "privacy": _privacy_from_metadata(manifest, raw, context=f"source manifest {manifest_path}"),
            "root_schema_version": str(manifest.get("schema_version")),
            "eligibility_windows": windows,
            "family_proxy_mapping": mapping,
        }
        if private_ref:
            private_path = _resolve_ref(manifest_path, private_ref)
            source["private_ledger_ref"] = _artifact_entry(private_path, expected_sha256=str(private_ref.get("sha256") or ""), public_artifact=bool(private_ref.get("public_artifact", False)))
        if partition_ref:
            partition_path = _resolve_ref(manifest_path, partition_ref)
            source["pre_label_partitions_ref"] = _artifact_entry(partition_path, expected_sha256=str(partition_ref.get("sha256") or ""))
        normalized.append(_source_with_hash(source))
    return normalized


def _dejavu_source(manifest_path: Path, manifest: dict[str, Any], adapter_version: str) -> list[dict[str, Any]]:
    command_argv = _command_from_manifest("dejavu_a1", manifest_path, manifest)
    family = str(manifest.get("source_insufficiency", {}).get("family") or "database") if isinstance(manifest.get("source_insufficiency"), dict) else "database"
    source = {
        "source_key": "dejavu-a1-reviewed-local",
        "source_system": "dejavu_a1",
        "source_dataset": "dejavu-a1",
        "source_family": family if family in SUPPORTED_FAMILIES else UNSUPPORTED_FAMILY,
        "source_family_candidate": family if family in SUPPORTED_FAMILIES else UNSUPPORTED_FAMILY,
        "source_manifest_path": _normalize_path(manifest_path),
        "source_manifest_sha256": _file_sha256(manifest_path),
        "source_content_hashes": [{"path": _normalize_path(manifest_path), "sha256": _file_sha256(manifest_path)}],
        "source_hashes": manifest.get("source_hashes", {}),
        "adapter_or_harness": {"name": "dejavu_a1", "version": adapter_version, "command_argv": command_argv, "command_argv_sha256": _json_sha256(command_argv)},
        "created_at": str(manifest.get("created_at") or ""),
        "license": _license_from_metadata(manifest, None, context=f"source manifest {manifest_path}"),
        "privacy": _privacy_from_metadata(manifest, None, context=f"source manifest {manifest_path}"),
        "root_schema_version": "p105.dejavu_a1.reviewed_local_manifest.v1",
        "noncounting_reason": "source_insufficient" if isinstance(manifest.get("source_insufficiency"), dict) else None,
        "source_insufficiency": manifest.get("source_insufficiency", {}),
    }
    return [_source_with_hash(source)]


def _runtime_source(manifest_path: Path, manifest: dict[str, Any], adapter_key: str, adapter_version: str) -> list[dict[str, Any]]:
    artifacts = _artifact_paths(manifest_path, manifest)
    required_artifacts = {
        "public_telemetry": artifacts.get("public_telemetry"),
        "coverage": artifacts.get("coverage") or artifacts.get("actual_coverage"),
        "partitions": artifacts.get("partitions") or artifacts.get("pre_label_partitions"),
        "private_ledger": (
            artifacts.get("private_injection_ledger")
            or artifacts.get("private_saturation_ledger")
            or artifacts.get("private_label_ledger")
            or artifacts.get("private_ledger")
        ),
    }
    missing_artifacts = sorted(key for key, value in required_artifacts.items() if value is None)
    if missing_artifacts:
        raise RegistryError(f"runtime source {adapter_key} is missing required artifacts: {','.join(missing_artifacts)}")
    command_argv = _command_from_manifest(adapter_key, manifest_path, manifest)
    family = str(manifest.get("source_family") or manifest.get("family") or RUNTIME_FAMILY_BY_ADAPTER.get(adapter_key, UNSUPPORTED_FAMILY))
    if family not in SUPPORTED_FAMILIES:
        family = UNSUPPORTED_FAMILY
    default_key = {"db_pool": "p105-db-pool", "queue": "p105-queue", "deploy": "p105-deploy"}.get(adapter_key, manifest_path.stem)
    source_key = str(manifest.get("source_key") or default_key)
    windows: list[dict[str, Any]] = []
    public_telemetry = artifacts.get("public_telemetry")
    if public_telemetry:
        for row in _read_jsonl_objects(Path(str(public_telemetry["path"]))):
            windows.append(
                {
                    "source_window_id": str(row.get("source_window_id") or source_key),
                    "pre_label_partition_id": str(row.get("partition_id") or row.get("pre_label_partition") or "unpartitioned"),
                    "coverage_seconds": int(row.get("coverage_bucket_seconds") or 0),
                }
            )
    if not windows:
        raise RegistryError(f"runtime source {adapter_key} public telemetry has no source windows")
    source = {
        "source_key": source_key,
        "source_system": adapter_key,
        "source_dataset": str(manifest.get("program_version") or source_key),
        "source_family": family,
        "source_family_candidate": family,
        "source_manifest_path": _normalize_path(manifest_path),
        "source_manifest_sha256": _file_sha256(manifest_path),
        "source_content_hashes": _content_hashes_from_artifacts(artifacts, manifest_path),
        "source_artifacts": artifacts,
        "adapter_or_harness": {"name": adapter_key, "version": adapter_version, "command_argv": command_argv, "command_argv_sha256": _json_sha256(command_argv)},
        "created_at": str(manifest.get("created_at") or ""),
        "license": _license_from_metadata(manifest, None, context=f"source manifest {manifest_path}"),
        "privacy": _privacy_from_metadata(manifest, None, context=f"source manifest {manifest_path}"),
        "root_schema_version": _root_schema(manifest),
        "runtime_attestation": manifest.get("runtime_attestation", {}),
        "authority": manifest.get("authority", {}),
        "eligibility_windows": windows,
        **_source_bindings(artifacts, source_key),
    }
    return [_source_with_hash(source)]


def _load_decisions(ledger_path: Path) -> tuple[str, dict[str, dict[str, Any]]]:
    ledger = _read_json(ledger_path, "review ledger")
    if ledger.get("schema_version") != LEDGER_SCHEMA_VERSION:
        raise RegistryError(f"review ledger schema_version must be {LEDGER_SCHEMA_VERSION}")
    decisions_raw = _require_list(ledger, "decisions", context="review ledger")
    decisions: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(decisions_raw):
        if not isinstance(item, dict):
            raise RegistryError(f"review ledger decisions[{index}] must be an object")
        source_key = _require_string(item, "source_key", context=f"review ledger decisions[{index}]")
        if source_key in decisions:
            raise RegistryError(f"review ledger has duplicate source_key decision: {source_key}")
        for key in (
            "reviewer_id",
            "reviewed_at",
            "decision",
            "license_decision",
            "privacy_decision",
            "family_authority_decision",
            "source_manifest_sha256",
            "review_signature_sha256",
        ):
            _require_string(item, key, context=f"review ledger decisions[{index}]")
        decisions[source_key] = item
    return _file_sha256(ledger_path), decisions


def _is_approved(decision: dict[str, Any] | None) -> bool:
    return bool(
        decision
        and decision.get("decision") == "approved"
        and decision.get("license_decision") == "approved"
        and decision.get("privacy_decision") == "approved"
        and decision.get("family_authority_decision") == "approved"
    )


def _noncounting_reason(source_key: str, family: str, decision: dict[str, Any] | None, reviewed: bool) -> str | None:
    if not reviewed or decision is None:
        return "unreviewed_source"
    if decision.get("license_decision") != "approved":
        return "license_rejected"
    if decision.get("privacy_decision") != "approved":
        return "privacy_rejected"
    if not _is_approved(decision):
        return "predicate_unmapped"
    if family == UNSUPPORTED_FAMILY:
        if "parser" in source_key and "failed" in source_key:
            return "parser_failed"
        return "source_insufficient"
    return None


def _registry_source(manifest_path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    context = f"source manifest {manifest_path}"
    if manifest.get("schema_version") != SOURCE_MANIFEST_SCHEMA_VERSION:
        raise RegistryError(f"{context} schema_version must be {SOURCE_MANIFEST_SCHEMA_VERSION}")
    missing_metadata: list[str] = []
    if not isinstance(manifest.get("command_argv"), list):
        missing_metadata.append("command_argv")
    privacy_value = manifest.get("privacy")
    if (
        not isinstance(privacy_value, dict)
        or (privacy_value.get("review_status") == "reviewed-local" and not privacy_value.get("reviewer_id"))
    ):
        missing_metadata.append("reviewer_id")
    if missing_metadata:
        raise RegistryError(f"{context} missing required provenance/reviewer metadata: {', '.join(missing_metadata)}")
    source_key = _require_string(manifest, "source_key", context=context)
    family = _require_string(manifest, "source_family_candidate", context=context)
    if family not in SUPPORTED_FAMILIES and family != UNSUPPORTED_FAMILY:
        family = UNSUPPORTED_FAMILY
    source = {
        "source_key": source_key,
        "source_system": _require_string(manifest, "source_system", context=context),
        "source_dataset": _require_string(manifest, "source_dataset", context=context),
        "source_family_candidate": family,
        "source_manifest_path": _normalize_path(manifest_path),
        "source_manifest_sha256": _file_sha256(manifest_path),
        "source_content_hashes": _validate_content_hashes(manifest.get("source_content_hashes"), context=context),
        "adapter_or_harness": _validate_adapter(manifest.get("adapter_or_harness"), context=context),
        "created_at": _require_string(manifest, "created_at", context=context),
        "license": _validate_license(manifest.get("license"), context=context),
        "privacy": _validate_privacy(manifest.get("privacy"), context=context),
    }
    source["provenance_sha256"] = _json_sha256(source)
    _validate_command_argv(manifest.get("command_argv"), context=context)
    return source


def _adapter_key_for_manifest(manifest_path: Path, manifest: dict[str, Any]) -> str:
    schema = _root_schema(manifest)
    name = manifest_path.name
    if schema in FLEET_ADAPTER_BY_ROOT_SCHEMA:
        return FLEET_ADAPTER_BY_ROOT_SCHEMA[schema]
    if "database-fleet" in name or "database_fleet" in name:
        return "database_fleet"
    if "queue-fleet" in name or "queue_fleet" in name:
        return "queue_fleet"
    if "deploy-fleet" in name or "deploy_fleet" in name:
        return "deploy_fleet"
    if schema == "p32-replay-pack.v1" or "p32" in name:
        return "p32"
    if schema == "p41-raw-sources-v1" or "p41" in name:
        return "p41"
    if "dejavu" in schema or "dejavu" in name:
        return "dejavu_a1"
    if "database.pool" in schema or "db-pool" in name or "db_pool" in name:
        return "db_pool"
    if "queue" in schema or "queue" in name:
        return "queue"
    if "deploy" in schema or "deploy" in name:
        return "deploy"
    if "p44" in schema or "p44" in name:
        return "p44"
    return "unknown"


def _generic_registry_source(manifest_path: Path, manifest: dict[str, Any], adapters: dict[str, str], *, fail_on_unknown_source_schema: bool) -> dict[str, Any]:
    context = f"source manifest {manifest_path}"
    adapter_key = _adapter_key_for_manifest(manifest_path, manifest)
    adapter_version = adapters.get(adapter_key)
    if not adapter_version and fail_on_unknown_source_schema:
        raise RegistryError(f"unknown_source_schema: missing adapter mapping for {adapter_key}")
    if not adapter_version:
        adapter_version = f"compatibility-inferred:{adapter_key}"
    schema = _root_schema(manifest)
    source_key = str(manifest.get("source_key") or manifest.get("id") or manifest.get("source_id") or manifest_path.stem)
    family = str(manifest.get("source_family_candidate") or manifest.get("family") or UNSUPPORTED_FAMILY)
    if family not in SUPPORTED_FAMILIES:
        family = UNSUPPORTED_FAMILY
    command_argv = [adapter_key, str(manifest_path)]
    source = {
        "source_key": source_key,
        "source_system": adapter_key,
        "source_dataset": str(manifest.get("source_dataset") or manifest.get("title") or manifest_path.stem),
        "source_family_candidate": family,
        "source_manifest_path": _normalize_path(manifest_path),
        "source_manifest_sha256": _file_sha256(manifest_path),
        "source_content_hashes": [{"path": _normalize_path(manifest_path), "sha256": _file_sha256(manifest_path)}],
        "adapter_or_harness": {
            "name": adapter_key,
            "version": adapter_version,
            "command_argv": command_argv,
            "command_argv_sha256": _json_sha256(command_argv),
        },
        "created_at": str(manifest.get("created_at") or ""),
        "license": {
            "name": str(manifest.get("license_name") or "review-required"),
            "url": str(manifest.get("license_url") or "https://example.invalid/review-required"),
            "citation_text": str(manifest.get("citation_text") or "review required before release counting"),
            "redistribution_status": str(manifest.get("redistribution_status") or "review-required"),
        },
        "privacy": {
            "review_status": str(manifest.get("review_status") or "unreviewed"),
            "reviewer_id": str(manifest.get("reviewer_id") or ""),
            "reviewed_at": str(manifest.get("reviewed_at") or ""),
            "redaction_status": str(manifest.get("redaction_status") or ""),
            "notes": f"normalized by explicit schema adapter {adapter_version} from root schema {schema}",
        },
        "root_schema_version": schema,
    }
    if not schema:
        raise RegistryError(f"{context} missing root schema")
    source["provenance_sha256"] = _json_sha256(source)
    return source


def _adapted_registry_sources(manifest_path: Path, manifest: dict[str, Any], adapters: dict[str, str], *, fail_on_unknown_source_schema: bool) -> list[dict[str, Any]]:
    adapter_key = _adapter_key_for_manifest(manifest_path, manifest)
    adapter_version = adapters.get(adapter_key)
    if not adapter_version and fail_on_unknown_source_schema:
        raise RegistryError(f"unknown_source_schema: missing adapter mapping for {adapter_key}")
    if not adapter_version:
        adapter_version = f"compatibility-inferred:{adapter_key}"
    if adapter_key == "p32":
        return _p32_sources(manifest_path, manifest, adapter_version)
    if adapter_key == "p41":
        return _p41_sources(manifest_path, manifest, adapter_version)
    if adapter_key == "p44":
        return _p44_sources(manifest_path, manifest, adapter_version)
    if adapter_key == "dejavu_a1":
        return _dejavu_source(manifest_path, manifest, adapter_version)
    if adapter_key in {"db_pool", "queue", "deploy", "database_fleet", "queue_fleet", "deploy_fleet"}:
        return _runtime_source(manifest_path, manifest, adapter_key, adapter_version)
    return [_generic_registry_source(manifest_path, manifest, adapters, fail_on_unknown_source_schema=fail_on_unknown_source_schema)]


def _registry_sources_for_manifest(
    manifest_path: Path,
    manifest: dict[str, Any],
    adapters: dict[str, str],
    *,
    fail_on_unknown_source_schema: bool,
) -> list[dict[str, Any]]:
    if manifest.get("schema_version") == SOURCE_MANIFEST_SCHEMA_VERSION:
        return [_registry_source(manifest_path, manifest)]
    return _adapted_registry_sources(manifest_path, manifest, adapters, fail_on_unknown_source_schema=fail_on_unknown_source_schema)


def _eligibility_entry(source: dict[str, Any], decision: dict[str, Any] | None, window: dict[str, Any] | None = None) -> dict[str, Any]:
    window = window or {}
    privacy = source["privacy"]
    reviewed = _is_approved(decision) or (
        privacy["review_status"] == "reviewed-local" and bool(privacy["reviewer_id"]) and bool(privacy["reviewed_at"])
    )
    family = str(source["source_family_candidate"])
    reason = _noncounting_reason(str(source["source_key"]), family, decision, reviewed)
    if reason is None and source.get("noncounting_reason"):
        reason = str(source["noncounting_reason"])
    eligible = reason is None and family in SUPPORTED_FAMILIES
    family_candidate = family if eligible else UNSUPPORTED_FAMILY
    private_ledger_raw = source.get("private_ledger_ref")
    private_ledger_ref: dict[str, Any] = dict(private_ledger_raw) if isinstance(private_ledger_raw, dict) else {}
    coverage_interval_ids = window.get("coverage_interval_ids") or source.get("coverage_interval_ids") or []
    materialized_record_sha256 = str(window.get("materialized_record_sha256") or source["provenance_sha256"])
    entry = {
        "source_key": source["source_key"],
        "source_window_id": str(window.get("source_window_id") or source["source_key"]),
        "source_manifest_sha256": source["source_manifest_sha256"],
        "materialized_record_sha256": materialized_record_sha256,
        "pre_label_partition_id": str(window.get("pre_label_partition_id") or "unpartitioned"),
        "family_candidate": family_candidate,
        "family_authority_source": "reviewed_source_registry",
        "eligible_for_release_floor": eligible,
        "unsupported_family_reason": reason,
        "coverage_interval_ids": list(coverage_interval_ids) if isinstance(coverage_interval_ids, list) else [],
        "private_ledger_path": str(private_ledger_ref.get("path") or ""),
        "private_ledger_sha256": str(private_ledger_ref.get("sha256") or ""),
        "label_join_phase": "after_sampling_and_partition",
        "adapter_or_parser_version": source["adapter_or_harness"]["version"],
        "privacy_license_registry_sha256": source["provenance_sha256"],
    }
    if entry["unsupported_family_reason"] is not None and entry["unsupported_family_reason"] not in ALLOWED_UNSUPPORTED_REASONS:
        raise RegistryError(f"unsupported_family_reason is not allowed: {entry['unsupported_family_reason']}")
    entry["provenance_sha256"] = _json_sha256(entry)
    return entry


def _eligibility_entries(source: dict[str, Any], decision: dict[str, Any] | None) -> list[dict[str, Any]]:
    windows = source.get("eligibility_windows")
    if isinstance(windows, list) and windows:
        return [_eligibility_entry(source, decision, window if isinstance(window, dict) else {}) for window in windows]
    return [_eligibility_entry(source, decision)]


def build_registry(
    *,
    candidate_manifests: list[Path],
    review_ledger: Path,
    output_registry: Path,
    output_eligibility: Path,
    created_at: str,
    schema_version: str,
    command_argv: list[str],
    fail_on_unreviewed_counting_source: bool,
    schema_adapters: dict[str, str] | None = None,
    fail_on_unknown_source_schema: bool = False,
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    if schema_version != REGISTRY_SCHEMA_VERSION:
        raise RegistryError(f"schema_version must be {REGISTRY_SCHEMA_VERSION}")
    adapters = dict(schema_adapters or {})
    required_adapter_keys = set(REQUIRED_SCHEMA_ADAPTERS) - set(FLEET_ROOT_SCHEMAS)
    for candidate_manifest in candidate_manifests:
        preview = _read_json(candidate_manifest, "source manifest")
        fleet_adapter = FLEET_ADAPTER_BY_ROOT_SCHEMA.get(_root_schema(preview))
        if fleet_adapter is not None:
            required_adapter_keys.add(fleet_adapter)
    _validate_schema_adapters(
        adapters,
        fail_on_unknown_source_schema=fail_on_unknown_source_schema,
        required_keys=required_adapter_keys,
    )
    ledger_sha256, decisions = _load_decisions(review_ledger)
    errors: list[str] = []
    sources: list[dict[str, Any]] = []
    entries: list[dict[str, Any]] = []

    for manifest_path in candidate_manifests:
        manifest = _read_json(manifest_path, "source manifest")
        _validate_known_root_schema(manifest_path, manifest, fail_on_unknown_source_schema=fail_on_unknown_source_schema)
        _validate_closed_adapter_profile(
            manifest_path,
            manifest,
            adapters,
            fail_on_unknown_source_schema=fail_on_unknown_source_schema,
        )
        for source in _registry_sources_for_manifest(
            manifest_path,
            manifest,
            adapters,
            fail_on_unknown_source_schema=fail_on_unknown_source_schema,
        ):
            source_key = str(source["source_key"])
            decision = decisions.get(source_key)
            if decision is not None and decision["source_manifest_sha256"] != source["source_manifest_sha256"]:
                raise RegistryError(f"source manifest hash mismatch for {source_key}: reviewed metadata was tampered")
            sources.append(source)
            source_entries = _eligibility_entries(source, decision)
            entries.extend(source_entries)
            if fail_on_unreviewed_counting_source and any(entry["unsupported_family_reason"] == "unreviewed_source" for entry in source_entries):
                errors.append(f"{source_key}: unreviewed source is unsupported_family and cannot count")

    command_hash = _json_sha256(command_argv)
    sources.sort(key=lambda item: str(item["source_key"]))
    entries.sort(key=lambda item: (str(item["source_key"]), str(item["source_window_id"])))
    registry: dict[str, Any] = {
        "schema_version": schema_version,
        "created_at": created_at,
        "command_argv": command_argv,
        "command_argv_sha256": command_hash,
        "review_ledger_path": _normalize_path(review_ledger),
        "review_ledger_sha256": ledger_sha256,
        "schema_adapters": dict(sorted(adapters.items())),
        "sources": sources,
    }
    registry["registry_sha256"] = _json_sha256(registry)
    eligibility: dict[str, Any] = {
        "schema_version": ELIGIBILITY_SCHEMA_VERSION,
        "created_at": created_at,
        "command_argv": command_argv,
        "command_argv_sha256": command_hash,
        "registry_sha256": registry["registry_sha256"],
        "review_ledger_sha256": ledger_sha256,
        "schema_adapters": dict(sorted(adapters.items())),
        "entries": entries,
        "output_registry_path": _normalize_path(output_registry),
        "output_eligibility_path": _normalize_path(output_eligibility),
    }
    eligibility["eligibility_sha256"] = _json_sha256(eligibility)
    return registry, eligibility, errors


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build P105 reviewed source registry and eligibility manifest")
    parser.add_argument("--candidate-manifest", action="append", required=True, type=Path)
    parser.add_argument("--review-ledger", required=True, type=Path)
    parser.add_argument("--output-registry", required=True, type=Path)
    parser.add_argument("--output-eligibility", required=True, type=Path)
    parser.add_argument("--created-at", required=True)
    parser.add_argument("--schema-version", required=True)
    parser.add_argument("--schema-adapter", action="append", default=[])
    parser.add_argument("--fail-on-unknown-source-schema", action="store_true")
    parser.add_argument("--fail-on-unreviewed-counting-source", action="store_true")
    args = parser.parse_args(argv)

    command_argv = [sys.executable, str(Path(__file__)), *(argv if argv is not None else sys.argv[1:])]
    try:
        schema_adapters = _parse_schema_adapters(args.schema_adapter)
        registry, eligibility, errors = build_registry(
            candidate_manifests=args.candidate_manifest,
            review_ledger=args.review_ledger,
            output_registry=args.output_registry,
            output_eligibility=args.output_eligibility,
            created_at=args.created_at,
            schema_version=args.schema_version,
            command_argv=command_argv,
            fail_on_unreviewed_counting_source=args.fail_on_unreviewed_counting_source,
            schema_adapters=schema_adapters,
            fail_on_unknown_source_schema=args.fail_on_unknown_source_schema,
        )
    except RegistryError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    _write_json(args.output_registry, registry)
    _write_json(args.output_eligibility, eligibility)
    if errors:
        print("; ".join(errors), file=sys.stderr)
        return 1
    print(f"Wrote {args.output_registry}")
    print(f"Wrote {args.output_eligibility}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
