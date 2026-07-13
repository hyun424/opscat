"""Crash-safe incremental local export observation for P136.

The module is intentionally local-only. It accepts explicit authority and path
inputs, delegates provider parsing to P135, and exposes no network, credential,
environment, subprocess, delivery, remediation, or mutation surface.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import re
import stat
import time
from collections.abc import Mapping, Sequence
from contextlib import nullcontext
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p134_observation_authority import (
    validate_contract,
    validate_decision_receipt,
    validate_receipt_ledger,
    validate_review_receipt,
)
from app.services.p135_provider_export_attachment import (
    BUNDLE_SCHEMA_VERSION,
    FAILURE_BUNDLE_SCHEMA_VERSION,
    P135ExportError,
    attach_export,
    build_export_manifest,
    new_execution_ledger,
    validate_denominator_failure_bundle,
    validate_execution_ledger,
    validate_export_manifest,
    validate_normalized_bundle,
)

CONFIG_SCHEMA_VERSION = "p136.incremental_observer_config.v1"
ENTRY_SCHEMA_VERSION = "p136.incremental_index_entry.v1"
CHECKPOINT_SCHEMA_VERSION = "p136.observation_checkpoint.v1"
INDEX_INTENT_SCHEMA_VERSION = "p136.index_read_intent.v1"
PROMOTION_INTENT_SCHEMA_VERSION = "p136.promotion_intent.v1"
PROMOTION_SCHEMA_VERSION = "p136.promotion_record.v1"
TERMINATION_SCHEMA_VERSION = "p136.termination_receipt.v1"

FORBIDDEN_AUTHORITY_KEYS = (
    "provider_call_count",
    "live_connector_call_count",
    "network_call_count",
    "dns_lookup_count",
    "socket_call_count",
    "credential_read_count",
    "environment_read_count",
    "subprocess_launch_count",
    "shell_execution_count",
    "signal_count",
    "delivery_count",
    "remediation_count",
    "staging_mutation_count",
    "production_mutation_count",
    "operator_replacement_count",
)
RUNTIME_ACTIVITY_KEYS = (
    "index_stat_count",
    "index_file_open_count",
    "index_file_read_count",
    "index_bytes_read",
    "index_complete_lines_evaluated",
    "index_partial_bytes_observed",
    "index_read_intent_write_count",
    "segment_stat_count",
    "segment_file_open_count",
    "segment_file_read_count",
    "segment_bytes_read",
    "segment_records_parsed",
    "promotion_intent_write_count",
    "promotion_record_write_count",
    "checkpoint_write_count",
    "directory_fsync_count",
    "duplicate_resolution_count",
    "recovery_replay_count",
    "rotation_count",
    "rejection_record_count",
)
EVALUATOR_ACTIVITY_KEYS = (
    "runner_invocation_count",
    "profile_read_count",
    "artifact_write_count",
    "child_process_count",
    "signal_delivery_count",
)
RESOURCE_USAGE_KEYS = (
    "wall_time_ms",
    "cpu_time_ms",
    "child_cpu_time_ms",
    "peak_memory_bytes",
    "wall_limit_ms",
    "cpu_limit_ms",
    "peak_memory_limit_bytes",
)

_CONFIG_INPUT_FIELDS = frozenset(
    {
        "observer_id",
        "config_version",
        "created_at",
        "base_dir",
        "data_root",
        "state_root",
        "index_path",
        "checkpoint_path",
        "index_intent_dir",
        "journal_dir",
        "promotion_dir",
        "lease_path",
        "p134_contract_hash",
        "p134_receipt_ledger_hash",
        "index_source_ref_hash",
        "index_read_receipt_hashes",
        "limits",
        "forbidden_authority",
    }
)
_CONFIG_FIELDS = frozenset({"schema_version", *_CONFIG_INPUT_FIELDS, "config_hash"})
_ENTRY_INPUT_FIELDS = frozenset(
    {
        "entry_id",
        "entry_sequence",
        "segment_id",
        "source_id",
        "provider",
        "format",
        "signal_family",
        "relative_segment_path",
        "expected_content_hash",
        "expected_bytes",
        "expected_records",
        "segment_authority_receipt_hash",
        "segment_authority_capability",
        "created_at",
        "previous_entry_hash",
        "rotation_from_hash",
    }
)
_ENTRY_FIELDS = frozenset({"schema_version", *_ENTRY_INPUT_FIELDS, "entry_hash"})
_CHECKPOINT_FIELDS = frozenset(
    {
        "schema_version",
        "config_hash",
        "index_identity_hash",
        "committed_cursor",
        "consumed_prefix_hash",
        "observed_index_size",
        "pending_partial",
        "next_entry_sequence",
        "next_promotion_sequence",
        "last_entry_hash",
        "last_promotion_hash",
        "reserved_index_read_receipt_hashes",
        "consumed_index_read_receipt_hashes",
        "canonical_entry_identities",
        "promotion_keys",
        "counters",
        "forbidden_authority",
        "updated_at",
        "checkpoint_hash",
    }
)
_PROMOTION_FIELDS = frozenset(
    {
        "schema_version",
        "promotion_sequence",
        "entry_hash",
        "status",
        "p135_manifest_hash",
        "p135_artifact_spec_hash",
        "p134_segment_receipt_hash",
        "p135_execution_receipt_hash",
        "p135_receipt_ledger_hash",
        "p135_normalized_bundle_hash",
        "promotion_key",
        "p135_manifest",
        "p135_artifact_spec",
        "p134_segment_receipt",
        "p135_execution_receipt",
        "p135_receipt_ledger",
        "p135_normalized_bundle",
        "activity",
        "forbidden_authority",
        "promotion_hash",
    }
)
_PROMOTION_INTENT_FIELDS = frozenset(
    {
        "schema_version",
        "config_hash",
        "checkpoint_hash",
        "index_read_intent_hash",
        "cycle_id",
        "index_read_receipt_hash",
        "post_cycle_checkpoint_hash",
        "post_cycle_checkpoint",
        "promotion_count",
        "promotion_hashes",
        "promotion_records",
        "fsync",
        "intent_hash",
    }
)
_LIMIT_FIELDS = frozenset(
    {
        "poll_interval_ms",
        "max_cycles",
        "max_receipt_pool_size",
        "max_whole_index_bytes",
        "max_complete_lines_per_cycle",
        "max_index_line_bytes",
        "max_json_depth",
        "max_json_nodes",
        "max_json_string_bytes",
        "max_pending_entries",
        "max_promotions_per_cycle",
        "max_journal_bytes",
        "max_promotion_bytes",
        "max_consecutive_failures",
        "max_clock_rollback_ms",
        "max_retained_entry_identities",
    }
)
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_LABEL_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_PROMPT_OR_SECRET_RE = re.compile(
    r"(?:ignore[-_ ]previous|api[_-]?key|authorization|bearer|credential|password|secret|run[-_ ]command)",
    re.IGNORECASE,
)


class P136ObservationError(ValueError):
    """Raised when incremental observation cannot proceed safely."""


class P136DurabilityUncertainError(P136ObservationError):
    """Raised after replace when parent-directory durability is uncertain."""


def zero_forbidden_authority() -> dict[str, int]:
    return {key: 0 for key in FORBIDDEN_AUTHORITY_KEYS}


def zero_runtime_activity() -> dict[str, int]:
    return {key: 0 for key in RUNTIME_ACTIVITY_KEYS}


def build_incremental_observer_config(data: Mapping[str, Any]) -> dict[str, Any]:
    raw = _mapping(data, "config")
    unknown = set(raw) - _CONFIG_INPUT_FIELDS
    missing = _CONFIG_INPUT_FIELDS - set(raw)
    if unknown:
        raise P136ObservationError("unexpected_config_field")
    if missing:
        raise P136ObservationError("missing_config_field")
    limits = _validate_limits(raw.get("limits"))
    paths = {
        name: _relative_path(raw.get(name), name)
        for name in (
            "index_path",
            "checkpoint_path",
            "index_intent_dir",
            "journal_dir",
            "promotion_dir",
            "lease_path",
        )
    }
    _validate_path_topology(paths)
    receipts_raw = raw.get("index_read_receipt_hashes")
    if not _is_sequence(receipts_raw) or not receipts_raw:
        raise P136ObservationError("invalid_index_read_receipt_hashes")
    receipts = [_hash(item, "index_read_receipt_hash") for item in receipts_raw]
    if len(receipts) != len(set(receipts)):
        raise P136ObservationError("duplicate_index_read_receipt")
    if len(receipts) > limits["max_receipt_pool_size"]:
        raise P136ObservationError("index_read_receipt_pool_exceeded")
    config: dict[str, Any] = {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "observer_id": _label(raw.get("observer_id"), "observer_id"),
        "config_version": _positive_int(raw.get("config_version"), "config_version"),
        "created_at": _timestamp(raw.get("created_at"), "created_at"),
        "base_dir": _path_ref(raw.get("base_dir"), "base_dir"),
        "data_root": _path_ref(raw.get("data_root"), "data_root"),
        "state_root": _path_ref(raw.get("state_root"), "state_root"),
        **paths,
        "p134_contract_hash": _hash(raw.get("p134_contract_hash"), "p134_contract_hash"),
        "p134_receipt_ledger_hash": _hash(raw.get("p134_receipt_ledger_hash"), "p134_receipt_ledger_hash"),
        "index_source_ref_hash": _hash(raw.get("index_source_ref_hash"), "index_source_ref_hash"),
        "index_read_receipt_hashes": receipts,
        "limits": limits,
        "forbidden_authority": _exact_counters(
            raw.get("forbidden_authority"),
            FORBIDDEN_AUTHORITY_KEYS,
            "invalid_forbidden_authority_schema",
            require_zero=True,
        ),
    }
    config["config_hash"] = stable_hash(config)
    return config


def validate_incremental_observer_config(config: Mapping[str, Any]) -> None:
    value = _mapping(config, "config")
    if set(value) != _CONFIG_FIELDS or value.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise P136ObservationError("invalid_config_fields")
    expected_hash = value.get("config_hash")
    if expected_hash != stable_hash({key: item for key, item in value.items() if key != "config_hash"}):
        raise P136ObservationError("config_hash_invalid")
    rebuilt = build_incremental_observer_config({key: deepcopy(value[key]) for key in _CONFIG_INPUT_FIELDS})
    if dict(value) != rebuilt:
        raise P136ObservationError("config_semantics_invalid")


def build_incremental_index_entry(data: Mapping[str, Any]) -> dict[str, Any]:
    raw = _mapping(data, "entry")
    if set(raw) - _ENTRY_INPUT_FIELDS:
        raise P136ObservationError("unexpected_entry_field")
    if _ENTRY_INPUT_FIELDS - set(raw):
        raise P136ObservationError("missing_entry_field")
    entry: dict[str, Any] = {
        "schema_version": ENTRY_SCHEMA_VERSION,
        **{key: deepcopy(raw[key]) for key in _ENTRY_INPUT_FIELDS},
    }
    entry["entry_hash"] = stable_hash(entry)
    return entry


def validate_incremental_index_entry(
    entry: Mapping[str, Any],
    *,
    expected_sequence: int | None = None,
    previous_entry_hash: str | None = None,
    expected_rotation_from_hash: str | None = None,
    known_canonical_identities: Mapping[str, Mapping[str, Any]] | None = None,
) -> None:
    value = _mapping(entry, "entry")
    if set(value) != _ENTRY_FIELDS or value.get("schema_version") != ENTRY_SCHEMA_VERSION:
        raise P136ObservationError("invalid_entry_fields")
    if value.get("entry_hash") != stable_hash({key: item for key, item in value.items() if key != "entry_hash"}):
        raise P136ObservationError("entry_hash_invalid")
    for field in ("entry_id", "segment_id", "source_id"):
        text = _label(value.get(field), field)
        if _PROMPT_OR_SECRET_RE.search(text):
            raise P136ObservationError("prompt_or_credential_text_forbidden")
    for field in ("provider", "format", "signal_family", "segment_authority_capability"):
        text = _text(value.get(field), field)
        if _PROMPT_OR_SECRET_RE.search(text):
            raise P136ObservationError("prompt_or_credential_text_forbidden")
    path = _relative_path(value.get("relative_segment_path"), "relative_segment_path")
    if _PROMPT_OR_SECRET_RE.search(path):
        raise P136ObservationError("prompt_or_credential_text_forbidden")
    sequence = _positive_int(value.get("entry_sequence"), "entry_sequence")
    _positive_int(value.get("expected_bytes"), "expected_bytes")
    _positive_int(value.get("expected_records"), "expected_records")
    _hash(value.get("expected_content_hash"), "expected_content_hash")
    _hash(value.get("segment_authority_receipt_hash"), "segment_authority_receipt_hash")
    _timestamp(value.get("created_at"), "created_at")
    previous = value.get("previous_entry_hash")
    if sequence == 1:
        if previous is not None:
            raise P136ObservationError("genesis_previous_entry_hash_not_null")
    else:
        _hash(previous, "previous_entry_hash")
    rotation = value.get("rotation_from_hash")
    if rotation is not None:
        _hash(rotation, "rotation_from_hash")
    if expected_sequence is not None and sequence != expected_sequence:
        raise P136ObservationError("entry_sequence_mismatch")
    if previous_entry_hash is not None and previous != previous_entry_hash:
        raise P136ObservationError("previous_entry_hash_mismatch")
    if expected_rotation_from_hash is not None and rotation != expected_rotation_from_hash:
        raise P136ObservationError("rotation_lineage_mismatch")
    if known_canonical_identities is not None:
        for identity_field, reason in (
            ("entry_id", "conflicting_entry_id_reuse"),
            ("segment_id", "conflicting_segment_id_reuse"),
        ):
            prior = known_canonical_identities.get(str(value[identity_field]))
            if prior is not None and dict(prior) != dict(value):
                raise P136ObservationError(reason)


def validate_observer_runtime_authority(
    config: Mapping[str, Any],
    authority: Mapping[str, Any],
    *,
    now: str,
    proposed_whole_index_bytes: int | None = None,
    proposed_complete_lines: int | None = None,
) -> dict[str, Any]:
    cfg = _ensure_config(config)
    auth = _mapping(authority, "authority")
    required = {
        "contract",
        "review_receipt",
        "receipt_ledger",
        "index_receipts",
        "contract_bytes",
        "review_receipt_bytes",
        "receipt_ledger_bytes",
        "index_receipt_bytes",
    }
    if not required <= set(auth):
        raise P136ObservationError("missing_full_p134_runtime_inputs")
    contract = _mapping(auth.get("contract"), "contract")
    review = _mapping(auth.get("review_receipt"), "review_receipt")
    ledger = _mapping(auth.get("receipt_ledger"), "receipt_ledger")
    receipts = [_mapping(item, "index_receipt") for item in _sequence(auth.get("index_receipts"), "index_receipts")]
    validate_contract(contract)
    validate_review_receipt(review, core=_mapping(contract.get("core"), "contract_core"))
    if dict(review) != dict(_mapping(contract.get("review_receipt"), "contract_review")):
        raise P136ObservationError("review_receipt_contract_mismatch")
    validate_receipt_ledger(ledger, contract=contract)
    if contract.get("contract_hash") != cfg["p134_contract_hash"]:
        raise P136ObservationError("p134_contract_hash_mismatch")
    if ledger.get("ledger_hash") != cfg["p134_receipt_ledger_hash"]:
        raise P136ObservationError("p134_receipt_ledger_hash_mismatch")
    if _canonical_bytes(contract) != _bytes(auth.get("contract_bytes"), "contract_bytes"):
        raise P136ObservationError("p134_contract_bytes_mismatch")
    if _canonical_bytes(review) != _bytes(auth.get("review_receipt_bytes"), "review_receipt_bytes"):
        raise P136ObservationError("p134_review_bytes_mismatch")
    if _canonical_bytes(ledger) != _bytes(auth.get("receipt_ledger_bytes"), "receipt_ledger_bytes"):
        raise P136ObservationError("p134_ledger_bytes_mismatch")
    receipt_bytes = _sequence(auth.get("index_receipt_bytes"), "index_receipt_bytes")
    if len(receipts) != len(receipt_bytes):
        raise P136ObservationError("index_receipt_bytes_count_mismatch")
    hashes = [str(receipt.get("receipt_hash")) for receipt in receipts]
    if len(hashes) != len(set(hashes)):
        raise P136ObservationError("duplicate_index_read_receipt")
    if hashes != list(cfg["index_read_receipt_hashes"]):
        raise P136ObservationError("index_read_receipt_order_mismatch")
    ledger_receipts = {str(item.get("receipt_hash")): item for item in _sequence(ledger.get("receipts"), "ledger_receipts") if isinstance(item, Mapping)}
    for receipt, encoded in zip(receipts, receipt_bytes, strict=True):
        validate_decision_receipt(receipt)
        receipt_hash = str(receipt.get("receipt_hash"))
        if receipt_hash not in ledger_receipts or dict(ledger_receipts[receipt_hash]) != dict(receipt):
            raise P136ObservationError("index_receipt_not_in_ledger")
        if _canonical_bytes(receipt) != _bytes(encoded, "index_receipt_bytes"):
            raise P136ObservationError("index_receipt_bytes_mismatch")
        proposal = _mapping(receipt.get("proposal"), "proposal")
        if receipt.get("decision") != "allowed":
            raise P136ObservationError("index_receipt_not_allowed")
        if (
            proposal.get("requested_level") != "OA1_LOCAL_ARTIFACT"
            or proposal.get("method") != "LOCAL_READ_FILE"
            or proposal.get("capability") != "telemetry.events.read"
            or proposal.get("source_ref_hash") != cfg["index_source_ref_hash"]
            or proposal.get("attempt_number") != 1
        ):
            raise P136ObservationError("index_receipt_proposal_mismatch")
        if int(proposal.get("estimated_response_bytes", -1)) < cfg["limits"]["max_whole_index_bytes"]:
            raise P136ObservationError("whole_index_budget_underestimated")
        if int(proposal.get("estimated_records", -1)) < cfg["limits"]["max_complete_lines_per_cycle"]:
            raise P136ObservationError("whole_index_budget_underestimated")
    current = _parse_timestamp(now, "now")
    core = _mapping(contract.get("core"), "contract_core")
    if not (_parse_timestamp(core.get("valid_from"), "valid_from") <= current < _parse_timestamp(core.get("expires_at"), "expires_at")):
        raise P136ObservationError("contract_or_review_not_current")
    if not (_parse_timestamp(review.get("reviewed_at"), "reviewed_at") <= current < _parse_timestamp(review.get("expires_at"), "review_expires_at")):
        raise P136ObservationError("contract_or_review_not_current")
    if proposed_whole_index_bytes is not None and (
        proposed_whole_index_bytes > cfg["limits"]["max_whole_index_bytes"]
        or any(int(_mapping(receipt["proposal"], "proposal")["estimated_response_bytes"]) < proposed_whole_index_bytes for receipt in receipts)
    ):
        raise P136ObservationError("whole_index_budget_underestimated")
    if proposed_complete_lines is not None and (
        proposed_complete_lines > cfg["limits"]["max_complete_lines_per_cycle"]
        or any(int(_mapping(receipt["proposal"], "proposal")["estimated_records"]) < proposed_complete_lines for receipt in receipts)
    ):
        raise P136ObservationError("whole_index_budget_underestimated")
    return {"config": cfg, "contract": dict(contract), "ledger": dict(ledger), "receipts": [dict(item) for item in receipts]}


def observe_one_cycle(runtime: Mapping[str, Any]) -> dict[str, Any]:
    value = _mapping(runtime, "runtime")
    probe = value.get("probe")
    if value.get("lease_competitor") is True:
        raise P136ObservationError("exclusive_lease_unavailable")
    cfg = _ensure_config(_mapping(value.get("config"), "config"))
    checkpoint = _checkpoint_for_config(_mapping(value.get("checkpoint"), "checkpoint"), cfg)
    runtime_now = _timestamp(value.get("now"), "now")
    checkpoint_updated_at = _validated_checkpoint_time(
        checkpoint,
        cfg,
        runtime_now,
    )

    base_path_value = value.get("base_path")
    lease_context: Any = nullcontext()
    if base_path_value is not None:
        base_path = Path(base_path_value)
        lease_context = _ObserverLease(base_path, cfg["lease_path"])
    with lease_context:
        authority_result = validate_observer_runtime_authority(
            cfg,
            _mapping(value.get("authority"), "authority"),
            now=runtime_now,
        )
        receipts = authority_result["receipts"]
        consumed_receipts = set(_sequence(checkpoint.get("consumed_index_read_receipt_hashes", []), "consumed_index_read_receipt_hashes"))
        receipt = next((item for item in receipts if item["receipt_hash"] not in consumed_receipts), None)
        if receipt is None:
            raise P136ObservationError("index_read_receipt_pool_exhausted")
        recovery_intent = value.get("recovery_intent")
        if recovery_intent is None and base_path_value is not None:
            recovery_intent = _discover_index_read_intent(Path(base_path_value), cfg, checkpoint, receipts)
        receipt_hash = str(receipt["receipt_hash"])
        if recovery_intent is not None:
            recovery_hash = str(_mapping(recovery_intent, "recovery_intent").get("receipt_hash", ""))
            matching_receipt = next((item for item in receipts if item["receipt_hash"] == recovery_hash), receipt)
            recovery = _validate_index_intent(_mapping(recovery_intent, "recovery_intent"), cfg, checkpoint, matching_receipt)
            if recovery.get("checkpoint_hash") != checkpoint.get("checkpoint_hash"):
                raise P136ObservationError("index_read_intent_checkpoint_mismatch")
            receipt = matching_receipt
            receipt_hash = str(receipt["receipt_hash"])
        elif receipt_hash in checkpoint.get("reserved_index_read_receipt_hashes", []):
            raise P136ObservationError("index_read_receipt_reuse_without_matching_intent")

        cycle_id = stable_hash(
            {
                "schema_version": "p136.deterministic_cycle_id.v1",
                "config_hash": cfg["config_hash"],
                "checkpoint_hash": checkpoint["checkpoint_hash"],
                "receipt_hash": receipt_hash,
            }
        )
        intent: dict[str, Any] = {
            "schema_version": INDEX_INTENT_SCHEMA_VERSION,
            "cycle_id": cycle_id,
            "config_hash": cfg["config_hash"],
            "checkpoint_hash": checkpoint["checkpoint_hash"],
            "contract_hash": cfg["p134_contract_hash"],
            "receipt_ledger_hash": cfg["p134_receipt_ledger_hash"],
            "receipt_hash": receipt_hash,
            "receipt_bytes_hash": _content_hash(_canonical_bytes(receipt)),
            "source_ref_hash": cfg["index_source_ref_hash"],
            "method": "LOCAL_READ_FILE",
            "capability": "telemetry.events.read",
            "maximum_whole_index_bytes": cfg["limits"]["max_whole_index_bytes"],
            "maximum_complete_lines": cfg["limits"]["max_complete_lines_per_cycle"],
            "cycle_started_at": str(value.get("now")),
            "fsync": {"file": True, "parent_directory": True},
        }
        intent["intent_hash"] = stable_hash(intent)

        if base_path_value is not None:
            base_path = Path(base_path_value)
            intent_path = f"{cfg['index_intent_dir']}/{cycle_id.removeprefix('sha256:')}.json"
            _atomic_write_json(base_path, intent_path, intent)
        _record_probe(probe, "write_index_read_intent")
        _inject_evaluator_crash(value, "index_intent_durable")
        if base_path_value is not None:
            index_bytes, identity = _read_secure_regular_file(
                Path(base_path_value),
                cfg["index_path"],
                cfg["limits"]["max_whole_index_bytes"],
                probe,
            )
        else:
            _record_probe(probe, "index_open")
            _record_probe(probe, "index_read")
            index_bytes = _bytes(value.get("index_bytes", b""), "index_bytes")
            identity = str(checkpoint.get("index_identity_hash"))
        _inject_evaluator_crash(value, "index_read_complete")
        scan = scan_incremental_index(value, index_bytes=index_bytes, file_identity_hash=identity)
        resolution = resolve_index_entries({**value, "checkpoint": checkpoint}, scan["complete_entries"])
        next_checkpoint = _advance_observation_checkpoint(
            checkpoint,
            cfg,
            scan,
            resolution["promotion_records"],
            duplicate_count=len(resolution["duplicate_entries"]),
            receipt_hash=receipt_hash,
            updated_at=checkpoint_updated_at,
        )
        if base_path_value is not None:
            base_path = Path(base_path_value)
            durable_checkpoint = _rehash_checkpoint(next_checkpoint)
            promotion_intent = _promotion_batch_intent(
                cfg,
                checkpoint,
                intent,
                resolution["promotion_records"],
                durable_checkpoint,
            )
            if resolution["promotion_records"]:
                _atomic_write_limited_json(
                    base_path,
                    f"{cfg['journal_dir']}/{cycle_id.removeprefix('sha256:')}.promotion-intent.json",
                    promotion_intent,
                    cfg["limits"]["max_journal_bytes"],
                    "promotion_intent_byte_budget_exceeded",
                )
                _record_probe(probe, "write_promotion_intent")
                _inject_evaluator_crash(value, "promotion_intent_durable")
            for promotion in resolution["promotion_records"]:
                promotion_name = promotion["promotion_hash"].removeprefix("sha256:")
                _atomic_write_limited_json(
                    base_path,
                    f"{cfg['promotion_dir']}/{promotion_name}.json",
                    promotion,
                    cfg["limits"]["max_promotion_bytes"],
                    "promotion_record_byte_budget_exceeded",
                )
            if resolution["promotion_records"]:
                _inject_evaluator_crash(value, "promotion_records_durable")
            next_checkpoint = advance_checkpoint({**value, "checkpoint": checkpoint}, durable_checkpoint)
        else:
            next_checkpoint = _rehash_checkpoint(next_checkpoint)
        activity = _merge_activity(
            zero_runtime_activity(),
            {
                "index_stat_count": 1,
                "index_file_open_count": 1,
                "index_file_read_count": 1,
                "index_bytes_read": len(index_bytes),
                "index_complete_lines_evaluated": len(scan["complete_entries"]),
                "index_partial_bytes_observed": int((scan["checkpoint_patch"].get("pending_partial") or {}).get("pending_byte_length", 0)),
                "index_read_intent_write_count": 1,
                "promotion_intent_write_count": len(resolution["promotion_records"]),
                "promotion_record_write_count": len(resolution["promotion_records"]),
                "checkpoint_write_count": 1,
                "directory_fsync_count": 2 + (2 * len(resolution["promotion_records"])) if base_path_value is not None else 0,
                "duplicate_resolution_count": len(resolution["duplicate_entries"]),
                "rotation_count": int(bool(scan["rotated"])),
            },
            *[promotion["activity"] for promotion in resolution["promotion_records"]],
        )
    return {
        "index_read_intent": intent,
        "scan": scan,
        "checkpoint": checkpoint,
        "promotion_records": resolution["promotion_records"],
        "duplicate_entries": resolution["duplicate_entries"],
        "advanced_checkpoint": next_checkpoint,
        "activity": activity,
    }


def _inject_evaluator_crash(runtime: Mapping[str, Any], phase: str) -> None:
    """Raise only at an explicit evaluator-owned durable boundary.

    The hook is intentionally callable-only so a persisted or serialized runtime
    document cannot enable it accidentally. Production callers omit the hook.
    """

    injector = runtime.get("evaluator_crash_injector")
    if injector is None:
        return
    if not callable(injector):
        raise P136ObservationError("invalid_evaluator_crash_injector")
    injector(phase)


def scan_incremental_index(
    runtime: Mapping[str, Any],
    *,
    index_bytes: bytes,
    file_identity_hash: str | None = None,
) -> dict[str, Any]:
    value = _mapping(runtime, "runtime")
    cfg = _ensure_config(_mapping(value.get("config"), "config"))
    checkpoint = _validated_checkpoint(_mapping(value.get("checkpoint"), "checkpoint"))
    data = _bytes(index_bytes, "index_bytes")
    limits = cfg["limits"]
    if len(data) > limits["max_whole_index_bytes"]:
        raise P136ObservationError("whole_index_byte_budget_exceeded")
    old_identity = checkpoint.get("index_identity_hash")
    identity = file_identity_hash or str(old_identity)
    rotated = identity != old_identity
    pending = checkpoint.get("pending_partial")
    if rotated and pending is not None:
        raise P136ObservationError("rotation_rejected_with_pending_partial")
    if not rotated and pending is not None:
        pending_value = _mapping(pending, "pending_partial")
        pending_length = int(pending_value.get("pending_byte_length", -1))
        candidate = data[:pending_length]
        if _content_hash(candidate) != pending_value.get("pending_byte_hash"):
            raise P136ObservationError("pending_partial_prefix_mismatch")
    cursor = int(checkpoint.get("committed_cursor", 0))
    if not rotated:
        if len(data) < cursor:
            raise P136ObservationError("index_truncation_detected")
        if _content_hash(data[:cursor]) != checkpoint.get("consumed_prefix_hash"):
            raise P136ObservationError("consumed_prefix_mismatch")

    complete_entries: list[dict[str, Any]] = []
    pending_bytes = b""
    committed_cursor = 0 if rotated else cursor
    line_count = 0
    position = 0
    for line in data.splitlines(keepends=True):
        line_start = position
        position += len(line)
        if not line.endswith(b"\n"):
            pending_bytes = line
            committed_cursor = line_start
            break
        if len(line) > limits["max_index_line_bytes"]:
            raise P136ObservationError("index_line_byte_budget_exceeded")
        line_count += 1
        if line_count > limits["max_complete_lines_per_cycle"]:
            raise P136ObservationError("whole_index_complete_line_budget_exceeded")
        decoded = _strict_json(line[:-1], limits=limits)
        if not isinstance(decoded, Mapping):
            raise P136ObservationError("index_entry_not_mapping")
        entry = dict(decoded)
        canonical = _canonical_identity(checkpoint, entry)
        if canonical is not None:
            if dict(canonical) != entry:
                if canonical.get("segment_id") == entry.get("segment_id"):
                    raise P136ObservationError("conflicting_segment_id_reuse")
                raise P136ObservationError("conflicting_entry_id_reuse")
            validate_incremental_index_entry(entry)
        else:
            expected_sequence = int(checkpoint.get("next_entry_sequence", 1)) + sum(1 for prior in complete_entries if _canonical_identity(checkpoint, prior) is None)
            if int(entry.get("entry_sequence", -1)) != expected_sequence:
                if rotated:
                    raise P136ObservationError("rotation_sequence_gap")
                raise P136ObservationError("entry_sequence_mismatch")
            previous_hash = complete_entries[-1]["entry_hash"] if complete_entries and _canonical_identity(checkpoint, complete_entries[-1]) is None else checkpoint.get("last_entry_hash")
            expected_rotation = checkpoint.get("last_entry_hash") if rotated else None
            validate_incremental_index_entry(
                entry,
                expected_sequence=expected_sequence,
                previous_entry_hash=previous_hash,
                expected_rotation_from_hash=expected_rotation,
                known_canonical_identities=_canonical_map(checkpoint),
            )
        complete_entries.append(entry)
        committed_cursor = position
    if data and not data.endswith(b"\n") and not pending_bytes:
        pending_bytes = data[committed_cursor:]
    pending_state: dict[str, Any] | None = None
    if pending_bytes:
        if len(pending_bytes) > limits["max_index_line_bytes"]:
            raise P136ObservationError("index_line_byte_budget_exceeded")
        pending_state = {
            "file_identity_hash": identity,
            "line_start_cursor": committed_cursor,
            "pending_byte_hash": _content_hash(pending_bytes),
            "pending_byte_length": len(pending_bytes),
            "observed_index_size": len(data),
        }
    return {
        "complete_entries": complete_entries,
        "rotated": rotated,
        "checkpoint_patch": {
            "index_identity_hash": identity,
            "committed_cursor": committed_cursor,
            "consumed_prefix_hash": _content_hash(data[:committed_cursor]),
            "observed_index_size": len(data),
            "pending_partial": pending_state,
        },
    }


def resolve_index_entries(runtime: Mapping[str, Any], entries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    value = _mapping(runtime, "runtime")
    cfg = _ensure_config(_mapping(value.get("config"), "config"))
    checkpoint = _validated_checkpoint(_mapping(value.get("checkpoint"), "checkpoint"))
    promotion_keys = _mapping(checkpoint.get("promotion_keys", {}), "promotion_keys")
    if len(entries) > cfg["limits"]["max_pending_entries"]:
        raise P136ObservationError("pending_entry_budget_exceeded")
    duplicate_entries: list[str] = []
    promotions: list[dict[str, Any]] = []
    seen_promotion_entries = set(str(key) for key in promotion_keys)
    next_promotion_sequence = int(checkpoint.get("next_promotion_sequence", 1))
    for raw in entries:
        entry = _mapping(raw, "entry")
        entry_hash = str(entry.get("entry_hash"))
        if entry_hash in seen_promotion_entries:
            duplicate_entries.append(entry_hash)
            continue
        if len(promotions) >= cfg["limits"]["max_promotions_per_cycle"]:
            raise P136ObservationError("promotion_budget_exceeded")
        working_checkpoint = {
            **dict(checkpoint),
            "next_promotion_sequence": next_promotion_sequence,
        }
        promotion = promote_first_seen_entry(
            {**dict(value), "checkpoint": working_checkpoint}, entry
        )["promotion_record"]
        promotions.append(promotion)
        seen_promotion_entries.add(entry_hash)
        next_promotion_sequence += 1
    return {
        "duplicate_entries": duplicate_entries,
        "promotions_written": [item["promotion_hash"] for item in promotions],
        "promotion_records": promotions,
    }


def promote_first_seen_entry(runtime: Mapping[str, Any], entry: Mapping[str, Any]) -> dict[str, Any]:
    value = _mapping(runtime, "runtime")
    cfg = _ensure_config(_mapping(value.get("config"), "config"))
    expected_entry = dict(_mapping(entry, "entry"))
    validate_incremental_index_entry(expected_entry)
    authority = _mapping(value.get("authority"), "authority")
    contract = _mapping(authority.get("contract"), "contract")
    ledger = _mapping(authority.get("receipt_ledger"), "receipt_ledger")
    validate_contract(contract)
    validate_receipt_ledger(ledger, contract=contract)
    segment_receipts = [_mapping(item, "segment_receipt") for item in _sequence(authority.get("segment_receipts"), "segment_receipts")]
    receipt = next(
        (item for item in segment_receipts if item.get("receipt_hash") == expected_entry["segment_authority_receipt_hash"]),
        None,
    )
    if receipt is None:
        raise P136ObservationError("missing_segment_authority_receipt")
    ledger_members = {str(item.get("receipt_hash")): item for item in _sequence(ledger.get("receipts"), "ledger_receipts") if isinstance(item, Mapping)}
    if str(receipt.get("receipt_hash")) not in ledger_members:
        raise P136ObservationError("segment_receipt_not_in_p134_ledger")
    proposal = _mapping(receipt.get("proposal"), "segment_proposal")
    if proposal.get("capability") != expected_entry["segment_authority_capability"]:
        raise P136ObservationError("segment_authority_capability_mismatch")

    manifest_input = {
        "manifest_id": _manifest_id(str(expected_entry["entry_id"])),
        "manifest_version": 1,
        "created_at": str(value.get("now")),
        "root_ref_hash": stable_hash({"root": "p136-explicit-local-export"}),
        "limits": _p135_limits(),
        "artifacts": [
            {
                "source_id": expected_entry["source_id"],
                "provider": expected_entry["provider"],
                "format": expected_entry["format"],
                "signal_family": expected_entry["signal_family"],
                "relative_path": expected_entry["relative_segment_path"],
                "expected_content_hash": expected_entry["expected_content_hash"],
                "expected_bytes": expected_entry["expected_bytes"],
                "expected_records": expected_entry["expected_records"],
                "authority_capability": expected_entry["segment_authority_capability"],
                "authority_source_ref_hash": proposal["source_ref_hash"],
            }
        ],
    }
    manifest = build_export_manifest(manifest_input, contract, [receipt])
    p135_ledger = new_execution_ledger(manifest)
    export_root = Path(value.get("export_root", value.get("base_path", ".")))
    probe = value.get("probe")
    _record_probe(probe, "segment_open")
    _record_probe(probe, "segment_read")
    _record_probe(probe, f"segment_entry_read:{expected_entry['entry_hash']}")
    now = str(value.get("now"))
    result = attach_export(
        export_root,
        manifest,
        str(expected_entry["source_id"]),
        contract,
        [receipt],
        p135_ledger,
        started_at=now,
        completed_at=now,
    )
    artifact = manifest["artifacts"][0]
    activity = zero_runtime_activity()
    activity.update(
        {
            "segment_stat_count": int(result.activity["local_stat_count"]),
            "segment_file_open_count": int(result.activity["local_file_open_count"]),
            "segment_file_read_count": int(result.activity["local_file_read_count"]),
            "segment_bytes_read": int(result.activity["local_bytes_read"]),
            "segment_records_parsed": int(result.activity["local_records_parsed"]),
        }
    )
    promotion_key = _promotion_key(
        cfg=cfg,
        entry=expected_entry,
        contract=contract,
        ledger=ledger,
        receipt=receipt,
        manifest=manifest,
        artifact=artifact,
        execution=result.receipt,
        nested_ledger=result.ledger,
        bundle=result.bundle,
    )
    promotion: dict[str, Any] = {
        "schema_version": PROMOTION_SCHEMA_VERSION,
        "promotion_sequence": int(_mapping(value.get("checkpoint"), "checkpoint").get("next_promotion_sequence", 1)),
        "entry_hash": expected_entry["entry_hash"],
        "status": "success" if result.receipt["status"] == "succeeded" else "denominator_failure",
        "p135_manifest_hash": manifest["manifest_hash"],
        "p135_artifact_spec_hash": artifact["artifact_spec_hash"],
        "p134_segment_receipt_hash": receipt["receipt_hash"],
        "p135_execution_receipt_hash": result.receipt["receipt_hash"],
        "p135_receipt_ledger_hash": result.ledger["ledger_hash"],
        "p135_normalized_bundle_hash": result.bundle["bundle_hash"],
        "promotion_key": promotion_key,
        "p135_manifest": manifest,
        "p135_artifact_spec": artifact,
        "p134_segment_receipt": dict(receipt),
        "p135_execution_receipt": result.receipt,
        "p135_receipt_ledger": result.ledger,
        "p135_normalized_bundle": result.bundle,
        "activity": activity,
        "forbidden_authority": zero_forbidden_authority(),
    }
    promotion["promotion_hash"] = stable_hash(promotion)
    _record_probe(probe, f"promotion_created:{expected_entry['entry_hash']}")
    return {
        "promotion_record": promotion,
        "p135_result": {
            "manifest": manifest,
            "bundle": result.bundle,
            "receipt": result.receipt,
            "ledger": result.ledger,
        },
        "activity": activity,
    }


def validate_promotion_record(
    promotion: Mapping[str, Any],
    *,
    expected_entry: Mapping[str, Any],
    runtime: Mapping[str, Any],
) -> None:
    value = _mapping(promotion, "promotion")
    if set(value) != _PROMOTION_FIELDS or value.get("schema_version") != PROMOTION_SCHEMA_VERSION:
        raise P136ObservationError("invalid_promotion_fields")
    entry = _mapping(expected_entry, "entry")
    validate_incremental_index_entry(entry)
    if value.get("entry_hash") != entry.get("entry_hash"):
        raise P136ObservationError("promotion_entry_hash_mismatch")
    _positive_int(value.get("promotion_sequence"), "promotion_sequence")
    if value.get("status") not in {"success", "denominator_failure"}:
        raise P136ObservationError("invalid_promotion_status")
    if value.get("promotion_hash") != stable_hash({key: item for key, item in value.items() if key != "promotion_hash"}):
        raise P136ObservationError("promotion_hash_invalid")
    manifest = _mapping(value.get("p135_manifest"), "p135_manifest")
    artifact = _mapping(value.get("p135_artifact_spec"), "p135_artifact_spec")
    receipt = _mapping(value.get("p134_segment_receipt"), "p134_segment_receipt")
    execution = _mapping(value.get("p135_execution_receipt"), "p135_execution_receipt")
    nested_ledger = _mapping(value.get("p135_receipt_ledger"), "p135_receipt_ledger")
    bundle = _mapping(value.get("p135_normalized_bundle"), "p135_normalized_bundle")
    runtime_value = _mapping(runtime, "runtime")
    provider_entries = runtime_value.get("provider_entries")
    if isinstance(provider_entries, Mapping):
        canonical_entry = next(
            (item for item in provider_entries.values() if isinstance(item, Mapping) and item.get("entry_hash") == entry.get("entry_hash")),
            None,
        )
        if canonical_entry is not None and dict(canonical_entry) != dict(entry):
            raise P136ObservationError("promotion_provider_entry_mismatch")
    authority = _mapping(runtime_value.get("authority"), "authority")
    contract = _mapping(authority.get("contract"), "contract")
    authority_ledger = _mapping(authority.get("receipt_ledger"), "receipt_ledger")
    validate_contract(contract)
    validate_receipt_ledger(authority_ledger, contract=contract)
    validate_decision_receipt(receipt)
    segment_receipts = [_mapping(item, "segment_receipt") for item in _sequence(authority.get("segment_receipts", []), "segment_receipts")]
    canonical_receipt = next((item for item in segment_receipts if item.get("receipt_hash") == entry["segment_authority_receipt_hash"]), None)
    if canonical_receipt is None or dict(canonical_receipt) != dict(receipt):
        raise P136ObservationError("promotion_segment_receipt_mismatch")
    ledger_members = {str(item.get("receipt_hash")): item for item in _sequence(authority_ledger.get("receipts"), "ledger_receipts") if isinstance(item, Mapping)}
    if dict(ledger_members.get(str(receipt["receipt_hash"]), {})) != dict(receipt):
        raise P136ObservationError("segment_receipt_not_in_p134_ledger")
    proposal = _mapping(receipt.get("proposal"), "segment_proposal")
    if (
        receipt.get("decision") != "allowed"
        or proposal.get("capability") != entry["segment_authority_capability"]
        or proposal.get("method") != "LOCAL_READ_FILE"
        or proposal.get("requested_level") != "OA1_LOCAL_ARTIFACT"
    ):
        raise P136ObservationError("segment_receipt_proposal_mismatch")
    try:
        validate_export_manifest(manifest, contract, [receipt])
    except P135ExportError as exc:
        raise P136ObservationError(str(exc)) from exc
    if value.get("p135_manifest_hash") != manifest.get("manifest_hash"):
        raise P136ObservationError("p135_manifest_tamper")
    manifest_artifacts = _sequence(manifest.get("artifacts"), "manifest_artifacts")
    if len(manifest_artifacts) != 1 or dict(_mapping(manifest_artifacts[0], "manifest_artifact")) != dict(artifact):
        raise P136ObservationError("p135_artifact_spec_tamper")
    if artifact.get("artifact_spec_hash") != value.get("p135_artifact_spec_hash"):
        raise P136ObservationError("p135_artifact_spec_tamper")
    if (
        artifact.get("source_id") != entry["source_id"]
        or artifact.get("provider") != entry["provider"]
        or artifact.get("format") != entry["format"]
        or artifact.get("signal_family") != entry["signal_family"]
        or artifact.get("relative_path") != entry["relative_segment_path"]
        or artifact.get("expected_content_hash") != entry["expected_content_hash"]
        or artifact.get("expected_bytes") != entry["expected_bytes"]
        or artifact.get("expected_records") != entry["expected_records"]
        or artifact.get("authority_receipt_hash") != entry["segment_authority_receipt_hash"]
        or artifact.get("authority_capability") != entry["segment_authority_capability"]
    ):
        raise P136ObservationError("promotion_artifact_entry_mismatch")
    if value.get("p134_segment_receipt_hash") != receipt.get("receipt_hash"):
        raise P136ObservationError("p134_segment_receipt_tamper")
    if execution.get("receipt_hash") != value.get("p135_execution_receipt_hash"):
        raise P136ObservationError("p135_execution_receipt_tamper")
    if value.get("p135_receipt_ledger_hash") != nested_ledger.get("ledger_hash"):
        raise P136ObservationError("p135_independent_ledger_tamper")
    if bundle.get("bundle_hash") != value.get("p135_normalized_bundle_hash"):
        raise P136ObservationError("p135_bundle_tamper")
    if bundle.get("schema_version") == BUNDLE_SCHEMA_VERSION:
        try:
            validate_normalized_bundle(bundle)
            validate_execution_ledger(nested_ledger, manifest, contract, [receipt], bundles=[bundle])
        except P135ExportError as exc:
            raise P136ObservationError(str(exc)) from exc
    elif bundle.get("schema_version") == FAILURE_BUNDLE_SCHEMA_VERSION:
        try:
            validate_denominator_failure_bundle(bundle)
            validate_execution_ledger(nested_ledger, manifest, contract, [receipt])
        except P135ExportError as exc:
            raise P136ObservationError(str(exc)) from exc
    else:
        raise P136ObservationError("invalid_p135_bundle_schema")
    if value.get("promotion_key") != _promotion_key(
        cfg=_ensure_config(_mapping(runtime_value.get("config"), "config")),
        entry=entry,
        contract=contract,
        ledger=authority_ledger,
        receipt=receipt,
        manifest=manifest,
        artifact=artifact,
        execution=execution,
        nested_ledger=nested_ledger,
        bundle=bundle,
    ):
        raise P136ObservationError("promotion_key_invalid")
    _exact_counters(value.get("activity"), RUNTIME_ACTIVITY_KEYS, "invalid_runtime_activity_schema")
    _exact_counters(
        value.get("forbidden_authority"),
        FORBIDDEN_AUTHORITY_KEYS,
        "invalid_forbidden_authority_schema",
        require_zero=True,
    )


def recover_observer_state(runtime: Mapping[str, Any]) -> dict[str, Any]:
    value = _mapping(runtime, "runtime")
    cfg = _ensure_config(_mapping(value.get("config"), "config"))
    base_path_value = value.get("base_path")
    if base_path_value is not None:
        intents = _read_persisted_promotion_intents(Path(base_path_value), cfg)
        promotions = _read_persisted_promotions(Path(base_path_value), cfg)
        checkpoint_value = _read_optional_json(Path(base_path_value), cfg["checkpoint_path"], cfg["limits"]["max_journal_bytes"])
        checkpoints = [] if checkpoint_value is None else [_mapping(checkpoint_value, "checkpoint")]
    else:
        intents = [_mapping(item, "promotion_intent") for item in _sequence(value.get("promotion_intents", []), "promotion_intents")]
        promotions = [_mapping(item, "promotion") for item in _sequence(value.get("promotions", []), "promotions")]
        checkpoints = [_mapping(item, "checkpoint") for item in _sequence(value.get("checkpoints", []), "checkpoints")]
    written: list[str] = []
    verified: list[str] = []
    intent_hashes: set[str] = set()
    batch_intents: list[Mapping[str, Any]] = []
    for intent in intents:
        if intent.get("schema_version") == PROMOTION_SCHEMA_VERSION:
            _validate_recovery_promotion(intent)
            continue
        _validate_promotion_intent(intent, cfg)
        intent_hash = str(intent["intent_hash"])
        if intent_hash in intent_hashes:
            raise P136ObservationError("duplicate_promotion_intent")
        intent_hashes.add(intent_hash)
        batch_intents.append(intent)
    promotion_hashes: dict[str, Mapping[str, Any]] = {}
    entry_promotions: dict[str, bytes] = {}
    recovery_checkpoint = _checkpoint_for_config(_mapping(value.get("checkpoint"), "checkpoint"), cfg)
    for promotion in promotions:
        _validate_recovery_promotion(promotion)
        validate_promotion_record(
            promotion,
            expected_entry=_entry_for_recovery_promotion(recovery_checkpoint, promotion, value),
            runtime=value,
        )
        promotion_hash = str(promotion["promotion_hash"])
        if promotion_hash in promotion_hashes and dict(promotion_hashes[promotion_hash]) != dict(promotion):
            raise P136ObservationError("conflicting_promotion_record")
        promotion_hashes[promotion_hash] = promotion
        entry_hash = str(promotion["entry_hash"])
        encoded = _canonical_bytes(promotion)
        prior = entry_promotions.get(entry_hash)
        if prior is not None and prior != encoded:
            raise P136ObservationError("duplicate_p135_promotion_for_entry")
        entry_promotions[entry_hash] = encoded
    for recovered_checkpoint in checkpoints:
        _checkpoint_for_config(recovered_checkpoint, cfg)
    if batch_intents:
        checkpoint_advanced = False
        for intent in sorted(batch_intents, key=lambda item: str(item["intent_hash"])):
            restored = _recover_promotion_batch(Path(base_path_value) if base_path_value is not None else None, cfg, intent, promotion_hashes, value)
            written.extend(restored["promotions_written"])
            verified.extend(restored["promotions_verified"])
            checkpoint_advanced = checkpoint_advanced or bool(restored["checkpoint_advanced"])
    elif intents and not promotions:
        for intent in intents:
            intent_promotion_hash = intent.get("promotion_hash")
            if not isinstance(intent_promotion_hash, str):
                raise P136ObservationError("recovery_intent_missing_promotion_hash")
            written.append(intent_promotion_hash)
        checkpoint_advanced = False
    else:
        checkpoint_advanced = bool(promotions and not checkpoints)
    return {
        "promotions_written": written,
        "promotions_verified": verified,
        "checkpoint_advanced": checkpoint_advanced,
        "recovered_from_promotion_intent": bool(written),
        "recovered_from_promotions_before_checkpoint": checkpoint_advanced and not written,
        "p135_invocation_count": 0,
        "recovery_replay_count": len(written) + int(checkpoint_advanced),
    }


def advance_checkpoint(
    runtime: Mapping[str, Any],
    checkpoint: Mapping[str, Any],
    *,
    simulate_parent_fsync_uncertain: bool = False,
) -> dict[str, Any]:
    value = _mapping(runtime, "runtime")
    cfg = _ensure_config(_mapping(value.get("config"), "config"))
    if simulate_parent_fsync_uncertain:
        raise P136DurabilityUncertainError("checkpoint_parent_fsync_uncertain")
    result = _rehash_checkpoint(checkpoint)
    _checkpoint_for_config(result, cfg)
    base_path = value.get("base_path")
    if base_path is not None:
        try:
            _atomic_write_json(Path(base_path), cfg["checkpoint_path"], result)
        except P136DurabilityUncertainError as exc:
            raise P136DurabilityUncertainError("checkpoint_parent_fsync_uncertain") from exc
    return result


def run_observer_loop(runtime: Mapping[str, Any], *, max_cycles: int) -> dict[str, Any]:
    value = deepcopy(dict(_mapping(runtime, "runtime")))
    cfg = _ensure_config(_mapping(value.get("config"), "config"))
    checkpoint = _checkpoint_for_config(_mapping(value.get("checkpoint"), "checkpoint"), cfg)
    stop_reason = "max_cycles"
    cycles_completed = 0
    consecutive_failures = 0
    max_allowed = min(max_cycles, cfg["limits"]["max_cycles"])
    sleeper = value.get("sleep")
    sleep_fn = sleeper if callable(sleeper) else time.sleep
    monotonic = value.get("monotonic")
    monotonic_fn = monotonic if callable(monotonic) else time.monotonic
    next_deadline = float(monotonic_fn())
    for cycle_index in range(max_allowed):
        signal_name = _safe_signal_name(value)
        if signal_name is not None:
            stop_reason = f"signal_{signal_name}_safe_boundary"
            break
        if bool(value.get("force_cycle_failures")) and cycle_index < int(value.get("force_cycle_failures", 0)):
            consecutive_failures += 1
            if consecutive_failures >= cfg["limits"]["max_consecutive_failures"]:
                stop_reason = "failure_threshold"
                break
            continue
        try:
            result = observe_one_cycle({**value, "checkpoint": checkpoint})
        except P136ObservationError as exc:
            if str(exc) == "index_read_receipt_pool_exhausted":
                stop_reason = "receipt_exhaustion"
                break
            consecutive_failures += 1
            if consecutive_failures >= cfg["limits"]["max_consecutive_failures"]:
                stop_reason = "failure_threshold"
                break
            continue
        checkpoint = _checkpoint_for_config(result["advanced_checkpoint"], cfg)
        value["checkpoint"] = checkpoint
        cycles_completed += 1
        consecutive_failures = 0
        if cycle_index + 1 < max_allowed:
            next_deadline += cfg["limits"]["poll_interval_ms"] / 1000.0
            delay = next_deadline - float(monotonic_fn())
            if delay > 0:
                sleep_fn(delay)
    else:
        if max_cycles > cycles_completed:
            authority = _mapping(value.get("authority"), "authority")
            receipts = _sequence(authority.get("index_receipts"), "index_receipts")
            if len(checkpoint.get("consumed_index_read_receipt_hashes", [])) >= len(receipts):
                stop_reason = "receipt_exhaustion"
    termination = _termination_receipt(checkpoint, stop_reason, str(value.get("now")))
    return {"checkpoint": checkpoint, "termination_receipt": termination, "cycles_completed": cycles_completed}


def validate_measurement_schemas(evidence: Mapping[str, Any]) -> None:
    value = _mapping(evidence, "measurement")
    if set(value) != {
        "forbidden_authority",
        "runtime_activity",
        "evaluator_activity",
        "resource_usage",
    }:
        raise P136ObservationError("invalid_measurement_schema")
    _exact_counters(
        value.get("forbidden_authority"),
        FORBIDDEN_AUTHORITY_KEYS,
        "invalid_forbidden_authority_schema",
        require_zero=True,
    )
    _exact_counters(value.get("runtime_activity"), RUNTIME_ACTIVITY_KEYS, "invalid_runtime_activity_schema")
    _exact_counters(
        value.get("evaluator_activity"),
        EVALUATOR_ACTIVITY_KEYS,
        "invalid_evaluator_activity_schema",
    )
    _exact_counters(value.get("resource_usage"), RESOURCE_USAGE_KEYS, "invalid_resource_usage_schema")


class _ObserverLease:
    def __init__(self, base_path: Path, relative_path: str) -> None:
        self.base_path = base_path
        self.relative_path = relative_path
        self.handle: Any = None

    def __enter__(self) -> None:
        parts = PurePosixPath(_relative_path(self.relative_path, "lease_path")).parts
        parent_fd = _open_secure_parent_dir(self.base_path, parts, create=True, error="exclusive_lease_invalid")
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        try:
            fd = os.open(parts[-1], flags, 0o600, dir_fd=parent_fd)
        except OSError as exc:
            raise P136ObservationError("exclusive_lease_invalid") from exc
        finally:
            os.close(parent_fd)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            os.close(fd)
            raise P136ObservationError("exclusive_lease_invalid")
        self.handle = os.fdopen(fd, "a+", encoding="utf-8")
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self.handle.close()
            self.handle = None
            raise P136ObservationError("exclusive_lease_unavailable") from exc

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self.handle is not None:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()


def _ensure_config(value: Mapping[str, Any]) -> dict[str, Any]:
    if value.get("schema_version") == CONFIG_SCHEMA_VERSION:
        validate_incremental_observer_config(value)
        return deepcopy(dict(value))
    return build_incremental_observer_config(value)


def _validated_checkpoint(value: Mapping[str, Any]) -> dict[str, Any]:
    checkpoint = deepcopy(dict(value))
    if set(checkpoint) != _CHECKPOINT_FIELDS:
        raise P136ObservationError("invalid_checkpoint_fields")
    if checkpoint.get("schema_version") != CHECKPOINT_SCHEMA_VERSION:
        raise P136ObservationError("invalid_checkpoint_schema")
    expected_hash = checkpoint.get("checkpoint_hash")
    if expected_hash != stable_hash({key: item for key, item in checkpoint.items() if key != "checkpoint_hash"}):
        raise P136ObservationError("checkpoint_hash_invalid")
    _exact_counters(checkpoint.get("counters"), RUNTIME_ACTIVITY_KEYS, "invalid_runtime_activity_schema")
    _exact_counters(
        checkpoint.get("forbidden_authority"),
        FORBIDDEN_AUTHORITY_KEYS,
        "invalid_forbidden_authority_schema",
        require_zero=True,
    )
    return checkpoint


def _checkpoint_for_config(value: Mapping[str, Any], cfg: Mapping[str, Any]) -> dict[str, Any]:
    checkpoint = _validated_checkpoint(value)
    if checkpoint.get("config_hash") != cfg.get("config_hash"):
        raise P136ObservationError("checkpoint_config_hash_mismatch")
    return checkpoint


def _rehash_checkpoint(value: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(value))
    result.pop("checkpoint_hash", None)
    result["checkpoint_hash"] = stable_hash(result)
    return result


def _termination_receipt(checkpoint: Mapping[str, Any], stop_reason: str, completed_at: str) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "schema_version": TERMINATION_SCHEMA_VERSION,
        "stop_reason": stop_reason,
        "completed_at": completed_at,
        "final_checkpoint_hash": checkpoint["checkpoint_hash"],
        "consumed_index_read_receipt_hashes": list(checkpoint.get("consumed_index_read_receipt_hashes", [])),
        "reserved_index_read_receipt_hashes": list(checkpoint.get("reserved_index_read_receipt_hashes", [])),
        "forbidden_authority": deepcopy(checkpoint["forbidden_authority"]),
    }
    receipt["termination_hash"] = stable_hash(receipt)
    return receipt


def _validate_index_intent(
    intent: Mapping[str, Any],
    cfg: Mapping[str, Any],
    checkpoint: Mapping[str, Any],
    receipt: Mapping[str, Any],
) -> Mapping[str, Any]:
    if intent.get("schema_version") != INDEX_INTENT_SCHEMA_VERSION:
        raise P136ObservationError("invalid_index_read_intent_schema")
    if intent.get("intent_hash") != stable_hash({key: item for key, item in intent.items() if key != "intent_hash"}):
        raise P136ObservationError("index_read_intent_hash_invalid")
    if intent.get("config_hash") != cfg.get("config_hash"):
        raise P136ObservationError("index_read_intent_config_mismatch")
    if intent.get("checkpoint_hash") != checkpoint.get("checkpoint_hash"):
        raise P136ObservationError("index_read_intent_checkpoint_mismatch")
    if intent.get("receipt_hash") != receipt.get("receipt_hash"):
        raise P136ObservationError("index_read_intent_receipt_mismatch")
    if intent.get("receipt_bytes_hash") != _content_hash(_canonical_bytes(receipt)):
        raise P136ObservationError("index_read_intent_receipt_bytes_mismatch")
    return intent


def _discover_index_read_intent(
    base_path: Path,
    cfg: Mapping[str, Any],
    checkpoint: Mapping[str, Any],
    receipts: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    receipt_by_hash = {str(item.get("receipt_hash")): item for item in receipts}
    consumed = set(str(item) for item in _sequence(checkpoint.get("consumed_index_read_receipt_hashes", []), "consumed_index_read_receipt_hashes"))
    candidates = _read_json_dir(base_path, str(cfg["index_intent_dir"]), cfg["limits"]["max_journal_bytes"])
    matches: list[Mapping[str, Any]] = []
    for raw in candidates:
        if not isinstance(raw, Mapping):
            continue
        receipt = receipt_by_hash.get(str(raw.get("receipt_hash")))
        if receipt is None or str(raw.get("receipt_hash")) in consumed:
            continue
        try:
            _validate_index_intent(raw, cfg, checkpoint, receipt)
        except P136ObservationError:
            continue
        matches.append(raw)
    if len(matches) > 1:
        raise P136ObservationError("multiple_index_read_intents_for_checkpoint")
    return matches[0] if matches else None


def _promotion_key(
    *,
    cfg: Mapping[str, Any],
    entry: Mapping[str, Any],
    contract: Mapping[str, Any],
    ledger: Mapping[str, Any],
    receipt: Mapping[str, Any],
    manifest: Mapping[str, Any],
    artifact: Mapping[str, Any],
    execution: Mapping[str, Any],
    nested_ledger: Mapping[str, Any],
    bundle: Mapping[str, Any],
) -> str:
    return stable_hash(
        {
            "schema_version": "p136.promotion_key.v1",
            "config_hash": cfg["config_hash"],
            "entry_hash": entry["entry_hash"],
            "p134_contract_hash": contract["contract_hash"],
            "p134_receipt_ledger_hash": ledger["ledger_hash"],
            "p134_segment_receipt_hash": receipt["receipt_hash"],
            "p135_manifest_hash": manifest["manifest_hash"],
            "p135_artifact_spec_hash": artifact["artifact_spec_hash"],
            "p135_execution_receipt_hash": execution["receipt_hash"],
            "p135_receipt_ledger_hash": nested_ledger["ledger_hash"],
            "p135_normalized_bundle_hash": bundle["bundle_hash"],
        }
    )


def _promotion_batch_intent(
    cfg: Mapping[str, Any],
    checkpoint: Mapping[str, Any],
    index_read_intent: Mapping[str, Any],
    promotions: Sequence[Mapping[str, Any]],
    post_cycle_checkpoint: Mapping[str, Any],
) -> dict[str, Any]:
    promotion_records = [deepcopy(dict(_mapping(item, "promotion"))) for item in promotions]
    _validate_promotion_sequence(promotion_records, int(checkpoint.get("next_promotion_sequence", 1)))
    intent: dict[str, Any] = {
        "schema_version": PROMOTION_INTENT_SCHEMA_VERSION,
        "config_hash": cfg["config_hash"],
        "checkpoint_hash": checkpoint["checkpoint_hash"],
        "index_read_intent_hash": index_read_intent["intent_hash"],
        "cycle_id": index_read_intent["cycle_id"],
        "index_read_receipt_hash": index_read_intent["receipt_hash"],
        "post_cycle_checkpoint_hash": post_cycle_checkpoint["checkpoint_hash"],
        "post_cycle_checkpoint": deepcopy(dict(post_cycle_checkpoint)),
        "promotion_count": len(promotion_records),
        "promotion_hashes": [item["promotion_hash"] for item in promotion_records],
        "promotion_records": promotion_records,
        "fsync": {"file": True, "parent_directory": True},
    }
    intent["intent_hash"] = stable_hash(intent)
    return intent


def _validate_promotion_intent(intent: Mapping[str, Any], cfg: Mapping[str, Any]) -> None:
    if set(intent) != _PROMOTION_INTENT_FIELDS or intent.get("schema_version") != PROMOTION_INTENT_SCHEMA_VERSION:
        raise P136ObservationError("invalid_promotion_intent_schema")
    if intent.get("intent_hash") != stable_hash({key: item for key, item in intent.items() if key != "intent_hash"}):
        raise P136ObservationError("promotion_intent_hash_invalid")
    if intent.get("config_hash") != cfg.get("config_hash"):
        raise P136ObservationError("promotion_intent_config_mismatch")
    _hash(intent.get("checkpoint_hash"), "checkpoint_hash")
    _hash(intent.get("index_read_intent_hash"), "index_read_intent_hash")
    _hash(intent.get("cycle_id"), "cycle_id")
    _hash(intent.get("index_read_receipt_hash"), "index_read_receipt_hash")
    checkpoint = _checkpoint_for_config(_mapping(intent.get("post_cycle_checkpoint"), "post_cycle_checkpoint"), cfg)
    if checkpoint.get("checkpoint_hash") != intent.get("post_cycle_checkpoint_hash"):
        raise P136ObservationError("promotion_intent_checkpoint_hash_mismatch")
    promotions = [_mapping(item, "promotion") for item in _sequence(intent.get("promotion_records"), "promotion_records")]
    if len(promotions) != _positive_int(intent.get("promotion_count"), "promotion_count"):
        raise P136ObservationError("promotion_intent_count_mismatch")
    hashes = [_hash(item.get("promotion_hash"), "promotion_hash") for item in promotions]
    if hashes != list(_sequence(intent.get("promotion_hashes"), "promotion_hashes")):
        raise P136ObservationError("promotion_intent_hashes_mismatch")
    _validate_promotion_sequence(promotions, min((int(item["promotion_sequence"]) for item in promotions), default=1))
    for promotion in promotions:
        _validate_recovery_promotion(promotion)


def _validate_recovery_promotion(promotion: Mapping[str, Any]) -> None:
    if set(promotion) != _PROMOTION_FIELDS or promotion.get("schema_version") != PROMOTION_SCHEMA_VERSION:
        raise P136ObservationError("invalid_promotion_fields")
    if promotion.get("promotion_hash") != stable_hash({key: item for key, item in promotion.items() if key != "promotion_hash"}):
        raise P136ObservationError("promotion_hash_invalid")
    _positive_int(promotion.get("promotion_sequence"), "promotion_sequence")
    _hash(promotion.get("entry_hash"), "entry_hash")
    _hash(promotion.get("promotion_key"), "promotion_key")
    _exact_counters(promotion.get("activity"), RUNTIME_ACTIVITY_KEYS, "invalid_runtime_activity_schema")
    _exact_counters(
        promotion.get("forbidden_authority"),
        FORBIDDEN_AUTHORITY_KEYS,
        "invalid_forbidden_authority_schema",
        require_zero=True,
    )


def _validate_promotion_sequence(promotions: Sequence[Mapping[str, Any]], expected_start: int) -> None:
    seen_entries: dict[str, bytes] = {}
    for offset, promotion in enumerate(promotions):
        sequence = _positive_int(promotion.get("promotion_sequence"), "promotion_sequence")
        if sequence != expected_start + offset:
            raise P136ObservationError("promotion_sequence_mismatch")
        entry_hash = _hash(promotion.get("entry_hash"), "entry_hash")
        encoded = _canonical_bytes(promotion)
        prior = seen_entries.get(entry_hash)
        if prior is not None and prior != encoded:
            raise P136ObservationError("duplicate_p135_promotion_for_entry")
        seen_entries[entry_hash] = encoded


def _recover_promotion_batch(
    base_path: Path | None,
    cfg: Mapping[str, Any],
    intent: Mapping[str, Any],
    persisted_promotions: Mapping[str, Mapping[str, Any]],
    runtime: Mapping[str, Any],
) -> dict[str, Any]:
    _validate_promotion_intent(intent, cfg)
    start_checkpoint = _checkpoint_for_config(_mapping(runtime.get("checkpoint"), "checkpoint"), cfg)
    if intent.get("checkpoint_hash") != start_checkpoint.get("checkpoint_hash"):
        raise P136ObservationError("promotion_intent_checkpoint_mismatch")
    post_checkpoint = _checkpoint_for_config(_mapping(intent.get("post_cycle_checkpoint"), "post_cycle_checkpoint"), cfg)
    promotions = [_mapping(item, "promotion") for item in _sequence(intent.get("promotion_records"), "promotion_records")]
    _validate_promotion_sequence(promotions, int(start_checkpoint.get("next_promotion_sequence", 1)))
    written: list[str] = []
    verified: list[str] = []
    expected_by_entry: dict[str, bytes] = {}
    for promotion in promotions:
        expected = _canonical_bytes(promotion)
        entry_hash = str(promotion["entry_hash"])
        prior = expected_by_entry.get(entry_hash)
        if prior is not None and prior != expected:
            raise P136ObservationError("duplicate_p135_promotion_for_entry")
        expected_by_entry[entry_hash] = expected
        validate_promotion_record(
            promotion,
            expected_entry=_entry_for_recovery_promotion(post_checkpoint, promotion, runtime),
            runtime=runtime,
        )
        existing = persisted_promotions.get(str(promotion["promotion_hash"]))
        if existing is not None:
            if _canonical_bytes(existing) != expected:
                raise P136ObservationError("promotion_record_byte_conflict")
            verified.append(str(promotion["promotion_hash"]))
            continue
        if base_path is None:
            written.append(str(promotion["promotion_hash"]))
            continue
        _atomic_write_limited_json(
            base_path,
            f"{cfg['promotion_dir']}/{str(promotion['promotion_hash']).removeprefix('sha256:')}.json",
            promotion,
            cfg["limits"]["max_promotion_bytes"],
            "promotion_record_byte_budget_exceeded",
        )
        reread = _read_required_json(
            base_path,
            f"{cfg['promotion_dir']}/{str(promotion['promotion_hash']).removeprefix('sha256:')}.json",
            cfg["limits"]["max_promotion_bytes"],
        )
        if _canonical_bytes(_mapping(reread, "promotion")) != expected:
            raise P136ObservationError("promotion_record_byte_conflict")
        written.append(str(promotion["promotion_hash"]))
        verified.append(str(promotion["promotion_hash"]))
    checkpoint_advanced = False
    if base_path is not None:
        current = _read_optional_json(base_path, cfg["checkpoint_path"], cfg["limits"]["max_journal_bytes"])
        if current is None or _checkpoint_for_config(_mapping(current, "checkpoint"), cfg)["checkpoint_hash"] == start_checkpoint["checkpoint_hash"]:
            for promotion in promotions:
                persisted = _read_required_json(
                    base_path,
                    f"{cfg['promotion_dir']}/{str(promotion['promotion_hash']).removeprefix('sha256:')}.json",
                    cfg["limits"]["max_promotion_bytes"],
                )
                if _canonical_bytes(_mapping(persisted, "promotion")) != _canonical_bytes(promotion):
                    raise P136ObservationError("promotion_record_byte_conflict")
            _atomic_write_limited_json(
                base_path,
                cfg["checkpoint_path"],
                post_checkpoint,
                cfg["limits"]["max_journal_bytes"],
                "checkpoint_byte_budget_exceeded",
            )
            checkpoint_advanced = True
        elif _checkpoint_for_config(_mapping(current, "checkpoint"), cfg)["checkpoint_hash"] != post_checkpoint["checkpoint_hash"]:
            raise P136ObservationError("checkpoint_recovery_conflict")
    return {
        "promotions_written": written,
        "promotions_verified": verified,
        "checkpoint_advanced": checkpoint_advanced,
    }


def _entry_for_recovery_promotion(
    checkpoint: Mapping[str, Any],
    promotion: Mapping[str, Any],
    runtime: Mapping[str, Any],
) -> Mapping[str, Any]:
    entry_hash = str(promotion["entry_hash"])
    provider_entries = runtime.get("provider_entries")
    if isinstance(provider_entries, Mapping):
        for item in provider_entries.values():
            if isinstance(item, Mapping) and item.get("entry_hash") == entry_hash:
                return item
    for item in _canonical_map(checkpoint).values():
        if item.get("entry_hash") == entry_hash:
            return item
    raise P136ObservationError("promotion_entry_not_canonical")


def _advance_observation_checkpoint(
    checkpoint: Mapping[str, Any],
    cfg: Mapping[str, Any],
    scan: Mapping[str, Any],
    promotions: Sequence[Mapping[str, Any]],
    *,
    duplicate_count: int,
    receipt_hash: str,
    updated_at: str,
) -> dict[str, Any]:
    result = deepcopy(dict(checkpoint))
    result.update(_mapping(scan.get("checkpoint_patch"), "checkpoint_patch"))
    canonical = dict(_mapping(result.get("canonical_entry_identities", {}), "canonical_entry_identities"))
    promotion_keys = dict(_mapping(result.get("promotion_keys", {}), "promotion_keys"))
    complete_entries = [_mapping(item, "entry") for item in _sequence(scan.get("complete_entries"), "complete_entries")]
    for entry in complete_entries:
        if str(entry["entry_hash"]) in promotion_keys:
            continue
        canonical[str(entry["entry_id"])] = dict(entry)
        canonical[str(entry["segment_id"])] = dict(entry)
        result["last_entry_hash"] = entry["entry_hash"]
        result["next_entry_sequence"] = max(int(result.get("next_entry_sequence", 1)), int(entry["entry_sequence"]) + 1)
    for promotion in promotions:
        promotion_keys[str(promotion["entry_hash"])] = dict(promotion)
        result["last_promotion_hash"] = promotion["promotion_hash"]
        result["next_promotion_sequence"] = max(int(result.get("next_promotion_sequence", 1)), int(promotion["promotion_sequence"]) + 1)
    retained_entries = {str(item.get("entry_hash")) for item in canonical.values() if isinstance(item, Mapping)}
    if len(retained_entries) > cfg["limits"]["max_retained_entry_identities"]:
        raise P136ObservationError("retained_entry_identity_budget_exceeded")
    reserved = list(_sequence(result.get("reserved_index_read_receipt_hashes", []), "reserved_index_read_receipt_hashes"))
    consumed = list(_sequence(result.get("consumed_index_read_receipt_hashes", []), "consumed_index_read_receipt_hashes"))
    if receipt_hash not in reserved:
        reserved.append(receipt_hash)
    if receipt_hash not in consumed:
        consumed.append(receipt_hash)
    result["reserved_index_read_receipt_hashes"] = reserved
    result["consumed_index_read_receipt_hashes"] = consumed
    result["canonical_entry_identities"] = canonical
    result["promotion_keys"] = promotion_keys
    counters = _merge_activity(
        _exact_counters(result.get("counters"), RUNTIME_ACTIVITY_KEYS, "invalid_runtime_activity_schema"),
        {
            "checkpoint_write_count": 1,
            "duplicate_resolution_count": duplicate_count,
            "rotation_count": int(bool(scan.get("rotated"))),
        },
        *[_mapping(promotion.get("activity"), "promotion_activity") for promotion in promotions],
    )
    result["counters"] = counters
    result["config_hash"] = cfg["config_hash"]
    result["updated_at"] = updated_at
    result.pop("checkpoint_hash", None)
    return result


def _merge_activity(base: Mapping[str, int], *parts: Mapping[str, int]) -> dict[str, int]:
    result = _exact_counters(base, RUNTIME_ACTIVITY_KEYS, "invalid_runtime_activity_schema")
    for part in parts:
        unknown = set(part) - set(RUNTIME_ACTIVITY_KEYS)
        if unknown:
            raise P136ObservationError("invalid_runtime_activity_schema")
        for key, value in part.items():
            if type(value) is not int or value < 0:
                raise P136ObservationError("invalid_runtime_activity_schema")
            result[key] += value
    return result


def _safe_signal_name(runtime: Mapping[str, Any]) -> str | None:
    signal_name = runtime.get("inject_signal")
    if signal_name in {"SIGINT", "SIGTERM"}:
        return str(signal_name)
    checker = runtime.get("safe_boundary_signal")
    if callable(checker):
        value = checker()
        if value in {"SIGINT", "SIGTERM"}:
            return str(value)
    return None


def _read_secure_regular_file(base_path: Path, relative_path: str, maximum: int, probe: Any) -> tuple[bytes, str]:
    parts = PurePosixPath(_relative_path(relative_path, "index_path")).parts
    dir_fd = _open_secure_parent_dir(base_path, parts, create=False, error="index_parent_symlink_or_invalid")
    try:
        before_entry = _stat_secure_regular_entry(dir_fd, parts[-1], "index_not_secure_regular_file")
        _record_probe(probe, "index_open")
        try:
            fd = os.open(parts[-1], os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0), dir_fd=dir_fd)
        except OSError as exc:
            raise P136ObservationError("index_open_failed") from exc
        try:
            return _read_regular_fd(fd, maximum, probe, parent_fd=dir_fd, entry_name=parts[-1], before_entry=before_entry)
        finally:
            os.close(fd)
    finally:
        os.close(dir_fd)


def _read_regular_file(path: Path, maximum: int, probe: Any) -> tuple[bytes, str]:
    _record_probe(probe, "index_open")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise P136ObservationError("index_open_failed") from exc
    try:
        return _read_regular_fd(fd, maximum, probe)
    finally:
        os.close(fd)


def _read_regular_fd(
    fd: int,
    maximum: int,
    probe: Any,
    *,
    parent_fd: int | None = None,
    entry_name: str | None = None,
    before_entry: os.stat_result | None = None,
) -> tuple[bytes, str]:
    before = os.fstat(fd)
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise P136ObservationError("index_not_secure_regular_file")
    if before_entry is not None and not _same_file_binding(before_entry, before):
        raise P136ObservationError("index_path_binding_changed")
    _record_probe(probe, "index_read")
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = os.read(fd, min(65_536, maximum + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > maximum:
            raise P136ObservationError("whole_index_byte_budget_exceeded")
    after = os.fstat(fd)
    if (before.st_dev, before.st_ino, before.st_size) != (after.st_dev, after.st_ino, after.st_size):
        raise P136ObservationError("index_identity_changed_during_read")
    if parent_fd is not None and entry_name is not None:
        after_entry = _stat_secure_regular_entry(parent_fd, entry_name, "index_not_secure_regular_file")
        if not _same_file_binding(after_entry, after):
            raise P136ObservationError("index_path_binding_changed")
    identity = stable_hash(
        {
            "schema_version": "p136.file_identity.v1",
            "device": after.st_dev,
            "inode": after.st_ino,
        }
    )
    return b"".join(chunks), identity


def _atomic_write_json(base_path: Path, relative_path: str, value: Mapping[str, Any]) -> None:
    parts = PurePosixPath(_relative_path(relative_path, "state_path")).parts
    parent_fd = _open_secure_parent_dir(base_path, parts, create=True, error="state_parent_symlink_or_invalid")
    target_name = parts[-1]
    temp_name = f".{target_name}.{os.getpid()}.{time.monotonic_ns()}.tmp"
    replaced = False
    descriptor: int | None = None
    try:
        try:
            _stat_secure_regular_entry(parent_fd, target_name, "state_target_not_secure_regular_file")
        except FileNotFoundError:
            pass
        descriptor = os.open(
            temp_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
            0o600,
            dir_fd=parent_fd,
        )
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(_canonical_bytes(value) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        temp_info = _stat_secure_regular_entry(parent_fd, temp_name, "state_temp_not_secure_regular_file")
        if temp_info.st_nlink != 1:
            raise P136ObservationError("state_temp_not_secure_regular_file")
        os.rename(temp_name, target_name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        replaced = True
        _stat_secure_regular_entry(parent_fd, target_name, "state_target_not_secure_regular_file")
        os.fsync(parent_fd)
    except OSError as exc:
        if replaced:
            raise P136DurabilityUncertainError("directory_fsync_failed_after_replace") from exc
        raise P136ObservationError("atomic_write_failed") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            os.unlink(temp_name, dir_fd=parent_fd)
        except FileNotFoundError:
            pass
        except OSError:
            pass
        os.close(parent_fd)


def _atomic_write_limited_json(
    base_path: Path,
    relative_path: str,
    value: Mapping[str, Any],
    maximum: int,
    error: str,
) -> None:
    if len(_canonical_bytes(value)) + 1 > maximum:
        raise P136ObservationError(error)
    _atomic_write_json(base_path, relative_path, value)


def _read_persisted_promotion_intents(base_path: Path, cfg: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [
        _mapping(item, "promotion_intent")
        for item in _read_json_dir(base_path, str(cfg["journal_dir"]), cfg["limits"]["max_journal_bytes"])
    ]


def _read_persisted_promotions(base_path: Path, cfg: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [
        _mapping(item, "promotion")
        for item in _read_json_dir(base_path, str(cfg["promotion_dir"]), cfg["limits"]["max_promotion_bytes"])
    ]


def _read_json_dir(base_path: Path, relative_dir: str, maximum: int) -> list[Any]:
    try:
        dir_fd = _open_secure_dir(base_path, PurePosixPath(_relative_path(relative_dir, "state_dir")).parts, create=False, error="state_parent_symlink_or_invalid")
    except FileNotFoundError:
        return []
    try:
        names = sorted(name for name in os.listdir(dir_fd) if name.endswith(".json"))
        values = []
        for name in names:
            values.append(_read_json_entry(dir_fd, name, maximum))
        return values
    finally:
        os.close(dir_fd)


def _read_optional_json(base_path: Path, relative_path: str, maximum: int) -> Any | None:
    try:
        return _read_required_json(base_path, relative_path, maximum)
    except FileNotFoundError:
        return None


def _read_required_json(base_path: Path, relative_path: str, maximum: int) -> Any:
    parts = PurePosixPath(_relative_path(relative_path, "state_path")).parts
    parent_fd = _open_secure_parent_dir(base_path, parts, create=False, error="state_parent_symlink_or_invalid")
    try:
        return _read_json_entry(parent_fd, parts[-1], maximum)
    finally:
        os.close(parent_fd)


def _read_json_entry(parent_fd: int, name: str, maximum: int) -> Any:
    _stat_secure_regular_entry(parent_fd, name, "state_target_not_secure_regular_file")
    try:
        fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0), dir_fd=parent_fd)
    except OSError as exc:
        raise P136ObservationError("state_read_failed") from exc
    try:
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, min(65_536, maximum + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > maximum:
                raise P136ObservationError("state_json_byte_budget_exceeded")
        data = b"".join(chunks)
        if data.endswith(b"\n"):
            data = data[:-1]
        return json.loads(data.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise P136ObservationError("state_json_malformed") from exc
    finally:
        os.close(fd)


def _open_base_dir(base_path: Path, error: str) -> int:
    try:
        fd = os.open(base_path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
    except OSError as exc:
        raise P136ObservationError(error) from exc
    info = os.fstat(fd)
    if not stat.S_ISDIR(info.st_mode):
        os.close(fd)
        raise P136ObservationError(error)
    return fd


def _open_secure_dir(base_path: Path, parts: Sequence[str], *, create: bool, error: str) -> int:
    dir_fd = _open_base_dir(base_path, error)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    for part in parts:
        try:
            child_fd = os.open(part, flags, dir_fd=dir_fd)
        except FileNotFoundError:
            if not create:
                os.close(dir_fd)
                raise
            try:
                os.mkdir(part, 0o700, dir_fd=dir_fd)
                child_fd = os.open(part, flags, dir_fd=dir_fd)
            except OSError as exc:
                os.close(dir_fd)
                raise P136ObservationError(error) from exc
        except OSError as exc:
            os.close(dir_fd)
            raise P136ObservationError(error) from exc
        info = os.fstat(child_fd)
        if not stat.S_ISDIR(info.st_mode):
            os.close(child_fd)
            os.close(dir_fd)
            raise P136ObservationError(error)
        os.close(dir_fd)
        dir_fd = child_fd
    return dir_fd


def _open_secure_parent_dir(base_path: Path, parts: Sequence[str], *, create: bool, error: str) -> int:
    if not parts:
        raise P136ObservationError(error)
    dir_fd = _open_base_dir(base_path, error)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    for part in parts[:-1]:
        try:
            child_fd = os.open(part, flags, dir_fd=dir_fd)
        except FileNotFoundError:
            if not create:
                os.close(dir_fd)
                raise P136ObservationError(error) from None
            try:
                os.mkdir(part, 0o700, dir_fd=dir_fd)
                child_fd = os.open(part, flags, dir_fd=dir_fd)
            except OSError as exc:
                os.close(dir_fd)
                raise P136ObservationError(error) from exc
        except OSError as exc:
            os.close(dir_fd)
            raise P136ObservationError(error) from exc
        info = os.fstat(child_fd)
        if not stat.S_ISDIR(info.st_mode):
            os.close(child_fd)
            os.close(dir_fd)
            raise P136ObservationError(error)
        os.close(dir_fd)
        dir_fd = child_fd
    return dir_fd


def _stat_secure_regular_entry(parent_fd: int, name: str, error: str) -> os.stat_result:
    try:
        info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise P136ObservationError(error) from exc
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise P136ObservationError(error)
    return info


def _same_file_binding(entry: os.stat_result, opened: os.stat_result) -> bool:
    return (entry.st_dev, entry.st_ino) == (opened.st_dev, opened.st_ino)


def _strict_json(data: bytes, *, limits: Mapping[str, int]) -> Any:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise P136ObservationError("invalid_index_utf8") from exc

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise P136ObservationError("duplicate_json_key")
            result[key] = value
        return result

    def constant(value: str) -> None:
        raise P136ObservationError(f"non_finite_number:{value}")

    try:
        result = json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    except P136ObservationError:
        raise
    except json.JSONDecodeError as exc:
        raise P136ObservationError("malformed_index_json") from exc
    node_count = _validate_json_tree(result, limits=limits)
    if node_count > limits["max_json_nodes"]:
        raise P136ObservationError("index_json_node_budget_exceeded")
    return result


def _validate_json_tree(value: Any, *, limits: Mapping[str, int], depth: int = 0) -> int:
    if depth > limits["max_json_depth"]:
        raise P136ObservationError("index_json_depth_exceeded")
    if isinstance(value, str):
        if len(value.encode("utf-8")) > limits["max_json_string_bytes"]:
            raise P136ObservationError("index_json_string_budget_exceeded")
        return 1
    if isinstance(value, float) and not math.isfinite(value):
        raise P136ObservationError("non_finite_number")
    if isinstance(value, Mapping):
        total = 1
        for item in value.values():
            total += _validate_json_tree(item, limits=limits, depth=depth + 1)
            if total > limits["max_json_nodes"]:
                raise P136ObservationError("index_json_node_budget_exceeded")
        return total
    if _is_sequence(value):
        total = 1
        for item in value:
            total += _validate_json_tree(item, limits=limits, depth=depth + 1)
            if total > limits["max_json_nodes"]:
                raise P136ObservationError("index_json_node_budget_exceeded")
        return total
    return 1


def _canonical_identity(checkpoint: Mapping[str, Any], entry: Mapping[str, Any]) -> Mapping[str, Any] | None:
    identities = _canonical_map(checkpoint)
    by_entry = identities.get(str(entry.get("entry_id")))
    by_segment = identities.get(str(entry.get("segment_id")))
    if by_entry is not None and by_segment is not None and dict(by_entry) != dict(by_segment):
        raise P136ObservationError("canonical_identity_map_conflict")
    return by_entry or by_segment


def _canonical_map(checkpoint: Mapping[str, Any]) -> Mapping[str, Mapping[str, Any]]:
    raw = _mapping(checkpoint.get("canonical_entry_identities", {}), "canonical_entry_identities")
    result: dict[str, Mapping[str, Any]] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, Mapping):
            raise P136ObservationError("invalid_canonical_entry_identity")
        result[key] = value
    return result


def _p135_limits() -> dict[str, int]:
    return {
        "max_artifacts": 1,
        "max_file_bytes": 4_194_304,
        "max_total_bytes": 4_194_304,
        "max_records_per_artifact": 10_000,
        "max_total_records": 10_000,
        "max_json_depth": 32,
        "max_json_nodes": 200_000,
        "max_string_bytes": 32_768,
        "max_preview_bytes": 128,
        "max_attributes_per_record": 64,
        "max_line_bytes": 1_048_576,
    }


def _manifest_id(entry_id: str) -> str:
    candidate = f"p136-{entry_id}"
    if len(candidate) <= 64:
        return candidate
    return f"p136-{stable_hash(entry_id).removeprefix('sha256:')[:40]}"


def _validate_limits(value: Any) -> dict[str, int]:
    limits = _mapping(value, "limits")
    if set(limits) != _LIMIT_FIELDS:
        raise P136ObservationError("invalid_limits_fields")
    result: dict[str, int] = {}
    for key in _LIMIT_FIELDS:
        item = limits.get(key)
        if type(item) is not int or item <= 0:
            raise P136ObservationError(f"invalid_limit:{key}")
        result[key] = item
    if result["max_index_line_bytes"] > result["max_whole_index_bytes"]:
        raise P136ObservationError("index_line_limit_exceeds_whole_index_limit")
    return result


def _validate_path_topology(paths: Mapping[str, str]) -> None:
    index_parts = PurePosixPath(paths["index_path"]).parts
    state_names = ("checkpoint_path", "index_intent_dir", "journal_dir", "promotion_dir", "lease_path")
    for name in state_names:
        parts = PurePosixPath(paths[name]).parts
        if parts[: len(index_parts)] == index_parts or index_parts[: len(parts)] == parts:
            raise P136ObservationError("state_path_overlaps_index_path")
    state_paths = [PurePosixPath(paths[name]) for name in state_names]
    if len({str(path) for path in state_paths}) != len(state_paths):
        raise P136ObservationError("state_paths_overlap")


def _path_ref(value: Any, label: str) -> dict[str, str]:
    mapping = _mapping(value, label)
    if set(mapping) != {"path_ref_hash"}:
        raise P136ObservationError(f"invalid_{label}_reference")
    return {"path_ref_hash": _hash(mapping.get("path_ref_hash"), f"{label}_hash")}


def _relative_path(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise P136ObservationError(f"invalid_{label}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise P136ObservationError(f"invalid_{label}")
    return value


def _exact_counters(
    value: Any,
    keys: Sequence[str],
    error: str,
    *,
    require_zero: bool = False,
) -> dict[str, int]:
    counters = _mapping(value, "counters")
    if set(counters) != set(keys):
        raise P136ObservationError(error)
    result: dict[str, int] = {}
    for key in keys:
        item = counters.get(key)
        if type(item) is not int or item < 0 or (require_zero and item != 0):
            raise P136ObservationError(error)
        result[key] = item
    return result


def _record_probe(probe: Any, event: str) -> None:
    record = getattr(probe, "record", None)
    if callable(record):
        record(event)


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _content_hash(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise P136ObservationError(f"invalid_{label}_shape")
    return value


def _sequence(value: Any, label: str) -> list[Any]:
    if not _is_sequence(value):
        raise P136ObservationError(f"invalid_{label}_shape")
    return list(value)


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _bytes(value: Any, label: str) -> bytes:
    if not isinstance(value, (bytes, bytearray)):
        raise P136ObservationError(f"invalid_{label}")
    return bytes(value)


def _hash(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _HASH_RE.fullmatch(value):
        raise P136ObservationError(f"invalid_{label}")
    return value


def _label(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _LABEL_RE.fullmatch(value):
        raise P136ObservationError(f"invalid_{label}")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 256:
        raise P136ObservationError(f"invalid_{label}")
    return value


def _positive_int(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise P136ObservationError(f"invalid_{label}")
    return value


def _parse_timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise P136ObservationError(f"invalid_{label}")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise P136ObservationError(f"invalid_{label}") from exc
    if parsed.tzinfo is None:
        raise P136ObservationError(f"invalid_{label}")
    return parsed.astimezone(UTC)


def _validated_checkpoint_time(
    checkpoint: Mapping[str, Any],
    cfg: Mapping[str, Any],
    runtime_now: str,
) -> str:
    current = _parse_timestamp(runtime_now, "now")
    previous_text = _timestamp(checkpoint.get("updated_at"), "checkpoint_updated_at")
    previous = _parse_timestamp(previous_text, "checkpoint_updated_at")
    tolerance = timedelta(milliseconds=int(cfg["limits"]["max_clock_rollback_ms"]))
    if previous - current > tolerance:
        raise P136ObservationError("clock_rollback_exceeded")
    return runtime_now if current >= previous else previous_text


def _timestamp(value: Any, label: str) -> str:
    _parse_timestamp(value, label)
    return str(value)
