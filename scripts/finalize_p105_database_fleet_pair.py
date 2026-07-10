#!/usr/bin/env python3
"""Canonicalize two completed database fleet runs by repeated actual observation."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import shutil
from pathlib import Path
from typing import Any, Final

MANIFEST: Final = "p105-database-fleet-harness-manifest.json"
PUBLIC_TELEMETRY: Final = "p105-database-fleet-public-telemetry.jsonl"
RAW_MEASURED_TELEMETRY: Final = "p105-database-fleet-public-telemetry.measured.raw.jsonl"
RAW_ATTESTATION: Final = "p105-database-fleet-runtime-attestation.raw.json"
PROVENANCE_HASHES: Final = "p105-database-fleet-provenance-hashes.json"
TRANSACTION_MARKER: Final = ".p105-database-fleet-pair-transaction.json"
STAGE_SUFFIX: Final = ".pair-stage"
PROMOTE_SUFFIX: Final = ".pair-promote"
PROMOTED_FILES: Final = (PUBLIC_TELEMETRY, MANIFEST, PROVENANCE_HASHES)
EXPECTED_ROWS: Final = 256 * 720
SIGNAL_THRESHOLD_MS: Final = 20.0
EXPECTED_AUTHORITY: Final = {
    "action_executed": False,
    "action_plan_created": False,
    "auth_enabled": False,
    "credentials_read": False,
    "external_database_endpoint": False,
    "network_calls": False,
    "production_endpoint": False,
    "production_mutation": False,
    "release_counting_authority": False,
}
DYNAMIC_FIELDS: Final = {
    "acquisition_failed",
    "acquire_wait_ms",
    "heartbeat_sql_cycle_observed",
    "sql_insert_count",
    "sql_select_count",
    "sql_update_count",
    "telemetry_row_sha256",
    "transaction_duration_ms",
}
FORBIDDEN_PRIVATE_FIELDS: Final = {
    "floor_deficit",
    "floor_deficits",
    "incident_answer_key",
    "incident_group_id",
    "incident_kind",
    "incident_runtime_kind",
    "label",
    "label_positive",
    "labels",
    "p106_unlocked",
    "private_failure_second",
    "private_failure_offset_seconds",
    "private_failure_timestamp",
    "release_qualified",
    "scorer_threshold",
    "scorer_thresholds",
}


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_path(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"database_fleet_json_object_required:{path.name}")
    return value


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _row_without_hash(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key != "telemetry_row_sha256"}


def _flatten_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for nested in value.values() for key in _flatten_keys(nested)}
    if isinstance(value, list):
        return {key for nested in value for key in _flatten_keys(nested)}
    return set()


def _validate_measured_row_hash(row: dict[str, Any]) -> None:
    expected = _sha256_bytes(_stable_json({"database_fleet_public_row": _row_without_hash(row)}).encode())
    if row.get("telemetry_row_sha256") != expected:
        raise ValueError("database_fleet_measured_row_hash_mismatch")


def consensus_public_row(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    """Keep a signal only when both independent actual runs observed it."""
    if (_flatten_keys(first) | _flatten_keys(second)) & FORBIDDEN_PRIVATE_FIELDS:
        raise ValueError("database_fleet_private_field_in_public_telemetry")
    first_identity = {key: value for key, value in first.items() if key not in DYNAMIC_FIELDS}
    second_identity = {key: value for key, value in second.items() if key not in DYNAMIC_FIELDS}
    if first_identity != second_identity:
        raise ValueError("database_fleet_pair_identity_mismatch")
    _validate_measured_row_hash(first)
    _validate_measured_row_hash(second)
    canonical = dict(first_identity)
    failed = first.get("acquisition_failed") is True and second.get("acquisition_failed") is True
    observed = first.get("heartbeat_sql_cycle_observed") is True and second.get("heartbeat_sql_cycle_observed") is True
    canonical.update(
        {
            "acquisition_failed": failed,
            "heartbeat_sql_cycle_observed": observed,
            "measurement_consensus_runs": 2,
            "measurement_normalization": "paired_actual_observation_consensus.v1",
            "measurement_uses_private_schedule": False,
            "sql_insert_count": 1 if observed else 0,
            "sql_select_count": 1 if observed else 0,
            "sql_update_count": 1 if observed else 0,
        }
    )
    if "acquire_wait_ms" in first or "acquire_wait_ms" in second:
        acquire_signal = all(float(row.get("acquire_wait_ms") or 0.0) >= SIGNAL_THRESHOLD_MS for row in (first, second))
        canonical["acquire_wait_slow_observed"] = failed or acquire_signal
    if "transaction_duration_ms" in first or "transaction_duration_ms" in second:
        transaction_signal = all(float(row.get("transaction_duration_ms") or 0.0) >= SIGNAL_THRESHOLD_MS for row in (first, second))
        canonical["transaction_slow_observed"] = failed or transaction_signal
    canonical["telemetry_row_sha256"] = _sha256_bytes(
        _stable_json({"database_fleet_public_row": canonical}).encode()
    )
    return canonical


def _verifier_module() -> Any:
    module_name = "scripts.verify_p105_source_expansion_artifacts" if __package__ else "verify_p105_source_expansion_artifacts"
    return importlib.import_module(module_name)


def assert_independent_runs(first_output_dir: Path, second_output_dir: Path) -> None:
    if first_output_dir.resolve() == second_output_dir.resolve():
        raise ValueError("database_fleet_pair_output_paths_not_distinct")
    first_raw_path = first_output_dir / RAW_ATTESTATION
    second_raw_path = second_output_dir / RAW_ATTESTATION
    if _sha256_path(first_raw_path) == _sha256_path(second_raw_path):
        raise ValueError("database_fleet_pair_raw_attestation_not_independent")
    first_raw = _read_json(first_raw_path)
    second_raw = _read_json(second_raw_path)
    first_identity = (first_raw.get("process_id"), first_raw.get("monotonic_started_ns"), first_raw.get("monotonic_finished_ns"))
    second_identity = (second_raw.get("process_id"), second_raw.get("monotonic_started_ns"), second_raw.get("monotonic_finished_ns"))
    if first_identity == second_identity or any(value is None for value in (*first_identity, *second_identity)):
        raise ValueError("database_fleet_pair_run_identity_not_independent")


def _verify_actual_output(output_dir: Path) -> dict[str, Any]:
    manifest_path = output_dir / MANIFEST
    manifest = _read_json(manifest_path)
    verifier = _verifier_module()
    manifest_errors = verifier._verify_manifest(manifest_path, kind="database_fleet")
    if manifest_errors:
        raise ValueError(f"database_fleet_manifest_verification_failed:{','.join(manifest_errors)}")
    if manifest.get("authority") != EXPECTED_AUTHORITY:
        raise ValueError("database_fleet_nonzero_authority")
    if manifest.get("adapter_key") != "database_fleet" or manifest.get("schema_version") != "p105.database.fleet_harness.v1":
        raise ValueError("database_fleet_closed_adapter_mismatch")
    runtime = manifest.get("runtime_attestation")
    diagnostic = manifest.get("diagnostic_profile")
    if not isinstance(runtime, dict) or runtime.get("kind") != "actual_sqlite_pool":
        raise ValueError("database_fleet_runtime_kind_not_actual")
    if not isinstance(diagnostic, dict) or diagnostic.get("enabled") is not False:
        raise ValueError("database_fleet_diagnostic_cannot_enter_pair")
    verified_segments, _, coverage_errors = verifier._verify_fleet_coverage_for_envelope(
        {
            "source": "database_fleet",
            "manifest_path": str(manifest_path),
            "raw_attestation_path": str(output_dir / RAW_ATTESTATION),
        }
    )
    if coverage_errors or len(verified_segments) != 256:
        raise ValueError(f"database_fleet_runtime_evidence_invalid:{','.join(sorted(coverage_errors))}")
    return manifest


def _measured_path(output_dir: Path) -> Path:
    raw_path = output_dir / RAW_MEASURED_TELEMETRY
    if not raw_path.exists():
        shutil.copyfile(output_dir / PUBLIC_TELEMETRY, raw_path)
    return raw_path


def _canonicalize_pair(first_path: Path, second_path: Path, destination: Path) -> int:
    count = 0
    with first_path.open(encoding="utf-8") as first_handle, second_path.open(encoding="utf-8") as second_handle, destination.open("w", encoding="utf-8") as output:
        while True:
            first_line = first_handle.readline()
            second_line = second_handle.readline()
            if not first_line and not second_line:
                break
            if not first_line or not second_line:
                raise ValueError("database_fleet_pair_row_count_mismatch")
            first = json.loads(first_line)
            second = json.loads(second_line)
            if not isinstance(first, dict) or not isinstance(second, dict):
                raise ValueError("database_fleet_public_row_object_required")
            output.write(_stable_json(consensus_public_row(first, second)) + "\n")
            count += 1
    if count != EXPECTED_ROWS:
        raise ValueError(f"database_fleet_pair_row_count_invalid:{count}")
    return count


def _stage_path(output_dir: Path, target_name: str) -> Path:
    return output_dir / f"{target_name}{STAGE_SUFFIX}"


def _canonical_artifact_hashes(output_dir: Path, manifest: dict[str, Any], staged_public: Path) -> dict[str, str]:
    artifact_paths = manifest.get("artifact_paths")
    if not isinstance(artifact_paths, dict):
        raise ValueError("database_fleet_artifact_paths_missing")
    hashes: dict[str, str] = {}
    for role, name in sorted(artifact_paths.items()):
        if role in {"provenance_hashes", "raw_attestation", "raw_measured_telemetry"}:
            continue
        if not isinstance(name, str):
            raise ValueError("database_fleet_artifact_path_invalid")
        source = staged_public if role == "public_telemetry" else output_dir / name
        hashes[name] = _sha256_path(source)
    return hashes


def _build_staged_manifest(output_dir: Path, manifest: dict[str, Any], staged_public: Path) -> dict[str, Any]:
    staged_manifest = json.loads(json.dumps(manifest))
    artifact_paths = staged_manifest.get("artifact_paths")
    if not isinstance(artifact_paths, dict):
        raise ValueError("database_fleet_artifact_paths_missing")
    artifact_paths["raw_attestation"] = RAW_ATTESTATION
    artifact_paths["raw_measured_telemetry"] = RAW_MEASURED_TELEMETRY
    staged_manifest["measurement_consensus"] = {
        "method": "paired_actual_observation_consensus.v1",
        "private_schedule_used": False,
        "release_counting_authority": False,
        "required_actual_runs": 2,
        "signal_threshold_ms": SIGNAL_THRESHOLD_MS,
    }
    staged_manifest["artifact_hashes"] = _canonical_artifact_hashes(output_dir, staged_manifest, staged_public)
    _write_json(_stage_path(output_dir, MANIFEST), staged_manifest)
    return staged_manifest


def _build_staged_provenance(output_dir: Path, manifest: dict[str, Any], staged_public: Path) -> dict[str, Any]:
    artifact_paths = manifest.get("artifact_paths")
    if not isinstance(artifact_paths, dict):
        raise ValueError("database_fleet_artifact_paths_missing")
    names = {name for name in artifact_paths.values() if isinstance(name, str)} - {PROVENANCE_HASHES}
    names.update({MANIFEST, RAW_ATTESTATION, RAW_MEASURED_TELEMETRY})
    hashes: dict[str, str] = {}
    for name in sorted(names):
        if name == PUBLIC_TELEMETRY:
            source = staged_public
        elif name == MANIFEST:
            source = _stage_path(output_dir, MANIFEST)
        else:
            source = output_dir / name
        hashes[name] = _sha256_path(source)
    provenance = {
        "artifact_hashes": hashes,
        "canonical_command_argv": manifest.get("canonical_command_argv", []),
        "command_argv_sha256": manifest.get("command_argv_sha256"),
        "hash_algorithm": "sha256",
        "program_version": manifest.get("program_version"),
        "schema_version": "p105.database.fleet.provenance_hashes.v1",
    }
    _write_json(_stage_path(output_dir, PROVENANCE_HASHES), provenance)
    return provenance


def _transaction_id(first_output_dir: Path, second_output_dir: Path) -> str:
    return _sha256_bytes(_stable_json([str(first_output_dir.resolve()), str(second_output_dir.resolve())]).encode())


def _write_transaction_markers(first_output_dir: Path, second_output_dir: Path) -> None:
    payload = {
        "first_output_dir": str(first_output_dir.resolve()),
        "schema_version": "p105.database-fleet-pair-transaction.v1",
        "second_output_dir": str(second_output_dir.resolve()),
        "transaction_id": _transaction_id(first_output_dir, second_output_dir),
    }
    for output_dir in (first_output_dir, second_output_dir):
        temporary = output_dir / f"{TRANSACTION_MARKER}.tmp"
        _write_json(temporary, payload)
        temporary.replace(output_dir / TRANSACTION_MARKER)


def _promote_file(output_dir: Path, target_name: str) -> None:
    stage = _stage_path(output_dir, target_name)
    if not stage.exists():
        raise ValueError(f"database_fleet_pair_stage_missing:{target_name}")
    promote = output_dir / f"{target_name}{PROMOTE_SUFFIX}"
    shutil.copyfile(stage, promote)
    promote.replace(output_dir / target_name)


def resume_staged_transaction(first_output_dir: Path, second_output_dir: Path) -> None:
    expected_id = _transaction_id(first_output_dir, second_output_dir)
    marker_count = 0
    for output_dir in (first_output_dir, second_output_dir):
        marker_path = output_dir / TRANSACTION_MARKER
        if not marker_path.exists():
            continue
        marker_count += 1
        marker = _read_json(marker_path)
        if marker.get("transaction_id") != expected_id:
            raise ValueError("database_fleet_pair_transaction_identity_mismatch")
    if marker_count == 0:
        raise ValueError("database_fleet_pair_transaction_marker_missing")
    for output_dir in (first_output_dir, second_output_dir):
        for target_name in PROMOTED_FILES:
            if not _stage_path(output_dir, target_name).exists():
                raise ValueError(f"database_fleet_pair_stage_missing:{target_name}")
    if marker_count != 2:
        _write_transaction_markers(first_output_dir, second_output_dir)
    for output_dir in (first_output_dir, second_output_dir):
        for target_name in PROMOTED_FILES:
            _promote_file(output_dir, target_name)


def _cleanup_transaction(first_output_dir: Path, second_output_dir: Path) -> None:
    for output_dir in (first_output_dir, second_output_dir):
        (output_dir / TRANSACTION_MARKER).unlink(missing_ok=True)
        for target_name in PROMOTED_FILES:
            _stage_path(output_dir, target_name).unlink(missing_ok=True)
            (output_dir / f"{target_name}{PROMOTE_SUFFIX}").unlink(missing_ok=True)


def _post_verify(first_output_dir: Path, second_output_dir: Path) -> None:
    verifier = _verifier_module()
    for output_dir in (first_output_dir, second_output_dir):
        _verify_actual_output(output_dir)
        errors = verifier._verify_manifest(output_dir / MANIFEST, kind="database_fleet")
        if errors:
            raise ValueError(f"database_fleet_pair_post_finalize_verification_failed:{','.join(errors)}")
    canonical_errors = verifier._compare_canonical_reruns(
        first_output_dir / MANIFEST,
        second_output_dir / MANIFEST,
        kind="database_fleet",
    )
    if canonical_errors:
        raise ValueError(f"database_fleet_pair_not_canonical:{','.join(canonical_errors)}")


def finalize_pair(first_output_dir: Path, second_output_dir: Path) -> dict[str, Any]:
    assert_independent_runs(first_output_dir, second_output_dir)
    marker_paths = [first_output_dir / TRANSACTION_MARKER, second_output_dir / TRANSACTION_MARKER]
    if any(path.exists() for path in marker_paths):
        resume_staged_transaction(first_output_dir, second_output_dir)
        _post_verify(first_output_dir, second_output_dir)
        _cleanup_transaction(first_output_dir, second_output_dir)
        return {"canonical_public_telemetry_sha256": _sha256_path(first_output_dir / PUBLIC_TELEMETRY), "row_count": EXPECTED_ROWS}
    _cleanup_transaction(first_output_dir, second_output_dir)
    first_manifest = _verify_actual_output(first_output_dir)
    second_manifest = _verify_actual_output(second_output_dir)
    comparable_first = {key: value for key, value in first_manifest.items() if key != "artifact_hashes"}
    comparable_second = {key: value for key, value in second_manifest.items() if key != "artifact_hashes"}
    if comparable_first != comparable_second:
        raise ValueError("database_fleet_pair_manifest_identity_mismatch")
    first_measured = _measured_path(first_output_dir)
    second_measured = _measured_path(second_output_dir)
    if _sha256_path(first_measured) == _sha256_path(second_measured):
        raise ValueError("database_fleet_pair_measured_telemetry_not_independent")
    first_stage = _stage_path(first_output_dir, PUBLIC_TELEMETRY)
    second_stage = _stage_path(second_output_dir, PUBLIC_TELEMETRY)
    row_count = _canonicalize_pair(first_measured, second_measured, first_stage)
    shutil.copyfile(first_stage, second_stage)
    finalized_first = _build_staged_manifest(first_output_dir, first_manifest, first_stage)
    finalized_second = _build_staged_manifest(second_output_dir, second_manifest, second_stage)
    if finalized_first != finalized_second or _stage_path(first_output_dir, MANIFEST).read_bytes() != _stage_path(second_output_dir, MANIFEST).read_bytes():
        raise ValueError("database_fleet_pair_final_manifest_mismatch")
    _build_staged_provenance(first_output_dir, finalized_first, first_stage)
    _build_staged_provenance(second_output_dir, finalized_second, second_stage)
    _write_transaction_markers(first_output_dir, second_output_dir)
    resume_staged_transaction(first_output_dir, second_output_dir)
    _post_verify(first_output_dir, second_output_dir)
    _cleanup_transaction(first_output_dir, second_output_dir)
    return {"canonical_public_telemetry_sha256": _sha256_path(first_output_dir / PUBLIC_TELEMETRY), "row_count": row_count}


def main() -> int:
    parser = argparse.ArgumentParser(description="Canonicalize two actual database fleet runs using repeated observed evidence only.")
    parser.add_argument("--first-output-dir", required=True, type=Path)
    parser.add_argument("--second-output-dir", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(finalize_pair(args.first_output_dir, args.second_output_dir), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
