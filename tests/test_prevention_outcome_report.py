from __future__ import annotations

import copy
import importlib
import json
from typing import Any

import pytest


def _api() -> Any:
    try:
        return importlib.import_module("app.services.prevention_outcome_report")
    except ModuleNotFoundError as exc:
        pytest.fail(f"P107 RED: missing prevention outcome report module ({exc}).", pytrace=False)


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _base_episode() -> dict[str, Any]:
    return {
        "episode_id": "p107-episode-a01",
        "candidate_id": "preventive.mock.rollback_pr",
        "treatment_cohort_hash": "sha256:treatment-a01",
        "control_cohort_hash": "sha256:control-a01",
        "preflight_policy_hash": "sha256:policy-a01",
        "attempts": [
            {
                "attempt_id": "attempt-a01",
                "idempotency_key": "p107-a01-key",
                "action_count": 1,
                "effect_hash": "sha256:effect-a01",
                "rollback_attempted": False,
            }
        ],
        "metric_windows": [
            {
                "window_id": "w1",
                "started_at": "2026-07-10T00:00:00Z",
                "ended_at": "2026-07-10T00:15:00Z",
                "primary_metric_delta": -0.31,
                "guardrail_breached": False,
            }
        ],
        "decision": "observe",
        "terminal_state": "succeeded",
        "authority_counters": {
            "auth": 0,
            "credential_reads": 0,
            "production_adapter_calls": 0,
            "production_mutation": 0,
            "network_calls": 0,
            "shell_calls": 0,
            "cloud_calls": 0,
            "db_mutation": 0,
        },
    }


def _base_audit_records() -> list[dict[str, Any]]:
    return [
        {
            "event_type": "episode_started",
            "episode_id": "p107-episode-a01",
            "head_hash": "sha256:audit-head-001",
            "previous_hash": None,
            "sequence": 1,
        },
        {
            "event_type": "attempt_recorded",
            "episode_id": "p107-episode-a01",
            "attempt_id": "attempt-a01",
            "head_hash": "sha256:audit-head-002",
            "previous_hash": "sha256:audit-head-001",
            "sequence": 2,
        },
        {
            "event_type": "terminal_state",
            "episode_id": "p107-episode-a01",
            "terminal_state": "succeeded",
            "head_hash": "sha256:audit-head-a01",
            "previous_hash": "sha256:audit-head-002",
            "sequence": 3,
        },
    ]


def _base_recovery_replay() -> dict[str, Any]:
    return {
        "replay_id": "recovery-replay-a01",
        "purpose": "recovery_outcome",
        "source": "audit",
        "source_episode_id": "p107-episode-a01",
        "source_audit_head_hash": "sha256:audit-head-a01",
        "expected_terminal_head_hash": "sha256:audit-head-a01",
        "run_started_at": "2026-07-10T00:16:00Z",
        "run_finished_at": "2026-07-10T00:18:00Z",
        "fixtures": ["A01"],
        "recovered": True,
        "rollback_verified": True,
        "audit_records": _base_audit_records(),
        "idempotency_state": {
            "idempotency_key": "p107-a01-key",
            "committed_effect_count": 1,
            "duplicate_effect_count": 0,
            "terminal_state": "succeeded",
        },
        "hash": "sha256:recovery-a01",
    }


def _canonical_recovery_replay(replay: dict[str, Any]) -> dict[str, Any]:
    from app.services.prevention_replay_gate import compute_audit_record_hash, compute_replay_hash

    previous: str | None = None
    for record in replay["audit_records"]:
        record["previous_hash"] = previous
        record["head_hash"] = compute_audit_record_hash(record)
        previous = record["head_hash"]
    replay["source_audit_head_hash"] = previous
    replay["expected_terminal_head_hash"] = previous
    replay["hash"] = compute_replay_hash(replay)
    return replay


def _base_release_replay() -> dict[str, Any]:
    return {
        "replay_id": "release-replay-a01",
        "purpose": "release_regression",
        "source": "audit",
        "source_episode_id": "p107-episode-a01",
        "source_audit_head_hash": "sha256:audit-head-a01",
        "run_started_at": "2026-07-10T00:19:00Z",
        "run_finished_at": "2026-07-10T00:21:00Z",
        "fixtures": ["A01"],
        "release_gates_passed": True,
        "hash": "sha256:release-a01",
    }


def _base_review() -> dict[str, Any]:
    return {
        "schema_version": "p107.independent_review.v1",
        "review_id": "review-p107-a01",
        "reviewer": {
            "role": "verifier",
            "id": "verifier-p108-a01",
        },
        "verdict": "pass",
        "reviewed_at": "2026-07-10T00:22:00Z",
        "freshness": {
            "max_age_seconds": 3600,
            "evidence_generated_at": "2026-07-10T00:22:00Z",
            "fresh": True,
        },
        "reviewed_artifact_hashes": {
            "audit_head_hash": "sha256:audit-head-a01",
            "report_hash": "sha256:report-a01",
            "replay_hash": "sha256:release-a01",
        },
        "required_findings": {
            "recovery_release_replay_separated": True,
            "no_production_authority": True,
            "fixtures_a01_a14_complete": True,
            "docs_verified_no_overclaim": True,
        },
    }


def _build_report(
    episode: dict[str, Any] | None = None,
    recovery_replay: dict[str, Any] | None = None,
    release_replay: dict[str, Any] | None = None,
    review: dict[str, Any] | None = None,
) -> Any:
    builder = getattr(_api(), "build_prevention_outcome_report", None)
    if builder is None:
        pytest.fail("P107 RED: expose build_prevention_outcome_report(...).", pytrace=False)
    return builder(
        episode=episode or _base_episode(),
        recovery_replay=recovery_replay or _base_recovery_replay(),
        release_replay=release_replay or _base_release_replay(),
        independent_review=review or _base_review(),
    )


def test_report_keeps_recovery_replay_separate_from_release_replay() -> None:
    report = _build_report()

    assert _get(report, "recovery_replay_hash") == "sha256:recovery-a01"
    assert _get(report, "release_replay_hash") == "sha256:release-a01"
    assert _get(report, "recovery_replay_hash") != _get(report, "release_replay_hash")
    assert _get(report, "release_replay_used_as_recovery_evidence") is False


def test_report_is_deterministic_for_equivalent_inputs() -> None:
    first = _build_report()
    second = _build_report(
        episode=copy.deepcopy(_base_episode()),
        recovery_replay=copy.deepcopy(_base_recovery_replay()),
        release_replay=copy.deepcopy(_base_release_replay()),
        review=copy.deepcopy(_base_review()),
    )

    assert _get(first, "report_hash") == _get(second, "report_hash")
    assert json.dumps(_get(first, "canonical_report"), sort_keys=True) == json.dumps(
        _get(second, "canonical_report"),
        sort_keys=True,
    )


def test_report_rejects_release_replay_presented_as_recovery() -> None:
    release_as_recovery = dict(_base_release_replay())
    release_as_recovery["purpose"] = "release_regression"

    result = _build_report(recovery_replay=release_as_recovery)

    assert _get(result, "accepted") is False
    assert "recovery replay" in " ".join(_get(result, "reasons", [])).lower()


def test_independent_review_accepts_exact_p107_schema_and_artifact_hashes() -> None:
    validator = getattr(_api(), "validate_independent_review", None)
    if validator is None:
        pytest.fail("P107 RED: expose validate_independent_review(review, artifacts).", pytrace=False)
    artifacts = {
        "audit_head_hash": "sha256:audit-head-a01",
        "report_hash": "sha256:report-a01",
        "replay_hash": "sha256:release-a01",
    }

    result = validator(_base_review(), artifacts=artifacts, now="2026-07-10T01:00:00Z")

    assert _get(result, "accepted") is True
    assert _get(result, "schema_version") == "p107.independent_review.v1"
    assert _get(result, "reviewer") == {"role": "verifier", "id": "verifier-p108-a01"}
    assert _get(result, "verdict") == "pass"
    assert _get(result, "reviewed_artifact_hashes_match") is True
    assert _get(result, "freshness") == {
        "max_age_seconds": 3600,
        "evidence_generated_at": "2026-07-10T00:22:00Z",
        "fresh": True,
    }


@pytest.mark.parametrize("role", ["code-reviewer", "architect", "verifier", "independent-reviewer"])
def test_independent_review_accepts_each_approved_reviewer_role(role: str) -> None:
    validator = getattr(_api(), "validate_independent_review", None)
    assert callable(validator)
    review = _base_review()
    review["reviewer"]["role"] = role

    result = validator(review, artifacts=review["reviewed_artifact_hashes"], now="2026-07-10T01:00:00Z")

    assert _get(result, "accepted") is True


@pytest.mark.parametrize("verdict", ["fail", "blocked"])
def test_independent_review_never_accepts_non_pass_verdict(verdict: str) -> None:
    validator = getattr(_api(), "validate_independent_review", None)
    assert callable(validator)
    review = _base_review()
    review["verdict"] = verdict
    review.pop("reviewer")

    result = validator(review, artifacts=review["reviewed_artifact_hashes"], now="2026-07-10T00:30:00Z")

    assert _get(result, "accepted") is False
    assert "verdict" in " ".join(_get(result, "reasons", [])).lower()
    assert "reviewer" in " ".join(_get(result, "reasons", [])).lower()


@pytest.mark.parametrize("verdict", ["PASS", "Pass", "FAIL", "BLOCKED", "approved"])
def test_independent_review_rejects_non_lowercase_or_unknown_verdict(verdict: str) -> None:
    validator = getattr(_api(), "validate_independent_review", None)
    if validator is None:
        pytest.fail("P107 RED: expose validate_independent_review(review, artifacts).", pytrace=False)
    review = _base_review()
    review["verdict"] = verdict

    result = validator(review, artifacts=review["reviewed_artifact_hashes"], now="2026-07-10T00:30:00Z")

    assert _get(result, "accepted") is False
    assert "verdict" in " ".join(_get(result, "reasons", [])).lower()


@pytest.mark.parametrize("verdict", ["pass", "fail", "blocked"])
def test_independent_review_recognizes_lowercase_verdict_vocabulary(verdict: str) -> None:
    validator = getattr(_api(), "validate_independent_review", None)
    if validator is None:
        pytest.fail("P107 RED: expose validate_independent_review(review, artifacts).", pytrace=False)
    review = _base_review()
    review["verdict"] = verdict

    result = validator(review, artifacts=review["reviewed_artifact_hashes"], now="2026-07-10T00:30:00Z")

    assert _get(result, "verdict") == verdict
    assert _get(result, "verdict_allowed") is True


def test_independent_review_rejects_legacy_review_keys() -> None:
    validator = getattr(_api(), "validate_independent_review", None)
    if validator is None:
        pytest.fail("P107 RED: expose validate_independent_review(review, artifacts).", pytrace=False)
    review = _base_review()
    review["schema_version"] = "p107.independent_review.v1"
    review["reviewer_role"] = "independent-verifier"
    review["artifact_hashes"] = {
        "episode": "sha256:episode-a01",
        "recovery_replay": "sha256:recovery-a01",
        "release_replay": "sha256:release-a01",
        "report": "sha256:report-a01",
    }

    result = validator(review, artifacts=review["reviewed_artifact_hashes"], now="2026-07-10T00:30:00Z")

    assert _get(result, "accepted") is False
    assert "legacy" in " ".join(_get(result, "reasons", [])).lower()


def test_independent_review_requires_nonempty_review_id() -> None:
    validator = getattr(_api(), "validate_independent_review", None)
    assert callable(validator)
    review = _base_review()
    review["review_id"] = ""

    result = validator(review, artifacts=review["reviewed_artifact_hashes"], now="2026-07-10T01:00:00Z")

    assert _get(result, "accepted") is False
    assert "review_id" in " ".join(_get(result, "reasons", [])).lower()


@pytest.mark.parametrize("timestamp_key", ["reviewed_at", "evidence_generated_at"])
def test_independent_review_rejects_timestamps_later_than_trusted_now(timestamp_key: str) -> None:
    validator = getattr(_api(), "validate_independent_review", None)
    assert callable(validator)
    review = _base_review()
    if timestamp_key == "reviewed_at":
        review["reviewed_at"] = "2026-07-10T01:00:01Z"
    else:
        review["freshness"]["evidence_generated_at"] = "2026-07-10T01:00:01Z"

    result = validator(review, artifacts=review["reviewed_artifact_hashes"], now="2026-07-10T01:00:00Z")

    assert _get(result, "accepted") is False
    assert "future" in " ".join(_get(result, "reasons", [])).lower()


def test_independent_review_rejects_exact_backdated_freshness() -> None:
    validator = getattr(_api(), "validate_independent_review", None)
    if validator is None:
        pytest.fail("P107 RED: expose validate_independent_review(review, artifacts).", pytrace=False)
    review = _base_review()
    review["freshness"] = {
        "max_age_seconds": 3600,
        "evidence_generated_at": "2026-07-10T00:00:00Z",
        "fresh": True,
    }

    result = validator(review, artifacts=review["reviewed_artifact_hashes"], now="2026-07-10T01:00:01Z")

    assert _get(result, "accepted") is False
    assert _get(result, "fresh") is False
    assert "fresh" in " ".join(_get(result, "reasons", [])).lower()


def test_report_is_derived_from_audit_records_only() -> None:
    builder = getattr(_api(), "build_prevention_outcome_report_from_audit", None)
    if builder is None:
        pytest.fail("P107 RED: expose build_prevention_outcome_report_from_audit(audit_records, ...).", pytrace=False)

    report = builder(
        audit_records=_base_audit_records(),
        recovery_replay=_base_recovery_replay(),
        release_replay=_base_release_replay(),
        independent_review=_base_review(),
    )

    assert _get(report, "audit_head_hash") == "sha256:audit-head-a01"
    assert _get(report, "source_episode_id") == "p107-episode-a01"
    assert _get(report, "derived_from") == "audit_records"
    assert _get(report, "uses_production_state") is False


def test_report_includes_all_required_metrics_with_bounded_null_safe_rates() -> None:
    report = _build_report()

    metrics = _get(report, "metrics")
    assert set(metrics) == {
        "episode_count",
        "attempt_count",
        "recovery_success_rate",
        "rollback_success_rate",
        "release_gate_success_rate",
        "guardrail_breach_rate",
        "authority_breach_rate",
    }
    for name in {
        "recovery_success_rate",
        "rollback_success_rate",
        "release_gate_success_rate",
        "guardrail_breach_rate",
        "authority_breach_rate",
    }:
        assert metrics[name] is not None
        assert 0.0 <= metrics[name] <= 1.0


def test_report_renders_stable_json_and_markdown() -> None:
    renderer = getattr(_api(), "render_prevention_outcome_report", None)
    if renderer is None:
        pytest.fail("P107 RED: expose render_prevention_outcome_report(report).", pytrace=False)
    report = _build_report()

    rendered = renderer(report)

    assert _get(rendered, "json") == _get(renderer(copy.deepcopy(report)), "json")
    assert json.loads(_get(rendered, "json"))["report_hash"] == _get(report, "report_hash")
    assert _get(rendered, "markdown").startswith("# P107 Prevention Outcome Report\n")
    assert "release replay" in _get(rendered, "markdown").lower()


@pytest.mark.parametrize("replay_id", ["recovery-replay-a01", "rollback-recovery-a01", "audit-recovery-a01"])
def test_recovery_replay_accepts_valid_recovery_prefixes(replay_id: str) -> None:
    validator = getattr(_api(), "validate_recovery_replay_contract", None)
    if validator is None:
        pytest.fail("P107 RED: expose validate_recovery_replay_contract(replay).", pytrace=False)
    replay = _base_recovery_replay()
    replay["replay_id"] = replay_id
    _canonical_recovery_replay(replay)

    result = validator(replay)

    assert _get(result, "accepted") is True


@pytest.mark.parametrize("replay_id", ["release-replay-a01", "prod-recovery-a01", "recovery_a01", "", None])
def test_recovery_replay_rejects_invalid_prefix_matrix(replay_id: str | None) -> None:
    validator = getattr(_api(), "validate_recovery_replay_contract", None)
    if validator is None:
        pytest.fail("P107 RED: expose validate_recovery_replay_contract(replay).", pytrace=False)
    replay = _base_recovery_replay()
    replay["replay_id"] = replay_id

    result = validator(replay)

    assert _get(result, "accepted") is False
    assert "prefix" in " ".join(_get(result, "reasons", [])).lower()


def test_recovery_replay_rejects_metadata_without_audit_or_idempotency_proof() -> None:
    replay = _base_recovery_replay()
    replay.pop("audit_records")
    replay.pop("idempotency_state")

    result = _api().validate_recovery_replay_contract(replay)

    assert _get(result, "accepted") is False
    reasons = " ".join(_get(result, "reasons", [])).lower()
    assert "audit" in reasons
    assert "idempotency" in reasons


def test_recovery_replay_rejects_duplicate_effect_or_terminal_contradiction() -> None:
    replay = _base_recovery_replay()
    replay["idempotency_state"]["duplicate_effect_count"] = 1
    replay["idempotency_state"]["terminal_state"] = "rolled_back"

    result = _api().validate_recovery_replay_contract(replay)

    assert _get(result, "accepted") is False
    reasons = " ".join(_get(result, "reasons", [])).lower()
    assert "duplicate" in reasons
    assert "terminal" in reasons


def test_recovery_replay_accepts_structurally_valid_non_terminal_resume_prefix() -> None:
    replay = _base_recovery_replay()
    replay["audit_records"] = _base_audit_records()[:2]
    replay["source_audit_head_hash"] = "sha256:audit-head-002"
    replay["expected_terminal_head_hash"] = "sha256:audit-head-002"
    replay["resume_safe"] = True
    replay["recovered"] = False
    replay["rollback_verified"] = False
    replay["idempotency_state"]["terminal_state"] = None
    _canonical_recovery_replay(replay)

    result = _api().validate_recovery_replay_contract(replay)

    assert _get(result, "accepted") is True


def test_recovery_replay_rejects_unsupported_event_type() -> None:
    replay = _base_recovery_replay()
    replay["audit_records"][1]["event_type"] = "fabricated"

    result = _api().validate_recovery_replay_contract(replay)

    assert _get(result, "accepted") is False
    assert "event type" in " ".join(_get(result, "reasons", [])).lower()


def test_recovery_replay_rejects_non_mapping_record_without_raising() -> None:
    replay = _base_recovery_replay()
    replay["audit_records"][1] = "fabricated"

    result = _api().validate_recovery_replay_contract(replay)

    assert _get(result, "accepted") is False
    assert "object" in " ".join(_get(result, "reasons", [])).lower()


def test_recovery_replay_rejects_non_mapping_tail_without_raising() -> None:
    replay = _base_recovery_replay()
    replay["audit_records"][-1] = "fabricated"

    result = _api().validate_recovery_replay_contract(replay)

    assert _get(result, "accepted") is False
    assert "object" in " ".join(_get(result, "reasons", [])).lower()


@pytest.mark.parametrize("invalid_timestamp", ["2026-07-10Z", "2026-07-10", "00:22:00Z"])
def test_independent_review_rejects_non_rfc3339_timestamp(invalid_timestamp: str) -> None:
    review = _base_review()
    review["reviewed_at"] = invalid_timestamp

    result = _api().validate_independent_review(
        review,
        artifacts=review["reviewed_artifact_hashes"],
        now=invalid_timestamp,
    )

    assert _get(result, "accepted") is False
    assert "rfc3339" in " ".join(_get(result, "reasons", [])).lower()


def test_release_replay_requires_terminal_audit_chain() -> None:
    validator = getattr(_api(), "validate_release_replay_contract", None)
    if validator is None:
        pytest.fail("P107 RED: expose validate_release_replay_contract(replay, audit_records).", pytrace=False)
    audit_records = _base_audit_records()
    audit_records.pop()

    result = validator(_base_release_replay(), audit_records=audit_records)

    assert _get(result, "accepted") is False
    assert "terminal" in " ".join(_get(result, "reasons", [])).lower()


def test_release_replay_rejects_fabricated_single_terminal_marker() -> None:
    validator = getattr(_api(), "validate_release_replay_contract", None)
    assert callable(validator)
    fabricated = [{"event_type": "terminal_state", "terminal_state": "succeeded"}]

    result = validator(_base_release_replay(), audit_records=fabricated)

    assert _get(result, "accepted") is False
    assert "chain" in " ".join(_get(result, "reasons", [])).lower()
