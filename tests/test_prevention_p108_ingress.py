from __future__ import annotations

import importlib
import json
from typing import Any

import pytest

from app.services.prevention_canary_fixture_matrix import REQUIRED_METRIC_GATES, ZERO_AUTHORITY_COUNTERS

P107_RELEASE_PROFILE_TESTS = (
    "tests/test_prevention_p106_handoff.py",
    "tests/test_prevention_canary_fingerprints.py",
    "tests/test_prevention_policy_preflight.py",
    "tests/test_prevention_state_machine.py",
    "tests/test_prevention_episode_audit.py",
    "tests/test_prevention_canary_harness.py",
    "tests/test_prevention_canary_executor_contract.py",
    "tests/test_prevention_canary_idempotency.py",
    "tests/test_prevention_canary_concurrency.py",
    "tests/test_prevention_canary_crash_consistency.py",
    "tests/test_prevention_canary_rollback.py",
    "tests/test_prevention_canary_fixture_matrix.py",
    "tests/test_prevention_outcome_report.py",
    "tests/test_prevention_static_authority_boundary.py",
    "tests/test_p107_release_evidence.py",
)


def _api() -> Any:
    try:
        return importlib.import_module("app.services.prevention_p108_ingress")
    except ModuleNotFoundError as exc:
        pytest.fail(f"P108 RED: missing raw P107 ingress module ({exc}).", pytrace=False)


def _stable_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    import hashlib

    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _without_key(value: dict[str, Any], key: str) -> dict[str, Any]:
    payload = dict(value)
    payload.pop(key, None)
    return payload


def _rehash_audit_records(records: list[dict[str, Any]]) -> None:
    previous_hash: str | None = None
    for record in records:
        record["previous_hash"] = previous_hash if previous_hash is not None else record.get("previous_hash")
        record["head_hash"] = _stable_hash(_without_key(record, "head_hash"))
        previous_hash = record["head_hash"]


def _rehash_pack(pack: dict[str, Any]) -> dict[str, Any]:
    _rehash_audit_records(pack["raw_audit_records"])
    audit_head_hash = pack["raw_audit_records"][-1]["head_hash"]

    for replay_key in ("raw_recovery_replay", "raw_release_replay"):
        replay = pack[replay_key]
        replay["source_audit_head_hash"] = audit_head_hash
        replay["expected_terminal_head_hash"] = audit_head_hash
    recovery_records = pack["raw_recovery_replay"]["audit_records"]
    for index, record in enumerate(recovery_records):
        record.update(pack["raw_audit_records"][index])
    pack["raw_recovery_replay"]["hash"] = _stable_hash(_without_key(pack["raw_recovery_replay"], "hash"))
    pack["raw_release_replay"]["hash"] = _stable_hash(_without_key(pack["raw_release_replay"], "hash"))

    canonical_report = pack["outcome_report"]["canonical_report"]
    canonical_report["audit_head_hash"] = audit_head_hash
    canonical_report["recovery_replay_hash"] = pack["raw_recovery_replay"]["hash"]
    canonical_report["release_replay_hash"] = pack["raw_release_replay"]["hash"]
    canonical_report["report_hash"] = _stable_hash(_without_key(canonical_report, "report_hash"))

    review = pack["raw_independent_review"]
    review["reviewed_artifact_hashes"]["audit_head_hash"] = audit_head_hash
    review["reviewed_artifact_hashes"]["report_hash"] = canonical_report["report_hash"]
    review["reviewed_artifact_hashes"]["replay_hash"] = pack["raw_release_replay"]["hash"]

    pack["outcome_report"]["audit_head_hash"] = audit_head_hash
    pack["outcome_report"]["recovery_replay_hash"] = pack["raw_recovery_replay"]["hash"]
    pack["outcome_report"]["release_replay_hash"] = pack["raw_release_replay"]["hash"]
    pack["outcome_report"]["report_hash"] = canonical_report["report_hash"]
    pack["outcome_report"]["independent_review_hash"] = _stable_hash(review)
    pack["outcome_report"]["independent_review"] = review
    return pack


def _complete_pack() -> dict[str, Any]:
    p107 = importlib.import_module("app.services.p107_release_evidence")
    canonical_report = {
        "schema_version": "p107.outcome_report.v1",
        "source_episode_id": "p107-episode-a01",
        "audit_head_hash": "sha256:audit-head-a01",
        "terminal_state": "succeeded",
        "recovery_replay_hash": "sha256:recovery-replay-a01",
        "release_replay_hash": "sha256:release-replay-a01",
        "release_replay_used_as_recovery_evidence": False,
        "authority_counters": dict(ZERO_AUTHORITY_COUNTERS),
    }
    report_hash = p107.compute_canonical_report_hash(canonical_report)
    canonical_report["report_hash"] = report_hash
    review = {
        "schema_version": "p107.independent_review.v1",
        "review_id": "review-p107-a01",
        "reviewer": {"role": "verifier", "id": "verifier-p108-ingress"},
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
            "replay_hash": "sha256:release-replay-a01",
        },
    }
    pack = {
        "schema_version": "p108.raw_p107_ingress_pack.v1",
        "producer": {"id": "p107-producer"},
        "raw_audit_records": [
            {
                "sequence": 1,
                "episode_id": "p107-episode-a01",
                "event_type": "episode_started",
                "previous_hash": "GENESIS",
                "head_hash": "sha256:audit-start-a01",
                "authority_counters": dict(ZERO_AUTHORITY_COUNTERS),
            },
            {
                "sequence": 2,
                "episode_id": "p107-episode-a01",
                "event_type": "attempt_recorded",
                "previous_hash": "sha256:audit-start-a01",
                "head_hash": "sha256:audit-attempt-a01",
                "authority_counters": dict(ZERO_AUTHORITY_COUNTERS),
            },
            {
                "sequence": 3,
                "episode_id": "p107-episode-a01",
                "event_type": "terminal_state",
                "previous_hash": "sha256:audit-attempt-a01",
                "terminal_state": "succeeded",
                "head_hash": "sha256:audit-head-a01",
                "authority_counters": dict(ZERO_AUTHORITY_COUNTERS),
            },
        ],
        "raw_recovery_replay": {
            "schema_version": "p107.recovery_replay.v1",
            "replay_id": "recovery-replay-a01",
            "hash": "sha256:recovery-replay-a01",
            "purpose": "recovery_outcome",
            "source": "audit",
            "source_episode_id": "p107-episode-a01",
            "source_audit_head_hash": "sha256:audit-head-a01",
            "expected_terminal_head_hash": "sha256:audit-head-a01",
            "audit_records": [
                {
                    "sequence": 1,
                    "episode_id": "p107-episode-a01",
                    "event_type": "episode_started",
                    "previous_hash": "GENESIS",
                    "head_hash": "sha256:audit-start-a01",
                },
                {
                    "sequence": 2,
                    "episode_id": "p107-episode-a01",
                    "event_type": "attempt_recorded",
                    "previous_hash": "sha256:audit-start-a01",
                    "head_hash": "sha256:audit-attempt-a01",
                },
                {
                    "sequence": 3,
                    "episode_id": "p107-episode-a01",
                    "event_type": "terminal_state",
                    "previous_hash": "sha256:audit-attempt-a01",
                    "terminal_state": "succeeded",
                    "head_hash": "sha256:audit-head-a01",
                },
            ],
            "idempotency_state": {
                "idempotency_key": "p107-a01",
                "committed_effect_count": 1,
                "duplicate_effect_count": 0,
                "terminal_state": "succeeded",
            },
            "recovered": True,
            "rollback_verified": True,
            "adapter": "local_mock",
            "transport": "local_mock",
            "authority_counters": dict(ZERO_AUTHORITY_COUNTERS),
        },
        "raw_release_replay": {
            "schema_version": "p107.release_replay.v1",
            "replay_id": "release-replay-a01",
            "hash": "sha256:release-replay-a01",
            "purpose": "release_regression",
            "source": "audit",
            "source_episode_id": "p107-episode-a01",
            "source_audit_head_hash": "sha256:audit-head-a01",
            "expected_terminal_head_hash": "sha256:audit-head-a01",
            "release_gates_passed": True,
            "adapter": "local_mock",
            "transport": "local_mock",
            "authority_counters": dict(ZERO_AUTHORITY_COUNTERS),
        },
        "raw_independent_review": review,
        "fixture_matrix_result": {
            "accepted": True,
            "fixture_ids": [f"A{index:02d}" for index in range(1, 15)],
            "matrix_hash": "sha256:fixture-matrix-a01",
        },
        "outcome_report": {
            "accepted": True,
            "report_hash": report_hash,
            "canonical_report": canonical_report,
            "audit_head_hash": "sha256:audit-head-a01",
            "recovery_replay_hash": "sha256:recovery-replay-a01",
            "release_replay_hash": "sha256:release-replay-a01",
            "release_replay_used_as_recovery_evidence": False,
            "authority_counters": dict(ZERO_AUTHORITY_COUNTERS),
            "static_authority_boundary_passed": True,
            "runtime_authority_sentinel_passed": True,
            "canonical_p106_gate_recomputed": True,
            "caller_supplied_p107_gate_eligible_used": False,
            "p106_unlocked": False,
            "metric_gates": dict(REQUIRED_METRIC_GATES),
            "independent_review_hash": _stable_hash(review),
            "independent_review": review,
        },
        "verify_profile": {
            "profile": "p107-release",
            "test_files": list(P107_RELEASE_PROFILE_TESTS),
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
        "submitted_readiness": {
            "release_qualified": False,
            "accepted": False,
            "fresh": False,
            "p108_replay_gate_ready": False,
        },
    }
    return _rehash_pack(pack)


def _validate(pack: dict[str, Any] | None = None, *, trusted_now: str = "2026-07-10T02:00:00Z") -> dict[str, Any]:
    validator = getattr(_api(), "validate_raw_p107_ingress_pack", None)
    if validator is None:
        pytest.fail("P108 RED: expose validate_raw_p107_ingress_pack(pack).", pytrace=False)
    return validator(pack or _complete_pack(), trusted_now=trusted_now)


def test_valid_raw_p107_pack_recomputes_release_readiness_and_binds_raw_hashes() -> None:
    result = _validate()
    pack = _complete_pack()

    assert result["accepted"] is True
    assert result["p108_ingress_gate"] is True
    assert result["recomputed_p107_release_qualified"] is True
    assert result["trusted_submitted_readiness"] is False
    assert result["bindings"] == {
        "audit_head_hash": pack["outcome_report"]["audit_head_hash"],
        "recovery_replay_hash": pack["outcome_report"]["recovery_replay_hash"],
        "release_replay_hash": pack["outcome_report"]["release_replay_hash"],
        "outcome_report_hash": pack["outcome_report"]["report_hash"],
        "independent_review_hash": pack["outcome_report"]["independent_review_hash"],
    }


def test_ingress_rejects_forged_self_consistent_audit_chain_hashes() -> None:
    pack = _complete_pack()
    forged = _stable_hash({"forged": "terminal"})
    pack["raw_audit_records"][-1]["terminal_state"] = "rolled_back"
    pack["raw_audit_records"][-1]["head_hash"] = forged
    pack["raw_recovery_replay"]["audit_records"][-1]["terminal_state"] = "rolled_back"
    pack["raw_recovery_replay"]["audit_records"][-1]["head_hash"] = forged
    pack["raw_recovery_replay"]["idempotency_state"]["terminal_state"] = "rolled_back"
    for component in ("raw_recovery_replay", "raw_release_replay"):
        pack[component]["source_audit_head_hash"] = forged
        pack[component]["expected_terminal_head_hash"] = forged
        pack[component]["hash"] = _stable_hash(_without_key(pack[component], "hash"))
    pack["outcome_report"]["audit_head_hash"] = forged
    pack["outcome_report"]["canonical_report"]["audit_head_hash"] = forged
    pack["outcome_report"]["recovery_replay_hash"] = pack["raw_recovery_replay"]["hash"]
    pack["outcome_report"]["release_replay_hash"] = pack["raw_release_replay"]["hash"]
    pack["outcome_report"]["canonical_report"]["recovery_replay_hash"] = pack["raw_recovery_replay"]["hash"]
    pack["outcome_report"]["canonical_report"]["release_replay_hash"] = pack["raw_release_replay"]["hash"]
    pack["outcome_report"]["canonical_report"]["terminal_state"] = "rolled_back"
    pack["outcome_report"]["canonical_report"]["report_hash"] = _stable_hash(
        _without_key(pack["outcome_report"]["canonical_report"], "report_hash")
    )
    pack["outcome_report"]["report_hash"] = pack["outcome_report"]["canonical_report"]["report_hash"]
    pack["raw_independent_review"]["reviewed_artifact_hashes"]["audit_head_hash"] = forged
    pack["raw_independent_review"]["reviewed_artifact_hashes"]["report_hash"] = pack["outcome_report"]["report_hash"]
    pack["raw_independent_review"]["reviewed_artifact_hashes"]["replay_hash"] = pack["raw_release_replay"]["hash"]
    pack["outcome_report"]["independent_review"] = pack["raw_independent_review"]
    pack["outcome_report"]["independent_review_hash"] = _stable_hash(pack["raw_independent_review"])

    result = _validate(pack)

    assert result["accepted"] is False
    reasons = " ".join(result["reasons"]).lower()
    assert "canonical audit" in reasons
    assert "forged" in reasons or "hash" in reasons


@pytest.mark.parametrize(
    "mutation",
    ["truncation", "reorder", "fork", "fabricated_terminal", "append_after_terminal"],
)
def test_ingress_rejects_mutated_self_consistent_audit_chains(mutation: str) -> None:
    pack = _complete_pack()
    if mutation == "truncation":
        pack["raw_audit_records"] = pack["raw_audit_records"][:-1]
    elif mutation == "reorder":
        pack["raw_audit_records"][1], pack["raw_audit_records"][2] = pack["raw_audit_records"][2], pack["raw_audit_records"][1]
    elif mutation == "fork":
        pack["raw_audit_records"][2]["previous_hash"] = pack["raw_audit_records"][0]["head_hash"]
        pack["raw_audit_records"][2]["head_hash"] = _stable_hash(_without_key(pack["raw_audit_records"][2], "head_hash"))
    elif mutation == "fabricated_terminal":
        pack["raw_audit_records"][1]["event_type"] = "terminal_state"
        pack["raw_audit_records"][1]["terminal_state"] = "succeeded"
        pack["raw_audit_records"][1]["head_hash"] = _stable_hash(_without_key(pack["raw_audit_records"][1], "head_hash"))
        pack["raw_audit_records"] = [pack["raw_audit_records"][0], pack["raw_audit_records"][1]]
    elif mutation == "append_after_terminal":
        appended = dict(pack["raw_audit_records"][1])
        appended["sequence"] = 4
        appended["previous_hash"] = pack["raw_audit_records"][-1]["head_hash"]
        appended["head_hash"] = _stable_hash(_without_key(appended, "head_hash"))
        pack["raw_audit_records"].append(appended)

    result = _validate(pack)

    assert result["accepted"] is False
    assert "audit" in " ".join(result["reasons"]).lower()


def test_ingress_ignores_copied_true_readiness_and_rejects_missing_raw_artifacts() -> None:
    pack = _complete_pack()
    pack["submitted_readiness"] = {
        "release_qualified": True,
        "accepted": True,
        "fresh": True,
        "p108_replay_gate_ready": True,
    }
    pack.pop("raw_release_replay")

    result = _validate(pack)

    assert result["accepted"] is False
    assert result["trusted_submitted_readiness"] is False
    assert "raw_release_replay" in " ".join(result["reasons"])


@pytest.mark.parametrize(
    ("field", "value", "expected_reason"),
    [
        ("raw_audit_records", [{"sequence": 1, "head_hash": "sha256:forged-audit", "terminal_state": "succeeded"}], "audit"),
        ("raw_recovery_replay", {"hash": "sha256:forged-recovery", "adapter": "local_mock"}, "recovery"),
        ("raw_release_replay", {"hash": "sha256:forged-release", "source_audit_head_hash": "sha256:audit-head-a01", "adapter": "local_mock"}, "release"),
        ("raw_independent_review", {"schema_version": "p107.independent_review.v1"}, "review"),
    ],
)
def test_ingress_rejects_raw_binding_mismatches(field: str, value: Any, expected_reason: str) -> None:
    pack = _complete_pack()
    pack[field] = value

    result = _validate(pack)

    assert result["accepted"] is False
    assert expected_reason in " ".join(result["reasons"]).lower()


def test_ingress_rejects_raw_independent_review_without_review_id() -> None:
    pack = _complete_pack()
    pack["raw_independent_review"].pop("review_id")
    pack["outcome_report"]["independent_review"] = pack["raw_independent_review"]
    pack["outcome_report"]["independent_review_hash"] = _stable_hash(pack["raw_independent_review"])

    result = _validate(pack)

    assert result["accepted"] is False
    reasons = " ".join(result["reasons"]).lower()
    assert "review_id" in reasons


@pytest.mark.parametrize("timestamp_key", ["reviewed_at", "evidence_generated_at"])
def test_ingress_rejects_future_dated_raw_p107_review(timestamp_key: str) -> None:
    pack = _complete_pack()
    if timestamp_key == "reviewed_at":
        pack["raw_independent_review"]["reviewed_at"] = "2026-07-10T02:00:01Z"
    else:
        pack["raw_independent_review"]["freshness"]["evidence_generated_at"] = "2026-07-10T02:00:01Z"
    pack["outcome_report"]["independent_review"] = pack["raw_independent_review"]
    pack["outcome_report"]["independent_review_hash"] = _stable_hash(pack["raw_independent_review"])

    result = _validate(pack, trusted_now="2026-07-10T02:00:00Z")

    assert result["accepted"] is False
    reasons = " ".join(result["reasons"]).lower()
    assert "future" in reasons or "trusted now" in reasons


@pytest.mark.parametrize(
    ("container", "key", "value"),
    [
        ("raw_release_replay", "environment", "staging"),
        ("raw_release_replay", "adapter", "production-adapter"),
        ("raw_release_replay", "transport", "live-http"),
        ("raw_release_replay", "credential_scope", "read-only-token"),
        ("raw_recovery_replay", "network_evidence", {"url": "https://example.invalid"}),
    ],
)
def test_ingress_rejects_staging_live_credentials_and_network_metadata(container: str, key: str, value: Any) -> None:
    pack = _complete_pack()
    pack[container][key] = value

    result = _validate(pack)

    assert result["accepted"] is False
    assert "offline boundary" in " ".join(result["reasons"]).lower()


def test_ingress_rejects_unknown_or_nonzero_authority_counters() -> None:
    pack = _complete_pack()
    pack["outcome_report"]["authority_counters"]["socket_calls"] = 0
    pack["raw_release_replay"]["authority_counters"]["network_calls"] = 1

    result = _validate(pack)

    assert result["accepted"] is False
    reasons = " ".join(result["reasons"]).lower()
    assert "authority counters" in reasons
    assert "unknown" in reasons
    assert "nonzero" in reasons


def test_ingress_calls_canonical_p107_release_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _api()
    calls: list[dict[str, Any]] = []

    def fake_p107_validator(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {
            "schema_version": "p107.release_evidence.v1",
            "release_qualified": True,
            "reasons": [],
            "fixture_matrix_hash": "sha256:fixture-matrix-a01",
            "outcome_report_hash": _complete_pack()["outcome_report"]["report_hash"],
            "audit_head_hash": "sha256:audit-head-a01",
            "recovery_replay_hash": "sha256:recovery-replay-a01",
            "release_replay_hash": "sha256:release-replay-a01",
            "authority_counters": dict(ZERO_AUTHORITY_COUNTERS),
            "independent_review": {"accepted": True},
        }

    monkeypatch.setattr(module, "produce_p107_release_evidence", fake_p107_validator)

    result = module.validate_raw_p107_ingress_pack(_complete_pack(), trusted_now="2026-07-10T02:00:00Z")

    assert result["accepted"] is True
    assert len(calls) == 1
    assert set(calls[0]) == {"fixture_matrix_result", "outcome_report", "verify_profile", "docs_scan", "trusted_now"}
