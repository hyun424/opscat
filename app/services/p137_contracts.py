"""P137 exact-key contracts and canonical byte helpers.

P137 is intentionally local-only. This module defines pure schema validation,
hashing, path, counter, and canonical-byte checks; it does not read provider
artifacts, credentials, environment, network, or execute actions.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any

from app.services.p110_evaluation import stable_hash

CONFIG_SCHEMA_VERSION = "p137.triage_agent_config.v1"
BUNDLE_SCHEMA_VERSION = "p137.p136_handoff_bundle.v1"
EVIDENCE_ATOM_SCHEMA_VERSION = "p137.evidence_atom.v1"
INCIDENT_SCHEMA_VERSION = "p137.incident_state.v1"
HYPOTHESIS_SCHEMA_VERSION = "p137.hypothesis.v1"
EVIDENCE_REQUEST_SCHEMA_VERSION = "p137.evidence_request.v1"
CLASSIFICATION_SCHEMA_VERSION = "p137.classification_record.v1"
LEDGER_SCHEMA_VERSION = "p137.investigation_ledger.v1"
INTENT_SCHEMA_VERSION = "p137.ingest_intent.v1"
CHECKPOINT_SCHEMA_VERSION = "p137.checkpoint.v1"
HEARTBEAT_SCHEMA_VERSION = "p137.heartbeat.v1"
READINESS_SCHEMA_VERSION = "p137.readiness.v1"
TERMINATION_SCHEMA_VERSION = "p137.termination_receipt.v1"
RELEASE_EVIDENCE_SCHEMA_VERSION = "p137.release_evidence.v1"
CORRELATION_POLICY_SCHEMA_VERSION = "p137.correlation_policy.v1"
RANKING_POLICY_SCHEMA_VERSION = "p137.ranking_policy.v1"
CLASSIFICATION_POLICY_SCHEMA_VERSION = "p137.classification_policy.v1"

CLASSIFICATION_SCORE_FORMULA_ID = "p137_integer_semantic_score_v1"
CLASSIFICATION_TIE_POLICY = "semantic_tuple_tie_yields_insufficient_evidence"
DENOMINATOR_FAILURE_POLICY_ID = "p137_closed_request_need_mapping_v1"
CANONICAL_STATEMENT_RULES = (
    "error_rate_regression",
    "latency_regression",
    "resource_saturation_signal",
    "data_quality_drop",
    "security_signal_cluster",
    "deployment_correlated_change",
    "topology_correlated_change",
    "scheduled_or_known_benign_noise",
    "metric_spike_with_correlated_logs",
    "telemetry_gap_only",
    "unknown_insufficient_context",
)
CANONICAL_REASON_RULES = (
    "same_system_time_window",
    "same_entity_time_window",
    "provider_signal_overlap",
    "label_hash_overlap",
    "content_hash_overlap",
    "p136_rejection_nearby",
    "numeric_threshold_exceeded",
    "log_preview_cluster",
    "topology_change_detected",
    "promoted_baseline_delta",
    "fetch_record_match",
    "known_benign_schedule",
    "decisive_counter_signal",
    "weak_counter_signal",
    "required_local_selection_missing",
    "external_authority_unavailable",
)
CANONICAL_RELATION_RULES = (
    "supports_secondary",
    "missing_required_local",
    "missing_external_unavailable",
    "supports_primary",
    "supports_benign",
    "contradicts_decisive",
    "contradicts_soft",
)
CLASSIFICATION_POLICY_FIELDS = frozenset(
    {
        "schema_version",
        "statement_rules",
        "reason_rules",
        "relation_rules",
        "metric_thresholds",
        "baseline_delta_warning_bps",
        "baseline_delta_critical_bps",
        "score_formula_id",
        "tie_policy",
        "denominator_failure_policy",
        "policy_hash",
    }
)
CONTINUOUS_MODE_FIELDS = frozenset(
    {
        "enabled",
        "max_cycles",
        "poll_interval_ms",
        "fixed_handoff_path",
        "expected_bundle_version",
        "handoff_version_polling",
        "heartbeat_interval_ms",
        "readiness_path",
        "readiness_stale_after_ms",
        "handoff_version_stale_after_ms",
    }
)
_METRIC_THRESHOLD_FIELDS = frozenset(
    {"warning_lower", "critical_lower", "warning_upper", "critical_upper"}
)

FIXED_P136_HANDOFF_PATH = "handoff/p137/p136_handoff_bundle.v1.json"
P136_QUALIFIED_RELEASE_STATUS = "p136_incremental_local_observation_qualified"

ALLOWED_REQUEST_CATALOG = (
    "compare_current_window_to_promoted_baseline",
    "fetch_record_by_evidence_id",
    "join_records_by_entity_and_window",
    "select_records_by_content_hash",
    "select_records_by_entity_ref",
    "select_records_by_label_hash",
    "select_records_by_provider",
    "select_records_by_risk_flag",
    "select_records_by_signal_family",
    "select_records_by_system_id",
    "select_records_by_time_window",
    "select_rejections_by_reason",
    "summarize_log_preview_hashes",
    "summarize_numeric_samples",
    "summarize_topology_refs",
)
CLOSED_CLASSIFICATIONS = ("confirmed_incident", "insufficient_evidence", "benign_anomaly", "aborted_fail_closed")
GUARD_PROBE_SURFACES = (
    "provider",
    "live_connector",
    "network",
    "dns",
    "socket",
    "credential",
    "environment",
    "subprocess",
    "shell",
    "signal",
    "delivery",
    "remediation",
    "staging_mutation",
    "production_mutation",
    "operator_replacement",
)
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
    "lease_acquire_count",
    "state_read_count",
    "handoff_bundle_open_count",
    "handoff_bundle_read_count",
    "handoff_bundle_bytes_read",
    "p136_validator_invocation_count",
    "promotion_record_read_count",
    "promotion_bytes_validated",
    "evidence_atom_count",
    "ingest_intent_write_count",
    "evidence_atom_write_count",
    "incident_write_count",
    "hypothesis_write_count",
    "evidence_request_write_count",
    "attempted_request_hash_write_count",
    "classification_write_count",
    "ledger_write_count",
    "heartbeat_write_count",
    "readiness_write_count",
    "termination_receipt_write_count",
    "directory_fsync_count",
    "recovery_replay_count",
    "cas_retry_count",
    "duplicate_atom_count",
    "duplicate_request_count",
    "rejection_record_count",
)
EVALUATOR_ACTIVITY_KEYS = (
    "runner_invocation_count",
    "profile_read_count",
    "handoff_fixture_write_count",
    "artifact_write_count",
    "fake_guard_callable_count",
    "child_process_count",
    "signal_delivery_count",
)
RESOURCE_USAGE_KEYS = ("wall_time_ms", "cpu_time_ms", "child_cpu_time_ms", "peak_memory_bytes", "wall_limit_ms", "cpu_limit_ms", "peak_memory_limit_bytes")
DUPLICATE_COUNT_KEYS = ("entry_hash_duplicates", "promotion_key_duplicates", "attempted_request_hash_duplicates")
LIMIT_KEYS = (
    "max_promotions_per_cycle",
    "max_records_per_cycle",
    "max_incidents_open",
    "max_correlation_window_ms",
    "max_incident_duration_ms",
    "max_hypotheses_per_incident",
    "max_support_edges_per_hypothesis",
    "max_contradiction_edges_per_hypothesis",
    "max_missing_evidence_items_per_hypothesis",
    "max_evidence_requests_per_incident",
    "max_request_input_records",
    "max_request_output_records",
    "max_request_output_bytes",
    "max_journal_bytes",
    "max_ledger_records",
    "max_consecutive_failures",
    "max_cycle_wall_ms",
    "max_agent_wall_ms",
    "max_cpu_ms",
    "max_peak_memory_bytes",
    "max_cycles",
    "poll_interval_ms",
    "heartbeat_interval_ms",
    "readiness_stale_after_ms",
    "handoff_version_stale_after_ms",
)

_CONFIG_INPUT_FIELDS = frozenset(
    {
        "agent_id",
        "config_version",
        "created_at",
        "base_dir_ref_hash",
        "state_root_ref_hash",
        "handoff_root_ref_hash",
        "p136_handoff_bundle_path",
        "p136_handoff_chain_root_hash",
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
        "validated_p136_release_status",
        "allowed_request_catalog",
        "correlation_policy",
        "ranking_policy",
        "classification_policy",
        "continuous_mode",
        "limits",
        "forbidden_authority",
    }
)
CONFIG_FIELDS = frozenset({"schema_version", *_CONFIG_INPUT_FIELDS, "config_hash"})
BUNDLE_FIELDS = frozenset(
    {
        "schema_version",
        "bundle_version",
        "bundle_sequence",
        "previous_bundle_hash",
        "handoff_chain_root_hash",
        "created_at",
        "p136_config",
        "p136_config_hash",
        "p136_runtime_authority",
        "now",
        "p136_checkpoint",
        "p136_checkpoint_hash",
        "canonical_entry_map",
        "promotion_map",
        "p136_independent_review",
        "p136_independent_review_hash",
        "p136_release_evidence",
        "p136_release_evidence_hash",
        "descriptors",
        "canonical_byte_hashes",
        "fixed_handoff_path",
        "write_durability",
        "bundle_hash",
    }
)
P136_AUTHORITY_FIELDS = frozenset(
    {
        "contract",
        "review_receipt",
        "receipt_ledger",
        "index_receipts",
        "segment_receipts",
        "contract_bytes",
        "review_receipt_bytes",
        "receipt_ledger_bytes",
        "index_receipt_bytes",
        "segment_receipt_bytes",
    }
)
EVIDENCE_ATOM_INPUT_FIELDS = frozenset(
    {
        "atom_id",
        "promotion_record_hash",
        "promotion_key",
        "p136_entry_hash",
        "p135_bundle_hash",
        "source_id",
        "provider",
        "format",
        "signal_family",
        "system_id",
        "entity_ref_hash",
        "window",
        "signal_name",
        "numeric_value",
        "numeric_unit",
        "evidence_state",
        "severity_code",
        "metric_breach_code",
        "marker_code",
        "counter_signal_code",
        "state_reason_codes",
        "denominator_visible",
        "content_hash",
        "label_hashes",
        "topology_ref_hashes",
        "deploy_config_ref_hashes",
        "risk_flags",
        "redacted_preview_hash",
        "ordinal",
    }
)
EVIDENCE_ATOM_FIELDS = frozenset({"schema_version", *EVIDENCE_ATOM_INPUT_FIELDS, "atom_hash"})

HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
HEX_RE = re.compile(r"^[0-9a-f]+$")
LABEL_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
PROMPT_OR_SECRET_RE = re.compile(
    r"(?:ignore[-_ ]previous|api[_-]?key|authorization|bearer|credential|password|secret|run[-_ ]command|https?://|socket|dns)",
    re.IGNORECASE,
)


class P137ContractError(ValueError):
    """Raised when a P137 exact-key contract fails closed."""


def reject_evaluator_guard_callables(guard_callables: Mapping[str, Any]) -> None:
    """Reject the exact evaluator-only forbidden surface map without invocation."""

    value = _mapping(guard_callables, "guard_callables")
    if set(value) != set(GUARD_PROBE_SURFACES):
        raise P137ContractError("invalid_guard_probe_surfaces")
    if any(not callable(value[surface]) for surface in GUARD_PROBE_SURFACES):
        raise P137ContractError("invalid_guard_probe_callable")
    raise P137ContractError("guard_probe_blocked_before_boundary")


def content_hash(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def zero_forbidden_authority() -> dict[str, int]:
    return {key: 0 for key in FORBIDDEN_AUTHORITY_KEYS}


def zero_runtime_activity(**overrides: int) -> dict[str, int]:
    values = {key: 0 for key in RUNTIME_ACTIVITY_KEYS}
    values.update(overrides)
    return values


def zero_evaluator_activity(**overrides: int) -> dict[str, int]:
    values = {key: 0 for key in EVALUATOR_ACTIVITY_KEYS}
    values.update(overrides)
    return values


def bounded_resource_usage(**overrides: int) -> dict[str, int]:
    values = {
        "wall_time_ms": 0,
        "cpu_time_ms": 0,
        "child_cpu_time_ms": 0,
        "peak_memory_bytes": 0,
        "wall_limit_ms": 1,
        "cpu_limit_ms": 1,
        "peak_memory_limit_bytes": 1,
    }
    values.update(overrides)
    return values


def build_correlation_policy() -> dict[str, str]:
    """Return the only P137 correlation-policy contract supported by v1."""

    return {"schema_version": CORRELATION_POLICY_SCHEMA_VERSION}


def build_ranking_policy() -> dict[str, str]:
    """Return the only P137 ranking-policy contract supported by v1."""

    return {"schema_version": RANKING_POLICY_SCHEMA_VERSION}


def build_classification_policy(
    *,
    metric_thresholds: Mapping[str, Any] | None = None,
    baseline_delta_warning_bps: int = 1_000,
    baseline_delta_critical_bps: int = 2_500,
) -> dict[str, Any]:
    """Build the closed, self-hashed P137 classifier policy.

    Rule lists are identifiers for the versioned tables in the P137 contract;
    they are not executable text or user-provided expressions.
    """

    warning = _positive_int(baseline_delta_warning_bps, "baseline_delta_warning_bps")
    critical = _positive_int(baseline_delta_critical_bps, "baseline_delta_critical_bps")
    if critical < warning:
        raise P137ContractError("baseline_delta_threshold_order_invalid")
    value: dict[str, Any] = {
        "schema_version": CLASSIFICATION_POLICY_SCHEMA_VERSION,
        "statement_rules": list(CANONICAL_STATEMENT_RULES),
        "reason_rules": list(CANONICAL_REASON_RULES),
        "relation_rules": list(CANONICAL_RELATION_RULES),
        "metric_thresholds": _metric_threshold_map(metric_thresholds or {}),
        "baseline_delta_warning_bps": warning,
        "baseline_delta_critical_bps": critical,
        "score_formula_id": CLASSIFICATION_SCORE_FORMULA_ID,
        "tie_policy": CLASSIFICATION_TIE_POLICY,
        "denominator_failure_policy": DENOMINATOR_FAILURE_POLICY_ID,
    }
    value["policy_hash"] = stable_hash(value)
    return value


def build_continuous_mode(
    *,
    enabled: bool,
    max_cycles: int,
    poll_interval_ms: int,
    heartbeat_interval_ms: int,
    readiness_path: str,
    readiness_stale_after_ms: int,
    handoff_version_stale_after_ms: int,
    expected_bundle_version: int = 1,
    handoff_version_polling: bool = True,
) -> dict[str, Any]:
    return {
        "enabled": _bool(enabled, "continuous_mode_enabled"),
        "max_cycles": _positive_int(max_cycles, "continuous_mode_max_cycles"),
        "poll_interval_ms": _positive_int(poll_interval_ms, "continuous_mode_poll_interval_ms"),
        "fixed_handoff_path": FIXED_P136_HANDOFF_PATH,
        "expected_bundle_version": _positive_int(expected_bundle_version, "expected_bundle_version"),
        "handoff_version_polling": _bool(handoff_version_polling, "handoff_version_polling"),
        "heartbeat_interval_ms": _positive_int(heartbeat_interval_ms, "continuous_mode_heartbeat_interval_ms"),
        "readiness_path": _relative_path(readiness_path, "continuous_mode_readiness_path"),
        "readiness_stale_after_ms": _positive_int(readiness_stale_after_ms, "continuous_mode_readiness_stale_after_ms"),
        "handoff_version_stale_after_ms": _positive_int(
            handoff_version_stale_after_ms,
            "continuous_mode_handoff_version_stale_after_ms",
        ),
    }


def validate_continuous_mode(mode: Mapping[str, Any], *, paths: Mapping[str, str], limits: Mapping[str, int]) -> None:
    value = _mapping(mode, "continuous_mode")
    if set(value) != CONTINUOUS_MODE_FIELDS:
        raise P137ContractError("invalid_continuous_mode_fields")
    rebuilt = build_continuous_mode(
        enabled=_bool(value.get("enabled"), "continuous_mode_enabled"),
        max_cycles=_positive_int(value.get("max_cycles"), "continuous_mode_max_cycles"),
        poll_interval_ms=_positive_int(value.get("poll_interval_ms"), "continuous_mode_poll_interval_ms"),
        heartbeat_interval_ms=_positive_int(value.get("heartbeat_interval_ms"), "continuous_mode_heartbeat_interval_ms"),
        readiness_path=_relative_path(value.get("readiness_path"), "continuous_mode_readiness_path"),
        readiness_stale_after_ms=_positive_int(
            value.get("readiness_stale_after_ms"),
            "continuous_mode_readiness_stale_after_ms",
        ),
        handoff_version_stale_after_ms=_positive_int(
            value.get("handoff_version_stale_after_ms"),
            "continuous_mode_handoff_version_stale_after_ms",
        ),
        expected_bundle_version=_positive_int(value.get("expected_bundle_version"), "expected_bundle_version"),
        handoff_version_polling=_bool(value.get("handoff_version_polling"), "handoff_version_polling"),
    )
    if dict(value) != rebuilt:
        raise P137ContractError("continuous_mode_semantics_invalid")
    if rebuilt["readiness_path"] != paths["readiness_path"]:
        raise P137ContractError("continuous_mode_readiness_path_mismatch")
    for key in (
        "max_cycles",
        "poll_interval_ms",
        "heartbeat_interval_ms",
        "readiness_stale_after_ms",
        "handoff_version_stale_after_ms",
    ):
        if rebuilt[key] != limits[key]:
            raise P137ContractError(f"continuous_mode_limit_mismatch:{key}")


def validate_classification_policy(policy: Mapping[str, Any]) -> None:
    value = _mapping(policy, "classification_policy")
    if set(value) != CLASSIFICATION_POLICY_FIELDS:
        raise P137ContractError("invalid_classification_policy_fields")
    warning = _positive_int(value.get("baseline_delta_warning_bps"), "baseline_delta_warning_bps")
    critical = _positive_int(value.get("baseline_delta_critical_bps"), "baseline_delta_critical_bps")
    rebuilt = build_classification_policy(
        metric_thresholds=_mapping(value.get("metric_thresholds"), "metric_thresholds"),
        baseline_delta_warning_bps=warning,
        baseline_delta_critical_bps=critical,
    )
    if dict(value) != rebuilt:
        raise P137ContractError("classification_policy_semantics_invalid")


def build_triage_agent_config(data: Mapping[str, Any]) -> dict[str, Any]:
    raw = _mapping(data, "config")
    _reject_unknown_missing(raw, _CONFIG_INPUT_FIELDS, "config")
    limits = _positive_int_map(raw.get("limits"), LIMIT_KEYS, "limit")
    paths = {
        key: _relative_path(raw.get(key), key)
        for key in (
            "p136_handoff_bundle_path",
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
        )
    }
    if paths["p136_handoff_bundle_path"] != FIXED_P136_HANDOFF_PATH:
        raise P137ContractError("invalid_fixed_handoff_path")
    _validate_state_paths(paths)
    correlation_policy = _fixed_policy(
        raw.get("correlation_policy"),
        label="correlation_policy",
        schema_version=CORRELATION_POLICY_SCHEMA_VERSION,
    )
    ranking_policy = _fixed_policy(
        raw.get("ranking_policy"),
        label="ranking_policy",
        schema_version=RANKING_POLICY_SCHEMA_VERSION,
    )
    classification_policy = deepcopy(dict(_mapping(raw.get("classification_policy"), "classification_policy")))
    validate_classification_policy(classification_policy)
    continuous_mode = deepcopy(dict(_mapping(raw.get("continuous_mode"), "continuous_mode")))
    validate_continuous_mode(continuous_mode, paths=paths, limits=limits)
    config: dict[str, Any] = {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "agent_id": _label(raw.get("agent_id"), "agent_id"),
        "config_version": _positive_int(raw.get("config_version"), "config_version"),
        "created_at": _timestamp(raw.get("created_at"), "created_at"),
        "base_dir_ref_hash": _hash(raw.get("base_dir_ref_hash"), "base_dir_ref_hash"),
        "state_root_ref_hash": _hash(raw.get("state_root_ref_hash"), "state_root_ref_hash"),
        "handoff_root_ref_hash": _hash(raw.get("handoff_root_ref_hash"), "handoff_root_ref_hash"),
        **paths,
        "p136_handoff_chain_root_hash": _hash(raw.get("p136_handoff_chain_root_hash"), "p136_handoff_chain_root_hash"),
        "validated_p136_release_status": _required_text(raw.get("validated_p136_release_status"), "validated_p136_release_status"),
        "allowed_request_catalog": list(_request_catalog(raw.get("allowed_request_catalog"))),
        "correlation_policy": correlation_policy,
        "ranking_policy": ranking_policy,
        "classification_policy": classification_policy,
        "continuous_mode": continuous_mode,
        "limits": limits,
        "forbidden_authority": _exact_counter_map(raw.get("forbidden_authority"), FORBIDDEN_AUTHORITY_KEYS, "invalid_forbidden_authority_schema", require_zero=True),
    }
    if config["validated_p136_release_status"] != P136_QUALIFIED_RELEASE_STATUS:
        raise P137ContractError("invalid_p136_release_status")
    _reject_forbidden_text(config)
    config["config_hash"] = stable_hash(config)
    return config


def validate_triage_agent_config(config: Mapping[str, Any]) -> None:
    value = _mapping(config, "config")
    if set(value) != CONFIG_FIELDS or value.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise P137ContractError("invalid_config_fields")
    if value.get("config_hash") != stable_hash({key: item for key, item in value.items() if key != "config_hash"}):
        raise P137ContractError("config_hash_invalid")
    rebuilt = build_triage_agent_config({key: deepcopy(value[key]) for key in _CONFIG_INPUT_FIELDS})
    if rebuilt != dict(value):
        raise P137ContractError("config_semantics_invalid")


def decode_canonical_lower_hex(
    encoded: Any,
    *,
    field: str,
    expected_hash: str | None = None,
    expected_length: int | None = None,
) -> bytes:
    if not isinstance(encoded, str) or not encoded or len(encoded) % 2 != 0 or HEX_RE.fullmatch(encoded) is None:
        raise P137ContractError(f"invalid_canonical_hex:{field}")
    try:
        decoded = bytes.fromhex(encoded)
    except ValueError as exc:
        raise P137ContractError(f"invalid_canonical_hex:{field}") from exc
    if decoded.hex() != encoded:
        raise P137ContractError(f"invalid_canonical_hex:{field}")
    if expected_hash is not None and content_hash(decoded) != _hash(expected_hash, f"{field}_hash"):
        raise P137ContractError(f"canonical_byte_hash_mismatch:{field}")
    if expected_length is not None and len(decoded) != _nonnegative_int(expected_length, f"{field}_length"):
        raise P137ContractError(f"canonical_byte_length_mismatch:{field}")
    return decoded


def build_evidence_atom(data: Mapping[str, Any]) -> dict[str, Any]:
    raw = _mapping(data, "evidence_atom")
    _reject_unknown_missing(raw, EVIDENCE_ATOM_INPUT_FIELDS, "evidence_atom")
    numeric_value = _numeric_or_none(raw.get("numeric_value"))
    numeric_unit = None if numeric_value is None else _required_text(raw.get("numeric_unit"), "numeric_unit")
    atom: dict[str, Any] = {
        "schema_version": EVIDENCE_ATOM_SCHEMA_VERSION,
        "atom_id": _label(raw.get("atom_id"), "atom_id"),
        "promotion_record_hash": _hash(raw.get("promotion_record_hash"), "promotion_record_hash"),
        "promotion_key": _hash(raw.get("promotion_key"), "promotion_key"),
        "p136_entry_hash": _hash(raw.get("p136_entry_hash"), "p136_entry_hash"),
        "p135_bundle_hash": _hash(raw.get("p135_bundle_hash"), "p135_bundle_hash"),
        "source_id": _required_text(raw.get("source_id"), "source_id"),
        "provider": _required_text(raw.get("provider"), "provider"),
        "format": _required_text(raw.get("format"), "format"),
        "signal_family": _required_text(raw.get("signal_family"), "signal_family"),
        "system_id": _required_text(raw.get("system_id"), "system_id"),
        "entity_ref_hash": _hash(raw.get("entity_ref_hash"), "entity_ref_hash"),
        "window": _window(raw.get("window")),
        "signal_name": _required_text(raw.get("signal_name"), "signal_name"),
        "numeric_value": numeric_value,
        "numeric_unit": numeric_unit,
        "evidence_state": _enum(raw.get("evidence_state"), {"promoted_success", "denominator_visible_failure", "context_only"}, "evidence_state"),
        "severity_code": _enum(raw.get("severity_code"), {"sev0", "sev1", "sev2", "sev3", "sev4", "unknown"}, "severity_code"),
        "metric_breach_code": _enum(
            raw.get("metric_breach_code"),
            {"none", "above_warning", "above_critical", "below_warning", "below_critical", "baseline_delta_warning", "baseline_delta_critical"},
            "metric_breach_code",
        ),
        "marker_code": _enum(
            raw.get("marker_code"),
            {"none", "known_benign_schedule", "topology_noise", "deployment_marker", "topology_marker", "security_marker", "data_quality_marker"},
            "marker_code",
        ),
        "counter_signal_code": _enum(raw.get("counter_signal_code"), {"none", "weak_counter_signal", "decisive_counter_signal"}, "counter_signal_code"),
        "state_reason_codes": _closed_text_list(
            raw.get("state_reason_codes"),
            "state_reason_codes",
            {
                "parser_failure",
                "redaction_failure",
                "provenance_failure",
                "local_catalog_selectable",
                "p135_adapter_failure",
                "provider_authority_required",
                "network_authority_required",
                "credential_authority_required",
                "operator_authority_required",
                "action_authority_required",
            },
        ),
        "denominator_visible": _bool(raw.get("denominator_visible"), "denominator_visible"),
        "content_hash": _optional_hash(raw.get("content_hash"), "content_hash"),
        "label_hashes": _hash_list(raw.get("label_hashes"), "label_hashes"),
        "topology_ref_hashes": _hash_list(raw.get("topology_ref_hashes"), "topology_ref_hashes"),
        "deploy_config_ref_hashes": _hash_list(raw.get("deploy_config_ref_hashes"), "deploy_config_ref_hashes"),
        "risk_flags": _text_list(raw.get("risk_flags"), "risk_flags"),
        "redacted_preview_hash": _optional_hash(raw.get("redacted_preview_hash"), "redacted_preview_hash"),
        "ordinal": _positive_int(raw.get("ordinal"), "ordinal"),
    }
    _reject_forbidden_text(atom)
    atom["atom_hash"] = stable_hash(atom)
    return atom


def validate_evidence_atom(atom: Mapping[str, Any]) -> None:
    value = _mapping(atom, "evidence_atom")
    if set(value) != EVIDENCE_ATOM_FIELDS or value.get("schema_version") != EVIDENCE_ATOM_SCHEMA_VERSION:
        raise P137ContractError("invalid_evidence_atom_fields")
    rebuilt = build_evidence_atom({key: deepcopy(value[key]) for key in EVIDENCE_ATOM_INPUT_FIELDS})
    if value.get("atom_hash") != stable_hash({key: item for key, item in value.items() if key != "atom_hash"}):
        raise P137ContractError("atom_hash_invalid")
    if rebuilt != dict(value):
        raise P137ContractError("evidence_atom_semantics_invalid")


def validate_exact_self_hash(value: Mapping[str, Any], *, fields: frozenset[str], schema_version: str, hash_field: str, label: str) -> None:
    item = _mapping(value, label)
    if set(item) != fields or item.get("schema_version") != schema_version:
        raise P137ContractError(f"invalid_{label}_fields")
    if item.get(hash_field) != stable_hash({key: raw for key, raw in item.items() if key != hash_field}):
        raise P137ContractError(f"{hash_field}_invalid")


def _reject_unknown_missing(value: Mapping[str, Any], fields: frozenset[str], label: str) -> None:
    unknown = set(value) - fields
    missing = fields - set(value)
    if unknown:
        raise P137ContractError(f"unexpected_{label}_field")
    if missing:
        raise P137ContractError(f"missing_{label}_field")


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise P137ContractError(f"invalid_{label}_shape")
    return value


def _hash(value: Any, label: str) -> str:
    if not isinstance(value, str) or HASH_RE.fullmatch(value) is None:
        raise P137ContractError(f"invalid_hash:{label}")
    return value


def _label(value: Any, label: str) -> str:
    text = _required_text(value, label)
    if LABEL_RE.fullmatch(text) is None:
        raise P137ContractError(f"invalid_label:{label}")
    return text


def _required_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise P137ContractError(f"invalid_text:{label}")
    if PROMPT_OR_SECRET_RE.search(value):
        raise P137ContractError("prompt_or_credential_text_forbidden")
    return value


def _enum(value: Any, allowed: set[str], label: str) -> str:
    text = _required_text(value, label)
    if text not in allowed:
        raise P137ContractError(f"invalid_{label}")
    return text


def _timestamp(value: Any, label: str) -> str:
    text = _required_text(value, label)
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise P137ContractError(f"invalid_timestamp:{label}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise P137ContractError(f"invalid_timestamp:{label}")
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise P137ContractError(f"invalid_bool:{label}")
    return value


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise P137ContractError(f"invalid_positive_int:{label}")
    return value


def _nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise P137ContractError(f"invalid_nonnegative_int:{label}")
    return value


def _positive_int_map(value: Any, keys: Sequence[str], label: str) -> dict[str, int]:
    raw = _mapping(value, f"{label}s")
    if set(raw) != set(keys):
        raise P137ContractError(f"invalid_{label}s_schema")
    result: dict[str, int] = {}
    for key in keys:
        try:
            result[key] = _positive_int(raw[key], f"{label}:{key}")
        except P137ContractError as exc:
            raise P137ContractError(f"invalid_{label}:{key}") from exc
    return result


def _exact_counter_map(value: Any, keys: Sequence[str], error: str, *, require_zero: bool = False) -> dict[str, int]:
    raw = _mapping(value, "counters")
    if set(raw) != set(keys):
        raise P137ContractError(error)
    result: dict[str, int] = {}
    for key in keys:
        current = raw[key]
        if isinstance(current, bool) or not isinstance(current, int) or current < 0:
            raise P137ContractError(error)
        if require_zero and current != 0:
            raise P137ContractError("forbidden_authority_nonzero")
        result[key] = current
    return result


def _request_catalog(value: Any) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise P137ContractError("invalid_allowed_request_catalog")
    catalog = tuple(str(item) for item in value)
    if catalog != ALLOWED_REQUEST_CATALOG:
        raise P137ContractError("invalid_allowed_request_catalog")
    return catalog


def _fixed_policy(value: Any, *, label: str, schema_version: str) -> dict[str, str]:
    raw = _mapping(value, label)
    if set(raw) != {"schema_version"} or raw.get("schema_version") != schema_version:
        raise P137ContractError(f"invalid_{label}")
    return {"schema_version": schema_version}


def _metric_threshold_map(value: Any) -> dict[str, dict[str, dict[str, int | float | None]]]:
    raw = _mapping(value, "metric_thresholds")
    result: dict[str, dict[str, dict[str, int | float | None]]] = {}
    for signal_name in sorted(raw):
        _label(signal_name, "metric_threshold_signal")
        units = _mapping(raw[signal_name], "metric_threshold_units")
        normalized_units: dict[str, dict[str, int | float | None]] = {}
        for numeric_unit in sorted(units):
            _required_text(numeric_unit, "metric_threshold_unit")
            bounds = _mapping(units[numeric_unit], "metric_threshold_bounds")
            if set(bounds) != _METRIC_THRESHOLD_FIELDS:
                raise P137ContractError("invalid_metric_threshold_fields")
            normalized: dict[str, int | float | None] = {
                key: _numeric_or_none(bounds[key]) for key in sorted(_METRIC_THRESHOLD_FIELDS)
            }
            warning_lower = normalized["warning_lower"]
            critical_lower = normalized["critical_lower"]
            warning_upper = normalized["warning_upper"]
            critical_upper = normalized["critical_upper"]
            if warning_lower is not None and critical_lower is not None and critical_lower > warning_lower:
                raise P137ContractError("metric_lower_threshold_order_invalid")
            if warning_upper is not None and critical_upper is not None and warning_upper > critical_upper:
                raise P137ContractError("metric_upper_threshold_order_invalid")
            normalized_units[numeric_unit] = normalized
        result[signal_name] = normalized_units
    return result


def _relative_path(value: Any, label: str) -> str:
    text = _required_text(value, label)
    path = PurePosixPath(text)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise P137ContractError(f"unsafe_path:{label}")
    normalized = path.as_posix()
    if normalized != text:
        raise P137ContractError(f"unsafe_path:{label}")
    return normalized


def _validate_state_paths(paths: Mapping[str, str]) -> None:
    handoff = paths["p136_handoff_bundle_path"]
    state_paths = {key: value for key, value in paths.items() if key != "p136_handoff_bundle_path"}
    for name, path in state_paths.items():
        if _paths_overlap(path, handoff):
            raise P137ContractError("state_path_overlaps_handoff_path")
        for other_name, other_path in state_paths.items():
            if name >= other_name:
                continue
            if _paths_overlap(path, other_path):
                raise P137ContractError("state_paths_overlap")


def _paths_overlap(left: str, right: str) -> bool:
    left_parts = PurePosixPath(left).parts
    right_parts = PurePosixPath(right).parts
    return left_parts == right_parts or left_parts[: len(right_parts)] == right_parts or right_parts[: len(left_parts)] == left_parts


def _numeric_or_none(value: Any) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise P137ContractError("invalid_numeric_value")
    return value


def _text_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise P137ContractError(f"invalid_{label}")
    result = [_required_text(item, f"{label}_item") for item in value]
    if len(result) != len(set(result)):
        raise P137ContractError(f"duplicate_{label}")
    return sorted(result)


def _closed_text_list(value: Any, label: str, allowed: set[str]) -> list[str]:
    result = _text_list(value, label)
    if any(item not in allowed for item in result):
        raise P137ContractError(f"invalid_{label}")
    return result


def _optional_hash(value: Any, label: str) -> str | None:
    return None if value is None else _hash(value, label)


def _hash_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise P137ContractError(f"invalid_{label}")
    result = [_hash(item, f"{label}_item") for item in value]
    if len(result) != len(set(result)):
        raise P137ContractError(f"duplicate_{label}")
    return sorted(result)


def _json_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise P137ContractError(f"invalid_{label}")
    return deepcopy(list(value))


def _window(value: Any) -> dict[str, str]:
    raw = _mapping(value, "observed_window")
    if set(raw) != {"start", "end"}:
        raise P137ContractError("invalid_observed_window")
    start = _timestamp(raw["start"], "window_start")
    end = _timestamp(raw["end"], "window_end")
    if start > end:
        raise P137ContractError("invalid_observed_window")
    return {"start": start, "end": end}


def _reject_forbidden_text(value: Any) -> None:
    if isinstance(value, str):
        _required_text(value, "text")
    elif isinstance(value, Mapping):
        for item in value.values():
            _reject_forbidden_text(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            _reject_forbidden_text(item)
