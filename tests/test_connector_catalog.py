"""Connector setup catalog and permission preview gates for P5."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tests.test_operator_dashboard import ALPHA_HEADERS

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY")


def test_connector_catalog_api_exposes_safe_permission_preview(client: Any) -> None:
    response = client.get("/connectors", headers=ALPHA_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "local-mock"
    assert payload["auth_setup_required"] is False
    assert payload["production_side_effects_enabled"] is False
    assert payload["tenant_id"] == "tenant-a"
    assert payload["workspace_id"] == "alpha"

    connectors = {item["connector_id"]: item for item in payload["connectors"]}
    assert {"fake.observability", "sentry.readonly", "slack.wake_up", "github.issues"}.issubset(connectors)

    for connector in connectors.values():
        assert connector["display_name"]
        assert connector["description"]
        assert connector["capabilities"]
        for capability in connector["capabilities"]:
            for field in ["name", "description", "risk_level", "read_only", "required_role", "requires_approval", "required_secret_name", "dry_run_only"]:
                assert field in capability
            if not capability["read_only"]:
                assert capability["dry_run_only"] is True

    assert connectors["sentry.readonly"]["capabilities"][0]["required_secret_name"] == "sentry.token"
    assert connectors["github.issues"]["capabilities"][0]["requires_approval"] is True
    assert all(marker not in json.dumps(payload, sort_keys=True) for marker in SECRET_MARKERS)


def test_connector_permissions_doc_lists_minimum_capabilities_and_no_broad_tokens() -> None:
    doc = Path("docs/connector-permissions.md")

    assert doc.exists()
    text = doc.read_text()
    for required in [
        "# Connector Permissions",
        "fake.observability",
        "sentry.readonly",
        "slack.wake_up",
        "github.issues",
        "No broad provider tokens",
        "No real external side effects",
        "GET /connectors",
        "auth is deferred",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)
