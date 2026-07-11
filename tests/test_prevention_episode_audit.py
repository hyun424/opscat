from __future__ import annotations

import dataclasses
import hashlib
import importlib
import json
from pathlib import Path
from typing import Any

import pytest

ZERO_AUTHORITY_COUNTERS = {
    "auth": 0,
    "credential_reads": 0,
    "production_adapter_calls": 0,
    "production_mutations": 0,
    "network_calls": 0,
    "shell_calls": 0,
    "cloud_calls": 0,
    "db_mutations": 0,
}


def _api() -> Any:
    try:
        return importlib.import_module("app.services.prevention_episode_audit")
    except ModuleNotFoundError as exc:
        pytest.fail(f"P107 RED: missing prevention episode audit implementation ({exc}).", pytrace=False)


def _episode(api: Any) -> Any:
    cls = getattr(api, "PreventionEpisode", None)
    if cls is None:
        pytest.fail("P107 RED: expose frozen PreventionEpisode.", pytrace=False)
    return cls(
        episode_id="episode-001",
        selected_candidate_hash="sha256:candidate",
        canonical_p106_evidence_hash="sha256:p106",
        p105_p106_prerequisite_identity="p105:p106:identity",
        registry_hash="sha256:registry",
        cohort_scope={"service": "payment-api", "environment": "staging"},
        telemetry_window={"start": "2026-07-10T00:00:00Z", "end": "2026-07-10T00:05:00Z"},
        created_at="2026-07-10T00:00:00Z",
    )


def _attempt(api: Any, *, sequence: int = 2, parent_hash: str = "sha256:parent", state: str = "wal_intent_appended") -> Any:
    cls = getattr(api, "PreventiveActionAttempt", None)
    if cls is None:
        pytest.fail("P107 RED: expose frozen PreventiveActionAttempt.", pytrace=False)
    return cls(
        episode_id="episode-001",
        attempt_id=f"attempt-{sequence}",
        sequence=sequence,
        state=state,
        selected_candidate_hash="sha256:candidate",
        canonical_p106_evidence_hash="sha256:p106",
        registry_hash="sha256:registry",
        policy_recheck_hash="sha256:policy",
        cohort_fingerprint_hash="sha256:cohort",
        idempotency_key="idem-001",
        treatment_control_fingerprints={"treatment": "fp-a", "control": "fp-a"},
        authority_counters=dict(ZERO_AUTHORITY_COUNTERS),
        parent_hash=parent_hash,
        occurred_at="2026-07-10T00:00:01Z",
    )


def _canonical_bytes(api: Any, record: Any) -> bytes:
    serializer = getattr(api, "canonical_record_bytes", None)
    if serializer is None:
        pytest.fail("P107 RED: expose canonical_record_bytes(record).", pytrace=False)
    return serializer(record)


def _new_store(api: Any, tmp_path: Path) -> Any:
    store_cls = getattr(api, "JsonlPreventionAuditStore", None)
    if store_cls is None:
        pytest.fail("P107 RED: expose JsonlPreventionAuditStore(path) append-only store.", pytrace=False)
    return store_cls(tmp_path / "prevention-audit.jsonl")


def _append(store: Any, record: Any) -> Any:
    return store.append(record)


def _replay(api: Any, store_or_path: Any, **kwargs: Any) -> Any:
    replay = getattr(api, "replay_prevention_audit", None)
    if replay is None:
        pytest.fail("P107 RED: expose replay_prevention_audit(store_or_path, ...).", pytrace=False)
    return replay(store_or_path, **kwargs)


def test_prevention_episode_is_frozen_and_canonicalized() -> None:
    api = _api()
    episode = _episode(api)

    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
        episode.episode_id = "mutated"
    assert _canonical_bytes(api, episode) == _canonical_bytes(api, episode)


def test_preventive_action_attempt_is_frozen_and_hash_bound() -> None:
    api = _api()
    attempt = _attempt(api)

    for field_name in [
        "selected_candidate_hash",
        "registry_hash",
        "policy_recheck_hash",
        "cohort_fingerprint_hash",
        "idempotency_key",
        "authority_counters",
        "parent_hash",
    ]:
        assert getattr(attempt, field_name)
    assert attempt.authority_counters == ZERO_AUTHORITY_COUNTERS
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
        attempt.parent_hash = "sha256:mutated"


def test_audit_store_is_append_only(tmp_path: Path) -> None:
    api = _api()
    store = _new_store(api, tmp_path)
    episode = _episode(api)
    first_head = _append(store, episode)
    original_bytes = Path(store.path).read_bytes()

    with pytest.raises(Exception) as raised:
        _append(store, _attempt(api, sequence=1, parent_hash=first_head))

    assert "sequence" in str(raised.value).lower() or "append" in str(raised.value).lower()
    assert Path(store.path).read_bytes() == original_bytes


def test_wal_attempt_intent_is_durable_before_side_effect(tmp_path: Path) -> None:
    api = _api()
    store = _new_store(api, tmp_path)
    calls: list[str] = []

    class HarnessSpy:
        def invoke(self, idempotency_key: str) -> dict[str, Any]:
            calls.append("harness")
            assert Path(store.path).read_text(encoding="utf-8").count("wal_intent_appended") == 1
            assert getattr(store, "flush_count", 0) >= 1
            return {"idempotency_key": idempotency_key, "effect_observed": True}

    recorder = getattr(api, "record_prevention_attempt_with_wal", None)
    if recorder is None:
        pytest.fail("P107 RED: expose record_prevention_attempt_with_wal(store, attempt, harness).", pytrace=False)

    recorder(store, _episode(api), _attempt(api), HarnessSpy())

    assert calls == ["harness"]


def test_wal_rollback_intent_is_durable_before_rollback_effect(tmp_path: Path) -> None:
    api = _api()
    store = _new_store(api, tmp_path)
    calls: list[str] = []

    class RollbackSpy:
        def rollback(self, idempotency_key: str) -> dict[str, Any]:
            calls.append("rollback")
            assert Path(store.path).read_text(encoding="utf-8").count("rollback_intent_appended") == 1
            assert getattr(store, "flush_count", 0) >= 1
            return {"idempotency_key": idempotency_key, "rollback_observed": True}

    recorder = getattr(api, "record_prevention_rollback_with_wal", None)
    if recorder is None:
        pytest.fail("P107 RED: expose record_prevention_rollback_with_wal(store, rollback_attempt, rollbacker).", pytrace=False)

    recorder(store, _episode(api), _attempt(api, state="rollback_intent_appended"), RollbackSpy())

    assert calls == ["rollback"]


def _write_records(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text("\n".join(json.dumps(record, sort_keys=True) for record in records) + "\n", encoding="utf-8")


def _valid_record(sequence: int, state: str, parent_hash: str) -> dict[str, Any]:
    record = {
        "episode_id": "episode-001",
        "attempt_id": f"attempt-{sequence}",
        "sequence": sequence,
        "state": state,
        "parent_hash": parent_hash,
        "expected_terminal_head_hash": None,
        "selected_candidate_hash": "sha256:candidate",
        "canonical_p106_evidence_hash": "sha256:p106",
        "registry_hash": "sha256:registry",
        "policy_recheck_hash": "sha256:policy",
        "cohort_fingerprint_hash": "sha256:cohort",
        "idempotency_key": "idem-001",
        "authority_counters": dict(ZERO_AUTHORITY_COUNTERS),
    }
    encoded = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    record["record_hash"] = f"sha256:{hashlib.sha256(encoded).hexdigest()}"
    return record


def _rehash(record: dict[str, Any]) -> None:
    payload = dict(record)
    payload.pop("record_hash", None)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    record["record_hash"] = f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _valid_chain(states: list[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    parent = "GENESIS"
    for sequence, state in enumerate(states, start=1):
        record = _valid_record(sequence, state, parent)
        records.append(record)
        parent = record["record_hash"]
    return records


def _invalid_record_cases() -> list[tuple[list[dict[str, Any]], str]]:
    gap = _valid_chain(["received"])
    gap.append(_valid_record(3, "p106_recomputed", gap[-1]["record_hash"]))

    incomplete = _valid_chain(["received"])
    incomplete.append(_valid_record(2, "wal_intent_appended", incomplete[-1]["record_hash"]))

    transition = _valid_chain(["received"])
    transition.append(_valid_record(2, "received", transition[-1]["record_hash"]))

    appended_after_terminal = _valid_chain(["received", "p106_recomputed", "blocked_fail_closed"])
    appended_after_terminal.append(
        _valid_record(4, "monitoring", appended_after_terminal[-1]["record_hash"])
    )

    fork = _valid_chain(["received", "p106_recomputed"])
    fork.append(_valid_record(3, "cohort_checked", fork[0]["record_hash"]))
    return [
        (gap, "gap"),
        (incomplete, "incomplete"),
        (transition, "transition"),
        (appended_after_terminal, "terminal"),
        (fork, "fork"),
    ]


@pytest.mark.parametrize(
    ("records", "reason"),
    _invalid_record_cases(),
)
def test_audit_replay_rejects_invalid_modes(tmp_path: Path, records: list[dict[str, Any]], reason: str) -> None:
    api = _api()
    path = tmp_path / "audit.jsonl"
    _write_records(path, records)

    with pytest.raises(Exception) as raised:
        _replay(api, path)

    assert reason in str(raised.value).lower()


def test_audit_replay_rejects_tail_deletion_or_truncation(tmp_path: Path) -> None:
    api = _api()
    path = tmp_path / "audit.jsonl"
    _write_records(path, _valid_chain(["received", "p106_recomputed", "cohort_checked"]))

    with pytest.raises(Exception) as raised:
        _replay(api, path)

    assert "truncation" in str(raised.value).lower() or "incomplete" in str(raised.value).lower()


def test_audit_replay_rejects_partial_record(tmp_path: Path) -> None:
    api = _api()
    path = tmp_path / "audit.jsonl"
    path.write_text('{"sequence": 1, "state": "received"}\n{"sequence":', encoding="utf-8")

    with pytest.raises(Exception) as raised:
        _replay(api, path)

    assert "partial" in str(raised.value).lower()


def test_audit_replay_rejects_expected_terminal_head_hash_mismatch(tmp_path: Path) -> None:
    api = _api()
    path = tmp_path / "audit.jsonl"
    records = _valid_chain(["received", "p106_recomputed", "blocked_fail_closed"])
    records[-1]["expected_terminal_head_hash"] = "sha256:expected-other-head"
    _rehash(records[-1])
    _write_records(path, records)

    with pytest.raises(Exception) as raised:
        _replay(api, path)

    assert "head hash" in str(raised.value).lower()


def test_audit_replay_rejects_tamper(tmp_path: Path) -> None:
    api = _api()
    path = tmp_path / "audit.jsonl"
    record = _valid_record(1, "received", "GENESIS")
    record["record_hash"] = "sha256:not-the-canonical-hash"
    _write_records(path, [record])

    with pytest.raises(Exception) as raised:
        _replay(api, path, allow_incomplete=True)

    assert "tamper" in str(raised.value).lower() or "hash" in str(raised.value).lower()


def test_audit_replay_rejects_fixture_shaped_hash_bypass(tmp_path: Path) -> None:
    api = _api()
    path = tmp_path / "audit.jsonl"
    record = _valid_record(1, "received", "GENESIS")
    record["selected_candidate_hash"] = "sha256:tampered-candidate"
    _write_records(path, [record])

    with pytest.raises(Exception) as raised:
        _replay(api, path, allow_incomplete=True)

    assert "tamper" in str(raised.value).lower() or "hash" in str(raised.value).lower()


def test_audit_replay_rejects_reorder(tmp_path: Path) -> None:
    api = _api()
    path = tmp_path / "audit.jsonl"
    records = _valid_chain(["received", "p106_recomputed"])
    _write_records(path, list(reversed(records)))

    with pytest.raises(Exception) as raised:
        _replay(api, path)

    assert "order" in str(raised.value).lower() or "sequence" in str(raised.value).lower()


def test_audit_replay_output_is_stable(tmp_path: Path) -> None:
    api = _api()
    path = tmp_path / "audit.jsonl"
    _write_records(path, _valid_chain(["received", "p106_recomputed", "blocked_fail_closed"]))

    first = _replay(api, path)
    second = _replay(api, path)

    assert first.deterministic_replay is True
    assert first.replay_hash == second.replay_hash
    assert first.report_input_model == second.report_input_model
