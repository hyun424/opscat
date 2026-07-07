from __future__ import annotations

from datetime import UTC, datetime

from app.services.correlation_service import CorrelationSignal, correlate_signals


def test_provider_signals_for_same_outage_correlate_once_with_evidence() -> None:
    ts = datetime(2026, 7, 7, 1, 0, tzinfo=UTC)
    signals = [
        CorrelationSignal(
            provider="sentry",
            idempotency_key="s1",
            workspace_id="alpha",
            service="payment-api",
            environment="staging",
            fingerprint="pay-timeout",
            occurred_at=ts,
            deploy_marker="v1.42",
        ),
        CorrelationSignal(
            provider="datadog",
            idempotency_key="d1",
            workspace_id="alpha",
            service="payment-api",
            environment="staging",
            fingerprint="pay-timeout",
            occurred_at=ts,
            deploy_marker="v1.42",
        ),
        CorrelationSignal(provider="loki", idempotency_key="l1", workspace_id="alpha", service="payment-api", environment="staging", fingerprint="pay-timeout", occurred_at=ts),
    ]

    [result] = correlate_signals(signals)

    assert result.signal_count == 3
    assert result.confidence >= 0.8
    assert any("providers=datadog,loki,sentry" in reason for reason in result.evidence_reasons)
    assert result.rejected_neighbors == ()


def test_correlation_never_merges_cross_workspace_or_environment_neighbors() -> None:
    ts = datetime(2026, 7, 7, 1, 0, tzinfo=UTC)
    signals = [
        CorrelationSignal(provider="sentry", idempotency_key="alpha", workspace_id="alpha", environment="staging", fingerprint="same", occurred_at=ts),
        CorrelationSignal(provider="sentry", idempotency_key="beta", workspace_id="beta", environment="staging", fingerprint="same", occurred_at=ts),
        CorrelationSignal(provider="sentry", idempotency_key="prod", workspace_id="alpha", environment="production", fingerprint="same", occurred_at=ts),
    ]

    results = correlate_signals(signals)

    assert len(results) == 3
    alpha = next(result for result in results if result.workspace_id == "alpha" and result.environment == "staging")
    reasons = {item.reason for item in alpha.rejected_neighbors}
    assert "cross-workspace signals never merge" in reasons
    assert "cross-environment signals never merge" in reasons
