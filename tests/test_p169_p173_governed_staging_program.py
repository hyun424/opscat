from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Protocol

import pytest

from app.services.p147_p152_contracts import stable_hash
from app.services.p169_p173_governed_staging_program import (
    SPECS,
    AttachedCapabilityRegistry,
    BlindedStagingBenchmark,
    GovernedAttachmentRecorder,
    ProgramError,
    ShadowApprovalEvaluator,
    assemble_release_evidence,
    build_final_review,
    build_freeze_manifest,
    evaluate_p169,
    evaluate_p170,
    evaluate_p171,
    evaluate_p172,
    evaluate_p173,
    load_phase_input,
    validate_release_evidence,
    validate_report,
    validate_wall_clock_soak,
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


def _attachment_events(*, real_network: bool) -> list[dict[str, Any]]:
    providers = (("prometheus", "metrics"), ("loki", "logs"), ("sentry", "errors"))
    return [
        {
            "request_id": f"read-{index}",
            "source_id": f"source-{provider}",
            "provider": provider,
            "source_class": source_class,
            "observed_at": "2026-07-17T00:00:00Z",
            "collected_at": f"2026-07-17T00:00:0{index}Z",
            "method": "GET",
            "scheme": "https",
            "host": f"{provider}.staging.example.com",
            "path": "/api/v1/query",
            "timeout_seconds": 5,
            "response_bytes": 1024,
            "redirect_count": 0,
            "credential_ref": "env:OPSCAT_STAGING_TOKEN",
            "response_hash": "sha256:" + str(index) * 64,
            "redaction_applied": True,
            "real_network": real_network,
        }
        for index, (provider, source_class) in enumerate(providers, start=1)
    ]


def _benchmark_artifacts() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    truths: list[dict[str, Any]] = []
    for index in range(30):
        root = ("db_pool_exhaustion", "queue_backlog", "recent_deploy_regression")[index % 3]
        evidence = [
            {"id": f"incident-{index}-metric", "source_class": "metrics"},
            {"id": f"incident-{index}-log", "source_class": "logs"},
        ]
        cases.append(
            {
                "case_id": f"incident-{index}",
                "prediction": {
                    "incident": True,
                    "root_cause_top3": [root, "dependency_timeout", "retry_storm"],
                    "citations": [item["id"] for item in evidence],
                    "precursor": True,
                },
                "evidence": evidence,
            }
        )
        truths.append({"case_id": f"incident-{index}", "incident": True, "root_cause": root})
    for index in range(300):
        evidence = [{"id": f"healthy-{index}-health", "source_class": "health"}]
        cases.append(
            {
                "case_id": f"healthy-{index}",
                "prediction": {
                    "incident": False,
                    "root_cause_top3": [],
                    "citations": [evidence[0]["id"]],
                    "precursor": False,
                },
                "evidence": evidence,
            }
        )
        truths.append({"case_id": f"healthy-{index}", "incident": False, "root_cause": "none"})
    predictions = {
        "schema_version": "p171.predictions.v1",
        "benchmark_id": "p171-test-benchmark",
        "committed_at": "2026-07-17T00:00:00Z",
        "cases": cases,
        "artifact_hash": "",
    }
    predictions["artifact_hash"] = stable_hash({key: value for key, value in predictions.items() if key != "artifact_hash"})
    sealed_truth = {
        "schema_version": "p171.sealed_truth.v1",
        "benchmark_id": "p171-test-benchmark",
        "sealed_at": "2026-07-16T23:55:00Z",
        "opened_at": "2026-07-17T00:05:00Z",
        "cases": truths,
        "artifact_hash": "",
    }
    sealed_truth["artifact_hash"] = stable_hash({key: value for key, value in sealed_truth.items() if key != "artifact_hash"})
    gates = {
        "minimum_incident_cases": 30,
        "minimum_healthy_windows": 300,
        "minimum_top1_accuracy": 0.80,
        "minimum_top3_recall": 0.95,
        "minimum_precursor_recall": 0.80,
        "maximum_false_alert_rate": 0.0,
        "maximum_false_alert_95pct_upper": 0.01,
        "minimum_citation_validity_rate": 1.0,
    }
    preregistration = {
        "schema_version": "p171.preregistration.v1",
        "benchmark_id": "p171-test-benchmark",
        "committed_at": "2026-07-16T23:59:00Z",
        "gates": gates,
        "prediction_artifact_hash": predictions["artifact_hash"],
        "truth_case_ids_hash": stable_hash(sorted(item["case_id"] for item in truths)),
        "self_hash": "",
    }
    preregistration["self_hash"] = stable_hash({key: value for key, value in preregistration.items() if key != "self_hash"})
    return preregistration, predictions, sealed_truth


def test_p169_attachment_receipts_are_hash_chained_and_claims_are_honest() -> None:
    recorded = GovernedAttachmentRecorder(
        mode="recorded",
        target_owner_approval=False,
        live_ack=False,
        credential_ref="env:OPSCAT_STAGING_TOKEN",
    )
    receipts = [recorded.record(event) for event in _attachment_events(real_network=False)]
    summary = recorded.summary()
    assert summary["receipt_count"] == 3
    assert summary["provider_count"] == 3
    assert summary["source_class_count"] == 3
    assert summary["real_network_call_count"] == 0
    assert summary["live_attachment_observed"] is False
    assert summary["maximum_claim"] == "governed_read_only_staging_attachment_ready_not_observed"
    assert receipts[0]["previous_receipt_hash"] == "sha256:" + "0" * 64
    assert receipts[1]["previous_receipt_hash"] == receipts[0]["receipt_hash"]
    assert all("response_body" not in receipt for receipt in receipts)
    assert all(receipt["method"] == "GET" for receipt in receipts)
    assert all(receipt["scheme"] == "https" for receipt in receipts)
    assert all(receipt["redirect_count"] == 0 for receipt in receipts)

    forged_transport = deepcopy(_attachment_events(real_network=False)[0])
    forged_transport["method"] = "POST"
    with pytest.raises(ProgramError, match="method"):
        recorded.record(forged_transport)

    forged_transport = deepcopy(_attachment_events(real_network=False)[0])
    forged_transport["host"] = "attacker.example.com"
    with pytest.raises(ProgramError, match="host"):
        recorded.record(forged_transport)

    with pytest.raises(ProgramError, match="approval"):
        GovernedAttachmentRecorder(mode="live", target_owner_approval=False, live_ack=True, credential_ref="env:OPSCAT_TOKEN")
    with pytest.raises(ProgramError, match="credential"):
        GovernedAttachmentRecorder(mode="live", target_owner_approval=True, live_ack=True, credential_ref="raw-secret")

    live = GovernedAttachmentRecorder(
        mode="live",
        target_owner_approval=True,
        live_ack=True,
        credential_ref="env:OPSCAT_STAGING_TOKEN",
    )
    for event in _attachment_events(real_network=True):
        live.record(event)
    assert live.summary()["live_attachment_observed"] is True

    forged = deepcopy(receipts[1])
    forged["provider"] = "unknown"
    with pytest.raises(ProgramError, match="receipt"):
        recorded.validate_receipts([receipts[0], forged, receipts[2]])


def test_p170_wall_clock_evidence_separates_test_readiness_from_real_24h() -> None:
    short = {
        "started_at": "2026-07-17T00:00:00Z",
        "ended_at": "2026-07-17T00:01:00Z",
        "frozen_poll_interval_seconds": 10,
        "expected_poll_count": 6,
        "successful_poll_count": 6,
        "failed_poll_count": 0,
        "segments": [
            {
                "session_id": "session-a",
                "boot_id": "boot-a",
                "started_monotonic_ns": 1_000_000_000,
                "ended_monotonic_ns": 61_000_000_000,
                "poll_count": 6,
            }
        ],
        "wall_clock_24h_completed": False,
        "restart_resume_verified": False,
        "duplicate_evidence_count": 0,
    }
    validated = validate_wall_clock_soak(short, require_live_24h=False)
    assert validated["elapsed_seconds"] == 60
    assert validated["polling_success_rate"] == 1.0
    assert validated["wall_clock_24h_completed"] is False

    forged = deepcopy(short)
    forged["wall_clock_24h_completed"] = True
    with pytest.raises(ProgramError, match="24h"):
        validate_wall_clock_soak(forged, require_live_24h=False)

    full = deepcopy(short)
    full.update(
        {
            "ended_at": "2026-07-18T00:00:00Z",
            "expected_poll_count": 8_640,
            "successful_poll_count": 8_640,
            "wall_clock_24h_completed": True,
            "restart_resume_verified": True,
            "segments": [
                {
                    "session_id": "session-a",
                    "boot_id": "boot-a",
                    "started_monotonic_ns": 1_000_000_000,
                    "ended_monotonic_ns": 43_201_000_000_000,
                    "poll_count": 4_320,
                },
                {
                    "session_id": "session-b",
                    "boot_id": "boot-b",
                    "started_monotonic_ns": 2_000_000_000,
                    "ended_monotonic_ns": 43_202_000_000_000,
                    "poll_count": 4_320,
                },
            ],
        }
    )
    assert validate_wall_clock_soak(full, require_live_24h=True)["wall_clock_24h_completed"] is True


def test_p171_blinded_benchmark_reports_denominators_and_confidence_bound() -> None:
    preregistration, predictions, sealed_truth = _benchmark_artifacts()
    result = BlindedStagingBenchmark().evaluate(
        preregistration=preregistration,
        predictions=predictions,
        sealed_truth=sealed_truth,
    )
    metrics = result["metrics"]
    assert metrics["incident_case_count"] == 30
    assert metrics["healthy_window_count"] == 300
    assert metrics["root_cause_top1_accuracy"] == 1.0
    assert metrics["root_cause_top3_recall"] == 1.0
    assert metrics["precursor_recall"] == 1.0
    assert metrics["false_alert_rate"] == 0.0
    assert metrics["false_alert_rate_95pct_upper"] <= 0.01
    assert metrics["citation_validity_rate"] == 1.0
    assert result["confidence_bound_qualified"] is True
    assert set(result["per_family"]) == {"db_pool_exhaustion", "queue_backlog", "recent_deploy_regression"}

    under_preregistration, under_predictions, under_truth = _benchmark_artifacts()
    under_predictions["cases"] = under_predictions["cases"][:230]
    under_predictions["artifact_hash"] = stable_hash(
        {key: value for key, value in under_predictions.items() if key != "artifact_hash"}
    )
    under_truth["cases"] = under_truth["cases"][:230]
    under_truth["artifact_hash"] = stable_hash({key: value for key, value in under_truth.items() if key != "artifact_hash"})
    under_preregistration["prediction_artifact_hash"] = under_predictions["artifact_hash"]
    under_preregistration["truth_case_ids_hash"] = stable_hash(sorted(item["case_id"] for item in under_truth["cases"]))
    under_preregistration["self_hash"] = stable_hash(
        {key: value for key, value in under_preregistration.items() if key != "self_hash"}
    )
    underpowered = BlindedStagingBenchmark().evaluate(
        preregistration=under_preregistration,
        predictions=under_predictions,
        sealed_truth=under_truth,
    )
    assert underpowered["confidence_bound_qualified"] is False
    assert underpowered["qualification"] == "informational_point_estimate_only"

    leaked_preregistration, leaked_predictions, leaked_truth = _benchmark_artifacts()
    leaked_predictions["cases"][0]["evidence"][0]["root_cause"] = "db_pool_exhaustion"
    leaked_predictions["artifact_hash"] = stable_hash(
        {key: value for key, value in leaked_predictions.items() if key != "artifact_hash"}
    )
    leaked_preregistration["prediction_artifact_hash"] = leaked_predictions["artifact_hash"]
    leaked_preregistration["self_hash"] = stable_hash(
        {key: value for key, value in leaked_preregistration.items() if key != "self_hash"}
    )
    with pytest.raises(ProgramError, match="truth"):
        BlindedStagingBenchmark().evaluate(
            preregistration=leaked_preregistration,
            predictions=leaked_predictions,
            sealed_truth=leaked_truth,
        )

    forged_preregistration, forged_predictions, forged_truth = _benchmark_artifacts()
    forged_predictions["cases"][0]["prediction"]["root_cause_top3"][0] = "forged_after_open"
    forged_predictions["artifact_hash"] = stable_hash(
        {key: value for key, value in forged_predictions.items() if key != "artifact_hash"}
    )
    with pytest.raises(ProgramError, match="commitment"):
        BlindedStagingBenchmark().evaluate(
            preregistration=forged_preregistration,
            predictions=forged_predictions,
            sealed_truth=forged_truth,
        )


def test_p172_registry_uses_only_observed_providers_and_requires_independent_sources() -> None:
    registry = AttachedCapabilityRegistry(
        [
            {"provider": "prometheus", "source_class": "metrics", "observed": True},
            {"provider": "loki", "source_class": "logs", "observed": True},
            {"provider": "sentry", "source_class": "errors", "observed": False},
        ],
        max_tool_calls=8,
    )
    assert registry.available_tools() == ("loki.logs.read", "prometheus.metrics.read")
    decision = registry.evaluate(
        tool_calls=["prometheus.metrics.read", "loki.logs.read"],
        evidence=[
            {"id": "metric-1", "provider": "prometheus", "source_class": "metrics", "state": "supporting", "age_seconds": 5},
            {"id": "log-1", "provider": "loki", "source_class": "logs", "state": "supporting", "age_seconds": 4},
        ],
    )
    assert decision["route"] == "evidence_sufficient"
    assert decision["independent_source_class_count"] == 2

    with pytest.raises(ProgramError, match="observed"):
        registry.evaluate(tool_calls=["sentry.errors.read"], evidence=[])
    assert registry.evaluate(
        tool_calls=["prometheus.metrics.read"],
        evidence=[{"id": "metric-1", "provider": "prometheus", "source_class": "metrics", "state": "supporting", "age_seconds": 5}],
    )["route"] == "investigate_more"
    assert registry.evaluate(
        tool_calls=["prometheus.metrics.read", "loki.logs.read"],
        evidence=[
            {"id": "metric-1", "provider": "prometheus", "source_class": "metrics", "state": "supporting", "age_seconds": 61},
            {"id": "log-1", "provider": "loki", "source_class": "logs", "state": "contradicting", "age_seconds": 2},
        ],
    )["route"] == "human_required"

    canonical = evaluate_p172(_input("p172"), _predecessor("p172"), project_root=ROOT)
    assert canonical["metrics"]["route"] == "attachment_required"
    assert canonical["metrics"]["available_tool_count"] == 0
    assert canonical["metrics"]["p169_live_attachment_observed"] is False
    assert canonical["status"] == "p172_attached_capability_registry_ready_not_observed"


def test_p173_counterfactual_policy_never_mints_approval_or_executes() -> None:
    evaluator = ShadowApprovalEvaluator()
    candidate: dict[str, Any] = {
        "request_id": "shadow-1",
        "root_cause": "db_pool_exhaustion",
        "confidence": 0.95,
        "citations": [
            {"id": "metric-1", "source_class": "metrics"},
            {"id": "log-1", "source_class": "logs"},
        ],
        "observed_age_seconds": 5,
        "heartbeat_age_seconds": 5,
        "deadman_active": True,
        "kill_switch": False,
        "target": "staging-shadow",
    }
    decision = evaluator.evaluate(candidate)
    assert decision["route"] == "would_approve_not_authorized"
    assert decision["action"] == "tune_pool"
    assert "approval_id" not in decision
    assert "capability_signature" not in decision
    assert evaluator.counters() == {
        "counterfactual_would_approve_count": 1,
        "auto_approval_count": 0,
        "human_approval_count": 0,
        "action_execution_count": 0,
        "staging_mutation_count": 0,
        "production_mutation_count": 0,
        "unsafe_action_count": 0,
    }

    assert evaluator.evaluate({**candidate, "request_id": "shadow-2", "kill_switch": True})["route"] == "blocked"
    assert evaluator.evaluate({**candidate, "request_id": "shadow-3", "citations": candidate["citations"][:1]})["route"] == "human_required"
    assert evaluator.evaluate({**candidate, "request_id": "shadow-4", "root_cause": "unknown"})["route"] == "human_required"


def test_p173_requires_complete_safety_matrix_and_reproducible_duplicate() -> None:
    report = evaluate_p173(_input("p173"), _predecessor("p173"), project_root=ROOT)
    metrics = report["metrics"]
    assert metrics["scenario_count"] == 8
    assert metrics["scenario_coverage"] == 1.0
    assert metrics["eligible_fixed_action_coverage"] >= 0.70
    assert metrics["replay_reproduction_rate"] == 1.0
    assert metrics["unsafe_or_ambiguous_approval_count"] == 0
    assert metrics["false_auto_approval_count"] == 0

    incomplete = _input("p173")
    incomplete["candidates"] = incomplete["candidates"][:-1]
    with pytest.raises(ProgramError, match="scenario_matrix"):
        evaluate_p173(incomplete, _predecessor("p173"), project_root=ROOT)

    forged_duplicate = _input("p173")
    duplicate = next(item for item in forged_duplicate["candidates"] if item["scenario"] == "duplicate")
    duplicate["replay_candidate"]["target"] = "production"
    duplicate["candidate_hash"] = stable_hash(duplicate["replay_candidate"])
    with pytest.raises(ProgramError, match="duplicate_replay_content"):
        evaluate_p173(forged_duplicate, _predecessor("p173"), project_root=ROOT)


def test_p172_release_binds_canonical_p169_secondary_dependency() -> None:
    report = evaluate_p172(_input("p172"), _predecessor("p172"), project_root=ROOT)
    with pytest.raises(ProgramError, match="project_root"):
        validate_report("p172", report)
    report["metrics"]["p169_release_hash"] = "sha256:" + "a" * 64
    report["report_hash"] = stable_hash({key: value for key, value in report.items() if key != "report_hash"})
    with pytest.raises(ProgramError, match="dependency"):
        build_freeze_manifest("p172", report, project_root=ROOT)


@pytest.mark.parametrize(
    ("phase", "evaluator"),
    [
        ("p169", evaluate_p169),
        ("p170", evaluate_p170),
        ("p171", evaluate_p171),
        ("p172", evaluate_p172),
        ("p173", evaluate_p173),
    ],
)
def test_phase_release_contract_is_ordered_source_bound_and_bounded(phase: str, evaluator: PhaseEvaluator) -> None:
    report = evaluator(_input(phase), _predecessor(phase), project_root=ROOT)
    assert report["status"] == SPECS[phase].status
    assert report["maximum_qualified_mode"] == SPECS[phase].maximum_mode
    assert report["counters"]["action_execution_count"] == 0
    assert report["counters"]["staging_mutation_count"] == 0
    assert report["counters"]["production_mutation_count"] == 0
    freeze = build_freeze_manifest(phase, report, project_root=ROOT)
    review = build_final_review(
        phase,
        report,
        freeze,
        writer_agent_id="019f6e00-0000-7000-8000-000000000001",
        reviewer_agent_id="019f6e00-0000-7000-8000-000000000002",
        reviewed_at="2026-07-17T12:00:00Z",
        project_root=ROOT,
    )
    release = assemble_release_evidence(phase, report, freeze, review, project_root=ROOT)
    assert validate_release_evidence(phase, release, project_root=ROOT)["status"] == SPECS[phase].status


def test_release_rejects_predecessor_and_claim_forgery() -> None:
    report = evaluate_p169(_input("p169"), _predecessor("p169"), project_root=ROOT)
    freeze = build_freeze_manifest("p169", report, project_root=ROOT)
    review = build_final_review(
        "p169",
        report,
        freeze,
        writer_agent_id="019f6e00-0000-7000-8000-000000000001",
        reviewer_agent_id="019f6e00-0000-7000-8000-000000000002",
        reviewed_at="2026-07-17T12:00:00Z",
        project_root=ROOT,
    )
    release = assemble_release_evidence("p169", report, freeze, review, project_root=ROOT)
    forged = deepcopy(release)
    forged["maximum_qualified_mode"] = "production_operator_replacement"
    forged["evidence_hash"] = "sha256:" + "0" * 64
    with pytest.raises(ProgramError):
        validate_release_evidence("p169", forged, project_root=ROOT)

    predecessor = _predecessor("p169")
    predecessor["evidence_hash"] = "sha256:" + "0" * 64
    with pytest.raises(ProgramError, match="predecessor"):
        evaluate_p169(_input("p169"), predecessor, project_root=ROOT)
