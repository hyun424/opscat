"""P33 live connector dry-run harness.

The harness validates live-connector-shaped manifests through local mock probes.
It never performs live API calls or production mutation during normal operation.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.redaction import redact_value

_BOUNDARY: dict[str, bool] = {
    "local_mock_only": True,
    "dry_run_only": True,
    "live_api_calls_enabled": False,
    "production_mutation_enabled": False,
    "remediation_execution_enabled": False,
    "unrestricted_shell_enabled": False,
    "default_external_model_calls": False,
    "unattended_production_operation_claimed": False,
}
_WRITE_SCOPE_MARKERS = ("write", "admin", "delete", "manage", "execute", "mutation")
_REMOTE_PREFIXES = ("http://", "https://", "s3://", "gs://", "az://", "ftp://")


@dataclass(frozen=True)
class MockTransportProbe:
    status: str
    latency_ms: int
    timeout_ms: int
    rate_limited: bool
    retry_after_ms: int

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> MockTransportProbe:
        return cls(
            status=str(data.get("status", "unknown")),
            latency_ms=int(data.get("latency_ms", 0) or 0),
            timeout_ms=int(data.get("timeout_ms", 1000) or 1000),
            rate_limited=bool(data.get("rate_limited", False)),
            retry_after_ms=int(data.get("retry_after_ms", 0) or 0),
        )

    @property
    def healthy(self) -> bool:
        return self.status == "healthy" and self.latency_ms <= self.timeout_ms and not self.rate_limited

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "latency_ms": self.latency_ms,
            "timeout_ms": self.timeout_ms,
            "rate_limited": self.rate_limited,
            "retry_after_ms": self.retry_after_ms,
            "healthy": self.healthy,
            "live_api_called": False,
        }


@dataclass(frozen=True)
class ConnectorDryRunManifest:
    id: str
    provider: str
    endpoint_ref: str
    credential_ref: str
    declared_scopes: tuple[str, ...]
    expected_fields: tuple[str, ...]
    observed_fields: tuple[str, ...]
    transport: MockTransportProbe

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ConnectorDryRunManifest:
        return cls(
            id=str(data.get("id", "connector-unknown")),
            provider=str(data.get("provider", "unknown")),
            endpoint_ref=str(data.get("endpoint_ref", "")),
            credential_ref=str(data.get("credential_ref", "")),
            declared_scopes=tuple(str(item) for item in _sequence(data.get("declared_scopes", ()))),
            expected_fields=tuple(str(item) for item in _sequence(data.get("expected_fields", ()))),
            observed_fields=tuple(str(item) for item in _sequence(data.get("observed_fields", ()))),
            transport=MockTransportProbe.from_dict(_mapping(data.get("mock_transport"))),
        )


@dataclass(frozen=True)
class ConnectorDryRunResult:
    manifest: ConnectorDryRunManifest
    status: str
    reasons: tuple[str, ...]
    missing_fields: tuple[str, ...]
    extra_fields: tuple[str, ...]
    permission_safe: bool

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "connector_id": self.manifest.id,
            "provider": self.manifest.provider,
            "endpoint_ref": self.manifest.endpoint_ref,
            "credential_ref": self.manifest.credential_ref,
            "declared_scopes": list(self.manifest.declared_scopes),
            "status": self.status,
            "reasons": list(self.reasons),
            "permission_safe": self.permission_safe,
            "schema": {
                "expected_fields": list(self.manifest.expected_fields),
                "observed_fields": list(self.manifest.observed_fields),
                "missing_fields": list(self.missing_fields),
                "extra_fields": list(self.extra_fields),
                "compatible": not self.missing_fields,
            },
            "transport": self.manifest.transport.to_dict(),
            "live_api_call_count": 0,
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


@dataclass(frozen=True)
class LiveConnectorDryRunReport:
    results: tuple[ConnectorDryRunResult, ...]

    def to_dict(self) -> dict[str, Any]:
        connector_count = len(self.results)
        ready = sum(1 for item in self.results if item.status == "ready")
        degraded = sum(1 for item in self.results if item.status == "degraded")
        blocked = sum(1 for item in self.results if item.status == "blocked")
        schema_drift = sum(1 for item in self.results if item.missing_fields or item.extra_fields)
        permission_safe = sum(1 for item in self.results if item.permission_safe)
        schema_compatible = sum(1 for item in self.results if not item.missing_fields)
        transport_healthy = sum(1 for item in self.results if item.manifest.transport.healthy)
        permission_rate = _ratio(permission_safe, connector_count)
        schema_rate = _ratio(schema_compatible, connector_count)
        transport_rate = _ratio(transport_healthy, connector_count)
        readiness_rate = _ratio(ready + degraded, connector_count)
        health_score = round((permission_rate + schema_rate + transport_rate + readiness_rate) / 4, 3)
        payload = {
            "summary": {
                "connector_count": connector_count,
                "ready_count": ready,
                "degraded_count": degraded,
                "blocked_count": blocked,
                "schema_drift_count": schema_drift,
                "passed": connector_count >= 3 and blocked >= 1 and health_score >= 0.75,
            },
            "score": {
                "connector_health_score": health_score,
                "permission_safety_rate": permission_rate,
                "schema_compatibility_rate": schema_rate,
                "transport_health_rate": transport_rate,
                "readiness_rate": readiness_rate,
                "live_api_call_count": 0,
            },
            "boundary": dict(_BOUNDARY),
            "operator_handoff": _operator_handoff(self.results),
            "connectors": [item.to_dict() for item in self.results],
        }
        redacted = redact_value(payload)
        return dict(redacted) if isinstance(redacted, Mapping) else payload


class LiveConnectorDryRunRunner:
    def run_path(self, path: str | Path) -> LiveConnectorDryRunReport:
        return self.run(load_connector_dry_run_manifests(path))

    def run(self, manifests: Sequence[ConnectorDryRunManifest]) -> LiveConnectorDryRunReport:
        return LiveConnectorDryRunReport(results=tuple(_evaluate_manifest(item) for item in manifests))


def load_connector_dry_run_manifests(path: str | Path) -> tuple[ConnectorDryRunManifest, ...]:
    local_path = _ensure_local_path(path)
    data = json.loads(local_path.read_text(encoding="utf-8"))
    raw = data.get("connectors", ()) if isinstance(data, Mapping) else data
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
        raise ValueError("connector dry-run manifest must contain connectors")
    return tuple(ConnectorDryRunManifest.from_dict(item) for item in raw if isinstance(item, Mapping))


def run_live_connector_dry_run_fixture(path: str | Path) -> LiveConnectorDryRunReport:
    return LiveConnectorDryRunRunner().run_path(path)


def render_live_connector_dry_run_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    score = _mapping(payload.get("score"))
    handoff = _mapping(payload.get("operator_handoff"))
    lines = [
        "# OpsCat Live Connector Dry-run Report",
        "",
        "Boundary: live-connector-shaped dry-run only; no live API calls; no production mutation; no remediation execution; does not claim unattended production operation.",
        "",
        "## Summary",
        f"- Connectors: {summary.get('connector_count')}",
        f"- Ready connectors: {summary.get('ready_count')}",
        f"- Degraded connectors: {summary.get('degraded_count')}",
        f"- Blocked connectors: {summary.get('blocked_count')}",
        f"- Schema drift: {summary.get('schema_drift_count')}",
        "",
        "## Score",
        f"- connector_health_score: {score.get('connector_health_score')}",
        f"- permission_safety_rate: {score.get('permission_safety_rate')}",
        f"- schema_compatibility_rate: {score.get('schema_compatibility_rate')}",
        f"- live_api_call_count: {score.get('live_api_call_count')}",
        "",
        "## Operator handoff",
        f"- Ready connectors: {', '.join(str(item) for item in _sequence(handoff.get('ready_connectors', ())))}",
        f"- Blocked connectors: {', '.join(str(item) for item in _sequence(handoff.get('blocked_connectors', ())))}",
        f"- Next step: {handoff.get('next_step')}",
        "",
        "## Connectors",
    ]
    connectors = payload.get("connectors", [])
    if isinstance(connectors, Sequence) and not isinstance(connectors, (str, bytes, bytearray)):
        for item in connectors:
            if isinstance(item, Mapping):
                reasons = ",".join(str(reason) for reason in _sequence(item.get("reasons", ())))
                lines.append(
                    f"- `{item.get('connector_id')}` provider={item.get('provider')} "
                    f"status={item.get('status')} reasons={reasons}"
                )
    return "\n".join(lines) + "\n"


def write_live_connector_dry_run_outputs(payload: Mapping[str, Any], *, output_json: str | Path | None = None, output_md: str | Path | None = None) -> None:
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(output_md).write_text(render_live_connector_dry_run_markdown(payload), encoding="utf-8")


def _evaluate_manifest(manifest: ConnectorDryRunManifest) -> ConnectorDryRunResult:
    permission_safe = not any(_is_write_scope(scope) for scope in manifest.declared_scopes)
    missing = tuple(field for field in manifest.expected_fields if field not in manifest.observed_fields)
    extra = tuple(field for field in manifest.observed_fields if field not in manifest.expected_fields)
    reasons: list[str] = []
    if not permission_safe:
        reasons.append("write_or_admin_scope")
    if missing or extra:
        reasons.append("schema_drift")
    if not manifest.transport.healthy:
        reasons.append("mock_transport_unhealthy")
    if not permission_safe:
        status = "blocked"
    elif missing or extra or not manifest.transport.healthy:
        status = "degraded"
    else:
        status = "ready"
        reasons.append("dry_run_ready")
    return ConnectorDryRunResult(
        manifest=manifest,
        status=status,
        reasons=tuple(reasons),
        missing_fields=missing,
        extra_fields=extra,
        permission_safe=permission_safe,
    )


def _operator_handoff(results: Sequence[ConnectorDryRunResult]) -> dict[str, Any]:
    ready = [item.manifest.id for item in results if item.status == "ready"]
    degraded = [item.manifest.id for item in results if item.status == "degraded"]
    blocked = [item.manifest.id for item in results if item.status == "blocked"]
    return {
        "ready_connectors": ready,
        "degraded_connectors": degraded,
        "blocked_connectors": blocked,
        "next_step": "fix blocked permissions and schema drift before live read-only polling",
    }


def _is_write_scope(scope: str) -> bool:
    normalized = scope.lower().replace(":", "_").replace("-", "_")
    return any(marker in normalized for marker in _WRITE_SCOPE_MARKERS)


def _ensure_local_path(path: str | Path) -> Path:
    value = str(path)
    if value.lower().startswith(_REMOTE_PREFIXES):
        raise ValueError("remote connector manifests are not allowed for dry-run verification")
    local_path = Path(value)
    if not local_path.exists():
        raise FileNotFoundError(f"connector dry-run manifest does not exist: {local_path}")
    return local_path


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 3) if denominator else 0.0


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()
