"""Typed connector contract for OpsCat integrations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ConnectorCapability:
    name: str
    description: str
    risk_level: str = "read_only"
    read_only: bool = True
    required_role: str = "viewer"
    requires_approval: bool = False
    required_secret_name: str | None = None


@dataclass(frozen=True)
class ConnectorCallRequest:
    connector_id: str
    capability: str
    tenant_id: str
    workspace_id: str
    actor: str
    incident_id: str | None = None
    idempotency_key: str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)
    dry_run: bool = True
    approved: bool = False


@dataclass(frozen=True)
class ConnectorCallResult:
    connector_id: str
    capability: str
    ok: bool
    read_only: bool
    output: Mapping[str, Any] = field(default_factory=dict)
    error: str | None = None
    evidence_summary: str | None = None


class Connector(Protocol):
    connector_id: str
    capabilities: Mapping[str, ConnectorCapability]

    def call(self, request: ConnectorCallRequest) -> ConnectorCallResult:
        """Execute one typed connector capability."""
