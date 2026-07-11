from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, cast

import pytest

from app.services import p122_release_evidence as release
from app.services.p110_evaluation import stable_hash
from app.services.p121_signals import zero_authority_counters
from app.services.p122_release_evidence import _authority_zero, _source_hashes, produce_p122_release_evidence, validate_p122_release_evidence

_CRASH_STAGES = (
    "install",
    "demo_startup",
    "incident_ingest",
    "evidence_request",
    "decision",
    "approval",
    "validation",
    "rollback",
    "replay_write",
    "eval_write",
    "release_evidence_write",
    "report_write",
)
_STAGE_OPERATIONS = {
    "install": "package_install",
    "demo_startup": "demo_bootstrap",
    "incident_ingest": "incident_record_ingest",
    "evidence_request": "evidence_request_dispatch",
    "decision": "bounded_decision_commit",
    "approval": "approval_receipt_commit",
    "validation": "validation_result_commit",
    "rollback": "rollback_result_commit",
    "replay_write": "replay_artifact_commit",
    "eval_write": "frozen_eval_commit",
    "release_evidence_write": "release_evidence_commit",
    "report_write": "performance_report_commit",
}


def _self_hashed(payload: dict[str, Any]) -> dict[str, Any]:
    payload["report_hash"] = stable_hash(payload)
    return payload


def _valid_performance_report(*, counters: dict[str, int], iterations: int) -> dict[str, Any]:
    expected = {
        "incident_records": iterations,
        "audit_records": iterations * 4,
        "timeline_records": iterations * 4,
        "replay_records": iterations,
        "authority_records": iterations,
    }
    crash_logs = [
        {
            "correlation_id": f"p122-crash-{index:02d}-{stage}",
            "event": "release_stage_crash_recovered",
            "level": "INFO",
            "stage": stage,
            "timestamp_monotonic_seconds": float(index + 1),
        }
        for index, stage in enumerate(_CRASH_STAGES)
    ]
    report: dict[str, Any] = {
        "schema_version": "p122.performance_soak.v2",
        "iterations": iterations,
        "elapsed_seconds": 10.0,
        "duration_seconds": 10.0,
        "cpu_seconds": 5.0,
        "cpu_utilization_ratio": 0.5,
        "events_per_second": iterations * 4 / 10.0,
        "replays_per_second": iterations / 10.0,
        "expected_records": expected,
        "observed_records": dict(expected),
        "lost_incident_records": 0,
        "lost_audit_records": 0,
        "lost_timeline_records": 0,
        "lost_replay_records": 0,
        "lost_authority_records": 0,
        "unique_replay_files": iterations,
        "deterministic_content_hash_count": 1,
        "max_rss_kib": 1,
        "context": {"python": "3.14.0", "platform": "test", "machine": "test", "cpu_count": 1},
        "timings_seconds": {
            "install": 1.0,
            "install_method": "wheel-extract",
            "cold_start": 0.1,
            "demo_total": 2.0,
            "demo_min": 0.001,
            "demo_max": 0.01,
            "demo_mean": 0.002,
            "demo_samples": iterations,
        },
        "storage_envelope": {
            "total_bytes": 100_000,
            "file_count": 100,
            "largest_file_bytes": 1_000,
            "bytes_per_iteration": 100.0,
            "scope": "workdir including install, record, WAL, and crash-replay artifacts",
        },
        "release_stage_crash_inventory": list(_CRASH_STAGES),
        "release_stage_crash_replay": {
            "schema_version": "p122.release_stage_crash_replay.v1",
            "protocol": "multiprocessing-spawn-exit-restart",
            "point_count": 12,
            "injected_count": 12,
            "recovered_count": 12,
            "observed_restart_receipt_count": 12,
            "verified": True,
            "points": [
                {
                    "stage": stage,
                    "operation": _STAGE_OPERATIONS[stage],
                    "operation_adapter": release._P122_STAGE_ADAPTERS[stage][0],
                    "output_schema": release._P122_STAGE_ADAPTERS[stage][1],
                    "correlation_id": f"p122-crash-{index:02d}-{stage}",
                    "crash_injected": True,
                    "crash_exit_code": 86,
                    "recovery_exit_code": 0,
                    "crash_worker_pid": 1000 + (index * 2),
                    "recovery_worker_pid": 1001 + (index * 2),
                    "recovered": True,
                    "restart_verified": True,
                    "restart_count": 1,
                    "pending_record_hash": "sha256:" + (f"{index + 1:064x}"[-64:]),
                    "restart_receipt_hash": "sha256:" + (f"{index + 101:064x}"[-64:]),
                    "precommit_hash": "sha256:" + (f"{index + 201:064x}"[-64:]),
                    "output_hash": "sha256:" + (f"{index + 201:064x}"[-64:]),
                    "output_ref": f"/tmp/{index:02d}-{stage}/committed/{release._P122_STAGE_ADAPTERS[stage][2]}",
                    "adapter_invoked": True,
                    "post_restart_validation": True,
                    "pending_ref": f"/tmp/{index:02d}-{stage}/pending.json",
                    "restart_receipt_ref": f"/tmp/{index:02d}-{stage}/restart-receipt.json",
                    "recovered_at_seconds": float(index + 1),
                }
                for index, stage in enumerate(_CRASH_STAGES)
            ],
        },
        "upstream_executed_crash_replay": {
            "source": "app.services.p121_execution.prove_p121_restart_recovery",
            "proof_hash": "sha256:a2d204f4ee9b964cf133333b5d50fede6141a61af1133654fd681bd92625de91",
            "point_count": 15,
            "replayed_count": 15,
            "pending_rollback_replayed": True,
            "pending_rollback_count_after_replay": 0,
        },
        "observability": {
            "health": {"status": "healthy", "local_fixture": True},
            "readiness": {
                "ready": True,
                "checks": {
                    "authority_rejection_observed": True,
                    "record_loss_zero": True,
                    "release_crashes_recovered": True,
                },
            },
            "metrics": {
                "iterations_total": iterations,
                "records_observed_total": iterations * 11,
                "records_lost_total": 0,
                "release_stage_crashes_injected_total": 12,
                "release_stage_crashes_recovered_total": 12,
                "authority_rejections_total": 1,
            },
            "correlated_logs": [
                *crash_logs,
                {
                    "correlation_id": "p122-authority-rejection-00",
                    "event": "authority_rejected",
                    "level": "WARNING",
                    "reason": "production_like_demo_configuration_denied",
                    "timestamp_monotonic_seconds": 10.0,
                },
            ],
            "diagnostics": {
                "crash_replay_artifact_root": "/tmp",
                "record_artifact_root": "/tmp",
                "redacted_sample": {"api_key": "[REDACTED]", "message": "Authorization: Bearer [REDACTED]", "scope": "local-fixture"},
                "redaction_verified": True,
                "replay_inspectable": True,
            },
            "authority_rejection": {
                "correlation_id": "p122-authority-rejection-00",
                "reason": "production_like_demo_configuration_denied",
                "observed": True,
                "fail_closed": True,
                "output_created": False,
            },
        },
        "authority_counters": counters,
        "scope_limit": "local fixture performance only; not production capacity evidence",
    }
    report["semantic_binding"] = release._performance_semantic_projection(report)["projection_hash"]
    return _self_hashed(report)


def _release_with_reports(
    monkeypatch: pytest.MonkeyPatch,
    *,
    iterations: int = 1000,
    docs_valid: bool = True,
    migration_valid: bool = True,
) -> dict[str, Any]:
    counters = zero_authority_counters()
    reports: dict[str, dict[str, Any]] = {}
    for phase, keys in release._UPSTREAM_AUTHORITY_KEYS.items():
        upstream: dict[str, Any] = {
            "release_status": "ready",
            "release_evidence_hash": f"sha256:p{phase}",
            "authority": {"counters": {key: 0 for key in keys}},
        }
        if phase == 116:
            upstream["gates"] = {"ready": True}
            upstream["acceptance_gates"] = {"ready": True}
        reports[f"p{phase}/release-evidence.json"] = upstream
    reports.update(
        {
            "p122/security-report.json": {"status": "pass", "severity_counts": {}, "report_hash": "sha256:security"},
            "p122/vulnerability-audit.json": {"status": "pass", "vulnerability_count": 0, "uv_lock_hash": "sha256:uv", "report_hash": "sha256:vulnerability"},
            "p122/sbom.json": {"bomFormat": "CycloneDX", "components": [{"name": "demo"}]},
            "p122/license-inventory.json": {"components": [{"name": "demo"}], "findings": []},
            "p122/performance-soak.json": _valid_performance_report(counters=counters, iterations=iterations),
            "p122/package-checksums.json": {"opscat-0.2.0-py3-none-any.whl": "sha256:wheel", "opscat-0.2.0.tar.gz": "sha256:sdist"},
            "p122/reproducible-build.json": {
                "byte_reproducible": True,
                "checksums": {"opscat-0.2.0-py3-none-any.whl": "sha256:wheel", "opscat-0.2.0.tar.gz": "sha256:sdist"},
                "report_hash": "sha256:build",
            },
            "p122/clean-install.json": _self_hashed(
                {
                    "schema_version": "p122.clean_install.v1",
                    "wheel_hash": "sha256:wheel",
                    "install_exit_code": 0,
                    "demo_exit_code": 0,
                    "contracts_exit_code": 0,
                    "uninstall_exit_code": 0,
                    "import_residue_after_uninstall": False,
                    "authority_counters": counters,
                    "exact_nonlocal_authority_zero": True,
                }
            ),
            "p122/docs-verification.json": _self_hashed(
                {
                    "schema_version": "p122.docs_verification.v1",
                    "checked_docs": [str(path) for path in release._P122_DOCS] + ["docs/security-threat-model.md"],
                    "broken_links": [],
                    "missing_troubleshooting": [],
                    "missing_schema": [],
                    "missing_examples": [],
                    "invalid_json_examples": [],
                    "stale_script_examples": [],
                    "unbounded_claims": [],
                    "missing_required_claims": [],
                    "valid": docs_valid,
                }
            ),
            "p122/migration-compatibility.json": _self_hashed(
                {
                    "schema_version": "p122.migration_compatibility.v1",
                    "source_version": "0.1.9",
                    "target_version": "0.2.0",
                    "fixture_upgrade_executed": True,
                    "backup_created": True,
                    "restore_verified": True,
                    "rollback_verified": True,
                    "compatibility_verified": migration_valid,
                    "authority_key_set_exact": True,
                    "authority_values_int_zero": True,
                    "expected_authority_keys": list(release.P121_AUTHORITY_COUNTER_KEYS),
                    "authority_counters": counters,
                    "artifacts": {"fixture": "fixture", "backup": "backup", "upgraded": "upgraded", "restored": "restored", "rollback": "rollback"},
                }
            ),
            "p122/independent-review.json": {},
        }
    )

    monkeypatch.setattr(release, "_read", lambda path: reports.get("/".join(path.parts[-2:]), {}))
    file_hashes = {
        "uv.lock": "sha256:uv",
        "opscat-0.2.0-py3-none-any.whl": "sha256:wheel",
        "opscat-0.2.0.tar.gz": "sha256:sdist",
    }
    monkeypatch.setattr(release, "_file_hash", lambda path: file_hashes.get(path.name, "sha256:source"))
    monkeypatch.setattr(release, "_source_hashes", lambda root: {"source": "sha256:source"})
    monkeypatch.setattr(release, "_source_manifest", lambda root: ("source",))
    monkeypatch.setattr(release, "_security_report_valid", lambda report, **kwargs: True)
    monkeypatch.setattr(release, "_vulnerability_audit_valid", lambda report, **kwargs: True)
    monkeypatch.setattr(release, "_sbom_valid", lambda report, **kwargs: True)
    monkeypatch.setattr(release, "_license_inventory_valid", lambda report, **kwargs: True)
    monkeypatch.setattr(release, "_docs_verification_valid", lambda report, **kwargs: report.get("valid") is True and release._report_hash_current(report))
    monkeypatch.setattr(release, "_performance_artifacts_valid", lambda *args, **kwargs: True)
    monkeypatch.setattr(release, "_crash_point_refs_valid", lambda *args, **kwargs: True)
    return produce_p122_release_evidence(reviewer_id="reviewer", builder_id="builder", root=Path("/repo"))


def test_release_evidence_keeps_public_claim_bounded() -> None:
    evidence = produce_p122_release_evidence(reviewer_id="reviewer", builder_id="builder")
    assert evidence["product_claim"] == "production-grade packaging practices with local/mock/sandbox qualification"
    assert "operator replacement" in evidence["public_limitation"]
    assert isinstance(evidence["authority"]["exact_nonlocal_authority_zero"], bool)


def test_self_review_fails_closed() -> None:
    evidence = produce_p122_release_evidence(reviewer_id="same", builder_id="same")
    assert evidence["release_status"] == "p122_blocked"
    assert evidence["gates"]["distinct_reviewer"] is False


def test_authority_counter_validation_requires_exact_p121_key_set() -> None:
    valid = {"authority": {"counters": zero_authority_counters()}}
    assert _authority_zero(valid) is True

    missing = copy.deepcopy(valid)
    missing["authority"]["counters"].pop(next(iter(zero_authority_counters())))
    assert _authority_zero(missing) is False

    extra = copy.deepcopy(valid)
    extra["authority"]["counters"]["unexpected_zero"] = 0
    assert _authority_zero(extra) is False

    boolean = copy.deepcopy(valid)
    boolean["authority"]["counters"][next(iter(zero_authority_counters()))] = False
    assert _authority_zero(boolean) is False


def test_release_validation_rejects_tampered_hash_fields_without_rehash_escape() -> None:
    evidence = produce_p122_release_evidence(reviewer_id="reviewer", builder_id="builder")
    tampered = copy.deepcopy(evidence)
    tampered["security_report_hash"] = "sha256:" + ("0" * 64)
    tampered["release_evidence_hash"] = tampered["release_evidence_hash"]

    result = validate_p122_release_evidence(tampered)

    assert result["valid"] is False
    assert result["checks"]["all_fields_current"] is False


def test_release_validation_rejects_review_ticket_matrix_tampering() -> None:
    evidence = produce_p122_release_evidence(reviewer_id="reviewer", builder_id="builder")
    tampered = copy.deepcopy(evidence)
    tampered["review"]["artifact"] = {
        "verdict": "PASS",
        "reviewer_id": "reviewer",
        "ticket_matrix": {"P122-008": "PASS"},
        "self_hash": "sha256:" + ("0" * 64),
    }

    result = validate_p122_release_evidence(tampered)

    assert result["valid"] is False
    assert result["checks"]["independent_review_current"] is False


def test_source_manifest_expands_all_p122_and_claim_inputs_without_allowlist_omissions(tmp_path: Path) -> None:
    expected = (
        ".github/workflows/new-security.yml",
        "app/public_contracts.py",
        "app/services/local_safe_subprocess_runner.py",
        "app/services/p121_crash_claim.py",
        "docs/install.md",
        "docs/operations/p122-new-report.md",
        "docs/tickets/p122/P122-009-adversarial.md",
        "scripts/run_p122_new_gate.py",
        "scripts/verify.sh",
        "tests/test_p122_new_gate.py",
    )
    for name in expected:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(name, encoding="utf-8")

    hashes = _source_hashes(tmp_path)

    assert set(expected) <= set(hashes)


def test_source_manifest_excludes_workstation_and_ignored_metadata(tmp_path: Path) -> None:
    included = tmp_path / ".github/workflows/security.yml"
    ignored = (
        tmp_path / ".github/.DS_Store",
        tmp_path / ".github/workflows/._security.yml",
        tmp_path / ".github/.idea/workspace.xml",
    )
    included.parent.mkdir(parents=True, exist_ok=True)
    included.write_text("name: security\n", encoding="utf-8")
    for path in ignored:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("workstation metadata\n", encoding="utf-8")

    manifest = set(release._source_manifest(tmp_path))

    assert ".github/workflows/security.yml" in manifest
    assert not ({path.relative_to(tmp_path).as_posix() for path in ignored} & manifest)


def test_source_manifest_closes_direct_imports_contract_owners_and_claimed_runtime_inputs(tmp_path: Path) -> None:
    sources = {
        "scripts/run_p122_probe.py": "from app.services.direct_dependency import VALUE\n",
        "app/services/direct_dependency.py": "VALUE = 1\n",
        "app/public_contracts.py": 'CONTRACTS = [{"owner_module": "app.services.claimed_owner"}]\n',
        "app/services/claimed_owner.py": "OWNER = True\n",
        "docker-compose.yml": "services: {}\n",
        "config/opscat.local.example.json": "{}\n",
    }
    for name, content in sources.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    before = _source_hashes(tmp_path)

    assert {
        "app/services/direct_dependency.py",
        "app/services/claimed_owner.py",
        "docker-compose.yml",
        "config/opscat.local.example.json",
    } <= set(before)
    tmp_path.joinpath("app/services/direct_dependency.py").write_text("VALUE = 2\n", encoding="utf-8")
    after = _source_hashes(tmp_path)
    assert before["app/services/direct_dependency.py"] != after["app/services/direct_dependency.py"]


def test_real_source_manifest_contains_claimed_transitive_dependencies() -> None:
    manifest = set(release._source_manifest(Path.cwd()))
    assert {
        "app/services/p110_evaluation.py",
        "app/services/p120_governance.py",
        "app/services/redaction.py",
        "app/config.py",
        "app/services/p115_action_contract.py",
        "app/services/p115_ontology.py",
        "app/services/p119_attribution.py",
        "docker-compose.yml",
        "config/opscat.local.example.json",
    } <= manifest


def test_release_performance_docs_and_migration_gates_require_exact_current_reports(monkeypatch: pytest.MonkeyPatch) -> None:
    evidence = _release_with_reports(monkeypatch)
    assert evidence["gates"]["performance_soak_complete"] is True
    assert evidence["gates"]["docs_verification_passed"] is True
    assert evidence["gates"]["migration_compatibility_passed"] is True

    short = _release_with_reports(monkeypatch, iterations=999)
    assert short["gates"]["performance_soak_complete"] is False
    invalid_docs = _release_with_reports(monkeypatch, docs_valid=False)
    assert invalid_docs["gates"]["docs_verification_passed"] is False
    invalid_migration = _release_with_reports(monkeypatch, migration_valid=False)
    assert invalid_migration["gates"]["migration_compatibility_passed"] is False


@pytest.mark.parametrize("report_name,gate_name", [("performance-soak.json", "performance_soak_complete"), ("migration-compatibility.json", "migration_compatibility_passed")])
def test_release_report_authority_gates_reject_bool_missing_extra_and_nonzero(
    monkeypatch: pytest.MonkeyPatch, report_name: str, gate_name: str
) -> None:
    evidence = _release_with_reports(monkeypatch)
    original_read = release._read
    for mutation in ("bool", "missing", "extra", "nonzero"):
        def tampered_read(path: Path, *, mutation: str = mutation) -> dict[str, object]:
            report = copy.deepcopy(original_read(path))
            if path.name == report_name:
                counters = report["authority_counters"]
                assert isinstance(counters, dict)
                key = next(iter(zero_authority_counters()))
                if mutation == "bool":
                    counters[key] = False
                elif mutation == "missing":
                    counters.pop(key)
                elif mutation == "extra":
                    counters["unexpected"] = 0
                else:
                    counters[key] = 1
                report["report_hash"] = stable_hash({key: value for key, value in report.items() if key != "report_hash"})
            return report

        monkeypatch.setattr(release, "_read", tampered_read)
        tampered = produce_p122_release_evidence(reviewer_id="reviewer", builder_id="builder", root=Path("/repo"))
        assert tampered["gates"][gate_name] is False
        monkeypatch.setattr(release, "_read", original_read)

    assert evidence["gates"][gate_name] is True


@pytest.mark.parametrize(
    "field",
    [
        "security_report_hash",
        "vulnerability_audit_hash",
        "sbom_hash",
        "license_inventory_hash",
        "docs_verification_hash",
        "migration_report_hash",
        "performance_report_hash",
    ],
)
def test_release_validation_rebinds_new_report_hash_fields_even_after_outer_rehash(monkeypatch: pytest.MonkeyPatch, field: str) -> None:
    evidence = _release_with_reports(monkeypatch)
    evidence[field] = "sha256:" + ("0" * 64)
    evidence["release_evidence_hash"] = stable_hash({key: value for key, value in evidence.items() if key != "release_evidence_hash"})

    result = validate_p122_release_evidence(evidence, root=Path("/repo"))

    assert result["checks"]["self_hash_current"] is True
    assert result["checks"]["all_fields_current"] is False


def test_release_validation_uses_embedded_crash_receipts_without_recapture(monkeypatch: pytest.MonkeyPatch) -> None:
    evidence = _release_with_reports(monkeypatch)

    def reject_recapture(*args: object, **kwargs: object) -> dict[str, object]:
        raise AssertionError("release validation attempted to recapture creator-local receipts")

    monkeypatch.setattr(release, "_capture_performance_receipts", reject_recapture)
    result = validate_p122_release_evidence(evidence, root=Path("/repo"))

    assert result["checks"]["all_fields_current"] is True


@pytest.mark.parametrize(
    "mutation",
    [
        "crash_stage",
        "timing_samples",
        "storage_total",
        "expected_denominator",
        "observed_denominator",
        "health",
        "readiness",
        "metrics",
        "correlated_logs",
        "diagnostic_redaction",
        "authority_rejection",
        "p121_proof",
    ],
)
def test_performance_gate_rejects_semantic_self_rehash_forgery(monkeypatch: pytest.MonkeyPatch, mutation: str) -> None:
    _release_with_reports(monkeypatch)
    original_read = release._read

    def tampered_read(path: Path) -> dict[str, object]:
        report = copy.deepcopy(original_read(path))
        if path.name != "performance-soak.json":
            return report
        if mutation == "crash_stage":
            report["release_stage_crash_inventory"][0] = "not_install"
        elif mutation == "timing_samples":
            report["timings_seconds"]["demo_samples"] = 999
        elif mutation == "storage_total":
            report["storage_envelope"]["total_bytes"] = 0
        elif mutation == "expected_denominator":
            report["expected_records"]["audit_records"] = 3999
        elif mutation == "observed_denominator":
            report["observed_records"]["replay_records"] = 999
        elif mutation == "health":
            report["observability"]["health"]["status"] = "degraded"
        elif mutation == "readiness":
            report["observability"]["readiness"]["ready"] = False
        elif mutation == "metrics":
            report["observability"]["metrics"]["records_observed_total"] = 10_999
        elif mutation == "correlated_logs":
            report["observability"]["correlated_logs"].pop()
        elif mutation == "diagnostic_redaction":
            report["observability"]["diagnostics"]["redaction_verified"] = False
        elif mutation == "authority_rejection":
            report["observability"]["authority_rejection"]["fail_closed"] = False
        else:
            report["upstream_executed_crash_replay"]["point_count"] = 14
        report["report_hash"] = stable_hash({key: value for key, value in report.items() if key != "report_hash"})
        return report

    monkeypatch.setattr(release, "_read", tampered_read)
    evidence = produce_p122_release_evidence(reviewer_id="reviewer", builder_id="builder", root=Path("/repo"))

    assert evidence["gates"]["performance_soak_complete"] is False


def _stored_p122_report(name: str) -> dict[str, Any]:
    value = json.loads(Path("evals/p122", name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def _rehash_report(report: dict[str, Any]) -> None:
    report["report_hash"] = stable_hash({key: value for key, value in report.items() if key != "report_hash"})


def test_supply_chain_reports_require_exact_current_schemas_inventories_and_hashes() -> None:
    root = Path.cwd()
    security = _stored_p122_report("security-report.json")
    vulnerability = _stored_p122_report("vulnerability-audit.json")
    sbom = _stored_p122_report("sbom.json")
    licenses = _stored_p122_report("license-inventory.json")
    clean_install = _stored_p122_report("clean-install.json")

    assert release._security_report_valid(security, root=root)
    assert release._vulnerability_audit_valid(vulnerability, root=root, clean_install=clean_install)
    assert release._sbom_valid(sbom, root=root)
    assert release._license_inventory_valid(licenses, sbom=sbom)

    security["unknown"] = True
    _rehash_report(security)
    assert not release._security_report_valid(security, root=root)

    vulnerability["dependency_count"] = int(vulnerability["dependency_count"]) + 1
    _rehash_report(vulnerability)
    assert not release._vulnerability_audit_valid(vulnerability, root=root, clean_install=clean_install)

    components = sbom["components"]
    assert isinstance(components, list)
    components.pop()
    assert not release._sbom_valid(sbom, root=root)

    license_components = licenses["components"]
    assert isinstance(license_components, list)
    component = license_components[0]
    assert isinstance(component, dict)
    component.update({"license": "GPL-3.0-only", "status": "allowed"})
    assert not release._license_inventory_valid(licenses, sbom=_stored_p122_report("sbom.json"))


def test_critical_and_fake_supply_chain_evidence_fails_after_self_rehash() -> None:
    root = Path.cwd()
    security = _stored_p122_report("security-report.json")
    security["findings"] = [
        {
            "rule_id": "artifact.arbitrary_subprocess",
            "severity": "critical",
            "path": "dist/opscat.whl!app/backdoor.py",
            "line": 1,
            "message": "arbitrary command execution",
            "fingerprint": "a" * 16,
        }
    ]
    security["severity_counts"] = {"critical": 1}
    security["status"] = "pass"
    _rehash_report(security)
    assert not release._security_report_valid(security, root=root)

    vulnerability = _stored_p122_report("vulnerability-audit.json")
    vulnerability["vulnerabilities"] = [{"package": "fastapi", "version": "0", "vulnerability": {"id": "CVE-FAKE"}}]
    vulnerability["vulnerability_count"] = 0
    vulnerability["status"] = "pass"
    _rehash_report(vulnerability)
    assert not release._vulnerability_audit_valid(
        vulnerability,
        root=root,
        clean_install=_stored_p122_report("clean-install.json"),
    )


def test_docs_report_requires_exact_29_document_schema_arrays_and_current_hashes() -> None:
    root = Path.cwd()
    report = _stored_p122_report("docs-verification.json")
    assert release._docs_verification_valid(report, root=root)

    for mutation in ("unknown", "missing_doc", "stale_hash", "short_array"):
        tampered = copy.deepcopy(report)
        if mutation == "unknown":
            tampered["unknown"] = []
        elif mutation == "missing_doc":
            tampered["checked_docs"].pop()
        elif mutation == "stale_hash":
            doc = tampered["checked_docs"][0]
            tampered["document_hashes"][doc] = "sha256:" + ("0" * 64)
        else:
            tampered["claim_checked_docs"].pop()
        _rehash_report(tampered)
        assert not release._docs_verification_valid(tampered, root=root), mutation


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown_top",
        "unknown_nested",
        "missing_nested",
        "semantic_binding",
        "restart_count",
        "pending_hash",
        "receipt_hash",
    ],
)
def test_performance_report_rejects_schema_semantic_and_receipt_forgery(mutation: str) -> None:
    report = _stored_p122_report("performance-soak.json")
    receipts = release._capture_performance_receipts(report, root=Path.cwd())
    assert release._performance_report_valid(report, root=Path.cwd(), crash_receipts=receipts)
    tampered = copy.deepcopy(report)
    point = tampered["release_stage_crash_replay"]["points"][0]
    if mutation == "unknown_top":
        tampered["unknown"] = True
    elif mutation == "unknown_nested":
        tampered["observability"]["health"]["unknown"] = True
    elif mutation == "missing_nested":
        tampered["storage_envelope"].pop("scope")
    elif mutation == "semantic_binding":
        tampered["semantic_binding"] = "sha256:" + ("0" * 64)
    elif mutation == "restart_count":
        point["restart_count"] = 2
    elif mutation == "pending_hash":
        point["pending_record_hash"] = "sha256:" + ("0" * 64)
    elif mutation == "receipt_hash":
        point["restart_receipt_hash"] = "sha256:" + ("0" * 64)
    _rehash_report(tampered)
    assert not release._performance_report_valid(tampered, root=Path.cwd(), crash_receipts=receipts)


def test_performance_report_rejects_rehashed_receipt_with_unknown_nested_field() -> None:
    report = _stored_p122_report("performance-soak.json")
    receipts = release._capture_performance_receipts(report, root=Path.cwd())
    receipt = receipts["points"][0]["receipt"]
    receipt["output_validation"]["unknown"] = True
    receipt["record_hash"] = stable_hash({key: value for key, value in receipt.items() if key != "record_hash"})
    receipts["points"][0]["restart_receipt_hash"] = receipt["record_hash"]
    receipts["bundle_hash"] = stable_hash({key: value for key, value in receipts.items() if key != "bundle_hash"})

    assert not release._performance_report_valid(report, root=Path.cwd(), crash_receipts=receipts)


def test_performance_validation_rejects_creator_local_absolute_paths_even_when_embedded(monkeypatch: pytest.MonkeyPatch) -> None:
    report = _stored_p122_report("performance-soak.json")
    receipts = release._capture_performance_receipts(report, root=Path.cwd())
    assert release._performance_report_valid(report, root=Path.cwd())

    creator_local = copy.deepcopy(report)
    for index, point in enumerate(creator_local["release_stage_crash_replay"]["points"]):
        stage_root = Path("/tmp/creator-only") / f"{index:02d}-{point['stage']}"
        point["pending_ref"] = str(stage_root / "pending.json")
        point["restart_receipt_ref"] = str(stage_root / "restart-receipt.json")
        point["output_ref"] = str(stage_root / "committed" / release._P122_STAGE_ADAPTERS[point["stage"]][2])
    creator_local["observability"]["diagnostics"]["crash_replay_artifact_root"] = "/tmp/creator-only"
    creator_local["observability"]["diagnostics"]["record_artifact_root"] = "/tmp/creator-only/records"
    _rehash_report(creator_local)
    assert not release._performance_report_valid(creator_local, root=Path.cwd())

    receipts["source_report_hash"] = creator_local["report_hash"]
    receipts["bundle_hash"] = stable_hash({key: value for key, value in receipts.items() if key != "bundle_hash"})

    original_read = release._read

    def reject_creator_tmp(path: Path) -> dict[str, object]:
        if path.is_absolute() and str(path).startswith("/tmp/"):
            raise AssertionError(f"creator-local path dereferenced: {path}")
        return original_read(path)

    monkeypatch.setattr(release, "_read", reject_creator_tmp)
    assert not release._performance_report_valid(creator_local, root=Path.cwd(), crash_receipts=receipts)


def test_performance_receipt_capture_never_reads_absolute_refs(monkeypatch: pytest.MonkeyPatch) -> None:
    report = _stored_p122_report("performance-soak.json")
    point = report["release_stage_crash_replay"]["points"][0]
    point["pending_ref"] = "/tmp/creator-only/pending.json"
    point["restart_receipt_ref"] = "/tmp/creator-only/restart-receipt.json"
    _rehash_report(report)
    original_read = release._read

    def reject_creator_tmp(path: Path) -> dict[str, object]:
        if path.is_absolute() and str(path).startswith("/tmp/"):
            raise AssertionError(f"creator-local path dereferenced: {path}")
        return original_read(path)

    monkeypatch.setattr(release, "_read", reject_creator_tmp)
    receipts = release._capture_performance_receipts(report, root=Path.cwd())

    assert receipts["points"][0]["pending"] == {}
    assert receipts["points"][0]["receipt"] == {}


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("pending_ref", "/tmp/creator-only/pending.json"),
        ("restart_receipt_ref", "/tmp/creator-only/restart-receipt.json"),
        ("output_ref", "/tmp/creator-only/committed/installed-wheel"),
        ("pending_ref", "evals/p122/performance-artifacts/crash-replay/00-install/../pending.json"),
        ("restart_receipt_ref", "evals/p122/performance-artifacts/crash-replay/00-install/./restart-receipt.json"),
        ("output_ref", "evals/p122/not-performance-artifacts/00-install/committed/installed-wheel"),
    ],
)
def test_performance_validation_rejects_rehashed_forged_refs_with_embedded_receipts(field: str, replacement: str) -> None:
    report = _stored_p122_report("performance-soak.json")
    receipts = release._capture_performance_receipts(report, root=Path.cwd())
    report["release_stage_crash_replay"]["points"][0][field] = replacement
    _rehash_report(report)
    receipts["source_report_hash"] = report["report_hash"]
    receipts["bundle_hash"] = stable_hash({key: value for key, value in receipts.items() if key != "bundle_hash"})

    assert not release._performance_report_valid(report, root=Path.cwd(), crash_receipts=receipts)


def test_performance_validation_rejects_nonexistent_repo_relative_refs_with_embedded_receipts(tmp_path: Path) -> None:
    report = _stored_p122_report("performance-soak.json")
    receipts = release._capture_performance_receipts(report, root=Path.cwd())

    assert not release._performance_report_valid(report, root=tmp_path, crash_receipts=receipts)
