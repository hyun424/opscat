"""P107 release evidence aggregation for the local/mock canary lane."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from app.services.prevention_canary_fixture_matrix import (
    REQUIRED_FIXTURE_IDS,
    REQUIRED_METRIC_GATES,
    ZERO_AUTHORITY_COUNTERS,
)
from app.services.prevention_outcome_report import compute_canonical_report_hash, validate_independent_review

P107_RELEASE_PROFILE = "p107-release"
P107_RELEASE_PROFILE_TESTS = (
    Path("tests/test_prevention_p106_handoff.py"),
    Path("tests/test_prevention_canary_fingerprints.py"),
    Path("tests/test_prevention_policy_preflight.py"),
    Path("tests/test_prevention_state_machine.py"),
    Path("tests/test_prevention_episode_audit.py"),
    Path("tests/test_prevention_canary_harness.py"),
    Path("tests/test_prevention_canary_executor_contract.py"),
    Path("tests/test_prevention_canary_idempotency.py"),
    Path("tests/test_prevention_canary_concurrency.py"),
    Path("tests/test_prevention_canary_crash_consistency.py"),
    Path("tests/test_prevention_canary_rollback.py"),
    Path("tests/test_prevention_canary_fixture_matrix.py"),
    Path("tests/test_prevention_outcome_report.py"),
    Path("tests/test_prevention_static_authority_boundary.py"),
    Path("tests/test_p107_release_evidence.py"),
)
REQUIRED_BOUNDARY_DOCS = (
    Path("docs/release-evidence.md"),
    Path("docs/integration-verification.md"),
    Path("README.md"),
    Path("CHANGELOG.md"),
)


def produce_p107_release_evidence(
    *,
    fixture_matrix_result: Mapping[str, Any],
    outcome_report: Mapping[str, Any],
    verify_profile: Mapping[str, Any],
    docs_scan: Mapping[str, Any],
    trusted_now: str | None = None,
) -> dict[str, Any]:
    reasons: list[str] = []

    fixture_accepted = fixture_matrix_result.get("accepted") is True
    if not fixture_accepted:
        reasons.append("fixture matrix did not pass")
    fixture_ids = list(fixture_matrix_result.get("fixture_ids", []))
    if fixture_ids != list(REQUIRED_FIXTURE_IDS):
        reasons.append("fixture matrix does not contain exact A01-A14 coverage")

    outcome_accepted = outcome_report.get("accepted") is True
    if not outcome_accepted:
        reasons.append("outcome report did not pass")
    canonical_report = outcome_report.get("canonical_report")
    claimed_report_hash = outcome_report.get("report_hash")
    if not isinstance(canonical_report, Mapping):
        reasons.append("canonical outcome report is missing")
    else:
        computed_report_hash = compute_canonical_report_hash(canonical_report)
        if canonical_report.get("report_hash") != claimed_report_hash or computed_report_hash != claimed_report_hash:
            reasons.append("outcome report hash does not match canonical report content")
        canonical_bindings = {
            "audit_head_hash": outcome_report.get("audit_head_hash"),
            "recovery_replay_hash": outcome_report.get("recovery_replay_hash"),
            "release_replay_hash": outcome_report.get("release_replay_hash"),
            "release_replay_used_as_recovery_evidence": outcome_report.get(
                "release_replay_used_as_recovery_evidence"
            ),
        }
        if any(canonical_report.get(key) != expected for key, expected in canonical_bindings.items()):
            reasons.append("canonical outcome report security facts do not match independently supplied evidence")
    if outcome_report.get("release_replay_used_as_recovery_evidence") is True:
        reasons.append("release replay cannot be used as recovery replay evidence")
    if outcome_report.get("recovery_replay_hash") == outcome_report.get("release_replay_hash"):
        reasons.append("release replay hash must differ from recovery replay hash")

    raw_authority_counters = outcome_report.get("authority_counters")
    authority_counters = _authority_counters(outcome_report)
    if not isinstance(raw_authority_counters, Mapping):
        reasons.append("authority counters are missing")
    if authority_counters != ZERO_AUTHORITY_COUNTERS:
        reasons.append("authority counters must be exact zero")
    static_boundary_passed = outcome_report.get("static_authority_boundary_passed") is True
    runtime_boundary_passed = outcome_report.get("runtime_authority_sentinel_passed") is True
    canonical_p106_gate_recomputed = outcome_report.get("canonical_p106_gate_recomputed") is True
    caller_supplied_p107_gate_eligible_used = outcome_report.get("caller_supplied_p107_gate_eligible_used", False) is True
    p106_unlocked = outcome_report.get("p106_unlocked", False) is True
    if not static_boundary_passed:
        reasons.append("static authority boundary did not pass")
    if not runtime_boundary_passed:
        reasons.append("runtime authority sentinel did not pass")
    if not canonical_p106_gate_recomputed:
        reasons.append("canonical P106 gate was not recomputed")
    if outcome_report.get("caller_supplied_p107_gate_eligible_used") is not False:
        reasons.append("caller supplied p107 gate eligibility usage flag must be explicitly false")
    if outcome_report.get("p106_unlocked") is not False:
        reasons.append("P106 evidence must explicitly preserve p107_unlocked=false")

    review_result = _validate_review(outcome_report.get("independent_review"), outcome_report, trusted_now=trusted_now)
    if not review_result["accepted"]:
        reasons.append("P107 independent review contract did not pass")

    verify_contract = verify_p107_release_integration_contract(
        tests=[Path(path) for path in verify_profile.get("test_files", [])],
        docs=[Path(path) for path in docs_scan.get("docs_checked", [])],
    )
    verify_profile_fresh = verify_profile.get("fresh") is True
    if verify_profile.get("profile") != P107_RELEASE_PROFILE:
        reasons.append("verify profile must be p107-release")
    if verify_profile.get("passed") is not True:
        reasons.append("verify profile did not pass")
    if not verify_profile_fresh:
        reasons.append("verify profile is not fresh")
    if not verify_contract["accepted"]:
        reasons.append("verify integration contract is incomplete")

    docs_overclaim_detected = bool(docs_scan.get("overclaiming_phrases"))
    if docs_overclaim_detected:
        reasons.append("docs overclaim detected")
    if docs_scan.get("required_p107_boundary_phrases_present") is not True:
        reasons.append("docs boundary phrases missing")

    metric_gate_failures = _metric_gate_failures(outcome_report.get("metric_gates"))
    if metric_gate_failures:
        reasons.append("required P107 metric gates did not pass")

    release_qualified = not reasons
    return {
        "schema_version": "p107.release_evidence.v1",
        "release_qualified": release_qualified,
        "reasons": reasons,
        "fixture_matrix_hash": fixture_matrix_result.get("matrix_hash"),
        "fixture_ids": fixture_ids,
        "outcome_report_hash": outcome_report.get("report_hash"),
        "audit_head_hash": outcome_report.get("audit_head_hash"),
        "recovery_replay_hash": outcome_report.get("recovery_replay_hash"),
        "release_replay_hash": outcome_report.get("release_replay_hash"),
        "release_replay_used_as_recovery_evidence": outcome_report.get("release_replay_used_as_recovery_evidence") is True,
        "verify_profile_fresh": verify_profile_fresh,
        "verify_profile": P107_RELEASE_PROFILE,
        "verify_contract": verify_contract,
        "docs_overclaim_detected": docs_overclaim_detected,
        "docs_boundary_scan_configured": verify_contract["docs_boundary_scan_configured"],
        "authority_counters": authority_counters,
        "static_authority_boundary_passed": static_boundary_passed,
        "runtime_authority_sentinel_passed": runtime_boundary_passed,
        "canonical_p106_gate_recomputed": canonical_p106_gate_recomputed,
        "caller_supplied_p107_gate_eligible_used": caller_supplied_p107_gate_eligible_used,
        "p106_unlocked": p106_unlocked,
        "metric_gate_failures": metric_gate_failures,
        "p108_independent_review_present": outcome_report.get("independent_review") is not None,
        "p108_independent_review_fresh": review_result["fresh"],
        "p108_replay_gate_ready": release_qualified and review_result["accepted"],
        "independent_review": review_result,
    }


def verify_p107_release_integration_contract(
    *,
    tests: Iterable[str | Path],
    docs: Iterable[str | Path],
) -> dict[str, Any]:
    profile_tests = [str(path) for path in P107_RELEASE_PROFILE_TESTS]
    supplied_tests = [str(Path(path)) for path in tests]
    supplied_docs = {str(Path(path)) for path in docs}
    missing_profile_tests = [Path(path).name for path in profile_tests if path not in supplied_tests]
    unexpected_profile_tests = [path for path in supplied_tests if path not in profile_tests]
    docs_boundary_scan_configured = all(str(path) in supplied_docs for path in REQUIRED_BOUNDARY_DOCS)
    return {
        "accepted": not missing_profile_tests and docs_boundary_scan_configured,
        "p107_release_profile": P107_RELEASE_PROFILE,
        "profile_tests": profile_tests,
        "missing_profile_tests": missing_profile_tests,
        "unexpected_profile_tests": unexpected_profile_tests,
        "docs_boundary_scan_configured": docs_boundary_scan_configured,
        "required_docs": [str(path) for path in REQUIRED_BOUNDARY_DOCS],
    }


def _authority_counters(outcome_report: Mapping[str, Any]) -> dict[str, int]:
    counters = outcome_report.get("authority_counters")
    if not isinstance(counters, Mapping):
        return dict(ZERO_AUTHORITY_COUNTERS)
    return {key: int(counters.get(key, 0) or 0) for key in ZERO_AUTHORITY_COUNTERS}


def _metric_gate_failures(metric_gates: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(metric_gates, Mapping):
        return {key: {"expected": expected, "actual": None} for key, expected in REQUIRED_METRIC_GATES.items()}
    failures = {}
    for key, expected in REQUIRED_METRIC_GATES.items():
        actual = metric_gates.get(key)
        if actual != expected:
            failures[key] = {"expected": expected, "actual": actual}
    return failures


def _validate_review(review: Any, outcome_report: Mapping[str, Any], *, trusted_now: str | None = None) -> dict[str, Any]:
    if not isinstance(review, Mapping):
        return {"accepted": False, "fresh": False, "reason": "missing_independent_review"}
    expected_artifacts = {
        "audit_head_hash": outcome_report.get("audit_head_hash"),
        "report_hash": outcome_report.get("report_hash"),
        "replay_hash": outcome_report.get("release_replay_hash"),
    }
    reviewed_at = review.get("reviewed_at")
    validation = validate_independent_review(
        review,
        artifacts=expected_artifacts,
        now=trusted_now if trusted_now is not None else reviewed_at if isinstance(reviewed_at, str) else None,
    )
    return {
        "accepted": validation["accepted"],
        "fresh": validation["fresh"],
        "schema_version": validation["schema_version"],
        "reviewer": validation["reviewer"],
        "verdict": validation["verdict"],
        "reviewed_artifact_hashes_match": validation["reviewed_artifact_hashes_match"],
        "reasons": validation["reasons"],
    }
