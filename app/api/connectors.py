"""Connector catalog and permission preview API."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends

from app.security.dependencies import get_current_principal
from app.services.connector_service import default_connector_registry
from app.services.identity_service import Principal

router = APIRouter(prefix="/connectors", tags=["connectors"])

_DISPLAY_NAMES = {
    "fake.observability": "Fake Observability",
    "sentry.readonly": "Sentry Read-Only Fixtures",
    "prometheus.readonly": "Prometheus Read-Only",
    "slack.wake_up": "Slack Wake-Up Preview",
    "github.issues": "GitHub Draft Issue Preview",
}

_DESCRIPTIONS = {
    "fake.observability": "Read synthetic observability events and metrics for local demos.",
    "sentry.readonly": "Read sanitized Sentry-style recorded fixtures; no network calls are performed.",
    "prometheus.readonly": "Read bounded metric evidence from offline fixtures or an explicitly configured allowlisted Prometheus endpoint.",
    "slack.wake_up": "Build redacted Slack wake-up message previews; real sends are disabled.",
    "github.issues": "Build approval-gated GitHub issue previews; live issue creation is disabled.",
}


@router.get("")
def list_connectors(principal: Principal = Depends(get_current_principal)) -> dict[str, Any]:
    """Return safe connector capability metadata before any secret setup."""

    registry = default_connector_registry()
    connectors: list[dict[str, Any]] = []
    for connector_id, capabilities in registry.list_capabilities().items():
        connectors.append(
            {
                "connector_id": connector_id,
                "display_name": _DISPLAY_NAMES.get(connector_id, connector_id),
                "description": _DESCRIPTIONS.get(connector_id, "Typed local/mock connector capability."),
                "capabilities": [_capability_payload(capability) for capability in sorted(capabilities, key=lambda item: (item.required_secret_name is None, item.name))],
            }
        )
    return {
        "mode": "local-mock",
        "auth_setup_required": False,
        "identity_boundary": "local-header demo identity",
        "production_side_effects_enabled": False,
        "tenant_id": principal.tenant_id,
        "workspace_id": principal.workspace_id,
        "connectors": connectors,
    }


def _capability_payload(capability: Any) -> dict[str, Any]:
    payload = asdict(capability)
    payload["dry_run_only"] = not bool(payload["read_only"])
    return payload
