"""Connector allowlist registry."""

from __future__ import annotations

from app.connectors.base import Connector, ConnectorCapability


class ConnectorRegistry:
    def __init__(self) -> None:
        self._connectors: dict[str, Connector] = {}

    def register(self, connector: Connector) -> None:
        if connector.connector_id in self._connectors:
            raise ValueError(f"duplicate connector id: {connector.connector_id}")
        self._connectors[connector.connector_id] = connector

    def get(self, connector_id: str) -> Connector:
        try:
            return self._connectors[connector_id]
        except KeyError as exc:
            raise KeyError(f"unknown connector: {connector_id}") from exc

    def capability(self, connector_id: str, capability_name: str) -> ConnectorCapability:
        connector = self.get(connector_id)
        try:
            return connector.capabilities[capability_name]
        except KeyError as exc:
            raise KeyError(f"unknown capability: {connector_id}.{capability_name}") from exc

    def list_capabilities(self) -> dict[str, list[ConnectorCapability]]:
        return {connector_id: list(connector.capabilities.values()) for connector_id, connector in sorted(self._connectors.items())}
