from __future__ import annotations

import copy
import json

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p118_evaluator import run_p118_frozen_evaluation
from app.services.p118_operation_contract import P118_AUTHORITY_COUNTER_KEYS
from app.services.p118_release_evidence import empty_p118_release_authority_counters, produce_p118_release_evidence, validate_p118_release_evidence
from scripts.run_p118_frozen_evaluation import main as run_eval_main
from scripts.validate_p118_release_evidence import main as validate_release_main


def test_frozen_evaluation_has_300_cases_per_family_metrics_and_zero_authority() -> None:
    report = run_p118_frozen_evaluation(seed=11801)

    assert report["case_count"] >= 300
    assert report["freshness"]["fresh"] is True
    assert set(report["per_family_metrics"]) == {
        "approval",
        "authority_counters",
        "cas",
        "contract_rejection",
        "crash_recovery",
        "idempotency",
        "leases",
        "release_evidence",
        "replay",
        "rollback",
        "signed_pack_verification",
        "validation",
        "wal",
    }
    assert report["authority"]["exact_nonlocal_authority_zero"] is True
    assert report["aggregate"]["duplicate_action_count"] == 0
    assert report["evaluation_hash"].startswith("sha256:")


def test_release_evidence_requires_distinct_reviewer_fresh_hashes_and_exact_zero_authority() -> None:
    report = run_p118_frozen_evaluation(seed=11801)
    evidence = produce_p118_release_evidence(
        frozen_evaluation_report=report,
        reviewer_identity={"id": "reviewer-p118"},
        builder_identity={"id": "builder-p118"},
        authority_counters=empty_p118_release_authority_counters(),
    )

    assert evidence["release_status"] == "p118_local_mock_sandbox_ready"
    assert evidence["gates"]["distinct_reviewer"] is True
    assert evidence["gates"]["exact_nonlocal_authority_zero"] is True
    assert evidence["product_claim"] == "local/mock/sandbox reactive execution substrate readiness"
    assert validate_p118_release_evidence(evidence)["valid"] is True

    stale = dict(evidence)
    stale["frozen_evaluation_hash"] = "sha256:" + "0" * 64
    assert validate_p118_release_evidence(stale)["valid"] is False


def test_release_evidence_fails_closed_for_self_review_and_nonzero_authority() -> None:
    report = run_p118_frozen_evaluation(seed=11801)
    counters = empty_p118_release_authority_counters()
    counters["production_mutation"] = 1
    evidence = produce_p118_release_evidence(
        frozen_evaluation_report=report,
        reviewer_identity={"id": "same"},
        builder_identity={"id": "same"},
        authority_counters=counters,
    )

    assert evidence["release_status"] == "p118_blocked"
    assert evidence["gates"]["distinct_reviewer"] is False
    assert evidence["gates"]["exact_nonlocal_authority_zero"] is False


@pytest.mark.parametrize(
    "counters",
    [
        {key: False if index == 0 else 0 for index, key in enumerate(P118_AUTHORITY_COUNTER_KEYS)},
        {key: 0 for key in P118_AUTHORITY_COUNTER_KEYS[:-1]},
    ],
)
def test_release_evidence_production_and_validator_reject_bool_or_incomplete_exact_zero(counters: dict[str, object]) -> None:
    report = run_p118_frozen_evaluation(seed=11801)
    produced = produce_p118_release_evidence(
        frozen_evaluation_report=report,
        reviewer_identity={"id": "reviewer-p118"},
        builder_identity={"id": "builder-p118"},
        authority_counters=counters,  # type: ignore[arg-type]
    )
    assert produced["release_status"] == "p118_blocked"
    assert produced["gates"]["exact_nonlocal_authority_zero"] is False

    valid = produce_p118_release_evidence(
        frozen_evaluation_report=report,
        reviewer_identity={"id": "reviewer-p118"},
        builder_identity={"id": "builder-p118"},
        authority_counters=empty_p118_release_authority_counters(),
    )
    forged = copy.deepcopy(valid)
    forged["authority"]["counters"] = counters
    forged["authority"]["exact_nonlocal_authority_zero"] = True
    forged["release_evidence_hash"] = stable_hash({key: value for key, value in forged.items() if key != "release_evidence_hash"})
    assert validate_p118_release_evidence(forged)["valid"] is False


def test_p118_evaluation_and_release_validation_scripts_round_trip(tmp_path) -> None:  # type: ignore[no-untyped-def]
    report_path = tmp_path / "evaluation.json"
    evidence_path = tmp_path / "release-evidence.json"

    assert run_eval_main(["--output", str(report_path), "--seed", "11801"]) == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    evidence = produce_p118_release_evidence(
        frozen_evaluation_report=report,
        reviewer_identity={"id": "reviewer-p118"},
        builder_identity={"id": "builder-p118"},
        authority_counters=empty_p118_release_authority_counters(),
    )
    evidence_path.write_text(json.dumps(evidence, sort_keys=True), encoding="utf-8")

    assert validate_release_main([str(evidence_path)]) == 0


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        ("target", "invalid_frozen_fixture_input"),
        ("action_ref", "invalid_frozen_p115_action_pack_ref"),
        ("decision_ref", "invalid_frozen_p117_decision_ref"),
    ],
)
def test_frozen_manifest_contents_directly_drive_evaluation_and_reject_corruption(tmp_path, mutation: str, error: str) -> None:  # type: ignore[no-untyped-def]
    manifest = json.loads(open("evals/p118/frozen-case-manifest.json", encoding="utf-8").read())
    corrupted = copy.deepcopy(manifest)
    case = corrupted["cases"][0]
    if mutation == "target":
        case["fixture_input"]["fixture_target_id"] = "production:checkout"
    elif mutation == "action_ref":
        case["p115_action_pack_ref"]["action_pack_ref"]["action_pack_id"] = "pack:forged"
    else:
        case["p117_decision_ref"]["selected_action_pack_id"] = "pack:forged"
    corrupted["manifest_hash"] = stable_hash({key: value for key, value in corrupted.items() if key != "manifest_hash"})
    path = tmp_path / f"{mutation}.json"
    path.write_text(json.dumps(corrupted), encoding="utf-8")

    with pytest.raises(ValueError, match=error):
        run_p118_frozen_evaluation(seed=11801, manifest_path=path)
