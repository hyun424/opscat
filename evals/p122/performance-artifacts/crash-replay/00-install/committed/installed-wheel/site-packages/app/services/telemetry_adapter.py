"""P26 read-only telemetry fixture adapters.

The module intentionally adapts local fixture payloads shaped like Prometheus,
Datadog, and Sentry responses. It does not perform live API calls, credential
loading, or remediation execution.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.proactive_risk_sentinel import TrendWindow
from app.services.redaction import redact_text, redact_value

_BOUNDARY: dict[str, bool] = {
    "local_mock_only": True,
    "fixture_adapter_only": True,
    "live_api_calls_enabled": False,
    "action_execution_enabled": False,
    "production_mutation_enabled": False,
    "default_external_model_calls": False,
}


@dataclass(frozen=True)
class TelemetryPoint:
    timestamp: str
    value: float

    def to_dict(self) -> dict[str, Any]:
        return {"timestamp": self.timestamp, "value": self.value}


@dataclass(frozen=True)
class TelemetrySeries:
    source: str
    service: str
    metric: str
    unit: str
    labels: Mapping[str, str]
    points: tuple[TelemetryPoint, ...]
    evidence_id: str

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "source": self.source,
            "service": self.service,
            "metric": self.metric,
            "unit": self.unit,
            "labels": dict(self.labels),
            "points": [point.to_dict() for point in self.points],
            "evidence_id": self.evidence_id,
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


@dataclass(frozen=True)
class TelemetryEvent:
    source: str
    service: str
    type: str
    timestamp: str
    title: str
    message: str
    labels: Mapping[str, str]
    evidence_id: str

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "source": self.source,
            "service": self.service,
            "type": self.type,
            "timestamp": self.timestamp,
            "title": self.title,
            "message": self.message,
            "labels": dict(self.labels),
            "evidence_id": self.evidence_id,
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


@dataclass(frozen=True)
class TelemetrySnapshot:
    source: str
    series: tuple[TelemetrySeries, ...]
    events: tuple[TelemetryEvent, ...] = ()
    boundary: Mapping[str, bool] | None = None

    def to_trend_windows(self) -> tuple[TrendWindow, ...]:
        windows: list[TrendWindow] = []
        for series in self.series:
            rule = _METRIC_RULES.get(series.metric)
            if rule is None or len(series.points) < 2:
                continue
            values = tuple(point.value for point in series.points)
            baseline = _float_rule(rule, "baseline", values[0])
            threshold = _float_rule(rule, "threshold", max(values) if values else 1.0)
            suggested = tuple(str(item) for item in _sequence(rule.get("suggested_approval_actions", ())))
            blocked = tuple(str(item) for item in _sequence(rule.get("blocked_actions", ())))
            evidence = _series_evidence(series)
            windows.append(
                TrendWindow(
                    id=f"telemetry-{series.source}-{series.metric}-{series.service}".replace("_", "-"),
                    service=series.service,
                    metric=series.metric,
                    risk_type=str(rule["risk_type"]),
                    window_minutes=int(rule.get("window_minutes", 60)),
                    baseline=baseline,
                    threshold=threshold,
                    values=values,
                    evidence=evidence,
                    suggested_approval_actions=suggested,
                    blocked_actions=blocked,
                    local_mock_only=True,
                )
            )
        for event in self.events:
            if _looks_like_prompt_injection(event):
                windows.append(
                    TrendWindow(
                        id=f"telemetry-{event.source}-prompt-injection-{event.evidence_id}".replace("_", "-"),
                        service=event.service,
                        metric="prompt_injection_indicator",
                        risk_type="prompt_injection_risk",
                        window_minutes=15,
                        baseline=0.0,
                        threshold=2.0,
                        values=(0.0, 1.0, 2.0, 4.0),
                        evidence=(
                            {
                                "id": event.evidence_id,
                                "source": event.source,
                                "type": event.type,
                                "title": redact_text(event.title),
                                "message": redact_text(event.message),
                            },
                        ),
                        suggested_approval_actions=("open security review",),
                        blocked_actions=("kubectl_restart", "shell_execute", "ignore_policy"),
                        local_mock_only=True,
                    )
                )
        return tuple(windows)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "source": self.source,
            "series": [item.to_dict() for item in self.series],
            "events": [item.to_dict() for item in self.events],
            "boundary": dict(self.boundary or _BOUNDARY),
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


class TelemetryAdapterRegistry:
    def __init__(self, adapters: Mapping[str, Callable[[Path], TelemetrySnapshot]]) -> None:
        self._adapters = dict(adapters)

    @classmethod
    def default(cls) -> TelemetryAdapterRegistry:
        return cls(
            {
                "prometheus": _adapt_prometheus,
                "datadog": _adapt_datadog,
                "sentry": _adapt_sentry,
            }
        )

    def fixture_matrix(self) -> dict[str, str]:
        return {
            "prometheus": "prometheus_query_range.json",
            "datadog": "datadog_timeseries.json",
            "sentry": "sentry_issues.json",
        }

    def adapt(self, source: str, path: str | Path) -> TelemetrySnapshot:
        normalized = source.lower().strip()
        adapter = self._adapters.get(normalized)
        if adapter is None:
            raise ValueError(f"unsupported telemetry source: {source}")
        return adapter(Path(path))


_METRIC_RULES: dict[str, Mapping[str, Any]] = {
    "db_pool_wait_seconds_p95": {
        "risk_type": "connection_pool_saturation",
        "baseline": 0.08,
        "threshold": 1.0,
        "window_minutes": 60,
        "suggested_approval_actions": ("pool_config_change", "rollback"),
        "blocked_actions": ("database_session_kill", "kubectl_restart", "shell_execute"),
    },
    "http_5xx_rate": {
        "risk_type": "error_budget_burn",
        "baseline": 0.005,
        "threshold": 0.05,
        "window_minutes": 60,
        "suggested_approval_actions": ("traffic_shift", "rollback"),
        "blocked_actions": ("kubectl_restart", "shell_execute"),
    },
    "system.disk.in_use": {
        "risk_type": "disk_full_eta",
        "baseline": 70.0,
        "threshold": 95.0,
        "window_minutes": 60,
        "suggested_approval_actions": ("log_level_change", "cleanup_job"),
        "blocked_actions": ("rm_rf", "shell_execute"),
    },
    "queue.lag.seconds": {
        "risk_type": "queue_sla_breach",
        "baseline": 30.0,
        "threshold": 300.0,
        "window_minutes": 60,
        "suggested_approval_actions": ("scale_consumer",),
        "blocked_actions": ("purge_queue", "shell_execute"),
    },
    "sentry.issue.count": {
        "risk_type": "error_budget_burn",
        "baseline": 1.0,
        "threshold": 10.0,
        "window_minutes": 60,
        "suggested_approval_actions": ("rollback", "traffic_shift"),
        "blocked_actions": ("kubectl_restart", "shell_execute"),
    },
}


def adapt_telemetry_fixture(source: str, path: str | Path) -> TelemetrySnapshot:
    return TelemetryAdapterRegistry.default().adapt(source, path)


def build_telemetry_report(snapshots: Sequence[TelemetrySnapshot]) -> dict[str, Any]:
    windows = [window for snapshot in snapshots for window in snapshot.to_trend_windows()]
    payload = {
        "summary": {
            "snapshot_count": len(snapshots),
            "series_count": sum(len(snapshot.series) for snapshot in snapshots),
            "event_count": sum(len(snapshot.events) for snapshot in snapshots),
            "trend_window_count": len(windows),
        },
        "boundary": dict(_BOUNDARY),
        "snapshots": [snapshot.to_dict() for snapshot in snapshots],
        "trend_windows": [window.to_dict() for window in windows],
    }
    redacted = redact_value(payload)
    return dict(redacted) if isinstance(redacted, Mapping) else payload


def render_telemetry_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary", {}) if isinstance(payload.get("summary"), Mapping) else {}
    boundary = payload.get("boundary", {}) if isinstance(payload.get("boundary"), Mapping) else {}
    lines = [
        "# OpsCat Telemetry Adapter Report",
        "",
        "Boundary: read-only fixture adapter; no-auth/local-mock by default; no live API calls; no remediation execution; no production mutation; does not claim unattended production operation.",
        "",
        "## Summary",
        f"- Snapshots: {summary.get('snapshot_count')}",
        f"- Series: {summary.get('series_count')}",
        f"- Events: {summary.get('event_count')}",
        f"- Trend windows: {summary.get('trend_window_count')}",
        "",
        "## Boundary",
        f"- live_api_calls_enabled: {boundary.get('live_api_calls_enabled')}",
        f"- action_execution_enabled: {boundary.get('action_execution_enabled')}",
        f"- production_mutation_enabled: {boundary.get('production_mutation_enabled')}",
        "",
        "## Snapshots",
    ]
    snapshots = payload.get("snapshots", [])
    if isinstance(snapshots, Sequence) and not isinstance(snapshots, (str, bytes, bytearray)):
        for snapshot in snapshots:
            if isinstance(snapshot, Mapping):
                lines.append(
                    f"- `{snapshot.get('source')}` series={len(_sequence(snapshot.get('series', [])))} events={len(_sequence(snapshot.get('events', [])))}"
                )
    lines.extend(["", "## Trend Windows"])
    trend_windows = payload.get("trend_windows", [])
    if isinstance(trend_windows, Sequence) and not isinstance(trend_windows, (str, bytes, bytearray)):
        for window in trend_windows:
            if isinstance(window, Mapping):
                lines.append(f"- `{window.get('id')}` service={window.get('service')} risk={window.get('risk_type')} metric={window.get('metric')}")
    return "\n".join(lines) + "\n"


def write_telemetry_outputs(payload: Mapping[str, Any], *, output_json: str | Path | None = None, output_md: str | Path | None = None) -> None:
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(render_telemetry_markdown(payload), encoding="utf-8")


def _adapt_prometheus(path: Path) -> TelemetrySnapshot:
    data = _read_mapping(path)
    raw_results = _sequence(_as_mapping(data.get("data", {})).get("result", ()))
    series: list[TelemetrySeries] = []
    for index, item in enumerate(raw_results, start=1):
        if not isinstance(item, Mapping):
            continue
        metric_labels = {str(key): str(value) for key, value in _as_mapping(item.get("metric", {})).items()}
        metric = metric_labels.get("__name__") or metric_labels.get("metric") or "unknown_metric"
        service = metric_labels.get("service") or metric_labels.get("job") or "unknown-service"
        unit = metric_labels.get("unit") or _unit_for_metric(metric)
        points = _normalize_points(_sequence(item.get("values", ())))
        labels = {key: value for key, value in metric_labels.items() if key not in {"__name__", "metric", "unit"}}
        series.append(TelemetrySeries("prometheus", service, metric, unit, labels, points, f"prometheus-series-{index}"))
    return TelemetrySnapshot(source="prometheus", series=tuple(series), boundary=_BOUNDARY)


def _adapt_datadog(path: Path) -> TelemetrySnapshot:
    data = _read_mapping(path)
    series: list[TelemetrySeries] = []
    for index, item in enumerate(_sequence(data.get("series", ())), start=1):
        if not isinstance(item, Mapping):
            continue
        metric = str(item.get("metric", "unknown_metric"))
        labels = _parse_datadog_tags(item)
        service = labels.get("service", str(item.get("service", "unknown-service")))
        unit = _datadog_unit(item.get("unit", _unit_for_metric(metric)))
        points = _normalize_points(_sequence(item.get("pointlist", ())))
        series.append(TelemetrySeries("datadog", service, metric, unit, labels, points, f"datadog-series-{index}"))
    events: list[TelemetryEvent] = []
    for index, item in enumerate(_sequence(data.get("events", ())), start=1):
        if not isinstance(item, Mapping):
            labels = {}
            continue
        labels = _parse_datadog_tags(item)
        service = labels.get("service", str(item.get("service", "unknown-service")))
        events.append(
            TelemetryEvent(
                source="datadog",
                service=service,
                type=str(item.get("type", "event")),
                timestamp=_normalize_timestamp(item.get("timestamp", "")),
                title=str(item.get("title", "Datadog event")),
                message=str(item.get("text", item.get("message", ""))),
                labels=labels,
                evidence_id=f"datadog-event-{index}",
            )
        )
    return TelemetrySnapshot(source="datadog", series=tuple(series), events=tuple(events), boundary=_BOUNDARY)


def _adapt_sentry(path: Path) -> TelemetrySnapshot:
    data = _read_mapping(path)
    series: list[TelemetrySeries] = []
    events: list[TelemetryEvent] = []
    for index, issue in enumerate(_sequence(data.get("issues", ())), start=1):
        if not isinstance(issue, Mapping):
            continue
        service = str(issue.get("service", issue.get("project", "unknown-service")))
        count = float(issue.get("count", 1) or 1)
        last_seen = _normalize_timestamp(issue.get("lastSeen", issue.get("last_seen", "")))
        labels = {
            "project": str(issue.get("project", service)),
            "level": str(issue.get("level", "error")),
            "culprit": str(issue.get("culprit", "unknown")),
        }
        values = _issue_count_values(count)
        points = tuple(TelemetryPoint(_offset_timestamp(last_seen, minute_offset), value) for minute_offset, value in zip((-45, -30, -15, 0), values, strict=True))
        series.append(TelemetrySeries("sentry", service, "sentry.issue.count", "count", labels, points, f"sentry-issue-series-{index}"))
        message = str(issue.get("message", issue.get("title", "")))
        events.append(
            TelemetryEvent(
                source="sentry",
                service=service,
                type="issue",
                timestamp=last_seen,
                title=str(issue.get("title", "Sentry issue")),
                message=message,
                labels=labels,
                evidence_id=f"sentry-issue-{index}",
            )
        )
        for event_index, event in enumerate(_sequence(issue.get("events", ())), start=1):
            if not isinstance(event, Mapping):
                continue
            events.append(
                TelemetryEvent(
                    source="sentry",
                    service=service,
                    type=str(event.get("type", "event")),
                    timestamp=_normalize_timestamp(event.get("timestamp", last_seen)),
                    title=str(event.get("title", issue.get("title", "Sentry event"))),
                    message=str(event.get("message", event.get("request", ""))),
                    labels={**labels, **{str(key): str(value) for key, value in _as_mapping(event.get("tags", {})).items()}},
                    evidence_id=f"sentry-event-{index}-{event_index}",
                )
            )
    return TelemetrySnapshot(source="sentry", series=tuple(series), events=tuple(events), boundary=_BOUNDARY)


def _read_mapping(path: Path) -> Mapping[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError(f"telemetry fixture must be an object: {path}")
    return data


def _normalize_points(raw_points: Sequence[Any]) -> tuple[TelemetryPoint, ...]:
    deduped: dict[str, TelemetryPoint] = {}
    for raw in raw_points:
        if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)) and len(raw) >= 2:
            timestamp = _normalize_timestamp(raw[0])
            try:
                value = float(raw[1])
            except (TypeError, ValueError):
                continue
            deduped[timestamp] = TelemetryPoint(timestamp, value)
        elif isinstance(raw, Mapping):
            timestamp = _normalize_timestamp(raw.get("timestamp", raw.get("ts", "")))
            try:
                value = float(raw.get("value", 0.0))
            except (TypeError, ValueError):
                continue
            deduped[timestamp] = TelemetryPoint(timestamp, value)
    return tuple(deduped[key] for key in sorted(deduped))


def _normalize_timestamp(value: Any) -> str:
    if isinstance(value, int | float):
        numeric = float(value)
        if numeric > 10_000_000_000:
            numeric = numeric / 1000.0
        return datetime.fromtimestamp(numeric, tz=UTC).isoformat().replace("+00:00", "Z")
    text = str(value)
    if not text:
        return "1970-01-01T00:00:00Z"
    try:
        numeric = float(text)
    except ValueError:
        return text.replace("+00:00", "Z")
    if numeric > 10_000_000_000:
        numeric = numeric / 1000.0
    return datetime.fromtimestamp(numeric, tz=UTC).isoformat().replace("+00:00", "Z")


def _offset_timestamp(timestamp: str, minutes: int) -> str:
    if not timestamp.endswith("Z"):
        return timestamp
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return timestamp
    return datetime.fromtimestamp(dt.timestamp() + minutes * 60, tz=UTC).isoformat().replace("+00:00", "Z")


def _parse_datadog_tags(item: Mapping[str, Any]) -> dict[str, str]:
    tags: dict[str, str] = {}
    raw_tags = item.get("tags", item.get("scope", ()))
    if isinstance(raw_tags, str):
        parts: Sequence[Any] = tuple(part.strip() for part in raw_tags.split(",") if part.strip())
    else:
        parts = _sequence(raw_tags)
    for tag in parts:
        text = str(tag)
        if ":" in text:
            key, value = text.split(":", 1)
            tags[key] = value
    return tags


def _datadog_unit(raw: Any) -> str:
    if isinstance(raw, str):
        return raw
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
        for item in raw:
            if isinstance(item, Mapping) and item.get("short_name"):
                return str(item["short_name"])
            if isinstance(item, str):
                return item
    return "unit"


def _unit_for_metric(metric: str) -> str:
    if metric.endswith("seconds") or metric.endswith("seconds_p95"):
        return "seconds"
    if metric.endswith("rate"):
        return "ratio"
    if metric.endswith("in_use"):
        return "percent"
    if metric.endswith("count"):
        return "count"
    return "unit"


def _series_evidence(series: TelemetrySeries) -> tuple[Mapping[str, Any], ...]:
    current = series.points[-1].value if series.points else 0.0
    return (
        {
            "id": series.evidence_id,
            "source": series.source,
            "service": series.service,
            "metric": series.metric,
            "unit": series.unit,
            "point_count": len(series.points),
            "current": current,
            "labels": dict(series.labels),
        },
    )


def _looks_like_prompt_injection(event: TelemetryEvent) -> bool:
    lowered = f"{event.title} {event.message}".lower()
    return "ignore policy" in lowered or "kubectl restart" in lowered or "prompt injection" in lowered


def _issue_count_values(count: float) -> tuple[float, float, float, float]:
    return (max(1.0, round(count * 0.15, 2)), max(2.0, round(count * 0.3, 2)), max(4.0, round(count * 0.6, 2)), count)


def _float_rule(rule: Mapping[str, Any], key: str, default: float) -> float:
    try:
        return float(rule.get(key, default))
    except (TypeError, ValueError):
        return default


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()
