"""Pure, fail-closed observation-authority contracts for P134.

This module evaluates policy declarations only. It intentionally has no file,
environment, network, provider, subprocess, command, delivery, or remediation
surface.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p121_signals import validate_exact_zero_authority, zero_authority_counters

CORE_SCHEMA_VERSION = "p134.observation_authority_core.v1"
REVIEW_SCHEMA_VERSION = "p134.observation_review_receipt.v1"
CONTRACT_SCHEMA_VERSION = "p134.observation_authority_contract.v1"
PROPOSAL_SCHEMA_VERSION = "p134.observation_proposal.v1"
RECEIPT_SCHEMA_VERSION = "p134.observation_decision_receipt.v1"
LEDGER_SCHEMA_VERSION = "p134.observation_receipt_ledger.v1"
GENESIS_SCHEMA_VERSION = "p134.ledger_genesis.v1"

AUTHORITY_LEVELS = (
    "OA0_CONTRACT_ONLY",
    "OA1_LOCAL_ARTIFACT",
    "OA2_PROVIDER_SHAPED_LOCAL_EXPORT",
    "OA3_OPT_IN_LIVE_GET_SHADOW",
    "OA4_CREDENTIAL_OR_EXTERNAL_READ",
)
QUALIFIED_LEVELS = frozenset(AUTHORITY_LEVELS[:2])
LOCAL_METHODS = frozenset({"LOCAL_STAT", "LOCAL_READ_FILE", "LOCAL_LIST_DIR"})
METHODS = frozenset({*LOCAL_METHODS, "HTTP_GET"})
CAPABILITIES = frozenset(
    {
        "telemetry.metadata.read",
        "telemetry.metrics.read",
        "telemetry.logs.read",
        "telemetry.traces.read",
        "telemetry.events.read",
        "telemetry.topology.read",
    }
)
REVIEW_LIMITATIONS = (
    "no_action_authority",
    "oa2_oa3_oa4_blocked",
    "policy_only_no_io",
    "reviewer_identity_unauthenticated",
)
REASON_ORDER = (
    "contract_only_level",
    "contract_not_yet_valid",
    "contract_expired",
    "review_not_approved",
    "review_expired",
    "kill_switch_active",
    "authority_level_exceeds_contract",
    "authority_level_not_qualified",
    "host_not_allowlisted",
    "method_not_allowlisted",
    "method_not_qualified",
    "capability_not_allowlisted",
    "attempt_budget_exceeded",
    "allowed_request_budget_exceeded",
    "cumulative_byte_budget_exceeded",
    "cumulative_record_budget_exceeded",
    "host_budget_exceeded",
    "method_budget_exceeded",
    "capability_budget_exceeded",
    "single_response_byte_budget_exceeded",
    "timeout_budget_exceeded",
)
POLICY_DENIAL_REASONS = frozenset(REASON_ORDER[:12])
BUDGET_DENIAL_REASONS = frozenset(REASON_ORDER[12:])

_LABEL_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_LOCAL_HOST_RE = re.compile(r"^local-artifact(?:\.[a-z0-9][a-z0-9._-]{0,47})?$")
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_FORBIDDEN_LABEL_RE = re.compile(
    r"(?:api[._-]?key|token|secret|password|credential|authorization|bearer|"
    r"webhook|provider|endpoint|header|query|payload|shell|command|remediation|"
    r"mutation|action|grafana|prometheus|datadog|sentry|slack)",
    re.IGNORECASE,
)

_CORE_INPUT_FIELDS = frozenset(
    {
        "contract_id",
        "contract_version",
        "subject_ref_hash",
        "max_authority_level",
        "allowed_hosts",
        "allowed_methods",
        "allowed_capabilities",
        "budgets",
        "valid_from",
        "expires_at",
        "default_decision",
        "kill_switch",
        "action_authority",
    }
)
_CORE_FIELDS = frozenset({"schema_version", *_CORE_INPUT_FIELDS, "core_hash"})
_REVIEW_INPUT_FIELDS = frozenset({"decision", "reviewer_ref_hash", "reviewed_at", "expires_at"})
_REVIEW_FIELDS = frozenset(
    {
        "schema_version",
        "contract_core_hash",
        *_REVIEW_INPUT_FIELDS,
        "limitations",
        "review_receipt_hash",
    }
)
_CONTRACT_FIELDS = frozenset({"schema_version", "core", "review_receipt", "contract_hash"})
_PROPOSAL_INPUT_FIELDS = frozenset(
    {
        "request_id",
        "sequence",
        "proposed_at",
        "requested_level",
        "source_ref_hash",
        "host_label",
        "method",
        "capability",
        "estimated_response_bytes",
        "estimated_records",
        "timeout_ms",
        "attempt_number",
    }
)
_PROPOSAL_FIELDS = frozenset({"schema_version", *_PROPOSAL_INPUT_FIELDS, "proposal_hash"})
_RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "receipt_id",
        "sequence",
        "request_id",
        "proposal",
        "proposal_hash",
        "contract_hash",
        "contract_core_hash",
        "review_receipt_hash",
        "decision",
        "reasons",
        "evaluated_at",
        "previous_receipt_hash",
        "counters_before",
        "counters_after",
        "action_authority",
        "receipt_hash",
    }
)
_LEDGER_FIELDS = frozenset(
    {
        "schema_version",
        "contract_hash",
        "window_started_at",
        "window_ends_at",
        "next_sequence",
        "receipts",
        "counters",
        "action_authority",
        "ledger_hash",
    }
)
_COUNTER_SCALAR_FIELDS = frozenset(
    {
        "evaluated_count",
        "allowed_count",
        "denied_count",
        "allowed_estimated_response_bytes",
        "allowed_estimated_records",
        "budget_denial_count",
        "policy_denial_count",
        "unique_allowed_host_count",
        "unique_allowed_method_count",
        "unique_allowed_capability_count",
    }
)
_COUNTER_MAP_FIELDS = frozenset(
    {"allowed_host_counts", "allowed_method_counts", "allowed_capability_counts"}
)
_COUNTER_FIELDS = frozenset({*_COUNTER_SCALAR_FIELDS, *_COUNTER_MAP_FIELDS})
_BUDGET_LIMITS: dict[str, tuple[int, int]] = {
    "window_seconds": (60, 86_400),
    "max_allowed_requests_per_window": (1, 1_000),
    "max_allowed_estimated_response_bytes_per_window": (1, 1_073_741_824),
    "max_allowed_estimated_records_per_window": (1, 10_000_000),
    "max_unique_hosts_per_window": (1, 64),
    "max_unique_methods_per_window": (1, 8),
    "max_unique_capabilities_per_window": (1, 32),
    "max_single_response_bytes": (1, 67_108_864),
    "max_timeout_ms": (1, 60_000),
    "max_attempt_number": (1, 10),
}


class P134AuthorityError(ValueError):
    """Raised when an observation-authority artifact fails closed."""


@dataclass(frozen=True)
class EvaluationResult:
    """Pure evaluation result; duplicate is intentionally outside the ledger."""

    receipt: dict[str, Any]
    ledger: dict[str, Any]
    duplicate: bool


def build_contract_core(data: Mapping[str, Any]) -> dict[str, Any]:
    """Build the canonical P134 authority core from strict semantic input."""

    raw = _mapping(data, "core")
    _expect_exact_fields(raw, _CORE_INPUT_FIELDS, "core")
    core: dict[str, Any] = {
        "schema_version": CORE_SCHEMA_VERSION,
        "contract_id": raw["contract_id"],
        "contract_version": raw["contract_version"],
        "subject_ref_hash": raw["subject_ref_hash"],
        "max_authority_level": raw["max_authority_level"],
        "allowed_hosts": _sorted_unique_strings(raw["allowed_hosts"], "allowed_hosts"),
        "allowed_methods": _sorted_unique_strings(raw["allowed_methods"], "allowed_methods"),
        "allowed_capabilities": _sorted_unique_strings(raw["allowed_capabilities"], "allowed_capabilities"),
        "budgets": dict(_mapping(raw["budgets"], "budgets")),
        "valid_from": raw["valid_from"],
        "expires_at": raw["expires_at"],
        "default_decision": raw["default_decision"],
        "kill_switch": raw["kill_switch"],
        "action_authority": dict(_mapping(raw["action_authority"], "action_authority")),
    }
    _validate_core_semantics(core)
    core["core_hash"] = stable_hash(core)
    return core


def validate_contract_core(core: Mapping[str, Any]) -> None:
    value = _mapping(core, "core")
    _expect_exact_fields(value, _CORE_FIELDS, "core")
    if value.get("schema_version") != CORE_SCHEMA_VERSION:
        raise P134AuthorityError("invalid_core_schema")
    _validate_self_hash(value, "core_hash", "core_hash_invalid")
    _validate_core_semantics({key: item for key, item in value.items() if key != "core_hash"})


def build_review_receipt(core: Mapping[str, Any], data: Mapping[str, Any]) -> dict[str, Any]:
    """Build structural review evidence bound to one exact core."""

    validate_contract_core(core)
    raw = _mapping(data, "review")
    _expect_exact_fields(raw, _REVIEW_INPUT_FIELDS, "review")
    review: dict[str, Any] = {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "contract_core_hash": core["core_hash"],
        "decision": raw["decision"],
        "reviewer_ref_hash": raw["reviewer_ref_hash"],
        "reviewed_at": raw["reviewed_at"],
        "expires_at": raw["expires_at"],
        "limitations": list(REVIEW_LIMITATIONS),
    }
    _validate_review_semantics(review, core=core)
    review["review_receipt_hash"] = stable_hash(review)
    return review


def validate_review_receipt(review: Mapping[str, Any], *, core: Mapping[str, Any]) -> None:
    validate_contract_core(core)
    value = _mapping(review, "review")
    _expect_exact_fields(value, _REVIEW_FIELDS, "review")
    if value.get("schema_version") != REVIEW_SCHEMA_VERSION:
        raise P134AuthorityError("invalid_review_schema")
    _validate_self_hash(value, "review_receipt_hash", "review_receipt_hash_invalid")
    _validate_review_semantics(
        {key: item for key, item in value.items() if key != "review_receipt_hash"},
        core=core,
    )


def build_contract(core: Mapping[str, Any], review_receipt: Mapping[str, Any]) -> dict[str, Any]:
    validate_contract_core(core)
    validate_review_receipt(review_receipt, core=core)
    contract: dict[str, Any] = {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "core": deepcopy(dict(core)),
        "review_receipt": deepcopy(dict(review_receipt)),
    }
    contract["contract_hash"] = stable_hash(contract)
    return contract


def validate_contract(contract: Mapping[str, Any]) -> None:
    value = _mapping(contract, "contract")
    _expect_exact_fields(value, _CONTRACT_FIELDS, "contract")
    if value.get("schema_version") != CONTRACT_SCHEMA_VERSION:
        raise P134AuthorityError("invalid_contract_schema")
    _validate_self_hash(value, "contract_hash", "contract_hash_invalid")
    core = _mapping(value.get("core"), "core")
    review = _mapping(value.get("review_receipt"), "review")
    validate_contract_core(core)
    validate_review_receipt(review, core=core)


def build_proposal(data: Mapping[str, Any]) -> dict[str, Any]:
    """Build a strict, non-secret observation proposal without performing I/O."""

    raw = _mapping(data, "proposal")
    _expect_exact_fields(raw, _PROPOSAL_INPUT_FIELDS, "proposal")
    proposal: dict[str, Any] = {
        "schema_version": PROPOSAL_SCHEMA_VERSION,
        **{key: raw[key] for key in _PROPOSAL_INPUT_FIELDS},
    }
    _validate_proposal_semantics(proposal)
    proposal["proposal_hash"] = stable_hash(proposal)
    return proposal


def validate_proposal(proposal: Mapping[str, Any]) -> None:
    value = _mapping(proposal, "proposal")
    _expect_exact_fields(value, _PROPOSAL_FIELDS, "proposal")
    if value.get("schema_version") != PROPOSAL_SCHEMA_VERSION:
        raise P134AuthorityError("invalid_proposal_schema")
    _validate_self_hash(value, "proposal_hash", "proposal_hash_invalid")
    _validate_proposal_semantics({key: item for key, item in value.items() if key != "proposal_hash"})


def new_receipt_ledger(contract: Mapping[str, Any], *, window_started_at: str) -> dict[str, Any]:
    """Create an empty deterministic ledger for one fixed policy window."""

    validate_contract(contract)
    start = _parse_timestamp(window_started_at, "window_started_at")
    window_seconds = _exact_int(_mapping(contract["core"], "core")["budgets"]["window_seconds"], "window_seconds")
    ledger: dict[str, Any] = {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "contract_hash": contract["contract_hash"],
        "window_started_at": _format_timestamp(start),
        "window_ends_at": _format_timestamp(start + timedelta(seconds=window_seconds)),
        "next_sequence": 1,
        "receipts": [],
        "counters": _empty_counters(),
        "action_authority": zero_authority_counters(),
    }
    ledger["ledger_hash"] = stable_hash(ledger)
    return ledger


def evaluate_proposal(
    contract: Mapping[str, Any],
    proposal: Mapping[str, Any],
    ledger: Mapping[str, Any],
) -> EvaluationResult:
    """Evaluate one proposal with no I/O and return a new canonical ledger."""

    validate_contract(contract)
    validate_proposal(proposal)
    validate_receipt_ledger(ledger, contract=contract)
    contract_value = dict(contract)
    proposal_value = dict(proposal)
    ledger_value = dict(ledger)

    for item in _receipt_list(ledger_value.get("receipts")):
        if item.get("request_id") != proposal_value["request_id"]:
            continue
        if item.get("proposal_hash") != proposal_value["proposal_hash"]:
            raise P134AuthorityError("request_id_reuse_conflict")
        return EvaluationResult(receipt=deepcopy(item), ledger=deepcopy(ledger_value), duplicate=True)

    sequence = _exact_int(proposal_value["sequence"], "sequence")
    if sequence != ledger_value["next_sequence"]:
        raise P134AuthorityError("sequence_mismatch")
    proposed_at = _parse_timestamp(proposal_value["proposed_at"], "proposed_at")
    window_start = _parse_timestamp(ledger_value["window_started_at"], "window_started_at")
    window_end = _parse_timestamp(ledger_value["window_ends_at"], "window_ends_at")
    if proposed_at < window_start or proposed_at >= window_end:
        raise P134AuthorityError("proposal_outside_ledger_window")
    receipts = _receipt_list(ledger_value.get("receipts"))
    if receipts and proposed_at < _parse_timestamp(receipts[-1]["evaluated_at"], "evaluated_at"):
        raise P134AuthorityError("clock_rollback")

    core = _mapping(contract_value["core"], "core")
    review = _mapping(contract_value["review_receipt"], "review")
    counters_before = deepcopy(_mapping(ledger_value["counters"], "counters"))
    ordered_reasons = _decision_reasons(core, review, proposal_value, counters_before)
    decision = "allowed" if not ordered_reasons else "denied"
    counters_after = _transition_counters(counters_before, proposal_value, decision, ordered_reasons)
    previous_hash = receipts[-1]["receipt_hash"] if receipts else _genesis_hash(ledger_value)
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "receipt_id": stable_hash(
            {
                "schema_version": "p134.receipt_id.v1",
                "contract_hash": contract_value["contract_hash"],
                "proposal_hash": proposal_value["proposal_hash"],
            }
        ),
        "sequence": sequence,
        "request_id": proposal_value["request_id"],
        "proposal": deepcopy(proposal_value),
        "proposal_hash": proposal_value["proposal_hash"],
        "contract_hash": contract_value["contract_hash"],
        "contract_core_hash": core["core_hash"],
        "review_receipt_hash": review["review_receipt_hash"],
        "decision": decision,
        "reasons": ordered_reasons,
        "evaluated_at": proposal_value["proposed_at"],
        "previous_receipt_hash": previous_hash,
        "counters_before": deepcopy(counters_before),
        "counters_after": deepcopy(counters_after),
        "action_authority": zero_authority_counters(),
    }
    receipt["receipt_hash"] = stable_hash(receipt)

    next_ledger = deepcopy(ledger_value)
    next_ledger["receipts"] = [*receipts, receipt]
    next_ledger["next_sequence"] = sequence + 1
    next_ledger["counters"] = deepcopy(counters_after)
    next_ledger["action_authority"] = zero_authority_counters()
    next_ledger["ledger_hash"] = stable_hash(
        {key: value for key, value in next_ledger.items() if key != "ledger_hash"}
    )
    validate_decision_receipt(receipt)
    validate_receipt_ledger(next_ledger, contract=contract_value)
    return EvaluationResult(receipt=receipt, ledger=next_ledger, duplicate=False)


def validate_decision_receipt(receipt: Mapping[str, Any]) -> None:
    value = _mapping(receipt, "receipt")
    _expect_exact_fields(value, _RECEIPT_FIELDS, "receipt")
    if value.get("schema_version") != RECEIPT_SCHEMA_VERSION:
        raise P134AuthorityError("invalid_receipt_schema")
    _validate_self_hash(value, "receipt_hash", "receipt_hash_invalid")
    _require_hash(value.get("receipt_id"), "receipt_id")
    _require_hash(value.get("proposal_hash"), "proposal_hash")
    _require_hash(value.get("contract_hash"), "contract_hash")
    _require_hash(value.get("contract_core_hash"), "contract_core_hash")
    _require_hash(value.get("review_receipt_hash"), "review_receipt_hash")
    _require_hash(value.get("previous_receipt_hash"), "previous_receipt_hash")
    expected_receipt_id = stable_hash(
        {
            "schema_version": "p134.receipt_id.v1",
            "contract_hash": value["contract_hash"],
            "proposal_hash": value["proposal_hash"],
        }
    )
    if value.get("receipt_id") != expected_receipt_id:
        raise P134AuthorityError("receipt_id_mismatch")
    _label(value.get("request_id"), "request_id")
    _bounded_int(value.get("sequence"), "sequence", 1, 1_000_000)
    proposal = _mapping(value.get("proposal"), "proposal")
    validate_proposal(proposal)
    if value.get("proposal_hash") != proposal.get("proposal_hash"):
        raise P134AuthorityError("embedded_proposal_hash_mismatch")
    if value.get("request_id") != proposal.get("request_id") or value.get("sequence") != proposal.get("sequence"):
        raise P134AuthorityError("embedded_proposal_identity_mismatch")
    if value.get("evaluated_at") != proposal.get("proposed_at"):
        raise P134AuthorityError("receipt_evaluated_at_mismatch")
    _parse_timestamp(value.get("evaluated_at"), "evaluated_at")
    decision = value.get("decision")
    if decision not in {"allowed", "denied"}:
        raise P134AuthorityError("invalid_receipt_decision")
    reasons = value.get("reasons")
    if not isinstance(reasons, list) or any(reason not in REASON_ORDER for reason in reasons):
        raise P134AuthorityError("invalid_receipt_reasons")
    expected_order = [reason for reason in REASON_ORDER if reason in set(reasons)]
    if reasons != expected_order or len(reasons) != len(set(reasons)):
        raise P134AuthorityError("invalid_receipt_reason_order")
    if (decision == "allowed") != (not reasons):
        raise P134AuthorityError("receipt_decision_reason_mismatch")
    before = _mapping(value.get("counters_before"), "counters")
    after = _mapping(value.get("counters_after"), "counters")
    _validate_counters(before)
    _validate_counters(after)
    expected_after = _transition_counters(before, proposal, str(decision), list(reasons))
    if dict(after) != expected_after:
        raise P134AuthorityError("receipt_counter_transition_mismatch")
    _validate_action_authority(value.get("action_authority"))


def validate_receipt_ledger(ledger: Mapping[str, Any], *, contract: Mapping[str, Any]) -> None:
    validate_contract(contract)
    value = _mapping(ledger, "ledger")
    _expect_exact_fields(value, _LEDGER_FIELDS, "ledger")
    if value.get("schema_version") != LEDGER_SCHEMA_VERSION:
        raise P134AuthorityError("invalid_ledger_schema")
    _validate_self_hash(value, "ledger_hash", "ledger_hash_invalid")
    if value.get("contract_hash") != contract.get("contract_hash"):
        raise P134AuthorityError("ledger_contract_hash_mismatch")
    start = _parse_timestamp(value.get("window_started_at"), "window_started_at")
    end = _parse_timestamp(value.get("window_ends_at"), "window_ends_at")
    window_seconds = _mapping(_mapping(contract.get("core"), "core").get("budgets"), "budgets").get(
        "window_seconds"
    )
    if end != start + timedelta(seconds=_exact_int(window_seconds, "window_seconds")):
        raise P134AuthorityError("ledger_window_mismatch")
    _validate_action_authority(value.get("action_authority"))
    receipts = _receipt_list(value.get("receipts"))
    expected_counters = _empty_counters()
    expected_previous = _genesis_hash(value)
    request_ids: set[str] = set()
    last_time: datetime | None = None
    core = _mapping(contract.get("core"), "core")
    review = _mapping(contract.get("review_receipt"), "review")
    for expected_sequence, receipt in enumerate(receipts, start=1):
        validate_decision_receipt(receipt)
        if receipt.get("sequence") != expected_sequence:
            raise P134AuthorityError("receipt_sequence_mismatch")
        if receipt.get("contract_hash") != contract.get("contract_hash"):
            raise P134AuthorityError("receipt_contract_hash_mismatch")
        if receipt.get("contract_core_hash") != core.get("core_hash"):
            raise P134AuthorityError("receipt_core_hash_mismatch")
        if receipt.get("review_receipt_hash") != review.get("review_receipt_hash"):
            raise P134AuthorityError("receipt_review_hash_mismatch")
        if receipt.get("previous_receipt_hash") != expected_previous:
            raise P134AuthorityError("receipt_previous_hash_mismatch")
        request_id = str(receipt.get("request_id"))
        if request_id in request_ids:
            raise P134AuthorityError("duplicate_receipt_request_id")
        request_ids.add(request_id)
        evaluated_at = _parse_timestamp(receipt.get("evaluated_at"), "evaluated_at")
        if evaluated_at < start or evaluated_at >= end:
            raise P134AuthorityError("receipt_outside_ledger_window")
        if last_time is not None and evaluated_at < last_time:
            raise P134AuthorityError("receipt_clock_rollback")
        if dict(_mapping(receipt.get("counters_before"), "counters")) != expected_counters:
            raise P134AuthorityError("receipt_counter_before_mismatch")
        proposal = _mapping(receipt.get("proposal"), "proposal")
        expected_reasons = _decision_reasons(core, review, proposal, expected_counters)
        expected_decision = "allowed" if not expected_reasons else "denied"
        if receipt.get("decision") != expected_decision or receipt.get("reasons") != expected_reasons:
            raise P134AuthorityError("receipt_policy_decision_mismatch")
        expected_counters = dict(_mapping(receipt.get("counters_after"), "counters"))
        expected_previous = str(receipt.get("receipt_hash"))
        last_time = evaluated_at
    if value.get("next_sequence") != len(receipts) + 1:
        raise P134AuthorityError("ledger_next_sequence_mismatch")
    final_counters = _mapping(value.get("counters"), "counters")
    if dict(final_counters) != expected_counters:
        raise P134AuthorityError("ledger_counter_mismatch")
    _validate_counters(final_counters)


def _validate_core_semantics(core: Mapping[str, Any]) -> None:
    if core.get("schema_version") != CORE_SCHEMA_VERSION:
        raise P134AuthorityError("invalid_core_schema")
    _label(core.get("contract_id"), "contract_id")
    _bounded_int(core.get("contract_version"), "contract_version", 1, 1_000_000)
    _require_hash(core.get("subject_ref_hash"), "subject_ref_hash")
    level = core.get("max_authority_level")
    if level not in AUTHORITY_LEVELS:
        raise P134AuthorityError("invalid_authority_level")
    if level not in QUALIFIED_LEVELS:
        raise P134AuthorityError("authority_level_not_qualified")
    hosts = _canonical_string_list(core.get("allowed_hosts"), "allowed_hosts")
    methods = _canonical_string_list(core.get("allowed_methods"), "allowed_methods")
    capabilities = _canonical_string_list(core.get("allowed_capabilities"), "allowed_capabilities")
    if level == "OA0_CONTRACT_ONLY":
        if hosts or methods or capabilities:
            raise P134AuthorityError("oa0_allowlist_not_empty")
    else:
        if not hosts or not methods or not capabilities:
            raise P134AuthorityError("oa1_allowlist_empty")
        if any(not _LOCAL_HOST_RE.fullmatch(host) or _FORBIDDEN_LABEL_RE.search(host) for host in hosts):
            raise P134AuthorityError("unsafe_allowed_host")
        if not set(methods) <= LOCAL_METHODS:
            raise P134AuthorityError("invalid_allowed_method")
        if not set(capabilities) <= CAPABILITIES:
            raise P134AuthorityError("invalid_allowed_capability")
    budgets = _mapping(core.get("budgets"), "budgets")
    _expect_exact_fields(budgets, frozenset(_BUDGET_LIMITS), "budget")
    for key, (minimum, maximum) in _BUDGET_LIMITS.items():
        _bounded_int(budgets.get(key), f"budget:{key}", minimum, maximum)
    if budgets["max_single_response_bytes"] > budgets["max_allowed_estimated_response_bytes_per_window"]:
        raise P134AuthorityError("single_response_exceeds_cumulative_budget")
    valid_from = _parse_timestamp(core.get("valid_from"), "valid_from")
    expires_at = _parse_timestamp(core.get("expires_at"), "expires_at")
    if valid_from >= expires_at:
        raise P134AuthorityError("invalid_contract_validity")
    if core.get("default_decision") != "deny":
        raise P134AuthorityError("default_decision_not_deny")
    if type(core.get("kill_switch")) is not bool:
        raise P134AuthorityError("invalid_kill_switch")
    _validate_action_authority(core.get("action_authority"))


def _validate_review_semantics(review: Mapping[str, Any], *, core: Mapping[str, Any]) -> None:
    if review.get("schema_version") != REVIEW_SCHEMA_VERSION:
        raise P134AuthorityError("invalid_review_schema")
    if review.get("contract_core_hash") != core.get("core_hash"):
        raise P134AuthorityError("review_core_hash_mismatch")
    if review.get("decision") not in {"approve", "reject"}:
        raise P134AuthorityError("invalid_review_decision")
    _require_hash(review.get("reviewer_ref_hash"), "reviewer_ref_hash")
    if review.get("limitations") != list(REVIEW_LIMITATIONS):
        raise P134AuthorityError("invalid_review_limitations")
    reviewed_at = _parse_timestamp(review.get("reviewed_at"), "reviewed_at")
    review_expires = _parse_timestamp(review.get("expires_at"), "review_expires_at")
    core_start = _parse_timestamp(core.get("valid_from"), "valid_from")
    core_end = _parse_timestamp(core.get("expires_at"), "expires_at")
    if reviewed_at < core_start or reviewed_at >= core_end:
        raise P134AuthorityError("review_outside_core_validity")
    if review_expires <= reviewed_at or review_expires > core_end:
        raise P134AuthorityError("review_expiry_invalid")


def _validate_proposal_semantics(proposal: Mapping[str, Any]) -> None:
    if proposal.get("schema_version") != PROPOSAL_SCHEMA_VERSION:
        raise P134AuthorityError("invalid_proposal_schema")
    _label(proposal.get("request_id"), "request_id")
    _bounded_int(proposal.get("sequence"), "sequence", 1, 1_000_000)
    _parse_timestamp(proposal.get("proposed_at"), "proposed_at")
    if proposal.get("requested_level") not in AUTHORITY_LEVELS:
        raise P134AuthorityError("invalid_requested_level")
    _require_hash(proposal.get("source_ref_hash"), "source_ref_hash")
    host_label = proposal.get("host_label")
    if not isinstance(host_label, str) or not _LOCAL_HOST_RE.fullmatch(host_label) or _FORBIDDEN_LABEL_RE.search(host_label):
        raise P134AuthorityError("unsafe_host_label")
    if proposal.get("method") not in METHODS:
        raise P134AuthorityError("invalid_method")
    if proposal.get("capability") not in CAPABILITIES:
        raise P134AuthorityError("invalid_capability")
    _bounded_int(proposal.get("estimated_response_bytes"), "estimated_response_bytes", 0, 67_108_864)
    _bounded_int(proposal.get("estimated_records"), "estimated_records", 0, 10_000_000)
    _bounded_int(proposal.get("timeout_ms"), "timeout_ms", 1, 60_000)
    _bounded_int(proposal.get("attempt_number"), "attempt_number", 1, 10)


def _transition_counters(
    before: Mapping[str, Any], proposal: Mapping[str, Any], decision: str, reasons: list[str]
) -> dict[str, Any]:
    result = deepcopy(dict(before))
    result["evaluated_count"] += 1
    if decision == "allowed":
        result["allowed_count"] += 1
        result["allowed_estimated_response_bytes"] += proposal["estimated_response_bytes"]
        result["allowed_estimated_records"] += proposal["estimated_records"]
        _increment_map(result["allowed_host_counts"], str(proposal["host_label"]))
        _increment_map(result["allowed_method_counts"], str(proposal["method"]))
        _increment_map(result["allowed_capability_counts"], str(proposal["capability"]))
    else:
        result["denied_count"] += 1
        if set(reasons) & POLICY_DENIAL_REASONS:
            result["policy_denial_count"] += 1
        if set(reasons) & BUDGET_DENIAL_REASONS:
            result["budget_denial_count"] += 1
    result["unique_allowed_host_count"] = len(result["allowed_host_counts"])
    result["unique_allowed_method_count"] = len(result["allowed_method_counts"])
    result["unique_allowed_capability_count"] = len(result["allowed_capability_counts"])
    _validate_counters(result)
    return result


def _decision_reasons(
    core: Mapping[str, Any],
    review: Mapping[str, Any],
    proposal: Mapping[str, Any],
    counters_before: Mapping[str, Any],
) -> list[str]:
    budgets = _mapping(core.get("budgets"), "budgets")
    proposed_at = _parse_timestamp(proposal.get("proposed_at"), "proposed_at")
    reasons: list[str] = []

    if core.get("max_authority_level") == "OA0_CONTRACT_ONLY":
        reasons.append("contract_only_level")
    if proposed_at < _parse_timestamp(core.get("valid_from"), "valid_from"):
        reasons.append("contract_not_yet_valid")
    if proposed_at >= _parse_timestamp(core.get("expires_at"), "expires_at"):
        reasons.append("contract_expired")
    if review.get("decision") != "approve":
        reasons.append("review_not_approved")
    if proposed_at >= _parse_timestamp(review.get("expires_at"), "review_expires_at"):
        reasons.append("review_expired")
    if core.get("kill_switch") is True:
        reasons.append("kill_switch_active")

    requested_level = str(proposal.get("requested_level"))
    maximum_level = str(core.get("max_authority_level"))
    if AUTHORITY_LEVELS.index(requested_level) > AUTHORITY_LEVELS.index(maximum_level):
        reasons.append("authority_level_exceeds_contract")
    if requested_level not in QUALIFIED_LEVELS:
        reasons.append("authority_level_not_qualified")
    if proposal.get("host_label") not in core.get("allowed_hosts", []):
        reasons.append("host_not_allowlisted")
    if proposal.get("method") not in core.get("allowed_methods", []):
        reasons.append("method_not_allowlisted")
    if proposal.get("method") == "HTTP_GET":
        reasons.append("method_not_qualified")
    if proposal.get("capability") not in core.get("allowed_capabilities", []):
        reasons.append("capability_not_allowlisted")
    if proposal.get("attempt_number") > budgets["max_attempt_number"]:
        reasons.append("attempt_budget_exceeded")
    if proposal.get("estimated_response_bytes") > budgets["max_single_response_bytes"]:
        reasons.append("single_response_byte_budget_exceeded")
    if proposal.get("timeout_ms") > budgets["max_timeout_ms"]:
        reasons.append("timeout_budget_exceeded")

    if not reasons:
        if counters_before["allowed_count"] + 1 > budgets["max_allowed_requests_per_window"]:
            reasons.append("allowed_request_budget_exceeded")
        if (
            counters_before["allowed_estimated_response_bytes"] + proposal["estimated_response_bytes"]
            > budgets["max_allowed_estimated_response_bytes_per_window"]
        ):
            reasons.append("cumulative_byte_budget_exceeded")
        if (
            counters_before["allowed_estimated_records"] + proposal["estimated_records"]
            > budgets["max_allowed_estimated_records_per_window"]
        ):
            reasons.append("cumulative_record_budget_exceeded")
        if _would_add_unique(counters_before["allowed_host_counts"], proposal["host_label"]) > budgets[
            "max_unique_hosts_per_window"
        ]:
            reasons.append("host_budget_exceeded")
        if _would_add_unique(counters_before["allowed_method_counts"], proposal["method"]) > budgets[
            "max_unique_methods_per_window"
        ]:
            reasons.append("method_budget_exceeded")
        if _would_add_unique(counters_before["allowed_capability_counts"], proposal["capability"]) > budgets[
            "max_unique_capabilities_per_window"
        ]:
            reasons.append("capability_budget_exceeded")

    reason_set = set(reasons)
    return [reason for reason in REASON_ORDER if reason in reason_set]


def _empty_counters() -> dict[str, Any]:
    return {
        "evaluated_count": 0,
        "allowed_count": 0,
        "denied_count": 0,
        "allowed_estimated_response_bytes": 0,
        "allowed_estimated_records": 0,
        "budget_denial_count": 0,
        "policy_denial_count": 0,
        "unique_allowed_host_count": 0,
        "unique_allowed_method_count": 0,
        "unique_allowed_capability_count": 0,
        "allowed_host_counts": {},
        "allowed_method_counts": {},
        "allowed_capability_counts": {},
    }


def _validate_counters(counters: Mapping[str, Any]) -> None:
    _expect_exact_fields(counters, _COUNTER_FIELDS, "counter")
    for key in _COUNTER_SCALAR_FIELDS:
        _bounded_int(counters.get(key), f"counter:{key}", 0, 10**15)
    maps = {
        "allowed_host_counts": _LOCAL_HOST_RE,
        "allowed_method_counts": None,
        "allowed_capability_counts": None,
    }
    for key, pattern in maps.items():
        values = _mapping(counters.get(key), key)
        for item_key, item_value in values.items():
            if not isinstance(item_key, str):
                raise P134AuthorityError(f"invalid_counter_map_key:{key}")
            if pattern is not None and not pattern.fullmatch(item_key):
                raise P134AuthorityError(f"invalid_counter_map_key:{key}")
            if key == "allowed_method_counts" and item_key not in LOCAL_METHODS:
                raise P134AuthorityError(f"invalid_counter_map_key:{key}")
            if key == "allowed_capability_counts" and item_key not in CAPABILITIES:
                raise P134AuthorityError(f"invalid_counter_map_key:{key}")
            _bounded_int(item_value, f"counter_map:{key}", 1, 10**15)
    if counters["evaluated_count"] != counters["allowed_count"] + counters["denied_count"]:
        raise P134AuthorityError("counter_evaluation_mismatch")
    if sum(_mapping(counters["allowed_host_counts"], "allowed_host_counts").values()) != counters["allowed_count"]:
        raise P134AuthorityError("counter_host_sum_mismatch")
    if sum(_mapping(counters["allowed_method_counts"], "allowed_method_counts").values()) != counters["allowed_count"]:
        raise P134AuthorityError("counter_method_sum_mismatch")
    if sum(_mapping(counters["allowed_capability_counts"], "allowed_capability_counts").values()) != counters["allowed_count"]:
        raise P134AuthorityError("counter_capability_sum_mismatch")
    if counters["unique_allowed_host_count"] != len(counters["allowed_host_counts"]):
        raise P134AuthorityError("counter_unique_host_mismatch")
    if counters["unique_allowed_method_count"] != len(counters["allowed_method_counts"]):
        raise P134AuthorityError("counter_unique_method_mismatch")
    if counters["unique_allowed_capability_count"] != len(counters["allowed_capability_counts"]):
        raise P134AuthorityError("counter_unique_capability_mismatch")
    if counters["policy_denial_count"] > counters["denied_count"] or counters["budget_denial_count"] > counters[
        "denied_count"
    ]:
        raise P134AuthorityError("counter_denial_mismatch")
    if counters["denied_count"] and counters["policy_denial_count"] + counters["budget_denial_count"] < counters[
        "denied_count"
    ]:
        raise P134AuthorityError("counter_denial_mismatch")


def _validate_action_authority(value: Any) -> None:
    try:
        validate_exact_zero_authority(value)
    except ValueError as exc:
        raise P134AuthorityError(str(exc)) from exc


def _genesis_hash(ledger: Mapping[str, Any]) -> str:
    return stable_hash(
        {
            "schema_version": GENESIS_SCHEMA_VERSION,
            "contract_hash": ledger["contract_hash"],
            "window_started_at": ledger["window_started_at"],
            "window_ends_at": ledger["window_ends_at"],
        }
    )


def _increment_map(values: dict[str, int], key: str) -> None:
    values[key] = values.get(key, 0) + 1


def _would_add_unique(values: Mapping[str, Any], key: Any) -> int:
    return len(values) + (0 if key in values else 1)


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise P134AuthorityError(f"invalid_{label}")
    return value


def _receipt_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise P134AuthorityError("invalid_receipts")
    return [dict(item) for item in value]


def _expect_exact_fields(value: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    actual = {str(key) for key in value}
    extra = sorted(actual - expected)
    if extra:
        raise P134AuthorityError(f"unexpected_{label}_field:{extra[0]}")
    missing = sorted(expected - actual)
    if missing:
        raise P134AuthorityError(f"missing_{label}_field:{missing[0]}")


def _sorted_unique_strings(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise P134AuthorityError(f"invalid_{label}")
    if len(value) != len(set(value)):
        raise P134AuthorityError(f"duplicate_{label}")
    return sorted(value)


def _canonical_string_list(value: Any, label: str) -> list[str]:
    result = _sorted_unique_strings(value, label)
    if value != result:
        raise P134AuthorityError(f"noncanonical_{label}")
    return result


def _label(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _LABEL_RE.fullmatch(value) or _FORBIDDEN_LABEL_RE.search(value):
        raise P134AuthorityError(f"invalid_{label}")
    return value


def _require_hash(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _HASH_RE.fullmatch(value):
        raise P134AuthorityError(f"invalid_{label}")
    return value


def _exact_int(value: Any, label: str) -> int:
    if type(value) is not int:
        raise P134AuthorityError(f"invalid_{label}")
    return value


def _bounded_int(value: Any, label: str, minimum: int, maximum: int) -> int:
    integer = _exact_int(value, label)
    if integer < minimum or integer > maximum:
        raise P134AuthorityError(f"invalid_{label}")
    return integer


def _parse_timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value):
        raise P134AuthorityError(f"invalid_{label}")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise P134AuthorityError(f"invalid_{label}") from exc
    if _format_timestamp(parsed) != value:
        raise P134AuthorityError(f"invalid_{label}")
    return parsed


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _validate_self_hash(value: Mapping[str, Any], field: str, reason: str) -> None:
    claimed = value.get(field)
    _require_hash(claimed, field)
    unsigned = {key: item for key, item in value.items() if key != field}
    if claimed != stable_hash(unsigned):
        raise P134AuthorityError(reason)


__all__ = [
    "AUTHORITY_LEVELS",
    "CAPABILITIES",
    "CONTRACT_SCHEMA_VERSION",
    "CORE_SCHEMA_VERSION",
    "EvaluationResult",
    "LEDGER_SCHEMA_VERSION",
    "LOCAL_METHODS",
    "METHODS",
    "P134AuthorityError",
    "PROPOSAL_SCHEMA_VERSION",
    "REASON_ORDER",
    "RECEIPT_SCHEMA_VERSION",
    "REVIEW_SCHEMA_VERSION",
    "build_contract",
    "build_contract_core",
    "build_proposal",
    "build_review_receipt",
    "evaluate_proposal",
    "new_receipt_ledger",
    "validate_contract",
    "validate_contract_core",
    "validate_decision_receipt",
    "validate_proposal",
    "validate_receipt_ledger",
    "validate_review_receipt",
]
