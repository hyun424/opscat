from __future__ import annotations

import hashlib
import importlib
import json
import re
import sys
from typing import Any

import pytest

from app.services import p147_p152_contracts

P152_SELECTOR_NAMES = (
    "test_contract_and_predecessor_fail_closed",
    "test_happy_path_report_and_counters",
    "test_fault_matrix_and_recovery",
    "test_forgery_and_authority_rejected",
    "test_release_evidence_requires_zero_finding_review",
)

P152_PHASES = ("p146", "p147", "p148", "p149", "p150", "p151")
P152_STATUSES = (
    "p146_live_shadow_qualification_ready",
    "p147_durable_provider_shadow_qualified",
    "p148_reversible_lab_action_qualified",
    "p149_canary_outcome_control_qualified",
    "p150_unattended_chaos_soak_qualified",
    "p151_ground_truth_quality_qualified",
)
P152_SCHEMAS = (
    "p146.release_evidence.v1",
    "p147.release_evidence.v1",
    "p148.release_evidence.v1",
    "p149.release_evidence.v1",
    "p150.release_evidence.v1",
    "p151.release_evidence.v1",
)
P152_PATHS = (
    "evals/p146/final/release-evidence.json",
    "evals/p147/output/release-evidence.json",
    "evals/p148/output/release-evidence.json",
    "evals/p149/output/release-evidence.json",
    "evals/p150/output/release-evidence.json",
    "evals/p151/output/release-evidence.json",
)
P152_LIMITATIONS = [
    "bounded_lab_only_no_production_authority",
    "local_fixture_approval_only_no_auth",
    "not_production_operator_replacement",
]
P152_CASE_IDS = tuple(f"P152-CASE-{index:02d}" for index in range(1, 9))

P152_REVIEW_KEYSET = set(p147_p152_contracts.REVIEW_KEYS)
UUIDV7_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


def _p152() -> Any:
    return importlib.import_module("app.services.p152_operator_readiness")


def _canonical_hash(value: dict[str, Any], self_hash_key: str) -> str:
    payload = {key: item for key, item in value.items() if key != self_hash_key}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _rehash(value: dict[str, Any], self_hash_key: str) -> dict[str, Any]:
    result = dict(value)
    result[self_hash_key] = _canonical_hash(result, self_hash_key)
    return result


def _predecessors() -> list[dict[str, Any]]:
    return [
        {
            "phase": phase,
            "path": path,
            "schema_version": schema,
            "required_status": status,
            "file_hash": f"sha256:{index:064x}",
            "evidence_hash": f"sha256:{index + 10:064x}",
        }
        for index, (phase, path, schema, status) in enumerate(zip(P152_PHASES, P152_PATHS, P152_SCHEMAS, P152_STATUSES, strict=True), start=1)
    ]


def _approve_once_receipt(*, pre_state_hash: str = "sha256:" + "a" * 64, expires_at: str = "2030-01-01T00:00:00Z") -> dict[str, Any]:
    service = _p152()
    return service.issue_local_approve_once_fixture_receipt(
        issuer="fixture-authority",
        subject="operator-a",
        action="restart_worker",
        target="process-owned-lab",
        pre_state_hash=pre_state_hash,
        expires_at=expires_at,
    )


def _integration_cases() -> list[dict[str, Any]]:
    valid_receipt = _approve_once_receipt()
    def case(
        index: int,
        *,
        kill_switch: bool = False,
        deadman: bool = False,
        expected_rejection: str | None,
        receipt: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "case_id": f"P152-CASE-{index:02d}",
            "permission_mode": "approve_once",
            "action": "restart_worker",
            "kill_switch": kill_switch,
            "deadman": deadman,
            "expect_action": False,
            "expected_rejection": expected_rejection,
        }
        if receipt is not None:
            result["receipt"] = receipt
        return result

    return [
        case(1, expected_rejection=None, receipt=valid_receipt),
        case(2, kill_switch=True, expected_rejection="approve_once_receipt_required"),
        case(3, deadman=True, expected_rejection="approve_once_receipt_forgery", receipt={**valid_receipt, "signature": "sha256:" + "0" * 64}),
        case(4, expected_rejection="approve_once_receipt_expired", receipt={**valid_receipt, "expires_at": "2000-01-01T00:00:00Z"}),
        case(5, expected_rejection="approve_once_receipt_replay", receipt=dict(valid_receipt)),
        case(6, expected_rejection="approve_once_receipt_match_invalid", receipt={**valid_receipt, "action": "rollback_canary"}),
        case(7, expected_rejection="approve_once_receipt_match_invalid", receipt={**valid_receipt, "target": "other-lab"}),
        case(8, expected_rejection="approve_once_receipt_match_invalid", receipt={**valid_receipt, "pre_state_hash": "sha256:" + "b" * 64}),
    ]


def _release_profile() -> dict[str, Any]:
    return {
        "schema_version": "p152.release_profile.v1",
        "phase": "p152",
        "case_ids": sorted(P152_CASE_IDS),
        "limits": {
            "allowed_permission_modes": ["manual", "approve_once", "auto_safe_lab"],
            "allowed_actions": ["observe", "restart_worker", "rollback_canary"],
            "allowed_targets": ["process-owned-lab"],
            "predecessor_count": 6,
            "production_operator_replacement_ready": False,
            "production_mutation_count": 0,
            "staging_mutation_count": 0,
            "authority_escape_count": 0,
            "local_fixture_approval_only": True,
            "auth_implementation": "deferred",
            "approve_once_action_execution": False,
            "kill_switch_blocks_execution": True,
            "deadman_blocks_execution": True,
            "rollback_required_for_executed_actions": True,
        },
    }


def _freeze_manifest(report: dict[str, Any]) -> dict[str, Any]:
    freeze = {
        "schema_version": "p152.freeze_manifest.v1",
        "phase": "p152",
        "plan_hash": report["source_hashes"]["docs/operations/p147-p152-program-plan.md"],
        "test_spec_hash": report["source_hashes"]["docs/operations/p152-test-spec.md"],
        "source_hashes": report["source_hashes"],
        "profile_hash": report["profile_hash"],
        "predecessor_file_hashes": [entry["file_hash"] for entry in _predecessors()],
        "report_hash": report["report_hash"],
        "manifest_hash": "",
    }
    freeze["manifest_hash"] = _canonical_hash(freeze, "manifest_hash")
    return freeze


def _manual_zero_review(report: dict[str, Any], freeze: dict[str, Any]) -> dict[str, Any]:
    review = {
        "schema_version": "p152.final_review.v1",
        "phase": "p152",
        "reviewer_identity": "independent-test-reviewer",
        "reviewer_agent_id": "019f690b-e480-7000-8000-335475de27da",
        "reviewed_at": "2026-07-16T00:00:00Z",
        "decision": "approve",
        "findings": {"p0": 0, "p1": 0, "p2": 0, "p3": 0},
        "limitations": P152_LIMITATIONS,
        "reviewed_report_hash": report["report_hash"],
        "reviewed_manifest_hash": freeze["manifest_hash"],
        "review_hash": "",
    }
    if "writer_agent_id" in P152_REVIEW_KEYSET:
        review["writer_agent_id"] = "019f690b-e89a-7000-8000-6f441175e518"
    review["review_hash"] = _canonical_hash(review, "review_hash")
    assert set(review) == P152_REVIEW_KEYSET
    assert UUIDV7_RE.fullmatch(review["reviewer_agent_id"])
    assert review["reviewed_at"].endswith("Z")
    return review


def test_contract_and_predecessor_fail_closed() -> None:
    service = _p152()
    assert service.CASE_SELECTOR_NAMES == P152_SELECTOR_NAMES
    for name in (
        "run_p152_qualification",
        "validate_approve_once_receipt",
        "evaluate_permission_mode",
        "validate_p152_report",
        "validate_p152_freeze_manifest",
        "validate_p152_final_review",
        "validate_p152_release_evidence",
        "assemble_p152_release_evidence",
        "build_p152_release_profile",
    ):
        assert callable(getattr(service, name))

    reordered = list(reversed(_predecessors()))
    with pytest.raises(service.P152OperatorReadinessError, match="predecessor|order|p146"):
        service.run_p152_qualification(
            predecessors=reordered, integration_cases=_integration_cases(), output_dir=None, evidence_mode="isolated_test"
        )
    with pytest.raises(service.P152OperatorReadinessError, match="predecessor|path|file|p14"):
        service.run_p152_qualification(
            predecessors=_predecessors(), integration_cases=_integration_cases(), output_dir=None
        )

    runner = importlib.import_module("scripts.run_p152_qualification")
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(sys, "argv", ["run_p152_qualification.py", "--predecessors", "forged.json"])
    try:
        with pytest.raises(SystemExit, match="path-backed P146-P151 predecessors"):
            runner.main()
    finally:
        monkeypatch.undo()


def test_happy_path_report_and_counters() -> None:
    service = _p152()
    report = service.run_p152_qualification(
        predecessors=_predecessors(), integration_cases=_integration_cases(), output_dir=None, evidence_mode="isolated_test"
    )
    profile = service.build_p152_release_profile()

    assert report["schema_version"] == "p152.report.v1"
    assert report["phase"] == "p152"
    assert report["status"] == "p152_bounded_operator_agent_qualified"
    assert report["case_count"] == 8
    assert report["passed"] == 8
    assert report["failed"] == 0
    assert report["metrics"] == {
        "predecessor_count": 6,
        "qualified_predecessor_count": 6,
        "kill_switch_pass": True,
        "deadman_pass": True,
        "rollback_closure": True,
        "production_operator_replacement_ready": False,
    }
    assert report["limitations"] == P152_LIMITATIONS
    assert profile == _release_profile()
    assert set(profile) == {"schema_version", "phase", "case_ids", "limits"}
    assert len(profile["case_ids"]) == 8
    assert profile["case_ids"] == sorted(profile["case_ids"])
    assert profile["limits"]["allowed_permission_modes"] == ["manual", "approve_once", "auto_safe_lab"]
    assert profile["limits"]["predecessor_count"] == 6
    assert profile["limits"]["production_operator_replacement_ready"] is False
    assert profile["limits"]["auth_implementation"] == "deferred"
    assert profile["limits"]["local_fixture_approval_only"] is True
    assert report["profile_hash"] == service.stable_hash(profile)
    assert report["counters"]["production_mutation_count"] == 0
    assert report["counters"]["staging_mutation_count"] == 0
    assert report["counters"]["authority_escape_count"] == 0
    assert "review_hash" not in report
    assert "evidence_hash" not in report
    assert service.validate_p152_report(report)["report_hash"] == report["report_hash"]

    forged_metrics = {**report, "metrics": {**report["metrics"], "qualified_predecessor_count": 0}}
    forged_metrics = _rehash(forged_metrics, "report_hash")
    with pytest.raises(service.P152OperatorReadinessError, match="metrics"):
        service.validate_p152_report(forged_metrics)

    forged_safety = {**report, "metrics": {**report["metrics"], "kill_switch_pass": False}}
    forged_safety = _rehash(forged_safety, "report_hash")
    with pytest.raises(service.P152OperatorReadinessError, match="metrics"):
        service.validate_p152_report(forged_safety)


def test_fault_matrix_and_recovery() -> None:
    service = _p152()
    manual = service.evaluate_permission_mode(
        permission_mode="manual",
        requested_action="restart_worker",
        target="process-owned-lab",
        pre_state_hash="sha256:" + "a" * 64,
        receipt=None,
    )
    assert manual["action_executed"] is False
    assert manual["reason_codes"] == ["manual_advisory_only"]

    auto = service.evaluate_permission_mode(
        permission_mode="auto_safe_lab",
        requested_action="restart_worker",
        target="process-owned-lab",
        pre_state_hash="sha256:" + "a" * 64,
        receipt=None,
    )
    assert auto["action_executed"] is True
    assert auto["rollback_closed"] is True

    killed = service.evaluate_permission_mode(
        permission_mode="auto_safe_lab",
        requested_action="restart_worker",
        target="process-owned-lab",
        pre_state_hash="sha256:" + "a" * 64,
        receipt=None,
        kill_switch=True,
    )
    assert killed["action_executed"] is False
    assert killed["kill_switch_blocked"] is True
    assert killed["escalation_receipt_hash"].startswith("sha256:")

    deadman = service.evaluate_permission_mode(
        permission_mode="auto_safe_lab",
        requested_action="restart_worker",
        target="process-owned-lab",
        pre_state_hash="sha256:" + "a" * 64,
        receipt=None,
        deadman=True,
    )
    assert deadman["action_executed"] is False
    assert deadman["deadman_blocked"] is True
    assert deadman["escalation_receipt_hash"].startswith("sha256:")


def test_forgery_and_authority_rejected() -> None:
    service = _p152()
    valid_receipt = service.issue_local_approve_once_fixture_receipt(
        issuer="fixture-authority",
        subject="operator-a",
        action="restart_worker",
        target="process-owned-lab",
        pre_state_hash="sha256:" + "b" * 64,
        expires_at="2030-01-01T00:00:00Z",
    )
    assert service.validate_approve_once_receipt(valid_receipt, action="restart_worker", target="process-owned-lab", pre_state_hash="sha256:" + "b" * 64)["ok"] is True
    assert valid_receipt["fixture_scope"] == "local_non_auth_fixture"
    assert valid_receipt["auth_implementation"] == "none"
    assert valid_receipt["can_execute"] is False

    for field, value in (
        ("signature", "sha256:" + "0" * 64),
        ("issuer", "operator-a"),
        ("fixture_scope", "production_auth"),
        ("auth_implementation", "implemented"),
        ("can_execute", True),
        ("action", "delete_production"),
        ("target", "prod-cluster"),
        ("pre_state_hash", "sha256:" + "c" * 64),
        ("expires_at", "2000-01-01T00:00:00Z"),
    ):
        forged = dict(valid_receipt)
        forged[field] = value
        with pytest.raises(service.P152OperatorReadinessError, match="approve_once|receipt|forg|auth|match|expired|fixture"):
            service.validate_approve_once_receipt(forged, action="restart_worker", target="process-owned-lab", pre_state_hash="sha256:" + "b" * 64)

    with pytest.raises(service.P152OperatorReadinessError, match="production|authority|blocked"):
        service.evaluate_permission_mode(
            permission_mode="auto_safe_lab",
            requested_action="delete_production",
            target="prod-cluster",
            pre_state_hash="sha256:" + "b" * 64,
            receipt=None,
        )
    _assert_approve_once_negative_qualification_cases(service)


def _assert_approve_once_negative_qualification_cases(service: Any) -> None:
    auto_safe_only = [
        {
            "case_id": f"P152-CASE-{index:02d}",
            "permission_mode": "auto_safe_lab",
            "action": "restart_worker",
            "kill_switch": False,
            "deadman": False,
            "expect_action": True,
        }
        for index in range(1, 9)
    ]
    with pytest.raises(service.P152OperatorReadinessError, match="frozen_permission_mode_coverage"):
        service.run_p152_qualification(
            predecessors=_predecessors(), integration_cases=auto_safe_only, output_dir=None, evidence_mode="isolated_test"
        )

    required_mutations = (
        (1, {"expected_rejection": "approve_once_receipt_required"}, "frozen_rejection_coverage"),
        (2, {"kill_switch": False}, "frozen_safety_coverage"),
        (3, {"deadman": False}, "frozen_safety_coverage"),
        (5, {"receipt": _approve_once_receipt(pre_state_hash="sha256:" + "b" * 64)}, "p152_gate_failed"),
    )
    for index, patch, error_match in required_mutations:
        cases = _integration_cases()
        cases[index - 1] = {**cases[index - 1], **patch}
        with pytest.raises(service.P152OperatorReadinessError, match=error_match):
            service.run_p152_qualification(
                predecessors=_predecessors(), integration_cases=cases, output_dir=None, evidence_mode="isolated_test"
            )


def test_release_evidence_requires_zero_finding_review() -> None:
    service = _p152()
    report = service.run_p152_qualification(
        predecessors=_predecessors(), integration_cases=_integration_cases(), output_dir=None, evidence_mode="isolated_test"
    )
    freeze = _freeze_manifest(report)
    assert service.validate_p152_freeze_manifest(freeze)["manifest_hash"] == freeze["manifest_hash"]
    forged_freeze = {**freeze, "manifest_hash": "sha256:" + "4" * 64}
    with pytest.raises(service.P152OperatorReadinessError, match="manifest_hash|self|canonical"):
        service.validate_p152_freeze_manifest(forged_freeze)

    review = _manual_zero_review(report, freeze)
    assert (
        service.validate_p152_final_review(
            review,
            report=report,
            freeze_manifest=freeze,
            writer_agent_id="019f690b-e89a-7000-8000-6f441175e518",
        )["review_hash"]
        == review["review_hash"]
    )
    with pytest.raises(service.P152OperatorReadinessError, match="manifest_hash_mismatch"):
        service.validate_p152_final_review(
            review,
            report=report,
            freeze_manifest={**freeze, "manifest_hash": "sha256:" + "0" * 64},
        )
    same_writer_review = {**review, "reviewer_agent_id": "019f690b-e89a-7000-8000-6f441175e518"}
    same_writer_review["review_hash"] = _canonical_hash(same_writer_review, "review_hash")
    with pytest.raises(service.P152OperatorReadinessError, match="writer|reviewer|separation"):
        service.validate_p152_final_review(same_writer_review, writer_agent_id="019f690b-e89a-7000-8000-6f441175e518")

    release = service.assemble_p152_release_evidence(report=report, freeze=freeze, review=review)
    assert release["schema_version"] == "p152.release_evidence.v1"
    assert release["phase"] == "p152"
    assert release["status"] == "p152_bounded_operator_agent_qualified"
    assert release["review_hash"] == review["review_hash"]
    assert release["metrics"]["production_operator_replacement_ready"] is False
    assert release["evidence_hash"] == _canonical_hash(release, "evidence_hash")
    assert service.validate_p152_release_evidence(release)["evidence_hash"] == release["evidence_hash"]

    forged_release_count = {**release, "metrics": {**release["metrics"], "qualified_predecessor_count": 0}}
    forged_release_count = _rehash(forged_release_count, "evidence_hash")
    with pytest.raises(service.P152OperatorReadinessError, match="metrics"):
        service.validate_p152_release_evidence(forged_release_count)

    forged_release_safety = {**release, "metrics": {**release["metrics"], "deadman_pass": False}}
    forged_release_safety = _rehash(forged_release_safety, "evidence_hash")
    with pytest.raises(service.P152OperatorReadinessError, match="metrics"):
        service.validate_p152_release_evidence(forged_release_safety)

    forged_release_prod = {**release, "metrics": {**release["metrics"], "production_operator_replacement_ready": True}}
    forged_release_prod = _rehash(forged_release_prod, "evidence_hash")
    with pytest.raises(service.P152OperatorReadinessError, match="metrics"):
        service.validate_p152_release_evidence(forged_release_prod)

    nonzero_review = {**review, "findings": {"p0": 0, "p1": 1, "p2": 0, "p3": 0}}
    nonzero_review["review_hash"] = _canonical_hash(nonzero_review, "review_hash")
    with pytest.raises(service.P152OperatorReadinessError, match="review|p1|zero"):
        service.assemble_p152_release_evidence(report=report, freeze=freeze, review=nonzero_review)
