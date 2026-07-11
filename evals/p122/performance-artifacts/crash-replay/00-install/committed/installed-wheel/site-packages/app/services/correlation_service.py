"""Deterministic incident correlation for provider-shaped OpsCat signals."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models import Evidence, Incident
from app.schemas.incidents import MockAlertRequest
from app.services.incident_service import alert_fingerprint, create_mock_incident
from app.services.redaction import redact_text, redact_value


@dataclass(frozen=True)
class CorrelationSignal:
    provider: str
    idempotency_key: str
    tenant_id: str = "demo"
    workspace_id: str = "demo"
    service: str = "payment-api"
    environment: str = "staging"
    fingerprint: str = ""
    severity: str = "high"
    message: str = ""
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    deploy_marker: str | None = None
    provider_reference: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)

    @property
    def stable_fingerprint(self) -> str:
        return self.fingerprint or f"{self.provider}:{self.idempotency_key}"


@dataclass(frozen=True)
class RejectedNeighbor:
    signal_id: str
    reason: str


@dataclass(frozen=True)
class CorrelationResult:
    tenant_id: str
    workspace_id: str
    service: str
    environment: str
    fingerprint: str
    signal_count: int
    confidence: float
    evidence_reasons: tuple[str, ...]
    rejected_neighbors: tuple[RejectedNeighbor, ...] = ()


def correlate_signals(signals: Iterable[CorrelationSignal], *, window_minutes: int = 30) -> list[CorrelationResult]:
    """Group normalized signals by tenant/workspace/service/env/fingerprint/window.

    The implementation is intentionally deterministic: duplicate provider
    references collapse, cross-workspace/environment signals are rejected, and
    confidence is derived from unique-provider/reference evidence only.
    """

    ordered = sorted(signals, key=lambda item: (item.occurred_at, item.provider, item.idempotency_key))
    buckets: dict[tuple[str, str, str, str, str, int], list[CorrelationSignal]] = defaultdict(list)
    rejected: list[RejectedNeighbor] = []
    for signal in ordered:
        bucket_start = int(signal.occurred_at.timestamp()) // (window_minutes * 60)
        key = (signal.tenant_id, signal.workspace_id, signal.service, signal.environment, signal.stable_fingerprint, bucket_start)
        buckets[key].append(signal)

    results: list[CorrelationResult] = []
    all_signals = list(ordered)
    for (tenant_id, workspace_id, service, environment, fingerprint, _window), bucket in buckets.items():
        unique_refs = {item.provider_reference or item.idempotency_key for item in bucket}
        providers = {item.provider for item in bucket}
        reasons = [
            f"{len(unique_refs)} unique signal reference(s) share fingerprint {fingerprint}",
            f"providers={','.join(sorted(providers))}",
            f"scope={tenant_id}/{workspace_id} service={service} env={environment}",
        ]
        deploy_markers = {item.deploy_marker for item in bucket if item.deploy_marker}
        if deploy_markers:
            reasons.append("deploy_marker=" + ",".join(sorted(deploy_markers)))
        local_rejections: list[RejectedNeighbor] = []
        for candidate in all_signals:
            if candidate in bucket:
                continue
            if candidate.stable_fingerprint != fingerprint:
                continue
            if candidate.workspace_id != workspace_id or candidate.tenant_id != tenant_id:
                local_rejections.append(RejectedNeighbor(candidate.idempotency_key, "cross-workspace signals never merge"))
            elif candidate.environment != environment:
                local_rejections.append(RejectedNeighbor(candidate.idempotency_key, "cross-environment signals never merge"))
        confidence = min(0.99, 0.52 + 0.12 * len(unique_refs) + 0.08 * max(0, len(providers) - 1) + (0.08 if deploy_markers else 0.0))
        results.append(
            CorrelationResult(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                service=service,
                environment=environment,
                fingerprint=fingerprint,
                signal_count=len(unique_refs),
                confidence=round(confidence, 2),
                evidence_reasons=tuple(reasons),
                rejected_neighbors=tuple(local_rejections),
            )
        )
        rejected.extend(local_rejections)
    return results


def signal_from_mapping(payload: Mapping[str, Any], *, tenant_id: str = "demo", workspace_id: str = "demo") -> CorrelationSignal:
    occurred_raw = payload.get("occurred_at") or payload.get("timestamp")
    occurred_at = _parse_datetime(occurred_raw)
    provider = str(payload.get("provider") or payload.get("source") or "generic").strip().lower()
    idempotency_key = str(payload.get("idempotency_key") or payload.get("event_id") or payload.get("id") or "").strip()
    if not idempotency_key:
        idempotency_key = f"{provider}:{hash(str(sorted(payload.items())))}"
    return CorrelationSignal(
        provider=provider,
        idempotency_key=idempotency_key,
        tenant_id=str(payload.get("tenant_id") or tenant_id),
        workspace_id=str(payload.get("workspace_id") or workspace_id),
        service=str(payload.get("service") or "payment-api"),
        environment=str(payload.get("environment") or "staging"),
        fingerprint=str(payload.get("fingerprint") or payload.get("error_fingerprint") or ""),
        severity=str(payload.get("severity") or "high"),
        message=redact_text(str(payload.get("message") or payload.get("title") or "")),
        occurred_at=occurred_at,
        deploy_marker=str(payload.get("deploy_marker") or payload.get("release") or "") or None,
        provider_reference=str(payload.get("provider_reference") or payload.get("url") or "") or None,
        raw=payload,
    )


def create_correlated_incident(db: Session, signals: Iterable[CorrelationSignal]) -> Incident:
    results = correlate_signals(signals)
    if not results:
        raise ValueError("at least one signal is required")
    result = sorted(results, key=lambda item: item.confidence, reverse=True)[0]
    payload = MockAlertRequest(
        tenant_id=result.tenant_id,
        workspace_id=result.workspace_id,
        scenario="correlated_outage",
        service=result.service,
        environment=result.environment,
        severity="high",
        message=f"Correlated {result.signal_count} signal(s) for {result.service} in {result.environment}",
        fingerprint=result.fingerprint,
        idempotency_key=f"correlation:{result.fingerprint}",
    )
    incident = create_mock_incident(db, payload)
    incident.confidence = result.confidence
    incident.alert_fingerprint = alert_fingerprint(payload)
    metadata = {
        "confidence": result.confidence,
        "signal_count": result.signal_count,
        "reasons": list(result.evidence_reasons),
        "rejected_neighbors": [item.__dict__ for item in result.rejected_neighbors],
    }
    incident.evidence.append(
        Evidence(
            incident_id=incident.id,
            tenant_id=incident.tenant_id,
            workspace_id=incident.workspace_id,
            type="correlation",
            source="correlation_service",
            source_url=f"correlation://{result.fingerprint}",
            content=redact_text("; ".join(result.evidence_reasons)),
            evidence_metadata=redact_value(metadata),
        )
    )
    db.flush()
    return incident


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif value:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    else:
        parsed = datetime.now(UTC)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    now = datetime.now(UTC)
    if parsed > now + timedelta(days=365):
        return now
    return parsed
