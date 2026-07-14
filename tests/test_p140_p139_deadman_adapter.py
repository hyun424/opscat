from __future__ import annotations

import fcntl
import json
import signal
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p121_signals import zero_authority_counters
from app.services.p133_deadman_outbox import EVENT_SCHEMA_VERSION, P133DeadmanError, load_deadman_config
from app.services.p139_local_triage_service import (
    run_local_triage_service_for_evaluation,
    zero_forbidden_authority,
)
from app.services.p140_p139_deadman_adapter import (
    P140AdapterError,
    P140StopController,
    check_p139_deadman_once,
    load_p140_config,
    run_p139_deadman_adapter,
)
from tests.fixtures.p140.builders import P140Fixture, build_p140_fixture


def _run_p139(fixture: P140Fixture) -> dict[str, object]:
    return run_local_triage_service_for_evaluation(
        base_path=fixture.p139.root,
        bundle=fixture.p139.bundle,
        now_values=("2026-07-13T00:10:04Z", "2026-07-13T00:10:05Z"),
        monotonic=lambda: 1.0,
        sleep=lambda _: None,
    )


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def _events(fixture: P140Fixture) -> list[dict[str, object]]:
    return sorted(
        (_json(path) for path in (fixture.data_root / "outbox").glob("*.json")),
        key=_event_sequence,
    )


def _event_sequence(event: dict[str, object]) -> int:
    sequence = event["sequence"]
    assert isinstance(sequence, int)
    return sequence


def _p139_path(fixture: P140Fixture, bundle_key: str) -> Path:
    return fixture.p139.root / fixture.p139.bundle[bundle_key]


def _p138_path(fixture: P140Fixture, config_key: str) -> Path:
    return fixture.p139.root / fixture.p139.bundle["p138_config"][config_key]


def _mark_ready_without_service_lease(fixture: P140Fixture) -> None:
    readiness_path = _p138_path(fixture, "readiness_path")
    heartbeat_path = _p138_path(fixture, "heartbeat_path")
    readiness = _json(readiness_path)
    heartbeat = _json(heartbeat_path)
    readiness.update({"status": "ready", "reason": "running"})
    readiness["readiness_hash"] = stable_hash({key: value for key, value in readiness.items() if key != "readiness_hash"})
    heartbeat["readiness_state"] = "ready"
    heartbeat["heartbeat_hash"] = stable_hash({key: value for key, value in heartbeat.items() if key != "heartbeat_hash"})
    _write_json(readiness_path, readiness)
    _write_json(heartbeat_path, heartbeat)


def _assert_redacted_state_invalid(fixture: P140Fixture, result: dict[str, object]) -> None:
    event = _events(fixture)[0]
    encoded = json.dumps(event, sort_keys=True)
    assert result["reason"] == "state_invalid"
    assert event["snapshot"]["state_hash"] is not None  # type: ignore[index]
    assert "receipt" not in encoded.lower()
    assert "termination" not in encoded.lower()
    assert "ledger" not in encoded.lower()
    assert result["p139_forbidden_authority"] == zero_forbidden_authority()


def test_config_round_trip_binds_p133_and_p139(tmp_path: Path) -> None:
    fixture = build_p140_fixture(tmp_path)
    loaded = load_p140_config(fixture.p140_config_path)
    assert loaded.config_hash == fixture.config.config_hash
    assert load_deadman_config(loaded.p133_config_path).state_path == loaded.p139_bundle_path


def test_config_rejects_unknown_secret_symlink_and_binding_drift(tmp_path: Path) -> None:
    fixture = build_p140_fixture(tmp_path)
    raw = _json(fixture.p140_config_path)
    raw["unknown"] = True
    _write_json(fixture.p140_config_path, raw)
    with pytest.raises(P140AdapterError, match="invalid_config_fields"):
        load_p140_config(fixture.p140_config_path)

    fixture = build_p140_fixture(tmp_path / "forbidden-case")
    raw = _json(fixture.p140_config_path)
    raw["adapter_id"] = "token-secret"
    raw["config_hash"] = stable_hash({key: value for key, value in raw.items() if key != "config_hash"})
    _write_json(fixture.p140_config_path, raw)
    with pytest.raises(P140AdapterError, match="forbidden_config_text"):
        load_p140_config(fixture.p140_config_path)

    fixture = build_p140_fixture(tmp_path / "binding")
    p133 = _json(fixture.p133_config_path)
    p133["runtime_ref"] = "p139:wrong"
    _write_json(fixture.p133_config_path, p133)
    with pytest.raises(P140AdapterError, match="p133_p139_binding_invalid"):
        load_p140_config(fixture.p140_config_path)

    fixture = build_p140_fixture(tmp_path / "symlink")
    target = fixture.root / "target.json"
    target.write_text(fixture.p139_bundle_path.read_text(encoding="utf-8"), encoding="utf-8")
    fixture.p139_bundle_path.unlink()
    fixture.p139_bundle_path.symlink_to(target)
    with pytest.raises(P140AdapterError, match="symlink_path_rejected"):
        load_p140_config(fixture.p140_config_path)


def test_missing_state_opens_exact_p133_event(tmp_path: Path) -> None:
    fixture = build_p140_fixture(tmp_path)
    result = check_p139_deadman_once(fixture.config, now=datetime(2026, 7, 13, 0, 10, 4, tzinfo=UTC))
    assert result["transition_kind"] == "opened"
    assert result["reason"] == "state_missing"
    event = _events(fixture)[0]
    assert event["schema_version"] == EVENT_SCHEMA_VERSION
    assert event["snapshot"]["reason"] == "state_missing"  # type: ignore[index]
    assert event["authority_counters"] == zero_authority_counters()
    assert result["p139_forbidden_authority"] == zero_forbidden_authority()
    assert result["resource_usage"]["peak_memory_bytes"] <= result["resource_usage"]["peak_memory_limit_bytes"]


def test_clean_stop_opens_runtime_stopped_and_observed_time_deduplicates(tmp_path: Path) -> None:
    fixture = build_p140_fixture(tmp_path)
    _run_p139(fixture)
    first = check_p139_deadman_once(fixture.config, now=datetime(2026, 7, 13, 0, 10, 5, tzinfo=UTC))
    second = check_p139_deadman_once(fixture.config, now=datetime(2026, 7, 13, 0, 10, 6, tzinfo=UTC))
    assert first["transition_kind"] == "opened"
    assert first["reason"] == "runtime_stopped"
    assert second["transition_kind"] == "deduplicated"
    assert len(_events(fixture)) == 1


def test_stale_readiness_opens_heartbeat_stale(tmp_path: Path) -> None:
    fixture = build_p140_fixture(tmp_path)
    _run_p139(fixture)
    heartbeat_path = _p138_path(fixture, "heartbeat_path")
    heartbeat = _json(heartbeat_path)
    heartbeat["written_at"] = "2026-07-13T00:11:59Z"
    heartbeat["heartbeat_hash"] = stable_hash({key: value for key, value in heartbeat.items() if key != "heartbeat_hash"})
    _write_json(heartbeat_path, heartbeat)
    result = check_p139_deadman_once(fixture.config, now=datetime(2026, 7, 13, 0, 12, 0, tzinfo=UTC))
    assert result["reason"] == "heartbeat_stale"
    assert _events(fixture)[0]["snapshot"]["reason"] == "heartbeat_stale"  # type: ignore[index]


def test_stale_heartbeat_opens_heartbeat_stale(tmp_path: Path) -> None:
    fixture = build_p140_fixture(tmp_path)
    _run_p139(fixture)
    readiness_path = _p138_path(fixture, "readiness_path")
    readiness = _json(readiness_path)
    readiness["written_at"] = "2026-07-13T00:11:59Z"
    readiness["readiness_hash"] = stable_hash({key: value for key, value in readiness.items() if key != "readiness_hash"})
    _write_json(readiness_path, readiness)
    result = check_p139_deadman_once(fixture.config, now=datetime(2026, 7, 13, 0, 12, 0, tzinfo=UTC))
    assert result["reason"] == "heartbeat_stale"
    assert _events(fixture)[0]["snapshot"]["heartbeat_age_seconds"] is None  # type: ignore[index]


def test_ready_requires_held_service_lease_and_recovers_once(tmp_path: Path) -> None:
    fixture = build_p140_fixture(tmp_path)
    _run_p139(fixture)
    opened = check_p139_deadman_once(fixture.config, now=datetime(2026, 7, 13, 0, 10, 5, tzinfo=UTC))
    _mark_ready_without_service_lease(fixture)
    free = check_p139_deadman_once(fixture.config, now=datetime(2026, 7, 13, 0, 10, 6, tzinfo=UTC))
    assert free["reason"] == "runtime_stopped"
    lease_path = _p139_path(fixture, "service_lease_path")
    with lease_path.open("a+", encoding="utf-8") as lease:
        fcntl.flock(lease.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        recovered = check_p139_deadman_once(fixture.config, now=datetime(2026, 7, 13, 0, 10, 7, tzinfo=UTC))
    assert opened["incident_id"] == recovered["incident_id"]
    assert recovered["transition_kind"] == "recovered"


def test_tampered_receipt_maps_to_redacted_state_invalid(tmp_path: Path) -> None:
    fixture = build_p140_fixture(tmp_path)
    _run_p139(fixture)
    receipt_path = _p139_path(fixture, "exit_receipt_path")
    receipt = _json(receipt_path)
    receipt["receipt_hash"] = "sha256:" + "0" * 64
    _write_json(receipt_path, receipt)
    result = check_p139_deadman_once(fixture.config, now=datetime(2026, 7, 13, 0, 10, 5, tzinfo=UTC))
    _assert_redacted_state_invalid(fixture, result)


def test_tampered_termination_maps_to_redacted_state_invalid(tmp_path: Path) -> None:
    fixture = build_p140_fixture(tmp_path)
    service_result = _run_p139(fixture)
    termination_hash = str(service_result["exit_receipt"]["p138_termination_hash"])  # type: ignore[index]
    termination_path = _p138_path(fixture, "termination_dir") / f"{termination_hash.removeprefix('sha256:')}.json"
    termination = _json(termination_path)
    termination["safe_boundary"] = "during_supervisor_cycle"
    termination["termination_hash"] = stable_hash({key: value for key, value in termination.items() if key != "termination_hash"})
    _write_json(termination_path, termination)
    result = check_p139_deadman_once(fixture.config, now=datetime(2026, 7, 13, 0, 10, 5, tzinfo=UTC))
    _assert_redacted_state_invalid(fixture, result)


def test_forked_exit_history_maps_to_redacted_state_invalid(tmp_path: Path) -> None:
    fixture = build_p140_fixture(tmp_path)
    _run_p139(fixture)
    _run_p139(fixture)
    receipt_path = _p139_path(fixture, "exit_receipt_path")
    current = _json(receipt_path)
    history_path = _p139_path(fixture, "exit_history_dir") / f"{str(current['receipt_hash']).removeprefix('sha256:')}.json"
    forked = dict(current)
    cycles_completed = forked["cycles_completed"]
    assert isinstance(cycles_completed, int)
    forked["cycles_completed"] = cycles_completed + 1
    forked["receipt_hash"] = stable_hash({key: value for key, value in forked.items() if key != "receipt_hash"})
    _write_json(history_path, forked)
    result = check_p139_deadman_once(fixture.config, now=datetime(2026, 7, 13, 0, 10, 5, tzinfo=UTC))
    _assert_redacted_state_invalid(fixture, result)


def test_ledger_mismatch_maps_to_redacted_state_invalid(tmp_path: Path) -> None:
    fixture = build_p140_fixture(tmp_path)
    _run_p139(fixture)
    readiness_path = _p138_path(fixture, "readiness_path")
    readiness = _json(readiness_path)
    readiness["last_valid_ledger_hash"] = "sha256:" + "0" * 64
    readiness["readiness_hash"] = stable_hash({key: value for key, value in readiness.items() if key != "readiness_hash"})
    _write_json(readiness_path, readiness)
    result = check_p139_deadman_once(fixture.config, now=datetime(2026, 7, 13, 0, 10, 5, tzinfo=UTC))
    _assert_redacted_state_invalid(fixture, result)


def test_future_control_records_do_not_create_false_recovery(tmp_path: Path) -> None:
    fixture = build_p140_fixture(tmp_path)
    _run_p139(fixture)
    opened = check_p139_deadman_once(fixture.config, now=datetime(2026, 7, 13, 0, 10, 5, tzinfo=UTC))
    _mark_ready_without_service_lease(fixture)
    for path, hash_key in (
        (_p138_path(fixture, "readiness_path"), "readiness_hash"),
        (_p138_path(fixture, "heartbeat_path"), "heartbeat_hash"),
    ):
        record = _json(path)
        record["written_at"] = "2026-07-13T00:10:59Z"
        record[hash_key] = stable_hash({key: value for key, value in record.items() if key != hash_key})
        _write_json(path, record)
    lease_path = _p139_path(fixture, "service_lease_path")
    with lease_path.open("a+", encoding="utf-8") as lease:
        fcntl.flock(lease.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        future = check_p139_deadman_once(fixture.config, now=datetime(2026, 7, 13, 0, 10, 6, tzinfo=UTC))
    assert opened["incident_id"] == future["incident_id"]
    assert future["transition_kind"] == "updated"
    assert future["reason"] == "state_invalid"
    assert len(_events(fixture)) == 2


def test_first_open_unclean_stop_records_runtime_stopped(tmp_path: Path) -> None:
    fixture = build_p140_fixture(tmp_path)
    _run_p139(fixture)
    _mark_ready_without_service_lease(fixture)
    result = check_p139_deadman_once(fixture.config, now=datetime(2026, 7, 13, 0, 10, 5, tzinfo=UTC))
    assert result["transition_kind"] == "opened"
    assert result["reason"] == "runtime_stopped"
    assert _events(fixture)[0]["snapshot"]["healthy"] is False  # type: ignore[index]


def test_stale_replay_deduplicates_existing_incident(tmp_path: Path) -> None:
    fixture = build_p140_fixture(tmp_path)
    _run_p139(fixture)
    opened = check_p139_deadman_once(fixture.config, now=datetime(2026, 7, 13, 0, 12, 0, tzinfo=UTC))
    replayed = check_p139_deadman_once(fixture.config, now=datetime(2026, 7, 13, 0, 12, 1, tzinfo=UTC))
    assert opened["reason"] == "heartbeat_stale"
    assert replayed["transition_kind"] == "deduplicated"
    assert len(_events(fixture)) == 1


def test_unhealthy_reason_change_emits_one_linked_update(tmp_path: Path) -> None:
    fixture = build_p140_fixture(tmp_path)
    _run_p139(fixture)
    opened = check_p139_deadman_once(fixture.config, now=datetime(2026, 7, 13, 0, 12, 0, tzinfo=UTC))
    for path, hash_key in (
        (_p138_path(fixture, "readiness_path"), "readiness_hash"),
        (_p138_path(fixture, "heartbeat_path"), "heartbeat_hash"),
    ):
        record = _json(path)
        record["written_at"] = "2026-07-13T00:11:59Z"
        record[hash_key] = stable_hash({key: value for key, value in record.items() if key != hash_key})
        _write_json(path, record)
    updated = check_p139_deadman_once(fixture.config, now=datetime(2026, 7, 13, 0, 12, 0, tzinfo=UTC))
    events = _events(fixture)
    assert opened["reason"] == "heartbeat_stale"
    assert updated["reason"] == "state_invalid"
    assert updated["transition_kind"] == "updated"
    assert updated["incident_id"] == opened["incident_id"]
    assert events[1]["previous_event_id"] == events[0]["event_id"]


def test_p139_status_probe_does_not_mutate_p139_tree(tmp_path: Path) -> None:
    fixture = build_p140_fixture(tmp_path)
    _run_p139(fixture)
    _mark_ready_without_service_lease(fixture)
    lease_path = _p139_path(fixture, "service_lease_path")
    with lease_path.open("a+", encoding="utf-8") as lease:
        fcntl.flock(lease.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        before = {path.relative_to(fixture.p139.root).as_posix(): path.read_bytes() for path in fixture.p139.root.rglob("*") if path.is_file()}
        result = check_p139_deadman_once(fixture.config, now=datetime(2026, 7, 13, 0, 10, 6, tzinfo=UTC))
        after = {path.relative_to(fixture.p139.root).as_posix(): path.read_bytes() for path in fixture.p139.root.rglob("*") if path.is_file()}
    assert result["reason"] == "heartbeat_current"
    assert before == after


def test_p139_restart_generation_update_emits_once(tmp_path: Path) -> None:
    fixture = build_p140_fixture(tmp_path)
    _run_p139(fixture)
    opened = check_p139_deadman_once(fixture.config, now=datetime(2026, 7, 13, 0, 10, 5, tzinfo=UTC))
    _run_p139(fixture)
    updated = check_p139_deadman_once(fixture.config, now=datetime(2026, 7, 13, 0, 10, 6, tzinfo=UTC))
    replayed = check_p139_deadman_once(fixture.config, now=datetime(2026, 7, 13, 0, 10, 7, tzinfo=UTC))
    events = _events(fixture)
    assert [opened["transition_kind"], updated["transition_kind"], replayed["transition_kind"]] == [
        "opened",
        "updated",
        "deduplicated",
    ]
    assert [event["transition_kind"] for event in events] == ["opened", "updated"]
    assert updated["incident_id"] == opened["incident_id"]


def test_identical_unhealthy_runtime_stopped_deduplicates(tmp_path: Path) -> None:
    fixture = build_p140_fixture(tmp_path)
    _run_p139(fixture)
    first = check_p139_deadman_once(fixture.config, now=datetime(2026, 7, 13, 0, 10, 5, tzinfo=UTC))
    second = check_p139_deadman_once(fixture.config, now=datetime(2026, 7, 13, 0, 10, 6, tzinfo=UTC))
    third = check_p139_deadman_once(fixture.config, now=datetime(2026, 7, 13, 0, 10, 7, tzinfo=UTC))
    assert [first["transition_kind"], second["transition_kind"], third["transition_kind"]] == [
        "opened",
        "deduplicated",
        "deduplicated",
    ]
    assert len(_events(fixture)) == 1


def test_adapter_and_p133_lease_contention_fail_before_partial_state(tmp_path: Path) -> None:
    fixture = build_p140_fixture(tmp_path)
    with fixture.config.adapter_lease_path.open("a+", encoding="utf-8") as lease:
        fcntl.flock(lease.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(P140AdapterError, match="adapter_lease_unavailable"):
            check_p139_deadman_once(fixture.config, now=datetime(2026, 7, 13, tzinfo=UTC))
    assert not (fixture.data_root / "cursor.json").exists()

    p133 = load_deadman_config(fixture.p133_config_path)
    p133.lease_path.parent.mkdir(parents=True, exist_ok=True)
    with p133.lease_path.open("a+", encoding="utf-8") as lease:
        fcntl.flock(lease.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(P133DeadmanError, match="deadman_lease_unavailable"):
            check_p139_deadman_once(fixture.config, now=datetime(2026, 7, 13, tzinfo=UTC))
    assert not (fixture.data_root / "cursor.json").exists()


def test_p133_write_paths_outside_p140_roots_rejected_before_writes(tmp_path: Path) -> None:
    fixture = build_p140_fixture(tmp_path)
    outside = (tmp_path / "outside-p140-roots").resolve()
    outside.mkdir()
    raw = _json(fixture.p133_config_path)
    roots = raw["allowed_artifact_roots"]
    assert isinstance(roots, list)
    roots.append(str(outside))
    raw["outbox_dir"] = str(outside / "outbox")
    raw["cursor_path"] = str(outside / "cursor.json")
    raw["ack_dir"] = str(outside / "acks")
    _write_json(fixture.p133_config_path, raw)
    with pytest.raises(P140AdapterError, match="path_outside_allowed_roots|p133_p140_path_scope_invalid"):
        load_p140_config(fixture.p140_config_path)
    assert not (outside / "outbox").exists()
    assert not (outside / "cursor.json").exists()
    assert not (outside / "acks").exists()


def test_nested_p133_write_path_under_p139_base_is_rejected(tmp_path: Path) -> None:
    fixture = build_p140_fixture(tmp_path)
    raw = _json(fixture.p133_config_path)
    roots = raw["allowed_artifact_roots"]
    assert isinstance(roots, list)
    roots.append(str(fixture.p139.root))
    raw["outbox_dir"] = str(fixture.p139.root / "unsafe-outbox")
    _write_json(fixture.p133_config_path, raw)
    with pytest.raises(P140AdapterError, match="path_topology_overlap"):
        load_p140_config(fixture.p140_config_path)


@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM])
def test_signal_requested_before_run_stops_without_check(tmp_path: Path, signum: int) -> None:
    fixture = build_p140_fixture(tmp_path)
    controller = P140StopController()
    controller.handle_signal(signum, None)
    result = run_p139_deadman_adapter(fixture.config, forever=True, stop_controller=controller, sleep=lambda _: None)
    assert result["cycles"] == 0
    assert result["graceful_stop"] is True
    assert result["stop_reason"] in {"sigint", "sigterm"}
    assert not _events(fixture)
