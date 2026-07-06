"""Safe built-in fake connectors for contract tests and demos."""

from __future__ import annotations

from collections.abc import Mapping

from app.connectors.base import ConnectorCallRequest, ConnectorCallResult, ConnectorCapability


class FakeObservabilityConnector:
    connector_id = "fake.observability"
    capabilities: Mapping[str, ConnectorCapability] = {
        "events.read": ConnectorCapability(
            name="events.read",
            description="Read sanitized alert/event context from a fake observability provider.",
            risk_level="read_only",
            read_only=True,
            required_role="viewer",
        ),
        "metrics.read": ConnectorCapability(
            name="metrics.read",
            description="Read sanitized metric windows from a fake observability provider.",
            risk_level="read_only",
            read_only=True,
            required_role="viewer",
        ),
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
        service = str(request.payload.get("service", "unknown-service"))
        window = str(request.payload.get("window", "15m"))
        return ConnectorCallResult(
            connector_id=self.connector_id,
            capability=request.capability,
            ok=True,
            read_only=True,
            evidence_summary=f"Fake {request.capability} for {service} over {window}; sanitized and read-only.",
            output={"service": service, "window": window, "events": [{"severity": "high", "message": "sanitized timeout spike"}]},
        )
