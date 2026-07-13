from __future__ import annotations

import builtins
import json
import os
import socket
import subprocess
from copy import deepcopy
from typing import Any

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p121_signals import zero_authority_counters
from app.services.p134_observation_authority import (
    P134AuthorityError,
    build_contract,
    build_contract_core,
    build_proposal,
    build_review_receipt,
    evaluate_proposal,
    new_receipt_ledger,
    validate_contract,
    validate_decision_receipt,
    validate_receipt_ledger,
)


def _budgets(**overrides: int) -> dict[str, int]:
    values = {
        "window_seconds": 3600,
        "max_allowed_requests_per_window": 8,
        "max_allowed_estimated_response_bytes_per_window": 10_000,
        "max_allowed_estimated_records_per_window": 1_000,
        "max_unique_hosts_per_window": 3,
        "max_unique_methods_per_window": 3,
        "max_unique_capabilities_per_window": 3,
        "max_single_response_bytes": 4_000,
        "max_timeout_ms": 5_000,
        "max_attempt_number": 3,
    }
    values.update(overrides)
    return values


def _core_data(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "contract_id": "night-watch",
        "contract_version": 1,
        "subject_ref_hash": stable_hash({"subject": "local-monitor"}),
        "max_authority_level": "OA1_LOCAL_ARTIFACT",
        "allowed_hosts": ["local-artifact.logs", "local-artifact.metrics", "local-artifact.traces"],
        "allowed_methods": ["LOCAL_LIST_DIR", "LOCAL_READ_FILE", "LOCAL_STAT"],
        "allowed_capabilities": [
            "telemetry.logs.read",
            "telemetry.metrics.read",
            "telemetry.traces.read",
        ],
        "budgets": _budgets(),
        "valid_from": "2026-07-13T00:00:00Z",
        "expires_at": "2026-07-14T00:00:00Z",
        "default_decision": "deny",
        "kill_switch": False,
        "action_authority": zero_authority_counters(),
    }
    values.update(overrides)
    return values


def _contract(*, review_decision: str = "approve", **core_overrides: Any) -> dict[str, Any]:
    core = build_contract_core(_core_data(**core_overrides))
    review = build_review_receipt(
        core,
        {
            "decision": review_decision,
            "reviewer_ref_hash": stable_hash({"reviewer": "independent-reviewer"}),
            "reviewed_at": "2026-07-13T00:00:01Z",
            "expires_at": "2026-07-13T23:59:59Z",
        },
    )
    return build_contract(core, review)


def _proposal(sequence: int = 1, **overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "request_id": f"request-{sequence}",
        "sequence": sequence,
        "proposed_at": f"2026-07-13T00:{10 + sequence:02d}:00Z",
        "requested_level": "OA1_LOCAL_ARTIFACT",
        "source_ref_hash": stable_hash({"source": f"source-{sequence}"}),
        "host_label": "local-artifact.metrics",
        "method": "LOCAL_READ_FILE",
        "capability": "telemetry.metrics.read",
        "estimated_response_bytes": 100,
        "estimated_records": 10,
        "timeout_ms": 1_000,
        "attempt_number": 1,
    }
    values.update(overrides)
    return build_proposal(values)


def _ledger(contract: dict[str, Any]) -> dict[str, Any]:
    return new_receipt_ledger(contract, window_started_at="2026-07-13T00:00:00Z")


def _rehash(payload: dict[str, Any], field: str) -> None:
    payload[field] = stable_hash({key: value for key, value in payload.items() if key != field})


def test_contract_core_is_canonical_hash_bound_and_action_separated() -> None:
    core = build_contract_core(_core_data())

    assert core["schema_version"] == "p134.observation_authority_core.v1"
    assert core["allowed_hosts"] == sorted(core["allowed_hosts"])
    assert core["allowed_methods"] == sorted(core["allowed_methods"])
    assert core["allowed_capabilities"] == sorted(core["allowed_capabilities"])
    assert core["core_hash"] == stable_hash({key: value for key, value in core.items() if key != "core_hash"})
    assert all(type(value) is int and value == 0 for value in core["action_authority"].values())


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ({"unexpected": "field"}, "unexpected_core_field"),
        ({"max_authority_level": "OA2_PROVIDER_SHAPED_LOCAL_EXPORT"}, "authority_level_not_qualified"),
        ({"contract_version": True}, "invalid_contract_version"),
        ({"allowed_hosts": ["https://metrics.example"]}, "unsafe_allowed_host"),
        ({"subject_ref_hash": "api_key=actual-secret-value"}, "invalid_subject_ref_hash"),
    ],
)
def test_contract_core_rejects_unknown_future_boolean_network_and_secret_shapes(
    mutation: dict[str, Any], reason: str
) -> None:
    with pytest.raises(P134AuthorityError, match=reason):
        build_contract_core(_core_data(**mutation))


def test_contract_core_rejects_boolean_budget_and_nonzero_action_authority() -> None:
    boolean_budget = _budgets(max_timeout_ms=True)
    with pytest.raises(P134AuthorityError, match="invalid_budget:max_timeout_ms"):
        build_contract_core(_core_data(budgets=boolean_budget))

    authority = zero_authority_counters()
    authority["live_connector_call_count"] = 1
    with pytest.raises(P134AuthorityError, match="live_connector_call_count_nonzero"):
        build_contract_core(_core_data(action_authority=authority))


def test_oa0_requires_empty_allowlists_and_oa1_requires_nonempty_allowlists() -> None:
    oa0 = build_contract_core(
        _core_data(
            max_authority_level="OA0_CONTRACT_ONLY",
            allowed_hosts=[],
            allowed_methods=[],
            allowed_capabilities=[],
        )
    )
    assert oa0["max_authority_level"] == "OA0_CONTRACT_ONLY"

    with pytest.raises(P134AuthorityError, match="oa0_allowlist_not_empty"):
        build_contract_core(_core_data(max_authority_level="OA0_CONTRACT_ONLY"))
    with pytest.raises(P134AuthorityError, match="oa1_allowlist_empty"):
        build_contract_core(_core_data(allowed_capabilities=[]))


def test_review_and_contract_bind_exact_core_and_reject_tamper() -> None:
    contract = _contract()
    validate_contract(contract)

    tampered = deepcopy(contract)
    tampered["review_receipt"]["contract_core_hash"] = stable_hash({"other": "core"})
    _rehash(tampered["review_receipt"], "review_receipt_hash")
    _rehash(tampered, "contract_hash")
    with pytest.raises(P134AuthorityError, match="review_core_hash_mismatch"):
        validate_contract(tampered)


def test_review_time_and_exact_limitations_fail_closed() -> None:
    core = build_contract_core(_core_data())
    with pytest.raises(P134AuthorityError, match="review_outside_core_validity"):
        build_review_receipt(
            core,
            {
                "decision": "approve",
                "reviewer_ref_hash": stable_hash({"reviewer": "r"}),
                "reviewed_at": "2026-07-12T23:59:59Z",
                "expires_at": "2026-07-13T23:59:59Z",
            },
        )


def test_proposal_schema_rejects_unknown_fields_urls_and_unrecognized_methods() -> None:
    with pytest.raises(P134AuthorityError, match="unexpected_proposal_field"):
        _proposal(extra="value")
    with pytest.raises(P134AuthorityError, match="unsafe_host_label"):
        _proposal(host_label="https://metrics.example")
    with pytest.raises(P134AuthorityError, match="invalid_method"):
        _proposal(method="POST")


def test_allowed_proposal_emits_genesis_linked_receipt_and_exact_counters() -> None:
    contract = _contract()
    ledger = _ledger(contract)
    result = evaluate_proposal(contract, _proposal(), ledger)

    assert result.duplicate is False
    assert result.receipt["decision"] == "allowed"
    assert result.receipt["reasons"] == []
    assert result.receipt["proposal"] == _proposal()
    assert result.receipt["proposal_hash"] == result.receipt["proposal"]["proposal_hash"]
    expected_genesis = stable_hash(
        {
            "schema_version": "p134.ledger_genesis.v1",
            "contract_hash": contract["contract_hash"],
            "window_started_at": ledger["window_started_at"],
            "window_ends_at": ledger["window_ends_at"],
        }
    )
    assert result.receipt["previous_receipt_hash"] == expected_genesis
    assert result.ledger["counters"]["evaluated_count"] == 1
    assert result.ledger["counters"]["allowed_count"] == 1
    assert result.ledger["counters"]["denied_count"] == 0
    assert result.ledger["counters"]["allowed_estimated_response_bytes"] == 100
    assert result.ledger["counters"]["allowed_estimated_records"] == 10
    validate_decision_receipt(result.receipt)
    validate_receipt_ledger(result.ledger, contract=contract)


def test_embedded_proposal_tamper_is_rejected_even_when_outer_hashes_are_recomputed() -> None:
    contract = _contract()
    result = evaluate_proposal(contract, _proposal(), _ledger(contract))
    tampered = deepcopy(result.ledger)
    tampered_receipt = tampered["receipts"][0]
    tampered_receipt["proposal"]["estimated_records"] = 999
    _rehash(tampered_receipt["proposal"], "proposal_hash")
    tampered_receipt["proposal_hash"] = tampered_receipt["proposal"]["proposal_hash"]
    tampered_receipt["receipt_id"] = stable_hash(
        {
            "schema_version": "p134.receipt_id.v1",
            "contract_hash": contract["contract_hash"],
            "proposal_hash": tampered_receipt["proposal_hash"],
        }
    )
    _rehash(tampered_receipt, "receipt_hash")
    _rehash(tampered, "ledger_hash")

    with pytest.raises(P134AuthorityError, match="receipt_counter_transition_mismatch"):
        validate_receipt_ledger(tampered, contract=contract)


def test_duplicate_returns_original_receipt_and_byte_identical_ledger() -> None:
    contract = _contract()
    first = evaluate_proposal(contract, _proposal(), _ledger(contract))
    duplicate = evaluate_proposal(contract, _proposal(), first.ledger)

    assert duplicate.duplicate is True
    assert duplicate.receipt == first.receipt
    assert duplicate.ledger == first.ledger
    assert "duplicate_count" not in duplicate.ledger["counters"]

    with pytest.raises(P134AuthorityError, match="request_id_reuse_conflict"):
        evaluate_proposal(
            contract,
            _proposal(capability="telemetry.logs.read"),
            first.ledger,
        )


def test_policy_denial_consumes_only_denial_accounting() -> None:
    contract = _contract()
    result = evaluate_proposal(
        contract,
        _proposal(host_label="local-artifact.unknown"),
        _ledger(contract),
    )

    counters = result.ledger["counters"]
    assert result.receipt["decision"] == "denied"
    assert result.receipt["reasons"] == ["host_not_allowlisted"]
    assert counters["evaluated_count"] == 1
    assert counters["denied_count"] == 1
    assert counters["policy_denial_count"] == 1
    assert counters["budget_denial_count"] == 0
    assert counters["allowed_count"] == 0
    assert counters["allowed_estimated_response_bytes"] == 0
    assert counters["allowed_estimated_records"] == 0


def test_allowed_request_cumulative_byte_and_record_budgets_are_enforced() -> None:
    contract = _contract(
        budgets=_budgets(
            max_allowed_requests_per_window=1,
            max_allowed_estimated_response_bytes_per_window=100,
            max_allowed_estimated_records_per_window=10,
            max_single_response_bytes=100,
        )
    )
    first = evaluate_proposal(contract, _proposal(), _ledger(contract))
    second = evaluate_proposal(contract, _proposal(2), first.ledger)

    assert second.receipt["decision"] == "denied"
    assert second.receipt["reasons"] == [
        "allowed_request_budget_exceeded",
        "cumulative_byte_budget_exceeded",
        "cumulative_record_budget_exceeded",
    ]
    assert second.ledger["counters"]["allowed_count"] == 1
    assert second.ledger["counters"]["budget_denial_count"] == 1


@pytest.mark.parametrize(
    ("budget_override", "second_override", "reason"),
    [
        ({"max_unique_hosts_per_window": 1}, {"host_label": "local-artifact.logs"}, "host_budget_exceeded"),
        ({"max_unique_methods_per_window": 1}, {"method": "LOCAL_STAT"}, "method_budget_exceeded"),
        (
            {"max_unique_capabilities_per_window": 1},
            {"capability": "telemetry.logs.read"},
            "capability_budget_exceeded",
        ),
    ],
)
def test_unique_host_method_and_capability_budgets_are_reachable_without_io(
    budget_override: dict[str, int], second_override: dict[str, Any], reason: str
) -> None:
    contract = _contract(budgets=_budgets(**budget_override))
    first = evaluate_proposal(contract, _proposal(), _ledger(contract))
    second = evaluate_proposal(contract, _proposal(2, **second_override), first.ledger)
    assert reason in second.receipt["reasons"]
    assert second.receipt["decision"] == "denied"


def test_single_response_timeout_and_attempt_budgets_apply_to_every_proposal() -> None:
    contract = _contract(
        budgets=_budgets(max_single_response_bytes=50, max_timeout_ms=500, max_attempt_number=1)
    )
    result = evaluate_proposal(
        contract,
        _proposal(estimated_response_bytes=100, timeout_ms=1_000, attempt_number=2),
        _ledger(contract),
    )

    assert result.receipt["reasons"] == [
        "attempt_budget_exceeded",
        "single_response_byte_budget_exceeded",
        "timeout_budget_exceeded",
    ]
    assert result.ledger["counters"]["budget_denial_count"] == 1


@pytest.mark.parametrize(
    ("contract_kwargs", "proposal_kwargs", "reason"),
    [
        ({}, {"proposed_at": "2026-07-12T23:59:59Z"}, "contract_not_yet_valid"),
        ({}, {"proposed_at": "2026-07-13T23:59:59Z"}, "review_expired"),
        ({"kill_switch": True}, {}, "kill_switch_active"),
        ({"review_decision": "reject"}, {}, "review_not_approved"),
        (
            {},
            {"requested_level": "OA2_PROVIDER_SHAPED_LOCAL_EXPORT"},
            "authority_level_not_qualified",
        ),
        ({}, {"method": "HTTP_GET"}, "method_not_qualified"),
    ],
)
def test_time_review_kill_switch_and_future_levels_deny_without_execution(
    contract_kwargs: dict[str, Any], proposal_kwargs: dict[str, Any], reason: str
) -> None:
    review_decision = str(contract_kwargs.pop("review_decision", "approve"))
    contract = _contract(review_decision=review_decision, **contract_kwargs)
    if reason == "contract_not_yet_valid":
        ledger_start = "2026-07-12T23:00:00Z"
    elif reason == "review_expired":
        ledger_start = "2026-07-13T23:00:00Z"
    else:
        ledger_start = "2026-07-13T00:00:00Z"
    ledger = new_receipt_ledger(contract, window_started_at=ledger_start)
    result = evaluate_proposal(contract, _proposal(**proposal_kwargs), ledger)
    assert reason in result.receipt["reasons"]
    assert result.receipt["decision"] == "denied"


@pytest.mark.parametrize(
    ("proposal", "reason"),
    [
        (_proposal(sequence=2), "sequence_mismatch"),
        (_proposal(proposed_at="2026-07-13T01:00:00Z"), "proposal_outside_ledger_window"),
    ],
)
def test_structural_sequence_and_window_errors_leave_ledger_unchanged(
    proposal: dict[str, Any], reason: str
) -> None:
    contract = _contract()
    ledger = _ledger(contract)
    before = deepcopy(ledger)
    with pytest.raises(P134AuthorityError, match=reason):
        evaluate_proposal(contract, proposal, ledger)
    assert ledger == before


def test_clock_rollback_leaves_existing_ledger_unchanged() -> None:
    contract = _contract()
    first = evaluate_proposal(
        contract,
        _proposal(proposed_at="2026-07-13T00:30:00Z"),
        _ledger(contract),
    )
    before = deepcopy(first.ledger)
    with pytest.raises(P134AuthorityError, match="clock_rollback"):
        evaluate_proposal(
            contract,
            _proposal(2, proposed_at="2026-07-13T00:29:59Z"),
            first.ledger,
        )
    assert first.ledger == before


def test_ledger_validation_rejects_semantic_counter_tamper_and_reorder() -> None:
    contract = _contract()
    first = evaluate_proposal(contract, _proposal(), _ledger(contract))
    second = evaluate_proposal(contract, _proposal(2), first.ledger)

    tampered = deepcopy(second.ledger)
    tampered["counters"]["allowed_count"] = 99
    _rehash(tampered, "ledger_hash")
    with pytest.raises(P134AuthorityError, match="ledger_counter_mismatch"):
        validate_receipt_ledger(tampered, contract=contract)

    reordered = deepcopy(second.ledger)
    reordered["receipts"].reverse()
    _rehash(reordered, "ledger_hash")
    with pytest.raises(P134AuthorityError, match="receipt_sequence_mismatch"):
        validate_receipt_ledger(reordered, contract=contract)


def test_ledger_validation_rejects_rehashed_policy_decision_forgery() -> None:
    contract = _contract()
    allowed = evaluate_proposal(contract, _proposal(), _ledger(contract))
    forged = deepcopy(allowed.ledger)
    receipt = forged["receipts"][0]
    proposal = receipt["proposal"]
    proposal["host_label"] = "local-artifact.unknown"
    _rehash(proposal, "proposal_hash")
    receipt["proposal_hash"] = proposal["proposal_hash"]
    receipt["receipt_id"] = stable_hash(
        {
            "schema_version": "p134.receipt_id.v1",
            "contract_hash": contract["contract_hash"],
            "proposal_hash": proposal["proposal_hash"],
        }
    )
    receipt["counters_after"]["allowed_host_counts"] = {"local-artifact.unknown": 1}
    forged["counters"] = deepcopy(receipt["counters_after"])
    _rehash(receipt, "receipt_hash")
    _rehash(forged, "ledger_hash")

    with pytest.raises(P134AuthorityError, match="receipt_policy_decision_mismatch"):
        validate_receipt_ledger(forged, contract=contract)


def test_ledger_validation_rejects_rehashed_receipt_id_forgery() -> None:
    contract = _contract()
    result = evaluate_proposal(contract, _proposal(), _ledger(contract))
    forged = deepcopy(result.ledger)
    receipt = forged["receipts"][0]
    receipt["receipt_id"] = stable_hash({"forged": "receipt-id"})
    _rehash(receipt, "receipt_hash")
    _rehash(forged, "ledger_hash")

    with pytest.raises(P134AuthorityError, match="receipt_id_mismatch"):
        validate_receipt_ledger(forged, contract=contract)


def test_pure_evaluation_performs_no_file_env_network_or_subprocess_io(monkeypatch: pytest.MonkeyPatch) -> None:
    contract = _contract()
    proposal = _proposal()
    ledger = _ledger(contract)

    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("forbidden I/O invoked")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(os, "getenv", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)

    result = evaluate_proposal(contract, proposal, ledger)
    assert result.receipt["decision"] == "allowed"


def test_serialized_contract_proposal_receipt_and_ledger_contain_no_raw_identity_or_endpoint() -> None:
    contract = _contract()
    proposal = _proposal()
    result = evaluate_proposal(contract, proposal, _ledger(contract))
    serialized = json.dumps(
        {"contract": contract, "proposal": proposal, "receipt": result.receipt, "ledger": result.ledger},
        sort_keys=True,
    )

    for forbidden in (
        "local-monitor",
        "independent-reviewer",
        "https://",
        "http://",
        "Authorization",
        "Bearer ",
        "api_key=",
        "/Users/",
    ):
        assert forbidden not in serialized
