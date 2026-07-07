"""Example fixture connector template for OpsCat contributors.

This connector intentionally performs no network I/O. It demonstrates the
minimum contract needed for registry/service execution: explicit capability
metadata, required secret naming, redacted output, fixture success, and
provider-failure behavior.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.connectors.base import ConnectorCallRequest, ConnectorCallResult, ConnectorCapability
from app.services.redaction import redact_value


class ExampleStatusConnector:
    connector_id = "example.status"
    capabilities: Mapping[str, ConnectorCapability] = {
        "status.read": ConnectorCapability(
            name="status.read",
            description="Read synthetic service status from a fixture-backed example connector.",
            risk_level="read_only",
            read_only=True,
            required_role="viewer",
            required_secret_name="example.token",
        )
    }

    def call(self, request: ConnectorCallRequest) -> ConnectorCallResult:
        if request.capability not in self.capabilities:
            return ConnectorCallResult(
                connector_id=self.connector_id,
                capability=request.capability,
                ok=False,
                read_only=True,
                error="unsupported capability",
            )
        if not str(request.payload.get("auth_token", "")).strip():
            return ConnectorCallResult(
                connector_id=self.connector_id,
                capability=request.capability,
                ok=False,
                read_only=True,
                error="missing credential: auth_token",
                evidence_summary="Example connector failed closed before fixture access because auth_token was not supplied.",
            )
        service = str(request.payload.get("service") or "unknown-service")
        if bool(request.payload.get("force_failure")):
            return ConnectorCallResult(
                connector_id=self.connector_id,
                capability=request.capability,
                ok=False,
                read_only=True,
                error="example provider failure: fixture forced failure",
                evidence_summary=f"Example fixture provider failed closed for {service}.",
                output=redact_value({"service": service, "auth_token": request.payload.get("auth_token")}),
            )
        output = redact_value(
            {
                "provider": "example-fixture",
                "recorded": True,
                "service": service,
                "status": "degraded" if service == "checkout-api" else "ok",
                "auth_token": request.payload.get("auth_token"),
                "checks": ["fixture reachable", "no network call", "redacted output"],
            }
        )
        return ConnectorCallResult(
            connector_id=self.connector_id,
            capability=request.capability,
            ok=True,
            read_only=True,
            evidence_summary=f"Read synthetic status fixture for {service}; no network call performed.",
            output=_dict(output),
        )


def _dict(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, dict) else {"value": value}
