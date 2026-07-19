from __future__ import annotations

import io
import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from urllib.parse import urlsplit
from urllib.request import Request

import pytest

import app.services.p174_live_harness as harness_module
import scripts.run_p174_live_harness as live_runner
from app.services.p174_gcp_provider_lab import HttpP174ProviderTransport, ProviderLab, validate_manifest
from app.services.p174_live_harness import (
    CAMPAIGN_DISTRIBUTION,
    HEALTHY_WINDOW_GATE,
    SCENARIO_CAMPAIGN_GATE,
    JsonlEvidenceRecorder,
    P174LiveHarnessError,
    ScenarioKind,
    ScenarioStep,
    ScheduleStep,
    build_seeded_campaign,
    parse_reviewed_manifest,
    run_qualification,
    stable_hash,
    verify_evidence_jsonl,
)
from lab.p174.workload.p174_workload import InMemoryCausalStore, RuntimeActionService, ServiceHandler
from scripts.run_p174_live_harness import _POLICY_VERSION, LoopbackObserverClient, ProviderLabActionClient
from scripts.run_p174_live_harness import main as cli_main


def _manifest(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": "p174.live_harness_manifest.v1",
        "manifest_id": "p174-reviewed-1",
        "reviewed": True,
        "reviewed_by": "security-reviewer",
        "reviewed_at": "2026-07-17T00:00:00Z",
        "lab_id": "lab-a",
        "seed": 174,
        "observer_contract_hash": "sha256:" + "1" * 64,
        "action_contract_hash": "sha256:" + "2" * 64,
        "allowed_targets": ["target_a", "target_b"],
        "allowed_actions": ["action_a", "action_b"],
    }
    value.update(overrides)
    return value


def _provider_manifest() -> dict[str, object]:
    return {
        "schema_version": "p174.live_session_manifest.v1",
        "organization_id": "000000000000",
        "billing_account_id": "000000-000000-000000",
        "project_id": "opscat-p174-lab",
        "target_id": "target_a",
        "run_id": "run-174",
        "zone": "asia-northeast3-a",
        "allowed_actions": ["tune_pool", "restart_worker", "rollback_canary"],
        "allowed_targets": ["target_a"],
        "forbidden_project_ids": ["forbidden-existing-project-b"],
        "lease_ttl_seconds": 60,
        "deadman_seconds": 120,
        "kill_switch": False,
        "dry_run": False,
        "production_mutation_allowed": False,
        "user_staging_mutation_allowed": False,
        "service_account_keys_allowed": False,
        "live_apply_acknowledged": False,
    }


def _write_authority_file(
    path: Path,
    *,
    action_capability: str = "a" * 32,
    fault_capability: str = "f" * 32,
    project_id: str = "opscat-p174-lab",
    target_id: str = "target_a",
    run_id: str = "run-174",
    policy_version: str = "p174-policy-v1",
) -> Path:
    path.write_text(
        "\n".join(
            (
                f"P174_ACTION_CAPABILITY={action_capability}",
                f"P174_FAULT_CAPABILITY={fault_capability}",
                f"P174_PROJECT_ID={project_id}",
                f"P174_TARGET_ID={target_id}",
                f"P174_RUN_ID={run_id}",
                f"P174_POLICY_VERSION={policy_version}",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


def _observer_payload(*, timestamp: float, sequence_tail: int, prefixed_hash: bool = True) -> dict[str, Any]:
    receipts = [
        {
            "source": source,
            "sequence": sequence_tail - 2 + offset,
            "receipt_hash": f"{'sha256:' if prefixed_hash else ''}{offset + 1:064x}",
        }
        for offset, source in enumerate(("prometheus", "loki", "api"))
    ]
    return {"receipts": receipts, "evaluation": {"healthy": True, "ts": timestamp}}


class HealthyObserver:
    def __init__(self, *, fail_window_at: int | None = None) -> None:
        self.fail_window_at = fail_window_at
        self.health_calls = 0
        self.scenario_calls = 0

    def observe_health_window(self, step: ScheduleStep) -> dict[str, object]:
        self.health_calls += 1
        healthy = self.fail_window_at != self.health_calls
        timestamp = datetime(2026, 7, 17, tzinfo=UTC) + timedelta(seconds=15 * (self.health_calls - 1))
        return {
            "healthy": healthy,
            "window_id": f"window-{self.health_calls}",
            "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
            "sequence": self.health_calls * 3,
        }

    def observe_scenario(self, step: ScenarioStep) -> dict[str, object]:
        self.scenario_calls += 1
        state = _baseline_state(self.scenario_calls)
        return {
            "ready": True,
            "stabilization_attempts": 1,
            "state": state,
            "state_hash": stable_hash(state),
            "episode": self.scenario_calls,
        }


class HealthyAction:
    def __init__(self, *, fail_scenario_at: int | None = None) -> None:
        self.fail_scenario_at = fail_scenario_at
        self.calls = 0
        self.fault_calls = 0
        self.cleanup_calls = 0

    def inject_fault(self, step: ScenarioStep, baseline: Mapping[str, Any]) -> dict[str, object]:
        self.fault_calls += 1
        scenario = step.scenario
        base_state = dict(baseline["state"])
        fault_state = dict(base_state)
        if scenario.fault == "queue_backlog":
            fault_state["queue_depth"] = int(fault_state["queue_depth"]) + 80
        elif scenario.fault == "canary_regression":
            fault_state["canary_version"] = "regressed"
            fault_state["error_rate"] = 0.12
            fault_state["latency_ms"] = 600
        elif scenario.fault == "worker_pause":
            fault_state["worker_paused"] = True
        return {
            "accepted": True,
            "fault": scenario.fault,
            "baseline_state": base_state,
            "baseline_state_hash": stable_hash(base_state),
            "state": fault_state,
            "state_hash": stable_hash(fault_state),
            "receipt_hash": stable_hash({"fault": scenario.fault, "index": step.index}),
        }

    def run_scenario(
        self,
        step: ScenarioStep,
        baseline: Mapping[str, Any],
        fault_result: Mapping[str, Any],
    ) -> dict[str, object]:
        self.calls += 1
        if self.fail_scenario_at == self.calls:
            return {"status": "applied", "accepted": True, "state": dict(fault_result["state"]), "state_hash": fault_result["state_hash"]}
        scenario = step.scenario
        fault_state = dict(fault_result["state"])
        post_state = dict(fault_state)
        if scenario.expected_outcome == "applied":
            status = "applied"
            if scenario.action == "restart_worker":
                post_state["queue_depth"] = max(0, int(post_state["queue_depth"]) - 60)
                post_state["worker_restart_generation"] = int(post_state["worker_restart_generation"]) + 1
            elif scenario.action == "rollback_canary":
                post_state["canary_version"] = "stable"
                post_state["error_rate"] = 0.02
                post_state["latency_ms"] = 200
        elif scenario.expected_outcome == "rolled_back":
            status = "rolled_back"
            post_state["pool_size"] = fault_state["pool_size"]
        elif scenario.expected_outcome == "failed_closed":
            status = "failed_closed"
            post_state["worker_restart_generation"] = int(post_state["worker_restart_generation"]) + 1
        else:
            status = "rejected" if scenario.expected_outcome == "rejected" else "blocked"
        return {
            "accepted": status in {"applied", "rolled_back"},
            "status": status,
            "state": post_state,
            "state_hash": stable_hash(post_state),
            "receipt_hash": stable_hash({"status": status, "index": step.index}),
            "irreversible_action": status == "failed_closed",
            "rollback_closure_claimed": status == "rolled_back",
        }

    def cleanup_scenario(
        self,
        step: ScenarioStep,
        baseline: Mapping[str, Any],
        post_result: Mapping[str, Any],
    ) -> dict[str, object]:
        self.cleanup_calls += 1
        restored = dict(baseline["state"])
        return {"status": "cleaned", "state": restored, "state_hash": stable_hash(restored)}


def _baseline_state(index: int) -> dict[str, Any]:
    return {
        "project_id": "opscat-p174-lab",
        "target_id": "target_a",
        "run_id": "run-174",
        "queue_depth": index,
        "pool_size": 5,
        "canary_version": "stable",
        "error_rate": 0.02,
        "latency_ms": 200,
        "worker_restart_generation": 0,
        "worker_paused": False,
        "worker_paused_until": "2026-07-17T00:00:00Z",
        "rollback_requests_total": 0,
    }


def test_qualification_requires_200_healthy_windows_and_exact_typed_100_scenario_campaign() -> None:
    manifest = parse_reviewed_manifest(_manifest())
    recorder = JsonlEvidenceRecorder()

    summary = run_qualification(manifest, HealthyObserver(), HealthyAction(), recorder=recorder)

    assert summary["qualified"] is True
    assert summary["fail_closed"] is False
    assert summary["gates"]["healthy_window"]["observed_consecutive"] == HEALTHY_WINDOW_GATE
    assert summary["gates"]["scenario_campaign"]["observed_successful"] == SCENARIO_CAMPAIGN_GATE
    assert summary["campaign"]["distribution"] == CAMPAIGN_DISTRIBUTION
    assert summary["coverage_counters"] == {
        "restart_recovery": 25,
        "canary_rollback": 25,
        "rejection": 20,
        "rollback_required": 20,
        "safety_boundary": 10,
        "fault:queue_backlog": 45,
        "fault:canary_regression": 35,
        "fault:worker_pause": 20,
        "action:restart_worker": 25,
        "action:rollback_canary": 25,
        "action:tune_pool": 30,
        "action:unsupported_action": 20,
        "expected:applied": 50,
        "expected:rejected": 20,
        "expected:rolled_back": 20,
        "expected:blocked_no_mutation": 10,
    }
    assert summary["evidence"]["event_count"] == 1 + HEALTHY_WINDOW_GATE + SCENARIO_CAMPAIGN_GATE
    first_window = recorder.events[1].payload
    assert first_window["window_id"] == "window-1"
    assert first_window["timestamp"] == "2026-07-17T00:00:00Z"
    assert first_window["sequence"] == 3
    verified = verify_evidence_jsonl(recorder.to_jsonl())
    assert verified["tail_hash"] == summary["evidence"]["tail_hash"]


def test_campaign_is_seeded_manifest_hash_bound_and_has_exact_distribution() -> None:
    first = parse_reviewed_manifest(_manifest(seed=9))
    second = parse_reviewed_manifest(_manifest(seed=9))
    different = parse_reviewed_manifest(_manifest(seed=10))

    first_campaign = [step.to_dict() for step in build_seeded_campaign(first)]
    assert first_campaign == [step.to_dict() for step in build_seeded_campaign(second)]
    assert first_campaign != [step.to_dict() for step in build_seeded_campaign(different)]
    counts: dict[str, int] = {}
    for row in first_campaign:
        counts[row["scenario"]] = counts.get(row["scenario"], 0) + 1
        assert set(row) == {"gate", "index", "target", "scenario", "fault", "action", "expected_outcome", "campaign_hash"}
    assert counts == CAMPAIGN_DISTRIBUTION
    by_name = {row["scenario"]: row for row in first_campaign}
    assert by_name["rollback_required"]["fault"] == "worker_pause"
    assert by_name["rollback_required"]["action"] == "tune_pool"
    assert by_name["rollback_required"]["expected_outcome"] == "rolled_back"
    assert by_name["rejection"]["action"] == "unsupported_action"
    assert by_name["safety_boundary"]["action"] == "tune_pool"


def test_diagnostic_scenario_limit_never_reduces_qualification_gate() -> None:
    manifest = parse_reviewed_manifest(_manifest())

    summary = run_qualification(manifest, HealthyObserver(), HealthyAction(), max_scenarios=1)

    assert summary["qualified"] is False
    assert summary["fail_closed"] is True
    assert summary["gates"]["scenario_campaign"] == {
        "required_exact": SCENARIO_CAMPAIGN_GATE,
        "observed_successful": 1,
        "passed": False,
    }
    assert summary["campaign"]["diagnostic_limit"] == 1


def test_diagnostic_campaign_only_runs_all_scenarios_without_claiming_qualification() -> None:
    manifest = parse_reviewed_manifest(_manifest())
    observer = HealthyObserver()
    action = HealthyAction()

    summary = run_qualification(manifest, observer, action, diagnostic_campaign_only=True)

    assert observer.health_calls == 0
    assert action.calls == 100
    assert summary["qualified"] is False
    assert summary["fail_closed"] is True
    assert summary["diagnostic_campaign_only"] is True
    assert summary["status"] == "diagnostic_complete"
    assert summary["gates"]["healthy_window"]["observed_consecutive"] == 0
    assert summary["gates"]["scenario_campaign"]["passed"] is True


def test_persistently_unready_baseline_records_evidence_without_any_mutation() -> None:
    class UnreadyObserver(HealthyObserver):
        def observe_scenario(self, step: ScenarioStep) -> dict[str, object]:
            self.scenario_calls += 1
            state = _baseline_state(self.scenario_calls)
            state["queue_depth"] = 80
            return {
                "ready": False,
                "stabilization_attempts": 20,
                "state": state,
                "state_hash": stable_hash(state),
            }

    manifest = parse_reviewed_manifest(_manifest())
    observer = UnreadyObserver()
    action = HealthyAction()
    recorder = JsonlEvidenceRecorder()

    summary = run_qualification(
        manifest,
        observer,
        action,
        recorder=recorder,
        max_scenarios=1,
        diagnostic_campaign_only=True,
    )

    assert summary["status"] == "blocked"
    assert summary["failures"][0]["reason"] == "scenario_baseline_not_ready"
    assert action.fault_calls == 0
    assert action.calls == 0
    assert action.cleanup_calls == 0
    event = recorder.events[-1]
    assert event.event_type == "scenario_campaign"
    assert event.payload["baseline_ready"] is False
    assert event.payload["stabilization_attempts"] == 20
    assert event.payload["baseline_observation_hash"] == stable_hash(
        {
            "ready": False,
            "stabilization_attempts": 20,
            "state": _baseline_state(1) | {"queue_depth": 80},
            "state_hash": stable_hash(_baseline_state(1) | {"queue_depth": 80}),
        }
    )
    assert event.payload["mutation_attempted"] is False
    assert event.payload["checks"] == {"baseline_ready": False}


@pytest.mark.parametrize("attempts", [None, 21])
def test_invalid_stabilization_provenance_fails_before_any_mutation(attempts: int | None) -> None:
    class InvalidProvenanceObserver(HealthyObserver):
        def observe_scenario(self, step: ScenarioStep) -> dict[str, object]:
            self.scenario_calls += 1
            state = _baseline_state(self.scenario_calls)
            result: dict[str, object] = {
                "ready": True,
                "state": state,
                "state_hash": stable_hash(state),
            }
            if attempts is not None:
                result["stabilization_attempts"] = attempts
            return result

    action = HealthyAction()
    recorder = JsonlEvidenceRecorder()

    summary = run_qualification(
        parse_reviewed_manifest(_manifest()),
        InvalidProvenanceObserver(),
        action,
        recorder=recorder,
        max_scenarios=1,
        diagnostic_campaign_only=True,
    )

    assert summary["status"] == "blocked"
    assert summary["failures"][0]["reason"] == "client_exception"
    assert action.fault_calls == 0
    assert action.calls == 0
    assert action.cleanup_calls == 0
    assert recorder.events[-1].event_type == "exception"


def test_fail_closed_when_healthy_window_gate_is_short() -> None:
    manifest = parse_reviewed_manifest(_manifest())
    observer = HealthyObserver(fail_window_at=200)
    action = HealthyAction()

    summary = run_qualification(manifest, observer, action)

    assert summary["qualified"] is False
    assert summary["fail_closed"] is True
    assert summary["status"] == "blocked"
    assert summary["gates"]["healthy_window"]["observed_consecutive"] == 199
    assert summary["gates"]["scenario_campaign"]["observed_successful"] == 0
    assert action.calls == 0


@pytest.mark.parametrize("invalid_field", ["window_id", "timestamp", "sequence"])
def test_fail_closed_on_duplicate_rapid_or_non_increasing_healthy_windows(invalid_field: str) -> None:
    class InvalidWindowObserver(HealthyObserver):
        def observe_health_window(self, step: ScheduleStep) -> dict[str, object]:
            observed = super().observe_health_window(step)
            if self.health_calls == 2:
                if invalid_field == "window_id":
                    observed["window_id"] = "window-1"
                elif invalid_field == "timestamp":
                    observed["timestamp"] = "2026-07-17T00:00:13Z"
                else:
                    observed["sequence"] = 3
            return observed

    summary = run_qualification(parse_reviewed_manifest(_manifest()), InvalidWindowObserver(), HealthyAction())

    assert summary["qualified"] is False
    assert summary["gates"]["healthy_window"]["observed_consecutive"] == 1
    assert summary["failures"][0]["reason"] == "client_exception"


def test_fail_closed_when_any_scenario_claim_lacks_concrete_state_delta() -> None:
    manifest = parse_reviewed_manifest(_manifest())
    action = HealthyAction(fail_scenario_at=1)

    summary = run_qualification(manifest, HealthyObserver(), action)

    assert summary["qualified"] is False
    assert summary["fail_closed"] is True
    assert summary["gates"]["healthy_window"]["observed_consecutive"] == 200
    assert summary["gates"]["scenario_campaign"]["observed_successful"] == 0
    assert summary["failures"][0]["reason"] == "scenario_claim_not_proven"


def test_fail_closed_when_client_omits_explicit_state_hash() -> None:
    class MissingHashAction(HealthyAction):
        def inject_fault(self, step: ScenarioStep, baseline: Mapping[str, Any]) -> dict[str, object]:
            result = super().inject_fault(step, baseline)
            result.pop("state_hash")
            return result

    summary = run_qualification(
        parse_reviewed_manifest(_manifest()),
        HealthyObserver(),
        MissingHashAction(),
        max_scenarios=1,
    )

    assert summary["qualified"] is False
    assert summary["failures"][0]["reason"] == "client_exception"
    assert summary["failures"][0]["details_hash"] == stable_hash({"error_type": "P174LiveHarnessError", "error": "state_hash_missing_or_invalid"})


def test_action_exception_after_fault_still_attempts_and_proves_cleanup() -> None:
    class RaisingAction(HealthyAction):
        def run_scenario(
            self,
            step: ScenarioStep,
            baseline: Mapping[str, Any],
            fault_result: Mapping[str, Any],
        ) -> dict[str, object]:
            self.calls += 1
            raise RuntimeError("action_transport_lost")

    action = RaisingAction()
    recorder = JsonlEvidenceRecorder()

    summary = run_qualification(
        parse_reviewed_manifest(_manifest()),
        HealthyObserver(),
        action,
        recorder=recorder,
        max_scenarios=1,
        diagnostic_campaign_only=True,
    )

    assert summary["status"] == "blocked"
    assert summary["failures"][0]["reason"] == "client_exception"
    assert action.fault_calls == 1
    assert action.calls == 1
    assert action.cleanup_calls == 1
    event = recorder.events[-1]
    assert event.event_type == "exception"
    assert event.payload["error_type"] == "RuntimeError"
    assert event.payload["error"] == "action_transport_lost"
    assert event.payload["cleanup_attempted"] is True
    assert event.payload["cleanup_proven"] is True


def test_action_exception_with_malformed_fault_evidence_still_attempts_cleanup() -> None:
    class MalformedFaultRaisingAction(HealthyAction):
        def inject_fault(self, step: ScenarioStep, baseline: Mapping[str, Any]) -> dict[str, object]:
            result = super().inject_fault(step, baseline)
            result.pop("state_hash")
            return result

        def run_scenario(
            self,
            step: ScenarioStep,
            baseline: Mapping[str, Any],
            fault_result: Mapping[str, Any],
        ) -> dict[str, object]:
            self.calls += 1
            raise RuntimeError("action_transport_lost")

    action = MalformedFaultRaisingAction()
    recorder = JsonlEvidenceRecorder()

    summary = run_qualification(
        parse_reviewed_manifest(_manifest()),
        HealthyObserver(),
        action,
        recorder=recorder,
        max_scenarios=1,
        diagnostic_campaign_only=True,
    )

    assert summary["status"] == "blocked"
    assert action.fault_calls == 1
    assert action.calls == 1
    assert action.cleanup_calls == 1
    event = recorder.events[-1]
    assert event.event_type == "exception"
    assert event.payload["cleanup_attempted"] is True
    assert event.payload["cleanup_proven"] is True
    assert event.payload["fault_hash_error_type"] == "P174LiveHarnessError"
    assert event.payload["fault_hash_error"] == "state_hash_missing_or_invalid"


def test_manifest_rejects_unreviewed_fields_urls_commands_and_unreviewed_input() -> None:
    for payload in (
        _manifest(reviewed=False),
        _manifest(callback_url="http://127.0.0.1:1"),
        _manifest(allowed_actions=["gcloud"]),
        _manifest(allowed_targets=["prod"]),
    ):
        try:
            parse_reviewed_manifest(payload)
        except P174LiveHarnessError:
            continue
        raise AssertionError(f"manifest unexpectedly accepted: {payload}")


def test_evidence_chain_detects_tampering() -> None:
    manifest = parse_reviewed_manifest(_manifest())
    recorder = JsonlEvidenceRecorder()
    run_qualification(manifest, HealthyObserver(), HealthyAction(), recorder=recorder)
    lines = recorder.to_jsonl().splitlines()
    first = json.loads(lines[1])
    first["payload"]["passed"] = False
    lines[1] = json.dumps(first, sort_keys=True, separators=(",", ":"))

    try:
        verify_evidence_jsonl("\n".join(lines) + "\n")
    except P174LiveHarnessError as exc:
        assert "evidence_hash_mismatch" in str(exc)
    else:
        raise AssertionError("tampered evidence was accepted")


def test_cli_requires_allow_live_lab_and_loopback_endpoint(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    provider_manifest_path = tmp_path / "provider-manifest.json"
    authority_path = _write_authority_file(tmp_path / "authority.env")
    manifest_path.write_text(json.dumps(_manifest(), sort_keys=True), encoding="utf-8")
    provider_manifest_path.write_text(json.dumps(_provider_manifest(), sort_keys=True), encoding="utf-8")

    base_args = [
        "--manifest",
        str(manifest_path),
        "--provider-manifest",
        str(provider_manifest_path),
        "--observer-endpoint",
        "http://127.0.0.1:17400",
        "--action-endpoint",
        "http://127.0.0.1:17401",
        "--output-summary",
        str(tmp_path / "summary.json"),
        "--output-jsonl",
        str(tmp_path / "evidence.jsonl"),
        "--authority-file",
        str(authority_path),
    ]

    assert cli_main(base_args) == 2
    assert cli_main([*base_args, "--allow-live-lab", "--observer-endpoint", "http://example.com:80"]) == 2
    assert cli_main([*base_args, "--allow-live-lab", "--action-capability", "a" * 32]) == 2
    assert cli_main([*base_args, "--allow-live-lab", "--healthy-window-interval-seconds", "14"]) == 2


def test_cli_authority_file_is_strict_private_and_manifest_bound(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    manifest_path = tmp_path / "manifest.json"
    provider_manifest_path = tmp_path / "provider-manifest.json"
    manifest_path.write_text(json.dumps(_manifest(), sort_keys=True), encoding="utf-8")
    provider_manifest_path.write_text(json.dumps(_provider_manifest(), sort_keys=True), encoding="utf-8")

    def invoke(authority_path: Path) -> tuple[int, str]:
        rc = cli_main(
            [
                "--manifest",
                str(manifest_path),
                "--provider-manifest",
                str(provider_manifest_path),
                "--authority-file",
                str(authority_path),
                "--observer-endpoint",
                "http://example.com:80",
                "--action-endpoint",
                "http://127.0.0.1:8020",
                "--output-summary",
                str(tmp_path / "summary.json"),
                "--output-jsonl",
                str(tmp_path / "evidence.jsonl"),
                "--allow-live-lab",
            ]
        )
        error = json.loads(capsys.readouterr().err)["error"]
        return rc, str(error)

    permissive = _write_authority_file(tmp_path / "permissive.env")
    permissive.chmod(0o640)
    assert invoke(permissive) == (2, "authority_file_mode_must_be_0600")

    mismatched = _write_authority_file(tmp_path / "mismatched.env", project_id="other-project")
    assert invoke(mismatched) == (2, "authority_binding_mismatch:P174_PROJECT_ID")

    policy_mismatch = _write_authority_file(tmp_path / "policy-mismatch.env", policy_version="other-policy")
    assert invoke(policy_mismatch) == (2, "authority_binding_mismatch:P174_POLICY_VERSION")

    shared_capability = _write_authority_file(tmp_path / "shared-capability.env", action_capability="s" * 32, fault_capability="s" * 32)
    assert invoke(shared_capability) == (2, "authority_capabilities_must_be_distinct")

    short_capability = _write_authority_file(tmp_path / "short-capability.env", action_capability="short")
    assert invoke(short_capability) == (2, "authority_action_capability_length_invalid")

    unknown = _write_authority_file(tmp_path / "unknown.env")
    unknown.write_text(unknown.read_text(encoding="utf-8") + "P174_EXTRA=forbidden\n", encoding="utf-8")
    assert invoke(unknown) == (2, "authority_file_key_forbidden:P174_EXTRA")

    duplicate = _write_authority_file(tmp_path / "duplicate.env")
    duplicate.write_text(duplicate.read_text(encoding="utf-8") + f"P174_RUN_ID={'run-174'}\n", encoding="utf-8")
    assert invoke(duplicate) == (2, "authority_file_key_duplicate:P174_RUN_ID")

    target = _write_authority_file(tmp_path / "target.env")
    symlink = tmp_path / "authority-link.env"
    symlink.symlink_to(target)
    assert invoke(symlink) == (2, "authority_file_symlink_forbidden")


def test_live_harness_policy_matches_workload_runtime_authority() -> None:
    workload_script = Path(__file__).resolve().parents[1] / "infra/gcp/p174/workload-iap.sh"
    script = workload_script.read_text(encoding="utf-8")

    assert "P174_POLICY_VERSION=p174-policy-v1" in script
    assert _POLICY_VERSION == "p174-policy-v1"


def test_loopback_observer_spaces_and_validates_distinct_receipt_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monotonic = {"now": 100.0}
    sleeps: list[float] = []
    payloads = iter(
        (
            _observer_payload(timestamp=1_784_246_400.0, sequence_tail=3, prefixed_hash=False),
            _observer_payload(timestamp=1_784_246_415.0, sequence_tail=6, prefixed_hash=False),
        )
    )

    def urlopen(_request: Request, timeout: float) -> _Response:
        return _Response(200, next(payloads))

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        monotonic["now"] += seconds

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    client = LoopbackObserverClient(
        "http://127.0.0.1:8030",
        min_interval_seconds=15,
        sleep_fn=sleep,
        monotonic_fn=lambda: monotonic["now"],
    )
    step = ScheduleStep(gate="healthy_window", index=1, target="target_a", action="observe", schedule_hash="sha256:" + "1" * 64)

    first = client.observe_health_window(step)
    second = client.observe_health_window(step)

    assert sleeps == [15.0]
    assert first["timestamp"] == "2026-07-17T00:00:00Z"
    assert first["sequence"] == 3
    assert second["sequence"] == 6
    assert first["window_id"] != second["window_id"]


def test_loopback_observer_rejects_subminimum_interval() -> None:
    with pytest.raises(ValueError):
        LoopbackObserverClient("http://127.0.0.1:8030", min_interval_seconds=14)
    with pytest.raises(ValueError, match="scenario_ready_attempts_invalid"):
        LoopbackObserverClient("http://127.0.0.1:8030", scenario_ready_attempts=21)


def test_loopback_observer_waits_for_bounded_scenario_baseline_stabilization(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    payloads = iter(
        (
            {"evaluation": {"healthy": False}, "state": {"queue_depth": 38}, "metrics": {"pool_size": 16}},
            {"evaluation": {"healthy": False}, "state": {"queue_depth": 22}, "metrics": {"pool_size": 16}},
            {"evaluation": {"healthy": True}, "state": {"queue_depth": 4}, "metrics": {"pool_size": 16}},
        )
    )
    client = LoopbackObserverClient(
        "http://127.0.0.1:8030",
        scenario_ready_attempts=3,
        scenario_ready_interval_seconds=0.25,
        sleep_fn=sleeps.append,
    )
    monkeypatch.setattr(client, "_get_json", lambda _path: next(payloads))
    step = ScenarioStep(
        "scenario_campaign",
        1,
        "target_a",
        harness_module._scenario_definition("rollback_required"),
        "sha256:" + "a" * 64,
    )

    observed = client.observe_scenario(step)

    assert observed["ready"] is True
    assert observed["stabilization_attempts"] == 3
    assert observed["state"]["queue_depth"] == 4
    assert sleeps == [0.25, 0.25]


def test_loopback_observer_fails_closed_after_bounded_unready_baselines(monkeypatch: pytest.MonkeyPatch) -> None:
    client = LoopbackObserverClient(
        "http://127.0.0.1:8030",
        scenario_ready_attempts=2,
        scenario_ready_interval_seconds=0.25,
        sleep_fn=lambda _seconds: None,
    )
    monkeypatch.setattr(
        client,
        "_get_json",
        lambda _path: {"evaluation": {"healthy": False}, "state": {"queue_depth": 80}, "metrics": {"pool_size": 16}},
    )
    step = ScenarioStep(
        "scenario_campaign",
        1,
        "target_a",
        harness_module._scenario_definition("rollback_required"),
        "sha256:" + "b" * 64,
    )

    observed = client.observe_scenario(step)

    assert observed["ready"] is False
    assert observed["stabilization_attempts"] == 2


def test_queue_backlog_fault_scales_above_worker_pool_capacity() -> None:
    step = ScenarioStep(
        "scenario_campaign",
        1,
        "target_a",
        harness_module._scenario_definition("restart_recovery"),
        "sha256:" + "c" * 64,
    )

    assert live_runner._fault_parameters(step, {"pool_size": 16}) == {"items": 64}
    assert live_runner._fault_parameters(step, {"pool_size": 1}) == {"items": 12}


@pytest.mark.parametrize("pool_size", [True, "16", float("nan"), 0, 65, 1.5])
def test_queue_backlog_fault_rejects_invalid_pool_capacity(pool_size: object) -> None:
    step = ScenarioStep(
        "scenario_campaign",
        1,
        "target_a",
        harness_module._scenario_definition("restart_recovery"),
        "sha256:" + "d" * 64,
    )

    with pytest.raises(live_runner._CliError, match="fault_baseline_pool_size_invalid"):
        live_runner._fault_parameters(step, {"pool_size": pool_size})


@pytest.mark.parametrize(
    "second_payload",
    [
        _observer_payload(timestamp=1_784_246_413.0, sequence_tail=6),
        _observer_payload(timestamp=1_784_246_415.0, sequence_tail=3),
        _observer_payload(timestamp=1_784_246_400.0, sequence_tail=3),
    ],
)
def test_loopback_observer_rejects_rapid_duplicate_or_non_increasing_windows(
    second_payload: Mapping[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payloads = iter((_observer_payload(timestamp=1_784_246_400.0, sequence_tail=3), second_payload))
    monkeypatch.setattr("urllib.request.urlopen", lambda _request, timeout: _Response(200, next(payloads)))
    client = LoopbackObserverClient(
        "http://127.0.0.1:8030",
        min_interval_seconds=15,
        sleep_fn=lambda _seconds: None,
        monotonic_fn=lambda: 0.0,
    )
    step = ScheduleStep(gate="healthy_window", index=1, target="target_a", action="observe", schedule_hash="sha256:" + "1" * 64)
    client.observe_health_window(step)

    with pytest.raises(ValueError):
        client.observe_health_window(step)


class _Headers:
    def __init__(self, values: Mapping[str, str]) -> None:
        self._values = {key.lower(): value for key, value in values.items()}

    def get(self, key: str, default: str = "") -> str:
        return self._values.get(key.lower(), default)


class _PostHarness(ServiceHandler):
    def __init__(self, *, service: RuntimeActionService, path: str, body: Mapping[str, Any], headers: Mapping[str, str]) -> None:
        raw = json.dumps(dict(body), sort_keys=True).encode("utf-8")
        self.server = cast(Any, SimpleNamespace(p174_role="fault-controller", p174_service=service))
        self.path = path
        self.headers = cast(Any, _Headers({**headers, "content-length": str(len(raw))}))
        self.rfile = io.BytesIO(raw)
        self.wfile = cast(Any, io.BytesIO())
        self.status: int | None = None

    def send_response(self, code: int, message: str | None = None) -> None:
        self.status = code

    def send_header(self, keyword: str, value: str) -> None:
        return None

    def end_headers(self) -> None:
        return None


def _dispatch_service_post(
    service: RuntimeActionService,
    path: str,
    body: Mapping[str, Any],
    headers: Mapping[str, str],
) -> tuple[int, dict[str, Any]]:
    handler = _PostHarness(service=service, path=path, body=body, headers=headers)
    handler.do_POST()
    assert handler.status is not None
    payload = json.loads(cast(io.BytesIO, handler.wfile).getvalue())
    assert isinstance(payload, dict)
    return handler.status, payload


class _Response:
    def __init__(self, status: int, payload: Mapping[str, Any]) -> None:
        self.status = status
        self.payload = payload

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, _limit: int = -1) -> bytes:
        return json.dumps(self.payload, sort_keys=True).encode()


class _ServiceGateway:
    def __init__(self, service: RuntimeActionService, clock: dict[str, datetime]) -> None:
        self.service = service
        self.clock = clock
        self.calls: list[dict[str, Any]] = []
        self.drain_after_restart = False
        self.drain_next_queue_fault = False
        self.drain_after_queue_fault = False
        self.collect_calls = 0

    def __call__(self, request: Request, timeout: float) -> _Response:
        method = request.get_method()
        url = request.full_url
        path = urlsplit(url).path
        headers = {key.lower(): value for key, value in request.header_items()}
        if method == "GET" and path == "/collect":
            self.collect_calls += 1
            observed_at = self.clock["now"] + timedelta(seconds=15 * (self.collect_calls - 1))
            payload = {
                **_observer_payload(timestamp=observed_at.timestamp(), sequence_tail=self.collect_calls * 3),
                **self.service.state(),
            }
            status = 200
        elif method == "GET" and path == "/state":
            if self.drain_after_queue_fault:
                for _ in range(4):
                    self.service.process_worker_batch()
                self.drain_after_queue_fault = False
            if self.drain_after_restart:
                self.clock["now"] += timedelta(seconds=1)
                self.service.process_worker_batch()
            payload = self.service.state()
            status = 200
        elif method == "POST":
            assert request.data is not None
            body = json.loads(cast(bytes, request.data))
            assert isinstance(body, dict)
            status, payload = _dispatch_service_post(self.service, path, body, headers)
            if path == "/actions" and body.get("action") == "restart_worker":
                self.drain_after_restart = True
            if path == "/faults" and body.get("fault") == "queue_backlog" and self.drain_next_queue_fault:
                self.drain_next_queue_fault = False
                self.drain_after_queue_fault = True
            if path == "/faults/cleanup":
                self.drain_after_restart = False
        else:
            raise AssertionError((method, url))
        self.calls.append({"method": method, "url": url, "path": path, "status": status, "headers": headers})
        return _Response(status, payload)


def _runtime_service(clock: dict[str, datetime], action_capability: str, fault_capability: str) -> RuntimeActionService:
    return RuntimeActionService(
        InMemoryCausalStore(),
        project_id="opscat-p174-lab",
        target_id="target_a",
        run_id="run-174",
        policy_version="p174-policy-v1",
        capability=action_capability,
        fault_capability=fault_capability,
        now=lambda: clock["now"],
    )


def _provider_client(
    *,
    action_capability: str,
    fault_capability: str,
    lease_expires_at: datetime,
) -> tuple[ProviderLab, ProviderLabActionClient]:
    provider_manifest = validate_manifest(_provider_manifest())
    transport = HttpP174ProviderTransport(
        base_url="http://127.0.0.1:8020",
        capability=action_capability,
        lease_expires_at=lease_expires_at,
        post_check_delay_seconds=0,
        post_check_samples=3,
    )
    lab = ProviderLab(provider_manifest, transport=transport)
    lab.acquire_lease("owner-1")
    return lab, ProviderLabActionClient(
        target_url="http://127.0.0.1:8020",
        lab=lab,
        owner_id="owner-1",
        fault_capability=fault_capability,
        policy_version="p174-policy-v1",
        lease_expires_at=lease_expires_at,
    )


def _observed_baseline(service: RuntimeActionService) -> dict[str, Any]:
    payload = service.state()
    state = {**payload["state"], **payload["metrics"]}
    return {"ready": True, "state": state, "state_hash": stable_hash(state)}


def _protected(state: Mapping[str, Any]) -> dict[str, Any]:
    keys = ("project_id", "target_id", "run_id", "pool_size", "canary_version", "worker_restart_generation", "worker_paused_until")
    return {key: state[key] for key in keys}


def test_fault_receipt_proves_backlog_even_if_worker_drains_before_next_read(monkeypatch: pytest.MonkeyPatch) -> None:
    action_capability = "a" * 32
    fault_capability = "f" * 32
    clock = {"now": datetime.now(tz=UTC).replace(microsecond=0)}
    service = _runtime_service(clock, action_capability, fault_capability)
    gateway = _ServiceGateway(service, clock)
    gateway.drain_next_queue_fault = True
    monkeypatch.setattr("urllib.request.urlopen", gateway)
    _, client = _provider_client(
        action_capability=action_capability,
        fault_capability=fault_capability,
        lease_expires_at=clock["now"] + timedelta(seconds=60),
    )
    manifest = parse_reviewed_manifest(_manifest(allowed_targets=["target_a"]))
    step = next(item for item in build_seeded_campaign(manifest) if item.scenario.fault == "queue_backlog")
    baseline = _observed_baseline(service)

    fault = client.inject_fault(step, baseline)
    later_state = client._target_state()

    assert fault["state"]["queue_depth"] > fault["baseline_state"]["queue_depth"]
    assert later_state["queue_depth"] < fault["state"]["queue_depth"]


def test_rollback_and_cleanup_proof_tolerates_live_queue_progress() -> None:
    baseline_state = _baseline_state(2)
    baseline = {"ready": True, "state": baseline_state, "state_hash": stable_hash(baseline_state)}
    fault_state = {**baseline_state, "queue_depth": 3, "worker_paused_until": "2026-07-17T00:01:00Z"}
    post_state = {**fault_state, "queue_depth": 6}
    cleanup_state = {**baseline_state, "queue_depth": 0}
    fault_result = {
        "accepted": True,
        "baseline_state": baseline_state,
        "baseline_state_hash": stable_hash(baseline_state),
        "state": fault_state,
        "state_hash": stable_hash(fault_state),
    }
    post_result = {
        "status": "rolled_back",
        "rollback_closure_claimed": True,
        "state": post_state,
        "state_hash": stable_hash(post_state),
    }
    cleanup_result = {"status": "cleaned", "state": cleanup_state, "state_hash": stable_hash(cleanup_state)}
    step = ScenarioStep(
        gate="scenario_campaign",
        index=1,
        target="target_a",
        scenario=harness_module._scenario_definition("rollback_required"),
        campaign_hash="sha256:" + "a" * 64,
    )

    verdict = harness_module._scenario_verdict(step, baseline, fault_result, post_result, cleanup_result)

    assert verdict["passed"] is True
    assert verdict["reason"] == "ok"
    assert verdict["checks"] == {
        "baseline_ready": True,
        "fault_accepted": True,
        "fault_delta_proven": True,
        "expected_delta_proven": True,
        "cleanup_proven": True,
    }
    assert verdict["post_status"] == "rolled_back"
    assert verdict["post_failure_reason"] is None
    assert verdict["post_failure_detail"] is None
    assert verdict["post_state_sequence"] is None
    assert verdict["rollback_closure_claimed"] is True


def test_scenario_verdict_exposes_the_exact_failed_proof_gate() -> None:
    baseline_state = _baseline_state(2)
    baseline = {"ready": False, "state": baseline_state, "state_hash": stable_hash(baseline_state)}
    fault_state = {**baseline_state, "worker_paused_until": "2026-07-17T00:01:00Z"}
    post_state = dict(fault_state)
    cleanup_state = dict(baseline_state)
    fault_result = {
        "accepted": True,
        "baseline_state": baseline_state,
        "baseline_state_hash": stable_hash(baseline_state),
        "state": fault_state,
        "state_hash": stable_hash(fault_state),
    }
    post_result = {
        "status": "rolled_back",
        "rollback_closure_claimed": True,
        "state": post_state,
        "state_hash": stable_hash(post_state),
    }
    cleanup_result = {"status": "cleaned", "state": cleanup_state, "state_hash": stable_hash(cleanup_state)}
    step = ScenarioStep(
        gate="scenario_campaign",
        index=1,
        target="target_a",
        scenario=harness_module._scenario_definition("rollback_required"),
        campaign_hash="sha256:" + "c" * 64,
    )

    verdict = harness_module._scenario_verdict(step, baseline, fault_result, post_result, cleanup_result)

    assert verdict["passed"] is False
    assert verdict["reason"] == "claim_not_proven"
    assert verdict["checks"]["baseline_ready"] is False
    assert all(value is True for key, value in verdict["checks"].items() if key != "baseline_ready")


def test_restart_recovery_fails_closed_without_post_queue_evidence() -> None:
    baseline_state = _baseline_state(2)
    baseline = {"ready": True, "state": baseline_state, "state_hash": stable_hash(baseline_state)}
    fault_state = {**baseline_state, "queue_depth": 82}
    post_state = {**fault_state, "worker_restart_generation": 1}
    post_state.pop("queue_depth")
    cleanup_state = dict(baseline_state)
    fault_result = {
        "accepted": True,
        "baseline_state": baseline_state,
        "baseline_state_hash": stable_hash(baseline_state),
        "state": fault_state,
        "state_hash": stable_hash(fault_state),
    }
    post_result = {"status": "applied", "state": post_state, "state_hash": stable_hash(post_state)}
    cleanup_result = {"status": "cleaned", "state": cleanup_state, "state_hash": stable_hash(cleanup_state)}
    step = ScenarioStep(
        gate="scenario_campaign",
        index=1,
        target="target_a",
        scenario=harness_module._scenario_definition("restart_recovery"),
        campaign_hash="sha256:" + "b" * 64,
    )

    with pytest.raises(P174LiveHarnessError, match="numeric_state_required:queue_depth"):
        harness_module._scenario_verdict(step, baseline, fault_result, post_result, cleanup_result)


def test_scenario_request_keys_are_campaign_bound_and_retry_stable() -> None:
    scenario = harness_module._scenario_definition("rollback_required")
    first = ScenarioStep("scenario_campaign", 21, "target_a", scenario, "sha256:" + "a" * 64)
    second = ScenarioStep("scenario_campaign", 21, "target_a", scenario, "sha256:" + "a" * 16 + "b" * 48)

    assert live_runner._scenario_request_key("fault", first) == live_runner._scenario_request_key("fault", first)
    assert live_runner._scenario_request_key("fault", first) != live_runner._scenario_request_key("fault", second)
    assert live_runner._scenario_request_key("fault", first).startswith("p175-fault-" + "a" * 64 + "-")
    assert len(live_runner._scenario_request_key("cleanup", first)) <= 128


def test_cli_wires_observer_collect_faults_and_provider_lab_action_flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest_path = tmp_path / "manifest.json"
    provider_manifest_path = tmp_path / "provider-manifest.json"
    authority_path = _write_authority_file(tmp_path / "authority.env")
    manifest_path.write_text(json.dumps(_manifest(), sort_keys=True), encoding="utf-8")
    provider_manifest_path.write_text(json.dumps(_provider_manifest(), sort_keys=True), encoding="utf-8")
    action_capability = "a" * 32
    fault_capability = "f" * 32
    clock = {"now": datetime.now(tz=UTC).replace(microsecond=0)}
    service = _runtime_service(clock, action_capability, fault_capability)
    gateway = _ServiceGateway(service, clock)

    monkeypatch.setattr("urllib.request.urlopen", gateway)
    monkeypatch.setattr("app.services.p174_gcp_provider_lab.time.sleep", lambda _seconds: None)
    monkeypatch.setattr("scripts.run_p174_live_harness.time.sleep", lambda _seconds: None)

    rc = cli_main(
        [
            "--manifest",
            str(manifest_path),
            "--provider-manifest",
            str(provider_manifest_path),
            "--authority-file",
            str(authority_path),
            "--observer-endpoint",
            "http://127.0.0.1:8030",
            "--action-endpoint",
            "http://127.0.0.1:8020",
            "--output-summary",
            str(tmp_path / "summary.json"),
            "--output-jsonl",
            str(tmp_path / "evidence.jsonl"),
            "--allow-live-lab",
            "--owner-id",
            "owner-1",
            "--max-scenarios",
            "1",
            "--timeout-seconds",
            "1",
        ]
    )

    assert rc == 0
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["qualified"] is False
    assert summary["gates"]["scenario_campaign"]["required_exact"] == 100
    assert summary["gates"]["scenario_campaign"]["observed_successful"] == 1
    assert any(call["url"] == "http://127.0.0.1:8030/collect" for call in gateway.calls)
    assert sum(call["path"] == "/state" and call["method"] == "GET" for call in gateway.calls) >= 7
    mutations = [call for call in gateway.calls if call["method"] == "POST"]
    assert {call["path"] for call in mutations} >= {"/faults", "/actions", "/faults/cleanup"}
    assert all(call["status"] == 202 for call in mutations)
    for call in gateway.calls:
        headers = call["headers"]
        if call["path"] in {"/faults", "/faults/cleanup"}:
            assert headers.get("x-p174-fault-capability") == fault_capability
            assert "x-p174-capability" not in headers
        else:
            assert "x-p174-fault-capability" not in headers
        if call["path"] in {"/actions", "/actions/rollback"}:
            assert headers.get("x-p174-capability") == action_capability
        if call["method"] == "GET":
            assert call["status"] == 200


def test_mutated_fault_with_malformed_receipt_is_cleaned_before_injection_failure_returns(monkeypatch: pytest.MonkeyPatch) -> None:
    action_capability = "a" * 32
    fault_capability = "f" * 32
    clock = {"now": datetime.now(tz=UTC).replace(microsecond=0)}
    service = _runtime_service(clock, action_capability, fault_capability)
    gateway = _ServiceGateway(service, clock)

    def malformed_fault_gateway(request: Request, timeout: float) -> _Response:
        response = gateway(request, timeout)
        if request.get_method() == "POST" and urlsplit(request.full_url).path == "/faults" and response.status == 202:
            malformed = dict(response.payload)
            malformed.pop("state", None)
            return _Response(response.status, malformed)
        return response

    monkeypatch.setattr("urllib.request.urlopen", malformed_fault_gateway)
    lab, client = _provider_client(
        action_capability=action_capability,
        fault_capability=fault_capability,
        lease_expires_at=clock["now"] - timedelta(seconds=1),
    )
    recorder = JsonlEvidenceRecorder()

    summary = run_qualification(
        parse_reviewed_manifest(_manifest(allowed_targets=["target_a"])),
        HealthyObserver(),
        client,
        recorder=recorder,
        max_scenarios=1,
        diagnostic_campaign_only=True,
    )

    assert summary["status"] == "blocked"
    assert summary["failures"][0]["reason"] == "client_exception"
    mutations = [call["path"] for call in gateway.calls if call["method"] == "POST"]
    assert mutations == ["/faults", "/faults/cleanup"]
    event = recorder.events[-1]
    assert event.event_type == "exception"
    assert event.payload["error_type"] == "_CliError"
    assert event.payload["error"].endswith(";cleanup:proven")
    assert lab.transport.name == "p174-private-http-v1"


def test_malformed_fault_receipt_never_claims_cleanup_when_protected_state_remains_mutated(monkeypatch: pytest.MonkeyPatch) -> None:
    action_capability = "a" * 32
    fault_capability = "f" * 32
    clock = {"now": datetime.now(tz=UTC).replace(microsecond=0)}
    service = _runtime_service(clock, action_capability, fault_capability)
    gateway = _ServiceGateway(service, clock)

    def unproven_cleanup_gateway(request: Request, timeout: float) -> _Response:
        response = gateway(request, timeout)
        path = urlsplit(request.full_url).path
        if request.get_method() == "POST" and path == "/faults":
            malformed = dict(response.payload)
            malformed.pop("state", None)
            return _Response(response.status, malformed)
        if request.get_method() == "POST" and path == "/faults/cleanup":
            state = service._state()
            state["pool_size"] = int(state["pool_size"]) + 1
            service.store.set_json(service.state_key, state)
        return response

    monkeypatch.setattr("urllib.request.urlopen", unproven_cleanup_gateway)
    _lab, client = _provider_client(
        action_capability=action_capability,
        fault_capability=fault_capability,
        lease_expires_at=clock["now"] - timedelta(seconds=1),
    )
    recorder = JsonlEvidenceRecorder()

    summary = run_qualification(
        parse_reviewed_manifest(_manifest(allowed_targets=["target_a"])),
        HealthyObserver(),
        client,
        recorder=recorder,
        max_scenarios=1,
        diagnostic_campaign_only=True,
    )

    assert summary["status"] == "blocked"
    event = recorder.events[-1]
    assert event.event_type == "exception"
    assert event.payload["error"].endswith(";cleanup_unproven")
    assert not event.payload["error"].endswith(";cleanup:proven")


def test_provider_scenarios_use_real_state_provider_lab_and_server_snapshot_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    action_capability = "a" * 32
    fault_capability = "f" * 32
    clock = {"now": datetime.now(tz=UTC).replace(microsecond=0)}
    service = _runtime_service(clock, action_capability, fault_capability)
    gateway = _ServiceGateway(service, clock)
    monkeypatch.setattr("urllib.request.urlopen", gateway)
    lab, client = _provider_client(
        action_capability=action_capability,
        fault_capability=fault_capability,
        lease_expires_at=clock["now"] - timedelta(seconds=1),
    )
    original_run_action = lab.run_action
    provider_calls = 0

    def counted_run_action(owner_id: str, request: Any) -> dict[str, Any]:
        nonlocal provider_calls
        provider_calls += 1
        return original_run_action(owner_id, request)

    monkeypatch.setattr(lab, "run_action", counted_run_action)
    manifest = parse_reviewed_manifest(_manifest(allowed_targets=["target_a"]))
    scenarios = {step.scenario.name: step for step in build_seeded_campaign(manifest)}

    cases: tuple[tuple[ScenarioKind, str], ...] = (
        ("canary_rollback", "applied"),
        ("rollback_required", "rolled_back"),
        ("rejection", "rejected"),
        ("safety_boundary", "blocked"),
    )
    for name, expected_status in cases:
        step = scenarios[name]
        baseline = _observed_baseline(service)
        fault = client.inject_fault(step, baseline)
        assert "cleanup_token" not in fault
        post = client.run_scenario(step, baseline, fault)
        assert post["status"] == expected_status
        if name == "canary_rollback":
            assert post["state"]["canary_version"] == "stable"
        if name in {"rejection", "safety_boundary"}:
            assert _protected(post["state"]) == _protected(fault["state"])
        cleanup = client.cleanup_scenario(step, baseline, post)
        assert _protected(cleanup["state"]) == _protected(fault["baseline_state"])

    assert provider_calls == 4
    cleanup_calls = [call for call in gateway.calls if call["path"] == "/faults/cleanup"]
    assert len(cleanup_calls) == 4
    assert all(call["status"] == 202 for call in cleanup_calls)
    assert all(call["headers"].get("x-p174-fault-capability") == fault_capability for call in cleanup_calls)


def test_all_100_seeded_scenarios_execute_and_cleanup_against_real_provider_path(monkeypatch: pytest.MonkeyPatch) -> None:
    action_capability = "a" * 32
    fault_capability = "f" * 32
    clock = {"now": datetime.now(tz=UTC).replace(microsecond=0)}
    service = _runtime_service(clock, action_capability, fault_capability)
    gateway = _ServiceGateway(service, clock)
    monkeypatch.setattr("urllib.request.urlopen", gateway)
    lab, client = _provider_client(
        action_capability=action_capability,
        fault_capability=fault_capability,
        lease_expires_at=clock["now"] - timedelta(seconds=1),
    )
    manifest = parse_reviewed_manifest(_manifest(allowed_targets=["target_a"]))
    expected_status = {
        "restart_recovery": "applied",
        "canary_rollback": "applied",
        "rejection": "rejected",
        "rollback_required": "rolled_back",
        "safety_boundary": "blocked",
    }

    for step in build_seeded_campaign(manifest):
        baseline = _observed_baseline(service)
        fault = client.inject_fault(step, baseline)
        post = client.run_scenario(step, baseline, fault)
        assert post["status"] == expected_status[step.scenario.name], step.to_dict()
        cleanup = client.cleanup_scenario(step, baseline, post)
        assert _protected(cleanup["state"]) == _protected(fault["baseline_state"])

    assert len(lab.receipts) == 70
    assert sum(call["path"] == "/faults/cleanup" for call in gateway.calls) == 100


def test_stable_hash_is_canonical() -> None:
    assert stable_hash({"b": 2, "a": 1}) == stable_hash({"a": 1, "b": 2})
