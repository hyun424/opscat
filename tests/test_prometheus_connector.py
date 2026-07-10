from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from app.connectors.base import ConnectorCallRequest
from app.connectors.prometheus import PrometheusProviderResponse, PrometheusReadOnlyConnector
from app.connectors.registry import ConnectorRegistry
from app.models import Evidence, Incident, TimelineEvent
from app.services.connector_service import ConnectorService, default_connector_registry
from app.services.identity_service import get_or_create_local_principal


def _request(capability: str, payload: dict[str, Any] | None = None, *, incident_id: str | None = None) -> ConnectorCallRequest:
    return ConnectorCallRequest(
        connector_id="prometheus.readonly",
        capability=capability,
        tenant_id="tenant-a",
        workspace_id="workspace-a",
        actor="viewer@example.com",
        incident_id=incident_id,
        payload=payload or {},
    )


class RecordingTransport:
    def __init__(self, response: PrometheusProviderResponse) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, *, params: dict[str, str], headers: dict[str, str], timeout_seconds: float, max_response_bytes: int) -> PrometheusProviderResponse:
        self.calls.append(
            {
                "url": url,
                "params": params,
                "headers": headers,
                "timeout_seconds": timeout_seconds,
                "max_response_bytes": max_response_bytes,
            }
        )
        return self.response


def test_default_registry_exposes_prometheus_read_only_capabilities() -> None:
    capabilities = default_connector_registry().list_capabilities()["prometheus.readonly"]

    assert {item.name for item in capabilities} == {"health.check", "query.instant", "query.range"}
    assert all(item.read_only is True for item in capabilities)
    assert all(item.risk_level == "read_only" for item in capabilities)
    assert all(item.required_secret_name is None for item in capabilities)


def test_fixture_mode_is_default_and_never_calls_transport() -> None:
    transport = RecordingTransport(PrometheusProviderResponse(status_code=500, payload={}))
    connector = PrometheusReadOnlyConnector(transport=transport)

    result = connector.call(_request("query.instant", {"query": "rate(http_requests_total[5m])"}))

    assert result.ok is True
    assert result.output["mode"] == "fixture"
    assert result.output["network_attempted"] is False
    assert result.output["result_type"] == "vector"
    assert result.output["evidence"]["source"] == "prometheus"
    assert transport.calls == []


def test_real_instant_query_uses_configured_allowlisted_endpoint_and_normalizes() -> None:
    transport = RecordingTransport(
        PrometheusProviderResponse(
            status_code=200,
            payload={
                "status": "success",
                "data": {
                    "resultType": "vector",
                    "result": [
                        {"metric": {"__name__": "up", "job": "api", "instance": "127.0.0.1:9090"}, "value": [1783641600, "1"]}
                    ],
                },
            },
        )
    )
    connector = PrometheusReadOnlyConnector(
        base_url="http://127.0.0.1:9090",
        allowed_hosts=("127.0.0.1",),
        transport=transport,
    )

    result = connector.call(_request("query.instant", {"provider_mode": "real", "query": "up"}))

    assert result.ok is True
    assert result.output["mode"] == "real"
    assert result.output["network_attempted"] is True
    assert result.output["result_count"] == 1
    assert result.output["series"][0]["metric"]["job"] == "api"
    assert result.output["evidence"]["observations"][0]["value"] == "1"
    assert transport.calls[0]["url"] == "http://127.0.0.1:9090/api/v1/query"
    assert transport.calls[0]["params"] == {"query": "up"}
    assert transport.calls[0]["headers"] == {"Accept": "application/json"}


def test_real_connector_blocks_request_controlled_and_non_allowlisted_destinations() -> None:
    transport = RecordingTransport(PrometheusProviderResponse(status_code=200, payload={"status": "success", "data": {"resultType": "vector", "result": []}}))
    connector = PrometheusReadOnlyConnector(
        base_url="https://prometheus.example.com",
        allowed_hosts=("metrics.example.com",),
        transport=transport,
    )

    result = connector.call(
        _request(
            "query.instant",
            {
                "provider_mode": "real",
                "query": "up",
                "base_url": "http://169.254.169.254/latest/meta-data",
            },
        )
    )

    assert result.ok is False
    assert result.output["normalized_error"] == "endpoint_not_allowed"
    assert "169.254.169.254" not in repr(result)
    assert transport.calls == []


def test_real_connector_requires_https_outside_loopback_even_when_host_is_allowlisted() -> None:
    transport = RecordingTransport(PrometheusProviderResponse(status_code=200, payload={}))
    connector = PrometheusReadOnlyConnector(
        base_url="http://metrics.example.com",
        allowed_hosts=("metrics.example.com",),
        transport=transport,
    )

    result = connector.call(_request("query.instant", {"provider_mode": "real", "query": "up"}))

    assert result.ok is False
    assert result.output["normalized_error"] == "https_required"
    assert transport.calls == []


def test_range_query_budget_fails_closed_before_network() -> None:
    transport = RecordingTransport(PrometheusProviderResponse(status_code=200, payload={}))
    connector = PrometheusReadOnlyConnector(base_url="http://localhost:9090", allowed_hosts=("localhost",), transport=transport)

    result = connector.call(
        _request(
            "query.range",
            {
                "provider_mode": "real",
                "query": "rate(http_requests_total[5m])",
                "start": "2026-07-10T00:00:00Z",
                "end": "2026-07-11T00:00:00Z",
                "step": "1s",
            },
        )
    )

    assert result.ok is False
    assert result.output["normalized_error"] == "query_budget_exceeded"
    assert transport.calls == []


def test_provider_error_is_normalized_and_sensitive_payload_is_redacted() -> None:
    transport = RecordingTransport(
        PrometheusProviderResponse(
            status_code=422,
            payload={"status": "error", "errorType": "bad_data", "error": "invalid query token=prom-secret alice@example.com"},
        )
    )
    connector = PrometheusReadOnlyConnector(base_url="http://localhost:9090", allowed_hosts=("localhost",), transport=transport)

    result = connector.call(_request("query.instant", {"provider_mode": "real", "query": "bad("}))

    assert result.ok is False
    assert result.output["normalized_error"] == "invalid_query"
    assert "prom-secret" not in repr(result)
    assert "alice@example.com" not in repr(result)


def test_successful_prometheus_read_is_persisted_as_scoped_incident_evidence(db_session: Any) -> None:
    incident = Incident(
        id="inc-prom-1",
        tenant_id="tenant-a",
        workspace_id="workspace-a",
        service="checkout-api",
        environment="staging",
        severity="high",
        status="investigating",
    )
    db_session.add(incident)
    db_session.flush()
    principal = get_or_create_local_principal(
        db_session,
        email="viewer@example.com",
        tenant_id="tenant-a",
        workspace_id="workspace-a",
        role="viewer",
    )
    registry = ConnectorRegistry()
    registry.register(PrometheusReadOnlyConnector())

    result = ConnectorService(registry=registry).call(
        db_session,
        principal,
        _request("query.instant", {"query": "up{job=\"checkout-api\"}"}, incident_id=incident.id),
    )

    assert result.ok is True
    evidence = db_session.query(Evidence).filter(Evidence.incident_id == incident.id).one()
    assert evidence.tenant_id == "tenant-a"
    assert evidence.workspace_id == "workspace-a"
    assert evidence.type == "metric_observation"
    assert evidence.source == "connector:prometheus.readonly"
    assert evidence.evidence_metadata["provider"] == "prometheus"
    assert evidence.evidence_metadata["network_attempted"] is False
    timeline = db_session.query(TimelineEvent).filter(TimelineEvent.incident_id == incident.id).all()
    assert any(item.event_type == "connector_evidence_collected" for item in timeline)


def test_prometheus_probe_cli_defaults_to_offline_fixture(tmp_path: Path) -> None:
    output = tmp_path / "prometheus-probe.json"

    completed = subprocess.run(
        ["python", "scripts/probe_prometheus.py", "--output-json", str(output)],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["output"]["mode"] == "fixture"
    assert payload["output"]["network_attempted"] is False
    assert "network_attempted=False" in completed.stdout

