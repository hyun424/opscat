from __future__ import annotations

import json
import time
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from lab.p176.live.fault_controller import (
    FaultController,
    FaultControllerError,
    dispatch_http_request,
    start_deadman_watchdog,
)
from lab.p176.live.telemetry_collector import (
    TelemetryCollectorError,
    build_runtime_evidence_snapshot,
    collect_normalized_evidence,
    dispatch_telemetry_request,
    verify_upstream_health,
)


def _lease(*, lease_id: str = "lease-1", run_id: str = "run-1", verb: str = "inject_queue_backlog") -> dict[str, object]:
    return {
        "lease_id": lease_id,
        "run_id": run_id,
        "verb": verb,
        "target_service_id": "event-queue",
        "issued_at": "2026-07-20T00:00:00Z",
        "expires_at": "2026-07-20T00:05:00Z",
        "deadman_expires_at": "2026-07-20T00:06:00Z",
        "parameters": {"depth": 25},
    }


def test_fault_controller_accepts_only_registered_harness_fault_verbs() -> None:
    controller = FaultController()

    accepted = controller.inject_fault(_lease())

    assert accepted["schema_version"] == "p176.live_fault_receipt.v1"
    assert accepted["status"] == "fault_injected"
    assert accepted["mutation_authority"] == "harness-only"
    assert accepted["opscat_mutation_allowed"] is False
    assert accepted["target"]["kind"] == "harness_service"
    assert accepted["target"]["service_id"] == "event-queue"
    assert accepted["verb"] == "inject_queue_backlog"
    assert accepted["receipt_hash"]

    with pytest.raises(FaultControllerError, match="unregistered_fault_verb"):
        controller.inject_fault(_lease(verb="inject_arbitrary_shell"))

    with pytest.raises(FaultControllerError, match="opscat_mutation_path_forbidden"):
        controller.inject_fault({**_lease(lease_id="lease-2"), "target": {"kind": "opscat_control_plane"}})


def test_fault_controller_rejects_lease_replay_and_payload_drift() -> None:
    controller = FaultController()
    first = controller.inject_fault(_lease())

    with pytest.raises(FaultControllerError, match="lease_replay_rejected"):
        controller.inject_fault(_lease())

    changed = _lease()
    changed["parameters"] = {"depth": 50}
    with pytest.raises(FaultControllerError, match="lease_payload_drift"):
        controller.inject_fault(changed)

    assert controller.receipts()[0] == first


def test_fault_cleanup_and_deadman_emit_residual_zero_receipts() -> None:
    controller = FaultController()
    fault = controller.inject_fault(_lease())

    cleanup = controller.cleanup_fault_lease(
        {
            "lease_id": fault["lease_id"],
            "run_id": fault["run_id"],
            "cleanup_verb": "cleanup_fault_lease",
            "requested_at": "2026-07-20T00:02:00Z",
        }
    )

    assert cleanup["schema_version"] == "p176.live_fault_cleanup_receipt.v1"
    assert cleanup["status"] == "cleanup_completed"
    assert cleanup["cleanup_verb"] == "cleanup_fault_lease"
    assert cleanup["residual_effect_count"] == 0
    assert cleanup["deadman"]["armed"] is False
    assert cleanup["deadman"]["receipt_id"] == fault["deadman"]["receipt_id"]
    assert cleanup["receipt_hash"]

    with pytest.raises(FaultControllerError, match="fault_already_cleaned"):
        controller.deadman_sweep(now="2026-07-20T00:07:00Z")

    active = controller.inject_fault(_lease(lease_id="lease-2", run_id="run-2"))
    deadman = controller.deadman_sweep(now="2026-07-20T00:07:00Z")

    assert deadman["schema_version"] == "p176.live_fault_deadman_receipt.v1"
    assert deadman["status"] == "deadman_cleanup_completed"
    assert deadman["lease_id"] == active["lease_id"]
    assert deadman["residual_effect_count"] == 0
    assert deadman["deadman"]["triggered"] is True


def test_independent_deadman_watchdog_cleans_fault_after_client_disappears() -> None:
    controller = FaultController()
    expired = (datetime.now(UTC) - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
    controller.inject_fault({**_lease(), "deadman_expires_at": expired})

    stop, thread = start_deadman_watchdog(controller, interval_seconds=0.01)
    try:
        deadline = time.monotonic() + 1.0
        while controller.active_symptoms()["active_fault_count"] and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        stop.set()
        thread.join(timeout=1.0)

    assert controller.active_symptoms()["active_fault_count"] == 0
    assert controller.live_safety()["residual_effect_count"] == 0
    assert controller.live_safety()["lease_expired_count"] == 1
    assert controller.receipts()[-1]["status"] == "deadman_cleanup_completed"


def test_fault_controller_http_contract_is_capability_authenticated_and_fail_closed() -> None:
    controller = FaultController()
    token = "a" * 64

    status, capabilities = dispatch_http_request(
        method="GET",
        path="/v1/capabilities",
        headers={},
        body=b"",
        controller=controller,
        capability_token=token,
    )
    assert status == 200
    assert capabilities["mutation_authority"] == "harness-only"
    assert len(capabilities["allowed_fault_verbs"]) == 30

    status, denied = dispatch_http_request(
        method="POST",
        path="/v1/faults/inject",
        headers={"authorization": "Bearer wrong"},
        body=json.dumps(_lease()).encode(),
        controller=controller,
        capability_token=token,
    )
    assert status == 401
    assert denied == {"error": "capability_token_invalid"}
    assert controller.receipts() == []

    status, injected = dispatch_http_request(
        method="POST",
        path="/v1/faults/inject",
        headers={"authorization": f"Bearer {token}", "content-type": "application/json"},
        body=json.dumps(_lease()).encode(),
        controller=controller,
        capability_token=token,
    )
    assert status == 201
    assert injected["status"] == "fault_injected"

    status, safety = dispatch_http_request(
        method="GET",
        path="/v1/safety",
        headers={},
        body=b"",
        controller=controller,
        capability_token=token,
    )
    assert status == 200
    assert safety["schema_version"] == "p176.live_runtime_safety.v1"
    assert safety["counters"]["residual_effect_count"] == 1

    status, symptoms = dispatch_http_request(
        method="GET",
        path="/v1/symptoms",
        headers={},
        body=b"",
        controller=controller,
        capability_token=token,
    )
    assert status == 200
    assert symptoms["active_fault_count"] == 1
    assert symptoms["signals"][0]["service_id"] == "event-queue"
    assert "inject_queue_backlog" not in repr(symptoms)

    status, cleaned = dispatch_http_request(
        method="POST",
        path="/v1/faults/cleanup",
        headers={"authorization": f"Bearer {token}", "content-type": "application/json"},
        body=json.dumps(
            {
                "lease_id": injected["lease_id"],
                "run_id": injected["run_id"],
                "cleanup_verb": "cleanup_fault_lease",
                "requested_at": "2026-07-20T00:02:00Z",
            }
        ).encode(),
        controller=controller,
        capability_token=token,
    )
    assert status == 200
    assert cleaned["residual_effect_count"] == 0

    status, safety = dispatch_http_request(
        method="GET",
        path="/v1/safety",
        headers={},
        body=b"",
        controller=controller,
        capability_token=token,
    )
    assert status == 200
    assert safety["counters"]["residual_effect_count"] == 0


def test_runtime_evidence_snapshot_projects_symptoms_without_exposing_fault_truth() -> None:
    symptoms = {
        "schema_version": "p176.live_fault_symptoms.v1",
        "active_fault_count": 1,
        "signals": [
            {
                "service_id": "event-queue",
                "status": "degraded",
                "signal_codes": ["queue", "backlog"],
            }
        ],
    }

    snapshot = build_runtime_evidence_snapshot(
        source_class="metrics",
        run_id="p176-live-run-1",
        symptoms=symptoms,
        observed_at="2026-07-20T00:00:00Z",
        received_at="2026-07-20T00:00:01Z",
    )

    assert snapshot["schema_version"] == "p176.live_runtime_evidence_snapshot.v1"
    assert snapshot["request_binding_hash"].startswith("sha256:")
    assert snapshot["source_class"] == "metrics"
    assert snapshot["summary"]["status"] == "degraded"
    assert snapshot["summary"]["signal_codes"] == ["backlog", "queue"]
    assert snapshot["summary"]["benign_variation_count"] == 0
    assert snapshot["content_hash"].startswith("sha256:")
    assert snapshot["redaction_receipt_hash"].startswith("sha256:")
    assert "inject_queue_backlog" not in repr(snapshot)


def test_telemetry_http_contract_allows_only_frozen_evidence_queries() -> None:
    symptoms = {
        "schema_version": "p176.live_fault_symptoms.v1",
        "active_fault_count": 0,
        "signals": [],
    }

    status, payload = dispatch_telemetry_request(
        path="/v1/evidence?source_class=logs&run_id=p176-live-run-1",
        symptom_loader=lambda: symptoms,
        observed_at="2026-07-20T00:00:00Z",
        received_at="2026-07-20T00:00:01Z",
    )
    assert status == 200
    assert payload["source_class"] == "logs"
    assert payload["summary"]["status"] == "healthy"

    status, noisy = dispatch_telemetry_request(
        path=(
            "/v1/evidence?source_class=metrics&run_id=p176-live-run-1"
            "&window_id=p176-window-002&service_id=checkout-api&healthy_profile=baseline_variance"
        ),
        symptom_loader=lambda: symptoms,
        observed_at="2026-07-20T00:00:00Z",
        received_at="2026-07-20T00:00:01Z",
    )
    assert status == 200
    assert noisy["summary"]["status"] == "healthy"
    assert noisy["summary"]["benign_variation_count"] == 1
    assert noisy["summary"]["affected_services"] == ["checkout-api"]
    assert noisy["summary"]["observed_services"] == ["checkout-api"]
    assert noisy["summary"]["signal_codes"] == ["metrics_baseline_variance"]

    status, next_window = dispatch_telemetry_request(
        path=(
            "/v1/evidence?source_class=metrics&run_id=p176-live-run-1"
            "&window_id=p176-window-004&service_id=checkout-api&healthy_profile=baseline_variance"
        ),
        symptom_loader=lambda: symptoms,
        observed_at="2026-07-20T00:00:00Z",
        received_at="2026-07-20T00:00:01Z",
    )
    assert status == 200
    assert next_window["content_hash"] != noisy["content_hash"]
    assert next_window["request_binding_hash"] != noisy["request_binding_hash"]

    for path in (
        "/v1/evidence?source_class=unknown&run_id=p176-live-run-1",
        "/v1/evidence?source_class=logs&run_id=x",
        "/v1/evidence?source_class=logs&run_id=p176-live-run-1&url=http://example.invalid",
        "/v1/other?source_class=logs&run_id=p176-live-run-1",
    ):
        status, payload = dispatch_telemetry_request(path=path, symptom_loader=lambda: symptoms)
        assert status in {400, 404}
        assert "error" in payload


def test_telemetry_collector_is_read_only_normalizes_sources_and_redacts_secrets() -> None:
    observed = {
        "metrics": [{"service_id": "checkout-api", "name": "latency_ms", "value": "42", "token": "sk_live_secret"}],
        "logs": [{"service_id": "checkout-api", "message": "password=hunter2 failed"}],
        "traces": [{"trace_id": "trace-1", "service_id": "checkout-api", "span": "POST /checkout"}],
        "deploy_history": [{"service_id": "checkout-api", "version": "2026.07.20", "authorization": "Bearer abc123"}],
        "host_state": [{"host_id": "host-a", "cpu_pct": 12}],
        "container_state": [{"container_id": "checkout-1", "service_id": "checkout-api", "status": "healthy"}],
        "topology": [{"service_id": "checkout-api", "depends_on": ["postgres-db", "redis-cache"]}],
        "dependency_health": [{"source": "checkout-api", "target": "postgres-db", "status": "healthy"}],
    }
    before = deepcopy(observed)

    evidence = collect_normalized_evidence(observed, run_id="run-1")

    assert observed == before
    assert evidence["schema_version"] == "p176.live_normalized_telemetry.v1"
    assert evidence["run_id"] == "run-1"
    assert evidence["read_only"] is True
    assert evidence["mutation_count"] == 0
    assert set(evidence["sources"]) == set(observed)
    assert all(source["records"] == 1 for source in evidence["sources"].values())
    assert "sk_live_secret" not in repr(evidence)
    assert "hunter2" not in repr(evidence)
    assert "Bearer abc123" not in repr(evidence)
    assert evidence["evidence_hash"]


def test_observer_telemetry_health_is_bound_to_the_single_private_target_endpoint() -> None:
    class Response:
        status = 200

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, _limit: int) -> bytes:
            return json.dumps({"status": "healthy", "component": "telemetry-collector"}).encode()

    calls: list[tuple[str, float]] = []

    def opener(url: str, *, timeout: float) -> Response:
        calls.append((url, timeout))
        return Response()

    result = verify_upstream_health("http://10.176.0.10:8000", opener=opener)

    assert result == {"status": "healthy", "component": "telemetry-collector"}
    assert calls == [("http://10.176.0.10:8000/health", 2.0)]

    with pytest.raises(TelemetryCollectorError, match="upstream_endpoint_not_allowed"):
        verify_upstream_health("http://127.0.0.1:8000", opener=opener)

    class UnhealthyResponse(Response):
        def read(self, _limit: int) -> bytes:
            return json.dumps({"status": "degraded", "component": "telemetry-collector"}).encode()

    with pytest.raises(TelemetryCollectorError, match="upstream_health_invalid"):
        verify_upstream_health(
            "http://10.176.0.10:8000",
            opener=lambda _url, timeout: UnhealthyResponse(),
        )
