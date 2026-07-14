"""Local-only reconciliation supervisor for P136 observation and P137 triage.

P138 owns coordination records only. P136 remains the sole observer and handoff
publisher; P137 remains the sole handoff validator and triage runtime.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import resource
import signal
import stat
import time
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from types import FrameType
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p136_incremental_observer import (
    CYCLE_COMPLETION_SCHEMA_VERSION,
    P136ObservationError,
    observe_one_cycle,
    recover_cycle_outcome,
    validate_cycle_outcome,
    validate_incremental_observer_config,
)
from app.services.p136_incremental_observer import (
    FORBIDDEN_AUTHORITY_KEYS as P136_FORBIDDEN_AUTHORITY_KEYS,
)
from app.services.p136_release_evidence import (
    P136ReleaseEvidenceError,
    validate_p136_release_evidence,
)
from app.services.p137_contracts import (
    CHECKPOINT_SCHEMA_VERSION as P137_CHECKPOINT_SCHEMA_VERSION,
)
from app.services.p137_contracts import (
    FIXED_P136_HANDOFF_PATH,
    P137ContractError,
    validate_triage_agent_config,
)
from app.services.p137_contracts import (
    FORBIDDEN_AUTHORITY_KEYS as P137_FORBIDDEN_AUTHORITY_KEYS,
)
from app.services.p137_ledger import P137LedgerError, validate_investigation_ledger
from app.services.p137_p136_handoff import (
    PUBLISHER_STATE_FIELDS,
    PUBLISHER_STATE_SCHEMA_VERSION,
    P137HandoffError,
    canonical_json_bytes,
    publish_p136_handoff_bundle,
    read_p136_handoff_publication_snapshot,
    recover_p136_handoff_publication,
    validate_p136_handoff_bundle,
)
from app.services.p137_release_evidence import (
    P137ReleaseEvidenceError,
    validate_p137_release_evidence,
)
from app.services.p137_runtime import (
    P137RuntimeError,
    run_p137_runtime_once,
)

CONFIG_SCHEMA_VERSION = "p138.observation_triage_supervisor_config.v1"
PHASE_SCHEMA_VERSION = "p138.supervisor_phase.v1"
LEDGER_SCHEMA_VERSION = "p138.supervisor_ledger.v1"
CHECKPOINT_SCHEMA_VERSION = "p138.supervisor_checkpoint.v1"
HEARTBEAT_SCHEMA_VERSION = "p138.supervisor_heartbeat.v1"
READINESS_SCHEMA_VERSION = "p138.supervisor_readiness.v1"
TERMINATION_SCHEMA_VERSION = "p138.supervisor_termination.v1"
RESULT_SCHEMA_VERSION = "p138.supervisor_result.v1"
LOOP_RESULT_SCHEMA_VERSION = "p138.supervisor_loop_result.v1"

P136_QUALIFIED_STATUS = "p136_incremental_local_observation_qualified"
P137_QUALIFIED_STATUS = "p137_local_evidence_triage_qualified"

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
    "supervisor_lease_acquire_count",
    "supervisor_state_read_count",
    "phase_write_count",
    "ledger_write_count",
    "heartbeat_write_count",
    "readiness_write_count",
    "termination_write_count",
    "reconciliation_count",
    "observation_count",
    "publication_count",
    "triage_count",
    "recovery_count",
    "no_work_count",
    "fsync_count",
)
EVALUATOR_ACTIVITY_KEYS = (
    "runner_invocation_count",
    "profile_read_count",
    "artifact_write_count",
    "fake_guard_injection_count",
    "signal_injection_count",
    "crash_injection_count",
)
RESOURCE_USAGE_KEYS = (
    "wall_time_ms",
    "cpu_time_ms",
    "peak_memory_bytes",
    "wall_limit_ms",
    "cpu_limit_ms",
    "peak_memory_limit_bytes",
)

if (
    tuple(P136_FORBIDDEN_AUTHORITY_KEYS) != FORBIDDEN_AUTHORITY_KEYS
    or tuple(P137_FORBIDDEN_AUTHORITY_KEYS) != FORBIDDEN_AUTHORITY_KEYS
):
    raise RuntimeError("p138_forbidden_authority_contract_drift")

_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_LABEL_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_FORBIDDEN_TEXT_RE = re.compile(
    r"(?:https?://|api[_-]?key|authorization|bearer|password|secret|"
    r"run[-_ ]command|notify|notification|deliver|remediat|"
    r"production[-_ ]target|staging[-_ ]target|operator[-_ ]replace)",
    re.IGNORECASE,
)
_PUBLISHER_RUNTIME_FIELDS = frozenset(
    {
        "canonical_entry_map",
        "p136_independent_review",
        "p136_release_evidence",
        "p137_release_evidence",
        "p137_final_implementation_review",
        "created_at",
    }
)
_CONFIG_INPUT_FIELDS = frozenset(
    {
        "supervisor_id",
        "config_version",
        "created_at",
        "base_dir_ref_hash",
        "p136_config",
        "p137_config",
        "validated_p136_release_status",
        "validated_p137_release_status",
        "p136_release_evidence_hash",
        "p137_release_evidence_hash",
        "phase_path",
        "ledger_path",
        "checkpoint_path",
        "lease_path",
        "heartbeat_path",
        "readiness_path",
        "termination_dir",
        "publisher_state_path",
        "publisher_intent_path",
        "publisher_lease_path",
        "p136_handoff_bundle_path",
        "limits",
        "forbidden_authority",
    }
)
_CONFIG_FIELDS = frozenset({"schema_version", *_CONFIG_INPUT_FIELDS, "config_hash"})
_LIMIT_FIELDS = frozenset(
    {
        "max_supervisor_cycles",
        "poll_interval_ms",
        "heartbeat_interval_ms",
        "readiness_stale_after_ms",
        "deadman_stale_after_ms",
        "max_consecutive_failures",
        "max_state_bytes",
        "wall_limit_ms",
        "cpu_limit_ms",
        "peak_memory_limit_bytes",
    }
)
_PHASE_FIELDS = frozenset(
    {
        "schema_version",
        "config_hash",
        "cycle_id",
        "phase",
        "previous_phase_hash",
        "previous_p138_ledger_hash",
        "expected_p136_cycle_id",
        "expected_p136_receipt_hash",
        "p136_cycle_outcome_path",
        "starting_p136_checkpoint_hash",
        "resulting_p136_checkpoint_hash",
        "promotion_sequences",
        "promotion_hashes",
        "publisher_state_hash",
        "bundle_sequence",
        "bundle_hash",
        "p137_checkpoint_hash",
        "p137_ledger_hash",
        "classification_hashes",
        "forbidden_authority",
        "runtime_activity",
        "evaluator_activity",
        "written_at",
        "phase_hash",
    }
)
_LEDGER_FIELDS = frozenset(
    {
        "schema_version",
        "config_hash",
        "cycle_sequence",
        "cycle_id",
        "phase_hash",
        "previous_ledger_hash",
        "starting_p136_checkpoint_hash",
        "resulting_p136_checkpoint_hash",
        "publisher_state_hash",
        "bundle_sequence",
        "bundle_hash",
        "p137_checkpoint_hash",
        "p137_ledger_hash",
        "classification_hashes",
        "last_published_promotion_sequence",
        "last_published_promotion_hash",
        "forbidden_authority",
        "runtime_activity",
        "evaluator_activity",
        "finalized_at",
        "ledger_hash",
    }
)
_CHECKPOINT_FIELDS = frozenset(
    {
        "schema_version",
        "config_hash",
        "last_finalized_cycle_sequence",
        "last_finalized_cycle_id",
        "last_p138_ledger_hash",
        "last_published_promotion_sequence",
        "last_published_promotion_hash",
        "updated_at",
        "checkpoint_hash",
    }
)
_PHASES = (
    "cycle_started",
    "p136_completed",
    "handoff_selected",
    "handoff_published",
    "p137_accepted",
    "cycle_finalized",
)
_HASH_NONE = "sha256:" + ("0" * 64)

ObserveCycle = Callable[[Mapping[str, Any]], dict[str, Any]]
RecoverCycle = Callable[..., dict[str, Any]]
PublishBundle = Callable[..., dict[str, Any]]
RunTriage = Callable[..., dict[str, Any]]


class P138SupervisorError(ValueError):
    """Raised when P138 cannot prove a safe local transition."""


class P138StopController:
    """Signal-safe stop flag; handlers perform no I/O."""

    def __init__(self) -> None:
        self.stop_requested = False
        self.signal_name: str | None = None

    def handle_signal(self, signum: int, _frame: FrameType | None) -> None:
        self.stop_requested = True
        self.signal_name = _signal_name(signum)


def zero_forbidden_authority() -> dict[str, int]:
    return {key: 0 for key in FORBIDDEN_AUTHORITY_KEYS}


def _observe_forbidden_authority(
    state: dict[str, Any],
    observed: Mapping[str, Any],
    label: str,
) -> None:
    """Fold a component/durable authority counter into runtime-owned evidence."""

    current = _exact_counter_map(
        state["forbidden_authority"],
        FORBIDDEN_AUTHORITY_KEYS,
        "invalid_runtime_forbidden_authority_schema",
        require_zero=True,
    )
    counters = _exact_counter_map(
        observed,
        FORBIDDEN_AUTHORITY_KEYS,
        label,
        require_zero=True,
    )
    state["forbidden_authority"] = {
        key: current[key] + counters[key] for key in FORBIDDEN_AUTHORITY_KEYS
    }


def zero_runtime_activity(**overrides: int) -> dict[str, int]:
    values = {key: 0 for key in RUNTIME_ACTIVITY_KEYS}
    values.update(overrides)
    return values


def zero_evaluator_activity(**overrides: int) -> dict[str, int]:
    values = {key: 0 for key in EVALUATOR_ACTIVITY_KEYS}
    values.update(overrides)
    return values


def build_observation_triage_supervisor_config(
    data: Mapping[str, Any],
) -> dict[str, Any]:
    raw = _mapping(data, "config")
    unknown = set(raw) - _CONFIG_INPUT_FIELDS
    missing = _CONFIG_INPUT_FIELDS - set(raw)
    if unknown:
        raise P138SupervisorError("unexpected_config_field")
    if missing:
        raise P138SupervisorError("missing_config_field")
    _reject_callable_values(raw, "config")
    p136_config = deepcopy(dict(_mapping(raw.get("p136_config"), "p136_config")))
    p137_config = deepcopy(dict(_mapping(raw.get("p137_config"), "p137_config")))
    try:
        validate_incremental_observer_config(p136_config)
        validate_triage_agent_config(p137_config)
    except (P136ObservationError, P137ContractError) as exc:
        raise P138SupervisorError(f"invalid_component_config:{exc}") from exc
    paths = {
        key: _relative_path(raw.get(key), key)
        for key in (
            "phase_path",
            "ledger_path",
            "checkpoint_path",
            "lease_path",
            "heartbeat_path",
            "readiness_path",
            "termination_dir",
            "publisher_state_path",
            "publisher_intent_path",
            "publisher_lease_path",
            "p136_handoff_bundle_path",
        )
    }
    if paths["p136_handoff_bundle_path"] != FIXED_P136_HANDOFF_PATH:
        raise P138SupervisorError("invalid_fixed_handoff_path")
    if p137_config.get("p136_handoff_bundle_path") != FIXED_P136_HANDOFF_PATH:
        raise P138SupervisorError("p137_fixed_handoff_path_mismatch")
    _validate_all_path_topology(paths, p136_config, p137_config)
    limits = _exact_positive_int_map(raw.get("limits"), _LIMIT_FIELDS, "invalid_limit")
    if limits["deadman_stale_after_ms"] < limits["heartbeat_interval_ms"]:
        raise P138SupervisorError("deadman_limit_below_heartbeat_interval")
    if limits["readiness_stale_after_ms"] < limits["heartbeat_interval_ms"]:
        raise P138SupervisorError("readiness_limit_below_heartbeat_interval")
    p136_status = _text(
        raw.get("validated_p136_release_status"),
        "validated_p136_release_status",
    )
    p137_status = _text(
        raw.get("validated_p137_release_status"),
        "validated_p137_release_status",
    )
    if p136_status != P136_QUALIFIED_STATUS:
        raise P138SupervisorError("invalid_p136_release_status")
    if p137_status != P137_QUALIFIED_STATUS:
        raise P138SupervisorError("invalid_p137_release_status")
    config: dict[str, Any] = {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "supervisor_id": _label(raw.get("supervisor_id"), "supervisor_id"),
        "config_version": _positive_int(raw.get("config_version"), "config_version"),
        "created_at": _timestamp(raw.get("created_at"), "created_at"),
        "base_dir_ref_hash": _hash(raw.get("base_dir_ref_hash"), "base_dir_ref_hash"),
        "p136_config": p136_config,
        "p137_config": p137_config,
        "validated_p136_release_status": p136_status,
        "validated_p137_release_status": p137_status,
        "p136_release_evidence_hash": _hash(
            raw.get("p136_release_evidence_hash"),
            "p136_release_evidence_hash",
        ),
        "p137_release_evidence_hash": _hash(
            raw.get("p137_release_evidence_hash"),
            "p137_release_evidence_hash",
        ),
        **paths,
        "limits": limits,
        "forbidden_authority": _exact_counter_map(
            raw.get("forbidden_authority"),
            FORBIDDEN_AUTHORITY_KEYS,
            "invalid_forbidden_authority_schema",
            require_zero=True,
        ),
    }
    _reject_forbidden_config_text(config)
    config["config_hash"] = stable_hash(config)
    return config


def validate_observation_triage_supervisor_config(
    config: Mapping[str, Any],
) -> None:
    value = _mapping(config, "config")
    if set(value) != _CONFIG_FIELDS or value.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise P138SupervisorError("invalid_config_fields")
    expected = stable_hash(
        {key: item for key, item in value.items() if key != "config_hash"}
    )
    if value.get("config_hash") != expected:
        raise P138SupervisorError("config_hash_invalid")
    rebuilt = build_observation_triage_supervisor_config(
        {key: deepcopy(value[key]) for key in _CONFIG_INPUT_FIELDS}
    )
    if rebuilt != dict(value):
        raise P138SupervisorError("config_semantics_invalid")


def validate_supervisor_phase(
    phase: Mapping[str, Any],
    *,
    config: Mapping[str, Any],
) -> None:
    cfg = _validated_config(config)
    value = _mapping(phase, "phase")
    if set(value) != _PHASE_FIELDS or value.get("schema_version") != PHASE_SCHEMA_VERSION:
        raise P138SupervisorError("invalid_phase_fields")
    if value.get("phase_hash") != stable_hash(
        {key: item for key, item in value.items() if key != "phase_hash"}
    ):
        raise P138SupervisorError("phase_hash_invalid")
    if value.get("config_hash") != cfg["config_hash"]:
        raise P138SupervisorError("phase_config_hash_mismatch")
    phase_name = value.get("phase")
    if phase_name not in _PHASES:
        raise P138SupervisorError("invalid_phase_name")
    cycle_id = _hash(value.get("cycle_id"), "cycle_id")
    if value.get("expected_p136_cycle_id") != cycle_id:
        raise P138SupervisorError("phase_expected_cycle_id_mismatch")
    _hash(value.get("expected_p136_receipt_hash"), "expected_p136_receipt_hash")
    _relative_path(value.get("p136_cycle_outcome_path"), "p136_cycle_outcome_path")
    _hash(value.get("starting_p136_checkpoint_hash"), "starting_p136_checkpoint_hash")
    previous_phase_hash = value.get("previous_phase_hash")
    if previous_phase_hash is not None:
        _hash(previous_phase_hash, "previous_phase_hash")
    elif phase_name not in {"cycle_started", "cycle_finalized"}:
        raise P138SupervisorError("phase_predecessor_missing")
    previous_ledger_hash = value.get("previous_p138_ledger_hash")
    if previous_ledger_hash is not None:
        _hash(previous_ledger_hash, "previous_p138_ledger_hash")
    resulting_hash = value.get("resulting_p136_checkpoint_hash")
    if resulting_hash is not None:
        _hash(resulting_hash, "resulting_p136_checkpoint_hash")
    direct_bootstrap = phase_name == "cycle_finalized" and previous_phase_hash is None
    if phase_name != "cycle_started" and not direct_bootstrap and resulting_hash is None:
        raise P138SupervisorError("phase_resulting_checkpoint_missing")
    sequences = _integer_sequence(value.get("promotion_sequences"), "promotion_sequences")
    hashes = _hash_sequence(value.get("promotion_hashes"), "promotion_hashes")
    if len(sequences) != len(hashes):
        raise P138SupervisorError("phase_promotion_count_mismatch")
    if sequences and sequences != list(range(sequences[0], sequences[-1] + 1)):
        raise P138SupervisorError("phase_promotion_sequence_not_contiguous")
    publisher_values = (
        value.get("publisher_state_hash"),
        value.get("bundle_sequence"),
        value.get("bundle_hash"),
    )
    if any(item is None for item in publisher_values) and any(
        item is not None for item in publisher_values
    ):
        raise P138SupervisorError("phase_publisher_binding_incomplete")
    if publisher_values[0] is not None:
        _hash(publisher_values[0], "publisher_state_hash")
        _positive_int(publisher_values[1], "bundle_sequence")
        _hash(publisher_values[2], "bundle_hash")
    p137_values = (
        value.get("p137_checkpoint_hash"),
        value.get("p137_ledger_hash"),
    )
    if (p137_values[0] is None) != (p137_values[1] is None):
        raise P138SupervisorError("phase_p137_binding_incomplete")
    if p137_values[0] is not None:
        _hash(p137_values[0], "p137_checkpoint_hash")
        _hash(p137_values[1], "p137_ledger_hash")
    classifications = _hash_sequence(
        value.get("classification_hashes"), "classification_hashes"
    )
    if classifications != sorted(set(classifications)):
        raise P138SupervisorError("phase_classification_hashes_not_sorted_unique")
    if p137_values[0] is None and classifications:
        raise P138SupervisorError("phase_classification_without_p137")
    if phase_name in {"handoff_published", "p137_accepted"} and publisher_values[0] is None:
        raise P138SupervisorError("phase_publisher_binding_missing")
    if phase_name == "p137_accepted" and p137_values[0] is None:
        raise P138SupervisorError("phase_p137_binding_missing")
    _exact_counter_map(
        value.get("forbidden_authority"),
        FORBIDDEN_AUTHORITY_KEYS,
        "invalid_phase_forbidden_authority_schema",
        require_zero=True,
    )
    _exact_counter_map(
        value.get("runtime_activity"),
        RUNTIME_ACTIVITY_KEYS,
        "invalid_phase_runtime_activity_schema",
    )
    _exact_counter_map(
        value.get("evaluator_activity"),
        EVALUATOR_ACTIVITY_KEYS,
        "invalid_phase_evaluator_activity_schema",
    )
    _timestamp(value.get("written_at"), "phase_written_at")


def validate_supervisor_ledger(
    ledger: Mapping[str, Any],
    *,
    config: Mapping[str, Any],
    previous: Mapping[str, Any] | None = None,
    _allow_unbound_non_genesis: bool = False,
) -> None:
    cfg = _validated_config(config)
    value = _mapping(ledger, "ledger")
    if set(value) != _LEDGER_FIELDS or value.get("schema_version") != LEDGER_SCHEMA_VERSION:
        raise P138SupervisorError("invalid_ledger_fields")
    if value.get("ledger_hash") != stable_hash(
        {key: item for key, item in value.items() if key != "ledger_hash"}
    ):
        raise P138SupervisorError("ledger_hash_invalid")
    if value.get("config_hash") != cfg["config_hash"]:
        raise P138SupervisorError("ledger_config_hash_mismatch")
    sequence = _positive_int(value.get("cycle_sequence"), "cycle_sequence")
    _hash(value.get("cycle_id"), "cycle_id")
    _hash(value.get("phase_hash"), "phase_hash")
    _hash(value.get("starting_p136_checkpoint_hash"), "starting_p136_checkpoint_hash")
    _hash(value.get("resulting_p136_checkpoint_hash"), "resulting_p136_checkpoint_hash")
    previous_hash = value.get("previous_ledger_hash")
    if previous_hash is not None:
        _hash(previous_hash, "previous_ledger_hash")
    publisher_values = (
        value.get("publisher_state_hash"),
        value.get("bundle_sequence"),
        value.get("bundle_hash"),
    )
    if any(item is None for item in publisher_values) and any(
        item is not None for item in publisher_values
    ):
        raise P138SupervisorError("ledger_publisher_binding_incomplete")
    if publisher_values[0] is not None:
        _hash(publisher_values[0], "publisher_state_hash")
        _positive_int(publisher_values[1], "bundle_sequence")
        _hash(publisher_values[2], "bundle_hash")
    p137_values = (
        value.get("p137_checkpoint_hash"),
        value.get("p137_ledger_hash"),
    )
    if (p137_values[0] is None) != (p137_values[1] is None):
        raise P138SupervisorError("ledger_p137_binding_incomplete")
    if p137_values[0] is not None:
        _hash(p137_values[0], "p137_checkpoint_hash")
        _hash(p137_values[1], "p137_ledger_hash")
    classifications = _hash_sequence(
        value.get("classification_hashes"), "classification_hashes"
    )
    if classifications != sorted(set(classifications)):
        raise P138SupervisorError("ledger_classification_hashes_not_sorted_unique")
    boundary = _nonnegative_int(
        value.get("last_published_promotion_sequence"),
        "last_published_promotion_sequence",
    )
    boundary_hash = value.get("last_published_promotion_hash")
    if boundary == 0:
        if boundary_hash is not None:
            raise P138SupervisorError("ledger_genesis_promotion_hash_not_null")
    else:
        _hash(boundary_hash, "last_published_promotion_hash")
        if publisher_values[0] is None:
            raise P138SupervisorError("ledger_boundary_without_publisher")
    _exact_counter_map(
        value.get("forbidden_authority"),
        FORBIDDEN_AUTHORITY_KEYS,
        "invalid_ledger_forbidden_authority_schema",
        require_zero=True,
    )
    _exact_counter_map(
        value.get("runtime_activity"),
        RUNTIME_ACTIVITY_KEYS,
        "invalid_ledger_runtime_activity_schema",
    )
    _exact_counter_map(
        value.get("evaluator_activity"),
        EVALUATOR_ACTIVITY_KEYS,
        "invalid_ledger_evaluator_activity_schema",
    )
    _timestamp(value.get("finalized_at"), "finalized_at")
    if previous is None:
        if not _allow_unbound_non_genesis and (
            sequence != 1 or previous_hash is not None
        ):
            raise P138SupervisorError("ledger_genesis_lineage_invalid")
    else:
        validate_supervisor_ledger(
            previous,
            config=cfg,
            _allow_unbound_non_genesis=True,
        )
        if (
            sequence != int(previous["cycle_sequence"]) + 1
            or previous_hash != previous["ledger_hash"]
        ):
            raise P138SupervisorError("ledger_cas_predecessor_mismatch")


def _validate_supervisor_checkpoint(
    checkpoint: Mapping[str, Any],
    *,
    config: Mapping[str, Any],
    ledger: Mapping[str, Any],
) -> None:
    value = _mapping(checkpoint, "checkpoint")
    if set(value) != _CHECKPOINT_FIELDS or value.get("schema_version") != CHECKPOINT_SCHEMA_VERSION:
        raise P138SupervisorError("invalid_checkpoint_fields")
    if value.get("checkpoint_hash") != stable_hash(
        {key: item for key, item in value.items() if key != "checkpoint_hash"}
    ):
        raise P138SupervisorError("checkpoint_hash_invalid")
    if (
        value.get("config_hash") != config["config_hash"]
        or value.get("last_finalized_cycle_sequence") != ledger["cycle_sequence"]
        or value.get("last_finalized_cycle_id") != ledger["cycle_id"]
        or value.get("last_p138_ledger_hash") != ledger["ledger_hash"]
        or value.get("last_published_promotion_sequence")
        != ledger["last_published_promotion_sequence"]
        or value.get("last_published_promotion_hash")
        != ledger["last_published_promotion_hash"]
    ):
        raise P138SupervisorError("checkpoint_ledger_mismatch")
    _timestamp(value.get("updated_at"), "checkpoint_updated_at")


def _validated_config(config: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(_mapping(config, "config")))
    validate_observation_triage_supervisor_config(value)
    return value


def _validate_all_path_topology(
    p138_paths: Mapping[str, str],
    p136_config: Mapping[str, Any],
    p137_config: Mapping[str, Any],
) -> None:
    named: list[tuple[str, PurePosixPath]] = []
    for name, path in p138_paths.items():
        named.append((name, PurePosixPath(path)))
    ledger_path = PurePosixPath(p138_paths["ledger_path"])
    named.append(
        (
            "ledger_history_dir",
            ledger_path.parent / f".{ledger_path.name}.history",
        )
    )
    for name in (
        "index_path",
        "checkpoint_path",
        "index_intent_dir",
        "journal_dir",
        "promotion_dir",
        "cycle_outcome_dir",
        "lease_path",
    ):
        named.append((f"p136.{name}", PurePosixPath(_relative_path(p136_config.get(name), f"p136.{name}"))))
    for name in (
        "checkpoint_path",
        "lease_path",
        "journal_dir",
        "incident_dir",
        "hypothesis_dir",
        "request_dir",
        "classification_dir",
        "heartbeat_path",
        "readiness_path",
        "termination_dir",
        "ledger_path",
    ):
        named.append((f"p137.{name}", PurePosixPath(_relative_path(p137_config.get(name), f"p137.{name}"))))
    for index, (left_name, left) in enumerate(named):
        for right_name, right in named[index + 1 :]:
            if left == right or _path_is_ancestor(left, right) or _path_is_ancestor(right, left):
                raise P138SupervisorError(f"paths_overlap:{left_name}:{right_name}")


def _path_is_ancestor(left: PurePosixPath, right: PurePosixPath) -> bool:
    return left.parts == right.parts[: len(left.parts)]


def _reject_forbidden_config_text(config: Mapping[str, Any]) -> None:
    for key in (
        "supervisor_id",
        "phase_path",
        "ledger_path",
        "checkpoint_path",
        "lease_path",
        "heartbeat_path",
        "readiness_path",
        "termination_dir",
        "publisher_state_path",
        "publisher_intent_path",
        "publisher_lease_path",
    ):
        value = str(config[key])
        if _FORBIDDEN_TEXT_RE.search(value):
            raise P138SupervisorError(f"forbidden_config_text:{key}")


def _exact_positive_int_map(
    value: Any,
    keys: frozenset[str],
    error: str,
) -> dict[str, int]:
    mapping = _mapping(value, "limits")
    if set(mapping) != set(keys):
        raise P138SupervisorError(f"{error}:fields")
    result: dict[str, int] = {}
    for key in keys:
        try:
            result[key] = _positive_int(mapping.get(key), key)
        except P138SupervisorError as exc:
            raise P138SupervisorError(f"{error}:{key}") from exc
    return result


def _exact_counter_map(
    value: Any,
    keys: Sequence[str],
    error: str,
    *,
    require_zero: bool = False,
) -> dict[str, int]:
    mapping = _mapping(value, "counter_map")
    if set(mapping) != set(keys):
        raise P138SupervisorError(error)
    result: dict[str, int] = {}
    for key in keys:
        item = mapping.get(key)
        if type(item) is not int or item < 0 or (require_zero and item != 0):
            raise P138SupervisorError(error)
        result[key] = item
    return result


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise P138SupervisorError(f"invalid_{label}_shape")
    return value


def _sequence(value: Any, label: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise P138SupervisorError(f"invalid_{label}_shape")
    return list(value)


def _hash(value: Any, label: str) -> str:
    if not isinstance(value, str) or _HASH_RE.fullmatch(value) is None:
        raise P138SupervisorError(f"invalid_{label}")
    return value


def _optional_hash(value: Any, label: str) -> str | None:
    return None if value is None else _hash(value, label)


def _label(value: Any, label: str) -> str:
    if not isinstance(value, str) or _LABEL_RE.fullmatch(value) is None:
        raise P138SupervisorError(f"invalid_{label}")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 256:
        raise P138SupervisorError(f"invalid_{label}")
    return value


def _positive_int(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise P138SupervisorError(f"invalid_{label}")
    return value


def _nonnegative_int(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise P138SupervisorError(f"invalid_{label}")
    return value


def _integer_sequence(value: Any, label: str) -> list[int]:
    result = _sequence(value, label)
    for item in result:
        _positive_int(item, label)
    return result


def _hash_sequence(value: Any, label: str) -> list[str]:
    return [_hash(item, label) for item in _sequence(value, label)]


def _relative_path(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise P138SupervisorError(f"unsafe_path:{label}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise P138SupervisorError(f"unsafe_path:{label}")
    return path.as_posix()


def _timestamp(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise P138SupervisorError(f"invalid_{label}")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise P138SupervisorError(f"invalid_{label}") from exc
    if parsed.tzinfo is None:
        raise P138SupervisorError(f"invalid_{label}")
    return value


def _parse_timestamp(value: Any, label: str) -> datetime:
    return datetime.fromisoformat(_timestamp(value, label)[:-1] + "+00:00").astimezone(UTC)


def _reject_callable_values(value: Any, label: str) -> None:
    if callable(value):
        raise P138SupervisorError(f"callable_forbidden:{label}")
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_callable_values(item, f"{label}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            _reject_callable_values(item, f"{label}[{index}]")


def _signal_name(signum: int) -> str:
    if signum == signal.SIGINT:
        return "sigint"
    if signum == signal.SIGTERM:
        return "sigterm"
    return f"signal-{signum}"


class _SupervisorLease:
    def __init__(self, root: Path, relative_path: str) -> None:
        self.root = root
        self.relative_path = relative_path
        self.handle: Any = None

    def acquire(self) -> bool:
        path = _secure_runtime_path(
            self.root,
            self.relative_path,
            create_parent=True,
        )
        flags = (
            os.O_RDWR
            | os.O_CREAT
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        try:
            descriptor = os.open(path, flags, 0o600)
        except OSError as exc:
            raise P138SupervisorError("supervisor_lease_invalid") from exc
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            os.close(descriptor)
            raise P138SupervisorError("supervisor_lease_invalid")
        self.handle = os.fdopen(descriptor, "a+", encoding="utf-8")
        try:
            fcntl.flock(
                self.handle.fileno(),
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
        except BlockingIOError:
            self.handle.close()
            self.handle = None
            return False
        return True

    def release(self) -> None:
        if self.handle is not None:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()
            self.handle = None


def _secure_runtime_path(
    root: Path,
    relative_path: str,
    *,
    create_parent: bool,
) -> Path:
    relative = PurePosixPath(_relative_path(relative_path, "runtime_path"))
    try:
        root_info = root.lstat()
    except OSError as exc:
        raise P138SupervisorError("runtime_root_invalid") from exc
    if root.is_symlink() or not stat.S_ISDIR(root_info.st_mode):
        raise P138SupervisorError("runtime_root_symlink_forbidden")
    current = root
    for part in relative.parts[:-1]:
        current = current / part
        if not current.exists():
            if not create_parent:
                continue
            try:
                current.mkdir(mode=0o700)
            except FileExistsError:
                pass
        if current.exists():
            try:
                info = current.lstat()
            except OSError as exc:
                raise P138SupervisorError("runtime_path_invalid") from exc
            if current.is_symlink() or not stat.S_ISDIR(info.st_mode):
                raise P138SupervisorError("runtime_path_symlink_forbidden")
    path = root.joinpath(*relative.parts)
    if path.is_symlink():
        raise P138SupervisorError("runtime_path_symlink_forbidden")
    return path


def _atomic_write_json(
    root: Path,
    relative_path: str,
    value: Mapping[str, Any],
    *,
    maximum: int,
) -> None:
    payload = canonical_json_bytes(value) + b"\n"
    if len(payload) > maximum:
        raise P138SupervisorError("state_byte_budget_exceeded")
    path = _secure_runtime_path(root, relative_path, create_parent=True)
    temp = path.parent / f".{path.name}.{os.getpid()}.{time.monotonic_ns()}.tmp"
    replaced = False
    try:
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        descriptor = os.open(temp, flags, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        replaced = True
        parent_descriptor = os.open(
            path.parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        try:
            os.fsync(parent_descriptor)
        finally:
            os.close(parent_descriptor)
    except OSError as exc:
        error = (
            "state_durability_uncertain"
            if replaced
            else "state_atomic_write_failed"
        )
        raise P138SupervisorError(error) from exc
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def _unlink_state(root: Path, relative_path: str) -> None:
    path = _secure_runtime_path(root, relative_path, create_parent=False)
    try:
        path.unlink()
    except FileNotFoundError:
        return
    descriptor = os.open(
        path.parent,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_json_optional(
    root: Path,
    relative_path: str,
    *,
    maximum: int,
) -> dict[str, Any] | None:
    path = _secure_runtime_path(root, relative_path, create_parent=False)
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise P138SupervisorError("state_read_failed") from exc
    if path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise P138SupervisorError("runtime_path_symlink_forbidden")
    if info.st_size > maximum:
        raise P138SupervisorError("state_byte_budget_exceeded")
    try:
        raw = path.read_bytes()
        if not raw.endswith(b"\n"):
            raise P138SupervisorError("state_json_noncanonical")
        value = json.loads(raw[:-1])
    except (OSError, json.JSONDecodeError) as exc:
        raise P138SupervisorError("state_json_invalid") from exc
    if not isinstance(value, Mapping):
        raise P138SupervisorError("state_json_invalid")
    if canonical_json_bytes(value) + b"\n" != raw:
        raise P138SupervisorError("state_json_noncanonical")
    return dict(value)


def _read_state(
    root: Path,
    relative_path: str,
    *,
    config: Mapping[str, Any],
    activity: dict[str, int],
) -> dict[str, Any] | None:
    activity["supervisor_state_read_count"] += 1
    return _read_json_optional(
        root,
        relative_path,
        maximum=int(config["limits"]["max_state_bytes"]),
    )


def _ledger_history_path(config: Mapping[str, Any], ledger_hash: str) -> str:
    digest = _hash(ledger_hash, "ledger_history_hash").removeprefix("sha256:")
    ledger_path = PurePosixPath(str(config["ledger_path"]))
    history_dir = ledger_path.parent / f".{ledger_path.name}.history"
    return str(history_dir / f"{digest}.json")


def _read_validated_ledger_chain(
    *,
    root: Path,
    config: Mapping[str, Any],
    current: Mapping[str, Any] | None,
    activity: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    if current is None:
        return []
    current_value = deepcopy(dict(_mapping(current, "ledger")))
    validate_supervisor_ledger(
        current_value,
        config=config,
        _allow_unbound_non_genesis=True,
    )
    reverse_chain: list[dict[str, Any]] = []
    cursor = current_value
    while True:
        history_path = _ledger_history_path(config, str(cursor["ledger_hash"]))
        archived = (
            _read_state(
                root,
                history_path,
                config=config,
                activity=activity,
            )
            if activity is not None
            else _read_json_optional(
                root,
                history_path,
                maximum=int(config["limits"]["max_state_bytes"]),
            )
        )
        if archived is None:
            raise P138SupervisorError("ledger_history_missing")
        if archived != cursor:
            raise P138SupervisorError("ledger_history_current_mismatch")
        reverse_chain.append(cursor)
        if int(cursor["cycle_sequence"]) == 1:
            validate_supervisor_ledger(cursor, config=config)
            break
        predecessor_hash = cursor.get("previous_ledger_hash")
        if predecessor_hash is None:
            raise P138SupervisorError("ledger_history_predecessor_missing")
        predecessor_path = _ledger_history_path(config, str(predecessor_hash))
        predecessor = (
            _read_state(
                root,
                predecessor_path,
                config=config,
                activity=activity,
            )
            if activity is not None
            else _read_json_optional(
                root,
                predecessor_path,
                maximum=int(config["limits"]["max_state_bytes"]),
            )
        )
        if predecessor is None:
            raise P138SupervisorError("ledger_history_predecessor_missing")
        validate_supervisor_ledger(cursor, config=config, previous=predecessor)
        cursor = deepcopy(predecessor)
    reverse_chain.reverse()
    return reverse_chain


def _write_ledger_history(
    *,
    root: Path,
    config: Mapping[str, Any],
    ledger: Mapping[str, Any],
) -> None:
    history_path = _ledger_history_path(config, str(ledger["ledger_hash"]))
    existing = _read_json_optional(
        root,
        history_path,
        maximum=int(config["limits"]["max_state_bytes"]),
    )
    if existing is not None:
        if existing != dict(ledger):
            raise P138SupervisorError("ledger_history_conflict")
        return
    _atomic_write_json(
        root,
        history_path,
        ledger,
        maximum=int(config["limits"]["max_state_bytes"]),
    )


def _validate_runtime_inputs(
    *,
    root: Path,
    config: Mapping[str, Any],
    p136_runtime: Mapping[str, Any],
    publisher_inputs: Mapping[str, Any],
    allow_evaluator_callables: bool,
) -> None:
    runtime = _mapping(p136_runtime, "p136_runtime")
    inputs = _mapping(publisher_inputs, "publisher_inputs")
    if set(inputs) != _PUBLISHER_RUNTIME_FIELDS:
        raise P138SupervisorError("invalid_publisher_runtime_fields")
    if not allow_evaluator_callables:
        if runtime.get("evaluator_crash_injector") is not None:
            raise P138SupervisorError("production_evaluator_callable_forbidden")
        _reject_callable_values(inputs, "publisher_inputs")
    runtime_config = _mapping(runtime.get("config"), "p136_runtime_config")
    if dict(runtime_config) != dict(config["p136_config"]):
        raise P138SupervisorError("p136_runtime_config_mismatch")
    runtime_root = runtime.get("base_path")
    if runtime_root is None or Path(runtime_root).resolve() != root.resolve():
        raise P138SupervisorError("p136_runtime_root_mismatch")
    p136_evidence = _mapping(
        inputs.get("p136_release_evidence"),
        "p136_release_evidence",
    )
    p136_review = _mapping(
        inputs.get("p136_independent_review"),
        "p136_independent_review",
    )
    if (
        p136_evidence.get("status") != P136_QUALIFIED_STATUS
        or p136_evidence.get("evidence_hash")
        != config["p136_release_evidence_hash"]
    ):
        raise P138SupervisorError("p136_release_evidence_mismatch")
    try:
        validate_p136_release_evidence(
            p136_evidence,
            independent_review=p136_review,
        )
    except P136ReleaseEvidenceError as exc:
        raise P138SupervisorError(f"invalid_p136_release_evidence:{exc}") from exc
    p137_evidence = _mapping(
        inputs.get("p137_release_evidence"),
        "p137_release_evidence",
    )
    if p137_evidence.get("evidence_hash") != config["p137_release_evidence_hash"]:
        raise P138SupervisorError("p137_release_evidence_mismatch")
    p137_review = _mapping(
        inputs.get("p137_final_implementation_review"),
        "p137_final_implementation_review",
    )
    try:
        validate_p137_release_evidence(
            p137_evidence,
            final_implementation_review=p137_review,
        )
    except P137ReleaseEvidenceError as exc:
        raise P138SupervisorError(f"invalid_p137_release_evidence:{exc}") from exc
    _timestamp(inputs.get("created_at"), "publisher_created_at")


def _component_functions(
    callables: Mapping[str, Any] | None,
) -> tuple[ObserveCycle, RecoverCycle, PublishBundle, RunTriage]:
    defaults: dict[str, Callable[..., dict[str, Any]]] = {
        "observe": observe_one_cycle,
        "recover": recover_cycle_outcome,
        "publish": publish_p136_handoff_bundle,
        "triage": run_p137_runtime_once,
    }
    if callables is None:
        return (
            observe_one_cycle,
            recover_cycle_outcome,
            publish_p136_handoff_bundle,
            run_p137_runtime_once,
        )
    value = _mapping(callables, "component_callables")
    if set(value) - set(defaults):
        raise P138SupervisorError("invalid_evaluator_component_callables")
    for key, item in value.items():
        if not callable(item):
            raise P138SupervisorError(
                f"invalid_evaluator_component_callable:{key}"
            )
        defaults[key] = item
    return (
        defaults["observe"],
        defaults["recover"],
        defaults["publish"],
        defaults["triage"],
    )


def _validate_publisher_state(
    state: Mapping[str, Any],
    *,
    fixed_handoff_path: str,
) -> None:
    if (
        set(state) != PUBLISHER_STATE_FIELDS
        or state.get("schema_version") != PUBLISHER_STATE_SCHEMA_VERSION
    ):
        raise P138SupervisorError("invalid_publisher_state_fields")
    if state.get("state_hash") != stable_hash(
        {key: item for key, item in state.items() if key != "state_hash"}
    ):
        raise P138SupervisorError("publisher_state_hash_invalid")
    _hash(state.get("handoff_chain_root_hash"), "publisher_chain_root_hash")
    _positive_int(state.get("last_bundle_sequence"), "publisher_bundle_sequence")
    _hash(state.get("last_bundle_hash"), "publisher_bundle_hash")
    _hash(
        state.get("last_p136_checkpoint_hash"),
        "publisher_p136_checkpoint_hash",
    )
    if state.get("fixed_handoff_path") != fixed_handoff_path:
        raise P138SupervisorError("publisher_state_fixed_path_mismatch")


def _publisher_snapshot(
    *,
    root: Path,
    config: Mapping[str, Any],
    state: Mapping[str, Any] | None,
    bundle: Mapping[str, Any] | None,
    bundle_bytes: bytes | None,
    p137_checkpoint: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if state is None and bundle is None:
        return None
    if state is None:
        raise P138SupervisorError("publisher_current_bundle_without_state")
    if bundle is None or bundle_bytes is None:
        raise P138SupervisorError("publisher_state_current_bundle_missing")
    _validate_publisher_state(
        state,
        fixed_handoff_path=str(config["p136_handoff_bundle_path"]),
    )
    if (
        state.get("last_bundle_sequence") != bundle.get("bundle_sequence")
        or state.get("last_bundle_hash") != bundle.get("bundle_hash")
        or state.get("last_p136_checkpoint_hash")
        != bundle.get("p136_checkpoint_hash")
        or state.get("handoff_chain_root_hash")
        != bundle.get("handoff_chain_root_hash")
    ):
        raise P138SupervisorError("publisher_state_current_bundle_mismatch")
    if bundle.get("bundle_hash") != stable_hash(
        {key: item for key, item in bundle.items() if key != "bundle_hash"}
    ):
        raise P138SupervisorError("publisher_bundle_hash_invalid")
    if canonical_json_bytes(bundle) != bundle_bytes:
        raise P138SupervisorError("publisher_fixed_bytes_not_canonical")
    if (
        bundle.get("handoff_chain_root_hash")
        != config["p137_config"]["p136_handoff_chain_root_hash"]
    ):
        raise P138SupervisorError("publisher_p137_chain_root_mismatch")
    try:
        validated = validate_p136_handoff_bundle(
            bundle_bytes,
            config=config["p137_config"],
            p137_checkpoint=p137_checkpoint,
        )
    except (P137HandoffError, P137ContractError) as exc:
        raise P138SupervisorError(f"invalid_current_handoff:{exc}") from exc
    if (
        validated.get("bundle_hash") != bundle.get("bundle_hash")
        or validated.get("bundle_sequence") != bundle.get("bundle_sequence")
    ):
        raise P138SupervisorError("publisher_validator_result_mismatch")
    return {
        "state": dict(state),
        "bundle": dict(bundle),
        "bundle_bytes": bundle_bytes,
        "validated": validated,
    }


def _read_publisher_snapshot_locked(
    *,
    root: Path,
    config: Mapping[str, Any],
    activity: dict[str, int],
) -> dict[str, Any]:
    """Read publisher state, intent, and fixed bytes as one serialized tuple."""

    activity["supervisor_state_read_count"] += 3
    try:
        return read_p136_handoff_publication_snapshot(
            base_path=root,
            state_path=str(config["publisher_state_path"]),
            intent_path=str(config["publisher_intent_path"]),
            fixed_handoff_path=str(config["p136_handoff_bundle_path"]),
            lease_path=str(config["publisher_lease_path"]),
        )
    except P137HandoffError as exc:
        if str(exc) == "publisher_lease_unavailable":
            raise P138SupervisorError("publisher:publisher_lease_unavailable") from exc
        raise P138SupervisorError(f"publisher_snapshot:{exc}") from exc


def _validate_p137_checkpoint(
    checkpoint: Mapping[str, Any],
    *,
    config: Mapping[str, Any],
) -> None:
    fields = {
        "schema_version",
        "config_hash",
        "last_accepted_bundle_sequence",
        "last_accepted_bundle_hash",
        "last_accepted_ledger_hash",
        "last_accepted_checkpoint_hash",
        "checkpoint_hash",
    }
    if (
        set(checkpoint) != fields
        or checkpoint.get("schema_version") != P137_CHECKPOINT_SCHEMA_VERSION
    ):
        raise P138SupervisorError("invalid_p137_checkpoint_fields")
    if checkpoint.get("config_hash") != config["config_hash"]:
        raise P138SupervisorError("p137_checkpoint_config_mismatch")
    _positive_int(
        checkpoint.get("last_accepted_bundle_sequence"),
        "p137_checkpoint_bundle_sequence",
    )
    _hash(
        checkpoint.get("last_accepted_bundle_hash"),
        "p137_checkpoint_bundle_hash",
    )
    _hash(
        checkpoint.get("last_accepted_ledger_hash"),
        "p137_checkpoint_ledger_hash",
    )
    _optional_hash(
        checkpoint.get("last_accepted_checkpoint_hash"),
        "p137_previous_checkpoint_hash",
    )
    if checkpoint.get("checkpoint_hash") != stable_hash(
        {key: item for key, item in checkpoint.items() if key != "checkpoint_hash"}
    ):
        raise P138SupervisorError("p137_checkpoint_hash_invalid")


def _validate_p137_durable_membership(
    *,
    root: Path,
    config: Mapping[str, Any],
    checkpoint: Mapping[str, Any] | None,
    ledger: Mapping[str, Any] | None,
) -> list[str]:
    if checkpoint is None and ledger is None:
        return []
    if checkpoint is None or ledger is None:
        raise P138SupervisorError("p137_checkpoint_ledger_incomplete")
    _validate_p137_checkpoint(checkpoint, config=config)
    try:
        validate_investigation_ledger(ledger)
    except P137LedgerError as exc:
        raise P138SupervisorError(f"invalid_p137_ledger:{exc}") from exc
    if (
        ledger.get("config_hash") != config["config_hash"]
        or checkpoint.get("last_accepted_ledger_hash") != ledger.get("ledger_hash")
    ):
        raise P138SupervisorError("p137_checkpoint_ledger_mismatch")
    hashes = sorted(
        set(
            _hash_sequence(
                ledger.get("classification_hashes"),
                "p137_classification_hashes",
            )
        )
    )
    for classification_hash in hashes:
        relative = (
            f"{config['classification_dir']}/"
            f"{classification_hash}.json"
        )
        record = _read_json_optional(
            root,
            relative,
            maximum=int(config["limits"]["max_journal_bytes"]),
        )
        if record is None or record.get("classification_hash") != classification_hash:
            raise P138SupervisorError(
                "p137_ledger_classification_membership_missing"
            )
        if classification_hash != stable_hash(
            {
                key: item
                for key, item in record.items()
                if key != "classification_hash"
            }
        ):
            raise P138SupervisorError("p137_classification_hash_invalid")
    return hashes


def _publisher_acceptance(
    snapshot: Mapping[str, Any] | None,
    checkpoint: Mapping[str, Any] | None,
) -> str:
    if snapshot is None:
        if checkpoint is not None:
            raise P138SupervisorError("p137_checkpoint_without_publisher_bundle")
        return "none"
    bundle = _mapping(snapshot.get("bundle"), "publisher_bundle")
    sequence = int(bundle["bundle_sequence"])
    bundle_hash = str(bundle["bundle_hash"])
    if checkpoint is None:
        if sequence != 1:
            raise P138SupervisorError("p137_bundle_sequence_gap")
        return "pending"
    accepted_sequence = int(checkpoint["last_accepted_bundle_sequence"])
    accepted_hash = str(checkpoint["last_accepted_bundle_hash"])
    if accepted_sequence == sequence:
        if accepted_hash != bundle_hash:
            raise P138SupervisorError("p137_same_sequence_bundle_fork")
        return "accepted"
    if accepted_sequence + 1 == sequence:
        if bundle.get("previous_bundle_hash") != accepted_hash:
            raise P138SupervisorError("p137_bundle_previous_hash_break")
        return "pending"
    raise P138SupervisorError("p137_bundle_sequence_gap")


def _new_phase(
    *,
    config: Mapping[str, Any],
    phase_name: str,
    prior_phase: Mapping[str, Any] | None,
    prior_ledger: Mapping[str, Any] | None,
    cycle_id: str,
    receipt_hash: str,
    outcome_path: str,
    starting_checkpoint_hash: str,
    resulting_checkpoint_hash: str | None,
    promotion_sequences: Sequence[int],
    promotion_hashes: Sequence[str],
    publisher_state_hash: str | None,
    bundle_sequence: int | None,
    bundle_hash: str | None,
    p137_checkpoint_hash: str | None,
    p137_ledger_hash: str | None,
    classification_hashes: Sequence[str],
    forbidden_authority: Mapping[str, int],
    runtime_activity: Mapping[str, int],
    evaluator_activity: Mapping[str, int],
    now: str,
) -> dict[str, Any]:
    phase: dict[str, Any] = {
        "schema_version": PHASE_SCHEMA_VERSION,
        "config_hash": config["config_hash"],
        "cycle_id": cycle_id,
        "phase": phase_name,
        "previous_phase_hash": (
            None if prior_phase is None else prior_phase["phase_hash"]
        ),
        "previous_p138_ledger_hash": (
            None if prior_ledger is None else prior_ledger["ledger_hash"]
        ),
        "expected_p136_cycle_id": cycle_id,
        "expected_p136_receipt_hash": receipt_hash,
        "p136_cycle_outcome_path": outcome_path,
        "starting_p136_checkpoint_hash": starting_checkpoint_hash,
        "resulting_p136_checkpoint_hash": resulting_checkpoint_hash,
        "promotion_sequences": list(promotion_sequences),
        "promotion_hashes": list(promotion_hashes),
        "publisher_state_hash": publisher_state_hash,
        "bundle_sequence": bundle_sequence,
        "bundle_hash": bundle_hash,
        "p137_checkpoint_hash": p137_checkpoint_hash,
        "p137_ledger_hash": p137_ledger_hash,
        "classification_hashes": sorted(set(classification_hashes)),
        "forbidden_authority": dict(
            _exact_counter_map(
                forbidden_authority,
                FORBIDDEN_AUTHORITY_KEYS,
                "invalid_runtime_forbidden_authority_schema",
                require_zero=True,
            )
        ),
        "runtime_activity": dict(runtime_activity),
        "evaluator_activity": dict(evaluator_activity),
        "written_at": _timestamp(now, "phase_written_at"),
    }
    phase["phase_hash"] = stable_hash(phase)
    validate_supervisor_phase(phase, config=config)
    return phase


def _write_phase(
    *,
    root: Path,
    config: Mapping[str, Any],
    state: dict[str, Any],
    phase_name: str,
    prior_ledger: Mapping[str, Any] | None,
    bindings: Mapping[str, Any],
    now: str,
    crash_after_phase: str | None,
) -> dict[str, Any]:
    activity = state["runtime_activity"]
    activity["phase_write_count"] += 1
    activity["fsync_count"] += 2
    phase = _new_phase(
        config=config,
        phase_name=phase_name,
        prior_phase=state.get("phase"),
        prior_ledger=prior_ledger,
        cycle_id=str(bindings["cycle_id"]),
        receipt_hash=str(bindings["receipt_hash"]),
        outcome_path=str(bindings["outcome_path"]),
        starting_checkpoint_hash=str(bindings["starting_checkpoint_hash"]),
        resulting_checkpoint_hash=bindings.get("resulting_checkpoint_hash"),
        promotion_sequences=list(bindings.get("promotion_sequences", [])),
        promotion_hashes=list(bindings.get("promotion_hashes", [])),
        publisher_state_hash=bindings.get("publisher_state_hash"),
        bundle_sequence=bindings.get("bundle_sequence"),
        bundle_hash=bindings.get("bundle_hash"),
        p137_checkpoint_hash=bindings.get("p137_checkpoint_hash"),
        p137_ledger_hash=bindings.get("p137_ledger_hash"),
        classification_hashes=list(bindings.get("classification_hashes", [])),
        forbidden_authority=state["forbidden_authority"],
        runtime_activity=activity,
        evaluator_activity=state["evaluator_activity"],
        now=now,
    )
    _atomic_write_json(
        root,
        str(config["phase_path"]),
        phase,
        maximum=int(config["limits"]["max_state_bytes"]),
    )
    state["phase"] = phase
    state["phase_path"].append(phase_name)
    if crash_after_phase == phase_name and phase_name != "cycle_finalized":
        raise P138SupervisorError(f"crash_after_{phase_name}")
    return phase


def _phase_bindings(phase: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "cycle_id": phase["cycle_id"],
        "receipt_hash": phase["expected_p136_receipt_hash"],
        "outcome_path": phase["p136_cycle_outcome_path"],
        "starting_checkpoint_hash": phase["starting_p136_checkpoint_hash"],
        "resulting_checkpoint_hash": phase["resulting_p136_checkpoint_hash"],
        "promotion_sequences": list(phase["promotion_sequences"]),
        "promotion_hashes": list(phase["promotion_hashes"]),
        "publisher_state_hash": phase["publisher_state_hash"],
        "bundle_sequence": phase["bundle_sequence"],
        "bundle_hash": phase["bundle_hash"],
        "p137_checkpoint_hash": phase["p137_checkpoint_hash"],
        "p137_ledger_hash": phase["p137_ledger_hash"],
        "classification_hashes": list(phase["classification_hashes"]),
    }


def _p136_cycle_bindings(
    *,
    config: Mapping[str, Any],
    starting_checkpoint: Mapping[str, Any],
    receipt_hash: str,
) -> dict[str, Any]:
    starting_hash = _hash(
        starting_checkpoint.get("checkpoint_hash"),
        "starting_p136_checkpoint_hash",
    )
    cycle_id = stable_hash(
        {
            "schema_version": "p136.deterministic_cycle_id.v1",
            "config_hash": config["p136_config"]["config_hash"],
            "checkpoint_hash": starting_hash,
            "receipt_hash": receipt_hash,
        }
    )
    outcome_path = (
        f"{config['p136_config']['cycle_outcome_dir']}/"
        f"{cycle_id.removeprefix('sha256:')}.json"
    )
    return {
        "cycle_id": cycle_id,
        "receipt_hash": receipt_hash,
        "outcome_path": outcome_path,
        "starting_checkpoint_hash": starting_hash,
        "resulting_checkpoint_hash": None,
        "promotion_sequences": [],
        "promotion_hashes": [],
        "publisher_state_hash": None,
        "bundle_sequence": None,
        "bundle_hash": None,
        "p137_checkpoint_hash": None,
        "p137_ledger_hash": None,
        "classification_hashes": [],
    }


def _validate_p136_result(
    result: Mapping[str, Any],
    *,
    config: Mapping[str, Any],
    bindings: Mapping[str, Any],
) -> dict[str, Any]:
    value = deepcopy(dict(_mapping(result, "p136_result")))
    checkpoint = _mapping(
        value.get("advanced_checkpoint"),
        "p136_advanced_checkpoint",
    )
    if checkpoint.get("config_hash") != config["p136_config"]["config_hash"]:
        raise P138SupervisorError("p136_result_config_mismatch")
    _hash(checkpoint.get("checkpoint_hash"), "p136_result_checkpoint_hash")
    _exact_counter_map(
        checkpoint.get("forbidden_authority"),
        FORBIDDEN_AUTHORITY_KEYS,
        "invalid_p136_result_authority",
        require_zero=True,
    )
    outcome = _mapping(value.get("cycle_outcome"), "p136_cycle_outcome")
    try:
        validate_cycle_outcome(outcome, config["p136_config"])
    except P136ObservationError as exc:
        raise P138SupervisorError(f"invalid_p136_cycle_outcome:{exc}") from exc
    if (
        outcome.get("schema_version") != CYCLE_COMPLETION_SCHEMA_VERSION
        or outcome.get("cycle_id") != bindings["cycle_id"]
        or outcome.get("index_read_receipt_hash") != bindings["receipt_hash"]
        or outcome.get("starting_checkpoint_hash")
        != bindings["starting_checkpoint_hash"]
        or outcome.get("resulting_checkpoint_hash") != checkpoint.get("checkpoint_hash")
    ):
        raise P138SupervisorError("p136_cycle_outcome_binding_mismatch")
    promotions = [
        deepcopy(dict(_mapping(item, "promotion")))
        for item in _sequence(value.get("promotion_records"), "promotion_records")
    ]
    if [item.get("promotion_sequence") for item in promotions] != list(
        outcome["promotion_sequences"]
    ) or [item.get("promotion_hash") for item in promotions] != list(
        outcome["promotion_hashes"]
    ):
        raise P138SupervisorError("p136_cycle_outcome_promotion_mismatch")
    checkpoint_promotions = _mapping(
        checkpoint.get("promotion_keys"),
        "p136_checkpoint_promotion_keys",
    )
    for promotion in promotions:
        _exact_counter_map(
            promotion.get("forbidden_authority"),
            FORBIDDEN_AUTHORITY_KEYS,
            "invalid_p136_promotion_authority",
            require_zero=True,
        )
        entry_hash = _hash(promotion.get("entry_hash"), "promotion_entry_hash")
        if checkpoint_promotions.get(entry_hash) != promotion:
            raise P138SupervisorError("p136_checkpoint_promotion_mismatch")
    value["advanced_checkpoint"] = dict(checkpoint)
    value["cycle_outcome"] = dict(outcome)
    value["promotion_records"] = promotions
    return value


def _delta_from_p136_result(
    result: Mapping[str, Any],
    *,
    prior_ledger: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    checkpoint = _mapping(result.get("advanced_checkpoint"), "p136_checkpoint")
    boundary = (
        0
        if prior_ledger is None
        else _nonnegative_int(
            prior_ledger.get("last_published_promotion_sequence"),
            "last_published_promotion_sequence",
        )
    )
    boundary_hash = (
        None
        if prior_ledger is None
        else prior_ledger.get("last_published_promotion_hash")
    )
    if boundary > 0:
        _hash(boundary_hash, "last_published_promotion_hash")
    next_sequence = _positive_int(
        checkpoint.get("next_promotion_sequence"),
        "p136_next_promotion_sequence",
    )
    expected_sequences = list(range(boundary + 1, next_sequence))
    promotions = [
        dict(_mapping(item, "promotion"))
        for item in _sequence(result.get("promotion_records"), "promotion_records")
    ]
    actual_sequences = [
        _positive_int(item.get("promotion_sequence"), "promotion_sequence")
        for item in promotions
    ]
    if actual_sequences != expected_sequences:
        raise P138SupervisorError("promotion_delta_not_exact_contiguous_range")
    if len({str(item["promotion_hash"]) for item in promotions}) != len(promotions):
        raise P138SupervisorError("promotion_delta_duplicate_hash")
    return promotions


def _validate_genesis_bootstrap(
    snapshot: Mapping[str, Any],
) -> tuple[int, str | None, list[int], list[str]]:
    bundle = _mapping(snapshot.get("bundle"), "publisher_bundle")
    if bundle.get("bundle_sequence") != 1 or bundle.get("previous_bundle_hash") is not None:
        raise P138SupervisorError("bootstrap_requires_genesis_bundle")
    checkpoint = _mapping(bundle.get("p136_checkpoint"), "p136_checkpoint")
    next_sequence = _positive_int(
        checkpoint.get("next_promotion_sequence"),
        "p136_next_promotion_sequence",
    )
    wrappers = _mapping(bundle.get("promotion_map"), "promotion_map")
    promotions = [
        _mapping(_mapping(wrapper, "promotion_wrapper").get("promotion"), "promotion")
        for wrapper in wrappers.values()
    ]
    promotions.sort(key=lambda item: int(item.get("promotion_sequence", 0)))
    sequences = [
        _positive_int(item.get("promotion_sequence"), "promotion_sequence")
        for item in promotions
    ]
    expected = list(range(1, next_sequence))
    checkpoint_promotions = _mapping(
        checkpoint.get("promotion_keys"),
        "p136_checkpoint_promotion_keys",
    )
    if sequences != expected or len(wrappers) != len(checkpoint_promotions):
        raise P138SupervisorError("bootstrap_promotion_history_incomplete")
    for promotion in promotions:
        entry_hash = str(promotion.get("entry_hash"))
        if checkpoint_promotions.get(entry_hash) != dict(promotion):
            raise P138SupervisorError("bootstrap_promotion_history_incomplete")
    hashes = [
        _hash(item.get("promotion_hash"), "promotion_hash") for item in promotions
    ]
    return (
        (sequences[-1] if sequences else 0),
        (hashes[-1] if hashes else None),
        sequences,
        hashes,
    )


def _validate_publisher_against_p138_ledger(
    *,
    snapshot: Mapping[str, Any] | None,
    ledger: Mapping[str, Any] | None,
    phase: Mapping[str, Any] | None,
) -> None:
    if ledger is None:
        if snapshot is not None and snapshot["bundle"].get("bundle_sequence") != 1:
            raise P138SupervisorError("bootstrap_requires_genesis_bundle")
        return
    ledger_sequence = ledger.get("bundle_sequence")
    ledger_hash = ledger.get("bundle_hash")
    if snapshot is None:
        if ledger_sequence is not None:
            raise P138SupervisorError("publisher_state_missing_for_p138_ledger")
        return
    bundle = _mapping(snapshot.get("bundle"), "publisher_bundle")
    if (
        bundle.get("bundle_sequence") == ledger_sequence
        and bundle.get("bundle_hash") == ledger_hash
    ):
        return
    if (
        phase is not None
        and phase.get("phase")
        in {
            "handoff_selected",
            "handoff_published",
            "p137_accepted",
            "cycle_finalized",
        }
        and (
            phase.get("phase") == "handoff_selected"
            or phase.get("bundle_sequence") == bundle.get("bundle_sequence")
            and phase.get("bundle_hash") == bundle.get("bundle_hash")
        )
        and (
            ledger_sequence is None
            and bundle.get("bundle_sequence") == 1
            and bundle.get("previous_bundle_hash") is None
            or isinstance(ledger_sequence, int)
            and bundle.get("bundle_sequence") == ledger_sequence + 1
            and bundle.get("previous_bundle_hash") == ledger_hash
        )
    ):
        return
    raise P138SupervisorError("publisher_p138_ledger_lineage_mismatch")


def _checkpoint_from_ledger(
    ledger: Mapping[str, Any],
    *,
    now: str,
) -> dict[str, Any]:
    checkpoint: dict[str, Any] = {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "config_hash": ledger["config_hash"],
        "last_finalized_cycle_sequence": ledger["cycle_sequence"],
        "last_finalized_cycle_id": ledger["cycle_id"],
        "last_p138_ledger_hash": ledger["ledger_hash"],
        "last_published_promotion_sequence": ledger[
            "last_published_promotion_sequence"
        ],
        "last_published_promotion_hash": ledger[
            "last_published_promotion_hash"
        ],
        "updated_at": _timestamp(now, "checkpoint_updated_at"),
    }
    checkpoint["checkpoint_hash"] = stable_hash(checkpoint)
    return checkpoint


def _finalize_cycle(
    *,
    root: Path,
    config: Mapping[str, Any],
    state: dict[str, Any],
    prior_ledger: Mapping[str, Any] | None,
    bindings: dict[str, Any],
    boundary_sequence: int,
    boundary_hash: str | None,
    now: str,
    crash_after_phase: str | None,
) -> dict[str, Any]:
    if state.get("phase") is None or state["phase"].get("phase") != "cycle_finalized":
        _write_phase(
            root=root,
            config=config,
            state=state,
            phase_name="cycle_finalized",
            prior_ledger=prior_ledger,
            bindings=bindings,
            now=now,
            crash_after_phase=crash_after_phase,
        )
    if crash_after_phase == "cycle_finalized":
        raise P138SupervisorError("crash_after_cycle_finalized")
    phase = _mapping(state.get("phase"), "final_phase")
    expected_boundary = _boundary_after_delta(
        prior_ledger=prior_ledger,
        sequences=list(phase["promotion_sequences"]),
        hashes=list(phase["promotion_hashes"]),
    )
    if expected_boundary != (boundary_sequence, boundary_hash):
        raise P138SupervisorError("final_phase_boundary_mismatch")
    return _commit_finalized_phase(
        root=root,
        config=config,
        state=state,
        prior_ledger=prior_ledger,
        crash_after_phase=crash_after_phase,
    )


def _commit_finalized_phase(
    *,
    root: Path,
    config: Mapping[str, Any],
    state: dict[str, Any],
    prior_ledger: Mapping[str, Any] | None,
    crash_after_phase: str | None,
) -> dict[str, Any]:
    phase = _mapping(state.get("phase"), "final_phase")
    if phase.get("phase") != "cycle_finalized":
        raise P138SupervisorError("final_phase_missing")
    ledger, checkpoint = _expected_finalized_records(
        config=config,
        phase=phase,
        prior_ledger=prior_ledger,
    )
    activity = state["runtime_activity"]
    activity["ledger_write_count"] += 2
    activity["fsync_count"] += 6
    _write_ledger_history(root=root, config=config, ledger=ledger)
    _atomic_write_json(
        root,
        str(config["ledger_path"]),
        ledger,
        maximum=int(config["limits"]["max_state_bytes"]),
    )
    state["ledger"] = ledger
    if crash_after_phase == "ledger_durable":
        raise P138SupervisorError("crash_after_ledger_durable")
    _atomic_write_json(
        root,
        str(config["checkpoint_path"]),
        checkpoint,
        maximum=int(config["limits"]["max_state_bytes"]),
    )
    state["checkpoint"] = checkpoint
    return ledger


def _expected_finalized_records(
    *,
    config: Mapping[str, Any],
    phase: Mapping[str, Any],
    prior_ledger: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    boundary_sequence, boundary_hash = _boundary_after_delta(
        prior_ledger=prior_ledger,
        sequences=list(phase["promotion_sequences"]),
        hashes=list(phase["promotion_hashes"]),
    )
    activity = _exact_counter_map(
        phase["runtime_activity"],
        RUNTIME_ACTIVITY_KEYS,
        "invalid_phase_runtime_activity_schema",
    )
    activity["ledger_write_count"] += 2
    activity["fsync_count"] += 6
    ledger: dict[str, Any] = {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "config_hash": config["config_hash"],
        "cycle_sequence": (
            1 if prior_ledger is None else int(prior_ledger["cycle_sequence"]) + 1
        ),
        "cycle_id": phase["cycle_id"],
        "phase_hash": phase["phase_hash"],
        "previous_ledger_hash": (
            None if prior_ledger is None else prior_ledger["ledger_hash"]
        ),
        "starting_p136_checkpoint_hash": phase[
            "starting_p136_checkpoint_hash"
        ],
        "resulting_p136_checkpoint_hash": phase[
            "resulting_p136_checkpoint_hash"
        ],
        "publisher_state_hash": phase.get("publisher_state_hash"),
        "bundle_sequence": phase.get("bundle_sequence"),
        "bundle_hash": phase.get("bundle_hash"),
        "p137_checkpoint_hash": phase.get("p137_checkpoint_hash"),
        "p137_ledger_hash": phase.get("p137_ledger_hash"),
        "classification_hashes": list(phase.get("classification_hashes", [])),
        "last_published_promotion_sequence": boundary_sequence,
        "last_published_promotion_hash": boundary_hash,
        "forbidden_authority": dict(
            _exact_counter_map(
                phase["forbidden_authority"],
                FORBIDDEN_AUTHORITY_KEYS,
                "invalid_phase_forbidden_authority_schema",
                require_zero=True,
            )
        ),
        "runtime_activity": dict(activity),
        "evaluator_activity": dict(
            _exact_counter_map(
                phase["evaluator_activity"],
                EVALUATOR_ACTIVITY_KEYS,
                "invalid_phase_evaluator_activity_schema",
            )
        ),
        "finalized_at": _timestamp(phase["written_at"], "finalized_at"),
    }
    ledger["ledger_hash"] = stable_hash(ledger)
    validate_supervisor_ledger(
        ledger,
        config=config,
        previous=prior_ledger,
    )
    checkpoint = _checkpoint_from_ledger(
        ledger,
        now=str(phase["written_at"]),
    )
    return ledger, checkpoint


def _reconcile_finalized_phase(
    *,
    root: Path,
    config: Mapping[str, Any],
    state: dict[str, Any],
    phase: Mapping[str, Any],
    ledger: Mapping[str, Any] | None,
    checkpoint: Mapping[str, Any] | None,
    ledger_chain: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    phase_predecessor = phase.get("previous_p138_ledger_hash")
    ledger_is_final = (
        ledger is not None
        and ledger.get("phase_hash") == phase.get("phase_hash")
        and ledger.get("cycle_id") == phase.get("cycle_id")
    )
    if ledger_is_final:
        assert ledger is not None
        prior_ledger = ledger_chain[-2] if len(ledger_chain) > 1 else None
        if phase_predecessor != (
            None if prior_ledger is None else prior_ledger.get("ledger_hash")
        ):
            raise P138SupervisorError("finalized_phase_predecessor_mismatch")
        expected_ledger, expected_checkpoint = _expected_finalized_records(
            config=config,
            phase=phase,
            prior_ledger=prior_ledger,
        )
        if dict(ledger) != expected_ledger:
            raise P138SupervisorError("finalized_phase_ledger_content_mismatch")
        if checkpoint is not None:
            try:
                _validate_supervisor_checkpoint(
                    checkpoint,
                    config=config,
                    ledger=expected_ledger,
                )
            except P138SupervisorError:
                if prior_ledger is None:
                    raise
                _validate_supervisor_checkpoint(
                    checkpoint,
                    config=config,
                    ledger=prior_ledger,
                )
            else:
                state["ledger"] = expected_ledger
                state["checkpoint"] = dict(checkpoint)
                return expected_ledger, dict(checkpoint), False
        _atomic_write_json(
            root,
            str(config["checkpoint_path"]),
            expected_checkpoint,
            maximum=int(config["limits"]["max_state_bytes"]),
        )
        state["runtime_activity"]["fsync_count"] += 2
        state["ledger"] = expected_ledger
        state["checkpoint"] = expected_checkpoint
        return expected_ledger, expected_checkpoint, True

    if ledger is None:
        if phase_predecessor is not None:
            raise P138SupervisorError("finalized_phase_predecessor_missing")
        prior_ledger = None
        if checkpoint is not None:
            raise P138SupervisorError("checkpoint_without_ledger")
    else:
        if phase_predecessor != ledger.get("ledger_hash"):
            raise P138SupervisorError("finalized_phase_ledger_membership_mismatch")
        prior_ledger = ledger
        if checkpoint is None:
            raise P138SupervisorError("finalized_predecessor_checkpoint_missing")
        _validate_supervisor_checkpoint(
            checkpoint,
            config=config,
            ledger=prior_ledger,
        )
    committed = _commit_finalized_phase(
        root=root,
        config=config,
        state=state,
        prior_ledger=prior_ledger,
        crash_after_phase=None,
    )
    committed_checkpoint = _mapping(state.get("checkpoint"), "checkpoint")
    return committed, dict(committed_checkpoint), True


def _publisher_bindings(
    *,
    state: Mapping[str, Any],
    bundle: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "publisher_state_hash": _hash(
            state.get("state_hash"), "publisher_state_hash"
        ),
        "bundle_sequence": _positive_int(
            bundle.get("bundle_sequence"), "bundle_sequence"
        ),
        "bundle_hash": _hash(bundle.get("bundle_hash"), "bundle_hash"),
    }


def _p137_bindings(
    *,
    checkpoint: Mapping[str, Any],
    ledger: Mapping[str, Any],
    classification_hashes: Sequence[str],
) -> dict[str, Any]:
    return {
        "p137_checkpoint_hash": _hash(
            checkpoint.get("checkpoint_hash"), "p137_checkpoint_hash"
        ),
        "p137_ledger_hash": _hash(
            ledger.get("ledger_hash"), "p137_ledger_hash"
        ),
        "classification_hashes": sorted(set(classification_hashes)),
    }


def _run_p137_component(
    *,
    triage: RunTriage,
    root: Path,
    config: Mapping[str, Any],
    state: dict[str, Any],
    now: str,
) -> dict[str, Any]:
    state["runtime_activity"]["triage_count"] += 1
    state["component_calls"].append("p137")
    result = triage(
        base_path=root,
        config=config["p137_config"],
        now=now,
    )
    value = deepcopy(dict(_mapping(result, "p137_result")))
    _exact_counter_map(
        value.get("authority_counters"),
        FORBIDDEN_AUTHORITY_KEYS,
        "invalid_p137_result_authority",
        require_zero=True,
    )
    _observe_forbidden_authority(
        state,
        _mapping(value.get("authority_counters"), "p137_authority_counters"),
        "invalid_p137_result_authority",
    )
    if value.get("status") != "ok":
        error = value.get("expected_error") or value.get("termination_reason")
        raise P138SupervisorError(f"p137:{error}")
    checkpoint = _mapping(value.get("checkpoint"), "p137_result_checkpoint")
    ledger = _mapping(value.get("ledger"), "p137_result_ledger")
    classifications = _validate_p137_durable_membership(
        root=root,
        config=config["p137_config"],
        checkpoint=checkpoint,
        ledger=ledger,
    )
    value["checkpoint"] = dict(checkpoint)
    value["ledger"] = dict(ledger)
    value["classification_hashes"] = classifications
    state["p137_result"] = value
    return value


def _publish_component(
    *,
    publish: PublishBundle,
    root: Path,
    config: Mapping[str, Any],
    p136_runtime: Mapping[str, Any],
    publisher_inputs: Mapping[str, Any],
    p136_result: Mapping[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    state["runtime_activity"]["publication_count"] += 1
    state["component_calls"].append("publisher")
    bundle = publish(
        base_path=root,
        state_path=config["publisher_state_path"],
        intent_path=config["publisher_intent_path"],
        fixed_handoff_path=config["p136_handoff_bundle_path"],
        lease_path=config["publisher_lease_path"],
        p136_config=config["p136_config"],
        p136_runtime_authority=p136_runtime["authority"],
        now=p136_runtime["now"],
        p136_checkpoint=p136_result["advanced_checkpoint"],
        canonical_entry_map=publisher_inputs["canonical_entry_map"],
        promotion_records=p136_result["promotion_records"],
        p136_independent_review=publisher_inputs["p136_independent_review"],
        p136_release_evidence=publisher_inputs["p136_release_evidence"],
        created_at=publisher_inputs["created_at"],
    )
    value = deepcopy(dict(_mapping(bundle, "publisher_bundle")))
    state["publisher_bundle"] = value
    return value


def _observation_component(
    *,
    observe: ObserveCycle,
    recover: RecoverCycle,
    p136_runtime: Mapping[str, Any],
    config: Mapping[str, Any],
    bindings: Mapping[str, Any],
    state: dict[str, Any],
    recovering: bool,
) -> dict[str, Any]:
    if recovering:
        state["runtime_activity"]["recovery_count"] += 1
        state["component_calls"].append("p136_recovery")
        try:
            result = recover(
                p136_runtime,
                cycle_id=bindings["cycle_id"],
                index_read_receipt_hash=bindings["receipt_hash"],
            )
        except P136ObservationError as exc:
            if str(exc) != "expected_cycle_outcome_missing":
                raise
            bound_runtime = dict(p136_runtime)
            bound_runtime["expected_cycle_id"] = bindings["cycle_id"]
            bound_runtime["expected_index_read_receipt_hash"] = bindings[
                "receipt_hash"
            ]
            state["runtime_activity"]["observation_count"] += 1
            state["component_calls"].append("p136")
            result = observe(bound_runtime)
    else:
        state["runtime_activity"]["observation_count"] += 1
        state["component_calls"].append("p136")
        result = observe(p136_runtime)
    value = _validate_p136_result(
        result,
        config=config,
        bindings=bindings,
    )
    checkpoint = _mapping(value["advanced_checkpoint"], "p136_advanced_checkpoint")
    _observe_forbidden_authority(
        state,
        _mapping(checkpoint.get("forbidden_authority"), "p136_forbidden_authority"),
        "invalid_p136_result_authority",
    )
    if isinstance(p136_runtime, dict):
        p136_runtime["checkpoint"] = deepcopy(value["advanced_checkpoint"])
    state["p136_result"] = value
    return value


def _result(
    *,
    status: str,
    expected_error: str | None,
    stop_reason: str | None,
    state: Mapping[str, Any],
    resource_usage: Mapping[str, int],
) -> dict[str, Any]:
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "status": status,
        "expected_error": expected_error,
        "stop_reason": stop_reason,
        "phase_path": list(state.get("phase_path", [])),
        "component_calls": list(state.get("component_calls", [])),
        "runtime_activity": dict(state["runtime_activity"]),
        "forbidden_authority": dict(
            _exact_counter_map(
                state["forbidden_authority"],
                FORBIDDEN_AUTHORITY_KEYS,
                "invalid_runtime_forbidden_authority_schema",
                require_zero=True,
            )
        ),
        "evaluator_activity": dict(state["evaluator_activity"]),
        "resource_usage": dict(resource_usage),
        "phase": deepcopy(state.get("phase")),
        "ledger": deepcopy(state.get("ledger")),
        "checkpoint": deepcopy(state.get("checkpoint")),
        "p136_result": deepcopy(state.get("p136_result")),
        "publisher_bundle": deepcopy(state.get("publisher_bundle")),
        "p137_result": deepcopy(state.get("p137_result")),
        "no_work": bool(state.get("no_work", False)),
        "recovered": bool(state.get("recovered", False)),
    }


def _resource_start() -> tuple[float, float, int]:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    cpu = float(usage.ru_utime) + float(usage.ru_stime)
    return time.monotonic(), cpu, _rss_bytes(int(usage.ru_maxrss))


def _resource_end(
    started: tuple[float, float, int],
    config: Mapping[str, Any],
) -> dict[str, int]:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    current_cpu = float(usage.ru_utime) + float(usage.ru_stime)
    current_rss = _rss_bytes(int(usage.ru_maxrss))
    return {
        "wall_time_ms": max(0, int((time.monotonic() - started[0]) * 1000)),
        "cpu_time_ms": max(0, int((current_cpu - started[1]) * 1000)),
        "peak_memory_bytes": max(0, current_rss - started[2]),
        "wall_limit_ms": int(config["limits"]["wall_limit_ms"]),
        "cpu_limit_ms": int(config["limits"]["cpu_limit_ms"]),
        "peak_memory_limit_bytes": int(
            config["limits"]["peak_memory_limit_bytes"]
        ),
    }


def _rss_bytes(value: int) -> int:
    return value if os.uname().sysname == "Darwin" else value * 1024


def _resource_exceeded(value: Mapping[str, int]) -> bool:
    return (
        value["wall_time_ms"] > value["wall_limit_ms"]
        or value["cpu_time_ms"] > value["cpu_limit_ms"]
        or value["peak_memory_bytes"] > value["peak_memory_limit_bytes"]
    )


def run_p138_supervisor_once(
    *,
    base_path: Path,
    config: Mapping[str, Any],
    p136_runtime: Mapping[str, Any],
    publisher_inputs: Mapping[str, Any],
    now: str = "2026-07-14T00:00:00Z",
    stop_controller: P138StopController | None = None,
    component_callables: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one production P138 reconciliation/cycle with module-owned components."""

    if component_callables is not None:
        raise P138SupervisorError("production_component_callables_forbidden")
    return _run_p138_supervisor_once(
        base_path=base_path,
        config=config,
        p136_runtime=p136_runtime,
        publisher_inputs=publisher_inputs,
        now=now,
        stop_controller=stop_controller,
        component_callables=None,
        crash_after_phase=None,
        evaluator_mode=False,
    )


def run_p138_supervisor_once_for_evaluation(
    *,
    base_path: Path,
    config: Mapping[str, Any],
    p136_runtime: Mapping[str, Any],
    publisher_inputs: Mapping[str, Any],
    now: str = "2026-07-14T00:00:00Z",
    stop_controller: P138StopController | None = None,
    component_callables: Mapping[str, Any] | None = None,
    crash_after_phase: str | None = None,
) -> dict[str, Any]:
    """Evaluator-only entrypoint for deterministic crash/component injection."""

    if crash_after_phase is not None and crash_after_phase not in {
        *_PHASES,
        "ledger_durable",
        "p137_committed",
    }:
        raise P138SupervisorError("unknown_evaluator_crash_boundary")
    return _run_p138_supervisor_once(
        base_path=base_path,
        config=config,
        p136_runtime=p136_runtime,
        publisher_inputs=publisher_inputs,
        now=now,
        stop_controller=stop_controller,
        component_callables=component_callables,
        crash_after_phase=crash_after_phase,
        evaluator_mode=True,
    )


def _run_p138_supervisor_once(
    *,
    base_path: Path,
    config: Mapping[str, Any],
    p136_runtime: Mapping[str, Any],
    publisher_inputs: Mapping[str, Any],
    now: str,
    stop_controller: P138StopController | None,
    component_callables: Mapping[str, Any] | None,
    crash_after_phase: str | None,
    evaluator_mode: bool,
) -> dict[str, Any]:
    cfg = _validated_config(config)
    runtime_now = _timestamp(now, "now")
    root = Path(base_path)
    _validate_runtime_inputs(
        root=root,
        config=cfg,
        p136_runtime=p136_runtime,
        publisher_inputs=publisher_inputs,
        allow_evaluator_callables=evaluator_mode,
    )
    observe, recover, publish, triage = _component_functions(component_callables)
    evaluator = zero_evaluator_activity(
        crash_injection_count=int(crash_after_phase is not None)
    )
    state: dict[str, Any] = {
        "runtime_activity": zero_runtime_activity(),
        # This is the runtime-owned capability-use counter. Component and
        # durable-record authority maps are validated into this state; result
        # records copy the observed counter rather than stamping a claim.
        "forbidden_authority": zero_forbidden_authority(),
        "evaluator_activity": evaluator,
        "phase_path": [],
        "component_calls": [],
        "phase": None,
        "ledger": None,
        "checkpoint": None,
        "p136_result": None,
        "publisher_bundle": None,
        "p137_result": None,
        "no_work": False,
        "recovered": False,
    }
    started = _resource_start()
    lease = _SupervisorLease(root, str(cfg["lease_path"]))
    try:
        if not lease.acquire():
            resources = _resource_end(started, cfg)
            return _result(
                status="failed_closed",
                expected_error="supervisor_lease_unavailable",
                stop_reason="lease_conflict",
                state=state,
                resource_usage=resources,
            )
        state["runtime_activity"]["supervisor_lease_acquire_count"] = 1
        if stop_controller is not None and stop_controller.stop_requested:
            resources = _resource_end(started, cfg)
            return _result(
                status="stopped",
                expected_error="signal_at_safe_boundary",
                stop_reason=stop_controller.signal_name or "signal",
                state=state,
                resource_usage=resources,
            )
        return _run_p138_locked(
            root=root,
            config=cfg,
            p136_runtime=p136_runtime,
            publisher_inputs=publisher_inputs,
            now=runtime_now,
            observe=observe,
            recover=recover,
            publish=publish,
            triage=triage,
            crash_after_phase=crash_after_phase,
            state=state,
            started=started,
        )
    except P136ObservationError as exc:
        error = f"p136:{exc}"
        stop_reason = (
            "receipt_exhausted"
            if str(exc) == "index_read_receipt_pool_exhausted"
            else None
        )
        return _result(
            status="failed_closed",
            expected_error=error,
            stop_reason=stop_reason,
            state=state,
            resource_usage=_resource_end(started, cfg),
        )
    except P137HandoffError as exc:
        return _result(
            status="failed_closed",
            expected_error=f"publisher:{exc}",
            stop_reason=None,
            state=state,
            resource_usage=_resource_end(started, cfg),
        )
    except P137RuntimeError as exc:
        return _result(
            status="failed_closed",
            expected_error=f"p137:{exc}",
            stop_reason=None,
            state=state,
            resource_usage=_resource_end(started, cfg),
        )
    except (P138SupervisorError, OSError, ValueError) as exc:
        return _result(
            status="failed_closed",
            expected_error=str(exc),
            stop_reason=None,
            state=state,
            resource_usage=_resource_end(started, cfg),
        )
    finally:
        lease.release()


def _run_p138_locked(
    *,
    root: Path,
    config: Mapping[str, Any],
    p136_runtime: Mapping[str, Any],
    publisher_inputs: Mapping[str, Any],
    now: str,
    observe: ObserveCycle,
    recover: RecoverCycle,
    publish: PublishBundle,
    triage: RunTriage,
    crash_after_phase: str | None,
    state: dict[str, Any],
    started: tuple[float, float, int],
) -> dict[str, Any]:
    activity = state["runtime_activity"]
    activity["reconciliation_count"] += 1
    phase = _read_state(
        root,
        str(config["phase_path"]),
        config=config,
        activity=activity,
    )
    ledger = _read_state(
        root,
        str(config["ledger_path"]),
        config=config,
        activity=activity,
    )
    checkpoint = _read_state(
        root,
        str(config["checkpoint_path"]),
        config=config,
        activity=activity,
    )
    publisher_tuple = _read_publisher_snapshot_locked(
        root=root,
        config=config,
        activity=activity,
    )
    publisher_state = publisher_tuple["state"]
    bundle = publisher_tuple["bundle"]
    bundle_bytes = publisher_tuple["bundle_bytes"]
    p137_checkpoint = _read_state(
        root,
        str(config["p137_config"]["checkpoint_path"]),
        config=config,
        activity=activity,
    )
    p137_ledger = _read_state(
        root,
        str(config["p137_config"]["ledger_path"]),
        config=config,
        activity=activity,
    )
    ledger_chain = _read_validated_ledger_chain(
        root=root,
        config=config,
        current=ledger,
        activity=activity,
    )
    current_reads = activity["supervisor_state_read_count"]
    if phase is not None:
        validate_supervisor_phase(phase, config=config)
        _observe_forbidden_authority(
            state,
            _mapping(phase.get("forbidden_authority"), "phase_forbidden_authority"),
            "invalid_phase_forbidden_authority_schema",
        )
        previous_runtime = _exact_counter_map(
            phase["runtime_activity"],
            RUNTIME_ACTIVITY_KEYS,
            "invalid_phase_runtime_activity_schema",
        )
        previous_evaluator = _exact_counter_map(
            phase["evaluator_activity"],
            EVALUATOR_ACTIVITY_KEYS,
            "invalid_phase_evaluator_activity_schema",
        )
        state["runtime_activity"] = previous_runtime
        state["runtime_activity"]["supervisor_lease_acquire_count"] += 1
        state["runtime_activity"]["supervisor_state_read_count"] += current_reads
        state["runtime_activity"]["reconciliation_count"] += 1
        state["evaluator_activity"] = _sum_counter_maps(
            previous_evaluator,
            state["evaluator_activity"],
            keys=EVALUATOR_ACTIVITY_KEYS,
        )
        activity = state["runtime_activity"]
        state["recovered"] = True
    elif ledger is not None:
        _observe_forbidden_authority(
            state,
            _mapping(ledger.get("forbidden_authority"), "ledger_forbidden_authority"),
            "invalid_ledger_forbidden_authority_schema",
        )
    state["phase"] = phase
    runtime_checkpoint = _mapping(
        p136_runtime.get("checkpoint"),
        "p136_runtime_checkpoint",
    )
    if phase is not None and phase.get("phase") == "cycle_finalized":
        if runtime_checkpoint.get("checkpoint_hash") != phase.get(
            "resulting_p136_checkpoint_hash"
        ):
            raise P138SupervisorError("p136_checkpoint_p138_ledger_mismatch")
    elif phase is None and ledger is not None:
        runtime_checkpoint = _mapping(
            p136_runtime.get("checkpoint"),
            "p136_runtime_checkpoint",
        )
        if runtime_checkpoint.get("checkpoint_hash") != ledger.get(
            "resulting_p136_checkpoint_hash"
        ):
            raise P138SupervisorError("p136_checkpoint_p138_ledger_mismatch")
    if checkpoint is not None and not (
        phase is not None and phase.get("phase") == "cycle_finalized"
    ):
        if ledger is None:
            raise P138SupervisorError("checkpoint_without_ledger")
        _validate_supervisor_checkpoint(
            checkpoint,
            config=config,
            ledger=ledger,
        )
    state["ledger"] = ledger
    state["checkpoint"] = checkpoint
    publisher_intent = publisher_tuple["intent"]
    if publisher_intent is not None:
        recover_p136_handoff_publication(
            base_path=root,
            state_path=str(config["publisher_state_path"]),
            intent_path=str(config["publisher_intent_path"]),
            fixed_handoff_path=str(config["p136_handoff_bundle_path"]),
            lease_path=str(config["publisher_lease_path"]),
        )
        state["component_calls"].append("publisher_recovery")
        activity["recovery_count"] += 1
        publisher_tuple = _read_publisher_snapshot_locked(
            root=root,
            config=config,
            activity=activity,
        )
        publisher_state = publisher_tuple["state"]
        bundle = publisher_tuple["bundle"]
        bundle_bytes = publisher_tuple["bundle_bytes"]
    classifications = _validate_p137_durable_membership(
        root=root,
        config=config["p137_config"],
        checkpoint=p137_checkpoint,
        ledger=p137_ledger,
    )
    snapshot = _publisher_snapshot(
        root=root,
        config=config,
        state=publisher_state,
        bundle=bundle,
        bundle_bytes=bundle_bytes,
        p137_checkpoint=p137_checkpoint,
    )
    _validate_publisher_against_p138_ledger(
        snapshot=snapshot,
        ledger=ledger,
        phase=phase,
    )
    acceptance = _publisher_acceptance(snapshot, p137_checkpoint)
    if (
        phase is not None
        and phase.get("phase") != "cycle_finalized"
        and phase.get("previous_p138_ledger_hash")
        != (None if ledger is None else ledger.get("ledger_hash"))
    ):
        raise P138SupervisorError("phase_p138_ledger_predecessor_mismatch")
    if phase is not None and phase.get("phase") == "cycle_finalized":
        ledger, checkpoint, repaired = _reconcile_finalized_phase(
            root=root,
            config=config,
            state=state,
            phase=phase,
            ledger=ledger,
            checkpoint=checkpoint,
            ledger_chain=ledger_chain,
        )
        _unlink_state(root, str(config["phase_path"]))
        state["runtime_activity"]["fsync_count"] += 1
        phase = None
        state["phase"] = None
        state["ledger"] = ledger
        state["checkpoint"] = checkpoint
        state["phase_path"] = []
        if repaired:
            return _successful_once_result(
                state=state,
                config=config,
                started=started,
            )
        state["runtime_activity"] = zero_runtime_activity(
            supervisor_lease_acquire_count=1,
            supervisor_state_read_count=current_reads,
            reconciliation_count=1,
            fsync_count=1,
        )
        activity = state["runtime_activity"]
    if phase is None:
        if ledger is None and snapshot is None:
            raise P138SupervisorError("bootstrap_publisher_genesis_required")
        if ledger is None and snapshot is not None:
            return _bootstrap_current_bundle(
                root=root,
                config=config,
                state=state,
                snapshot=snapshot,
                acceptance=acceptance,
                p137_checkpoint=p137_checkpoint,
                p137_ledger=p137_ledger,
                classification_hashes=classifications,
                triage=triage,
                now=now,
                crash_after_phase=crash_after_phase,
                started=started,
            )
        if ledger is not None and snapshot is not None:
            if (
                snapshot["bundle"].get("bundle_sequence")
                != ledger.get("bundle_sequence")
                or snapshot["bundle"].get("bundle_hash")
                != ledger.get("bundle_hash")
                or acceptance != "accepted"
                or p137_checkpoint is None
                or p137_ledger is None
            ):
                raise P138SupervisorError("finalized_predecessor_not_reconciled")
        return _start_or_resume_observation(
            root=root,
            config=config,
            p136_runtime=p136_runtime,
            publisher_inputs=publisher_inputs,
            prior_ledger=ledger,
            state=state,
            observe=observe,
            recover=recover,
            publish=publish,
            triage=triage,
            snapshot=snapshot,
            p137_checkpoint=p137_checkpoint,
            p137_ledger=p137_ledger,
            now=now,
            crash_after_phase=crash_after_phase,
            started=started,
        )
    return _resume_phase(
        root=root,
        config=config,
        p136_runtime=p136_runtime,
        publisher_inputs=publisher_inputs,
        prior_ledger=ledger,
        state=state,
        observe=observe,
        recover=recover,
        publish=publish,
        triage=triage,
        snapshot=snapshot,
        acceptance=acceptance,
        p137_checkpoint=p137_checkpoint,
        p137_ledger=p137_ledger,
        classification_hashes=classifications,
        now=now,
        crash_after_phase=crash_after_phase,
        started=started,
    )


def _bootstrap_current_bundle(
    *,
    root: Path,
    config: Mapping[str, Any],
    state: dict[str, Any],
    snapshot: Mapping[str, Any],
    acceptance: str,
    p137_checkpoint: Mapping[str, Any] | None,
    p137_ledger: Mapping[str, Any] | None,
    classification_hashes: Sequence[str],
    triage: RunTriage,
    now: str,
    crash_after_phase: str | None,
    started: tuple[float, float, int],
) -> dict[str, Any]:
    boundary_sequence, boundary_hash, sequences, hashes = _validate_genesis_bootstrap(
        snapshot
    )
    bundle = _mapping(snapshot.get("bundle"), "publisher_bundle")
    publisher_state = _mapping(snapshot.get("state"), "publisher_state")
    if acceptance == "pending":
        p137_result = _run_p137_component(
            triage=triage,
            root=root,
            config=config,
            state=state,
            now=now,
        )
        p137_checkpoint = p137_result["checkpoint"]
        p137_ledger = p137_result["ledger"]
        classification_hashes = p137_result["classification_hashes"]
    elif acceptance != "accepted":
        raise P138SupervisorError("bootstrap_bundle_not_accepted")
    if p137_checkpoint is None or p137_ledger is None:
        raise P138SupervisorError("bootstrap_p137_state_missing")
    state["publisher_bundle"] = dict(bundle)
    state["runtime_activity"]["recovery_count"] += 1
    checkpoint_hash = _hash(
        bundle.get("p136_checkpoint_hash"),
        "bootstrap_p136_checkpoint_hash",
    )
    cycle_id = stable_hash(
        {
            "schema_version": "p138.genesis_bootstrap_cycle.v1",
            "config_hash": config["config_hash"],
            "bundle_hash": bundle["bundle_hash"],
        }
    )
    bindings: dict[str, Any] = {
        "cycle_id": cycle_id,
        "receipt_hash": bundle["bundle_hash"],
        "outcome_path": (
            f"p138/bootstrap/{bundle['bundle_hash'].removeprefix('sha256:')}.json"
        ),
        "starting_checkpoint_hash": checkpoint_hash,
        "resulting_checkpoint_hash": checkpoint_hash,
        "promotion_sequences": sequences,
        "promotion_hashes": hashes,
        **_publisher_bindings(state=publisher_state, bundle=bundle),
        **_p137_bindings(
            checkpoint=p137_checkpoint,
            ledger=p137_ledger,
            classification_hashes=classification_hashes,
        ),
    }
    ledger = _finalize_cycle(
        root=root,
        config=config,
        state=state,
        prior_ledger=None,
        bindings=bindings,
        boundary_sequence=boundary_sequence,
        boundary_hash=boundary_hash,
        now=now,
        crash_after_phase=crash_after_phase,
    )
    state["ledger"] = ledger
    return _successful_once_result(state=state, config=config, started=started)


def _start_or_resume_observation(
    *,
    root: Path,
    config: Mapping[str, Any],
    p136_runtime: Mapping[str, Any],
    publisher_inputs: Mapping[str, Any],
    prior_ledger: Mapping[str, Any] | None,
    state: dict[str, Any],
    observe: ObserveCycle,
    recover: RecoverCycle,
    publish: PublishBundle,
    triage: RunTriage,
    snapshot: Mapping[str, Any] | None,
    p137_checkpoint: Mapping[str, Any] | None,
    p137_ledger: Mapping[str, Any] | None,
    now: str,
    crash_after_phase: str | None,
    started: tuple[float, float, int],
) -> dict[str, Any]:
    starting_checkpoint = _mapping(
        p136_runtime.get("checkpoint"),
        "p136_starting_checkpoint",
    )
    boundary = (
        0
        if prior_ledger is None
        else int(prior_ledger["last_published_promotion_sequence"])
    )
    if int(starting_checkpoint.get("next_promotion_sequence", -1)) != boundary + 1:
        if prior_ledger is None:
            raise P138SupervisorError("unrelated_p136_checkpoint_without_history")
        raise P138SupervisorError("p136_checkpoint_publication_boundary_mismatch")
    prior_promotion_hash = (
        None
        if prior_ledger is None
        else prior_ledger.get("last_published_promotion_hash")
    )
    if (
        boundary > 0
        and starting_checkpoint.get("last_promotion_hash")
        != prior_promotion_hash
    ):
        raise P138SupervisorError("p136_checkpoint_publication_hash_mismatch")
    consumed = set(
        _sequence(
            starting_checkpoint.get("consumed_index_read_receipt_hashes"),
            "consumed_index_read_receipt_hashes",
        )
    )
    receipt_hash = next(
        (
            item
            for item in config["p136_config"]["index_read_receipt_hashes"]
            if item not in consumed
        ),
        None,
    )
    if receipt_hash is None:
        raise P136ObservationError("index_read_receipt_pool_exhausted")
    bindings = _p136_cycle_bindings(
        config=config,
        starting_checkpoint=starting_checkpoint,
        receipt_hash=str(receipt_hash),
    )
    _write_phase(
        root=root,
        config=config,
        state=state,
        phase_name="cycle_started",
        prior_ledger=prior_ledger,
        bindings=bindings,
        now=now,
        crash_after_phase=crash_after_phase,
    )
    p136_result = _observation_component(
        observe=observe,
        recover=recover,
        p136_runtime=p136_runtime,
        config=config,
        bindings=bindings,
        state=state,
        recovering=False,
    )
    return _continue_after_p136(
        root=root,
        config=config,
        p136_runtime=p136_runtime,
        publisher_inputs=publisher_inputs,
        prior_ledger=prior_ledger,
        state=state,
        p136_result=p136_result,
        publish=publish,
        triage=triage,
        snapshot=snapshot,
        p137_checkpoint=p137_checkpoint,
        p137_ledger=p137_ledger,
        now=now,
        crash_after_phase=crash_after_phase,
        started=started,
        phase_already_completed=False,
    )


def _resume_phase(
    *,
    root: Path,
    config: Mapping[str, Any],
    p136_runtime: Mapping[str, Any],
    publisher_inputs: Mapping[str, Any],
    prior_ledger: Mapping[str, Any] | None,
    state: dict[str, Any],
    observe: ObserveCycle,
    recover: RecoverCycle,
    publish: PublishBundle,
    triage: RunTriage,
    snapshot: Mapping[str, Any] | None,
    acceptance: str,
    p137_checkpoint: Mapping[str, Any] | None,
    p137_ledger: Mapping[str, Any] | None,
    classification_hashes: Sequence[str],
    now: str,
    crash_after_phase: str | None,
    started: tuple[float, float, int],
) -> dict[str, Any]:
    phase = _mapping(state.get("phase"), "phase")
    phase_name = str(phase["phase"])
    bindings = _phase_bindings(phase)
    if phase_name in {"cycle_started", "p136_completed", "handoff_selected"}:
        p136_result = _observation_component(
            observe=observe,
            recover=recover,
            p136_runtime=p136_runtime,
            config=config,
            bindings=bindings,
            state=state,
            recovering=True,
        )
        outcome = p136_result["cycle_outcome"]
        if phase_name != "cycle_started" and (
            phase.get("resulting_p136_checkpoint_hash")
            != outcome.get("resulting_checkpoint_hash")
            or list(phase.get("promotion_sequences", []))
            != list(outcome.get("promotion_sequences", []))
            or list(phase.get("promotion_hashes", []))
            != list(outcome.get("promotion_hashes", []))
        ):
            raise P138SupervisorError("phase_p136_outcome_mismatch")
        if phase_name == "cycle_started":
            return _continue_after_p136(
                root=root,
                config=config,
                p136_runtime=p136_runtime,
                publisher_inputs=publisher_inputs,
                prior_ledger=prior_ledger,
                state=state,
                p136_result=p136_result,
                publish=publish,
                triage=triage,
                snapshot=snapshot,
                p137_checkpoint=p137_checkpoint,
                p137_ledger=p137_ledger,
                now=now,
                crash_after_phase=crash_after_phase,
                started=started,
                phase_already_completed=False,
            )
        if phase_name == "p136_completed":
            return _continue_after_p136(
                root=root,
                config=config,
                p136_runtime=p136_runtime,
                publisher_inputs=publisher_inputs,
                prior_ledger=prior_ledger,
                state=state,
                p136_result=p136_result,
                publish=publish,
                triage=triage,
                snapshot=snapshot,
                p137_checkpoint=p137_checkpoint,
                p137_ledger=p137_ledger,
                now=now,
                crash_after_phase=crash_after_phase,
                started=started,
                phase_already_completed=True,
            )
        return _continue_publication(
            root=root,
            config=config,
            p136_runtime=p136_runtime,
            publisher_inputs=publisher_inputs,
            prior_ledger=prior_ledger,
            state=state,
            p136_result=p136_result,
            delta=_delta_from_p136_result(
                p136_result,
                prior_ledger=prior_ledger,
            ),
            publish=publish,
            triage=triage,
            snapshot=snapshot,
            p137_checkpoint=p137_checkpoint,
            p137_ledger=p137_ledger,
            now=now,
            crash_after_phase=crash_after_phase,
            started=started,
            phase_already_published=False,
        )
    if phase_name == "handoff_published":
        if snapshot is None:
            raise P138SupervisorError("handoff_published_bundle_missing")
        return _accept_and_finalize_published(
            root=root,
            config=config,
            prior_ledger=prior_ledger,
            state=state,
            bindings=bindings,
            delta_sequences=list(phase["promotion_sequences"]),
            delta_hashes=list(phase["promotion_hashes"]),
            snapshot=snapshot,
            acceptance=acceptance,
            p137_checkpoint=p137_checkpoint,
            p137_ledger=p137_ledger,
            classification_hashes=classification_hashes,
            triage=triage,
            now=now,
            crash_after_phase=crash_after_phase,
            started=started,
        )
    if phase_name == "p137_accepted":
        if (
            p137_checkpoint is None
            or p137_ledger is None
            or phase.get("p137_checkpoint_hash")
            != p137_checkpoint.get("checkpoint_hash")
            or phase.get("p137_ledger_hash") != p137_ledger.get("ledger_hash")
            or list(phase.get("classification_hashes", []))
            != list(classification_hashes)
        ):
            raise P138SupervisorError("p137_accepted_durable_membership_mismatch")
        boundary_sequence, boundary_hash = _boundary_after_delta(
            prior_ledger=prior_ledger,
            sequences=list(phase["promotion_sequences"]),
            hashes=list(phase["promotion_hashes"]),
        )
        ledger = _finalize_cycle(
            root=root,
            config=config,
            state=state,
            prior_ledger=prior_ledger,
            bindings=bindings,
            boundary_sequence=boundary_sequence,
            boundary_hash=boundary_hash,
            now=now,
            crash_after_phase=crash_after_phase,
        )
        state["ledger"] = ledger
        return _successful_once_result(state=state, config=config, started=started)
    raise P138SupervisorError(f"unsupported_phase_resume:{phase_name}")


def _continue_after_p136(
    *,
    root: Path,
    config: Mapping[str, Any],
    p136_runtime: Mapping[str, Any],
    publisher_inputs: Mapping[str, Any],
    prior_ledger: Mapping[str, Any] | None,
    state: dict[str, Any],
    p136_result: Mapping[str, Any],
    publish: PublishBundle,
    triage: RunTriage,
    snapshot: Mapping[str, Any] | None,
    p137_checkpoint: Mapping[str, Any] | None,
    p137_ledger: Mapping[str, Any] | None,
    now: str,
    crash_after_phase: str | None,
    started: tuple[float, float, int],
    phase_already_completed: bool,
) -> dict[str, Any]:
    outcome = _mapping(p136_result.get("cycle_outcome"), "p136_cycle_outcome")
    bindings = _phase_bindings(_mapping(state.get("phase"), "phase"))
    bindings.update(
        {
            "resulting_checkpoint_hash": outcome["resulting_checkpoint_hash"],
            "promotion_sequences": list(outcome["promotion_sequences"]),
            "promotion_hashes": list(outcome["promotion_hashes"]),
        }
    )
    if not phase_already_completed:
        _write_phase(
            root=root,
            config=config,
            state=state,
            phase_name="p136_completed",
            prior_ledger=prior_ledger,
            bindings=bindings,
            now=now,
            crash_after_phase=crash_after_phase,
        )
    delta = _delta_from_p136_result(p136_result, prior_ledger=prior_ledger)
    if not delta:
        state["no_work"] = True
        state["runtime_activity"]["no_work_count"] += 1
        boundary_sequence = (
            0
            if prior_ledger is None
            else int(prior_ledger["last_published_promotion_sequence"])
        )
        boundary_hash = (
            None
            if prior_ledger is None
            else prior_ledger["last_published_promotion_hash"]
        )
        if prior_ledger is not None:
            bindings.update(
                {
                    "publisher_state_hash": prior_ledger["publisher_state_hash"],
                    "bundle_sequence": prior_ledger["bundle_sequence"],
                    "bundle_hash": prior_ledger["bundle_hash"],
                    "p137_checkpoint_hash": prior_ledger["p137_checkpoint_hash"],
                    "p137_ledger_hash": prior_ledger["p137_ledger_hash"],
                    "classification_hashes": list(
                        prior_ledger["classification_hashes"]
                    ),
                }
            )
        ledger = _finalize_cycle(
            root=root,
            config=config,
            state=state,
            prior_ledger=prior_ledger,
            bindings=bindings,
            boundary_sequence=boundary_sequence,
            boundary_hash=boundary_hash,
            now=now,
            crash_after_phase=crash_after_phase,
        )
        state["ledger"] = ledger
        return _successful_once_result(state=state, config=config, started=started)
    _write_phase(
        root=root,
        config=config,
        state=state,
        phase_name="handoff_selected",
        prior_ledger=prior_ledger,
        bindings=bindings,
        now=now,
        crash_after_phase=crash_after_phase,
    )
    return _continue_publication(
        root=root,
        config=config,
        p136_runtime=p136_runtime,
        publisher_inputs=publisher_inputs,
        prior_ledger=prior_ledger,
        state=state,
        p136_result=p136_result,
        delta=delta,
        publish=publish,
        triage=triage,
        snapshot=snapshot,
        p137_checkpoint=p137_checkpoint,
        p137_ledger=p137_ledger,
        now=now,
        crash_after_phase=crash_after_phase,
        started=started,
        phase_already_published=False,
    )


def _continue_publication(
    *,
    root: Path,
    config: Mapping[str, Any],
    p136_runtime: Mapping[str, Any],
    publisher_inputs: Mapping[str, Any],
    prior_ledger: Mapping[str, Any] | None,
    state: dict[str, Any],
    p136_result: Mapping[str, Any],
    delta: Sequence[Mapping[str, Any]],
    publish: PublishBundle,
    triage: RunTriage,
    snapshot: Mapping[str, Any] | None,
    p137_checkpoint: Mapping[str, Any] | None,
    p137_ledger: Mapping[str, Any] | None,
    now: str,
    crash_after_phase: str | None,
    started: tuple[float, float, int],
    phase_already_published: bool,
) -> dict[str, Any]:
    del phase_already_published
    bindings = _phase_bindings(_mapping(state.get("phase"), "phase"))
    delta_sequences = [
        _positive_int(item.get("promotion_sequence"), "promotion_sequence")
        for item in delta
    ]
    delta_hashes = [
        _hash(item.get("promotion_hash"), "promotion_hash") for item in delta
    ]
    if snapshot is None or not _snapshot_is_unfinalized_successor(
        snapshot=snapshot,
        prior_ledger=prior_ledger,
    ):
        _publish_component(
            publish=publish,
            root=root,
            config=config,
            p136_runtime=p136_runtime,
            publisher_inputs=publisher_inputs,
            p136_result=p136_result,
            state=state,
        )
        publisher_tuple = _read_publisher_snapshot_locked(
            root=root,
            config=config,
            activity=state["runtime_activity"],
        )
        publisher_state = publisher_tuple["state"]
        bundle = publisher_tuple["bundle"]
        bundle_bytes = publisher_tuple["bundle_bytes"]
        snapshot = _publisher_snapshot(
            root=root,
            config=config,
            state=publisher_state,
            bundle=bundle,
            bundle_bytes=bundle_bytes,
            p137_checkpoint=p137_checkpoint,
        )
    if snapshot is None:
        raise P138SupervisorError("publication_durable_snapshot_missing")
    _validate_snapshot_for_delta(
        snapshot=snapshot,
        p136_result=p136_result,
        sequences=delta_sequences,
        hashes=delta_hashes,
    )
    durable_bundle = _mapping(snapshot.get("bundle"), "publisher_bundle")
    durable_publisher_state = _mapping(
        snapshot.get("state"),
        "publisher_state",
    )
    state["publisher_bundle"] = dict(durable_bundle)
    bindings.update(
        {
            "promotion_sequences": delta_sequences,
            "promotion_hashes": delta_hashes,
            **_publisher_bindings(
                state=durable_publisher_state,
                bundle=durable_bundle,
            ),
        }
    )
    _write_phase(
        root=root,
        config=config,
        state=state,
        phase_name="handoff_published",
        prior_ledger=prior_ledger,
        bindings=bindings,
        now=now,
        crash_after_phase=crash_after_phase,
    )
    acceptance = _publisher_acceptance(snapshot, p137_checkpoint)
    classifications = _validate_p137_durable_membership(
        root=root,
        config=config["p137_config"],
        checkpoint=p137_checkpoint,
        ledger=p137_ledger,
    )
    return _accept_and_finalize_published(
        root=root,
        config=config,
        prior_ledger=prior_ledger,
        state=state,
        bindings=bindings,
        delta_sequences=delta_sequences,
        delta_hashes=delta_hashes,
        snapshot=snapshot,
        acceptance=acceptance,
        p137_checkpoint=p137_checkpoint,
        p137_ledger=p137_ledger,
        classification_hashes=classifications,
        triage=triage,
        now=now,
        crash_after_phase=crash_after_phase,
        started=started,
    )


def _snapshot_is_unfinalized_successor(
    *,
    snapshot: Mapping[str, Any],
    prior_ledger: Mapping[str, Any] | None,
) -> bool:
    bundle = _mapping(snapshot.get("bundle"), "publisher_bundle")
    if prior_ledger is None:
        return (
            bundle.get("bundle_sequence") == 1
            and bundle.get("previous_bundle_hash") is None
        )
    prior_sequence = prior_ledger.get("bundle_sequence")
    prior_hash = prior_ledger.get("bundle_hash")
    if prior_sequence is None:
        return (
            bundle.get("bundle_sequence") == 1
            and bundle.get("previous_bundle_hash") is None
        )
    return (
        bundle.get("bundle_sequence") == int(prior_sequence) + 1
        and bundle.get("previous_bundle_hash") == prior_hash
    )


def _validate_snapshot_for_delta(
    *,
    snapshot: Mapping[str, Any],
    p136_result: Mapping[str, Any],
    sequences: Sequence[int],
    hashes: Sequence[str],
) -> None:
    bundle = _mapping(snapshot.get("bundle"), "publisher_bundle")
    checkpoint = _mapping(
        p136_result.get("advanced_checkpoint"),
        "p136_advanced_checkpoint",
    )
    if bundle.get("p136_checkpoint_hash") != checkpoint.get("checkpoint_hash"):
        raise P138SupervisorError("published_p136_checkpoint_mismatch")
    promotion_map = _mapping(bundle.get("promotion_map"), "promotion_map")
    promotions = [
        _mapping(_mapping(wrapper, "promotion_wrapper").get("promotion"), "promotion")
        for wrapper in promotion_map.values()
    ]
    promotions.sort(key=lambda item: int(item.get("promotion_sequence", 0)))
    if [item.get("promotion_sequence") for item in promotions] != list(sequences):
        raise P138SupervisorError("published_promotion_sequence_mismatch")
    if [item.get("promotion_hash") for item in promotions] != list(hashes):
        raise P138SupervisorError("published_promotion_hash_mismatch")


def _accept_and_finalize_published(
    *,
    root: Path,
    config: Mapping[str, Any],
    prior_ledger: Mapping[str, Any] | None,
    state: dict[str, Any],
    bindings: dict[str, Any],
    delta_sequences: Sequence[int],
    delta_hashes: Sequence[str],
    snapshot: Mapping[str, Any],
    acceptance: str,
    p137_checkpoint: Mapping[str, Any] | None,
    p137_ledger: Mapping[str, Any] | None,
    classification_hashes: Sequence[str],
    triage: RunTriage,
    now: str,
    crash_after_phase: str | None,
    started: tuple[float, float, int],
) -> dict[str, Any]:
    bundle = _mapping(snapshot.get("bundle"), "publisher_bundle")
    publisher_state = _mapping(snapshot.get("state"), "publisher_state")
    durable_bindings = _publisher_bindings(
        state=publisher_state,
        bundle=bundle,
    )
    if any(bindings.get(key) != value for key, value in durable_bindings.items()):
        raise P138SupervisorError("handoff_phase_publisher_binding_mismatch")
    if list(bindings.get("promotion_sequences", [])) != list(delta_sequences):
        raise P138SupervisorError("handoff_phase_promotion_sequence_mismatch")
    if list(bindings.get("promotion_hashes", [])) != list(delta_hashes):
        raise P138SupervisorError("handoff_phase_promotion_hash_mismatch")
    if acceptance == "pending":
        result = _run_p137_component(
            triage=triage,
            root=root,
            config=config,
            state=state,
            now=now,
        )
        p137_checkpoint = result["checkpoint"]
        p137_ledger = result["ledger"]
        classification_hashes = result["classification_hashes"]
        if crash_after_phase == "p137_committed":
            raise P138SupervisorError("crash_after_p137_committed")
    elif acceptance != "accepted":
        raise P138SupervisorError("published_bundle_not_pending_or_accepted")
    if p137_checkpoint is None or p137_ledger is None:
        raise P138SupervisorError("p137_durable_acceptance_missing")
    if (
        p137_checkpoint.get("last_accepted_bundle_sequence")
        != bundle.get("bundle_sequence")
        or p137_checkpoint.get("last_accepted_bundle_hash")
        != bundle.get("bundle_hash")
    ):
        raise P138SupervisorError("p137_accepted_bundle_mismatch")
    bindings.update(
        _p137_bindings(
            checkpoint=p137_checkpoint,
            ledger=p137_ledger,
            classification_hashes=classification_hashes,
        )
    )
    _write_phase(
        root=root,
        config=config,
        state=state,
        phase_name="p137_accepted",
        prior_ledger=prior_ledger,
        bindings=bindings,
        now=now,
        crash_after_phase=crash_after_phase,
    )
    boundary_sequence, boundary_hash = _boundary_after_delta(
        prior_ledger=prior_ledger,
        sequences=delta_sequences,
        hashes=delta_hashes,
    )
    ledger = _finalize_cycle(
        root=root,
        config=config,
        state=state,
        prior_ledger=prior_ledger,
        bindings=bindings,
        boundary_sequence=boundary_sequence,
        boundary_hash=boundary_hash,
        now=now,
        crash_after_phase=crash_after_phase,
    )
    state["ledger"] = ledger
    return _successful_once_result(state=state, config=config, started=started)


def _boundary_after_delta(
    *,
    prior_ledger: Mapping[str, Any] | None,
    sequences: Sequence[int],
    hashes: Sequence[str],
) -> tuple[int, str | None]:
    prior_sequence = (
        0
        if prior_ledger is None
        else _nonnegative_int(
            prior_ledger.get("last_published_promotion_sequence"),
            "last_published_promotion_sequence",
        )
    )
    prior_hash = (
        None
        if prior_ledger is None
        else prior_ledger.get("last_published_promotion_hash")
    )
    if len(sequences) != len(hashes):
        raise P138SupervisorError("promotion_delta_count_mismatch")
    if not sequences:
        return prior_sequence, prior_hash
    if list(sequences) != list(range(prior_sequence + 1, sequences[-1] + 1)):
        raise P138SupervisorError("promotion_delta_not_exact_contiguous_range")
    for item in hashes:
        _hash(item, "promotion_hash")
    return int(sequences[-1]), str(hashes[-1])


def _successful_once_result(
    *,
    state: Mapping[str, Any],
    config: Mapping[str, Any],
    started: tuple[float, float, int],
) -> dict[str, Any]:
    resources = _resource_end(started, config)
    if _resource_exceeded(resources):
        return _result(
            status="failed_closed",
            expected_error="resource_exhausted",
            stop_reason="resource_exhausted",
            state=state,
            resource_usage=resources,
        )
    return _result(
        status="ok",
        expected_error=None,
        stop_reason=None,
        state=state,
        resource_usage=resources,
    )


def _sum_counter_maps(
    left: Mapping[str, int],
    right: Mapping[str, int],
    *,
    keys: Sequence[str],
) -> dict[str, int]:
    return {key: int(left.get(key, 0)) + int(right.get(key, 0)) for key in keys}


def _control_record_hash(record: Mapping[str, Any], field: str) -> str:
    return stable_hash({key: item for key, item in record.items() if key != field})


def _heartbeat_record(
    *,
    config: Mapping[str, Any],
    cycle_sequence: int,
    monotonic_elapsed_ms: int,
    ledger_hash: str,
    readiness_state: str,
    now: str,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "schema_version": HEARTBEAT_SCHEMA_VERSION,
        "config_hash": config["config_hash"],
        "cycle_sequence": cycle_sequence,
        "monotonic_elapsed_ms": monotonic_elapsed_ms,
        "last_valid_ledger_hash": ledger_hash,
        "readiness_state": readiness_state,
        "written_at": _timestamp(now, "heartbeat_written_at"),
    }
    record["heartbeat_hash"] = stable_hash(record)
    return record


def _readiness_record(
    *,
    config: Mapping[str, Any],
    status: str,
    reason: str,
    ledger_hash: str,
    now: str,
) -> dict[str, Any]:
    if status not in {"ready", "stopped"}:
        raise P138SupervisorError("invalid_readiness_status")
    record: dict[str, Any] = {
        "schema_version": READINESS_SCHEMA_VERSION,
        "config_hash": config["config_hash"],
        "status": status,
        "reason": reason,
        "last_valid_ledger_hash": ledger_hash,
        "written_at": _timestamp(now, "readiness_written_at"),
    }
    record["readiness_hash"] = stable_hash(record)
    return record


def _termination_record(
    *,
    config: Mapping[str, Any],
    stop_reason: str,
    cycles_completed: int,
    ledger_hash: str,
    forbidden_authority: Mapping[str, int],
    now: str,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "schema_version": TERMINATION_SCHEMA_VERSION,
        "config_hash": config["config_hash"],
        "stop_reason": _text(stop_reason, "stop_reason"),
        "safe_boundary": "between_supervisor_cycles",
        "last_valid_ledger_hash": ledger_hash,
        "cycles_completed": cycles_completed,
        "forbidden_authority": dict(
            _exact_counter_map(
                forbidden_authority,
                FORBIDDEN_AUTHORITY_KEYS,
                "invalid_loop_forbidden_authority_schema",
                require_zero=True,
            )
        ),
        "written_at": _timestamp(now, "termination_written_at"),
    }
    record["termination_hash"] = stable_hash(record)
    return record


def _validate_existing_control_record(
    record: Mapping[str, Any],
    *,
    config: Mapping[str, Any],
    kind: str,
) -> datetime:
    contracts = {
        "heartbeat": (
            HEARTBEAT_SCHEMA_VERSION,
            "heartbeat_hash",
            {
                "schema_version",
                "config_hash",
                "cycle_sequence",
                "monotonic_elapsed_ms",
                "last_valid_ledger_hash",
                "readiness_state",
                "written_at",
                "heartbeat_hash",
            },
        ),
        "readiness": (
            READINESS_SCHEMA_VERSION,
            "readiness_hash",
            {
                "schema_version",
                "config_hash",
                "status",
                "reason",
                "last_valid_ledger_hash",
                "written_at",
                "readiness_hash",
            },
        ),
    }
    schema, hash_field, fields = contracts[kind]
    if (
        set(record) != fields
        or record.get("schema_version") != schema
        or record.get("config_hash") != config["config_hash"]
        or record.get(hash_field) != _control_record_hash(record, hash_field)
    ):
        raise P138SupervisorError(f"invalid_{kind}_record")
    _hash(record.get("last_valid_ledger_hash"), f"{kind}_ledger_hash")
    return _parse_timestamp(record.get("written_at"), f"{kind}_written_at")


def _prior_control_stop_reason(
    *,
    root: Path,
    config: Mapping[str, Any],
    now: str,
    ledger_hash: str,
) -> str | None:
    readiness = _read_json_optional(
        root,
        str(config["readiness_path"]),
        maximum=int(config["limits"]["max_state_bytes"]),
    )
    heartbeat = _read_json_optional(
        root,
        str(config["heartbeat_path"]),
        maximum=int(config["limits"]["max_state_bytes"]),
    )
    current = _parse_timestamp(now, "now")
    if readiness is not None:
        written = _validate_existing_control_record(
            readiness,
            config=config,
            kind="readiness",
        )
        if readiness.get("last_valid_ledger_hash") != ledger_hash:
            raise P138SupervisorError("readiness_ledger_binding_mismatch")
        elapsed = int((current - written).total_seconds() * 1000)
        if elapsed > int(config["limits"]["readiness_stale_after_ms"]):
            return "readiness_stale"
    if heartbeat is not None:
        written = _validate_existing_control_record(
            heartbeat,
            config=config,
            kind="heartbeat",
        )
        if heartbeat.get("last_valid_ledger_hash") != ledger_hash:
            raise P138SupervisorError("heartbeat_ledger_binding_mismatch")
        elapsed = int((current - written).total_seconds() * 1000)
        if elapsed > int(config["limits"]["deadman_stale_after_ms"]):
            return "deadman_stale"
    return None


def _initial_loop_state(
    *,
    root: Path,
    config: Mapping[str, Any],
    activity: dict[str, int],
    now: str,
) -> tuple[str, str | None]:
    lease = _SupervisorLease(root, str(config["lease_path"]))
    if not lease.acquire():
        raise P138SupervisorError("supervisor_lease_unavailable")
    try:
        activity["supervisor_lease_acquire_count"] += 1
        ledger = _read_state(
            root,
            str(config["ledger_path"]),
            config=config,
            activity=activity,
        )
        _read_validated_ledger_chain(
            root=root,
            config=config,
            current=ledger,
            activity=activity,
        )
        ledger_hash = (
            _HASH_NONE
            if ledger is None
            else _hash(ledger.get("ledger_hash"), "last_valid_ledger_hash")
        )
        return ledger_hash, _prior_control_stop_reason(
            root=root,
            config=config,
            now=now,
            ledger_hash=ledger_hash,
        )
    finally:
        lease.release()


def _write_loop_control(
    *,
    root: Path,
    config: Mapping[str, Any],
    activity: dict[str, int],
    cycle_sequence: int,
    elapsed_ms: int,
    readiness_status: str,
    reason: str,
    ledger_hash: str,
    forbidden_authority: Mapping[str, int],
    now: str,
    terminate: bool,
    write_heartbeat: bool,
) -> dict[str, Any] | None:
    lease = _SupervisorLease(root, str(config["lease_path"]))
    if not lease.acquire():
        raise P138SupervisorError("supervisor_lease_unavailable")
    try:
        activity["supervisor_lease_acquire_count"] += 1
        durable_ledger = _read_state(
            root,
            str(config["ledger_path"]),
            config=config,
            activity=activity,
        )
        _read_validated_ledger_chain(
            root=root,
            config=config,
            current=durable_ledger,
            activity=activity,
        )
        durable_hash = (
            _HASH_NONE
            if durable_ledger is None
            else _hash(
                durable_ledger.get("ledger_hash"),
                "durable_control_ledger_hash",
            )
        )
        if ledger_hash != durable_hash:
            raise P138SupervisorError("loop_control_ledger_binding_mismatch")
        readiness = _readiness_record(
            config=config,
            status=readiness_status,
            reason=reason,
            ledger_hash=ledger_hash,
            now=now,
        )
        if write_heartbeat:
            heartbeat = _heartbeat_record(
                config=config,
                cycle_sequence=cycle_sequence,
                monotonic_elapsed_ms=elapsed_ms,
                ledger_hash=ledger_hash,
                readiness_state=readiness_status,
                now=now,
            )
            _atomic_write_json(
                root,
                str(config["heartbeat_path"]),
                heartbeat,
                maximum=int(config["limits"]["max_state_bytes"]),
            )
            activity["heartbeat_write_count"] += 1
            activity["fsync_count"] += 2
        _atomic_write_json(
            root,
            str(config["readiness_path"]),
            readiness,
            maximum=int(config["limits"]["max_state_bytes"]),
        )
        activity["readiness_write_count"] += 1
        activity["fsync_count"] += 2
        if not terminate:
            return None
        termination = _termination_record(
            config=config,
            stop_reason=reason,
            cycles_completed=cycle_sequence,
            ledger_hash=ledger_hash,
            forbidden_authority=forbidden_authority,
            now=now,
        )
        termination_path = (
            f"{config['termination_dir']}/"
            f"{termination['termination_hash'].removeprefix('sha256:')}.json"
        )
        _atomic_write_json(
            root,
            termination_path,
            termination,
            maximum=int(config["limits"]["max_state_bytes"]),
        )
        activity["termination_write_count"] += 1
        activity["fsync_count"] += 2
        return termination
    finally:
        lease.release()


def _loop_result(
    *,
    stop_reason: str,
    cycles_completed: int,
    maximum: int,
    last_result: Mapping[str, Any] | None,
    runtime_activity: Mapping[str, int],
    forbidden_authority: Mapping[str, int],
    evaluator_activity: Mapping[str, int],
    termination: Mapping[str, Any] | None,
) -> dict[str, Any]:
    return {
        "schema_version": LOOP_RESULT_SCHEMA_VERSION,
        "status": "stopped",
        "stop_reason": stop_reason,
        "cycles_completed": cycles_completed,
        "max_supervisor_cycles": maximum,
        "last_result": deepcopy(last_result),
        "runtime_activity": dict(runtime_activity),
        "forbidden_authority": dict(
            _exact_counter_map(
                forbidden_authority,
                FORBIDDEN_AUTHORITY_KEYS,
                "invalid_loop_forbidden_authority_schema",
                require_zero=True,
            )
        ),
        "evaluator_activity": dict(evaluator_activity),
        "termination": deepcopy(termination),
    }


def run_p138_supervisor_loop(
    *,
    base_path: Path,
    config: Mapping[str, Any],
    p136_runtime: Mapping[str, Any],
    publisher_inputs: Mapping[str, Any],
    stop_controller: P138StopController | None = None,
) -> dict[str, Any]:
    """Run the finite production supervisor loop and stop at a safe boundary."""

    return _run_p138_supervisor_loop(
        base_path=base_path,
        config=config,
        p136_runtime=p136_runtime,
        publisher_inputs=publisher_inputs,
        now_values=None,
        stop_controller=stop_controller,
        monotonic=time.monotonic,
        sleep=time.sleep,
        component_callables=None,
        evaluator_mode=False,
    )


def run_p138_supervisor_loop_for_evaluation(
    *,
    base_path: Path,
    config: Mapping[str, Any],
    p136_runtime: Mapping[str, Any],
    publisher_inputs: Mapping[str, Any],
    now_values: Sequence[str] | None = None,
    stop_controller: P138StopController | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    component_callables: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluator-only loop with deterministic clocks, sleeps, and components."""

    return _run_p138_supervisor_loop(
        base_path=base_path,
        config=config,
        p136_runtime=p136_runtime,
        publisher_inputs=publisher_inputs,
        now_values=now_values,
        stop_controller=stop_controller,
        monotonic=monotonic,
        sleep=sleep,
        component_callables=component_callables,
        evaluator_mode=True,
    )


def _run_p138_supervisor_loop(
    *,
    base_path: Path,
    config: Mapping[str, Any],
    p136_runtime: Mapping[str, Any],
    publisher_inputs: Mapping[str, Any],
    now_values: Sequence[str] | None,
    stop_controller: P138StopController | None,
    monotonic: Callable[[], float],
    sleep: Callable[[float], None],
    component_callables: Mapping[str, Any] | None,
    evaluator_mode: bool,
) -> dict[str, Any]:
    cfg = _validated_config(config)
    root = Path(base_path)
    _validate_runtime_inputs(
        root=root,
        config=cfg,
        p136_runtime=p136_runtime,
        publisher_inputs=publisher_inputs,
        allow_evaluator_callables=evaluator_mode,
    )
    if component_callables is not None:
        _component_functions(component_callables)
    maximum = int(cfg["limits"]["max_supervisor_cycles"])
    supplied_times = None if now_values is None else list(now_values)
    if supplied_times is not None and len(supplied_times) < maximum:
        maximum = len(supplied_times)
    if maximum <= 0:
        raise P138SupervisorError("empty_loop_schedule")
    first_now = (
        _utc_timestamp()
        if supplied_times is None
        else _timestamp(supplied_times[0], "now")
    )
    activity = zero_runtime_activity()
    forbidden_authority = zero_forbidden_authority()
    evaluator = zero_evaluator_activity()
    last_result: dict[str, Any] | None = None
    cycles_completed = 0
    consecutive_failures = 0
    started_monotonic = monotonic()
    last_heartbeat_monotonic: float | None = None
    last_ledger_hash, stale_reason = _initial_loop_state(
        root=root,
        config=cfg,
        activity=activity,
        now=first_now,
    )
    signal_reason = (
        None
        if stop_controller is None or not stop_controller.stop_requested
        else stop_controller.signal_name or "signal"
    )
    initial_stop = stale_reason or signal_reason
    if initial_stop is not None:
        termination = _write_loop_control(
            root=root,
            config=cfg,
            activity=activity,
            cycle_sequence=0,
            elapsed_ms=max(0, int((monotonic() - started_monotonic) * 1000)),
            readiness_status="stopped",
            reason=initial_stop,
            ledger_hash=last_ledger_hash,
            forbidden_authority=forbidden_authority,
            now=first_now,
            terminate=True,
            write_heartbeat=True,
        )
        return _loop_result(
            stop_reason=initial_stop,
            cycles_completed=0,
            maximum=maximum,
            last_result=None,
            runtime_activity=activity,
            forbidden_authority=forbidden_authority,
            evaluator_activity=evaluator,
            termination=termination,
        )
    for index in range(maximum):
        now = _utc_timestamp() if supplied_times is None else supplied_times[index]
        if evaluator_mode:
            last_result = run_p138_supervisor_once_for_evaluation(
                base_path=root,
                config=cfg,
                p136_runtime=p136_runtime,
                publisher_inputs=publisher_inputs,
                now=now,
                stop_controller=stop_controller,
                component_callables=component_callables,
            )
        else:
            last_result = run_p138_supervisor_once(
                base_path=root,
                config=cfg,
                p136_runtime=p136_runtime,
                publisher_inputs=publisher_inputs,
                now=now,
                stop_controller=stop_controller,
            )
        activity = _sum_counter_maps(
            activity,
            _mapping(last_result.get("runtime_activity"), "runtime_activity"),
            keys=RUNTIME_ACTIVITY_KEYS,
        )
        evaluator = _sum_counter_maps(
            evaluator,
            _mapping(last_result.get("evaluator_activity"), "evaluator_activity"),
            keys=EVALUATOR_ACTIVITY_KEYS,
        )
        forbidden_authority = _sum_counter_maps(
            forbidden_authority,
            _mapping(
                last_result.get("forbidden_authority"),
                "forbidden_authority",
            ),
            keys=FORBIDDEN_AUTHORITY_KEYS,
        )
        _exact_counter_map(
            forbidden_authority,
            FORBIDDEN_AUTHORITY_KEYS,
            "invalid_loop_forbidden_authority_schema",
            require_zero=True,
        )
        ledger = last_result.get("ledger")
        if isinstance(ledger, Mapping):
            last_ledger_hash = _hash(
                ledger.get("ledger_hash"),
                "last_valid_ledger_hash",
            )
        if last_result.get("status") == "ok":
            cycles_completed += 1
            consecutive_failures = 0
        else:
            consecutive_failures += 1
        stop_reason: str | None = None
        if last_result.get("stop_reason") == "receipt_exhausted":
            stop_reason = "receipt_exhausted"
        elif stop_controller is not None and stop_controller.stop_requested:
            stop_reason = stop_controller.signal_name or "signal"
        elif consecutive_failures >= int(
            cfg["limits"]["max_consecutive_failures"]
        ):
            stop_reason = "consecutive_failure_threshold_reached"
        elif index + 1 == maximum:
            stop_reason = "max_cycles_reached"
        current_monotonic = monotonic()
        heartbeat_due = (
            stop_reason is not None
            or last_heartbeat_monotonic is None
            or int((current_monotonic - last_heartbeat_monotonic) * 1000)
            >= int(cfg["limits"]["heartbeat_interval_ms"])
        )
        termination = _write_loop_control(
            root=root,
            config=cfg,
            activity=activity,
            cycle_sequence=index + 1,
            elapsed_ms=max(0, int((current_monotonic - started_monotonic) * 1000)),
            readiness_status="stopped" if stop_reason is not None else "ready",
            reason=stop_reason or "cycle_complete",
            ledger_hash=last_ledger_hash,
            forbidden_authority=forbidden_authority,
            now=now,
            terminate=stop_reason is not None,
            write_heartbeat=heartbeat_due,
        )
        if heartbeat_due:
            last_heartbeat_monotonic = current_monotonic
        if stop_reason is not None:
            return _loop_result(
                stop_reason=stop_reason,
                cycles_completed=cycles_completed,
                maximum=maximum,
                last_result=last_result,
                runtime_activity=activity,
                forbidden_authority=forbidden_authority,
                evaluator_activity=evaluator,
                termination=termination,
            )
        sleep(float(cfg["limits"]["poll_interval_ms"]) / 1000.0)
    raise P138SupervisorError("unreachable_loop_exit")


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
