from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Protocol

import pytest

from app.services.p147_p152_contracts import stable_hash
from app.services.p164_p168_disposable_operator_program import (
    BoundedAutoApprovalPolicy,
    DisposableTelemetryClient,
    DisposableTelemetryLab,
    DisposableTelemetryLabServer,
    DurableShadowOperator,
    ProgramError,
    ReversibleLabActionController,
    SealedPerformanceEvaluator,
    UnattendedSoakRunner,
    assemble_release_evidence,
    build_final_review,
    build_freeze_manifest,
    evaluate_p164,
    evaluate_p165,
    evaluate_p166,
    evaluate_p167,
    evaluate_p168,
    load_phase_input,
    validate_evaluation,
    validate_release_evidence,
)

ROOT = Path(__file__).resolve().parents[1]


class PhaseEvaluator(Protocol):
    def __call__(
        self,
        payload: dict[str, Any],
        predecessor: dict[str, Any],
        *,
        project_root: Path,
    ) -> dict[str, Any]: ...


def _input(phase: str) -> dict[str, Any]:
    return load_phase_input(ROOT / f"evals/{phase}/input/cases.json", phase)


def _predecessor(phase: str) -> dict[str, Any]:
    previous = f"p{int(phase[1:]) - 1}"
    return load_phase_input(ROOT / f"evals/{previous}/output/release-evidence.json", f"{previous}-release")


def test_p164_provider_shaped_numeric_loopback_telemetry_and_redaction() -> None:
    lab = DisposableTelemetryLab(approval_capability="test-capability")
    with DisposableTelemetryLabServer(lab) as server:
        client = DisposableTelemetryClient(server.base_url)
        baseline = client.read_bundle()
        assert baseline["metrics"]["status"] == "success"
        assert baseline["logs"]["status"] == "success"
        assert baseline["traces"]["data"][0]["service"] == "checkout"
        assert set(baseline) == {"metrics", "logs", "traces", "deploys", "health", "topology"}

        lab.set_stage("db_pool_exhaustion", "precursor", observed_at="2026-07-17T00:00:00Z")
        precursor = client.read_bundle()
        assert precursor["metrics"]["data"]["result"][0]["metric"]["stage"] == "precursor"
        assert precursor["health"]["healthy"] is True

        lab.set_stage("db_pool_exhaustion", "incident", observed_at="2026-07-17T00:01:00Z")
        incident = client.read_bundle()
        assert incident["health"]["healthy"] is False
        assert "secret-token" not in str(incident)
        assert "hunter2" not in str(incident)
        assert "Bearer opscat-auth" not in str(incident)
        assert "opscat-api-key" not in str(incident)
        assert str(incident["logs"]).count("[REDACTED]") >= 4

    with pytest.raises(ProgramError, match="loopback"):
        DisposableTelemetryClient("http://localhost:9000")
    with pytest.raises(ProgramError, match="endpoint"):
        DisposableTelemetryClient("http://127.0.0.1:9").get("/unknown")


def test_p165_durable_shadow_resumes_exactly_once_and_detects_tampering(tmp_path: Path) -> None:
    lab = DisposableTelemetryLab(approval_capability="shadow-capability")
    with DisposableTelemetryLabServer(lab) as server:
        client = DisposableTelemetryClient(server.base_url)
        shadow = DurableShadowOperator(tmp_path, max_age_seconds=30, deadman_seconds=60)
        first = shadow.observe(client, cursor=1, now="2026-07-17T00:00:05Z")
        assert first["status"] == "healthy"
        with pytest.raises(ProgramError, match="cursor"):
            shadow.observe(client, cursor=1, now="2026-07-17T00:00:06Z")

        lab.set_stage("queue_backlog", "incident", observed_at="2026-07-17T00:00:10Z")
        restarted = DurableShadowOperator(tmp_path, max_age_seconds=30, deadman_seconds=60)
        second = restarted.observe(client, cursor=2, now="2026-07-17T00:00:15Z")
        assert second["status"] == "incident"
        assert restarted.verify_ledger()["entry_count"] == 2
        checkpoint = load_phase_input(tmp_path / "shadow-checkpoint.json", "p165-checkpoint")
        assert checkpoint["last_cursor"] == 2
        assert checkpoint["ledger_head"] == second["entry_hash"]
        assert restarted.deadman_status(now="2026-07-17T00:02:00Z") == "deadman_expired"

    ledger = tmp_path / "shadow-ledger.jsonl"
    original = ledger.read_text(encoding="utf-8")
    ledger.write_text(original.replace('"cursor":1', '"cursor":9', 1), encoding="utf-8")
    with pytest.raises(ProgramError, match="ledger"):
        DurableShadowOperator(tmp_path).verify_ledger()


def test_p165_malformed_telemetry_is_not_masked_as_connector_unavailable(tmp_path: Path) -> None:
    class MalformedTelemetryClient:
        def read_bundle(self) -> dict[str, Any]:
            return {"health": {"observed_at": "not-a-timestamp", "stage": "healthy"}}

    with pytest.raises(ProgramError, match="timestamp"):
        DurableShadowOperator(tmp_path).observe(
            MalformedTelemetryClient(),
            cursor=1,
            now="2026-07-17T00:00:05Z",
        )


def test_p166_truth_sealed_evaluation_is_recomputable_and_leakage_safe() -> None:
    cases = _input("p166")["cases"]
    evaluator = SealedPerformanceEvaluator()
    result = evaluator.evaluate(cases)
    assert result["metrics"]["precursor_recall"] >= 0.80
    assert result["metrics"]["false_positive_rate"] <= 0.05
    assert result["metrics"]["root_cause_top3_accuracy"] == 1.0
    assert result["metrics"]["root_cause_top1_accuracy"] == 1.0
    assert result["metrics"]["citation_validity_rate"] == 1.0
    assert result["metrics"]["median_precursor_lead_seconds"] >= 180
    assert result["metrics"]["abstention_accuracy"] == 1.0
    assert all(row["prediction_committed_at"] < row["truth_opened_at"] for row in result["rows"])
    assert all(row["prediction_hash"] == stable_hash(row["prediction"]) for row in result["rows"])
    assert validate_evaluation(result, cases)["evaluation_hash"] == result["evaluation_hash"]

    tampered = deepcopy(result)
    tampered["metrics"]["false_positive_rate"] = 0.9
    with pytest.raises(ProgramError, match="evaluation"):
        validate_evaluation(tampered, cases)

    leaked = deepcopy(cases[0])
    leaked["evidence"][0]["outcome"] = "db_pool_exhaustion"
    with pytest.raises(ProgramError, match="future"):
        evaluator.evaluate([leaked])


def test_p167_policy_is_evidence_bound_fixed_and_rollback_closed() -> None:
    capability = "p167-capability"
    lab = DisposableTelemetryLab(approval_capability=capability)
    policy = BoundedAutoApprovalPolicy(approval_capability=capability)
    with DisposableTelemetryLabServer(lab) as server:
        client = DisposableTelemetryClient(server.base_url)
        controller = ReversibleLabActionController(client, approval_capability=capability)
        lab.set_stage("db_pool_exhaustion", "incident", observed_at="2026-07-17T00:00:00Z")
        request = {
            "request_id": "p167-ok",
            "root_cause": "db_pool_exhaustion",
            "citations": ["metric:pool_wait", "log:pool_timeout"],
            "confidence": 0.95,
            "fresh": True,
            "heartbeat_current": True,
            "observed_age_seconds": 5,
            "heartbeat_age_seconds": 5,
            "deadman_active": True,
            "kill_switch": False,
            "target": "disposable-lab",
            "issued_at": "2026-07-17T00:00:05Z",
        }
        decision = policy.decide(request)
        assert decision["status"] == "approved"
        assert decision["evidence_hash"] == stable_hash(request["citations"])
        assert decision["issued_at"] == request["issued_at"]
        assert decision["expires_at"] == "2026-07-17T00:00:35Z"
        recovered = controller.execute(decision, request_id="p167-ok", now="2026-07-17T00:00:06Z")
        assert recovered["outcome"] == "recovery_verified"
        assert recovered["postcheck"]["health"]["observed_at"] > "2026-07-17T00:00:00Z"
        assert controller.execute(decision, request_id="p167-ok", now="2026-07-17T00:00:07Z") == recovered

        with pytest.raises(ProgramError, match="request"):
            controller.execute(decision, request_id="p167-replay", now="2026-07-17T00:00:07Z")
        assert controller.execute(decision, request_id="p167-ok", now="2026-07-17T00:00:36Z") == recovered
        replay_with_changed_decision = policy.decide({**request, "issued_at": "2026-07-17T00:00:07Z"})
        with pytest.raises(ProgramError, match="idempotency_content_mismatch"):
            controller.execute(replay_with_changed_decision, request_id="p167-ok", now="2026-07-17T00:00:08Z")

        missing_liveness = {key: value for key, value in request.items() if key != "deadman_active"}
        with pytest.raises(ProgramError, match="required"):
            policy.decide(missing_liveness)

        denied = policy.decide({**request, "kill_switch": True})
        assert denied["status"] == "denied"
        with pytest.raises(ProgramError, match="approval"):
            controller.execute(denied, request_id="p167-denied", now="2026-07-17T00:00:06Z")
        assert policy.decide({**request, "observed_age_seconds": 31})["status"] == "denied"
        assert policy.decide({**request, "heartbeat_age_seconds": 61})["status"] == "denied"
        assert policy.decide({**request, "deadman_active": False})["status"] == "denied"

        lab.set_stage("dependency_timeout", "incident", observed_at="2026-07-17T00:01:00Z")
        harmful_request = {**request, "request_id": "p167-harm", "issued_at": "2026-07-17T00:01:05Z"}
        harmful = controller.execute(
            policy.decide(harmful_request),
            request_id="p167-harm",
            now="2026-07-17T00:01:06Z",
        )
        assert harmful["outcome"] == "rollback_verified"
        assert harmful["rolled_back"] is True

        forged = deepcopy(decision)
        forged["action"] = "rollback_canary"
        with pytest.raises(ProgramError, match="approval"):
            controller.execute(forged, request_id="p167-ok", now="2026-07-17T00:00:06Z")


def test_p168_accelerated_unattended_soak_closes_every_effect(tmp_path: Path) -> None:
    capability = "p168-capability"
    lab = DisposableTelemetryLab(approval_capability=capability)
    policy = BoundedAutoApprovalPolicy(approval_capability=capability)
    with DisposableTelemetryLabServer(lab) as server:
        client = DisposableTelemetryClient(server.base_url)
        controller = ReversibleLabActionController(client, approval_capability=capability)
        runner = UnattendedSoakRunner(
            lab,
            client,
            policy,
            controller,
            state_dir=tmp_path,
        )
        summary = runner.run(cycle_count=120, restart_after_cycle=60)

    assert summary["cycle_count"] == 120
    assert summary["healthy_cycle_count"] == 72
    assert summary["precursor_cycle_count"] == 18
    assert summary["incident_cycle_count"] == 30
    assert summary["false_action_on_healthy_count"] == 0
    assert summary["duplicate_action_count"] == 0
    assert summary["deadman_escape_count"] == 0
    assert summary["unresolved_effect_count"] == 0
    assert summary["ledger_complete"] is True
    assert summary["restart_resume_verified"] is True
    assert summary["kill_switch_drill_count"] == 2
    assert summary["deadman_drill_count"] == 2
    assert summary["harmful_action_drill_count"] == 2
    assert summary["ledger_hash"].startswith("sha256:")
    assert summary["resource_limits_passed"] is True
    assert summary["wall_clock_24h_completed"] is False
    assert summary["human_approval_count"] == 0


@pytest.mark.parametrize(
    ("phase", "evaluator"),
    [
        ("p164", evaluate_p164),
        ("p165", evaluate_p165),
        ("p166", evaluate_p166),
        ("p167", evaluate_p167),
        ("p168", evaluate_p168),
    ],
)
def test_phase_qualification_release_contract_and_bounded_claim(
    phase: str,
    evaluator: PhaseEvaluator,
) -> None:
    report = evaluator(_input(phase), _predecessor(phase), project_root=ROOT)
    assert report["failed"] == 0
    assert report["counters"]["external_network_call_count"] == 0
    assert report["counters"]["staging_mutation_count"] == 0
    assert report["counters"]["production_mutation_count"] == 0
    assert "production_operator_replacement" in report["forbidden_claims"]
    if phase == "p164":
        assert report["counters"]["loopback_http_request_count"] == 108
    if phase == "p168":
        assert report["metrics"]["wall_clock_24h_completed"] is False
    freeze = build_freeze_manifest(phase, report, project_root=ROOT)
    offset = int(phase[1:])
    review = build_final_review(
        phase,
        report,
        freeze,
        writer_id=f"019fd{offset:03x}-0000-7000-8000-000000000001",
        reviewer_id=f"019fe{offset:03x}-0000-7000-8000-000000000002",
        reviewed_at="2026-07-17T12:00:00Z",
        decision="approved_bounded_claim",
        finding_count=0,
        reviewer_provenance="codex-native-independent-review",
        attestation_hash=stable_hash({"phase": phase, "reviewer": "independent-test-reviewer"}),
    )
    release = assemble_release_evidence(phase, report, freeze, review)
    validated = validate_release_evidence(
        phase,
        release,
        project_root=ROOT,
        report=report,
        freeze=freeze,
        review=review,
    )
    assert validated["status"] == report["status"]
    assert validated["maximum_qualified_mode"] == report["maximum_qualified_mode"]


def test_release_evidence_rejects_predecessor_and_self_hash_forgery() -> None:
    report = evaluate_p164(_input("p164"), _predecessor("p164"), project_root=ROOT)
    freeze = build_freeze_manifest("p164", report, project_root=ROOT)
    review = build_final_review(
        "p164",
        report,
        freeze,
        writer_id="019fd164-0000-7000-8000-000000000001",
        reviewer_id="019fe164-0000-7000-8000-000000000002",
        reviewed_at="2026-07-17T12:00:00Z",
        decision="approved_bounded_claim",
        finding_count=0,
        reviewer_provenance="codex-native-independent-review",
        attestation_hash=stable_hash("p164-independent-test-review"),
    )
    release = assemble_release_evidence("p164", report, freeze, review)
    forged = deepcopy(release)
    forged["predecessor"]["evidence_hash"] = stable_hash("forged")
    with pytest.raises(ProgramError):
        validate_release_evidence("p164", forged, project_root=ROOT)


def test_release_evidence_rejects_inflated_metrics_despite_valid_self_hash() -> None:
    release = load_phase_input(ROOT / "evals/p168/output/release-evidence.json", "p168-release")
    forged = deepcopy(release)
    forged["metrics"]["wall_clock_24h_completed"] = True
    forged["metrics"]["virtual_cycle_count"] = 999_999
    forged["report_hash"] = stable_hash("forged-report")
    forged["freeze_hash"] = stable_hash("forged-freeze")
    forged["review_hash"] = stable_hash("forged-review")
    forged["evidence_hash"] = stable_hash({key: value for key, value in forged.items() if key != "evidence_hash"})
    with pytest.raises(ProgramError, match="artifact|binding"):
        validate_release_evidence("p168", forged, project_root=ROOT)


def test_shadow_ledger_append_is_fsynced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []
    real_fsync = os.fsync

    def recording_fsync(descriptor: int) -> None:
        calls.append(descriptor)
        real_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", recording_fsync)
    lab = DisposableTelemetryLab(approval_capability="durability-capability")
    with DisposableTelemetryLabServer(lab) as server:
        DurableShadowOperator(tmp_path).observe(
            DisposableTelemetryClient(server.base_url),
            cursor=1,
            now="2026-07-17T00:00:05Z",
        )
    assert len(calls) >= 3
    assert json.loads((tmp_path / "shadow-ledger.jsonl").read_text().splitlines()[0])["cursor"] == 1
