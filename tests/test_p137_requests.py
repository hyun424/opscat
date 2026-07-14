from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p137_requests import (
    ALLOWED_REQUEST_CATALOG,
    P137RequestError,
    build_request_budget,
    execute_evidence_request,
    validate_evidence_request,
)


def _atom(index: int = 1) -> dict[str, object]:
    return {
        "atom_id": f"evidence-{index}",
        "atom_hash": stable_hash({"atom": index}),
        "content_hash": stable_hash({"content": index}),
        "entity_ref_hash": stable_hash({"entity": 1}),
        "label_hashes": [stable_hash({"label": "api"})],
        "provider": "prometheus",
        "risk_flags": [],
        "signal_family": "metrics",
        "system_id": "system-a",
        "window": {"start": "2026-01-01T00:00:00Z", "end": "2026-01-01T00:05:00Z"},
        "state_reason_codes": [],
        "redacted_preview_hash": None,
        "topology_ref_hashes": [],
        "signal_name": "error_rate",
        "numeric_value": float(index),
    }


def test_catalog_is_exact_lexical_and_local_selection_is_self_hashed() -> None:
    assert len(ALLOWED_REQUEST_CATALOG) == 15
    assert tuple(sorted(ALLOWED_REQUEST_CATALOG)) == ALLOWED_REQUEST_CATALOG
    atom = _atom()
    result = execute_evidence_request(
        incident_id="incident-a",
        incident_hash=stable_hash({"incident": "a"}),
        request_sequence=1,
        catalog_name="select_records_by_system_id",
        parameters={"system_id": "system-a", "limit": 10},
        atoms=[atom],
        budget=build_request_budget(),
    )
    assert result.duplicate is False
    assert result.record["result_summary"]["matched_atom_hashes"] == [atom["atom_hash"]]
    assert result.record["runtime_activity"]["external_call_count"] == 0
    validate_evidence_request(result.record)


def test_equivalent_attempt_reuses_durable_bytes_and_conflict_is_rejected() -> None:
    atom = _atom()
    kwargs: dict[str, Any] = dict(
        incident_id="incident-a",
        incident_hash=stable_hash({"incident": "a"}),
        request_sequence=1,
        catalog_name="fetch_record_by_evidence_id",
        parameters={"evidence_id": "evidence-1", "limit": 1},
        atoms=[atom],
        budget=build_request_budget(),
    )
    first = execute_evidence_request(**kwargs)
    replay = execute_evidence_request(**kwargs, existing_by_attempt={first.record["attempted_request_hash"]: first.record})
    assert replay.duplicate is True
    assert replay.record == first.record
    forged = deepcopy(first.record)
    forged["attempted_request_hash"] = stable_hash({"wrong": True})
    with pytest.raises(P137RequestError):
        execute_evidence_request(**kwargs, existing_by_attempt={first.record["attempted_request_hash"]: forged})


def test_equivalent_attempt_rejects_rehashed_omitted_catalog_match() -> None:
    atoms = [_atom(1), _atom(2)]
    kwargs: dict[str, Any] = dict(
        incident_id="incident-a",
        incident_hash=stable_hash({"incident": "a"}),
        request_sequence=1,
        catalog_name="select_records_by_system_id",
        parameters={"system_id": "system-a", "limit": 10},
        atoms=atoms,
        budget=build_request_budget(),
    )
    first = execute_evidence_request(**kwargs)
    forged = deepcopy(first.record)
    forged["result_summary"]["matched_atom_hashes"] = forged["result_summary"]["matched_atom_hashes"][:1]
    forged["result_summary"]["output_count"] = 1
    forged["runtime_activity"]["output_records_selected"] = 1
    forged["request_hash"] = stable_hash({key: item for key, item in forged.items() if key != "request_hash"})

    with pytest.raises(P137RequestError, match="durable_request_semantic_mismatch"):
        execute_evidence_request(**kwargs, existing_by_attempt={first.record["attempted_request_hash"]: forged})


@pytest.mark.parametrize("catalog", ["provider_query", "restart_service"])
def test_non_catalog_and_authority_shaped_parameters_fail_closed(catalog: str) -> None:
    with pytest.raises(P137RequestError, match="request_catalog_not_allowlisted"):
        execute_evidence_request(
            incident_id="incident-a",
            incident_hash=stable_hash({"incident": "a"}),
            request_sequence=1,
            catalog_name=catalog,
            parameters={"limit": 1},
            atoms=[],
            budget=build_request_budget(),
        )
    with pytest.raises(P137RequestError, match="request_authority_forbidden"):
        execute_evidence_request(
            incident_id="incident-a",
            incident_hash=stable_hash({"incident": "a"}),
            request_sequence=1,
            catalog_name="select_records_by_provider",
            parameters={"provider": "https://provider.invalid/query", "limit": 1},
            atoms=[],
            budget=build_request_budget(),
        )


def test_request_budget_rejects_booleans_and_input_overflow() -> None:
    budget = build_request_budget()
    with pytest.raises(P137RequestError):
        build_request_budget({**budget, "max_input_records": True})
    with pytest.raises(P137RequestError, match="request_input_record_budget_exceeded"):
        execute_evidence_request(
            incident_id="incident-a",
            incident_hash=stable_hash({"incident": "a"}),
            request_sequence=1,
            catalog_name="summarize_numeric_samples",
            parameters={"signal_name": "error_rate", "limit": 1},
            atoms=[_atom(1), _atom(2)],
            budget={**budget, "max_input_records": 1},
        )
