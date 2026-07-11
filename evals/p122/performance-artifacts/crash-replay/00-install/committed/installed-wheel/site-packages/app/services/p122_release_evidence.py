"""Open-source packaging release evidence with exact-source freshness checks."""

from __future__ import annotations

import ast
import hashlib
import json
import math
import re
import tomllib
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p121_signals import P121_AUTHORITY_COUNTER_KEYS

P122_RELEASE_SCHEMA_VERSION = "p122.release_evidence.v1"
_ROOT = Path(__file__).resolve().parents[2]
_P122_DOCS = (
    Path("docs/migration.md"),
    Path("docs/install.md"),
    Path("docs/quickstart.md"),
    Path("docs/performance.md"),
    Path("docs/operations/p122-verification-handoff.md"),
    Path("docs/operations/p122-final-summary.md"),
    Path("docs/tickets/p122/README.md"),
)
_P122_VERIFIED_DOCS = (
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "README.md",
    "SECURITY.md",
    "docs/install.md",
    "docs/limitations.md",
    "docs/migration.md",
    "docs/operations/p122-final-summary.md",
    "docs/operations/p122-open-source-production-packaging-roadmap.md",
    "docs/operations/p122-plan-review.md",
    "docs/operations/p122-test-spec.md",
    "docs/operations/p122-verification-handoff.md",
    "docs/performance.md",
    "docs/public-contracts.md",
    "docs/quickstart.md",
    "docs/release-evidence.md",
    "docs/release-notes-0.2.0.md",
    "docs/security-threat-model.md",
    "docs/supply-chain.md",
    "docs/threat-model.md",
    "docs/tickets/p122/P122-001-architecture-cleanup-and-stable-public-contracts.md",
    "docs/tickets/p122/P122-002-packaging-clean-install-sample-deployment-and-local-demo.md",
    "docs/tickets/p122/P122-003-public-docs-tutorials-contributor-guide-and-limitations.md",
    "docs/tickets/p122/P122-004-security-threat-model-secret-scanning-sbom-licenses-and-supply-chain.md",
    "docs/tickets/p122/P122-005-ci-matrix-and-reproducible-frozen-evals.md",
    "docs/tickets/p122/P122-006-performance-soak-crash-replay-and-agent-observability.md",
    "docs/tickets/p122/P122-007-upgrade-migration-compatibility-and-release-artifacts.md",
    "docs/tickets/p122/P122-008-release-candidate-review-verification-handoff-and-public-limitations.md",
    "docs/tickets/p122/README.md",
)
_REQUIRED_SOURCE_PATHS = (
    "pyproject.toml",
    "uv.lock",
    "LICENSE",
    "README.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "app/cli.py",
    "app/config.py",
    "app/plugin_sdk.py",
    "app/public_contracts.py",
    "app/services/p110_evaluation.py",
    "app/services/p115_action_contract.py",
    "app/services/p115_ontology.py",
    "app/services/p119_attribution.py",
    "app/services/p120_governance.py",
    "app/services/redaction.py",
    "app/services/local_safe_subprocess_runner.py",
    "app/services/supervised_worker_execution_harness.py",
    "app/services/p122_release_evidence.py",
    "scripts/verify.sh",
    "scripts/run_local_safe_subprocess_runner.py",
    "scripts/run_supervised_worker_execution_harness.py",
    "docker-compose.yml",
    "config/opscat.local.example.json",
    "tests/test_local_safe_subprocess_runner.py",
    "tests/test_supervised_worker_execution_harness.py",
)
_P122_CRASH_STAGES = (
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
_P122_STAGE_OPERATIONS = {
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
_P122_STAGE_ADAPTERS = {
    "install": ("wheel_install_transaction_v1", "p122.wheel_install_transaction.v1", "installed-wheel"),
    "demo_startup": ("local_cli_demo_start_v1", "opscat.local_demo.v1", "local-demo.json"),
    "incident_ingest": ("p115_incident_case_ingest_v1", "p115.incident_case.v1", "incident.json"),
    "evidence_request": ("p121_evidence_receipt_v1", "p121.evidence_receipt.v1", "evidence.json"),
    "decision": ("p121_prevention_decision_v1", "p121.prevention_decision.v1", "decision.json"),
    "approval": ("p121_local_approval_v1", "p121.approval.v1", "approval.json"),
    "validation": ("p121_validation_outcome_v1", "p121.validation_outcome.v1", "validation.json"),
    "rollback": ("p121_rollback_outcome_v1", "p121.validation_outcome.v1", "rollback.json"),
    "replay_write": ("p121_restart_recovery_bundle_v1", "p121.restart_recovery_proof.v1", "replay-bundle"),
    "eval_write": ("p121_frozen_evaluation_v1", "p121.frozen_prevention_evaluation.v1", "frozen-evaluation.json"),
    "release_evidence_write": ("p122_release_evidence_snapshot_v1", "p122.release_evidence.v1", "release-evidence.json"),
    "report_write": ("p122_docs_report_v1", "p122.docs_verification.v1", "docs-verification.json"),
}
_P122_OUTPUT_VALIDATION_KEYS = {
    "install": {
        "schema_version",
        "installed_package",
        "installed_file_count",
        "app_package_present",
        "metadata_hash",
        "console_entrypoint",
        "record_entries_verified",
    },
    "demo_startup": {"schema_version", "artifact_hash", "event_count", "exact_nonlocal_authority_zero"},
    "incident_ingest": {"schema_version", "artifact_hash", "case_id", "release_role"},
    "evidence_request": {"schema_version", "artifact_hash", "evidence_id", "exact_nonlocal_authority_zero"},
    "decision": {"schema_version", "artifact_hash", "route", "exact_nonlocal_authority_zero"},
    "approval": {"schema_version", "artifact_hash", "approved", "exact_nonlocal_authority_zero"},
    "validation": {"schema_version", "artifact_hash", "validation_passed", "rollback_attempted", "rollback_passed", "exact_nonlocal_authority_zero"},
    "rollback": {"schema_version", "artifact_hash", "validation_passed", "rollback_attempted", "rollback_passed", "exact_nonlocal_authority_zero"},
    "replay_write": {"schema_version", "artifact_hash", "wal_hash", "point_count", "exact_nonlocal_authority_zero"},
    "eval_write": {"schema_version", "artifact_hash", "case_count", "first_score_consumed", "exact_nonlocal_authority_zero"},
    "release_evidence_write": {"schema_version", "artifact_hash", "release_status", "contract_manifest_hash", "contract_validation_executed"},
    "report_write": {"schema_version", "artifact_hash", "valid", "checked_doc_count"},
}
_P121_RESTART_RECOVERY_PROOF_HASH = "sha256:a2d204f4ee9b964cf133333b5d50fede6141a61af1133654fd681bd92625de91"
_SHA256_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
_SCHEMA_REF_PATTERN = re.compile(r"\b[a-z][a-z0-9_.-]*\.v[0-9]+\b")
_ALLOWED_LICENSES = frozenset(
    {
        "0BSD",
        "Apache-2.0",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "ISC",
        "LGPL-3.0-only",
        "LGPL-3.0-or-later",
        "MIT",
        "MPL-2.0",
        "PSF-2.0",
        "Python-2.0",
    }
)
_RISKY_LICENSE_TOKENS = ("AGPL", "GPL-2", "GPL-3")
_SOURCE_PATTERNS = (
    ".github/**/*",
    "app/services/p121_*.py",
    "app/services/p122_*.py",
    "scripts/*p121*.py",
    "scripts/*p122*.py",
    "tests/test_p121*.py",
    "tests/test_p122*.py",
    "docs/*.md",
    "docs/operations/*p122*.md",
    "docs/tickets/p122/**/*.md",
)
_IGNORED_SOURCE_NAMES = frozenset({".DS_Store", "Thumbs.db", "desktop.ini"})
_IGNORED_SOURCE_PARTS = frozenset({".git", ".idea", ".mypy_cache", ".omx", ".pytest_cache", ".ruff_cache", ".venv", ".vscode", "__pycache__"})
_REVIEW_TICKET_KEYS = tuple(f"P122-{index:03d}" for index in range(1, 9))
_UPSTREAM_AUTHORITY_KEYS: dict[int, frozenset[str]] = {
    115: frozenset(
        {
            "action_execution_count",
            "auth_grant_count",
            "credential_access_count",
            "external_network_count",
            "production_mutation_count",
            "subprocess_execution_count",
        }
    ),
    116: frozenset(
        {
            "arbitrary_action_enabled",
            "credentials_enabled",
            "external_network_enabled",
            "filesystem_mutation_enabled",
            "production_mutation_enabled",
            "subprocess_execution_enabled",
            "unattended_production_operation_claimed",
        }
    ),
    117: frozenset(
        {
            "auth_grant_count",
            "cloud_mutation_count",
            "credential_access_count",
            "database_mutation_count",
            "executor_call_count",
            "kubernetes_mutation_count",
            "network_mutation_count",
            "online_policy_write_count",
            "production_adapter_call_count",
            "production_mutation_count",
            "shell_execution_count",
            "subprocess_execution_count",
        }
    ),
    118: frozenset(
        {
            "auth",
            "cloud",
            "credentials",
            "database_mutation",
            "executor",
            "kubernetes",
            "network_mutation",
            "online_policy_write",
            "production_adapter",
            "production_mutation",
            "shell",
            "subprocess",
        }
    ),
    119: frozenset(
        {
            "auth_context_count",
            "authority_escape_count",
            "cloud_mutation_count",
            "credential_scope_count",
            "database_mutation_count",
            "freeform_action_execution_count",
            "kubernetes_mutation_count",
            "l4_plus_action_count",
            "live_connector_call_count",
            "llm_command_execution_count",
            "network_mutation_count",
            "online_policy_write_count",
            "production_mutation_count",
            "secret_material_count",
            "shell_execution_count",
            "staging_mutation_count",
            "subprocess_execution_count",
        }
    ),
    120: frozenset(
        {
            "auth_context_count",
            "authority_escape_count",
            "cloud_mutation_count",
            "connector_write_call_count",
            "credential_scope_count",
            "database_mutation_count",
            "filesystem_mutation_outside_artifact_count",
            "freeform_action_execution_count",
            "kubernetes_mutation_count",
            "l4_plus_action_count",
            "live_connector_call_count",
            "llm_command_execution_count",
            "network_mutation_count",
            "online_policy_write_count",
            "production_mutation_count",
            "secret_material_count",
            "shell_execution_count",
            "staging_mutation_count",
            "subprocess_execution_count",
        }
    ),
    121: frozenset(P121_AUTHORITY_COUNTER_KEYS),
}


def produce_p122_release_evidence(
    *,
    reviewer_id: str,
    builder_id: str,
    root: Path = _ROOT,
    performance_crash_receipts: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    upstream = {str(phase): _read(root / f"evals/p{phase}/release-evidence.json") for phase in range(115, 122)}
    security = _read(root / "evals/p122/security-report.json")
    vulnerability_audit = _read(root / "evals/p122/vulnerability-audit.json")
    sbom = _read(root / "evals/p122/sbom.json")
    licenses = _read(root / "evals/p122/license-inventory.json")
    performance = _read(root / "evals/p122/performance-soak.json")
    portable_crash_receipts = (
        dict(performance_crash_receipts)
        if performance_crash_receipts is not None
        else _capture_performance_receipts(performance, root=root)
    )
    checksums = _read(root / "evals/p122/package-checksums.json")
    reproducible_build = _read(root / "evals/p122/reproducible-build.json")
    clean_install = _read(root / "evals/p122/clean-install.json")
    docs_verification = _read(root / "evals/p122/docs-verification.json")
    migration = _read(root / "evals/p122/migration-compatibility.json")
    review = _read(root / "evals/p122/independent-review.json")
    upstream_ready = all(_upstream_ready(phase, upstream[str(phase)]) for phase in range(115, 122))
    exact_zero = all(_authority_zero(value, phase=int(phase)) for phase, value in upstream.items())
    package_current = bool(checksums) and all((root / "dist" / name).is_file() and digest == _file_hash(root / "dist" / name) for name, digest in checksums.items())
    review_current = _independent_review_current(review, reviewer_id=reviewer_id, builder_id=builder_id)
    source_manifest = _source_manifest(root)
    source_hashes = _source_hashes(root)
    gates = {
        "distinct_reviewer": bool(reviewer_id and builder_id and reviewer_id != builder_id),
        "independent_review_passed": review_current and review.get("verdict") == "PASS" and review.get("reviewer_id") == reviewer_id,
        "upstream_p115_p121_ready": upstream_ready,
        "exact_nonlocal_authority_zero": exact_zero,
        "security_gate_passed": _security_report_valid(security, root=root, package_checksums=checksums),
        "known_vulnerability_audit_passed": _vulnerability_audit_valid(
            vulnerability_audit,
            root=root,
            clean_install=clean_install,
        ),
        "sbom_complete": _sbom_valid(sbom, root=root),
        "licenses_compatible": _license_inventory_valid(licenses, sbom=sbom),
        "package_artifacts_current": package_current and len(checksums) >= 2,
        "package_build_byte_reproducible": reproducible_build.get("byte_reproducible") is True
        and reproducible_build.get("checksums") == checksums,
        "clean_install_demo_uninstall_passed": clean_install.get("wheel_hash") == checksums.get("opscat-0.2.0-py3-none-any.whl")
        and clean_install.get("install_exit_code") == 0
        and clean_install.get("demo_exit_code") == 0
        and clean_install.get("contracts_exit_code") == 0
        and clean_install.get("uninstall_exit_code") == 0
        and clean_install.get("import_residue_after_uninstall") is False
        and _exact_p121_authority_counters(clean_install.get("authority_counters"))
        and clean_install.get("exact_nonlocal_authority_zero") is True,
        "performance_soak_complete": _performance_report_valid(
            performance,
            root=root,
            crash_receipts=portable_crash_receipts,
        ),
        "crash_replay_inventory_complete": _release_stage_crash_replay_valid(
            performance,
            root=root,
            crash_receipts=portable_crash_receipts,
        )
        and _p121_restart_recovery_proof_valid(performance),
        "docs_verification_passed": _docs_verification_valid(docs_verification, root=root),
        "migration_compatibility_passed": _migration_report_valid(migration),
        "source_manifest_complete": set(source_hashes) == set(source_manifest)
        and set(_REQUIRED_SOURCE_PATHS) <= set(source_manifest),
    }
    ready = all(gates.values())
    evidence: dict[str, Any] = {
        "schema_version": P122_RELEASE_SCHEMA_VERSION,
        "release_id": "P122-008",
        "release_status": "p122_open_source_local_rc" if ready else "p122_blocked",
        "product_claim": "production-grade packaging practices with local/mock/sandbox qualification",
        "public_limitation": "Production autonomy, auth completion, credentials, live connector writes, production/staging mutation, and operator replacement are not proven or enabled.",
        "gates": gates,
        "upstream_release_hashes": {phase: value.get("release_evidence_hash") for phase, value in upstream.items()},
        "source_hashes": source_hashes,
        "package_checksums": checksums,
        "reproducible_build_hash": reproducible_build.get("report_hash"),
        "clean_install_hash": clean_install.get("report_hash"),
        "security_report_hash": security.get("report_hash"),
        "vulnerability_audit_hash": vulnerability_audit.get("report_hash"),
        "sbom_hash": stable_hash(sbom) if sbom else None,
        "license_inventory_hash": stable_hash(licenses) if licenses else None,
        "performance_report_hash": performance.get("report_hash"),
        "performance_crash_receipts": portable_crash_receipts,
        "docs_verification_hash": docs_verification.get("report_hash"),
        "migration_report_hash": migration.get("report_hash"),
        "authority": {"exact_nonlocal_authority_zero": exact_zero, "nonzero_phases": [phase for phase, value in upstream.items() if not _authority_zero(value, phase=int(phase))]},
        "review": {"reviewer_id": reviewer_id, "builder_id": builder_id, "artifact": review},
        "unresolved_risks": ["local fixture and frozen benchmark evidence does not establish live-production effectiveness"],
        "reasons": [f"{key} failed closed" for key, passed in gates.items() if not passed],
    }
    evidence["release_evidence_hash"] = stable_hash(evidence)
    return evidence


def validate_p122_release_evidence(evidence: Mapping[str, Any], *, root: Path = _ROOT) -> dict[str, Any]:
    rebuilt = produce_p122_release_evidence(
        reviewer_id=str(_mapping(evidence.get("review")).get("reviewer_id", "")),
        builder_id=str(_mapping(evidence.get("review")).get("builder_id", "")),
        root=root,
        performance_crash_receipts=_mapping(evidence.get("performance_crash_receipts")),
    )
    expected_without_hash = {key: value for key, value in rebuilt.items() if key != "release_evidence_hash"}
    actual_without_hash = {key: value for key, value in evidence.items() if key != "release_evidence_hash"}
    checks = {
        "schema_current": evidence.get("schema_version") == P122_RELEASE_SCHEMA_VERSION,
        "self_hash_current": evidence.get("release_evidence_hash") == stable_hash({key: value for key, value in evidence.items() if key != "release_evidence_hash"}),
        "all_fields_current": actual_without_hash == expected_without_hash,
        "independent_review_current": _independent_review_current(
            _mapping(_mapping(evidence.get("review")).get("artifact")),
            reviewer_id=str(_mapping(evidence.get("review")).get("reviewer_id", "")),
            builder_id=str(_mapping(evidence.get("review")).get("builder_id", "")),
        ),
        "source_hashes_current": evidence.get("source_hashes") == rebuilt.get("source_hashes"),
        "package_checksums_current": evidence.get("package_checksums") == rebuilt.get("package_checksums"),
        "upstream_hashes_current": evidence.get("upstream_release_hashes") == rebuilt.get("upstream_release_hashes"),
        "gates_current": evidence.get("gates") == rebuilt.get("gates"),
        "release_qualified": evidence.get("release_status") == "p122_open_source_local_rc" and rebuilt.get("release_status") == "p122_open_source_local_rc",
    }
    return {"valid": all(checks.values()), "checks": checks, "reasons": [f"{key} failed closed" for key, passed in checks.items() if not passed]}


def _upstream_ready(phase: int, value: Mapping[str, Any]) -> bool:
    if phase == 116:
        return bool(value.get("gates")) and all(value.get("gates", {}).values()) and all(value.get("acceptance_gates", {}).values())
    status = str(value.get("release_status", ""))
    return status.endswith(("qualified", "ready"))


def _authority_zero(value: Mapping[str, Any], *, phase: int = 121) -> bool:
    authority = _mapping(value.get("authority"))
    counters = _mapping(authority.get("counters")) or _mapping(authority.get("production_authority_counters"))
    expected_keys = _UPSTREAM_AUTHORITY_KEYS.get(phase, frozenset(P121_AUTHORITY_COUNTER_KEYS))
    return set(counters) == expected_keys and all(
        isinstance(counters.get(key), int) and not isinstance(counters.get(key), bool) and counters.get(key) == 0
        for key in expected_keys
    )


def _independent_review_current(review: Mapping[str, Any], *, reviewer_id: str, builder_id: str) -> bool:
    if not review or not reviewer_id or not builder_id or reviewer_id == builder_id:
        return False
    matrix = _mapping(review.get("ticket_matrix"))
    if set(matrix) != set(_REVIEW_TICKET_KEYS):
        return False
    if any(matrix.get(key) != "PASS" for key in _REVIEW_TICKET_KEYS):
        return False
    expected_hash = stable_hash({key: value for key, value in review.items() if key != "self_hash"})
    return review.get("self_hash") == expected_hash


def _exact_p121_authority_counters(value: Any) -> bool:
    counters = _mapping(value)
    return set(counters) == set(P121_AUTHORITY_COUNTER_KEYS) and all(
        isinstance(counters.get(key), int) and not isinstance(counters.get(key), bool) and counters.get(key) == 0
        for key in P121_AUTHORITY_COUNTER_KEYS
    )


def _report_hash_current(report: Mapping[str, Any]) -> bool:
    return bool(report) and report.get("report_hash") == stable_hash({key: value for key, value in report.items() if key != "report_hash"})


def _security_report_valid(
    report: Mapping[str, Any],
    *,
    root: Path,
    package_checksums: Mapping[str, Any] | None = None,
) -> bool:
    expected_keys = {
        "schema_version",
        "gate",
        "status",
        "root",
        "root_binding_hash",
        "source_inventory",
        "source_inventory_hash",
        "archive_inventory",
        "archive_inventory_hash",
        "scanned_file_count",
        "dependency_count",
        "generated_artifact_scan_count",
        "severity_counts",
        "findings",
        "artifacts",
        "limitations",
        "report_hash",
    }
    findings = report.get("findings")
    if not isinstance(findings, list) or not all(_security_finding_valid(item) for item in findings):
        return False
    severity_counts = dict(Counter(str(_mapping(item).get("severity")) for item in findings))
    blocking = severity_counts.get("critical", 0) + severity_counts.get("high", 0)
    artifact_count = len(package_checksums) if package_checksums is not None else len(list((root / "dist").glob("opscat-0.2.0*")))
    return (
        set(report) == expected_keys
        and report.get("schema_version") == "p122.security_report.v2"
        and report.get("gate") == "p122_security_supply_chain"
        and report.get("status") == ("fail" if blocking else "pass") == "pass"
        and report.get("root") == str(root)
        and _positive_int(report.get("scanned_file_count"))
        and _exact_int(report.get("dependency_count"), len(_locked_packages(root)))
        and _exact_int(report.get("generated_artifact_scan_count"), artifact_count)
        and _security_inventory_schema_valid(report)
        and dict(_mapping(report.get("severity_counts"))) == dict(sorted(severity_counts.items()))
        and dict(_mapping(report.get("artifacts")))
        == {
            "security_report": "evals/p122/security-report.json",
            "sbom": "evals/p122/sbom.json",
            "license_inventory": "evals/p122/license-inventory.json",
        }
        and report.get("limitations")
        == [
            "This deterministic static gate performs no network lookup; scripts/run_p122_vulnerability_audit.py provides a separate freshness-bound advisory database gate.",
            "Secret scanning is regex and entropy based; it can miss novel token formats and intentionally redacts matched values.",
            "Static shell/action checks are heuristic and focus on Python subprocess/os.system paths in non-fixture source.",
            "License metadata prefers installed package metadata and falls back to the documented in-script allowlist.",
        ]
        and _report_hash_current(report)
        and _security_report_current(report, root=root)
    )


def _security_finding_valid(value: Any) -> bool:
    finding = _mapping(value)
    return (
        set(finding) == {"rule_id", "severity", "path", "line", "message", "fingerprint"}
        and finding.get("severity") in {"low", "medium", "high", "critical"}
        and all(isinstance(finding.get(key), str) and bool(finding.get(key)) for key in ("rule_id", "path", "message"))
        and _positive_int(finding.get("line"))
        and re.fullmatch(r"[0-9a-f]{16}", str(finding.get("fingerprint", ""))) is not None
    )


def _security_inventory_schema_valid(report: Mapping[str, Any]) -> bool:
    source_inventory = report.get("source_inventory")
    archive_inventory = report.get("archive_inventory")
    if not isinstance(source_inventory, list) or not isinstance(archive_inventory, list):
        return False
    source_paths = [str(_mapping(item).get("path", "")) for item in source_inventory]
    archive_paths = [str(_mapping(item).get("path", "")) for item in archive_inventory]
    return (
        source_paths == sorted(source_paths)
        and len(source_paths) == len(set(source_paths))
        and archive_paths == sorted(archive_paths)
        and len(archive_paths) == len(set(archive_paths))
        and _exact_int(report.get("scanned_file_count"), len(source_inventory))
        and _exact_int(report.get("generated_artifact_scan_count"), len(archive_inventory))
        and _SHA256_PATTERN.fullmatch(str(report.get("root_binding_hash", ""))) is not None
        and _SHA256_PATTERN.fullmatch(str(report.get("source_inventory_hash", ""))) is not None
        and _SHA256_PATTERN.fullmatch(str(report.get("archive_inventory_hash", ""))) is not None
        and all(_source_inventory_entry_valid(item) for item in source_inventory)
        and all(_archive_inventory_entry_valid(item) for item in archive_inventory)
    )


def _source_inventory_entry_valid(value: Any) -> bool:
    entry = _mapping(value)
    path = Path(str(entry.get("path", "")))
    return (
        set(entry) == {"path", "size", "hash"}
        and bool(path.parts)
        and not path.is_absolute()
        and ".." not in path.parts
        and isinstance(entry.get("size"), int)
        and not isinstance(entry.get("size"), bool)
        and int(entry.get("size", -1)) >= 0
        and _SHA256_PATTERN.fullmatch(str(entry.get("hash", ""))) is not None
    )


def _archive_inventory_entry_valid(value: Any) -> bool:
    entry = _mapping(value)
    members = entry.get("members")
    path = Path(str(entry.get("path", "")))
    if not isinstance(members, list):
        return False
    member_paths = [str(_mapping(item).get("path", "")) for item in members]
    return (
        set(entry) == {"path", "format", "size", "hash", "readable", "members"}
        and not path.is_absolute()
        and path.parts[:1] == ("dist",)
        and ".." not in path.parts
        and entry.get("format") in {"wheel", "sdist"}
        and entry.get("readable") is True
        and _positive_int(entry.get("size"))
        and _SHA256_PATTERN.fullmatch(str(entry.get("hash", ""))) is not None
        and member_paths == sorted(member_paths)
        and all(_source_inventory_entry_valid(item) for item in members)
    )


def _security_report_current(report: Mapping[str, Any], *, root: Path) -> bool:
    try:
        from scripts.run_p122_security_gate import security_report_current

        return security_report_current(report, root=root)
    except (ImportError, OSError, RuntimeError, ValueError):
        return False


def _vulnerability_audit_valid(
    report: Mapping[str, Any],
    *,
    root: Path,
    clean_install: Mapping[str, Any],
) -> bool:
    expected_keys = {
        "schema_version",
        "auditor",
        "vulnerability_service",
        "uv_lock_hash",
        "dependency_count",
        "vulnerability_count",
        "vulnerabilities",
        "status",
        "limitations",
        "report_hash",
    }
    vulnerabilities = report.get("vulnerabilities")
    runtime_graph = clean_install.get("audited_lock_runtime_graph")
    expected_count = len(runtime_graph) - 1 if isinstance(runtime_graph, list) and "opscat==0.2.0" in runtime_graph else -1
    return (
        set(report) == expected_keys
        and report.get("schema_version") == "p122.vulnerability_audit.v1"
        and report.get("auditor") == "pip-audit==2.10.1"
        and report.get("vulnerability_service") == "pypi"
        and report.get("uv_lock_hash") == _file_hash(root / "uv.lock")
        and _exact_int(report.get("dependency_count"), expected_count)
        and isinstance(vulnerabilities, list)
        and all(set(_mapping(item)) == {"package", "version", "vulnerability"} for item in vulnerabilities)
        and _exact_int(report.get("vulnerability_count"), len(vulnerabilities))
        and report.get("status") == ("pass" if not vulnerabilities else "fail") == "pass"
        and report.get("limitations") == ["The database result is point-in-time evidence and must be rerun for every release."]
        and _report_hash_current(report)
    )


def _sbom_valid(report: Mapping[str, Any], *, root: Path) -> bool:
    return dict(report) == _expected_sbom(root)


def _expected_sbom(root: Path) -> dict[str, Any]:
    lock_text = (root / "uv.lock").read_text(encoding="utf-8")
    lock_hash = hashlib.sha256(lock_text.encode()).hexdigest()
    components: list[dict[str, Any]] = []
    for package in sorted(_locked_packages(root), key=lambda item: str(item["name"]).lower()):
        name = str(package["name"])
        version = str(package["version"])
        hashes = _locked_package_hashes(package)
        components.append(
            {
                "type": "library",
                "bom-ref": f"pkg:pypi/{name}@{version}",
                "name": name,
                "version": version,
                "purl": f"pkg:pypi/{name}@{version}",
                "hashes": hashes,
                "evidence": {"source": "uv.lock", "hashes_present": bool(hashes)},
            }
        )
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{hashlib.sha256(lock_hash.encode()).hexdigest()[:32]}",
        "version": 1,
        "metadata": {
            "component": {"type": "application", "name": "opscat", "version": "0.2.0"},
            "properties": [{"name": "opscat:p122:uv_lock_sha256", "value": lock_hash}],
        },
        "components": components,
    }


def _locked_packages(root: Path) -> list[dict[str, Any]]:
    lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    packages = lock.get("package")
    if not isinstance(packages, list):
        return []
    return [item for item in packages if isinstance(item, dict) and item.get("name") and item.get("version")]


def _locked_package_hashes(package: Mapping[str, Any]) -> list[dict[str, str]]:
    hashes: list[dict[str, str]] = []
    artifacts: list[Any] = [package.get("sdist")]
    wheels = package.get("wheels")
    if isinstance(wheels, list):
        artifacts.extend(wheels)
    for artifact in artifacts:
        raw_hash = _mapping(artifact).get("hash")
        if isinstance(raw_hash, str):
            algorithm, separator, content = raw_hash.partition(":")
            if separator and algorithm and content:
                hashes.append({"alg": algorithm.upper(), "content": content})
    return list({(item["alg"], item["content"]): item for item in hashes}.values())


def _license_inventory_valid(report: Mapping[str, Any], *, sbom: Mapping[str, Any]) -> bool:
    if set(report) != {"policy", "components", "findings"}:
        return False
    policy = _mapping(report.get("policy"))
    components = report.get("components")
    sbom_components = sbom.get("components")
    if not isinstance(components, list) or not isinstance(sbom_components, list):
        return False
    expected_inventory = [(item.get("name"), item.get("version")) for item in map(_mapping, sbom_components)]
    actual_inventory = [(item.get("name"), item.get("version")) for item in map(_mapping, components)]
    return (
        dict(policy) == {"allowed": sorted(_ALLOWED_LICENSES), "incompatible_tokens": list(_RISKY_LICENSE_TOKENS)}
        and actual_inventory == expected_inventory
        and all(_allowed_license_component(item) for item in components)
        and report.get("findings") == []
    )


def _allowed_license_component(value: Any) -> bool:
    component = _mapping(value)
    expression = component.get("license")
    if set(component) != {"name", "version", "license", "status"} or component.get("status") != "allowed" or not isinstance(expression, str):
        return False
    if re.search(r"\b(?:AGPL|GPL)-(?:2|3)", expression.upper()):
        return False
    tokens = {token.strip("() ") for token in re.split(r"\s+(?:OR|AND)\s+", expression) if token.strip("() ")}
    return bool(tokens) and tokens <= _ALLOWED_LICENSES


def _docs_verification_valid(report: Mapping[str, Any], *, root: Path = _ROOT) -> bool:
    expected_keys = {
        "schema_version",
        "checked_docs",
        "core_docs",
        "document_hashes",
        "schema_markers",
        "link_checked_docs",
        "claim_checked_docs",
        "schema_checked_docs",
        "example_checked_docs",
        "broken_links",
        "missing_troubleshooting",
        "missing_schema",
        "missing_examples",
        "invalid_json_examples",
        "stale_script_examples",
        "malformed_schema_references",
        "unbounded_claims",
        "missing_required_claims",
        "valid",
        "report_hash",
    }
    checked_docs = list(_P122_VERIFIED_DOCS)
    document_hashes = {
        name: "sha256:" + hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in checked_docs
        if (root / name).is_file()
    }
    schema_markers = {
        name: sorted(set(_SCHEMA_REF_PATTERN.findall((root / name).read_text(encoding="utf-8"))))
        for name in checked_docs
        if (root / name).is_file()
    }
    empty_arrays = {
        "broken_links",
        "missing_troubleshooting",
        "missing_schema",
        "missing_examples",
        "invalid_json_examples",
        "stale_script_examples",
        "malformed_schema_references",
        "unbounded_claims",
        "missing_required_claims",
    }
    return (
        set(report) == expected_keys
        and report.get("schema_version") == "p122.docs_verification.v1"
        and len(checked_docs) == 29
        and report.get("checked_docs") == checked_docs
        and report.get("core_docs") == [str(path) for path in _P122_DOCS]
        and report.get("document_hashes") == document_hashes
        and report.get("schema_markers") == schema_markers
        and all(report.get(key) == checked_docs for key in ("link_checked_docs", "claim_checked_docs", "schema_checked_docs", "example_checked_docs"))
        and all(report.get(key) == [] for key in empty_arrays)
        and report.get("valid") is True
        and _report_hash_current(report)
    )


def _migration_report_valid(report: Mapping[str, Any]) -> bool:
    expected_keys = {
        "schema_version",
        "source_version",
        "target_version",
        "fixture_upgrade_executed",
        "backup_created",
        "restore_verified",
        "rollback_verified",
        "compatibility_verified",
        "authority_key_set_exact",
        "authority_values_int_zero",
        "expected_authority_keys",
        "authority_counters",
        "artifacts",
        "report_hash",
    }
    artifacts = _mapping(report.get("artifacts"))
    return (
        set(report) == expected_keys
        and report.get("schema_version") == "p122.migration_compatibility.v1"
        and str(report.get("source_version", "")).startswith("0.1.")
        and report.get("target_version") == "0.2.0"
        and all(
            report.get(key) is True
            for key in (
                "fixture_upgrade_executed",
                "backup_created",
                "restore_verified",
                "rollback_verified",
                "compatibility_verified",
                "authority_key_set_exact",
                "authority_values_int_zero",
            )
        )
        and report.get("expected_authority_keys") == list(P121_AUTHORITY_COUNTER_KEYS)
        and set(artifacts) == {"fixture", "backup", "upgraded", "restored", "rollback"}
        and all(isinstance(value, str) and bool(value) for value in artifacts.values())
        and _exact_p121_authority_counters(report.get("authority_counters"))
        and _report_hash_current(report)
    )


def _capture_performance_receipts(performance: Mapping[str, Any], *, root: Path = _ROOT) -> dict[str, Any]:
    replay = _mapping(performance.get("release_stage_crash_replay"))
    raw_points = replay.get("points")
    points = raw_points if isinstance(raw_points, list) else []
    embedded_points: list[dict[str, Any]] = []
    for index, stage in enumerate(_P122_CRASH_STAGES):
        point = _mapping(points[index]) if index < len(points) else {}
        refs_valid = _crash_point_refs_valid(point, index=index, stage=stage, root=root)
        pending_path = _capture_receipt_path(point.get("pending_ref"), root=root) if refs_valid else None
        receipt_path = _capture_receipt_path(point.get("restart_receipt_ref"), root=root) if refs_valid else None
        embedded_points.append(
            {
                "stage": stage,
                "pending_record_hash": point.get("pending_record_hash"),
                "restart_receipt_hash": point.get("restart_receipt_hash"),
                "pending": dict(_read(pending_path)) if pending_path is not None else {},
                "receipt": dict(_read(receipt_path)) if receipt_path is not None else {},
            }
        )
    bundle: dict[str, Any] = {
        "schema_version": "p122.embedded_crash_receipts.v1",
        "source_report_hash": performance.get("report_hash"),
        "points": embedded_points,
    }
    bundle["bundle_hash"] = stable_hash(bundle)
    return bundle


def _capture_receipt_path(value: Any, *, root: Path) -> Path | None:
    return _repo_relative_path(value, root=root)


def _release_stage_crash_replay_valid(
    performance: Mapping[str, Any],
    *,
    root: Path = _ROOT,
    crash_receipts: Mapping[str, Any] | None = None,
) -> bool:
    inventory = performance.get("release_stage_crash_inventory")
    replay = _mapping(performance.get("release_stage_crash_replay"))
    points = replay.get("points")
    embedded_points = _embedded_receipt_points(crash_receipts, performance=performance)
    return (
        set(replay)
        == {
            "schema_version",
            "protocol",
            "point_count",
            "injected_count",
            "recovered_count",
            "observed_restart_receipt_count",
            "verified",
            "points",
        }
        and inventory == list(_P122_CRASH_STAGES)
        and isinstance(points, list)
        and len(points) == len(_P122_CRASH_STAGES)
        and replay.get("schema_version") == "p122.release_stage_crash_replay.v1"
        and replay.get("protocol") == "multiprocessing-spawn-exit-restart"
        and replay.get("verified") is True
        and all(
            _exact_int(replay.get(key), len(_P122_CRASH_STAGES))
            for key in ("point_count", "injected_count", "recovered_count", "observed_restart_receipt_count")
        )
        and (embedded_points is None or len(embedded_points) == len(_P122_CRASH_STAGES))
        and all(
            _release_stage_point_valid(
                point,
                index=index,
                stage=stage,
                root=root,
                records=embedded_points[index] if embedded_points is not None else _repo_relative_receipt_records(point, root=root),
            )
            for index, (point, stage) in enumerate(zip(points, _P122_CRASH_STAGES, strict=True))
        )
    )


def _embedded_receipt_points(
    crash_receipts: Mapping[str, Any] | None,
    *,
    performance: Mapping[str, Any],
) -> list[Mapping[str, Any]] | None:
    if crash_receipts is None:
        return None
    raw_points = crash_receipts.get("points")
    if not isinstance(raw_points, list):
        return []
    expected_hash = stable_hash({key: value for key, value in crash_receipts.items() if key != "bundle_hash"})
    if (
        set(crash_receipts) != {"schema_version", "source_report_hash", "points", "bundle_hash"}
        or crash_receipts.get("schema_version") != "p122.embedded_crash_receipts.v1"
        or crash_receipts.get("source_report_hash") != performance.get("report_hash")
        or crash_receipts.get("bundle_hash") != expected_hash
        or len(raw_points) != len(_P122_CRASH_STAGES)
    ):
        return []
    return [_mapping(item) for item in raw_points]


def _repo_relative_receipt_records(value: Any, *, root: Path) -> Mapping[str, Any]:
    point = _mapping(value)
    pending_path = _repo_relative_path(point.get("pending_ref"), root=root)
    receipt_path = _repo_relative_path(point.get("restart_receipt_ref"), root=root)
    output_path = _repo_relative_path(point.get("output_ref"), root=root)
    if pending_path is None or receipt_path is None or output_path is None:
        return {}
    if pending_path.name != "pending.json" or receipt_path.name != "restart-receipt.json" or pending_path.parent != receipt_path.parent:
        return {}
    return {
        "stage": point.get("stage"),
        "pending_record_hash": point.get("pending_record_hash"),
        "restart_receipt_hash": point.get("restart_receipt_hash"),
        "pending": _read(pending_path),
        "receipt": _read(receipt_path),
        "output_path": output_path,
    }


def _repo_relative_path(value: Any, *, root: Path) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        return None
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        return None
    return resolved


def _release_stage_point_valid(value: Any, *, index: int, stage: str, root: Path, records: Mapping[str, Any]) -> bool:
    point = _mapping(value)
    crash_pid = point.get("crash_worker_pid")
    recovery_pid = point.get("recovery_worker_pid")
    return (
        set(point)
        == {
            "stage",
            "operation",
            "operation_adapter",
            "output_schema",
            "correlation_id",
            "crash_injected",
            "crash_exit_code",
            "recovery_exit_code",
            "crash_worker_pid",
            "recovery_worker_pid",
            "recovered",
            "restart_verified",
            "restart_count",
            "pending_record_hash",
            "restart_receipt_hash",
            "pending_ref",
            "restart_receipt_ref",
            "precommit_hash",
            "output_hash",
            "output_ref",
            "adapter_invoked",
            "post_restart_validation",
            "recovered_at_seconds",
        }
        and point.get("stage") == stage
        and point.get("operation") == _P122_STAGE_OPERATIONS[stage]
        and point.get("operation_adapter") == _P122_STAGE_ADAPTERS[stage][0]
        and point.get("output_schema") == _P122_STAGE_ADAPTERS[stage][1]
        and point.get("correlation_id") == f"p122-crash-{index:02d}-{stage}"
        and point.get("crash_injected") is True
        and _exact_int(point.get("crash_exit_code"), 86)
        and _exact_int(point.get("recovery_exit_code"), 0)
        and _positive_int(crash_pid)
        and _positive_int(recovery_pid)
        and crash_pid != recovery_pid
        and point.get("recovered") is True
        and point.get("restart_verified") is True
        and _exact_int(point.get("restart_count"), 1)
        and _SHA256_PATTERN.fullmatch(str(point.get("pending_record_hash", ""))) is not None
        and _SHA256_PATTERN.fullmatch(str(point.get("restart_receipt_hash", ""))) is not None
        and _crash_point_refs_valid(point, index=index, stage=stage, root=root)
        and point.get("adapter_invoked") is True
        and point.get("post_restart_validation") is True
        and point.get("precommit_hash") == point.get("output_hash")
        and _SHA256_PATTERN.fullmatch(str(point.get("output_hash", ""))) is not None
        and _performance_artifacts_valid(point, records=records, index=index, stage=stage)
        and _finite_number(point.get("recovered_at_seconds"), minimum=0.0)
    )


def _crash_point_refs_valid(point: Mapping[str, Any], *, index: int, stage: str, root: Path) -> bool:
    artifact_name = _P122_STAGE_ADAPTERS[stage][2]
    base = f"evals/p122/performance-artifacts/crash-replay/{index:02d}-{stage}"
    expected = {
        "pending_ref": f"{base}/pending.json",
        "restart_receipt_ref": f"{base}/restart-receipt.json",
        "output_ref": f"{base}/committed/{artifact_name}",
    }
    if any(point.get(key) != value for key, value in expected.items()):
        return False
    pending_path = _repo_relative_path(expected["pending_ref"], root=root)
    receipt_path = _repo_relative_path(expected["restart_receipt_ref"], root=root)
    output_path = _repo_relative_path(expected["output_ref"], root=root)
    return (
        pending_path is not None
        and pending_path.is_file()
        and receipt_path is not None
        and receipt_path.is_file()
        and output_path is not None
        and output_path.exists()
        and not output_path.is_symlink()
    )


def _performance_artifacts_valid(
    point: Mapping[str, Any],
    *,
    records: Mapping[str, Any],
    index: int,
    stage: str,
) -> bool:
    pending = _mapping(records.get("pending"))
    receipt = _mapping(records.get("receipt"))
    operation = _P122_STAGE_OPERATIONS[stage]
    adapter, output_schema, artifact_name = _P122_STAGE_ADAPTERS[stage]
    output_path = records.get("output_path")
    output_hash = _artifact_hash(output_path) if isinstance(output_path, Path) else point.get("output_hash")
    correlation_id = f"p122-crash-{index:02d}-{stage}"
    pending_keys = {
        "schema_version",
        "stage",
        "operation",
        "operation_adapter",
        "output_schema",
        "durable_phase",
        "correlation_id",
        "ordinal",
        "status",
        "adapter_invoked",
        "precommit_ref",
        "output_ref",
        "precommit_kind",
        "precommit_hash",
        "precommit_validation_hash",
        "worker_pid",
        "parent_pid",
        "record_hash",
    }
    receipt_keys = {
        "schema_version",
        "stage",
        "operation",
        "operation_adapter",
        "output_schema",
        "durable_phase",
        "correlation_id",
        "ordinal",
        "status",
        "adapter_invoked",
        "precommit_hash",
        "precommit_validation_hash",
        "output_hash",
        "output_validation",
        "post_restart_validation",
        "pending_record_hash",
        "pending_worker_pid",
        "recovery_worker_pid",
        "restart_count",
        "record_hash",
    }
    return (
        set(records) in (
            {"stage", "pending_record_hash", "restart_receipt_hash", "pending", "receipt"},
            {"stage", "pending_record_hash", "restart_receipt_hash", "pending", "receipt", "output_path"},
        )
        and records.get("stage") == stage
        and records.get("pending_record_hash") == point.get("pending_record_hash")
        and records.get("restart_receipt_hash") == point.get("restart_receipt_hash")
        and set(pending) == pending_keys
        and pending.get("schema_version") == "p122.release_stage_pending.v1"
        and pending.get("stage") == stage
        and pending.get("operation") == operation
        and pending.get("operation_adapter") == adapter
        and pending.get("output_schema") == output_schema
        and pending.get("durable_phase") == f"{operation}_pending"
        and pending.get("correlation_id") == correlation_id
        and _exact_int(pending.get("ordinal"), index)
        and pending.get("status") == "pending"
        and pending.get("adapter_invoked") is True
        and pending.get("precommit_ref") == f"precommit/{artifact_name}"
        and pending.get("output_ref") == f"committed/{artifact_name}"
        and pending.get("precommit_kind") in {"file", "directory"}
        and pending.get("precommit_hash") == point.get("precommit_hash")
        and _SHA256_PATTERN.fullmatch(str(pending.get("precommit_validation_hash", ""))) is not None
        and pending.get("worker_pid") == point.get("crash_worker_pid")
        and _positive_int(pending.get("parent_pid"))
        and _record_hash_valid(pending)
        and pending.get("record_hash") == point.get("pending_record_hash")
        and set(receipt) == receipt_keys
        and receipt.get("schema_version") == "p122.release_stage_restart_receipt.v1"
        and receipt.get("stage") == stage
        and receipt.get("operation") == operation
        and receipt.get("operation_adapter") == adapter
        and receipt.get("output_schema") == output_schema
        and receipt.get("durable_phase") == f"{operation}_recovered"
        and receipt.get("correlation_id") == correlation_id
        and _exact_int(receipt.get("ordinal"), index)
        and receipt.get("status") == "recovered_after_restart"
        and receipt.get("adapter_invoked") is True
        and receipt.get("precommit_hash") == pending.get("precommit_hash") == point.get("precommit_hash")
        and receipt.get("precommit_validation_hash") == pending.get("precommit_validation_hash")
        and receipt.get("output_hash") == point.get("output_hash") == output_hash
        and set(_mapping(receipt.get("output_validation"))) == _P122_OUTPUT_VALIDATION_KEYS[stage]
        and _mapping(receipt.get("output_validation")).get("schema_version") == output_schema
        and receipt.get("post_restart_validation") is True
        and receipt.get("pending_record_hash") == pending.get("record_hash")
        and receipt.get("pending_worker_pid") == point.get("crash_worker_pid")
        and receipt.get("recovery_worker_pid") == point.get("recovery_worker_pid")
        and _exact_int(receipt.get("restart_count"), 1)
        and _record_hash_valid(receipt)
        and receipt.get("record_hash") == point.get("restart_receipt_hash")
    )


def _record_hash_valid(record: Mapping[str, Any]) -> bool:
    return record.get("record_hash") == stable_hash({key: value for key, value in record.items() if key != "record_hash"})


def _artifact_hash(path: Path) -> str:
    if path.is_file():
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    if not path.is_dir():
        return ""
    entries: list[dict[str, Any]] = []
    for item in sorted(path.rglob("*")):
        if item.is_symlink():
            return ""
        if item.is_file():
            entries.append(
                {
                    "path": item.relative_to(path).as_posix(),
                    "size": item.stat().st_size,
                    "hash": "sha256:" + hashlib.sha256(item.read_bytes()).hexdigest(),
                }
            )
    return stable_hash({"kind": "directory", "entries": entries})


def _performance_report_valid(
    performance: Mapping[str, Any],
    *,
    root: Path = _ROOT,
    crash_receipts: Mapping[str, Any] | None = None,
) -> bool:
    iterations = performance.get("iterations")
    return (
        set(performance)
        == {
            "schema_version",
            "iterations",
            "elapsed_seconds",
            "duration_seconds",
            "cpu_seconds",
            "cpu_utilization_ratio",
            "events_per_second",
            "replays_per_second",
            "expected_records",
            "observed_records",
            "lost_incident_records",
            "lost_audit_records",
            "lost_timeline_records",
            "lost_replay_records",
            "lost_authority_records",
            "unique_replay_files",
            "deterministic_content_hash_count",
            "max_rss_kib",
            "context",
            "timings_seconds",
            "storage_envelope",
            "release_stage_crash_inventory",
            "release_stage_crash_replay",
            "upstream_executed_crash_replay",
            "observability",
            "authority_counters",
            "scope_limit",
            "semantic_binding",
            "report_hash",
        }
        and performance.get("schema_version") == "p122.performance_soak.v2"
        and _report_hash_current(performance)
        and performance.get("semantic_binding") == _performance_semantic_projection(performance)["projection_hash"]
        and isinstance(iterations, int)
        and not isinstance(iterations, bool)
        and iterations >= 1000
        and _performance_record_denominators_valid(performance, iterations=iterations)
        and _performance_measurements_valid(performance, iterations=iterations)
        and _release_stage_crash_replay_valid(performance, root=root, crash_receipts=crash_receipts)
        and _p121_restart_recovery_proof_valid(performance)
        and _observability_valid(performance, iterations=iterations, portable=crash_receipts is not None, root=root)
        and _exact_p121_authority_counters(performance.get("authority_counters"))
    )


def _performance_semantic_projection(report: Mapping[str, Any]) -> dict[str, Any]:
    crash_replay = _mapping(report.get("release_stage_crash_replay"))
    raw_points = crash_replay.get("points")
    points: Sequence[Any] = raw_points if isinstance(raw_points, list) else ()
    point_projection = [
        {
            "stage": point.get("stage"),
            "operation": point.get("operation"),
            "operation_adapter": point.get("operation_adapter"),
            "output_schema": point.get("output_schema"),
            "crash_exit_code": point.get("crash_exit_code"),
            "recovery_exit_code": point.get("recovery_exit_code"),
            "adapter_invoked": point.get("adapter_invoked"),
            "precommit_hash": point.get("precommit_hash"),
            "output_hash": point.get("output_hash"),
            "post_restart_validation": point.get("post_restart_validation"),
            "restart_verified": point.get("restart_verified"),
        }
        for point in map(_mapping, points)
    ]
    upstream = _mapping(report.get("upstream_executed_crash_replay"))
    observability = _mapping(report.get("observability"))
    readiness = _mapping(observability.get("readiness"))
    metrics = _mapping(observability.get("metrics"))
    diagnostics = _mapping(observability.get("diagnostics"))
    rejection = _mapping(observability.get("authority_rejection"))
    projection: dict[str, Any] = {
        "schema_version": report.get("schema_version"),
        "iterations": report.get("iterations"),
        "expected_records": dict(_mapping(report.get("expected_records"))),
        "observed_records": dict(_mapping(report.get("observed_records"))),
        "record_loss": {
            key: report.get(key)
            for key in (
                "lost_incident_records",
                "lost_audit_records",
                "lost_timeline_records",
                "lost_replay_records",
                "lost_authority_records",
            )
        },
        "unique_replay_files": report.get("unique_replay_files"),
        "release_stage_crash_inventory": report.get("release_stage_crash_inventory"),
        "release_stage_crash_protocol": crash_replay.get("protocol"),
        "release_stage_crash_counts": {
            key: crash_replay.get(key)
            for key in ("point_count", "injected_count", "recovered_count", "observed_restart_receipt_count", "verified")
        },
        "release_stage_restart_receipts": point_projection,
        "upstream_crash_replay": {
            key: upstream.get(key)
            for key in ("point_count", "replayed_count", "pending_rollback_replayed", "pending_rollback_count_after_replay")
        },
        "authority_counters": dict(_mapping(report.get("authority_counters"))),
        "observability": {
            "ready": readiness.get("ready"),
            "readiness_checks": dict(_mapping(readiness.get("checks"))),
            "records_lost_total": metrics.get("records_lost_total"),
            "release_stage_crashes_injected_total": metrics.get("release_stage_crashes_injected_total"),
            "release_stage_crashes_recovered_total": metrics.get("release_stage_crashes_recovered_total"),
            "authority_rejections_total": metrics.get("authority_rejections_total"),
            "authority_rejection_observed": rejection.get("observed"),
            "authority_rejection_reason": rejection.get("reason"),
            "authority_rejection_fail_closed": rejection.get("fail_closed"),
            "redaction_verified": diagnostics.get("redaction_verified"),
            "replay_inspectable": diagnostics.get("replay_inspectable"),
        },
        "scope_limit": report.get("scope_limit"),
    }
    return {**projection, "projection_hash": stable_hash(projection)}


def _performance_record_denominators_valid(performance: Mapping[str, Any], *, iterations: int) -> bool:
    expected = {
        "incident_records": iterations,
        "audit_records": iterations * 4,
        "timeline_records": iterations * 4,
        "replay_records": iterations,
        "authority_records": iterations,
    }
    lost_keys = {f"lost_{name}" for name in expected}
    return (
        dict(_mapping(performance.get("expected_records"))) == expected
        and dict(_mapping(performance.get("observed_records"))) == expected
        and all(_exact_int(performance.get(key), 0) for key in lost_keys)
        and {key for key in performance if str(key).startswith("lost_")} == lost_keys
        and _exact_int(performance.get("unique_replay_files"), iterations)
        and _exact_int(performance.get("deterministic_content_hash_count"), 1)
    )


def _performance_measurements_valid(performance: Mapping[str, Any], *, iterations: int) -> bool:
    duration = performance.get("duration_seconds")
    timings = _mapping(performance.get("timings_seconds"))
    storage = _mapping(performance.get("storage_envelope"))
    timing_keys = {"install", "cold_start", "demo_total", "demo_min", "demo_max", "demo_mean"}
    timing_values = {key: timings.get(key) for key in timing_keys}
    total_bytes = storage.get("total_bytes")
    duration_value = float(duration) if isinstance(duration, int | float) and not isinstance(duration, bool) else -1.0
    cpu_seconds_value = _numeric_value(performance.get("cpu_seconds"))
    cpu_ratio_value = _numeric_value(performance.get("cpu_utilization_ratio"))
    events_per_second_value = _numeric_value(performance.get("events_per_second"))
    replays_per_second_value = _numeric_value(performance.get("replays_per_second"))
    demo_total = timings.get("demo_total")
    demo_total_value = float(demo_total) if isinstance(demo_total, int | float) and not isinstance(demo_total, bool) else -1.0
    return (
        set(_mapping(performance.get("context"))) == {"python", "platform", "machine", "cpu_count"}
        and all(isinstance(_mapping(performance.get("context")).get(key), str) and bool(_mapping(performance.get("context")).get(key)) for key in ("python", "platform", "machine"))
        and _positive_int(_mapping(performance.get("context")).get("cpu_count"))
        and set(timings) == {"install", "install_method", "cold_start", "demo_total", "demo_min", "demo_max", "demo_mean", "demo_samples"}
        and set(storage) == {"total_bytes", "file_count", "largest_file_bytes", "bytes_per_iteration", "scope"}
        and _finite_number(duration, minimum=0.0, positive=True)
        and performance.get("elapsed_seconds") == duration
        and _finite_number(performance.get("cpu_seconds"), minimum=0.0)
        and _finite_number(performance.get("cpu_utilization_ratio"), minimum=0.0)
        and math.isclose(cpu_ratio_value, cpu_seconds_value / duration_value, rel_tol=1e-9, abs_tol=1e-9)
        and _finite_number(performance.get("events_per_second"), minimum=0.0, positive=True)
        and math.isclose(events_per_second_value, iterations * 4 / duration_value, rel_tol=1e-9, abs_tol=1e-9)
        and _finite_number(performance.get("replays_per_second"), minimum=0.0, positive=True)
        and math.isclose(replays_per_second_value, iterations / duration_value, rel_tol=1e-9, abs_tol=1e-9)
        and _positive_int(performance.get("max_rss_kib"))
        and timings.get("install_method") == "wheel-extract"
        and _exact_int(timings.get("demo_samples"), iterations)
        and all(_finite_number(value, minimum=0.0) for value in timing_values.values())
        and _finite_number(timings.get("demo_total"), minimum=0.0, positive=True)
        and float(timings.get("demo_min", -1)) <= float(timings.get("demo_mean", -1)) <= float(timings.get("demo_max", -1))
        and duration_value >= demo_total_value
        and isinstance(total_bytes, int)
        and not isinstance(total_bytes, bool)
        and total_bytes > 0
        and all(_positive_int(storage.get(key)) for key in ("file_count", "largest_file_bytes"))
        and int(storage.get("largest_file_bytes", 0)) <= total_bytes
        and _finite_number(storage.get("bytes_per_iteration"), minimum=0.0, positive=True)
        and math.isclose(float(storage.get("bytes_per_iteration", 0)), total_bytes / iterations, rel_tol=1e-9, abs_tol=1e-9)
        and storage.get("scope") == "workdir including install, record, WAL, and crash-replay artifacts"
        and performance.get("scope_limit") == "local fixture performance only; not production capacity evidence"
    )


def _p121_restart_recovery_proof_valid(performance: Mapping[str, Any]) -> bool:
    proof = _mapping(performance.get("upstream_executed_crash_replay"))
    return (
        set(proof)
        == {
            "source",
            "proof_hash",
            "point_count",
            "replayed_count",
            "pending_rollback_replayed",
            "pending_rollback_count_after_replay",
        }
        and proof.get("source") == "app.services.p121_execution.prove_p121_restart_recovery"
        and proof.get("proof_hash") == _P121_RESTART_RECOVERY_PROOF_HASH
        and _SHA256_PATTERN.fullmatch(str(proof.get("proof_hash", ""))) is not None
        and _exact_int(proof.get("point_count"), 15)
        and _exact_int(proof.get("replayed_count"), 15)
        and proof.get("pending_rollback_replayed") is True
        and _exact_int(proof.get("pending_rollback_count_after_replay"), 0)
    )


def _observability_valid(
    performance: Mapping[str, Any],
    *,
    iterations: int,
    portable: bool = False,
    root: Path = _ROOT,
) -> bool:
    observability = _mapping(performance.get("observability"))
    health = _mapping(observability.get("health"))
    readiness = _mapping(observability.get("readiness"))
    metrics = _mapping(observability.get("metrics"))
    diagnostics = _mapping(observability.get("diagnostics"))
    rejection = _mapping(observability.get("authority_rejection"))
    logs = observability.get("correlated_logs")
    expected_metrics = {
        "iterations_total": iterations,
        "records_observed_total": iterations * 11,
        "records_lost_total": 0,
        "release_stage_crashes_injected_total": 12,
        "release_stage_crashes_recovered_total": 12,
        "authority_rejections_total": 1,
    }
    return (
        set(observability) == {"health", "readiness", "metrics", "correlated_logs", "diagnostics", "authority_rejection"}
        and dict(health) == {"status": "healthy", "local_fixture": True}
        and set(readiness) == {"ready", "checks"}
        and readiness.get("ready") is True
        and dict(_mapping(readiness.get("checks")))
        == {"authority_rejection_observed": True, "record_loss_zero": True, "release_crashes_recovered": True}
        and dict(metrics) == expected_metrics
        and _correlated_logs_valid(logs)
        and _diagnostics_valid(diagnostics, portable=portable, root=root)
        and dict(rejection)
        == {
            "correlation_id": "p122-authority-rejection-00",
            "reason": "production_like_demo_configuration_denied",
            "observed": True,
            "fail_closed": True,
            "output_created": False,
        }
    )


def _correlated_logs_valid(value: Any) -> bool:
    if not isinstance(value, list) or len(value) != len(_P122_CRASH_STAGES) + 1:
        return False
    for index, stage in enumerate(_P122_CRASH_STAGES):
        log = _mapping(value[index])
        if not (
            set(log) == {"correlation_id", "event", "level", "stage", "timestamp_monotonic_seconds"}
            and log.get("correlation_id") == f"p122-crash-{index:02d}-{stage}"
            and log.get("event") == "release_stage_crash_recovered"
            and log.get("level") == "INFO"
            and log.get("stage") == stage
            and _finite_number(log.get("timestamp_monotonic_seconds"), minimum=0.0)
        ):
            return False
    rejection_log = _mapping(value[-1])
    return (
        set(rejection_log) == {"correlation_id", "event", "level", "reason", "timestamp_monotonic_seconds"}
        and rejection_log.get("correlation_id") == "p122-authority-rejection-00"
        and rejection_log.get("event") == "authority_rejected"
        and rejection_log.get("level") == "WARNING"
        and rejection_log.get("reason") == "production_like_demo_configuration_denied"
        and _finite_number(rejection_log.get("timestamp_monotonic_seconds"), minimum=0.0)
    )


def _diagnostics_valid(diagnostics: Mapping[str, Any], *, portable: bool = False, root: Path = _ROOT) -> bool:
    redacted = _mapping(diagnostics.get("redacted_sample"))
    crash_root = _repo_relative_path(diagnostics.get("crash_replay_artifact_root"), root=root)
    record_root = _repo_relative_path(diagnostics.get("record_artifact_root"), root=root)
    return (
        set(diagnostics) == {"crash_replay_artifact_root", "record_artifact_root", "redacted_sample", "redaction_verified", "replay_inspectable"}
        and diagnostics.get("redaction_verified") is True
        and diagnostics.get("replay_inspectable") is True
        and (portable or (crash_root is not None and crash_root.is_dir()))
        and (portable or (record_root is not None and record_root.is_dir()))
        and dict(redacted) == {"api_key": "[REDACTED]", "message": "Authorization: Bearer [REDACTED]", "scope": "local-fixture"}
        and "p122-secret-fixture" not in json.dumps(dict(diagnostics), sort_keys=True)
    )


def _exact_int(value: Any, expected: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == expected


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _finite_number(value: Any, *, minimum: float, positive: bool = False) -> bool:
    if not isinstance(value, int | float) or isinstance(value, bool) or not math.isfinite(float(value)):
        return False
    return float(value) > minimum if positive else float(value) >= minimum


def _numeric_value(value: Any) -> float:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else math.nan


def _source_manifest(root: Path) -> tuple[str, ...]:
    names = set(_REQUIRED_SOURCE_PATHS)
    for pattern in _SOURCE_PATTERNS:
        names.update(path.relative_to(root).as_posix() for path in root.glob(pattern) if _source_manifest_path_allowed(root, path))
    pending = [name for name in names if name.endswith(".py") and (root / name).is_file()]
    scanned: set[str] = set()
    while pending:
        name = pending.pop()
        if name in scanned:
            continue
        scanned.add(name)
        for dependency in _python_source_dependencies(root, name):
            if dependency not in names:
                names.add(dependency)
                pending.append(dependency)
    return tuple(sorted(name for name in names if _source_manifest_path_allowed(root, root / name)))


def _source_manifest_path_allowed(root: Path, path: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    return (
        path.is_file()
        and not path.is_symlink()
        and relative.name not in _IGNORED_SOURCE_NAMES
        and not relative.name.startswith("._")
        and not any(part in _IGNORED_SOURCE_PARTS for part in relative.parts)
    )


def _python_source_dependencies(root: Path, name: str) -> set[str]:
    path = root / name
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=name)
    except (OSError, SyntaxError, UnicodeDecodeError):
        return set()
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
            modules.update(f"{node.module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=True):
                if isinstance(key, ast.Constant) and key.value == "owner_module" and isinstance(value, ast.Constant) and isinstance(value.value, str):
                    modules.add(value.value)
    return {resolved for module in modules if (resolved := _resolve_python_module(root, module)) is not None}


def _resolve_python_module(root: Path, module: str) -> str | None:
    if not module.startswith(("app", "scripts")):
        return None
    module_path = Path(*module.split("."))
    candidates = (module_path.with_suffix(".py"), module_path / "__init__.py")
    for candidate in candidates:
        if (root / candidate).is_file():
            return candidate.as_posix()
    return None


def _source_hashes(root: Path) -> dict[str, str]:
    return {name: _file_hash(root / name) for name in _source_manifest(root)}


def _file_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


__all__ = ["produce_p122_release_evidence", "validate_p122_release_evidence"]
