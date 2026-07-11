from __future__ import annotations

import copy
import dataclasses
import hashlib
import importlib
import json
from pathlib import Path
from typing import Any

import pytest

REQUIRED_EDGES = {
    "signal": "sha256:signal",
    "evidence": "sha256:evidence",
    "forecast": "sha256:forecast",
    "plan": "sha256:plan",
    "policy": "sha256:policy",
    "canary": "sha256:canary",
    "rollback": "sha256:rollback",
    "final_outcome": "sha256:final-outcome",
}


def _api() -> Any:
    try:
        return importlib.import_module("app.services.prevention_outcome_ledger")
    except ModuleNotFoundError as exc:
        pytest.fail(f"P108 RED: missing prevention outcome ledger implementation ({exc}).", pytrace=False)


def _entry(api: Any, *, episode_id: str = "episode-001", sequence: int = 1, parent_hash: str = "GENESIS") -> Any:
    cls = getattr(api, "PreventionOutcomeLedgerEntry", None)
    if cls is None:
        pytest.fail("P108 RED: expose frozen PreventionOutcomeLedgerEntry.", pytrace=False)
    return cls(
        episode_id=episode_id,
        sequence=sequence,
        parent_hash=parent_hash,
        occurred_at="2026-07-10T00:00:00Z",
        p107_audit_head_hash="sha256:p107-audit-head",
        p107_outcome_report_hash="sha256:p107-outcome-report",
        p107_release_replay_hash="sha256:p107-release-replay",
        cross_phase_edges=dict(REQUIRED_EDGES),
        temporal_cutoffs={
            "signal_observed_at": "2026-07-10T00:00:00Z",
            "forecast_cutoff_at": "2026-07-10T00:01:00Z",
            "plan_cutoff_at": "2026-07-10T00:02:00Z",
            "outcome_observed_at": "2026-07-10T00:10:00Z",
        },
        outcome_payload={
            "label": "inconclusive",
            "primary_metric": "incident_rate",
            "treatment": {"cohort_hash": "sha256:treatment", "value": 0.2},
            "control": {"cohort_hash": "sha256:control", "value": 0.3},
        },
        idempotency_key=f"p108:{episode_id}",
    )


def _canonical_bytes(api: Any, entry: Any) -> bytes:
    serializer = getattr(api, "canonical_entry_bytes", None)
    if serializer is None:
        pytest.fail("P108 RED: expose canonical_entry_bytes(entry).", pytrace=False)
    return serializer(entry)


def _new_store(api: Any, tmp_path: Path) -> Any:
    store_cls = getattr(api, "JsonlPreventionOutcomeLedgerStore", None)
    if store_cls is None:
        pytest.fail("P108 RED: expose JsonlPreventionOutcomeLedgerStore(path).", pytrace=False)
    return store_cls(tmp_path / "p108-outcome-ledger.jsonl")


def _new_memory_ledger(api: Any) -> Any:
    ledger_cls = getattr(api, "PreventionOutcomeLedger", None)
    if ledger_cls is None:
        pytest.fail("P108 RED: expose in-memory PreventionOutcomeLedger.", pytrace=False)
    return ledger_cls()


def _append(store: Any, entry: Any) -> str:
    return store.append(entry)


def _replay(api: Any, store_or_path: Any) -> Any:
    replay = getattr(api, "replay_prevention_outcome_ledger", None)
    if replay is None:
        pytest.fail("P108 RED: expose replay_prevention_outcome_ledger(store_or_path).", pytrace=False)
    return replay(store_or_path)


def test_outcome_ledger_entry_is_frozen_and_hash_stable_for_equivalent_inputs() -> None:
    api = _api()
    left = _entry(api)
    right = _entry(api)

    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
        left.episode_id = "mutated"

    assert _canonical_bytes(api, left) == _canonical_bytes(api, right)
    assert api.ledger_entry_hash(left) == api.ledger_entry_hash(right)


def test_append_requires_all_cross_phase_edges_and_content_hashes(tmp_path: Path) -> None:
    api = _api()
    store = _new_store(api, tmp_path)

    for missing_edge in REQUIRED_EDGES:
        edges = dict(REQUIRED_EDGES)
        edges.pop(missing_edge)
        bad = dataclasses.replace(_entry(api), cross_phase_edges=edges)
        with pytest.raises(Exception) as raised:
            _append(store, bad)
        assert missing_edge in str(raised.value)
        assert Path(store.path).read_text(encoding="utf-8") == ""

    bad_hash = dataclasses.replace(_entry(api), cross_phase_edges={**REQUIRED_EDGES, "signal": "not-a-content-hash"})
    with pytest.raises(Exception) as raised:
        _append(store, bad_hash)
    assert "content" in str(raised.value).lower() or "sha256" in str(raised.value).lower()

    wrong_entry_hash = dataclasses.asdict(_entry(api))
    wrong_entry_hash["entry_hash"] = "sha256:not-the-canonical-entry-hash"
    with pytest.raises(Exception) as raised:
        _append(store, wrong_entry_hash)
    assert "hash" in str(raised.value).lower()


def test_duplicate_equivalent_episode_append_is_idempotent(tmp_path: Path) -> None:
    api = _api()
    store = _new_store(api, tmp_path)
    entry = _entry(api)

    first = _append(store, entry)
    second = _append(store, _entry(api))

    assert first == second
    assert Path(store.path).read_text(encoding="utf-8").count("\n") == 1


def test_in_memory_ledger_uses_same_hash_link_and_idempotency_contract() -> None:
    api = _api()
    ledger = _new_memory_ledger(api)

    first = _append(ledger, _entry(api))
    duplicate = _append(ledger, _entry(api))
    second = _append(ledger, _entry(api, episode_id="episode-002", sequence=2, parent_hash=first))

    assert duplicate == first
    assert ledger.head_hash == second
    assert len(ledger.entries) == 2
    assert ledger.entries[1]["parent_hash"] == first


def test_same_episode_id_with_different_content_is_rejected(tmp_path: Path) -> None:
    api = _api()
    store = _new_store(api, tmp_path)
    original = _entry(api)
    _append(store, original)
    before = Path(store.path).read_bytes()
    conflicting = dataclasses.replace(
        original,
        outcome_payload={**original.outcome_payload, "label": "harmful"},
    )

    with pytest.raises(Exception) as raised:
        _append(store, conflicting)

    assert "conflict" in str(raised.value).lower() or "episode" in str(raised.value).lower()
    assert Path(store.path).read_bytes() == before


def test_sequence_parent_and_head_hash_are_validated_on_append_and_replay(tmp_path: Path) -> None:
    api = _api()
    store = _new_store(api, tmp_path)
    first = _append(store, _entry(api))
    second_entry = _entry(api, episode_id="episode-002", sequence=2, parent_hash=first)
    second = _append(store, second_entry)

    replay = _replay(api, store)

    assert replay.head_hash == second
    assert replay.record_count == 2
    assert replay.entries[-1]["parent_hash"] == first

    with pytest.raises(Exception) as raised:
        _append(store, _entry(api, episode_id="episode-003", sequence=4, parent_hash=second))
    assert "sequence" in str(raised.value).lower()

    with pytest.raises(Exception) as raised:
        _append(store, _entry(api, episode_id="episode-003", sequence=3, parent_hash="sha256:not-head"))
    assert "parent" in str(raised.value).lower()


def test_jsonl_replay_rejects_truncation_sequence_parent_duplicate_parent_and_tamper(tmp_path: Path) -> None:
    api = _api()
    store = _new_store(api, tmp_path)
    first_hash = _append(store, _entry(api))
    _append(store, _entry(api, episode_id="episode-002", sequence=2, parent_hash=first_hash))
    records = [json.loads(line) for line in Path(store.path).read_text(encoding="utf-8").splitlines()]

    cases: list[tuple[str, list[dict[str, Any]] | str, str]] = []

    gap = copy.deepcopy(records)
    gap[1]["sequence"] = 3
    _rehash(gap[1])
    cases.append(("gap", gap, "sequence"))

    parent = copy.deepcopy(records)
    parent[1]["parent_hash"] = "sha256:wrong-parent"
    _rehash(parent[1])
    cases.append(("parent", parent, "parent"))

    duplicate_parent = copy.deepcopy(records)
    duplicate_parent[1]["parent_hash"] = "GENESIS"
    _rehash(duplicate_parent[1])
    cases.append(("duplicate-parent", duplicate_parent, "duplicate"))

    tampered = copy.deepcopy(records)
    tampered[0]["outcome_payload"]["label"] = "prevented"
    cases.append(("tamper", tampered, "tamper"))

    cases.append(("truncated", Path(store.path).read_text(encoding="utf-8").rstrip("\n"), "partial"))

    for name, payload, expected in cases:
        path = tmp_path / f"{name}.jsonl"
        if isinstance(payload, str):
            path.write_text(payload, encoding="utf-8")
        else:
            path.write_text("\n".join(json.dumps(record, sort_keys=True) for record in payload) + "\n", encoding="utf-8")
        with pytest.raises(Exception) as raised:
            _replay(api, path)
        assert expected in str(raised.value).lower()


def _rehash(record: dict[str, Any]) -> None:
    payload = dict(record)
    payload.pop("entry_hash", None)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    record["entry_hash"] = f"sha256:{hashlib.sha256(encoded).hexdigest()}"
