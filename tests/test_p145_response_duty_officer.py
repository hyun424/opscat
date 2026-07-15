from __future__ import annotations

import ast
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p145_response_duty_officer import (
    APPROVED_PLAN_REVIEW_SHA256,
    APPROVED_PLAN_SHA256,
    APPROVED_TEST_SPEC_SHA256,
    CASE_SELECTOR_NAMES,
    FORBIDDEN_AUTHORITY_KEYS,
    PREDECESSOR_BINDINGS,
    P145DutyOfficerError,
    apply_lab_transform,
    build_observation,
    expected_source_profile_bindings,
    process_episode_fixture,
    validate_case_fixture,
    validate_fault_lab_state,
    verify_recovery,
)
from app.services.p145_runner import record_pytest_case_result


def _fixture(case_id: str) -> dict[str, Any]:
    value = json.loads(Path(f"tests/fixtures/p145/cases/{case_id}.json").read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return validate_case_fixture(value)


def _assert_case(case_id: str, tmp_path: Path) -> dict[str, Any]:
    fixture = _fixture(case_id)
    result = process_episode_fixture(fixture, output_dir=tmp_path).as_dict()
    record_pytest_case_result(result)
    assert result["terminal_status"] == fixture["expected_terminal_status"]
    assert result["counts"]["forbidden_authority"] == {key: 0 for key in FORBIDDEN_AUTHORITY_KEYS}
    for group, expected in fixture["expected_counts"].items():
        for key, value in expected.items():
            assert result["counts"][group][key] == value
    assert Path(result["journal_path"]).is_file()
    if result["counts"]["runtime_activity"]["cursor_write_count"]:
        assert Path(result["cursor_path"]).is_file()
    return result


def _rehash_fixture(fixture: dict[str, Any]) -> dict[str, Any]:
    fixture["fixture_hash"] = stable_hash({key: value for key, value in fixture.items() if key != "fixture_hash"})
    return fixture


def _rehash_fixture_evidence(fixture: dict[str, Any]) -> dict[str, Any]:
    fixture["evidence_hash"] = stable_hash(
        {
            "event": fixture["p133_event"],
            "correlated_event": fixture["correlated_p133_event"],
            "predecessor_bindings": fixture["predecessor_bindings"],
            "source_profile_bindings": fixture["source_profile_bindings"],
            "evidence": fixture["evidence"],
        }
    )
    return _rehash_fixture(fixture)


def _write_canonical_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def _rewrite_rehashed_journal(path: Path, entries: list[dict[str, Any]]) -> None:
    previous = "sha256:" + "0" * 64
    for index, entry in enumerate(entries, start=1):
        entry["cas_version"] = index
        entry["logical_time"] = index
        entry["payload_hash"] = stable_hash(entry["payload"])
        entry["previous_receipt_hash"] = previous
        entry["receipt_hash"] = stable_hash({key: value for key, value in entry.items() if key != "receipt_hash"})
        previous = entry["receipt_hash"]
    path.write_text(
        "".join(json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n" for entry in entries),
        encoding="utf-8",
    )


def _rebind_cursor_to_entries(case_dir: Path, entries: list[dict[str, Any]]) -> None:
    cursor_path = case_dir / "cursor.json"
    cursor = json.loads(cursor_path.read_text(encoding="utf-8"))
    cursor["terminal_receipt_hash"] = entries[-1]["receipt_hash"]
    cursor["cursor_hash"] = stable_hash({key: value for key, value in cursor.items() if key != "cursor_hash"})
    _write_canonical_json(cursor_path, cursor)


def _assert_rejected_before_ownership(fixture: dict[str, Any], output_dir: Path, reason: str) -> dict[str, Any]:
    result = process_episode_fixture(fixture, output_dir=output_dir).as_dict()
    assert result["terminal_status"] == "human_escalation_required"
    assert result["phase_path"] == ["registered", "escalation_receipt_committed", "human_escalation_required"]
    assert result["counts"]["runtime_activity"]["p133_ack_write_count"] == 0
    assert result["counts"]["lab_activity"]["local_policy_authorization_count"] == 0
    assert result["counts"]["lab_activity"]["action_intent_count"] == 0
    assert result["counts"]["lab_activity"]["action_commit_count"] == 0
    assert result["counts"]["lab_activity"]["lab_state_mutation_count"] == 0
    assert reason in result["command_notes"]
    return result


def test_refreshed_approved_chain_bindings_are_exact() -> None:
    assert APPROVED_PLAN_SHA256 == "sha256:72e3ce302020acd05061fecb178b5f5fbddadae751cf42be0dfc28e92edb8a3b"
    assert APPROVED_TEST_SPEC_SHA256 == "sha256:72274365b622629154b4347ea3caff48bb4672076287c72165c19b01aeab8050"
    assert APPROVED_PLAN_REVIEW_SHA256 == "sha256:d59b48335c6c265ca2d723aae6a739252eabab5db2438a03de428bd496a851e8"
    refreshed = {
        "p137_local_evidence_triage_qualified": "sha256:a645581b8da537cb6de521b00d319d803a4a0791e0c663abf8a5924069a2a825",
        "p138_local_observation_to_triage_supervisor_qualified": "sha256:11eb88212c919bc64a9c0220c97d40ce9a45a2f71f38bd4a9ed7d759ce433d83",
        "p139_local_triage_service_host_qualified": "sha256:e791fc9a6719182931bc42b76d4512b00fc57d1c7bff96e4ca96cefe9f6e628f",
        "p140_p139_deadman_adapter_qualified": "sha256:c590518a868c8cbc0475eff6f8d4ac8a6fae4786a7c5eacecfeaa9432f09699f",
        "p141_notification_authority_simulator_qualified": "sha256:f3298f1295515b89e5374a449e9deb29fbd70f7c2a1e09446b80d9279d73d3b2",
        "p142_loopback_transport_lab_qualified": "sha256:3e952653a335da77ca6ce5f9cc7d6dcb9b39299afc7324c016fe8446f5c7f8e6",
        "p143_provider_neutral_egress_contract_lab_qualified": "sha256:a791376fe892fd9d31474e6cc007410687f2ece4da4eae096e23c0a6bfe0e1a8",
        "p144_final_evidence": "sha256:ab7189b68bc185aed2598fb3699a971e955d36afa1ec3f7c49006586cc5559c9",
        "p144_independent_final_review": "sha256:a0fc69970dfcdf54c46675f943d8ebaaa3e5e28a94706683eea689abca95351a",
        "p144_canonical_matrix": "sha256:4d033cfe27f4e39fe1d2904bdf43f7fd447c8d9996c272bf55a1e0ab7c06cc42",
        "p144_freeze_manifest": "sha256:9ead2b671bc764168842fde4448a7d7c2b5ddccce9f4e018f05f43bc472fdfae",
    }
    assert {key: PREDECESSOR_BINDINGS[key] for key in refreshed} == refreshed
    source_bindings = expected_source_profile_bindings(CASE_SELECTOR_NAMES["P145-CASE-01"])
    assert source_bindings["approved_plan_sha256"] == APPROVED_PLAN_SHA256
    assert source_bindings["approved_test_spec_sha256"] == APPROVED_TEST_SPEC_SHA256
    assert source_bindings["plan_review_sha256"] == APPROVED_PLAN_REVIEW_SHA256


def test_expected_values_are_evaluator_only_and_cannot_change_execution(tmp_path: Path) -> None:
    fixture = _fixture("P145-CASE-13")
    baseline = process_episode_fixture(fixture, output_dir=tmp_path / "baseline").as_dict()
    for name in ("terminal", "phase", "crash", "counts"):
        forged = deepcopy(fixture)
        if name == "terminal":
            forged["expected_terminal_status"] = "rollback_verified"
            forged["expected_phase_path"] = ["registered", "rollback_receipt_committed", "rollback_verified"]
        elif name == "phase":
            forged["expected_phase_path"] = ["registered", "recovery_receipt_committed", "recovery_verified"]
        elif name == "crash":
            forged["expected_crash_point"] = "before_action_commit"
        else:
            for group_name, group in forged["expected_counts"].items():
                if isinstance(group, dict):
                    for key in group:
                        group[key] = 0 if group_name == "forbidden_authority" else 999
        observed = process_episode_fixture(_rehash_fixture(forged), output_dir=tmp_path / name).as_dict()
        for key in ("terminal_status", "phase_path", "counts", "crash_point"):
            assert observed[key] == baseline[key]


def test_branch_label_cannot_drive_policy_or_preflight(tmp_path: Path) -> None:
    fixture = _fixture("P145-CASE-01")
    baseline = process_episode_fixture(fixture, output_dir=tmp_path / "baseline").as_dict()
    relabeled = deepcopy(fixture)
    relabeled["branch"] = "stale"
    observed = process_episode_fixture(_rehash_fixture(relabeled), output_dir=tmp_path / "relabeled").as_dict()
    assert observed["terminal_status"] == baseline["terminal_status"]
    assert observed["phase_path"] == baseline["phase_path"]
    assert observed["counts"] == baseline["counts"]


def test_policy_and_evidence_inputs_drive_preflight_and_freshness(tmp_path: Path) -> None:
    stale = deepcopy(_fixture("P145-CASE-07"))
    stale["evidence"]["fresh"] = True
    stale["evidence_hash"] = stable_hash(
        {
            "event": stale["p133_event"],
            "correlated_event": stale["correlated_p133_event"],
            "predecessor_bindings": stale["predecessor_bindings"],
            "source_profile_bindings": stale["source_profile_bindings"],
            "evidence": stale["evidence"],
        }
    )
    recovered = process_episode_fixture(_rehash_fixture(stale), output_dir=tmp_path / "fresh").as_dict()
    assert recovered["terminal_status"] == "recovery_verified"
    assert recovered["counts"]["lab_activity"]["action_commit_count"] == 1

    blocked = deepcopy(_fixture("P145-CASE-12"))
    blocked["policy"]["rollback_metadata_present"] = True
    recovered = process_episode_fixture(_rehash_fixture(blocked), output_dir=tmp_path / "preflight").as_dict()
    assert recovered["terminal_status"] == "recovery_verified"
    assert recovered["counts"]["lab_activity"]["action_commit_count"] == 1


def test_every_case_freezes_a_nonempty_exact_phase_path() -> None:
    for case_id in CASE_SELECTOR_NAMES:
        fixture = _fixture(case_id)
        assert fixture["expected_phase_path"]
        assert fixture["expected_phase_path"][-1] == fixture["expected_terminal_status"]


def test_predecessor_and_source_profile_binding_forgery_blocks_before_ownership(tmp_path: Path) -> None:
    for field, key in (
        ("predecessor_bindings", "p144_final_evidence"),
        ("source_profile_bindings", "profile_sha256"),
    ):
        fixture = deepcopy(_fixture("P145-CASE-01"))
        fixture[field][key] = "sha256:" + "f" * 64
        result = process_episode_fixture(_rehash_fixture(fixture), output_dir=tmp_path / field).as_dict()
        assert result["terminal_status"] == "human_escalation_required"
        assert result["counts"]["runtime_activity"]["p133_ack_write_count"] == 0
        assert result["counts"]["lab_activity"]["action_intent_count"] == 0


def test_authority_bound_module_has_no_evaluator_or_forbidden_runtime_reachability() -> None:
    source_path = Path("app/services/p145_response_duty_officer.py")
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert imported.isdisjoint({"subprocess", "socket", "requests", "httpx", "urllib", "boto3", "kubernetes"})
    forbidden_names = {"environ", "getenv", "system", "popen", "spawn", "subprocess", "ticket", "staging", "production"}
    reached = {
        node.attr.lower()
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
    } | {
        node.func.id.lower()
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert reached.isdisjoint(forbidden_names)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "os":
            assert {alias.name for alias in node.names} <= {"O_RDONLY", "close", "fsync", "open", "replace"}


def test_fault_lab_state_hash_and_observation_forgery_fail_closed() -> None:
    fixture = _fixture("P145-CASE-01")
    state = fixture["initial_lab_state"]
    validate_fault_lab_state(state)
    forged = dict(state)
    forged["latency_ms"] += 1
    with pytest.raises(P145DutyOfficerError, match="fault_lab_state_hash_invalid"):
        validate_fault_lab_state(forged)
    mutated = apply_lab_transform(state, "deploy_rollback", action_id="a1")
    observation = build_observation(mutated, logical_time=1)
    observation["signals"]["latency_ms"] = 999
    with pytest.raises(P145DutyOfficerError, match="observation_hash_invalid"):
        verify_recovery(mutated, [observation])


def test_deploy_regression_rolls_back_and_recovers(tmp_path: Path) -> None:
    result = _assert_case("P145-CASE-01", tmp_path)
    assert result["counts"]["runtime_activity"]["p133_ack_write_count"] == 1
    assert result["counts"]["lab_activity"]["action_commit_count"] == 1
    assert result["counts"]["lab_activity"]["recovery_proof_count"] == 1


def test_pool_saturation_contradicts_deploy_hypothesis(tmp_path: Path) -> None:
    assert _assert_case("P145-CASE-02", tmp_path)["counts"]["lab_activity"]["action_commit_count"] == 1


def test_dependency_timeout_rejects_restart(tmp_path: Path) -> None:
    result = _assert_case("P145-CASE-03", tmp_path)
    assert result["policy_receipt_hash"] is not None


def test_queue_backlog_uses_two_bounded_actions(tmp_path: Path) -> None:
    assert _assert_case("P145-CASE-04", tmp_path)["counts"]["lab_activity"]["action_commit_count"] == 2


def test_natural_recovery_is_observe_only(tmp_path: Path) -> None:
    assert _assert_case("P145-CASE-05", tmp_path)["counts"]["lab_activity"]["action_commit_count"] == 0


def test_conflicting_telemetry_escalates_without_action(tmp_path: Path) -> None:
    assert _assert_case("P145-CASE-06", tmp_path)["counts"]["lab_activity"]["action_commit_count"] == 0


def test_stale_evidence_cannot_authorize_action(tmp_path: Path) -> None:
    assert _assert_case("P145-CASE-07", tmp_path)["counts"]["lab_activity"]["local_policy_authorization_count"] == 0


def test_log_prompt_injection_is_untrusted_evidence(tmp_path: Path) -> None:
    assert any("injection" in note for note in _assert_case("P145-CASE-08", tmp_path)["command_notes"])


def test_missing_critical_evidence_requests_then_escalates(tmp_path: Path) -> None:
    assert _assert_case("P145-CASE-09", tmp_path)["terminal_status"] == "human_escalation_required"


def test_harmful_first_action_rolls_back(tmp_path: Path) -> None:
    assert _assert_case("P145-CASE-10", tmp_path)["counts"]["lab_activity"]["rollback_commit_count"] == 1


def test_primary_metric_only_is_not_recovery(tmp_path: Path) -> None:
    assert _assert_case("P145-CASE-11", tmp_path)["terminal_status"] == "human_escalation_required"


def test_missing_rollback_blocks_before_mutation(tmp_path: Path) -> None:
    assert _assert_case("P145-CASE-12", tmp_path)["counts"]["lab_activity"]["lab_state_mutation_count"] == 0


def test_crash_after_action_receipt_resumes_verification_once(tmp_path: Path) -> None:
    result = _assert_case("P145-CASE-13", tmp_path)
    assert result["crash_point"] == "action_receipt"
    assert "controller_restarted" in result["command_notes"]
    assert result["counts"]["runtime_activity"]["p133_ack_write_count"] == 1
    assert result["counts"]["lab_activity"]["action_commit_count"] == 1


def test_crash_before_action_commit_is_at_most_once(tmp_path: Path) -> None:
    assert _assert_case("P145-CASE-14", tmp_path)["counts"]["lab_activity"]["duplicate_action_count"] == 0


def test_same_resource_lease_contention_allows_one_mutator(tmp_path: Path) -> None:
    result = _assert_case("P145-CASE-15", tmp_path)
    assert result["terminal_status"] == "human_escalation_required"
    assert "competing_worker_lease_conflict" in result["command_notes"]
    assert result["counts"]["lab_activity"]["action_commit_count"] == 1
    assert result["counts"]["lab_activity"]["duplicate_action_count"] == 0
    lease = json.loads((tmp_path / "P145-CASE-15" / "lease.json").read_text(encoding="utf-8"))
    assert lease["owner_id"] == "worker-a"
    assert lease["acquire_count"] == 1


def test_dead_runner_emits_recoverable_handoff(tmp_path: Path) -> None:
    assert _assert_case("P145-CASE-16", tmp_path)["counts"]["runtime_activity"]["escalation_receipt_count"] == 1


def test_action_budget_exhaustion_preserves_history(tmp_path: Path) -> None:
    assert _assert_case("P145-CASE-17", tmp_path)["terminal_status"] == "human_escalation_required"


def test_duplicate_incident_replay_reuses_terminal_receipt(tmp_path: Path) -> None:
    result = _assert_case("P145-CASE-18", tmp_path)
    assert result["terminal_receipt_hash"]
    assert result["counts"]["runtime_activity"]["p133_ack_write_count"] == 0
    assert result["counts"]["lab_activity"]["action_commit_count"] == 0
    assert "terminal_receipt_reused" in result["command_notes"]


def test_poisoned_prior_memory_is_contradiction_not_authority(tmp_path: Path) -> None:
    assert _assert_case("P145-CASE-19", tmp_path)["terminal_status"] == "recovery_verified"


def test_protected_domain_is_human_required(tmp_path: Path) -> None:
    assert _assert_case("P145-CASE-20", tmp_path)["counts"]["runtime_activity"]["p133_ack_write_count"] == 0


def test_evidence_hash_forgery_fails_before_ownership(tmp_path: Path) -> None:
    assert _assert_case("P145-CASE-21", tmp_path)["counts"]["runtime_activity"]["p133_ack_write_count"] == 0


def test_journal_duplicate_phase_fails_closed(tmp_path: Path) -> None:
    result = _assert_case("P145-CASE-22", tmp_path)
    assert result["terminal_status"] == "human_escalation_required"
    assert "journal_duplicate_phase_rejected" in result["command_notes"]
    assert result["counts"]["lab_activity"]["action_commit_count"] == 0


def test_journal_reorder_fails_closed(tmp_path: Path) -> None:
    result = _assert_case("P145-CASE-23", tmp_path)
    assert "journal_reorder_rejected" in result["command_notes"]
    assert result["counts"]["lab_activity"]["action_commit_count"] == 0


def test_journal_missing_predecessor_fails_closed(tmp_path: Path) -> None:
    result = _assert_case("P145-CASE-24", tmp_path)
    assert "journal_missing_predecessor_rejected" in result["command_notes"]
    assert result["counts"]["runtime_activity"]["cursor_write_count"] == 0


def test_lab_state_drift_invalidates_recovery(tmp_path: Path) -> None:
    assert _assert_case("P145-CASE-25", tmp_path)["terminal_status"] == "human_escalation_required"


def test_rollback_failure_never_claims_recovery(tmp_path: Path) -> None:
    result = _assert_case("P145-CASE-26", tmp_path)
    assert result["terminal_status"] == "human_escalation_required"
    assert result["counts"]["lab_activity"]["rollback_intent_count"] == 1
    assert result["counts"]["lab_activity"]["rollback_commit_count"] == 0


def test_recurrence_after_apparent_recovery_is_rejected(tmp_path: Path) -> None:
    assert _assert_case("P145-CASE-27", tmp_path)["terminal_status"] == "human_escalation_required"


def test_insufficient_consecutive_observations_escalates(tmp_path: Path) -> None:
    assert _assert_case("P145-CASE-28", tmp_path)["terminal_status"] == "human_escalation_required"


def test_out_of_order_observations_fail_closed(tmp_path: Path) -> None:
    assert _assert_case("P145-CASE-29", tmp_path)["terminal_status"] == "human_escalation_required"


def test_observation_gap_fails_closed(tmp_path: Path) -> None:
    assert _assert_case("P145-CASE-30", tmp_path)["terminal_status"] == "human_escalation_required"


def test_clock_rollback_fails_closed(tmp_path: Path) -> None:
    assert _assert_case("P145-CASE-31", tmp_path)["counts"]["lab_activity"]["duplicate_action_count"] == 0


def test_flapping_recovery_is_not_sustained(tmp_path: Path) -> None:
    assert _assert_case("P145-CASE-32", tmp_path)["terminal_status"] == "human_escalation_required"


def test_partial_degraded_recovery_is_not_success(tmp_path: Path) -> None:
    assert _assert_case("P145-CASE-33", tmp_path)["terminal_status"] == "human_escalation_required"


def test_delayed_regression_after_rollback_escalates(tmp_path: Path) -> None:
    assert _assert_case("P145-CASE-34", tmp_path)["terminal_status"] == "human_escalation_required"


def test_rollback_collateral_harm_escalates(tmp_path: Path) -> None:
    assert _assert_case("P145-CASE-35", tmp_path)["terminal_status"] == "human_escalation_required"


def test_lab_mutated_before_receipt_recovers_without_repeat(tmp_path: Path) -> None:
    assert _assert_case("P145-CASE-36", tmp_path)["counts"]["lab_activity"]["duplicate_action_count"] == 0


def test_action_receipt_before_fsync_is_not_committed(tmp_path: Path) -> None:
    assert _assert_case("P145-CASE-37", tmp_path)["terminal_status"] == "rollback_verified"


def test_rollback_mutated_before_receipt_recovers_once(tmp_path: Path) -> None:
    assert _assert_case("P145-CASE-38", tmp_path)["counts"]["lab_activity"]["rollback_commit_count"] == 1


def test_terminal_receipt_before_cursor_replays_without_action(tmp_path: Path) -> None:
    assert _assert_case("P145-CASE-39", tmp_path)["counts"]["runtime_activity"]["cursor_write_count"] == 1


def test_lease_expiry_during_verification_escalates(tmp_path: Path) -> None:
    assert _assert_case("P145-CASE-40", tmp_path)["terminal_status"] == "human_escalation_required"


def test_lease_expiry_during_rollback_recovers_or_escalates(tmp_path: Path) -> None:
    assert _assert_case("P145-CASE-41", tmp_path)["terminal_status"] == "rollback_verified"


def test_journal_disk_full_fails_before_action(tmp_path: Path) -> None:
    assert _assert_case("P145-CASE-42", tmp_path)["counts"]["lab_activity"]["lab_state_mutation_count"] == 0


def test_lab_fsync_failure_forces_verified_rollback(tmp_path: Path) -> None:
    assert _assert_case("P145-CASE-43", tmp_path)["terminal_status"] == "rollback_verified"


def test_cursor_fsync_failure_replays_terminal_only(tmp_path: Path) -> None:
    assert _assert_case("P145-CASE-44", tmp_path)["counts"]["lab_activity"]["duplicate_action_count"] == 0


def test_duplicate_correlated_incidents_share_one_action(tmp_path: Path) -> None:
    fixture = _fixture("P145-CASE-45")
    first_event = fixture["p133_event"]
    second_event = fixture["correlated_p133_event"]
    assert first_event["event_id"] != second_event["event_id"]
    assert first_event["incident_id"] != second_event["incident_id"]
    assert first_event["correlation_id"] == second_event["correlation_id"]

    result = _assert_case("P145-CASE-45", tmp_path)
    assert result["counts"]["runtime_activity"]["p133_ack_write_count"] == 2
    assert result["counts"]["lab_activity"]["action_commit_count"] == 1
    assert result["counts"]["lab_activity"]["lab_state_mutation_count"] == 1
    assert "correlated_duplicate_action_reused" in result["command_notes"]
    assert len(result["ack_receipt_hashes"]) == 2

    journal = [json.loads(line) for line in Path(result["journal_path"]).read_text(encoding="utf-8").splitlines()]
    phases = [entry["phase"] for entry in journal]
    assert phases.index("owned_acknowledged") < phases.index("action_receipt_committed")
    assert phases.index("action_receipt_committed") < phases.index("correlated_event_registered")
    assert phases.index("correlated_event_registered") < phases.index("correlated_owned_acknowledged")
    correlation_entry = next(entry for entry in journal if entry["phase"] == "correlation_action_receipt_committed")
    action_entry = next(entry for entry in journal if entry["phase"] == "action_receipt_committed")
    assert correlation_entry["payload"] == {
        "schema_version": "p145.correlation_action_receipt.v1",
        "correlation_id": first_event["correlation_id"],
        "first_event_id": first_event["event_id"],
        "first_incident_id": first_event["incident_id"],
        "second_event_id": second_event["event_id"],
        "second_incident_id": second_event["incident_id"],
        "action_receipt_hash": action_entry["payload"]["receipt_hash"],
        "action_reused": True,
        "second_action_mutation": False,
    }
    assert result["correlation_action_receipt"] == {
        **correlation_entry["payload"],
        "journal_receipt_hash": correlation_entry["receipt_hash"],
    }
    assert json.loads((tmp_path / "P145-CASE-45" / "p133-ack-correlated.json").read_text(encoding="utf-8"))["event_id"] == second_event["event_id"]


def test_correlated_duplicate_replay_mode_changes_observed_proof(tmp_path: Path) -> None:
    correlated = _fixture("P145-CASE-45")
    correlated_result = process_episode_fixture(correlated, output_dir=tmp_path / "correlated").as_dict()

    ordinary = deepcopy(correlated)
    ordinary["replay_mode"] = "none"
    ordinary["p133_event"].pop("correlation_id")
    ordinary["p133_event"]["event_hash"] = stable_hash(
        {key: value for key, value in ordinary["p133_event"].items() if key != "event_hash"}
    )
    ordinary["correlated_p133_event"] = None
    ordinary_result = process_episode_fixture(
        _rehash_fixture_evidence(ordinary), output_dir=tmp_path / "ordinary"
    ).as_dict()

    assert correlated_result["phase_path"] != ordinary_result["phase_path"]
    assert correlated_result["counts"]["runtime_activity"]["p133_ack_write_count"] == 2
    assert ordinary_result["counts"]["runtime_activity"]["p133_ack_write_count"] == 1
    assert "correlation_action_receipt_committed" in correlated_result["phase_path"]
    assert "correlation_action_receipt_committed" not in ordinary_result["phase_path"]
    assert "correlated_duplicate_action_reused" in correlated_result["command_notes"]
    assert "correlated_duplicate_action_reused" not in ordinary_result["command_notes"]
    assert correlated_result["counts"]["lab_activity"]["action_commit_count"] == 1
    assert ordinary_result["counts"]["lab_activity"]["action_commit_count"] == 1


def test_correlated_duplicate_second_event_is_hash_bound_before_ownership(tmp_path: Path) -> None:
    forged = deepcopy(_fixture("P145-CASE-45"))
    forged["correlated_p133_event"]["incident_id"] = "forged-correlated-incident"
    result = process_episode_fixture(_rehash_fixture(forged), output_dir=tmp_path).as_dict()
    assert result["terminal_status"] == "human_escalation_required"
    assert result["counts"]["runtime_activity"]["p133_ack_write_count"] == 0
    assert result["counts"]["lab_activity"]["action_intent_count"] == 0
    assert "correlated_p133_event_hash_invalid" in result["command_notes"]


@pytest.mark.parametrize("ack_name", ["p133-ack.json", "p133-ack-correlated.json"])
@pytest.mark.parametrize("tamper", ["delete", "corrupt"])
def test_case45_terminal_replay_rejects_missing_or_corrupt_ack_projection(
    ack_name: str, tamper: str, tmp_path: Path,
) -> None:
    fixture = _fixture("P145-CASE-45")
    first = process_episode_fixture(fixture, output_dir=tmp_path).as_dict()
    assert first["terminal_status"] == "recovery_verified"
    assert first["counts"]["runtime_activity"]["p133_ack_write_count"] == 2

    ack_path = tmp_path / "P145-CASE-45" / ack_name
    if tamper == "delete":
        ack_path.unlink()
    else:
        ack_path.write_text("{not-json}\n", encoding="utf-8")

    replay = process_episode_fixture(fixture, output_dir=tmp_path).as_dict()
    assert replay["terminal_status"] == "human_escalation_required"
    assert replay["counts"]["runtime_activity"]["p133_ack_write_count"] == 0
    assert replay["counts"]["lab_activity"]["action_commit_count"] == 0
    assert replay["counts"]["lab_activity"]["lab_state_mutation_count"] == 0
    assert any("p133_ack_artifact" in note for note in replay["command_notes"])


def test_case45_terminal_replay_rejects_rehashed_ack_semantic_drift(tmp_path: Path) -> None:
    fixture = _fixture("P145-CASE-45")
    process_episode_fixture(fixture, output_dir=tmp_path)
    ack_path = tmp_path / "P145-CASE-45" / "p133-ack-correlated.json"
    ack = json.loads(ack_path.read_text(encoding="utf-8"))
    ack["incident_id"] = "drifted-incident"
    ack["ack_hash"] = stable_hash({key: value for key, value in ack.items() if key != "ack_hash"})
    ack_path.write_text(json.dumps(ack, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

    replay = process_episode_fixture(fixture, output_dir=tmp_path).as_dict()
    assert replay["terminal_status"] == "human_escalation_required"
    assert replay["counts"]["runtime_activity"]["p133_ack_write_count"] == 0
    assert "tamper_rejected:p133_ack_artifact_drift" in replay["command_notes"]


def test_case45_terminal_replay_rejects_extra_ack_artifact(tmp_path: Path) -> None:
    fixture = _fixture("P145-CASE-45")
    process_episode_fixture(fixture, output_dir=tmp_path)
    case_dir = tmp_path / "P145-CASE-45"
    extra = json.loads((case_dir / "p133-ack.json").read_text(encoding="utf-8"))
    extra["event_id"] = "extra-event"
    extra["ack_hash"] = stable_hash({key: value for key, value in extra.items() if key != "ack_hash"})
    (case_dir / "p133-ack-extra.json").write_text(
        json.dumps(extra, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8"
    )

    replay = process_episode_fixture(fixture, output_dir=tmp_path).as_dict()
    assert replay["terminal_status"] == "human_escalation_required"
    assert replay["counts"]["runtime_activity"]["p133_ack_write_count"] == 0
    assert "tamper_rejected:p133_ack_artifact_extra" in replay["command_notes"]


def test_terminal_replay_recomputes_recovery_from_fully_rehashed_durable_truth(tmp_path: Path) -> None:
    fixture = _fixture("P145-CASE-01")
    first = process_episode_fixture(fixture, output_dir=tmp_path).as_dict()
    assert first["terminal_status"] == "recovery_verified"
    case_dir = tmp_path / "P145-CASE-01"

    lab_path = case_dir / "fault-lab-state.json"
    lab = json.loads(lab_path.read_text(encoding="utf-8"))
    lab["error_rate_bps"] = 9000
    lab["state_hash"] = stable_hash({key: value for key, value in lab.items() if key != "state_hash"})
    _write_canonical_json(lab_path, lab)

    journal_path = case_dir / "journal.jsonl"
    entries = [json.loads(line) for line in journal_path.read_text(encoding="utf-8").splitlines()]
    observation_hashes: list[str] = []
    for entry in entries:
        payload = entry["payload"]
        if entry["phase"] == "lab_mutated":
            payload["post_state_hash"] = lab["state_hash"]
        elif entry["phase"] == "action_receipt_committed":
            payload["post_state_hash"] = lab["state_hash"]
            payload["receipt_hash"] = stable_hash(
                {key: value for key, value in payload.items() if key != "receipt_hash"}
            )
        elif entry["phase"] == "observation_committed":
            payload["state_hash"] = lab["state_hash"]
            payload["signals"]["error_rate_bps"] = lab["error_rate_bps"]
            payload["observation_hash"] = stable_hash(
                {key: value for key, value in payload.items() if key != "observation_hash"}
            )
            observation_hashes.append(payload["observation_hash"])
        elif entry["phase"] == "recovery_receipt_committed":
            payload["current_state_hash"] = lab["state_hash"]
            payload["observation_hashes"] = observation_hashes
            payload["recovered"] = True
            payload["blockers"] = []
            payload["recovery_proof_hash"] = stable_hash(
                {key: value for key, value in payload.items() if key != "recovery_proof_hash"}
            )
    _rewrite_rehashed_journal(journal_path, entries)

    cursor_path = case_dir / "cursor.json"
    cursor = json.loads(cursor_path.read_text(encoding="utf-8"))
    cursor["terminal_receipt_hash"] = entries[-1]["receipt_hash"]
    cursor["cursor_hash"] = stable_hash({key: value for key, value in cursor.items() if key != "cursor_hash"})
    _write_canonical_json(cursor_path, cursor)

    replay = process_episode_fixture(fixture, output_dir=tmp_path).as_dict()
    assert replay["terminal_status"] == "human_escalation_required"
    assert replay["counts"]["lab_activity"]["action_commit_count"] == 0
    assert replay["counts"]["lab_activity"]["lab_state_mutation_count"] == 0
    assert any("terminal_truth" in note for note in replay["command_notes"])
    assert (case_dir / "journal.jsonl.rejected").exists() or (case_dir / "journal.rejected.jsonl").exists()


def test_terminal_replay_rejects_fully_rehashed_verification_predecessor_reorder(tmp_path: Path) -> None:
    fixture = _fixture("P145-CASE-01")
    process_episode_fixture(fixture, output_dir=tmp_path)
    case_dir = tmp_path / fixture["case_id"]
    journal_path = case_dir / "journal.jsonl"
    entries = [json.loads(line) for line in journal_path.read_text(encoding="utf-8").splitlines()]
    verification_index = next(index for index, entry in enumerate(entries) if entry["phase"] == "verification_started")
    observation_index = next(index for index, entry in enumerate(entries) if entry["phase"] == "observation_committed")
    entries[verification_index], entries[observation_index] = entries[observation_index], entries[verification_index]
    _rewrite_rehashed_journal(journal_path, entries)
    cursor_path = case_dir / "cursor.json"
    cursor = json.loads(cursor_path.read_text(encoding="utf-8"))
    cursor["terminal_receipt_hash"] = entries[-1]["receipt_hash"]
    cursor["cursor_hash"] = stable_hash({key: value for key, value in cursor.items() if key != "cursor_hash"})
    _write_canonical_json(cursor_path, cursor)

    replay = process_episode_fixture(fixture, output_dir=tmp_path).as_dict()
    assert replay["terminal_status"] == "human_escalation_required"
    assert replay["counts"]["lab_activity"]["action_commit_count"] == 0
    assert any("terminal_sequence_invalid" in note for note in replay["command_notes"])


@pytest.mark.parametrize("case_id", ["P145-CASE-01", "P145-CASE-10", "P145-CASE-11"])
def test_terminal_replay_requires_complete_policy_to_terminal_sequence(
    case_id: str, tmp_path: Path,
) -> None:
    fixture = _fixture(case_id)
    process_episode_fixture(fixture, output_dir=tmp_path / case_id)
    case_dir = tmp_path / case_id / case_id
    journal_path = case_dir / "journal.jsonl"
    entries = [json.loads(line) for line in journal_path.read_text(encoding="utf-8").splitlines()]
    entries = [entry for entry in entries if entry["phase"] != "local_policy_authorized"]
    _rewrite_rehashed_journal(journal_path, entries)
    _rebind_cursor_to_entries(case_dir, entries)

    replay = process_episode_fixture(fixture, output_dir=tmp_path / case_id).as_dict()
    assert replay["terminal_status"] == "human_escalation_required"
    assert replay["counts"]["lab_activity"]["action_commit_count"] == 0
    assert any("terminal_sequence" in note for note in replay["command_notes"])


def test_terminal_replay_rejects_rehashed_cross_branch_verification_sequence(tmp_path: Path) -> None:
    fixture = _fixture("P145-CASE-01")
    process_episode_fixture(fixture, output_dir=tmp_path)
    case_dir = tmp_path / fixture["case_id"]
    journal_path = case_dir / "journal.jsonl"
    entries = [json.loads(line) for line in journal_path.read_text(encoding="utf-8").splitlines()]
    moved_phases = {"verification_started", "observation_committed"}
    moved = [entry for entry in entries if entry["phase"] in moved_phases]
    remaining = [entry for entry in entries if entry["phase"] not in moved_phases]
    insert_at = next(index for index, entry in enumerate(remaining) if entry["phase"] == "local_policy_authorized")
    entries = remaining[:insert_at] + moved + remaining[insert_at:]
    _rewrite_rehashed_journal(journal_path, entries)
    _rebind_cursor_to_entries(case_dir, entries)

    replay = process_episode_fixture(fixture, output_dir=tmp_path).as_dict()
    assert replay["terminal_status"] == "human_escalation_required"
    assert replay["counts"]["lab_activity"]["action_commit_count"] == 0
    assert any("terminal_sequence" in note for note in replay["command_notes"])


@pytest.mark.parametrize(
    ("case_id", "ack_name", "phase"),
    [
        ("P145-CASE-01", "p133-ack.json", "owned_acknowledged"),
        ("P145-CASE-45", "p133-ack-correlated.json", "correlated_owned_acknowledged"),
    ],
)
def test_terminal_replay_rejects_rehashed_ack_lease_owner_drift(
    case_id: str, ack_name: str, phase: str, tmp_path: Path,
) -> None:
    fixture = _fixture(case_id)
    process_episode_fixture(fixture, output_dir=tmp_path / case_id)
    case_dir = tmp_path / case_id / case_id
    ack_path = case_dir / ack_name
    acknowledgement = json.loads(ack_path.read_text(encoding="utf-8"))
    acknowledgement["lease_owner"] = "forged-worker"
    acknowledgement["ack_hash"] = stable_hash({
        key: value for key, value in acknowledgement.items() if key != "ack_hash"
    })
    _write_canonical_json(ack_path, acknowledgement)
    journal_path = case_dir / "journal.jsonl"
    entries = [json.loads(line) for line in journal_path.read_text(encoding="utf-8").splitlines()]
    next(entry for entry in entries if entry["phase"] == phase)["payload"] = acknowledgement
    _rewrite_rehashed_journal(journal_path, entries)
    _rebind_cursor_to_entries(case_dir, entries)

    replay = process_episode_fixture(fixture, output_dir=tmp_path / case_id).as_dict()
    assert replay["terminal_status"] == "human_escalation_required"
    assert replay["counts"]["lab_activity"]["action_commit_count"] == 0
    assert any("lease" in note and "ack" in note for note in replay["command_notes"])


def test_acknowledgement_epoch_and_cas_are_bound_to_persisted_lease_history(tmp_path: Path) -> None:
    fixture = _fixture("P145-CASE-01")
    process_episode_fixture(fixture, output_dir=tmp_path)
    case_dir = tmp_path / fixture["case_id"]
    acknowledgement = json.loads((case_dir / "p133-ack.json").read_text(encoding="utf-8"))
    assert {
        "lease_epoch", "lease_cas_version", "lease_receipt_hash",
    } <= set(acknowledgement)
    lease = json.loads((case_dir / "lease.json").read_text(encoding="utf-8"))
    assert any(
        receipt["owner_id"] == acknowledgement["lease_owner"]
        and receipt["epoch"] == acknowledgement["lease_epoch"]
        and receipt["cas_version"] == acknowledgement["lease_cas_version"]
        and receipt["receipt_hash"] == acknowledgement["lease_receipt_hash"]
        for receipt in lease["ownership_history"]
    )

    acknowledgement["lease_cas_version"] += 1
    acknowledgement["ack_hash"] = stable_hash({
        key: value for key, value in acknowledgement.items() if key != "ack_hash"
    })
    _write_canonical_json(case_dir / "p133-ack.json", acknowledgement)
    journal_path = case_dir / "journal.jsonl"
    entries = [json.loads(line) for line in journal_path.read_text(encoding="utf-8").splitlines()]
    next(entry for entry in entries if entry["phase"] == "owned_acknowledged")["payload"] = acknowledgement
    _rewrite_rehashed_journal(journal_path, entries)
    _rebind_cursor_to_entries(case_dir, entries)

    replay = process_episode_fixture(fixture, output_dir=tmp_path).as_dict()
    assert replay["terminal_status"] == "human_escalation_required"
    assert any("ack" in note and "lease" in note for note in replay["command_notes"])


@pytest.mark.parametrize("field", ["episode_id", "case_id"])
def test_terminal_replay_rejects_rehashed_cursor_identity_drift(field: str, tmp_path: Path) -> None:
    fixture = _fixture("P145-CASE-01")
    process_episode_fixture(fixture, output_dir=tmp_path / field)
    cursor_path = tmp_path / field / fixture["case_id"] / "cursor.json"
    cursor = json.loads(cursor_path.read_text(encoding="utf-8"))
    cursor[field] = "sha256:" + "f" * 64 if field == "episode_id" else "P145-CASE-48"
    cursor["cursor_hash"] = stable_hash({key: value for key, value in cursor.items() if key != "cursor_hash"})
    _write_canonical_json(cursor_path, cursor)

    replay = process_episode_fixture(fixture, output_dir=tmp_path / field).as_dict()
    assert replay["terminal_status"] == "human_escalation_required"
    assert replay["counts"]["lab_activity"]["action_commit_count"] == 0
    assert any("cursor_identity" in note for note in replay["command_notes"])


@pytest.mark.parametrize("artifact", ["lease", "lab", "cursor", "crash"])
def test_terminal_replay_rejects_rehashed_unknown_side_artifact_fields(
    artifact: str, tmp_path: Path,
) -> None:
    fixture = _fixture("P145-CASE-13" if artifact == "crash" else "P145-CASE-01")
    first = process_episode_fixture(fixture, output_dir=tmp_path / artifact).as_dict()
    assert first["terminal_status"] == "recovery_verified"
    case_dir = tmp_path / artifact / fixture["case_id"]
    paths = {
        "lease": (case_dir / "lease.json", "lease_hash"),
        "lab": (case_dir / "fault-lab-state.json", "state_hash"),
        "cursor": (case_dir / "cursor.json", "cursor_hash"),
        "crash": (case_dir / "crash-state.json", "crash_hash"),
    }
    path, hash_field = paths[artifact]
    value = json.loads(path.read_text(encoding="utf-8"))
    value["external_approval"] = True
    value[hash_field] = stable_hash({key: item for key, item in value.items() if key != hash_field})
    _write_canonical_json(path, value)

    replay = process_episode_fixture(fixture, output_dir=tmp_path / artifact).as_dict()
    assert replay["terminal_status"] == "human_escalation_required"
    assert replay["counts"]["lab_activity"]["action_commit_count"] == 0
    assert any("tamper_rejected" in note for note in replay["command_notes"])


def test_terminal_replay_quarantines_malformed_side_artifact_json(tmp_path: Path) -> None:
    fixture = _fixture("P145-CASE-01")
    process_episode_fixture(fixture, output_dir=tmp_path)
    lease_path = tmp_path / fixture["case_id"] / "lease.json"
    lease_path.write_text("{not-json}\n", encoding="utf-8")

    replay = process_episode_fixture(fixture, output_dir=tmp_path).as_dict()
    assert replay["terminal_status"] == "human_escalation_required"
    assert replay["counts"]["lab_activity"]["action_commit_count"] == 0
    assert any("corrupt_json:lease.json" in note for note in replay["command_notes"])


@pytest.mark.parametrize("mutation", ["unknown_field", "reason_drift"])
def test_escalation_side_receipt_requires_closed_schema_and_journal_projection(
    mutation: str, tmp_path: Path,
) -> None:
    fixture = _fixture("P145-CASE-07")
    first = process_episode_fixture(fixture, output_dir=tmp_path / mutation).as_dict()
    assert first["terminal_status"] == "human_escalation_required"
    case_dir = tmp_path / mutation / "P145-CASE-07"
    entries = [json.loads(line) for line in (case_dir / "journal.jsonl").read_text(encoding="utf-8").splitlines()]
    receipt = deepcopy(next(entry["payload"] for entry in entries if entry["phase"] == "escalation_receipt_committed"))
    if mutation == "unknown_field":
        receipt["provider_approval"] = True
    else:
        receipt["reason"] = "operator_approved"
    receipt["receipt_hash"] = stable_hash({key: value for key, value in receipt.items() if key != "receipt_hash"})
    _write_canonical_json(case_dir / "escalation-receipt.json", receipt)

    replay = process_episode_fixture(fixture, output_dir=tmp_path / mutation).as_dict()
    assert replay["terminal_status"] == "human_escalation_required"
    assert replay["counts"]["lab_activity"]["action_commit_count"] == 0
    assert any("escalation_receipt" in note and "tamper" in note for note in replay["command_notes"])


def test_terminal_replay_rejects_fully_rehashed_escalation_reason_drift(tmp_path: Path) -> None:
    fixture = _fixture("P145-CASE-07")
    first = process_episode_fixture(fixture, output_dir=tmp_path).as_dict()
    assert first["terminal_status"] == "human_escalation_required"
    case_dir = tmp_path / fixture["case_id"]
    journal_path = case_dir / "journal.jsonl"
    entries = [json.loads(line) for line in journal_path.read_text(encoding="utf-8").splitlines()]
    escalation = next(entry for entry in entries if entry["phase"] == "escalation_receipt_committed")
    escalation["payload"]["reason"] = "operator_approved"
    escalation["payload"]["receipt_hash"] = stable_hash({
        key: value for key, value in escalation["payload"].items() if key != "receipt_hash"
    })
    _rewrite_rehashed_journal(journal_path, entries)
    cursor_path = case_dir / "cursor.json"
    cursor = json.loads(cursor_path.read_text(encoding="utf-8"))
    cursor["terminal_receipt_hash"] = entries[-1]["receipt_hash"]
    cursor["cursor_hash"] = stable_hash({key: value for key, value in cursor.items() if key != "cursor_hash"})
    _write_canonical_json(cursor_path, cursor)

    replay = process_episode_fixture(fixture, output_dir=tmp_path).as_dict()
    assert replay["terminal_status"] == "human_escalation_required"
    assert replay["counts"]["lab_activity"]["action_commit_count"] == 0
    assert any("escalation_receipt_reason_drift" in note for note in replay["command_notes"])


def test_terminal_replay_rejects_rehashed_lease_owner_drift(tmp_path: Path) -> None:
    fixture = _fixture("P145-CASE-01")
    process_episode_fixture(fixture, output_dir=tmp_path)
    lease_path = tmp_path / fixture["case_id"] / "lease.json"
    lease = json.loads(lease_path.read_text(encoding="utf-8"))
    lease["owner_id"] = "unbound-worker"
    lease["lease_hash"] = stable_hash({key: value for key, value in lease.items() if key != "lease_hash"})
    _write_canonical_json(lease_path, lease)

    replay = process_episode_fixture(fixture, output_dir=tmp_path).as_dict()
    assert replay["terminal_status"] == "human_escalation_required"
    assert replay["counts"]["lab_activity"]["action_commit_count"] == 0
    assert any("lease_ownership_history_projection_invalid" in note for note in replay["command_notes"])


def test_primary_event_correlation_requires_correlated_duplicate_mode(tmp_path: Path) -> None:
    fixture = deepcopy(_fixture("P145-CASE-01"))
    fixture["p133_event"]["correlation_id"] = "sha256:" + "c" * 64
    fixture["p133_event"]["event_hash"] = stable_hash(
        {key: value for key, value in fixture["p133_event"].items() if key != "event_hash"}
    )
    _rehash_fixture_evidence(fixture)
    _assert_rejected_before_ownership(fixture, tmp_path, "input_schema_invalid:p133_event")


def test_correlated_duplicate_requires_exact_rehashed_primary_correlation(tmp_path: Path) -> None:
    fixture = deepcopy(_fixture("P145-CASE-45"))
    fixture["p133_event"]["correlation_id"] = "sha256:" + "d" * 64
    fixture["p133_event"]["event_hash"] = stable_hash(
        {key: value for key, value in fixture["p133_event"].items() if key != "event_hash"}
    )
    _rehash_fixture_evidence(fixture)
    _assert_rejected_before_ownership(fixture, tmp_path, "correlated_p133_binding_invalid")


def test_local_escalation_receipt_corruption_fails_closed(tmp_path: Path) -> None:
    assert _assert_case("P145-CASE-46", tmp_path)["terminal_status"] == "human_escalation_required"


def test_unknown_schema_field_and_authority_word_rejected(tmp_path: Path) -> None:
    fixture = _fixture("P145-CASE-47")
    assert fixture["evidence"]["external_approval"] == {"approved": True}
    result = _assert_rejected_before_ownership(fixture, tmp_path, "input_schema_invalid:evidence")
    record_pytest_case_result(result)


@pytest.mark.parametrize(
    ("component", "field"),
    [
        ("p133_event", "external_approval"),
        ("evidence", "provider_sdk_call"),
        ("policy", "production_mutation"),
    ],
)
def test_unknown_authority_like_nested_fields_fail_before_ack_or_action(
    component: str, field: str, tmp_path: Path,
) -> None:
    fixture = deepcopy(_fixture("P145-CASE-01"))
    fixture[component][field] = {"enabled": True}
    if component == "p133_event":
        event = fixture[component]
        event["event_hash"] = stable_hash({key: value for key, value in event.items() if key != "event_hash"})
    if component in {"p133_event", "evidence"}:
        _rehash_fixture_evidence(fixture)
    else:
        _rehash_fixture(fixture)
    _assert_rejected_before_ownership(fixture, tmp_path / component, f"input_schema_invalid:{component}")


@pytest.mark.parametrize(
    ("component", "field", "value"),
    [
        ("p133_event", "sequence", True),
        ("evidence", "fresh", 1),
        ("policy", "action_budget", 3),
    ],
)
def test_nested_required_types_and_ranges_fail_before_ack_or_action(
    component: str, field: str, value: object, tmp_path: Path,
) -> None:
    fixture = deepcopy(_fixture("P145-CASE-01"))
    fixture[component][field] = value
    if component == "p133_event":
        event = fixture[component]
        event["event_hash"] = stable_hash({key: item for key, item in event.items() if key != "event_hash"})
    if component in {"p133_event", "evidence"}:
        _rehash_fixture_evidence(fixture)
    else:
        _rehash_fixture(fixture)
    _assert_rejected_before_ownership(fixture, tmp_path / component, f"input_schema_invalid:{component}")


@pytest.mark.parametrize(
    ("case_id", "component", "field"),
    [
        ("P145-CASE-01", "p133_event", "event_id"),
        ("P145-CASE-01", "evidence", "fresh"),
        ("P145-CASE-01", "policy", "allowed"),
        ("P145-CASE-45", "correlated_p133_event", "correlation_id"),
    ],
)
def test_missing_required_nested_fields_fail_before_ack_or_action(
    case_id: str, component: str, field: str, tmp_path: Path,
) -> None:
    fixture = deepcopy(_fixture(case_id))
    target = fixture[component]
    assert isinstance(target, dict)
    target.pop(field)
    if component in {"p133_event", "correlated_p133_event"}:
        target["event_hash"] = stable_hash({key: item for key, item in target.items() if key != "event_hash"})
    if component in {"p133_event", "correlated_p133_event", "evidence"}:
        _rehash_fixture_evidence(fixture)
    else:
        _rehash_fixture(fixture)
    _assert_rejected_before_ownership(fixture, tmp_path / component, f"input_schema_invalid:{component}")


def test_correlated_event_unknown_field_and_domain_enum_fail_before_ownership(tmp_path: Path) -> None:
    for name, mutation in (
        ("unknown", ("external_message_send", True)),
        ("domain", ("domain", "external_provider")),
    ):
        fixture = deepcopy(_fixture("P145-CASE-45"))
        event = fixture["correlated_p133_event"]
        assert isinstance(event, dict)
        field, value = mutation
        event[field] = value
        event["event_hash"] = stable_hash({key: item for key, item in event.items() if key != "event_hash"})
        _rehash_fixture_evidence(fixture)
        _assert_rejected_before_ownership(
            fixture, tmp_path / name, "input_schema_invalid:correlated_p133_event"
        )


@pytest.mark.parametrize("component", ["predecessor_bindings", "source_profile_bindings"])
def test_nested_binding_unknown_fields_fail_before_ownership(component: str, tmp_path: Path) -> None:
    fixture = deepcopy(_fixture("P145-CASE-01"))
    fixture[component]["external_approval"] = "sha256:" + "a" * 64
    _rehash_fixture_evidence(fixture)
    _assert_rejected_before_ownership(fixture, tmp_path / component, f"input_schema_invalid:{component}")


def test_hypothesis_unknown_nested_field_fails_before_ownership(tmp_path: Path) -> None:
    fixture = deepcopy(_fixture("P145-CASE-01"))
    fixture["hypotheses"][0]["operator_command"] = "run-provider-remediation"
    _rehash_fixture(fixture)
    _assert_rejected_before_ownership(fixture, tmp_path, "input_schema_invalid:hypotheses")


def test_expected_comparison_and_lab_state_nested_schemas_are_closed(tmp_path: Path) -> None:
    expected = deepcopy(_fixture("P145-CASE-01"))
    expected["expected_counts"]["runtime_activity"]["external_approval_count"] = 0
    with pytest.raises(P145DutyOfficerError, match="invalid_expected_counts"):
        validate_case_fixture(_rehash_fixture(expected))

    lab = deepcopy(_fixture("P145-CASE-01"))
    lab["initial_lab_state"]["shell_command"] = "forbidden"
    lab["initial_lab_state"]["state_hash"] = stable_hash(
        {key: value for key, value in lab["initial_lab_state"].items() if key != "state_hash"}
    )
    with pytest.raises(P145DutyOfficerError, match="invalid_fault_lab_state_schema"):
        process_episode_fixture(_rehash_fixture(lab), output_dir=tmp_path / "lab")


def test_conflicting_existing_p133_ack_fails_closed(tmp_path: Path) -> None:
    result = _assert_case("P145-CASE-48", tmp_path)
    assert result["counts"]["runtime_activity"]["p133_ack_write_count"] == 0
    assert "p133_ack_cas_conflict" in result["command_notes"]
    ack = json.loads((tmp_path / "P145-CASE-48" / "p133-ack.json").read_text(encoding="utf-8"))
    assert ack["event_id"] == "conflicting-event"


@pytest.mark.parametrize(
    "case_id",
    [
        "P145-CASE-13",
        "P145-CASE-14",
        "P145-CASE-36",
        "P145-CASE-37",
        "P145-CASE-38",
        "P145-CASE-39",
        "P145-CASE-40",
        "P145-CASE-41",
        "P145-CASE-42",
        "P145-CASE-43",
        "P145-CASE-44",
    ],
)
def test_crash_windows_reload_fresh_controller_without_duplicate_receipts(case_id: str, tmp_path: Path) -> None:
    result = _assert_case(case_id, tmp_path)
    assert "controller_restarted" in result["command_notes"]
    assert result["counts"]["runtime_activity"]["p133_ack_write_count"] <= 1
    assert result["counts"]["lab_activity"]["duplicate_action_count"] == 0
    phases = result["phase_path"]
    assert phases.count("owned_acknowledged") <= 1
    action_ids = [
        json.loads(line)["payload"]["action_id"]
        for line in Path(result["journal_path"]).read_text(encoding="utf-8").splitlines()
        if json.loads(line)["phase"] == "action_receipt_committed"
    ]
    assert len(action_ids) == len(set(action_ids))


def test_all_terminals_have_required_durable_predecessor(tmp_path: Path) -> None:
    predecessors = {
        "recovery_verified": "recovery_receipt_committed",
        "rollback_verified": "rollback_receipt_committed",
        "human_escalation_required": "escalation_receipt_committed",
    }
    for case_id in CASE_SELECTOR_NAMES:
        result = process_episode_fixture(_fixture(case_id), output_dir=tmp_path / case_id).as_dict()
        assert result["phase_path"][-2] == predecessors[result["terminal_status"]]
        assert result["phase_path"][-1] == result["terminal_status"]
