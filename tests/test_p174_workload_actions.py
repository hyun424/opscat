from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from lab.p174.workload.p174_workload import InMemoryCausalStore, RuntimeActionService, ValidationError

EXPECTED = {
    "project_id": "p174-project",
    "target_id": "target-a",
    "run_id": "run-1",
    "policy_version": "policy-v1",
    "capability": "p174.actions",
    "fault_capability": "p174.faults",
}


def _headers(now: datetime) -> dict[str, str]:
    return {
        "X-P174-Capability": EXPECTED["capability"],
        "X-P174-Lease-Expires": (now + timedelta(seconds=30)).isoformat().replace("+00:00", "Z"),
    }


def _body(action: str, *, request_id: str = "request-1", idem: str = "idem-1", parameters: dict[str, object] | None = None) -> dict[str, object]:
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


def _service(now: datetime) -> RuntimeActionService:
    return _bound_service(InMemoryCausalStore(), now)


def _bound_service(
    store: InMemoryCausalStore,
    now: datetime,
    *,
    project_id: str = EXPECTED["project_id"],
    target_id: str = EXPECTED["target_id"],
    run_id: str = EXPECTED["run_id"],
) -> RuntimeActionService:
    return RuntimeActionService(
        store,
        project_id=project_id,
        target_id=target_id,
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


def test_shared_causal_queue_and_tune_pool_effects_are_observable() -> None:
    now = datetime(2026, 7, 17, tzinfo=UTC)
    service = _service(now)

    service.enqueue_work()
    service.enqueue_work()
    service.process_worker_job()

    before = service.state()["metrics"]
    assert before["queue_depth"] == 1

    receipt = service.submit_action(_body("tune_pool", parameters={"pool_size": 9}), _headers(now))

    assert receipt["accepted"] is True
    assert receipt["status"] == "completed"
    assert receipt["before_metrics"]["queue_depth"] == 1
    assert receipt["after_metrics"]["pool_size"] == 9
    assert service.state()["metrics"]["pool_size"] == 9
    assert receipt["provider_claimed_success"] is True
    assert receipt["evidence"]["receipt_id"].startswith("p174-receipt-")
    assert service._state()["deadman_expires_at"] == "2026-07-17T00:02:00Z"


def test_authority_bindings_use_isolated_state_queue_and_idempotency_namespaces() -> None:
    now = datetime(2026, 7, 17, tzinfo=UTC)
    store = InMemoryCausalStore()
    old = _bound_service(store, now)
    old.enqueue_work()
    old.enqueue_work()
    old.submit_action(_body("tune_pool", parameters={"pool_size": 9}), _headers(now))

    current = _bound_service(store, now, run_id="run-2")
    observed = current.state()
    repeated = _body("tune_pool", parameters={"pool_size": 7})
    repeated["run_id"] = "run-2"
    receipt = current.submit_action(repeated, _headers(now))

    assert observed["state"]["run_id"] == "run-2"
    assert observed["state"]["pool_size"] == 5
    assert observed["state"]["action_requests_total"] == 0
    assert observed["metrics"]["queue_depth"] == 0
    assert receipt["status"] == "completed"
    assert current.state()["state"]["pool_size"] == 7
    assert old.state()["state"]["run_id"] == "run-1"
    assert old.state()["state"]["pool_size"] == 9
    assert old.state()["metrics"]["queue_depth"] == 2

    old.enqueue_work()

    assert old.state()["metrics"]["queue_depth"] == 3
    assert current.state()["metrics"]["queue_depth"] == 0


def test_cross_run_rollback_cannot_reach_a_prior_authority_epoch() -> None:
    now = datetime(2026, 7, 17, tzinfo=UTC)
    store = InMemoryCausalStore()
    old = _bound_service(store, now)
    old.submit_action(_body("tune_pool", idem="shared-idem", parameters={"pool_size": 9}), _headers(now))
    current = _bound_service(store, now, run_id="run-2")
    rollback = {
        "schema_version": "p174.actions.rollback.v1",
        "request_id": "rollback-new-run",
        "idempotency_key": "rollback-new-run-idem",
        "project_id": EXPECTED["project_id"],
        "target_id": EXPECTED["target_id"],
        "run_id": "run-2",
        "original_request_id": "request-1",
        "original_idempotency_key": "shared-idem",
        "created_at": "2026-07-17T00:00:00Z",
        "evidence_hash": "sha256:" + "b" * 64,
        "policy_version": EXPECTED["policy_version"],
    }

    with pytest.raises(ValidationError, match="original_request_not_found"):
        current.rollback_action(rollback, _headers(now))

    assert old.state()["state"]["pool_size"] == 9
    assert current.state()["state"]["pool_size"] == 5


def test_project_and_target_bindings_cannot_take_over_existing_state() -> None:
    now = datetime(2026, 7, 17, tzinfo=UTC)
    store = InMemoryCausalStore()
    original = _bound_service(store, now)
    other_project = _bound_service(store, now, project_id="other-project")
    other_target = _bound_service(store, now, target_id="other-target")

    original.enqueue_work()
    other_project.enqueue_work()
    other_target.enqueue_work()
    other_target.enqueue_work()

    assert len({original.state_key, other_project.state_key, other_target.state_key}) == 3
    assert original.state()["metrics"]["queue_depth"] == 1
    assert other_project.state()["metrics"]["queue_depth"] == 1
    assert other_target.state()["metrics"]["queue_depth"] == 2


def test_tune_pool_changes_real_worker_throughput() -> None:
    now = datetime(2026, 7, 17, tzinfo=UTC)
    service = _service(now)
    for _ in range(20):
        service.enqueue_work()

    assert service.process_worker_batch() == 5
    assert service.state()["metrics"]["queue_depth"] == 15

    service.submit_action(_body("tune_pool", parameters={"pool_size": 16}), _headers(now))
    assert service.process_worker_batch() == 15
    assert service.state()["metrics"]["queue_depth"] == 0


def test_idempotent_replay_returns_same_receipt_and_suppresses_duplicate_effect() -> None:
    now = datetime(2026, 7, 17, tzinfo=UTC)
    service = _service(now)
    body = _body("tune_pool", parameters={"pool_size": 11})

    first = service.submit_action(body, _headers(now))
    replay = service.submit_action(body, _headers(now))

    assert replay == first
    assert replay["status"] == "completed"
    assert service.state()["metrics"]["pool_size"] == 11

    changed = dict(body)
    changed["parameters"] = {"pool_size": 12}
    with pytest.raises(ValidationError, match="idempotency_key_payload_mismatch"):
        service.submit_action(changed, _headers(now))


def test_action_effect_and_idempotency_receipt_commit_atomically() -> None:
    now = datetime(2026, 7, 17, tzinfo=UTC)
    store = _FailFirstCommitStore()
    service = _bound_service(store, now)
    body = _body("restart_worker", idem="atomic-action-idem")

    with pytest.raises(RuntimeError, match="injected_commit_failure"):
        service.submit_action(body, _headers(now))

    failed_state = service.state()["state"]
    assert failed_state["worker_restart_generation"] == 0
    assert failed_state["action_requests_total"] == 0
    assert store.get_json(service.idempotency_prefix + "atomic-action-idem") is None

    receipt = service.submit_action(body, _headers(now))

    assert receipt["status"] == "completed"
    assert service.state()["state"]["worker_restart_generation"] == 1
    assert service.state()["state"]["action_requests_total"] == 1


def test_rollback_effect_and_idempotency_receipt_commit_atomically() -> None:
    now = datetime(2026, 7, 17, tzinfo=UTC)
    store = _FailFirstCommitStore()
    store.fail_next_commit = False
    service = _bound_service(store, now)
    service.submit_action(_body("tune_pool", idem="original-action", parameters={"pool_size": 9}), _headers(now))
    rollback = {
        "schema_version": "p174.actions.rollback.v1",
        "request_id": "atomic-rollback",
        "idempotency_key": "atomic-rollback-idem",
        "project_id": EXPECTED["project_id"],
        "target_id": EXPECTED["target_id"],
        "run_id": EXPECTED["run_id"],
        "original_request_id": "request-1",
        "original_idempotency_key": "original-action",
        "created_at": "2026-07-17T00:00:00Z",
        "evidence_hash": "sha256:" + "b" * 64,
        "policy_version": EXPECTED["policy_version"],
    }
    store.fail_next_commit = True

    with pytest.raises(RuntimeError, match="injected_commit_failure"):
        service.rollback_action(rollback, _headers(now))

    failed_state = service.state()["state"]
    assert failed_state["pool_size"] == 9
    assert failed_state["rollback_requests_total"] == 0
    assert store.get_json(service.idempotency_prefix + "atomic-rollback-idem") is None

    receipt = service.rollback_action(rollback, _headers(now))

    assert receipt["status"] == "completed"
    assert service.state()["state"]["pool_size"] == 5
    assert service.state()["state"]["rollback_requests_total"] == 1


def test_rejects_wrong_binding_capability_expired_lease_and_unbounded_actions() -> None:
    now = datetime(2026, 7, 17, tzinfo=UTC)
    service = _service(now)

    wrong_project = _body("tune_pool")
    wrong_project["project_id"] = "other-project"
    with pytest.raises(ValidationError, match="project_id_mismatch"):
        service.submit_action(wrong_project, _headers(now))

    bad_headers = _headers(now)
    bad_headers["X-P174-Capability"] = "other.capability"
    with pytest.raises(ValidationError, match="capability_mismatch"):
        service.submit_action(_body("tune_pool"), bad_headers)

    expired_headers = _headers(now)
    expired_headers["X-P174-Lease-Expires"] = (now - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
    with pytest.raises(ValidationError, match="lease_expired"):
        service.submit_action(_body("tune_pool"), expired_headers)

    with pytest.raises(ValidationError, match="unsupported_action"):
        service.submit_action(_body("shell", parameters={"command": "echo nope"}), _headers(now))


def test_rollback_restores_reversible_snapshot_and_restart_rollback_is_noop_receipt() -> None:
    now = datetime(2026, 7, 17, tzinfo=UTC)
    service = _service(now)

    tune_receipt = service.submit_action(_body("tune_pool", idem="idem-tune", parameters={"pool_size": 13}), _headers(now))
    rollback = service.rollback_action(
        {
            "schema_version": "p174.actions.rollback.v1",
            "request_id": "rollback-1",
            "idempotency_key": "rollback-idem-1",
            "project_id": EXPECTED["project_id"],
            "target_id": EXPECTED["target_id"],
            "run_id": EXPECTED["run_id"],
            "original_request_id": "request-1",
            "original_idempotency_key": "idem-tune",
            "created_at": "2026-07-17T00:00:00Z",
            "evidence_hash": "sha256:" + "b" * 64,
            "policy_version": EXPECTED["policy_version"],
        },
        _headers(now),
    )

    assert rollback["accepted"] is True
    assert rollback["status"] == "completed"
    assert rollback["action"] == "rollback"
    assert rollback["state"]["pool_size"] == tune_receipt["before_metrics"]["pool_size"]

    restart = service.submit_action(_body("restart_worker", request_id="restart-1", idem="idem-restart"), _headers(now))
    restart_rollback = service.rollback_action(
        {
            "schema_version": "p174.actions.rollback.v1",
            "request_id": "rollback-2",
            "idempotency_key": "rollback-idem-2",
            "project_id": EXPECTED["project_id"],
            "target_id": EXPECTED["target_id"],
            "run_id": EXPECTED["run_id"],
            "original_request_id": "restart-1",
            "original_idempotency_key": "idem-restart",
            "created_at": "2026-07-17T00:00:00Z",
            "evidence_hash": "sha256:" + "c" * 64,
            "policy_version": EXPECTED["policy_version"],
        },
        _headers(now),
    )

    assert restart["status"] == "completed"
    assert restart_rollback["status"] == "completed"
    assert restart_rollback["provider_claimed_success"] is True
    assert restart_rollback["evidence"]["rollback_mode"] == "noop_bounded_pause"
