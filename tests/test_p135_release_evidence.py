from __future__ import annotations

import hashlib
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p135_release_evidence import (
    EXPECTED_REJECTION_ERRORS,
    EXPECTED_SOURCE_BINDINGS,
    PRODUCT_CLAIM,
    PUBLIC_LIMITATION,
    REQUIRED_CASES,
    P135ReleaseEvidenceError,
    build_authority_ledger,
    build_independent_review_artifact,
    build_p135_release_evidence,
    validate_authority_ledger,
    validate_independent_review_artifact,
    validate_p135_release_evidence,
)


def _source_root(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    root = tmp_path / "project"
    hashes: dict[str, str] = {}
    for index, relative in enumerate(sorted(EXPECTED_SOURCE_BINDINGS), start=1):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"source-{index}\n", encoding="utf-8")
        hashes[relative] = f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
    return root, hashes


def _case(name: str, *, outcome: str = "passed", provider: str | None = None, error: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "passed": True,
        "outcome": outcome,
        "provider": provider,
        "error": error,
        "authority_zero": True,
        "no_network_credentials_actions": True,
    }
    payload["case_hash"] = stable_hash(payload)
    return payload


def _matrix() -> dict[str, Any]:
    providers = {
        "prometheus_matrix_success": "prometheus",
        "loki_streams_success": "loki",
        "grafana_dashboard_success": "grafana",
        "sentry_issues_success": "sentry",
        "otlp_metrics_success": "opentelemetry",
    }
    cases = {
        name: _case(
            name,
            outcome="success" if name in providers else "duplicate" if name == "deterministic_duplicate" else "rejected",
            provider=providers.get(name),
            error=(
                None
                if name in providers or name == "deterministic_duplicate"
                else EXPECTED_REJECTION_ERRORS[name]
            ),
        )
        for name in REQUIRED_CASES
    }
    payload: dict[str, Any] = {
        "schema_version": "p135.release_case_matrix.v1",
        "required_cases": list(REQUIRED_CASES),
        "cases": cases,
        "totals": {
            "expected_cases": 30,
            "passed_cases": 30,
            "failed_cases": 0,
            "successful_provider_attachments": 5,
            "duplicate_cases": 1,
            "rejected_cases": 24,
            "denominator_scope": "principal_provider_export_assertions",
        },
        "provider_successes": {
            "grafana": 1,
            "loki": 1,
            "opentelemetry": 1,
            "prometheus": 1,
            "sentry": 1,
        },
        "resource_usage": {
            "wall_time_ms": 100,
            "cpu_time_ms": 50,
            "peak_memory_bytes": 20_000_000,
            "wall_limit_ms": 30_000,
            "cpu_limit_ms": 10_000,
            "peak_memory_limit_bytes": 100_663_296,
        },
        "matrix_hash": "",
    }
    payload["matrix_hash"] = stable_hash({key: value for key, value in payload.items() if key != "matrix_hash"})
    return payload


def _artifacts(tmp_path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], Path]:
    root, source_hashes = _source_root(tmp_path)
    matrix = _matrix()
    authority_ledger = build_authority_ledger(
        evaluator_activity={
            "runner_invocation_count": 1,
            "profile_read_count": 1,
            "artifact_write_count": 5,
        },
        observation_activity={
            "local_stat_count": 8,
            "local_file_open_count": 8,
            "local_file_read_count": 8,
            "local_bytes_read": 1000,
            "local_records_parsed": 8,
            "duplicate_validation_read_count": 1,
        },
    )
    review = build_independent_review_artifact(
        reviewed_source_hashes=source_hashes,
        reviewer_context_hash=stable_hash({"context": "reviewer"}),
        implementation_context_hash=stable_hash({"context": "implementation"}),
        findings={"p0": 0, "p1": 0, "p2": 0, "p3": 0},
    )
    evidence = build_p135_release_evidence(matrix, authority_ledger, review, project_root=root)
    return evidence, matrix, authority_ledger, review, root


def test_release_evidence_qualifies_exact_30_case_provider_export(tmp_path: Path) -> None:
    evidence, matrix, authority_ledger, review, root = _artifacts(tmp_path)

    assert evidence["release_status"] == "p135_provider_shaped_export_attachment_qualified"
    assert evidence["product_claim"] == PRODUCT_CLAIM
    assert evidence["public_limitation"] == PUBLIC_LIMITATION
    assert evidence["totals"] == {"expected_cases": 30, "passed_cases": 30, "failed_cases": 0}
    assert all(evidence["gates"].values())
    validate_p135_release_evidence(
        evidence,
        case_matrix=matrix,
        authority_ledger=authority_ledger,
        independent_review=review,
        project_root=root,
    )


def test_release_blocks_missing_case_and_overclaim(tmp_path: Path) -> None:
    _, matrix, authority_ledger, review, root = _artifacts(tmp_path)
    drifted = deepcopy(matrix)
    drifted["cases"].pop("nonzero_forbidden_authority_rejected")
    drifted["matrix_hash"] = stable_hash({key: value for key, value in drifted.items() if key != "matrix_hash"})
    blocked = build_p135_release_evidence(drifted, authority_ledger, review, project_root=root)

    assert blocked["release_status"] == "p135_blocked"
    assert blocked["gates"]["case_matrix_substantive"] is False
    with pytest.raises(P135ReleaseEvidenceError, match="release_gate_failed"):
        validate_p135_release_evidence(
            blocked,
            case_matrix=drifted,
            authority_ledger=authority_ledger,
            independent_review=review,
            project_root=root,
        )

    overclaim = deepcopy(blocked)
    overclaim["product_claim"] = "P135 proves live production provider attachment with credentials."
    overclaim["release_evidence_hash"] = stable_hash(
        {key: value for key, value in overclaim.items() if key != "release_evidence_hash"}
    )
    with pytest.raises(P135ReleaseEvidenceError, match="release_claim_mismatch"):
        validate_p135_release_evidence(
            overclaim,
            case_matrix=drifted,
            authority_ledger=authority_ledger,
            independent_review=review,
            project_root=root,
        )

    wrong_reason = _matrix()
    wrong_reason["cases"]["content_hash_mismatch_rejected"]["error"] = "some_other_error"
    wrong_reason["cases"]["content_hash_mismatch_rejected"]["case_hash"] = stable_hash(
        {
            key: value
            for key, value in wrong_reason["cases"]["content_hash_mismatch_rejected"].items()
            if key != "case_hash"
        }
    )
    wrong_reason["matrix_hash"] = stable_hash(
        {key: value for key, value in wrong_reason.items() if key != "matrix_hash"}
    )
    blocked_reason = build_p135_release_evidence(
        wrong_reason,
        authority_ledger,
        review,
        project_root=root,
    )
    assert blocked_reason["release_status"] == "p135_blocked"


def test_authority_ledger_rejects_nonzero_forbidden_and_boolean_activity() -> None:
    ledger = build_authority_ledger(
        evaluator_activity={"runner_invocation_count": 1, "profile_read_count": 1, "artifact_write_count": 5},
        observation_activity={
            "local_stat_count": 1,
            "local_file_open_count": 1,
            "local_file_read_count": 1,
            "local_bytes_read": 10,
            "local_records_parsed": 1,
            "duplicate_validation_read_count": 0,
        },
    )
    validate_authority_ledger(ledger)

    nonzero = deepcopy(ledger)
    nonzero["forbidden_authority"]["network_call_count"] = 1
    nonzero["authority_ledger_hash"] = stable_hash(
        {key: value for key, value in nonzero.items() if key != "authority_ledger_hash"}
    )
    with pytest.raises(P135ReleaseEvidenceError, match="forbidden_authority_not_zero"):
        validate_authority_ledger(nonzero)

    boolean = deepcopy(ledger)
    boolean["observation_activity"]["local_file_read_count"] = True
    boolean["authority_ledger_hash"] = stable_hash(
        {key: value for key, value in boolean.items() if key != "authority_ledger_hash"}
    )
    with pytest.raises(P135ReleaseEvidenceError, match="invalid_observation_activity"):
        validate_authority_ledger(boolean)


def test_independent_review_requires_current_sources_and_zero_blocking_findings(tmp_path: Path) -> None:
    _, hashes = _source_root(tmp_path)
    review = build_independent_review_artifact(
        reviewed_source_hashes=hashes,
        reviewer_context_hash=stable_hash({"context": "same"}),
        implementation_context_hash=stable_hash({"context": "same"}),
        findings={"p0": 0, "p1": 0, "p2": 0, "p3": 0},
    )
    with pytest.raises(P135ReleaseEvidenceError, match="review_context_not_independent"):
        validate_independent_review_artifact(review, expected_source_hashes=hashes)

    blocking = deepcopy(review)
    blocking["reviewer_context_hash"] = stable_hash({"context": "reviewer"})
    blocking["findings"]["p1"] = 1
    blocking["independent_review_hash"] = stable_hash(
        {key: value for key, value in blocking.items() if key != "independent_review_hash"}
    )
    with pytest.raises(P135ReleaseEvidenceError, match="review_blocking_findings"):
        validate_independent_review_artifact(blocking, expected_source_hashes=hashes)
