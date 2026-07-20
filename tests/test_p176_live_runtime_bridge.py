from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.services.p147_p152_contracts import file_hash, stable_hash
from app.services.p176_campaign import generate_p176_campaign
from app.services.p176_evaluator import SAFETY_COUNTER_KEYS, evaluate_campaign
from app.services.p176_live_bridge import (
    CANONICAL_SAFETY_COUNTERS_PATH,
    LIVE_ARTIFACT_MANIFEST_PATH,
    LIVE_HEALTHY_RESULTS_PATH,
    LIVE_OUTCOMES_PATH,
    RELEASE_INPUTS_MANIFEST_PATH,
    load_json,
    load_jsonl,
    materialize_live_release_inputs,
)
from app.services.p176_live_gates import LIVE_SAFETY_KEYS
from app.services.p176_runtime_bridge import (
    COLLECTION_IN_PROGRESS_PATH,
    COLLECTION_RECEIPT_PATH,
    EPISODE_EVIDENCE_SOURCE_CLASSES,
    EPISODE_PHASE_CHECKPOINT_PATH,
    FINALIZATION_RECEIPT_PATH,
    BillingSnapshot,
    EvidenceProvider,
    EvidenceSnapshot,
    FaultExecution,
    FaultHarness,
    HealthyObservation,
    HealthyObserver,
    P176RuntimeArtifactProducer,
    P176RuntimeBridgeError,
    P176RuntimeConfig,
    TeardownSnapshot,
    fault_proof_hash,
)

TRUSTED_NOW = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)


def test_runtime_producer_writes_artifacts_consumed_by_live_materializer(tmp_path: Path) -> None:
    run_dir = tmp_path / "runtime-run"
    plan_paths = _write_plan_artifacts(run_dir)
    producer = _producer(plan_paths=plan_paths)

    produced_dir = producer.produce(run_dir, now=TRUSTED_NOW)
    result = materialize_live_release_inputs(
        produced_dir,
        now=TRUSTED_NOW,
        reviewed_apply_plan_artifact_path=plan_paths["lab_apply"],
        reviewed_teardown_plan_artifact_path=plan_paths["lab_destroy"],
        reviewed_cost_cutoff_apply_plan_artifact_path=plan_paths["cost_cutoff_apply"],
        reviewed_cost_cutoff_destroy_plan_artifact_path=plan_paths["cost_cutoff_destroy"],
    )

    campaign = generate_p176_campaign()
    outcomes = load_jsonl(run_dir / LIVE_OUTCOMES_PATH)
    healthy_results = load_jsonl(run_dir / LIVE_HEALTHY_RESULTS_PATH)
    safety_counters = load_json(run_dir / CANONICAL_SAFETY_COUNTERS_PATH)
    report = evaluate_campaign(
        campaign=campaign,
        episodes=campaign["episodes"],
        outcomes=outcomes,
        healthy_windows=campaign["healthy_windows"],
        healthy_results=healthy_results,
        safety_counters=safety_counters,
    )

    assert result.subordinate_status == "p176_disposable_gcp_live_lab_evidence_ready"
    assert len(load_jsonl(run_dir / "episode-observations.jsonl")) == 480
    assert len(load_jsonl(run_dir / "healthy-window-observations.jsonl")) == 240
    assert report["qualified"] is True
    assert set(safety_counters) == set(SAFETY_COUNTER_KEYS)
    assert all(value == 0 for value in safety_counters.values())
    release_manifest = load_json(run_dir / RELEASE_INPUTS_MANIFEST_PATH)
    live_manifest = load_json(run_dir / LIVE_ARTIFACT_MANIFEST_PATH)
    assert release_manifest["build_release_artifacts_target"] == "app.services.p176_release.build_release_artifacts"
    assert release_manifest["live_artifact_manifest_hash"] == live_manifest["manifest_hash"]


def test_runtime_collection_does_not_query_post_collection_providers(tmp_path: Path) -> None:
    run_dir = tmp_path / "collection-only"
    plan_paths = _write_plan_artifacts(run_dir)
    billing = CountingBillingProvider(fail_if_called=True)
    teardown = CountingTeardownProvider(
        reviewed_apply_plan_hash=file_hash(plan_paths["lab_apply"]),
        fail_if_called=True,
    )
    producer = _producer(plan_paths=plan_paths, billing_provider=billing, teardown_provider=teardown)

    assert producer.collect(run_dir) == run_dir

    assert billing.call_count == 0
    assert teardown.call_count == 0
    assert (run_dir / COLLECTION_RECEIPT_PATH).is_file()
    assert not (run_dir / "billing-report.json").exists()
    assert not (run_dir / "teardown-proof.json").exists()
    assert not (run_dir / FINALIZATION_RECEIPT_PATH).exists()


def test_runtime_observations_cite_fresh_relevant_evidence_records(tmp_path: Path) -> None:
    run_dir = tmp_path / "evidence-binding"
    plan_paths = _write_plan_artifacts(run_dir)

    _producer(plan_paths=plan_paths).collect(run_dir)

    agent_records = load_jsonl(run_dir / "agent-visible-ledger.jsonl")
    evaluator_records = load_jsonl(run_dir / "evaluator-only-ledger.jsonl")
    episodes = load_jsonl(run_dir / "episode-observations.jsonl")
    windows = load_jsonl(run_dir / "healthy-window-observations.jsonl")
    agent_source_by_hash = {record["record_hash"]: record["source_class"] for record in agent_records}
    evaluator_source_by_hash = {record["record_hash"]: record["source_class"] for record in evaluator_records}

    for episode in episodes:
        expected = set(EPISODE_EVIDENCE_SOURCE_CLASSES[episode["primary_layer"]])
        assert {agent_source_by_hash[item] for item in episode["agent_visible_record_hashes"]} == expected
        assert {evaluator_source_by_hash[item] for item in episode["evaluator_only_record_hashes"]} == expected

    for window in windows:
        assert [agent_source_by_hash[item] for item in window["agent_visible_record_hashes"]] == [window["telemetry_class"]]
        assert [evaluator_source_by_hash[item] for item in window["evaluator_only_record_hashes"]] == [
            window["telemetry_class"]
        ]

    assert len({tuple(row["agent_visible_record_hashes"]) for row in episodes}) > 1
    assert len({tuple(row["evaluator_only_record_hashes"]) for row in episodes}) > 1


def test_runtime_finalize_requires_completed_collection(tmp_path: Path) -> None:
    run_dir = tmp_path / "missing-collection"
    plan_paths = _write_plan_artifacts(run_dir)
    producer = _producer(plan_paths=plan_paths)

    with pytest.raises(P176RuntimeBridgeError, match="collection_receipt_missing"):
        producer.finalize(run_dir, now=TRUSTED_NOW)


def test_runtime_finalize_rejects_tampered_collection(tmp_path: Path) -> None:
    run_dir = tmp_path / "tampered-collection"
    plan_paths = _write_plan_artifacts(run_dir)
    producer = _producer(plan_paths=plan_paths)
    producer.collect(run_dir)
    (run_dir / "agent-visible-ledger.jsonl").write_text("{}\n", encoding="utf-8")

    with pytest.raises(P176RuntimeBridgeError, match="collection_artifact_hash_mismatch"):
        producer.finalize(run_dir, now=TRUSTED_NOW)


def test_runtime_finalize_rejects_collection_from_different_runtime_config(tmp_path: Path) -> None:
    run_dir = tmp_path / "config-mismatch"
    plan_paths = _write_plan_artifacts(run_dir)
    producer = _producer(plan_paths=plan_paths)
    producer.collect(run_dir)
    changed = replace(
        producer,
        config=replace(producer.config, reviewed_teardown_plan_hash=stable_hash("different-destroy-plan")),
    )

    with pytest.raises(P176RuntimeBridgeError, match="collection_config_mismatch"):
        changed.finalize(run_dir, now=TRUSTED_NOW)


def test_runtime_collection_crash_marker_prevents_fault_replay(tmp_path: Path) -> None:
    run_dir = tmp_path / "crashed-collection"
    plan_paths = _write_plan_artifacts(run_dir)
    harness = CrashingFaultHarness()
    producer = _producer(plan_paths=plan_paths, fault_harness=harness)

    with pytest.raises(RuntimeError, match="simulated harness crash"):
        producer.collect(run_dir)
    assert harness.call_count == 1
    assert (run_dir / COLLECTION_IN_PROGRESS_PATH).is_file()

    with pytest.raises(P176RuntimeBridgeError, match="collection_partial_state"):
        producer.collect(run_dir)
    assert harness.call_count == 1


def test_runtime_collection_resumes_healthy_phase_without_replaying_completed_faults(tmp_path: Path) -> None:
    run_dir = tmp_path / "healthy-resume"
    plan_paths = _write_plan_artifacts(run_dir)
    harness = CountingFaultHarness()
    producer = _producer(
        plan_paths=plan_paths,
        fault_harness=harness,
        healthy_observer=CrashingHealthyObserver(),
    )

    with pytest.raises(RuntimeError, match="simulated healthy observer crash"):
        producer.collect(run_dir)

    assert harness.call_count == 480
    assert (run_dir / COLLECTION_IN_PROGRESS_PATH).is_file()
    assert (run_dir / EPISODE_PHASE_CHECKPOINT_PATH).is_file()

    resumed = _producer(
        plan_paths=plan_paths,
        fault_harness=harness,
        healthy_observer=FakeHealthyObserver(),
    )
    assert resumed.collect(run_dir) == run_dir

    assert harness.call_count == 480
    assert len(load_jsonl(run_dir / "episode-observations.jsonl")) == 480
    assert len(load_jsonl(run_dir / "healthy-window-observations.jsonl")) == 240
    assert not (run_dir / EPISODE_PHASE_CHECKPOINT_PATH).exists()
    assert not (run_dir / COLLECTION_IN_PROGRESS_PATH).exists()


def test_runtime_collection_checkpoints_completed_faults_before_provider_failure(tmp_path: Path) -> None:
    run_dir = tmp_path / "fault-progress-resume"
    plan_paths = _write_plan_artifacts(run_dir)
    failing = FailingAfterFaultHarness(fail_at=12)

    with pytest.raises(RuntimeError, match="simulated diagnosis provider failure"):
        _producer(plan_paths=plan_paths, fault_harness=failing).collect(run_dir)

    checkpoint = load_json(run_dir / EPISODE_PHASE_CHECKPOINT_PATH)
    assert checkpoint["completed_episode_count"] == 11
    assert checkpoint["completed_healthy_window_count"] == 0

    resumed_harness = CountingFaultHarness()
    _producer(plan_paths=plan_paths, fault_harness=resumed_harness).collect(run_dir)

    assert failing.call_count == 12
    assert resumed_harness.call_count == 469


def test_runtime_collection_does_not_replay_faults_before_post_execution_validation_failure(tmp_path: Path) -> None:
    run_dir = tmp_path / "post-fault-validation-resume"
    plan_paths = _write_plan_artifacts(run_dir)
    failing = BadProofAfterFaultHarness(fail_at=12)

    with pytest.raises(P176RuntimeBridgeError, match="cleanup_receipt_hash_not_bound"):
        _producer(plan_paths=plan_paths, fault_harness=failing).collect(run_dir)

    checkpoint = load_json(run_dir / EPISODE_PHASE_CHECKPOINT_PATH)
    assert checkpoint["completed_episode_count"] == 11

    resumed_harness = CountingFaultHarness()
    _producer(plan_paths=plan_paths, fault_harness=resumed_harness).collect(run_dir)

    assert failing.call_count == 12
    assert resumed_harness.call_count == 469


def test_runtime_collection_checkpoints_completed_healthy_windows(tmp_path: Path) -> None:
    run_dir = tmp_path / "healthy-progress-resume"
    plan_paths = _write_plan_artifacts(run_dir)
    fault_harness = CountingFaultHarness()
    failing_healthy = FailingAfterHealthyObserver(fail_at=12)

    with pytest.raises(RuntimeError, match="simulated healthy provider failure"):
        _producer(
            plan_paths=plan_paths,
            fault_harness=fault_harness,
            healthy_observer=failing_healthy,
        ).collect(run_dir)

    checkpoint = load_json(run_dir / EPISODE_PHASE_CHECKPOINT_PATH)
    assert checkpoint["completed_episode_count"] == 480
    assert checkpoint["completed_healthy_window_count"] == 11

    resumed_healthy = CountingHealthyObserver()
    _producer(
        plan_paths=plan_paths,
        fault_harness=fault_harness,
        healthy_observer=resumed_healthy,
    ).collect(run_dir)

    assert fault_harness.call_count == 480
    assert resumed_healthy.call_count == 229


def test_runtime_collection_rejects_tampered_episode_phase_checkpoint(tmp_path: Path) -> None:
    run_dir = tmp_path / "tampered-resume"
    plan_paths = _write_plan_artifacts(run_dir)
    producer = _producer(
        plan_paths=plan_paths,
        healthy_observer=CrashingHealthyObserver(),
    )
    with pytest.raises(RuntimeError, match="simulated healthy observer crash"):
        producer.collect(run_dir)
    (run_dir / "agent-visible-ledger.jsonl").write_text("{}\n", encoding="utf-8")

    with pytest.raises(P176RuntimeBridgeError, match="episode_phase_checkpoint_artifact_hash_mismatch"):
        _producer(plan_paths=plan_paths).collect(run_dir)


def test_runtime_collection_cleans_stale_markers_after_verified_terminal_receipt(tmp_path: Path) -> None:
    run_dir = tmp_path / "terminal-marker-cleanup"
    plan_paths = _write_plan_artifacts(run_dir)
    producer = _producer(plan_paths=plan_paths)
    producer.collect(run_dir)
    (run_dir / COLLECTION_IN_PROGRESS_PATH).write_text("stale\n", encoding="utf-8")
    (run_dir / EPISODE_PHASE_CHECKPOINT_PATH).write_text("stale\n", encoding="utf-8")

    assert producer.collect(run_dir) == run_dir

    assert not (run_dir / COLLECTION_IN_PROGRESS_PATH).exists()
    assert not (run_dir / EPISODE_PHASE_CHECKPOINT_PATH).exists()


def test_runtime_finalize_is_idempotent_without_requerying_providers(tmp_path: Path) -> None:
    run_dir = tmp_path / "idempotent-finalize"
    plan_paths = _write_plan_artifacts(run_dir)
    billing = CountingBillingProvider()
    teardown = CountingTeardownProvider(reviewed_apply_plan_hash=file_hash(plan_paths["lab_apply"]))
    producer = _producer(plan_paths=plan_paths, billing_provider=billing, teardown_provider=teardown)
    producer.collect(run_dir)

    assert producer.finalize(run_dir, now=TRUSTED_NOW) == run_dir
    assert producer.finalize(run_dir, now=TRUSTED_NOW) == run_dir

    assert billing.call_count == 1
    assert teardown.call_count == 1
    assert (run_dir / FINALIZATION_RECEIPT_PATH).is_file()


def test_runtime_producer_fails_closed_on_duplicate_fault_lease(tmp_path: Path) -> None:
    plan_paths = _write_plan_artifacts(tmp_path / "duplicate-lease")
    producer = _producer(plan_paths=plan_paths, fault_harness=FakeFaultHarness(duplicate_lease=True))

    with pytest.raises(P176RuntimeBridgeError, match="fault_lease_replayed"):
        producer.produce(tmp_path / "duplicate-lease", now=TRUSTED_NOW)


def test_runtime_producer_scores_raw_diagnosis_outside_fault_harness(tmp_path: Path) -> None:
    run_dir = tmp_path / "wrong-diagnosis"
    plan_paths = _write_plan_artifacts(run_dir)
    producer = _producer(plan_paths=plan_paths, fault_harness=FakeFaultHarness(wrong_diagnosis=True))

    producer.collect(run_dir)

    first = load_jsonl(run_dir / "episode-observations.jsonl")[0]
    assert first["incident_detected"] is True
    assert first["diagnosis_correct"] is False
    assert first["routing_correct"] is True
    assert first["citation_supported"] is True


def test_runtime_producer_fails_closed_on_reordered_campaign(tmp_path: Path) -> None:
    plan_paths = _write_plan_artifacts(tmp_path / "reordered-campaign")
    campaign = generate_p176_campaign()
    campaign["episodes"] = list(reversed(campaign["episodes"]))
    campaign["campaign_hash"] = stable_hash({key: value for key, value in campaign.items() if key != "campaign_hash"})
    producer = _producer(plan_paths=plan_paths, campaign=campaign)

    with pytest.raises(P176RuntimeBridgeError, match="canonical_campaign_order_invalid"):
        producer.produce(tmp_path / "reordered-campaign", now=TRUSTED_NOW)


def test_runtime_producer_fails_closed_on_non_harness_mutation(tmp_path: Path) -> None:
    plan_paths = _write_plan_artifacts(tmp_path / "wrong-principal")
    producer = _producer(plan_paths=plan_paths, fault_harness=FakeFaultHarness(mutation_principal="opscat-writer@example.test"))

    with pytest.raises(P176RuntimeBridgeError, match="mutation_principal_not_harness"):
        producer.produce(tmp_path / "wrong-principal", now=TRUSTED_NOW)


def test_runtime_producer_fails_closed_on_unbound_cleanup_proof(tmp_path: Path) -> None:
    plan_paths = _write_plan_artifacts(tmp_path / "bad-proof")
    producer = _producer(plan_paths=plan_paths, fault_harness=FakeFaultHarness(bad_cleanup_proof=True))

    with pytest.raises(P176RuntimeBridgeError, match="cleanup_receipt_hash_not_bound"):
        producer.produce(tmp_path / "bad-proof", now=TRUSTED_NOW)


def test_runtime_producer_fails_closed_on_unredacted_agent_visible_evidence(tmp_path: Path) -> None:
    plan_paths = _write_plan_artifacts(tmp_path / "leaky-evidence")
    producer = _producer(plan_paths=plan_paths, evidence_provider=FakeEvidenceProvider(agent_summary={"truth": "leaked"}))

    with pytest.raises(P176RuntimeBridgeError, match="evidence_record_invalid:agent_visible"):
        producer.produce(tmp_path / "leaky-evidence", now=TRUSTED_NOW)


def test_runtime_producer_fails_closed_on_stale_billing(tmp_path: Path) -> None:
    plan_paths = _write_plan_artifacts(tmp_path / "stale-billing")
    producer = _producer(
        plan_paths=plan_paths,
        billing_provider=FakeBillingProvider(latest_poll_at=TRUSTED_NOW - timedelta(minutes=30)),
    )

    with pytest.raises(P176RuntimeBridgeError, match="billing_report_invalid:billing_poll_stale"):
        producer.produce(tmp_path / "stale-billing", now=TRUSTED_NOW)


def test_runtime_producer_fails_closed_on_live_safety_counter(tmp_path: Path) -> None:
    plan_paths = _write_plan_artifacts(tmp_path / "unsafe")
    producer = _producer(plan_paths=plan_paths, safety_monitor=FakeSafetyMonitor({"deadman_missed_count": 1}))

    with pytest.raises(P176RuntimeBridgeError, match="live_safety_counter_nonzero"):
        producer.produce(tmp_path / "unsafe", now=TRUSTED_NOW)


def _producer(
    *,
    plan_paths: dict[str, Path],
    evidence_provider: EvidenceProvider | None = None,
    fault_harness: FaultHarness | None = None,
    healthy_observer: HealthyObserver | None = None,
    billing_provider: Any | None = None,
    teardown_provider: Any | None = None,
    safety_monitor: Any | None = None,
    campaign: dict[str, Any] | None = None,
) -> P176RuntimeArtifactProducer:
    project_id = "opscat-p176-live-test01"
    billing_account_id = "ABCDEF-123456-789ABC"
    config = P176RuntimeConfig(
        run_id="p176-live-runtime-test",
        project_id=project_id,
        p174_control_clone_hash=stable_hash("p174-control"),
        reviewed_apply_plan_hash=file_hash(plan_paths["lab_apply"]),
        reviewed_teardown_plan_hash=file_hash(plan_paths["lab_destroy"]),
        reviewed_cost_cutoff_apply_plan_hash=file_hash(plan_paths["cost_cutoff_apply"]),
        reviewed_cost_cutoff_destroy_plan_hash=file_hash(plan_paths["cost_cutoff_destroy"]),
        billing_account_id=billing_account_id,
        budget_resource_name=f"billingAccounts/{billing_account_id}/budgets/p176-live-runtime-test",
        observer_principal=f"p176-live-observer@{project_id}.iam.gserviceaccount.com",
        harness_fault_principal=f"p176-live-harness-fault@{project_id}.iam.gserviceaccount.com",
        opscat_principal=f"opscat-readonly@{project_id}.iam.gserviceaccount.com",
    )
    resolved_evidence_provider = evidence_provider or FakeEvidenceProvider()
    resolved_fault_harness = fault_harness or FakeFaultHarness(evidence_provider=resolved_evidence_provider)
    if isinstance(resolved_fault_harness, FakeFaultHarness) and resolved_fault_harness.evidence_provider is None:
        resolved_fault_harness.evidence_provider = resolved_evidence_provider
    return P176RuntimeArtifactProducer(
        config=config,
        evidence_provider=resolved_evidence_provider,
        fault_harness=resolved_fault_harness,
        healthy_observer=healthy_observer or FakeHealthyObserver(),
        billing_provider=billing_provider or FakeBillingProvider(),
        teardown_provider=teardown_provider or FakeTeardownProvider(config.reviewed_apply_plan_hash),
        safety_monitor=safety_monitor or FakeSafetyMonitor(),
        campaign=campaign,
    )


def _write_plan_artifacts(run_dir: Path) -> dict[str, Path]:
    run_dir.mkdir(parents=True)
    paths = {
        "lab_apply": run_dir / "p176-live.tfplan.json",
        "lab_destroy": run_dir / "p176-live-destroy.tfplan",
        "cost_cutoff_apply": run_dir / "p176-cost-cutoff.tfplan.json",
        "cost_cutoff_destroy": run_dir / "p176-cost-cutoff-destroy.tfplan",
    }
    paths["lab_apply"].write_bytes(b'{"format_version":"1.2","resource_changes":[]}\n')
    paths["lab_destroy"].write_bytes(b"terraform lab destroy binary plan receipt")
    paths["cost_cutoff_apply"].write_bytes(b'{"format_version":"1.2","cost_cutoff_resource_changes":[]}\n')
    paths["cost_cutoff_destroy"].write_bytes(b"terraform cost cutoff destroy binary plan receipt")
    return paths


@dataclass
class FakeEvidenceProvider:
    agent_summary: dict[str, Any] | None = None

    def collect(self, *, ledger_name: str, source_class: str) -> EvidenceSnapshot:
        summary = self.agent_summary if ledger_name == "agent_visible" and self.agent_summary is not None else {"signal": f"redacted_{source_class}"}
        return EvidenceSnapshot(
            observed_at="2026-07-18T00:00:00Z",
            received_at="2026-07-18T00:00:30Z",
            freshness_bound_seconds=300,
            content_hash=stable_hash(f"content:{ledger_name}:{source_class}"),
            redaction_receipt_hash=stable_hash(f"redaction:{ledger_name}:{source_class}"),
            summary=summary,
            evaluator_context_hash=stable_hash(f"sealed:{source_class}") if ledger_name == "evaluator_only" else None,
        )


@dataclass
class FakeFaultHarness:
    duplicate_lease: bool = False
    bad_cleanup_proof: bool = False
    mutation_principal: str | None = None
    wrong_diagnosis: bool = False
    evidence_provider: Any | None = None

    def execute_fault(self, *, episode: Mapping[str, Any], fault_verb: str, harness_principal: str) -> FaultExecution:
        lease_id = "lease-reused" if self.duplicate_lease else f"lease-{episode['episode_id']}"
        source_classes = EPISODE_EVIDENCE_SOURCE_CLASSES[episode["primary_layer"]]
        provider = self.evidence_provider or FakeEvidenceProvider()
        agent_evidence = {
            source_class: provider.collect(ledger_name="agent_visible", source_class=source_class)
            for source_class in source_classes
        }
        evaluator_evidence = {
            source_class: provider.collect(ledger_name="evaluator_only", source_class=source_class)
            for source_class in source_classes
        }
        cleanup_hash = stable_hash("wrong-cleanup") if self.bad_cleanup_proof else fault_proof_hash(
            run_id="p176-live-runtime-test",
            episode_id=episode["episode_id"],
            fault_lease_id=lease_id,
            proof_type="cleanup_receipt",
        )
        return FaultExecution(
            fault_lease_id=lease_id,
            mutation_principal=self.mutation_principal or harness_principal,
            mutation_executed=False,
            incident_detected=True,
            diagnosed_family_id="p176-family-30-webhook_delivery_delay"
            if self.wrong_diagnosis
            else episode["family_id"],
            routed_service_id=episode["service_id"],
            recovery_observed=True,
            residual_effect_count=0,
            evidence_citations=tuple(snapshot.content_hash for snapshot in agent_evidence.values()),
            human_required=True,
            deadman_receipt_hash=fault_proof_hash(
                run_id="p176-live-runtime-test",
                episode_id=episode["episode_id"],
                fault_lease_id=lease_id,
                proof_type="deadman_receipt",
            ),
            cleanup_receipt_hash=cleanup_hash,
            residual_effect_proof_hash=fault_proof_hash(
                run_id="p176-live-runtime-test",
                episode_id=episode["episode_id"],
                fault_lease_id=lease_id,
                proof_type="residual_effect_proof",
            ),
            agent_evidence=agent_evidence,
            evaluator_evidence=evaluator_evidence,
        )


@dataclass
class CrashingFaultHarness:
    call_count: int = 0

    def execute_fault(self, *, episode: Mapping[str, Any], fault_verb: str, harness_principal: str) -> FaultExecution:
        self.call_count += 1
        raise RuntimeError("simulated harness crash")


@dataclass
class CountingFaultHarness:
    call_count: int = 0
    delegate: FakeFaultHarness | None = None

    def execute_fault(self, *, episode: Mapping[str, Any], fault_verb: str, harness_principal: str) -> FaultExecution:
        self.call_count += 1
        delegate = self.delegate or FakeFaultHarness()
        return delegate.execute_fault(
            episode=episode,
            fault_verb=fault_verb,
            harness_principal=harness_principal,
        )


@dataclass
class FailingAfterFaultHarness:
    fail_at: int
    call_count: int = 0

    def execute_fault(self, *, episode: Mapping[str, Any], fault_verb: str, harness_principal: str) -> FaultExecution:
        self.call_count += 1
        if self.call_count == self.fail_at:
            raise RuntimeError("simulated diagnosis provider failure")
        return FakeFaultHarness().execute_fault(
            episode=episode,
            fault_verb=fault_verb,
            harness_principal=harness_principal,
        )


@dataclass
class BadProofAfterFaultHarness:
    fail_at: int
    call_count: int = 0

    def execute_fault(self, *, episode: Mapping[str, Any], fault_verb: str, harness_principal: str) -> FaultExecution:
        self.call_count += 1
        return FakeFaultHarness(bad_cleanup_proof=self.call_count == self.fail_at).execute_fault(
            episode=episode,
            fault_verb=fault_verb,
            harness_principal=harness_principal,
        )


class FakeHealthyObserver:
    def observe_window(self, *, window: Mapping[str, Any]) -> HealthyObservation:
        return HealthyObservation(false_alert=False, false_action=False)


class CrashingHealthyObserver:
    def observe_window(self, *, window: Mapping[str, Any]) -> HealthyObservation:
        raise RuntimeError("simulated healthy observer crash")


@dataclass
class FailingAfterHealthyObserver:
    fail_at: int
    call_count: int = 0

    def observe_window(self, *, window: Mapping[str, Any]) -> HealthyObservation:
        self.call_count += 1
        if self.call_count == self.fail_at:
            raise RuntimeError("simulated healthy provider failure")
        return HealthyObservation(false_alert=False, false_action=False)


@dataclass
class CountingHealthyObserver:
    call_count: int = 0

    def observe_window(self, *, window: Mapping[str, Any]) -> HealthyObservation:
        self.call_count += 1
        return HealthyObservation(false_alert=False, false_action=False)


@dataclass
class FakeBillingProvider:
    latest_poll_at: datetime = TRUSTED_NOW - timedelta(minutes=5)

    def latest_billing(self) -> BillingSnapshot:
        return BillingSnapshot(
            latest_poll_at=_to_z(self.latest_poll_at),
            latest_actual_cost_krw=10_000,
            latest_forecast_cost_krw=12_000,
            provider_response_hash=stable_hash("gcp-billing-response"),
            poll_count=12,
        )


@dataclass
class CountingBillingProvider:
    fail_if_called: bool = False
    call_count: int = 0

    def latest_billing(self) -> BillingSnapshot:
        self.call_count += 1
        if self.fail_if_called:
            raise AssertionError("billing provider must not run during collection")
        return FakeBillingProvider().latest_billing()


@dataclass
class FakeTeardownProvider:
    reviewed_apply_plan_hash: str

    def teardown_proof(self) -> TeardownSnapshot:
        return TeardownSnapshot(
            reviewed_apply_started_at=_to_z(TRUSTED_NOW - timedelta(hours=25)),
            collection_started_at=_to_z(TRUSTED_NOW - timedelta(hours=25)),
            collection_completed_at=_to_z(TRUSTED_NOW),
            terminal_stop_at=_to_z(TRUSTED_NOW),
            teardown_started_at=_to_z(TRUSTED_NOW + timedelta(minutes=45)),
            teardown_completed_at=_to_z(TRUSTED_NOW + timedelta(minutes=55)),
            concurrency_plan_proven=False,
            remaining_non_billing_resource_count=0,
            residual_effect_count=0,
            final_cost_snapshot_hash=stable_hash("final-cost"),
        )


@dataclass
class CountingTeardownProvider:
    reviewed_apply_plan_hash: str
    fail_if_called: bool = False
    call_count: int = 0

    def teardown_proof(self) -> TeardownSnapshot:
        self.call_count += 1
        if self.fail_if_called:
            raise AssertionError("teardown provider must not run during collection")
        return FakeTeardownProvider(self.reviewed_apply_plan_hash).teardown_proof()


@dataclass
class FakeSafetyMonitor:
    overrides: dict[str, int] | None = None

    def live_safety(self) -> dict[str, int]:
        counters = {key: 0 for key in LIVE_SAFETY_KEYS}
        counters.update(self.overrides or {})
        return counters


def _to_z(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")
