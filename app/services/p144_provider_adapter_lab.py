"""Numeric-loopback provider adapter conformance lab for P143 projections."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import socket
import stat
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services import p142_loopback_transport_lab as p142
from app.services import p143_egress_contract_lab as p143
from app.services.p110_evaluation import stable_hash

CONFIG_SCHEMA_VERSION = "p144.adapter_config.v1"
REQUEST_SCHEMA_VERSION = "p144.adapter_request.v1"
ATTEMPT_SCHEMA_VERSION = "p144.adapter_attempt.v1"
RECEIPT_SCHEMA_VERSION = "p144.adapter_receipt.v1"
RUN_SCHEMA_VERSION = "p144.adapter_run.v1"
JOURNAL_SCHEMA_VERSION = "p144.adapter_journal_entry.v1"
EXPECTED_P143_STATUS = "p143_provider_neutral_egress_contract_lab_qualified"
EXPECTED_P143_EVIDENCE_HASH = "sha256:a791376fe892fd9d31474e6cc007410687f2ece4da4eae096e23c0a6bfe0e1a8"
EXPECTED_P142_STATUS = "p142_loopback_transport_lab_qualified"
EXPECTED_P142_EVIDENCE_HASH = "sha256:3e952653a335da77ca6ce5f9cc7d6dcb9b39299afc7324c016fe8446f5c7f8e6"
EXPECTED_P141_STATUS = "p141_notification_authority_simulator_qualified"
EXPECTED_P141_EVIDENCE_HASH = "sha256:f3298f1295515b89e5374a449e9deb29fbd70f7c2a1e09446b80d9279d73d3b2"
EXPECTED_P133_STATUS = "p133_local_deadman_outbox_qualified"
EXPECTED_P133_EVIDENCE_HASH = "sha256:ba47502a7b82cea2521c581716801563f4ea31746cc243dfbbbd639707ffe73f"
FIXED_METHOD = "POST"
FIXED_PATH = "/opscat/provider-adapter/v1/deliveries"
FIXED_APPLICATION_HEADER_NAMES: tuple[str, ...] = (
    "content-type",
    "content-length",
    "idempotency-key",
    "x-opscat-delivery-id",
    "x-opscat-attempt-id",
    "x-opscat-schema",
)
REQUEST_CORE_FIELDS: tuple[str, ...] = (
    "schema_version",
    "delivery_id",
    "source_id",
    "intent_id",
    "projection_id",
    "channel_type",
    "idempotency_key",
    "dedupe_key",
    "body_sha256",
    "body_bytes",
    "p143_source_bindings",
    "receiver_capability_hash",
    "dependency_bindings_hash",
)
ADAPTER_COUNTER_KEYS: tuple[str, ...] = (
    "adapter_request_prepare_count",
    "adapter_request_write_count",
    "adapter_attempt_prepare_count",
    "provider_response_classification_count",
    "retry_schedule_count",
    "terminal_receipt_write_count",
    "replay_journal_entry_count",
    "schema_rejection_count",
    "conflict_rejection_count",
)
TRANSPORT_COUNTER_KEYS: tuple[str, ...] = p142.TRANSPORT_COUNTER_KEYS
FORBIDDEN_COUNTER_KEYS: tuple[str, ...] = (
    "credential_read_count",
    "authentication_attempt_count",
    "environment_read_count",
    "external_dns_resolution_count",
    "dns_socket_call_count",
    "non_loopback_socket_attempt_count",
    "unix_socket_attempt_count",
    "tls_handshake_count",
    "proxy_use_count",
    "redirect_follow_count",
    "provider_sdk_call_count",
    "provider_auth_material_count",
    "provider_endpoint_config_count",
    "provider_callback_count",
    "external_http_request_count",
    "external_message_send_count",
    "production_delivery_count",
    "p133_ack_write_count",
    "approval_count",
    "action_execution_count",
    "remediation_execution_count",
    "ticket_creation_count",
    "staging_mutation_count",
    "production_mutation_count",
    "operator_replacement_count",
    "subprocess_shell_count",
    "arbitrary_command_execution_count",
)

_CONFIG_FIELDS = frozenset(
    {
        "schema_version",
        "workspace_root",
        "p143_artifact_root",
        "p142_artifact_root",
        "state_root",
        "adapter_root",
        "journal_root",
        "receipt_root",
        "cursor_path",
        "lease_path",
        "max_sources_per_run",
        "max_attempts_per_delivery",
        "max_request_bytes",
        "max_response_bytes",
        "max_total_bytes_per_run",
        "max_elapsed_ms_per_delivery",
        "max_retry_after_ms",
        "connect_timeout_ms",
        "read_timeout_ms",
    }
)
_FORBIDDEN_FIELD_WORDS = frozenset(
    {
        "action",
        "ack",
        "approval",
        "auth",
        "callback",
        "certificate",
        "command",
        "cookie",
        "credential",
        "dns",
        "endpoint",
        "environment",
        "header",
        "host",
        "method",
        "mutation",
        "password",
        "provider",
        "proxy",
        "remediation",
        "sdk",
        "secret",
        "shell",
        "staging",
        "ticket",
        "tls",
        "token",
        "url",
    }
)
_UNSAFE_VALUE_RE = re.compile(
    r"(?:https?://|wss?://|localhost|@|\$\{|\b(?:api[-_]?key|auth|bearer|cookie|credential|dns|endpoint|env|host|password|provider|proxy|secret|sdk|tls|token|url|webhook)\b)",
    re.IGNORECASE,
)
_ID_RE = re.compile(r"[a-z0-9][a-z0-9._:-]{0,127}\Z")
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_RECEIPT_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
_HTTP_HEADER_NAME_RE = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+\Z")
_CHANNELS = frozenset({"chat_message", "email_message", "pager_event", "incident_comment"})
_CLASSIFICATIONS = frozenset(
    {
        "accepted",
        "duplicate_accepted",
        "permanent_failure",
        "transient_failure",
        "redirect_rejected",
        "malformed_response",
        "oversized_response",
        "truncated_response",
        "connection_failure",
        "timeout",
        "indeterminate_requires_review",
    }
)
_RETRY_DECISIONS = frozenset({"not_eligible", "scheduled", "budget_exhausted", "requires_review"})
_MEASURED_ADAPTER_COUNTERS: dict[str, int] = {key: 0 for key in ADAPTER_COUNTER_KEYS}
_MEASURED_TRANSPORT_COUNTERS: dict[str, int] = {key: 0 for key in TRANSPORT_COUNTER_KEYS}


class ProviderAdapterError(ValueError):
    """Raised when P144 cannot prove its no-authority numeric-loopback boundary."""


class _DuplicateJsonKey(ValueError):
    pass


@dataclass(frozen=True)
class ReceiverCapability:
    family: int
    packed_address: bytes
    port: int
    owner_pid: int
    socket_identity: tuple[int, int, int]
    nonce: bytes
    _socket: socket.socket

    def __getstate__(self) -> object:
        raise TypeError("receiver_capability_not_serializable")


@dataclass(frozen=True)
class AdapterConfig:
    schema_version: str
    config_hash: str
    workspace_root: Path
    p143_artifact_root: Path
    p142_artifact_root: Path
    state_root: Path
    adapter_root: Path
    journal_root: Path
    receipt_root: Path
    cursor_path: Path
    lease_path: Path
    max_sources_per_run: int
    max_attempts_per_delivery: int
    max_request_bytes: int
    max_response_bytes: int
    max_total_bytes_per_run: int
    max_elapsed_ms_per_delivery: int
    max_retry_after_ms: int
    connect_timeout_ms: int
    read_timeout_ms: int
    writable_roots: tuple[Path, ...]


def canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def zero_adapter_counters() -> dict[str, int]:
    return {key: 0 for key in ADAPTER_COUNTER_KEYS}


def zero_transport_counters() -> dict[str, int]:
    return {key: 0 for key in TRANSPORT_COUNTER_KEYS}


def zero_forbidden_counters() -> dict[str, int]:
    return {key: 0 for key in FORBIDDEN_COUNTER_KEYS}


def reset_measured_counters() -> None:
    _MEASURED_ADAPTER_COUNTERS.update(zero_adapter_counters())
    _MEASURED_TRANSPORT_COUNTERS.update(zero_transport_counters())


def record_measured_counters(adapter: Mapping[str, Any], transport: Mapping[str, Any]) -> None:
    if not _counter_map(adapter, ADAPTER_COUNTER_KEYS, exact_zero=False):
        raise ProviderAdapterError("adapter_counters_invalid")
    if not _counter_map(transport, TRANSPORT_COUNTER_KEYS, exact_zero=False):
        raise ProviderAdapterError("transport_counters_invalid")
    _MEASURED_ADAPTER_COUNTERS.update({key: int(adapter[key]) for key in ADAPTER_COUNTER_KEYS})
    _MEASURED_TRANSPORT_COUNTERS.update({key: int(transport[key]) for key in TRANSPORT_COUNTER_KEYS})


def measured_adapter_counters() -> dict[str, int]:
    return dict(_MEASURED_ADAPTER_COUNTERS)


def measured_transport_counters() -> dict[str, int]:
    return dict(_MEASURED_TRANSPORT_COUNTERS)


def issue_receiver_capability(listener: socket.socket) -> ReceiverCapability:
    family = listener.family
    if family not in {socket.AF_INET, socket.AF_INET6}:
        raise ProviderAdapterError("unix_socket_rejected")
    address = listener.getsockname()[0]
    port = int(listener.getsockname()[1])
    parsed = ipaddress.ip_address(address)
    if str(parsed) not in {"127.0.0.1", "::1"}:
        raise ProviderAdapterError("non_loopback_receiver")
    fileno = listener.fileno()
    if fileno < 0:
        raise ProviderAdapterError("receiver_not_live")
    stat_result = os.fstat(fileno)
    return ReceiverCapability(
        family=family,
        packed_address=socket.inet_pton(family, str(parsed)),
        port=port,
        owner_pid=os.getpid(),
        socket_identity=(stat_result.st_dev, stat_result.st_ino, fileno),
        nonce=os.urandom(16),
        _socket=listener,
    )


def receiver_capability_hash(capability: ReceiverCapability) -> str:
    _validate_receiver_capability(capability)
    return stable_hash(
        {
            "family": "inet6" if capability.family == socket.AF_INET6 else "inet4",
            "address_sha256": hashlib.sha256(capability.packed_address).hexdigest(),
            "port": capability.port,
            "owner_pid": capability.owner_pid,
            "socket_identity": list(capability.socket_identity),
            "nonce_sha256": hashlib.sha256(capability.nonce).hexdigest(),
        }
    )


def load_adapter_config(path: Path | str) -> AdapterConfig:
    config_path = Path(path).resolve()
    _reject_symlink_components(config_path)
    raw = _read_json(config_path, "configuration")
    if set(raw) != _CONFIG_FIELDS:
        unknown = set(raw) - _CONFIG_FIELDS
        if any(_field_forbidden(str(item)) for item in unknown):
            raise ProviderAdapterError("forbidden_configuration_field")
        raise ProviderAdapterError("invalid_configuration_fields")
    if raw.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise ProviderAdapterError("invalid_configuration_schema")
    _reject_unsafe_values(raw)
    workspace_root = _resolve(config_path.parent, raw["workspace_root"])
    p143_root = _resolve(workspace_root, raw["p143_artifact_root"])
    p142_root = _resolve(workspace_root, raw["p142_artifact_root"])
    state_root = _resolve(workspace_root, raw["state_root"])
    adapter_root = _resolve(workspace_root, raw["adapter_root"])
    journal_root = _resolve(workspace_root, raw["journal_root"])
    receipt_root = _resolve(workspace_root, raw["receipt_root"])
    cursor_path = _resolve(workspace_root, raw["cursor_path"])
    lease_path = _resolve(workspace_root, raw["lease_path"])
    for candidate in (workspace_root, p143_root, p142_root, state_root, adapter_root, journal_root, receipt_root, cursor_path, lease_path):
        _reject_symlink_components(candidate)
    if not p143_root.is_dir() or not p142_root.is_dir():
        raise ProviderAdapterError("dependency_root_missing")
    writable_roots = _distinct_roots((adapter_root, journal_root, receipt_root, cursor_path, lease_path))
    read_roots = (p143_root, p142_root)
    if any(_overlaps(read_root, write_root) for read_root in read_roots for write_root in writable_roots):
        raise ProviderAdapterError("read_write_root_overlap")
    for root in writable_roots:
        root.mkdir(parents=True, exist_ok=True)
        _require_safe_directory(root, "writable_root", boundary=workspace_root)
    budgets = {key: _bounded_int(raw, key) for key in _BUDGET_BOUNDS}
    if budgets["max_retry_after_ms"] > budgets["max_elapsed_ms_per_delivery"]:
        raise ProviderAdapterError("inconsistent_budget")
    if budgets["connect_timeout_ms"] > budgets["max_elapsed_ms_per_delivery"] or budgets["read_timeout_ms"] > budgets["max_elapsed_ms_per_delivery"]:
        raise ProviderAdapterError("inconsistent_budget")
    if budgets["max_total_bytes_per_run"] < budgets["max_request_bytes"] + budgets["max_response_bytes"]:
        raise ProviderAdapterError("inconsistent_budget")
    return AdapterConfig(
        schema_version=CONFIG_SCHEMA_VERSION,
        config_hash=stable_hash(raw),
        workspace_root=workspace_root,
        p143_artifact_root=p143_root,
        p142_artifact_root=p142_root,
        state_root=state_root,
        adapter_root=adapter_root,
        journal_root=journal_root,
        receipt_root=receipt_root,
        cursor_path=cursor_path,
        lease_path=lease_path,
        writable_roots=writable_roots,
        **budgets,
    )


_BUDGET_BOUNDS = {
    "max_sources_per_run": (1, 256),
    "max_attempts_per_delivery": (1, 5),
    "max_request_bytes": (1024, 1_048_576),
    "max_response_bytes": (256, 65_536),
    "max_total_bytes_per_run": (2048, 16_777_216),
    "max_elapsed_ms_per_delivery": (10, 60_000),
    "max_retry_after_ms": (0, 60_000),
    "connect_timeout_ms": (1, 10_000),
    "read_timeout_ms": (1, 10_000),
}


def validate_adapter_config(config: AdapterConfig) -> dict[str, Any]:
    dependency_bindings(config)
    return {"status": "valid", "schema_version": config.schema_version, "config_hash": config.config_hash}


def dependency_bindings(config: AdapterConfig) -> dict[str, Any]:
    p143_evidence = _read_json(config.p143_artifact_root / "output/release-evidence.json", "p143_release_evidence")
    p142_evidence = _read_json(config.p142_artifact_root / "output/release-evidence.json", "p142_release_evidence")
    _require_self_hash(p143_evidence, "evidence_hash", "p143_release_evidence_hash_invalid")
    if p143_evidence.get("status") != EXPECTED_P143_STATUS or p143_evidence.get("evidence_hash") != EXPECTED_P143_EVIDENCE_HASH:
        raise ProviderAdapterError("p143_release_dependency_drift")
    _require_self_hash(p142_evidence, "evidence_hash", "p142_release_evidence_hash_invalid")
    if p142_evidence.get("status") != EXPECTED_P142_STATUS or p142_evidence.get("evidence_hash") != EXPECTED_P142_EVIDENCE_HASH:
        raise ProviderAdapterError("p142_release_dependency_drift")
    p143_dep = p143_evidence.get("dependency_bindings")
    p142_p141 = p142_evidence.get("p141_dependency")
    if not isinstance(p143_dep, Mapping) or not isinstance(p142_p141, Mapping):
        raise ProviderAdapterError("transitive_dependency_graph_invalid")
    expected_p142_binding = {
        "p142_status": p142_evidence.get("status"),
        "p142_evidence_hash": p142_evidence.get("evidence_hash"),
        "p142_matrix_hash": p142_evidence.get("matrix_hash"),
        "p142_freeze_manifest_hash": p142_evidence.get("freeze_manifest_hash"),
        "p142_final_review_hash": p142_evidence.get("final_review_hash"),
        "p141_dependency": dict(p142_p141),
    }
    if dict(p143_dep) != expected_p142_binding:
        raise ProviderAdapterError("transitive_dependency_graph_invalid")
    p143_p141 = p143_dep.get("p141_dependency")
    if p143_p141 != p142_p141:
        raise ProviderAdapterError("transitive_dependency_graph_invalid")

    _validate_frozen_release(config.p143_artifact_root, p143_evidence, p143_dep, "p143")
    _validate_frozen_release(config.p142_artifact_root, p142_evidence, p142_p141, "p142")
    eval_root = config.p142_artifact_root.parent
    p141_root = eval_root / "p141"
    p133_path = eval_root / "p133/release-evidence.json"
    p141_release = _read_json(p141_root / "output/release-evidence.json", "p141_release_evidence")
    p141_freeze = _read_json(p141_root / "output/freeze-manifest.json", "p141_freeze_manifest")
    p141_review = _read_json(p141_root / "final-implementation-review.json", "p141_final_review")
    p133_release = _read_json(p133_path, "p133_release_evidence")
    _require_self_hash(p141_release, "evidence_hash", "p141_release_evidence_hash_invalid")
    _require_self_hash(p141_freeze, "freeze_manifest_hash", "p141_freeze_manifest_hash_invalid")
    _require_self_hash(p141_review, "review_hash", "p141_review_hash_invalid")
    _require_self_hash(p133_release, "release_evidence_hash", "p133_release_evidence_hash_invalid")
    expected_p141 = {
        "p141_status": p141_release.get("status"),
        "p141_evidence_hash": p141_release.get("evidence_hash"),
        "p141_matrix_hash": p141_release.get("matrix_hash"),
        "p141_freeze_manifest_hash": p141_release.get("freeze_manifest_hash"),
        "p141_final_review_hash": p141_release.get("final_review_hash"),
    }
    if (
        dict(p142_p141) != expected_p141
        or p141_release.get("status") != EXPECTED_P141_STATUS
        or p141_release.get("evidence_hash") != EXPECTED_P141_EVIDENCE_HASH
        or p141_freeze.get("freeze_manifest_hash") != p141_release.get("freeze_manifest_hash")
        or p141_review.get("review_hash") != p141_release.get("final_review_hash")
        or p141_review.get("reviewed_freeze_manifest_hash") != p141_freeze.get("freeze_manifest_hash")
        or p141_review.get("reviewed_dependency_bindings") != p141_freeze.get("dependency_bindings")
    ):
        raise ProviderAdapterError("transitive_dependency_graph_invalid")
    p141_dependencies = p141_freeze.get("dependency_bindings")
    if not isinstance(p141_dependencies, Mapping):
        raise ProviderAdapterError("transitive_dependency_graph_invalid")
    p133_dependency = {
        "p133_status": p133_release.get("release_status"),
        "p133_evidence_hash": p133_release.get("release_evidence_hash"),
    }
    if (
        p133_dependency
        != {
            "p133_status": EXPECTED_P133_STATUS,
            "p133_evidence_hash": EXPECTED_P133_EVIDENCE_HASH,
        }
        or p141_dependencies.get("p133_status") != p133_dependency["p133_status"]
        or p141_dependencies.get("p133_evidence_hash") != p133_dependency["p133_evidence_hash"]
    ):
        raise ProviderAdapterError("transitive_p133_dependency_graph_invalid")
    return {
        "p143_status": p143_evidence["status"],
        "p143_evidence_hash": p143_evidence["evidence_hash"],
        "p143_matrix_hash": p143_evidence["matrix_hash"],
        "p143_freeze_manifest_hash": p143_evidence["freeze_manifest_hash"],
        "p143_final_review_hash": p143_evidence["final_review_hash"],
        "p142_status": p142_evidence["status"],
        "p142_evidence_hash": p142_evidence["evidence_hash"],
        "p142_matrix_hash": p142_evidence["matrix_hash"],
        "p142_freeze_manifest_hash": p142_evidence["freeze_manifest_hash"],
        "p142_final_review_hash": p142_evidence["final_review_hash"],
        "p143_p141_dependency": dict(p143_p141),
        "p142_p141_dependency": dict(p142_p141),
        "p141_dependency": dict(p142_p141),
        "p133_dependency": p133_dependency,
    }


def _validate_frozen_release(root: Path, evidence: Mapping[str, Any], dependency: Any, label: str) -> None:
    freeze = _read_json(root / "output/freeze-manifest.json", f"{label}_freeze_manifest")
    matrix = _read_json(root / "output/canonical-matrix.json", f"{label}_matrix")
    review = _read_json(root / "final-implementation-review.json", f"{label}_final_review")
    _require_self_hash(freeze, "freeze_manifest_hash", f"{label}_freeze_manifest_hash_invalid")
    _require_self_hash(matrix, "matrix_hash", f"{label}_matrix_hash_invalid")
    _require_self_hash(review, "review_hash", f"{label}_review_hash_invalid")
    if (
        evidence.get("matrix_hash") != matrix.get("matrix_hash")
        or evidence.get("freeze_manifest_hash") != freeze.get("freeze_manifest_hash")
        or evidence.get("final_review_hash") != review.get("review_hash")
        or freeze.get("matrix_hash") != matrix.get("matrix_hash")
        or freeze.get("dependency_bindings") != dependency
        or review.get("reviewed_freeze_manifest_hash") != freeze.get("freeze_manifest_hash")
        or review.get("reviewed_dependency_bindings") != dependency
    ):
        raise ProviderAdapterError("transitive_dependency_graph_invalid")


def _require_self_hash(value: Mapping[str, Any], field: str, error: str) -> None:
    if value.get(field) != stable_hash({key: item for key, item in value.items() if key != field}):
        raise ProviderAdapterError(error)


def prepare_adapter_request(
    config: AdapterConfig,
    projection: Mapping[str, Any],
    capability: ReceiverCapability,
    *,
    dependency_hash: str | None = None,
) -> dict[str, Any]:
    _validate_projection(projection)
    _validate_receiver_capability(capability)
    body = _body_from_projection(projection)
    body_bytes = canonical_json(body)
    if len(body_bytes) > config.max_request_bytes:
        raise ProviderAdapterError("request_size_exceeded_before_socket")
    capability_hash = receiver_capability_hash(capability)
    dependency_bindings_hash = dependency_hash or stable_hash(dependency_bindings(config))
    source_bindings = {
        "intent_id": projection["intent_id"],
        "intent_hash": projection["intent_hash"],
        "projection_id": projection["projection_id"],
        "projection_hash": projection["projection_hash"],
    }
    delivery_id = stable_hash(
        {
            "source_bindings": source_bindings,
            "body_sha256": "sha256:" + hashlib.sha256(body_bytes).hexdigest(),
            "receiver_capability_hash": capability_hash,
            "dependency_bindings_hash": dependency_bindings_hash,
        }
    )
    request_core: dict[str, Any] = {
        "schema_version": REQUEST_SCHEMA_VERSION,
        "delivery_id": delivery_id,
        "source_id": stable_hash({"projection_hash": projection["projection_hash"]}),
        "intent_id": projection["intent_id"],
        "projection_id": projection["projection_id"],
        "channel_type": projection["channel_type"],
        "idempotency_key": projection["payload"]["idempotency_key"],
        "dedupe_key": projection["payload"]["dedupe_key"],
        "body_sha256": "sha256:" + hashlib.sha256(body_bytes).hexdigest(),
        "body_bytes": body_bytes.decode("utf-8"),
        "p143_source_bindings": source_bindings,
        "receiver_capability_hash": capability_hash,
        "dependency_bindings_hash": dependency_bindings_hash,
    }
    request_binding_hash = compute_request_binding_hash(request_core)
    first_attempt_id = deterministic_attempt_id(delivery_id, request_binding_hash, 0)
    request = {
        **request_core,
        "request_binding_hash": request_binding_hash,
        "fixed_headers": _fixed_headers(delivery_id, first_attempt_id, request_core, body_bytes),
    }
    request["request_hash"] = stable_hash(request)
    _validate_adapter_request(request)
    return request


def compute_request_binding_hash(request: Mapping[str, Any]) -> str:
    if not set(REQUEST_CORE_FIELDS).issubset(request):
        raise ProviderAdapterError("request_core_fields_invalid")
    core = {key: request[key] for key in REQUEST_CORE_FIELDS}
    _validate_request_core(core)
    return stable_hash(core)


def deterministic_attempt_id(delivery_id: str, request_binding_hash: str, attempt_index: int) -> str:
    _hash_value(delivery_id, "delivery_id")
    _hash_value(request_binding_hash, "request_binding_hash")
    if type(attempt_index) is not int or attempt_index < 0:
        raise ProviderAdapterError("attempt_index_invalid")
    return stable_hash(
        {
            "p144_attempt": {
                "delivery_id": delivery_id,
                "request_binding_hash": request_binding_hash,
                "attempt_index": attempt_index,
            }
        }
    )


def encode_http_request(capability: ReceiverCapability, request: Mapping[str, Any], attempt_id: str) -> bytes:
    _validate_receiver_capability(capability)
    _validate_adapter_request(request)
    _hash_value(attempt_id, "attempt_id")
    address = socket.inet_ntop(capability.family, capability.packed_address)
    host = f"[{address}]:{capability.port}" if capability.family == socket.AF_INET6 else f"{address}:{capability.port}"
    headers = deepcopy(request["fixed_headers"])
    headers[4][1] = attempt_id
    lines = [
        f"{FIXED_METHOD} {FIXED_PATH} HTTP/1.1",
        f"host: {host}",
        "connection: close",
        *[f"{key}: {value}" for key, value in headers],
        "",
        "",
    ]
    return "\r\n".join(lines).encode("ascii") + str(request["body_bytes"]).encode("utf-8")


def classify_provider_response(
    status_code: int | None,
    headers: Mapping[str, str] | None,
    body: bytes,
    *,
    delivery_id: str,
    max_response_bytes: int,
    max_retry_after_ms: int,
    remaining_ms: int,
    wall_clock: datetime,
    truncated: bool = False,
) -> dict[str, Any]:
    safe_headers = _safe_response_headers(headers or {})
    if status_code is None:
        return _classification("connection_failure", "connection_failed", safe_headers)
    if truncated:
        return _classification("truncated_response", "response_truncated", safe_headers)
    if len(body) > max_response_bytes:
        return _classification("oversized_response", "response_size_exceeded", safe_headers)
    if 300 <= status_code <= 399:
        return _classification("redirect_rejected", "redirect_not_followed", safe_headers)
    parsed_body = _parse_fixture_body(body, status_code, delivery_id)
    if not parsed_body["valid"]:
        return _classification("malformed_response", parsed_body["reason"], safe_headers)
    retry_after = p142.parse_retry_after(safe_headers.get("retry-after"), wall_clock=wall_clock, max_retry_after_ms=max_retry_after_ms, remaining_ms=remaining_ms)
    if status_code in {200, 201, 202, 204}:
        return _classification("accepted", "accepted_status", safe_headers, provider_receipt_id=parsed_body["receipt_id"], retry_after=retry_after)
    if status_code in {208, 409} and parsed_body["result"] == "duplicate":
        return _classification(
            "duplicate_accepted",
            "duplicate_body_valid",
            safe_headers,
            provider_receipt_id=parsed_body["receipt_id"],
            duplicate_of=parsed_body["duplicate_of"],
            retry_after=retry_after,
        )
    if status_code in {400, 404, 405, 410, 413, 415, 422}:
        return _classification("permanent_failure", "permanent_status", safe_headers, retry_after=retry_after)
    if status_code in {408, 425, 429, 500, 502, 503, 504}:
        if safe_headers.get("retry-after") is not None and not retry_after["valid"]:
            return _classification("malformed_response", str(retry_after["reason"]), safe_headers, retry_after=retry_after)
        return _classification("transient_failure", "transient_status", safe_headers, retry_after=retry_after)
    return _classification("malformed_response", "unsupported_status", safe_headers, retry_after=retry_after)


def process_adapter_deliveries(
    config: AdapterConfig,
    capability: ReceiverCapability,
    *,
    wall_clock: Callable[[], datetime] | None = None,
    monotonic: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
    crash_after: str | None = None,
) -> dict[str, Any]:
    wall_clock = wall_clock or (lambda: datetime.now(UTC).replace(microsecond=0))
    monotonic = monotonic or (lambda: 0.0)
    sleep = sleep or (lambda _seconds: None)
    _validate_receiver_capability(capability)
    _ensure_output_dirs(config)
    with _run_lease(config):
        bindings = dependency_bindings(config)
        projections = _load_qualified_projections(config)
        candidates: list[tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]] = []
        for projection in projections:
            request = prepare_adapter_request(config, projection, capability, dependency_hash=stable_hash(bindings))
            entries = _load_journal_entries(config, str(request["delivery_id"]))
            if entries and entries[0].get("prepared_artifact") != request:
                raise ProviderAdapterError("journal_request_source_drift")
            if entries and entries[-1]["phase"] == "run_written":
                _validate_completed_delivery(config, request, entries)
                continue
            candidates.append((projection, request, entries))
        selected = candidates[: config.max_sources_per_run]
        if not selected:
            completed = _completed_run_from_cursor(config, projections, capability, bindings)
            record_measured_counters(completed["adapter_counters"], completed["transport_counters"])
            return completed

        results = [
            _process_delivery(
                config,
                capability,
                projection,
                request,
                entries,
                wall_clock=wall_clock,
                monotonic=monotonic,
                sleep=sleep,
                crash_after=crash_after,
            )
            for projection, request, entries in selected
        ]
        adapter_counters = zero_adapter_counters()
        transport_counters = zero_transport_counters()
        terminal_counts = {classification: 0 for classification in sorted(_CLASSIFICATIONS)}
        for result in results:
            _merge_counter_map(adapter_counters, result["adapter_counters"], ADAPTER_COUNTER_KEYS)
            _merge_counter_map(transport_counters, result["transport_counters"], TRANSPORT_COUNTER_KEYS)
            terminal_counts[str(result["receipt"]["terminal_classification"])] += 1
        delivery_ids = [str(result["request"]["delivery_id"]) for result in results]
        sources = [result["projection"] for result in results]
        prepared_runs = []
        for delivery_id in delivery_ids:
            entries = _load_journal_entries(config, delivery_id)
            if entries[-1]["phase"] == "run_prepared":
                prepared_runs.append(entries[-1]["prepared_artifact"])
        if prepared_runs:
            if any(item != prepared_runs[0] for item in prepared_runs):
                raise ProviderAdapterError("prepared_run_conflict")
            run = dict(prepared_runs[0])
            _validate_adapter_run(run)
        else:
            run = _adapter_run(config, sources, delivery_ids, terminal_counts, adapter_counters, transport_counters, bindings, wall_clock())
            for delivery_id in delivery_ids:
                _append_journal_entry(config, delivery_id, "run_prepared", prepared_artifact=run)
        run_path = config.adapter_root / f"{run['run_id'][7:]}.run.json"
        _write_bound_artifact(run_path, run, config, "run", crash_after=crash_after)
        for delivery_id in delivery_ids:
            entries = _load_journal_entries(config, delivery_id)
            if entries[-1]["phase"] == "run_prepared":
                _append_journal_entry(config, delivery_id, "run_written", prepared_artifact=run)
        record_measured_counters(run["adapter_counters"], run["transport_counters"])
        return run


def _process_delivery(
    config: AdapterConfig,
    capability: ReceiverCapability,
    projection: dict[str, Any],
    request: dict[str, Any],
    initial_entries: list[dict[str, Any]],
    *,
    wall_clock: Callable[[], datetime],
    monotonic: Callable[[], float],
    sleep: Callable[[float], None],
    crash_after: str | None,
) -> dict[str, Any]:
    delivery_id = str(request["delivery_id"])
    request_path = config.adapter_root / f"{delivery_id[7:]}.request.json"
    receipt_path = config.receipt_root / f"{delivery_id[7:]}.receipt.json"
    if not initial_entries:
        _append_journal_entry(config, delivery_id, "request_prepared", prepared_artifact=request)
    _write_bound_artifact(request_path, request, config, "request", crash_after=crash_after)
    start = monotonic()
    while True:
        entries = _load_journal_entries(config, delivery_id)
        attempts = _attempts_from_journal(config, entries)
        phase = str(entries[-1]["phase"])
        if phase == "request_prepared" or (phase == "attempt_written" and attempts[-1]["retry_decision"] == "scheduled"):
            attempt_index = len(attempts)
            if attempt_index >= config.max_attempts_per_delivery:
                raise ProviderAdapterError("attempt_budget_state_invalid")
            attempt_id = deterministic_attempt_id(delivery_id, str(request["request_binding_hash"]), attempt_index)
            wire = encode_http_request(capability, request, attempt_id)
            _append_journal_entry(
                config,
                delivery_id,
                "attempt_prepared",
                attempt_index=attempt_index,
                attempt_id=attempt_id,
                request_bytes_sha256=_bytes_sha256(wire),
                prepared_artifact={
                    "attempt_id": attempt_id,
                    "attempt_index": attempt_index,
                    "request_binding_hash": request["request_binding_hash"],
                    "request_hash": request["request_hash"],
                },
            )
            continue
        if phase == "attempt_prepared":
            context = entries[-1]
            started_at = _timestamp(wall_clock())
            _append_journal_entry(
                config,
                delivery_id,
                "attempt_started",
                attempt_index=int(context["attempt_index"]),
                attempt_id=str(context["attempt_id"]),
                request_bytes_sha256=context["request_bytes_sha256"],
                prepared_artifact={"started_at": started_at, "transport_counters": zero_transport_counters()},
            )
            if crash_after == "attempt_started":
                raise RuntimeError("injected_crash:attempt_started")
            continue
        if phase == "attempt_started":
            _send_once_and_journal(config, capability, request, entries[-1], wall_clock=wall_clock, crash_after=crash_after)
            continue
        if phase == "request_committed":
            context = entries[-1]
            prepared = _mapping(context["prepared_artifact"], "request_committed_artifact")
            counters = dict(_mapping(prepared.get("transport_counters"), "request_committed_counters"))
            counters["loopback_transport_failure_count"] += 1
            classification = _classification("indeterminate_requires_review", "request_committed_response_unknown", {})
            _append_journal_entry(
                config,
                delivery_id,
                "transport_completed",
                attempt_index=int(context["attempt_index"]),
                attempt_id=str(context["attempt_id"]),
                request_bytes_sha256=context["request_bytes_sha256"],
                committed_request_bytes=int(context["committed_request_bytes"]),
                prepared_artifact={
                    "started_at": prepared["started_at"],
                    "completed_at": _timestamp(wall_clock()),
                    "classification": classification,
                    "transport_counters": counters,
                },
            )
            continue
        if phase == "transport_completed":
            context = entries[-1]
            prepared = _mapping(context["prepared_artifact"], "transport_completed_artifact")
            classification = dict(_mapping(prepared.get("classification"), "transport_classification"))
            counters = dict(_mapping(prepared.get("transport_counters"), "transport_counters"))
            retry_decision = _retry_decision(classification, int(context["attempt_index"]), config, start, monotonic())
            attempt = _adapter_attempt(
                request,
                str(context["attempt_id"]),
                int(context["attempt_index"]),
                classification,
                retry_decision,
                counters,
                str(prepared["started_at"]),
                str(prepared["completed_at"]),
            )
            _append_journal_entry(
                config,
                delivery_id,
                "attempt_written",
                attempt_index=int(context["attempt_index"]),
                attempt_id=str(context["attempt_id"]),
                request_bytes_sha256=context["request_bytes_sha256"],
                committed_request_bytes=int(context["committed_request_bytes"]),
                response_sha256=context["response_sha256"],
                prepared_artifact=attempt,
            )
            _write_bound_artifact(config.adapter_root / f"{attempt['attempt_id'][7:]}.attempt.json", attempt, config, "attempt", crash_after=crash_after)
            if retry_decision == "scheduled":
                retry_after = classification.get("retry_after")
                delay_ms = retry_after.get("delay_ms") if isinstance(retry_after, Mapping) else None
                sleep(int(delay_ms or 0) / 1000)
            continue
        if phase == "attempt_written":
            attempt = dict(_mapping(entries[-1]["prepared_artifact"], "attempt_artifact"))
            _write_bound_artifact(config.adapter_root / f"{attempt['attempt_id'][7:]}.attempt.json", attempt, config, "attempt")
            if attempt["retry_decision"] == "scheduled":
                continue
            classification = _classification_for_attempt(entries, str(attempt["attempt_id"]))
            receipt = _adapter_receipt(request, attempts, classification)
            _append_journal_entry(config, delivery_id, "receipt_prepared", prepared_artifact=receipt)
            continue
        if phase == "receipt_prepared":
            receipt = dict(_mapping(entries[-1]["prepared_artifact"], "receipt_artifact"))
            _write_bound_artifact(receipt_path, receipt, config, "receipt", crash_after=crash_after)
            _append_journal_entry(config, delivery_id, "receipt_written", prepared_artifact=receipt)
            continue
        if phase == "receipt_written":
            receipt = dict(_mapping(entries[-1]["prepared_artifact"], "receipt_artifact"))
            _write_bound_artifact(receipt_path, receipt, config, "receipt")
            cursor = _adapter_cursor(delivery_id)
            prior_bytes_sha256 = _bytes_sha256(config.cursor_path.read_bytes()) if config.cursor_path.exists() else None
            _append_journal_entry(
                config,
                delivery_id,
                "cursor_prepared",
                prepared_artifact={"artifact": cursor, "prior_bytes_sha256": prior_bytes_sha256},
            )
            continue
        if phase == "cursor_prepared":
            prepared = _mapping(entries[-1]["prepared_artifact"], "cursor_artifact")
            cursor = dict(_mapping(prepared.get("artifact"), "cursor"))
            _write_prepared_cursor(config, cursor, prepared.get("prior_bytes_sha256"), crash_after=crash_after)
            _append_journal_entry(config, delivery_id, "cursor_written", prepared_artifact=cursor)
            continue
        if phase in {"cursor_written", "run_prepared", "run_written"}:
            receipt_entry = next(entry for entry in reversed(entries) if entry["phase"] == "receipt_written")
            receipt = dict(_mapping(receipt_entry["prepared_artifact"], "receipt_artifact"))
            adapter_counters, transport_counters = _delivery_counters(entries, len(initial_entries))
            return {
                "projection": projection,
                "request": request,
                "receipt": receipt,
                "adapter_counters": adapter_counters,
                "transport_counters": transport_counters,
            }
        raise ProviderAdapterError("invalid_journal_recovery_state")


def list_adapter_receipts(config: AdapterConfig) -> list[dict[str, Any]]:
    receipts = [_read_json(path, "receipt") for path in sorted(config.receipt_root.glob("*.receipt.json"))]
    for receipt in receipts:
        _validate_adapter_receipt(receipt)
    return receipts


def _send_once_and_journal(
    config: AdapterConfig,
    capability: ReceiverCapability,
    request: Mapping[str, Any],
    started_entry: Mapping[str, Any],
    *,
    wall_clock: Callable[[], datetime],
    crash_after: str | None,
) -> None:
    counters = zero_transport_counters()
    sock: socket.socket | None = None
    committed = False
    raw = b""
    classification: dict[str, Any]
    try:
        sock = socket.socket(capability.family, socket.SOCK_STREAM)
        counters["loopback_socket_attempt_count"] += 1
        sock.settimeout(config.connect_timeout_ms / 1000)
        target = _socket_target(capability)
        sock.connect(target)
        wire = encode_http_request(capability, request, str(started_entry["attempt_id"]))
        if _bytes_sha256(wire) != started_entry.get("request_bytes_sha256"):
            raise ProviderAdapterError("prepared_request_bytes_conflict")
        sock.settimeout(config.read_timeout_ms / 1000)
        sock.sendall(wire)
        committed = True
        counters["loopback_request_commit_count"] += 1
        counters["loopback_request_byte_count"] += len(wire)
        started = _mapping(started_entry["prepared_artifact"], "attempt_started_artifact")["started_at"]
        _append_journal_entry(
            config,
            str(request["delivery_id"]),
            "request_committed",
            attempt_index=int(started_entry["attempt_index"]),
            attempt_id=str(started_entry["attempt_id"]),
            request_bytes_sha256=started_entry["request_bytes_sha256"],
            committed_request_bytes=len(wire),
            prepared_artifact={"started_at": started, "transport_counters": counters},
        )
        if crash_after == "request_committed":
            raise RuntimeError("injected_crash:request_committed")
        raw, overflow = _read_raw_response(sock, config.max_response_bytes, config.read_timeout_ms)
        counters["loopback_complete_response_count"] += 1
        counters["loopback_response_byte_count"] += min(len(raw), config.max_response_bytes)
        if overflow:
            classification = _classification("oversized_response", "response_size_exceeded", {})
            status = None
        else:
            status, headers, body = _parse_raw_response(raw)
            classification = classify_provider_response(
                status,
                headers,
                body,
                delivery_id=str(request["delivery_id"]),
                max_response_bytes=config.max_response_bytes,
                max_retry_after_ms=config.max_retry_after_ms,
                remaining_ms=config.max_elapsed_ms_per_delivery,
                wall_clock=wall_clock(),
            )
        if status is not None:
            if 200 <= status <= 299:
                counters["loopback_http_2xx_count"] += 1
            elif 300 <= status <= 399:
                counters["loopback_http_3xx_count"] += 1
            elif 400 <= status <= 499:
                counters["loopback_http_4xx_count"] += 1
            elif 500 <= status <= 599:
                counters["loopback_http_5xx_count"] += 1
    except RuntimeError:
        raise
    except TimeoutError:
        counters["loopback_transport_failure_count"] += 1
        classification = (
            _classification("indeterminate_requires_review", "request_committed_response_unknown", {})
            if committed
            else _classification("timeout", "socket_timeout", {})
        )
    except OSError:
        counters["loopback_transport_failure_count"] += 1
        classification = (
            _classification("indeterminate_requires_review", "request_committed_response_unknown", {})
            if committed
            else _classification("connection_failure", "connection_failed", {})
        )
    except ProviderAdapterError as exc:
        counters["loopback_transport_failure_count"] += 1
        reason = str(exc)
        if reason == "truncated_response":
            classification = _classification("truncated_response", "response_truncated", {})
        elif reason == "oversized_response":
            classification = _classification("oversized_response", "response_size_exceeded", {})
        else:
            classification = _classification("malformed_response", reason, {})
    finally:
        if sock is not None:
            sock.close()
    latest = _load_journal_entries(config, str(request["delivery_id"]))[-1]
    started_at = _mapping(started_entry["prepared_artifact"], "attempt_started_artifact")["started_at"]
    _append_journal_entry(
        config,
        str(request["delivery_id"]),
        "transport_completed",
        attempt_index=int(started_entry["attempt_index"]),
        attempt_id=str(started_entry["attempt_id"]),
        request_bytes_sha256=started_entry["request_bytes_sha256"],
        committed_request_bytes=int(latest["committed_request_bytes"]) if latest["phase"] == "request_committed" else 0,
        response_sha256=_bytes_sha256(raw) if raw else None,
        prepared_artifact={
            "started_at": started_at,
            "completed_at": _timestamp(wall_clock()),
            "classification": classification,
            "transport_counters": counters,
        },
    )
    if crash_after == "transport_completed":
        raise RuntimeError("injected_crash:transport_completed")


def _adapter_attempt(
    request: Mapping[str, Any],
    attempt_id: str,
    attempt_index: int,
    classification: Mapping[str, Any],
    retry_decision: str,
    transport_counters: Mapping[str, Any],
    started_at: str,
    completed_at: str,
) -> dict[str, Any]:
    attempt = {
        "schema_version": ATTEMPT_SCHEMA_VERSION,
        "delivery_id": request["delivery_id"],
        "attempt_id": attempt_id,
        "attempt_index": attempt_index,
        "request_hash": request["request_hash"],
        "started_at": started_at,
        "completed_at": completed_at,
        "transport_receipt_hash": stable_hash({"transport": transport_counters, "classification": classification}),
        "transport_counters": dict(transport_counters),
        "classification": classification["classification"],
        "retry_decision": retry_decision,
        "requires_review": classification["classification"] == "indeterminate_requires_review",
        "automatic_retry_allowed": retry_decision == "scheduled",
        "transport_failure_class": classification["terminal_reason"],
    }
    attempt["attempt_hash"] = stable_hash(attempt)
    _validate_adapter_attempt(attempt)
    return attempt


def _classification_for_attempt(entries: Sequence[Mapping[str, Any]], attempt_id: str) -> dict[str, Any]:
    for entry in reversed(entries):
        if entry.get("phase") == "transport_completed" and entry.get("attempt_id") == attempt_id:
            prepared = _mapping(entry.get("prepared_artifact"), "transport_completed_artifact")
            return dict(_mapping(prepared.get("classification"), "transport_classification"))
    raise ProviderAdapterError("transport_classification_missing")


def _adapter_receipt(request: Mapping[str, Any], attempts: Sequence[Mapping[str, Any]], classification: Mapping[str, Any]) -> dict[str, Any]:
    receipt = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "delivery_id": request["delivery_id"],
        "request_hash": request["request_hash"],
        "attempt_hashes": [attempt["attempt_hash"] for attempt in attempts],
        "terminal_classification": classification["classification"],
        "terminal_reason": classification["terminal_reason"],
        "provider_receipt_id": classification.get("provider_receipt_id"),
        "duplicate_of": classification.get("duplicate_of"),
        "requires_review": classification["classification"] == "indeterminate_requires_review",
        "automatic_retry_allowed": False,
        "transport_failure_class": classification["terminal_reason"],
        "production_delivered": False,
        "external_delivered": False,
    }
    receipt["receipt_hash"] = stable_hash(receipt)
    _validate_adapter_receipt(receipt)
    return receipt


def _adapter_run(
    config: AdapterConfig,
    sources: Sequence[Mapping[str, Any]],
    delivery_ids: Sequence[str],
    terminal_counts: Mapping[str, int],
    adapter_counters: Mapping[str, int],
    transport_counters: Mapping[str, int],
    bindings: Mapping[str, Any],
    now: datetime,
) -> dict[str, Any]:
    run = {
        "schema_version": RUN_SCHEMA_VERSION,
        "run_id": stable_hash({"p144_run": {"config_hash": config.config_hash, "delivery_ids": list(delivery_ids)}}),
        "started_at": _timestamp(now),
        "completed_at": _timestamp(now),
        "source_start": sources[0]["projection_id"] if sources else None,
        "source_end": sources[-1]["projection_id"] if sources else None,
        "processed_source_ids": [source["projection_id"] for source in sources],
        "delivery_ids": list(delivery_ids),
        "terminal_counts": dict(terminal_counts),
        "adapter_counters": dict(adapter_counters),
        "transport_counters": dict(transport_counters),
        "forbidden_counters": zero_forbidden_counters(),
        "dependency_bindings": dict(bindings),
    }
    run["run_hash"] = stable_hash(run)
    _validate_adapter_run(run)
    return run


def _classification(
    classification: str,
    reason: str,
    safe_headers: Mapping[str, str],
    *,
    provider_receipt_id: str | None = None,
    duplicate_of: str | None = None,
    retry_after: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if classification not in _CLASSIFICATIONS:
        raise ProviderAdapterError("invalid_classification")
    if provider_receipt_id is not None:
        _receipt_id(provider_receipt_id)
    if duplicate_of is not None:
        _hash_value(duplicate_of, "duplicate_of")
    return {
        "classification": classification,
        "terminal_reason": reason,
        "safe_headers": dict(safe_headers),
        "provider_receipt_id": provider_receipt_id,
        "duplicate_of": duplicate_of,
        "retry_after": dict(retry_after or {"present": False, "valid": False, "delay_ms": None, "reason": None}),
    }


def _retry_decision(classification: Mapping[str, Any], attempt_index: int, config: AdapterConfig, start: float, now: float) -> str:
    if classification["classification"] == "indeterminate_requires_review":
        return "requires_review"
    if classification["classification"] != "transient_failure":
        return "not_eligible"
    retry_after = classification.get("retry_after")
    if isinstance(retry_after, Mapping) and retry_after.get("present") and not retry_after.get("valid"):
        return "not_eligible"
    if attempt_index + 1 >= config.max_attempts_per_delivery:
        return "budget_exhausted"
    if int((now - start) * 1000) >= config.max_elapsed_ms_per_delivery:
        return "budget_exhausted"
    return "scheduled"


def _load_qualified_projections(config: AdapterConfig) -> list[dict[str, Any]]:
    p143_config = p143.load_egress_contract_config(config.p143_artifact_root / "config/p143.json")
    profile = p143._load_profile(p143_config)
    p143_sources = p143._load_sources(p143_config)
    journals = p143._load_all_journals(p143_config)
    p143._validate_existing_artifacts(p143_config, journals)
    p143._validate_expected_artifact_graph(p143_config, profile, p143_sources, journals)
    projections = [_read_json(path, "projection") for path in sorted(p143_config.projection_dir.glob("*.json"))]
    results = {result["projection_hash"]: result for result in p143.list_egress_results(p143_config)}
    qualified: list[dict[str, Any]] = []
    for projection in projections:
        _validate_projection(projection)
        result = results.get(projection["projection_hash"])
        if result is not None and result.get("compatible") is True:
            qualified.append(projection)
    if not qualified:
        raise ProviderAdapterError("qualified_projection_missing")
    return qualified


def _validate_projection(value: Mapping[str, Any]) -> None:
    required = {"schema_version", "projection_id", "intent_id", "intent_hash", "channel_type", "payload", "truncation", "rate_limit", "projection_hash"}
    if set(value) != required or value.get("schema_version") != p143.PROJECTION_SCHEMA_VERSION:
        raise ProviderAdapterError("invalid_projection_schema")
    if value.get("channel_type") not in _CHANNELS:
        raise ProviderAdapterError("unsupported_channel_type")
    if value.get("projection_hash") != stable_hash({key: item for key, item in value.items() if key != "projection_hash"}):
        raise ProviderAdapterError("projection_hash_invalid")
    payload = value.get("payload")
    if not isinstance(payload, Mapping):
        raise ProviderAdapterError("invalid_projection_payload")
    for key in ("idempotency_key", "dedupe_key"):
        _hash_value(payload.get(key), key)


def _body_from_projection(projection: Mapping[str, Any]) -> dict[str, Any]:
    payload = projection["payload"]
    body = {
        "schema_version": "p144.provider_adapter_body.v1",
        "projection_id": projection["projection_id"],
        "channel_type": projection["channel_type"],
        "title": payload.get("title"),
        "body": payload.get("body"),
        "severity": payload.get("severity"),
        "evidence_refs": list(payload.get("evidence_refs", [])),
    }
    _reject_unsafe_values(body)
    return body


def _fixed_headers(delivery_id: str, attempt_id: str, source: Mapping[str, Any], body: bytes) -> list[list[str]]:
    _hash_value(delivery_id, "delivery_id")
    _hash_value(attempt_id, "attempt_id")
    idempotency = source.get("idempotency_key") or source.get("payload", {}).get("idempotency_key")
    _hash_value(idempotency, "idempotency_key")
    return [
        ["content-type", "application/json"],
        ["content-length", str(len(body))],
        ["idempotency-key", str(idempotency)],
        ["x-opscat-delivery-id", delivery_id],
        ["x-opscat-attempt-id", attempt_id],
        ["x-opscat-schema", REQUEST_SCHEMA_VERSION],
    ]


def _validate_adapter_request(value: Mapping[str, Any]) -> None:
    required = set(REQUEST_CORE_FIELDS) | {
        "request_binding_hash",
        "fixed_headers",
        "request_hash",
    }
    if set(value) != required or value.get("schema_version") != REQUEST_SCHEMA_VERSION:
        raise ProviderAdapterError("invalid_request_schema")
    _validate_request_core({key: value[key] for key in REQUEST_CORE_FIELDS})
    binding_hash = compute_request_binding_hash(value)
    if value.get("request_binding_hash") != binding_hash:
        raise ProviderAdapterError("request_binding_hash_invalid")
    _hash_value(value.get("request_hash"), "request_hash")
    body_bytes = value["body_bytes"].encode("utf-8")
    first_attempt_id = deterministic_attempt_id(str(value["delivery_id"]), binding_hash, 0)
    expected_headers = _fixed_headers(str(value["delivery_id"]), first_attempt_id, value, body_bytes)
    headers = value.get("fixed_headers")
    if headers != expected_headers:
        raise ProviderAdapterError("fixed_headers_invalid")
    for _name, header_value in expected_headers:
        _header_value(header_value)
    if value.get("request_hash") != stable_hash({key: item for key, item in value.items() if key != "request_hash"}):
        raise ProviderAdapterError("request_hash_invalid")


def _validate_request_core(value: Mapping[str, Any]) -> None:
    if set(value) != set(REQUEST_CORE_FIELDS) or value.get("schema_version") != REQUEST_SCHEMA_VERSION:
        raise ProviderAdapterError("request_core_fields_invalid")
    for key in (
        "delivery_id",
        "source_id",
        "intent_id",
        "projection_id",
        "idempotency_key",
        "dedupe_key",
        "body_sha256",
        "receiver_capability_hash",
        "dependency_bindings_hash",
    ):
        _hash_value(value.get(key), key)
    if value.get("channel_type") not in _CHANNELS:
        raise ProviderAdapterError("invalid_channel_type")
    body_text = value.get("body_bytes")
    if not isinstance(body_text, str):
        raise ProviderAdapterError("request_body_invalid")
    body_bytes = body_text.encode("utf-8")
    if value.get("body_sha256") != "sha256:" + hashlib.sha256(body_bytes).hexdigest():
        raise ProviderAdapterError("request_body_hash_invalid")
    source = value.get("p143_source_bindings")
    if not isinstance(source, Mapping) or set(source) != {"intent_id", "intent_hash", "projection_id", "projection_hash"}:
        raise ProviderAdapterError("request_source_bindings_invalid")
    for key in ("intent_id", "intent_hash", "projection_id", "projection_hash"):
        _hash_value(source.get(key), key)
    if source.get("intent_id") != value.get("intent_id") or source.get("projection_id") != value.get("projection_id"):
        raise ProviderAdapterError("request_source_bindings_invalid")


def _validate_adapter_attempt(value: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "delivery_id",
        "attempt_id",
        "attempt_index",
        "request_hash",
        "started_at",
        "completed_at",
        "transport_receipt_hash",
        "transport_counters",
        "classification",
        "retry_decision",
        "requires_review",
        "automatic_retry_allowed",
        "transport_failure_class",
        "attempt_hash",
    }
    if set(value) != required or value.get("schema_version") != ATTEMPT_SCHEMA_VERSION:
        raise ProviderAdapterError("invalid_attempt_schema")
    if value.get("classification") not in _CLASSIFICATIONS or value.get("retry_decision") not in _RETRY_DECISIONS:
        raise ProviderAdapterError("attempt_classification_invalid")
    if type(value.get("attempt_index")) is not int or value["attempt_index"] < 0:
        raise ProviderAdapterError("attempt_index_invalid")
    for key in ("started_at", "completed_at"):
        _timestamp_string(value.get(key), key)
    if not _counter_map(value.get("transport_counters"), TRANSPORT_COUNTER_KEYS, exact_zero=False):
        raise ProviderAdapterError("transport_counters_invalid")
    if value.get("attempt_hash") != stable_hash({key: item for key, item in value.items() if key != "attempt_hash"}):
        raise ProviderAdapterError("attempt_hash_invalid")


def _validate_adapter_receipt(value: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "delivery_id",
        "request_hash",
        "attempt_hashes",
        "terminal_classification",
        "terminal_reason",
        "provider_receipt_id",
        "duplicate_of",
        "requires_review",
        "automatic_retry_allowed",
        "transport_failure_class",
        "production_delivered",
        "external_delivered",
        "receipt_hash",
    }
    if set(value) != required or value.get("schema_version") != RECEIPT_SCHEMA_VERSION:
        raise ProviderAdapterError("invalid_receipt_schema")
    if value.get("production_delivered") is not False or value.get("external_delivered") is not False:
        raise ProviderAdapterError("delivery_authority_invalid")
    if value.get("terminal_classification") not in _CLASSIFICATIONS:
        raise ProviderAdapterError("receipt_classification_invalid")
    if value.get("receipt_hash") != stable_hash({key: item for key, item in value.items() if key != "receipt_hash"}):
        raise ProviderAdapterError("receipt_hash_invalid")


def _validate_adapter_run(value: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "run_id",
        "started_at",
        "completed_at",
        "source_start",
        "source_end",
        "processed_source_ids",
        "delivery_ids",
        "terminal_counts",
        "adapter_counters",
        "transport_counters",
        "forbidden_counters",
        "dependency_bindings",
        "run_hash",
    }
    if set(value) != required or value.get("schema_version") != RUN_SCHEMA_VERSION:
        raise ProviderAdapterError("invalid_run_schema")
    if not _counter_map(value.get("adapter_counters"), ADAPTER_COUNTER_KEYS, exact_zero=False):
        raise ProviderAdapterError("adapter_counters_invalid")
    if not _counter_map(value.get("transport_counters"), TRANSPORT_COUNTER_KEYS, exact_zero=False):
        raise ProviderAdapterError("transport_counters_invalid")
    if not _counter_map(value.get("forbidden_counters"), FORBIDDEN_COUNTER_KEYS, exact_zero=True):
        raise ProviderAdapterError("forbidden_counters_invalid")
    if value.get("run_hash") != stable_hash({key: item for key, item in value.items() if key != "run_hash"}):
        raise ProviderAdapterError("run_hash_invalid")


def _parse_raw_response(raw: bytes) -> tuple[int | None, dict[str, str], bytes]:
    if b"\r\n\r\n" not in raw:
        raise ProviderAdapterError("malformed_response")
    head, body = raw.split(b"\r\n\r\n", 1)
    try:
        lines = head.decode("iso-8859-1").split("\r\n")
    except UnicodeDecodeError as exc:
        raise ProviderAdapterError("malformed_response") from exc
    parts = lines[0].split(" ", 2)
    if len(parts) < 2 or not parts[0].startswith("HTTP/1.") or not parts[1].isdigit():
        raise ProviderAdapterError("malformed_status")
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" not in line:
            raise ProviderAdapterError("malformed_headers")
        key, value = line.split(":", 1)
        if _HTTP_HEADER_NAME_RE.fullmatch(key) is None:
            raise ProviderAdapterError("malformed_headers")
        lower = key.lower()
        if lower == "transfer-encoding":
            raise ProviderAdapterError("transfer_encoding_forbidden")
        if lower in headers and lower in {"content-length", "transfer-encoding"}:
            raise ProviderAdapterError("duplicate_framing_header")
        headers[lower] = value.strip()
    length = headers.get("content-length")
    if length is not None:
        if not length.isdigit():
            raise ProviderAdapterError("malformed_headers")
        expected = int(length)
        if len(body) < expected:
            raise ProviderAdapterError("truncated_response")
        body = body[:expected]
    return int(parts[1]), headers, body


def _read_raw_response(sock: socket.socket, max_bytes: int, timeout_ms: int) -> tuple[bytes, bool]:
    sock.settimeout(timeout_ms / 1000)
    chunks = bytearray()
    truncated = False
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        chunks.extend(chunk)
        if len(chunks) > max_bytes + 8192:
            truncated = True
            break
    return bytes(chunks), truncated


def _parse_fixture_body(body: bytes, status_code: int, delivery_id: str) -> dict[str, Any]:
    if status_code == 204 or (400 <= status_code <= 599 and not body):
        return {"valid": True, "result": "rejected", "receipt_id": None, "duplicate_of": None}
    if len(body) > 4096:
        return {"valid": False, "reason": "fixture_body_too_large"}
    try:
        text = body.decode("utf-8")
        parsed = json.loads(text, object_pairs_hook=_strict_json_object)
    except _DuplicateJsonKey as exc:
        return {"valid": False, "reason": str(exc)}
    except Exception:
        return {"valid": False, "reason": "malformed_provider_json"}
    if not isinstance(parsed, Mapping) or parsed.get("schema_version") != "p144.fixture_response.v1":
        return {"valid": False, "reason": "invalid_fixture_schema"}
    if parsed.get("result") == "accepted" and set(parsed) == {"schema_version", "result", "receipt_id"}:
        return {"valid": True, "result": "accepted", "receipt_id": _receipt_id(parsed["receipt_id"]), "duplicate_of": None}
    if parsed.get("result") == "duplicate" and set(parsed) == {"schema_version", "result", "receipt_id", "duplicate_of"} and parsed.get("duplicate_of") == delivery_id:
        return {"valid": True, "result": "duplicate", "receipt_id": _receipt_id(parsed["receipt_id"]), "duplicate_of": parsed["duplicate_of"]}
    allowed_error_codes = {
        "invalid_payload",
        "unsupported_channel",
        "too_large",
        "throttled",
        "temporarily_unavailable",
        "internal_error",
    }
    if parsed.get("result") == "rejected" and set(parsed) == {"schema_version", "result", "error_code"} and parsed.get("error_code") in allowed_error_codes:
        return {"valid": True, "result": "rejected", "receipt_id": None, "duplicate_of": None}
    return {"valid": False, "reason": "invalid_fixture_body"}


def _safe_response_headers(headers: Mapping[str, str]) -> dict[str, str]:
    safe: dict[str, str] = {}
    for key in ("retry-after", "content-type", "content-length", "x-opscat-provider-receipt-id"):
        if key in headers:
            safe[key] = _header_value(str(headers[key]))
    return safe


def _validate_receiver_capability(capability: ReceiverCapability) -> None:
    if not isinstance(capability, ReceiverCapability):
        raise ProviderAdapterError("receiver_capability_required")
    if capability.owner_pid != os.getpid():
        raise ProviderAdapterError("receiver_not_process_owned")
    if capability.family not in {socket.AF_INET, socket.AF_INET6}:
        raise ProviderAdapterError("unix_socket_rejected")
    address = socket.inet_ntop(capability.family, capability.packed_address)
    if address not in {"127.0.0.1", "::1"}:
        raise ProviderAdapterError("non_loopback_receiver")
    if capability.port <= 0 or len(capability.nonce) != 16:
        raise ProviderAdapterError("receiver_capability_invalid")
    if capability._socket.fileno() != capability.socket_identity[2]:
        raise ProviderAdapterError("receiver_identity_drift")
    if capability._socket.fileno() < 0:
        raise ProviderAdapterError("receiver_not_live")
    current = os.fstat(capability._socket.fileno())
    if (current.st_dev, current.st_ino, capability._socket.fileno()) != capability.socket_identity:
        raise ProviderAdapterError("receiver_identity_drift")


def _socket_target(capability: ReceiverCapability) -> tuple[Any, ...]:
    address = socket.inet_ntop(capability.family, capability.packed_address)
    if capability.family == socket.AF_INET:
        return (address, capability.port)
    return (address, capability.port, 0, 0)


_JOURNAL_FIELDS = frozenset(
    {
        "schema_version",
        "delivery_id",
        "entry_index",
        "phase",
        "attempt_index",
        "attempt_id",
        "request_bytes_sha256",
        "committed_request_bytes",
        "response_sha256",
        "prepared_artifact",
        "prepared_artifact_bytes_sha256",
        "prior_entry_hash",
        "entry_hash",
    }
)
_JOURNAL_TRANSITIONS: dict[str | None, frozenset[str]] = {
    None: frozenset({"request_prepared"}),
    "request_prepared": frozenset({"attempt_prepared"}),
    "attempt_prepared": frozenset({"attempt_started"}),
    "attempt_started": frozenset({"request_committed", "transport_completed"}),
    "request_committed": frozenset({"transport_completed"}),
    "transport_completed": frozenset({"attempt_written"}),
    "attempt_written": frozenset({"attempt_prepared", "receipt_prepared"}),
    "receipt_prepared": frozenset({"receipt_written"}),
    "receipt_written": frozenset({"cursor_prepared"}),
    "cursor_prepared": frozenset({"cursor_written"}),
    "cursor_written": frozenset({"run_prepared"}),
    "run_prepared": frozenset({"run_written"}),
    "run_written": frozenset(),
}


def _append_journal_entry(
    config: AdapterConfig,
    delivery_id: str,
    phase: str,
    *,
    attempt_index: int | None = None,
    attempt_id: str | None = None,
    request_bytes_sha256: str | None = None,
    committed_request_bytes: int = 0,
    response_sha256: str | None = None,
    prepared_artifact: Mapping[str, Any],
) -> dict[str, Any]:
    entries = _load_journal_entries(config, delivery_id)
    prior = entries[-1] if entries else None
    if phase not in _JOURNAL_TRANSITIONS.get(prior["phase"] if prior else None, frozenset()):
        raise ProviderAdapterError("invalid_journal_transition")
    if prior is not None:
        attempt_index = attempt_index if attempt_index is not None else prior["attempt_index"]
        attempt_id = attempt_id if attempt_id is not None else prior["attempt_id"]
        request_bytes_sha256 = request_bytes_sha256 if request_bytes_sha256 is not None else prior["request_bytes_sha256"]
        committed_request_bytes = max(committed_request_bytes, int(prior["committed_request_bytes"]))
        response_sha256 = response_sha256 if response_sha256 is not None else prior["response_sha256"]
    artifact = dict(prepared_artifact)
    entry: dict[str, Any] = {
        "schema_version": JOURNAL_SCHEMA_VERSION,
        "delivery_id": delivery_id,
        "entry_index": len(entries),
        "phase": phase,
        "attempt_index": attempt_index,
        "attempt_id": attempt_id,
        "request_bytes_sha256": request_bytes_sha256,
        "committed_request_bytes": committed_request_bytes,
        "response_sha256": response_sha256,
        "prepared_artifact": artifact,
        "prepared_artifact_bytes_sha256": _bytes_sha256(canonical_json(artifact) + b"\n"),
        "prior_entry_hash": prior["entry_hash"] if prior else None,
    }
    entry["entry_hash"] = stable_hash(entry)
    name = f"{delivery_id[7:]}.{len(entries):04d}.{phase}.json"
    path = config.journal_root / name
    if path.exists() or path.is_symlink():
        raise ProviderAdapterError("append_only_journal_conflict")
    _atomic_write_json(path, entry, config.writable_roots)
    return entry


def _load_journal_entries(config: AdapterConfig, delivery_id: str) -> list[dict[str, Any]]:
    prefix = f"{delivery_id[7:]}."
    paths = sorted(path for path in config.journal_root.glob(f"{prefix}*.json") if not path.name.startswith("."))
    entries: list[dict[str, Any]] = []
    prior_hash: str | None = None
    prior_phase: str | None = None
    prior_attempt_index: int | None = None
    for index, path in enumerate(paths):
        entry = _read_json(path, "journal_entry")
        if set(entry) != _JOURNAL_FIELDS or entry.get("schema_version") != JOURNAL_SCHEMA_VERSION:
            raise ProviderAdapterError("invalid_journal_entry_schema")
        expected_name = f"{delivery_id[7:]}.{index:04d}.{entry.get('phase')}.json"
        if path.name != expected_name or entry.get("delivery_id") != delivery_id or entry.get("entry_index") != index:
            raise ProviderAdapterError("journal_entry_identity_invalid")
        phase = entry.get("phase")
        if not isinstance(phase, str) or phase not in _JOURNAL_TRANSITIONS.get(prior_phase, frozenset()):
            raise ProviderAdapterError("invalid_journal_transition")
        if entry.get("prior_entry_hash") != prior_hash:
            raise ProviderAdapterError("journal_hash_chain_invalid")
        artifact = entry.get("prepared_artifact")
        if not isinstance(artifact, Mapping) or entry.get("prepared_artifact_bytes_sha256") != _bytes_sha256(canonical_json(artifact) + b"\n"):
            raise ProviderAdapterError("prepared_artifact_bytes_invalid")
        if entry.get("entry_hash") != stable_hash({key: value for key, value in entry.items() if key != "entry_hash"}):
            raise ProviderAdapterError("journal_entry_hash_invalid")
        attempt_index = entry.get("attempt_index")
        if attempt_index is not None and (type(attempt_index) is not int or attempt_index < 0):
            raise ProviderAdapterError("journal_attempt_index_invalid")
        if phase == "attempt_prepared":
            expected_attempt = 0 if prior_attempt_index is None else prior_attempt_index + 1
            if attempt_index != expected_attempt:
                raise ProviderAdapterError("journal_attempt_index_invalid")
            prior_attempt_index = int(attempt_index)
        elif prior_attempt_index is not None and attempt_index != prior_attempt_index:
            raise ProviderAdapterError("journal_attempt_identity_invalid")
        if entry.get("attempt_id") is not None:
            if attempt_index is None:
                raise ProviderAdapterError("journal_attempt_identity_invalid")
            if entry.get("attempt_id") != deterministic_attempt_id(delivery_id, _journal_request_binding_hash(entries, entry), attempt_index):
                raise ProviderAdapterError("journal_attempt_identity_invalid")
        if type(entry.get("committed_request_bytes")) is not int or entry["committed_request_bytes"] < 0:
            raise ProviderAdapterError("journal_committed_bytes_invalid")
        entries.append(entry)
        prior_hash = str(entry["entry_hash"])
        prior_phase = phase
    return entries


def _journal_request_binding_hash(entries: Sequence[Mapping[str, Any]], current: Mapping[str, Any]) -> str:
    first = entries[0] if entries else current
    artifact = _mapping(first.get("prepared_artifact"), "journal_request")
    value = artifact.get("request_binding_hash")
    if not isinstance(value, str):
        raise ProviderAdapterError("journal_request_binding_hash_missing")
    return value


def _attempts_from_journal(config: AdapterConfig, entries: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    for entry in entries:
        if entry.get("phase") != "attempt_written":
            continue
        attempt = dict(_mapping(entry.get("prepared_artifact"), "attempt_artifact"))
        _validate_adapter_attempt(attempt)
        path = config.adapter_root / f"{attempt['attempt_id'][7:]}.attempt.json"
        _write_bound_artifact(path, attempt, config, "attempt")
        attempts.append(attempt)
    return attempts


def _delivery_counters(entries: Sequence[Mapping[str, Any]], replay_count: int) -> tuple[dict[str, int], dict[str, int]]:
    adapter = zero_adapter_counters()
    adapter["adapter_request_prepare_count"] = sum(entry["phase"] == "request_prepared" for entry in entries)
    adapter["adapter_request_write_count"] = adapter["adapter_request_prepare_count"]
    adapter["adapter_attempt_prepare_count"] = sum(entry["phase"] == "attempt_prepared" for entry in entries)
    adapter["provider_response_classification_count"] = sum(entry["phase"] == "transport_completed" for entry in entries)
    adapter["retry_schedule_count"] = sum(
        entry["phase"] == "attempt_written" and _mapping(entry["prepared_artifact"], "attempt").get("retry_decision") == "scheduled" for entry in entries
    )
    adapter["terminal_receipt_write_count"] = sum(entry["phase"] == "receipt_written" for entry in entries)
    adapter["replay_journal_entry_count"] = replay_count
    transport = zero_transport_counters()
    for attempt in _attempt_values(entries):
        _merge_counter_map(transport, _mapping(attempt["transport_counters"], "attempt_transport_counters"), TRANSPORT_COUNTER_KEYS)
    return adapter, transport


def _attempt_values(entries: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [_mapping(entry["prepared_artifact"], "attempt") for entry in entries if entry["phase"] == "attempt_written"]


def _adapter_cursor(delivery_id: str) -> dict[str, Any]:
    cursor: dict[str, Any] = {"schema_version": "p144.adapter_cursor.v1", "last_delivery_id": delivery_id}
    cursor["cursor_hash"] = stable_hash(cursor)
    return cursor


def _write_prepared_cursor(config: AdapterConfig, cursor: Mapping[str, Any], prior_hash: Any, *, crash_after: str | None) -> None:
    desired = canonical_json(cursor) + b"\n"
    if config.cursor_path.exists():
        current = config.cursor_path.read_bytes()
        if current == desired:
            return
        if prior_hash is not None and _bytes_sha256(current) != prior_hash:
            raise ProviderAdapterError("cursor_prepared_byte_conflict")
    elif prior_hash is not None:
        raise ProviderAdapterError("cursor_prior_artifact_missing")
    _atomic_write_json(config.cursor_path, cursor, config.writable_roots, artifact_kind="cursor", crash_after=crash_after)


def _validate_completed_delivery(config: AdapterConfig, request: Mapping[str, Any], entries: Sequence[Mapping[str, Any]]) -> None:
    request_path = config.adapter_root / f"{request['delivery_id'][7:]}.request.json"
    _write_bound_artifact(request_path, request, config, "request")
    _attempts_from_journal(config, entries)
    receipt_entry = next((entry for entry in reversed(entries) if entry["phase"] == "receipt_written"), None)
    run_entry = next((entry for entry in reversed(entries) if entry["phase"] == "run_written"), None)
    if receipt_entry is None or run_entry is None:
        raise ProviderAdapterError("completed_journal_incomplete")
    receipt = dict(_mapping(receipt_entry["prepared_artifact"], "receipt"))
    run = dict(_mapping(run_entry["prepared_artifact"], "run"))
    _write_bound_artifact(config.receipt_root / f"{request['delivery_id'][7:]}.receipt.json", receipt, config, "receipt")
    _write_bound_artifact(config.adapter_root / f"{run['run_id'][7:]}.run.json", run, config, "run")


def _completed_run_from_cursor(
    config: AdapterConfig,
    projections: Sequence[Mapping[str, Any]],
    capability: ReceiverCapability,
    bindings: Mapping[str, Any],
) -> dict[str, Any]:
    if not config.cursor_path.is_file():
        raise ProviderAdapterError("completed_run_missing")
    cursor = _read_json(config.cursor_path, "cursor")
    delivery_id = cursor.get("last_delivery_id")
    for projection in projections:
        request = prepare_adapter_request(config, projection, capability, dependency_hash=stable_hash(bindings))
        if request["delivery_id"] != delivery_id:
            continue
        entries = _load_journal_entries(config, str(delivery_id))
        _validate_completed_delivery(config, request, entries)
        run_entry = next(entry for entry in reversed(entries) if entry["phase"] == "run_written")
        run = dict(_mapping(run_entry["prepared_artifact"], "run"))
        _validate_adapter_run(run)
        return run
    raise ProviderAdapterError("completed_run_cursor_binding_invalid")


@contextmanager
def _run_lease(config: AdapterConfig) -> Iterator[None]:
    config.lease_path.parent.mkdir(parents=True, exist_ok=True)
    token = f"{os.getpid()}:{hashlib.sha256(os.urandom(16)).hexdigest()}\n".encode("ascii")
    try:
        descriptor = os.open(config.lease_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ProviderAdapterError("lease_conflict_before_socket") from exc
    try:
        os.write(descriptor, token)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        yield
    finally:
        if config.lease_path.is_file() and config.lease_path.read_bytes() == token:
            config.lease_path.unlink()


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProviderAdapterError(f"{label}_invalid")
    return value


def _bytes_sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _write_bound_artifact(path: Path, value: Mapping[str, Any], config: AdapterConfig, kind: str, *, crash_after: str | None = None) -> None:
    data = canonical_json(value) + b"\n"
    if path.exists():
        if path.read_bytes() != data:
            raise ProviderAdapterError("conflicting_replay_artifacts")
        return
    _atomic_write_json(path, value, config.writable_roots, artifact_kind=kind, crash_after=crash_after)


def _atomic_write_json(path: Path, value: Mapping[str, Any], writable_roots: Sequence[Path], *, artifact_kind: str | None = None, crash_after: str | None = None) -> None:
    if not any(path == root or path.is_relative_to(root) for root in writable_roots):
        raise ProviderAdapterError("write_outside_root")
    _reject_symlink_components(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = canonical_json(value) + b"\n"
    tmp = path.with_name(f".{path.name}.tmp")
    with tmp.open("wb") as handle:
        handle.write(data)
        handle.flush()
        if crash_after == f"{artifact_kind}:file_fsync":
            raise RuntimeError(f"injected_crash:{artifact_kind}:file_fsync")
        os.fsync(handle.fileno())
    if crash_after == f"{artifact_kind}:before_replace":
        raise RuntimeError(f"injected_crash:{artifact_kind}:before_replace")
    os.replace(tmp, path)
    if crash_after == f"{artifact_kind}:after_replace":
        raise RuntimeError(f"injected_crash:{artifact_kind}:after_replace")
    dir_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def _ensure_output_dirs(config: AdapterConfig) -> None:
    for root in config.writable_roots:
        root.mkdir(parents=True, exist_ok=True)
        _require_safe_directory(root, "writable_root")


def _resolve(base: Path, value: Any) -> Path:
    literal = _literal_path(value)
    if literal.is_absolute():
        _reject_symlink_components(literal)
        path = literal.resolve()
    else:
        unresolved = base / literal
        _reject_symlink_components(unresolved)
        path = unresolved.resolve()
    if any(part in {"", ".", ".."} for part in literal.parts):
        raise ProviderAdapterError("unsafe_path")
    return path


def _literal_path(value: Any) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value or any(ord(ch) < 32 for ch in value):
        raise ProviderAdapterError("invalid_path")
    if ".." in Path(value).parts:
        raise ProviderAdapterError("unsafe_path")
    return Path(value)


def _distinct_roots(paths: Sequence[Path]) -> tuple[Path, ...]:
    roots: list[Path] = []
    for path in paths:
        root = path if path.suffix == "" else path.parent
        root = root.resolve()
        if root not in roots:
            roots.append(root)
    for left_index, left in enumerate(roots):
        for right in roots[left_index + 1 :]:
            if _overlaps(left, right):
                raise ProviderAdapterError("write_root_overlap")
    return tuple(roots)


def _overlaps(left: Path, right: Path) -> bool:
    return left == right or left.is_relative_to(right) or right.is_relative_to(left)


def _require_safe_directory(path: Path, label: str, *, boundary: Path | None = None) -> None:
    if not path.exists():
        return
    if not path.is_dir() or path.is_symlink():
        raise ProviderAdapterError(f"{label}_unsafe")
    current = path
    boundary = boundary.resolve() if boundary is not None else None
    while True:
        mode = current.stat().st_mode
        if mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise ProviderAdapterError(f"{label}_unsafe_permissions")
        if boundary is None or current == boundary or current.parent == current:
            break
        if not current.parent.is_relative_to(boundary) and current.parent != boundary:
            break
        current = current.parent


def _reject_symlink_components(path: Path) -> None:
    current = Path(path.root) if path.is_absolute() else Path(".")
    for part in path.parts:
        if part in {path.root, ""}:
            continue
        current = current / part
        if current.is_symlink():
            raise ProviderAdapterError("symlink_path_rejected")


def _read_json(path: Path, label: str) -> dict[str, Any]:
    _ = label
    _reject_symlink_components(path)
    if not path.is_file():
        raise ProviderAdapterError("json_file_missing")
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle, object_pairs_hook=_strict_json_object)
    except _DuplicateJsonKey as exc:
        raise ProviderAdapterError(str(exc)) from exc
    if not isinstance(value, dict):
        raise ProviderAdapterError("json_object_required")
    return value


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise _DuplicateJsonKey(f"duplicate_json_key:{key}")
        value[key] = item
    return value


def _bounded_int(raw: Mapping[str, Any], key: str) -> int:
    value = raw.get(key)
    minimum, maximum = _BUDGET_BOUNDS[key]
    if type(value) is not int or not minimum <= value <= maximum:
        raise ProviderAdapterError("invalid_budget")
    return value


def _field_forbidden(field: str) -> bool:
    lower = field.lower()
    return any(word in lower for word in _FORBIDDEN_FIELD_WORDS)


def _reject_unsafe_values(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if _field_forbidden(str(key)):
                raise ProviderAdapterError("forbidden_value_field")
            _reject_unsafe_values(item)
    elif isinstance(value, list):
        for item in value:
            _reject_unsafe_values(item)
    elif isinstance(value, str) and _UNSAFE_VALUE_RE.search(value):
        raise ProviderAdapterError("unsafe_configuration_value")


def _hash_value(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ProviderAdapterError(f"{label}_hash_invalid")
    return value


def _receipt_id(value: Any) -> str:
    if not isinstance(value, str) or not _RECEIPT_ID_RE.fullmatch(value) or _UNSAFE_VALUE_RE.search(value):
        raise ProviderAdapterError("provider_receipt_id_invalid")
    return value


def _header_value(value: str) -> str:
    if len(value.encode("ascii", "strict")) > 256 or any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ProviderAdapterError("header_value_invalid")
    return value


def _timestamp(now: datetime) -> str:
    if now.tzinfo is None:
        raise ProviderAdapterError("timestamp_not_utc")
    return now.astimezone(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _timestamp_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _TIMESTAMP_RE.fullmatch(value):
        raise ProviderAdapterError(f"{label}_invalid")
    return value


def _counter_map(value: Any, keys: tuple[str, ...], *, exact_zero: bool) -> bool:
    return isinstance(value, Mapping) and set(value) == set(keys) and all(type(value[key]) is int and (value[key] == 0 if exact_zero else value[key] >= 0) for key in keys)


def _merge_counter_map(target: dict[str, int], source: Mapping[str, int], keys: tuple[str, ...]) -> None:
    for key in keys:
        target[key] += int(source.get(key, 0))


__all__ = [
    "ADAPTER_COUNTER_KEYS",
    "FORBIDDEN_COUNTER_KEYS",
    "TRANSPORT_COUNTER_KEYS",
    "AdapterConfig",
    "ProviderAdapterError",
    "ReceiverCapability",
    "canonical_json",
    "classify_provider_response",
    "compute_request_binding_hash",
    "dependency_bindings",
    "deterministic_attempt_id",
    "encode_http_request",
    "issue_receiver_capability",
    "list_adapter_receipts",
    "load_adapter_config",
    "measured_adapter_counters",
    "measured_transport_counters",
    "prepare_adapter_request",
    "process_adapter_deliveries",
    "receiver_capability_hash",
    "record_measured_counters",
    "reset_measured_counters",
    "validate_adapter_config",
    "zero_adapter_counters",
    "zero_forbidden_counters",
    "zero_transport_counters",
]
