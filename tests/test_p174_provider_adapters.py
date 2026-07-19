from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

import app.services.p174_gcp_provider_lab as provider_module
import scripts.run_p174_provider_lab as runner
from app.services.p110_evaluation import stable_hash
from app.services.p174_gcp_provider_lab import (
    ACTION_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION,
    FakeGcpProviderTransport,
    HttpP174ProviderTransport,
    P174ProviderLabError,
    ProviderActionRequest,
    ProviderLab,
    validate_manifest,
    validate_receipt_chain,
)

NOW = datetime(2026, 7, 17, 3, 0, 0, tzinfo=UTC)


def _manifest(**overrides: Any) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "organization_id": "000000000000",
        "billing_account_id": "000000-000000-000000",
        "project_id": "opscat-p174-lab-20260717",
        "target_id": "target-vm",
        "run_id": "run-174",
        "zone": "asia-northeast3-a",
        "allowed_actions": ["tune_pool", "restart_worker", "rollback_canary"],
        "allowed_targets": ["target-vm"],
        "forbidden_project_ids": ["forbidden-existing-project-b", "forbidden-existing-project-e"],
        "lease_ttl_seconds": 60,
        "deadman_seconds": 120,
        "kill_switch": False,
        "dry_run": False,
        "production_mutation_allowed": False,
        "user_staging_mutation_allowed": False,
        "service_account_keys_allowed": False,
        "live_apply_acknowledged": False,
    }
    manifest.update(overrides)
    return manifest


def _request(action: str = "tune_pool", *, request_id: str = "req-1", run_id: str = "run-174", target_id: str = "target-vm") -> ProviderActionRequest:
    return ProviderActionRequest(
        schema_version=ACTION_SCHEMA_VERSION,
        request_id=request_id,
        idempotency_key=request_id,
        project_id="opscat-p174-lab-20260717",
        target_id=target_id,
        run_id=run_id,
        action=action,
        parameters={"pool_size": 3} if action == "tune_pool" else {},
        evidence_hash="sha256:" + "a" * 64,
        policy_version="p174-policy-v1",
        created_at=NOW,
    )


def test_manifest_validation_rejects_open_authority_and_unsafe_values() -> None:
    assert validate_manifest(_manifest()).manifest_hash.startswith("sha256:")

    with pytest.raises(P174ProviderLabError, match="allowed_actions_not_exact"):
        validate_manifest(_manifest(allowed_actions=["tune_pool", "restart_worker", "rollback_canary", "gcloud"]))

    with pytest.raises(P174ProviderLabError, match="forbidden_project_selected"):
        validate_manifest(_manifest(project_id="forbidden-existing-project-b"))

    with pytest.raises(P174ProviderLabError, match="unsafe_manifest_value"):
        validate_manifest(_manifest(target_id="https://metadata.google.internal"))

    with pytest.raises(P174ProviderLabError, match="unsafe_manifest_value"):
        validate_manifest(_manifest(allowed_targets=["target-vm", "gcloud compute instances delete prod"]))


def test_read_and_action_receipts_are_append_only_hash_chained_and_bound() -> None:
    lab = ProviderLab(validate_manifest(_manifest()), transport=FakeGcpProviderTransport(), now=lambda: NOW)
    lab.acquire_lease("owner-1")

    read_receipt = lab.read_state("owner-1")
    action_receipt = lab.run_action("owner-1", _request())

    assert read_receipt["receipt_type"] == "read"
    assert action_receipt["receipt_type"] == "action"
    assert action_receipt["previous_receipt_hash"] == read_receipt["receipt_hash"]
    assert action_receipt["project_id"] == "opscat-p174-lab-20260717"
    assert action_receipt["target_id"] == "target-vm"
    assert action_receipt["run_id"] == "run-174"
    assert action_receipt["receipt_hash"] == stable_hash({key: value for key, value in action_receipt.items() if key != "receipt_hash"})

    exported = list(lab.receipts)
    exported[0]["project_id"] = "tampered"
    with pytest.raises(P174ProviderLabError, match="receipt_hash_invalid"):
        validate_receipt_chain(exported, manifest_hash=lab.manifest.manifest_hash)
    lab.validate_receipts()


def test_idempotency_replays_same_receipt_and_rejects_conflicts() -> None:
    lab = ProviderLab(validate_manifest(_manifest()), transport=FakeGcpProviderTransport(), now=lambda: NOW)
    lab.acquire_lease("owner-1")

    first = lab.run_action("owner-1", _request(request_id="req-idem"))
    second = lab.run_action("owner-1", _request(request_id="req-idem"))
    assert second == first
    assert len([receipt for receipt in lab.receipts if receipt["receipt_type"] == "action"]) == 1

    with pytest.raises(P174ProviderLabError, match="idempotency_conflict"):
        lab.run_action("owner-1", _request(action="restart_worker", request_id="req-idem"))


def test_exact_binding_lease_expiry_kill_switch_and_deadman_are_enforced() -> None:
    moving_now = {"value": NOW}
    lab = ProviderLab(validate_manifest(_manifest(lease_ttl_seconds=5, deadman_seconds=10)), transport=FakeGcpProviderTransport(), now=lambda: moving_now["value"])
    lab.acquire_lease("owner-1")

    with pytest.raises(P174ProviderLabError, match="run_binding_mismatch"):
        lab.run_action("owner-1", _request(run_id="other-run"))

    with pytest.raises(P174ProviderLabError, match="target_not_allowed"):
        lab.run_action("owner-1", _request(target_id="other-target"))

    moving_now["value"] = NOW + timedelta(seconds=6)
    with pytest.raises(P174ProviderLabError, match="lease_expired"):
        lab.run_action("owner-1", _request(request_id="late"))

    lab = ProviderLab(validate_manifest(_manifest(kill_switch=True)), transport=FakeGcpProviderTransport(), now=lambda: NOW)
    lab.acquire_lease("owner-1")
    with pytest.raises(P174ProviderLabError, match="kill_switch_active"):
        lab.run_action("owner-1", _request())

    lab = ProviderLab(validate_manifest(_manifest(lease_ttl_seconds=20, deadman_seconds=10)), transport=FakeGcpProviderTransport(), now=lambda: NOW + timedelta(seconds=11))
    lab.acquire_lease("owner-1", at=NOW)
    with pytest.raises(P174ProviderLabError, match="deadman_expired"):
        lab.run_action("owner-1", _request(request_id="deadman"))


def test_state_machine_rolls_back_harmful_and_uncertain_post_checks() -> None:
    harmful_transport = FakeGcpProviderTransport(post_check_status="harmful")
    harmful = ProviderLab(
        validate_manifest(_manifest()),
        transport=harmful_transport,
        now=lambda: NOW,
    )
    harmful.acquire_lease("owner-1")
    harmful_receipt = harmful.run_action("owner-1", _request())
    assert harmful_receipt["state_sequence"] == ["dry_run", "preflight", "execute", "post_check", "rollback", "rollback_check"]
    assert harmful_receipt["status"] == "rolled_back"
    assert harmful_transport.action_log == ["preflight:tune_pool", "execute:tune_pool", "post_check:tune_pool", "rollback:tune_pool", "rollback_check:tune_pool"]

    uncertain = ProviderLab(
        validate_manifest(_manifest()),
        transport=FakeGcpProviderTransport(post_check_status="uncertain"),
        now=lambda: NOW,
    )
    uncertain.acquire_lease("owner-1")
    uncertain_receipt = uncertain.run_action("owner-1", _request(request_id="uncertain"))
    assert uncertain_receipt["status"] == "rolled_back"
    assert uncertain_receipt["rollback_reason"] == "uncertain_post_check"


def test_transport_failure_after_execute_is_durably_receipted_and_rolled_back() -> None:
    class FailingPostCheck(FakeGcpProviderTransport):
        def post_check(self, request: ProviderActionRequest) -> Any:
            self.action_log.append(f"post_check:{request.action}")
            raise TimeoutError("lost response")

    transport = FailingPostCheck()
    lab = ProviderLab(validate_manifest(_manifest()), transport=transport, now=lambda: NOW)
    lab.acquire_lease("owner-1")

    receipt = lab.run_action("owner-1", _request(request_id="post-check-failure"))

    assert receipt["status"] == "rolled_back"
    assert receipt["state_sequence"] == ["dry_run", "preflight", "execute", "post_check_failed", "rollback", "rollback_check"]
    assert receipt["failure_reason"] == "post_check:TimeoutError"
    lab.validate_receipts()


def test_rollback_failure_after_execute_is_durably_receipted() -> None:
    class FailingPostCheckAndRollback(FakeGcpProviderTransport):
        def post_check(self, request: ProviderActionRequest) -> Any:
            raise TimeoutError("lost response")

        def rollback(self, request: ProviderActionRequest) -> Any:
            raise OSError("rollback unavailable")

    lab = ProviderLab(validate_manifest(_manifest()), transport=FailingPostCheckAndRollback(), now=lambda: NOW)
    lab.acquire_lease("owner-1")

    receipt = lab.run_action("owner-1", _request(request_id="rollback-failure"))

    assert receipt["status"] == "rollback_failed"
    assert receipt["state_sequence"][-2:] == ["post_check_failed", "rollback_failed"]
    assert receipt["failure_reason"] == "post_check:TimeoutError;rollback:OSError"
    lab.validate_receipts()


def test_rollback_without_independent_closure_proof_is_failure() -> None:
    transport = FakeGcpProviderTransport(post_check_status="uncertain", rollback_check_status="uncertain")
    lab = ProviderLab(validate_manifest(_manifest()), transport=transport, now=lambda: NOW)
    lab.acquire_lease("owner-1")

    receipt = lab.run_action("owner-1", _request(request_id="rollback-not-closed"))

    assert receipt["status"] == "rollback_failed"
    assert receipt["state_sequence"][-2:] == ["rollback_check", "rollback_failed"]
    assert receipt["failure_reason"] == "rollback:closure_not_proven"


def test_dry_run_stops_before_execute_and_only_allows_three_actions() -> None:
    transport = FakeGcpProviderTransport()
    lab = ProviderLab(validate_manifest(_manifest(dry_run=True)), transport=transport, now=lambda: NOW)
    lab.acquire_lease("owner-1")

    receipt = lab.run_action("owner-1", _request())
    assert receipt["status"] == "dry_run_complete"
    assert receipt["state_sequence"] == ["dry_run", "preflight"]
    assert transport.action_log == ["preflight:tune_pool"]

    with pytest.raises(P174ProviderLabError, match="action_not_allowed"):
        lab.run_action("owner-1", _request(action="delete_project", request_id="bad-action"))


def test_blocked_preflight_receipt_preserves_bounded_root_cause() -> None:
    class FailingPreflightTransport(FakeGcpProviderTransport):
        def preflight(self, request: ProviderActionRequest) -> provider_module.TransportResult:
            raise P174ProviderLabError("runtime_run_binding_mismatch\nignored-line")

    lab = ProviderLab(validate_manifest(_manifest()), transport=FailingPreflightTransport(), now=lambda: NOW)
    lab.acquire_lease("owner-1")

    receipt = lab.run_action("owner-1", _request(request_id="preflight-detail"))

    assert receipt["status"] == "blocked"
    assert receipt["failure_reason"] == "preflight:P174ProviderLabError"
    assert receipt["failure_detail"] == "runtime_run_binding_mismatch ignored-line"


def test_outcome_scoring_is_independent_of_provider_claims() -> None:
    transport = FakeGcpProviderTransport(
        before_metrics={"error_rate": 0.10, "latency_ms": 200.0, "pool_size": 5.0, "service_up": 1.0},
        after_metrics={"error_rate": 0.05, "latency_ms": 180.0, "pool_size": 8.0, "service_up": 1.0},
        provider_claimed_success=False,
    )
    lab = ProviderLab(validate_manifest(_manifest()), transport=transport, now=lambda: NOW)
    lab.acquire_lease("owner-1")

    receipt = lab.run_action("owner-1", _request())
    assert receipt["status"] == "applied"
    assert receipt["outcome_score"]["score"] > 0
    assert receipt["outcome_score"]["provider_claimed_success"] is False
    assert receipt["outcome_score"]["scored_from_provider_claim"] is False


def test_noop_post_check_is_uncertain_and_rolls_back() -> None:
    unchanged = {"error_rate": 0.1, "latency_ms": 200.0, "pool_size": 5.0, "queue_depth": 10.0, "service_up": 1.0}
    transport = FakeGcpProviderTransport(before_metrics=unchanged, after_metrics=unchanged)
    lab = ProviderLab(validate_manifest(_manifest()), transport=transport, now=lambda: NOW)
    lab.acquire_lease("owner-1")

    receipt = lab.run_action("owner-1", _request(request_id="noop"))

    assert receipt["status"] == "rolled_back"
    assert receipt["rollback_reason"] == "uncertain_post_check"


def test_runner_executes_fixture_without_network_or_real_mutation(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(runner._json_dumps(_manifest()), encoding="utf-8")

    rc = runner.main(["--manifest", str(manifest_path), "--owner-id", "owner-1", "--action", "restart_worker", "--request-id", "req-cli", "--now", "2026-07-17T03:00:00Z"])

    assert rc == 0
    output = runner._read_json_text(capsys.readouterr().out)
    assert output["status"] == "applied"
    assert output["transport"] == "fake-gcp-in-memory"
    assert output["receipt_hash"].startswith("sha256:")


def test_runner_dry_run_and_live_receipts_share_reviewed_manifest_chain(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    manifest_path = tmp_path / "manifest.json"
    receipt_log = tmp_path / "receipts.jsonl"
    manifest_path.write_text(runner._json_dumps(_manifest()), encoding="utf-8")

    common_args = [
        "--manifest",
        str(manifest_path),
        "--owner-id",
        "owner-1",
        "--action",
        "tune_pool",
        "--now",
        "2026-07-17T03:00:00Z",
        "--receipt-log",
        str(receipt_log),
    ]
    assert runner.main([*common_args, "--request-id", "req-dry", "--dry-run"]) == 0
    capsys.readouterr()
    assert runner.main([*common_args, "--request-id", "req-live"]) == 0
    capsys.readouterr()

    receipts = [runner._read_json_text(line) for line in receipt_log.read_text(encoding="utf-8").splitlines()]
    expected_manifest_hash = validate_manifest(_manifest()).manifest_hash
    assert [receipt["status"] for receipt in receipts] == ["dry_run_complete", "applied"]
    assert {receipt["manifest_hash"] for receipt in receipts} == {expected_manifest_hash}
    validate_receipt_chain(receipts, manifest_hash=expected_manifest_hash)


def test_runner_requires_verified_evidence_hash_before_http_transport(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(runner._json_dumps(_manifest()), encoding="utf-8")

    rc = runner.main(
        [
            "--manifest",
            str(manifest_path),
            "--owner-id",
            "owner-1",
            "--action",
            "tune_pool",
            "--request-id",
            "missing-evidence",
            "--transport",
            "http",
            "--dry-run",
        ]
    )

    assert rc == 1
    assert "verified_evidence_hash_required_for_live_transport" in capsys.readouterr().err


def test_runner_binds_live_lease_and_request_time_to_target_clock(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path = tmp_path / "manifest.json"
    receipt_log = tmp_path / "receipts.jsonl"
    manifest_path.write_text(runner._json_dumps(_manifest()), encoding="utf-8")
    target_now = NOW - timedelta(minutes=30)
    observed: dict[str, Any] = {}

    class TargetClockTransport(FakeGcpProviderTransport):
        def __init__(self, **_kwargs: Any) -> None:
            super().__init__()

        def read(self, manifest: Any) -> dict[str, Any]:
            return {"observed_at": target_now.isoformat().replace("+00:00", "Z")}

        def renew_lease(self, lease_expires_at: datetime) -> None:
            observed["lease_expires_at"] = lease_expires_at

        def preflight(self, request: ProviderActionRequest) -> Any:
            observed["created_at"] = request.created_at
            return super().preflight(request)

    monkeypatch.setattr(runner, "HttpP174ProviderTransport", TargetClockTransport)
    monkeypatch.setenv("P174_ACTION_CAPABILITY", "x" * 32)

    rc = runner.main(
        [
            "--manifest", str(manifest_path), "--owner-id", "owner-1", "--action", "tune_pool",
            "--request-id", "target-clock", "--transport", "http", "--action-endpoint", "http://127.0.0.1:8020",
            "--evidence-hash", "sha256:" + "a" * 64, "--receipt-log", str(receipt_log), "--allow-live-lab",
        ]
    )

    assert rc == 0, capsys.readouterr().err
    assert observed["created_at"] == target_now
    assert observed["lease_expires_at"] == target_now + timedelta(seconds=60)


def test_worker_pause_proof_fails_closed_without_target_observation_time() -> None:
    assert provider_module._worker_pause_released({"worker_paused_until": "2026-07-17T03:00:00Z"}) is False


def test_http_transport_uses_only_fixed_private_paths_and_real_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    responses: Iterator[dict[str, Any]] = iter(
        [
            {
                "project_id": "opscat-p174-lab-20260717",
                "target_id": "target-vm",
                "run_id": "run-174",
                "status": "healthy",
                "metrics": {"error_rate": 0.1, "latency_ms": 250.0, "service_up": 1.0, "pool_size": 5.0, "queue_depth": 20.0},
            },
            {
                "accepted": True,
                "project_id": "opscat-p174-lab-20260717",
                "target_id": "target-vm",
                "run_id": "run-174",
                "status": "applied",
                "metrics": {"error_rate": 0.05, "latency_ms": 200.0, "service_up": 1.0, "pool_size": 8.0, "queue_depth": 16.0},
            },
            {
                "project_id": "opscat-p174-lab-20260717",
                "target_id": "target-vm",
                "run_id": "run-174",
                "status": "healthy",
                "metrics": {"error_rate": 0.05, "latency_ms": 200.0, "service_up": 1.0, "pool_size": 8.0, "queue_depth": 16.0},
            },
        ]
    )
    requested_urls: list[str] = []

    class Response:
        status = 200

        def __init__(self, payload: dict[str, Any]) -> None:
            self.payload = payload

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, _limit: int) -> bytes:
            return runner._json_dumps(self.payload).encode("utf-8")

    def fake_urlopen(request: Any, timeout: float) -> Response:
        assert timeout == 1.0
        requested_urls.append(request.full_url)
        assert request.get_header("X-p174-capability") == "x" * 32
        response = Response(next(responses))
        response.status = 202 if request.get_method() == "POST" else 200
        return response

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    transport = HttpP174ProviderTransport(
        base_url="http://10.174.0.10:8020",
        capability="x" * 32,
        lease_expires_at=NOW + timedelta(seconds=60),
        timeout_seconds=1.0,
        post_check_delay_seconds=0,
        post_check_samples=1,
    )
    lab = ProviderLab(validate_manifest(_manifest()), transport=transport, now=lambda: NOW)
    lab.acquire_lease("owner-1")

    receipt = lab.run_action("owner-1", _request())

    assert receipt["status"] == "applied"
    assert receipt["outcome_score"]["outcome"] == "improved"
    assert requested_urls == [
        "http://10.174.0.10:8020/state",
        "http://10.174.0.10:8020/actions",
        "http://10.174.0.10:8020/state",
    ]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("service_up", True),
        ("queue_depth", "20"),
        ("latency_ms", float("nan")),
        ("error_rate", float("inf")),
        ("queue_depth", -1),
    ],
)
def test_http_transport_rejects_malformed_runtime_metrics(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
) -> None:
    metrics: dict[str, object] = {
        "error_rate": 0.1,
        "latency_ms": 250.0,
        "service_up": 1.0,
        "pool_size": 16,
        "queue_depth": 20,
    }
    metrics[field] = value
    payload = {
        "project_id": "opscat-p174-lab-20260717",
        "target_id": "target-vm",
        "run_id": "run-174",
        "status": "healthy",
        "state": {
            "project_id": "opscat-p174-lab-20260717",
            "target_id": "target-vm",
            "run_id": "run-174",
        },
        "metrics": metrics,
    }

    class Response:
        status = 200

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, _limit: int) -> bytes:
            return runner._json_dumps(payload).encode()

    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: Response())
    transport = HttpP174ProviderTransport(
        base_url="http://10.174.0.10:8020",
        capability="x" * 32,
        lease_expires_at=NOW + timedelta(seconds=60),
    )

    with pytest.raises(P174ProviderLabError, match="runtime_metrics_invalid"):
        transport.preflight(_request(action="restart_worker", request_id=f"bad-metric-{field}"))


def test_http_transport_applies_restart_worker_only_after_three_stable_recovery_samples(monkeypatch: pytest.MonkeyPatch) -> None:
    def state(
        metrics: dict[str, float | int],
        *,
        accepted: bool | None = None,
        generation: int = 8,
        worker_jobs_total: int = 101,
        paused_until: str = "2026-07-17T00:00:00Z",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "project_id": "opscat-p174-lab-20260717",
            "target_id": "target-vm",
            "run_id": "run-174",
            "status": "healthy",
            "observed_at": "2026-07-17T03:00:00Z",
            "state": {
                "project_id": "opscat-p174-lab-20260717",
                "target_id": "target-vm",
                "run_id": "run-174",
                "worker_restart_generation": generation,
                "worker_jobs_total": worker_jobs_total,
                "worker_paused_until": paused_until,
            },
            "metrics": metrics,
        }
        if accepted is not None:
            payload["accepted"] = accepted
        return payload

    responses: Iterator[dict[str, Any]] = iter(
        [
            state({"error_rate": 0.5, "latency_ms": 2000, "service_up": 1, "pool_size": 16, "queue_depth": 100}, generation=7, worker_jobs_total=100),
            state({"error_rate": 0.1, "latency_ms": 500, "service_up": 1, "pool_size": 16, "queue_depth": 60}, accepted=True, generation=8, worker_jobs_total=101),
            state({"error_rate": 0.1, "latency_ms": 500, "service_up": 1, "pool_size": 16, "queue_depth": 60}, worker_jobs_total=101),
            state({"error_rate": 0.1, "latency_ms": 450, "service_up": 1, "pool_size": 16, "queue_depth": 55}, worker_jobs_total=102),
            state({"error_rate": 0.1, "latency_ms": 400, "service_up": 1, "pool_size": 16, "queue_depth": 50}, worker_jobs_total=103),
        ]
    )
    requested_urls: list[str] = []

    class Response:
        status = 200

        def __init__(self, payload: dict[str, Any]) -> None:
            self.payload = payload

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, _limit: int) -> bytes:
            return runner._json_dumps(self.payload).encode()

    def fake_urlopen(request: Any, *_args: Any, **_kwargs: Any) -> Response:
        requested_urls.append(request.full_url)
        response = Response(next(responses))
        response.status = 202 if request.get_method() == "POST" else 200
        return response

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    transport = HttpP174ProviderTransport(
        base_url="http://10.174.0.10:8020",
        capability="x" * 32,
        lease_expires_at=NOW + timedelta(seconds=60),
        post_check_delay_seconds=0,
        post_check_samples=3,
    )
    lab = ProviderLab(validate_manifest(_manifest()), transport=transport, now=lambda: NOW)
    lab.acquire_lease("owner-1")

    receipt = lab.run_action("owner-1", _request(action="restart_worker", request_id="restart-live"))

    assert receipt["status"] == "applied"
    assert receipt["irreversible_action"] is True
    assert receipt["rollback_closure_claimed"] is False
    assert requested_urls == [
        "http://10.174.0.10:8020/state",
        "http://10.174.0.10:8020/actions",
        "http://10.174.0.10:8020/state",
        "http://10.174.0.10:8020/state",
        "http://10.174.0.10:8020/state",
    ]


def test_http_transport_restart_worker_accepts_bounded_queue_jitter_with_proven_worker_progress(monkeypatch: pytest.MonkeyPatch) -> None:
    def state(
        queue_depth: int,
        worker_jobs_total: int,
        *,
        accepted: bool | None = None,
        generation: int = 3,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "project_id": "opscat-p174-lab-20260717",
            "target_id": "target-vm",
            "run_id": "run-174",
            "status": "healthy",
            "observed_at": "2026-07-17T03:00:00Z",
            "state": {
                "project_id": "opscat-p174-lab-20260717",
                "target_id": "target-vm",
                "run_id": "run-174",
                "worker_restart_generation": generation,
                "worker_jobs_total": worker_jobs_total,
                "worker_paused_until": "2026-07-17T00:00:00Z",
            },
            "metrics": {
                "error_rate": 0.01,
                "latency_ms": 100,
                "service_up": 1,
                "pool_size": 16,
                "queue_depth": queue_depth,
            },
        }
        if accepted is not None:
            payload["accepted"] = accepted
        return payload

    responses: Iterator[dict[str, Any]] = iter(
        [
            {**state(24, 100, generation=2), "metrics": {"error_rate": 0.2, "latency_ms": 500, "service_up": 1, "pool_size": 16, "queue_depth": 24}},
            state(10, 101, accepted=True),
            state(2, 108),
            state(5, 112),
            state(3, 116),
        ]
    )

    class Response:
        status = 200

        def __init__(self, payload: dict[str, Any]) -> None:
            self.payload = payload

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, _limit: int) -> bytes:
            return runner._json_dumps(self.payload).encode()

    def fake_urlopen(request: Any, *_args: Any, **_kwargs: Any) -> Response:
        response = Response(next(responses))
        response.status = 202 if request.get_method() == "POST" else 200
        return response

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    transport = HttpP174ProviderTransport(
        base_url="http://10.174.0.10:8020",
        capability="x" * 32,
        lease_expires_at=NOW + timedelta(seconds=60),
        post_check_delay_seconds=0,
        post_check_samples=3,
    )
    lab = ProviderLab(validate_manifest(_manifest()), transport=transport, now=lambda: NOW)
    lab.acquire_lease("owner-1")

    receipt = lab.run_action("owner-1", _request(action="restart_worker", request_id="restart-jitter"))

    assert receipt["status"] == "applied"


def test_http_transport_restart_worker_uses_representative_metrics_instead_of_last_sample_jitter(monkeypatch: pytest.MonkeyPatch) -> None:
    def state(
        queue_depth: int,
        worker_jobs_total: int,
        *,
        accepted: bool | None = None,
        generation: int = 4,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "project_id": "opscat-p174-lab-20260717",
            "target_id": "target-vm",
            "run_id": "run-174",
            "status": "healthy",
            "observed_at": "2026-07-17T03:00:00Z",
            "state": {
                "project_id": "opscat-p174-lab-20260717",
                "target_id": "target-vm",
                "run_id": "run-174",
                "worker_restart_generation": generation,
                "worker_jobs_total": worker_jobs_total,
                "worker_paused_until": "2026-07-17T00:00:00Z",
            },
            "metrics": {
                "error_rate": max(0.0, (queue_depth - 32) / max(1, queue_depth)),
                "latency_ms": 25 + queue_depth * 1.25,
                "service_up": 1,
                "pool_size": 16,
                "queue_depth": queue_depth,
            },
        }
        if accepted is not None:
            payload["accepted"] = accepted
        return payload

    responses: Iterator[dict[str, Any]] = iter(
        [
            state(24, 100, generation=3),
            state(10, 101, accepted=True),
            state(2, 108),
            state(4, 112),
            state(28, 116),
        ]
    )

    class Response:
        status = 200

        def __init__(self, payload: dict[str, Any]) -> None:
            self.payload = payload

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, _limit: int) -> bytes:
            return runner._json_dumps(self.payload).encode()

    def fake_urlopen(request: Any, *_args: Any, **_kwargs: Any) -> Response:
        response = Response(next(responses))
        response.status = 202 if request.get_method() == "POST" else 200
        return response

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    transport = HttpP174ProviderTransport(
        base_url="http://10.174.0.10:8020",
        capability="x" * 32,
        lease_expires_at=NOW + timedelta(seconds=60),
        post_check_delay_seconds=0,
        post_check_samples=3,
    )
    lab = ProviderLab(validate_manifest(_manifest()), transport=transport, now=lambda: NOW)
    lab.acquire_lease("owner-1")

    receipt = lab.run_action("owner-1", _request(action="restart_worker", request_id="restart-final-jitter"))

    assert receipt["status"] == "applied"
    assert receipt["outcome_score"]["latency_ms_delta"] == 25.0


def test_http_transport_restart_worker_fails_closed_without_worker_progress(monkeypatch: pytest.MonkeyPatch) -> None:
    def state(queue_depth: int, *, accepted: bool | None = None, generation: int = 5) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "project_id": "opscat-p174-lab-20260717",
            "target_id": "target-vm",
            "run_id": "run-174",
            "status": "healthy",
            "observed_at": "2026-07-17T03:00:00Z",
            "state": {
                "project_id": "opscat-p174-lab-20260717",
                "target_id": "target-vm",
                "run_id": "run-174",
                "worker_restart_generation": generation,
                "worker_jobs_total": 100,
                "worker_paused_until": "2026-07-17T00:00:00Z",
            },
            "metrics": {"error_rate": 0.01, "latency_ms": 100, "service_up": 1, "pool_size": 16, "queue_depth": queue_depth},
        }
        if accepted is not None:
            payload["accepted"] = accepted
        return payload

    responses: Iterator[dict[str, Any]] = iter(
        [
            {**state(24, generation=4), "metrics": {"error_rate": 0.2, "latency_ms": 500, "service_up": 1, "pool_size": 16, "queue_depth": 24}},
            state(10, accepted=True),
            state(4),
            state(3),
            state(2),
        ]
    )

    class Response:
        status = 200

        def __init__(self, payload: dict[str, Any]) -> None:
            self.payload = payload

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, _limit: int) -> bytes:
            return runner._json_dumps(self.payload).encode()

    def fake_urlopen(request: Any, *_args: Any, **_kwargs: Any) -> Response:
        response = Response(next(responses))
        response.status = 202 if request.get_method() == "POST" else 200
        return response

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    transport = HttpP174ProviderTransport(
        base_url="http://10.174.0.10:8020",
        capability="x" * 32,
        lease_expires_at=NOW + timedelta(seconds=60),
        post_check_delay_seconds=0,
        post_check_samples=3,
    )
    lab = ProviderLab(validate_manifest(_manifest()), transport=transport, now=lambda: NOW)
    lab.acquire_lease("owner-1")

    receipt = lab.run_action("owner-1", _request(action="restart_worker", request_id="restart-no-progress"))

    assert receipt["status"] == "failed_closed"
    assert receipt["failure_reason"] == "uncertain_post_check:irreversible_action"


@pytest.mark.parametrize(
    ("before_generation", "post_generation"),
    [
        (None, None),
        ("old", "new"),
        (False, True),
        (3, None),
        (3, "new"),
        (3, True),
        (3, 5),
    ],
)
def test_restart_worker_completion_rejects_missing_malformed_or_nonsequential_generation(
    before_generation: object,
    post_generation: object,
) -> None:
    before = {"queue_depth": 24.0}
    samples = [
        {"queue_depth": 4.0, "pool_size": 16.0, "service_up": 1.0},
        {"queue_depth": 6.0, "pool_size": 16.0, "service_up": 1.0},
        {"queue_depth": 3.0, "pool_size": 16.0, "service_up": 1.0},
    ]
    before_state = {
        "worker_restart_generation": before_generation,
        "worker_jobs_total": 100,
    }
    states = [
        {
            "worker_restart_generation": post_generation,
            "worker_jobs_total": 101 + index,
            "worker_paused_until": "2026-07-17T00:00:00Z",
            "observed_at": "2026-07-17T03:00:00Z",
        }
        for index in range(3)
    ]

    assert provider_module._restart_worker_completion_proven(before, samples, before_state, states) is False


def test_restart_worker_completion_rejects_one_malformed_generation_sample() -> None:
    samples = [
        {"queue_depth": 4.0, "pool_size": 16.0, "service_up": 1.0},
        {"queue_depth": 6.0, "pool_size": 16.0, "service_up": 1.0},
        {"queue_depth": 3.0, "pool_size": 16.0, "service_up": 1.0},
    ]
    states = [
        {
            "worker_restart_generation": generation,
            "worker_jobs_total": 101 + index,
            "worker_paused_until": "2026-07-17T00:00:00Z",
            "observed_at": "2026-07-17T03:00:00Z",
        }
        for index, generation in enumerate((4, "4", 4))
    ]

    assert provider_module._restart_worker_completion_proven(
        {"queue_depth": 24.0},
        samples,
        {"worker_restart_generation": 3, "worker_jobs_total": 100},
        states,
    ) is False


def test_restart_worker_completion_requires_a_majority_of_recovered_queue_samples() -> None:
    samples = [
        {"queue_depth": 28.0, "pool_size": 16.0, "service_up": 1.0},
        {"queue_depth": 30.0, "pool_size": 16.0, "service_up": 1.0},
        {"queue_depth": 3.0, "pool_size": 16.0, "service_up": 1.0},
    ]
    states = [
        {
            "worker_restart_generation": 4,
            "worker_jobs_total": 101 + index,
            "worker_paused_until": "2026-07-17T00:00:00Z",
            "observed_at": "2026-07-17T03:00:00Z",
        }
        for index in range(3)
    ]

    assert provider_module._restart_worker_completion_proven(
        {"queue_depth": 24.0},
        samples,
        {"worker_restart_generation": 3, "worker_jobs_total": 100},
        states,
    ) is False


def test_http_transport_restart_worker_fails_closed_without_three_independent_samples(monkeypatch: pytest.MonkeyPatch) -> None:
    def state(metrics: dict[str, float | int], *, accepted: bool | None = None, generation: int = 9) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "project_id": "opscat-p174-lab-20260717",
            "target_id": "target-vm",
            "run_id": "run-174",
            "status": "healthy",
            "state": {
                "project_id": "opscat-p174-lab-20260717",
                "target_id": "target-vm",
                "run_id": "run-174",
                "worker_restart_generation": generation,
                "worker_paused_until": "2026-07-17T00:00:00Z",
            },
            "metrics": metrics,
        }
        if accepted is not None:
            payload["accepted"] = accepted
        return payload

    responses: Iterator[dict[str, Any]] = iter(
        [
            state({"error_rate": 0.5, "latency_ms": 2000, "service_up": 1, "pool_size": 16, "queue_depth": 100}, generation=8),
            state({"error_rate": 0.1, "latency_ms": 500, "service_up": 1, "pool_size": 16, "queue_depth": 60}, accepted=True),
            state({"error_rate": 0.1, "latency_ms": 500, "service_up": 1, "pool_size": 16, "queue_depth": 60}),
            state({"error_rate": 0.1, "latency_ms": 450, "service_up": 1, "pool_size": 16, "queue_depth": 55}),
        ]
    )
    requested_urls: list[str] = []

    class Response:
        status = 200

        def __init__(self, payload: dict[str, Any]) -> None:
            self.payload = payload

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, _limit: int) -> bytes:
            return runner._json_dumps(self.payload).encode()

    def fake_urlopen(request: Any, *_args: Any, **_kwargs: Any) -> Response:
        requested_urls.append(request.full_url)
        response = Response(next(responses))
        response.status = 202 if request.get_method() == "POST" else 200
        return response

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    transport = HttpP174ProviderTransport(
        base_url="http://10.174.0.10:8020",
        capability="x" * 32,
        lease_expires_at=NOW + timedelta(seconds=60),
        post_check_delay_seconds=0,
        post_check_samples=2,
    )
    lab = ProviderLab(validate_manifest(_manifest()), transport=transport, now=lambda: NOW)
    lab.acquire_lease("owner-1")

    receipt = lab.run_action("owner-1", _request(action="restart_worker", request_id="restart-fail-closed"))

    assert receipt["status"] == "failed_closed"
    assert receipt["state_sequence"] == ["dry_run", "preflight", "execute", "post_check"]
    assert receipt["failure_reason"] == "uncertain_post_check:irreversible_action"
    assert receipt["irreversible_action"] is True
    assert receipt["rollback_closure_claimed"] is False
    assert "http://10.174.0.10:8020/actions/rollback" not in requested_urls


def test_http_transport_rejects_transient_improvement_without_durable_queue_recovery(monkeypatch: pytest.MonkeyPatch) -> None:
    def state(metrics: dict[str, float | int], *, accepted: bool | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "project_id": "opscat-p174-lab-20260717",
            "target_id": "target-vm",
            "run_id": "run-174",
            "status": "healthy",
            "metrics": metrics,
        }
        if accepted is not None:
            payload["accepted"] = accepted
        return payload

    responses: Iterator[dict[str, Any]] = iter(
        [
            state({"error_rate": 0.5, "latency_ms": 2000, "service_up": 1, "pool_size": 5, "queue_depth": 100}),
            state({"error_rate": 0.1, "latency_ms": 500, "service_up": 1, "pool_size": 16, "queue_depth": 80}, accepted=True),
            state({"error_rate": 0.1, "latency_ms": 500, "service_up": 1, "pool_size": 16, "queue_depth": 80}),
            state({"error_rate": 0.2, "latency_ms": 800, "service_up": 1, "pool_size": 16, "queue_depth": 90}),
            state({"error_rate": 0.5, "latency_ms": 2000, "service_up": 1, "pool_size": 5, "queue_depth": 90}, accepted=True),
            state({"error_rate": 0.5, "latency_ms": 2000, "service_up": 1, "pool_size": 5, "queue_depth": 90}),
            state({"error_rate": 0.5, "latency_ms": 2000, "service_up": 1, "pool_size": 5, "queue_depth": 91}),
        ]
    )

    class Response:
        status = 200

        def __init__(self, payload: dict[str, Any]) -> None:
            self.payload = payload

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, _limit: int) -> bytes:
            return runner._json_dumps(self.payload).encode()

    def fake_urlopen(request: Any, *_args: Any, **_kwargs: Any) -> Response:
        response = Response(next(responses))
        response.status = 202 if request.get_method() == "POST" else 200
        return response

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    transport = HttpP174ProviderTransport(
        base_url="http://10.174.0.10:8020",
        capability="x" * 32,
        lease_expires_at=NOW + timedelta(seconds=60),
        post_check_delay_seconds=0,
        post_check_samples=2,
    )
    lab = ProviderLab(validate_manifest(_manifest()), transport=transport, now=lambda: NOW)
    lab.acquire_lease("owner-1")

    receipt = lab.run_action("owner-1", _request())

    assert receipt["status"] == "rolled_back"
    assert receipt["rollback_reason"] == "uncertain_post_check"


def test_http_transport_rollback_canary_requires_stable_canary_state_in_every_sample(monkeypatch: pytest.MonkeyPatch) -> None:
    def state(
        metrics: dict[str, float | int],
        *,
        canary_version: str,
        accepted: bool | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "project_id": "opscat-p174-lab-20260717",
            "target_id": "target-vm",
            "run_id": "run-174",
            "status": "healthy",
            "state": {
                "project_id": "opscat-p174-lab-20260717",
                "target_id": "target-vm",
                "run_id": "run-174",
                "canary_version": canary_version,
            },
            "metrics": metrics,
        }
        if accepted is not None:
            payload["accepted"] = accepted
        return payload

    responses: Iterator[dict[str, Any]] = iter(
        [
            state({"error_rate": 0.5, "latency_ms": 2000, "service_up": 1, "pool_size": 5, "queue_depth": 10}, canary_version="regressed"),
            state({"error_rate": 0.05, "latency_ms": 200, "service_up": 1, "pool_size": 5, "queue_depth": 10}, canary_version="stable", accepted=True),
            state({"error_rate": 0.05, "latency_ms": 200, "service_up": 1, "pool_size": 5, "queue_depth": 10}, canary_version="stable"),
            state({"error_rate": 0.05, "latency_ms": 200, "service_up": 1, "pool_size": 5, "queue_depth": 10}, canary_version="regressed"),
            state({"error_rate": 0.5, "latency_ms": 2000, "service_up": 1, "pool_size": 5, "queue_depth": 10}, canary_version="regressed", accepted=True),
            state({"error_rate": 0.5, "latency_ms": 2000, "service_up": 1, "pool_size": 5, "queue_depth": 10}, canary_version="regressed"),
            state({"error_rate": 0.5, "latency_ms": 2000, "service_up": 1, "pool_size": 5, "queue_depth": 10}, canary_version="regressed"),
        ]
    )
    requested_urls: list[str] = []

    class Response:
        status = 200

        def __init__(self, payload: dict[str, Any]) -> None:
            self.payload = payload

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, _limit: int) -> bytes:
            return runner._json_dumps(self.payload).encode()

    def fake_urlopen(request: Any, *_args: Any, **_kwargs: Any) -> Response:
        requested_urls.append(request.full_url)
        response = Response(next(responses))
        response.status = 202 if request.get_method() == "POST" else 200
        return response

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    transport = HttpP174ProviderTransport(
        base_url="http://10.174.0.10:8020",
        capability="x" * 32,
        lease_expires_at=NOW + timedelta(seconds=60),
        post_check_delay_seconds=0,
        post_check_samples=2,
    )
    lab = ProviderLab(validate_manifest(_manifest()), transport=transport, now=lambda: NOW)
    lab.acquire_lease("owner-1")

    receipt = lab.run_action("owner-1", _request(action="rollback_canary", request_id="rollback-canary-live"))

    assert receipt["status"] == "rolled_back"
    assert receipt["rollback_reason"] == "uncertain_post_check"
    assert requested_urls == [
        "http://10.174.0.10:8020/state",
        "http://10.174.0.10:8020/actions",
        "http://10.174.0.10:8020/state",
        "http://10.174.0.10:8020/state",
        "http://10.174.0.10:8020/actions/rollback",
        "http://10.174.0.10:8020/state",
        "http://10.174.0.10:8020/state",
    ]


def test_http_transport_rejects_200_for_mutation_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        status = 200

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, _limit: int) -> bytes:
            return b'{"accepted":true}'

    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: Response())
    transport = HttpP174ProviderTransport(
        base_url="http://10.174.0.10:8020",
        capability="x" * 32,
        lease_expires_at=NOW + timedelta(seconds=60),
    )

    with pytest.raises(P174ProviderLabError, match=r"runtime_http_status_mismatch:POST:200:expected:202"):
        transport._request("POST", "/actions", body={"schema_version": ACTION_SCHEMA_VERSION})


def test_http_transport_rejects_non_lab_hosts() -> None:
    with pytest.raises(P174ProviderLabError, match="action_endpoint_host_forbidden"):
        HttpP174ProviderTransport(
            base_url="http://metadata.google.internal",
            capability="x" * 32,
            lease_expires_at=NOW + timedelta(seconds=60),
        )
