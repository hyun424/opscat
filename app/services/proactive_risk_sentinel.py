"""P24 proactive risk sentinel for local/mock pre-incident forecasting."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.redaction import redact_text, redact_value

_DECREASING_RISKS = {"certificate_expiry_risk", "observability_gap"}
_BLOCK_MARKERS = ("kill", "restart", "shell", "kubectl", "rm_rf", "database_mutation", "disable_tls", "purge_queue")


@dataclass(frozen=True)
class TrendWindow:
    id: str
    service: str
    metric: str
    risk_type: str
    window_minutes: int
    baseline: float
    threshold: float
    values: tuple[float, ...]
    evidence: tuple[Mapping[str, Any], ...]
    suggested_approval_actions: tuple[str, ...] = ()
    blocked_actions: tuple[str, ...] = ()
    local_mock_only: bool = True

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TrendWindow:
        values = tuple(float(item) for item in _sequence(data.get("values", ())))
        evidence = tuple(dict(item) for item in _sequence(data.get("evidence", ())) if isinstance(item, Mapping))
        return cls(
            id=str(data.get("id", "")),
            service=str(data.get("service", "")),
            metric=str(data.get("metric", "")),
            risk_type=str(data.get("risk_type", "")),
            window_minutes=int(data.get("window_minutes", 0) or 0),
            baseline=float(data.get("baseline", 0.0) or 0.0),
            threshold=float(data.get("threshold", 0.0) or 0.0),
            values=values,
            evidence=evidence,
            suggested_approval_actions=tuple(str(item) for item in _sequence(data.get("suggested_approval_actions", ()))),
            blocked_actions=tuple(str(item) for item in _sequence(data.get("blocked_actions", ()))),
            local_mock_only=bool(data.get("local_mock_only", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "service": redact_text(self.service),
            "metric": self.metric,
            "risk_type": self.risk_type,
            "window_minutes": self.window_minutes,
            "baseline": self.baseline,
            "threshold": self.threshold,
            "values": list(self.values),
            "evidence": [dict(redact_value(item)) for item in self.evidence],
            "suggested_approval_actions": list(self.suggested_approval_actions),
            "blocked_actions": list(self.blocked_actions),
            "local_mock_only": self.local_mock_only,
        }


@dataclass(frozen=True)
class RiskSignal:
    signal_id: str
    service: str
    metric: str
    risk_type: str
    trend: str
    current: float
    baseline: float
    threshold: float
    baseline_ratio: float
    threshold_distance: float
    eta_minutes: int | None
    confidence: float
    evidence_ids: tuple[str, ...]
    window: TrendWindow

    @classmethod
    def from_window(cls, window: TrendWindow) -> RiskSignal:
        current = window.values[-1] if window.values else 0.0
        first = window.values[0] if window.values else current
        decreasing = window.risk_type in _DECREASING_RISKS and window.threshold < window.baseline
        total_delta = (first - current) if decreasing else (current - first)
        step_count = max(1, len(window.values) - 1)
        step_minutes = max(1.0, window.window_minutes / max(1, len(window.values)))
        slope_per_step = total_delta / step_count
        remaining = (current - window.threshold) if decreasing else (window.threshold - current)
        eta = None
        if slope_per_step > 0:
            eta = max(0, round((remaining / slope_per_step) * step_minutes)) if remaining > 0 else 0
        ratio_denominator = abs(window.baseline) if abs(window.baseline) > 1e-9 else 1.0
        baseline_ratio = round(abs(current - window.baseline) / ratio_denominator, 4)
        distance_denominator = abs(window.threshold - window.baseline) or 1.0
        threshold_distance = round(max(0.0, abs(window.threshold - current) / abs(distance_denominator)), 4)
        trend = _trend(window, total_delta, current)
        confidence = _confidence(window, trend, baseline_ratio, threshold_distance, eta)
        evidence_ids = tuple(str(item.get("id", "")) for item in window.evidence if isinstance(item, Mapping) and item.get("id"))
        return cls(
            signal_id=f"signal-{window.id}",
            service=window.service,
            metric=window.metric,
            risk_type=window.risk_type,
            trend=trend,
            current=round(current, 4),
            baseline=window.baseline,
            threshold=window.threshold,
            baseline_ratio=baseline_ratio,
            threshold_distance=threshold_distance,
            eta_minutes=eta,
            confidence=confidence,
            evidence_ids=evidence_ids,
            window=window,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "service": redact_text(self.service),
            "metric": self.metric,
            "risk_type": self.risk_type,
            "trend": self.trend,
            "current": self.current,
            "baseline": self.baseline,
            "threshold": self.threshold,
            "baseline_ratio": self.baseline_ratio,
            "threshold_distance": self.threshold_distance,
            "eta_minutes": self.eta_minutes,
            "confidence": self.confidence,
            "evidence_ids": list(self.evidence_ids),
        }


@dataclass(frozen=True)
class PreventiveAction:
    id: str
    capability: str
    route: str
    description: str
    action_execution_enabled: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "capability": self.capability,
            "route": self.route,
            "description": redact_text(self.description),
            "action_execution_enabled": self.action_execution_enabled,
        }


@dataclass(frozen=True)
class PreventionPlan:
    signal_id: str
    auto_allowed_actions: tuple[PreventiveAction, ...]
    approval_required_actions: tuple[PreventiveAction, ...]
    blocked_actions: tuple[PreventiveAction, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "auto_allowed_actions": [item.to_dict() for item in self.auto_allowed_actions],
            "approval_required_actions": [item.to_dict() for item in self.approval_required_actions],
            "blocked_actions": [item.to_dict() for item in self.blocked_actions],
        }


@dataclass(frozen=True)
class RiskForecast:
    forecast_id: str
    signal: RiskSignal
    route: str
    eta_minutes: int | None
    confidence: float
    impact: str
    prevention_plan: PreventionPlan

    def to_dict(self) -> dict[str, Any]:
        return {
            "forecast_id": self.forecast_id,
            "risk_type": self.signal.risk_type,
            "service": redact_text(self.signal.service),
            "metric": self.signal.metric,
            "route": self.route,
            "eta_minutes": self.eta_minutes,
            "confidence": self.confidence,
            "impact": self.impact,
            "evidence_ids": list(self.signal.evidence_ids),
            "signal": self.signal.to_dict(),
            "prevention_plan": self.prevention_plan.to_dict(),
        }


@dataclass(frozen=True)
class ProactiveRiskResult:
    windows: tuple[TrendWindow, ...]
    signals: tuple[RiskSignal, ...]
    forecasts: tuple[RiskForecast, ...]

    def to_dict(self) -> dict[str, Any]:
        forecast_payloads = [forecast.to_dict() for forecast in self.forecasts]
        unsafe_auto = sum(
            1
            for forecast in forecast_payloads
            for action in forecast["prevention_plan"]["auto_allowed_actions"]
            if action.get("action_execution_enabled") or action.get("capability") not in {"read_only_diagnostic", "report", "notification_draft"}
        )
        lead_times = [forecast.eta_minutes for forecast in self.forecasts if forecast.eta_minutes is not None and forecast.eta_minutes > 0]
        payload = {
            "summary": {
                "window_count": len(self.windows),
                "signal_count": len(self.signals),
                "forecast_count": len(self.forecasts),
            },
            "score": {
                "unsafe_auto_action_count": unsafe_auto,
                "lead_time_minutes_min": min(lead_times) if lead_times else 0,
                "lead_time_minutes_median": _median(lead_times),
                "blocked_forecast_count": sum(1 for forecast in self.forecasts if forecast.route == "blocked"),
                "monitor_forecast_count": sum(1 for forecast in self.forecasts if forecast.route == "monitor"),
            },
            "boundary": {
                "local_mock_only": True,
                "action_execution_enabled": False,
                "production_mutation_enabled": False,
                "default_external_model_calls": False,
            },
            "signals": [signal.to_dict() for signal in self.signals],
            "forecasts": forecast_payloads,
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


class PreventiveActionPlanner:
    def plan(self, signal: RiskSignal) -> PreventionPlan:
        auto_allowed = (
            PreventiveAction("read-evidence", "read_only_diagnostic", "auto_allowed", f"Collect read-only diagnostics for {signal.risk_type}"),
            PreventiveAction("write-report", "report", "auto_allowed", f"Draft proactive risk report for {signal.service}"),
            PreventiveAction("draft-warning", "notification_draft", "auto_allowed", f"Draft warning with ETA {signal.eta_minutes} minutes"),
        )
        approval_required = tuple(
            PreventiveAction(f"approve-{index}", _capability_for(action), "approval_required", f"Operator approval required before {action}")
            for index, action in enumerate(signal.window.suggested_approval_actions, start=1)
        )
        blocked = tuple(
            PreventiveAction(f"block-{index}", _capability_for(action), "blocked", f"Blocked preventive action: {action}")
            for index, action in enumerate(signal.window.blocked_actions, start=1)
        )
        return PreventionPlan(signal.signal_id, auto_allowed, approval_required, blocked)


class ProactiveRiskSentinel:
    def __init__(self, planner: PreventiveActionPlanner | None = None) -> None:
        self.planner = planner or PreventiveActionPlanner()

    def run(self, windows: Sequence[TrendWindow], *, max_windows: int | None = None) -> ProactiveRiskResult:
        selected = tuple(windows[:max_windows] if max_windows is not None else windows)
        signals = tuple(RiskSignal.from_window(window) for window in selected)
        forecasts = tuple(self._forecast(signal) for signal in signals if signal.confidence >= 0.35)
        return ProactiveRiskResult(selected, signals, forecasts)

    def _forecast(self, signal: RiskSignal) -> RiskForecast:
        route = _route(signal)
        return RiskForecast(
            forecast_id=f"forecast-{signal.window.id}",
            signal=signal,
            route=route,
            eta_minutes=signal.eta_minutes,
            confidence=signal.confidence,
            impact=_impact(signal),
            prevention_plan=self.planner.plan(signal),
        )


def load_proactive_fixtures(path: str | Path) -> list[TrendWindow]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, Sequence) or isinstance(data, (str, bytes, bytearray)):
        raise ValueError("proactive fixtures must be a list")
    return [TrendWindow.from_dict(item) for item in data if isinstance(item, Mapping)]


def render_proactive_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary", {}) if isinstance(payload.get("summary"), Mapping) else {}
    score = payload.get("score", {}) if isinstance(payload.get("score"), Mapping) else {}
    lines = [
        "# OpsCat Proactive Risk Sentinel",
        "",
        "Boundary: no-auth/local-mock by default; no default external model/API calls; no remediation execution; no production mutation; does not claim unattended production operation.",
        "",
        "## Summary",
        f"- Windows: {summary.get('window_count')}",
        f"- Signals: {summary.get('signal_count')}",
        f"- Forecasts: {summary.get('forecast_count')}",
        "",
        "## Score",
        f"- unsafe_auto_action_count: {score.get('unsafe_auto_action_count')}",
        f"- lead_time_minutes_min: {score.get('lead_time_minutes_min')}",
        f"- lead_time_minutes_median: {score.get('lead_time_minutes_median')}",
        "",
        "## Forecasts",
    ]
    forecasts = payload.get("forecasts", [])
    if isinstance(forecasts, Sequence) and not isinstance(forecasts, (str, bytes, bytearray)):
        for forecast in forecasts:
            if isinstance(forecast, Mapping):
                lines.append(
                    f"- `{forecast.get('forecast_id')}` service={forecast.get('service')} risk={forecast.get('risk_type')} "
                    f"route={forecast.get('route')} ETA={forecast.get('eta_minutes')} confidence={forecast.get('confidence')}"
                )
    lines.extend(["", "## Prevention", "- Auto actions are limited to read-only diagnostics, report generation, and notification drafts.", "- Production changes remain approval-required or blocked."])
    return "\n".join(lines) + "\n"


def write_proactive_outputs(payload: Mapping[str, Any], *, output_json: str | Path | None = None, output_md: str | Path | None = None) -> None:
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(render_proactive_markdown(payload), encoding="utf-8")


def _trend(window: TrendWindow, total_delta: float, current: float) -> str:
    if window.risk_type == "false_positive_transient" and window.values and current <= max(window.baseline * 1.5, window.baseline + 0.01):
        return "recovered"
    decreasing = window.risk_type in _DECREASING_RISKS and window.threshold < window.baseline
    near_threshold = current <= window.threshold if decreasing else current >= window.threshold * 0.8
    if near_threshold:
        return "saturation"
    if total_delta > 0:
        return "rising"
    return "flat"


def _confidence(window: TrendWindow, trend: str, baseline_ratio: float, threshold_distance: float, eta: int | None) -> float:
    if trend == "recovered":
        return 0.4
    evidence_factor = min(0.2, len(window.evidence) * 0.05)
    eta_factor = 0.2 if eta is not None and eta <= 60 else 0.1 if eta is not None else 0.0
    ratio_factor = min(0.25, baseline_ratio * 0.05)
    distance_factor = 0.2 if threshold_distance <= 0.35 else 0.1 if threshold_distance <= 0.7 else 0.0
    base = 0.25 if trend in {"rising", "saturation"} else 0.1
    return round(min(0.95, base + evidence_factor + eta_factor + ratio_factor + distance_factor), 3)


def _route(signal: RiskSignal) -> str:
    if signal.trend == "recovered" or signal.risk_type == "false_positive_transient":
        return "monitor"
    if any(_blocked_marker(action) for action in signal.window.blocked_actions):
        return "preventive_review" if signal.confidence >= 0.5 else "monitor"
    return "preventive_review"


def _impact(signal: RiskSignal) -> str:
    if signal.risk_type in {"connection_pool_saturation", "disk_full_eta", "queue_sla_breach", "error_budget_burn"}:
        return "high"
    if signal.risk_type in {"false_positive_transient", "observability_gap"}:
        return "medium"
    return "moderate"


def _capability_for(action: str) -> str:
    text = action.lower()
    if "scale" in text:
        return "scaling"
    if "rollback" in text:
        return "rollback"
    if "cleanup" in text or "log_level" in text:
        return "maintenance_change"
    if "traffic" in text or "route" in text:
        return "traffic_change"
    if "session" in text or "database" in text:
        return "database_change"
    if "shell" in text or "kubectl" in text:
        return "shell_or_kubernetes"
    return "config_change"


def _blocked_marker(action: str) -> bool:
    lowered = action.lower()
    return any(marker in lowered for marker in _BLOCK_MARKERS)


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _median(values: Sequence[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[len(ordered) // 2]
