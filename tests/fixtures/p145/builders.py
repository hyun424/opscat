from __future__ import annotations

import json
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p145_response_duty_officer import (
    CASE_SCHEMA_VERSION,
    CASE_SELECTOR_NAMES,
    PREDECESSOR_BINDINGS,
    expected_source_profile_bindings,
    initial_fault_lab_state,
    process_episode_fixture,
)
from app.services.p145_runner import p145_release_case_catalog


def build_case_fixture(case_id: str) -> dict[str, Any]:
    case = {item["case_id"]: item for item in p145_release_case_catalog()}[case_id]
    behavior = _case_behavior(case_id)
    event = {
        "schema_version": "p133.deadman_event.v1",
        "event_id": stable_hash({"p145_event": case_id}),
        "incident_id": f"incident-{case_id.lower()}",
        "sequence": int(case_id.rsplit("-", 1)[1]),
        "domain": "security" if case_id == "P145-CASE-20" else "local_fault_lab",
        "event_hash": "",
    }
    correlated_event: dict[str, Any] | None = None
    if case_id == "P145-CASE-45":
        correlation_id = stable_hash({"p145_correlation": case_id})
        event["correlation_id"] = correlation_id
        correlated_event = {
            "schema_version": "p133.deadman_event.v1",
            "event_id": stable_hash({"p145_event": case_id, "correlated_duplicate": 2}),
            "incident_id": f"incident-{case_id.lower()}-correlated",
            "sequence": int(case_id.rsplit("-", 1)[1]) + 1,
            "domain": "local_fault_lab",
            "correlation_id": correlation_id,
            "event_hash": "",
        }
        correlated_event["event_hash"] = stable_hash(
            {key: value for key, value in correlated_event.items() if key != "event_hash"}
        )
    event["event_hash"] = stable_hash({key: value for key, value in event.items() if key != "event_hash"})
    if case_id == "P145-CASE-21":
        event["event_hash"] = "sha256:" + "e" * 64

    state = _initial_state(case_id, behavior["selected_action"])
    evidence = {
        "schema_valid": True,
        "hash_valid": True,
        "fresh": True,
        "support_complete": True,
        "contradiction_absent": True,
        "critical_missing_evidence": False,
        "prompt_injection_present": False,
        "confidence_margin_bps": 1600,
        "minimum_margin_bps": 1000,
        "prior_memory_poisoned": case_id == "P145-CASE-19",
    }
    evidence.update(behavior.pop("evidence"))
    policy = {
        "allowed": True,
        "blast_radius_bps": 100,
        "max_blast_radius_bps": 500,
        "action_budget": 2,
        "rollback_metadata_present": True,
        "preflight_passed": True,
    }
    policy.update(behavior.pop("policy"))
    source_bindings = expected_source_profile_bindings(case["selector"])
    fixture: dict[str, Any] = {
        "schema_version": CASE_SCHEMA_VERSION,
        "case_id": case_id,
        "scenario": case["scenario"],
        "selector": case["selector"],
        "episode_id": stable_hash({"episode": case_id}),
        "branch": behavior.pop("branch"),
        "p133_event": event,
        "correlated_p133_event": correlated_event,
        "predecessor_bindings": deepcopy(PREDECESSOR_BINDINGS),
        "source_profile_bindings": source_bindings,
        "evidence": evidence,
        "evidence_hash": stable_hash({
            "event": event,
            "correlated_event": correlated_event,
            "predecessor_bindings": PREDECESSOR_BINDINGS,
            "source_profile_bindings": source_bindings,
            "evidence": evidence,
        }),
        "initial_lab_state": state,
        "hypotheses": [
            {"name": "deploy_regression", "confidence_bps": 6800, "support": ["fresh_observation"], "contradictions": []},
            {"name": "pool_saturation", "confidence_bps": 5200, "support": ["competing_signal"], "contradictions": []},
        ],
        "policy": policy,
        **behavior,
        "expected_terminal_status": case["expected_terminal_status"],
        "expected_phase_path": ["evaluator_placeholder"],
        "expected_crash_point": behavior["fault_injection"],
        "expected_counts": {},
        "fixture_hash": "",
    }
    fixture["fixture_hash"] = stable_hash({key: value for key, value in fixture.items() if key != "fixture_hash"})
    return fixture


def write_case_fixtures(root: Path) -> None:
    case_dir = root / "tests/fixtures/p145/cases"
    case_dir.mkdir(parents=True, exist_ok=True)
    for case_id in CASE_SELECTOR_NAMES:
        fixture = build_case_fixture(case_id)
        with tempfile.TemporaryDirectory(prefix="p145-fixture-") as temporary:
            observed = process_episode_fixture(fixture, output_dir=Path(temporary)).as_dict()
        fixture["expected_terminal_status"] = observed["terminal_status"]
        fixture["expected_phase_path"] = observed["phase_path"]
        fixture["expected_crash_point"] = observed["crash_point"]
        fixture["expected_counts"] = observed["counts"]
        fixture["fixture_hash"] = stable_hash({key: value for key, value in fixture.items() if key != "fixture_hash"})
        (case_dir / f"{case_id}.json").write_text(
            json.dumps(fixture, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )


def _initial_state(case_id: str, action: str) -> dict[str, Any]:
    state = initial_fault_lab_state(f"resource-{case_id.lower()}")
    if action == "deploy_rollback":
        state.update({"error_rate_bps": 2400, "latency_ms": 220, "saturation_bps": 300, "backlog": 200, "dependency_timeout_bps": 100, "collateral_health_bps": 9900})
    elif action == "pool_recycle":
        state.update({"error_rate_bps": 100, "latency_ms": 120, "saturation_bps": 2500, "backlog": 200, "dependency_timeout_bps": 100, "collateral_health_bps": 9900})
    elif action == "fallback_enable":
        state.update({"error_rate_bps": 100, "latency_ms": 80, "saturation_bps": 300, "backlog": 200, "dependency_timeout_bps": 3200, "collateral_health_bps": 9900})
    elif action == "consumer_scale_local":
        state.update({"error_rate_bps": 100, "latency_ms": 60, "saturation_bps": 900, "backlog": 1800, "dependency_timeout_bps": 100, "collateral_health_bps": 9900})
        if case_id == "P145-CASE-45":
            state["backlog"] = 1200
    elif action == "load_shed_local":
        state.update({"error_rate_bps": 800, "latency_ms": 120, "saturation_bps": 300, "backlog": 900, "dependency_timeout_bps": 100, "collateral_health_bps": 9900})
    else:
        state.update({"error_rate_bps": 100, "latency_ms": 120, "saturation_bps": 300, "backlog": 200, "dependency_timeout_bps": 100, "collateral_health_bps": 9900})
    state["state_hash"] = stable_hash({key: value for key, value in state.items() if key != "state_hash"})
    return state


def _case_behavior(case_id: str) -> dict[str, Any]:
    behavior: dict[str, Any] = {
        "branch": "behavior_inputs",
        "selected_action": "deploy_rollback",
        "action_count": 1,
        "observation_mode": "healthy",
        "rollback_mode": "not_needed",
        "fault_injection": None,
        "tamper_mode": None,
        "lease_mode": "normal",
        "existing_ack": "none",
        "replay_mode": "none",
        "evidence": {},
        "policy": {},
    }
    if case_id == "P145-CASE-02":
        behavior["selected_action"] = "pool_recycle"
    elif case_id == "P145-CASE-03":
        behavior["selected_action"] = "fallback_enable"
    elif case_id in {"P145-CASE-04", "P145-CASE-45"}:
        behavior["selected_action"] = "consumer_scale_local"
        behavior["action_count"] = 2 if case_id == "P145-CASE-04" else 1
    elif case_id == "P145-CASE-05":
        behavior["selected_action"] = "observe_only"
        behavior["action_count"] = 0

    evidence_overrides = {
        "P145-CASE-06": {"contradiction_absent": False},
        "P145-CASE-07": {"fresh": False},
        "P145-CASE-08": {"prompt_injection_present": True},
        "P145-CASE-09": {"support_complete": False, "critical_missing_evidence": True},
        "P145-CASE-47": {"external_approval": {"approved": True}},
    }
    behavior["evidence"] = evidence_overrides.get(case_id, {})
    if case_id == "P145-CASE-12":
        behavior["policy"] = {"rollback_metadata_present": False}
    elif case_id == "P145-CASE-17":
        behavior["policy"] = {"action_budget": 0}

    observation_modes = {
        "P145-CASE-10": "harmful",
        "P145-CASE-11": "primary_only",
        "P145-CASE-25": "lab_drift",
        "P145-CASE-26": "harmful",
        "P145-CASE-27": "recurrence",
        "P145-CASE-28": "insufficient",
        "P145-CASE-29": "out_of_order",
        "P145-CASE-30": "gap",
        "P145-CASE-31": "clock_rollback",
        "P145-CASE-32": "flapping",
        "P145-CASE-33": "partial",
        "P145-CASE-34": "delayed_regression",
        "P145-CASE-35": "rollback_collateral_harm",
        "P145-CASE-38": "harmful",
        "P145-CASE-41": "harmful",
    }
    behavior["observation_mode"] = observation_modes.get(case_id, behavior["observation_mode"])
    if case_id in {"P145-CASE-10", "P145-CASE-34", "P145-CASE-35", "P145-CASE-37", "P145-CASE-38", "P145-CASE-41", "P145-CASE-43"}:
        behavior["rollback_mode"] = "succeed"
    elif case_id == "P145-CASE-26":
        behavior["rollback_mode"] = "fail"

    behavior["fault_injection"] = {
        "P145-CASE-13": "action_receipt",
        "P145-CASE-14": "before_action_commit",
        "P145-CASE-36": "lab_mutated_before_action_receipt",
        "P145-CASE-37": "action_receipt_before_fsync",
        "P145-CASE-38": "rollback_mutated_before_receipt",
        "P145-CASE-39": "terminal_receipt_before_cursor",
        "P145-CASE-40": "lease_expiry_during_verification",
        "P145-CASE-41": "lease_expiry_during_rollback",
        "P145-CASE-42": "journal_disk_full",
        "P145-CASE-43": "lab_fsync_failure",
        "P145-CASE-44": "cursor_fsync_failure",
    }.get(case_id)
    behavior["tamper_mode"] = {
        "P145-CASE-22": "journal_duplicate_phase",
        "P145-CASE-23": "terminal_reorder",
        "P145-CASE-24": "cursor_missing_predecessor",
        "P145-CASE-46": "escalation_receipt",
    }.get(case_id)
    if case_id == "P145-CASE-15":
        behavior["lease_mode"] = "contention"
    elif case_id == "P145-CASE-16":
        behavior["lease_mode"] = "dead_runner"
    elif case_id == "P145-CASE-40":
        behavior["lease_mode"] = "expire_verification"
    elif case_id == "P145-CASE-41":
        behavior["lease_mode"] = "expire_rollback"
    if case_id == "P145-CASE-18":
        behavior["replay_mode"] = "duplicate_terminal"
    elif case_id == "P145-CASE-45":
        behavior["replay_mode"] = "correlated_duplicate"
    if case_id == "P145-CASE-48":
        behavior["existing_ack"] = "conflict"
        behavior["action_count"] = 0
    if case_id in {"P145-CASE-20", "P145-CASE-21", "P145-CASE-22", "P145-CASE-23", "P145-CASE-24", "P145-CASE-46", "P145-CASE-47"}:
        behavior["action_count"] = 0
    return behavior
