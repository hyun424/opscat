from __future__ import annotations

import json
from typing import Any

from app.services.prevention_replay_gate import validate_recovery_replay_contract, validate_release_replay_contract


def _stable_hash(value: Any) -> str:
    import hashlib

    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _without_key(value: dict[str, Any], key: str) -> dict[str, Any]:
    payload = dict(value)
    payload.pop(key, None)
    return payload


def _audit_records() -> list[dict[str, Any]]:
    records = [
        {
            "sequence": 1,
            "episode_id": "p107-episode-a01",
            "event_type": "episode_started",
            "previous_hash": "GENESIS",
        },
        {
            "sequence": 2,
            "episode_id": "p107-episode-a01",
            "event_type": "attempt_recorded",
        },
        {
            "sequence": 3,
            "episode_id": "p107-episode-a01",
            "event_type": "terminal_state",
            "terminal_state": "succeeded",
        },
    ]
    previous_hash: str | None = None
    for record in records:
        record["previous_hash"] = previous_hash if previous_hash is not None else record["previous_hash"]
        record["head_hash"] = _stable_hash(_without_key(record, "head_hash"))
        previous_hash = str(record["head_hash"])
    return records


def _recovery_replay() -> dict[str, Any]:
    records = _audit_records()
    replay = {
        "replay_id": "recovery-replay-a01",
        "purpose": "recovery_outcome",
        "source": "audit",
        "source_episode_id": "p107-episode-a01",
        "source_audit_head_hash": records[-1]["head_hash"],
        "expected_terminal_head_hash": records[-1]["head_hash"],
        "audit_records": records,
        "idempotency_state": {
            "idempotency_key": "p107-a01-key",
            "committed_effect_count": 1,
            "duplicate_effect_count": 0,
            "terminal_state": "succeeded",
        },
        "recovered": True,
        "rollback_verified": True,
    }
    replay["hash"] = _stable_hash(replay)
    return replay


def _release_replay(records: list[dict[str, Any]]) -> dict[str, Any]:
    replay = {
        "replay_id": "release-replay-a01",
        "purpose": "release_regression",
        "source": "audit",
        "source_episode_id": "p107-episode-a01",
        "source_audit_head_hash": records[-1]["head_hash"],
        "expected_terminal_head_hash": records[-1]["head_hash"],
        "release_gates_passed": True,
    }
    replay["hash"] = _stable_hash(replay)
    return replay


def test_recovery_replay_hash_is_recomputed_excluding_own_hash_field() -> None:
    replay = _recovery_replay()
    replay["hash"] = _stable_hash(_without_key(replay, "hash"))

    result = validate_recovery_replay_contract(replay)

    assert result["accepted"] is True
    assert result["recomputed_replay_hash"] == replay["hash"]


def test_recovery_replay_rejects_self_referential_or_forged_replay_hash() -> None:
    replay = _recovery_replay()
    replay["hash"] = _stable_hash({"forged": "recovery"})

    result = validate_recovery_replay_contract(replay)

    assert result["accepted"] is False
    assert "replay hash" in " ".join(result["reasons"]).lower()


def test_recovery_replay_rejects_prefix_only_self_consistent_audit_hashes() -> None:
    replay = _recovery_replay()
    records = replay["audit_records"]
    assert isinstance(records, list)
    previous_hash = "GENESIS"
    for index, record in enumerate(records, start=1):
        record["previous_hash"] = previous_hash
        record["head_hash"] = f"sha256:forged-{index}"
        previous_hash = str(record["head_hash"])
    replay["source_audit_head_hash"] = previous_hash
    replay["expected_terminal_head_hash"] = previous_hash
    replay["hash"] = _stable_hash(_without_key(replay, "hash"))

    result = validate_recovery_replay_contract(replay)

    assert result["accepted"] is False
    reasons = " ".join(result["reasons"]).lower()
    assert "head hash" in reasons
    assert "source audit head hash" in reasons


def test_recovery_replay_rejects_full_sha_forged_self_consistent_audit_hashes() -> None:
    replay = _recovery_replay()
    records = replay["audit_records"]
    assert isinstance(records, list)
    previous_hash = "GENESIS"
    forged_hashes = [f"sha256:{str(index) * 64}" for index in range(1, 4)]
    for record, forged_hash in zip(records, forged_hashes, strict=True):
        record["previous_hash"] = previous_hash
        record["head_hash"] = forged_hash
        previous_hash = forged_hash
    replay["source_audit_head_hash"] = previous_hash
    replay["expected_terminal_head_hash"] = previous_hash
    replay["hash"] = _stable_hash(_without_key(replay, "hash"))

    result = validate_recovery_replay_contract(replay)

    assert result["accepted"] is False
    reasons = " ".join(result["reasons"]).lower()
    assert "canonical event content" in reasons
    assert "canonical terminal chain head" in reasons


def test_release_replay_hash_is_recomputed_excluding_own_hash_field() -> None:
    records = _audit_records()
    replay = _release_replay(records)
    replay["hash"] = _stable_hash(_without_key(replay, "hash"))

    result = validate_release_replay_contract(replay, records)

    assert result["accepted"] is True
    assert result["recomputed_replay_hash"] == replay["hash"]


def test_release_replay_rejects_self_referential_or_forged_replay_hash() -> None:
    records = _audit_records()
    replay = _release_replay(records)
    replay["hash"] = _stable_hash({"forged": "release"})

    result = validate_release_replay_contract(replay, records)

    assert result["accepted"] is False
    assert "replay hash" in " ".join(result["reasons"]).lower()


def test_release_replay_rejects_prefix_only_self_consistent_audit_hashes() -> None:
    records = _audit_records()
    previous_hash = "GENESIS"
    for index, record in enumerate(records, start=1):
        record["previous_hash"] = previous_hash
        record["head_hash"] = f"sha256:forged-{index}"
        previous_hash = str(record["head_hash"])
    replay = _release_replay(records)
    replay["source_audit_head_hash"] = previous_hash
    replay["expected_terminal_head_hash"] = previous_hash
    replay["hash"] = _stable_hash(_without_key(replay, "hash"))

    result = validate_release_replay_contract(replay, records)

    assert result["accepted"] is False
    reasons = " ".join(result["reasons"]).lower()
    assert "head hash" in reasons
    assert "source audit head hash" in reasons


def test_release_replay_rejects_full_sha_forged_self_consistent_audit_hashes() -> None:
    records = _audit_records()
    previous_hash = "GENESIS"
    forged_hashes = [f"sha256:{str(index) * 64}" for index in range(1, 4)]
    for record, forged_hash in zip(records, forged_hashes, strict=True):
        record["previous_hash"] = previous_hash
        record["head_hash"] = forged_hash
        previous_hash = forged_hash
    replay = _release_replay(records)
    replay["source_audit_head_hash"] = previous_hash
    replay["expected_terminal_head_hash"] = previous_hash
    replay["hash"] = _stable_hash(_without_key(replay, "hash"))

    result = validate_release_replay_contract(replay, records)

    assert result["accepted"] is False
    reasons = " ".join(result["reasons"]).lower()
    assert "canonical event content" in reasons
    assert "canonical terminal chain head" in reasons
