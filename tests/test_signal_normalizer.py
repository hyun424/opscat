"""Fixture signal normalization and import adapter gates for P5."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.signal_normalizer import SignalNormalizationError, normalize_signal
from tests.test_operator_dashboard import ALPHA_HEADERS

FIXTURE_DIR = Path("examples/fixtures/signals")


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURE_DIR / name).read_text())


def test_signal_normalizer_maps_provider_fixtures_to_mock_alert_contract() -> None:
    cases = [
        ("sentry_issue.json", "sentry", "payment_bad_deploy", "payment-api"),
        ("datadog_monitor.json", "datadog", "worker_queue_backlog", "worker"),
        ("loki_log_alert.json", "loki", "prompt_injection_log", "payment-api"),
        ("generic_webhook.json", "generic", "external_api_timeout", "payment-api"),
    ]

    for filename, provider, scenario, service in cases:
        normalized = normalize_signal(_fixture(filename), tenant_id="tenant-a", workspace_id="alpha")
        assert normalized.tenant_id == "tenant-a"
        assert normalized.workspace_id == "alpha"
        assert normalized.scenario == scenario
        assert normalized.service == service
        assert normalized.idempotency_key and normalized.idempotency_key.startswith("fixture-")
        assert normalized.fingerprint == f"{provider}:{normalized.idempotency_key}"
        assert "[REDACTED]" in (normalized.message or "") or provider == "generic"


def test_signal_normalizer_rejects_unsupported_provider() -> None:
    payload = _fixture("generic_webhook.json") | {"provider": "unknown"}

    try:
        normalize_signal(payload, tenant_id="tenant-a", workspace_id="alpha")
    except SignalNormalizationError as exc:
        assert "unsupported provider" in str(exc)
    else:
        raise AssertionError("unsupported provider should fail closed")


def test_fixture_import_endpoint_reuses_incident_flow_and_idempotency(client: Any) -> None:
    payload = _fixture("sentry_issue.json")

    first = client.post("/webhooks/alerts/fixture?process_now=true", headers=ALPHA_HEADERS, json=payload)
    second = client.post("/webhooks/alerts/fixture?process_now=true", headers=ALPHA_HEADERS, json=payload)

    assert first.status_code == 201
    assert second.status_code == 201
    first_body = first.json()
    second_body = second.json()
    assert first_body["id"] == second_body["id"]
    assert first_body["source"] == "mock_alert"
    assert first_body["service"] == "payment-api"
    assert first_body["workspace_id"] == "alpha"
    rendered = json.dumps(first_body, sort_keys=True)
    assert "PaymentTimeoutError" in rendered
    assert "sntrys_" not in rendered
    assert "customer" not in rendered


def test_fixture_import_endpoint_fails_closed_for_bad_provider(client: Any) -> None:
    response = client.post("/webhooks/alerts/fixture", headers=ALPHA_HEADERS, json={"provider": "unknown"})

    assert response.status_code == 400
    assert response.json()["detail"]["message"] == "unsupported provider"
