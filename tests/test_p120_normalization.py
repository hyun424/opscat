from __future__ import annotations

import pytest

from app.services.p120_governance import zero_authority_counters
from app.services.p120_normalization import (
    P120NormalizationError,
    build_read_only_importer_contract,
    normalize_telemetry_record,
    validate_normalized_record,
)


def _base() -> dict[str, object]:
    return {
        "id": "rec-1",
        "source_id": "src-1",
        "system_id": "sys-1",
        "service": "checkout",
        "host": "checkout-1",
        "timestamp": "2026-07-12T00:00:00Z",
        "redaction_receipt": "redacted:abc",
        "topology_refs": ["svc:checkout"],
        "deploy_config_refs": ["deploy:42"],
    }


def test_normalizes_realistic_system_schemas_to_canonical_envelope() -> None:
    records = [
        normalize_telemetry_record(
            {**_base(), "metric": "http_requests_total", "value": 42, "unit": "count", "labels": {"route": "/pay"}},
            source_schema="prometheus",
            ingestion_time="2026-07-12T00:00:10Z",
        ),
        normalize_telemetry_record(
            {**_base(), "metric_name": "system.cpu.user", "point": 0.7, "unit": "ratio", "tags": {"env": "fixture"}, "ts": "2026-07-12T00:00:00Z"},
            source_schema="datadog",
            ingestion_time="2026-07-12T00:00:10Z",
        ),
        normalize_telemetry_record(
            {**_base(), "event_id": "evt-1", "title": "CheckoutError", "level": "error", "first_seen": "2026-07-12T00:00:00Z", "last_seen": "2026-07-12T00:00:03Z"},
            source_schema="sentry",
            ingestion_time="2026-07-12T00:00:10Z",
        ),
        normalize_telemetry_record(
            {**_base(), "message": "worker timeout", "template": "worker timeout", "unit": "line", "fields": {"queue": "payments"}},
            source_schema="log_event",
            ingestion_time="2026-07-12T00:00:10Z",
        ),
        normalize_telemetry_record(
            {**_base(), "span_name": "POST /pay", "duration_ms": 320, "start_time": "2026-07-12T00:00:00Z", "end_time": "2026-07-12T00:00:01Z"},
            source_schema="trace_span",
            ingestion_time="2026-07-12T00:00:10Z",
        ),
    ]
    assert {record["modality"] for record in records} == {"metric", "event", "log", "trace"}
    for record in records:
        validate_normalized_record(record)
        assert record["denominator_visible"] is True
        assert record["authority_counters"] == zero_authority_counters()


def test_malformed_stale_duplicate_reordered_and_contradictory_records_remain_visible() -> None:
    stale = normalize_telemetry_record(
        {**_base(), "metric": "latency", "value": 10, "unit": "ms", "timestamp": "2026-07-10T00:00:00Z"},
        source_schema="prometheus",
        ingestion_time="2026-07-12T00:00:00Z",
    )
    assert stale["evidence_state"] == "fail_closed"
    assert "stale_record" in stale["state_reasons"]

    duplicate = normalize_telemetry_record(
        {**_base(), "metric": "latency", "value": 10, "unit": "ms", "duplicate_of": "rec-0", "arrival_order": 1, "expected_order": 3, "contradicts": ["rec-9"]},
        source_schema="prometheus",
        ingestion_time="2026-07-12T00:00:10Z",
    )
    assert duplicate["evidence_state"] == "contradiction"
    assert {"duplicate_record_visible", "reorder_visible", "contradictory_telemetry_visible"} <= set(duplicate["state_reasons"])

    malformed = normalize_telemetry_record({"id": "bad", "source_id": "src-1"}, source_schema="unknown_schema", ingestion_time="2026-07-12T00:00:10Z")
    assert malformed["evidence_state"] == "fail_closed"
    assert malformed["denominator_visible"] is True


def test_read_only_importer_contract_rejects_write_live_credential_and_loss_red_cases() -> None:
    contract = build_read_only_importer_contract(
        {
            "connector_id": "fixture-importer",
            "source_kind": "local_fixture",
            "supported_schemas": ["prometheus", "log_event"],
            "authority_counters": zero_authority_counters(),
        }
    )
    assert str(contract["contract_hash"]).startswith("sha256:")

    with pytest.raises(P120NormalizationError, match="credential_required_connector"):
        build_read_only_importer_contract({**contract, "requires_credentials": True})
    with pytest.raises(P120NormalizationError, match="write_endpoint_reachable"):
        build_read_only_importer_contract({**contract, "write_endpoints_reachable": True})
    with pytest.raises(P120NormalizationError, match="live_connector_call_present"):
        build_read_only_importer_contract({**contract, "live_connector_calls": 1})
    with pytest.raises(P120NormalizationError, match="ingestion_loss_above_threshold"):
        build_read_only_importer_contract({**contract, "ingestion_loss_rate": 0.002})
