from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p118_operation_contract import (
    P118ContractError,
    build_operation_envelope,
    exact_zero_authority_counters,
)


def _hash(suffix: str) -> str:
    return "sha256:" + suffix * 64


def _envelope(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "operation_id": "op-p118-001",
        "schema_version": "p118.operation_envelope.v1",
        "p117_decision_episode_id": "episode-p118-001",
        "p117_selected_action_pack_id": "pack-local-001",
        "p115_action_pack_digest": _hash("1"),
        "fixture_target_id": "local:fixture:checkout-api",
        "action_level": "L3",
        "precondition_refs": ["precondition:cpu-saturated"],
        "validation_plan_ref": "validation:mock-healthcheck",
        "rollback_plan_ref": "rollback:mock-revert",
        "approval_receipt": {"receipt_id": "approval-local", "policy_hash": _hash("2")},
        "lease_receipt": {"receipt_id": "lease-worker-a", "owner_id": "worker-a"},
        "wal_position": 0,
        "cas_version": 0,
        "idempotency_key": "idem:op-p118-001",
        "authority_counter_snapshot": exact_zero_authority_counters(),
    }
    payload.update(overrides)
    return payload


def test_operation_envelope_is_immutable_deterministic_and_local_l3_max() -> None:
    envelope = build_operation_envelope(_envelope())
    payload = envelope.to_dict()

    assert payload["schema_version"] == "p118.operation_envelope.v1"
    assert payload["action_level"] == "L3"
    assert payload["terminal_statuses"] == [
        "aborted_fail_closed",
        "expired",
        "orphaned_recovered",
        "rejected",
        "rollback_failed",
        "rolled_back",
        "succeeded",
        "validation_failed",
    ]
    assert payload["envelope_hash"] == stable_hash({key: value for key, value in payload.items() if key != "envelope_hash"})
    assert build_operation_envelope(_envelope()).to_dict()["envelope_hash"] == payload["envelope_hash"]
    with pytest.raises(FrozenInstanceError):
        envelope.schema_version = "p118.operation_envelope.v2"  # type: ignore[misc]
    with pytest.raises(TypeError):
        envelope.payload["operation_id"] = "mutated"  # type: ignore[index]


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        ({"operation_id": ""}, "missing_operation_id"),
        ({"schema_version": "p118.operation_envelope.v2"}, "unsupported_schema_version"),
        ({"fixture_target_id": "production:cluster:checkout"}, "forbidden_authority_text"),
        ({"action_level": "L4"}, "action_level_above_l3"),
        ({"shell_text": "kubectl delete pod checkout"}, "forbidden_authority_field"),
        ({"online_policy_write": {"enabled": True}}, "forbidden_authority_field"),
    ],
)
def test_operation_contract_rejects_missing_fields_authority_and_l4(mutation: dict[str, object], error: str) -> None:
    with pytest.raises(P118ContractError, match=error):
        build_operation_envelope(_envelope(**mutation))


def test_operation_contract_requires_exact_zero_authority_counters() -> None:
    payload = _envelope()
    counters = copy.deepcopy(payload["authority_counter_snapshot"])
    assert isinstance(counters, dict)
    counters["shell"] = 1
    payload["authority_counter_snapshot"] = counters

    with pytest.raises(P118ContractError, match="authority_counter_nonzero:shell"):
        build_operation_envelope(payload)

    payload = _envelope()
    extra = copy.deepcopy(payload["authority_counter_snapshot"])
    assert isinstance(extra, dict)
    extra["untracked_executor"] = 0
    payload["authority_counter_snapshot"] = extra
    with pytest.raises(P118ContractError, match="unknown_authority_counter"):
        build_operation_envelope(payload)
