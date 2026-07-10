from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

QUEUE_PROVENANCE = "p105-queue-provenance-hashes.json"
DEPLOY_PROVENANCE = "p105-deploy-provenance-hashes.json"
DB_POOL_PROVENANCE = "p105-db-pool-provenance-hashes.json"
VERIFIER_ID = "scripts/verify_p105_source_expansion_artifacts.py"
SOURCE_RUNTIME_RECEIPT_SCHEMA = "p105.source-runtime-qualification.v1"
RUN_ENVELOPE_SCHEMA = "p105.source-runtime-run-envelope.v1"
RELEASE_VERIFICATION_SCHEMA = "p105.release-verification.v1"
RELEASE_ROWS_ARTIFACT = "p105-release-qualified-rows.json"
RELEASE_SOURCE_MANIFEST = "p105-source-manifest.json"
RELEASE_PREFLIGHT = "p105-source-availability-preflight.json"
REQUIRED_RELEASE_SOURCE_ENTRIES = ("dejavu_a1", "db_pool", "queue", "deploy")
EXPECTED_RELEASE_ZERO_AUTHORITY = {
    "auth_enabled": False,
    "production_mutation_enabled": False,
    "action_authority": False,
    "remediation_execution_enabled": False,
    "default_external_model_calls": 0,
}
EXPECTED_RUNTIME_KIND_BY_SOURCE = {
    "db_pool": "actual_sqlite_pool",
    "deploy": "actual_threading_http_server",
    "queue": "actual_rabbitmq_docker",
}
RAW_EVIDENCE_KEYS = {
    "actual_rabbitmq_docker": ("container_id", "docker_network_name", "rabbitmq_management_observed", "broker_observation"),
    "actual_sqlite_pool": ("sqlite_connection_observations", "sql_operation_evidence", "monotonic_started_ns"),
    "actual_threading_http_server": ("loopback_port", "thread_id", "handler_observation", "monotonic_started_ns"),
}
FORBIDDEN_SOURCE_COUNTING_KEYS = {"verified_release_counting", "release_counting_allowed", "counting_rows", "counting_coverage_seconds"}


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} is not a JSON object")
    return payload


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _flatten_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            keys.add(str(key))
            keys.update(_flatten_keys(nested))
    elif isinstance(value, list):
        for nested in value:
            keys.update(_flatten_keys(nested))
    return keys


def _runtime_attestation(manifest: dict[str, Any], raw_attestation: dict[str, Any] | None) -> dict[str, Any]:
    manifest_attestation = manifest.get("runtime_attestation")
    if isinstance(manifest_attestation, dict):
        return manifest_attestation
    if raw_attestation is None:
        return {}
    raw_nested = raw_attestation.get("runtime_attestation")
    if isinstance(raw_nested, dict):
        return raw_nested
    return raw_attestation


def _raw_evidence_present(raw_attestation: dict[str, Any], runtime_kind: str) -> bool:
    flattened = _flatten_keys(raw_attestation)
    required_keys = RAW_EVIDENCE_KEYS.get(runtime_kind, ())
    return any(key in flattened for key in required_keys)


def _provenance_name(kind: str, manifest: dict[str, Any] | None = None) -> str:
    if kind == "db_pool":
        default = DB_POOL_PROVENANCE
    elif kind == "queue":
        default = QUEUE_PROVENANCE
    else:
        default = DEPLOY_PROVENANCE
    if manifest is None:
        return default
    artifact_paths = manifest.get("artifact_paths")
    if isinstance(artifact_paths, dict) and isinstance(artifact_paths.get("provenance_hashes"), str):
        return str(artifact_paths["provenance_hashes"])
    artifacts = manifest.get("artifacts")
    if isinstance(artifacts, dict) and isinstance(artifacts.get("provenance_hashes"), str):
        return str(artifacts["provenance_hashes"])
    return default


def _read_manifest_and_provenance(manifest_path: Path, *, kind: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    try:
        manifest = _read_json(manifest_path)
    except (OSError, json.JSONDecodeError, ValueError):
        return None, None, [f"{kind}_manifest_unreadable"]
    provenance_path = manifest_path.parent / _provenance_name(kind, manifest)
    try:
        provenance = _read_json(provenance_path)
    except (OSError, json.JSONDecodeError, ValueError):
        errors.append(f"{kind}_provenance_hash_manifest_tamper")
        provenance = None
    return manifest, provenance, errors


def _artifact_hashes_from_provenance(provenance: dict[str, Any] | None) -> dict[str, str]:
    if provenance is None:
        return {}
    artifact_hashes = provenance.get("artifact_hashes")
    if not isinstance(artifact_hashes, dict):
        return {}
    return {str(name): str(digest) for name, digest in artifact_hashes.items() if isinstance(name, str) and isinstance(digest, str)}


def _canonical_root_hash(provenance: dict[str, Any] | None) -> str | None:
    artifact_hashes = _artifact_hashes_from_provenance(provenance)
    if not artifact_hashes:
        return None
    return _sha256_text(_stable_json({"artifact_hashes": artifact_hashes}))


def _artifact_tamper_code(kind: str, artifact_name: str) -> str:
    if kind == "queue":
        if artifact_name == "p105-queue-public-telemetry.jsonl":
            return "queue_telemetry_tamper"
        if artifact_name == "p105-queue-private-injection-ledger.json":
            return "queue_private_ledger_tamper"
        if artifact_name == "p105-queue-harness-manifest.json":
            return "queue_manifest_tamper"
        return "queue_artifact_tamper"
    if artifact_name == "p105-deploy-rollback-evidence.json":
        return "deploy_rollback_tamper"
    if artifact_name == "p105-deploy-public-telemetry.jsonl":
        return "deploy_telemetry_tamper"
    if artifact_name == "p105-deploy-harness-manifest.json":
        return "deploy_manifest_tamper"
    return "deploy_artifact_tamper"


def _verify_manifest(manifest_path: Path, *, kind: str) -> list[str]:
    errors: list[str] = []
    try:
        manifest = _read_json(manifest_path)
    except (OSError, json.JSONDecodeError, ValueError):
        return [f"{kind}_manifest_unreadable"]
    base_dir = manifest_path.parent
    provenance_name = _provenance_name(kind, manifest)
    provenance_path = base_dir / provenance_name
    try:
        provenance = _read_json(provenance_path)
    except (OSError, json.JSONDecodeError, ValueError):
        return [f"{kind}_provenance_hash_manifest_tamper"]
    expected_hashes = provenance.get("artifact_hashes")
    if not isinstance(expected_hashes, dict) or not expected_hashes:
        errors.append(f"{kind}_provenance_hash_manifest_tamper")
        return errors
    for artifact_name, expected_hash in sorted(expected_hashes.items()):
        if not isinstance(artifact_name, str) or not isinstance(expected_hash, str):
            errors.append(f"{kind}_provenance_hash_manifest_tamper")
            continue
        artifact_path = base_dir / artifact_name
        if not artifact_path.exists():
            errors.append(_artifact_tamper_code(kind, artifact_name))
            continue
        actual_hash = _sha256_path(artifact_path)
        if actual_hash != expected_hash:
            errors.append(_artifact_tamper_code(kind, artifact_name))
    if manifest.get("program_version") != provenance.get("program_version"):
        errors.append(f"{kind}_provenance_hash_manifest_tamper")
    if manifest.get("command_argv_sha256") != provenance.get("command_argv_sha256"):
        errors.append(f"{kind}_provenance_hash_manifest_tamper")
    return sorted(set(errors))


def _compare_reruns(first_manifest: Path, second_manifest: Path, *, kind: str) -> list[str]:
    first = _read_json(first_manifest)
    provenance_name = _provenance_name(kind, first)
    names = sorted(_read_json(first_manifest.parent / provenance_name).get("artifact_hashes", {}))
    names.append(provenance_name)
    errors: list[str] = []
    for name in names:
        if (first_manifest.parent / name).read_bytes() != (second_manifest.parent / name).read_bytes():
            errors.append(f"{kind}_rerun_not_byte_identical")
            break
    return errors


def _compare_canonical_reruns(first_manifest: Path, second_manifest: Path, *, kind: str) -> list[str]:
    try:
        return _compare_reruns(first_manifest, second_manifest, kind=kind)
    except (OSError, json.JSONDecodeError, ValueError):
        return [f"{kind}_rerun_canonical_unreadable"]


def _verify_optional_source_file(path: Path | None, *, name: str) -> tuple[dict[str, Any] | None, list[str]]:
    if path is None:
        return None, [f"{name}_missing"]
    if not path.exists():
        return None, [f"{name}_missing"]
    try:
        payload = _read_json(path)
    except (OSError, json.JSONDecodeError, ValueError):
        return None, [f"{name}_unreadable"]
    return payload, []


def _validate_no_source_counting_authority(source_name: str, payload: dict[str, Any] | None) -> list[str]:
    if payload is None:
        return []
    if _flatten_keys(payload) & FORBIDDEN_SOURCE_COUNTING_KEYS:
        return [f"{source_name}_forged_release_counting_authority"]
    return []


def _run_envelope(
    *,
    source: str,
    run_label: str,
    manifest_path: Path | None,
    raw_attestation_path: Path | None,
    expected_runtime_kinds: set[str],
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    manifest: dict[str, Any] | None = None
    provenance: dict[str, Any] | None = None
    raw_attestation: dict[str, Any] | None = None
    if manifest_path is None:
        errors.append(f"{source}_{run_label}_manifest_missing")
    elif not manifest_path.exists():
        errors.append(f"{source}_{run_label}_manifest_missing")
    else:
        manifest, provenance, manifest_errors = _read_manifest_and_provenance(manifest_path, kind=source)
        errors.extend(manifest_errors)
        if manifest is not None:
            errors.extend(_verify_manifest(manifest_path, kind=source))
            errors.extend(_validate_no_source_counting_authority(f"{source}_{run_label}_manifest", manifest))
    if raw_attestation_path is None:
        errors.append(f"{source}_{run_label}_raw_attestation_missing")
    elif not raw_attestation_path.exists():
        errors.append(f"{source}_{run_label}_raw_attestation_missing")
    else:
        try:
            raw_attestation = _read_json(raw_attestation_path)
        except (OSError, json.JSONDecodeError, ValueError):
            errors.append(f"{source}_{run_label}_raw_attestation_unreadable")
    runtime_attestation = _runtime_attestation(manifest or {}, raw_attestation)
    runtime_kind = runtime_attestation.get("kind") if isinstance(runtime_attestation.get("kind"), str) else None
    runtime_capability = runtime_attestation.get("capability") if isinstance(runtime_attestation.get("capability"), str) else None
    required_kind = EXPECTED_RUNTIME_KIND_BY_SOURCE[source]
    if runtime_kind != required_kind:
        errors.append(f"{source}_{run_label}_runtime_kind_not_actual")
    if expected_runtime_kinds and runtime_kind not in expected_runtime_kinds:
        errors.append(f"{source}_{run_label}_runtime_kind_unexpected")
    if raw_attestation is not None and runtime_kind is not None and not _raw_evidence_present(raw_attestation, runtime_kind):
        errors.append(f"{source}_{run_label}_raw_evidence_missing")
    if manifest is not None:
        command_sha = manifest.get("command_argv_sha256")
        if command_sha is None and isinstance(manifest.get("command_argv"), list):
            command_sha = _sha256_text(_stable_json(manifest["command_argv"]))
        if command_sha is None and isinstance(manifest.get("canonical_command_argv"), list):
            command_sha = _sha256_text(_stable_json(manifest["canonical_command_argv"]))
    else:
        command_sha = None
    canonical_root_hash = _canonical_root_hash(provenance)
    envelope = {
        "schema_version": RUN_ENVELOPE_SCHEMA,
        "created_by": VERIFIER_ID,
        "source": source,
        "run_label": run_label,
        "manifest_path": str(manifest_path) if manifest_path is not None else None,
        "manifest_sha256": _sha256_path(manifest_path) if manifest_path is not None and manifest_path.exists() else None,
        "provenance_hashes_path": str(manifest_path.parent / _provenance_name(source, manifest)) if manifest_path is not None and manifest is not None else None,
        "canonical_artifact_root_sha256": canonical_root_hash,
        "canonical_artifact_hashes": _artifact_hashes_from_provenance(provenance),
        "raw_attestation_path": str(raw_attestation_path) if raw_attestation_path is not None else None,
        "raw_attestation_sha256": _sha256_path(raw_attestation_path) if raw_attestation_path is not None and raw_attestation_path.exists() else None,
        "runtime_attestation": {"kind": runtime_kind, "capability": runtime_capability},
        "command_argv_sha256": command_sha,
        "validation_error_codes": sorted(set(errors)),
        "verified": not errors,
    }
    return envelope, errors


def _parse_expected_runtime_kinds(value: str | None) -> set[str]:
    if value is None:
        return set(EXPECTED_RUNTIME_KIND_BY_SOURCE.values())
    return {item.strip() for item in value.split(",") if item.strip()}


def _run_runtime_phase(args: argparse.Namespace) -> int:
    errors: list[str] = []
    registry, registry_errors = _verify_optional_source_file(args.registry, name="registry")
    eligibility, eligibility_errors = _verify_optional_source_file(args.eligibility, name="eligibility")
    errors.extend(registry_errors)
    errors.extend(eligibility_errors)
    errors.extend(_validate_no_source_counting_authority("registry", registry))
    errors.extend(_validate_no_source_counting_authority("eligibility", eligibility))
    expected_kinds = _parse_expected_runtime_kinds(args.expect_runtime_kinds)
    run_specs = [
        ("db_pool", "run_1", args.db_pool_manifest, args.db_pool_raw_attestation),
        ("db_pool", "run_2", args.db_pool_rerun_manifest, args.db_pool_rerun_raw_attestation),
        ("queue", "run_1", args.queue_manifest, args.queue_raw_attestation),
        ("queue", "run_2", args.queue_rerun_manifest, args.queue_rerun_raw_attestation),
        ("deploy", "run_1", args.deploy_manifest, args.deploy_raw_attestation),
        ("deploy", "run_2", args.deploy_rerun_manifest, args.deploy_rerun_raw_attestation),
    ]
    envelopes: list[dict[str, Any]] = []
    for source, run_label, manifest_path, raw_attestation_path in run_specs:
        envelope, envelope_errors = _run_envelope(
            source=source,
            run_label=run_label,
            manifest_path=manifest_path,
            raw_attestation_path=raw_attestation_path,
            expected_runtime_kinds=expected_kinds,
        )
        envelopes.append(envelope)
        errors.extend(envelope_errors)
    if args.expect_byte_identical_canonical_reruns:
        for source, primary, rerun in (
            ("db_pool", args.db_pool_manifest, args.db_pool_rerun_manifest),
            ("queue", args.queue_manifest, args.queue_rerun_manifest),
            ("deploy", args.deploy_manifest, args.deploy_rerun_manifest),
        ):
            if primary is None or rerun is None:
                errors.append(f"{source}_rerun_manifest_missing")
            else:
                errors.extend(_compare_canonical_reruns(primary, rerun, kind=source))
    if args.write_run_envelopes_dir is None:
        errors.append("run_envelopes_dir_missing")
    else:
        for envelope in envelopes:
            filename = f"{str(envelope['source']).replace('_', '-')}-{str(envelope['run_label']).replace('_', '-')}.json"
            _write_json(args.write_run_envelopes_dir / filename, envelope)
            envelope["envelope_path"] = str(args.write_run_envelopes_dir / filename)
            envelope["envelope_sha256"] = _sha256_path(args.write_run_envelopes_dir / filename)
    verified_release_counting = not errors
    receipt = {
        "schema_version": SOURCE_RUNTIME_RECEIPT_SCHEMA,
        "created_by": VERIFIER_ID,
        "verified_release_counting": verified_release_counting,
        "expect_tamper_fixtures_fail_closed": args.expect_tamper_fixtures_fail_closed,
        "release_gate": {"p106_unlocked": False, "release_qualified": False},
        "registry": {"path": str(args.registry) if args.registry else None, "sha256": _sha256_path(args.registry) if args.registry and args.registry.exists() else None},
        "eligibility": {"path": str(args.eligibility) if args.eligibility else None, "sha256": _sha256_path(args.eligibility) if args.eligibility and args.eligibility.exists() else None},
        "expected_runtime_kinds": sorted(expected_kinds),
        "run_envelopes": envelopes,
        "canonical_roots": {
            str(envelope["source"]): envelope["canonical_artifact_root_sha256"]
            for envelope in envelopes
            if envelope.get("run_label") == "run_1"
        },
        "validation_error_codes": sorted(set(errors)),
    }
    if args.output_json:
        _write_json(args.output_json, receipt)
    if errors:
        sys.stderr.write(json.dumps(receipt, sort_keys=True) + "\n")
        return 1
    print(json.dumps(receipt, sort_keys=True))
    return 0


def _hash_release_dir(release_dir: Path) -> tuple[list[dict[str, Any]], str | None]:
    files = [
        {"path": str(path.relative_to(release_dir)), "sha256": _sha256_path(path)}
        for path in sorted(release_dir.rglob("*"))
        if path.is_file()
    ]
    if not files:
        return files, None
    return files, _sha256_text(_stable_json(files))


def _binding_sha256(payload: dict[str, Any], name: str) -> str | None:
    nested = payload.get(name)
    if isinstance(nested, dict) and isinstance(nested.get("sha256"), str):
        return nested["sha256"]
    for key in (f"{name}_sha256", f"{name}_hash"):
        if isinstance(payload.get(key), str):
            return str(payload[key])
    return None


def _source_entry_root_sha256(entry: Any) -> str | None:
    if not isinstance(entry, dict):
        return None
    for key in ("canonical_artifact_root_sha256", "artifact_root_sha256", "runtime_artifact_root_sha256"):
        if isinstance(entry.get(key), str):
            return str(entry[key])
    return None


def _release_artifact_manifests(release_dir: Path) -> tuple[dict[str, Any] | None, list[dict[str, str]], list[str]]:
    rows_path = release_dir / RELEASE_ROWS_ARTIFACT
    if not rows_path.exists():
        return None, [], ["release_rows_missing"]
    try:
        rows_payload = _read_json(rows_path)
    except (OSError, json.JSONDecodeError, ValueError):
        return None, [], ["release_rows_unreadable"]
    embedded = rows_payload.get("artifact_manifests")
    if not isinstance(embedded, dict):
        return rows_payload, [], ["release_artifact_manifest_missing"]
    errors: list[str] = []
    verified: list[dict[str, str]] = []
    expected_paths = {
        "source": RELEASE_SOURCE_MANIFEST,
        "preflight": RELEASE_PREFLIGHT,
    }
    for required_key in expected_paths:
        if not isinstance(embedded.get(required_key), dict):
            errors.append(f"release_{required_key}_artifact_binding_missing")
    for key, manifest in sorted(embedded.items()):
        if not isinstance(key, str) or not isinstance(manifest, dict):
            errors.append("release_artifact_manifest_malformed")
            continue
        relative_path = manifest.get("path")
        expected_hash = manifest.get("sha256")
        if not isinstance(relative_path, str) or not isinstance(expected_hash, str) or not expected_hash:
            errors.append(f"release_{key}_artifact_binding_missing")
            continue
        expected_path = expected_paths.get(key)
        if expected_path is not None and relative_path != expected_path:
            errors.append(f"release_{key}_artifact_path_mismatch")
            continue
        relative_artifact_path = Path(relative_path)
        if relative_artifact_path.is_absolute() or ".." in relative_artifact_path.parts:
            errors.append("release_artifact_manifest_malformed")
            continue
        artifact_path = release_dir / relative_artifact_path
        if not artifact_path.exists() or not artifact_path.is_file():
            errors.append(f"release_{key}_artifact_missing")
            continue
        actual_hash = _sha256_path(artifact_path)
        if actual_hash != expected_hash:
            errors.append("release_artifact_hash_mismatch")
            errors.append(f"release_{key}_artifact_hash_mismatch")
            continue
        verified.append({"key": key, "path": relative_path, "sha256": actual_hash})
    return rows_payload, verified, errors


def _verify_release_bindings(
    *,
    release_dir: Path,
    receipt_path: Path | None,
    receipt: dict[str, Any] | None,
    registry_path: Path | None,
    eligibility_path: Path | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list[dict[str, str]], str | None, list[str]]:
    errors: list[str] = []
    rows_payload, verified_artifacts, artifact_errors = _release_artifact_manifests(release_dir)
    errors.extend(artifact_errors)
    if rows_payload is not None:
        authority = rows_payload.get("authority")
        if not isinstance(authority, dict):
            errors.append("release_authority_missing")
        elif authority != EXPECTED_RELEASE_ZERO_AUTHORITY:
            errors.append("nonzero_authority_counter")
    source_manifest_path = release_dir / RELEASE_SOURCE_MANIFEST
    preflight_path = release_dir / RELEASE_PREFLIGHT
    source_manifest: dict[str, Any] | None = None
    preflight: dict[str, Any] | None = None
    if not source_manifest_path.exists():
        errors.append("source_manifest_missing")
    else:
        try:
            source_manifest = _read_json(source_manifest_path)
        except (OSError, json.JSONDecodeError, ValueError):
            errors.append("source_manifest_unreadable")
    if not preflight_path.exists():
        errors.append("source_availability_preflight_missing")
    else:
        try:
            preflight = _read_json(preflight_path)
        except (OSError, json.JSONDecodeError, ValueError):
            errors.append("source_availability_preflight_unreadable")
    if source_manifest is not None:
        expected_receipt_hash = _binding_sha256(source_manifest, "source_runtime_qualification_receipt")
        actual_receipt_hash = _sha256_path(receipt_path) if receipt_path is not None and receipt_path.exists() else None
        if expected_receipt_hash is None:
            errors.append("source_runtime_receipt_binding_missing")
        elif expected_receipt_hash != actual_receipt_hash:
            errors.append("source_runtime_receipt_hash_mismatch")
        expected_registry_hash = _binding_sha256(source_manifest, "registry") or _binding_sha256(source_manifest, "source_registry")
        actual_registry_hash = _sha256_path(registry_path) if registry_path is not None and registry_path.exists() else None
        if expected_registry_hash is None:
            errors.append("registry_binding_missing")
        elif expected_registry_hash != actual_registry_hash:
            errors.append("registry_hash_mismatch")
        expected_eligibility_hash = _binding_sha256(source_manifest, "eligibility") or _binding_sha256(source_manifest, "source_eligibility")
        actual_eligibility_hash = _sha256_path(eligibility_path) if eligibility_path is not None and eligibility_path.exists() else None
        if expected_eligibility_hash is None:
            errors.append("eligibility_binding_missing")
        elif expected_eligibility_hash != actual_eligibility_hash:
            errors.append("eligibility_hash_mismatch")
        sources = source_manifest.get("sources")
        if not isinstance(sources, dict):
            errors.append("source_manifest_sources_missing")
            sources = {}
        for source in REQUIRED_RELEASE_SOURCE_ENTRIES:
            if not isinstance(sources.get(source), dict):
                errors.append(f"source_manifest_{source}_missing")
        receipt_roots = receipt.get("canonical_roots") if isinstance(receipt, dict) else None
        if not isinstance(receipt_roots, dict):
            receipt_roots = {}
        for source in ("db_pool", "queue", "deploy"):
            source_entry = sources.get(source) if isinstance(sources, dict) else None
            source_root = _source_entry_root_sha256(source_entry)
            receipt_root = receipt_roots.get(source)
            if source_root is None:
                errors.append(f"{source}_artifact_root_binding_missing")
            elif source_root != receipt_root:
                errors.append(f"{source}_artifact_root_mismatch")
    if preflight is not None:
        preflight_sources = preflight.get("sources")
        if not isinstance(preflight_sources, dict):
            errors.append("source_availability_preflight_sources_missing")
            preflight_sources = {}
        for source in REQUIRED_RELEASE_SOURCE_ENTRIES:
            if not isinstance(preflight_sources.get(source), dict):
                errors.append(f"source_preflight_{source}_missing")
    verified_root = _sha256_text(_stable_json(verified_artifacts)) if verified_artifacts else None
    return rows_payload, source_manifest, verified_artifacts, verified_root, errors


def _run_release_phase(args: argparse.Namespace) -> int:
    errors: list[str] = []
    registry, registry_errors = _verify_optional_source_file(args.registry, name="registry")
    eligibility, eligibility_errors = _verify_optional_source_file(args.eligibility, name="eligibility")
    errors.extend(registry_errors)
    errors.extend(eligibility_errors)
    errors.extend(_validate_no_source_counting_authority("registry", registry))
    errors.extend(_validate_no_source_counting_authority("eligibility", eligibility))
    receipt: dict[str, Any] | None = None
    receipt_path = args.source_runtime_qualification_receipt
    if receipt_path is None:
        errors.append("source_runtime_qualification_receipt_missing")
    elif not receipt_path.exists():
        errors.append("source_runtime_qualification_receipt_missing")
    else:
        try:
            receipt = _read_json(receipt_path)
        except (OSError, json.JSONDecodeError, ValueError):
            errors.append("source_runtime_qualification_receipt_unreadable")
    if receipt is not None:
        if receipt.get("schema_version") != SOURCE_RUNTIME_RECEIPT_SCHEMA or receipt.get("created_by") != VERIFIER_ID:
            errors.append("forged_source_runtime_receipt")
        if args.expect_verified_release_counting_receipt and receipt.get("verified_release_counting") is not True:
            errors.append("source_runtime_receipt_not_verified_release_counting")
        if not isinstance(receipt.get("run_envelopes"), list) or not receipt.get("run_envelopes"):
            errors.append("source_runtime_receipt_envelopes_missing")
    release_files: list[dict[str, Any]] = []
    release_root_hash: str | None = None
    verified_artifacts: list[dict[str, str]] = []
    verified_artifact_root_hash: str | None = None
    if args.release_dir is None:
        errors.append("release_dir_missing")
    elif not args.release_dir.exists() or not args.release_dir.is_dir():
        errors.append("release_dir_missing")
    else:
        release_files, release_root_hash = _hash_release_dir(args.release_dir)
        if not release_files:
            errors.append("release_dir_empty")
        else:
            _, _, verified_artifacts, verified_artifact_root_hash, release_binding_errors = _verify_release_bindings(
                release_dir=args.release_dir,
                receipt_path=receipt_path,
                receipt=receipt,
                registry_path=args.registry,
                eligibility_path=args.eligibility,
            )
            errors.extend(release_binding_errors)
    if args.expect_db_pool_command_args and receipt is not None:
        db_envelopes = [item for item in receipt.get("run_envelopes", []) if isinstance(item, dict) and item.get("source") == "db_pool"]
        if not db_envelopes or any(not item.get("command_argv_sha256") for item in db_envelopes):
            errors.append("db_pool_command_args_missing")
    result = {
        "schema_version": RELEASE_VERIFICATION_SCHEMA,
        "created_by": VERIFIER_ID,
        "verified": not errors,
        "verified_release_counting_receipt": bool(receipt and receipt.get("verified_release_counting") is True),
        "release_gate": {"p106_unlocked": False, "release_qualified": False},
        "source_runtime_qualification_receipt": {
            "path": str(receipt_path) if receipt_path is not None else None,
            "sha256": _sha256_path(receipt_path) if receipt_path is not None and receipt_path.exists() else None,
        },
        "release_dir": str(args.release_dir) if args.release_dir is not None else None,
        "release_root_sha256": release_root_hash,
        "verified_release_artifact_root_sha256": verified_artifact_root_hash,
        "release_files": release_files,
        "verified_release_artifacts": verified_artifacts,
        "validation_error_codes": sorted(set(errors)),
    }
    if args.output_json:
        _write_json(args.output_json, result)
    if errors:
        sys.stderr.write(json.dumps(result, sort_keys=True) + "\n")
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify P105 source-expansion artifact hashes and fail closed on tamper.")
    parser.add_argument("--phase", choices=["runtime", "release"])
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--eligibility", type=Path)
    parser.add_argument("--dejavu-manifest", type=Path)
    parser.add_argument("--db-pool-manifest", type=Path)
    parser.add_argument("--db-pool-rerun-manifest", type=Path)
    parser.add_argument("--db-pool-raw-attestation", type=Path)
    parser.add_argument("--db-pool-rerun-raw-attestation", type=Path)
    parser.add_argument("--queue-manifest", type=Path)
    parser.add_argument("--queue-rerun-manifest", type=Path)
    parser.add_argument("--queue-raw-attestation", type=Path)
    parser.add_argument("--queue-rerun-raw-attestation", type=Path)
    parser.add_argument("--deploy-manifest", type=Path)
    parser.add_argument("--deploy-rerun-manifest", type=Path)
    parser.add_argument("--deploy-raw-attestation", type=Path)
    parser.add_argument("--deploy-rerun-raw-attestation", type=Path)
    parser.add_argument("--release-dir", type=Path)
    parser.add_argument("--source-runtime-qualification-receipt", type=Path)
    parser.add_argument("--write-run-envelopes-dir", type=Path)
    parser.add_argument("--expect-byte-identical-reruns", action="store_true")
    parser.add_argument("--expect-byte-identical-canonical-reruns", action="store_true")
    parser.add_argument("--expect-tamper-fixtures-fail-closed", action="store_true")
    parser.add_argument("--expect-runtime-kinds")
    parser.add_argument("--expect-verified-release-counting-receipt", action="store_true")
    parser.add_argument("--expect-db-pool-command-args", action="store_true")
    parser.add_argument("--output-json", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    if args.phase == "runtime":
        return _run_runtime_phase(args)
    if args.phase == "release":
        return _run_release_phase(args)
    errors: list[str] = []
    verified: dict[str, Any] = {}
    if args.queue_manifest:
        queue_errors = _verify_manifest(args.queue_manifest, kind="queue")
        verified["queue_manifest"] = str(args.queue_manifest)
        errors.extend(queue_errors)
        if args.expect_byte_identical_reruns and args.queue_rerun_manifest:
            errors.extend(_compare_reruns(args.queue_manifest, args.queue_rerun_manifest, kind="queue"))
    if args.deploy_manifest:
        deploy_errors = _verify_manifest(args.deploy_manifest, kind="deploy")
        verified["deploy_manifest"] = str(args.deploy_manifest)
        errors.extend(deploy_errors)
        if args.expect_byte_identical_reruns and args.deploy_rerun_manifest:
            errors.extend(_compare_reruns(args.deploy_manifest, args.deploy_rerun_manifest, kind="deploy"))
    for optional_name in ("registry", "eligibility", "dejavu_manifest"):
        optional_path = getattr(args, optional_name)
        if optional_path is not None:
            verified[optional_name] = {"path": str(optional_path), "sha256": _sha256_path(optional_path) if optional_path.exists() else None}
            if not optional_path.exists():
                errors.append(f"{optional_name}_missing")
    result = {
        "expect_tamper_fixtures_fail_closed": args.expect_tamper_fixtures_fail_closed,
        "release_gate": {"p106_unlocked": False, "release_qualified": False},
        "validation_error_codes": sorted(set(errors)),
        "verified": verified,
    }
    if args.output_json:
        _write_json(args.output_json, result)
    if errors:
        sys.stderr.write(json.dumps(result, sort_keys=True) + "\n")
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
