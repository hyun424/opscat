from __future__ import annotations

import hashlib
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p121_signals import zero_authority_counters
from app.services.p134_observation_authority import (
    build_contract,
    build_contract_core,
    build_proposal,
    build_review_receipt,
    evaluate_proposal,
    new_receipt_ledger,
)
from app.services.p134_release_evidence import (
    EXPECTED_SOURCE_BINDINGS,
    PRODUCT_CLAIM,
    PUBLIC_LIMITATION,
    P134ReleaseEvidenceError,
    build_authority_ledger,
    build_independent_review_artifact,
    build_p134_release_evidence,
    validate_authority_ledger,
    validate_independent_review_artifact,
    validate_p134_release_evidence,
)

CONTRACT_CASES = (
    "oa0_default_deny",
    "oa1_allowed",
    "deterministic_duplicate",
    "capability_denied",
    "host_denied",
    "method_denied",
    "level_escalation_denied",
    "kill_switch_deny",
    "contract_not_yet_valid",
    "contract_expired",
    "allowed_request_budget_exhausted",
    "byte_budget_exhausted",
    "record_budget_exhausted",
    "host_budget_exhausted",
    "capability_budget_exhausted",
    "response_byte_estimate_too_large",
    "timeout_too_large",
    "attempt_budget_exhausted",
)
FAULT_CASES = (
    "tampered_review_receipt",
    "changed_request_id_replay",
    "boolean_counter_rejected",
    "url_credential_input_rejected",
    "ledger_reorder_rejected",
    "nonzero_action_authority_rejected",
)
EXPECTED_REASONS = {
    "oa0_default_deny": "contract_only_level",
    "capability_denied": "capability_not_allowlisted",
    "host_denied": "host_not_allowlisted",
    "method_denied": "method_not_allowlisted",
    "level_escalation_denied": "authority_level_not_qualified",
    "kill_switch_deny": "kill_switch_active",
    "contract_not_yet_valid": "contract_not_yet_valid",
    "contract_expired": "contract_expired",
    "allowed_request_budget_exhausted": "allowed_request_budget_exceeded",
    "byte_budget_exhausted": "cumulative_byte_budget_exceeded",
    "record_budget_exhausted": "cumulative_record_budget_exceeded",
    "host_budget_exhausted": "host_budget_exceeded",
    "capability_budget_exhausted": "capability_budget_exceeded",
    "response_byte_estimate_too_large": "single_response_byte_budget_exceeded",
    "timeout_too_large": "timeout_budget_exceeded",
    "attempt_budget_exhausted": "attempt_budget_exceeded",
}
EXPECTED_ERRORS = {
    "tampered_review_receipt": "review_receipt_hash_invalid",
    "changed_request_id_replay": "request_id_reuse_conflict",
    "boolean_counter_rejected": "invalid_counter:evaluated_count",
    "url_credential_input_rejected": "unsafe_host_label",
    "ledger_reorder_rejected": "receipt_sequence_mismatch",
    "nonzero_action_authority_rejected": "production_mutation_count_nonzero",
}


def _contract() -> dict[str, Any]:
    core = build_contract_core(
        {
            "contract_id": "release-profile",
            "contract_version": 1,
            "subject_ref_hash": stable_hash({"subject": "release-subject"}),
            "max_authority_level": "OA1_LOCAL_ARTIFACT",
            "allowed_hosts": ["local-artifact.logs", "local-artifact.metrics"],
            "allowed_methods": ["LOCAL_READ_FILE", "LOCAL_STAT"],
            "allowed_capabilities": ["telemetry.logs.read", "telemetry.metrics.read"],
            "budgets": {
                "window_seconds": 3600,
                "max_allowed_requests_per_window": 8,
                "max_allowed_estimated_response_bytes_per_window": 10_000,
                "max_allowed_estimated_records_per_window": 1_000,
                "max_unique_hosts_per_window": 2,
                "max_unique_methods_per_window": 2,
                "max_unique_capabilities_per_window": 2,
                "max_single_response_bytes": 4_000,
                "max_timeout_ms": 5_000,
                "max_attempt_number": 3,
            },
            "valid_from": "2026-07-13T00:00:00Z",
            "expires_at": "2026-07-14T00:00:00Z",
            "default_decision": "deny",
            "kill_switch": False,
            "action_authority": zero_authority_counters(),
        }
    )
    review = build_review_receipt(
        core,
        {
            "decision": "approve",
            "reviewer_ref_hash": stable_hash({"reviewer": "release-review"}),
            "reviewed_at": "2026-07-13T00:00:01Z",
            "expires_at": "2026-07-13T23:59:59Z",
        },
    )
    return build_contract(core, review)


def _receipt_ledger(contract: dict[str, Any]) -> dict[str, Any]:
    ledger = new_receipt_ledger(contract, window_started_at="2026-07-13T00:00:00Z")
    for sequence, (host, method, capability) in enumerate(
        (
            ("local-artifact.metrics", "LOCAL_READ_FILE", "telemetry.metrics.read"),
            ("local-artifact.logs", "LOCAL_STAT", "telemetry.logs.read"),
        ),
        start=1,
    ):
        proposal = build_proposal(
            {
                "request_id": f"canonical-{sequence}",
                "sequence": sequence,
                "proposed_at": f"2026-07-13T00:{10 + sequence:02d}:00Z",
                "requested_level": "OA1_LOCAL_ARTIFACT",
                "source_ref_hash": stable_hash({"source": sequence}),
                "host_label": host,
                "method": method,
                "capability": capability,
                "estimated_response_bytes": 100 * sequence,
                "estimated_records": 10 * sequence,
                "timeout_ms": 1_000,
                "attempt_number": 1,
            }
        )
        ledger = evaluate_proposal(contract, proposal, ledger).ledger
    return ledger


def _case(
    *,
    outcome: str,
    decision: str | None,
    reasons: list[str] | None = None,
    duplicate: bool = False,
    ledger_unchanged: bool = False,
    error: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "passed": True,
        "outcome": outcome,
        "decision": decision,
        "reasons": reasons or [],
        "duplicate": duplicate,
        "ledger_unchanged": ledger_unchanged,
        "error": error,
    }
    payload["case_hash"] = stable_hash(payload)
    return payload


def _contract_matrix(contract: dict[str, Any]) -> dict[str, Any]:
    cases: dict[str, dict[str, Any]] = {}
    for name in CONTRACT_CASES:
        if name == "oa1_allowed":
            cases[name] = _case(outcome="allowed", decision="allowed")
        elif name == "deterministic_duplicate":
            cases[name] = _case(
                outcome="duplicate",
                decision="allowed",
                duplicate=True,
                ledger_unchanged=True,
            )
        else:
            cases[name] = _case(
                outcome="denied",
                decision="denied",
                reasons=[EXPECTED_REASONS[name]],
            )
    payload: dict[str, Any] = {
        "schema_version": "p134.contract_matrix.v1",
        "required_cases": list(CONTRACT_CASES),
        "cases": cases,
        "totals": {
            "expected_cases": 18,
            "passed_cases": 18,
            "failed_cases": 0,
            "allowed_cases": 1,
            "denied_cases": 16,
            "duplicate_cases": 1,
            "denominator_scope": "principal_contract_assertions",
        },
        "canonical_contract": contract,
        "resource_usage": {
            "wall_time_ms": 100,
            "cpu_time_ms": 50,
            "peak_memory_bytes": 20_000_000,
            "wall_limit_ms": 20_000,
            "cpu_limit_ms": 10_000,
            "peak_memory_limit_bytes": 67_108_864,
        },
    }
    payload["contract_matrix_hash"] = stable_hash(payload)
    return payload


def _fault_matrix() -> dict[str, Any]:
    cases = {
        name: _case(
            outcome="rejected",
            decision=None,
            ledger_unchanged=True,
            error=EXPECTED_ERRORS[name],
        )
        for name in FAULT_CASES
    }
    payload: dict[str, Any] = {
        "schema_version": "p134.fault_matrix.v1",
        "required_cases": list(FAULT_CASES),
        "cases": cases,
        "totals": {
            "expected_cases": 6,
            "passed_cases": 6,
            "failed_cases": 0,
            "rejected_cases": 6,
            "denominator_scope": "principal_fault_assertions",
        },
    }
    payload["fault_matrix_hash"] = stable_hash(payload)
    return payload


def _source_root(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    root = tmp_path / "project"
    hashes: dict[str, str] = {}
    for index, relative in enumerate(sorted(EXPECTED_SOURCE_BINDINGS), start=1):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"source-{index}\n", encoding="utf-8")
        hashes[relative] = f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
    return root, hashes


def _review(source_hashes: dict[str, str]) -> dict[str, Any]:
    return build_independent_review_artifact(
        reviewed_source_hashes=source_hashes,
        reviewer_context_hash=stable_hash({"context": "reviewer"}),
        implementation_context_hash=stable_hash({"context": "implementation"}),
        findings={"p0": 0, "p1": 0, "p2": 0, "p3": 1},
    )


def _artifacts(
    tmp_path: Path,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    Path,
]:
    root, source_hashes = _source_root(tmp_path)
    contract = _contract()
    contract_matrix = _contract_matrix(contract)
    fault_matrix = _fault_matrix()
    receipt_ledger = _receipt_ledger(contract)
    authority_ledger = build_authority_ledger(
        evaluator_activity={"runner_invocation_count": 1, "profile_read_count": 1, "artifact_write_count": 5}
    )
    independent_review = _review(source_hashes)
    evidence = build_p134_release_evidence(
        contract_matrix,
        fault_matrix,
        receipt_ledger,
        authority_ledger,
        independent_review,
        project_root=root,
    )
    return (
        evidence,
        contract_matrix,
        fault_matrix,
        receipt_ledger,
        authority_ledger,
        independent_review,
        root,
    )


def test_release_evidence_qualifies_exact_24_case_policy_only_contract(tmp_path: Path) -> None:
    evidence, contract_matrix, fault_matrix, receipt_ledger, authority_ledger, review, root = _artifacts(tmp_path)

    assert evidence["release_status"] == "p134_observation_authority_contract_qualified"
    assert evidence["product_claim"] == PRODUCT_CLAIM
    assert evidence["public_limitation"] == PUBLIC_LIMITATION
    assert evidence["totals"] == {"expected_cases": 24, "passed_cases": 24, "failed_cases": 0}
    assert all(evidence["gates"].values())
    validate_p134_release_evidence(
        evidence,
        contract_matrix=contract_matrix,
        fault_matrix=fault_matrix,
        receipt_ledger=receipt_ledger,
        authority_ledger=authority_ledger,
        independent_review=review,
        project_root=root,
    )


def test_release_blocks_missing_or_optimistic_case(tmp_path: Path) -> None:
    _, contract_matrix, fault_matrix, receipt_ledger, authority_ledger, review, root = _artifacts(tmp_path)
    contract_matrix = deepcopy(contract_matrix)
    contract_matrix["cases"].pop("host_denied")
    contract_matrix["contract_matrix_hash"] = stable_hash(
        {key: value for key, value in contract_matrix.items() if key != "contract_matrix_hash"}
    )

    evidence = build_p134_release_evidence(
        contract_matrix,
        fault_matrix,
        receipt_ledger,
        authority_ledger,
        review,
        project_root=root,
    )
    assert evidence["release_status"] == "p134_blocked"
    assert evidence["gates"]["contract_matrix_substantive"] is False
    with pytest.raises(P134ReleaseEvidenceError, match="release_gate_failed"):
        validate_p134_release_evidence(
            evidence,
            contract_matrix=contract_matrix,
            fault_matrix=fault_matrix,
            receipt_ledger=receipt_ledger,
            authority_ledger=authority_ledger,
            independent_review=review,
            project_root=root,
        )


def test_release_blocks_rehashed_unknown_matrix_fields(tmp_path: Path) -> None:
    _, contract_matrix, fault_matrix, receipt_ledger, authority_ledger, review, root = _artifacts(tmp_path)
    contract_matrix = deepcopy(contract_matrix)
    contract_matrix["optimistic_extension"] = True
    contract_matrix["contract_matrix_hash"] = stable_hash(
        {key: value for key, value in contract_matrix.items() if key != "contract_matrix_hash"}
    )

    evidence = build_p134_release_evidence(
        contract_matrix,
        fault_matrix,
        receipt_ledger,
        authority_ledger,
        review,
        project_root=root,
    )
    assert evidence["release_status"] == "p134_blocked"
    assert evidence["gates"]["contract_matrix_substantive"] is False


def test_authority_ledger_rejects_boolean_nonzero_and_mixed_activity() -> None:
    ledger = build_authority_ledger(
        evaluator_activity={"runner_invocation_count": 1, "profile_read_count": 1, "artifact_write_count": 5}
    )
    validate_authority_ledger(ledger)

    boolean = deepcopy(ledger)
    boolean["runtime_observation"]["socket_call_count"] = False
    boolean["authority_ledger_hash"] = stable_hash(
        {key: value for key, value in boolean.items() if key != "authority_ledger_hash"}
    )
    with pytest.raises(P134ReleaseEvidenceError, match="runtime_observation_not_zero"):
        validate_authority_ledger(boolean)

    nonzero = deepcopy(ledger)
    nonzero["evaluator_authority"]["subprocess_launch_count"] = 1
    nonzero["authority_ledger_hash"] = stable_hash(
        {key: value for key, value in nonzero.items() if key != "authority_ledger_hash"}
    )
    with pytest.raises(P134ReleaseEvidenceError, match="evaluator_authority_not_zero"):
        validate_authority_ledger(nonzero)

    for artifact_write_count in (0, 4, 999):
        invalid_activity = deepcopy(ledger)
        invalid_activity["evaluator_activity"]["artifact_write_count"] = artifact_write_count
        invalid_activity["authority_ledger_hash"] = stable_hash(
            {
                key: value
                for key, value in invalid_activity.items()
                if key != "authority_ledger_hash"
            }
        )
        with pytest.raises(P134ReleaseEvidenceError, match="evaluator_activity_invalid"):
            validate_authority_ledger(invalid_activity)


def test_independent_review_requires_distinct_contexts_current_sources_and_zero_p0_p1_p2(tmp_path: Path) -> None:
    _, hashes = _source_root(tmp_path)
    same = stable_hash({"context": "same"})
    review = build_independent_review_artifact(
        reviewed_source_hashes=hashes,
        reviewer_context_hash=same,
        implementation_context_hash=same,
        findings={"p0": 0, "p1": 0, "p2": 0, "p3": 0},
    )
    with pytest.raises(P134ReleaseEvidenceError, match="review_context_not_independent"):
        validate_independent_review_artifact(review, expected_source_hashes=hashes)

    findings = deepcopy(review)
    findings["reviewer_context_hash"] = stable_hash({"context": "other"})
    findings["findings"]["p2"] = 1
    findings["independent_review_hash"] = stable_hash(
        {key: value for key, value in findings.items() if key != "independent_review_hash"}
    )
    with pytest.raises(P134ReleaseEvidenceError, match="review_blocking_findings"):
        validate_independent_review_artifact(findings, expected_source_hashes=hashes)


def test_release_rejects_tamper_stale_source_and_execution_claim(tmp_path: Path) -> None:
    evidence, contract_matrix, fault_matrix, receipt_ledger, authority_ledger, review, root = _artifacts(tmp_path)

    tampered = deepcopy(evidence)
    tampered["product_claim"] = "P134 performs real file ingestion and live GET observation."
    tampered["release_evidence_hash"] = stable_hash(
        {key: value for key, value in tampered.items() if key != "release_evidence_hash"}
    )
    with pytest.raises(P134ReleaseEvidenceError, match="release_claim_mismatch"):
        validate_p134_release_evidence(
            tampered,
            contract_matrix=contract_matrix,
            fault_matrix=fault_matrix,
            receipt_ledger=receipt_ledger,
            authority_ledger=authority_ledger,
            independent_review=review,
            project_root=root,
        )

    stale_path = root / sorted(EXPECTED_SOURCE_BINDINGS)[0]
    stale_path.write_text("changed\n", encoding="utf-8")
    with pytest.raises(P134ReleaseEvidenceError, match="release_evidence_source_stale"):
        validate_p134_release_evidence(
            evidence,
            contract_matrix=contract_matrix,
            fault_matrix=fault_matrix,
            receipt_ledger=receipt_ledger,
            authority_ledger=authority_ledger,
            independent_review=review,
            project_root=root,
        )
