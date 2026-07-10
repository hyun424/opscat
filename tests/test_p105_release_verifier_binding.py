from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from scripts import verify_p105_source_expansion_artifacts as verifier

VERIFY_SCRIPT = Path("scripts/verify_p105_source_expansion_artifacts.py")


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


LEGACY_ROOTS = {
    "db_pool": hashlib.sha256(b"db-pool-root").hexdigest(),
    "queue": hashlib.sha256(b"queue-root").hexdigest(),
    "deploy": hashlib.sha256(b"deploy-root").hexdigest(),
}
FLEET_ROOTS = {
    "database_fleet": hashlib.sha256(b"database-fleet-root").hexdigest(),
    "queue_fleet": hashlib.sha256(b"queue-fleet-root").hexdigest(),
    "deploy_fleet": hashlib.sha256(b"deploy-fleet-root").hexdigest(),
}


def _runtime_receipt(path: Path, registry: Path, eligibility: Path, roots: dict[str, str] | None = None) -> Path:
    receipt_roots = dict(roots or LEGACY_ROOTS)
    return _write_json(
        path,
        {
            "schema_version": "p105.source-runtime-qualification.v1",
            "created_by": "scripts/verify_p105_source_expansion_artifacts.py",
            "verified_release_counting": True,
            "registry": {"path": str(registry), "sha256": _sha256_path(registry)},
            "eligibility": {"path": str(eligibility), "sha256": _sha256_path(eligibility)},
            "canonical_roots": receipt_roots,
            "run_envelopes": [
                {
                    "schema_version": "p105.source-runtime-run-envelope.v1",
                    "created_by": "scripts/verify_p105_source_expansion_artifacts.py",
                    "source": source,
                    "run_label": "run_1",
                    "canonical_artifact_root_sha256": root,
                    "command_argv_sha256": hashlib.sha256(source.encode()).hexdigest(),
                    "validation_error_codes": [],
                    "verified": True,
                }
                for source, root in receipt_roots.items()
            ],
            "validation_error_codes": [],
        },
    )


def _release_dir(tmp_path: Path, *, include_fleet: bool = False) -> tuple[Path, Path, Path | None, Path, Path]:
    registry = _write_json(tmp_path / "registry.json", {"schema_version": "p105.source-registry.v1", "sources": []})
    eligibility = _write_json(tmp_path / "eligibility.json", {"schema_version": "p105.source-eligibility.v1", "entries": []})
    receipt = _runtime_receipt(tmp_path / "receipt.json", registry, eligibility, LEGACY_ROOTS)
    receipt_payload = _read_json(receipt)
    fleet_receipt = _runtime_receipt(tmp_path / "fleet-receipt.json", registry, eligibility, FLEET_ROOTS) if include_fleet else None
    fleet_receipt_payload = _read_json(fleet_receipt) if fleet_receipt is not None else {"canonical_roots": {}}
    release_dir = tmp_path / "release"
    source_manifest: dict[str, Any] = {
        "schema_version": "p105.source_manifest.v1",
        "source_runtime_qualification_receipt": str(receipt),
        "source_runtime_qualification_receipt_sha256": _sha256_path(receipt),
        "fleet_runtime_qualification_receipt": str(fleet_receipt) if fleet_receipt is not None else None,
        "fleet_runtime_qualification_receipt_sha256": _sha256_path(fleet_receipt) if fleet_receipt is not None else None,
        "source_registry_sha256": _sha256_path(registry),
        "source_eligibility_sha256": _sha256_path(eligibility),
        "forbidden_inputs": [],
        "sources": {
            "dejavu_a1": {"manifest_path": "dejavu.json", "manifest_sha256": hashlib.sha256(b"dejavu").hexdigest()},
            **{
                source: {
                    "manifest_path": f"{source}.json",
                    "manifest_sha256": hashlib.sha256(source.encode()).hexdigest(),
                    "canonical_artifact_root_sha256": root,
                }
                for source, root in receipt_payload["canonical_roots"].items()
            },
            **{
                source: {
                    "manifest_path": f"{source}.json",
                    "manifest_sha256": hashlib.sha256(source.encode()).hexdigest(),
                    "canonical_artifact_root_sha256": root,
                }
                for source, root in fleet_receipt_payload["canonical_roots"].items()
            },
        },
    }
    preflight = {
        "schema_version": "p105.source_availability_preflight.v1",
        "checked_before_scoring": True,
        "sources": {
            source: {
                "available_source_rows": 1,
                "local_source_hashes": [hashlib.sha256(source.encode()).hexdigest()],
                "materialized_record_hashes": [hashlib.sha256(f"{source}:row".encode()).hexdigest()],
            }
            for source in ("dejavu_a1", "db_pool", "queue", "deploy", *((FLEET_ROOTS.keys()) if include_fleet else ()))
        },
    }
    source_path = _write_json(release_dir / "p105-source-manifest.json", source_manifest)
    preflight_path = _write_json(release_dir / "p105-source-availability-preflight.json", preflight)
    _write_json(
        release_dir / "p105-release-qualified-rows.json",
        {
            "schema_version": "p105.forecast.release_benchmark.v1",
            "mode": "release_qualified",
            "authority": {
                "auth_enabled": False,
                "production_mutation_enabled": False,
                "action_authority": False,
                "remediation_execution_enabled": False,
                "default_external_model_calls": 0,
            },
            "release_gate": {"release_qualified": False, "p106_unlocked": False},
            "source_input_manifest": source_manifest,
            "source_availability_preflight": preflight,
            "artifact_manifests": {
                "source": {
                    "path": "p105-source-manifest.json",
                    "sha256": _sha256_path(source_path),
                    "referenced_by_benchmark_payload": True,
                },
                "preflight": {
                    "path": "p105-source-availability-preflight.json",
                    "sha256": _sha256_path(preflight_path),
                    "referenced_by_benchmark_payload": True,
                },
            },
        },
    )
    return release_dir, receipt, fleet_receipt, registry, eligibility


def _verify_release(
    release_dir: Path,
    receipt: Path,
    registry: Path,
    eligibility: Path,
    output: Path,
    *,
    fleet_receipt: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        str(VERIFY_SCRIPT),
        "--phase",
        "release",
        "--registry",
        str(registry),
        "--eligibility",
        str(eligibility),
        "--source-runtime-qualification-receipt",
        str(receipt),
        "--release-dir",
        str(release_dir),
        "--expect-verified-release-counting-receipt",
        "--expect-db-pool-command-args",
        "--output-json",
        str(output),
    ]
    if fleet_receipt is not None:
        command.extend(["--fleet-runtime-qualification-receipt", str(fleet_receipt)])
    return subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
    )


def test_release_phase_binds_central_directory_to_receipt_registry_eligibility_and_runtime_roots(tmp_path: Path) -> None:
    release_dir, receipt, _, registry, eligibility = _release_dir(tmp_path)

    completed = _verify_release(release_dir, receipt, registry, eligibility, tmp_path / "verification.json")

    assert completed.returncode == 0, completed.stderr
    verification = _read_json(tmp_path / "verification.json")
    assert verification["verified"] is True
    assert verification["validation_error_codes"] == []
    assert verification["verified_release_counting_receipt"] is True
    assert verification["release_gate"] == {"p106_unlocked": False, "release_qualified": False}
    assert {artifact["key"] for artifact in verification["verified_release_artifacts"]} == {"preflight", "source"}
    assert len(verification["release_root_sha256"]) == 64


def test_release_phase_binds_fleet_release_to_legacy_and_fleet_receipts(tmp_path: Path) -> None:
    release_dir, receipt, fleet_receipt, registry, eligibility = _release_dir(tmp_path, include_fleet=True)
    assert fleet_receipt is not None

    completed = _verify_release(release_dir, receipt, registry, eligibility, tmp_path / "verification.json", fleet_receipt=fleet_receipt)

    assert completed.returncode == 0, completed.stderr
    verification = _read_json(tmp_path / "verification.json")
    assert verification["verified"] is True
    assert verification["verified_release_counting_receipt"] is True
    assert verification["verified_fleet_release_counting_receipt"] is True
    assert verification["validation_error_codes"] == []


def test_release_phase_rejects_source_owned_fleet_receipt_impersonating_release_counting(tmp_path: Path) -> None:
    release_dir, receipt, fleet_receipt, registry, eligibility = _release_dir(tmp_path, include_fleet=True)
    assert fleet_receipt is not None
    payload = _read_json(fleet_receipt)
    payload["created_by"] = "source-owned-fleet-harness"
    _write_json(fleet_receipt, payload)

    completed = _verify_release(release_dir, receipt, registry, eligibility, tmp_path / "verification.json", fleet_receipt=fleet_receipt)

    assert completed.returncode == 1
    verification = _read_json(tmp_path / "verification.json")
    assert "forged_fleet_runtime_receipt" in verification["validation_error_codes"]
    assert verification["release_gate"] == {"p106_unlocked": False, "release_qualified": False}


def test_fleet_release_fails_closed_without_both_receipt_bindings_and_preflight_groups(tmp_path: Path) -> None:
    release_dir, receipt, fleet_receipt, registry, eligibility = _release_dir(tmp_path, include_fleet=True)
    assert fleet_receipt is not None
    source_path = release_dir / "p105-source-manifest.json"
    source_manifest = _read_json(source_path)
    source_manifest.pop("fleet_runtime_qualification_receipt_sha256")
    source_manifest["sources"].pop("db_pool")
    _write_json(source_path, source_manifest)
    preflight_path = release_dir / "p105-source-availability-preflight.json"
    preflight = _read_json(preflight_path)
    preflight["sources"].pop("queue")
    preflight["sources"].pop("database_fleet")
    _write_json(preflight_path, preflight)

    completed = _verify_release(release_dir, receipt, registry, eligibility, tmp_path / "verification.json", fleet_receipt=fleet_receipt)

    assert completed.returncode == 1
    verification = _read_json(tmp_path / "verification.json")
    assert {
        "fleet_runtime_receipt_binding_missing",
        "source_manifest_db_pool_missing",
        "db_pool_artifact_root_binding_missing",
        "source_preflight_queue_missing",
        "source_preflight_database_fleet_missing",
        "release_artifact_hash_mismatch",
    } <= set(verification["validation_error_codes"])


def test_release_phase_fails_closed_on_missing_or_mismatched_source_bindings(tmp_path: Path) -> None:
    release_dir, receipt, _, registry, eligibility = _release_dir(tmp_path)
    source_path = release_dir / "p105-source-manifest.json"
    source_manifest = _read_json(source_path)
    source_manifest["source_runtime_qualification_receipt_sha256"] = "0" * 64
    source_manifest.pop("source_registry_sha256")
    source_manifest["source_eligibility_sha256"] = "1" * 64
    source_manifest["sources"].pop("queue")
    source_manifest["sources"]["db_pool"]["canonical_artifact_root_sha256"] = "2" * 64
    _write_json(source_path, source_manifest)
    rows_path = release_dir / "p105-release-qualified-rows.json"
    rows = _read_json(rows_path)
    rows["authority"]["action_authority"] = True
    _write_json(rows_path, rows)

    completed = _verify_release(release_dir, receipt, registry, eligibility, tmp_path / "verification.json")

    assert completed.returncode == 1
    verification = _read_json(tmp_path / "verification.json")
    assert {
        "source_runtime_receipt_hash_mismatch",
        "registry_binding_missing",
        "eligibility_hash_mismatch",
        "source_manifest_queue_missing",
        "db_pool_artifact_root_mismatch",
        "release_artifact_hash_mismatch",
        "release_source_artifact_hash_mismatch",
        "nonzero_authority_counter",
    } <= set(verification["validation_error_codes"])
    assert verification["release_gate"] == {"p106_unlocked": False, "release_qualified": False}


def test_release_phase_requires_first_class_preflight_entries_for_every_actual_source(tmp_path: Path) -> None:
    release_dir, receipt, _, registry, eligibility = _release_dir(tmp_path)
    preflight_path = release_dir / "p105-source-availability-preflight.json"
    preflight = _read_json(preflight_path)
    preflight["sources"].pop("dejavu_a1")
    preflight["sources"].pop("deploy")
    _write_json(preflight_path, preflight)

    completed = _verify_release(release_dir, receipt, registry, eligibility, tmp_path / "verification.json")

    assert completed.returncode == 1
    verification = _read_json(tmp_path / "verification.json")
    assert {
        "source_preflight_dejavu_a1_missing",
        "source_preflight_deploy_missing",
        "release_artifact_hash_mismatch",
        "release_preflight_artifact_hash_mismatch",
    } <= set(verification["validation_error_codes"])
    assert verification["release_gate"] == {"p106_unlocked": False, "release_qualified": False}


def test_release_phase_rejects_artifact_binding_to_alternate_relative_file(tmp_path: Path) -> None:
    release_dir, receipt, _, registry, eligibility = _release_dir(tmp_path)
    source_path = release_dir / "p105-source-manifest.json"
    alternate_path = release_dir / "alternate-source.json"
    alternate_path.write_bytes(source_path.read_bytes())
    rows_path = release_dir / "p105-release-qualified-rows.json"
    rows = _read_json(rows_path)
    rows["artifact_manifests"]["source"] = {
        "path": alternate_path.name,
        "sha256": _sha256_path(alternate_path),
        "referenced_by_benchmark_payload": True,
    }
    _write_json(rows_path, rows)

    completed = _verify_release(release_dir, receipt, registry, eligibility, tmp_path / "verification.json")

    assert completed.returncode == 1
    verification = _read_json(tmp_path / "verification.json")
    assert "release_source_artifact_path_mismatch" in verification["validation_error_codes"]


def test_release_root_binds_rows_and_extra_files_without_overwriting_directory_hash(tmp_path: Path) -> None:
    release_dir, receipt, _, registry, eligibility = _release_dir(tmp_path)
    first_output = tmp_path / "verification-first.json"
    first = _verify_release(release_dir, receipt, registry, eligibility, first_output)
    assert first.returncode == 0, first.stderr
    first_verification = _read_json(first_output)

    rows_path = release_dir / "p105-release-qualified-rows.json"
    rows = _read_json(rows_path)
    rows["non_authoritative_note"] = "row artifact changed"
    _write_json(rows_path, rows)
    second_output = tmp_path / "verification-second.json"
    second = _verify_release(release_dir, receipt, registry, eligibility, second_output)
    assert second.returncode == 0, second.stderr
    second_verification = _read_json(second_output)

    assert first_verification["release_root_sha256"] != second_verification["release_root_sha256"]
    assert first_verification["verified_release_artifact_root_sha256"] == second_verification["verified_release_artifact_root_sha256"]

    (release_dir / "extra.txt").write_text("extra\n", encoding="utf-8")
    third_output = tmp_path / "verification-third.json"
    third = _verify_release(release_dir, receipt, registry, eligibility, third_output)
    assert third.returncode == 0, third.stderr
    third_verification = _read_json(third_output)

    assert second_verification["release_root_sha256"] != third_verification["release_root_sha256"]


def _fleet_window(source: str, split: str, ordinal: int) -> str:
    family = {"database_fleet": "database", "queue_fleet": "queue", "deploy_fleet": "deploy"}[source]
    return f"p105-fleet-{family}-{split}-svc000-sample{ordinal:03d}"


def _fleet_service(source: str) -> str:
    family = {"database_fleet": "database", "queue_fleet": "queue", "deploy_fleet": "deploy"}[source]
    return f"p105.fleet.{family}.000"


def _write_fleet_runtime_bundle(
    base: Path,
    source: str,
    *,
    coverage_seconds: int = 10,
    include_unbound_raw_observation: bool = False,
) -> tuple[Path, Path]:
    base.mkdir(parents=True, exist_ok=True)
    split = "held_out"
    service = _fleet_service(source)
    raw_rows = [
        {
            "source_window_id": _fleet_window(source, split, ordinal),
            "monotonic_ns": ordinal * 5_000_000_000,
            "sample_ordinal": ordinal,
            "service": service,
            "split": split,
        }
        for ordinal in range(3)
    ]
    public_path = base / f"{source}-public.jsonl"
    public_path.write_text(
        "".join(json.dumps({"source_window_id": row["source_window_id"], "service": service, "split": split, "sample_ordinal": row["sample_ordinal"]}, sort_keys=True) + "\n" for row in raw_rows),
        encoding="utf-8",
    )
    if include_unbound_raw_observation:
        raw_rows.append(
            {
                "source_window_id": _fleet_window(source, split, 3),
                "monotonic_ns": 15_000_000_000,
                "sample_ordinal": 3,
                "service": service,
                "split": split,
            }
        )
    coverage = {
        "schema_version": f"p105.{source}.coverage.v1",
        "coverage_segments": [
            {
                "canonical_duration_seconds": coverage_seconds,
                "service": service,
                "split": split,
                "start_sample_ordinal": 0,
                "end_sample_ordinal": 2,
                "sample_count": 3,
            }
        ],
    }
    coverage_path = _write_json(base / f"{source}-coverage.json", coverage)
    raw_key = {
        "database_fleet": "sample_monotonic_observations",
        "queue_fleet": "raw_sample_observations",
        "deploy_fleet": "handler_observations",
    }[source]
    raw_attestation = {
        "kind": {
            "database_fleet": "actual_sqlite_pool",
            "queue_fleet": "actual_rabbitmq_docker",
            "deploy_fleet": "actual_threading_http_server",
        }[source],
        "capability": "test",
        "sqlite_connection_observations": [{"ok": True}],
        "broker_observation": {"ok": True},
        "handler_observation": {"ok": True},
        raw_key: raw_rows,
    }
    raw_path = _write_json(base / f"{source}-raw.json", raw_attestation)
    command_hash = hashlib.sha256(source.encode()).hexdigest()
    manifest = {
        "schema_version": f"p105.{source}.manifest.v1",
        "adapter_key": source,
        "runtime_attestation": {"kind": raw_attestation["kind"], "capability": "test"},
        "command_argv_sha256": command_hash,
        "program_version": "test",
        "artifact_paths": {
            "public_telemetry": public_path.name,
            "coverage": coverage_path.name,
            "provenance_hashes": f"{source}-provenance.json",
        },
    }
    manifest_path = _write_json(base / f"{source}-manifest.json", manifest)
    provenance = {
        "program_version": "test",
        "command_argv_sha256": command_hash,
        "artifact_hashes": {
            public_path.name: _sha256_path(public_path),
            coverage_path.name: _sha256_path(coverage_path),
            raw_path.name: _sha256_path(raw_path),
            manifest_path.name: _sha256_path(manifest_path),
        },
    }
    _write_json(base / f"{source}-provenance.json", provenance)
    return manifest_path, raw_path


def _verify_fleet_runtime(
    tmp_path: Path,
    *,
    queue_coverage_seconds: int = 10,
    queue_unbound_raw_observation: bool = False,
) -> subprocess.CompletedProcess[str]:
    registry = _write_json(tmp_path / "runtime-registry.json", {"schema_version": "p105.source-registry.v1", "sources": []})
    eligibility = _write_json(tmp_path / "runtime-eligibility.json", {"schema_version": "p105.source-eligibility.v1", "entries": []})
    manifests: dict[str, Path] = {}
    raw_attestations: dict[str, Path] = {}
    for source in ("database_fleet", "queue_fleet", "deploy_fleet"):
        manifest, raw = _write_fleet_runtime_bundle(
            tmp_path / source,
            source,
            coverage_seconds=queue_coverage_seconds if source == "queue_fleet" else 10,
            include_unbound_raw_observation=queue_unbound_raw_observation and source == "queue_fleet",
        )
        manifests[source] = manifest
        raw_attestations[source] = raw
    return subprocess.run(
        [
            sys.executable,
            str(VERIFY_SCRIPT),
            "--phase",
            "runtime",
            "--registry",
            str(registry),
            "--eligibility",
            str(eligibility),
            "--database-fleet-manifest",
            str(manifests["database_fleet"]),
            "--database-fleet-rerun-manifest",
            str(manifests["database_fleet"]),
            "--database-fleet-raw-attestation",
            str(raw_attestations["database_fleet"]),
            "--database-fleet-rerun-raw-attestation",
            str(raw_attestations["database_fleet"]),
            "--queue-fleet-manifest",
            str(manifests["queue_fleet"]),
            "--queue-fleet-rerun-manifest",
            str(manifests["queue_fleet"]),
            "--queue-fleet-raw-attestation",
            str(raw_attestations["queue_fleet"]),
            "--queue-fleet-rerun-raw-attestation",
            str(raw_attestations["queue_fleet"]),
            "--deploy-fleet-manifest",
            str(manifests["deploy_fleet"]),
            "--deploy-fleet-rerun-manifest",
            str(manifests["deploy_fleet"]),
            "--deploy-fleet-raw-attestation",
            str(raw_attestations["deploy_fleet"]),
            "--deploy-fleet-rerun-raw-attestation",
            str(raw_attestations["deploy_fleet"]),
            "--write-run-envelopes-dir",
            str(tmp_path / "envelopes"),
            "--output-json",
            str(tmp_path / "receipt.json"),
        ],
        text=True,
        capture_output=True,
        check=False,
    )


def test_runtime_receipt_contains_verifier_owned_fleet_coverage_segments(tmp_path: Path) -> None:
    completed = _verify_fleet_runtime(tmp_path)

    assert completed.returncode == 0, completed.stderr
    receipt = _read_json(tmp_path / "receipt.json")
    segments_by_source = receipt["verified_fleet_coverage_segments"]
    assert set(segments_by_source) == {"database_fleet", "queue_fleet", "deploy_fleet"}
    queue_segment = segments_by_source["queue_fleet"][0]
    assert queue_segment == {
        "bound_source_window_ids": [
            "p105-fleet-queue-held_out-svc000-sample000",
            "p105-fleet-queue-held_out-svc000-sample001",
            "p105-fleet-queue-held_out-svc000-sample002",
        ],
        "bound_source_window_ids_sha256": queue_segment["bound_source_window_ids_sha256"],
        "conservative_duration_seconds": 10,
        "end_sample_ordinal": 2,
        "family": "queue",
        "sample_count": 3,
        "service": "p105.fleet.queue.000",
        "source": "queue_fleet",
        "split": "held_out",
        "split_id": "held_out",
        "start_sample_ordinal": 0,
    }
    assert len(receipt["verified_fleet_coverage_segment_sha256"]["queue_fleet"]) == 64
    assert (tmp_path / "envelopes" / "queue-fleet-verified-coverage-segments.json").exists()


def test_runtime_fails_closed_when_harness_fleet_coverage_disagrees_with_raw_monotonic_recompute(tmp_path: Path) -> None:
    completed = _verify_fleet_runtime(tmp_path, queue_coverage_seconds=15)

    assert completed.returncode == 1
    receipt = _read_json(tmp_path / "receipt.json")
    assert "queue_fleet_coverage_segments_mismatch" in receipt["validation_error_codes"]


def test_runtime_fails_closed_when_raw_monotonic_observation_is_not_bound_to_public_telemetry(tmp_path: Path) -> None:
    completed = _verify_fleet_runtime(tmp_path, queue_unbound_raw_observation=True)

    assert completed.returncode == 1
    receipt = _read_json(tmp_path / "receipt.json")
    assert "queue_fleet_raw_monotonic_observation_unbound" in receipt["validation_error_codes"]


def test_canonical_rerun_comparison_excludes_independently_enveloped_raw_volatility(tmp_path: Path) -> None:
    manifests: list[Path] = []
    for run, raw_value in (("run-1", "volatile-a"), ("run-2", "volatile-b")):
        directory = tmp_path / run
        directory.mkdir()
        (directory / "public.jsonl").write_text('{"value":1}\n', encoding="utf-8")
        (directory / "raw.json").write_text(json.dumps({"monotonic": raw_value}) + "\n", encoding="utf-8")
        manifests.append(
            _write_json(
                directory / "manifest.json",
                {
                    "artifact_paths": {
                        "public_telemetry": "public.jsonl",
                        "raw_attestation": "raw.json",
                        "provenance_hashes": "provenance.json",
                    },
                    "schema_version": "p105.deploy.fleet_harness.v1",
                },
            )
        )

    assert verifier._compare_canonical_reruns(manifests[0], manifests[1], kind="deploy_fleet") == []

    (manifests[1].parent / "public.jsonl").write_text('{"value":2}\n', encoding="utf-8")
    assert verifier._compare_canonical_reruns(manifests[0], manifests[1], kind="deploy_fleet") == [
        "deploy_fleet_rerun_not_byte_identical"
    ]
