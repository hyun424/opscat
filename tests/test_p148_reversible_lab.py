from __future__ import annotations

import hashlib
import json
import shutil
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from app.services.p110_evaluation import stable_hash

ROOT = Path(__file__).resolve().parents[1]

FROZEN_COUNTER_KEYS = {
    "read_attempt_count",
    "read_success_count",
    "model_call_count",
    "external_model_call_count",
    "investigation_tool_call_count",
    "action_intent_count",
    "action_commit_count",
    "action_execution_count",
    "rollback_count",
    "heartbeat_count",
    "deadman_count",
    "artifact_write_count",
    "credential_read_count",
    "external_network_count",
    "external_message_count",
    "shell_count",
    "staging_mutation_count",
    "production_mutation_count",
    "authority_escape_count",
}

P148_LIMITATIONS = [
    "deterministic_judgment_only_no_external_model",
    "no_staging_production_or_external_side_effects",
    "process_owned_disposable_lab_only",
]

P148_CASE_IDS = [
    "success",
    "duplicate",
    "pre_state_mismatch",
    "expiry",
    "kill_switch",
    "unknown_capability",
    "staging_target",
    "failed_postcondition",
    "injected_crash",
    "rollback",
]
P148_COMMITMENT_SCHEMA = "p148.action_receipt_commitment.v1"


def _p148() -> Any:
    from app.services import p148_reversible_lab

    return p148_reversible_lab


def _counter_template(**overrides: int) -> dict[str, int]:
    counters = {key: 0 for key in FROZEN_COUNTER_KEYS}
    counters.update(overrides)
    return counters


def _with_self_hash(payload: dict[str, Any], field: str) -> dict[str, Any]:
    sealed = deepcopy(payload)
    sealed[field] = stable_hash({key: value for key, value in sealed.items() if key != field})
    return sealed


def _raw_file_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _write_canonical_json(path: Path, value: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=False, separators=(",", ":"), ensure_ascii=True) + "\n", encoding="utf-8")
    return path


def _p148_receipt_commitment(case_id: str) -> dict[str, Any]:
    receipt = {
        "schema_version": P148_COMMITMENT_SCHEMA,
        "case_id": case_id,
        "target_id": "lab-process://p149-canary-target",
        "idempotency_key": f"{case_id}-idem",
        "rollback_handler": "restore_process_snapshot",
        "p148_receipt_hash": "",
    }
    receipt["p148_receipt_hash"] = stable_hash({key: receipt[key] for key in sorted(receipt) if key != "p148_receipt_hash"})
    return receipt


def _p148_receipt_commitments() -> list[dict[str, Any]]:
    return [_p148_receipt_commitment(f"P149-CASE-{index:02d}") for index in range(1, 9)]


def _p147_release_evidence() -> dict[str, Any]:
    from app.services.p147_p152_contracts import phase_source_paths

    return _with_self_hash(
        {
            "schema_version": "p147.release_evidence.v1",
            "phase": "p147",
            "status": "p147_durable_provider_shadow_qualified",
            "claim": "provider-shaped conformance",
            "limitations": [
                "credential_free_no_external_network",
                "no_model_action_or_mutation",
                "offline_injected_provider_shapes_only_no_oa3_or_live_staging",
            ],
            "report_hash": "sha256:" + "1" * 64,
            "freeze_hash": "sha256:" + "2" * 64,
            "review_hash": "sha256:" + "3" * 64,
            "predecessors": [
                {
                    "phase": "p146",
                    "path": "evals/p146/final/release-evidence.json",
                    "schema_version": "p146.release_evidence.v1",
                    "required_status": "p146_live_shadow_qualification_ready",
                    "file_hash": "sha256:" + "4" * 64,
                    "evidence_hash": "sha256:" + "5" * 64,
                }
            ],
            "source_hashes": {relative: "sha256:" + "6" * 64 for relative in sorted(phase_source_paths("p147"))},
            "metrics": {
                "provider_read_count": 6,
                "normalized_record_count": 6,
                "resumed_cursor_count": 1,
                "heartbeat_count": 1,
                "deadman_count": 1,
                "investigation_tool_call_count": 1,
            },
            "counters": _counter_template(
                read_attempt_count=6,
                read_success_count=6,
                investigation_tool_call_count=1,
                heartbeat_count=1,
                deadman_count=1,
                artifact_write_count=1,
            ),
            "passed": 8,
            "failed": 0,
            "evidence_hash": "",
        },
        "evidence_hash",
    )


def _minimal_p147_release_evidence() -> dict[str, Any]:
    return _with_self_hash(
        {
            "schema_version": "p147.release_evidence.v1",
            "phase": "p147",
            "status": "p147_durable_provider_shadow_qualified",
            "evidence_hash": "",
        },
        "evidence_hash",
    )


def _copy_p148_project_root(root: Path) -> Path:
    from app.services.p147_p152_contracts import phase_source_paths

    for phase in ("p147", "p148"):
        for relative in phase_source_paths(phase):
            source = ROOT / relative
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    return root


def _project_root_with_p147_release(root: Path, evidence: dict[str, Any] | None = None) -> tuple[Path, dict[str, Any], Path]:
    from app.services.p147_p152_contracts import phase_source_paths

    project_root = _copy_p148_project_root(root)
    release = evidence or _p147_release_evidence()
    if evidence is None:
        release["source_hashes"] = {relative: _raw_file_hash(project_root / relative) for relative in sorted(phase_source_paths("p147"))}
        release = _with_self_hash(release, "evidence_hash")
    path = _write_canonical_json(project_root / "evals/p147/output/release-evidence.json", release)
    return project_root, release, path


def _p147_predecessor() -> dict[str, Any]:
    return {
        "phase": "p147",
        "path": "evals/p147/output/release-evidence.json",
        "schema_version": "p147.release_evidence.v1",
        "required_status": "p147_durable_provider_shadow_qualified",
        "file_hash": "sha256:" + "1" * 64,
        "evidence_hash": "sha256:" + "2" * 64,
    }


def _profile() -> dict[str, Any]:
    return {
        "schema_version": "p148.release_profile.v1",
        "phase": "p148",
        "case_ids": sorted(P148_CASE_IDS),
        "limits": {
            "case_count": 10,
            "unresolved_effect_count": 0,
            "nvidia_call_count": 0,
            "staging_mutation_count": 0,
            "production_mutation_count": 0,
        },
    }


def _judgment_packet() -> dict[str, Any]:
    return {
        "schema_version": "p148.deterministic_judgment.v1",
        "judgment_id": "judgment-checkout-restart-001",
        "evidence_hashes": ["sha256:" + "3" * 64],
        "citations": [{"provider_kind": "prometheus", "record_hash": "sha256:" + "4" * 64}],
        "route": "auto_safe_lab",
        "recommended_action": "restart_process_owned_lab_worker",
        "target_id": "lab-process://checkout-worker-1",
        "external_model_call_count": 0,
    }


def _lab_actions() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "success",
            "action": "restart_process_owned_lab_worker",
            "target_id": "lab-process://checkout-worker-1",
            "target_scope": "process_owned_disposable_lab",
            "idempotency_key": "p148-success-key",
            "pre_state_hash": "sha256:" + "5" * 64,
            "observed_pre_state_hash": "sha256:" + "5" * 64,
            "rollback_snapshot_hash": "sha256:" + "6" * 64,
            "postcondition": {"worker_ready": True, "queue_depth": 0},
            "rollback_handler": "restore_process_snapshot",
            "kill_switch_clear": True,
            "receipt_commitments": _p148_receipt_commitments(),
        },
        {
            "case_id": "rollback",
            "action": "restart_process_owned_lab_worker",
            "target_id": "lab-process://checkout-worker-2",
            "target_scope": "process_owned_disposable_lab",
            "idempotency_key": "p148-rollback-key",
            "pre_state_hash": "sha256:" + "7" * 64,
            "observed_pre_state_hash": "sha256:" + "7" * 64,
            "rollback_snapshot_hash": "sha256:" + "8" * 64,
            "postcondition": {"worker_ready": False, "queue_depth": 12},
            "rollback_handler": "restore_process_snapshot",
            "kill_switch_clear": True,
            "receipt_commitments": [],
        },
    ]


def test_contract_and_predecessor_fail_closed(tmp_path: Path) -> None:
    p148 = _p148()
    from app.services.p147_p152_contracts import validate_current_release_bindings

    project_root, release, release_path = _project_root_with_p147_release(tmp_path / "project")
    artifacts = p148.generate_p148_preliminary_artifacts(project_root=project_root, output_dir=tmp_path / "canonical")
    canonical_report = json.loads(artifacts["report"].read_text(encoding="utf-8"))
    canonical_predecessor = canonical_report["predecessors"][0]
    assert canonical_predecessor == {
        "phase": "p147",
        "path": "evals/p147/output/release-evidence.json",
        "schema_version": "p147.release_evidence.v1",
        "required_status": "p147_durable_provider_shadow_qualified",
        "file_hash": _raw_file_hash(release_path),
        "evidence_hash": release["evidence_hash"],
    }
    assert canonical_predecessor["file_hash"] != canonical_predecessor["evidence_hash"]
    assert validate_current_release_bindings(project_root, canonical_report, p148.P148_CONTRACT)["report_hash"] == canonical_report["report_hash"]

    forged_release = deepcopy(release)
    forged_release["review_hash"] = "sha256:" + "f" * 64
    forged_release = _with_self_hash(forged_release, "evidence_hash")
    _write_canonical_json(release_path, forged_release)
    with pytest.raises(ValueError, match="predecessor|bindings|stale|invalid|p147"):
        validate_current_release_bindings(project_root, canonical_report, p148.P148_CONTRACT)

    stale_source_root, _, _ = _project_root_with_p147_release(tmp_path / "stale-source-project")
    stale_artifacts = p148.generate_p148_preliminary_artifacts(project_root=stale_source_root, output_dir=tmp_path / "stale-source")
    stale_report = json.loads(stale_artifacts["report"].read_text(encoding="utf-8"))
    (stale_source_root / "app/services/p148_reversible_lab.py").write_text(
        (stale_source_root / "app/services/p148_reversible_lab.py").read_text(encoding="utf-8") + "\n# stale source probe\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="source_hashes_stale:p148"):
        validate_current_release_bindings(stale_source_root, stale_report, p148.P148_CONTRACT)

    stale_root = _copy_p148_project_root(tmp_path / "stale-project")
    with pytest.raises(ValueError, match="artifact_missing_or_unsafe|predecessor"):
        p148.generate_p148_preliminary_artifacts(project_root=stale_root, output_dir=tmp_path / "stale")

    minimal_root, _, _ = _project_root_with_p147_release(tmp_path / "minimal-project", _minimal_p147_release_evidence())
    with pytest.raises(ValueError, match="release|keyset|predecessor|p147"):
        p148.generate_p148_preliminary_artifacts(project_root=minimal_root, output_dir=tmp_path / "minimal")

    forged = _p147_predecessor()
    forged["path"] = "evals/p147/output/report.json"
    forged["required_status"] = "p147_preliminary_provider_shadow_ready"

    with pytest.raises(ValueError, match="predecessor|p147|release|status"):
        p148.run_p148_qualification(
            project_root=ROOT,
            output_dir=tmp_path,
            profile=_profile(),
            predecessor=forged,
            judgment_packets=[_judgment_packet()],
            lab_actions=_lab_actions(),
        )

    incomplete = _p147_predecessor()
    del incomplete["file_hash"]
    with pytest.raises(ValueError, match="predecessor|field|file_hash"):
        p148.validate_p148_report(
            {
                "schema_version": "p148.report.v1",
                "phase": "p148",
                "status": "p148_reversible_lab_action_qualified",
                "claim": "process-owned reversible lab action",
                "limitations": P148_LIMITATIONS,
                "profile_hash": "sha256:" + "e" * 64,
                "predecessors": [incomplete],
                "source_hashes": {"app/services/p148_reversible_lab.py": "sha256:" + "f" * 64},
                "case_count": 10,
                "passed": 10,
                "failed": 0,
                "metrics": {
                    "judgment_count": 1,
                    "lab_action_count": 1,
                    "blocked_count": 7,
                    "rollback_count": 1,
                    "unresolved_effect_count": 0,
                    "nvidia_call_count": 0,
                    "committed_action_receipts": _p148_receipt_commitments(),
                },
                "counters": _counter_template(),
                "rows": [],
                "report_hash": "sha256:" + "0" * 64,
            }
        )


def test_happy_path_report_and_counters(tmp_path: Path) -> None:
    p148 = _p148()

    report = p148.run_p148_qualification(
        project_root=ROOT,
        output_dir=tmp_path,
        profile=_profile(),
        predecessor=_p147_predecessor(),
        judgment_packets=[_judgment_packet()],
        lab_actions=_lab_actions(),
    )

    assert p148.validate_p148_report(report) == report
    assert report["schema_version"] == "p148.report.v1"
    assert report["status"] == "p148_reversible_lab_action_qualified"
    assert report["limitations"] == P148_LIMITATIONS
    assert report["case_count"] == 10
    assert report["passed"] == 10
    assert report["failed"] == 0
    assert set(report["counters"]) == FROZEN_COUNTER_KEYS
    assert report["counters"]["action_intent_count"] == 1
    assert report["counters"]["action_commit_count"] == 1
    assert report["counters"]["action_execution_count"] == 1
    assert report["counters"]["rollback_count"] == 1
    assert report["counters"]["external_model_call_count"] == 0
    assert report["counters"]["staging_mutation_count"] == 0
    assert report["counters"]["production_mutation_count"] == 0
    assert report["metrics"] == {
        "judgment_count": 1,
        "lab_action_count": 1,
        "blocked_count": 7,
        "rollback_count": 1,
        "unresolved_effect_count": 0,
        "nvidia_call_count": 0,
        "committed_action_receipts": _p148_receipt_commitments(),
    }
    assert [row["case_id"] for row in report["rows"]] == sorted(P148_CASE_IDS)
    assert all(row["expected"]["schema_version"] == "p148.row_result.v1" for row in report["rows"])
    lab_root = tmp_path / "p148-disposable-lab"
    receipt_files = sorted(lab_root.glob("*/receipt-p148-success-key.json"))
    rollback_files = sorted(lab_root.glob("*/rollback-p148-rollback-key.json"))
    recovery_files = sorted(lab_root.glob("*/recovery-p148-injected_crash-key.json"))
    assert len(receipt_files) == 1
    assert len(rollback_files) == 1
    assert len(recovery_files) == 1
    receipt = json.loads(receipt_files[0].read_text(encoding="utf-8"))
    rollback = json.loads(rollback_files[0].read_text(encoding="utf-8"))
    recovery = json.loads(recovery_files[0].read_text(encoding="utf-8"))
    assert receipt["pre_state_hash"] != receipt["post_state_hash"]
    assert rollback["restored_state_hash"].startswith("sha256:")
    assert recovery["restored_state_hash"].startswith("sha256:")


def test_fault_matrix_and_recovery(tmp_path: Path) -> None:
    p148 = _p148()

    fault_actions = _lab_actions() + [
        {
            "case_id": "pre_state_mismatch",
            "action": "restart_process_owned_lab_worker",
            "target_id": "lab-process://checkout-worker-3",
            "target_scope": "process_owned_disposable_lab",
            "idempotency_key": "p148-prestate-key",
            "pre_state_hash": "sha256:" + "9" * 64,
            "observed_pre_state_hash": "sha256:" + "a" * 64,
            "rollback_snapshot_hash": "sha256:" + "b" * 64,
            "postcondition": {"worker_ready": True},
            "rollback_handler": "restore_process_snapshot",
            "kill_switch_clear": True,
        },
        {
            "case_id": "kill_switch",
            "action": "restart_process_owned_lab_worker",
            "target_id": "lab-process://checkout-worker-4",
            "target_scope": "process_owned_disposable_lab",
            "idempotency_key": "p148-kill-key",
            "pre_state_hash": "sha256:" + "c" * 64,
            "observed_pre_state_hash": "sha256:" + "c" * 64,
            "rollback_snapshot_hash": "sha256:" + "d" * 64,
            "postcondition": {"worker_ready": True},
            "rollback_handler": "restore_process_snapshot",
            "kill_switch_clear": False,
        },
    ]

    report = p148.run_p148_qualification(
        project_root=ROOT,
        output_dir=tmp_path,
        profile=_profile(),
        predecessor=_p147_predecessor(),
        judgment_packets=[_judgment_packet()],
        lab_actions=fault_actions,
    )

    rows = {row["case_id"]: row for row in report["rows"]}
    assert rows["pre_state_mismatch"]["observed"]["outcome"] == "blocked"
    assert "pre_state_mismatch" in rows["pre_state_mismatch"]["observed"]["reason_codes"]
    assert rows["kill_switch"]["observed"]["outcome"] == "blocked"
    assert "kill_switch_active" in rows["kill_switch"]["observed"]["reason_codes"]
    assert rows["rollback"]["observed"]["measurements"]["rollback_count"] == 1
    assert rows["rollback"]["observed"]["measurements"]["unresolved_effect_count"] == 0


def test_forgery_and_authority_rejected(tmp_path: Path) -> None:
    p148 = _p148()

    forged_judgment = deepcopy(_judgment_packet())
    forged_judgment["route"] = "approve_once"
    with pytest.raises(ValueError, match="route|auto_safe_lab|authority"):
        p148.run_p148_qualification(
            project_root=ROOT,
            output_dir=tmp_path,
            profile=_profile(),
            predecessor=_p147_predecessor(),
            judgment_packets=[forged_judgment],
            lab_actions=_lab_actions(),
        )

    staging_action = deepcopy(_lab_actions()[0])
    staging_action["target_scope"] = "staging"
    staging_action["target_id"] = "staging://checkout-worker-1"
    with pytest.raises(ValueError, match="process_owned|staging|production"):
        p148.run_p148_qualification(
            project_root=ROOT,
            output_dir=tmp_path,
            profile=_profile(),
            predecessor=_p147_predecessor(),
            judgment_packets=[_judgment_packet()],
            lab_actions=[staging_action],
        )

    forged_report = {
        "schema_version": "p148.report.v1",
        "phase": "p148",
        "status": "p148_reversible_lab_action_qualified",
        "claim": "process-owned reversible lab action",
        "limitations": P148_LIMITATIONS,
        "profile_hash": "sha256:" + "e" * 64,
        "predecessors": [_p147_predecessor()],
        "source_hashes": {"app/services/p148_reversible_lab.py": "sha256:" + "f" * 64},
        "case_count": 10,
        "passed": 10,
        "failed": 0,
        "metrics": {},
        "counters": _counter_template(staging_mutation_count=1, authority_escape_count=1),
        "rows": [],
        "report_hash": "sha256:" + "0" * 64,
    }
    with pytest.raises(ValueError, match="counter|staging_mutation_count|authority_escape_count|zero"):
        p148.validate_p148_report(forged_report)

    row_forged_report = p148.run_p148_qualification(
        project_root=ROOT,
        output_dir=tmp_path / "row-forgery",
        profile=_profile(),
        predecessor=_p147_predecessor(),
        judgment_packets=[_judgment_packet()],
        lab_actions=_lab_actions(),
    )
    success_row = next(row for row in row_forged_report["rows"] if row["case_id"] == "success")
    for result_key in ("expected", "observed"):
        success_row[result_key]["measurements"]["commit_count"] = 0
        success_row[result_key]["measurements"]["execution_count"] = 0
    sealed_success_row = _with_self_hash(success_row, "row_hash")
    row_forged_report["rows"] = [sealed_success_row if row["case_id"] == "success" else row for row in row_forged_report["rows"]]
    row_forged_report = _with_self_hash(row_forged_report, "report_hash")
    assert row_forged_report["metrics"]["committed_action_receipts"] == _p148_receipt_commitments()
    with pytest.raises(ValueError, match="row|counter|receipt|commit|execution"):
        p148.validate_p148_report(row_forged_report)


def test_release_evidence_requires_zero_finding_review(tmp_path: Path) -> None:
    p148 = _p148()

    report = p148.run_p148_qualification(
        project_root=ROOT,
        output_dir=tmp_path,
        profile=_profile(),
        predecessor=_p147_predecessor(),
        judgment_packets=[_judgment_packet()],
        lab_actions=_lab_actions(),
    )
    freeze_payload = {
        "schema_version": "p148.freeze_manifest.v1",
        "phase": "p148",
        "plan_hash": report["source_hashes"]["docs/operations/p147-p152-program-plan.md"],
        "test_spec_hash": report["source_hashes"]["docs/operations/p148-test-spec.md"],
        "source_hashes": report["source_hashes"],
        "profile_hash": report["profile_hash"],
        "predecessor_file_hashes": [report["predecessors"][0]["file_hash"]],
        "report_hash": report["report_hash"],
        "manifest_hash": "",
    }
    invalid_freeze_payload = deepcopy(freeze_payload)
    invalid_freeze_payload["plan_hash"] = "sha256:" + "9" * 64
    with pytest.raises(ValueError, match="freeze_plan_or_spec_binding_invalid"):
        p148.validate_p148_freeze_manifest(_with_self_hash(invalid_freeze_payload, "manifest_hash"))

    freeze = p148.validate_p148_freeze_manifest(_with_self_hash(freeze_payload, "manifest_hash"))
    review = _with_self_hash(
        {
            "schema_version": "p148.final_review.v1",
            "phase": "p148",
            "writer_agent_id": "019f72f0-0000-7000-8000-000000000149",
            "reviewer_identity": "independent-p148-reviewer",
            "reviewer_agent_id": "019f72f0-0000-7000-8000-000000000148",
            "reviewed_at": "2026-07-16T00:00:00Z",
            "decision": "approve",
            "findings": {"p0": 0, "p1": 0, "p2": 0, "p3": 1},
            "limitations": P148_LIMITATIONS,
            "reviewed_report_hash": report["report_hash"],
            "reviewed_manifest_hash": freeze["manifest_hash"],
            "review_hash": "",
        },
        "review_hash",
    )

    writer_agent_id = "019f72f0-0000-7000-8000-000000000149"
    assert writer_agent_id == review["writer_agent_id"]
    assert writer_agent_id != review["reviewer_agent_id"]
    with pytest.raises(ValueError, match="review|findings|p3|zero"):
        p148.validate_p148_final_review(review, report=report, freeze_manifest=freeze, writer_agent_id=writer_agent_id)

    review["findings"]["p3"] = 0
    review = _with_self_hash(review, "review_hash")
    accepted_review = p148.validate_p148_final_review(review, report=report, freeze_manifest=freeze, writer_agent_id=writer_agent_id)
    evidence_payload = {
        "schema_version": "p148.release_evidence.v1",
        "phase": "p148",
        "status": "p148_reversible_lab_action_qualified",
        "claim": report["claim"],
        "limitations": P148_LIMITATIONS,
        "report_hash": report["report_hash"],
        "freeze_hash": freeze["manifest_hash"],
        "review_hash": accepted_review["review_hash"],
        "predecessors": report["predecessors"],
        "source_hashes": report["source_hashes"],
        "metrics": report["metrics"],
        "counters": report["counters"],
        "passed": 10,
        "failed": 0,
        "evidence_hash": "",
    }
    evidence = p148.validate_p148_release_evidence(_with_self_hash(evidence_payload, "evidence_hash"))
    assert evidence["status"] == "p148_reversible_lab_action_qualified"

    forged_evidence_payload = deepcopy(evidence_payload)
    forged_evidence_payload["counters"]["action_commit_count"] = 0
    forged_evidence_payload["counters"]["action_execution_count"] = 0
    with pytest.raises(ValueError, match="release|counter|action_commit_count"):
        p148.validate_p148_release_evidence(_with_self_hash(forged_evidence_payload, "evidence_hash"))
