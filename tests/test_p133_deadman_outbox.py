from __future__ import annotations

import errno
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

import app.services.p133_deadman_outbox as p133
from app.monitor_cli import main as monitor_cli_main
from app.services.p110_evaluation import stable_hash
from app.services.p121_signals import P121_AUTHORITY_COUNTER_KEYS
from app.services.p133_deadman_outbox import (
    DeadmanOutbox,
    P133DeadmanError,
    P133DurabilityUncertainError,
    acknowledge_event,
    list_outbox,
    load_deadman_config,
    normalize_watchdog_result,
)


class FakeClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 7, 13, 0, 0, tzinfo=UTC)
        self.sleeps: list[float] = []

    def now(self) -> datetime:
        return self.current

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.current += timedelta(seconds=seconds)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _config_path(tmp_path: Path, **overrides: Any) -> Path:
    raw: dict[str, Any] = {
        "schema_version": "p133.deadman_config.v1",
        "allowed_artifact_roots": [str(tmp_path)],
        "state_path": str(tmp_path / "monitor-state.json"),
        "outbox_dir": str(tmp_path / "outbox"),
        "cursor_path": str(tmp_path / "cursor" / "deadman-cursor.json"),
        "ack_dir": str(tmp_path / "acks"),
        "runtime_ref": "local-runtime-01",
        "check_interval_seconds": 30,
        "heartbeat_timeout_seconds": 180,
        "reminder_interval_seconds": 300,
        "max_event_files": 32,
        "max_outbox_bytes": 1_048_576,
        "max_event_bytes": 32_768,
        "min_artifact_free_bytes": 1,
    }
    raw.update(overrides)
    path = tmp_path / "deadman-config.json"
    _write_json(path, raw)
    return path


def _load_event(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _valid_hash(payload: dict[str, Any], hash_key: str) -> bool:
    return payload[hash_key] == stable_hash({key: value for key, value in payload.items() if key != hash_key})


def _watchdog(reason: str, *, state_hash: str = "sha256:" + "a" * 64, age: int = 10) -> dict[str, Any]:
    return {"healthy": reason == "heartbeat_current", "reason": reason, "state_hash": state_hash, "heartbeat_age_seconds": age}


def test_config_rejects_unsafe_shapes_paths_and_secret_authority_fields(tmp_path: Path) -> None:
    config = load_deadman_config(_config_path(tmp_path))
    assert config.schema_version == "p133.deadman_config.v1"
    assert config.state_path == tmp_path / "monitor-state.json"
    assert config.config_hash.startswith("sha256:")
    assert len(config.config_hash) == 71

    bad_unknown = _config_path(tmp_path / "unknown", extra="field")
    with pytest.raises(P133DeadmanError, match="unknown_configuration_field"):
        load_deadman_config(bad_unknown)

    bad_bool = _config_path(tmp_path / "bool", check_interval_seconds=True)
    with pytest.raises(P133DeadmanError, match="invalid_positive_integer"):
        load_deadman_config(bad_bool)

    bad_secret = _config_path(tmp_path / "secret", api_token="abc")
    with pytest.raises(P133DeadmanError, match="forbidden_configuration_field"):
        load_deadman_config(bad_secret)

    bad_url = _config_path(tmp_path / "url", runtime_ref="https://example.invalid/runtime")
    with pytest.raises(P133DeadmanError, match="forbidden_configuration_value"):
        load_deadman_config(bad_url)

    bad_value = _config_path(tmp_path / "value", runtime_ref="prod-token-ref")
    with pytest.raises(P133DeadmanError, match="forbidden_configuration_value"):
        load_deadman_config(bad_value)

    outside = _config_path(tmp_path / "outside", state_path=str(tmp_path.parent / "state.json"))
    with pytest.raises(P133DeadmanError, match="path_outside_allowed_roots"):
        load_deadman_config(outside)

    overlap = _config_path(
        tmp_path / "overlap",
        outbox_dir=str(tmp_path / "overlap" / "same"),
        ack_dir=str(tmp_path / "overlap" / "same" / "acks"),
    )
    with pytest.raises(P133DeadmanError, match="artifact_paths_overlap"):
        load_deadman_config(overlap)

    root = tmp_path / "symlink-root"
    root.mkdir()
    link = root / "link"
    link.symlink_to(tmp_path, target_is_directory=True)
    symlink_parent = _config_path(root, allowed_artifact_roots=[str(root)], state_path=str(link / "state.json"))
    with pytest.raises(P133DeadmanError, match="path_has_symlink_parent"):
        load_deadman_config(symlink_parent)

    config_link = tmp_path / "linked-config.json"
    config_link.symlink_to(_config_path(tmp_path / "linked-config-target"))
    with pytest.raises(P133DeadmanError, match="path_has_symlink_parent"):
        load_deadman_config(config_link)


def test_first_check_creates_nested_artifact_directories_before_space_probe(tmp_path: Path) -> None:
    root = tmp_path / "allowed"
    root.mkdir()
    config = load_deadman_config(
        _config_path(
            root,
            outbox_dir=str(root / "nested" / "outbox"),
            cursor_path=str(root / "nested" / "cursor" / "cursor.json"),
            ack_dir=str(root / "nested" / "acks"),
        )
    )

    result = DeadmanOutbox(
        config,
        now=FakeClock().now,
        watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("runtime_stopped"),
    ).check_once()

    assert result["transition_kind"] == "opened"
    assert config.outbox_dir.is_dir()
    assert config.cursor_path.is_file()


def test_normalize_watchdog_result_has_exact_seven_value_mapping_and_redaction(tmp_path: Path) -> None:
    config = load_deadman_config(_config_path(tmp_path))
    expected = {
        "heartbeat_current": ("heartbeat_current", True),
        "runtime_stopped": ("runtime_stopped", False),
        "heartbeat_stale": ("heartbeat_stale", False),
        "state_missing": ("state_missing", False),
        "heartbeat_missing": ("heartbeat_invalid", False),
        "heartbeat_in_future": ("heartbeat_invalid", False),
        "state_invalid": ("state_invalid", False),
        "state_hash_invalid": ("state_invalid", False),
        "authority_not_exact_zero": ("state_invalid", False),
        "runtime_execution_boundary_violated": ("state_invalid", False),
        "invalid_source_state": ("state_invalid", False),
        "invalid_canary_state": ("state_invalid", False),
        "invalid_lifecycle_state": ("state_invalid", False),
        "source_manifest_mismatch": ("state_invalid", False),
        "invalid_timestamp": ("state_invalid", False),
    }
    observed: set[str] = set()
    for raw_reason, (reason, healthy) in expected.items():
        snapshot = normalize_watchdog_result(
            {
                "reason": raw_reason,
                "healthy": healthy,
                "state_hash": "sha256:" + "b" * 64,
                "heartbeat_age_seconds": 1.5,
                "path": "/tmp/secret-state",
                "runtime_id": "raw-runtime",
                "error": "credential token leaked",
            },
            config=config,
        )
        observed.add(snapshot["reason"])
        assert snapshot["reason"] == reason
        assert snapshot["healthy"] is healthy
        encoded = json.dumps(snapshot, sort_keys=True)
        assert "/tmp/secret-state" not in encoded
        assert "raw-runtime" not in encoded
        assert "credential token leaked" not in encoded
        assert snapshot["runtime_ref_hash"] == config.runtime_ref_hash
        assert snapshot["snapshot_fingerprint"] == p133._snapshot_fingerprint(snapshot)

    for malformed in ({}, {"reason": 3}, {"reason": "future_new_reason"}, {"reason": "heartbeat_current", "healthy": False}):
        snapshot = normalize_watchdog_result(malformed, config=config)
        assert snapshot["reason"] == "watchdog_contract_invalid"
        assert snapshot["healthy"] is False
        observed.add(snapshot["reason"])
    assert observed == {
        "heartbeat_current",
        "runtime_stopped",
        "heartbeat_stale",
        "state_missing",
        "heartbeat_invalid",
        "state_invalid",
        "watchdog_contract_invalid",
    }

    malformed_hash = normalize_watchdog_result(
        _watchdog("runtime_stopped", state_hash="sha256:" + "c" * 63 + "-suffix"),
        config=config,
    )
    assert malformed_hash["state_hash"] is None


def test_transitions_deduplicate_remind_recover_and_preserve_zero_authority(tmp_path: Path) -> None:
    config = load_deadman_config(_config_path(tmp_path))
    clock = FakeClock()
    results = [
        _watchdog("heartbeat_current"),
        _watchdog("heartbeat_stale", state_hash="sha256:" + "1" * 64),
        _watchdog("heartbeat_stale", state_hash="sha256:" + "1" * 64),
        _watchdog("heartbeat_stale", state_hash="sha256:" + "2" * 64),
        _watchdog("heartbeat_stale", state_hash="sha256:" + "2" * 64),
        _watchdog("heartbeat_current", state_hash="sha256:" + "3" * 64),
        _watchdog("heartbeat_current", state_hash="sha256:" + "3" * 64),
    ]
    runtime = DeadmanOutbox(config, now=clock.now, sleep=clock.sleep, watchdog_evaluator=lambda *_args, **_kwargs: results.pop(0))

    assert runtime.check_once()["transition_kind"] == "deduplicated"
    clock.current += timedelta(seconds=1)
    opened = runtime.check_once()
    clock.current += timedelta(seconds=299)
    dedup = runtime.check_once()
    clock.current += timedelta(seconds=1)
    updated = runtime.check_once()
    clock.current += timedelta(seconds=300)
    reminder = runtime.check_once()
    clock.current += timedelta(seconds=1)
    recovered = runtime.check_once()
    clock.current += timedelta(seconds=1)
    healthy = runtime.check_once()

    assert [opened["transition_kind"], dedup["transition_kind"], updated["transition_kind"], reminder["transition_kind"], recovered["transition_kind"], healthy["transition_kind"]] == [
        "opened",
        "deduplicated",
        "updated",
        "reminder",
        "recovered",
        "deduplicated",
    ]
    events = list_outbox(config)
    assert [event["transition_kind"] for event in events] == ["opened", "updated", "reminder", "recovered"]
    assert [event["sequence"] for event in events] == [1, 2, 3, 4]
    assert events[0]["previous_event_id"] is None
    assert events[1]["previous_event_id"] == events[0]["event_id"]
    assert events[-1]["snapshot"]["reason"] == "heartbeat_current"
    assert all(set(event["authority_counters"]) == set(P121_AUTHORITY_COUNTER_KEYS) for event in events)
    assert all(all(value == 0 and type(value) is int for value in event["authority_counters"].values()) for event in events)
    encoded = json.dumps(events, sort_keys=True)
    assert str(config.state_path) not in encoded
    assert config.runtime_ref not in encoded
    cursor = json.loads(config.cursor_path.read_text(encoding="utf-8"))
    assert cursor["active_incident"] is None
    assert cursor["next_sequence"] == 5
    assert _valid_hash(cursor, "cursor_hash")


def test_increasing_heartbeat_age_does_not_create_update_churn(tmp_path: Path) -> None:
    config = load_deadman_config(_config_path(tmp_path))
    clock = FakeClock()
    results = [
        _watchdog("heartbeat_stale", state_hash="sha256:" + "d" * 64, age=181),
        _watchdog("heartbeat_stale", state_hash="sha256:" + "d" * 64, age=211),
    ]
    runtime = DeadmanOutbox(
        config,
        now=clock.now,
        sleep=clock.sleep,
        watchdog_evaluator=lambda *_args, **_kwargs: results.pop(0),
    )
    opened = runtime.check_once()
    clock.current += timedelta(seconds=30)
    deduplicated = runtime.check_once()

    assert opened["transition_kind"] == "opened"
    assert deduplicated["transition_kind"] == "deduplicated"
    assert [event["transition_kind"] for event in list_outbox(config)] == ["opened"]


def test_event_first_cursor_second_crash_replay_reuses_existing_event_time_and_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = load_deadman_config(_config_path(tmp_path))
    clock = FakeClock()
    calls = {"cursor_writes": 0}
    original_write_cursor = p133._write_cursor

    def crash_before_cursor(path: Path, cursor: dict[str, Any], roots: tuple[Path, ...]) -> None:
        calls["cursor_writes"] += 1
        if calls["cursor_writes"] == 1:
            raise RuntimeError("crash_after_event_replace")
        original_write_cursor(path, cursor, roots)

    monkeypatch.setattr(p133, "_write_cursor", crash_before_cursor)
    runtime = DeadmanOutbox(config, now=clock.now, sleep=clock.sleep, watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("runtime_stopped", state_hash="sha256:" + "4" * 64))

    with pytest.raises(RuntimeError, match="crash_after_event_replace"):
        runtime.check_once()
    events_after_crash = sorted(config.outbox_dir.glob("*.json"))
    assert len(events_after_crash) == 1
    first_bytes = events_after_crash[0].read_bytes()
    first_event = _load_event(events_after_crash[0])
    assert not config.cursor_path.exists()

    clock.current += timedelta(hours=1)
    replayed = runtime.check_once()
    assert replayed["event_id"] == first_event["event_id"]
    assert replayed["occurred_at"] == first_event["occurred_at"]
    assert events_after_crash[0].read_bytes() == first_bytes
    cursor = json.loads(config.cursor_path.read_text(encoding="utf-8"))
    assert cursor["next_sequence"] == 2
    assert cursor["last_checked_at"] == "2026-07-13T01:00:00Z"
    assert cursor["active_incident"]["last_emitted_at"] == first_event["occurred_at"]


def test_crash_replay_reuses_later_transition_event_without_sequence_regression(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = load_deadman_config(_config_path(tmp_path))
    clock = FakeClock()
    opened_runtime = DeadmanOutbox(
        config,
        now=clock.now,
        sleep=clock.sleep,
        watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("heartbeat_stale", state_hash="sha256:" + "1" * 64),
    )
    opened_runtime.check_once()
    cursor_before = config.cursor_path.read_bytes()
    clock.current += timedelta(seconds=1)

    original_write_cursor = p133._write_cursor
    monkeypatch.setattr(
        p133,
        "_write_cursor",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("crash_after_update_event")),
    )
    updated_runtime = DeadmanOutbox(
        config,
        now=clock.now,
        sleep=clock.sleep,
        watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("runtime_stopped", state_hash="sha256:" + "2" * 64),
    )
    with pytest.raises(RuntimeError, match="crash_after_update_event"):
        updated_runtime.check_once()
    assert config.cursor_path.read_bytes() == cursor_before
    events_after_crash = list_outbox(config)
    assert [event["sequence"] for event in events_after_crash] == [1, 2]
    update_before = events_after_crash[-1]

    monkeypatch.setattr(p133, "_write_cursor", original_write_cursor)
    clock.current += timedelta(hours=1)
    replayed = updated_runtime.check_once()
    assert replayed["event_id"] == update_before["event_id"]
    assert replayed["occurred_at"] == update_before["occurred_at"]
    assert [event["sequence"] for event in list_outbox(config)] == [1, 2]
    cursor = json.loads(config.cursor_path.read_text(encoding="utf-8"))
    assert cursor["next_sequence"] == 3
    assert cursor["active_incident"]["last_event_id"] == update_before["event_id"]


def test_changed_watchdog_after_event_cursor_crash_fails_closed_without_advancing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = load_deadman_config(_config_path(tmp_path))
    clock = FakeClock()
    original_write_cursor = p133._write_cursor
    monkeypatch.setattr(
        p133,
        "_write_cursor",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("crash_after_event")),
    )
    runtime = DeadmanOutbox(
        config,
        now=clock.now,
        watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("runtime_stopped"),
    )
    with pytest.raises(RuntimeError, match="crash_after_event"):
        runtime.check_once()
    event_before = next(config.outbox_dir.iterdir()).read_bytes()
    monkeypatch.setattr(p133, "_write_cursor", original_write_cursor)
    clock.current += timedelta(seconds=1)
    recovered_runtime = DeadmanOutbox(
        config,
        now=clock.now,
        watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("heartbeat_current"),
    )

    with pytest.raises(P133DeadmanError, match="pending_event_requires_matching_replay"):
        recovered_runtime.check_once()
    assert not config.cursor_path.exists()
    assert next(config.outbox_dir.iterdir()).read_bytes() == event_before


def test_conflicting_replay_existing_event_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = load_deadman_config(_config_path(tmp_path))
    clock = FakeClock()
    monkeypatch.setattr(p133, "_write_cursor", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("crash_after_event_replace")))
    runtime = DeadmanOutbox(config, now=clock.now, sleep=clock.sleep, watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("runtime_stopped"))
    with pytest.raises(RuntimeError):
        runtime.check_once()
    event_path = next(config.outbox_dir.glob("*.json"))
    event = _load_event(event_path)
    event["transition_kind"] = "updated"
    event["event_hash"] = stable_hash({key: value for key, value in event.items() if key != "event_hash"})
    event_path.write_text(json.dumps(event, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    monkeypatch.setattr(p133, "_write_cursor", p133._ORIGINAL_WRITE_CURSOR)

    with pytest.raises(
        P133DeadmanError,
        match="linked_event_missing_previous_link|event_id_derivation_mismatch|conflicting_existing_event",
    ):
        runtime.check_once()


def test_ack_is_local_idempotent_and_retention_prunes_only_acknowledged_owned_events(tmp_path: Path) -> None:
    config = load_deadman_config(_config_path(tmp_path, max_event_files=1, max_outbox_bytes=100_000))
    clock = FakeClock()
    runtime = DeadmanOutbox(config, now=clock.now, sleep=clock.sleep, watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("heartbeat_stale", state_hash="sha256:" + "5" * 64))
    opened = runtime.check_once()
    ack = acknowledge_event(config, opened["event_id"], now=clock.now)
    clock.current += timedelta(hours=1)
    duplicate = acknowledge_event(config, opened["event_id"], now=clock.now)
    assert ack == duplicate
    assert _valid_hash(ack, "ack_hash")
    assert set(ack["authority_counters"]) == set(P121_AUTHORITY_COUNTER_KEYS)

    clock.current += timedelta(seconds=1)
    runtime = DeadmanOutbox(config, now=clock.now, sleep=clock.sleep, watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("runtime_stopped", state_hash="sha256:" + "6" * 64))
    updated = runtime.check_once()
    events = list_outbox(config)
    assert [event["event_id"] for event in events] == [updated["event_id"]]
    assert not (config.outbox_dir / f"{opened['event_id']}.json").exists()
    assert not (config.ack_dir / f"{opened['event_id']}.json").exists()
    assert json.loads(config.cursor_path.read_text(encoding="utf-8"))["active_incident"]["last_event_id"] == updated["event_id"]


def test_ack_rejects_missing_foreign_tampered_symlinked_and_changed_events(tmp_path: Path) -> None:
    clock = FakeClock()
    missing_config = load_deadman_config(_config_path(tmp_path / "missing"))
    with pytest.raises(P133DeadmanError, match="event_missing"):
        acknowledge_event(missing_config, "a" * 64, now=clock.now)

    foreign_source = load_deadman_config(_config_path(tmp_path / "source"))
    foreign_opened = DeadmanOutbox(
        foreign_source,
        now=clock.now,
        watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("runtime_stopped"),
    ).check_once()
    foreign_target = load_deadman_config(_config_path(tmp_path / "foreign"))
    foreign_target.outbox_dir.mkdir(parents=True)
    source_event = foreign_source.outbox_dir / f"{foreign_opened['event_id']}.json"
    target_event = foreign_target.outbox_dir / source_event.name
    target_event.write_bytes(source_event.read_bytes())
    with pytest.raises(P133DeadmanError, match="event_config_mismatch"):
        acknowledge_event(foreign_target, foreign_opened["event_id"], now=clock.now)

    tampered_config = load_deadman_config(_config_path(tmp_path / "tampered"))
    tampered_opened = DeadmanOutbox(
        tampered_config,
        now=clock.now,
        watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("runtime_stopped"),
    ).check_once()
    tampered_path = tampered_config.outbox_dir / f"{tampered_opened['event_id']}.json"
    tampered = _load_event(tampered_path)
    tampered["sequence"] = 99
    _write_json(tampered_path, tampered)
    with pytest.raises(P133DeadmanError, match="event_hash_invalid"):
        acknowledge_event(tampered_config, tampered_opened["event_id"], now=clock.now)

    symlink_config = load_deadman_config(_config_path(tmp_path / "linked"))
    symlink_opened = DeadmanOutbox(
        symlink_config,
        now=clock.now,
        watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("runtime_stopped"),
    ).check_once()
    linked_path = symlink_config.outbox_dir / f"{symlink_opened['event_id']}.json"
    linked_target = linked_path.with_name("target.json")
    os.replace(linked_path, linked_target)
    linked_path.symlink_to(linked_target)
    with pytest.raises(P133DeadmanError, match="event_not_regular"):
        acknowledge_event(symlink_config, symlink_opened["event_id"], now=clock.now)

    changed_config = load_deadman_config(_config_path(tmp_path / "changed"))
    changed_opened = DeadmanOutbox(
        changed_config,
        now=clock.now,
        watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("runtime_stopped"),
    ).check_once()
    acknowledge_event(changed_config, changed_opened["event_id"], now=clock.now)
    changed_path = changed_config.outbox_dir / f"{changed_opened['event_id']}.json"
    changed = _load_event(changed_path)
    changed["snapshot"]["reason"] = "heartbeat_stale"
    changed["snapshot"]["snapshot_fingerprint"] = p133._snapshot_fingerprint(changed["snapshot"])
    changed["event_hash"] = stable_hash({key: value for key, value in changed.items() if key != "event_hash"})
    _write_json(changed_path, changed)
    with pytest.raises(P133DeadmanError, match="event_id_derivation_mismatch"):
        acknowledge_event(changed_config, changed_opened["event_id"], now=clock.now)


def test_unrecoverable_budget_pressure_does_not_commit_event_or_cursor(tmp_path: Path) -> None:
    config = load_deadman_config(_config_path(tmp_path, max_event_files=1, max_outbox_bytes=100_000))
    clock = FakeClock()
    opened_runtime = DeadmanOutbox(
        config,
        now=clock.now,
        sleep=clock.sleep,
        watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("heartbeat_stale", state_hash="sha256:" + "3" * 64),
    )
    opened = opened_runtime.check_once()
    cursor_before = config.cursor_path.read_bytes()
    event_before = (config.outbox_dir / f"{opened['event_id']}.json").read_bytes()
    clock.current += timedelta(seconds=1)
    updated_runtime = DeadmanOutbox(
        config,
        now=clock.now,
        sleep=clock.sleep,
        watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("runtime_stopped", state_hash="sha256:" + "4" * 64),
    )

    with pytest.raises(P133DeadmanError, match="outbox_budget_exhausted"):
        updated_runtime.check_once()

    assert config.cursor_path.read_bytes() == cursor_before
    assert list(config.outbox_dir.glob("*.json")) == [config.outbox_dir / f"{opened['event_id']}.json"]
    assert (config.outbox_dir / f"{opened['event_id']}.json").read_bytes() == event_before


def test_retention_partial_delete_recovers_orphan_ack_before_retry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = load_deadman_config(_config_path(tmp_path, max_event_files=1, max_outbox_bytes=100_000))
    clock = FakeClock()
    opened_runtime = DeadmanOutbox(
        config,
        now=clock.now,
        watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("heartbeat_stale", state_hash="sha256:" + "5" * 64),
    )
    opened = opened_runtime.check_once()
    acknowledge_event(config, opened["event_id"], now=clock.now)
    cursor_before = config.cursor_path.read_bytes()
    original_unlink = p133._unlink_regular_file
    unlink_count = 0

    def crash_before_ack_unlink(
        path: Path,
        *,
        expected: os.stat_result,
        expected_bytes: bytes,
    ) -> None:
        nonlocal unlink_count
        unlink_count += 1
        if unlink_count == 2:
            raise RuntimeError("crash_before_ack_unlink")
        original_unlink(path, expected=expected, expected_bytes=expected_bytes)

    monkeypatch.setattr(p133, "_unlink_regular_file", crash_before_ack_unlink)
    clock.current += timedelta(seconds=1)
    updated_runtime = DeadmanOutbox(
        config,
        now=clock.now,
        watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("runtime_stopped", state_hash="sha256:" + "6" * 64),
    )
    with pytest.raises(RuntimeError, match="crash_before_ack_unlink"):
        updated_runtime.check_once()
    assert config.cursor_path.read_bytes() == cursor_before
    assert not (config.outbox_dir / f"{opened['event_id']}.json").exists()
    assert (config.ack_dir / f"{opened['event_id']}.json").exists()

    monkeypatch.setattr(p133, "_unlink_regular_file", original_unlink)
    updated = updated_runtime.check_once()
    assert updated["transition_kind"] == "updated"
    assert not (config.ack_dir / f"{opened['event_id']}.json").exists()
    assert [event["event_id"] for event in list_outbox(config)] == [updated["event_id"]]


def test_foreign_outbox_entry_blocks_retention_and_remains_present(tmp_path: Path) -> None:
    config = load_deadman_config(_config_path(tmp_path))
    config.outbox_dir.mkdir(parents=True)
    foreign = config.outbox_dir / "foreign.txt"
    foreign.write_text("not-owned", encoding="utf-8")

    with pytest.raises(P133DeadmanError, match="invalid_event_filename"):
        DeadmanOutbox(config).enforce_retention()
    assert foreign.read_text(encoding="utf-8") == "not-owned"


def test_process_lease_serializes_checks_lists_acks_and_retention(tmp_path: Path) -> None:
    config = load_deadman_config(_config_path(tmp_path))
    runtime = DeadmanOutbox(
        config,
        now=FakeClock().now,
        watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("runtime_stopped"),
    )

    with p133._DeadmanLease(config):
        with pytest.raises(P133DeadmanError, match="deadman_lease_unavailable"):
            runtime.check_once()
        with pytest.raises(P133DeadmanError, match="deadman_lease_unavailable"):
            list_outbox(config)
        with pytest.raises(P133DeadmanError, match="deadman_lease_unavailable"):
            runtime.enforce_retention()


def test_process_lease_rejects_real_competing_cli_processes(tmp_path: Path) -> None:
    config_path = _config_path(tmp_path)
    config = load_deadman_config(config_path)
    opened = DeadmanOutbox(
        config,
        now=FakeClock().now,
        watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("runtime_stopped"),
    ).check_once()
    commands = (
        ["deadman-check", "--config", str(config_path)],
        ["outbox-list", "--config", str(config_path)],
        ["outbox-ack", "--config", str(config_path), "--event-id", opened["event_id"]],
    )

    with p133._DeadmanLease(config):
        for args in commands:
            result = subprocess.run(
                [sys.executable, "-m", "app.monitor_cli", *args],
                cwd=Path.cwd(),
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            assert result.returncode == 2
            assert "deadman_lease_unavailable" in result.stderr


def test_post_load_directory_swaps_fail_closed_without_writing_foreign_targets(tmp_path: Path) -> None:
    for target_name in ("outbox", "acks", "cursor"):
        workspace = tmp_path / target_name
        config = load_deadman_config(_config_path(workspace))
        foreign = workspace / "foreign"
        foreign.mkdir()
        target = {
            "outbox": config.outbox_dir,
            "acks": config.ack_dir,
            "cursor": config.cursor_path.parent,
        }[target_name]
        target.mkdir(parents=True, exist_ok=True)
        backup = target.with_name(target.name + "-original")
        os.replace(target, backup)
        target.symlink_to(foreign, target_is_directory=True)
        runtime = DeadmanOutbox(
            config,
            now=FakeClock().now,
            watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("runtime_stopped"),
        )

        with pytest.raises((P133DeadmanError, OSError)):
            runtime.check_once()
        assert list(foreign.iterdir()) == []


def test_excessive_cursor_clock_rollback_fails_closed(tmp_path: Path) -> None:
    config = load_deadman_config(_config_path(tmp_path))
    clock = FakeClock()
    runtime = DeadmanOutbox(
        config,
        now=clock.now,
        watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("runtime_stopped"),
    )
    runtime.check_once()
    cursor = json.loads(config.cursor_path.read_text(encoding="utf-8"))
    cursor["last_checked_at"] = (clock.current + timedelta(seconds=6)).isoformat().replace("+00:00", "Z")
    cursor["cursor_hash"] = stable_hash({key: value for key, value in cursor.items() if key != "cursor_hash"})
    _write_json(config.cursor_path, cursor)

    with pytest.raises(P133DeadmanError, match="clock_rollback_exceeds_tolerance"):
        runtime.check_once()


def test_retention_candidate_swap_before_dirfd_unlink_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = load_deadman_config(_config_path(tmp_path, max_event_files=1, max_outbox_bytes=100_000))
    clock = FakeClock()
    runtime = DeadmanOutbox(
        config,
        now=clock.now,
        watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("heartbeat_stale"),
    )
    opened = runtime.check_once()
    acknowledge_event(config, opened["event_id"], now=clock.now)
    event_path = config.outbox_dir / f"{opened['event_id']}.json"
    original_unlink = p133._unlink_regular_file
    swapped = False

    def swap_then_unlink(
        path: Path,
        *,
        expected: os.stat_result,
        expected_bytes: bytes,
    ) -> None:
        nonlocal swapped
        if path == event_path and not swapped:
            swapped = True
            os.replace(path, path.with_suffix(".original"))
            path.write_text("foreign replacement\n", encoding="utf-8")
        original_unlink(path, expected=expected, expected_bytes=expected_bytes)

    monkeypatch.setattr(p133, "_unlink_regular_file", swap_then_unlink)
    clock.current += timedelta(seconds=1)
    changed = DeadmanOutbox(
        config,
        now=clock.now,
        watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("runtime_stopped", state_hash="sha256:" + "4" * 64),
    )

    with pytest.raises(P133DeadmanError, match="retention_candidate_changed"):
        changed.check_once()
    assert event_path.read_text(encoding="utf-8") == "foreign replacement\n"


def test_retention_same_inode_same_size_rewrite_before_unlink_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = load_deadman_config(_config_path(tmp_path, max_event_files=1, max_outbox_bytes=100_000))
    clock = FakeClock()
    runtime = DeadmanOutbox(
        config,
        now=clock.now,
        watchdog_evaluator=lambda *_args, **_kwargs: _watchdog(
            "heartbeat_stale", state_hash="sha256:" + "5" * 64
        ),
    )
    opened = runtime.check_once()
    acknowledge_event(config, opened["event_id"], now=clock.now)
    event_path = config.outbox_dir / f"{opened['event_id']}.json"
    original_unlink = p133._unlink_regular_file
    rewritten = False

    def rewrite_then_unlink(
        path: Path,
        *,
        expected: os.stat_result,
        expected_bytes: bytes,
    ) -> None:
        nonlocal rewritten
        if path == event_path and not rewritten:
            rewritten = True
            before = os.lstat(path)
            tampered = _load_event(path)
            tampered["occurred_at"] = "2026-07-13T00:00:01Z"
            tampered["event_hash"] = stable_hash(
                {key: value for key, value in tampered.items() if key != "event_hash"}
            )
            replacement = (json.dumps(tampered, indent=2, sort_keys=True) + "\n").encode()
            assert len(replacement) == before.st_size
            path.write_bytes(replacement)
            after = os.lstat(path)
            assert (after.st_dev, after.st_ino, after.st_size) == (
                before.st_dev,
                before.st_ino,
                before.st_size,
            )
        original_unlink(path, expected=expected, expected_bytes=expected_bytes)

    monkeypatch.setattr(p133, "_unlink_regular_file", rewrite_then_unlink)
    clock.current += timedelta(seconds=1)
    changed = DeadmanOutbox(
        config,
        now=clock.now,
        watchdog_evaluator=lambda *_args, **_kwargs: _watchdog(
            "runtime_stopped", state_hash="sha256:" + "4" * 64
        ),
    )

    with pytest.raises(P133DeadmanError, match="retention_candidate_changed"):
        changed.check_once()
    assert event_path.exists()
    assert _load_event(event_path)["occurred_at"] == "2026-07-13T00:00:01Z"


def test_retention_rejects_group_or_world_writable_artifact_directory(
    tmp_path: Path,
) -> None:
    config = load_deadman_config(_config_path(tmp_path, max_event_files=1, max_outbox_bytes=100_000))
    clock = FakeClock()
    runtime = DeadmanOutbox(
        config,
        now=clock.now,
        watchdog_evaluator=lambda *_args, **_kwargs: _watchdog(
            "heartbeat_stale", state_hash="sha256:" + "5" * 64
        ),
    )
    opened = runtime.check_once()
    acknowledge_event(config, opened["event_id"], now=clock.now)
    cursor_before = config.cursor_path.read_bytes()
    event_path = config.outbox_dir / f"{opened['event_id']}.json"
    config.outbox_dir.chmod(0o777)
    clock.current += timedelta(seconds=1)
    changed = DeadmanOutbox(
        config,
        now=clock.now,
        watchdog_evaluator=lambda *_args, **_kwargs: _watchdog(
            "runtime_stopped", state_hash="sha256:" + "4" * 64
        ),
    )

    with pytest.raises(P133DeadmanError, match="retention_parent_permissions_unsafe"):
        changed.check_once()
    assert event_path.exists()
    assert config.cursor_path.read_bytes() == cursor_before


def test_low_space_tamper_symlink_and_hardlink_rejections_preserve_prior_cursor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = load_deadman_config(_config_path(tmp_path, max_event_files=1, max_outbox_bytes=100_000))
    clock = FakeClock()
    runtime = DeadmanOutbox(config, now=clock.now, sleep=clock.sleep, watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("heartbeat_stale", state_hash="sha256:" + "7" * 64))
    opened = runtime.check_once()
    cursor_before = config.cursor_path.read_bytes()
    monkeypatch.setattr(p133, "_artifact_free_bytes", lambda *_args, **_kwargs: 0)
    clock.current += timedelta(seconds=1)
    runtime = DeadmanOutbox(config, now=clock.now, sleep=clock.sleep, watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("runtime_stopped", state_hash="sha256:" + "8" * 64))
    with pytest.raises(OSError, match="artifact_free_space_below_floor"):
        runtime.check_once()
    assert config.cursor_path.read_bytes() == cursor_before
    assert [event["event_id"] for event in list_outbox(config)] == [opened["event_id"]]
    monkeypatch.setattr(p133, "_artifact_free_bytes", p133._ORIGINAL_ARTIFACT_FREE_BYTES)

    acknowledge_event(config, opened["event_id"], now=clock.now)
    event_path = config.outbox_dir / f"{opened['event_id']}.json"
    full_opened_event = _load_event(event_path)
    event = _load_event(event_path)
    event["sequence"] = 99
    event_path.write_text(json.dumps(event, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(P133DeadmanError, match="event_hash_invalid"):
        runtime.enforce_retention()

    event_path.unlink()
    event_path.symlink_to(config.cursor_path)
    with pytest.raises(P133DeadmanError, match="event_not_regular"):
        runtime.enforce_retention()

    event_path.unlink()
    original = dict(full_opened_event)
    original["event_hash"] = stable_hash({key: value for key, value in original.items() if key != "event_hash"})
    _write_json(event_path, original)
    hardlink = config.outbox_dir / ("f" * 64 + ".json")
    hardlink.hardlink_to(event_path)
    with pytest.raises(P133DeadmanError, match="event_has_multiple_links"):
        runtime.enforce_retention()
    hardlink.unlink()

    foreign = dict(original)
    foreign["config_hash"] = "f" * 64
    foreign["event_hash"] = stable_hash({key: value for key, value in foreign.items() if key != "event_hash"})
    _write_json(event_path, foreign)
    with pytest.raises(P133DeadmanError, match="event_config_mismatch"):
        runtime.enforce_retention()


def test_persisted_artifacts_reject_hash_valid_unknown_fields(tmp_path: Path) -> None:
    config = load_deadman_config(_config_path(tmp_path))
    clock = FakeClock()
    runtime = DeadmanOutbox(
        config,
        now=clock.now,
        watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("runtime_stopped"),
    )
    opened = runtime.check_once()
    event_path = config.outbox_dir / f"{opened['event_id']}.json"
    event = _load_event(event_path)
    event["snapshot"]["raw_path"] = "/private/secret"
    event["snapshot"]["snapshot_fingerprint"] = p133._snapshot_fingerprint(event["snapshot"])
    event["event_hash"] = stable_hash({key: value for key, value in event.items() if key != "event_hash"})
    _write_json(event_path, event)
    with pytest.raises(P133DeadmanError, match="invalid_snapshot_fields"):
        list_outbox(config)

    event["snapshot"].pop("raw_path")
    event["snapshot"]["snapshot_fingerprint"] = p133._snapshot_fingerprint(event["snapshot"])
    event["event_hash"] = stable_hash({key: value for key, value in event.items() if key != "event_hash"})
    _write_json(event_path, event)
    cursor = json.loads(config.cursor_path.read_text(encoding="utf-8"))
    cursor["raw_exception"] = "credential leaked"
    cursor["cursor_hash"] = stable_hash({key: value for key, value in cursor.items() if key != "cursor_hash"})
    _write_json(config.cursor_path, cursor)
    with pytest.raises(P133DeadmanError, match="invalid_cursor_fields"):
        runtime.check_once()


def test_bounded_run_uses_injected_sleep_and_forever_requires_external_stop(tmp_path: Path) -> None:
    config = load_deadman_config(_config_path(tmp_path))
    clock = FakeClock()
    runtime = DeadmanOutbox(config, now=clock.now, sleep=clock.sleep, watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("heartbeat_current"))
    report = runtime.run(max_cycles=3)
    assert report["cycles"] == 3
    assert report["emitted_events"] == 0
    assert clock.sleeps == [30, 30]
    with pytest.raises(P133DeadmanError, match="run_requires_forever_or_max_cycles"):
        runtime.run()
    with pytest.raises(P133DeadmanError, match="max_cycles_must_be_positive"):
        runtime.run(max_cycles=0)

    stop_reasons = iter((None, "sigterm"))
    stopped = runtime.run(
        forever=True,
        stop_reason=lambda: next(stop_reasons),
        wait_for_stop=lambda _timeout: True,
    )
    assert stopped["cycles"] == 1
    assert stopped["stop_reason"] == "sigterm"


def test_reminder_boundary_uses_one_check_timestamp(tmp_path: Path) -> None:
    config = load_deadman_config(_config_path(tmp_path))
    clock = FakeClock()
    runtime = DeadmanOutbox(
        config,
        now=clock.now,
        sleep=clock.sleep,
        watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("runtime_stopped"),
    )
    runtime.check_once()
    clock.current += timedelta(seconds=299)
    calls = 0

    def advancing_now() -> datetime:
        nonlocal calls
        value = clock.current + timedelta(seconds=calls)
        calls += 1
        return value

    runtime = DeadmanOutbox(
        config,
        now=advancing_now,
        sleep=clock.sleep,
        watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("runtime_stopped"),
    )
    result = runtime.check_once()
    assert result["transition_kind"] == "deduplicated"
    assert calls == 1


def test_ack_and_runtime_reject_invalid_time_and_sequence_regression(tmp_path: Path) -> None:
    config = load_deadman_config(_config_path(tmp_path))
    clock = FakeClock()
    runtime = DeadmanOutbox(config, now=clock.now, sleep=clock.sleep, watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("runtime_stopped"))
    opened = runtime.check_once()
    cursor = json.loads(config.cursor_path.read_text(encoding="utf-8"))
    cursor["next_sequence"] = 1
    cursor["cursor_hash"] = stable_hash({key: value for key, value in cursor.items() if key != "cursor_hash"})
    _write_json(config.cursor_path, cursor)
    with pytest.raises(P133DeadmanError, match="cursor_sequence_regression"):
        runtime.check_once()
    with pytest.raises(P133DeadmanError, match="event_id_must_be_sha256"):
        acknowledge_event(config, "not-an-id", now=clock.now)
    with pytest.raises(P133DeadmanError, match="timestamp_must_be_utc"):
        acknowledge_event(config, opened["event_id"], now=lambda: datetime(2026, 7, 13))


def test_pre_replace_failure_preserves_prior_cursor_and_event_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = load_deadman_config(_config_path(tmp_path))
    clock = FakeClock()
    runtime = DeadmanOutbox(config, now=clock.now, sleep=clock.sleep, watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("runtime_stopped"))
    opened = runtime.check_once()
    event_path = config.outbox_dir / f"{opened['event_id']}.json"
    event_before = event_path.read_bytes()
    cursor_before = config.cursor_path.read_bytes()

    original_replace = p133.os.replace

    def fail_replace(*_args: object, **_kwargs: object) -> None:
        raise OSError(errno.ENOSPC, "replace failed")

    monkeypatch.setattr(p133.os, "replace", fail_replace)
    clock.current += timedelta(seconds=1)
    runtime = DeadmanOutbox(config, now=clock.now, sleep=clock.sleep, watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("heartbeat_stale", state_hash="sha256:" + "9" * 64))
    with pytest.raises(OSError, match="replace failed"):
        runtime.check_once()
    monkeypatch.setattr(p133.os, "replace", original_replace)
    assert event_path.read_bytes() == event_before
    assert config.cursor_path.read_bytes() == cursor_before


def test_post_replace_directory_sync_uncertainty_reloads_and_rewrites(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = load_deadman_config(_config_path(tmp_path))
    clock = FakeClock()
    original_fsync_dir = p133._fsync_dir
    calls = 0

    def fail_first_directory_sync(path: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError(errno.EIO, "directory sync failed")
        original_fsync_dir(path)

    monkeypatch.setattr(p133, "_fsync_dir", fail_first_directory_sync)
    runtime = DeadmanOutbox(
        config,
        now=clock.now,
        watchdog_evaluator=lambda *_args, **_kwargs: _watchdog("runtime_stopped"),
    )
    with pytest.raises(P133DurabilityUncertainError, match="directory_fsync_failed_after_replace"):
        runtime.check_once()
    assert len(list_outbox(config)) == 1
    assert not config.cursor_path.exists()

    monkeypatch.setattr(p133, "_fsync_dir", original_fsync_dir)
    clock.current += timedelta(seconds=1)
    recovered = runtime.check_once()
    assert recovered["transition_kind"] == "opened"
    assert len(list_outbox(config)) == 1
    assert config.cursor_path.exists()


def test_cli_deadman_check_list_ack_and_closed_run_flags(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config_path = _config_path(tmp_path)

    assert monitor_cli_main(["deadman-check", "--config", str(config_path)]) == 1
    check_result = json.loads(capsys.readouterr().out)
    assert check_result["reason"] == "state_missing"
    assert check_result["healthy"] is False
    event_id = check_result["event_id"]

    assert monitor_cli_main(["outbox-list", "--config", str(config_path)]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed["count"] == 1
    assert listed["events"][0]["event_id"] == event_id
    assert "snapshot" not in listed["events"][0]

    assert monitor_cli_main(["outbox-ack", "--config", str(config_path), "--event-id", event_id]) == 0
    acknowledged = json.loads(capsys.readouterr().out)
    assert acknowledged["event_id"] == event_id

    assert monitor_cli_main(["deadman-run", "--config", str(config_path), "--max-cycles", "2", "--no-sleep"]) == 0
    run_report = json.loads(capsys.readouterr().out)
    assert run_report["cycles"] == 2

    assert monitor_cli_main(["deadman-run", "--config", str(config_path), "--forever", "--no-sleep"]) == 2
    assert "--no-sleep requires --max-cycles" in capsys.readouterr().err
