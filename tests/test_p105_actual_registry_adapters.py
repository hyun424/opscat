from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from scripts import verify_p105_source_expansion_artifacts as verifier

REGISTRY_SCRIPT = Path("scripts/build_p105_source_registry.py")

SCHEMA_ADAPTER_ARGS = [
    "--schema-adapter",
    "p32=p105.adapter.p32-replay.v1",
    "--schema-adapter",
    "p41=p105.adapter.p41-sources.v1",
    "--schema-adapter",
    "p44=p105.adapter.p44-reviewed-local.v1",
    "--schema-adapter",
    "dejavu_a1=p105.adapter.dejavu-a1-reviewed-local.v1",
    "--schema-adapter",
    "db_pool=p105.adapter.database-pool-harness.v1",
    "--schema-adapter",
    "queue=p105.adapter.rabbitmq-harness.v1",
    "--schema-adapter",
    "deploy=p105.adapter.threading-http-deploy-harness.v1",
]


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")
    return path


def _runtime_manifest(tmp_path: Path, *, source: str, schema: str, family: str, ledger_key: str, attestation_kind: str) -> Path:
    root = tmp_path / source
    public_rows = [
        {
            "schema_version": f"{schema}.public_telemetry.v1",
            "source_key": f"p105-{source}",
            "source_window_id": f"{source}-window-001",
            "partition_id": "held_out_test",
            "pre_label_partition": "held_out_test",
            "coverage_bucket_seconds": 60,
            "service": f"{source}-svc",
        }
    ]
    public_path = _write_jsonl(root / f"{source}-public.jsonl", public_rows)
    ledger_path = _write_json(
        root / f"{source}-private-ledger.json",
        {
            "public_artifact": False,
            "records": [
                {
                    "label_join_phase": "after_sampling_and_partition",
                    "label_positive": True,
                    "partition_id": "held_out_test",
                    "public_source_window_ids": [f"{source}-window-001"],
                    "source_window_id": f"{source}-window-001",
                }
            ],
            "schema_version": f"{schema}.private_ledger.v1",
        },
    )
    partitions_path = _write_json(
        root / f"{source}-partitions.json",
        {
            "label_blind": True,
            "partitioned_before_private_injection_ledger": True,
            "records": [{"source_window_id": f"{source}-window-001", "partition_id": "held_out_test"}],
            "schema_version": f"{schema}.pre_label_partition.v1",
        },
    )
    coverage_path = _write_json(
        root / f"{source}-coverage.json",
        {
            "actual_coverage": True,
            "coverage_method": "actual_observation_tick_union",
            "observed_intervals": {f"{source}-svc": [{"start_tick": 0, "end_tick": 60}]},
            "schema_version": f"{schema}.coverage.v1",
        },
    )
    raw_attestation_path = _write_json(
        root / f"{source}-runtime-attestation.raw.json",
        {"kind": attestation_kind, "observed_runtime": True, "schema_version": f"{schema}.raw_runtime_attestation.v1"},
    )
    artifact_hashes = {
        public_path.name: _sha256_path(public_path),
        ledger_path.name: _sha256_path(ledger_path),
        partitions_path.name: _sha256_path(partitions_path),
        coverage_path.name: _sha256_path(coverage_path),
    }
    provenance_path = _write_json(root / f"{source}-provenance-hashes.json", {"artifact_hashes": artifact_hashes, "schema_version": f"{schema}.provenance_hashes.v1"})
    manifest = {
        "artifact_hashes": artifact_hashes,
        "artifact_paths": {
            "coverage": coverage_path.name,
            "partitions": partitions_path.name,
            ledger_key: ledger_path.name,
            "provenance_hashes": provenance_path.name,
            "public_telemetry": public_path.name,
            "runtime_attestation": raw_attestation_path.name,
        },
        "authority": {
            "production_endpoint": False,
            "production_mutation": False,
            "release_counting_authority": False,
        },
        "canonical_command_argv": ["python", f"scripts/run_p105_{source}_harness.py", "--output-dir", "<OUTPUT_DIR>"],
        "command_argv_sha256": _json_sha256(["python", f"scripts/run_p105_{source}_harness.py", "--output-dir", "<OUTPUT_DIR>"]),
        "created_at": "2024-03-09T16:33:20Z",
        "program_version": f"p105.{schema}.v1",
        "public_telemetry_row_count": 1,
        "runtime_attestation": {"capability": attestation_kind, "kind": attestation_kind},
        "schema_version": f"p105.{schema}.harness_manifest.v1",
        "source_family": family,
    }
    return _write_json(root / f"{source}-harness-manifest.json", manifest)


def _manifests(tmp_path: Path) -> list[Path]:
    p32_fixture = _write_json(tmp_path / "p32-source.json", {"events": [{"risk": "queue_sla_breach"}]})
    p32 = _write_json(
        tmp_path / "p32_replay_pack.json",
        {
            "id": "p32-real-telemetry-replay-pack",
            "title": "P32 real telemetry-shaped replay pack",
            "sources": [{"id": "p32-datadog-disk-queue", "source": "datadog", "path": str(p32_fixture), "expected_risks": ["queue_sla_breach"]}],
        },
    )
    p41_fixture = _write_json(tmp_path / "p41-source.jsonl", {"line": "raw"})
    p41 = _write_json(
        tmp_path / "p41_sources.json",
        {
            "version": "p41-raw-sources-v1",
            "sources": [{"id": "p41-loghub-apache-raw", "family": "loghub", "path": str(p41_fixture), "expected_labels": ["normal", "deploy_error"]}],
        },
    )
    p44_records = _write_jsonl(
        tmp_path / "p44" / "p44-reviewed-local-public-records.jsonl",
        [
            {
                "source_key": "p44:nab:db",
                "source_window_id": "p44-window-001",
                "family": "database",
                "pre_label_partition": "held_out_test",
                "materialized_record_hash": "a" * 64,
            }
        ],
    )
    p44_ledger = _write_json(tmp_path / "p44" / "p105-private-scorer-label-ledger.json", {"public_artifact": False, "records": []})
    p44_partitions = _write_json(
        tmp_path / "p44" / "p44-reviewed-local-pre-label-partitions.json",
        {"pre_label_partitions": [{"source_window_id": "p44-window-001", "partition_id": "held_out_test"}]},
    )
    p44 = _write_json(
        tmp_path / "p44" / "p44-reviewed-local-manifest.json",
        {
            "schema_version": "p105.reviewed_p44_local_manifest.v3",
            "review_status": "reviewed-local",
            "review_redaction_status": "reviewed_redacted",
            "license": {"name": "Apache-2.0", "url": "https://example.invalid/apache", "citation_text": "P44 citation", "redistribution_status": "derived-redacted-only"},
            "privacy": {"review_status": "reviewed-local", "reviewer_id": "p105-reviewer", "reviewed_at": "2024-03-09T16:33:20Z", "redaction_status": "reviewed_redacted", "notes": "reviewed"},
            "private_ledger_ref": {"path": p44_ledger.name, "sha256": _sha256_path(p44_ledger), "public_artifact": False},
            "pre_label_partitions_path": {"path": p44_partitions.name, "sha256": _sha256_path(p44_partitions)},
            "raw_sources": [
                {
                    "source_key": "p44:nab:db",
                    "source_dataset": "NAB",
                    "path": str(p44_records),
                    "source_content_hash": _sha256_path(p44_records),
                    "license_name": "Apache-2.0",
                    "license_url": "https://example.invalid/apache",
                    "citation_text": "P44 citation",
                    "privacy_review_status": "reviewed-local",
                    "redaction_decisions": ["drop_private_label"],
                    "family_proxy_mapping": {"family": "database", "mapping_review_status": "reviewed_supported", "evidence": ["metric semantics"]},
                }
            ],
            "reviewed_records": [
                {
                    "source_key": "p44:nab:db",
                    "source_window_id": "p44-window-001",
                    "materialized_record_hash": "a" * 64,
                    "pre_label_partition_id": "held_out_test",
                }
            ],
            "sources": [{"source_key": "p44:nab:db", "family": "database", "local_materialized_path": str(p44_records), "local_source_hash": _sha256_path(p44_records)}],
        },
    )
    dejavu = _write_json(
        tmp_path / "dejavu" / "p105-dejavu-a1-reviewed-local-manifest.json",
        {
            "adapter_or_parser_version": "p105.dejavu_a1.reviewed_local.v1",
            "command_argv": ["materialize-dejavu"],
            "created_at": "2024-03-09T16:33:20Z",
            "license": {"name": "CC-BY", "url": "https://example.invalid/dejavu", "citation_text": "DejaVu citation", "redistribution_status": "derived-redacted-only"},
            "privacy": {
                "review_status": "reviewed-local",
                "reviewer_id": "p105-reviewer",
                "reviewed_at": "2024-03-09T16:33:20Z",
                "redaction_status": "reviewed_redacted",
                "faults_csv_private_truth": True,
            },
            "review_status": "reviewed-local",
            "source_hashes": {"metrics_csv_sha256": "b" * 64, "faults_csv_sha256": "c" * 64, "graph_yml_sha256": "d" * 64},
            "source_insufficiency": {"family": "database", "status": "source_insufficient", "reason": "a1_actual_coverage_below_two_service_day_floor"},
        },
    )
    return [
        p32,
        p41,
        p44,
        dejavu,
        _runtime_manifest(tmp_path, source="db-pool", schema="database.pool", family="database", ledger_key="private_saturation_ledger", attestation_kind="actual_sqlite_pool"),
        _runtime_manifest(tmp_path, source="queue", schema="queue", family="queue", ledger_key="private_injection_ledger", attestation_kind="actual_rabbitmq_docker"),
        _runtime_manifest(tmp_path, source="deploy", schema="deploy", family="deploy", ledger_key="private_injection_ledger", attestation_kind="actual_threading_http_server"),
    ]


def _ledger(path: Path, reviewed_manifests: list[Path]) -> Path:
    decisions = []
    for manifest_path in reviewed_manifests:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        source_keys = ["p44:nab:db"] if "p44" in manifest_path.parts else [str(manifest.get("source_key") or f"p105-{manifest_path.parent.name}")]
        for source_key in source_keys:
            decisions.append(
                {
                    "source_key": source_key,
                    "reviewer_id": "p105-reviewer",
                    "reviewed_at": "2024-03-09T16:33:20Z",
                    "decision": "approved",
                    "license_decision": "approved",
                    "privacy_decision": "approved",
                    "family_authority_decision": "approved",
                    "source_manifest_sha256": _sha256_path(manifest_path),
                    "review_signature_sha256": _json_sha256({"source_key": source_key, "decision": "approved"}),
                }
            )
    return _write_json(path, {"schema_version": "p105.source-review-ledger.v1", "decisions": decisions})


def _run_registry(tmp_path: Path, manifests: list[Path], ledger: Path) -> tuple[subprocess.CompletedProcess[str], dict[str, Any], dict[str, Any]]:
    registry = tmp_path / "registry.json"
    eligibility = tmp_path / "eligibility.json"
    command = [
        sys.executable,
        str(REGISTRY_SCRIPT),
        *[item for manifest in manifests for item in ("--candidate-manifest", str(manifest))],
        "--review-ledger",
        str(ledger),
        "--output-registry",
        str(registry),
        "--output-eligibility",
        str(eligibility),
        "--created-at",
        "2024-03-09T16:33:20Z",
        "--schema-version",
        "p105.source-registry.v1",
        "--fail-on-unknown-source-schema",
        *SCHEMA_ADAPTER_ARGS,
    ]
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    registry_payload = json.loads(registry.read_text(encoding="utf-8")) if registry.exists() else {}
    eligibility_payload = json.loads(eligibility.read_text(encoding="utf-8")) if eligibility.exists() else {}
    return completed, registry_payload, eligibility_payload


def test_actual_root_schema_adapters_preserve_provenance_and_bindings(tmp_path: Path) -> None:
    manifests = _manifests(tmp_path)
    reviewed = [path for path in manifests if path.name not in {"p32_replay_pack.json", "p41_sources.json", "p105-dejavu-a1-reviewed-local-manifest.json"}]
    ledger = _ledger(tmp_path / "ledger.json", reviewed)

    completed, registry, eligibility = _run_registry(tmp_path, manifests, ledger)

    assert completed.returncode == 0, completed.stderr
    sources = {source["source_key"]: source for source in registry["sources"]}
    assert set(sources) >= {"p32-datadog-disk-queue", "p41-loghub-apache-raw", "p44:nab:db", "p105-db-pool", "p105-queue", "p105-deploy", "dejavu-a1-reviewed-local"}
    assert sources["p44:nab:db"]["license"]["name"] == "Apache-2.0"
    assert sources["p44:nab:db"]["privacy"]["redaction_decisions"] == ["drop_private_label"]
    assert sources["p44:nab:db"]["private_ledger_ref"]["public_artifact"] is False
    assert sources["p105-queue"]["source_family"] == "queue"
    assert sources["p105-queue"]["runtime_attestation"]["kind"] == "actual_rabbitmq_docker"
    assert sources["p105-queue"]["authority"]["release_counting_authority"] is False
    assert sources["p105-queue"]["source_artifacts"]["public_telemetry"]["sha256"] == sources["p105-queue"]["source_content_hashes"][0]["sha256"]
    assert sources["p105-db-pool"]["source_artifacts"]["private_saturation_ledger"]["public_artifact"] is False
    assert sources["p105-deploy"]["source_artifacts"]["coverage"]["actual_coverage"] is True

    entries = {(entry["source_key"], entry["source_window_id"]): entry for entry in eligibility["entries"]}
    assert entries[("p44:nab:db", "p44-window-001")]["pre_label_partition_id"] == "held_out_test"
    assert entries[("p105-queue", "queue-window-001")]["private_ledger_path"].endswith("queue-private-ledger.json")
    assert entries[("p105-queue", "queue-window-001")]["coverage_interval_ids"]
    assert entries[("p105-queue", "queue-window-001")]["eligible_for_release_floor"] is True
    assert entries[("p32-datadog-disk-queue", "p32-datadog-disk-queue")]["eligible_for_release_floor"] is False
    assert entries[("p41-loghub-apache-raw", "p41-loghub-apache-raw")]["unsupported_family_reason"] == "unreviewed_source"
    assert entries[("dejavu-a1-reviewed-local", "dejavu-a1-reviewed-local")]["unsupported_family_reason"] == "unreviewed_source"
    assert verifier._validate_no_source_counting_authority("registry", registry) == []
    assert verifier._validate_no_source_counting_authority("eligibility", eligibility) == []
    assert all("counting_rows" not in entry and "counting_coverage_seconds" not in entry for entry in eligibility["entries"])


def test_actual_runtime_adapter_rejects_manifest_hash_mismatch(tmp_path: Path) -> None:
    manifests = _manifests(tmp_path)
    reviewed = [path for path in manifests if path.name == "queue-harness-manifest.json"]
    ledger = _ledger(tmp_path / "ledger.json", reviewed)
    payload = json.loads(ledger.read_text(encoding="utf-8"))
    payload["decisions"][0]["source_manifest_sha256"] = "0" * 64
    _write_json(ledger, payload)

    completed, _, _ = _run_registry(tmp_path, reviewed, ledger)

    assert completed.returncode != 0
    assert "source manifest hash mismatch" in completed.stderr


def test_actual_runtime_adapter_rejects_missing_required_artifact(tmp_path: Path) -> None:
    manifests = _manifests(tmp_path)
    queue_manifest = next(path for path in manifests if path.name == "queue-harness-manifest.json")
    manifest = json.loads(queue_manifest.read_text(encoding="utf-8"))
    manifest["artifact_paths"]["coverage"] = "missing-coverage.json"
    queue_manifest = _write_json(queue_manifest, manifest)
    ledger = _ledger(tmp_path / "ledger.json", [queue_manifest])

    completed, _, _ = _run_registry(tmp_path, [queue_manifest], ledger)

    assert completed.returncode != 0
    assert "artifact path is missing" in completed.stderr


def test_actual_runtime_adapter_rejects_empty_public_telemetry(tmp_path: Path) -> None:
    manifests = _manifests(tmp_path)
    queue_manifest = next(path for path in manifests if path.name == "queue-harness-manifest.json")
    manifest = json.loads(queue_manifest.read_text(encoding="utf-8"))
    public_path = queue_manifest.parent / manifest["artifact_paths"]["public_telemetry"]
    public_path.write_text("", encoding="utf-8")
    manifest["artifact_hashes"][public_path.name] = _sha256_path(public_path)
    queue_manifest = _write_json(queue_manifest, manifest)
    ledger = _ledger(tmp_path / "ledger.json", [queue_manifest])

    completed, _, _ = _run_registry(tmp_path, [queue_manifest], ledger)

    assert completed.returncode != 0
    assert "public telemetry has no source windows" in completed.stderr


def test_actual_deploy_manifest_uses_verifier_compatibility_schema_and_adapter_family(tmp_path: Path) -> None:
    manifest_path = _runtime_manifest(
        tmp_path,
        source="deploy",
        schema="deploy",
        family="deploy",
        ledger_key="private_injection_ledger",
        attestation_kind="actual_threading_http_server",
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("schema_version")
    manifest.pop("source_family")
    manifest["source_key"] = "p105-isolated-local-deploy-canary"
    manifest["verifier_compatibility"] = {
        "manifest_schema": "p105.deploy.harness.manifest.v1",
        "raw_attestation_separated": True,
    }
    manifest_path = _write_json(manifest_path, manifest)
    ledger = _ledger(tmp_path / "ledger.json", [manifest_path])

    completed, registry, eligibility = _run_registry(tmp_path, [manifest_path], ledger)

    assert completed.returncode == 0, completed.stderr
    source = registry["sources"][0]
    assert source["source_key"] == "p105-isolated-local-deploy-canary"
    assert source["root_schema_version"] == "p105.deploy.harness.manifest.v1"
    assert source["source_family"] == "deploy"
    assert eligibility["entries"][0]["eligible_for_release_floor"] is True
