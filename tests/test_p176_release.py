from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p176_campaign import generate_p176_campaign
from app.services.p176_evaluator import SAFETY_COUNTER_KEYS
from app.services.p176_evidence import append_evidence_record
from app.services.p176_release import (
    LIMITATIONS,
    P176ReleaseError,
    assemble_release_evidence,
    build_readiness_artifact,
    build_release_artifacts,
    validate_final_review,
    validate_release_evidence,
)

ROOT = Path(__file__).resolve().parents[1]
SAFETY_ZERO = {key: 0 for key in SAFETY_COUNTER_KEYS}


def _outcomes() -> list[dict[str, object]]:
    return [
        {
            "episode_id": episode["episode_id"],
            "incident_detected": True,
            "diagnosis_correct": True,
            "routing_correct": True,
            "recovery_verified": True,
            "collateral_impact": False,
            "citation_supported": True,
            "human_required": True,
            "mutation_executed": False,
        }
        for episode in generate_p176_campaign()["episodes"]
    ]


def _healthy_results() -> list[dict[str, object]]:
    return [{"window_id": window["window_id"], "false_alert": False, "false_action": False} for window in generate_p176_campaign()["healthy_windows"]]


def _ledger(ledger_name: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, source_class in enumerate(
        (
            "metrics",
            "logs",
            "traces",
            "deploy_history",
            "host_state",
            "container_state",
            "topology",
            "dependency_health",
        ),
        start=1,
    ):
        record = append_evidence_record(
            previous=records[-1] if records else None,
            ledger_name=ledger_name,
            source_class=source_class,
            source_id=f"{ledger_name}/{source_class}",
            observed_at=f"2026-01-01T00:{index:02d}:00Z",
            received_at=f"2026-01-01T00:{index:02d}:30Z",
            freshness_bound_seconds=300,
            content_hash=stable_hash({"ledger": ledger_name, "seq": index}),
            redaction_receipt_hash=stable_hash({"redacted": ledger_name, "seq": index}),
            summary={"signal": f"redacted_{source_class}_bucket"},
            evaluator_context_hash=(
                stable_hash({"sealed": ledger_name, "seq": index}) if ledger_name == "evaluator_only" else None
            ),
        )
        records.append(record)
    return records


def _review(report: dict[str, Any], freeze: dict[str, Any], *, same_identity: bool = False) -> dict[str, Any]:
    review = {
        "schema_version": "p176.final_implementation_review.v1",
        "phase": "p176",
        "decision": "approve",
        "reviewed_at": "2026-07-18T09:00:00Z",
        "writer_id": "019f7486-f477-73d2-90ed-67d31911757a",
        "reviewer_id": (
            "019f7486-f477-73d2-90ed-67d31911757a"
            if same_identity
            else "019f7486-f68b-77a3-adc1-20d19eecf344"
        ),
        "reviewer_identity": "p176-independent-release-reviewer",
        "review_source": "codex_native_subagent",
        "reviewed_report_hash": report["report_hash"],
        "reviewed_freeze_manifest_hash": freeze["manifest_hash"],
        "findings": {"p0": 0, "p1": 0, "p2": 0, "p3": 0},
        "limitations": list(LIMITATIONS),
        "review_hash": "",
    }
    review["review_hash"] = stable_hash({key: value for key, value in review.items() if key != "review_hash"})
    return review


def test_no_results_readiness_never_claims_qualification() -> None:
    readiness = build_readiness_artifact(project_root=ROOT)

    assert readiness["status"] == "p176_not_executed_no_observed_outcomes"
    assert readiness["qualified"] is False
    assert readiness["maximum_claim"] == "readiness_only_not_qualification"
    assert "release-evidence" not in readiness
    assert readiness["readiness_hash"] == stable_hash({key: value for key, value in readiness.items() if key != "readiness_hash"})


def test_release_artifacts_bind_campaign_predecessor_chains_and_counters() -> None:
    artifacts = build_release_artifacts(
        project_root=ROOT,
        outcomes=_outcomes(),
        healthy_results=_healthy_results(),
        safety_counters=SAFETY_ZERO,
        agent_visible_ledger=_ledger("agent_visible"),
        evaluator_only_ledger=_ledger("evaluator_only"),
    )

    report = artifacts["report"]
    assert report["qualified"] is True
    assert report["campaign"]["campaign_hash"] == generate_p176_campaign()["campaign_hash"]
    assert report["predecessor"]["evidence_hash"].startswith("sha256:")
    assert report["safety_counters"] == SAFETY_ZERO
    assert report["evidence_chain_summaries"]["agent_visible"]["record_count"] == 8
    assert artifacts["denominator_report"]["denominators"]["fault_episode_count"] == 480
    assert artifacts["representativeness_report"]["failed_gates"] == []


def test_release_fails_closed_on_nonqualified_outcome_safety_or_chain_leak() -> None:
    bad_outcomes = _outcomes()
    bad_outcomes[0]["incident_detected"] = False
    with pytest.raises(P176ReleaseError, match="nonqualified_report"):
        build_release_artifacts(
            project_root=ROOT,
            outcomes=bad_outcomes,
            healthy_results=_healthy_results(),
            safety_counters=SAFETY_ZERO,
            agent_visible_ledger=_ledger("agent_visible"),
            evaluator_only_ledger=_ledger("evaluator_only"),
        )

    bad_counters = dict(SAFETY_ZERO)
    bad_counters["credential_leak_count"] = 1
    with pytest.raises(P176ReleaseError, match="nonqualified_report"):
        build_release_artifacts(
            project_root=ROOT,
            outcomes=_outcomes(),
            healthy_results=_healthy_results(),
            safety_counters=bad_counters,
            agent_visible_ledger=_ledger("agent_visible"),
            evaluator_only_ledger=_ledger("evaluator_only"),
        )

    leaked = _ledger("agent_visible")
    leaked[0] = deepcopy(leaked[0])
    leaked[0]["summary"] = {"ground_truth": "leak"}
    with pytest.raises(Exception, match="record_hash_invalid|agent_visible"):
        build_release_artifacts(
            project_root=ROOT,
            outcomes=_outcomes(),
            healthy_results=_healthy_results(),
            safety_counters=SAFETY_ZERO,
            agent_visible_ledger=leaked,
            evaluator_only_ledger=_ledger("evaluator_only"),
        )


def test_final_review_identity_and_release_tamper_validation_fail_closed() -> None:
    artifacts = build_release_artifacts(
        project_root=ROOT,
        outcomes=_outcomes(),
        healthy_results=_healthy_results(),
        safety_counters=SAFETY_ZERO,
        agent_visible_ledger=_ledger("agent_visible"),
        evaluator_only_ledger=_ledger("evaluator_only"),
    )

    with pytest.raises(P176ReleaseError, match="writer_reviewer"):
        validate_final_review(_review(artifacts["report"], artifacts["freeze_manifest"], same_identity=True), report=artifacts["report"], freeze_manifest=artifacts["freeze_manifest"])

    release = assemble_release_evidence(
        project_root=ROOT,
        report=artifacts["report"],
        denominator_report=artifacts["denominator_report"],
        representativeness_report=artifacts["representativeness_report"],
        freeze_manifest=artifacts["freeze_manifest"],
        final_review=_review(artifacts["report"], artifacts["freeze_manifest"]),
    )
    assert (
        validate_release_evidence(
            release,
            project_root=ROOT,
            report=artifacts["report"],
            denominator_report=artifacts["denominator_report"],
            representativeness_report=artifacts["representativeness_report"],
            freeze_manifest=artifacts["freeze_manifest"],
            final_review=_review(artifacts["report"], artifacts["freeze_manifest"]),
        )["qualified"]
        is True
    )

    tampered = deepcopy(release)
    tampered["safety_counters"]["auto_approval_count"] = 1
    with pytest.raises(P176ReleaseError, match="safety_counter_nonzero"):
        validate_release_evidence(
            tampered,
            project_root=ROOT,
            report=artifacts["report"],
            denominator_report=artifacts["denominator_report"],
            representativeness_report=artifacts["representativeness_report"],
            freeze_manifest=artifacts["freeze_manifest"],
            final_review=_review(artifacts["report"], artifacts["freeze_manifest"]),
        )

    fake_hashes = deepcopy(release)
    fake_hashes["report_hash"] = "sha256:" + "1" * 64
    fake_hashes["evidence_hash"] = stable_hash(
        {key: value for key, value in fake_hashes.items() if key != "evidence_hash"}
    )
    with pytest.raises(P176ReleaseError, match="companion_hash"):
        validate_release_evidence(
            fake_hashes,
            project_root=ROOT,
            report=artifacts["report"],
            denominator_report=artifacts["denominator_report"],
            representativeness_report=artifacts["representativeness_report"],
            freeze_manifest=artifacts["freeze_manifest"],
            final_review=_review(artifacts["report"], artifacts["freeze_manifest"]),
        )
