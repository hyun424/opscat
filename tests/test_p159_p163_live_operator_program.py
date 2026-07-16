from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Protocol

import pytest

from app.services.p147_p152_contracts import stable_hash
from app.services.p159_p163_live_operator_program import (
    BlindJudgmentEvaluator,
    BoundedEvidenceExpander,
    LiveObservationLoop,
    LoopbackIncidentLabServer,
    LoopbackLabClient,
    ProcessOwnedIncidentLab,
    ProgramError,
    RecordedObservationTransport,
    SupervisedLabRemediator,
    assemble_release_evidence,
    build_final_review,
    build_freeze_manifest,
    evaluate_p159,
    evaluate_p160,
    evaluate_p161,
    evaluate_p162,
    evaluate_p163,
    load_phase_input,
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


def _input(phase: str) -> dict:
    return load_phase_input(ROOT / f"evals/{phase}/input/cases.json", phase)


def _predecessor(phase: str) -> dict:
    previous = f"p{int(phase[1:]) - 1}"
    return load_phase_input(ROOT / f"evals/{previous}/output/release-evidence.json", f"{previous}-release")


def test_p159_real_loopback_lab_is_observable_and_write_capability_is_exact() -> None:
    lab = ProcessOwnedIncidentLab(approval_capability="p159-test-capability")
    with LoopbackIncidentLabServer(lab) as server:
        client = LoopbackLabClient(server.base_url)
        assert client.get("/health")["healthy"] is True
        lab.inject_fault("db_pool_exhaustion")
        assert client.get("/metrics")["pool_wait_ms"] >= 1000
        assert client.get("/logs")["entries"]
        assert client.get("/deploys")["revision"]
        with pytest.raises(ProgramError, match="approval"):
            client.post_action("tune_pool", approval_capability="wrong", request_id="p159-a1")
        receipt = client.post_action("tune_pool", approval_capability="p159-test-capability", request_id="p159-a1")
        assert receipt["status"] == "applied"
        assert client.post_action("tune_pool", approval_capability="p159-test-capability", request_id="p159-a1") == receipt

    with pytest.raises(ProgramError, match="loopback"):
        LoopbackLabClient("http://localhost:9000")


def test_p160_live_observation_distinguishes_incident_stale_failure_and_duplicates() -> None:
    transport = RecordedObservationTransport(
        {
            "/health": {"healthy": False, "generation": 2, "observed_at": "2026-07-17T00:00:00Z"},
            "/metrics": {"error_rate_bps": 4200, "latency_ms": 1800, "observed_at": "2026-07-17T00:00:00Z"},
            "/logs": {"entries": [{"id": "log-1", "message": "pool timeout"}], "observed_at": "2026-07-17T00:00:00Z"},
            "/deploys": {"revision": "r2", "observed_at": "2026-07-17T00:00:00Z"},
        }
    )
    loop = LiveObservationLoop(max_age_seconds=30)
    first = loop.observe(transport, now="2026-07-17T00:00:10Z")
    second = loop.observe(transport, now="2026-07-17T00:00:11Z")
    assert first["status"] == "service_incident"
    assert first["duplicate"] is False
    assert second["duplicate"] is True

    stale = loop.observe(transport, now="2026-07-17T00:02:00Z")
    assert stale["status"] == "telemetry_stale"
    failed = LiveObservationLoop().observe(RecordedObservationTransport({}, fail_paths={"/metrics"}), now="2026-07-17T00:00:10Z")
    assert failed["status"] == "connector_unavailable"


def test_p161_blind_evaluator_rejects_uncited_or_unsafe_model_proposals() -> None:
    evaluator = BlindJudgmentEvaluator()
    result = evaluator.evaluate_case(
        {
            "case_id": "blind-1",
            "evidence": [{"id": "m1", "signal": "pool_wait_high"}, {"id": "l1", "signal": "checkout_timeout"}],
            "truth": "db_pool_exhaustion",
            "deterministic": {"labels": ["db_pool_exhaustion"], "citations": ["m1", "l1"]},
            "model": {"labels": ["db_pool_exhaustion"], "citations": ["m1", "l1"], "safe_actions": ["tune_pool"]},
        }
    )
    assert result["evidence_commitment"] == stable_hash(
        {"case_id": "blind-1", "evidence": [{"id": "m1", "signal": "pool_wait_high"}, {"id": "l1", "signal": "checkout_timeout"}]}
    )
    assert result["hybrid"]["top1_correct"] is True

    forged = deepcopy(result["input"])
    forged["model"]["citations"] = ["missing"]
    with pytest.raises(ProgramError, match="citation"):
        evaluator.evaluate_case(forged)
    unsafe = deepcopy(result["input"])
    unsafe["model"]["safe_actions"] = ["kubectl delete pod"]
    with pytest.raises(ProgramError, match="unsafe"):
        evaluator.evaluate_case(unsafe)


def test_p162_evidence_expansion_is_read_only_budgeted_and_abstains() -> None:
    expander = BoundedEvidenceExpander(max_tool_calls=3)
    resolved = expander.investigate(
        initial_labels=["db_pool_exhaustion", "dependency_timeout"],
        plan=["metrics.query", "logs.search", "deploy.read"],
        catalog={
            "metrics.query": [{"id": "m1", "label": "db_pool_exhaustion"}],
            "logs.search": [{"id": "l1", "label": "db_pool_exhaustion"}],
            "deploy.read": [],
        },
    )
    assert resolved["outcome"] == "db_pool_exhaustion"
    assert resolved["tool_call_count"] == 2
    unresolved = expander.investigate(
        initial_labels=["db_pool_exhaustion", "dependency_timeout"],
        plan=["metrics.query", "logs.search"],
        catalog={
            "metrics.query": [{"id": "m1", "label": "db_pool_exhaustion"}],
            "logs.search": [{"id": "l1", "label": "dependency_timeout"}],
        },
    )
    assert unresolved["outcome"] == "insufficient_evidence"
    with pytest.raises(ProgramError, match="duplicate"):
        expander.investigate(initial_labels=["x"], plan=["metrics.query", "metrics.query"], catalog={})


def test_p163_supervised_remediator_verifies_recovery_and_rolls_back_harm() -> None:
    lab = ProcessOwnedIncidentLab(approval_capability="p163-test-capability")
    with LoopbackIncidentLabServer(lab) as server:
        client = LoopbackLabClient(server.base_url)
        lab.inject_fault("db_pool_exhaustion")
        remediator = SupervisedLabRemediator(client, approval_capability="p163-test-capability")
        recovered = remediator.execute("tune_pool", request_id="p163-ok")
        assert recovered["outcome"] == "recovery_verified"
        assert recovered["rolled_back"] is False

        lab.inject_fault("dependency_timeout")
        before = client.get("/health")
        rolled_back = remediator.execute("tune_pool", request_id="p163-harm")
        assert rolled_back["outcome"] == "rollback_verified"
        assert rolled_back["rolled_back"] is True
        assert client.get("/health")["generation"] >= before["generation"]


@pytest.mark.parametrize(
    ("phase", "evaluator"),
    [
        ("p159", evaluate_p159),
        ("p160", evaluate_p160),
        ("p161", evaluate_p161),
        ("p162", evaluate_p162),
        ("p163", evaluate_p163),
    ],
)
def test_phase_qualification_and_release_contracts(
    phase: str,
    evaluator: PhaseEvaluator,
) -> None:
    report = evaluator(_input(phase), _predecessor(phase), project_root=ROOT)
    assert report["failed"] == 0
    assert report["counters"]["production_mutation_count"] == 0
    assert report["counters"]["external_network_call_count"] == 0
    freeze = build_freeze_manifest(phase, report, project_root=ROOT)
    offset = int(phase[1:])
    review = build_final_review(
        phase,
        report,
        freeze,
        writer_id=f"019fb{offset:03x}-0000-7000-8000-000000000001",
        reviewer_id=f"019fc{offset:03x}-0000-7000-8000-000000000002",
        reviewed_at="2026-07-17T12:00:00Z",
    )
    release = assemble_release_evidence(phase, report, freeze, review)
    assert validate_release_evidence(phase, release, project_root=ROOT)["status"] == report["status"]
