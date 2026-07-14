"""Numeric-loopback-only transport lab for P141 notification envelopes."""

from __future__ import annotations

import email.utils
import fcntl
import hashlib
import ipaddress
import json
import math
import os
import re
import shutil
import socket
import stat
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p141_notification_authority import (
    list_notification_envelopes,
    list_simulated_receipts,
    load_notification_config,
)

CONFIG_SCHEMA_VERSION = "p142.loopback_transport_config.v1"
DISPATCH_SCHEMA_VERSION = "p142.dispatch_record.v1"
JOURNAL_SCHEMA_VERSION = "p142.dispatch_attempt_journal.v1"
RECEIPT_SCHEMA_VERSION = "p142.loopback_transport_receipt.v1"
CURSOR_SCHEMA_VERSION = "p142.loopback_transport_cursor.v1"
RUN_SCHEMA_VERSION = "p142.loopback_transport_run.v1"

FORBIDDEN_AUTHORITY_COUNTER_KEYS: tuple[str, ...] = (
    "credential_read_count",
    "environment_read_count",
    "dns_socket_call_count",
    "proxy_use_count",
    "tls_handshake_count",
    "authentication_attempt_count",
    "redirect_follow_count",
    "provider_sdk_call_count",
    "non_loopback_socket_attempt_count",
    "external_message_send_count",
    "ticket_creation_count",
    "p133_ack_write_count",
    "approval_count",
    "subprocess_shell_count",
    "arbitrary_command_execution_count",
    "action_execution_count",
    "remediation_execution_count",
    "staging_mutation_count",
    "production_mutation_count",
    "operator_replacement_count",
    "authority_escape_count",
)
TRANSPORT_COUNTER_KEYS: tuple[str, ...] = (
    "loopback_socket_attempt_count",
    "loopback_request_commit_count",
    "loopback_request_byte_count",
    "loopback_complete_response_count",
    "loopback_response_byte_count",
    "loopback_retry_count",
    "loopback_transport_failure_count",
    "loopback_http_2xx_count",
    "loopback_http_3xx_count",
    "loopback_http_4xx_count",
    "loopback_http_5xx_count",
)

_CONFIG_FIELDS = frozenset(
    {
        "schema_version",
        "lab_id",
        "p141_config_path",
        "p141_release_evidence_path",
        "p141_expected_release_evidence_hash",
        "routes",
        "dispatch_dir",
        "journal_dir",
        "receipt_dir",
        "cursor_path",
        "run_dir",
        "max_attempts",
        "connect_timeout_ms",
        "response_timeout_ms",
        "body_read_timeout_ms",
        "max_request_bytes",
        "max_response_bytes",
        "max_total_dispatch_ms",
        "base_backoff_ms",
        "max_backoff_ms",
        "max_retry_after_ms",
        "max_artifact_files",
        "max_total_bytes",
        "max_receipt_bytes",
        "min_artifact_free_bytes",
    }
)
_ROUTE_FIELDS = frozenset({"route_id", "destination_id", "method", "authority", "path"})
_DISPATCH_FIELDS = frozenset(
    {
        "schema_version",
        "config_hash",
        "envelope_id",
        "envelope_hash",
        "source_event_hash",
        "destination_id",
        "route_id",
        "method",
        "authority",
        "path",
        "request_body_hash",
        "dispatch_id",
        "dispatch_hash",
    }
)
_JOURNAL_FIELDS = frozenset({"schema_version", "dispatch_id", "config_hash", "entries", "journal_hash"})
_RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "config_hash",
        "p141_binding",
        "dispatch_id",
        "attempt_ids",
        "numeric_loopback_authority",
        "method",
        "path",
        "request_body_hash",
        "status_code",
        "failure_class",
        "response_body_hash",
        "response_truncated",
        "retry_after",
        "timing_budget",
        "retry_schedule",
        "delivered_to_loopback",
        "production_delivered",
        "acknowledged",
        "authority_counters",
        "transport_counters",
        "receipt_hash",
    }
)
_CURSOR_FIELDS = frozenset({"schema_version", "config_hash", "last_sequence", "last_event_id", "last_envelope_hash", "cursor_hash"})
_RUN_FIELDS = frozenset(
    {
        "schema_version",
        "lab_id",
        "config_hash",
        "processed_envelope_count",
        "dispatch_count",
        "receipt_count",
        "replayed_dispatch_count",
        "authority_counters",
        "transport_counters",
        "run_hash",
    }
)
_FORBIDDEN_FIELD_WORDS = frozenset(
    {
        "action",
        "api",
        "auth",
        "bearer",
        "command",
        "credential",
        "cookie",
        "dns",
        "endpoint",
        "environment",
        "header",
        "key",
        "mutation",
        "password",
        "proxy",
        "redirect",
        "remediation",
        "secret",
        "shell",
        "subprocess",
        "tls",
        "token",
        "url",
        "webhook",
    }
)
_UNSAFE_VALUE_RE = re.compile(
    r"(?:https://|wss?://|localhost|@|\$\{|\benv(?:ironment)?\b|\b(?:api[-_]?key|auth|bearer|credential|cookie|dns|password|provider|proxy|secret|tls|token|webhook|command|shell|subprocess|remediation|mutation|redirect)\b)",
    re.IGNORECASE,
)
_LABEL_RE = re.compile(r"[a-z0-9][a-z0-9_.:-]{0,63}\Z")
_PATH_RE = re.compile(r"/(?:[A-Za-z0-9._~-]+/)*[A-Za-z0-9._~-]*\Z")
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_HTTP_METHODS = frozenset({"POST", "PUT"})
_PHASES = ("pre_socket", "request_committed", "complete_response_observed", "receipt_written")
_MAX_LOCAL_JSON_BYTES = 16_777_216
_MAX_CLOCK_ROLLBACK_SECONDS = 5.0


class LoopbackTransportError(ValueError):
    """Raised when P142 cannot prove its loopback-only lab boundary."""


@dataclass(frozen=True)
class ParsedAuthority:
    family: int
    address: str
    packed: bytes
    port: int
    authority: str


@dataclass(frozen=True)
class LoopbackRoute:
    route_id: str
    destination_id: str
    method: str
    authority: str
    path: str
    parsed: ParsedAuthority


@dataclass(frozen=True)
class LoopbackTransportConfig:
    schema_version: str
    config_hash: str
    lab_id: str
    p141_config_path: Path
    p141_release_evidence_path: Path
    p141_expected_release_evidence_hash: str
    routes: tuple[LoopbackRoute, ...]
    dispatch_dir: Path
    journal_dir: Path
    receipt_dir: Path
    cursor_path: Path
    run_dir: Path
    lease_path: Path
    max_attempts: int
    connect_timeout_ms: int
    response_timeout_ms: int
    body_read_timeout_ms: int
    max_request_bytes: int
    max_response_bytes: int
    max_total_dispatch_ms: int
    base_backoff_ms: int
    max_backoff_ms: int
    max_retry_after_ms: int
    max_artifact_files: int
    max_total_bytes: int
    max_receipt_bytes: int
    min_artifact_free_bytes: int
    writable_roots: tuple[Path, ...]


def zero_forbidden_authority_counters() -> dict[str, int]:
    return {key: 0 for key in FORBIDDEN_AUTHORITY_COUNTER_KEYS}


def zero_transport_counters() -> dict[str, int]:
    return {key: 0 for key in TRANSPORT_COUNTER_KEYS}


def load_loopback_transport_config(path: Path | str) -> LoopbackTransportConfig:
    config_path = _absolute(_literal_path(path, "configuration_path"))
    _reject_symlink_components(config_path)
    _regular_file_stat(config_path, "configuration")
    raw = _read_json(config_path, "configuration")
    if set(raw) != _CONFIG_FIELDS:
        if any(_field_is_forbidden(item) for item in set(raw) - _CONFIG_FIELDS):
            raise LoopbackTransportError("forbidden_configuration_field")
        raise LoopbackTransportError("invalid_configuration_fields")
    if raw.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise LoopbackTransportError("invalid_configuration_schema")
    _reject_unsafe_values(raw)

    p141_config_path = _resolve(config_path.parent, raw["p141_config_path"])
    p141_release_evidence_path = _resolve(config_path.parent, raw["p141_release_evidence_path"])
    expected_p141_hash = _hash_value(raw["p141_expected_release_evidence_hash"], "p141_expected_release_evidence_hash")
    dispatch_dir = _resolve(config_path.parent, raw["dispatch_dir"])
    journal_dir = _resolve(config_path.parent, raw["journal_dir"])
    receipt_dir = _resolve(config_path.parent, raw["receipt_dir"])
    cursor_path = _resolve(config_path.parent, raw["cursor_path"])
    run_dir = _resolve(config_path.parent, raw["run_dir"])
    lease_path = cursor_path.with_name(f".{cursor_path.name}.lock")
    for path_candidate in (p141_config_path, p141_release_evidence_path, dispatch_dir, journal_dir, receipt_dir, cursor_path, run_dir, lease_path):
        _reject_symlink_components(path_candidate)
    for readable in (p141_config_path, p141_release_evidence_path):
        _regular_file_stat(readable, "dependency")
    writable_roots = _distinct_roots((dispatch_dir, journal_dir, receipt_dir, cursor_path.parent, run_dir))
    for root in writable_roots:
        root.mkdir(parents=True, exist_ok=True)
        _require_safe_directory(root, "writable_root")
    if any(_overlaps(readable, root) for readable in (p141_config_path.parent, p141_release_evidence_path.parent) for root in writable_roots):
        raise LoopbackTransportError("p141_p142_path_overlap")
    _require_distinct_output_paths(dispatch_dir, journal_dir, receipt_dir, cursor_path, run_dir, lease_path)

    routes = _routes(raw["routes"])
    lab_id = _safe_label(raw["lab_id"], "lab_id")
    integers = {
        key: _positive_int(raw, key)
        for key in (
            "max_attempts",
            "connect_timeout_ms",
            "response_timeout_ms",
            "body_read_timeout_ms",
            "max_request_bytes",
            "max_response_bytes",
            "max_total_dispatch_ms",
            "base_backoff_ms",
            "max_backoff_ms",
            "max_retry_after_ms",
            "max_artifact_files",
            "max_total_bytes",
            "max_receipt_bytes",
            "min_artifact_free_bytes",
        )
    }
    if integers["max_attempts"] > 8 or integers["base_backoff_ms"] > integers["max_backoff_ms"]:
        raise LoopbackTransportError("invalid_retry_budget")
    if integers["max_request_bytes"] > integers["max_total_bytes"] or integers["max_response_bytes"] > integers["max_total_bytes"]:
        raise LoopbackTransportError("per_artifact_budget_exceeds_total")
    return LoopbackTransportConfig(
        schema_version=CONFIG_SCHEMA_VERSION,
        config_hash=stable_hash(raw),
        lab_id=lab_id,
        p141_config_path=p141_config_path,
        p141_release_evidence_path=p141_release_evidence_path,
        p141_expected_release_evidence_hash=expected_p141_hash,
        routes=routes,
        dispatch_dir=dispatch_dir,
        journal_dir=journal_dir,
        receipt_dir=receipt_dir,
        cursor_path=cursor_path,
        run_dir=run_dir,
        lease_path=lease_path,
        writable_roots=writable_roots,
        **integers,
    )


def validate_loopback_transport_config(config: LoopbackTransportConfig) -> dict[str, Any]:
    _validate_p141_release_evidence(config)
    return {"status": "valid", "lab_id": config.lab_id, "config_hash": config.config_hash, "route_count": len(config.routes)}


def process_loopback_transport(
    config: LoopbackTransportConfig,
    *,
    monotonic: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
    wall_clock: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    clock = monotonic or time.monotonic
    sleeper = sleep or time.sleep
    now = wall_clock or (lambda: datetime.now(UTC))
    with _LoopbackLease(config):
        _ensure_output_dirs(config)
        cursor = _load_cursor(config)
        _validate_clock(cursor, now())
        _validate_p141_release_evidence(config)
        envelopes = _validated_p141_envelopes(config)
        pending = [item for item in envelopes if int(item["source_event"]["sequence"]) > int(cursor["last_sequence"])]
        processed = 0
        dispatch_count = 0
        receipt_count = 0
        replayed = 0
        transport = zero_transport_counters()
        current = cursor
        for batch in _event_envelope_batches(pending):
            receipts_for_batch = 0
            expected_receipts = 0
            for envelope in batch:
                routes = _routes_for_envelope(config, envelope)
                expected_receipts += len(routes)
                for route in routes:
                    request_body = _request_body(envelope, route)
                    if len(request_body) > config.max_request_bytes:
                        raise LoopbackTransportError("request_body_size_exceeded")
                    record = _dispatch_record(config, envelope, route, request_body)
                    _reserve_budget(config, record)
                    _write_or_validate_dispatch(config, record)
                    result = _dispatch_or_recover(
                        config,
                        record,
                        route,
                        request_body,
                        clock=clock,
                        sleep=sleeper,
                        wall_clock=now,
                    )
                    _merge_transport(transport, result["transport_counters"])
                    dispatch_count += 0 if result["replayed"] else 1
                    replayed += int(result["replayed"])
                    receipt_count += 1
                    receipts_for_batch += 1
            if receipts_for_batch != expected_receipts:
                raise LoopbackTransportError("cursor_receipts_missing")
            current = _cursor_for_envelope(config, batch[-1])
            _atomic_write_json(config.cursor_path, current, config.writable_roots)
            processed += len(batch)
        run = {
            "schema_version": RUN_SCHEMA_VERSION,
            "lab_id": config.lab_id,
            "config_hash": config.config_hash,
            "processed_envelope_count": processed,
            "dispatch_count": dispatch_count,
            "receipt_count": receipt_count,
            "replayed_dispatch_count": replayed,
            "authority_counters": zero_forbidden_authority_counters(),
            "transport_counters": transport,
        }
        run["run_hash"] = stable_hash(run)
        _validate_run(run)
        run_hash = str(run["run_hash"])
        _atomic_write_json(config.run_dir / f"{run_hash[7:]}.json", run, config.writable_roots)
        return run


def list_loopback_receipts(config: LoopbackTransportConfig) -> list[dict[str, Any]]:
    with _LoopbackLease(config):
        if not config.receipt_dir.exists():
            return []
        return _load_artifact_directory(config.receipt_dir, _validate_receipt, kind="receipt")


def parse_retry_after(value: str | None, *, wall_clock: datetime, max_retry_after_ms: int, remaining_ms: int) -> dict[str, Any]:
    if value is None:
        return {"present": False, "valid": False, "delay_ms": None, "reason": None}
    raw = value.strip()
    delay_seconds: int | None = None
    reason = None
    if re.fullmatch(r"[0-9]+", raw):
        delay_seconds = int(raw)
    elif raw.endswith(" GMT"):
        try:
            parsed = email.utils.parsedate_to_datetime(raw)
        except (TypeError, ValueError):
            reason = "invalid_retry_after"
        else:
            if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed) or email.utils.format_datetime(parsed, usegmt=True) != raw:
                reason = "invalid_retry_after"
            else:
                delay_seconds = max(0, math.ceil((parsed.astimezone(UTC) - _utc(wall_clock)).total_seconds()))
    else:
        reason = "invalid_retry_after"
    if delay_seconds is None:
        return {"present": True, "valid": False, "delay_ms": None, "reason": reason or "invalid_retry_after"}
    delay_ms = delay_seconds * 1000
    if delay_ms > max_retry_after_ms or delay_ms > remaining_ms:
        return {"present": True, "valid": False, "delay_ms": delay_ms, "reason": "retry_after_budget_exceeded"}
    return {"present": True, "valid": True, "delay_ms": delay_ms, "reason": None}


def deterministic_dispatch_id(
    config_hash: str,
    envelope_hash: str,
    destination_id: str,
    route_id: str,
    method: str,
    authority: str,
    path: str,
    body_hash: str,
) -> str:
    return stable_hash(
        {
            "config_hash": config_hash,
            "envelope_hash": envelope_hash,
            "destination_id": destination_id,
            "route_id": route_id,
            "method": method,
            "authority": authority,
            "path": path,
            "body_hash": body_hash,
        }
    )


def deterministic_attempt_id(dispatch_id: str, attempt_ordinal: int) -> str:
    return stable_hash({"dispatch_id": dispatch_id, "attempt_ordinal": attempt_ordinal})


def _dispatch_or_recover(
    config: LoopbackTransportConfig,
    record: Mapping[str, Any],
    route: LoopbackRoute,
    request_body: bytes,
    *,
    clock: Callable[[], float],
    sleep: Callable[[float], None],
    wall_clock: Callable[[], datetime],
) -> dict[str, Any]:
    dispatch_id = str(record["dispatch_id"])
    journal_path = config.journal_dir / f"{dispatch_id[7:]}.json"
    receipt_path = config.receipt_dir / f"{dispatch_id[7:]}.json"
    if receipt_path.exists() or receipt_path.is_symlink():
        receipt, receipt_bytes = _read_json_document(receipt_path, "receipt")
        _validate_receipt(receipt)
        expected_journal = _load_journal(journal_path, dispatch_id, config.config_hash)
        receipt_entries = expected_journal["entries"]
        if receipt_entries and "receipt_hash" not in receipt_entries[-1]:
            intent_receipt = _receipt_from_journal_intent(receipt_entries[-1])
            if receipt_entries[-1]["phases"][-1] == "complete_response_observed":
                expected_receipt = _receipt_from_response(
                    config,
                    record,
                    receipt_entries,
                    receipt_entries[-1]["response"],
                )
                if intent_receipt is not None and intent_receipt != expected_receipt:
                    raise LoopbackTransportError("receipt_intent_response_mismatch")
            elif intent_receipt is not None:
                expected_receipt = intent_receipt
            else:
                raise LoopbackTransportError("receipt_recovery_intent_missing")
            if receipt != expected_receipt or receipt_bytes != _json_bytes(expected_receipt):
                raise LoopbackTransportError("receipt_recovery_bytes_invalid")
            _validate_replayed_receipt_binding(
                config,
                record,
                expected_journal,
                receipt,
                require_journal_hash=False,
            )
            expected_journal = _mark_receipt_written(
                config,
                journal_path,
                expected_journal,
                str(receipt["receipt_hash"]),
            )
        _validate_replayed_receipt_binding(config, record, expected_journal, receipt)
        return {"replayed": True, "transport_counters": zero_transport_counters(), "receipt": receipt}
    journal = _load_journal(journal_path, dispatch_id, config.config_hash) if journal_path.exists() or journal_path.is_symlink() else _new_journal(dispatch_id, config.config_hash)
    _validate_journal(journal, dispatch_id, config.config_hash)
    entries: list[dict[str, Any]] = list(journal["entries"])
    if entries:
        latest = entries[-1]
        latest_phase = latest["phases"][-1]
        intent_receipt = _receipt_from_journal_intent(latest)
        if intent_receipt is not None and "receipt_hash" not in latest:
            if latest_phase == "complete_response_observed":
                expected_response_receipt = _receipt_from_response(
                    config,
                    record,
                    entries,
                    latest["response"],
                )
                if intent_receipt != expected_response_receipt:
                    raise LoopbackTransportError("receipt_intent_response_mismatch")
            _validate_replayed_receipt_binding(
                config,
                record,
                journal,
                intent_receipt,
                require_journal_hash=False,
            )
            _reserve_budget(config, intent_receipt)
            _atomic_write_json(receipt_path, intent_receipt, config.writable_roots)
            journal = _mark_receipt_written(
                config,
                journal_path,
                journal,
                str(intent_receipt["receipt_hash"]),
            )
            _validate_replayed_receipt_binding(config, record, journal, intent_receipt)
            return {
                "replayed": True,
                "transport_counters": zero_transport_counters(),
                "receipt": intent_receipt,
            }
        if latest_phase == "request_committed":
            receipt = _receipt_from_unknown(config, record, entries)
            _write_receipt_and_mark(config, journal_path, journal, receipt_path, receipt)
            return {"replayed": False, "transport_counters": receipt["transport_counters"], "receipt": receipt}
        if latest_phase == "complete_response_observed":
            receipt = _receipt_from_response(config, record, entries, latest["response"])
            _write_receipt_and_mark(config, journal_path, journal, receipt_path, receipt)
            return {"replayed": False, "transport_counters": receipt["transport_counters"], "receipt": receipt}
        if latest_phase == "receipt_written":
            raise LoopbackTransportError("receipt_missing_after_journal")
        if "connection_failure" not in latest:
            raise LoopbackTransportError("pre_socket_replay_without_failure")
    start = clock()
    last_error: str | None = None
    durable_counters = zero_transport_counters()
    while len(entries) < config.max_attempts:
        remaining_ms = config.max_total_dispatch_ms - int((clock() - start) * 1000)
        if remaining_ms <= 0:
            raise LoopbackTransportError("total_dispatch_timeout")
        ordinal = len(entries)
        attempt_id = deterministic_attempt_id(dispatch_id, ordinal)
        entry: dict[str, Any] = {"attempt_ordinal": ordinal, "attempt_id": attempt_id, "phases": ["pre_socket"]}
        entries.append(entry)
        journal = _write_journal(config, journal_path, dispatch_id, entries)
        sock: socket.socket | None = None
        counters = zero_transport_counters()
        try:
            sock = socket.socket(route.parsed.family, socket.SOCK_STREAM)
            counters["loopback_socket_attempt_count"] += 1
            sock.settimeout(min(config.connect_timeout_ms, remaining_ms) / 1000)
            address = socket.inet_ntop(route.parsed.family, route.parsed.packed)
            target: tuple[Any, ...] = (address, route.parsed.port) if route.parsed.family == socket.AF_INET else (address, route.parsed.port, 0, 0)
            sock.connect(target)
        except OSError as exc:
            last_error = type(exc).__name__
            counters["loopback_transport_failure_count"] += 1
            entry["connection_failure"] = {"class": last_error}
            journal = _write_journal(config, journal_path, dispatch_id, entries)
            if len(entries) >= config.max_attempts:
                _merge_transport(durable_counters, counters)
                receipt = _receipt_from_failure(config, record, entries, "connection_failed", durable_counters)
                _write_receipt_and_mark(config, journal_path, journal, receipt_path, receipt)
                return {"replayed": False, "transport_counters": receipt["transport_counters"], "receipt": receipt}
            delay_ms = min(config.max_backoff_ms, config.base_backoff_ms * (2 ** ordinal))
            if delay_ms > config.max_total_dispatch_ms - int((clock() - start) * 1000):
                _merge_transport(durable_counters, counters)
                receipt = _receipt_from_failure(config, record, entries, "connection_failed", durable_counters)
                _write_receipt_and_mark(config, journal_path, journal, receipt_path, receipt)
                return {"replayed": False, "transport_counters": receipt["transport_counters"], "receipt": receipt}
            counters["loopback_retry_count"] += 1
            _merge_transport(durable_counters, counters)
            sleep(delay_ms / 1000)
            continue
        try:
            _append_phase(entry, "request_committed")
            journal = _write_journal(config, journal_path, dispatch_id, entries)
            request = _http_request_bytes(record, request_body)
            try:
                sock.settimeout(config.response_timeout_ms / 1000)
                sock.sendall(request)
                counters["loopback_request_commit_count"] += 1
                counters["loopback_request_byte_count"] += len(request)
                response = _read_http_response(
                    sock,
                    config,
                    wall_clock=wall_clock,
                    remaining_ms=config.max_total_dispatch_ms - int((clock() - start) * 1000),
                )
            except OSError as exc:
                counters["loopback_transport_failure_count"] += 1
                _merge_transport(durable_counters, counters)
                receipt = _receipt_from_failure(
                    config,
                    record,
                    entries,
                    f"request_committed_{type(exc).__name__}",
                    durable_counters,
                )
                _write_receipt_and_mark(config, journal_path, journal, receipt_path, receipt)
                return {"replayed": False, "transport_counters": receipt["transport_counters"], "receipt": receipt}
            counters["loopback_complete_response_count"] += 1
            counters["loopback_response_byte_count"] += response["response_byte_count"]
            status = int(response["status_code"])
            if 200 <= status <= 299:
                counters["loopback_http_2xx_count"] += 1
            elif 300 <= status <= 399:
                counters["loopback_http_3xx_count"] += 1
            elif 400 <= status <= 499:
                counters["loopback_http_4xx_count"] += 1
            elif 500 <= status <= 599:
                counters["loopback_http_5xx_count"] += 1
            _merge_transport(durable_counters, counters)
            response["transport_counters"] = durable_counters
            _append_phase(entry, "complete_response_observed")
            entry["response"] = response
            journal = _write_journal(config, journal_path, dispatch_id, entries)
            receipt = _receipt_from_response(config, record, entries, response)
            _write_receipt_and_mark(config, journal_path, journal, receipt_path, receipt)
            return {"replayed": False, "transport_counters": receipt["transport_counters"], "receipt": receipt}
        finally:
            if sock is not None:
                sock.close()
    if all(value == 0 for value in durable_counters.values()):
        durable_counters["loopback_transport_failure_count"] = 1
    receipt = _receipt_from_failure(config, record, entries, last_error or "connection_failed", durable_counters)
    _write_receipt_and_mark(config, journal_path, journal, receipt_path, receipt)
    return {"replayed": False, "transport_counters": receipt["transport_counters"], "receipt": receipt}


def _read_http_response(
    sock: socket.socket, config: LoopbackTransportConfig, *, wall_clock: Callable[[], datetime], remaining_ms: int
) -> dict[str, Any]:
    sock.settimeout(config.response_timeout_ms / 1000)
    buffer = bytearray()
    while b"\r\n\r\n" not in buffer:
        chunk = sock.recv(1)
        if not chunk:
            raise LoopbackTransportError("malformed_response")
        buffer.extend(chunk)
        if len(buffer) > 8192:
            raise LoopbackTransportError("response_header_size_exceeded")
    head, body_start = bytes(buffer).split(b"\r\n\r\n", 1)
    lines = head.decode("iso-8859-1").split("\r\n")
    status_parts = lines[0].split(" ", 2)
    if len(status_parts) < 2 or not status_parts[0].startswith("HTTP/1.") or not status_parts[1].isdigit():
        raise LoopbackTransportError("malformed_response")
    status = int(status_parts[1])
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" not in line:
            raise LoopbackTransportError("malformed_response")
        key, value = line.split(":", 1)
        headers[key.lower()] = value.strip()
    if "location" in headers:
        redirect_evidence = {"location_present": True, "followed": False}
    else:
        redirect_evidence = {"location_present": False, "followed": False}
    body = bytearray(body_start)
    length = headers.get("content-length")
    if length is not None:
        if not length.isdigit():
            raise LoopbackTransportError("malformed_response")
        expected = int(length)
        while len(body) < expected:
            sock.settimeout(config.body_read_timeout_ms / 1000)
            chunk = sock.recv(min(4096, expected - len(body)))
            if not chunk:
                raise LoopbackTransportError("malformed_response")
            body.extend(chunk)
            if len(body) > config.max_response_bytes:
                break
    else:
        while len(body) <= config.max_response_bytes:
            sock.settimeout(config.body_read_timeout_ms / 1000)
            chunk = sock.recv(4096)
            if not chunk:
                break
            body.extend(chunk)
    truncated = len(body) > config.max_response_bytes
    bounded_body = bytes(body[: config.max_response_bytes])
    retry_after = parse_retry_after(headers.get("retry-after"), wall_clock=wall_clock(), max_retry_after_ms=config.max_retry_after_ms, remaining_ms=remaining_ms)
    return {
        "status_code": status,
        "headers": {"retry-after": headers.get("retry-after"), "location": headers.get("location")},
        "redirect": redirect_evidence,
        "response_body_hash": "sha256:" + hashlib.sha256(bounded_body).hexdigest(),
        "response_truncated": truncated,
        "response_byte_count": len(bounded_body),
        "retry_after": retry_after,
    }


def _http_request_bytes(record: Mapping[str, Any], body: bytes) -> bytes:
    request = (
        f"{record['method']} {record['path']} HTTP/1.1\r\n"
        f"Host: {record['authority']}\r\n"
        f"Connection: close\r\n"
        f"Content-Type: application/json\r\n"
        f"Idempotency-Key: {record['dispatch_id']}\r\n"
        f"Content-Length: {len(body)}\r\n\r\n"
    ).encode("ascii")
    return request + body


def _write_receipt_and_mark(config: LoopbackTransportConfig, journal_path: Path, journal: Mapping[str, Any], receipt_path: Path, receipt: dict[str, Any]) -> None:
    _reserve_budget(config, receipt)
    journal = _write_receipt_intent(config, journal_path, journal, receipt)
    _atomic_write_json(receipt_path, receipt, config.writable_roots)
    _mark_receipt_written(config, journal_path, journal, str(receipt["receipt_hash"]))


def _write_receipt_intent(
    config: LoopbackTransportConfig,
    journal_path: Path,
    journal: Mapping[str, Any],
    receipt: Mapping[str, Any],
) -> dict[str, Any]:
    _validate_receipt(receipt)
    entries = [dict(entry) for entry in journal["entries"]]
    entries[-1]["receipt_intent"] = {
        "receipt": dict(receipt),
        "receipt_bytes_sha256": "sha256:" + hashlib.sha256(_json_bytes(receipt)).hexdigest(),
    }
    return _write_journal(config, journal_path, str(journal["dispatch_id"]), entries)


def _receipt_from_journal_intent(entry: Mapping[str, Any]) -> dict[str, Any] | None:
    intent = entry.get("receipt_intent")
    if intent is None:
        return None
    if not isinstance(intent, Mapping) or set(intent) != {"receipt", "receipt_bytes_sha256"}:
        raise LoopbackTransportError("receipt_intent_invalid")
    receipt = intent.get("receipt")
    if not isinstance(receipt, Mapping):
        raise LoopbackTransportError("receipt_intent_invalid")
    receipt_value = dict(receipt)
    _validate_receipt(receipt_value)
    expected_bytes_hash = "sha256:" + hashlib.sha256(_json_bytes(receipt_value)).hexdigest()
    if intent.get("receipt_bytes_sha256") != expected_bytes_hash:
        raise LoopbackTransportError("receipt_intent_bytes_hash_invalid")
    return receipt_value


def _mark_receipt_written(
    config: LoopbackTransportConfig,
    journal_path: Path,
    journal: Mapping[str, Any],
    receipt_hash: str,
) -> dict[str, Any]:
    entries = list(journal["entries"])
    entries[-1]["receipt_hash"] = receipt_hash
    if entries[-1]["phases"][-1] == "complete_response_observed":
        _append_phase(entries[-1], "receipt_written")
    return _write_journal(config, journal_path, str(journal["dispatch_id"]), entries)


def _receipt_from_response(config: LoopbackTransportConfig, record: Mapping[str, Any], entries: Sequence[Mapping[str, Any]], response: Mapping[str, Any]) -> dict[str, Any]:
    status = int(response["status_code"])
    counters = dict(response["transport_counters"])
    receipt = _base_receipt(config, record, entries)
    receipt.update(
        {
            "status_code": status,
            "failure_class": None,
            "response_body_hash": response["response_body_hash"],
            "response_truncated": response["response_truncated"],
            "retry_after": response["retry_after"],
            "delivered_to_loopback": 200 <= status <= 299,
            "transport_counters": counters,
        }
    )
    receipt["receipt_hash"] = stable_hash(receipt)
    _validate_receipt(receipt)
    return receipt


def _receipt_from_unknown(config: LoopbackTransportConfig, record: Mapping[str, Any], entries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    counters = zero_transport_counters()
    counters["loopback_transport_failure_count"] = 1
    receipt = _base_receipt(config, record, entries)
    receipt.update(
        {
            "status_code": None,
            "failure_class": "request_committed_response_unknown",
            "response_body_hash": None,
            "response_truncated": False,
            "retry_after": {"present": False, "valid": False, "delay_ms": None, "reason": None},
            "delivered_to_loopback": False,
            "transport_counters": counters,
        }
    )
    receipt["receipt_hash"] = stable_hash(receipt)
    _validate_receipt(receipt)
    return receipt


def _receipt_from_failure(
    config: LoopbackTransportConfig,
    record: Mapping[str, Any],
    entries: Sequence[Mapping[str, Any]],
    failure_class: str,
    counters: Mapping[str, int],
) -> dict[str, Any]:
    receipt = _base_receipt(config, record, entries)
    merged = zero_transport_counters()
    _merge_transport(merged, counters)
    receipt.update(
        {
            "status_code": None,
            "failure_class": failure_class,
            "response_body_hash": None,
            "response_truncated": False,
            "retry_after": {"present": False, "valid": False, "delay_ms": None, "reason": None},
            "delivered_to_loopback": False,
            "transport_counters": merged,
        }
    )
    receipt["receipt_hash"] = stable_hash(receipt)
    _validate_receipt(receipt)
    return receipt


def _base_receipt(config: LoopbackTransportConfig, record: Mapping[str, Any], entries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "config_hash": config.config_hash,
        "p141_binding": {
            "envelope_id": record["envelope_id"],
            "envelope_hash": record["envelope_hash"],
            "source_event_hash": record["source_event_hash"],
            "destination_id": record["destination_id"],
        },
        "dispatch_id": record["dispatch_id"],
        "attempt_ids": [entry["attempt_id"] for entry in entries],
        "numeric_loopback_authority": record["authority"],
        "method": record["method"],
        "path": record["path"],
        "request_body_hash": record["request_body_hash"],
        "status_code": None,
        "failure_class": None,
        "response_body_hash": None,
        "response_truncated": False,
        "retry_after": None,
        "timing_budget": {
            "connect_timeout_ms": config.connect_timeout_ms,
            "response_timeout_ms": config.response_timeout_ms,
            "body_read_timeout_ms": config.body_read_timeout_ms,
            "max_total_dispatch_ms": config.max_total_dispatch_ms,
        },
        "retry_schedule": [
            {
                "attempt_ordinal": entry["attempt_ordinal"],
                "attempt_id": entry["attempt_id"],
                "phases": list(entry["phases"][:-1])
                if entry["phases"][-1] == "receipt_written"
                else list(entry["phases"]),
            }
            for entry in entries
        ],
        "delivered_to_loopback": False,
        "production_delivered": False,
        "acknowledged": False,
        "authority_counters": zero_forbidden_authority_counters(),
        "transport_counters": zero_transport_counters(),
    }


def _dispatch_record(config: LoopbackTransportConfig, envelope: Mapping[str, Any], route: LoopbackRoute, request_body: bytes) -> dict[str, Any]:
    body_hash = "sha256:" + hashlib.sha256(request_body).hexdigest()
    dispatch_id = deterministic_dispatch_id(
        config.config_hash,
        str(envelope["envelope_hash"]),
        route.destination_id,
        route.route_id,
        route.method,
        route.authority,
        route.path,
        body_hash,
    )
    record: dict[str, Any] = {
        "schema_version": DISPATCH_SCHEMA_VERSION,
        "config_hash": config.config_hash,
        "envelope_id": envelope["envelope_id"],
        "envelope_hash": envelope["envelope_hash"],
        "source_event_hash": envelope["source_event"]["event_hash"],
        "destination_id": route.destination_id,
        "route_id": route.route_id,
        "method": route.method,
        "authority": route.authority,
        "path": route.path,
        "request_body_hash": body_hash,
        "dispatch_id": dispatch_id,
    }
    record["dispatch_hash"] = stable_hash(record)
    _validate_dispatch_record(record, config.config_hash)
    return record


def _request_body(envelope: Mapping[str, Any], route: LoopbackRoute) -> bytes:
    body = {
        "schema_version": "p142.loopback_request_body.v1",
        "route_id": route.route_id,
        "envelope_id": envelope["envelope_id"],
        "envelope_hash": envelope["envelope_hash"],
        "source_event": envelope["source_event"],
        "message": envelope["message"],
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _routes_for_envelope(config: LoopbackTransportConfig, envelope: Mapping[str, Any]) -> tuple[LoopbackRoute, ...]:
    selected = tuple(route for route in config.routes if route.destination_id == envelope["destination_id"])
    if not selected:
        raise LoopbackTransportError("route_missing_for_destination")
    return selected


def _validated_p141_envelopes(config: LoopbackTransportConfig) -> list[dict[str, Any]]:
    p141_config = load_notification_config(config.p141_config_path)
    envelopes = list_notification_envelopes(p141_config)
    receipts = list_simulated_receipts(p141_config)
    receipts_by_envelope = {receipt["envelope_hash"]: receipt for receipt in receipts}
    for envelope in envelopes:
        if envelope.get("envelope_hash") != stable_hash({key: item for key, item in envelope.items() if key != "envelope_hash"}):
            raise LoopbackTransportError("p141_envelope_hash_invalid")
        receipt = receipts_by_envelope.get(envelope["envelope_hash"])
        if receipt is None or receipt.get("acknowledged") is not False or receipt.get("delivered") is not False:
            raise LoopbackTransportError("p141_receipt_binding_invalid")
    envelopes.sort(key=lambda item: (int(item["source_event"]["sequence"]), str(item["destination_id"])))
    return envelopes


def _event_envelope_batches(envelopes: Sequence[Mapping[str, Any]]) -> list[list[Mapping[str, Any]]]:
    batches: list[list[Mapping[str, Any]]] = []
    for envelope in envelopes:
        event = envelope["source_event"]
        sequence = int(event["sequence"])
        event_id = str(event["event_id"])
        if not batches or int(batches[-1][0]["source_event"]["sequence"]) != sequence:
            batches.append([envelope])
            continue
        if str(batches[-1][0]["source_event"]["event_id"]) != event_id:
            raise LoopbackTransportError("source_sequence_event_conflict")
        batches[-1].append(envelope)
    return batches


def _validate_p141_release_evidence(config: LoopbackTransportConfig) -> None:
    evidence = _read_json(config.p141_release_evidence_path, "p141_release_evidence")
    actual_hash = stable_hash({key: value for key, value in evidence.items() if key not in {"evidence_hash", "release_evidence_hash"}})
    declared = evidence.get("evidence_hash") or evidence.get("release_evidence_hash")
    if declared != config.p141_expected_release_evidence_hash or actual_hash != config.p141_expected_release_evidence_hash:
        raise LoopbackTransportError("p141_release_evidence_hash_drift")
    if evidence.get("status") not in {"p141_notification_authority_simulator_qualified", "test-p141-qualified"}:
        raise LoopbackTransportError("p141_release_evidence_not_qualified")


def _write_or_validate_dispatch(config: LoopbackTransportConfig, record: Mapping[str, Any]) -> None:
    path = config.dispatch_dir / f"{record['dispatch_id'][7:]}.json"
    if path.exists() or path.is_symlink():
        existing = _read_json(path, "dispatch")
        _validate_dispatch_record(existing, config.config_hash)
        if existing != dict(record):
            raise LoopbackTransportError("conflicting_existing_dispatch")
        return
    _atomic_write_json(path, record, config.writable_roots)


def _new_journal(dispatch_id: str, config_hash: str) -> dict[str, Any]:
    journal: dict[str, Any] = {"schema_version": JOURNAL_SCHEMA_VERSION, "dispatch_id": dispatch_id, "config_hash": config_hash, "entries": []}
    journal["journal_hash"] = stable_hash(journal)
    return journal


def _load_journal(path: Path, dispatch_id: str, config_hash: str) -> dict[str, Any]:
    journal = _read_json(path, "journal")
    _validate_journal(journal, dispatch_id, config_hash)
    return journal


def _write_journal(config: LoopbackTransportConfig, path: Path, dispatch_id: str, entries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    journal: dict[str, Any] = {"schema_version": JOURNAL_SCHEMA_VERSION, "dispatch_id": dispatch_id, "config_hash": config.config_hash, "entries": [dict(entry) for entry in entries]}
    journal["journal_hash"] = stable_hash(journal)
    _validate_journal(journal, dispatch_id, config.config_hash)
    _atomic_write_json(path, journal, config.writable_roots)
    return journal


def _append_phase(entry: dict[str, Any], phase: str) -> None:
    phases = entry["phases"]
    expected_next = _PHASES[len(phases)]
    if phase != expected_next:
        raise LoopbackTransportError("invalid_journal_transition")
    phases.append(phase)


def _validate_dispatch_record(value: Mapping[str, Any], config_hash: str) -> None:
    if set(value) != _DISPATCH_FIELDS or value.get("schema_version") != DISPATCH_SCHEMA_VERSION or value.get("config_hash") != config_hash:
        raise LoopbackTransportError("invalid_dispatch_record")
    for key in ("envelope_id", "envelope_hash", "source_event_hash", "request_body_hash", "dispatch_id", "dispatch_hash"):
        _hash_value(value.get(key), key)
    if value.get("dispatch_hash") != stable_hash({key: item for key, item in value.items() if key != "dispatch_hash"}):
        raise LoopbackTransportError("dispatch_hash_invalid")


def _validate_journal(value: Mapping[str, Any], dispatch_id: str, config_hash: str) -> None:
    if set(value) != _JOURNAL_FIELDS or value.get("schema_version") != JOURNAL_SCHEMA_VERSION:
        raise LoopbackTransportError("invalid_journal_fields")
    if value.get("dispatch_id") != dispatch_id or value.get("config_hash") != config_hash:
        raise LoopbackTransportError("journal_binding_invalid")
    entries = value.get("entries")
    if not isinstance(entries, list):
        raise LoopbackTransportError("journal_entries_invalid")
    for ordinal, entry in enumerate(entries):
        if not isinstance(entry, Mapping) or entry.get("attempt_ordinal") != ordinal or entry.get("attempt_id") != deterministic_attempt_id(dispatch_id, ordinal):
            raise LoopbackTransportError("journal_attempt_identity_invalid")
        phases = entry.get("phases")
        if not isinstance(phases, list) or phases != list(_PHASES[: len(phases)]) or len(phases) < 1:
            raise LoopbackTransportError("journal_phase_graph_invalid")
        connection_failed = "connection_failure" in entry
        if connection_failed and phases != ["pre_socket"]:
            raise LoopbackTransportError("journal_connection_failure_phase_invalid")
        if ordinal != len(entries) - 1 and (phases != ["pre_socket"] or not connection_failed):
            raise LoopbackTransportError("journal_terminal_attempt_not_last")
        intent_receipt = _receipt_from_journal_intent(entry)
        if intent_receipt is not None:
            if ordinal != len(entries) - 1:
                raise LoopbackTransportError("receipt_intent_not_terminal")
            terminal_phases = tuple(phases)
            if terminal_phases == ("pre_socket",):
                if not connection_failed or intent_receipt.get("failure_class") != "connection_failed":
                    raise LoopbackTransportError("receipt_intent_terminal_state_invalid")
            elif terminal_phases == ("pre_socket", "request_committed"):
                failure_class = intent_receipt.get("failure_class")
                if not isinstance(failure_class, str) or not failure_class.startswith("request_committed_"):
                    raise LoopbackTransportError("receipt_intent_terminal_state_invalid")
            elif terminal_phases in {
                ("pre_socket", "request_committed", "complete_response_observed"),
                ("pre_socket", "request_committed", "complete_response_observed", "receipt_written"),
            }:
                if intent_receipt.get("failure_class") is not None or type(intent_receipt.get("status_code")) is not int:
                    raise LoopbackTransportError("receipt_intent_terminal_state_invalid")
            else:
                raise LoopbackTransportError("receipt_intent_terminal_state_invalid")
            if intent_receipt.get("config_hash") != config_hash or intent_receipt.get("dispatch_id") != dispatch_id:
                raise LoopbackTransportError("receipt_intent_binding_invalid")
            if intent_receipt.get("attempt_ids") != [item["attempt_id"] for item in entries]:
                raise LoopbackTransportError("receipt_intent_attempts_invalid")
            if "receipt_hash" in entry and entry["receipt_hash"] != intent_receipt["receipt_hash"]:
                raise LoopbackTransportError("receipt_intent_hash_invalid")
    if value.get("journal_hash") != stable_hash({key: item for key, item in value.items() if key != "journal_hash"}):
        raise LoopbackTransportError("journal_hash_invalid")


def _validate_receipt(value: Mapping[str, Any]) -> None:
    if set(value) != _RECEIPT_FIELDS or value.get("schema_version") != RECEIPT_SCHEMA_VERSION:
        raise LoopbackTransportError("invalid_receipt_fields")
    for key in ("config_hash", "dispatch_id", "request_body_hash", "receipt_hash"):
        _hash_value(value.get(key), key)
    if not isinstance(value.get("attempt_ids"), list) or not value["attempt_ids"]:
        raise LoopbackTransportError("receipt_attempts_invalid")
    if value.get("production_delivered") is not False or value.get("acknowledged") is not False:
        raise LoopbackTransportError("receipt_authority_invalid")
    if type(value.get("delivered_to_loopback")) is not bool or type(value.get("response_truncated")) is not bool:
        raise LoopbackTransportError("receipt_boolean_invalid")
    _validate_counter_map(value.get("authority_counters"), FORBIDDEN_AUTHORITY_COUNTER_KEYS, exact_zero=True)
    _validate_counter_map(value.get("transport_counters"), TRANSPORT_COUNTER_KEYS, exact_zero=False)
    if value.get("receipt_hash") != stable_hash({key: item for key, item in value.items() if key != "receipt_hash"}):
        raise LoopbackTransportError("receipt_hash_invalid")


def _validate_replayed_receipt_binding(
    config: LoopbackTransportConfig,
    record: Mapping[str, Any],
    journal: Mapping[str, Any],
    receipt: Mapping[str, Any],
    *,
    require_journal_hash: bool = True,
) -> None:
    entries = journal["entries"]
    if not entries:
        raise LoopbackTransportError("receipt_without_attempt_journal")
    expected = {
        "config_hash": config.config_hash,
        "p141_binding": {
            "envelope_id": record["envelope_id"],
            "envelope_hash": record["envelope_hash"],
            "source_event_hash": record["source_event_hash"],
            "destination_id": record["destination_id"],
        },
        "dispatch_id": record["dispatch_id"],
        "attempt_ids": [entry["attempt_id"] for entry in entries],
        "numeric_loopback_authority": record["authority"],
        "method": record["method"],
        "path": record["path"],
        "request_body_hash": record["request_body_hash"],
        "timing_budget": {
            "connect_timeout_ms": config.connect_timeout_ms,
            "response_timeout_ms": config.response_timeout_ms,
            "body_read_timeout_ms": config.body_read_timeout_ms,
            "max_total_dispatch_ms": config.max_total_dispatch_ms,
        },
        "retry_schedule": [
            {
                "attempt_ordinal": entry["attempt_ordinal"],
                "attempt_id": entry["attempt_id"],
                "phases": list(entry["phases"][:-1])
                if entry["phases"][-1] == "receipt_written"
                else list(entry["phases"]),
            }
            for entry in entries
        ],
    }
    for key, value in expected.items():
        if receipt.get(key) != value:
            raise LoopbackTransportError("receipt_binding_invalid")
    journal_receipt_hash = entries[-1].get("receipt_hash")
    if require_journal_hash and journal_receipt_hash != receipt.get("receipt_hash"):
        raise LoopbackTransportError("receipt_journal_hash_invalid")


def _validate_run(value: Mapping[str, Any]) -> None:
    if set(value) != _RUN_FIELDS or value.get("schema_version") != RUN_SCHEMA_VERSION:
        raise LoopbackTransportError("invalid_run_fields")
    _validate_counter_map(value.get("authority_counters"), FORBIDDEN_AUTHORITY_COUNTER_KEYS, exact_zero=True)
    _validate_counter_map(value.get("transport_counters"), TRANSPORT_COUNTER_KEYS, exact_zero=False)
    if value.get("run_hash") != stable_hash({key: item for key, item in value.items() if key != "run_hash"}):
        raise LoopbackTransportError("run_hash_invalid")


def _validate_counter_map(value: Any, keys: Sequence[str], *, exact_zero: bool) -> None:
    if not isinstance(value, Mapping) or set(value) != set(keys):
        raise LoopbackTransportError("counter_keys_invalid")
    for key in keys:
        if type(value[key]) is not int:
            raise LoopbackTransportError("counter_value_invalid")
        if exact_zero and value[key] != 0:
            raise LoopbackTransportError("authority_counter_nonzero")
        if not exact_zero and value[key] < 0:
            raise LoopbackTransportError("transport_counter_negative")


def _load_cursor(config: LoopbackTransportConfig) -> dict[str, Any]:
    if not config.cursor_path.exists() and not config.cursor_path.is_symlink():
        cursor: dict[str, Any] = {
            "schema_version": CURSOR_SCHEMA_VERSION,
            "config_hash": config.config_hash,
            "last_sequence": 0,
            "last_event_id": None,
            "last_envelope_hash": None,
        }
        cursor["cursor_hash"] = stable_hash(cursor)
        return cursor
    cursor = _read_json(config.cursor_path, "cursor")
    if set(cursor) != _CURSOR_FIELDS or cursor.get("schema_version") != CURSOR_SCHEMA_VERSION or cursor.get("config_hash") != config.config_hash:
        raise LoopbackTransportError("invalid_cursor")
    if type(cursor.get("last_sequence")) is not int or cursor["last_sequence"] < 0:
        raise LoopbackTransportError("invalid_cursor_sequence")
    if cursor.get("cursor_hash") != stable_hash({key: item for key, item in cursor.items() if key != "cursor_hash"}):
        raise LoopbackTransportError("cursor_hash_invalid")
    return cursor


def _cursor_for_envelope(config: LoopbackTransportConfig, envelope: Mapping[str, Any]) -> dict[str, Any]:
    cursor = {
        "schema_version": CURSOR_SCHEMA_VERSION,
        "config_hash": config.config_hash,
        "last_sequence": envelope["source_event"]["sequence"],
        "last_event_id": envelope["source_event"]["event_id"],
        "last_envelope_hash": envelope["envelope_hash"],
    }
    cursor["cursor_hash"] = stable_hash(cursor)
    return cursor


class _LoopbackLease:
    def __init__(self, config: LoopbackTransportConfig) -> None:
        self.config = config
        self.handle: Any = None

    def __enter__(self) -> None:
        parent_fd, name = _open_artifact_parent(self.config.lease_path, create=True)
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        try:
            fd = os.open(name, flags, 0o600, dir_fd=parent_fd)
        finally:
            os.close(parent_fd)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            os.close(fd)
            raise LoopbackTransportError("loopback_lease_not_regular")
        self.handle = os.fdopen(fd, "a+", encoding="utf-8")
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self.handle.close()
            self.handle = None
            raise LoopbackTransportError("loopback_lease_unavailable") from exc

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self.handle is not None:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()


def _routes(value: Any) -> tuple[LoopbackRoute, ...]:
    if not _sequence(value) or not value:
        raise LoopbackTransportError("routes_required")
    result = []
    seen = set()
    for item in value:
        if not isinstance(item, Mapping) or set(item) != _ROUTE_FIELDS:
            raise LoopbackTransportError("invalid_route_fields")
        method = str(item["method"]).upper()
        if method not in _HTTP_METHODS:
            raise LoopbackTransportError("unsupported_method")
        path = _canonical_path(item["path"])
        authority = str(item["authority"])
        route = LoopbackRoute(
            route_id=_safe_label(item["route_id"], "route_id"),
            destination_id=_safe_label(item["destination_id"], "destination_id"),
            method=method,
            authority=authority,
            path=path,
            parsed=parse_loopback_authority(authority),
        )
        key = (route.destination_id, route.route_id)
        if key in seen:
            raise LoopbackTransportError("duplicate_route")
        seen.add(key)
        result.append(route)
    return tuple(result)


def parse_loopback_authority(value: str) -> ParsedAuthority:
    if not isinstance(value, str) or not value or any(token in value for token in ("/", "?", "#", "@")):
        raise LoopbackTransportError("invalid_authority")
    if value.startswith("["):
        match = re.fullmatch(r"\[::1\]:([0-9]+)", value)
        if not match:
            raise LoopbackTransportError("invalid_ipv6_loopback_authority")
        port = _port(match.group(1))
        address = ipaddress.IPv6Address("::1")
        return ParsedAuthority(socket.AF_INET6, "::1", address.packed, port, f"[::1]:{port}")
    host, sep, port_text = value.rpartition(":")
    if sep != ":" or not host or ":" in host:
        raise LoopbackTransportError("invalid_ipv4_loopback_authority")
    port = _port(port_text)
    if not re.fullmatch(r"(?:0|[1-9][0-9]{0,2})(?:\.(?:0|[1-9][0-9]{0,2})){3}", host):
        raise LoopbackTransportError("invalid_ipv4_loopback_authority")
    parts = host.split(".")
    if any(part != str(int(part)) or int(part) > 255 for part in parts):
        raise LoopbackTransportError("noncanonical_ipv4")
    if parts[0] != "127" or host in {"127.0.0.0", "127.255.255.255"}:
        raise LoopbackTransportError("non_loopback_numeric_target")
    address4 = ipaddress.IPv4Address(host)
    if not address4.is_loopback:
        raise LoopbackTransportError("non_loopback_numeric_target")
    return ParsedAuthority(socket.AF_INET, str(address4), address4.packed, port, f"{address4}:{port}")


def _port(value: str) -> int:
    if not re.fullmatch(r"[1-9][0-9]{0,4}", value):
        raise LoopbackTransportError("invalid_port")
    port = int(value)
    if not 1 <= port <= 65535:
        raise LoopbackTransportError("invalid_port")
    return port


def _canonical_path(value: Any) -> str:
    if not isinstance(value, str) or not value.startswith("/") or value != value.encode("ascii", "strict").decode("ascii"):
        raise LoopbackTransportError("invalid_path")
    if value != "/" and (
        not _PATH_RE.fullmatch(value)
        or "//" in value
        or "/./" in value
        or "/../" in value
        or value.endswith("/")
        or value.endswith("/.")
        or value.endswith("/..")
    ):
        raise LoopbackTransportError("invalid_path")
    if any(ch in value for ch in ("\\", "?", "#", "%", "$")) or any(ord(ch) < 33 or ch.isspace() for ch in value):
        raise LoopbackTransportError("invalid_path")
    return value


def _ensure_output_dirs(config: LoopbackTransportConfig) -> None:
    for directory in (config.dispatch_dir, config.journal_dir, config.receipt_dir, config.cursor_path.parent, config.run_dir):
        directory_fd = _open_directory_tree(directory, create=True)
        try:
            _require_safe_fd_directory(directory_fd, "writable_directory")
        finally:
            os.close(directory_fd)


def _reserve_budget(config: LoopbackTransportConfig, value: object) -> None:
    data_size = len(_json_bytes(value))
    if data_size > config.max_receipt_bytes and isinstance(value, Mapping) and value.get("schema_version") == RECEIPT_SCHEMA_VERSION:
        raise LoopbackTransportError("receipt_size_exceeded")
    file_count, total_bytes = _artifact_usage(config)
    if file_count + 1 > config.max_artifact_files or total_bytes + data_size > config.max_total_bytes:
        raise LoopbackTransportError("artifact_budget_exhausted")
    if shutil.disk_usage(config.cursor_path.parent).free < config.min_artifact_free_bytes + data_size:
        raise LoopbackTransportError("insufficient_artifact_space")


def _artifact_usage(config: LoopbackTransportConfig) -> tuple[int, int]:
    file_count = 0
    total_bytes = 0
    for directory in (config.dispatch_dir, config.journal_dir, config.receipt_dir, config.run_dir):
        if not directory.exists():
            continue
        directory_fd = _open_directory_tree(directory, create=False)
        try:
            for name in os.listdir(directory_fd):
                info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise LoopbackTransportError("artifact_not_regular")
                file_count += 1
                total_bytes += info.st_size
        finally:
            os.close(directory_fd)
    return file_count, total_bytes


def _load_artifact_directory(directory: Path, validator: Callable[[Mapping[str, Any]], None], *, kind: str) -> list[dict[str, Any]]:
    directory_fd = _open_directory_tree(directory, create=False)
    result: list[dict[str, Any]] = []
    try:
        for name in sorted(os.listdir(directory_fd)):
            if not name.endswith(".json"):
                continue
            value = _read_json_at(directory_fd, name, kind)
            validator(value)
            result.append(value)
    finally:
        os.close(directory_fd)
    return result


def _atomic_write_json(path: Path, value: object, roots: Sequence[Path]) -> None:
    if not any(path == root or path.is_relative_to(root) for root in roots):
        raise LoopbackTransportError("write_path_outside_roots")
    data = _json_bytes(value)
    parent_fd, name = _open_artifact_parent(path, create=True)
    temporary = f".{name}.{os.getpid()}.{time.monotonic_ns()}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    fd = -1
    try:
        try:
            current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            current = None
        if current is not None and (not stat.S_ISREG(current.st_mode) or current.st_nlink != 1):
            raise LoopbackTransportError("write_target_not_regular")
        fd = os.open(temporary, flags, 0o600, dir_fd=parent_fd)
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        temporary = ""
        os.fsync(parent_fd)
    finally:
        if fd >= 0:
            os.close(fd)
        if temporary:
            try:
                os.unlink(temporary, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
        os.close(parent_fd)


def _read_json(path: Path, kind: str) -> dict[str, Any]:
    value, _data = _read_json_document(path, kind)
    return value


def _read_json_document(path: Path, kind: str) -> tuple[dict[str, Any], bytes]:
    parent_fd, name = _open_artifact_parent(path, create=False)
    try:
        return _read_json_document_at(parent_fd, name, kind)
    finally:
        os.close(parent_fd)


def _read_json_at(parent_fd: int, name: str, kind: str) -> dict[str, Any]:
    value, _data = _read_json_document_at(parent_fd, name, kind)
    return value


def _read_json_document_at(parent_fd: int, name: str, kind: str) -> tuple[dict[str, Any], bytes]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(name, flags, dir_fd=parent_fd)
    except OSError as exc:
        raise LoopbackTransportError(f"{kind}_missing_or_unsafe") from exc
    try:
        info_before = os.fstat(fd)
        if not stat.S_ISREG(info_before.st_mode) or info_before.st_nlink != 1:
            raise LoopbackTransportError(f"{kind}_not_regular")
        with os.fdopen(fd, "rb") as handle:
            fd = -1
            data = handle.read(_MAX_LOCAL_JSON_BYTES + 1)
            info_after = os.fstat(handle.fileno())
        if len(data) > _MAX_LOCAL_JSON_BYTES:
            raise LoopbackTransportError(f"{kind}_size_exceeded")
        if (info_before.st_dev, info_before.st_ino, info_before.st_size, info_before.st_mtime_ns) != (
            info_after.st_dev,
            info_after.st_ino,
            info_after.st_size,
            info_after.st_mtime_ns,
        ):
            raise LoopbackTransportError(f"{kind}_changed_during_read")
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LoopbackTransportError(f"invalid_{kind}_json") from exc
    finally:
        if fd >= 0:
            os.close(fd)
    if not isinstance(value, dict):
        raise LoopbackTransportError(f"invalid_{kind}_shape")
    return value, data


def _open_artifact_parent(path: Path, *, create: bool) -> tuple[int, str]:
    if not path.is_absolute() or not path.name:
        raise LoopbackTransportError("artifact_path_invalid")
    return _open_directory_tree(path.parent, create=create), path.name


def _open_directory_tree(path: Path, *, create: bool) -> int:
    if not path.is_absolute():
        raise LoopbackTransportError("directory_path_not_absolute")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(path.anchor, flags)
    except OSError as exc:
        raise LoopbackTransportError("directory_root_invalid") from exc
    try:
        for part in path.parts[1:]:
            try:
                next_fd = os.open(part, flags, dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    raise LoopbackTransportError("directory_missing") from None
                os.mkdir(part, 0o700, dir_fd=fd)
                next_fd = os.open(part, flags, dir_fd=fd)
            except OSError as exc:
                raise LoopbackTransportError("directory_component_unsafe") from exc
            os.close(fd)
            fd = next_fd
        _require_safe_fd_directory(fd, "directory")
        return fd
    except Exception:
        os.close(fd)
        raise


def _regular_file_stat(path: Path, kind: str) -> os.stat_result:
    try:
        info = os.lstat(path)
    except OSError as exc:
        raise LoopbackTransportError(f"{kind}_missing") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise LoopbackTransportError(f"{kind}_not_regular")
    if info.st_nlink != 1:
        raise LoopbackTransportError(f"{kind}_has_multiple_links")
    return info


def _require_safe_directory(path: Path, kind: str) -> None:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise LoopbackTransportError(f"{kind}_not_directory")
    _require_safe_mode(info, kind)


def _require_safe_fd_directory(fd: int, kind: str) -> None:
    info = os.fstat(fd)
    if not stat.S_ISDIR(info.st_mode):
        raise LoopbackTransportError(f"{kind}_not_directory")
    _require_safe_mode(info, kind)


def _require_safe_mode(info: os.stat_result, kind: str) -> None:
    if info.st_uid != os.geteuid():
        raise LoopbackTransportError(f"{kind}_wrong_owner")
    if not (info.st_mode & stat.S_IWUSR) or not (info.st_mode & stat.S_IXUSR):
        raise LoopbackTransportError(f"{kind}_owner_write_search_required")
    if info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise LoopbackTransportError(f"{kind}_group_world_writable")


def _reject_symlink_components(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode):
            raise LoopbackTransportError("path_has_symlink_component")


def _resolve(base: Path, value: Any) -> Path:
    candidate = _literal_path(value, "local_path")
    return _absolute(candidate if candidate.is_absolute() else base / candidate)


def _literal_path(value: Any, label: str) -> Path:
    if not isinstance(value, (str, Path)):
        raise LoopbackTransportError(f"invalid_{label}")
    text = os.fspath(value)
    if not text.strip() or "~" in text or "$" in text:
        raise LoopbackTransportError(f"invalid_{label}")
    return Path(text)


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(path))


def _distinct_roots(paths: Sequence[Path]) -> tuple[Path, ...]:
    roots: list[Path] = []
    for path in paths:
        root = path if path.suffix == "" else path.parent
        if root not in roots:
            roots.append(root)
    return tuple(roots)


def _require_distinct_output_paths(*paths: Path) -> None:
    for index, left in enumerate(paths):
        for right in paths[index + 1 :]:
            if _overlaps(left, right):
                raise LoopbackTransportError("p142_artifact_paths_overlap")


def _overlaps(left: Path, right: Path) -> bool:
    return left == right or left.is_relative_to(right) or right.is_relative_to(left)


def _safe_label(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _LABEL_RE.fullmatch(value) or _UNSAFE_VALUE_RE.search(value):
        raise LoopbackTransportError(f"unsafe_{label}")
    return value


def _positive_int(raw: Mapping[str, Any], key: str) -> int:
    value = raw.get(key)
    if type(value) is not int or value <= 0 or value > 1_099_511_627_776:
        raise LoopbackTransportError(f"invalid_positive_integer:{key}")
    return value


def _hash_value(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise LoopbackTransportError(f"invalid_hash:{label}")
    return value


def _reject_unsafe_values(raw: Mapping[str, Any]) -> None:
    path_keys = {
        "p141_config_path",
        "p141_release_evidence_path",
        "dispatch_dir",
        "journal_dir",
        "receipt_dir",
        "cursor_path",
        "run_dir",
    }

    def walk(value: Any, *, key_name: str | None = None) -> None:
        if isinstance(value, str) and key_name not in path_keys and _UNSAFE_VALUE_RE.search(value):
            raise LoopbackTransportError("forbidden_configuration_value")
        if isinstance(value, Mapping):
            for key, item in value.items():
                if _field_is_forbidden(str(key)) and key not in _CONFIG_FIELDS and key not in _ROUTE_FIELDS:
                    raise LoopbackTransportError("forbidden_configuration_field")
                walk(item, key_name=str(key))
        elif _sequence(value):
            for item in value:
                walk(item, key_name=key_name)

    walk(raw)


def _field_is_forbidden(value: str) -> bool:
    words = {word for word in re.split(r"[^a-z0-9]+", value.lower()) if word}
    return bool(words & _FORBIDDEN_FIELD_WORDS)


def _sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _merge_transport(target: dict[str, int], source: Mapping[str, int]) -> None:
    for key in TRANSPORT_COUNTER_KEYS:
        target[key] += int(source.get(key, 0))


def _validate_clock(cursor: Mapping[str, Any], now: datetime) -> None:
    previous_sequence = cursor.get("last_sequence")
    if type(previous_sequence) is not int:
        raise LoopbackTransportError("invalid_cursor_sequence")
    _utc(now)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise LoopbackTransportError("utc_timestamp_required")
    return value.astimezone(UTC)


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


__all__ = [
    "CONFIG_SCHEMA_VERSION",
    "FORBIDDEN_AUTHORITY_COUNTER_KEYS",
    "LoopbackTransportConfig",
    "LoopbackTransportError",
    "TRANSPORT_COUNTER_KEYS",
    "deterministic_attempt_id",
    "deterministic_dispatch_id",
    "list_loopback_receipts",
    "load_loopback_transport_config",
    "parse_loopback_authority",
    "parse_retry_after",
    "process_loopback_transport",
    "validate_loopback_transport_config",
    "zero_forbidden_authority_counters",
    "zero_transport_counters",
]
