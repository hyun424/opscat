"""Normalize local provider-shaped fixture signals into OpsCat mock alerts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, cast

from app.schemas.incidents import MockAlertRequest
from app.services.redaction import redact_text

SUPPORTED_PROVIDERS = {"sentry", "datadog", "loki", "generic"}


class SignalNormalizationError(ValueError):
    pass


def normalize_signal(payload: Mapping[str, Any], *, tenant_id: str, workspace_id: str) -> MockAlertRequest:
    provider = _text(payload.get("provider")).lower()
    if provider not in SUPPORTED_PROVIDERS:
        raise SignalNormalizationError("unsupported provider")
    idempotency_key = _text(payload.get("idempotency_key"))
    if not idempotency_key:
        raise SignalNormalizationError("idempotency_key is required")
    scenario = _text(payload.get("scenario")) or _default_scenario(provider)
    service = _text(payload.get("service")) or _default_service(provider, scenario)
    environment = _text(payload.get("environment")) or "staging"
    severity = _severity(payload.get("severity"))
    message = _message(provider, payload)
    return MockAlertRequest(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        idempotency_key=idempotency_key,
        scenario=scenario,
        service=service,
        environment=environment,
        severity=severity,
        message=message,
        fingerprint=f"{provider}:{idempotency_key}",
    )


def _message(provider: str, payload: Mapping[str, Any]) -> str:
    base = _text(payload.get("message")) or f"{provider} fixture alert"
    return redact_text(base)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _severity(value: Any) -> Literal["low", "medium", "high", "critical"]:
    severity = _text(value).lower()
    if severity in {"low", "medium", "high", "critical"}:
        return cast(Literal["low", "medium", "high", "critical"], severity)
    return "high"


def _default_scenario(provider: str) -> str:
    if provider == "datadog":
        return "worker_queue_backlog"
    if provider == "loki":
        return "prompt_injection_log"
    if provider == "generic":
        return "external_api_timeout"
    return "payment_bad_deploy"


def _default_service(provider: str, scenario: str) -> str:
    if provider == "datadog" or scenario.startswith("worker"):
        return "worker"
    return "payment-api"
