"""Sentry-style read-only connector backed by recorded local fixtures.

The connector intentionally never performs network I/O. It validates that the
caller supplied a credential marker so the production path fails closed when a
secret was not resolved, then serves deterministic sanitized fixture data for
local development and tests.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any, cast

from app.connectors.base import ConnectorCallRequest, ConnectorCallResult, ConnectorCapability
from app.services.redaction import redact_value

_AUTH_TOKEN_FIELD = "auth_token"

_RECORDED_ISSUES: tuple[dict[str, Any], ...] = (
    {
        "id": "SENTRY-123",
        "short_id": "OPS-123",
        "project": "checkout-api",
        "title": "TimeoutError: upstream payment gateway exceeded 3s",
        "level": "error",
        "status": "unresolved",
        "count": 47,
        "permalink": "https://sentry.example.local/organizations/opscat/issues/SENTRY-123/",
        "first_seen": "2026-07-07T00:14:00Z",
        "last_seen": "2026-07-07T00:41:00Z",
        "assigned_to": "payments-oncall@example.com",
        "tags": {"service": "checkout-api", "environment": "staging", "release": "2026.07.07-rc1"},
    },
    {
        "id": "SENTRY-456",
        "short_id": "OPS-456",
        "project": "frontend-web",
        "title": "TypeError: cannot read property 'cartId' of undefined",
        "level": "warning",
        "status": "unresolved",
        "count": 9,
        "permalink": "https://sentry.example.local/organizations/opscat/issues/SENTRY-456/",
        "first_seen": "2026-07-07T00:23:00Z",
        "last_seen": "2026-07-07T00:38:00Z",
        "assigned_to": "frontend-oncall@example.com",
        "tags": {"service": "frontend-web", "environment": "staging", "release": "2026.07.07-rc1"},
    },
)

_RECORDED_EVENTS: dict[str, tuple[dict[str, Any], ...]] = {
    "SENTRY-123": (
        {
            "event_id": "evt-timeout-001",
            "timestamp": "2026-07-07T00:40:31Z",
            "message": "TimeoutError: upstream payment gateway exceeded 3s",
            "culprit": "checkout.submit",
            "user": {"email": "customer.1001@example.com", "id": "user-1001"},
            "request": {"url": "/checkout/submit", "headers": {"Authorization": "Bearer recorded-fixture-token"}},
            "breadcrumbs": [
                {"category": "http", "message": "POST /payments/authorize -> 504"},
                {"category": "log", "message": "payment_token=tok_recorded_fixture sentry_key=abc123 dsn=https://public:secret@sentry.example.invalid/1"},
            ],
        },
        {
            "event_id": "evt-timeout-002",
            "timestamp": "2026-07-07T00:41:05Z",
            "message": "TimeoutError: upstream payment gateway exceeded 3s",
            "culprit": "checkout.submit",
            "user": {"email": "customer.1002@example.com", "id": "user-1002"},
            "request": {"url": "/checkout/submit", "headers": {"Authorization": "Bearer recorded-fixture-token"}},
            "breadcrumbs": [{"category": "metric", "message": "gateway_latency_ms=3210"}],
        },
    ),
    "SENTRY-456": (
        {
            "event_id": "evt-frontend-001",
            "timestamp": "2026-07-07T00:37:52Z",
            "message": "TypeError: cannot read property 'cartId' of undefined",
            "culprit": "CartDrawer.render",
            "user": {"email": "shopper@example.com", "id": "user-2001"},
            "request": {"url": "/cart", "headers": {"Authorization": "Bearer recorded-fixture-token"}},
            "breadcrumbs": [{"category": "ui", "message": "cart drawer opened"}],
        },
    ),
}


class SentryReadOnlyConnector:
    connector_id = "sentry.readonly"
    capabilities: Mapping[str, ConnectorCapability] = {
        "issues.read": ConnectorCapability(
            name="issues.read",
            description="Read/search sanitized Sentry-style issue fixtures without live provider access.",
            risk_level="read_only",
            read_only=True,
            required_role="viewer",
            required_secret_name="sentry.token",
        ),
        "issue.events.read": ConnectorCapability(
            name="issue.events.read",
            description="Read sanitized Sentry-style event fixtures for one issue without live provider access.",
            risk_level="read_only",
            read_only=True,
            required_role="viewer",
            required_secret_name="sentry.token",
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
        if not str(request.payload.get(_AUTH_TOKEN_FIELD, "")).strip():
            return ConnectorCallResult(
                connector_id=self.connector_id,
                capability=request.capability,
                ok=False,
                read_only=True,
                error="missing credential: auth_token",
                evidence_summary="Sentry-style connector failed closed before reading recorded fixtures because auth_token was not supplied.",
            )
        if request.capability == "issues.read":
            return self._search_issues(request)
        return self._read_issue_events(request)

    def _search_issues(self, request: ConnectorCallRequest) -> ConnectorCallResult:
        project = _optional_text(request.payload.get("project"))
        query = _optional_text(request.payload.get("query")).lower()
        issues = [_redacted_mapping(issue) for issue in _RECORDED_ISSUES if _matches_issue(issue, project=project, query=query)]
        return ConnectorCallResult(
            connector_id=self.connector_id,
            capability=request.capability,
            ok=True,
            read_only=True,
            evidence_summary=f"Read {len(issues)} sanitized Sentry-style issue fixture(s); no network call performed.",
            output={"provider": "sentry-fixture", "recorded": True, "issues": issues},
        )

    def _read_issue_events(self, request: ConnectorCallRequest) -> ConnectorCallResult:
        issue_id = _optional_text(request.payload.get("issue_id"))
        if not issue_id:
            return ConnectorCallResult(
                connector_id=self.connector_id,
                capability=request.capability,
                ok=False,
                read_only=True,
                error="missing issue_id",
            )
        events = [_redacted_mapping(event) for event in _RECORDED_EVENTS.get(issue_id, ())]
        return ConnectorCallResult(
            connector_id=self.connector_id,
            capability=request.capability,
            ok=True,
            read_only=True,
            evidence_summary=f"Read {len(events)} sanitized Sentry-style event fixture(s) for {issue_id}; no network call performed.",
            output={"provider": "sentry-fixture", "recorded": True, "issue_id": issue_id, "events": events},
        )


def _matches_issue(issue: Mapping[str, Any], *, project: str, query: str) -> bool:
    if project and str(issue.get("project", "")) != project:
        return False
    if not query:
        return True
    haystack = " ".join(str(issue.get(key, "")) for key in ("id", "short_id", "title", "level", "status")).lower()
    return query in haystack


def _optional_text(value: Any) -> str:
    return str(value or "").strip()


def _redacted_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    copied = deepcopy(dict(value))
    return cast(dict[str, Any], redact_value(copied))
