from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p137_classification import build_classification_record
from app.services.p137_ledger import (
    P137LedgerError,
    advance_investigation_ledger,
    new_investigation_ledger,
    validate_investigation_ledger,
)
from app.services.p137_requests import build_request_budget, execute_evidence_request


def _maps() -> dict[str, dict[str, int]]:
    return {
        "counters": {"incident_count": 0},
        "authority_counters": {"network_call_count": 0},
        "runtime_activity": {"ledger_write_count": 0},
        "evaluator_activity": {"runner_invocation_count": 0},
        "resource_usage": {"wall_time_ms": 0},
    }


def test_ledger_cas_chains_incident_request_and_classification() -> None:
    ledger = new_investigation_ledger(config_hash=stable_hash({"config": 1}), **_maps())
    incident: dict[str, Any] = {"incident_sequence": 1, "incident_hash": stable_hash({"incident": 1})}
    request = execute_evidence_request(
        incident_id="incident-a",
        incident_hash=incident["incident_hash"],
        request_sequence=1,
        catalog_name="summarize_log_preview_hashes",
        parameters={"limit": 1},
        atoms=[],
        budget=build_request_budget(),
    ).record
    classification = build_classification_record(
        incident_id="incident-a",
        classification_sequence=1,
        classification="aborted_fail_closed",
        decided_at="2026-01-01T00:00:00Z",
        top_hypothesis=None,
        authority_counters={"network_call_count": 0},
        runtime_activity={"classification_write_count": 1},
        resource_usage={"wall_time_ms": 1},
    )
    advanced = advance_investigation_ledger(
        ledger,
        expected_previous_hash=ledger["ledger_hash"],
        incidents=[incident],
        requests=[request],
        classifications=[classification],
        counters={"incident_count": 1},
        runtime_activity={"ledger_write_count": 1},
    )
    assert advanced["previous_ledger_hash"] == ledger["ledger_hash"]
    assert advanced["next_incident_sequence"] == 2
    assert advanced["attempted_request_hashes"] == [request["attempted_request_hash"]]
    validate_investigation_ledger(advanced, prior=ledger, incidents=[incident], requests=[request], classifications=[classification])


def test_cas_conflict_and_rehashed_forged_membership_fail_closed() -> None:
    ledger = new_investigation_ledger(config_hash=stable_hash({"config": 1}), **_maps())
    with pytest.raises(P137LedgerError, match="ledger_cas_predecessor_mismatch"):
        advance_investigation_ledger(ledger, expected_previous_hash=stable_hash({"wrong": 1}))
    forged = deepcopy(ledger)
    forged["counters"]["incident_count"] = 99
    forged["ledger_hash"] = stable_hash({key: value for key, value in forged.items() if key != "ledger_hash"})
    # A self-consistent counter change is structurally valid at genesis; attaching
    # it to a predecessor is what makes fabricated transition evidence invalid.
    validate_investigation_ledger(forged)
    with pytest.raises(P137LedgerError):
        validate_investigation_ledger(forged, prior=ledger)


def test_nonzero_authority_and_duplicate_attempts_are_rejected() -> None:
    with pytest.raises(P137LedgerError, match="nonzero_authority_counters"):
        new_investigation_ledger(
            config_hash=stable_hash({"config": 1}),
            **{**_maps(), "authority_counters": {"network_call_count": 1}},
        )
