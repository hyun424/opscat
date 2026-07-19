from __future__ import annotations

import io
import json
import socket
import threading
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast

import pytest

import lab.p174.workload.p174_workload as workload_module
from lab.p174.workload.p174_workload import (
    STATE_KEY,
    STATE_LOCK_KEY,
    InMemoryCausalStore,
    RedisCausalStore,
    RuntimeActionService,
    ServiceHandler,
    ValidationError,
)

EXPECTED = {
    "project_id": "p174-project",
    "target_id": "target-a",
    "run_id": "run-1",
    "policy_version": "policy-v1",
    "capability": "p174.actions",
    "fault_capability": "p174.faults",
}


def _action_headers(now: datetime) -> dict[str, str]:
    return {
        "X-P174-Capability": EXPECTED["capability"],
        "X-P174-Lease-Expires": (now + timedelta(seconds=30)).isoformat().replace("+00:00", "Z"),
    }


def _fault_headers(now: datetime) -> dict[str, str]:
    return {
        "X-P174-Fault-Capability": EXPECTED["fault_capability"],
        "X-P174-Lease-Expires": (now + timedelta(seconds=30)).isoformat().replace("+00:00", "Z"),
    }


def _fault_body(fault: str, *, request_id: str = "fault-1", idem: str = "fault-idem-1", parameters: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "schema_version": "p174.faults.v1",
        "request_id": request_id,
        "idempotency_key": idem,
        "project_id": EXPECTED["project_id"],
        "target_id": EXPECTED["target_id"],
        "run_id": EXPECTED["run_id"],
        "fault": fault,
        "parameters": parameters or {},
        "created_at": "2026-07-17T00:00:00Z",
        "evidence_hash": "sha256:" + "f" * 64,
        "policy_version": EXPECTED["policy_version"],
    }


def _action_body(action: str, *, request_id: str = "action-1", idem: str = "action-idem-1", parameters: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "schema_version": "p174.actions.v1",
        "request_id": request_id,
        "idempotency_key": idem,
        "project_id": EXPECTED["project_id"],
        "target_id": EXPECTED["target_id"],
        "run_id": EXPECTED["run_id"],
        "action": action,
        "parameters": parameters or {},
        "created_at": "2026-07-17T00:00:00Z",
        "evidence_hash": "sha256:" + "a" * 64,
        "policy_version": EXPECTED["policy_version"],
    }


def _cleanup_body(
    *,
    token: str,
    request_id: str = "cleanup-1",
    idem: str = "cleanup-idem-1",
    original_request_id: str = "fault-1",
    original_idem: str = "fault-idem-1",
) -> dict[str, object]:
    return {
        "schema_version": "p174.faults.cleanup.v1",
        "request_id": request_id,
        "idempotency_key": idem,
        "project_id": EXPECTED["project_id"],
        "target_id": EXPECTED["target_id"],
        "run_id": EXPECTED["run_id"],
        "original_request_id": original_request_id,
        "original_idempotency_key": original_idem,
        "cleanup_token": token,
        "created_at": "2026-07-17T00:00:00Z",
        "evidence_hash": "sha256:" + "c" * 64,
        "policy_version": EXPECTED["policy_version"],
    }


def _service(now: datetime) -> RuntimeActionService:
    return _bound_service(InMemoryCausalStore(), now)


def _bound_service(
    store: InMemoryCausalStore,
    now: datetime,
    *,
    run_id: str = EXPECTED["run_id"],
) -> RuntimeActionService:
    return RuntimeActionService(
        store,
        project_id=EXPECTED["project_id"],
        target_id=EXPECTED["target_id"],
        run_id=run_id,
        policy_version=EXPECTED["policy_version"],
        capability=EXPECTED["capability"],
        fault_capability=EXPECTED["fault_capability"],
        now=lambda: now,
    )


class _FailFirstCommitStore(InMemoryCausalStore):
    def __init__(self) -> None:
        super().__init__()
        self.fail_next_commit = True

    def commit_mutation(
        self,
        json_values: Mapping[str, Mapping[str, Any]],
        *,
        queue_key: str | None = None,
        append_items: list[Mapping[str, Any]] | None = None,
        remove_items: list[Mapping[str, Any]] | None = None,
        expected_remove_count: int | None = None,
    ) -> int:
        if self.fail_next_commit:
            self.fail_next_commit = False
            raise RuntimeError("injected_commit_failure")
        return super().commit_mutation(
            json_values,
            queue_key=queue_key,
            append_items=append_items,
            remove_items=remove_items,
            expected_remove_count=expected_remove_count,
        )


def test_cleanup_serializes_with_stale_background_writer() -> None:
    now = datetime(2026, 7, 17, tzinfo=UTC)
    store = InMemoryCausalStore()
    service = RuntimeActionService(
        store,
        project_id=EXPECTED["project_id"],
        target_id=EXPECTED["target_id"],
        run_id=EXPECTED["run_id"],
        policy_version=EXPECTED["policy_version"],
        capability=EXPECTED["capability"],
        fault_capability=EXPECTED["fault_capability"],
        now=lambda: now,
    )
    fault = service.submit_fault(_fault_body("canary_regression"), _fault_headers(now))
    cleanup = _cleanup_body(token=str(fault["evidence"]["cleanup_token"]))
    stale_read = threading.Event()
    release_writer = threading.Event()

    def background_writer() -> None:
        with store.state_lock(service.state_lock_key):
            state = store.get_json(service.state_key)
            assert state is not None and state["canary_version"] == "regressed"
            stale_read.set()
            assert release_writer.wait(timeout=2)
            state["loadgen_requests_total"] = int(state["loadgen_requests_total"]) + 1
            store.set_json(service.state_key, state)

    writer = threading.Thread(target=background_writer)
    cleaner = threading.Thread(target=lambda: service.cleanup_fault(cleanup, _fault_headers(now)))
    writer.start()
    assert stale_read.wait(timeout=2)
    cleaner.start()
    assert cleaner.is_alive()
    release_writer.set()
    writer.join(timeout=2)
    cleaner.join(timeout=2)

    assert not writer.is_alive() and not cleaner.is_alive()
    final_state = service.state()["state"]
    assert final_state["canary_version"] == "stable"
    assert final_state["loadgen_requests_total"] == 1
    assert final_state["action_requests_total"] == 1


def test_redis_resp_bulk_read_fails_on_truncated_connection() -> None:
    reader, writer = socket.socketpair()
    try:
        writer.sendall(b"$5\r\nab")
        writer.shutdown(socket.SHUT_WR)
        with pytest.raises(RuntimeError, match="redis_connection_closed"):
            workload_module._read_resp(reader)
    finally:
        reader.close()
        writer.close()


def test_redis_lock_release_failure_always_clears_thread_binding(monkeypatch: pytest.MonkeyPatch) -> None:
    store = RedisCausalStore("redis")
    fail_release = {"value": True}

    def fake_command(*parts: str) -> bytes | int | None:
        if parts[0] == "SET":
            return b"OK"
        if parts[0] == "EVAL" and "redis.call('del'" in parts[1]:
            if fail_release["value"]:
                fail_release["value"] = False
                raise OSError("release disconnected")
            return 1
        return 1

    monkeypatch.setattr(store, "_command", fake_command)
    with pytest.raises(OSError, match="release disconnected"):
        with store.state_lock(STATE_LOCK_KEY):
            pass
    assert store._lock_binding.token is None
    with store.state_lock(STATE_LOCK_KEY):
        pass


def test_redis_stale_holder_cannot_mutate_state(monkeypatch: pytest.MonkeyPatch) -> None:
    store = RedisCausalStore("redis")
    redis_state: dict[str, str | None] = {"lock_token": None, "state": None}

    def guarded_command(*parts: str) -> bytes | int | None:
        if parts[0] == "SET":
            redis_state["lock_token"] = parts[2]
            return b"OK"
        if parts[0] == "EVAL":
            if "redis.call('del'" in parts[1]:
                redis_state["lock_token"] = None
                return 1
            supplied_token = parts[5]
            if supplied_token != redis_state["lock_token"]:
                raise RuntimeError("ERR state_lock_lost")
            redis_state["state"] = parts[6]
            return b"OK"
        raise AssertionError(parts)

    monkeypatch.setattr(store, "_command", guarded_command)
    with store.state_lock(STATE_LOCK_KEY):
        store.set_json(STATE_KEY, {"canary_version": "stable"})
        original_state = redis_state["state"]
        original_token = redis_state["lock_token"]
        redis_state["lock_token"] = "successor-token"
        with pytest.raises(RuntimeError, match="state_lock_lost"):
            store.set_json(STATE_KEY, {"canary_version": "regressed"})
        assert redis_state["state"] == original_state
        redis_state["lock_token"] = original_token


def test_redis_renewal_loss_is_observed_before_release(monkeypatch: pytest.MonkeyPatch) -> None:
    store = RedisCausalStore("redis")
    renewal_seen = threading.Event()

    monkeypatch.setattr(workload_module, "REDIS_STATE_LOCK_RENEW_SECONDS", 0.001)

    def lost_command(*parts: str) -> bytes | int | None:
        if parts[0] == "SET":
            return b"OK"
        if "redis.call('pexpire'" in parts[1]:
            renewal_seen.set()
            return 0
        if "redis.call('del'" in parts[1]:
            return 1
        return 1

    monkeypatch.setattr(store, "_command", lost_command)
    with pytest.raises(RuntimeError, match="redis_state_lock_lost"):
        with store.state_lock(STATE_LOCK_KEY):
            assert renewal_seen.wait(timeout=1)
    assert renewal_seen.is_set()


def test_redis_atomic_commit_indexes_lock_json_and_queue_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    store = RedisCausalStore("redis")
    captured: list[tuple[str, ...]] = []

    def fake_command(*parts: str) -> int:
        captured.append(parts)
        return 0

    monkeypatch.setattr(store, "_command", fake_command)
    store._lock_binding.key = "lock-key"
    store._lock_binding.token = "lock-token"

    store.commit_mutation(
        {"state-key": {"state": 1}, "idem-key": {"receipt": 1}},
        queue_key="queue-key",
        append_items=[{"work_id": "append"}],
    )

    command = captured[0]
    script = command[1]
    assert command[2:7] == ("4", "lock-key", "state-key", "idem-key", "queue-key")
    assert command[7] == "lock-token"
    assert "KEYS[2]" in script and "KEYS[3]" in script
    assert "rpush',KEYS[4],ARGV[4]" in script
    assert script.index("json_key_type_invalid") < script.index("redis.call('set'")
    assert script.index("queue_key_type_invalid") < script.index("redis.call('set'")


def test_redis_remove_precondition_is_before_all_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    store = RedisCausalStore("redis")
    captured: list[tuple[str, ...]] = []

    def fake_command(*parts: str) -> int:
        captured.append(parts)
        return 1

    monkeypatch.setattr(store, "_command", fake_command)
    store._lock_binding.key = "lock-key"
    store._lock_binding.token = "lock-token"

    store.commit_mutation(
        {"state-key": {"state": 1}, "idem-key": {"receipt": 1}},
        queue_key="queue-key",
        remove_items=[{"work_id": "remove"}],
        expected_remove_count=1,
    )

    command = captured[0]
    script = command[1]
    assert command[2:7] == ("4", "lock-key", "state-key", "idem-key", "queue-key")
    assert command[7] == "lock-token"
    assert "lpos',KEYS[4],ARGV[4]" in script
    assert "removable~=1" in script
    assert "lrem',KEYS[4],1,ARGV[4]" in script
    assert script.index("queue_remove_count_mismatch") < script.index("redis.call('set'")


def test_in_memory_commit_preserializes_before_mutating_queue_or_json() -> None:
    store = InMemoryCausalStore()
    store.set_json("state", {"version": "before"})
    store.push_queue("queue", {"work_id": "existing"})

    with pytest.raises(TypeError):
        store.commit_mutation(
            {"state": {"unserializable": object()}},
            queue_key="queue",
            append_items=[{"work_id": "new"}],
        )

    assert store.get_json("state") == {"version": "before"}
    assert store.queue_length("queue") == 1


def test_in_memory_remove_precondition_fails_before_any_mutation() -> None:
    store = InMemoryCausalStore()
    target = {"work_id": "remove"}
    store.set_json("state", {"version": "before"})
    store.push_queue("queue", target)

    with pytest.raises(RuntimeError, match="queue_remove_count_mismatch"):
        store.commit_mutation(
            {"state": {"version": "after"}, "receipt": {"status": "completed"}},
            queue_key="queue",
            remove_items=[target],
            expected_remove_count=2,
        )

    assert store.get_json("state") == {"version": "before"}
    assert store.get_json("receipt") is None
    assert store.queue_length("queue") == 1


class _Headers:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values

    def get(self, key: str, default: str = "") -> str:
        return self.values.get(key, default)


class _PostHarness(ServiceHandler):
    def __init__(self, *, role: str, service: RuntimeActionService, path: str, body: dict[str, object], headers: dict[str, str]) -> None:
        raw = json.dumps(body).encode("utf-8")
        self.server = cast(Any, SimpleNamespace(p174_role=role, p174_service=service))
        self.path = path
        self.headers = cast(Any, _Headers({**headers, "content-length": str(len(raw))}))
        self.rfile = io.BytesIO(raw)
        self.wfile = cast(Any, io.BytesIO())
        self.status: int | None = None
        self.response_headers: dict[str, str] = {}

    def send_response(self, code: int, message: str | None = None) -> None:
        self.status = code

    def send_header(self, keyword: str, value: str) -> None:
        self.response_headers[keyword.lower()] = value

    def end_headers(self) -> None:
        return None


def _dispatch_post(role: str, service: RuntimeActionService, path: str, body: dict[str, object], headers: dict[str, str]) -> tuple[int, dict[str, Any]]:
    handler = _PostHarness(role=role, service=service, path=path, body=body, headers=headers)
    handler.do_POST()
    assert handler.status is not None
    return handler.status, cast(dict[str, Any], json.loads(cast(io.BytesIO, handler.wfile).getvalue().decode("utf-8")))


def test_faults_surface_allows_exact_lab_faults_and_returns_stable_receipts() -> None:
    now = datetime(2026, 7, 17, tzinfo=UTC)
    service = _service(now)

    backlog = service.submit_fault(_fault_body("queue_backlog", parameters={"items": 7}), _fault_headers(now))
    canary = service.submit_fault(_fault_body("canary_regression", request_id="fault-2", idem="fault-idem-2"), _fault_headers(now))
    pause = service.submit_fault(_fault_body("worker_pause", request_id="fault-3", idem="fault-idem-3", parameters={"pause_seconds": 3}), _fault_headers(now))

    assert backlog["action"] == "fault:queue_backlog"
    assert backlog["before_metrics"]["queue_depth"] == 0
    assert backlog["after_metrics"]["queue_depth"] == 7
    assert backlog["evidence"]["fault_receipt_immutable"] is True
    assert backlog["evidence"]["lab_only"] is True
    assert backlog["evidence"]["injected_items"] == 7
    assert canary["action"] == "fault:canary_regression"
    assert canary["state"]["canary_version"] == "regressed"
    assert canary["after_metrics"]["error_rate"] > canary["before_metrics"]["error_rate"]
    assert pause["action"] == "fault:worker_pause"
    assert service.process_worker_job() is False


def test_fault_receipt_replay_is_immutable_and_suppresses_duplicate_effects() -> None:
    now = datetime(2026, 7, 17, tzinfo=UTC)
    service = _service(now)
    body = _fault_body("queue_backlog", parameters={"items": 2})

    first = service.submit_fault(body, _fault_headers(now))
    first["state"]["queue_depth"] = 999
    replay = service.submit_fault(body, _fault_headers(now))

    assert replay["state"]["queue_depth"] == 2
    assert service.state()["metrics"]["queue_depth"] == 2

    changed = dict(body)
    changed["parameters"] = {"items": 3}
    with pytest.raises(ValidationError, match="idempotency_key_payload_mismatch"):
        service.submit_fault(changed, _fault_headers(now))


def test_cross_run_fault_cleanup_cannot_restore_a_prior_snapshot() -> None:
    now = datetime(2026, 7, 17, tzinfo=UTC)
    store = InMemoryCausalStore()
    old = _bound_service(store, now)
    fault = old.submit_fault(_fault_body("queue_backlog", parameters={"items": 2}), _fault_headers(now))
    current = _bound_service(store, now, run_id="run-2")
    cleanup = _cleanup_body(token=str(fault["evidence"]["cleanup_token"]))
    cleanup["run_id"] = "run-2"

    with pytest.raises(ValidationError, match="original_fault_not_found"):
        current.cleanup_fault(cleanup, _fault_headers(now))

    assert old.state()["metrics"]["queue_depth"] == 2
    assert current.state()["metrics"]["queue_depth"] == 0


def test_faults_reject_unknown_faults_fields_bindings_and_unsafe_parameters() -> None:
    now = datetime(2026, 7, 17, tzinfo=UTC)
    service = _service(now)

    with pytest.raises(ValidationError, match="unsupported_fault"):
        service.submit_fault(_fault_body("shell", parameters={}), _fault_headers(now))

    with pytest.raises(ValidationError, match="invalid_fields"):
        service.submit_fault({**_fault_body("queue_backlog"), "url": "http://metadata.google.internal"}, _fault_headers(now))

    for key in ("command", "shell", "url", "docker_socket", "container_name", "process_name", "pid"):
        with pytest.raises(ValidationError, match="forbidden_parameter"):
            service.submit_fault(_fault_body("queue_backlog", request_id=f"fault-{key}", idem=f"idem-{key}", parameters={key: "nope"}), _fault_headers(now))

    with pytest.raises(ValidationError, match="invalid_queue_backlog_parameters"):
        service.submit_fault(_fault_body("queue_backlog", parameters={"items": 1_001}), _fault_headers(now))

    with pytest.raises(ValidationError, match="invalid_canary_regression_parameters"):
        service.submit_fault(_fault_body("canary_regression", parameters={"target": "api"}), _fault_headers(now))

    wrong_target = _fault_body("worker_pause")
    wrong_target["target_id"] = "other-target"
    with pytest.raises(ValidationError, match="target_id_mismatch"):
        service.submit_fault(wrong_target, _fault_headers(now))

    bad_headers = _fault_headers(now)
    bad_headers["X-P174-Fault-Capability"] = "other.capability"
    with pytest.raises(ValidationError, match="capability_mismatch"):
        service.submit_fault(_fault_body("worker_pause"), bad_headers)


def test_faults_reject_action_capability_and_legacy_action_header() -> None:
    now = datetime(2026, 7, 17, tzinfo=UTC)
    service = _service(now)

    with pytest.raises(ValidationError, match="capability_mismatch"):
        service.submit_fault(_fault_body("queue_backlog", parameters={"items": 1}), _action_headers(now))

    assert service.state()["metrics"]["queue_depth"] == 0


def test_rollback_canary_is_measurable_after_canary_regression_fault() -> None:
    now = datetime(2026, 7, 17, tzinfo=UTC)
    service = _service(now)
    for _ in range(5):
        service.enqueue_work()
    fault = service.submit_fault(_fault_body("canary_regression"), _fault_headers(now))

    rollback = service.submit_action(_action_body("rollback_canary", request_id="rollback-canary-1", idem="rollback-canary-idem-1"), _action_headers(now))

    assert fault["after_metrics"]["latency_ms"] > fault["before_metrics"]["latency_ms"]
    assert rollback["before_metrics"]["error_rate"] > rollback["after_metrics"]["error_rate"]
    assert rollback["before_metrics"]["latency_ms"] > rollback["after_metrics"]["latency_ms"]
    assert rollback["state"]["canary_version"] == "stable"


def test_post_faults_is_fault_controller_only() -> None:
    now = datetime(2026, 7, 17, tzinfo=UTC)
    service = _service(now)
    status, payload = _dispatch_post("fault-controller", service, "/faults", _fault_body("queue_backlog", parameters={"items": 4}), _fault_headers(now))

    assert status == 202
    assert payload["action"] == "fault:queue_backlog"
    assert payload["after_metrics"]["queue_depth"] == 4

    action_status, action_payload = _dispatch_post("fault-controller", _service(now), "/faults", _fault_body("queue_backlog"), _action_headers(now))
    assert action_status == 400
    assert action_payload["status"] == "rejected"
    assert action_payload["reason"] == "capability_mismatch"

    api_status, api_payload = _dispatch_post("api", _service(now), "/faults", _fault_body("queue_backlog"), _fault_headers(now))

    assert api_status == 404
    assert api_payload == {"error": "not_found"}


def test_fault_cleanup_uses_server_snapshot_and_preserves_unrelated_queue_work() -> None:
    now = datetime(2026, 7, 17, tzinfo=UTC)
    service = _service(now)
    service.enqueue_work()
    service.enqueue_work()
    fault = service.submit_fault(_fault_body("queue_backlog", parameters={"items": 3}), _fault_headers(now))

    cleanup = service.cleanup_fault(_cleanup_body(token=str(fault["evidence"]["cleanup_token"])), _fault_headers(now))
    state = service.state()

    assert cleanup["action"] == "fault_cleanup"
    assert cleanup["evidence"]["cleanup_mode"] == "server_snapshot_restore"
    assert cleanup["evidence"]["removed_queue_items"] == 3
    assert cleanup["state"]["queue_depth"] == 2
    assert state["state"]["queue_depth"] == 2
    assert service.process_worker_job() is True
    assert service.process_worker_job() is True
    assert service.process_worker_job() is False


def test_post_fault_cleanup_returns_202_and_state_proves_canary_restored() -> None:
    now = datetime(2026, 7, 17, tzinfo=UTC)
    service = _service(now)
    status, fault = _dispatch_post("fault-controller", service, "/faults", _fault_body("canary_regression"), _fault_headers(now))

    cleanup_status, cleanup = _dispatch_post("fault-controller", service, "/faults/cleanup", _cleanup_body(token=str(fault["evidence"]["cleanup_token"])), _fault_headers(now))
    state = service.state()

    assert status == 202
    assert cleanup_status == 202
    assert cleanup["accepted"] is True
    assert cleanup["state"]["canary_version"] == "stable"
    assert state["state"]["canary_version"] == "stable"


def test_fault_cleanup_rejects_client_state_action_capability_and_bad_bindings() -> None:
    now = datetime(2026, 7, 17, tzinfo=UTC)
    service = _service(now)
    fault = service.submit_fault(_fault_body("queue_backlog", parameters={"items": 1}), _fault_headers(now))
    token = str(fault["evidence"]["cleanup_token"])

    with pytest.raises(ValidationError, match="invalid_fields"):
        service.cleanup_fault({**_cleanup_body(token=token), "state": {"queue_depth": 0}}, _fault_headers(now))

    with pytest.raises(ValidationError, match="capability_mismatch"):
        service.cleanup_fault(_cleanup_body(token=token, request_id="cleanup-action-cap", idem="cleanup-action-cap-idem"), _action_headers(now))

    with pytest.raises(ValidationError, match="cleanup_token_mismatch"):
        service.cleanup_fault(_cleanup_body(token="sha256:" + "0" * 64, request_id="cleanup-bad-token", idem="cleanup-bad-token-idem"), _fault_headers(now))

    with pytest.raises(ValidationError, match="original_fault_binding_mismatch"):
        service.cleanup_fault(_cleanup_body(token=token, request_id="cleanup-bad-original", idem="cleanup-bad-original-idem", original_request_id="other-fault"), _fault_headers(now))

    wrong_policy = _cleanup_body(token=token, request_id="cleanup-bad-policy", idem="cleanup-bad-policy-idem")
    wrong_policy["policy_version"] = "other-policy"
    with pytest.raises(ValidationError, match="policy_version_mismatch"):
        service.cleanup_fault(wrong_policy, _fault_headers(now))

    wrong_evidence = _cleanup_body(token=token, request_id="cleanup-bad-evidence", idem="cleanup-bad-evidence-idem")
    wrong_evidence["evidence_hash"] = "not-a-sha"
    with pytest.raises(ValidationError, match="evidence_hash_invalid"):
        service.cleanup_fault(wrong_evidence, _fault_headers(now))


def test_fault_cleanup_is_idempotent_but_token_cannot_be_reused_for_new_cleanup() -> None:
    now = datetime(2026, 7, 17, tzinfo=UTC)
    service = _service(now)
    fault = service.submit_fault(_fault_body("queue_backlog", parameters={"items": 1}), _fault_headers(now))
    body = _cleanup_body(token=str(fault["evidence"]["cleanup_token"]))

    first = service.cleanup_fault(body, _fault_headers(now))
    replay = service.cleanup_fault(body, _fault_headers(now))

    assert replay == first
    with pytest.raises(ValidationError, match="cleanup_token_already_used"):
        service.cleanup_fault(_cleanup_body(token=str(fault["evidence"]["cleanup_token"]), request_id="cleanup-2", idem="cleanup-idem-2"), _fault_headers(now))


def test_fault_effect_receipt_cleanup_record_and_queue_commit_atomically() -> None:
    now = datetime(2026, 7, 17, tzinfo=UTC)
    store = _FailFirstCommitStore()
    service = _bound_service(store, now)
    body = _fault_body("queue_backlog", idem="atomic-fault-idem", parameters={"items": 3})

    with pytest.raises(RuntimeError, match="injected_commit_failure"):
        service.submit_fault(body, _fault_headers(now))

    assert service.state()["metrics"]["queue_depth"] == 0
    assert store.get_json(service.idempotency_prefix + "atomic-fault-idem") is None
    assert store.get_json(service.fault_prefix + "atomic-fault-idem") is None

    fault = service.submit_fault(body, _fault_headers(now))
    assert service.state()["metrics"]["queue_depth"] == 3

    cleanup = service.cleanup_fault(
        _cleanup_body(token=str(fault["evidence"]["cleanup_token"]), original_idem="atomic-fault-idem"),
        _fault_headers(now),
    )

    assert cleanup["evidence"]["removed_queue_items"] == 3
    assert service.state()["metrics"]["queue_depth"] == 0


def test_fault_cleanup_state_token_receipt_and_queue_commit_atomically() -> None:
    now = datetime(2026, 7, 17, tzinfo=UTC)
    store = _FailFirstCommitStore()
    store.fail_next_commit = False
    service = _bound_service(store, now)
    fault = service.submit_fault(
        _fault_body("queue_backlog", idem="cleanup-atomic-fault", parameters={"items": 3}),
        _fault_headers(now),
    )
    cleanup_body = _cleanup_body(
        token=str(fault["evidence"]["cleanup_token"]),
        idem="cleanup-atomic-idem",
        original_idem="cleanup-atomic-fault",
    )
    store.fail_next_commit = True

    with pytest.raises(RuntimeError, match="injected_commit_failure"):
        service.cleanup_fault(cleanup_body, _fault_headers(now))

    failed_record = store.get_json(service.fault_prefix + "cleanup-atomic-fault")
    assert failed_record is not None and failed_record["cleanup_used"] is False
    assert service.state()["metrics"]["queue_depth"] == 3
    assert store.get_json(service.idempotency_prefix + "cleanup-atomic-idem") is None

    cleanup = service.cleanup_fault(cleanup_body, _fault_headers(now))

    assert cleanup["evidence"]["removed_queue_items"] == 3
    assert service.state()["metrics"]["queue_depth"] == 0
    committed_record = store.get_json(service.fault_prefix + "cleanup-atomic-fault")
    assert committed_record is not None and committed_record["cleanup_used"] is True


def test_fault_cleanup_rejects_action_idempotency_as_original() -> None:
    now = datetime(2026, 7, 17, tzinfo=UTC)
    service = _service(now)
    service.submit_action(_action_body("tune_pool", request_id="action-original", idem="action-original-idem", parameters={"pool_size": 7}), _action_headers(now))

    with pytest.raises(ValidationError, match="original_request_not_fault"):
        service.cleanup_fault(
            _cleanup_body(
                token="sha256:" + "1" * 64,
                request_id="cleanup-action-original",
                idem="cleanup-action-original-idem",
                original_request_id="action-original",
                original_idem="action-original-idem",
            ),
            _fault_headers(now),
        )
