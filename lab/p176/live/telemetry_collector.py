"""Read-only P176 live lab telemetry normalizer."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import parse_qs, urlsplit

SCHEMA_VERSION = "p176.live_normalized_telemetry.v1"
TELEMETRY_CLASSES = (
    "metrics",
    "logs",
    "traces",
    "deploy_history",
    "host_state",
    "container_state",
    "topology",
    "dependency_health",
)
REDACTED = "[REDACTED]"
_SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "card_number",
        "cookie",
        "cvv",
        "password",
        "secret",
        "secret_name",
        "sentry_key",
        "sentry_secret",
        "token",
    }
)
_BEARER_RE = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
_ASSIGNMENT_RE = re.compile(
    r"\b(api[_-]?key|authorization|dsn|password|secret|sentry[_-]?key|sentry[_-]?secret|[a-z0-9_-]*token)=([^\s,;]+)",
    re.IGNORECASE,
)
_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PROVIDER_TOKEN_RE = re.compile(r"\b(sk_(?:live|test)_[A-Za-z0-9_=-]+|xox[baprs]-[A-Za-z0-9-]+)\b", re.IGNORECASE)
ALLOWED_UPSTREAM_ENDPOINT = "http://10.176.0.10:8000"
ALLOWED_FAULT_SIGNAL_ENDPOINT = "http://fault-controller:8091"
MAX_UPSTREAM_RESPONSE_BYTES = 16 * 1024


class TelemetryCollectorError(ValueError):
    """Raised when observer telemetry cannot prove its private target binding."""


def collect_normalized_evidence(observed: dict[str, Any], *, run_id: str) -> dict[str, Any]:
    snapshot = deepcopy(observed)
    sources: dict[str, dict[str, Any]] = {}
    for source_class in TELEMETRY_CLASSES:
        records = snapshot.get(source_class, [])
        if not isinstance(records, list):
            records = [records]
        normalized_records = [_normalize_record(record) for record in records]
        sources[source_class] = {
            "source_class": source_class,
            "records": len(normalized_records),
            "items": normalized_records,
        }

    evidence: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "read_only": True,
        "mutation_count": 0,
        "sources": sources,
    }
    evidence["evidence_hash"] = stable_hash(evidence)
    return evidence


def build_runtime_evidence_snapshot(
    *,
    source_class: str,
    run_id: str,
    symptoms: Mapping[str, Any],
    observed_at: str | None = None,
    received_at: str | None = None,
    healthy_profile: str = "quiet",
    healthy_service_id: str | None = None,
    window_id: str | None = None,
) -> dict[str, Any]:
    if source_class not in TELEMETRY_CLASSES:
        raise TelemetryCollectorError("source_class_not_allowed")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{2,127}", run_id):
        raise TelemetryCollectorError("run_id_invalid")
    if healthy_profile not in {"quiet", "baseline_variance"}:
        raise TelemetryCollectorError("healthy_profile_invalid")
    if window_id is not None and not re.fullmatch(r"p176-window-[0-9]{3}", window_id):
        raise TelemetryCollectorError("window_id_invalid")
    if (window_id is None) != (healthy_service_id is None):
        raise TelemetryCollectorError("healthy_window_binding_invalid")
    if healthy_service_id is not None and not re.fullmatch(r"[a-z][a-z0-9-]{2,63}", healthy_service_id):
        raise TelemetryCollectorError("healthy_service_id_invalid")
    if healthy_profile == "baseline_variance" and window_id is None:
        raise TelemetryCollectorError("healthy_window_binding_invalid")
    signals = symptoms.get("signals")
    active_count = symptoms.get("active_fault_count")
    if not isinstance(signals, list) or type(active_count) is not int or active_count != len(signals):
        raise TelemetryCollectorError("fault_symptoms_invalid")
    projected_signals: list[dict[str, Any]] = []
    for signal in signals:
        if not isinstance(signal, Mapping):
            raise TelemetryCollectorError("fault_symptoms_invalid")
        service_id = signal.get("service_id")
        status = signal.get("status")
        codes = signal.get("signal_codes")
        if not isinstance(service_id, str) or status != "degraded" or not isinstance(codes, list):
            raise TelemetryCollectorError("fault_symptoms_invalid")
        projected_signals.append(
            {
                "service_id": service_id,
                "status": status,
                "signal_codes": sorted({str(code) for code in codes if str(code)}),
            }
        )
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    if active_count and healthy_profile != "quiet":
        raise TelemetryCollectorError("healthy_profile_with_active_fault")
    benign_codes = [f"{source_class}_baseline_variance"] if healthy_profile == "baseline_variance" else []
    request_binding = {
        "run_id": run_id,
        "source_class": source_class,
        "window_id": window_id,
        "service_id": healthy_service_id,
        "healthy_profile": healthy_profile,
    }
    summary = {
        "status": "degraded" if active_count else "healthy",
        "source_class": source_class,
        "affected_services": sorted(
            {
                *{item["service_id"] for item in projected_signals},
                *([healthy_service_id] if benign_codes and healthy_service_id else []),
            }
        ),
        "signal_codes": sorted({code for item in projected_signals for code in item["signal_codes"]} | set(benign_codes)),
        "active_signal_count": active_count,
        "benign_variation_count": len(benign_codes),
        "observed_services": [healthy_service_id] if healthy_service_id else [],
    }
    content = {
        "run_id": run_id,
        "source_class": source_class,
        "signals": projected_signals,
        "healthy_profile": healthy_profile,
        "healthy_service_id": healthy_service_id if benign_codes else None,
        "benign_codes": benign_codes,
        "request_binding": request_binding,
    }
    return {
        "schema_version": "p176.live_runtime_evidence_snapshot.v1",
        "source_class": source_class,
        "request_binding_hash": f"sha256:{stable_hash(request_binding)}",
        "observed_at": observed_at or now,
        "received_at": received_at or now,
        "freshness_bound_seconds": 60,
        "content_hash": f"sha256:{stable_hash(content)}",
        "redaction_receipt_hash": f"sha256:{stable_hash({'redacted': True, 'content': content})}",
        "summary": summary,
    }


def dispatch_telemetry_request(
    *,
    path: str,
    symptom_loader: Any,
    upstream_endpoint: str | None = None,
    opener: Any = urllib_request.urlopen,
    observed_at: str | None = None,
    received_at: str | None = None,
) -> tuple[int, dict[str, Any]]:
    parsed = urlsplit(path)
    if parsed.path == "/v1/capabilities" and not parsed.query:
        return 200, {
            "schema_version": "p176.live_telemetry_capabilities.v1",
            "read_only": True,
            "source_classes": list(TELEMETRY_CLASSES),
        }
    if parsed.path != "/v1/evidence":
        return 404, {"error": "not_found"}
    query = parse_qs(parsed.query, keep_blank_values=True)
    base_keys = {"source_class", "run_id"}
    healthy_keys = base_keys | {"window_id", "service_id", "healthy_profile"}
    if frozenset(query) not in {frozenset(base_keys), frozenset(healthy_keys)} or any(
        len(values) != 1 for values in query.values()
    ):
        return 400, {"error": "evidence_query_invalid"}
    source_class = query["source_class"][0]
    run_id = query["run_id"][0]
    healthy_profile = query.get("healthy_profile", ["quiet"])[0]
    healthy_service_id = query.get("service_id", [None])[0]
    window_id = query.get("window_id", [None])[0]
    if window_id is not None and not re.fullmatch(r"p176-window-[0-9]{3}", window_id):
        return 400, {"error": "window_id_invalid"}
    try:
        if upstream_endpoint is not None:
            return 200, fetch_upstream_runtime_evidence(upstream_endpoint, path=path, opener=opener)
        symptoms = symptom_loader()
        return 200, build_runtime_evidence_snapshot(
            source_class=source_class,
            run_id=run_id,
            symptoms=symptoms,
            observed_at=observed_at,
            received_at=received_at,
            healthy_profile=healthy_profile,
            healthy_service_id=healthy_service_id,
            window_id=window_id,
        )
    except TelemetryCollectorError as exc:
        return 400, {"error": str(exc)}


def load_fault_symptoms(
    endpoint: str = ALLOWED_FAULT_SIGNAL_ENDPOINT,
    *,
    opener: Any = urllib_request.urlopen,
    timeout_seconds: float = 2.0,
) -> dict[str, Any]:
    if endpoint != ALLOWED_FAULT_SIGNAL_ENDPOINT:
        raise TelemetryCollectorError("fault_signal_endpoint_not_allowed")
    return _read_json_response(f"{endpoint}/v1/symptoms", opener=opener, timeout_seconds=timeout_seconds)


def fetch_upstream_runtime_evidence(
    endpoint: str,
    *,
    path: str,
    opener: Any = urllib_request.urlopen,
    timeout_seconds: float = 2.0,
) -> dict[str, Any]:
    if endpoint != ALLOWED_UPSTREAM_ENDPOINT:
        raise TelemetryCollectorError("upstream_endpoint_not_allowed")
    payload = _read_json_response(f"{endpoint}{path}", opener=opener, timeout_seconds=timeout_seconds)
    if payload.get("schema_version") != "p176.live_runtime_evidence_snapshot.v1":
        raise TelemetryCollectorError("upstream_evidence_invalid")
    return payload


def _read_json_response(url: str, *, opener: Any, timeout_seconds: float) -> dict[str, Any]:
    try:
        with opener(url, timeout=timeout_seconds) as response:
            if response.status != 200:
                raise TelemetryCollectorError("upstream_response_invalid")
            raw = response.read(MAX_UPSTREAM_RESPONSE_BYTES + 1)
    except TelemetryCollectorError:
        raise
    except (OSError, urllib_error.URLError) as exc:
        raise TelemetryCollectorError("upstream_unreachable") from exc
    if len(raw) > MAX_UPSTREAM_RESPONSE_BYTES:
        raise TelemetryCollectorError("upstream_response_too_large")
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TelemetryCollectorError("upstream_response_invalid") from exc
    if not isinstance(payload, dict):
        raise TelemetryCollectorError("upstream_response_invalid")
    return payload


def _normalize_record(record: Any) -> dict[str, Any]:
    redacted = redact_value(deepcopy(record))
    if isinstance(redacted, dict):
        return {str(key): redacted[key] for key in sorted(redacted)}
    return {"value": redacted}


def stable_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return {key: REDACTED if _is_sensitive_key(str(key)) else redact_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact_value(item) for item in value]
    return value


def redact_text(text: str) -> str:
    redacted = _BEARER_RE.sub("Bearer " + REDACTED, text)
    redacted = _ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}={REDACTED}", redacted)
    redacted = _PROVIDER_TOKEN_RE.sub(REDACTED, redacted)
    return _EMAIL_RE.sub(REDACTED, redacted)


def verify_upstream_health(
    endpoint: str,
    *,
    opener: Any = urllib_request.urlopen,
    timeout_seconds: float = 2.0,
) -> dict[str, Any]:
    if endpoint != ALLOWED_UPSTREAM_ENDPOINT:
        raise TelemetryCollectorError("upstream_endpoint_not_allowed")
    try:
        with opener(f"{endpoint}/health", timeout=timeout_seconds) as response:
            if response.status != 200:
                raise TelemetryCollectorError("upstream_health_invalid")
            raw = response.read(MAX_UPSTREAM_RESPONSE_BYTES + 1)
    except TelemetryCollectorError:
        raise
    except (OSError, urllib_error.URLError) as exc:
        raise TelemetryCollectorError("upstream_health_unreachable") from exc
    if len(raw) > MAX_UPSTREAM_RESPONSE_BYTES:
        raise TelemetryCollectorError("upstream_health_response_too_large")
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TelemetryCollectorError("upstream_health_invalid") from exc
    if not isinstance(payload, dict) or payload != {"status": "healthy", "component": "telemetry-collector"}:
        raise TelemetryCollectorError("upstream_health_invalid")
    return payload


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return normalized in _SENSITIVE_KEYS or normalized.endswith(("_key", "_token", "_secret", "_password"))


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        upstream = os.environ.get("P176_UPSTREAM_ENDPOINT")
        if self.path == "/health":
            try:
                if upstream:
                    verify_upstream_health(upstream)
                payload = {"status": "healthy", "component": "telemetry-collector"}
                status = 200
            except TelemetryCollectorError:
                payload = {
                    "status": "degraded",
                    "component": "telemetry-collector",
                    "reason": "upstream_unhealthy",
                }
                status = 503
        else:
            status, payload = dispatch_telemetry_request(
                path=self.path,
                symptom_loader=load_fault_symptoms,
                upstream_endpoint=upstream,
            )
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return None


def main() -> None:
    server = HTTPServer(("0.0.0.0", 8090), _HealthHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
