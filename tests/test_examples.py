"""Public API docs and local fixture examples for OSS usage."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SECRET_MARKERS = ("sk_live_", "xoxb-", "ghp_", "sntrys_", "BEGIN PRIVATE KEY", "prod-token")


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def test_public_api_docs_cover_core_local_surfaces() -> None:
    api_doc = Path("docs/api.md")

    assert api_doc.exists()
    text = api_doc.read_text()
    for required in [
        "# OpsCat Local API",
        "GET /health",
        "POST /webhooks/alerts/mock",
        "GET /incidents",
        "GET /incidents/{incident_id}",
        "POST /approvals/{action_id}",
        "GET /incidents/{incident_id}/report",
        "GET /operator",
        "GET /operator/actions/{action_id}",
        "pending approvals",
        "POST /night-autopilot/simulate",
        "Workflow worker CLI",
        "scripts/workflow_cli.py stats",
        "Connector catalog",
        "No auth setup is required",
        "local-header demo identity",
        "Do not use production credentials",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)


def test_example_fixtures_are_valid_safe_local_json() -> None:
    fixture_dir = Path("examples/fixtures/signals")
    expected = {
        "sentry_issue.json",
        "datadog_monitor.json",
        "loki_log_alert.json",
        "generic_webhook.json",
    }

    assert fixture_dir.exists()
    actual = {path.name for path in fixture_dir.glob("*.json")}
    assert expected.issubset(actual)
    for name in expected:
        payload = _json(fixture_dir / name)
        rendered = json.dumps(payload, sort_keys=True)
        assert payload["provider"]
        assert payload["scenario"]
        assert payload["service"]
        assert payload["environment"]
        assert payload["severity"] in {"low", "medium", "high", "critical"}
        assert "fixture" in payload["idempotency_key"]
        assert all(marker not in rendered for marker in SECRET_MARKERS)
        assert "[REDACTED]" in rendered or payload["provider"] == "generic"


def test_example_commands_are_localhost_and_credential_free() -> None:
    examples = Path("examples/README.md")

    assert examples.exists()
    text = examples.read_text()
    for required in [
        "# OpsCat Examples",
        "localhost:8000",
        "X-OpsCat-Actor",
        "examples/fixtures/signals/sentry_issue.json",
        "examples/fixtures/signals/datadog_monitor.json",
        "examples/fixtures/signals/loki_log_alert.json",
        "curl -s -X POST",
    ]:
        assert required in text
    assert all(marker not in text for marker in SECRET_MARKERS)
