"""Bounded Prometheus read-only connector with offline fixture defaults."""

from __future__ import annotations

import ipaddress
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from app.connectors.base import ConnectorCallRequest, ConnectorCallResult, ConnectorCapability
from app.services.redaction import redact_text, redact_value

_FIXTURE_MODE = "fixture"
_REAL_MODE = "real"
_DEFAULT_ALLOWED_HOSTS = ("localhost", "127.0.0.1", "::1")
_MAX_QUERY_LENGTH = 2_000
_MAX_RANGE_SECONDS = 6 * 60 * 60
_MAX_RANGE_POINTS = 1_200
_MAX_SERIES = 100
_MAX_SAMPLES_PER_SERIES = 1_200
_DEFAULT_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_DURATION_RE = re.compile(r"^(\d+)(ms|s|m|h)$")
_REQUEST_ENDPOINT_FIELDS = frozenset({"base_url", "endpoint", "endpoint_url", "url"})


@dataclass(frozen=True)
class PrometheusProviderResponse:
    status_code: int
    payload: Any = field(default_factory=dict)
    headers: Mapping[str, str] = field(default_factory=dict)


class PrometheusTransportError(RuntimeError):
    pass


class PrometheusResponseTooLargeError(PrometheusTransportError):
    pass


class PrometheusTransport(Protocol):
    def get(
        self,
        url: str,
        *,
        params: dict[str, str],
        headers: dict[str, str],
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> PrometheusProviderResponse:
        """Perform one bounded GET request."""


class UrllibPrometheusTransport:
    """Small stdlib transport used only by explicit real mode."""

    def get(
        self,
        url: str,
        *,
        params: dict[str, str],
        headers: dict[str, str],
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> PrometheusProviderResponse:
        query = urlencode(params)
        request_url = f"{url}?{query}" if query else url
        request = Request(request_url, headers=headers, method="GET")
        try:
            with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - endpoint is configuration-bound and allowlisted
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > max_response_bytes:
                    raise PrometheusResponseTooLargeError("prometheus response exceeded byte budget")
                body = response.read(max_response_bytes + 1)
                if len(body) > max_response_bytes:
                    raise PrometheusResponseTooLargeError("prometheus response exceeded byte budget")
                return PrometheusProviderResponse(
                    status_code=response.status,
                    payload=json.loads(body.decode("utf-8") or "{}"),
                    headers=dict(response.headers.items()),
                )
        except HTTPError as exc:
            body = exc.read(max_response_bytes + 1)
            if len(body) > max_response_bytes:
                raise PrometheusResponseTooLargeError("prometheus error response exceeded byte budget") from exc
            try:
                payload: Any = json.loads(body.decode("utf-8", errors="replace") or "{}")
            except json.JSONDecodeError:
                payload = {}
            return PrometheusProviderResponse(status_code=exc.code, payload=payload, headers=dict(exc.headers.items()))
        except (TimeoutError, URLError) as exc:
            raise PrometheusTransportError("prometheus provider connection failed") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PrometheusTransportError("prometheus provider returned invalid JSON") from exc


class PrometheusReadOnlyConnector:
    connector_id = "prometheus.readonly"
    capabilities: Mapping[str, ConnectorCapability] = {
        "health.check": ConnectorCapability(
            name="health.check",
            description="Check fixture or explicitly configured Prometheus read availability.",
            risk_level="read_only",
            read_only=True,
            required_role="viewer",
        ),
        "query.instant": ConnectorCapability(
            name="query.instant",
            description="Run one bounded Prometheus instant query through a configured read-only endpoint.",
            risk_level="read_only",
            read_only=True,
            required_role="viewer",
        ),
        "query.range": ConnectorCapability(
            name="query.range",
            description="Run one bounded Prometheus range query through a configured read-only endpoint.",
            risk_level="read_only",
            read_only=True,
            required_role="viewer",
        ),
    }

    def __init__(
        self,
        *,
        base_url: str | None = None,
        allowed_hosts: Sequence[str] = _DEFAULT_ALLOWED_HOSTS,
        transport: PrometheusTransport | None = None,
        timeout_seconds: float = 5.0,
        max_response_bytes: int = _DEFAULT_MAX_RESPONSE_BYTES,
    ) -> None:
        self._base_url = base_url.strip().rstrip("/") if base_url else None
        self._allowed_hosts = frozenset(host.strip().lower() for host in allowed_hosts if host.strip())
        self._transport = transport or UrllibPrometheusTransport()
        self._timeout_seconds = max(0.1, min(float(timeout_seconds), 15.0))
        self._max_response_bytes = max(1_024, min(int(max_response_bytes), _DEFAULT_MAX_RESPONSE_BYTES))

    def call(self, request: ConnectorCallRequest) -> ConnectorCallResult:
        if request.capability not in self.capabilities:
            return _failure(request, "unsupported_capability", "unsupported capability")
        mode = str(request.payload.get("provider_mode") or request.payload.get("mode") or _FIXTURE_MODE).strip().lower()
        if mode not in {_FIXTURE_MODE, _REAL_MODE}:
            return _failure(request, "invalid_mode", "provider mode must be fixture or real")
        if mode == _FIXTURE_MODE:
            return self._fixture_result(request)
        if any(field in request.payload for field in _REQUEST_ENDPOINT_FIELDS):
            return _failure(request, "endpoint_not_allowed", "request-controlled provider endpoints are not allowed")
        endpoint_error = self._endpoint_error()
        if endpoint_error is not None:
            return _failure(request, endpoint_error[0], endpoint_error[1])
        if request.capability == "health.check":
            return self._real_health(request)
        return self._real_query(request)

    def _fixture_result(self, request: ConnectorCallRequest) -> ConnectorCallResult:
        if request.capability == "health.check":
            return ConnectorCallResult(
                connector_id=self.connector_id,
                capability=request.capability,
                ok=True,
                read_only=True,
                evidence_summary="Prometheus connector health=fixture_ok; no network call performed.",
                output={"provider": "prometheus", "mode": _FIXTURE_MODE, "health_state": "fixture_ok", "network_attempted": False},
            )
        query, query_error = _validated_query(request.payload)
        if query_error is not None:
            return _failure(request, "invalid_query", query_error)
        assert query is not None
        if request.capability == "query.range":
            _, range_error = _range_params(request.payload)
            if range_error is not None:
                return _failure(request, range_error[0], range_error[1])
            series = [
                {
                    "metric": {"__name__": "http_requests_total", "job": "checkout-api", "status": "500"},
                    "values": [["1783641600", "12"], ["1783641660", "31"], ["1783641720", "47"]],
                }
            ]
            result_type = "matrix"
        else:
            series = [{"metric": {"__name__": "up", "job": "checkout-api"}, "value": ["1783641720", "1"]}]
            result_type = "vector"
        return _success(request, query=query, result_type=result_type, series=series, mode=_FIXTURE_MODE, network_attempted=False)

    def _real_health(self, request: ConnectorCallRequest) -> ConnectorCallResult:
        response = self._perform_get("/api/v1/query", {"query": "vector(1)"}, request)
        if isinstance(response, ConnectorCallResult):
            return response
        failure = _provider_failure(request, response)
        if failure is not None:
            return failure
        return ConnectorCallResult(
            connector_id=self.connector_id,
            capability=request.capability,
            ok=True,
            read_only=True,
            evidence_summary="Configured Prometheus read-only endpoint passed a bounded health query.",
            output={"provider": "prometheus", "mode": _REAL_MODE, "health_state": "configured", "network_attempted": True},
        )

    def _real_query(self, request: ConnectorCallRequest) -> ConnectorCallResult:
        query, query_error = _validated_query(request.payload)
        if query_error is not None:
            return _failure(request, "invalid_query", query_error)
        assert query is not None
        params = {"query": query}
        path = "/api/v1/query"
        if request.capability == "query.range":
            range_params, range_error = _range_params(request.payload)
            if range_error is not None:
                return _failure(request, range_error[0], range_error[1])
            params.update(range_params)
            path = "/api/v1/query_range"
        elif request.payload.get("time") not in (None, ""):
            time_value = str(request.payload["time"]).strip()
            if len(time_value) > 64 or any(ord(char) < 32 for char in time_value):
                return _failure(request, "invalid_query", "invalid instant query time")
            params["time"] = time_value
        response = self._perform_get(path, params, request)
        if isinstance(response, ConnectorCallResult):
            return response
        failure = _provider_failure(request, response)
        if failure is not None:
            return failure
        data = response.payload.get("data") if isinstance(response.payload, Mapping) else None
        if not isinstance(data, Mapping):
            return _failure(request, "invalid_response", "prometheus response is missing data")
        result_type = str(data.get("resultType", ""))
        raw_series = data.get("result")
        if result_type not in {"vector", "matrix", "scalar", "string"} or not isinstance(raw_series, Sequence) or isinstance(raw_series, (str, bytes, bytearray)):
            return _failure(request, "invalid_response", "prometheus response has an unsupported result shape")
        if result_type in {"scalar", "string"}:
            series = [{"metric": {}, "value": list(raw_series)[:2]}]
            truncated = False
        else:
            series = [_normalized_series(item, result_type) for item in list(raw_series)[:_MAX_SERIES] if isinstance(item, Mapping)]
            truncated = len(raw_series) > _MAX_SERIES
        return _success(request, query=query, result_type=result_type, series=series, mode=_REAL_MODE, network_attempted=True, truncated=truncated)

    def _perform_get(self, path: str, params: dict[str, str], request: ConnectorCallRequest) -> PrometheusProviderResponse | ConnectorCallResult:
        assert self._base_url is not None
        try:
            return self._transport.get(
                f"{self._base_url}{path}",
                params=params,
                headers={"Accept": "application/json"},
                timeout_seconds=self._timeout_seconds,
                max_response_bytes=self._max_response_bytes,
            )
        except PrometheusResponseTooLargeError:
            return _failure(request, "response_too_large", "prometheus response exceeded the configured byte budget")
        except PrometheusTransportError:
            return _failure(request, "connection_failed", "prometheus provider connection failed")
        except Exception as exc:
            return _failure(request, "transport_failure", f"prometheus transport failed: {type(exc).__name__}")

    def _endpoint_error(self) -> tuple[str, str] | None:
        if self._base_url is None:
            return ("endpoint_not_configured", "prometheus base URL is not configured")
        try:
            parsed = urlparse(self._base_url)
            hostname = (parsed.hostname or "").lower()
            _ = parsed.port
        except ValueError:
            return ("invalid_endpoint", "prometheus base URL is invalid")
        if parsed.scheme not in {"http", "https"} or not hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            return ("invalid_endpoint", "prometheus base URL is invalid")
        if hostname not in self._allowed_hosts:
            return ("endpoint_not_allowed", "prometheus host is not in the configured allowlist")
        if parsed.scheme != "https" and not _is_loopback(hostname):
            return ("https_required", "HTTPS is required for non-loopback Prometheus endpoints")
        return None


def parse_allowed_hosts(value: str | Sequence[str]) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(item.strip().lower() for item in value.split(",") if item.strip())
    return tuple(str(item).strip().lower() for item in value if str(item).strip())


def _validated_query(payload: Mapping[str, Any]) -> tuple[str | None, str | None]:
    query = str(payload.get("query", "")).strip()
    if not query:
        return None, "query is required"
    if len(query) > _MAX_QUERY_LENGTH:
        return None, "query exceeds the length budget"
    if any(ord(char) < 32 and char not in {"\t", "\n", "\r"} for char in query):
        return None, "query contains control characters"
    return query, None


def _range_params(payload: Mapping[str, Any]) -> tuple[dict[str, str], tuple[str, str] | None]:
    start = str(payload.get("start", "")).strip()
    end = str(payload.get("end", "")).strip()
    step = str(payload.get("step", "")).strip()
    if not start or not end or not step:
        return {}, ("invalid_query", "range query requires start, end, and step")
    try:
        start_seconds = _timestamp_seconds(start)
        end_seconds = _timestamp_seconds(end)
        step_seconds = _duration_seconds(step)
    except ValueError:
        return {}, ("invalid_query", "range query has an invalid timestamp or step")
    duration = end_seconds - start_seconds
    estimated_points = int(duration / step_seconds) + 1 if duration >= 0 else 0
    if duration <= 0:
        return {}, ("invalid_query", "range query end must be after start")
    if duration > _MAX_RANGE_SECONDS or estimated_points > _MAX_RANGE_POINTS:
        return {}, ("query_budget_exceeded", "range query exceeds duration or sample-point budget")
    return {"start": start, "end": end, "step": step}, None


def _timestamp_seconds(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.timestamp()


def _duration_seconds(value: str) -> float:
    try:
        seconds = float(value)
        if seconds <= 0:
            raise ValueError
        return seconds
    except ValueError:
        match = _DURATION_RE.fullmatch(value)
        if match is None:
            raise ValueError from None
        amount = int(match.group(1))
        unit = match.group(2)
        multiplier = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}[unit]
        seconds = amount * multiplier
        if seconds <= 0:
            raise ValueError from None
        return seconds


def _normalized_series(item: Mapping[str, Any], result_type: str) -> dict[str, Any]:
    metric = item.get("metric") if isinstance(item.get("metric"), Mapping) else {}
    normalized: dict[str, Any] = {"metric": {str(key): str(value) for key, value in cast(Mapping[str, Any], metric).items()}}
    if result_type == "matrix":
        candidate_values = item.get("values")
        raw_values: Sequence[Any] = candidate_values if isinstance(candidate_values, Sequence) and not isinstance(candidate_values, (str, bytes, bytearray)) else ()
        normalized["values"] = [
            _normalized_point(point)
            for point in list(raw_values)[:_MAX_SAMPLES_PER_SERIES]
            if isinstance(point, Sequence) and not isinstance(point, (str, bytes, bytearray))
        ]
    else:
        candidate_value = item.get("value")
        raw_value: Sequence[Any] = candidate_value if isinstance(candidate_value, Sequence) and not isinstance(candidate_value, (str, bytes, bytearray)) else ()
        normalized["value"] = _normalized_point(raw_value)
    redacted = redact_value(normalized)
    return dict(redacted) if isinstance(redacted, Mapping) else normalized


def _normalized_point(point: Sequence[Any]) -> list[str]:
    if len(point) < 2:
        return []
    return [str(point[0]), str(point[1])]


def _success(
    request: ConnectorCallRequest,
    *,
    query: str,
    result_type: str,
    series: Sequence[Mapping[str, Any]],
    mode: str,
    network_attempted: bool,
    truncated: bool = False,
) -> ConnectorCallResult:
    normalized_series = [_normalized_series(item, result_type) for item in series]
    observations: list[dict[str, Any]] = []
    for item in normalized_series:
        if result_type == "matrix":
            observations.append({"metric": item.get("metric", {}), "samples": item.get("values", [])})
        else:
            value = item.get("value", [])
            observations.append(
                {
                    "metric": item.get("metric", {}),
                    "timestamp": value[0] if isinstance(value, Sequence) and len(value) > 0 else None,
                    "value": value[1] if isinstance(value, Sequence) and len(value) > 1 else None,
                }
            )
    payload: dict[str, Any] = {
        "provider": "prometheus",
        "mode": mode,
        "network_attempted": network_attempted,
        "query": query,
        "result_type": result_type,
        "result_count": len(normalized_series),
        "truncated": truncated,
        "series": normalized_series,
        "evidence": {
            "evidence_type": "metric_observation",
            "source": "prometheus",
            "provider": "prometheus",
            "network_attempted": network_attempted,
            "query": query,
            "result_type": result_type,
            "observations": observations,
        },
    }
    redacted = redact_value(payload)
    output = dict(redacted) if isinstance(redacted, Mapping) else payload
    return ConnectorCallResult(
        connector_id="prometheus.readonly",
        capability=request.capability,
        ok=True,
        read_only=True,
        evidence_summary=f"Read {len(normalized_series)} normalized Prometheus {result_type} result(s) in {mode} mode.",
        output=output,
    )


def _provider_failure(request: ConnectorCallRequest, response: PrometheusProviderResponse) -> ConnectorCallResult | None:
    payload = response.payload if isinstance(response.payload, Mapping) else {}
    if response.status_code < 400 and payload.get("status") == "success":
        return None
    if response.status_code in {400, 422} or payload.get("errorType") == "bad_data":
        normalized = "invalid_query"
    elif response.status_code in {401, 403}:
        normalized = "authorization_failed"
    elif response.status_code == 429:
        normalized = "rate_limited"
    elif response.status_code >= 500:
        normalized = "provider_error"
    else:
        normalized = "invalid_response"
    detail = redact_text(str(payload.get("error") or payload.get("errorType") or "provider request failed"))
    return _failure(request, normalized, detail)


def _failure(request: ConnectorCallRequest, normalized_error: str, message: str) -> ConnectorCallResult:
    return ConnectorCallResult(
        connector_id="prometheus.readonly",
        capability=request.capability,
        ok=False,
        read_only=True,
        error=redact_text(message),
        evidence_summary=f"Prometheus read failed closed with normalized error {normalized_error}.",
        output={"provider": "prometheus", "mode": str(request.payload.get("provider_mode") or request.payload.get("mode") or _FIXTURE_MODE), "normalized_error": normalized_error},
    )


def _is_loopback(hostname: str) -> bool:
    if hostname == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False
