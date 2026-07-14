"""P135 provider-shaped local export attachment.

This module intentionally exposes only deterministic local-file attachment.
It performs no provider, network, environment, subprocess, delivery, action, or
mutation work.
"""

from __future__ import annotations

import errno
import hashlib
import json
import math
import os
import re
import stat
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p120_governance import zero_authority_counters as zero_p120_authority
from app.services.p120_normalization import validate_normalized_record
from app.services.p121_signals import validate_exact_zero_authority, zero_authority_counters
from app.services.p134_observation_authority import validate_contract, validate_decision_receipt

MANIFEST_SCHEMA_VERSION = "p135.export_manifest.v1"
BUNDLE_SCHEMA_VERSION = "p135.normalized_evidence_bundle.v1"
RECORD_SCHEMA_VERSION = "p135.normalized_evidence_record.v1"
FAILURE_BUNDLE_SCHEMA_VERSION = "p135.denominator_failure_bundle.v1"
RECEIPT_SCHEMA_VERSION = "p135.export_execution_receipt.v1"
LEDGER_SCHEMA_VERSION = "p135.export_execution_ledger.v1"

_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_LABEL_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_UTC_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
_CREDENTIAL_RE = re.compile(r"(api[_-]?key|token|secret|password|credential|authorization|bearer|sk_live)", re.I)
_PROMPT_RE = re.compile(r"(ignore previous instructions|curl\s+https?://|run command|execute|shell)", re.I)
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_UNSAFE_PATH_RE = re.compile(r"[:*?<>|`$;&]")

_PROFILES: dict[tuple[str, str], tuple[str, str, str]] = {
    ("grafana", "grafana.dashboard.classic.v1"): ("topology", "telemetry.topology.read", "p135.adapter.grafana.dashboard.classic.v1"),
    ("loki", "loki.query_range.streams.v1"): ("logs", "telemetry.logs.read", "p135.adapter.loki.query_range.streams.v1"),
    ("opentelemetry", "otlp.file.jsonl.v1"): ("metrics", "telemetry.metrics.read", "p135.adapter.otlp.file.jsonl.v1"),
    ("prometheus", "prometheus.query_range.matrix.v1"): ("metrics", "telemetry.metrics.read", "p135.adapter.prometheus.query_range.matrix.v1"),
    ("sentry", "sentry.issues.api.list.v1"): ("events", "telemetry.events.read", "p135.adapter.sentry.issues.api.list.v1"),
}

_LIMIT_BOUNDS: dict[str, tuple[int, int]] = {
    "max_artifacts": (1, 16),
    "max_file_bytes": (1, 4_194_304),
    "max_total_bytes": (1, 16_777_216),
    "max_records_per_artifact": (1, 10_000),
    "max_total_records": (1, 25_000),
    "max_json_depth": (1, 32),
    "max_json_nodes": (1, 200_000),
    "max_string_bytes": (1, 32_768),
    "max_preview_bytes": (0, 256),
    "max_attributes_per_record": (0, 64),
    "max_line_bytes": (1, 1_048_576),
}
_MANIFEST_INPUT_FIELDS = frozenset({"manifest_id", "manifest_version", "created_at", "root_ref_hash", "limits", "artifacts"})
_MANIFEST_FIELDS = frozenset({"schema_version", *_MANIFEST_INPUT_FIELDS, "p134_contract_hash", "manifest_hash"})
_ARTIFACT_INPUT_FIELDS = frozenset(
    {
        "source_id",
        "provider",
        "format",
        "signal_family",
        "relative_path",
        "expected_content_hash",
        "expected_bytes",
        "expected_records",
        "authority_capability",
        "authority_source_ref_hash",
    }
)
_ARTIFACT_FIELDS = frozenset(
    {
        "source_id",
        "provider",
        "format",
        "signal_family",
        "relative_path",
        "expected_content_hash",
        "expected_bytes",
        "expected_records",
        "authority_receipt_hash",
        "authority_capability",
        "artifact_spec_hash",
    }
)
_ACTIVITY_KEYS = (
    "local_stat_count",
    "local_file_open_count",
    "local_file_read_count",
    "local_bytes_read",
    "local_records_parsed",
    "duplicate_validation_read_count",
)
_EXTRA_FORBIDDEN_AUTHORITY_KEYS = (
    "provider_call_count",
    "network_call_count",
    "dns_lookup_count",
    "socket_call_count",
    "credential_read_count",
    "environment_read_count",
    "subprocess_launch_count",
    "signal_count",
    "delivery_count",
    "remediation_count",
    "operator_replacement_count",
)

class P135ExportError(ValueError):
    """Raised when P135 attachment fails closed."""

    def __init__(self, message: str, *, activity: Mapping[str, int] | None = None) -> None:
        super().__init__(message)
        self.activity = dict(activity) if activity is not None else None


@dataclass(frozen=True)
class AttachmentResult:
    bundle: dict[str, Any]
    receipt: dict[str, Any]
    ledger: dict[str, Any]
    activity: dict[str, int]
    duplicate: bool


@dataclass(frozen=True)
class _ReadResult:
    content: bytes
    content_hash: str
    byte_count: int
    pre_identity_hash: str
    post_identity_hash: str
    activity: dict[str, int]


def zero_forbidden_authority() -> dict[str, int]:
    return {**zero_authority_counters(), **{key: 0 for key in _EXTRA_FORBIDDEN_AUTHORITY_KEYS}}


def zero_observation_activity() -> dict[str, int]:
    return {key: 0 for key in _ACTIVITY_KEYS}


def build_export_manifest(data: Mapping[str, Any], contract: Mapping[str, Any], receipts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    raw = _mapping(data, "manifest")
    _expect_exact_fields(raw, _MANIFEST_INPUT_FIELDS, "manifest")
    validate_contract(contract)
    limits = _limits(raw["limits"])
    raw_artifacts = _sequence(raw["artifacts"], "artifacts")
    _bounded_count(len(raw_artifacts), "artifact_count", 1, limits["max_artifacts"])
    receipt_by_hash = _receipt_index(contract, receipts)

    artifacts: list[dict[str, Any]] = []
    total_bytes = 0
    total_records = 0
    source_ids: set[str] = set()
    for item in raw_artifacts:
        artifact = _build_artifact(item, receipt_by_hash, limits)
        source_id = artifact["source_id"]
        if source_id in source_ids:
            raise P135ExportError("duplicate_source_id")
        source_ids.add(source_id)
        total_bytes += artifact["expected_bytes"]
        total_records += artifact["expected_records"]
        artifacts.append(artifact)
    if total_bytes > limits["max_total_bytes"]:
        raise P135ExportError("manifest_total_byte_budget_exceeded")
    if total_records > limits["max_total_records"]:
        raise P135ExportError("manifest_total_record_budget_exceeded")
    artifacts = sorted(artifacts, key=lambda artifact: str(artifact["source_id"]))
    manifest: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "manifest_id": _label(raw["manifest_id"], "manifest_id"),
        "manifest_version": _bounded_int(raw["manifest_version"], "manifest_version", 1, 1_000_000),
        "created_at": _timestamp(raw["created_at"], "created_at"),
        "root_ref_hash": _hash(raw["root_ref_hash"], "root_ref_hash"),
        "p134_contract_hash": contract["contract_hash"],
        "limits": limits,
        "artifacts": artifacts,
    }
    manifest["manifest_hash"] = stable_hash(manifest)
    return manifest


def validate_export_manifest(manifest: Mapping[str, Any], contract: Mapping[str, Any], receipts: Sequence[Mapping[str, Any]]) -> None:
    value = _mapping(manifest, "manifest")
    _expect_exact_fields(value, _MANIFEST_FIELDS, "manifest")
    if value.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise P135ExportError("invalid_manifest_schema")
    validate_contract(contract)
    if value.get("p134_contract_hash") != contract.get("contract_hash"):
        raise P135ExportError("manifest_contract_hash_mismatch")
    _validate_self_hash(value, "manifest_hash", "manifest_hash_invalid")
    limits = _limits(value["limits"])
    artifacts = _sequence(value["artifacts"], "artifacts")
    _bounded_count(len(artifacts), "artifact_count", 1, limits["max_artifacts"])
    if [item.get("source_id") for item in artifacts] != sorted(str(item.get("source_id")) for item in artifacts):
        raise P135ExportError("noncanonical_artifact_order")
    receipt_by_hash = _receipt_index(contract, receipts)
    total_bytes = 0
    total_records = 0
    source_ids: set[str] = set()
    for artifact in artifacts:
        _validate_artifact(artifact, receipt_by_hash, limits)
        source_id = str(artifact["source_id"])
        if source_id in source_ids:
            raise P135ExportError("duplicate_source_id")
        source_ids.add(source_id)
        total_bytes += artifact["expected_bytes"]
        total_records += artifact["expected_records"]
    if total_bytes > limits["max_total_bytes"]:
        raise P135ExportError("manifest_total_byte_budget_exceeded")
    if total_records > limits["max_total_records"]:
        raise P135ExportError("manifest_total_record_budget_exceeded")


def new_execution_ledger(manifest: Mapping[str, Any]) -> dict[str, Any]:
    _hash(_mapping(manifest, "manifest").get("manifest_hash"), "manifest_hash")
    ledger: dict[str, Any] = {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "manifest_hash": manifest["manifest_hash"],
        "contract_hash": manifest["p134_contract_hash"],
        "receipts": [],
        "counters": zero_observation_activity(),
        "authority_counters": zero_forbidden_authority(),
    }
    ledger["ledger_hash"] = stable_hash(ledger)
    return ledger


def attach_export(
    root: Path,
    manifest: Mapping[str, Any],
    source_id: str,
    contract: Mapping[str, Any],
    receipts: Sequence[Mapping[str, Any]],
    ledger: Mapping[str, Any],
    *,
    started_at: str,
    completed_at: str,
    read_chunk: Callable[[int, int], bytes] | None = None,
) -> AttachmentResult:
    validate_export_manifest(manifest, contract, receipts)
    validate_execution_ledger(ledger, manifest, contract, receipts)
    _timestamp(started_at, "started_at")
    if _parse_timestamp(completed_at, "completed_at") < _parse_timestamp(started_at, "started_at"):
        raise P135ExportError("completion_before_start")
    artifact = _artifact_by_source(manifest, source_id)
    authority_receipt = _receipt_index(contract, receipts)[artifact["authority_receipt_hash"]]
    _bind_authority(artifact, authority_receipt)

    read = _read_regular_file(root, artifact, manifest["limits"], read_chunk=read_chunk or os.read)
    if read.byte_count != artifact["expected_bytes"]:
        raise P135ExportError("file_size_mismatch", activity=read.activity)
    if read.content_hash != artifact["expected_content_hash"]:
        raise P135ExportError("content_hash_mismatch", activity=read.activity)
    if read.byte_count > authority_receipt["proposal"]["estimated_response_bytes"]:
        raise P135ExportError("authority_byte_estimate_exceeded", activity=read.activity)

    prior = _prior_success_for_source(ledger, source_id)
    adapter_version = _adapter_version(artifact)
    success_key = stable_hash(
        {
            "schema_version": "p135.success_key.v1",
            "contract_hash": contract["contract_hash"],
            "authority_receipt_hash": artifact["authority_receipt_hash"],
            "artifact_spec_hash": artifact["artifact_spec_hash"],
            "adapter_version": adapter_version,
            "artifact_content_hash": read.content_hash,
        }
    )
    if prior is not None:
        if prior.get("success_key") == success_key:
            activity = dict(read.activity)
            activity["duplicate_validation_read_count"] = 1
            bundle = _duplicate_bundle_stub(artifact, prior)
            return AttachmentResult(bundle=bundle, receipt=deepcopy(dict(prior)), ledger=deepcopy(dict(ledger)), activity=activity, duplicate=True)
        raise P135ExportError("source_id_reuse_conflict")

    try:
        parsed = _parse_content(read.content, artifact, manifest["limits"])
        raw_records = _adapter_records(parsed, artifact, manifest["limits"], completed_at)
        if len(raw_records) > artifact["expected_records"]:
            raise P135ExportError("authority_record_estimate_exceeded")
        if len(raw_records) > manifest["limits"]["max_records_per_artifact"]:
            raise P135ExportError("artifact_record_budget_exceeded")
        receipt_ref = stable_hash({"schema_version": "p135.pending_execution_receipt_ref.v1", "success_key": success_key})
        records = [_p135_record(raw, artifact, read.content_hash, ordinal, receipt_ref, manifest["limits"], completed_at) for ordinal, raw in enumerate(raw_records, start=1)]
        bundle = _success_bundle(artifact, read, records)
        receipt = _execution_receipt(
            manifest,
            artifact,
            authority_receipt,
            read,
            bundle,
            ledger,
            started_at,
            completed_at,
            status="succeeded",
            success_key=success_key,
            adapter_version=adapter_version,
        )
        bundle = _bind_records_to_receipt(bundle, receipt["receipt_id"])
        receipt["normalized_bundle_hash"] = bundle["bundle_hash"]
        receipt["receipt_hash"] = stable_hash({key: value for key, value in receipt.items() if key != "receipt_hash"})
        next_ledger = _append_success_ledger(ledger, receipt)
        activity = dict(read.activity)
        activity["local_records_parsed"] = len(records)
        return AttachmentResult(bundle=bundle, receipt=receipt, ledger=next_ledger, activity=activity, duplicate=False)
    except P135ExportError as exc:
        failure_bundle = _failure_bundle(artifact, read, str(exc), completed_at)
        receipt = _execution_receipt(
            manifest,
            artifact,
            authority_receipt,
            read,
            failure_bundle,
            ledger,
            started_at,
            completed_at,
            status="failed",
            success_key="",
            adapter_version=adapter_version,
        )
        failure_bundle = _bind_records_to_receipt(failure_bundle, receipt["receipt_id"])
        receipt["normalized_bundle_hash"] = failure_bundle["bundle_hash"]
        receipt["receipt_hash"] = stable_hash({key: value for key, value in receipt.items() if key != "receipt_hash"})
        activity = dict(read.activity)
        activity["local_records_parsed"] = len(failure_bundle["records"])
        return AttachmentResult(bundle=failure_bundle, receipt=receipt, ledger=deepcopy(dict(ledger)), activity=activity, duplicate=False)


def validate_normalized_bundle(bundle: Mapping[str, Any]) -> None:
    value = _mapping(bundle, "bundle")
    _expect_exact_fields(
        value,
        frozenset(
            {
                "schema_version",
                "source_id",
                "provider",
                "format",
                "signal_family",
                "artifact_content_hash",
                "artifact_bytes",
                "record_count",
                "records",
                "bundle_hash",
            }
        ),
        "bundle",
    )
    if value.get("schema_version") != BUNDLE_SCHEMA_VERSION:
        raise P135ExportError("invalid_bundle_schema")
    records = _sequence(value["records"], "records")
    if value.get("record_count") != len(records):
        raise P135ExportError("bundle_record_count_mismatch")
    for ordinal, record in enumerate(records, start=1):
        _validate_p135_record(
            record,
            ordinal,
            source_id=str(value.get("source_id")),
            provider=str(value.get("provider")),
            format_name=str(value.get("format")),
            artifact_hash=_hash(value.get("artifact_content_hash"), "artifact_content_hash"),
        )
    _validate_self_hash(value, "bundle_hash", "bundle_hash_invalid")


def validate_denominator_failure_bundle(bundle: Mapping[str, Any]) -> None:
    value = _mapping(bundle, "bundle")
    _expect_exact_fields(
        value,
        frozenset(
            {
                "schema_version",
                "source_id",
                "provider",
                "format",
                "signal_family",
                "artifact_content_hash",
                "artifact_bytes",
                "failure_reason",
                "record_count",
                "records",
                "bundle_hash",
            }
        ),
        "bundle",
    )
    if value.get("schema_version") != FAILURE_BUNDLE_SCHEMA_VERSION:
        raise P135ExportError("invalid_failure_bundle_schema")
    records = _sequence(value["records"], "records")
    if not records or value.get("record_count") != len(records):
        raise P135ExportError("bundle_record_count_mismatch")
    for ordinal, record in enumerate(records, start=1):
        _validate_p135_record(
            record,
            ordinal,
            source_id=str(value.get("source_id")),
            provider=str(value.get("provider")),
            format_name=str(value.get("format")),
            artifact_hash=_hash(value.get("artifact_content_hash"), "artifact_content_hash"),
        )
        if record["p120_record"]["evidence_state"] != "fail_closed" or record["p120_record"]["denominator_visible"] is not True:
            raise P135ExportError("failure_record_not_denominator_visible")
    _validate_self_hash(value, "bundle_hash", "bundle_hash_invalid")


def validate_execution_ledger(
    ledger: Mapping[str, Any],
    manifest: Mapping[str, Any],
    contract: Mapping[str, Any],
    receipts: Sequence[Mapping[str, Any]],
    *,
    bundles: Sequence[Mapping[str, Any]] | None = None,
) -> None:
    value = _mapping(ledger, "ledger")
    _expect_exact_fields(value, frozenset({"schema_version", "manifest_hash", "contract_hash", "receipts", "counters", "authority_counters", "ledger_hash"}), "ledger")
    if value.get("schema_version") != LEDGER_SCHEMA_VERSION:
        raise P135ExportError("invalid_ledger_schema")
    _validate_forbidden_authority(value.get("authority_counters"))
    _validate_activity(value.get("counters"))
    if value.get("manifest_hash") != manifest.get("manifest_hash"):
        raise P135ExportError("ledger_manifest_hash_mismatch")
    if value.get("contract_hash") != contract.get("contract_hash"):
        raise P135ExportError("ledger_contract_hash_mismatch")
    validate_export_manifest(manifest, contract, receipts)
    bundle_by_hash: dict[str, Mapping[str, Any]] = {}
    if bundles is not None:
        for bundle in bundles:
            schema = bundle.get("schema_version")
            if schema == BUNDLE_SCHEMA_VERSION:
                validate_normalized_bundle(bundle)
            elif schema == FAILURE_BUNDLE_SCHEMA_VERSION:
                validate_denominator_failure_bundle(bundle)
            else:
                raise P135ExportError("invalid_promoted_bundle_schema")
            bundle_hash = _hash(bundle.get("bundle_hash"), "bundle_hash")
            if bundle_hash in bundle_by_hash:
                raise P135ExportError("duplicate_promoted_bundle_hash")
            bundle_by_hash[bundle_hash] = bundle
    expected = zero_observation_activity()
    seen_sources: set[str] = set()
    previous = _ledger_genesis_hash(value)
    for receipt in _sequence(value["receipts"], "receipts"):
        _validate_execution_receipt(receipt, manifest, contract, previous)
        if receipt.get("status") != "succeeded":
            raise P135ExportError("failed_receipt_promoted")
        if bundles is not None:
            bound_bundle = bundle_by_hash.get(str(receipt["normalized_bundle_hash"]))
            if bound_bundle is None:
                raise P135ExportError("receipt_bundle_hash_mismatch")
            _validate_receipt_bundle_binding(receipt, bound_bundle)
        source_id = str(receipt["source_id"])
        if source_id in seen_sources:
            raise P135ExportError("duplicate_ledger_source_id")
        seen_sources.add(source_id)
        activity = _mapping(receipt["observation_activity_counters"], "observation_activity_counters")
        for key in _ACTIVITY_KEYS:
            expected[key] += int(activity[key])
        previous = str(receipt["receipt_hash"])
    if dict(value["counters"]) != expected:
        raise P135ExportError("ledger_counter_mismatch")
    if bundles is not None and set(bundle_by_hash) != {
        str(receipt["normalized_bundle_hash"]) for receipt in value["receipts"]
    }:
        raise P135ExportError("unbound_promoted_bundle")
    _validate_self_hash(value, "ledger_hash", "ledger_hash_invalid")


def _build_artifact(raw_value: Any, receipts: Mapping[str, Mapping[str, Any]], limits: Mapping[str, int]) -> dict[str, Any]:
    raw = _mapping(raw_value, "artifact")
    _expect_exact_fields(raw, _ARTIFACT_INPUT_FIELDS, "artifact")
    source_id = _label(raw["source_id"], "source_id")
    provider = _text(raw["provider"], "provider")
    fmt = _text(raw["format"], "format")
    profile = _PROFILES.get((provider, fmt))
    if profile is None:
        raise P135ExportError("unsupported_provider_format")
    signal_family, capability, _adapter = profile
    if raw["signal_family"] != signal_family:
        raise P135ExportError("signal_family_mismatch")
    if raw["authority_capability"] != capability:
        raise P135ExportError("authority_capability_mismatch")
    expected_bytes = _bounded_int(raw["expected_bytes"], "expected_bytes", 1, limits["max_file_bytes"])
    expected_records = _bounded_int(raw["expected_records"], "expected_records", 1, limits["max_records_per_artifact"])
    receipt = _matching_receipt(receipts, raw["authority_source_ref_hash"], expected_bytes, expected_records)
    artifact: dict[str, Any] = {
        "source_id": source_id,
        "provider": provider,
        "format": fmt,
        "signal_family": signal_family,
        "relative_path": _relative_path(raw["relative_path"]),
        "expected_content_hash": _hash(raw["expected_content_hash"], "expected_content_hash"),
        "expected_bytes": expected_bytes,
        "expected_records": expected_records,
        "authority_receipt_hash": receipt["receipt_hash"],
        "authority_capability": capability,
    }
    artifact["artifact_spec_hash"] = stable_hash(artifact)
    return artifact


def _validate_artifact(artifact: Mapping[str, Any], receipts: Mapping[str, Mapping[str, Any]], limits: Mapping[str, int]) -> None:
    value = _mapping(artifact, "artifact")
    _expect_exact_fields(value, _ARTIFACT_FIELDS, "artifact")
    _validate_self_hash(value, "artifact_spec_hash", "artifact_spec_hash_invalid")
    rebuilt_input = {
        "source_id": value["source_id"],
        "provider": value["provider"],
        "format": value["format"],
        "signal_family": value["signal_family"],
        "relative_path": value["relative_path"],
        "expected_content_hash": value["expected_content_hash"],
        "expected_bytes": value["expected_bytes"],
        "expected_records": value["expected_records"],
        "authority_capability": value["authority_capability"],
        "authority_source_ref_hash": receipts[value["authority_receipt_hash"]]["proposal"]["source_ref_hash"],
    }
    rebuilt = _build_artifact(rebuilt_input, receipts, limits)
    if dict(value) != rebuilt:
        raise P135ExportError("artifact_semantic_mismatch")


def _read_regular_file(
    root: Path,
    artifact: Mapping[str, Any],
    limits: Mapping[str, int],
    *,
    read_chunk: Callable[[int, int], bytes],
) -> _ReadResult:
    relative = str(artifact["relative_path"])
    activity = zero_observation_activity()
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    directory_flags = flags | getattr(os, "O_DIRECTORY", 0)
    opened: list[int] = []
    try:
        current_fd = os.open(root, directory_flags)
        opened.append(current_fd)
        parts = Path(relative).parts
        for component in parts[:-1]:
            current_fd = os.open(component, directory_flags, dir_fd=current_fd)
            opened.append(current_fd)
        file_fd = os.open(parts[-1], flags, dir_fd=current_fd)
        opened.append(file_fd)
    except OSError as exc:
        for descriptor in reversed(opened):
            os.close(descriptor)
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise P135ExportError("symlink_rejected") from exc
        raise P135ExportError("file_open_failed") from exc
    try:
        pre = os.fstat(file_fd)
        activity["local_stat_count"] += 1
        if not stat.S_ISREG(pre.st_mode):
            raise P135ExportError("nonregular_file")
        if getattr(pre, "st_nlink", 1) != 1:
            raise P135ExportError("hardlink_rejected")
        if pre.st_size > limits["max_file_bytes"] or pre.st_size > artifact["expected_bytes"]:
            raise P135ExportError("file_size_mismatch")
        digest = hashlib.sha256()
        content = bytearray()
        activity["local_file_open_count"] = 1
        while True:
            chunk = read_chunk(file_fd, 8192)
            if not chunk:
                break
            activity["local_file_read_count"] = 1
            activity["local_bytes_read"] += len(chunk)
            if activity["local_bytes_read"] > limits["max_file_bytes"] or activity["local_bytes_read"] > artifact["expected_bytes"]:
                raise P135ExportError("file_size_mismatch")
            digest.update(chunk)
            content.extend(chunk)
        post = os.fstat(file_fd)
        activity["local_stat_count"] += 1
        try:
            post_path = os.stat(parts[-1], dir_fd=current_fd, follow_symlinks=False)
        except OSError as exc:
            raise P135ExportError("file_identity_changed") from exc
        activity["local_stat_count"] += 1
        if stat.S_ISLNK(post_path.st_mode) or _identity(pre) != _identity(post) or _identity(post) != _identity(post_path):
            raise P135ExportError("file_identity_changed")
        return _ReadResult(
            content=bytes(content),
            content_hash="sha256:" + digest.hexdigest(),
            byte_count=len(content),
            pre_identity_hash=stable_hash(_identity(pre)),
            post_identity_hash=stable_hash(_identity(post)),
            activity=activity,
        )
    except P135ExportError as exc:
        if exc.activity is not None:
            raise
        raise P135ExportError(str(exc), activity=activity) from exc
    except OSError as exc:
        raise P135ExportError("file_read_failed", activity=activity) from exc
    finally:
        for descriptor in reversed(opened):
            os.close(descriptor)


def _parse_content(content: bytes, artifact: Mapping[str, Any], limits: Mapping[str, int]) -> Any:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise P135ExportError("invalid_utf8") from exc
    if artifact["format"] == "otlp.file.jsonl.v1":
        lines = text.splitlines()
        if not lines:
            raise P135ExportError("empty_jsonl")
        parsed = []
        for line in lines:
            if len(line.encode("utf-8")) > limits["max_line_bytes"]:
                raise P135ExportError("line_budget_exceeded")
            parsed.append(_json_loads(line, limits))
        return parsed
    return _json_loads(text, limits)


def _json_loads(text: str, limits: Mapping[str, int]) -> Any:
    def pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        seen: set[str] = set()
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in seen:
                raise P135ExportError("duplicate_json_key")
            seen.add(key)
            result[key] = value
        return result

    def bad_constant(value: str) -> None:
        raise P135ExportError(f"non_finite_number:{value}")

    try:
        parsed = json.loads(text, object_pairs_hook=pairs_hook, parse_constant=bad_constant)
    except P135ExportError:
        raise
    except json.JSONDecodeError as exc:
        raise P135ExportError("invalid_json") from exc
    _check_structure(parsed, limits)
    return parsed


def _adapter_records(parsed: Any, artifact: Mapping[str, Any], limits: Mapping[str, int], ingested_at: str) -> list[dict[str, Any]]:
    provider = artifact["provider"]
    if provider == "prometheus":
        return _prometheus_records(parsed, artifact, limits, ingested_at)
    if provider == "loki":
        return _loki_records(parsed, artifact, limits, ingested_at)
    if provider == "grafana":
        return _grafana_records(parsed, artifact, limits, ingested_at)
    if provider == "sentry":
        return _sentry_records(parsed, artifact, limits, ingested_at)
    if provider == "opentelemetry":
        return _otlp_records(parsed, artifact, limits, ingested_at)
    raise P135ExportError("unsupported_provider")


def _prometheus_records(parsed: Any, artifact: Mapping[str, Any], limits: Mapping[str, int], ingested_at: str) -> list[dict[str, Any]]:
    data = _provider_mapping(parsed, "prometheus")
    if data.get("status") != "success" or _mapping(data.get("data"), "data").get("resultType") != "matrix":
        raise P135ExportError("prometheus_result_type_mismatch")
    records: list[dict[str, Any]] = []
    for series in _sequence(data["data"].get("result"), "result"):
        metric = _mapping(series.get("metric"), "metric")
        labels = _redacted_labels(metric, limits)
        for sample in _sequence(series.get("values"), "values"):
            if not isinstance(sample, list) or len(sample) != 2:
                raise P135ExportError("malformed_prometheus_sample")
            timestamp = _number(sample[0], "prometheus_timestamp")
            value = _number(sample[1], "prometheus_value")
            observed_at = _from_unix_seconds(timestamp)
            records.append(
                _raw_p120(
                    artifact,
                    record_id=stable_hash({"metric": metric, "sample": sample}),
                    source_schema="prometheus",
                    modality="metric",
                    signal_name=str(metric.get("__name__", "prometheus_metric")),
                    value=value,
                    unit="sample",
                    observed_at=observed_at,
                    window={"start": observed_at, "end": observed_at},
                    labels=labels,
                    raw_selected={"metric": metric, "sample": sample},
                    ingested_at=ingested_at,
                )
            )
    return records


def _loki_records(parsed: Any, artifact: Mapping[str, Any], limits: Mapping[str, int], ingested_at: str) -> list[dict[str, Any]]:
    data = _provider_mapping(parsed, "loki")
    if data.get("status") != "success" or _mapping(data.get("data"), "data").get("resultType") != "streams":
        raise P135ExportError("loki_result_type_mismatch")
    records: list[dict[str, Any]] = []
    for stream in _sequence(data["data"].get("result"), "result"):
        labels = _redacted_labels(_mapping(stream.get("stream"), "stream"), limits)
        for value in _sequence(stream.get("values"), "values"):
            if not isinstance(value, list) or len(value) != 2 or not isinstance(value[0], str) or not value[0].isdigit():
                raise P135ExportError("malformed_loki_timestamp")
            line = _bounded_text(value[1], "log_line", limits["max_line_bytes"])
            observed_at = _from_unix_nanos(value[0])
            records.append(
                _raw_p120(
                    artifact,
                    record_id=stable_hash({"stream": labels, "value": value}),
                    source_schema="log_event",
                    modality="log",
                    signal_name="loki_log_line",
                    value=1,
                    unit="line",
                    observed_at=observed_at,
                    window={"start": observed_at, "end": observed_at},
                    labels=labels,
                    raw_selected={"stream": labels, "line_hash": stable_hash({"line": line})},
                    ingested_at=ingested_at,
                )
            )
    return records


def _grafana_records(parsed: Any, artifact: Mapping[str, Any], limits: Mapping[str, int], ingested_at: str) -> list[dict[str, Any]]:
    data = _provider_mapping(parsed, "grafana")
    _bounded_int(data.get("schemaVersion"), "grafana_schemaVersion", 1, 10_000)
    _bounded_int(data.get("version"), "grafana_version", 0, 1_000_000)
    panels = _sequence(data.get("panels"), "panels")
    seen: set[int] = set()
    records: list[dict[str, Any]] = []
    for panel in panels:
        panel_map = _mapping(panel, "panel")
        panel_id = _bounded_int(panel_map.get("id"), "panel_id", 1, 1_000_000)
        if panel_id in seen:
            raise P135ExportError("duplicate_grafana_panel_id")
        seen.add(panel_id)
        labels = _redacted_labels(
            {
                "dashboard": data.get("uid", data.get("title", "dashboard")),
                "panel": panel_map.get("title", f"panel-{panel_id}"),
                "panel_type": panel_map.get("type", "unknown"),
            },
            limits,
        )
        observed_at = ingested_at
        records.append(
            _raw_p120(
                artifact,
                record_id=stable_hash({"dashboard": data.get("uid"), "panel_id": panel_id}),
                source_schema="topology",
                modality="topology",
                signal_name="grafana_panel_declared",
                value=1,
                unit="declaration",
                observed_at=observed_at,
                window={"start": observed_at, "end": observed_at},
                labels=labels,
                raw_selected={"panel_id": panel_id, "panel_hash": stable_hash(panel_map)},
                ingested_at=ingested_at,
            )
        )
    if not records:
        raise P135ExportError("missing_grafana_panels")
    return records


def _sentry_records(parsed: Any, artifact: Mapping[str, Any], limits: Mapping[str, int], ingested_at: str) -> list[dict[str, Any]]:
    issues = _sequence(parsed, "sentry_issues")
    seen: set[str] = set()
    records: list[dict[str, Any]] = []
    for issue in issues:
        item = _mapping(issue, "issue")
        issue_id = _text(item.get("id"), "issue_id")
        if issue_id in seen:
            raise P135ExportError("duplicate_sentry_issue_id")
        seen.add(issue_id)
        observed_at = _timestamp(item.get("lastSeen"), "lastSeen")
        records.append(
            _raw_p120(
                artifact,
                record_id=issue_id,
                source_schema="sentry",
                modality="event",
                signal_name=_safe_signal(item.get("title", "sentry_issue")),
                value=_number(item.get("count", 1), "count"),
                unit="event",
                observed_at=observed_at,
                window={"start": _timestamp(item.get("firstSeen", observed_at), "firstSeen"), "end": observed_at},
                labels=_redacted_labels({"project": _mapping(item.get("project"), "project").get("slug", "unknown"), "level": item.get("level", "unknown")}, limits),
                raw_selected={"issue_hash": stable_hash(item), "issue_id": issue_id},
                ingested_at=ingested_at,
                severity=str(item.get("level", "unknown")),
            )
        )
    if not records:
        raise P135ExportError("missing_sentry_issues")
    return records


def _otlp_records(parsed: Any, artifact: Mapping[str, Any], limits: Mapping[str, int], ingested_at: str) -> list[dict[str, Any]]:
    lines = _sequence(parsed, "otlp_lines")
    records: list[dict[str, Any]] = []
    for line in lines:
        item = _mapping(line, "otlp_line")
        signals = [key for key in ("resourceMetrics", "resourceLogs", "resourceSpans") if key in item]
        if signals != ["resourceMetrics"]:
            raise P135ExportError("otlp_signal_family_mismatch")
        for resource_metric in _sequence(item["resourceMetrics"], "resourceMetrics"):
            resource = _mapping(_mapping(resource_metric, "resourceMetric").get("resource"), "resource")
            resource_labels = _attributes(resource.get("attributes", []), limits)
            for scope_metric in _sequence(resource_metric.get("scopeMetrics"), "scopeMetrics"):
                for metric in _sequence(scope_metric.get("metrics"), "metrics"):
                    metric_map = _mapping(metric, "metric")
                    name = _text(metric_map.get("name"), "metric_name")
                    unit = str(metric_map.get("unit", ""))
                    points = _sequence(_mapping(metric_map.get("gauge"), "gauge").get("dataPoints"), "dataPoints")
                    for point in points:
                        point_map = _mapping(point, "point")
                        timestamp = _text(point_map.get("timeUnixNano"), "timeUnixNano")
                        if not timestamp.isdigit():
                            raise P135ExportError("invalid_otlp_time")
                        labels = {**resource_labels, **_attributes(point_map.get("attributes", []), limits)}
                        observed_at = _from_unix_nanos(timestamp)
                        records.append(
                            _raw_p120(
                                artifact,
                                record_id=stable_hash({"metric": name, "point": point_map}),
                                source_schema="opentelemetry",
                                modality="metric",
                                signal_name=name,
                                value=_number(point_map.get("asDouble", point_map.get("asInt")), "otlp_value"),
                                unit=unit or "unit",
                                observed_at=observed_at,
                                window={"start": observed_at, "end": observed_at},
                                labels=labels,
                                raw_selected={"metric": name, "point_hash": stable_hash(point_map)},
                                ingested_at=ingested_at,
                            )
                        )
    if not records:
        raise P135ExportError("missing_otlp_records")
    return records


def _raw_p120(
    artifact: Mapping[str, Any],
    *,
    record_id: str,
    source_schema: str,
    modality: str,
    signal_name: str,
    value: Any,
    unit: str,
    observed_at: str,
    window: Mapping[str, str],
    labels: Mapping[str, str],
    raw_selected: Mapping[str, Any],
    ingested_at: str,
    severity: str = "unknown",
) -> dict[str, Any]:
    service = str(labels.get("service", labels.get("job", labels.get("project", "unknown")))) or "unknown"
    record = {
        "telemetry_record_id": str(record_id),
        "source_id": artifact["source_id"],
        "system_id": stable_hash({"p135_system": artifact["source_id"]}),
        "service_id": service,
        "entity_ref": stable_hash({"entity": service, "source": artifact["source_id"]}),
        "modality": modality,
        "observed_at": observed_at,
        "ingested_at": ingested_at,
        "window": dict(window),
        "signal_name": signal_name,
        "value": value,
        "unit": unit,
        "severity": severity,
        "labels": dict(sorted(labels.items())),
        "topology_refs": [],
        "deploy_config_refs": [],
        "redaction_receipt": stable_hash({"redacted": raw_selected}),
        "normalization_version": "p120.telemetry_normalization.v1",
        "source_hash": stable_hash(raw_selected),
        "authority_counters": zero_p120_authority(),
        "evidence_state": "valid",
        "state_reasons": [],
        "denominator_visible": True,
        "source_schema": source_schema,
        "raw_ref": {"source_hash": stable_hash(raw_selected), "record_id": str(record_id)},
    }
    validate_normalized_record(record)
    return record


def _p135_record(
    p120_record: Mapping[str, Any],
    artifact: Mapping[str, Any],
    artifact_hash: str,
    ordinal: int,
    receipt_ref: str,
    limits: Mapping[str, int],
    ingested_at: str,
) -> dict[str, Any]:
    del ingested_at
    source_hash = stable_hash(p120_record["raw_ref"])
    selected = json.dumps(p120_record["labels"], sort_keys=True, separators=(",", ":"))
    preview, flags = _preview_and_flags(selected, limits["max_preview_bytes"])
    if any(isinstance(value, str) and _HASH_RE.fullmatch(value) for value in _mapping(p120_record.get("labels"), "labels").values()):
        flags = sorted({*flags, "credential_like_text", "prompt_like_text"})
    record: dict[str, Any] = {
        "schema_version": RECORD_SCHEMA_VERSION,
        "evidence_id": stable_hash({"source": artifact["source_id"], "ordinal": ordinal, "source_hash": source_hash}),
        "ordinal": ordinal,
        "provider": artifact["provider"],
        "format": artifact["format"],
        "p120_record": deepcopy(dict(p120_record)),
        "content_hash": stable_hash({"artifact": artifact_hash, "record": source_hash}),
        "redacted_preview": preview,
        "risk_flags": flags,
        "source_record_hash": source_hash,
        "execution_receipt_ref": receipt_ref,
    }
    record["record_hash"] = stable_hash(record)
    return record


def _success_bundle(artifact: Mapping[str, Any], read: _ReadResult, records: list[dict[str, Any]]) -> dict[str, Any]:
    bundle: dict[str, Any] = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "source_id": artifact["source_id"],
        "provider": artifact["provider"],
        "format": artifact["format"],
        "signal_family": artifact["signal_family"],
        "artifact_content_hash": read.content_hash,
        "artifact_bytes": read.byte_count,
        "record_count": len(records),
        "records": records,
    }
    bundle["bundle_hash"] = stable_hash(bundle)
    validate_normalized_bundle(bundle)
    return bundle


def _failure_bundle(artifact: Mapping[str, Any], read: _ReadResult, reason: str, ingested_at: str) -> dict[str, Any]:
    p120 = _raw_p120(
        artifact,
        record_id=stable_hash({"failure": reason, "artifact": read.content_hash}),
        source_schema="p135_failure",
        modality="event",
        signal_name="p135_fail_closed",
        value=1,
        unit="failure",
        observed_at=ingested_at,
        window={"start": ingested_at, "end": ingested_at},
        labels={"failure_reason": _safe_label_value(reason)},
        raw_selected={"failure_reason": reason, "artifact_content_hash": read.content_hash},
        ingested_at=ingested_at,
        severity="error",
    )
    p120["evidence_state"] = "fail_closed"
    p120["state_reasons"] = [reason]
    validate_normalized_record(p120)
    record = _p135_record(p120, artifact, read.content_hash, 1, stable_hash({"pending_failure": reason}), {"max_preview_bytes": 96}, ingested_at)
    bundle: dict[str, Any] = {
        "schema_version": FAILURE_BUNDLE_SCHEMA_VERSION,
        "source_id": artifact["source_id"],
        "provider": artifact["provider"],
        "format": artifact["format"],
        "signal_family": artifact["signal_family"],
        "artifact_content_hash": read.content_hash,
        "artifact_bytes": read.byte_count,
        "failure_reason": reason,
        "record_count": 1,
        "records": [record],
    }
    bundle["bundle_hash"] = stable_hash(bundle)
    validate_denominator_failure_bundle(bundle)
    return bundle


def _execution_receipt(
    manifest: Mapping[str, Any],
    artifact: Mapping[str, Any],
    authority_receipt: Mapping[str, Any],
    read: _ReadResult,
    bundle: Mapping[str, Any],
    ledger: Mapping[str, Any],
    started_at: str,
    completed_at: str,
    *,
    status: str,
    success_key: str,
    adapter_version: str,
) -> dict[str, Any]:
    observation_activity = dict(read.activity)
    observation_activity["local_records_parsed"] = int(bundle["record_count"])
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "receipt_id": stable_hash({"schema_version": "p135.execution_receipt_id.v1", "success_key": success_key or read.content_hash, "status": status}),
        "status": status,
        "source_id": artifact["source_id"],
        "provider": artifact["provider"],
        "format": artifact["format"],
        "adapter_version": adapter_version,
        "signal_family": artifact["signal_family"],
        "manifest_hash": manifest["manifest_hash"],
        "artifact_spec_hash": artifact["artifact_spec_hash"],
        "p134_contract_hash": manifest["p134_contract_hash"],
        "p134_decision_receipt_hash": artifact["authority_receipt_hash"],
        "root_ref_hash": manifest["root_ref_hash"],
        "path_ref_hash": stable_hash({"relative_path": artifact["relative_path"]}),
        "artifact_content_hash": read.content_hash,
        "bytes_read": read.byte_count,
        "records_normalized": bundle["record_count"],
        "started_at": started_at,
        "completed_at": completed_at,
        "pre_file_identity_hash": read.pre_identity_hash,
        "post_file_identity_hash": read.post_identity_hash,
        "normalized_bundle_hash": bundle["bundle_hash"],
        "previous_execution_receipt_hash": _previous_receipt_hash(ledger),
        "success_key": success_key,
        "authority_counters": zero_forbidden_authority(),
        "observation_activity_counters": observation_activity,
    }
    _bind_authority(artifact, authority_receipt)
    receipt["receipt_hash"] = stable_hash(receipt)
    return receipt


def _append_success_ledger(ledger: Mapping[str, Any], receipt: Mapping[str, Any]) -> dict[str, Any]:
    next_ledger = deepcopy(dict(ledger))
    receipts = list(next_ledger["receipts"])
    receipts.append(deepcopy(dict(receipt)))
    next_ledger["receipts"] = receipts
    counters = dict(next_ledger["counters"])
    activity = _mapping(receipt["observation_activity_counters"], "observation_activity_counters")
    for key in _ACTIVITY_KEYS:
        counters[key] += int(activity[key])
    next_ledger["counters"] = counters
    next_ledger["ledger_hash"] = stable_hash({key: value for key, value in next_ledger.items() if key != "ledger_hash"})
    return next_ledger


def _bind_records_to_receipt(bundle: Mapping[str, Any], receipt_hash: str) -> dict[str, Any]:
    result = deepcopy(dict(bundle))
    records = []
    for record in result["records"]:
        item = deepcopy(dict(record))
        item["execution_receipt_ref"] = receipt_hash
        item["record_hash"] = stable_hash({key: value for key, value in item.items() if key != "record_hash"})
        records.append(item)
    result["records"] = records
    result["bundle_hash"] = stable_hash({key: value for key, value in result.items() if key != "bundle_hash"})
    return result


def _validate_execution_receipt(receipt: Mapping[str, Any], manifest: Mapping[str, Any], contract: Mapping[str, Any], previous_hash: str) -> None:
    value = _mapping(receipt, "receipt")
    expected = frozenset(
        {
            "schema_version",
            "receipt_id",
            "status",
            "source_id",
            "provider",
            "format",
            "adapter_version",
            "signal_family",
            "manifest_hash",
            "artifact_spec_hash",
            "p134_contract_hash",
            "p134_decision_receipt_hash",
            "root_ref_hash",
            "path_ref_hash",
            "artifact_content_hash",
            "bytes_read",
            "records_normalized",
            "started_at",
            "completed_at",
            "pre_file_identity_hash",
            "post_file_identity_hash",
            "normalized_bundle_hash",
            "previous_execution_receipt_hash",
            "success_key",
            "authority_counters",
            "observation_activity_counters",
            "receipt_hash",
        }
    )
    _expect_exact_fields(value, expected, "receipt")
    if value.get("schema_version") != RECEIPT_SCHEMA_VERSION:
        raise P135ExportError("invalid_receipt_schema")
    status = value.get("status")
    if status not in {"succeeded", "failed"}:
        raise P135ExportError("invalid_receipt_status")
    if value.get("manifest_hash") != manifest.get("manifest_hash") or value.get("p134_contract_hash") != contract.get("contract_hash"):
        raise P135ExportError("receipt_binding_mismatch")
    artifact = _artifact_by_source(manifest, str(value.get("source_id")))
    for field, expected_value in {
        "provider": artifact["provider"],
        "format": artifact["format"],
        "adapter_version": _adapter_version(artifact),
        "signal_family": artifact["signal_family"],
        "artifact_spec_hash": artifact["artifact_spec_hash"],
        "p134_decision_receipt_hash": artifact["authority_receipt_hash"],
        "root_ref_hash": manifest["root_ref_hash"],
        "path_ref_hash": stable_hash({"relative_path": artifact["relative_path"]}),
        "artifact_content_hash": artifact["expected_content_hash"],
        "bytes_read": artifact["expected_bytes"],
    }.items():
        if value.get(field) != expected_value:
            raise P135ExportError(f"receipt_{field}_mismatch")
    for field in (
        "receipt_id",
        "manifest_hash",
        "artifact_spec_hash",
        "p134_contract_hash",
        "p134_decision_receipt_hash",
        "root_ref_hash",
        "path_ref_hash",
        "artifact_content_hash",
        "pre_file_identity_hash",
        "post_file_identity_hash",
        "normalized_bundle_hash",
        "previous_execution_receipt_hash",
    ):
        _hash(value.get(field), field)
    if value.get("pre_file_identity_hash") != value.get("post_file_identity_hash"):
        raise P135ExportError("receipt_file_identity_mismatch")
    _timestamp(value.get("started_at"), "started_at")
    if _parse_timestamp(value.get("completed_at"), "completed_at") < _parse_timestamp(value.get("started_at"), "started_at"):
        raise P135ExportError("completion_before_start")
    records_normalized = _bounded_int(value.get("records_normalized"), "records_normalized", 1, int(artifact["expected_records"]))
    success_key = value.get("success_key")
    if status == "succeeded":
        expected_success_key = stable_hash(
            {
                "schema_version": "p135.success_key.v1",
                "contract_hash": contract["contract_hash"],
                "authority_receipt_hash": artifact["authority_receipt_hash"],
                "artifact_spec_hash": artifact["artifact_spec_hash"],
                "adapter_version": _adapter_version(artifact),
                "artifact_content_hash": artifact["expected_content_hash"],
            }
        )
        if success_key != expected_success_key:
            raise P135ExportError("receipt_success_key_mismatch")
    elif success_key != "":
        raise P135ExportError("failed_receipt_success_key_present")
    expected_receipt_id = stable_hash(
        {
            "schema_version": "p135.execution_receipt_id.v1",
            "success_key": success_key or value["artifact_content_hash"],
            "status": status,
        }
    )
    if value.get("receipt_id") != expected_receipt_id:
        raise P135ExportError("receipt_id_mismatch")
    if value.get("previous_execution_receipt_hash") != previous_hash:
        raise P135ExportError("receipt_previous_hash_mismatch")
    _validate_forbidden_authority(value.get("authority_counters"))
    _validate_activity(value.get("observation_activity_counters"))
    activity = _mapping(value["observation_activity_counters"], "observation_activity_counters")
    expected_activity = {
        "local_stat_count": 3,
        "local_file_open_count": 1,
        "local_file_read_count": 1,
        "local_bytes_read": value["bytes_read"],
        "local_records_parsed": records_normalized,
        "duplicate_validation_read_count": 0,
    }
    if dict(activity) != expected_activity:
        raise P135ExportError("receipt_observation_activity_mismatch")
    _validate_self_hash(value, "receipt_hash", "receipt_hash_invalid")


def _validate_receipt_bundle_binding(receipt: Mapping[str, Any], bundle: Mapping[str, Any]) -> None:
    if bundle.get("bundle_hash") != receipt.get("normalized_bundle_hash"):
        raise P135ExportError("receipt_bundle_hash_mismatch")
    for field in ("source_id", "provider", "format", "signal_family", "artifact_content_hash"):
        if bundle.get(field) != receipt.get(field):
            raise P135ExportError(f"receipt_bundle_{field}_mismatch")
    if bundle.get("artifact_bytes") != receipt.get("bytes_read") or bundle.get("record_count") != receipt.get("records_normalized"):
        raise P135ExportError("receipt_bundle_count_mismatch")
    for record in _sequence(bundle.get("records"), "records"):
        if _mapping(record, "record").get("execution_receipt_ref") != receipt.get("receipt_id"):
            raise P135ExportError("receipt_bundle_record_ref_mismatch")


def _validate_p135_record(
    record: Mapping[str, Any],
    ordinal: int,
    *,
    source_id: str,
    provider: str,
    format_name: str,
    artifact_hash: str,
) -> None:
    value = _mapping(record, "record")
    _expect_exact_fields(
        value,
        frozenset(
            {
                "schema_version",
                "evidence_id",
                "ordinal",
                "provider",
                "format",
                "p120_record",
                "content_hash",
                "redacted_preview",
                "risk_flags",
                "source_record_hash",
                "execution_receipt_ref",
                "record_hash",
            }
        ),
        "record",
    )
    if value.get("schema_version") != RECORD_SCHEMA_VERSION:
        raise P135ExportError("invalid_record_schema")
    if value.get("ordinal") != ordinal:
        raise P135ExportError("record_ordinal_mismatch")
    if value.get("provider") != provider:
        raise P135ExportError("record_provider_mismatch")
    if value.get("format") != format_name:
        raise P135ExportError("record_format_mismatch")
    validate_normalized_record(_mapping(value.get("p120_record"), "p120_record"))
    p120_record = _mapping(value.get("p120_record"), "p120_record")
    if p120_record.get("source_id") != source_id:
        raise P135ExportError("record_source_id_mismatch")
    expected_source_schema = (
        "p135_failure"
        if p120_record.get("evidence_state") == "fail_closed"
        else {
            "grafana": "topology",
            "loki": "log_event",
            "opentelemetry": "opentelemetry",
            "prometheus": "prometheus",
            "sentry": "sentry",
        }.get(str(value.get("provider")))
    )
    if expected_source_schema is None or p120_record.get("source_schema") != expected_source_schema:
        raise P135ExportError("record_source_schema_mismatch")
    raw_ref = _mapping(p120_record.get("raw_ref"), "raw_ref")
    if raw_ref.get("source_hash") != p120_record.get("source_hash"):
        raise P135ExportError("p120_raw_ref_source_hash_mismatch")
    if raw_ref.get("record_id") != p120_record.get("telemetry_record_id"):
        raise P135ExportError("p120_raw_ref_record_id_mismatch")
    source_record_hash = stable_hash(raw_ref)
    if value.get("source_record_hash") != source_record_hash:
        raise P135ExportError("record_source_hash_mismatch")
    expected_evidence_id = stable_hash(
        {"source": source_id, "ordinal": ordinal, "source_hash": source_record_hash}
    )
    if value.get("evidence_id") != expected_evidence_id:
        raise P135ExportError("record_evidence_id_mismatch")
    expected_content_hash = stable_hash({"artifact": artifact_hash, "record": source_record_hash})
    if value.get("content_hash") != expected_content_hash:
        raise P135ExportError("record_content_hash_mismatch")
    _hash(value.get("execution_receipt_ref"), "execution_receipt_ref")
    _validate_self_hash(value, "record_hash", "record_hash_invalid")


def _receipt_index(contract: Mapping[str, Any], receipts: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for receipt in receipts:
        validate_decision_receipt(receipt)
        if receipt.get("contract_hash") != contract.get("contract_hash"):
            raise P135ExportError("authority_contract_mismatch")
        if receipt.get("decision") != "allowed":
            raise P135ExportError("authority_decision_not_allowed")
        result[str(receipt["receipt_hash"])] = receipt
    return result


def _matching_receipt(
    receipts: Mapping[str, Mapping[str, Any]],
    source_ref_hash: Any,
    expected_bytes: int,
    expected_records: int,
) -> Mapping[str, Any]:
    matches: list[Mapping[str, Any]] = []
    for receipt in receipts.values():
        proposal = _mapping(receipt.get("proposal"), "proposal")
        if proposal.get("source_ref_hash") != source_ref_hash:
            continue
        if proposal.get("requested_level") != "OA1_LOCAL_ARTIFACT" or proposal.get("method") != "LOCAL_READ_FILE":
            raise P135ExportError("authority_method_mismatch")
        if _bounded_int(proposal.get("estimated_response_bytes"), "estimated_response_bytes", 0, 67_108_864) < expected_bytes:
            raise P135ExportError("authority_byte_estimate_exceeded")
        if _bounded_int(proposal.get("estimated_records"), "estimated_records", 0, 10_000_000) < expected_records:
            raise P135ExportError("authority_record_estimate_exceeded")
        matches.append(receipt)
    if not matches:
        raise P135ExportError("missing_authority_receipt")
    if len(matches) != 1:
        raise P135ExportError("ambiguous_authority_receipt")
    return matches[0]


def _bind_authority(artifact: Mapping[str, Any], receipt: Mapping[str, Any]) -> None:
    proposal = _mapping(receipt.get("proposal"), "proposal")
    if receipt.get("decision") != "allowed":
        raise P135ExportError("authority_decision_not_allowed")
    if proposal.get("requested_level") != "OA1_LOCAL_ARTIFACT" or proposal.get("method") != "LOCAL_READ_FILE":
        raise P135ExportError("authority_method_mismatch")
    if proposal.get("capability") != artifact.get("authority_capability"):
        raise P135ExportError("authority_capability_mismatch")
    if _bounded_int(proposal.get("estimated_response_bytes"), "estimated_response_bytes", 0, 67_108_864) < _bounded_int(artifact.get("expected_bytes"), "expected_bytes", 1, 4_194_304):
        raise P135ExportError("authority_byte_estimate_exceeded")
    if _bounded_int(proposal.get("estimated_records"), "estimated_records", 0, 10_000_000) < _bounded_int(artifact.get("expected_records"), "expected_records", 1, 25_000):
        raise P135ExportError("authority_record_estimate_exceeded")


def _prior_success_for_source(ledger: Mapping[str, Any], source_id: str) -> Mapping[str, Any] | None:
    matches = [receipt for receipt in ledger["receipts"] if receipt.get("source_id") == source_id]
    if len(matches) > 1:
        raise P135ExportError("duplicate_ledger_source_id")
    return matches[0] if matches else None


def _duplicate_bundle_stub(artifact: Mapping[str, Any], receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "source_id": artifact["source_id"],
        "provider": artifact["provider"],
        "format": artifact["format"],
        "signal_family": artifact["signal_family"],
        "artifact_content_hash": receipt["artifact_content_hash"],
        "artifact_bytes": receipt["bytes_read"],
        "record_count": receipt["records_normalized"],
        "records": [],
        "bundle_hash": stable_hash({"duplicate": receipt["receipt_hash"]}),
    }


def _artifact_by_source(manifest: Mapping[str, Any], source_id: str) -> Mapping[str, Any]:
    for artifact in manifest["artifacts"]:
        if artifact["source_id"] == source_id:
            return artifact
    raise P135ExportError("unknown_source_id")


def _adapter_version(artifact: Mapping[str, Any]) -> str:
    return _PROFILES[(artifact["provider"], artifact["format"])][2]


def _limits(value: Any) -> dict[str, int]:
    raw = _mapping(value, "limits")
    _expect_exact_fields(raw, frozenset(_LIMIT_BOUNDS), "limit")
    return {key: _bounded_int(raw[key], f"limit:{key}", minimum, maximum) for key, (minimum, maximum) in _LIMIT_BOUNDS.items()}


def _relative_path(value: Any) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise P135ExportError("unsafe_relative_path")
    if value.startswith("/") or "://" in value or _UNSAFE_PATH_RE.search(value):
        raise P135ExportError("unsafe_relative_path")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise P135ExportError("unsafe_relative_path")
    if any(_CREDENTIAL_RE.search(part) for part in parts[:-1]):
        raise P135ExportError("credential_shaped_path")
    return value


def _check_structure(value: Any, limits: Mapping[str, int]) -> None:
    node_count = 0

    def walk(item: Any, depth: int) -> None:
        nonlocal node_count
        node_count += 1
        if node_count > limits["max_json_nodes"]:
            raise P135ExportError("json_node_budget_exceeded")
        if depth > limits["max_json_depth"]:
            raise P135ExportError("json_depth_budget_exceeded")
        if isinstance(item, str):
            if len(item.encode("utf-8")) > limits["max_string_bytes"]:
                raise P135ExportError("json_string_budget_exceeded")
        elif isinstance(item, float):
            if not math.isfinite(item):
                raise P135ExportError("non_finite_number")
        elif isinstance(item, list):
            for child in item:
                walk(child, depth + 1)
        elif isinstance(item, dict):
            for child in item.values():
                walk(child, depth + 1)

    walk(value, 1)


def _redacted_labels(labels: Mapping[str, Any], limits: Mapping[str, int]) -> dict[str, str]:
    if len(labels) > limits["max_attributes_per_record"]:
        raise P135ExportError("attribute_budget_exceeded")
    return {str(key): _safe_label_value(value) for key, value in sorted(labels.items()) if str(key) != "__name__"}


def _attributes(value: Any, limits: Mapping[str, int]) -> dict[str, str]:
    items = _sequence(value, "attributes")
    if len(items) > limits["max_attributes_per_record"]:
        raise P135ExportError("attribute_budget_exceeded")
    result: dict[str, str] = {}
    for item in items:
        attr = _mapping(item, "attribute")
        key = _text(attr.get("key"), "attribute_key")
        if key in result:
            raise P135ExportError("duplicate_otlp_attribute")
        result[key] = _safe_label_value(_mapping(attr.get("value"), "attribute_value"))
    return result


def _safe_label_value(value: Any) -> str:
    text = json.dumps(value, sort_keys=True) if isinstance(value, Mapping) else str(value)
    if _CREDENTIAL_RE.search(text) or _PROMPT_RE.search(text) or _CONTROL_RE.search(text) or len(text.encode("utf-8")) > 96:
        return stable_hash({"redacted": text})
    return text[:96]


def _preview_and_flags(text: str, max_bytes: int) -> tuple[str, list[str]]:
    flags: list[str] = []
    if _PROMPT_RE.search(text):
        flags.append("prompt_like_text")
    if _CREDENTIAL_RE.search(text):
        flags.append("credential_like_text")
    if _CONTROL_RE.search(text):
        flags.append("control_character_text")
    if flags:
        return "", sorted(flags)
    encoded = text.encode("utf-8")[:max_bytes]
    return encoded.decode("utf-8", errors="ignore"), flags


def _safe_signal(value: Any) -> str:
    text = str(value)
    if _CREDENTIAL_RE.search(text) or _PROMPT_RE.search(text):
        return stable_hash({"signal": text})
    return text[:128] or "unknown"


def _provider_mapping(value: Any, provider: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise P135ExportError(f"invalid_{provider}_payload")
    return value


def _validate_activity(value: Any) -> None:
    counters = _mapping(value, "activity")
    _expect_exact_fields(counters, frozenset(_ACTIVITY_KEYS), "activity")
    for key in _ACTIVITY_KEYS:
        _bounded_int(counters[key], key, 0, 10**15)


def _validate_forbidden_authority(value: Any) -> None:
    counters = _mapping(value, "authority_counters")
    expected = frozenset(zero_forbidden_authority())
    _expect_exact_fields(counters, expected, "authority_counter")
    for key in expected:
        item = counters[key]
        if type(item) is not int or item != 0:
            raise P135ExportError(f"{key}_nonzero")
    validate_exact_zero_authority({key: counters[key] for key in zero_authority_counters()})


def _identity(value: os.stat_result) -> dict[str, int]:
    return {
        "device": int(value.st_dev),
        "inode": int(value.st_ino),
        "mode": int(value.st_mode),
        "size": int(value.st_size),
        "mtime_ns": int(value.st_mtime_ns),
        "ctime_ns": int(value.st_ctime_ns),
    }


def _previous_receipt_hash(ledger: Mapping[str, Any]) -> str:
    receipts = list(ledger["receipts"])
    return receipts[-1]["receipt_hash"] if receipts else _ledger_genesis_hash(ledger)


def _ledger_genesis_hash(ledger: Mapping[str, Any]) -> str:
    return stable_hash({"schema_version": "p135.execution_ledger_genesis.v1", "manifest_hash": ledger["manifest_hash"], "contract_hash": ledger["contract_hash"]})


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise P135ExportError(f"invalid_{label}")
    return value


def _sequence(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise P135ExportError(f"invalid_{label}")
    return list(value)


def _expect_exact_fields(value: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    actual = {str(key) for key in value}
    extra = sorted(actual - expected)
    if extra:
        raise P135ExportError(f"unexpected_{label}_field:{extra[0]}")
    missing = sorted(expected - actual)
    if missing:
        raise P135ExportError(f"missing_{label}_field:{missing[0]}")


def _validate_self_hash(value: Mapping[str, Any], field: str, reason: str) -> None:
    if value.get(field) != stable_hash({key: item for key, item in value.items() if key != field}):
        raise P135ExportError(reason)


def _label(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _LABEL_RE.fullmatch(value):
        raise P135ExportError(f"invalid_{label}")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or value == "":
        raise P135ExportError(f"invalid_{label}")
    return value


def _bounded_text(value: Any, label: str, max_bytes: int) -> str:
    text = _text(value, label)
    if len(text.encode("utf-8")) > max_bytes:
        raise P135ExportError(f"{label}_budget_exceeded")
    return text


def _hash(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _HASH_RE.fullmatch(value):
        raise P135ExportError(f"invalid_{label}")
    return value


def _bounded_int(value: Any, label: str, minimum: int, maximum: int) -> int:
    if type(value) is not int:
        raise P135ExportError(f"invalid_{label}")
    if value < minimum or value > maximum:
        raise P135ExportError(f"invalid_{label}")
    return value


def _bounded_count(value: int, label: str, minimum: int, maximum: int) -> int:
    if value < minimum or value > maximum:
        raise P135ExportError(f"invalid_{label}")
    return value


def _number(value: Any, label: str) -> int | float:
    if isinstance(value, str):
        try:
            result = float(value) if "." in value else int(value)
        except ValueError as exc:
            raise P135ExportError(f"invalid_{label}") from exc
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        result = value
    else:
        raise P135ExportError(f"invalid_{label}")
    if isinstance(result, float) and not math.isfinite(result):
        raise P135ExportError(f"invalid_{label}")
    return result


def _timestamp(value: Any, label: str) -> str:
    _parse_timestamp(value, label)
    return str(value)


def _parse_timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not _UTC_RE.fullmatch(value):
        raise P135ExportError(f"invalid_{label}")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise P135ExportError(f"invalid_{label}") from exc


def _from_unix_seconds(value: int | float) -> str:
    return datetime.fromtimestamp(float(value), tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _from_unix_nanos(value: str) -> str:
    return datetime.fromtimestamp(int(value) / 1_000_000_000, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


__all__ = [
    "AttachmentResult",
    "P135ExportError",
    "attach_export",
    "build_export_manifest",
    "new_execution_ledger",
    "validate_denominator_failure_bundle",
    "validate_execution_ledger",
    "validate_export_manifest",
    "validate_normalized_bundle",
    "zero_forbidden_authority",
    "zero_observation_activity",
]
