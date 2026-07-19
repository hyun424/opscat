from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import socket
import threading
import time
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, datetime, timedelta
from functools import wraps
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Protocol, cast

STARTED_AT = time.time()
STATE_KEY = "p174:state"
STATE_LOCK_KEY = "p174:state:lock"
QUEUE_KEY = "p174:queue"
REDIS_STATE_LOCK_TTL_MS = 30_000
REDIS_STATE_LOCK_RENEW_SECONDS = 5.0
ACTION_FIELDS = {
    "schema_version",
    "request_id",
    "idempotency_key",
    "project_id",
    "target_id",
    "run_id",
    "action",
    "parameters",
    "created_at",
    "evidence_hash",
    "policy_version",
}
FAULT_FIELDS = {
    "schema_version",
    "request_id",
    "idempotency_key",
    "project_id",
    "target_id",
    "run_id",
    "fault",
    "parameters",
    "created_at",
    "evidence_hash",
    "policy_version",
}
FAULT_CLEANUP_FIELDS = {
    "schema_version",
    "request_id",
    "idempotency_key",
    "project_id",
    "target_id",
    "run_id",
    "original_request_id",
    "original_idempotency_key",
    "cleanup_token",
    "created_at",
    "evidence_hash",
    "policy_version",
}
ROLLBACK_FIELDS = {
    "schema_version",
    "request_id",
    "idempotency_key",
    "project_id",
    "target_id",
    "run_id",
    "original_request_id",
    "original_idempotency_key",
    "created_at",
    "evidence_hash",
    "policy_version",
}
SAFE_ACTIONS = {"tune_pool", "restart_worker", "rollback_canary"}
SAFE_FAULTS = {"queue_backlog", "canary_regression", "worker_pause"}
FORBIDDEN_PARAMETER_KEYS = {
    "command",
    "cmd",
    "shell",
    "url",
    "uri",
    "endpoint",
    "docker_socket",
    "docker.sock",
    "container",
    "container_id",
    "container_name",
    "process",
    "process_id",
    "process_name",
    "pid",
}
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class ValidationError(ValueError):
    pass


class CausalStore(Protocol):
    def get_json(self, key: str) -> dict[str, Any] | None: ...

    def set_json(self, key: str, value: Mapping[str, Any]) -> None: ...

    def push_queue(self, key: str, value: Mapping[str, Any]) -> None: ...

    def pop_queue(self, key: str) -> dict[str, Any] | None: ...

    def queue_length(self, key: str) -> int: ...

    def increment(self, key: str) -> int: ...

    def count_queue_items(self, key: str, values: list[Mapping[str, Any]]) -> int: ...

    def commit_mutation(
        self,
        json_values: Mapping[str, Mapping[str, Any]],
        *,
        queue_key: str | None = None,
        append_items: list[Mapping[str, Any]] | None = None,
        remove_items: list[Mapping[str, Any]] | None = None,
        expected_remove_count: int | None = None,
    ) -> int: ...

    def state_lock(self, key: str) -> AbstractContextManager[None]: ...


class InMemoryCausalStore:
    def __init__(self) -> None:
        self._values: dict[str, str] = {}
        self._queues: dict[str, list[str]] = {}
        self._lock = threading.RLock()

    def get_json(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            value = self._values.get(key)
        return cast(dict[str, Any], json.loads(value)) if value is not None else None

    def set_json(self, key: str, value: Mapping[str, Any]) -> None:
        with self._lock:
            self._values[key] = _canonical_json(value)

    def push_queue(self, key: str, value: Mapping[str, Any]) -> None:
        with self._lock:
            self._queues.setdefault(key, []).append(_canonical_json(value))

    def pop_queue(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            queue = self._queues.setdefault(key, [])
            if not queue:
                return None
            value = queue.pop(0)
        return cast(dict[str, Any], json.loads(value))

    def queue_length(self, key: str) -> int:
        with self._lock:
            return len(self._queues.setdefault(key, []))

    def increment(self, key: str) -> int:
        with self._lock:
            current = int(self._values.get(key, "0")) + 1
            self._values[key] = str(current)
            return current

    def count_queue_items(self, key: str, values: list[Mapping[str, Any]]) -> int:
        targets = {_canonical_json(value) for value in values}
        with self._lock:
            return sum(item in targets for item in self._queues.setdefault(key, []))

    def commit_mutation(
        self,
        json_values: Mapping[str, Mapping[str, Any]],
        *,
        queue_key: str | None = None,
        append_items: list[Mapping[str, Any]] | None = None,
        remove_items: list[Mapping[str, Any]] | None = None,
        expected_remove_count: int | None = None,
    ) -> int:
        serialized_values = {key: _canonical_json(value) for key, value in json_values.items()}
        appended = [_canonical_json(value) for value in append_items or []]
        removals = [_canonical_json(value) for value in remove_items or []]
        if appended and removals:
            raise ValueError("simultaneous_queue_append_remove_not_supported")
        if removals and expected_remove_count is None:
            raise ValueError("expected_remove_count_required")
        if expected_remove_count is not None and expected_remove_count < 0:
            raise ValueError("expected_remove_count_invalid")
        if expected_remove_count is not None and queue_key is None:
            raise ValueError("queue_key_required_for_expected_remove_count")
        with self._lock:
            current_queue = self._queues.setdefault(queue_key, []) if queue_key is not None else None
            candidate_queue = list(current_queue) if current_queue is not None else None
            removed = 0
            if candidate_queue is not None:
                candidate_queue.extend(appended)
                for target in removals:
                    try:
                        candidate_queue.remove(target)
                    except ValueError:
                        continue
                    removed += 1
            if expected_remove_count is not None and removed != expected_remove_count:
                raise RuntimeError("queue_remove_count_mismatch")
            if current_queue is not None and candidate_queue is not None:
                current_queue[:] = candidate_queue
            self._values.update(serialized_values)
        return removed

    @contextmanager
    def state_lock(self, _key: str) -> Any:
        with self._lock:
            yield


class RedisCausalStore:
    def __init__(self, host: str, port: int = 6379, timeout: float = 2.0) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self._lock_binding = threading.local()

    def get_json(self, key: str) -> dict[str, Any] | None:
        value = self._command("GET", key)
        return cast(dict[str, Any], json.loads(value.decode("utf-8"))) if isinstance(value, bytes) else None

    def set_json(self, key: str, value: Mapping[str, Any]) -> None:
        self._guarded_command("return redis.call('set',KEYS[2],ARGV[2])", [key], _canonical_json(value))

    def push_queue(self, key: str, value: Mapping[str, Any]) -> None:
        self._guarded_command("return redis.call('rpush',KEYS[2],ARGV[2])", [key], _canonical_json(value))

    def pop_queue(self, key: str) -> dict[str, Any] | None:
        value = self._guarded_command("return redis.call('lpop',KEYS[2])", [key])
        return cast(dict[str, Any], json.loads(value.decode("utf-8"))) if isinstance(value, bytes) else None

    def queue_length(self, key: str) -> int:
        value = self._command("LLEN", key)
        if not isinstance(value, int):
            raise RuntimeError("redis_llen_response_invalid")
        return value

    def increment(self, key: str) -> int:
        value = self._guarded_command("return redis.call('incr',KEYS[2])", [key])
        if not isinstance(value, int):
            raise RuntimeError("redis_incr_response_invalid")
        return value

    def count_queue_items(self, key: str, values: list[Mapping[str, Any]]) -> int:
        count = 0
        for value in values:
            position = self._command("LPOS", key, _canonical_json(value))
            if position is not None:
                if not isinstance(position, int):
                    raise RuntimeError("redis_lpos_response_invalid")
                count += 1
        return count

    def commit_mutation(
        self,
        json_values: Mapping[str, Mapping[str, Any]],
        *,
        queue_key: str | None = None,
        append_items: list[Mapping[str, Any]] | None = None,
        remove_items: list[Mapping[str, Any]] | None = None,
        expected_remove_count: int | None = None,
    ) -> int:
        append_values = [_canonical_json(value) for value in append_items or []]
        remove_values = [_canonical_json(value) for value in remove_items or []]
        if append_values and remove_values:
            raise ValueError("simultaneous_queue_append_remove_not_supported")
        if remove_values and expected_remove_count is None:
            raise ValueError("expected_remove_count_required")
        if expected_remove_count is not None and expected_remove_count < 0:
            raise ValueError("expected_remove_count_invalid")
        if expected_remove_count is not None and queue_key is None:
            raise ValueError("queue_key_required_for_expected_remove_count")
        if len(set(remove_values)) != len(remove_values):
            raise ValueError("duplicate_remove_items_not_supported")
        keys = list(json_values)
        arguments = [_canonical_json(value) for value in json_values.values()]
        preflight_commands: list[str] = []
        for index in range(len(keys)):
            preflight_commands.append(
                f"local json_type_{index}=redis.call('type',KEYS[{index + 2}])['ok']; "
                f"if json_type_{index}~='none' and json_type_{index}~='string' then "
                "return redis.error_reply('json_key_type_invalid') end;"
            )
        queue_index: int | None = None
        if queue_key is not None:
            queue_index = len(keys) + 2
            keys.append(queue_key)
            preflight_commands.append(
                f"local queue_type=redis.call('type',KEYS[{queue_index}])['ok']; if queue_type~='none' and queue_type~='list' then return redis.error_reply('queue_key_type_invalid') end;"
            )
        next_argument = len(arguments) + 2
        append_argument_indexes: list[int] = []
        remove_argument_indexes: list[int] = []
        for value in append_values:
            append_argument_indexes.append(next_argument)
            arguments.append(value)
            next_argument += 1
        for value in remove_values:
            remove_argument_indexes.append(next_argument)
            arguments.append(value)
            next_argument += 1
        if queue_index is not None and expected_remove_count is not None:
            preflight_commands.append("local removable=0;")
            for argument_index in remove_argument_indexes:
                preflight_commands.append(f"if redis.call('lpos',KEYS[{queue_index}],ARGV[{argument_index}]) then removable=removable+1 end;")
            preflight_commands.append(f"if removable~={expected_remove_count} then return redis.error_reply('queue_remove_count_mismatch') end;")
        mutation_commands: list[str] = []
        for index in range(len(json_values)):
            mutation_commands.append(f"redis.call('set',KEYS[{index + 2}],ARGV[{index + 2}]);")
        if queue_index is not None:
            for argument_index in append_argument_indexes:
                mutation_commands.append(f"redis.call('rpush',KEYS[{queue_index}],ARGV[{argument_index}]);")
            mutation_commands.append("local removed=0;")
            for argument_index in remove_argument_indexes:
                mutation_commands.append(f"removed=removed+redis.call('lrem',KEYS[{queue_index}],1,ARGV[{argument_index}]);")
            mutation_commands.append("return removed")
        else:
            mutation_commands.append("return 0")
        result = self._guarded_command(" ".join([*preflight_commands, *mutation_commands]), keys, *arguments)
        if not isinstance(result, int):
            raise RuntimeError("redis_commit_response_invalid")
        return result

    @contextmanager
    def state_lock(self, key: str) -> Any:
        if getattr(self._lock_binding, "token", None) is not None:
            raise RuntimeError("redis_state_lock_reentrant")
        token = secrets.token_hex(16)
        deadline = time.monotonic() + 5.0
        while self._command("SET", key, token, "NX", "PX", str(REDIS_STATE_LOCK_TTL_MS)) != b"OK":
            if time.monotonic() >= deadline:
                raise RuntimeError("redis_state_lock_timeout")
            time.sleep(0.01)
        stop_renewal = threading.Event()
        lock_lost = threading.Event()

        def renew() -> None:
            while not stop_renewal.wait(REDIS_STATE_LOCK_RENEW_SECONDS):
                try:
                    renewed = self._command(
                        "EVAL",
                        "if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('pexpire',KEYS[1],ARGV[2]) else return 0 end",
                        "1",
                        key,
                        token,
                        str(REDIS_STATE_LOCK_TTL_MS),
                    )
                except (OSError, RuntimeError):
                    lock_lost.set()
                    return
                if renewed != 1:
                    lock_lost.set()
                    return

        self._lock_binding.key = key
        self._lock_binding.token = token
        renewal = threading.Thread(target=renew, daemon=True)
        renewal.start()
        try:
            yield
        finally:
            stop_renewal.set()
            renewal.join(timeout=2.0)
            try:
                released = self._command(
                    "EVAL",
                    "if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('del',KEYS[1]) else return 0 end",
                    "1",
                    key,
                    token,
                )
            finally:
                self._lock_binding.key = None
                self._lock_binding.token = None
            if lock_lost.is_set():
                raise RuntimeError("redis_state_lock_lost")
            if released != 1:
                raise RuntimeError("redis_state_lock_lost")

    def _guarded_command(self, command: str, keys: list[str], *arguments: str) -> bytes | int | None:
        lock_key = getattr(self._lock_binding, "key", None)
        token = getattr(self._lock_binding, "token", None)
        if not isinstance(lock_key, str) or not isinstance(token, str):
            raise RuntimeError("redis_state_lock_required")
        script = "if redis.call('get',KEYS[1]) ~= ARGV[1] then return redis.error_reply('state_lock_lost') end; " + command
        return self._command("EVAL", script, str(len(keys) + 1), lock_key, *keys, token, *arguments)

    def _command(self, *parts: str) -> bytes | int | None:
        request = _encode_resp(parts)
        with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
            sock.settimeout(self.timeout)
            sock.sendall(request)
            return _read_resp(sock)


def _state_locked[**P, R](method: Callable[P, R]) -> Callable[P, R]:
    @wraps(method)
    def locked(*args: P.args, **kwargs: P.kwargs) -> R:
        service = cast(Any, args[0])
        with service.store.state_lock(service.state_lock_key):
            return method(*args, **kwargs)

    return locked


class RuntimeActionService:
    def __init__(
        self,
        store: CausalStore,
        *,
        project_id: str,
        target_id: str,
        run_id: str,
        policy_version: str,
        capability: str,
        fault_capability: str,
        now: Callable[[], datetime] | None = None,
        max_lease_seconds: int = 300,
        rollback_pause_seconds: float = 0.01,
    ) -> None:
        if not capability or not fault_capability or capability == fault_capability:
            raise ValidationError("capability_separation_required")
        self.store = store
        self.project_id = project_id
        self.target_id = target_id
        self.run_id = run_id
        self.policy_version = policy_version
        self.capability = capability
        self.fault_capability = fault_capability
        self.now = now or (lambda: datetime.now(UTC))
        self.max_lease_seconds = max_lease_seconds
        self.rollback_pause_seconds = rollback_pause_seconds
        binding_hash = hashlib.sha256(_canonical_json({"project_id": project_id, "target_id": target_id, "run_id": run_id}).encode("utf-8")).hexdigest()
        namespace = f"p174:{binding_hash}"
        self.state_key = f"{namespace}:state"
        self.state_lock_key = f"{namespace}:state:lock"
        self.queue_key = f"{namespace}:queue"
        self.work_sequence_key = f"{namespace}:work_seq"
        self.idempotency_prefix = f"{namespace}:idem:"
        self.fault_prefix = f"{namespace}:fault:"

    @_state_locked
    def state(self) -> dict[str, Any]:
        state = self._state()
        state["queue_depth"] = self.store.queue_length(self.queue_key)
        self.store.set_json(self.state_key, state)
        return {
            "status": "ok",
            "observed_at": self.now().isoformat().replace("+00:00", "Z"),
            "state": state,
            "metrics": self._metrics_from_state(state),
        }

    @_state_locked
    def enqueue_work(self) -> dict[str, Any]:
        work_id = f"work-{self.store.increment(self.work_sequence_key)}"
        self.store.push_queue(self.queue_key, {"work_id": work_id, "created_at": self.now().isoformat().replace("+00:00", "Z")})
        state = self._state()
        state["requests_total"] = int(state["requests_total"]) + 1
        state["queue_depth"] = self.store.queue_length(self.queue_key)
        self.store.set_json(self.state_key, state)
        return {"accepted": True, "work_id": work_id, "queue_depth": state["queue_depth"]}

    def _process_worker_job(self) -> bool:
        state = self._state()
        if _parse_utc(str(state["worker_paused_until"])) > self.now():
            state["queue_depth"] = self.store.queue_length(self.queue_key)
            self.store.set_json(self.state_key, state)
            return False
        job = self.store.pop_queue(self.queue_key)
        if job is None:
            state["queue_depth"] = 0
            self.store.set_json(self.state_key, state)
            return False
        state["worker_jobs_total"] = int(state["worker_jobs_total"]) + 1
        state["queue_depth"] = self.store.queue_length(self.queue_key)
        self.store.set_json(self.state_key, state)
        return True

    @_state_locked
    def process_worker_job(self) -> bool:
        return self._process_worker_job()

    @_state_locked
    def record_loadgen_result(self, *, accepted: bool) -> None:
        state = self._state()
        key = "loadgen_requests_total" if accepted else "loadgen_errors_total"
        state[key] = int(state[key]) + 1
        self.store.set_json(self.state_key, state)

    @_state_locked
    def record_rejection(self) -> dict[str, Any]:
        state = self._state()
        state["action_rejected_total"] = int(state["action_rejected_total"]) + 1
        self.store.set_json(self.state_key, state)
        return state

    @_state_locked
    def process_worker_batch(self) -> int:
        """Process capacity proportional to the configured pool size.

        Each pool slot represents one bounded worker lane per tick. This makes
        ``tune_pool`` alter real queue throughput and lets a reviewed recovery
        drain an incident backlog within the provider post-check horizon.
        """

        state = self._state()
        capacity = max(1, int(state["pool_size"]))
        processed = 0
        for _ in range(capacity):
            if not self._process_worker_job():
                break
            processed += 1
        return processed

    @_state_locked
    def submit_action(self, body: Mapping[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        self._validate_common_body(
            body,
            expected_fields=ACTION_FIELDS,
            schema_version="p174.actions.v1",
            headers=headers,
            capability_header="X-P174-Capability",
            expected_capability=self.capability,
        )
        action = self._required_string(body, "action")
        if action not in SAFE_ACTIONS:
            raise ValidationError("unsupported_action")
        parameters = self._parameters(body)
        request_hash = _hash_json(body)
        replay = self._idempotent_replay(str(body["idempotency_key"]), request_hash)
        if replay is not None:
            return replay

        before_state = self._state()
        after_state = dict(before_state)
        after_state["deadman_expires_at"] = (self.now() + timedelta(seconds=int(os.environ.get("P174_DEADMAN_TTL_SECONDS", "120")))).isoformat().replace("+00:00", "Z")
        evidence: dict[str, Any] = {"request_hash": request_hash, "policy_version": self.policy_version}
        if action == "tune_pool":
            pool_size = parameters.get("pool_size")
            if not isinstance(pool_size, int) or not 1 <= pool_size <= 64:
                raise ValidationError("invalid_tune_pool_parameters")
            after_state["pool_size"] = pool_size
        elif action == "restart_worker":
            pause_seconds = parameters.get("pause_seconds", 0.05)
            if not isinstance(pause_seconds, int | float) or not 0 <= float(pause_seconds) <= 2:
                raise ValidationError("invalid_restart_worker_parameters")
            after_state["worker_restart_generation"] = int(after_state["worker_restart_generation"]) + 1
            after_state["worker_paused_until"] = (self.now() + timedelta(seconds=float(pause_seconds))).isoformat().replace("+00:00", "Z")
        elif action == "rollback_canary":
            if parameters and set(parameters) != {"version"}:
                raise ValidationError("invalid_rollback_canary_parameters")
            if "version" in parameters and parameters["version"] != "stable":
                raise ValidationError("invalid_rollback_canary_version")
            after_state["canary_version"] = "stable"

        after_state["action_requests_total"] = int(after_state["action_requests_total"]) + 1
        after_state["queue_depth"] = self.store.queue_length(self.queue_key)
        receipt = self._receipt(body, action=action, before_state=before_state, after_state=after_state, request_hash=request_hash, evidence=evidence)
        self.store.commit_mutation(
            {
                self.state_key: after_state,
                self.idempotency_prefix + str(body["idempotency_key"]): {"request_hash": request_hash, "receipt": receipt},
            }
        )
        return receipt

    @_state_locked
    def submit_fault(self, body: Mapping[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        self._validate_common_body(
            body,
            expected_fields=FAULT_FIELDS,
            schema_version="p174.faults.v1",
            headers=headers,
            capability_header="X-P174-Fault-Capability",
            expected_capability=self.fault_capability,
        )
        fault = self._required_string(body, "fault")
        if fault not in SAFE_FAULTS:
            raise ValidationError("unsupported_fault")
        parameters = self._parameters(body)
        request_hash = _hash_json(body)
        replay = self._idempotent_replay(str(body["idempotency_key"]), request_hash)
        if replay is not None:
            return replay

        before_state = self._state()
        after_state = dict(before_state)
        after_state["deadman_expires_at"] = (self.now() + timedelta(seconds=int(os.environ.get("P174_DEADMAN_TTL_SECONDS", "120")))).isoformat().replace("+00:00", "Z")
        evidence: dict[str, Any] = {
            "request_hash": request_hash,
            "policy_version": self.policy_version,
            "fault_receipt_immutable": True,
            "lab_only": True,
        }
        cleanup_token = _hash_json(
            {
                "purpose": "p174:fault_cleanup",
                "request_id": body["request_id"],
                "idempotency_key": body["idempotency_key"],
                "request_hash": request_hash,
                "project_id": self.project_id,
                "target_id": self.target_id,
                "run_id": self.run_id,
            }
        )
        evidence["cleanup_token"] = cleanup_token
        inserted_queue_items: list[Mapping[str, Any]] = []
        if fault == "queue_backlog":
            if set(parameters) - {"items"}:
                raise ValidationError("invalid_queue_backlog_parameters")
            items = parameters.get("items", 25)
            if not isinstance(items, int) or not 1 <= items <= 1_000:
                raise ValidationError("invalid_queue_backlog_parameters")
            for index in range(items):
                queue_item = {
                    "work_id": f"fault-work-{request_hash.removeprefix('sha256:')}-{index}",
                    "fault": fault,
                    "fault_request_id": body["request_id"],
                    "fault_idempotency_key": body["idempotency_key"],
                    "cleanup_token": cleanup_token,
                    "created_at": self.now().isoformat().replace("+00:00", "Z"),
                }
                inserted_queue_items.append(queue_item)
            evidence["injected_items"] = items
        elif fault == "canary_regression":
            if set(parameters) - {"version"}:
                raise ValidationError("invalid_canary_regression_parameters")
            version = parameters.get("version", "regressed")
            if version != "regressed":
                raise ValidationError("invalid_canary_regression_version")
            after_state["canary_version"] = version
        elif fault == "worker_pause":
            if set(parameters) - {"pause_seconds"}:
                raise ValidationError("invalid_worker_pause_parameters")
            pause_seconds = parameters.get("pause_seconds", 30)
            if not isinstance(pause_seconds, int | float) or not 0 < float(pause_seconds) <= 300:
                raise ValidationError("invalid_worker_pause_parameters")
            after_state["worker_paused_until"] = (self.now() + timedelta(seconds=float(pause_seconds))).isoformat().replace("+00:00", "Z")
            evidence["pause_seconds"] = float(pause_seconds)

        after_state["action_requests_total"] = int(after_state["action_requests_total"]) + 1
        after_state["queue_depth"] = self.store.queue_length(self.queue_key) + len(inserted_queue_items)
        receipt = self._receipt(body, action=f"fault:{fault}", before_state=before_state, after_state=after_state, request_hash=request_hash, evidence=evidence)
        fault_record = {
            "request_id": body["request_id"],
            "idempotency_key": body["idempotency_key"],
            "request_hash": request_hash,
            "fault": fault,
            "before_state": before_state,
            "inserted_queue_items": inserted_queue_items,
            "cleanup_token": cleanup_token,
            "cleanup_used": False,
        }
        self.store.commit_mutation(
            {
                self.state_key: after_state,
                self.idempotency_prefix + str(body["idempotency_key"]): {"request_hash": request_hash, "receipt": receipt},
                self.fault_prefix + str(body["idempotency_key"]): fault_record,
            },
            queue_key=self.queue_key,
            append_items=inserted_queue_items,
        )
        return receipt

    @_state_locked
    def rollback_action(self, body: Mapping[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        self._validate_common_body(
            body,
            expected_fields=ROLLBACK_FIELDS,
            schema_version="p174.actions.rollback.v1",
            headers=headers,
            capability_header="X-P174-Capability",
            expected_capability=self.capability,
        )
        request_hash = _hash_json(body)
        replay = self._idempotent_replay(str(body["idempotency_key"]), request_hash)
        if replay is not None:
            return replay
        original = self.store.get_json(self.idempotency_prefix + str(body["original_idempotency_key"]))
        if original is None:
            raise ValidationError("original_request_not_found")
        original_receipt = cast(dict[str, Any], original["receipt"])
        if original_receipt.get("request_id") != body["original_request_id"]:
            raise ValidationError("original_request_binding_mismatch")

        before_state = self._state()
        original_action = str(original_receipt["action"])
        restored_state = dict(before_state)
        restored_state["deadman_expires_at"] = (self.now() + timedelta(seconds=int(os.environ.get("P174_DEADMAN_TTL_SECONDS", "120")))).isoformat().replace("+00:00", "Z")
        rollback_mode = "snapshot_restore"
        original_state = cast(dict[str, Any], original_receipt["before_state"])
        if original_action == "tune_pool":
            restored_state["pool_size"] = original_state["pool_size"]
        elif original_action == "rollback_canary":
            restored_state["canary_version"] = original_state["canary_version"]
        elif original_action == "restart_worker":
            rollback_mode = "noop_bounded_pause"
            time.sleep(self.rollback_pause_seconds)
        else:
            raise ValidationError("original_action_not_reversible")
        restored_state["rollback_requests_total"] = int(restored_state["rollback_requests_total"]) + 1
        receipt = self._receipt(
            body,
            action="rollback",
            before_state=before_state,
            after_state=restored_state,
            request_hash=request_hash,
            evidence={
                "request_hash": request_hash,
                "original_receipt_id": original_receipt["evidence"]["receipt_id"],
                "rollback_mode": rollback_mode,
                "policy_version": self.policy_version,
            },
        )
        self.store.commit_mutation(
            {
                self.state_key: restored_state,
                self.idempotency_prefix + str(body["idempotency_key"]): {"request_hash": request_hash, "receipt": receipt},
            }
        )
        return receipt

    @_state_locked
    def cleanup_fault(self, body: Mapping[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        self._validate_common_body(
            body,
            expected_fields=FAULT_CLEANUP_FIELDS,
            schema_version="p174.faults.cleanup.v1",
            headers=headers,
            capability_header="X-P174-Fault-Capability",
            expected_capability=self.fault_capability,
        )
        request_hash = _hash_json(body)
        replay = self._idempotent_replay(str(body["idempotency_key"]), request_hash)
        if replay is not None:
            return replay

        original = self.store.get_json(self.idempotency_prefix + str(body["original_idempotency_key"]))
        if original is None:
            raise ValidationError("original_fault_not_found")
        original_receipt = cast(dict[str, Any], original["receipt"])
        if original_receipt.get("request_id") != body["original_request_id"]:
            raise ValidationError("original_fault_binding_mismatch")
        original_action = str(original_receipt.get("action", ""))
        if not original_action.startswith("fault:"):
            raise ValidationError("original_request_not_fault")
        fault_record = self.store.get_json(self.fault_prefix + str(body["original_idempotency_key"]))
        if fault_record is None:
            raise ValidationError("fault_cleanup_record_missing")
        if fault_record.get("request_hash") != original.get("request_hash"):
            raise ValidationError("fault_cleanup_record_mismatch")
        if fault_record.get("request_id") != body["original_request_id"]:
            raise ValidationError("fault_cleanup_record_mismatch")
        if fault_record.get("cleanup_token") != body["cleanup_token"]:
            raise ValidationError("cleanup_token_mismatch")
        if fault_record.get("cleanup_used") is True:
            raise ValidationError("cleanup_token_already_used")

        before_state = self._state()
        restored_state = dict(before_state)
        original_state = cast(dict[str, Any], fault_record["before_state"])
        fault = str(fault_record.get("fault"))
        if fault not in SAFE_FAULTS:
            raise ValidationError("fault_cleanup_type_invalid")
        for field in ("pool_size", "canary_version", "worker_restart_generation", "worker_paused_until"):
            restored_state[field] = original_state[field]
        queue_items = cast(list[Mapping[str, Any]], fault_record.get("inserted_queue_items", []))
        removed_queue_items = self.store.count_queue_items(self.queue_key, queue_items) if queue_items else 0
        restored_state["deadman_expires_at"] = (self.now() + timedelta(seconds=int(os.environ.get("P174_DEADMAN_TTL_SECONDS", "120")))).isoformat().replace("+00:00", "Z")
        restored_state["queue_depth"] = self.store.queue_length(self.queue_key) - removed_queue_items
        restored_state["rollback_requests_total"] = int(restored_state["rollback_requests_total"]) + 1
        fault_record["cleanup_used"] = True
        fault_record["cleanup_request_id"] = body["request_id"]
        receipt = self._receipt(
            body,
            action="fault_cleanup",
            before_state=before_state,
            after_state=restored_state,
            request_hash=request_hash,
            evidence={
                "request_hash": request_hash,
                "original_fault_receipt_id": original_receipt["evidence"]["receipt_id"],
                "cleanup_mode": "server_snapshot_restore",
                "removed_queue_items": removed_queue_items,
                "policy_version": self.policy_version,
            },
        )
        self.store.commit_mutation(
            {
                self.state_key: restored_state,
                self.fault_prefix + str(body["original_idempotency_key"]): fault_record,
                self.idempotency_prefix + str(body["idempotency_key"]): {"request_hash": request_hash, "receipt": receipt},
            },
            queue_key=self.queue_key,
            remove_items=queue_items,
            expected_remove_count=removed_queue_items,
        )
        return receipt

    def _state(self) -> dict[str, Any]:
        state = self.store.get_json(self.state_key)
        if state is not None:
            return state
        now = self.now()
        initial = {
            "project_id": self.project_id,
            "target_id": self.target_id,
            "run_id": self.run_id,
            "pool_size": int(os.environ.get("P174_INITIAL_POOL_SIZE", "5")),
            "queue_depth": self.store.queue_length(self.queue_key),
            "canary_version": os.environ.get("CANARY_VERSION", "stable"),
            "worker_restart_generation": 0,
            "worker_paused_until": now.isoformat().replace("+00:00", "Z"),
            "deadman_expires_at": (now + timedelta(seconds=int(os.environ.get("P174_DEADMAN_TTL_SECONDS", "120")))).isoformat().replace("+00:00", "Z"),
            "requests_total": 0,
            "worker_jobs_total": 0,
            "action_requests_total": 0,
            "action_rejected_total": 0,
            "rollback_requests_total": 0,
            "loadgen_requests_total": 0,
            "loadgen_errors_total": 0,
            "latency_ms": 25,
            "error_rate": 0.0,
        }
        self.store.set_json(self.state_key, initial)
        return initial

    def _metrics_from_state(self, state: Mapping[str, Any]) -> dict[str, int | float]:
        queue_depth = int(state["queue_depth"])
        pool_size = max(1, int(state["pool_size"]))
        overload = max(0, queue_depth - pool_size * 2)
        canary_penalty = 0.1 if state.get("canary_version") != "stable" else 0.0
        return {
            "error_rate": round(min(1.0, overload / max(1, queue_depth) + canary_penalty), 6),
            "latency_ms": round(25.0 + (queue_depth * 20.0 / pool_size) + canary_penalty * 2_000.0, 3),
            "service_up": 1,
            "queue_depth": queue_depth,
            "pool_size": pool_size,
        }

    def _receipt(
        self,
        body: Mapping[str, Any],
        *,
        action: str,
        before_state: Mapping[str, Any],
        after_state: Mapping[str, Any],
        request_hash: str,
        evidence: Mapping[str, Any],
    ) -> dict[str, Any]:
        receipt_id = "p174-receipt-" + hashlib.sha256(f"{body['request_id']}:{request_hash}".encode()).hexdigest()[:24]
        enriched_evidence = dict(evidence)
        enriched_evidence["receipt_id"] = receipt_id
        enriched_evidence["created_at"] = self.now().isoformat().replace("+00:00", "Z")
        return {
            "accepted": True,
            "status": "completed",
            "request_id": body["request_id"],
            "idempotency_key": body["idempotency_key"],
            "action": action,
            "state": self._public_state(after_state),
            "before_state": self._public_state(before_state),
            "before_metrics": self._metrics_from_state(before_state),
            "after_metrics": self._metrics_from_state(after_state),
            "provider_claimed_success": True,
            "evidence": enriched_evidence,
        }

    def _public_state(self, state: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "project_id": state["project_id"],
            "target_id": state["target_id"],
            "run_id": state["run_id"],
            "pool_size": state["pool_size"],
            "queue_depth": state["queue_depth"],
            "canary_version": state["canary_version"],
            "worker_restart_generation": state["worker_restart_generation"],
            "worker_paused_until": state["worker_paused_until"],
        }

    def _validate_common_body(
        self,
        body: Mapping[str, Any],
        *,
        expected_fields: set[str],
        schema_version: str,
        headers: Mapping[str, str],
        capability_header: str,
        expected_capability: str,
    ) -> None:
        if set(body) != expected_fields:
            missing = sorted(expected_fields - set(body))
            extra = sorted(set(body) - expected_fields)
            raise ValidationError(f"invalid_fields:missing={missing}:extra={extra}")
        if body["schema_version"] != schema_version:
            raise ValidationError("schema_version_mismatch")
        for field in ("request_id", "idempotency_key", "project_id", "target_id", "run_id", "created_at", "evidence_hash", "policy_version"):
            self._required_string(body, field)
        if body["project_id"] != self.project_id:
            raise ValidationError("project_id_mismatch")
        if body["target_id"] != self.target_id:
            raise ValidationError("target_id_mismatch")
        if body["run_id"] != self.run_id:
            raise ValidationError("run_id_mismatch")
        if body["policy_version"] != self.policy_version:
            raise ValidationError("policy_version_mismatch")
        if not SHA256_RE.fullmatch(str(body["evidence_hash"])):
            raise ValidationError("evidence_hash_invalid")
        if headers.get(capability_header) != expected_capability:
            raise ValidationError("capability_mismatch")
        lease_expires = _parse_utc(headers.get("X-P174-Lease-Expires", ""))
        now = self.now()
        if lease_expires <= now:
            raise ValidationError("lease_expired")
        if lease_expires > now + timedelta(seconds=self.max_lease_seconds):
            raise ValidationError("lease_too_long")
        created_at = _parse_utc(str(body["created_at"]))
        if created_at > now + timedelta(seconds=30):
            raise ValidationError("created_at_from_future")
        if created_at < now - timedelta(seconds=int(os.environ.get("P174_DEADMAN_TTL_SECONDS", "120"))):
            raise ValidationError("deadman_expired")

    def _parameters(self, body: Mapping[str, Any]) -> dict[str, Any]:
        parameters = body["parameters"]
        if not isinstance(parameters, dict):
            raise ValidationError("parameters_must_be_object")
        forbidden = sorted(FORBIDDEN_PARAMETER_KEYS & set(parameters))
        if forbidden:
            raise ValidationError(f"forbidden_parameter:{forbidden[0]}")
        return cast(dict[str, Any], parameters)

    def _idempotent_replay(self, idempotency_key: str, request_hash: str) -> dict[str, Any] | None:
        existing = self.store.get_json(self.idempotency_prefix + idempotency_key)
        if existing is None:
            return None
        if existing.get("request_hash") != request_hash:
            raise ValidationError("idempotency_key_payload_mismatch")
        return cast(dict[str, Any], existing["receipt"])

    def _required_string(self, body: Mapping[str, Any], field: str) -> str:
        value = body[field]
        if not isinstance(value, str) or not value:
            raise ValidationError(f"{field}_invalid")
        return value


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _hash_json(value: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError("timestamp_invalid") from exc
    if parsed.tzinfo is None:
        raise ValidationError("timestamp_timezone_required")
    return parsed.astimezone(UTC)


def _encode_resp(parts: tuple[str, ...]) -> bytes:
    encoded = [f"*{len(parts)}\r\n".encode()]
    for part in parts:
        raw = part.encode()
        encoded.append(f"${len(raw)}\r\n".encode())
        encoded.append(raw + b"\r\n")
    return b"".join(encoded)


def _read_line(sock: socket.socket) -> bytes:
    chunks = bytearray()
    while not chunks.endswith(b"\r\n"):
        chunk = sock.recv(1)
        if not chunk:
            raise RuntimeError("redis_connection_closed")
        chunks.extend(chunk)
    return bytes(chunks[:-2])


def _read_resp(sock: socket.socket) -> bytes | int | None:
    prefix = sock.recv(1)
    if prefix == b"+":
        return _read_line(sock)
    if prefix == b":":
        return int(_read_line(sock))
    if prefix == b"$":
        size = int(_read_line(sock))
        if size == -1:
            return None
        data = bytearray()
        while len(data) < size + 2:
            chunk = sock.recv(size + 2 - len(data))
            if not chunk:
                raise RuntimeError("redis_connection_closed")
            data.extend(chunk)
        return bytes(data[:size])
    if prefix == b"-":
        raise RuntimeError(_read_line(sock).decode("utf-8"))
    raise RuntimeError("redis_response_invalid")


def tcp_ready(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


def write_json(handler: BaseHTTPRequestHandler, status: int, payload: Mapping[str, Any]) -> None:
    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    handler.send_response(status)
    handler.send_header("content-type", "application/json")
    handler.send_header("content-length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def metrics(role: str, service: RuntimeActionService) -> bytes:
    state = service.state()["state"]
    lines = [
        "# HELP p174_service_up Service health reported by the local P174 lab process.",
        "# TYPE p174_service_up gauge",
        f'p174_service_up{{service="{role}"}} 1',
        "# HELP p174_uptime_seconds Service uptime in seconds.",
        "# TYPE p174_uptime_seconds gauge",
        f'p174_uptime_seconds{{service="{role}"}} {time.time() - STARTED_AT:.3f}',
        "# HELP p174_queue_depth Shared Redis queue backlog depth.",
        "# TYPE p174_queue_depth gauge",
        f'p174_queue_depth{{service="{role}"}} {state["queue_depth"]}',
        "# HELP p174_pool_size Shared runtime pool size.",
        "# TYPE p174_pool_size gauge",
        f'p174_pool_size{{service="{role}"}} {state["pool_size"]}',
    ]
    for name in ("requests_total", "worker_jobs_total", "action_requests_total", "action_rejected_total", "rollback_requests_total", "loadgen_requests_total", "loadgen_errors_total"):
        lines.extend([f"# HELP p174_{name} P174 lab counter.", f"# TYPE p174_{name} counter", f'p174_{name}{{service="{role}"}} {state[name]}'])
    return ("\n".join(lines) + "\n").encode("utf-8")


class ServiceHandler(BaseHTTPRequestHandler):
    server_version = "opscat-p174"
    p174_role: str
    p174_service: RuntimeActionService

    def do_GET(self) -> None:
        role = str(self.server.p174_role)  # type: ignore[attr-defined]
        service = cast(RuntimeActionService, self.server.p174_service)  # type: ignore[attr-defined]
        if self.path in {"/health", "/state"}:
            payload = service.state()
            payload["role"] = role
            payload["uptime_seconds"] = round(time.time() - STARTED_AT, 3)
            if role == "api":
                payload["postgres_tcp"] = tcp_ready(os.environ.get("POSTGRES_HOST", "postgres"), 5432)
                payload["redis_tcp"] = tcp_ready(os.environ.get("REDIS_HOST", "redis"), 6379)
            write_json(self, 200, payload)
            return
        if self.path == "/metrics":
            body = metrics(role, service)
            self.send_response(200)
            self.send_header("content-type", "text/plain; version=0.0.4")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.startswith("/work"):
            write_json(self, 200, service.enqueue_work())
            return
        write_json(self, 404, {"error": "not_found"})

    def do_POST(self) -> None:
        role = str(self.server.p174_role)  # type: ignore[attr-defined]
        service = cast(RuntimeActionService, self.server.p174_service)  # type: ignore[attr-defined]
        if role != "fault-controller" or self.path not in {"/actions", "/actions/rollback", "/faults", "/faults/cleanup"}:
            write_json(self, 404, {"error": "not_found"})
            return
        try:
            payload = self._read_payload()
            headers = {
                "X-P174-Capability": self.headers.get("X-P174-Capability", ""),
                "X-P174-Fault-Capability": self.headers.get("X-P174-Fault-Capability", ""),
                "X-P174-Lease-Expires": self.headers.get("X-P174-Lease-Expires", ""),
            }
            if self.path == "/actions":
                write_json(self, 202, service.submit_action(payload, headers))
            elif self.path == "/actions/rollback":
                write_json(self, 202, service.rollback_action(payload, headers))
            elif self.path == "/faults":
                write_json(self, 202, service.submit_fault(payload, headers))
            else:
                write_json(self, 202, service.cleanup_fault(payload, headers))
        except ValidationError as exc:
            state = service.record_rejection()
            write_json(self, 400, {"accepted": False, "status": "rejected", "reason": str(exc), "state": service._public_state(state), "metrics": service._metrics_from_state(state)})
        except json.JSONDecodeError:
            service.record_rejection()
            write_json(self, 400, {"accepted": False, "status": "rejected", "reason": "invalid_json"})

    def _read_payload(self) -> dict[str, Any]:
        size = min(int(self.headers.get("content-length", "0")), 8192)
        payload = json.loads(self.rfile.read(size) or b"{}")
        if not isinstance(payload, dict):
            raise ValidationError("payload_must_be_object")
        return cast(dict[str, Any], payload)

    def log_message(self, fmt: str, *args: object) -> None:
        print(json.dumps({"ts": time.time(), "component": self.server_version, "message": fmt % args}), flush=True)


def make_service() -> RuntimeActionService:
    store = RedisCausalStore(os.environ.get("REDIS_HOST", "redis"), int(os.environ.get("REDIS_PORT", "6379")))
    return RuntimeActionService(
        store,
        project_id=os.environ.get("P174_PROJECT_ID", "p174-project"),
        target_id=os.environ.get("P174_TARGET_ID", "target-a"),
        run_id=os.environ.get("P174_RUN_ID", "run-1"),
        policy_version=os.environ.get("P174_POLICY_VERSION", "p174-policy-v1"),
        capability=os.environ.get("P174_ACTION_CAPABILITY", "p174-local-capability-0000000000000000"),
        fault_capability=os.environ.get("P174_FAULT_CAPABILITY", "p174-local-fault-capability-00000000000000"),
    )


def serve(role: str, port: int, service: RuntimeActionService) -> None:
    server = ThreadingHTTPServer(("0.0.0.0", port), ServiceHandler)
    server.p174_role = role  # type: ignore[attr-defined]
    server.p174_service = service  # type: ignore[attr-defined]
    print(json.dumps({"ts": time.time(), "event": "started", "role": role, "port": port}), flush=True)
    server.serve_forever()


def worker_loop(service: RuntimeActionService) -> None:
    while True:
        processed = service.process_worker_batch()
        print(json.dumps({"ts": time.time(), "event": "worker_tick", "processed": processed, "queue_depth": service.state()["metrics"]["queue_depth"]}), flush=True)
        time.sleep(1.0)


def loadgen_loop(service: RuntimeActionService) -> None:
    interval = float(os.environ.get("REQUEST_INTERVAL_SECONDS", "0.5"))
    while True:
        try:
            service.enqueue_work()
            service.record_loadgen_result(accepted=True)
            with open("/tmp/loadgen.healthy", "w", encoding="utf-8") as handle:
                handle.write(str(time.time()))
        except (OSError, RuntimeError):
            service.record_loadgen_result(accepted=False)
        time.sleep(interval)


def main() -> None:
    role = os.environ.get("P174_ROLE", "api")
    service = make_service()
    if role == "api":
        serve(role, 8000, service)
    if role == "worker":
        threading.Thread(target=worker_loop, args=(service,), daemon=True).start()
        serve(role, 8010, service)
    if role == "fault-controller":
        serve(role, 8020, service)
    if role == "loadgen":
        loadgen_loop(service)
    raise SystemExit(f"unknown P174_ROLE: {role}")


if __name__ == "__main__":
    main()
