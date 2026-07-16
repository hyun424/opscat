from __future__ import annotations

import copy
import hashlib
import importlib
import json
from pathlib import Path
from typing import Any

import pytest

P149_LIMITATIONS = [
    "automatic_rollback_no_production_authority",
    "one_process_owned_lab_target_only",
    "synthetic_slo_observations",
]
P148_COMMITMENT_SCHEMA = "p148.action_receipt_commitment.v1"
P149_TARGET_ID = "lab-process://p149-canary-target"
P149_WRITER_AGENT_ID = "019f72f0-0000-7000-8000-000000000148"


def _phase() -> Any:
    return importlib.import_module("app.services.p149_canary_control")


def _stable_hash(value: dict[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _p148_receipt_commitment(case_id: str) -> dict[str, Any]:
    receipt = {
        "schema_version": P148_COMMITMENT_SCHEMA,
        "case_id": case_id,
        "target_id": P149_TARGET_ID,
        "idempotency_key": f"{case_id}-idem",
        "rollback_handler": "restore_process_snapshot",
        "p148_receipt_hash": "",
    }
    receipt["p148_receipt_hash"] = _stable_hash({key: receipt[key] for key in sorted(receipt) if key != "p148_receipt_hash"})
    return receipt


def _p148_receipt_commitments() -> list[dict[str, Any]]:
    return [_p148_receipt_commitment(f"P149-CASE-{index:02d}") for index in range(1, 9)]


def _valid_p148_release_evidence() -> dict[str, Any]:
    from app.services.p147_p152_contracts import phase_source_paths

    evidence: dict[str, Any] = {
        "schema_version": "p148.release_evidence.v1",
        "phase": "p148",
        "status": "p148_reversible_lab_action_qualified",
        "claim": "process-owned reversible lab action",
        "limitations": [
            "deterministic_judgment_only_no_external_model",
            "no_staging_production_or_external_side_effects",
            "process_owned_disposable_lab_only",
        ],
        "report_hash": "sha256:" + "1" * 64,
        "freeze_hash": "sha256:" + "2" * 64,
        "review_hash": "sha256:" + "3" * 64,
        "predecessors": [
            {
                "phase": "p147",
                "path": "evals/p147/output/release-evidence.json",
                "schema_version": "p147.release_evidence.v1",
                "required_status": "p147_durable_provider_shadow_qualified",
                "file_hash": "sha256:" + "0" * 64,
                "evidence_hash": "sha256:" + "9" * 64,
            }
        ],
        "source_hashes": {path: "sha256:" + "4" * 64 for path in sorted(phase_source_paths("p148"))},
        "metrics": {
            "judgment_count": 10,
            "lab_action_count": 4,
            "blocked_count": 6,
            "rollback_count": 2,
            "unresolved_effect_count": 0,
            "nvidia_call_count": 0,
            "committed_action_receipts": _p148_receipt_commitments(),
        },
        "counters": {
            "read_attempt_count": 0,
            "read_success_count": 0,
            "model_call_count": 0,
            "external_model_call_count": 0,
            "investigation_tool_call_count": 0,
            "action_intent_count": 4,
            "action_commit_count": 4,
            "action_execution_count": 4,
            "rollback_count": 2,
            "heartbeat_count": 0,
            "deadman_count": 0,
            "artifact_write_count": 4,
            "credential_read_count": 0,
            "external_network_count": 0,
            "external_message_count": 0,
            "shell_count": 0,
            "staging_mutation_count": 0,
            "production_mutation_count": 0,
            "authority_escape_count": 0,
        },
        "passed": 10,
        "failed": 0,
        "evidence_hash": "",
    }
    evidence["evidence_hash"] = _stable_hash({key: value for key, value in evidence.items() if key != "evidence_hash"})
    return evidence


def _p149_case(case_id: str, outcome: str, observations: list[int], expected: str) -> dict[str, Any]:
    commitment = _p148_receipt_commitment(case_id)
    return {
        "case_id": case_id,
        "target": {
            "target_id": P149_TARGET_ID,
            "environment": "process_owned_disposable_lab",
            "cohort_hash": "sha256:" + "a" * 64,
            "control_hash": "sha256:" + "b" * 64,
            "affected_target_count": 1,
        },
        "slo": {
            "window_seconds": 60,
            "minimum_observations": 5,
            "improvement_basis_points": 1000,
            "harm_basis_points": 500,
            "relative_uncertainty_basis_points": 200,
            "observations_basis_points": observations,
        },
        "action_receipt": {
            "p148_receipt_hash": commitment["p148_receipt_hash"],
            "target_id": commitment["target_id"],
            "idempotency_key": commitment["idempotency_key"],
            "rollback_handler": commitment["rollback_handler"],
        },
        "injected_outcome": outcome,
        "expected_decision": expected,
    }


def _all_p149_cases() -> list[dict[str, Any]]:
    return [
        _p149_case("P149-CASE-01", "improved", [1100, 1200, 1150, 1180, 1210], "commit"),
        _p149_case("P149-CASE-02", "no_change", [0, 20, -10, 5, 0], "rollback"),
        _p149_case("P149-CASE-03", "harmful", [-500, -700, -650, -900, -800], "rollback"),
        _p149_case("P149-CASE-04", "uncertain", [1050, 800, 1200, 900, 1000], "rollback"),
        _p149_case("P149-CASE-05", "timeout", [1100, 1200, 1150, 1180, 1210], "rollback"),
        _p149_case("P149-CASE-06", "missing_evidence", [1100, 1200, 1150, 1180, 1210], "rollback"),
        _p149_case("P149-CASE-07", "replay", [1100, 1200, 1150, 1180, 1210], "no_duplicate_effect"),
        _p149_case("P149-CASE-08", "rollback_failure", [-500, -700, -650, -900, -800], "fail_closed"),
    ]


def _p149_final_review(report: dict[str, Any], freeze_manifest: dict[str, Any], findings: dict[str, int] | None = None) -> dict[str, Any]:
    from app.services import p147_p152_contracts

    review = {
        "schema_version": "p149.final_review.v1",
        "phase": "p149",
        "reviewer_identity": "independent-p149-reviewer",
        "reviewer_agent_id": "019f72f0-0000-7000-8000-000000000149",
        "reviewed_at": "2026-07-16T00:00:00Z",
        "decision": "approve",
        "findings": findings or {"p0": 0, "p1": 0, "p2": 0, "p3": 0},
        "limitations": P149_LIMITATIONS,
        "reviewed_report_hash": report["report_hash"],
        "reviewed_manifest_hash": freeze_manifest["manifest_hash"],
        "review_hash": "",
    }
    if "writer_agent_id" in p147_p152_contracts.REVIEW_KEYS:
        review["writer_agent_id"] = P149_WRITER_AGENT_ID
    review["review_hash"] = _stable_hash({key: value for key, value in review.items() if key != "review_hash"})
    return review


def test_contract_and_predecessor_fail_closed(tmp_path: Path) -> None:
    phase = _phase()
    predecessor = _valid_p148_release_evidence()
    with pytest.raises(Exception, match="predecessor_path_required"):
        phase.run_p149_qualification(predecessor=predecessor, cases=_all_p149_cases(), output_dir=tmp_path / "pathless")
    report = phase.run_p149_qualification(
        evidence_mode="isolated_test",
        predecessor=predecessor,
        cases=_all_p149_cases(),
        output_dir=tmp_path,
    )["report"]

    assert phase.validate_p149_report(report)["status"] == "p149_canary_outcome_control_qualified"
    assert report["predecessors"] == [
        {
            "phase": "p148",
            "path": "evals/p148/output/release-evidence.json",
            "schema_version": "p148.release_evidence.v1",
            "required_status": "p148_reversible_lab_action_qualified",
            "file_hash": predecessor["evidence_hash"],
            "evidence_hash": predecessor["evidence_hash"],
        }
    ]

    forged = copy.deepcopy(predecessor)
    forged["status"] = "p148_preliminary_not_release"
    forged["evidence_hash"] = _stable_hash({key: value for key, value in forged.items() if key != "evidence_hash"})
    with pytest.raises(Exception, match="p148|predecessor|status|release"):
        phase.run_p149_qualification(evidence_mode="isolated_test", predecessor=forged, cases=[], output_dir=tmp_path / "forged")


def test_happy_path_report_and_counters(tmp_path: Path) -> None:
    phase = _phase()
    canonical_path = Path(__file__).resolve().parents[1] / "evals/p149/input/canary-cases.json"
    canonical_cases = json.loads(canonical_path.read_text(encoding="utf-8"))
    canonical_report = phase.run_p149_qualification(
        evidence_mode="isolated_test",
        predecessor=_valid_p148_release_evidence(),
        cases=canonical_cases,
        output_dir=tmp_path / "canonical-input",
    )["report"]
    assert canonical_report["passed"] == 8

    copied_canonical = tmp_path / "canary-cases.json"
    copied_canonical.write_bytes(canonical_path.read_bytes())
    with pytest.raises(Exception, match="canonical.*path"):
        phase.run_p149_qualification(
            cases=canonical_cases,
            cases_path=copied_canonical,
            output_dir=tmp_path / "copied-canonical",
            project_root=Path(__file__).resolve().parents[1],
        )
    with pytest.raises(Exception, match="canonical.*path"):
        phase.run_p149_qualification(
            cases=_all_p149_cases(),
            output_dir=tmp_path / "memory-canonical",
            project_root=Path(__file__).resolve().parents[1],
        )

    result = phase.run_p149_qualification(
        evidence_mode="isolated_test",
        predecessor=_valid_p148_release_evidence(),
        cases=_all_p149_cases(),
        output_dir=tmp_path,
    )
    report = phase.validate_p149_report(result["report"])

    assert report["schema_version"] == "p149.report.v1"
    assert report["status"] == "p149_canary_outcome_control_qualified"
    assert report["metrics"]["canary_count"] == 8
    assert report["metrics"]["committed_count"] == 1
    assert report["metrics"]["rolled_back_count"] == 5
    assert report["metrics"]["max_affected_targets"] == 1
    assert report["metrics"]["rollback_success_rate"] == 1.0
    assert report["metrics"]["canonical_input_verified"] is False
    assert report["counters"]["action_execution_count"] == 6
    assert report["counters"]["rollback_count"] == 5
    assert report["counters"]["staging_mutation_count"] == 0
    assert report["counters"]["production_mutation_count"] == 0
    assert report["counters"]["authority_escape_count"] == 0

    forged_report = copy.deepcopy(report)
    forged_report["metrics"]["harmful_count"] = 0
    forged_report["counters"]["rollback_count"] = 0
    forged_report["report_hash"] = _stable_hash({key: value for key, value in forged_report.items() if key != "report_hash"})
    with pytest.raises(Exception, match="metric|counter|rows"):
        phase.validate_p149_report(forged_report)


def test_fault_matrix_and_recovery(tmp_path: Path) -> None:
    phase = _phase()
    cases = _all_p149_cases()
    report = phase.run_p149_qualification(evidence_mode="isolated_test", predecessor=_valid_p148_release_evidence(), cases=cases, output_dir=tmp_path)["report"]

    rows = {row["case_id"]: row for row in phase.validate_p149_report(report)["rows"]}
    assert set(rows) == {case["case_id"] for case in cases}
    assert rows["P149-CASE-01"]["observed"]["measurements"]["decision"] == "commit"
    assert rows["P149-CASE-03"]["observed"]["measurements"]["decision"] == "rollback"
    assert rows["P149-CASE-05"]["observed"]["measurements"]["rollback_count"] == 1
    assert "replay_suppressed" in rows["P149-CASE-07"]["observed"]["reason_codes"]
    assert rows["P149-CASE-08"]["passed"] is True
    assert rows["P149-CASE-08"]["failure_classes"] == []
    assert rows["P149-CASE-08"]["observed"]["measurements"]["affected_targets"] == 0
    assert rows["P149-CASE-08"]["observed"]["measurements"]["rollback_count"] == 0
    assert "rollback_preflight_blocked_before_effect" in rows["P149-CASE-08"]["observed"]["reason_codes"]
    assert rows["P149-CASE-08"]["observed"]["measurements"]["fail_closed"] is True
    assert "rollback_failure_fail_closed" in rows["P149-CASE-08"]["observed"]["reason_codes"]


def test_forgery_and_authority_rejected(tmp_path: Path) -> None:
    phase = _phase()
    missing_case = _all_p149_cases()[:-1]
    with pytest.raises(Exception, match="p149_profile|missing|P149-CASE-08"):
        phase.run_p149_qualification(evidence_mode="isolated_test", predecessor=_valid_p148_release_evidence(), cases=missing_case, output_dir=tmp_path / "missing-case")

    extra_case = _all_p149_cases() + [_p149_case("P149-CASE-09", "improved", [1100, 1200, 1150, 1180, 1210], "commit")]
    with pytest.raises(Exception, match="p149_profile|extra|P149-CASE-09"):
        phase.run_p149_qualification(evidence_mode="isolated_test", predecessor=_valid_p148_release_evidence(), cases=extra_case, output_dir=tmp_path / "extra-case")

    duplicate_case = _all_p149_cases()
    duplicate_case[-1] = copy.deepcopy(duplicate_case[0])
    with pytest.raises(Exception, match="p149_profile|duplicate|P149-CASE-01"):
        phase.run_p149_qualification(evidence_mode="isolated_test", predecessor=_valid_p148_release_evidence(), cases=duplicate_case, output_dir=tmp_path / "duplicate-case")

    forged_target = _all_p149_cases()
    forged_target[0]["target"]["affected_target_count"] = 2
    with pytest.raises(Exception, match="blast|affected|one|target"):
        phase.run_p149_qualification(evidence_mode="isolated_test", predecessor=_valid_p148_release_evidence(), cases=forged_target, output_dir=tmp_path / "blast")

    staging_target = _all_p149_cases()
    staging_target[0]["target"]["environment"] = "staging"
    with pytest.raises(Exception, match="staging|production|target|authority"):
        phase.run_p149_qualification(evidence_mode="isolated_test", predecessor=_valid_p148_release_evidence(), cases=staging_target, output_dir=tmp_path / "staging")

    missing_receipt = _all_p149_cases()
    del missing_receipt[0]["action_receipt"]["rollback_handler"]
    with pytest.raises(Exception, match="action_receipt|keyset"):
        phase.run_p149_qualification(evidence_mode="isolated_test", predecessor=_valid_p148_release_evidence(), cases=missing_receipt, output_dir=tmp_path / "missing-receipt")

    forged_receipt = _all_p149_cases()
    forged_receipt[1]["action_receipt"]["p148_receipt_hash"] = "sha256:not-a-real-hash"
    with pytest.raises(Exception, match="action_receipt|hash"):
        phase.run_p149_qualification(evidence_mode="isolated_test", predecessor=_valid_p148_release_evidence(), cases=forged_receipt, output_dir=tmp_path / "forged-receipt")

    uncommitted_receipt = _all_p149_cases()
    uncommitted_receipt[1]["action_receipt"]["p148_receipt_hash"] = "sha256:" + "f" * 64
    with pytest.raises(Exception, match="action_receipt|committed|P149-CASE-02"):
        phase.run_p149_qualification(evidence_mode="isolated_test", predecessor=_valid_p148_release_evidence(), cases=uncommitted_receipt, output_dir=tmp_path / "uncommitted-receipt")

    duplicate_receipts = _all_p149_cases()
    duplicate_receipts[1]["action_receipt"]["idempotency_key"] = duplicate_receipts[0]["action_receipt"]["idempotency_key"]
    with pytest.raises(Exception, match="action_receipt|idempotency|binding"):
        phase.run_p149_qualification(evidence_mode="isolated_test", predecessor=_valid_p148_release_evidence(), cases=duplicate_receipts, output_dir=tmp_path / "duplicate-receipt")

    forged_handler = _all_p149_cases()
    forged_handler[1]["action_receipt"]["rollback_handler"] = "restore_snapshot"
    with pytest.raises(Exception, match="action_receipt|rollback_handler|binding"):
        phase.run_p149_qualification(evidence_mode="isolated_test", predecessor=_valid_p148_release_evidence(), cases=forged_handler, output_dir=tmp_path / "forged-handler")

    kill_switch = _all_p149_cases()
    kill_switch[0]["injected_outcome"] = "kill_switch"
    kill_switch[0]["expected_decision"] = "rollback"
    report = phase.run_p149_qualification(
        evidence_mode="isolated_test",
        predecessor=_valid_p148_release_evidence(),
        cases=kill_switch,
        kill_switch_engaged=True,
        output_dir=tmp_path / "kill",
    )["report"]
    row = phase.validate_p149_report(report)["rows"][0]
    assert row["observed"]["measurements"]["decision"] == "rollback"
    assert row["observed"]["measurements"]["affected_targets"] == 0
    assert row["observed"]["measurements"]["rollback_count"] == 1
    assert "kill_switch" in row["observed"]["reason_codes"]


def test_release_evidence_requires_zero_finding_review(tmp_path: Path) -> None:
    phase = _phase()
    result = phase.run_p149_qualification(
        evidence_mode="isolated_test",
        predecessor=_valid_p148_release_evidence(),
        cases=_all_p149_cases(),
        output_dir=tmp_path,
    )

    assert "report" in result
    assert "freeze_manifest" in result
    assert "final_review" not in result
    assert "release_evidence" not in result

    report = phase.validate_p149_report(result["report"])
    manifest = phase.validate_p149_freeze_manifest(result["freeze_manifest"])
    nonzero_review = _p149_final_review(report, manifest, findings={"p0": 0, "p1": 0, "p2": 1, "p3": 0})
    assert nonzero_review["review_hash"] == _stable_hash({key: value for key, value in nonzero_review.items() if key != "review_hash"})
    with pytest.raises(Exception, match="review|finding|p2|zero"):
        phase.validate_p149_final_review(nonzero_review, report=report, freeze_manifest=manifest)

    review = phase.validate_p149_final_review(_p149_final_review(report, manifest), report=report, freeze_manifest=manifest)
    with pytest.raises(Exception, match="canonical|metric|input"):
        phase.validate_p149_release_evidence(
            phase.assemble_p149_release_evidence(report=report, freeze_manifest=manifest, final_review=review)
        )

    report = copy.deepcopy(report)
    report["metrics"]["canonical_input_verified"] = True
    report["report_hash"] = _stable_hash({key: value for key, value in report.items() if key != "report_hash"})
    report = phase.validate_p149_report(report)
    manifest = phase.build_freeze_manifest(
        project_root=Path(__file__).resolve().parents[1],
        contract=phase.P149_CONTRACT,
        report=report,
    )
    review = phase.validate_p149_final_review(
        _p149_final_review(report, manifest),
        report=report,
        freeze_manifest=manifest,
    )
    release = phase.validate_p149_release_evidence(
        phase.assemble_p149_release_evidence(report=report, freeze_manifest=manifest, final_review=review)
    )
    assert manifest["schema_version"] == "p149.freeze_manifest.v1"
    assert manifest["manifest_hash"] == _stable_hash({key: value for key, value in manifest.items() if key != "manifest_hash"})
    assert review["findings"] == {"p0": 0, "p1": 0, "p2": 0, "p3": 0}
    assert review["limitations"] == P149_LIMITATIONS
    assert review["reviewed_report_hash"] == report["report_hash"]
    assert review["reviewed_manifest_hash"] == manifest["manifest_hash"]
    assert review["review_hash"] == _stable_hash({key: value for key, value in review.items() if key != "review_hash"})
    assert release["status"] == "p149_canary_outcome_control_qualified"
    assert release["passed"] == 8
    assert release["failed"] == 0
    assert release["limitations"] == P149_LIMITATIONS
    assert release["report_hash"] == report["report_hash"]
    assert release["freeze_hash"] == manifest["manifest_hash"]
    assert release["review_hash"] == review["review_hash"]
    assert release["metrics"]["max_affected_targets"] == 1
    assert release["evidence_hash"] == _stable_hash({key: value for key, value in release.items() if key != "evidence_hash"})

    forged_release = copy.deepcopy(release)
    forged_release["metrics"]["harmful_count"] = 0
    forged_release["counters"]["rollback_count"] = 0
    forged_release["evidence_hash"] = _stable_hash({key: value for key, value in forged_release.items() if key != "evidence_hash"})
    with pytest.raises(Exception, match="metric|counter|rows"):
        phase.validate_p149_release_evidence(forged_release, report=report)

    bad_release = copy.deepcopy(release)
    bad_release["passed"] = 7
    bad_release["evidence_hash"] = _stable_hash({key: value for key, value in bad_release.items() if key != "evidence_hash"})
    with pytest.raises(Exception, match="exact|denominator"):
        phase.validate_p149_release_evidence(bad_release)

    stale_manifest = copy.deepcopy(manifest)
    stale_manifest["source_hashes"]["app/services/p149_canary_control.py"] = "sha256:" + "f" * 64
    stale_manifest["manifest_hash"] = _stable_hash({key: value for key, value in stale_manifest.items() if key != "manifest_hash"})
    stale_manifest = phase.validate_p149_freeze_manifest(stale_manifest)
    stale_review = phase.validate_p149_final_review(_p149_final_review(report, stale_manifest), report=report, freeze_manifest=stale_manifest)
    with pytest.raises(Exception, match="freeze_source_hashes_mismatch"):
        phase.assemble_p149_release_evidence(report=report, freeze_manifest=stale_manifest, final_review=stale_review)
