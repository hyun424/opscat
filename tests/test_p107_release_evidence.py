from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest

from app.services.prevention_canary_fixture_matrix import REQUIRED_METRIC_GATES, ZERO_AUTHORITY_COUNTERS

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


def _api() -> Any:
    try:
        return importlib.import_module("app.services.p107_release_evidence")
    except ModuleNotFoundError as exc:
        pytest.fail(f"P107 RED: missing P107 release evidence module ({exc}).", pytrace=False)


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _complete_inputs() -> dict[str, Any]:
    canonical_report = {
        "schema_version": "p107.outcome_report.v1",
        "source_episode_id": "p107-episode-a01",
        "audit_head_hash": "sha256:audit-head-a01",
        "terminal_state": "succeeded",
        "recovery_replay_hash": "sha256:recovery-replay",
        "release_replay_hash": "sha256:release-replay",
        "release_replay_used_as_recovery_evidence": False,
    }
    report_hash = _api().compute_canonical_report_hash(canonical_report)
    canonical_report["report_hash"] = report_hash
    inputs = {
        "fixture_matrix_result": {
            "accepted": True,
            "fixture_ids": [f"A{index:02d}" for index in range(1, 15)],
            "matrix_hash": "sha256:fixture-matrix",
        },
        "outcome_report": {
            "accepted": True,
            "report_hash": report_hash,
            "canonical_report": canonical_report,
            "audit_head_hash": "sha256:audit-head-a01",
            "recovery_replay_hash": "sha256:recovery-replay",
            "release_replay_hash": "sha256:release-replay",
            "release_replay_used_as_recovery_evidence": False,
            "authority_counters": dict(ZERO_AUTHORITY_COUNTERS),
            "static_authority_boundary_passed": True,
            "runtime_authority_sentinel_passed": True,
            "canonical_p106_gate_recomputed": True,
            "caller_supplied_p107_gate_eligible_used": False,
            "p106_unlocked": False,
            "metric_gates": dict(REQUIRED_METRIC_GATES),
            "independent_review_hash": "sha256:independent-review",
            "independent_review": {
                "schema_version": "p107.independent_review.v1",
                "review_id": "review-p107-a01",
                "reviewer": {
                    "role": "verifier",
                    "id": "verifier-p108-a01",
                },
                "verdict": "pass",
                "reviewed_at": "2026-07-10T01:45:00Z",
                "freshness": {
                    "max_age_seconds": 3600,
                    "evidence_generated_at": "2026-07-10T01:30:00Z",
                    "fresh": True,
                },
                "reviewed_artifact_hashes": {
                    "audit_head_hash": "sha256:audit-head-a01",
                    "report_hash": report_hash,
                    "replay_hash": "sha256:release-replay",
                },
            },
        },
        "verify_profile": {
            "profile": "p107-release",
            "command": "uv run --no-sync --extra dev pytest -q " + " ".join(str(path) for path in P107_RELEASE_PROFILE_TESTS),
            "test_files": [str(path) for path in P107_RELEASE_PROFILE_TESTS],
            "passed": True,
            "fresh": True,
            "completed_at": "2026-07-10T02:00:00Z",
        },
        "docs_scan": {
            "docs_checked": [
                "docs/release-evidence.md",
                "docs/integration-verification.md",
                "README.md",
                "CHANGELOG.md",
            ],
            "overclaiming_phrases": [],
            "required_p107_boundary_phrases_present": True,
        },
    }
    return inputs


def _produce(inputs: dict[str, Any] | None = None) -> Any:
    producer = getattr(_api(), "produce_p107_release_evidence", None)
    if producer is None:
        pytest.fail("P107 RED: expose produce_p107_release_evidence(...).", pytrace=False)
    return producer(**(inputs or _complete_inputs()), trusted_now="2026-07-10T02:00:00Z")


def test_release_evidence_binds_fixture_matrix_outcome_report_and_verify_profile() -> None:
    inputs = _complete_inputs()
    evidence = _produce(inputs)

    assert _get(evidence, "release_qualified") is True
    assert _get(evidence, "fixture_matrix_hash") == "sha256:fixture-matrix"
    assert _get(evidence, "outcome_report_hash") == inputs["outcome_report"]["report_hash"]
    assert _get(evidence, "audit_head_hash") == "sha256:audit-head-a01"
    assert _get(evidence, "verify_profile_fresh") is True


def test_release_evidence_rejects_tampered_canonical_report_with_forged_hashes() -> None:
    inputs = _complete_inputs()
    inputs["outcome_report"]["canonical_report"] = {
        "schema_version": "p107.outcome_report.v1",
        "terminal_state": "succeeded",
        "report_hash": "sha256:outcome-report",
    }

    evidence = _produce(inputs)

    assert _get(evidence, "release_qualified") is False
    assert _get(evidence, "p108_replay_gate_ready") is False
    assert "report hash" in " ".join(_get(evidence, "reasons", [])).lower()


def test_release_evidence_rejects_self_consistent_hashes_when_canonical_security_facts_diverge() -> None:
    inputs = _complete_inputs()
    canonical = inputs["outcome_report"]["canonical_report"]
    canonical["audit_head_hash"] = "sha256:forged-audit"
    forged_hash = _api().compute_canonical_report_hash(canonical)
    canonical["report_hash"] = forged_hash
    inputs["outcome_report"]["report_hash"] = forged_hash
    inputs["outcome_report"]["independent_review"]["reviewed_artifact_hashes"]["report_hash"] = forged_hash

    evidence = _produce(inputs)

    assert _get(evidence, "release_qualified") is False
    assert _get(evidence, "p108_replay_gate_ready") is False
    assert "canonical" in " ".join(_get(evidence, "reasons", [])).lower()


def test_release_evidence_rejects_recovery_report_that_reuses_release_replay() -> None:
    inputs = _complete_inputs()
    inputs["outcome_report"]["release_replay_used_as_recovery_evidence"] = True

    evidence = _produce(inputs)

    assert _get(evidence, "release_qualified") is False
    assert "release replay" in " ".join(_get(evidence, "reasons", [])).lower()


def test_release_evidence_rejects_docs_overclaim_or_missing_boundary_scan() -> None:
    inputs = _complete_inputs()
    inputs["docs_scan"]["overclaiming_phrases"] = ["production rollout enabled"]

    evidence = _produce(inputs)

    assert _get(evidence, "release_qualified") is False
    assert _get(evidence, "docs_overclaim_detected") is True


def test_release_evidence_requires_fresh_assigned_verify_command() -> None:
    inputs = _complete_inputs()
    inputs["verify_profile"]["fresh"] = False

    evidence = _produce(inputs)

    assert _get(evidence, "release_qualified") is False
    assert _get(evidence, "verify_profile_fresh") is False


def test_release_evidence_requires_exact_p107_independent_review_schema() -> None:
    inputs = _complete_inputs()
    inputs["outcome_report"]["independent_review"]["verdict"] = "PASS"

    evidence = _produce(inputs)

    assert _get(evidence, "release_qualified") is False
    assert "independent review" in " ".join(_get(evidence, "reasons", [])).lower()


def test_release_evidence_rejects_review_without_review_id() -> None:
    inputs = _complete_inputs()
    inputs["outcome_report"]["independent_review"].pop("review_id")

    evidence = _produce(inputs)

    assert _get(evidence, "release_qualified") is False
    assert _get(evidence, "p108_replay_gate_ready") is False
    assert "review_id" in " ".join(_get(evidence, "independent_review")["reasons"]).lower()


@pytest.mark.parametrize("timestamp_key", ["reviewed_at", "evidence_generated_at"])
def test_release_evidence_rejects_future_dated_review(timestamp_key: str) -> None:
    inputs = _complete_inputs()
    if timestamp_key == "reviewed_at":
        inputs["outcome_report"]["independent_review"]["reviewed_at"] = "2026-07-10T02:00:01Z"
    else:
        inputs["outcome_report"]["independent_review"]["freshness"]["evidence_generated_at"] = "2026-07-10T02:00:01Z"

    evidence = _produce(inputs)

    assert _get(evidence, "release_qualified") is False
    assert _get(evidence, "p108_replay_gate_ready") is False
    assert "future" in " ".join(_get(evidence, "independent_review")["reasons"]).lower()


def test_release_evidence_rejects_review_without_reviewed_at() -> None:
    inputs = _complete_inputs()
    inputs["outcome_report"]["independent_review"].pop("reviewed_at")

    evidence = _produce(inputs)

    assert _get(evidence, "release_qualified") is False
    assert _get(evidence, "p108_replay_gate_ready") is False


def test_release_evidence_binds_review_to_release_replay_hash() -> None:
    inputs = _complete_inputs()
    inputs["outcome_report"]["independent_review"]["reviewed_artifact_hashes"]["replay_hash"] = inputs[
        "outcome_report"
    ]["recovery_replay_hash"]

    evidence = _produce(inputs)

    assert _get(evidence, "release_qualified") is False
    assert _get(evidence, "independent_review")["reviewed_artifact_hashes_match"] is False


@pytest.mark.parametrize(
    "missing_key",
    [
        "authority_counters",
        "static_authority_boundary_passed",
        "runtime_authority_sentinel_passed",
        "canonical_p106_gate_recomputed",
        "caller_supplied_p107_gate_eligible_used",
        "p106_unlocked",
        "metric_gates",
    ],
)
def test_release_evidence_fails_closed_when_mandatory_outcome_gate_is_missing(missing_key: str) -> None:
    inputs = _complete_inputs()
    inputs["outcome_report"].pop(missing_key, None)

    evidence = _produce(inputs)

    assert _get(evidence, "release_qualified") is False


def test_verify_integration_contract_lists_all_p107_release_profile_tests() -> None:
    verifier = getattr(_api(), "verify_p107_release_integration_contract", None)
    if verifier is None:
        pytest.fail("P107 RED: expose verify_p107_release_integration_contract(...).", pytrace=False)

    result = verifier(
        tests=list(P107_RELEASE_PROFILE_TESTS),
        docs=[
            Path("docs/release-evidence.md"),
            Path("docs/integration-verification.md"),
            Path("README.md"),
            Path("CHANGELOG.md"),
        ],
    )

    assert _get(result, "accepted") is True
    assert tuple(_get(result, "profile_tests")) == tuple(str(path) for path in P107_RELEASE_PROFILE_TESTS)
    assert _get(result, "p107_release_profile") == "p107-release"
    assert _get(result, "docs_boundary_scan_configured") is True


def test_verify_integration_contract_rejects_missing_any_p107_profile_test() -> None:
    verifier = getattr(_api(), "verify_p107_release_integration_contract", None)
    if verifier is None:
        pytest.fail("P107 RED: expose verify_p107_release_integration_contract(...).", pytrace=False)

    result = verifier(
        tests=[path for path in P107_RELEASE_PROFILE_TESTS if path.name != "test_prevention_static_authority_boundary.py"],
        docs=[Path("docs/release-evidence.md")],
    )

    assert _get(result, "accepted") is False
    assert "test_prevention_static_authority_boundary.py" in _get(result, "missing_profile_tests")
