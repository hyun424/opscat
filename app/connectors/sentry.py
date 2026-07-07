"""Sentry-style read-only connector with fixture-default provider boundary.

The connector defaults to sanitized recorded fixtures so local demos and tests do
not need credentials. A real-provider-shaped path can be opted into with
``provider_mode=real``; that path requires a resolved local secret and uses a
small transport boundary so pagination, rate limits, provider errors, and health
states can be tested without live network access.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.connectors.base import ConnectorCallRequest, ConnectorCallResult, ConnectorCapability
from app.services.redaction import redact_text, redact_value

_AUTH_TOKEN_FIELD = "auth_token"
_MAX_PAGES = 3


@dataclass(frozen=True)
class SentryProviderResponse:
    status_code: int
    payload: Mapping[str, Any]
    headers: Mapping[str, str] | None = None


class SentryProviderError(RuntimeError):
    pass


class SentryRateLimitedError(SentryProviderError):
    pass


SentryTransport = Callable[[str, Mapping[str, Any]], SentryProviderResponse]

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


@dataclass(frozen=True)
class SentryProviderResponse:
    status_code: int
    payload: Any = field(default_factory=dict)
    headers: Mapping[str, str] = field(default_factory=dict)


class SentryTransport(Protocol):
    def get(self, url: str, *, token: str, params: Mapping[str, Any]) -> SentryProviderResponse:
        """Perform one Sentry-like GET request."""


class UrllibSentryTransport:
    """Tiny stdlib transport for opt-in local-secret real-provider experiments."""

    def get(self, url: str, *, token: str, params: Mapping[str, Any]) -> SentryProviderResponse:
        query = urlencode({key: value for key, value in params.items() if value not in (None, "")})
        full_url = f"{url}?{query}" if query else url
        request = Request(full_url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
        try:
            with urlopen(request, timeout=5) as response:  # noqa: S310 - explicit opt-in local-secret provider path
                body = response.read().decode("utf-8")
                return SentryProviderResponse(status_code=response.status, payload=json.loads(body or "{}"), headers=dict(response.headers.items()))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            payload: Any
            try:
                payload = json.loads(body or "{}")
            except json.JSONDecodeError:
                payload = {"detail": body}
            return SentryProviderResponse(status_code=exc.code, payload=payload, headers=dict(exc.headers.items()))
        except URLError as exc:
            raise ConnectionError("sentry provider connection failed") from exc


class SentryReadOnlyConnector:
    connector_id = "sentry.readonly"

    def __init__(self, transport: SentryTransport | None = None) -> None:
        self.transport = transport
    capabilities: Mapping[str, ConnectorCapability] = {
        "health.check": ConnectorCapability(
            name="health.check",
            description="Check Sentry connector setup without leaking credentials.",
            risk_level="read_only",
            read_only=True,
            required_role="viewer",
            required_secret_name=None,
        ),
        "issues.read": ConnectorCapability(
            name="issues.read",
            description="Read/search sanitized Sentry issue fixtures by default; real provider reads require provider_mode=real and sentry.token.",
            risk_level="read_only",
            read_only=True,
            required_role="viewer",
            required_secret_name="sentry.token",
        ),
        "issue.events.read": ConnectorCapability(
            name="issue.events.read",
            description="Read sanitized Sentry event fixtures by default; real provider reads require provider_mode=real and sentry.token.",
            risk_level="read_only",
            read_only=True,
            required_role="viewer",
            required_secret_name="sentry.token",
        ),
        "health.check": ConnectorCapability(
            name="health.check",
            description="Report fixture/default or opt-in real-provider Sentry health without leaking configuration.",
            risk_level="read_only",
            read_only=True,
            required_role="viewer",
            required_secret_name=None,
        ),
    }

    def __init__(self, transport: SentryTransport | None = None) -> None:
        self._transport = transport or UrllibSentryTransport()

    def call(self, request: ConnectorCallRequest) -> ConnectorCallResult:
        if request.capability not in self.capabilities:
            return ConnectorCallResult(
                connector_id=self.connector_id,
                capability=request.capability,
                ok=False,
                read_only=True,
                error="unsupported capability",
            )
        if request.capability == "health.check":
            return self._health_check(request)
        if not str(request.payload.get(_AUTH_TOKEN_FIELD, "")).strip() and not _fixture_mode(request.payload):
            return ConnectorCallResult(
                connector_id=self.connector_id,
                capability=request.capability,
                ok=True,
                read_only=True,
                error="missing credential: auth_token",
                evidence_summary="Sentry connector failed closed because live/provider-shaped mode requires a workspace auth token.",
            )
        if request.capability == "issues.read":
            return self._search_issues(request)
        return self._read_issue_events(request)

    def _health_check(self, request: ConnectorCallRequest) -> ConnectorCallResult:
        if _fixture_mode(request.payload) or not self.transport:
            state = "fixture-ok" if _fixture_mode(request.payload) or not str(request.payload.get(_AUTH_TOKEN_FIELD, "")).strip() else "configured"
            return ConnectorCallResult(
                connector_id=self.connector_id,
                capability=request.capability,
                ok=True,
                read_only=True,
                evidence_summary=f"Sentry connector health={state}; no provider mutation performed.",
                output={"state": state, "provider": "sentry-fixture", "fixture_default": True},
            )
        try:
            response = self.transport("/api/0/organizations/{org_slug}/issues/", {"limit": 1, "auth_token": request.payload.get(_AUTH_TOKEN_FIELD)})
        except SentryRateLimitedError:
            return _failure(request, "rate-limited", "Sentry provider rate limit reached; call is bounded and fail-closed.")
        except SentryProviderError:
            return _failure(request, "provider-error", "Sentry provider returned an error; call is fail-closed.")
        if response.status_code == 401:
            return _failure(request, "invalid-config", "Sentry provider rejected the configured token or organization.")
        if response.status_code == 429:
            return _failure(request, "rate-limited", "Sentry provider rate limit reached; call is bounded and fail-closed.")
        if response.status_code >= 400:
            return _failure(request, "provider-error", "Sentry provider returned an error; call is fail-closed.")
        return ConnectorCallResult(
            connector_id=self.connector_id,
            capability=request.capability,
            ok=True,
            read_only=True,
            evidence_summary="Sentry provider-shaped health check succeeded.",
            output={"state": "configured", "status_code": response.status_code},
        )

    def _search_issues(self, request: ConnectorCallRequest) -> ConnectorCallResult:
        project = _optional_text(request.payload.get("project"))
        query = _optional_text(request.payload.get("query")).lower()
        if self.transport and not _fixture_mode(request.payload):
            return self._provider_issues(request, project=project, query=query)
        issues = [_redacted_mapping(issue) for issue in _RECORDED_ISSUES if _matches_issue(issue, project=project, query=query)]
        return ConnectorCallResult(
            connector_id=self.connector_id,
            capability=request.capability,
            ok=True,
            read_only=True,
            evidence_summary=f"Read {len(issues)} sanitized Sentry-style issue fixture(s); no network call performed.",
            output={"provider": "sentry-fixture", "recorded": True, "issues": issues, "pagination": {"pages_read": 1, "bounded": True}},
        )

    def _provider_issues(self, request: ConnectorCallRequest, *, project: str, query: str) -> ConnectorCallResult:
        issues: list[dict[str, Any]] = []
        cursor = _optional_text(request.payload.get("cursor"))
        for page in range(1, _MAX_PAGES + 1):
            try:
                response = self.transport(
                    "/api/0/organizations/{org_slug}/issues/",
                    {"project": project, "query": query, "cursor": cursor, "page": page, "auth_token": request.payload.get(_AUTH_TOKEN_FIELD)},
                )
            except SentryRateLimitedError:
                return _failure(request, "rate-limited", "Sentry provider rate limit reached during bounded pagination.")
            except SentryProviderError:
                return _failure(request, "provider-error", "Sentry provider failed during bounded pagination.")
            if response.status_code == 429:
                return _failure(request, "rate-limited", "Sentry provider rate limit reached during bounded pagination.")
            if response.status_code >= 400:
                return _failure(request, "provider-error", "Sentry provider returned an error during bounded pagination.")
            payload_issues = response.payload.get("issues") or response.payload.get("data") or []
            if isinstance(payload_issues, list):
                issues.extend(_redacted_mapping(item) for item in payload_issues if isinstance(item, Mapping))
            cursor = str((response.headers or {}).get("next_cursor") or response.payload.get("next_cursor") or "")
            if not cursor:
                return ConnectorCallResult(
                    connector_id=self.connector_id,
                    capability=request.capability,
                    ok=True,
                    read_only=True,
                    evidence_summary=f"Read {len(issues)} sanitized Sentry issue(s) from provider-shaped transport across {page} page(s).",
                    output={"provider": "sentry", "recorded": False, "issues": issues, "pagination": {"pages_read": page, "bounded": True}},
                )
        return ConnectorCallResult(
            connector_id=self.connector_id,
            capability=request.capability,
            ok=True,
            read_only=True,
            evidence_summary=f"Read {len(issues)} sanitized Sentry issue(s); stopped at bounded page limit.",
            output={"provider": "sentry", "recorded": False, "issues": issues, "pagination": {"pages_read": _MAX_PAGES, "bounded": True, "truncated": True}},
        )

    def _search_fixture_issues(self, request: ConnectorCallRequest) -> ConnectorCallResult:
        project = _optional_text(request.payload.get("project"))
        query = _optional_text(request.payload.get("query")).lower()
        page = max(_int_payload(request.payload, "page", 1), 1)
        per_page = min(max(_int_payload(request.payload, "per_page", 50), 1), 100)
        matched = [_redacted_mapping(issue) for issue in _RECORDED_ISSUES if _matches_issue(issue, project=project, query=query)]
        page_items, next_cursor = _page(matched, page=page, per_page=per_page)
        return ConnectorCallResult(
            connector_id=self.connector_id,
            capability=request.capability,
            ok=True,
            read_only=True,
            evidence_summary=f"Read {len(page_items)} of {len(matched)} sanitized Sentry-style issue fixture(s); no network call performed.",
            output={
                "provider": "sentry-fixture",
                "mode": _FIXTURE_MODE,
                "recorded": True,
                "issues": page_items,
                "pagination": {"page": page, "per_page": per_page, "next_cursor": next_cursor, "has_more": next_cursor is not None},
                "rate_limit": {"bounded": True, "retry_after_seconds": 0},
            },
        )

    def _read_fixture_issue_events(self, request: ConnectorCallRequest) -> ConnectorCallResult:
        issue_id = _optional_text(request.payload.get("issue_id"))
        if not issue_id:
            return ConnectorCallResult(
                connector_id=self.connector_id,
                capability=request.capability,
                ok=False,
                read_only=True,
                error="missing issue_id",
            )
        page = max(_int_payload(request.payload, "page", 1), 1)
        per_page = min(max(_int_payload(request.payload, "per_page", 50), 1), 100)
        all_events = [_redacted_mapping(event) for event in _RECORDED_EVENTS.get(issue_id, ())]
        events, next_cursor = _page(all_events, page=page, per_page=per_page)
        return ConnectorCallResult(
            connector_id=self.connector_id,
            capability=request.capability,
            ok=True,
            read_only=True,
            evidence_summary=f"Read {len(events)} of {len(all_events)} sanitized Sentry-style event fixture(s) for {issue_id}; no network call performed.",
            output={
                "provider": "sentry-fixture",
                "mode": _FIXTURE_MODE,
                "recorded": True,
                "issue_id": issue_id,
                "events": events,
                "pagination": {"page": page, "per_page": per_page, "next_cursor": next_cursor, "has_more": next_cursor is not None},
                "rate_limit": {"bounded": True, "retry_after_seconds": 0},
            },
        )

    def _search_provider_issues(self, request: ConnectorCallRequest, *, token: str) -> ConnectorCallResult:
        config_error = _config_error(request.payload)
        if config_error is not None:
            return _provider_error_result(request.capability, "invalid_config", config_error)
        url = _provider_url(request.payload, f"organizations/{_organization(request.payload)}/issues/")
        params = {
            "project": _optional_text(request.payload.get("project")),
            "query": _optional_text(request.payload.get("query")),
            "cursor": _optional_text(request.payload.get("cursor")),
            "per_page": min(max(_int_payload(request.payload, "per_page", 50), 1), 100),
        }
        response = self._transport.get(url, token=token, params=params)
        failure = _normalized_provider_failure(response)
        if failure is not None:
            return _provider_error_result(request.capability, failure[0], failure[1], retry_after=failure[2])
        payload = response.payload if isinstance(response.payload, list) else response.payload.get("issues", []) if isinstance(response.payload, Mapping) else []
        issues = [_redacted_mapping(cast(Mapping[str, Any], item)) for item in cast(list[Any], payload)]
        return ConnectorCallResult(
            connector_id=self.connector_id,
            capability=request.capability,
            ok=True,
            read_only=True,
            evidence_summary=f"Read {len(issues)} Sentry provider issue(s) through bounded read-only client.",
            output={"provider": "sentry", "mode": _REAL_MODE, "recorded": False, "issues": issues, "pagination": _pagination_from_headers(response.headers)},
        )

    def _read_provider_issue_events(self, request: ConnectorCallRequest, *, token: str) -> ConnectorCallResult:
        config_error = _config_error(request.payload)
        if config_error is not None:
            return _provider_error_result(request.capability, "invalid_config", config_error)
        issue_id = _optional_text(request.payload.get("issue_id"))
        if not issue_id:
            return ConnectorCallResult(connector_id=self.connector_id, capability=request.capability, ok=False, read_only=True, error="missing issue_id")
        url = _provider_url(request.payload, f"issues/{issue_id}/events/")
        params = {"cursor": _optional_text(request.payload.get("cursor")), "per_page": min(max(_int_payload(request.payload, "per_page", 50), 1), 100)}
        response = self._transport.get(url, token=token, params=params)
        failure = _normalized_provider_failure(response)
        if failure is not None:
            return _provider_error_result(request.capability, failure[0], failure[1], retry_after=failure[2])
        payload = response.payload if isinstance(response.payload, list) else response.payload.get("events", []) if isinstance(response.payload, Mapping) else []
        events = [_redacted_mapping(cast(Mapping[str, Any], item)) for item in cast(list[Any], payload)]
        return ConnectorCallResult(
            connector_id=self.connector_id,
            capability=request.capability,
            ok=True,
            read_only=True,
            evidence_summary=f"Read {len(events)} Sentry provider event(s) for {redact_text(issue_id)} through bounded read-only client.",
            output={"provider": "sentry", "mode": _REAL_MODE, "recorded": False, "issue_id": redact_text(issue_id), "events": events, "pagination": _pagination_from_headers(response.headers)},
        )


def _matches_issue(issue: Mapping[str, Any], *, project: str, query: str) -> bool:
    if project and str(issue.get("project", "")) != project:
        return False
    if not query:
        return True
    haystack = " ".join(str(issue.get(key, "")) for key in ("id", "short_id", "title", "level", "status")).lower()
    return query in haystack


def _provider_mode(payload: Mapping[str, Any]) -> str:
    mode = _optional_text(payload.get("provider_mode") or payload.get("mode") or _FIXTURE_MODE).lower()
    return _REAL_MODE if mode in {_REAL_MODE, "live", "provider"} else _FIXTURE_MODE


def _config_error(payload: Mapping[str, Any]) -> str | None:
    organization = _organization(payload)
    if not organization or any(char.isspace() for char in organization):
        return "invalid Sentry organization slug"
    base_url = _base_url(payload)
    if not (base_url.startswith("https://") or base_url.startswith("http://localhost") or base_url.startswith("http://127.0.0.1")):
        return "invalid Sentry base URL"
    return None


def _organization(payload: Mapping[str, Any]) -> str:
    return _optional_text(payload.get("organization") or payload.get("org") or _DEFAULT_ORG)


def _base_url(payload: Mapping[str, Any]) -> str:
    return _optional_text(payload.get("base_url") or _DEFAULT_BASE_URL).rstrip("/")


def _provider_url(payload: Mapping[str, Any], path: str) -> str:
    return f"{_base_url(payload)}/{path.lstrip('/')}"


def _optional_text(value: Any) -> str:
    return str(value or "").strip()


def _int_payload(payload: Mapping[str, Any], key: str, default: int) -> int:
    try:
        return int(payload.get(key, default))
    except (TypeError, ValueError):
        return default


def _page(items: list[dict[str, Any]], *, page: int, per_page: int) -> tuple[list[dict[str, Any]], str | None]:
    start = (page - 1) * per_page
    end = start + per_page
    next_cursor = str(page + 1) if end < len(items) else None
    return items[start:end], next_cursor


def _pagination_from_headers(headers: Mapping[str, str]) -> dict[str, Any]:
    link = headers.get("Link") or headers.get("link") or ""
    retry_after = headers.get("Retry-After") or headers.get("retry-after")
    return {"provider_link": redact_text(link), "has_more": 'rel="next"' in link, "retry_after_seconds": _safe_int(retry_after)}


def _normalized_provider_failure(response: SentryProviderResponse) -> tuple[str, str, str | None] | None:
    if response.status_code in {200, 201}:
        return None
    retry_after = response.headers.get("Retry-After") or response.headers.get("retry-after")
    if response.status_code == 401 or response.status_code == 403:
        return ("invalid_config", "sentry provider rejected credentials or permissions", retry_after)
    if response.status_code == 429:
        return ("rate_limited", "sentry provider rate limited request", retry_after or "60")
    return ("provider_error", f"sentry provider returned HTTP {response.status_code}", retry_after)


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _health_failure(state: str, message: str, *, retry_after: str | None = None) -> ConnectorCallResult:
    return ConnectorCallResult(
        connector_id=SentryReadOnlyConnector.connector_id,
        capability="health.check",
        ok=False,
        read_only=True,
        error=redact_text(message),
        evidence_summary=f"Sentry health check failed closed with state {state}.",
        output={"provider": "sentry", "mode": _REAL_MODE, "health_state": state, "retry_after_seconds": _safe_int(retry_after), "network_attempted": False},
    )


def _provider_error_result(capability: str, error_type: str, message: str, *, retry_after: str | None = None) -> ConnectorCallResult:
    return ConnectorCallResult(
        connector_id=SentryReadOnlyConnector.connector_id,
        capability=capability,
        ok=False,
        read_only=True,
        error=redact_text(message),
        evidence_summary=f"Sentry provider read failed closed with normalized error {error_type}.",
        output={"provider": "sentry", "mode": _REAL_MODE, "normalized_error": error_type, "retry_after_seconds": _safe_int(retry_after)},
    )


def _redacted_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    copied = deepcopy(dict(value))
    return cast(dict[str, Any], redact_value(copied))


def _fixture_mode(payload: Mapping[str, Any]) -> bool:
    return bool(payload.get("fixture_mode", False) or payload.get("mode") == "fixture")


def _failure(request: ConnectorCallRequest, state: str, summary: str) -> ConnectorCallResult:
    return ConnectorCallResult(
        connector_id="sentry.readonly",
        capability=request.capability,
        ok=False,
        read_only=True,
        error=state,
        evidence_summary=summary,
        output={"state": state},
    )
