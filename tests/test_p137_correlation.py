from __future__ import annotations

import importlib
from copy import deepcopy
from typing import Any

import pytest

from app.services.p110_evaluation import stable_hash


def _api(*names: str) -> Any:
    try:
        module = importlib.import_module("app.services.p137_correlation")
    except ModuleNotFoundError as exc:
        pytest.fail(f"missing P137 correlation module/API: app.services.p137_correlation ({exc})")
    missing = [name for name in names if not hasattr(module, name)]
    if missing:
        pytest.fail(f"missing P137 correlation module/API: {', '.join(missing)}")
    return module


def _error() -> type[Exception]:
    return _api("P137CorrelationError").P137CorrelationError


def _atom(
    ordinal: int,
    *,
    system_id: str = "system-a",
    entity_ref_hash: str | None = None,
    provider: str = "prometheus",
    signal_family: str = "metrics",
    signal_name: str = "error_rate",
    start: str = "2026-07-14T00:00:00Z",
    end: str = "2026-07-14T00:05:00Z",
    labels: list[str] | None = None,
    content_hash: str | None = None,
    evidence_state: str = "promoted_success",
    promotion_key: str | None = None,
    p136_entry_hash: str | None = None,
) -> dict[str, Any]:
    entity = entity_ref_hash or stable_hash({"entity": "checkout"})
    atom = {
        "schema_version": "p137.evidence_atom.v1",
        "atom_id": f"atom-{ordinal}",
        "promotion_record_hash": stable_hash({"promotion": ordinal}),
        "promotion_key": promotion_key or stable_hash({"promotion_key": ordinal}),
        "p136_entry_hash": p136_entry_hash or stable_hash({"entry": ordinal}),
        "p135_bundle_hash": stable_hash({"bundle": ordinal}),
        "source_id": f"source-{ordinal}",
        "provider": provider,
        "format": "prometheus.query_range.matrix.v1",
        "signal_family": signal_family,
        "system_id": system_id,
        "entity_ref_hash": entity,
        "window": {"start": start, "end": end},
        "signal_name": signal_name,
        "numeric_value": 5,
        "numeric_unit": "ratio",
        "evidence_state": evidence_state,
        "severity_code": "sev2",
        "metric_breach_code": "above_critical",
        "marker_code": "none",
        "counter_signal_code": "none",
        "state_reason_codes": [],
        "denominator_visible": evidence_state == "denominator_visible_failure",
        "content_hash": content_hash or stable_hash({"content": "same"}),
        "label_hashes": labels or [stable_hash({"label": "checkout"})],
        "topology_ref_hashes": [],
        "deploy_config_ref_hashes": [],
        "risk_flags": [],
        "redacted_preview_hash": stable_hash({"preview": ordinal}),
        "ordinal": ordinal,
    }
    atom["atom_hash"] = stable_hash(atom)
    return atom


def test_correlates_exact_keys_and_preserves_stable_incident_id_on_restart() -> None:
    api = _api("correlate_incident_state")
    first = _atom(1)
    duplicate = deepcopy(first)
    duplicate["atom_id"] = "atom-duplicate"
    duplicate["ordinal"] = 99
    duplicate["promotion_record_hash"] = stable_hash({"promotion": "duplicate"})
    duplicate["atom_hash"] = stable_hash(duplicate)
    unrelated = _atom(
        2,
        system_id="system-b",
        entity_ref_hash=stable_hash({"entity": "billing"}),
        provider="loki",
        signal_family="logs",
        labels=[stable_hash({"label": "billing"})],
        content_hash=stable_hash({"content": "different"}),
        start="2026-07-14T02:00:00Z",
        end="2026-07-14T02:05:00Z",
    )

    result = api.correlate_incident_state(
        [unrelated, duplicate, first],
        now="2026-07-14T00:06:00Z",
        limits={
            "max_open_incidents": 4,
            "max_atoms_per_incident": 4,
            "max_correlation_window_seconds": 900,
            "max_incident_duration_seconds": 1800,
            "max_journal_entries": 8,
            "max_ledger_edges": 8,
        },
    )
    restarted = api.correlate_incident_state([first, duplicate, unrelated], now="2026-07-14T00:06:00Z")

    incidents = sorted(result["incidents"], key=lambda item: item["primary_system_id"])
    assert [incident["primary_system_id"] for incident in incidents] == ["system-a", "system-b"]
    assert incidents[0]["incident_id"] == sorted(restarted["incidents"], key=lambda item: item["primary_system_id"])[0]["incident_id"]
    assert incidents[0]["evidence_atom_hashes"] == [first["atom_hash"], duplicate["atom_hash"]]
    assert set(incidents[0]) == {
        "schema_version",
        "incident_id",
        "incident_sequence",
        "status",
        "created_at",
        "updated_at",
        "correlation_key",
        "primary_system_id",
        "entity_ref_hashes",
        "time_window",
        "source_promotion_record_hashes",
        "evidence_atom_hashes",
        "rejection_hashes",
        "hypothesis_hashes",
        "request_hashes",
        "attempted_request_hashes",
        "classification_hash",
        "previous_incident_hash",
        "incident_hash",
    }
    assert incidents[0]["incident_hash"] == stable_hash(
        {key: value for key, value in incidents[0].items() if key != "incident_hash"}
    )
    assert incidents[0]["correlation_key"]["relations"] == [
        "content_hash",
        "entity_ref_hash",
        "label_hash",
        "provider_signal_family",
        "system_id_time_window",
    ]


def test_rejection_reason_correlates_without_free_form_text_similarity() -> None:
    api = _api("correlate_incident_state")
    atom = _atom(1, system_id="system-a", signal_family="metrics")
    nearby_rejection = {
        "rejection_hash": stable_hash({"rejection": 1}),
        "system_id": "system-a",
        "entity_ref_hash": atom["entity_ref_hash"],
        "window": {"start": "2026-07-14T00:03:00Z", "end": "2026-07-14T00:04:00Z"},
        "reason_code": "parser_failure",
        "free_form_detail": "checkout looks similar to billing",
    }

    result = api.correlate_incident_state([atom], rejections=[nearby_rejection], now="2026-07-14T00:07:00Z")

    assert result["incidents"][0]["rejection_hashes"] == [nearby_rejection["rejection_hash"]]
    assert result["incidents"][0]["correlation_key"]["p136_rejection_reasons"] == ["parser_failure"]
    assert "free_form_detail" not in result["incidents"][0]["correlation_key"]


def test_incident_statuses_follow_transition_graph_and_terminal_states_are_closed() -> None:
    api = _api("transition_incident_status")
    error = _error()

    assert api.transition_incident_status("open", "correlating") == "correlating"
    assert api.transition_incident_status("investigating", "aborted_fail_closed") == "aborted_fail_closed"
    with pytest.raises(error, match="terminal_incident_transition_forbidden"):
        api.transition_incident_status("confirmed_incident", "investigating")
    with pytest.raises(error, match="illegal_incident_transition"):
        api.transition_incident_status("open", "ready_to_classify")


def test_budgets_fail_closed_before_unbounded_correlation() -> None:
    api = _api("correlate_incident_state")
    error = _error()

    with pytest.raises(error, match="open_incident_budget_exceeded"):
        api.correlate_incident_state(
            [
                _atom(1),
                _atom(
                    2,
                    system_id="system-b",
                    entity_ref_hash=stable_hash({"entity": "b"}),
                    provider="loki",
                    signal_family="logs",
                    labels=[stable_hash({"label": "b"})],
                    content_hash=stable_hash({"content": "b"}),
                    start="2026-07-14T02:00:00Z",
                    end="2026-07-14T02:05:00Z",
                ),
            ],
            limits={"max_open_incidents": 1},
        )

    with pytest.raises(error, match="incident_atom_budget_exceeded"):
        api.correlate_incident_state([_atom(1), _atom(2)], limits={"max_atoms_per_incident": 1})
