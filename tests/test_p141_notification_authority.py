from __future__ import annotations

import fcntl
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import app.services.p141_notification_authority as p141
from app.services.p110_evaluation import stable_hash
from app.services.p121_signals import zero_authority_counters as p121_zero_authority
from app.services.p133_deadman_outbox import DeadmanOutbox, load_deadman_config
from app.services.p141_notification_authority import (
    FORBIDDEN_AUTHORITY_COUNTER_KEYS,
    NotificationAuthorityError,
    list_notification_envelopes,
    list_simulated_receipts,
    load_notification_config,
    process_pending_notifications,
    zero_notification_authority_counters,
)
from tests.fixtures.p141.builders import build_p141_fixture, write_json

NOW = datetime(2026, 7, 14, 1, 0, tzinfo=UTC)


def test_config_round_trip_is_closed_local_and_destination_only(tmp_path: Path) -> None:
    fixture = build_p141_fixture(tmp_path)
    config = fixture.config
    assert config.schema_version == "p141.notification_config.v1"
    assert config.destination_ids == ("primary-operator", "backup-operator")
    assert config.config_hash.startswith("sha256:")

    raw = json.loads(fixture.config_path.read_text(encoding="utf-8"))
    raw["webhook_url"] = "https://example.invalid"
    write_json(fixture.config_path, raw)
    with pytest.raises(NotificationAuthorityError, match="forbidden_configuration_field"):
        load_notification_config(fixture.config_path)

    with pytest.raises(NotificationAuthorityError, match="unsafe_destination_id|forbidden_configuration_value"):
        build_p141_fixture(tmp_path / "url", destination_ids=["https://example.invalid/hook"])

    with pytest.raises(NotificationAuthorityError, match="unsafe_destination_id"):
        build_p141_fixture(tmp_path / "label", destination_ids=["slack-primary"])

    outside = build_p141_fixture(tmp_path / "outside")
    outside_raw = json.loads(outside.config_path.read_text(encoding="utf-8"))
    outside_raw["envelope_dir"] = str(tmp_path.parent / "outside-envelopes")
    write_json(outside.config_path, outside_raw)
    with pytest.raises(NotificationAuthorityError, match="path_outside_allowed_roots"):
        load_notification_config(outside.config_path)

    hardlink = build_p141_fixture(tmp_path / "hardlink")
    os.link(hardlink.config_path, hardlink.config_path.with_name("p141-copy.json"))
    with pytest.raises(NotificationAuthorityError, match="configuration_has_multiple_links"):
        load_notification_config(hardlink.config_path)


def test_one_event_creates_deterministic_envelopes_and_simulated_receipts_without_ack(tmp_path: Path) -> None:
    fixture = build_p141_fixture(tmp_path)
    ack_dir = fixture.p133_data / "acks"
    before_ack = sorted(ack_dir.glob("*")) if ack_dir.exists() else []

    result = process_pending_notifications(fixture.config, now=NOW)

    assert result["processed_event_count"] == 1
    assert result["simulated_attempt_count"] == 2
    assert result["delivered_count"] == 0
    assert result["acknowledged_count"] == 0
    assert result["authority_counters"] == zero_notification_authority_counters()
    assert all(value == 0 for value in result["authority_counters"].values())
    assert set(result["authority_counters"]) == set(FORBIDDEN_AUTHORITY_COUNTER_KEYS)
    assert (sorted(ack_dir.glob("*")) if ack_dir.exists() else []) == before_ack

    envelopes = list_notification_envelopes(fixture.config)
    receipts = list_simulated_receipts(fixture.config)
    assert len(envelopes) == len(receipts) == 2
    for envelope, receipt in zip(envelopes, receipts, strict=True):
        assert envelope["source_event"]["transition_kind"] == "opened"
        assert envelope["source_event"]["reason"] == "runtime_stopped"
        assert set(envelope["source_event"]) == {
            "event_id",
            "event_hash",
            "incident_id",
            "sequence",
            "transition_kind",
            "occurred_at",
            "reason",
            "healthy",
            "state_hash",
            "snapshot_fingerprint",
        }
        assert receipt["simulated"] is True
        assert receipt["delivered"] is False
        assert receipt["acknowledged"] is False
        assert receipt["authority_counters"] == zero_notification_authority_counters()


def test_replay_is_byte_identical_and_does_not_advance_attempt_counts(tmp_path: Path) -> None:
    fixture = build_p141_fixture(tmp_path)
    first = process_pending_notifications(fixture.config, now=NOW)
    before = {path: path.read_bytes() for path in fixture.p141_data.rglob("*.json")}

    replay = process_pending_notifications(fixture.config, now=NOW + timedelta(minutes=1))

    assert first["last_sequence"] == replay["last_sequence"] == 1
    assert replay["processed_event_count"] == 0
    assert replay["simulated_attempt_count"] == 0
    assert {path: path.read_bytes() for path in fixture.p141_data.rglob("*.json")} == before


def test_cursor_failure_replays_existing_artifacts_without_duplication(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = build_p141_fixture(tmp_path)
    original = p141._write_cursor
    monkeypatch.setattr(p141, "_write_cursor", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("crash")))
    with pytest.raises(OSError, match="crash"):
        process_pending_notifications(fixture.config, now=NOW)
    assert len(list(fixture.config.envelope_dir.glob("*.json"))) == 2
    assert len(list(fixture.config.receipt_dir.glob("*.json"))) == 2
    assert not fixture.config.cursor_path.exists()

    monkeypatch.setattr(p141, "_write_cursor", original)
    result = process_pending_notifications(fixture.config, now=NOW + timedelta(seconds=1))
    assert result["processed_event_count"] == 1
    assert len(list_notification_envelopes(fixture.config)) == 2
    assert len(list_simulated_receipts(fixture.config)) == 2


def test_tampered_p133_event_and_missing_chain_fail_closed(tmp_path: Path) -> None:
    fixture = build_p141_fixture(tmp_path)
    event_path = next((fixture.p133_data / "outbox").glob("*.json"))
    event = json.loads(event_path.read_text(encoding="utf-8"))
    event["snapshot"]["reason"] = "heartbeat_stale"
    write_json(event_path, event)
    with pytest.raises(Exception, match="event_hash_invalid"):
        process_pending_notifications(fixture.config, now=NOW)


def test_receipt_tamper_symlink_and_budget_exhaustion_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = build_p141_fixture(tmp_path)
    process_pending_notifications(fixture.config, now=NOW)
    receipt_path = next(fixture.config.receipt_dir.glob("*.json"))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["delivered"] = True
    write_json(receipt_path, receipt)
    with pytest.raises(NotificationAuthorityError, match="receipt_hash_invalid|receipt_contract_invalid"):
        list_simulated_receipts(fixture.config)

    budget = build_p141_fixture(
        tmp_path / "budget",
        max_total_bytes=3_000,
        max_envelope_bytes=3_000,
        max_receipt_bytes=3_000,
    )
    with pytest.raises(NotificationAuthorityError, match="artifact_budget_exhausted"):
        process_pending_notifications(budget.config, now=NOW)
    assert not list(budget.config.envelope_dir.glob("*.json"))
    assert not list(budget.config.receipt_dir.glob("*.json"))
    assert not budget.config.cursor_path.exists()

    symlink = build_p141_fixture(tmp_path / "symlink")
    symlink.config.envelope_dir.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(NotificationAuthorityError, match="not_directory|symlink|directory_component_unsafe"):
        process_pending_notifications(symlink.config, now=NOW)

    no_space = build_p141_fixture(tmp_path / "space", min_artifact_free_bytes=10)
    disk_usage_result = type("DiskUsage", (), {"total": 100, "used": 100, "free": 0})()
    monkeypatch.setattr(p141.shutil, "disk_usage", lambda _path: disk_usage_result)
    with pytest.raises(NotificationAuthorityError, match="insufficient_artifact_space"):
        process_pending_notifications(no_space.config, now=NOW)


def test_notification_authority_is_distinct_from_p121_and_source_has_no_external_io(tmp_path: Path) -> None:
    fixture = build_p141_fixture(tmp_path)
    process_pending_notifications(fixture.config, now=NOW)
    source = Path(p141.__file__).read_text(encoding="utf-8")
    forbidden_calls = ("socket.", "requests.", "httpx.", "urllib.", "subprocess.", "os.environ", "getenv(", "acknowledge_event(")
    assert not any(token in source for token in forbidden_calls)
    assert all(value == 0 for value in p121_zero_authority().values())


def test_cursor_cannot_skip_missing_artifact_and_p133_tree_is_byte_immutable(tmp_path: Path) -> None:
    fixture = build_p141_fixture(tmp_path)
    before = {
        path.relative_to(fixture.p133_data): path.read_bytes()
        for path in fixture.p133_data.rglob("*")
        if path.is_file() and not path.name.endswith(".lock")
    }
    process_pending_notifications(fixture.config, now=NOW)
    after = {
        path.relative_to(fixture.p133_data): path.read_bytes()
        for path in fixture.p133_data.rglob("*")
        if path.is_file() and not path.name.endswith(".lock")
    }
    assert after == before

    next(fixture.config.receipt_dir.glob("*.json")).unlink()
    with pytest.raises(NotificationAuthorityError, match="cursor_artifact_missing"):
        process_pending_notifications(fixture.config, now=NOW + timedelta(seconds=1))


def test_partial_destination_crash_and_receipt_orphan_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = build_p141_fixture(tmp_path)
    original = p141._atomic_write_json
    writes = 0

    def fail_before_second_destination(path: Path, value: object, roots: object) -> None:
        nonlocal writes
        writes += 1
        if writes == 3:
            raise OSError("partial destination crash")
        original(path, value, roots)  # type: ignore[arg-type]

    monkeypatch.setattr(p141, "_atomic_write_json", fail_before_second_destination)
    with pytest.raises(OSError, match="partial destination crash"):
        process_pending_notifications(fixture.config, now=NOW)
    assert not fixture.config.cursor_path.exists()
    assert len(list(fixture.config.envelope_dir.glob("*.json"))) == 1
    assert len(list(fixture.config.receipt_dir.glob("*.json"))) == 1

    monkeypatch.setattr(p141, "_atomic_write_json", original)
    result = process_pending_notifications(fixture.config, now=NOW + timedelta(seconds=1))
    assert result["replayed_attempt_count"] == 1
    assert len(list_notification_envelopes(fixture.config)) == 2

    orphan = build_p141_fixture(tmp_path / "orphan")
    envelope = p141._build_envelope(orphan.config, p141.list_outbox(orphan.config.p133_config)[0], "primary-operator")
    receipt = p141._build_receipt(envelope, p141.list_outbox(orphan.config.p133_config)[0], "primary-operator", NOW)
    orphan.config.receipt_dir.mkdir(parents=True)
    write_json(orphan.config.receipt_dir / f"{receipt['attempt_id']}.json", receipt)
    with pytest.raises(NotificationAuthorityError, match="receipt_without_envelope"):
        process_pending_notifications(orphan.config, now=NOW)


def test_all_p133_transitions_form_one_bound_chain(tmp_path: Path) -> None:
    fixture = build_p141_fixture(tmp_path)
    p133_config = load_deadman_config(fixture.p133_config_path)

    def check(at: datetime, reason: str, state: str) -> None:
        DeadmanOutbox(
            p133_config,
            now=lambda: at,
            watchdog_evaluator=lambda *_args, **_kwargs: {
                "healthy": reason == "heartbeat_current",
                "reason": reason,
                "state_hash": "sha256:" + state * 64,
                "heartbeat_age_seconds": 10,
            },
        ).check_once()

    check(datetime(2026, 7, 14, 0, 1, tzinfo=UTC), "heartbeat_stale", "b")
    check(datetime(2026, 7, 14, 0, 1, 6, tzinfo=UTC), "heartbeat_stale", "b")
    check(datetime(2026, 7, 14, 0, 1, 7, tzinfo=UTC), "heartbeat_current", "c")
    result = process_pending_notifications(fixture.config, now=NOW)
    assert result["processed_event_count"] == 4
    transitions = [item["source_event"]["transition_kind"] for item in list_notification_envelopes(fixture.config)]
    assert set(transitions) == {"opened", "updated", "reminder", "recovered"}


def test_transition_allowlist_and_chain_are_closed(tmp_path: Path) -> None:
    fixture = build_p141_fixture(tmp_path, transition_kinds=["opened"])
    assert process_pending_notifications(fixture.config, now=NOW)["processed_event_count"] == 1

    raw = json.loads(fixture.config_path.read_text(encoding="utf-8"))
    raw["transition_kinds"] = ["opened", "send"]
    write_json(fixture.config_path, raw)
    with pytest.raises(NotificationAuthorityError, match="unsafe_transition_kind"):
        load_notification_config(fixture.config_path)


def test_cross_config_and_cross_event_replay_fail_closed(tmp_path: Path) -> None:
    fixture = build_p141_fixture(tmp_path)
    process_pending_notifications(fixture.config, now=NOW)
    raw = json.loads(fixture.config_path.read_text(encoding="utf-8"))
    raw["template_version"] = "p141-deadman-v2"
    write_json(fixture.config_path, raw)
    changed = load_notification_config(fixture.config_path)
    with pytest.raises(NotificationAuthorityError, match="cursor_config_mismatch"):
        process_pending_notifications(changed, now=NOW + timedelta(seconds=1))

    receipt_paths = sorted(fixture.config.receipt_dir.glob("*.json"))
    left = json.loads(receipt_paths[0].read_text(encoding="utf-8"))
    right = json.loads(receipt_paths[1].read_text(encoding="utf-8"))
    left["event_hash"] = right["envelope_hash"]
    left["receipt_hash"] = stable_hash({key: value for key, value in left.items() if key != "receipt_hash"})
    write_json(receipt_paths[0], left)
    with pytest.raises(NotificationAuthorityError, match="cursor_receipt_binding_invalid"):
        process_pending_notifications(fixture.config, now=NOW + timedelta(seconds=1))


def test_envelope_and_receipt_tamper_fail_closed(tmp_path: Path) -> None:
    fixture = build_p141_fixture(tmp_path)
    process_pending_notifications(fixture.config, now=NOW)
    envelope_path = next(fixture.config.envelope_dir.glob("*.json"))
    envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
    envelope["message"]["summary"] = "forged"
    envelope["envelope_hash"] = stable_hash({key: value for key, value in envelope.items() if key != "envelope_hash"})
    write_json(envelope_path, envelope)
    with pytest.raises(NotificationAuthorityError, match="envelope_contract_invalid"):
        list_notification_envelopes(fixture.config)


def test_notification_lease_conflict_fails_before_writes(tmp_path: Path) -> None:
    fixture = build_p141_fixture(tmp_path)
    fixture.config.lease_path.parent.mkdir(parents=True, exist_ok=True)
    with fixture.config.lease_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(NotificationAuthorityError, match="notification_lease_unavailable"):
            process_pending_notifications(fixture.config, now=NOW)
    assert not fixture.config.envelope_dir.exists()


def test_clock_rollback_fails_closed(tmp_path: Path) -> None:
    fixture = build_p141_fixture(tmp_path)
    process_pending_notifications(fixture.config, now=NOW)
    with pytest.raises(NotificationAuthorityError, match="clock_rollback_exceeds_tolerance"):
        process_pending_notifications(fixture.config, now=NOW - timedelta(minutes=1))


def test_list_rejects_self_consistent_artifacts_not_backed_by_p133(tmp_path: Path) -> None:
    fixture = build_p141_fixture(tmp_path)
    process_pending_notifications(fixture.config, now=NOW)
    envelope_path = next(fixture.config.envelope_dir.glob("*.json"))
    envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
    source = envelope["source_event"]
    source["sequence"] = 999
    source["event_hash"] = "sha256:" + "f" * 64
    envelope["attempt_id"] = stable_hash(
        {
            "config_hash": fixture.config.config_hash,
            "event_hash": source["event_hash"],
            "destination_id": envelope["destination_id"],
            "template_version": fixture.config.template_version,
        }
    )
    envelope["envelope_id"] = stable_hash({"attempt_id": envelope["attempt_id"], "source_event": source})
    envelope["message"]["evidence_refs"][1] = source["event_hash"]
    envelope["envelope_hash"] = stable_hash({key: value for key, value in envelope.items() if key != "envelope_hash"})
    forged_path = fixture.config.envelope_dir / f"{envelope['attempt_id']}.json"
    write_json(forged_path, envelope)
    with pytest.raises(NotificationAuthorityError, match="envelope_not_backed_by_p133"):
        list_notification_envelopes(fixture.config)
