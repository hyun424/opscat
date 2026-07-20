from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest

from app.services.p147_p152_contracts import stable_hash
from app.services.p176_campaign import generate_p176_campaign
from app.services.p176_live_runtime import (
    DeferredBillingProvider,
    HttpEvidenceProvider,
    HttpFaultHarness,
    HttpSafetyMonitor,
    NvidiaP176DiagnosisAgent,
    P176LiveRuntimeError,
    build_runtime_producer_from_environment,
)
from app.services.p176_runtime_bridge import EPISODE_EVIDENCE_SOURCE_CLASSES, EvidenceSnapshot
from lab.p176.live.fault_controller import FaultController, dispatch_http_request
from lab.p176.live.telemetry_collector import build_runtime_evidence_snapshot


class _Response:
    def __init__(self, status: int, payload: dict[str, Any]) -> None:
        self.status = status
        self._body = json.dumps(payload).encode()

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, limit: int) -> bytes:
        return self._body[:limit]


def _snapshot(
    source_class: str,
    *,
    degraded: bool = True,
    window_id: str | None = None,
    service_id: str | None = None,
    healthy_profile: str = "quiet",
) -> dict[str, Any]:
    summary = {
        "status": "degraded" if degraded else "healthy",
        "source_class": source_class,
        "affected_services": ["event-queue"] if degraded else [],
        "signal_codes": ["backlog", "queue"] if degraded else [],
        "active_signal_count": 1 if degraded else 0,
    }
    return {
        "schema_version": "p176.live_runtime_evidence_snapshot.v1",
        "source_class": source_class,
        "request_binding_hash": stable_hash(
            {
                "run_id": "p176-live-run-1",
                "source_class": source_class,
                "window_id": window_id,
                "service_id": service_id,
                "healthy_profile": healthy_profile,
            }
        ),
        "observed_at": "2026-07-20T00:00:00Z",
        "received_at": "2026-07-20T00:00:01Z",
        "freshness_bound_seconds": 60,
        "content_hash": stable_hash({"source": source_class, "summary": summary}),
        "redaction_receipt_hash": stable_hash({"redacted": True, "source": source_class}),
        "summary": summary,
    }


def test_http_evidence_provider_calls_only_frozen_observer_path_and_validates_snapshot() -> None:
    calls: list[tuple[str, str]] = []

    def opener(request: Any, *, timeout: float) -> _Response:
        calls.append((request.full_url, request.method))
        return _Response(200, _snapshot("logs"))

    provider = HttpEvidenceProvider(
        endpoint="http://127.0.0.1:42001",
        run_id="p176-live-run-1",
        opener=opener,
    )

    snapshot = provider.collect(ledger_name="agent_visible", source_class="logs")

    assert snapshot.summary["status"] == "degraded"
    assert snapshot.evaluator_context_hash is None
    assert calls == [
        ("http://127.0.0.1:42001/v1/evidence?source_class=logs&run_id=p176-live-run-1", "GET")
    ]

    evaluator = provider.collect(ledger_name="evaluator_only", source_class="logs")
    assert evaluator.evaluator_context_hash == stable_hash(
        {"run_id": "p176-live-run-1", "source_class": "logs", "content_hash": evaluator.content_hash}
    )


def test_http_evidence_provider_requests_benign_runtime_variance_without_label_leakage() -> None:
    calls: list[str] = []

    def opener(request: Any, *, timeout: float) -> _Response:
        calls.append(request.full_url)
        raw = _snapshot(
            "metrics",
            degraded=False,
            window_id="p176-window-002",
            service_id="checkout-api",
            healthy_profile="baseline_variance",
        )
        raw["summary"]["signal_codes"] = ["metrics_baseline_variance"]
        raw["summary"]["benign_variation_count"] = 1
        return _Response(200, raw)

    provider = HttpEvidenceProvider(
        endpoint="http://127.0.0.1:42001",
        run_id="p176-live-run-1",
        opener=opener,
    )

    snapshot = provider.collect_healthy_window(
        ledger_name="agent_visible",
        source_class="metrics",
        window_id="p176-window-002",
        service_id="checkout-api",
        baseline_variance=True,
    )

    assert snapshot.summary["benign_variation_count"] == 1
    assert "noisy" not in repr(snapshot.summary)
    assert "healthy_profile=baseline_variance" in calls[0]


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeCompletion:
    def __init__(self, content: str) -> None:
        self.choices = [type("Choice", (), {"message": _FakeMessage(content)})()]


class _FakeCompletions:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> _FakeCompletion:
        self.calls.append(kwargs)
        return _FakeCompletion(self.content)


class _FakeClient:
    def __init__(self, content: str) -> None:
        completions = _FakeCompletions(content)
        self.chat = type("Chat", (), {"completions": completions})()


class _TransientProviderError(RuntimeError):
    status_code = 503


class _SequencedCompletions:
    def __init__(self, outcomes: list[Exception | _FakeCompletion]) -> None:
        self.outcomes = outcomes
        self.calls = 0

    def create(self, **_kwargs: Any) -> _FakeCompletion:
        outcome = self.outcomes[self.calls]
        self.calls += 1
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _SequencedClient:
    def __init__(self, outcomes: list[Exception | _FakeCompletion]) -> None:
        self.completions = _SequencedCompletions(outcomes)
        self.chat = type("Chat", (), {"completions": self.completions})()


def test_nvidia_agent_is_advisory_json_only_and_rejects_unknown_labels_or_citations() -> None:
    campaign = generate_p176_campaign()
    family_id = campaign["fault_families"][0]["family_id"]
    service_id = campaign["topology"][0]["service_id"]
    evidence = {
        "logs": EvidenceSnapshot(
            observed_at="2026-07-20T00:00:00Z",
            received_at="2026-07-20T00:00:01Z",
            freshness_bound_seconds=60,
            content_hash=stable_hash("logs"),
            redaction_receipt_hash=stable_hash("redacted-logs"),
            summary={"status": "degraded", "signal_codes": ["5xx"]},
        )
    }
    valid = {
        "incident_detected": True,
        "diagnosed_family_id": family_id,
        "routed_service_id": service_id,
        "confidence": 0.91,
        "evidence_citations": [evidence["logs"].content_hash],
        "human_required": False,
    }
    client = _FakeClient(json.dumps(valid))
    agent = NvidiaP176DiagnosisAgent(
        api_key="test-key",
        allowed_family_ids=[item["family_id"] for item in campaign["fault_families"]],
        allowed_service_ids=[item["service_id"] for item in campaign["topology"]],
        client=client,
    )

    decision = agent.diagnose(evidence=evidence)

    assert decision.diagnosed_family_id == family_id
    call = client.chat.completions.calls[0]
    prompt = json.dumps(call["messages"], sort_keys=True)
    assert "episode_id" not in prompt
    assert "evaluator_truth" not in prompt
    assert "fault_verb" not in prompt
    assert call["stream"] is False

    for field, value, error in (
        ("diagnosed_family_id", "unknown-family", "diagnosed_family_id_invalid"),
        ("routed_service_id", "unknown-service", "routed_service_id_invalid"),
        ("evidence_citations", [stable_hash("unknown")], "evidence_citation_unknown"),
    ):
        bad = dict(valid)
        bad[field] = value
        with pytest.raises(P176LiveRuntimeError, match=error):
            NvidiaP176DiagnosisAgent(
                api_key="test-key",
                allowed_family_ids=[family_id],
                allowed_service_ids=[service_id],
                client=_FakeClient(json.dumps(bad)),
            ).diagnose(evidence=evidence)


def test_nvidia_agent_retries_transient_capacity_errors_with_bounded_exponential_backoff() -> None:
    campaign = generate_p176_campaign()
    family_id = campaign["fault_families"][0]["family_id"]
    service_id = campaign["topology"][0]["service_id"]
    evidence = {
        "logs": EvidenceSnapshot(
            observed_at="2026-07-20T00:00:00Z",
            received_at="2026-07-20T00:00:01Z",
            freshness_bound_seconds=60,
            content_hash=stable_hash("logs-retry"),
            redaction_receipt_hash=stable_hash("redacted-logs-retry"),
            summary={"status": "degraded", "signal_codes": ["5xx"]},
        )
    }
    valid = _FakeCompletion(
        json.dumps(
            {
                "incident_detected": True,
                "diagnosed_family_id": family_id,
                "routed_service_id": service_id,
                "confidence": 0.8,
                "evidence_citations": [evidence["logs"].content_hash],
                "human_required": False,
            }
        )
    )
    client = _SequencedClient([_TransientProviderError(), _TransientProviderError(), valid])
    delays: list[float] = []
    agent = NvidiaP176DiagnosisAgent(
        api_key="test-key",
        allowed_family_ids=[family_id],
        allowed_service_ids=[service_id],
        client=client,
        sleeper=delays.append,
        jitter=lambda: 0.5,
    )

    decision = agent.diagnose(evidence=evidence)

    assert decision.diagnosed_family_id == family_id
    assert client.completions.calls == 3
    assert delays == [2.0, 4.0]


def test_nvidia_agent_fails_closed_after_bounded_transient_retries() -> None:
    campaign = generate_p176_campaign()
    family_id = campaign["fault_families"][0]["family_id"]
    service_id = campaign["topology"][0]["service_id"]
    evidence = {
        "logs": EvidenceSnapshot(
            observed_at="2026-07-20T00:00:00Z",
            received_at="2026-07-20T00:00:01Z",
            freshness_bound_seconds=60,
            content_hash=stable_hash("logs-retry-exhausted"),
            redaction_receipt_hash=stable_hash("redacted-logs-retry-exhausted"),
            summary={"status": "degraded", "signal_codes": ["5xx"]},
        )
    }
    client = _SequencedClient([_TransientProviderError() for _ in range(6)])
    delays: list[float] = []
    agent = NvidiaP176DiagnosisAgent(
        api_key="test-key",
        allowed_family_ids=[family_id],
        allowed_service_ids=[service_id],
        client=client,
        sleeper=delays.append,
        jitter=lambda: 0.5,
    )

    with pytest.raises(P176LiveRuntimeError, match="nvidia_transient_retries_exhausted:503"):
        agent.diagnose(evidence=evidence)

    assert client.completions.calls == 6
    assert delays == [2.0, 4.0, 8.0, 16.0, 30.0]


@dataclass
class _EvidenceProvider:
    events: list[str]

    def collect(self, *, ledger_name: str, source_class: str) -> EvidenceSnapshot:
        self.events.append(f"evidence:{ledger_name}:{source_class}")
        raw = _snapshot(source_class)
        return EvidenceSnapshot(
            observed_at=raw["observed_at"],
            received_at=raw["received_at"],
            freshness_bound_seconds=raw["freshness_bound_seconds"],
            content_hash=raw["content_hash"],
            redaction_receipt_hash=raw["redaction_receipt_hash"],
            summary=raw["summary"],
            evaluator_context_hash=stable_hash("evaluator") if ledger_name == "evaluator_only" else None,
        )


class _DecisionAgent:
    def __init__(self, events: list[str], *, fail: bool = False) -> None:
        self.events = events
        self.fail = fail

    def diagnose(self, *, evidence: dict[str, EvidenceSnapshot]) -> Any:
        self.events.append("diagnose")
        if self.fail:
            raise P176LiveRuntimeError("diagnosis_failed")
        first = next(iter(evidence.values()))
        return type(
            "Decision",
            (),
            {
                "incident_detected": True,
                "diagnosed_family_id": "p176-family-16-queue_backlog",
                "routed_service_id": "event-queue",
                "evidence_citations": (first.content_hash,),
                "human_required": False,
            },
        )()


class _Transport:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def get(self, path: str) -> dict[str, Any]:
        self.events.append(f"get:{path}")
        if path == "/v1/safety":
            return {"schema_version": "p176.live_runtime_safety.v1", "counters": {}}
        raise AssertionError(path)

    def post(self, path: str, payload: dict[str, Any], *, bearer_token: str) -> dict[str, Any]:
        assert bearer_token == "a" * 64
        if path.endswith("inject"):
            self.events.append("inject")
            return {
                "status": "fault_injected",
                "lease_id": payload["lease_id"],
                "run_id": payload["run_id"],
                "mutation_authority": "harness-only",
                "opscat_mutation_allowed": False,
                "deadman": {"receipt_id": "deadman-provider-receipt"},
                "residual_effect_count": 1,
                "receipt_hash": stable_hash("inject"),
            }
        self.events.append("cleanup")
        return {
            "status": "cleanup_completed",
            "lease_id": payload["lease_id"],
            "run_id": payload["run_id"],
            "mutation_authority": "harness-only",
            "opscat_mutation_allowed": False,
            "residual_effect_count": 0,
            "receipt_hash": stable_hash("cleanup"),
        }


def _episode() -> dict[str, Any]:
    return next(
        item
        for item in generate_p176_campaign()["episodes"]
        if item["family_id"] == "p176-family-16-queue_backlog" and item["service_id"] == "event-queue"
    )


def test_fault_harness_collects_while_fault_active_and_cleanup_dominates() -> None:
    events: list[str] = []
    harness = HttpFaultHarness(
        run_id="p176-live-run-1",
        capability_token="a" * 64,
        transport=_Transport(events),
        evidence_provider=_EvidenceProvider(events),
        diagnosis_agent=_DecisionAgent(events),
    )

    result = harness.execute_fault(
        episode=_episode(),
        fault_verb="inject_queue_backlog",
        harness_principal="p176-live-harness-fault@example.invalid",
    )

    assert events[0] == "inject"
    assert events[-1] == "cleanup"
    assert events.index("diagnose") < events.index("cleanup")
    assert result.residual_effect_count == 0
    assert result.recovery_observed is True
    assert set(result.agent_evidence) == set(EPISODE_EVIDENCE_SOURCE_CLASSES["cache_queue"])

    failing_events: list[str] = []
    failing = HttpFaultHarness(
        run_id="p176-live-run-1",
        capability_token="a" * 64,
        transport=_Transport(failing_events),
        evidence_provider=_EvidenceProvider(failing_events),
        diagnosis_agent=_DecisionAgent(failing_events, fail=True),
    )
    with pytest.raises(P176LiveRuntimeError, match="diagnosis_failed"):
        failing.execute_fault(
            episode=_episode(),
            fault_verb="inject_queue_backlog",
            harness_principal="p176-live-harness-fault@example.invalid",
        )
    assert failing_events[-1] == "cleanup"


def test_fault_harness_accepts_real_controller_receipts_and_real_symptom_projection() -> None:
    controller = FaultController()
    token = "a" * 64

    class ControllerTransport:
        def post(self, path: str, payload: dict[str, Any], *, bearer_token: str) -> dict[str, Any]:
            status, response = dispatch_http_request(
                method="POST",
                path=path,
                headers={"authorization": f"Bearer {bearer_token}", "content-type": "application/json"},
                body=json.dumps(payload).encode(),
                controller=controller,
                capability_token=token,
            )
            assert status in {200, 201}
            return response

    class ControllerEvidence:
        def collect(self, *, ledger_name: str, source_class: str) -> EvidenceSnapshot:
            raw = build_runtime_evidence_snapshot(
                source_class=source_class,
                run_id="p176-live-run-1",
                symptoms=controller.active_symptoms(),
                observed_at="2026-07-20T00:00:00Z",
                received_at="2026-07-20T00:00:01Z",
            )
            return EvidenceSnapshot(
                observed_at=raw["observed_at"],
                received_at=raw["received_at"],
                freshness_bound_seconds=raw["freshness_bound_seconds"],
                content_hash=raw["content_hash"],
                redaction_receipt_hash=raw["redaction_receipt_hash"],
                summary=raw["summary"],
                evaluator_context_hash=stable_hash("evaluator") if ledger_name == "evaluator_only" else None,
            )

    harness = HttpFaultHarness(
        run_id="p176-live-run-1",
        capability_token=token,
        transport=ControllerTransport(),
        evidence_provider=ControllerEvidence(),
        diagnosis_agent=_DecisionAgent([]),
    )

    result = harness.execute_fault(
        episode=_episode(),
        fault_verb="inject_queue_backlog",
        harness_principal="p176-live-harness-fault@example.invalid",
    )

    assert result.recovery_observed is True
    assert result.residual_effect_count == 0
    assert controller.active_symptoms()["active_fault_count"] == 0
    assert all(snapshot.summary["status"] == "degraded" for snapshot in result.agent_evidence.values())


def test_http_safety_monitor_requires_exact_zero_counter_contract() -> None:
    from app.services.p176_live_bridge import LIVE_SAFETY_COUNTER_KEYS

    counters = {key: 0 for key in LIVE_SAFETY_COUNTER_KEYS}

    class Transport:
        def get(self, path: str) -> dict[str, Any]:
            assert path == "/v1/safety"
            return {"schema_version": "p176.live_runtime_safety.v1", "counters": counters}

    assert HttpSafetyMonitor(transport=Transport()).live_safety() == counters

    bad = dict(counters)
    bad.pop(next(iter(bad)))

    class BadTransport:
        def get(self, path: str) -> dict[str, Any]:
            return {"schema_version": "p176.live_runtime_safety.v1", "counters": bad}

    with pytest.raises(P176LiveRuntimeError, match="safety_counter_keyset_invalid"):
        HttpSafetyMonitor(transport=BadTransport()).live_safety()


def test_runtime_factory_is_explicit_nvidia_and_defers_post_run_evidence(
    tmp_path: Any,
    monkeypatch: Any,
) -> None:
    run_dir = tmp_path / "p176-live-run-1"
    run_dir.mkdir()
    for name in (
        "reviewed-p176-live-apply.plan",
        "reviewed-p176-live-destroy.plan",
        "reviewed-p176-cost-cutoff-apply.plan",
        "reviewed-p176-cost-cutoff-destroy.plan",
    ):
        (run_dir / name).write_bytes(name.encode())
    monkeypatch.setenv("P176_RUNTIME_PHASE", "collect")
    monkeypatch.setenv("P176_LLM_PROVIDER", "nvidia")
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
    monkeypatch.setenv("EXPECTED_PROJECT_ID", "opscat-p176-live-test01")
    monkeypatch.setenv("P176_RUNTIME_RUN_ID", "p176-live-run-1")
    monkeypatch.setenv("P176_FAULT_CAPABILITY_TOKEN", "a" * 64)
    monkeypatch.setenv("P176_BILLING_ACCOUNT_ID", "ABCDEF-123456-789ABC")
    monkeypatch.setenv(
        "P176_BUDGET_RESOURCE_NAME",
        "billingAccounts/ABCDEF-123456-789ABC/budgets/p176-live-run-1",
    )

    producer = build_runtime_producer_from_environment(
        run_dir=run_dir,
        target_endpoint="http://127.0.0.1:42001",
        observer_endpoint="http://127.0.0.1:42002",
    )

    assert producer.config.run_id == "p176-live-run-1"
    assert isinstance(producer.billing_provider, DeferredBillingProvider)
    assert producer.config.reviewed_apply_plan_hash.startswith("sha256:")
    with pytest.raises(P176LiveRuntimeError, match="billing_snapshot_unavailable_during_collection"):
        producer.billing_provider.latest_billing()

    monkeypatch.setenv("P176_LLM_PROVIDER", "mock")
    with pytest.raises(P176LiveRuntimeError, match="P176_LLM_PROVIDER_must_be_nvidia"):
        build_runtime_producer_from_environment(
            run_dir=run_dir,
            target_endpoint="http://127.0.0.1:42001",
            observer_endpoint="http://127.0.0.1:42002",
        )


def test_runtime_factory_finalize_requires_regular_snapshot_files(tmp_path: Any, monkeypatch: Any) -> None:
    run_dir = tmp_path / "p176-live-run-1"
    run_dir.mkdir()
    for name in (
        "reviewed-p176-live-apply.plan",
        "reviewed-p176-live-destroy.plan",
        "reviewed-p176-cost-cutoff-apply.plan",
        "reviewed-p176-cost-cutoff-destroy.plan",
    ):
        (run_dir / name).write_bytes(name.encode())
    for name, value in {
        "P176_RUNTIME_PHASE": "finalize",
        "P176_LLM_PROVIDER": "nvidia",
        "EXPECTED_PROJECT_ID": "opscat-p176-live-test01",
        "P176_RUNTIME_RUN_ID": "p176-live-run-1",
        "P176_BILLING_ACCOUNT_ID": "ABCDEF-123456-789ABC",
        "P176_BUDGET_RESOURCE_NAME": "billingAccounts/ABCDEF-123456-789ABC/budgets/p176-live-run-1",
        "P176_BILLING_SNAPSHOT_PATH": str(tmp_path / "missing-billing.json"),
        "P176_TEARDOWN_SNAPSHOT_PATH": str(tmp_path / "missing-teardown.json"),
    }.items():
        monkeypatch.setenv(name, value)

    with pytest.raises(P176LiveRuntimeError, match="billing_snapshot_file_invalid"):
        build_runtime_producer_from_environment(
            run_dir=run_dir,
            target_endpoint="http://127.0.0.1:42001",
            observer_endpoint="http://127.0.0.1:42002",
        )
