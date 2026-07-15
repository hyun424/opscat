"""Authority-bounded P145 local response duty officer.

The runtime owns only local append-only journals, lease/CAS receipts, and a
process-owned fault-lab state. Evaluator expectations are accepted as fixture
metadata but are never read while an episode executes.
"""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from os import O_RDONLY, close, fsync, replace
from os import open as open_directory
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash

TERMINALS = frozenset({"recovery_verified", "rollback_verified", "human_escalation_required"})
CASE_SCHEMA_VERSION = "p145.release_case_fixture.v1"
JOURNAL_SCHEMA_VERSION = "p145.journal_entry.v1"
LAB_SCHEMA_VERSION = "p145.fault_lab_state.v1"
OBSERVATION_SCHEMA_VERSION = "p145.observation.v1"
LOCAL_POLICY_RECEIPT_SCHEMA_VERSION = "p145.local_policy_authorization_receipt.v1"
P133_ACK_SCHEMA_VERSION = "p145.p133_local_ownership_ack.v1"
P133_EVENT_SCHEMA_VERSION = "p133.deadman_event.v1"
CURSOR_SCHEMA_VERSION = "p145.cursor.v1"
LEASE_SCHEMA_VERSION = "p145.lease.v1"
CRASH_SCHEMA_VERSION = "p145.crash_state.v1"
ACTION_RECEIPT_SCHEMA_VERSION = "p145.action_receipt.v1"
ROLLBACK_RECEIPT_SCHEMA_VERSION = "p145.rollback_receipt.v1"
RECOVERY_PROOF_SCHEMA_VERSION = "p145.recovery_proof.v1"
ESCALATION_RECEIPT_SCHEMA_VERSION = "p145.escalation_receipt.v1"

APPROVED_PLAN_SHA256 = "sha256:72e3ce302020acd05061fecb178b5f5fbddadae751cf42be0dfc28e92edb8a3b"
APPROVED_TEST_SPEC_SHA256 = "sha256:72274365b622629154b4347ea3caff48bb4672076287c72165c19b01aeab8050"
APPROVED_PLAN_REVIEW_SHA256 = "sha256:d59b48335c6c265ca2d723aae6a739252eabab5db2438a03de428bd496a851e8"
APPROVED_PROFILE_SHA256 = "sha256:66f4fd5f27d7dd93a1bb6a1411068a35a592e6a583e5b6799f2c72bdcd31dfea"

PREDECESSOR_BINDINGS: dict[str, str] = {
    "p114_hypothesis_lattice_source": "sha256:21489964bc079ddab14c1f5598086e9e6e16744e50a4a1a6bec48b88281f9de8",
    "p115_outcome_qualified": "sha256:6651251c77265c4dca675f8aa7ce6ad077c477d1fc809e1d0a6aa9e47144419d",
    "p116_contract_ready": "sha256:9ce24fad9d1eba34da373efb058e9f13cfa7213cbc104e86f2a25ad4b4b2b3fb",
    "p117_outcome_qualified": "sha256:d78464fc832618e0178923122c65f8a51a60a846da066389780084562026f3f4",
    "p118_local_mock_sandbox_ready": "sha256:f678180d5006260e3f08cdb7f5e790b6a4f492888d8911acd9a7a4015b5f1fc4",
    "p119_local_closed_loop_ready": "sha256:c95b90e27d68a58592570d697294d13802720e671b8eadafb41cfcda4d323ec6",
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

FORBIDDEN_AUTHORITY_KEYS: tuple[str, ...] = (
    "credential_read_count", "authentication_attempt_count", "environment_read_count",
    "external_dns_resolution_count", "dns_socket_call_count", "non_loopback_socket_attempt_count",
    "external_http_request_count", "external_message_send_count", "tls_handshake_count",
    "proxy_use_count", "redirect_follow_count", "provider_sdk_call_count", "subprocess_shell_count",
    "arbitrary_command_execution_count", "external_approval_count", "ticket_creation_count",
    "staging_mutation_count", "production_mutation_count", "real_remediation_execution_count",
    "operator_replacement_count", "authority_escape_count",
)
RUNTIME_ACTIVITY_KEYS: tuple[str, ...] = (
    "journal_append_count", "journal_fsync_count", "directory_fsync_count", "lease_acquire_count",
    "lease_renew_count", "p133_ack_write_count", "heartbeat_write_count", "readiness_write_count",
    "cursor_write_count", "escalation_receipt_count",
)
LAB_ACTIVITY_KEYS: tuple[str, ...] = (
    "local_policy_authorization_count", "lab_state_read_count", "lab_state_mutation_count",
    "lab_state_fsync_count", "action_intent_count", "action_commit_count", "observation_count",
    "recovery_proof_count", "rollback_intent_count", "rollback_commit_count", "duplicate_action_count",
)
EVALUATOR_ACTIVITY_KEYS: tuple[str, ...] = (
    "runner_invocation_count", "profile_read_count", "fixture_write_count", "crash_injection_count",
    "artifact_write_count", "selector_command_count", "child_process_count", "signal_delivery_count",
)
RESOURCE_USAGE_KEYS: tuple[str, ...] = (
    "wall_time_ms", "cpu_time_ms", "child_cpu_time_ms", "peak_memory_kib", "open_file_count",
    "journal_bytes", "lab_bytes", "artifact_count",
)

TRANSFORMS: dict[str, dict[str, int]] = {
    "deploy_rollback": {"error_rate_bps": -2400, "latency_ms": -220, "collateral_health_bps": -100},
    "pool_recycle": {"saturation_bps": -2500, "latency_ms": -120, "collateral_health_bps": -50},
    "fallback_enable": {"dependency_timeout_bps": -3200, "latency_ms": -80, "collateral_health_bps": -150},
    "consumer_scale_local": {"backlog": -1200, "saturation_bps": -900, "latency_ms": -60, "collateral_health_bps": -75},
    "load_shed_local": {"backlog": -900, "error_rate_bps": -800, "collateral_health_bps": -200},
    "observe_only": {},
}
ACTION_HYPOTHESIS = {
    "deploy_rollback": "deploy_regression", "pool_recycle": "pool_saturation",
    "fallback_enable": "dependency_timeout", "consumer_scale_local": "queue_backlog",
    "load_shed_local": "traffic_surge", "observe_only": "natural_recovery",
}
PROTECTED_DOMAINS = frozenset({"auth", "authorization", "security", "credential", "destructive", "data_integrity", "unknown"})
ALLOWED_EVENT_DOMAINS = PROTECTED_DOMAINS | {"local_fault_lab"}
OBSERVATION_MODES = frozenset({
    "clock_rollback", "delayed_regression", "flapping", "gap", "harmful", "healthy", "insufficient",
    "lab_drift", "out_of_order", "partial", "primary_only", "recurrence", "rollback_collateral_harm",
    "stale_observation",
})
ROLLBACK_MODES = frozenset({"fail", "not_needed", "succeed"})
FAULT_INJECTION_MODES = frozenset({
    "action_receipt", "action_receipt_before_fsync", "before_action_commit", "cursor_fsync_failure",
    "journal_disk_full", "lab_fsync_failure", "lab_mutated_before_action_receipt",
    "lease_expiry_during_rollback", "lease_expiry_during_verification", "rollback_mutated_before_receipt",
    "terminal_receipt_before_cursor",
})
TAMPER_MODES = frozenset({"cursor_missing_predecessor", "escalation_receipt", "journal_duplicate_phase", "terminal_reorder"})
LEASE_MODES = frozenset({"contention", "dead_runner", "expire_rollback", "expire_verification", "normal"})
EXISTING_ACK_MODES = frozenset({"conflict", "none"})
REPLAY_MODES = frozenset({"correlated_duplicate", "duplicate_terminal", "none"})
EXPECTED_PHASES = frozenset({
    "action_intent_committed", "action_receipt_committed", "correlated_event_registered",
    "correlated_owned_acknowledged", "correlated_ownership_intent_committed",
    "correlation_action_receipt_committed", "deadman_handoff_committed", "escalation_receipt_committed",
    "evidence_validated", "human_escalation_required", "hypotheses_adjudicated", "lab_mutated",
    "local_policy_authorized", "observation_committed", "observe_only_authorized", "owned_acknowledged",
    "ownership_intent_committed", "preflight_blocked", "recovery_receipt_committed", "recovery_verified",
    "registered", "rollback_intent_committed", "rollback_lab_mutated", "rollback_receipt_committed",
    "rollback_verified", "verification_failed", "verification_started",
})
P133_EVENT_FIELDS = frozenset({"schema_version", "event_id", "incident_id", "sequence", "domain", "event_hash"})
EVIDENCE_FIELDS = frozenset({
    "schema_valid", "hash_valid", "fresh", "support_complete", "contradiction_absent",
    "critical_missing_evidence", "prompt_injection_present", "confidence_margin_bps",
    "minimum_margin_bps", "prior_memory_poisoned",
})
POLICY_FIELDS = frozenset({
    "allowed", "blast_radius_bps", "max_blast_radius_bps", "action_budget",
    "rollback_metadata_present", "preflight_passed",
})
SOURCE_PROFILE_BINDING_FIELDS = frozenset({
    "approved_plan_sha256", "approved_test_spec_sha256", "plan_review_sha256", "profile",
    "profile_sha256", "selector",
})
HYPOTHESIS_FIELDS = frozenset({"name", "confidence_bps", "support", "contradictions"})
_CASE_ID_RE = re.compile(r"P145-CASE-(?:0[1-9]|[1-3][0-9]|4[0-8])\Z")
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_ZERO_HASH = "sha256:" + "0" * 64
_JOURNAL_FIELDS = {
    "schema_version", "episode_id", "case_id", "cas_version", "phase", "logical_time",
    "payload", "payload_hash", "previous_receipt_hash", "receipt_hash",
}
_REPEATABLE_PHASES = {"action_intent_committed", "lab_mutated", "action_receipt_committed", "observation_committed"}
_OBSERVATION_FIELDS = frozenset({
    "schema_version", "sequence", "logical_time", "state_hash", "signals", "fresh", "observation_hash",
})
_OBSERVATION_SIGNAL_FIELDS = frozenset({
    "error_rate_bps", "latency_ms", "saturation_bps", "backlog",
    "dependency_timeout_bps", "collateral_health_bps",
})
_RECOVERY_PROOF_FIELDS = frozenset({
    "schema_version", "recovered", "blockers", "current_state_hash", "observation_hashes",
    "consecutive_required", "collateral_floor", "recovery_proof_hash",
})
_ESCALATION_RECEIPT_FIELDS = frozenset({"schema_version", "reason", "local_only", "receipt_hash"})
_CRASH_FIELDS = frozenset({"schema_version", "crash_point", "recovery_strategy", "crash_hash"})
_LEASE_HISTORY_FIELDS = frozenset({
    "event_id", "owner_id", "epoch", "cas_version", "active", "receipt_hash",
})
_TERMINAL_PREFIX = [
    "registered", "evidence_validated", "ownership_intent_committed",
    "owned_acknowledged", "hypotheses_adjudicated",
]
_CORRELATION_PHASES = [
    "correlated_event_registered", "correlated_ownership_intent_committed",
    "correlated_owned_acknowledged", "correlation_action_receipt_committed",
]


class P145DutyOfficerError(ValueError):
    """Raised when local state cannot be trusted."""


class _ControlledCrash(RuntimeError):
    def __init__(self, point: str) -> None:
        super().__init__(point)
        self.point = point


class _LeaseConflict(P145DutyOfficerError):
    pass


class _StorageFault(RuntimeError):
    def __init__(self, point: str) -> None:
        super().__init__(point)
        self.point = point


@dataclass(frozen=True)
class EpisodeResult:
    case_id: str
    scenario: str
    selector: str
    terminal_status: str
    phase_path: list[str]
    counts: dict[str, dict[str, int]]
    crash_point: str | None
    journal_path: str
    cursor_path: str
    ack_receipt_hash: str | None
    ack_receipt_hashes: list[str]
    policy_receipt_hash: str | None
    action_receipt_hashes: list[str]
    correlation_action_receipt: dict[str, Any] | None
    rollback_receipt_hash: str | None
    recovery_receipt_hash: str | None
    terminal_receipt_hash: str
    command_notes: list[str]
    result_hash: str

    def as_dict(self) -> dict[str, Any]:
        return deepcopy(self.__dict__)


def zero_forbidden_authority() -> dict[str, int]:
    return {key: 0 for key in FORBIDDEN_AUTHORITY_KEYS}


def zero_runtime_activity() -> dict[str, int]:
    return {key: 0 for key in RUNTIME_ACTIVITY_KEYS}


def zero_lab_activity() -> dict[str, int]:
    return {key: 0 for key in LAB_ACTIVITY_KEYS}


def zero_evaluator_activity() -> dict[str, int]:
    return {key: 0 for key in EVALUATOR_ACTIVITY_KEYS}


def zero_resource_usage() -> dict[str, int]:
    return {key: 0 for key in RESOURCE_USAGE_KEYS}


def exact_counter_map(value: Any, keys: tuple[str, ...], *, exact_zero: bool = False) -> bool:
    return isinstance(value, Mapping) and set(value) == set(keys) and all(
        type(value[key]) is int and value[key] >= 0 and (not exact_zero or value[key] == 0) for key in keys
    )


def expected_source_profile_bindings(selector: str) -> dict[str, str]:
    return {
        "approved_plan_sha256": APPROVED_PLAN_SHA256,
        "approved_test_spec_sha256": APPROVED_TEST_SPEC_SHA256,
        "plan_review_sha256": APPROVED_PLAN_REVIEW_SHA256,
        "profile": "p145-release",
        "profile_sha256": APPROVED_PROFILE_SHA256,
        "selector": selector,
    }


def initial_fault_lab_state(resource_id: str = "p145-local-service") -> dict[str, Any]:
    state: dict[str, Any] = {
        "schema_version": LAB_SCHEMA_VERSION, "resource_id": resource_id, "generation": 0,
        "error_rate_bps": 2600, "latency_ms": 520, "saturation_bps": 2200, "backlog": 1600,
        "dependency_timeout_bps": 1800, "collateral_health_bps": 9900,
        "last_action_id": None, "observation_seq": 0,
    }
    state["state_hash"] = _self_hash(state, "state_hash")
    return state


def validate_fault_lab_state(state: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(state))
    expected = {
        "schema_version", "resource_id", "generation", "error_rate_bps", "latency_ms", "saturation_bps",
        "backlog", "dependency_timeout_bps", "collateral_health_bps", "last_action_id", "observation_seq", "state_hash",
    }
    if set(value) != expected or value.get("schema_version") != LAB_SCHEMA_VERSION:
        raise P145DutyOfficerError("invalid_fault_lab_state_schema")
    if not isinstance(value.get("resource_id"), str) or not value["resource_id"]:
        raise P145DutyOfficerError("invalid_fault_lab_resource")
    for key, low, high in (
        ("generation", 0, None), ("error_rate_bps", 0, 10000), ("latency_ms", 0, None),
        ("saturation_bps", 0, 10000), ("backlog", 0, None), ("dependency_timeout_bps", 0, 10000),
        ("collateral_health_bps", 0, 10000), ("observation_seq", 0, None),
    ):
        if type(value.get(key)) is not int or value[key] < low or (high is not None and value[key] > high):
            raise P145DutyOfficerError(f"invalid_fault_lab_integer:{key}")
    if value.get("last_action_id") is not None and not isinstance(value.get("last_action_id"), str):
        raise P145DutyOfficerError("invalid_last_action_id")
    if value.get("state_hash") != _self_hash(value, "state_hash"):
        raise P145DutyOfficerError("fault_lab_state_hash_invalid")
    return value


def apply_lab_transform(state: Mapping[str, Any], action: str, *, action_id: str) -> dict[str, Any]:
    if action not in TRANSFORMS or action == "observe_only":
        raise P145DutyOfficerError("unsupported_lab_transform")
    current = validate_fault_lab_state(state)
    for key, delta in TRANSFORMS[action].items():
        current[key] = _bounded_signal(key, int(current[key]) + delta)
    current["generation"] += 1
    current["last_action_id"] = action_id
    current["observation_seq"] += 1
    current["state_hash"] = _self_hash(current, "state_hash")
    return current


def rollback_lab_transform(state: Mapping[str, Any], pre_state: Mapping[str, Any], *, action_id: str) -> dict[str, Any]:
    current = validate_fault_lab_state(state)
    restored = validate_fault_lab_state(pre_state)
    restored["generation"] = current["generation"] + 1
    restored["last_action_id"] = f"rollback:{action_id}"
    restored["observation_seq"] = current["observation_seq"] + 1
    restored["state_hash"] = _self_hash(restored, "state_hash")
    return restored


def build_observation(state: Mapping[str, Any], *, logical_time: int, stale: bool = False) -> dict[str, Any]:
    current = validate_fault_lab_state(state)
    observation: dict[str, Any] = {
        "schema_version": OBSERVATION_SCHEMA_VERSION, "sequence": current["observation_seq"],
        "logical_time": logical_time, "state_hash": current["state_hash"],
        "signals": {key: current[key] for key in (
            "error_rate_bps", "latency_ms", "saturation_bps", "backlog",
            "dependency_timeout_bps", "collateral_health_bps",
        )},
        "fresh": not stale,
    }
    observation["observation_hash"] = _self_hash(observation, "observation_hash")
    return observation


def verify_recovery(
    state: Mapping[str, Any], observations: list[dict[str, Any]], *, consecutive_required: int = 2,
    collateral_floor: int = 9500,
) -> dict[str, Any]:
    current = validate_fault_lab_state(state)
    blockers: list[str] = []
    if len(observations) < consecutive_required:
        blockers.append("insufficient_consecutive_observations")
    previous_seq: int | None = None
    previous_time: int | None = None
    successes = 0
    validated: list[dict[str, Any]] = []
    for raw in observations:
        observation = _validate_observation(raw)
        validated.append(observation)
        if previous_seq is not None and observation["sequence"] != previous_seq + 1:
            blockers.append("observation_gap_or_reorder")
        if previous_time is not None and observation["logical_time"] <= previous_time:
            blockers.append("clock_rollback")
        previous_seq = int(observation["sequence"])
        previous_time = int(observation["logical_time"])
        signals = observation["signals"]
        healthy = (
            signals["error_rate_bps"] <= 500 and signals["latency_ms"] <= 250
            and signals["saturation_bps"] <= 800 and signals["backlog"] <= 500
            and signals["dependency_timeout_bps"] <= 500
            and signals["collateral_health_bps"] >= collateral_floor and observation["fresh"] is True
        )
        successes = successes + 1 if healthy else 0
    if validated and validated[-1]["state_hash"] != current["state_hash"]:
        blockers.append("current_state_hash_mismatch")
    proof: dict[str, Any] = {
        "schema_version": RECOVERY_PROOF_SCHEMA_VERSION, "recovered": successes >= consecutive_required and not blockers,
        "blockers": sorted(set(blockers)), "current_state_hash": current["state_hash"],
        "observation_hashes": [item["observation_hash"] for item in validated],
        "consecutive_required": consecutive_required, "collateral_floor": collateral_floor,
    }
    proof["recovery_proof_hash"] = _self_hash(proof, "recovery_proof_hash")
    return proof


def process_episode_fixture(fixture: Mapping[str, Any], *, output_dir: Path) -> EpisodeResult:
    _assert_runtime_authority_boundary()
    spec = validate_case_fixture(fixture, validate_expectations=False)
    case_dir = _contained_case_dir(output_dir, spec["case_id"])
    case_dir.mkdir(parents=True, exist_ok=True)
    notes: list[str] = []
    _prepare_scenario_artifacts(spec, case_dir)

    if spec["replay_mode"] == "duplicate_terminal":
        first = _run_with_replay(spec, case_dir, notes)
        baseline = _snapshot(first)
        notes.append("controller_restarted")
        notes.append("terminal_receipt_reused")
        second = _EpisodeController(spec, case_dir, "worker-a", notes, consumed_faults=set())
        terminal = second.run()
        return second.result(terminal, baseline=baseline)

    consumed_faults: set[str] = set()
    worker_id = "worker-a"
    controller: _EpisodeController | None = None
    terminal = "human_escalation_required"
    for _attempt in range(4):
        controller = _EpisodeController(spec, case_dir, worker_id, notes, consumed_faults=consumed_faults)
        try:
            terminal = controller.run()
            break
        except (_ControlledCrash, _StorageFault) as exc:
            consumed_faults.add(exc.point)
            _write_crash_marker(case_dir, exc.point)
            notes.extend([f"controlled_crash:{exc.point}", "controller_restarted"])
            if exc.point in {"lease_expiry_during_verification", "lease_expiry_during_rollback"}:
                controller.expire_lease()
                worker_id = "worker-b"
    else:
        raise P145DutyOfficerError("crash_replay_exhausted")
    assert controller is not None
    return controller.result(terminal)


class _EpisodeController:
    def __init__(
        self, spec: Mapping[str, Any], case_dir: Path, worker_id: str, notes: list[str], *, consumed_faults: set[str],
    ) -> None:
        self.spec = spec
        self.case_dir = case_dir
        self.worker_id = worker_id
        self.notes = notes
        self.consumed_faults = consumed_faults
        self.journal_path = case_dir / "journal.jsonl"
        self.cursor_path = case_dir / "cursor.json"
        self.lab_path = case_dir / "fault-lab-state.json"
        self.lease_path = case_dir / "lease.json"
        self.ack_path = case_dir / "p133-ack.json"
        self.crash_path = case_dir / "crash-state.json"

    def run(self) -> str:
        try:
            entries = self._load_journal()
            self._validate_cursor(entries)
            self._validate_side_artifacts(entries)
        except P145DutyOfficerError as exc:
            return self._reject_tamper(exc)
        terminal = _terminal_from_entries(entries)
        if terminal is not None:
            if not self.cursor_path.exists():
                self._maybe_crash("cursor_fsync_failure")
                self._write_cursor(terminal, entries[-1]["receipt_hash"])
            return terminal

        self._acquire_lease()
        entries = self._load_journal()
        blocker = _pre_ownership_blocker(self.spec, self.ack_path)
        if not entries:
            self._append("registered", {"event_id": self._bound_event_id()})
            _write_json_fsynced(self.lab_path, validate_fault_lab_state(self.spec["initial_lab_state"]))

        if blocker is not None and not self._has("owned_acknowledged"):
            self.notes.append(blocker)
            return self._escalate(blocker, write_cursor=not self.spec["tamper_mode"])

        if not self._has("evidence_validated"):
            self._append("evidence_validated", {"evidence_hash": self.spec["evidence_hash"]})
        if not self._has("ownership_intent_committed"):
            self._append("ownership_intent_committed", {"event_id": self.spec["p133_event"]["event_id"]})
        if not self._has("owned_acknowledged"):
            try:
                ack = self._acknowledge_local_p133(self.spec["p133_event"], self.ack_path)
            except _LeaseConflict:
                self.notes.append("p133_ack_cas_conflict")
                return self._escalate("p133_ack_cas_conflict")
            self._append("owned_acknowledged", ack)

        if not self._has("hypotheses_adjudicated"):
            self._append("hypotheses_adjudicated", _adjudicate_hypotheses(self.spec))
        adjudication = _adjudicate_hypotheses(self.spec)
        if not _adjudication_allows_policy(adjudication):
            reason = _adjudication_blocker(adjudication)
            self.notes.append(reason)
            return self._escalate(reason)

        if self.spec["lease_mode"] == "dead_runner":
            if not self._has("deadman_handoff_committed"):
                self._append("deadman_handoff_committed", {"reason": "heartbeat_expired", "recoverable": True})
            self.notes.append("dead_runner_handoff")
            return self._escalate("dead_runner_handoff")

        action = str(self.spec["selected_action"])
        policy = self.spec["policy"]
        if policy["allowed"] is not True or policy["blast_radius_bps"] > policy["max_blast_radius_bps"] or policy["action_budget"] < self.spec["action_count"]:
            self.notes.append("local_policy_rejected")
            return self._escalate("local_policy_rejected")

        if action == "observe_only":
            if not self._has("observe_only_authorized"):
                self._append("observe_only_authorized", _policy_receipt(self.spec, action))
            if not self._has("verification_started"):
                self._append("verification_started", {"mode": "observe_only"})
            return self._verify_or_escalate()

        if not self._has("local_policy_authorized"):
            self._append("local_policy_authorized", _policy_receipt(self.spec, action))
        if policy["rollback_metadata_present"] is not True or policy["preflight_passed"] is not True:
            if not self._has("preflight_blocked"):
                self._append("preflight_blocked", {"reason": "rollback_or_preflight_invalid"})
            self.notes.append("rollback_or_preflight_invalid")
            return self._escalate("rollback_or_preflight_invalid")

        pre_state = validate_fault_lab_state(self.spec["initial_lab_state"])
        crash_state = _read_json_if_present(self.crash_path)
        recovery_strategy = crash_state.get("recovery_strategy") if crash_state else None
        if recovery_strategy == "escalate":
            self.notes.append(str(crash_state["crash_point"]))
            return self._escalate(str(crash_state["crash_point"]))
        for index in range(self.spec["action_count"]):
            action_id = _action_id(self.spec, index)
            if not self._has_action("action_intent_committed", action_id):
                self._maybe_storage_fault("journal_disk_full")
                self._append("action_intent_committed", {"action_id": action_id, "action_index": index, "action": action, "pre_state_hash": self._read_lab()["state_hash"]})
                self._maybe_crash("before_action_commit")
            state = self._read_lab()
            if recovery_strategy == "rollback" and not self._has_action("action_receipt_committed", action_id):
                return self._rollback(pre_state, action_id)
            if state["last_action_id"] != action_id:
                self._maybe_storage_fault("lab_fsync_failure")
                state = apply_lab_transform(state, action, action_id=action_id)
                _write_json_fsynced(self.lab_path, state)
            if not self._has_action("lab_mutated", action_id):
                self._append("lab_mutated", {"action_id": action_id, "action_index": index, "post_state_hash": state["state_hash"]})
                self._maybe_crash("lab_mutated_before_action_receipt")
                self._maybe_crash("action_receipt_before_fsync")
            if not self._has_action("action_receipt_committed", action_id):
                receipt = {
                    "schema_version": ACTION_RECEIPT_SCHEMA_VERSION, "action_id": action_id,
                    "action_index": index, "post_state_hash": state["state_hash"],
                    "rollback_pre_state_hash": pre_state["state_hash"],
                }
                receipt["receipt_hash"] = _self_hash(receipt, "receipt_hash")
                self._append("action_receipt_committed", receipt)
                self._maybe_crash("action_receipt")

        if self.spec["replay_mode"] == "correlated_duplicate":
            try:
                self._record_correlated_duplicate()
            except _LeaseConflict:
                self.notes.append("correlated_p133_ack_cas_conflict")
                return self._escalate("correlated_p133_ack_cas_conflict")

        if self.spec["lease_mode"] == "contention":
            competitor = _EpisodeController(self.spec, self.case_dir, "worker-b", self.notes, consumed_faults=self.consumed_faults)
            try:
                competitor._acquire_lease()
            except _LeaseConflict:
                self.notes.append("competing_worker_lease_conflict")
            return self._escalate("same_resource_lease_contention")

        if not self._has("verification_started"):
            self._append("verification_started", {"mode": "post_action"})
        self._maybe_crash("lease_expiry_during_verification")
        if crash_state.get("crash_point") == "lease_expiry_during_verification":
            self.notes.append("lease_expired_during_verification")
            return self._escalate("lease_expired_during_verification")
        if self.spec["observation_mode"] in {"harmful", "delayed_regression", "rollback_collateral_harm"}:
            return self._rollback(pre_state, _action_id(self.spec, self.spec["action_count"] - 1))
        return self._verify_or_escalate()

    def _verify_or_escalate(self) -> str:
        state = self._read_lab()
        observations = _scenario_observations(state, str(self.spec["observation_mode"]))
        for observation in observations:
            if not self._has_observation(observation["observation_hash"]):
                self._append("observation_committed", observation)
        if self.spec["observation_mode"] == "lab_drift":
            drifted = deepcopy(state)
            drifted["latency_ms"] += 1
            drifted["generation"] += 1
            drifted["state_hash"] = _self_hash(drifted, "state_hash")
            _write_json_fsynced(self.lab_path, drifted)
            state = drifted
        proof = verify_recovery(state, observations)
        if proof["recovered"]:
            self._append("recovery_receipt_committed", proof)
            return self._terminal("recovery_verified")
        self._append("verification_failed", proof)
        self.notes.extend(proof["blockers"] or ["recovery_threshold_not_met"])
        return self._escalate("recovery_not_verified")

    def _rollback(self, pre_state: Mapping[str, Any], action_id: str) -> str:
        if not self._has("rollback_intent_committed"):
            self._append("rollback_intent_committed", {"action_id": action_id, "pre_state_hash": pre_state["state_hash"]})
            self._maybe_crash("lease_expiry_during_rollback")
        if self.spec["rollback_mode"] == "fail":
            self.notes.append("rollback_failed")
            return self._escalate("rollback_failed")
        current = self._read_lab()
        if not self._has("rollback_lab_mutated") and current["state_hash"] != pre_state["state_hash"]:
            restored = rollback_lab_transform(current, pre_state, action_id=action_id)
            if self.spec["observation_mode"] == "rollback_collateral_harm":
                restored["collateral_health_bps"] = 7000
                restored["state_hash"] = _self_hash(restored, "state_hash")
            _write_json_fsynced(self.lab_path, restored)
            self._append("rollback_lab_mutated", {"action_id": action_id, "restored_state_hash": restored["state_hash"]})
            self._maybe_crash("rollback_mutated_before_receipt")
            current = restored
        if not self._has("rollback_receipt_committed"):
            receipt = {
                "schema_version": ROLLBACK_RECEIPT_SCHEMA_VERSION, "action_id": action_id,
                "restored_state_hash": current["state_hash"], "expected_pre_state_hash": pre_state["state_hash"],
                "verified": current["state_hash"] == pre_state["state_hash"] or current["last_action_id"] == f"rollback:{action_id}",
            }
            receipt["receipt_hash"] = _self_hash(receipt, "receipt_hash")
            self._append("rollback_receipt_committed", receipt)
        if self.spec["observation_mode"] in {"delayed_regression", "rollback_collateral_harm"}:
            self.notes.append(self.spec["observation_mode"])
            return self._escalate(str(self.spec["observation_mode"]))
        return self._terminal("rollback_verified")

    def _escalate(self, reason: str, *, write_cursor: bool = True) -> str:
        if not self._has("escalation_receipt_committed"):
            receipt = {"schema_version": ESCALATION_RECEIPT_SCHEMA_VERSION, "reason": reason, "local_only": True}
            receipt["receipt_hash"] = _self_hash(receipt, "receipt_hash")
            self._append("escalation_receipt_committed", receipt)
        return self._terminal("human_escalation_required", write_cursor=write_cursor)

    def _terminal(self, terminal: str, *, write_cursor: bool = True) -> str:
        existing = _terminal_from_entries(self._load_journal())
        if existing is not None:
            return existing
        terminal_hash = self._append(terminal, {"terminal_status": terminal})
        self._maybe_crash("terminal_receipt_before_cursor")
        self._maybe_crash("cursor_fsync_failure")
        if write_cursor:
            self._write_cursor(terminal, terminal_hash)
        return terminal

    def _append(self, phase: str, payload: Mapping[str, Any]) -> str:
        self._assert_lease_owner()
        entries = self._load_journal()
        previous = entries[-1]["receipt_hash"] if entries else _ZERO_HASH
        version = len(entries) + 1
        entry: dict[str, Any] = {
            "schema_version": JOURNAL_SCHEMA_VERSION, "episode_id": self.spec["episode_id"],
            "case_id": self.spec["case_id"], "cas_version": version, "phase": phase,
            "logical_time": version, "payload": deepcopy(dict(payload)), "payload_hash": stable_hash(payload),
            "previous_receipt_hash": previous,
        }
        entry["receipt_hash"] = _self_hash(entry, "receipt_hash")
        with self.journal_path.open("a", encoding="utf-8") as handle:
            handle.write(_canonical_json(entry) + "\n")
            handle.flush()
            fsync(handle.fileno())
        self._load_journal()
        return str(entry["receipt_hash"])

    def _load_journal(self) -> list[dict[str, Any]]:
        if not self.journal_path.exists():
            return []
        entries: list[dict[str, Any]] = []
        for line in self.journal_path.read_text(encoding="utf-8").splitlines():
            if not line:
                raise P145DutyOfficerError("journal_partial_entry")
            try:
                value = json.loads(line, object_pairs_hook=_strict_json_object)
            except (json.JSONDecodeError, P145DutyOfficerError) as exc:
                raise P145DutyOfficerError("journal_corrupt_json") from exc
            if not isinstance(value, dict) or line != _canonical_json(value):
                raise P145DutyOfficerError("journal_noncanonical")
            entries.append(value)
        _validate_journal_entries(entries, self.spec)
        return entries

    def _validate_cursor(self, entries: list[dict[str, Any]]) -> None:
        if not self.cursor_path.exists():
            return
        cursor = _read_json(self.cursor_path)
        terminal = _terminal_from_entries(entries)
        if terminal is None or set(cursor) != {"schema_version", "episode_id", "case_id", "terminal_status", "terminal_receipt_hash", "cursor_hash"}:
            raise P145DutyOfficerError("cursor_missing_predecessor")
        if cursor.get("schema_version") != CURSOR_SCHEMA_VERSION or cursor.get("terminal_status") != terminal:
            raise P145DutyOfficerError("cursor_terminal_mismatch")
        if cursor.get("episode_id") != self.spec["episode_id"] or cursor.get("case_id") != self.spec["case_id"]:
            raise P145DutyOfficerError("cursor_identity_binding_invalid")
        if cursor.get("terminal_receipt_hash") != entries[-1]["receipt_hash"] or cursor.get("cursor_hash") != _self_hash(cursor, "cursor_hash"):
            raise P145DutyOfficerError("cursor_hash_invalid")

    def _validate_side_artifacts(self, entries: list[dict[str, Any]]) -> None:
        lease: dict[str, Any] | None = None
        if self.lease_path.exists():
            lease = _read_json(self.lease_path)
            _validate_lease(lease, self._bound_event_id())
            _validate_lease_projection(lease, entries, _read_json_if_present(self.crash_path))
        self._reconcile_acknowledgements(entries, lease=lease)
        if self.lab_path.exists():
            validate_fault_lab_state(_read_json(self.lab_path))
        if self.crash_path.exists():
            _validate_crash_state(_read_json(self.crash_path), self.spec)
        escalation_path = self.case_dir / "escalation-receipt.json"
        if escalation_path.exists():
            _validate_escalation_side_receipt(_read_json(escalation_path), entries)
        if _terminal_from_entries(entries) is not None:
            _validate_terminal_truth(entries, self.spec, self.lab_path)
        elif self.lab_path.exists():
            current = validate_fault_lab_state(_read_json(self.lab_path))
            if current != _expected_durable_lab_state(entries, self.spec):
                raise P145DutyOfficerError("durable_lab_projection_invalid")

    def _reconcile_acknowledgements(
        self, entries: list[dict[str, Any]], *, lease: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        phase_contracts: tuple[tuple[str, str, Mapping[str, Any]], ...] = (
            ("owned_acknowledged", "p133-ack.json", self.spec["p133_event"]),
            (
                "correlated_owned_acknowledged",
                "p133-ack-correlated.json",
                self.spec["correlated_p133_event"] or {},
            ),
        )
        journal_entries = {entry["phase"]: entry for entry in entries if entry["phase"] in {
            "owned_acknowledged", "correlated_owned_acknowledged",
        }}
        active_paths = {path.name: path for path in self.case_dir.glob("p133-ack*.json") if path.is_file()}
        expected_names = {
            filename for phase, filename, _event in phase_contracts if phase in journal_entries
        }
        extra_names = set(active_paths) - expected_names
        if extra_names:
            if self._is_expected_preownership_ack_conflict(entries, active_paths, extra_names):
                return []
            raise P145DutyOfficerError("p133_ack_artifact_extra")
        if expected_names - set(active_paths):
            raise P145DutyOfficerError("p133_ack_artifact_missing")
        if expected_names and lease is None:
            if not self.lease_path.exists():
                raise P145DutyOfficerError("p133_ack_lease_missing")
            lease = _read_json(self.lease_path)
            _validate_lease(lease, self._bound_event_id())

        reconciled: list[dict[str, Any]] = []
        for phase, filename, event in phase_contracts:
            journal_entry = journal_entries.get(phase)
            if journal_entry is None:
                continue
            try:
                artifact = _read_json(active_paths[filename])
            except ValueError as exc:
                raise P145DutyOfficerError("p133_ack_artifact_corrupt") from exc
            if artifact != journal_entry["payload"]:
                raise P145DutyOfficerError("p133_ack_artifact_drift")
            assert lease is not None
            _validate_acknowledgement_projection(artifact, event, self.spec["episode_id"], lease)
            reconciled.append(artifact)

        if "correlated_owned_acknowledged" in journal_entries and _terminal_from_entries(entries) is not None:
            if "correlation_action_receipt_committed" not in {entry["phase"] for entry in entries}:
                raise P145DutyOfficerError("p133_ack_action_correlation_missing")
            _validate_correlation_journal_proof(entries, self.spec)
        return reconciled

    def _is_expected_preownership_ack_conflict(
        self,
        entries: list[dict[str, Any]],
        active_paths: Mapping[str, Path],
        extra_names: set[str],
    ) -> bool:
        if self.spec.get("existing_ack") != "conflict" or extra_names != {"p133-ack.json"}:
            return False
        if set(active_paths) != {"p133-ack.json"}:
            return False
        escalation = next((entry for entry in entries if entry["phase"] == "escalation_receipt_committed"), None)
        return not entries or (
            escalation is not None and escalation["payload"].get("reason") == "p133_ack_cas_conflict"
        )

    def _write_cursor(self, terminal: str, terminal_hash: str) -> None:
        cursor = {
            "schema_version": CURSOR_SCHEMA_VERSION, "episode_id": self.spec["episode_id"],
            "case_id": self.spec["case_id"], "terminal_status": terminal, "terminal_receipt_hash": terminal_hash,
        }
        cursor["cursor_hash"] = _self_hash(cursor, "cursor_hash")
        _write_json_fsynced(self.cursor_path, cursor)

    def _acquire_lease(self) -> None:
        event_id = self._bound_event_id()
        if self.lease_path.exists():
            lease = _read_json(self.lease_path)
            _validate_lease(lease, event_id)
            if lease["active"] and lease["owner_id"] != self.worker_id:
                raise _LeaseConflict("lease_cas_conflict")
            if lease["active"]:
                lease["renew_count"] += 1
            else:
                lease["owner_id"] = self.worker_id
                lease["active"] = True
                lease["acquire_count"] += 1
            lease["write_count"] += 1
        else:
            lease = {
                "schema_version": LEASE_SCHEMA_VERSION, "event_id": event_id, "owner_id": self.worker_id,
                "active": True, "acquire_count": 1, "renew_count": 0, "write_count": 1,
                "ownership_history": [],
            }
        _append_lease_ownership_receipt(lease)
        lease["lease_hash"] = _self_hash(lease, "lease_hash")
        _write_json_fsynced(self.lease_path, lease)

    def expire_lease(self) -> None:
        lease = _read_json(self.lease_path)
        lease["active"] = False
        lease["write_count"] += 1
        _append_lease_ownership_receipt(lease)
        lease["lease_hash"] = _self_hash(lease, "lease_hash")
        _write_json_fsynced(self.lease_path, lease)

    def _assert_lease_owner(self) -> dict[str, Any]:
        lease = _read_json(self.lease_path)
        _validate_lease(lease, self._bound_event_id())
        if lease["active"] is not True or lease["owner_id"] != self.worker_id:
            raise _LeaseConflict("lease_owner_drift")
        return lease

    def _bound_event_id(self) -> str:
        event = self.spec.get("p133_event")
        event_id = event.get("event_id") if isinstance(event, Mapping) else None
        return event_id if isinstance(event_id, str) else _ZERO_HASH

    def _acknowledge_local_p133(self, event: Mapping[str, Any], ack_path: Path) -> dict[str, Any]:
        lease = self._assert_lease_owner()
        ownership = lease["ownership_history"][-1]
        ack: dict[str, Any] = {
            "schema_version": P133_ACK_SCHEMA_VERSION, "event_id": event["event_id"], "event_hash": event["event_hash"],
            "incident_id": event["incident_id"], "correlation_id": event.get("correlation_id"),
            "episode_id": self.spec["episode_id"], "lease_owner": self.worker_id,
            "lease_epoch": ownership["epoch"], "lease_cas_version": ownership["cas_version"],
            "lease_receipt_hash": ownership["receipt_hash"],
            "meaning": "local_ownership_only_not_external_delivery_or_closure",
            "authority_counters": zero_forbidden_authority(),
        }
        ack["ack_hash"] = _self_hash(ack, "ack_hash")
        if ack_path.exists():
            existing = _read_json(ack_path)
            if existing != ack:
                raise _LeaseConflict("p133_ack_cas_conflict")
            return existing
        _write_json_exclusive_fsynced(ack_path, ack)
        return ack

    def _record_correlated_duplicate(self) -> None:
        second_event = self.spec["correlated_p133_event"]
        if not isinstance(second_event, Mapping):
            raise P145DutyOfficerError("correlated_p133_event_missing")
        action_entry = next(
            (entry for entry in self._load_journal() if entry["phase"] == "action_receipt_committed"),
            None,
        )
        if action_entry is None:
            raise P145DutyOfficerError("correlated_action_receipt_missing")
        if not self._has("correlated_event_registered"):
            self._append(
                "correlated_event_registered",
                {
                    "event_id": second_event["event_id"],
                    "incident_id": second_event["incident_id"],
                    "event_hash": second_event["event_hash"],
                    "correlation_id": second_event["correlation_id"],
                },
            )
        if not self._has("correlated_ownership_intent_committed"):
            self._append(
                "correlated_ownership_intent_committed",
                {"event_id": second_event["event_id"], "correlation_id": second_event["correlation_id"]},
            )
        if not self._has("correlated_owned_acknowledged"):
            correlated_ack = self._acknowledge_local_p133(
                second_event, self.case_dir / "p133-ack-correlated.json"
            )
            self._append("correlated_owned_acknowledged", correlated_ack)
        if not self._has("correlation_action_receipt_committed"):
            self._append(
                "correlation_action_receipt_committed",
                _correlation_action_receipt(self.spec, action_entry["payload"]["receipt_hash"]),
            )
        if "correlated_duplicate_action_reused" not in self.notes:
            self.notes.append("correlated_duplicate_action_reused")

    def _read_lab(self) -> dict[str, Any]:
        if not self.lab_path.exists():
            raise P145DutyOfficerError("fault_lab_state_missing")
        return validate_fault_lab_state(_read_json(self.lab_path))

    def _has(self, phase: str) -> bool:
        return any(entry["phase"] == phase for entry in self._load_journal())

    def _has_action(self, phase: str, action_id: str) -> bool:
        return any(entry["phase"] == phase and entry["payload"].get("action_id") == action_id for entry in self._load_journal())

    def _has_observation(self, observation_hash: str) -> bool:
        return any(entry["phase"] == "observation_committed" and entry["payload"].get("observation_hash") == observation_hash for entry in self._load_journal())

    def _maybe_crash(self, point: str) -> None:
        if self.spec["fault_injection"] == point and point not in self.consumed_faults:
            raise _ControlledCrash(point)

    def _maybe_storage_fault(self, point: str) -> None:
        if self.spec["fault_injection"] == point and point not in self.consumed_faults:
            raise _StorageFault(point)

    def _reject_tamper(self, exc: P145DutyOfficerError) -> str:
        reason = str(exc)
        note_map = {
            "journal_duplicate_phase": "journal_duplicate_phase_rejected",
            "journal_phase_reorder": "journal_reorder_rejected",
            "direct_terminal_write": "journal_reorder_rejected",
            "cursor_missing_predecessor": "journal_missing_predecessor_rejected",
            "cursor_terminal_mismatch": "journal_missing_predecessor_rejected",
            "cursor_hash_invalid": "journal_missing_predecessor_rejected",
        }
        self.notes.append(note_map.get(reason, f"tamper_rejected:{reason}"))
        if reason == "direct_terminal_write":
            self.notes.append("terminal_tamper_rejected")
        if reason.startswith("cursor_"):
            self.notes.append("cursor_tamper_rejected")
        self._quarantine_active_episode()
        self._acquire_lease()
        self._append("registered", {"event_id": self._bound_event_id(), "tamper_recovery": True})
        receipt = {
            "schema_version": ESCALATION_RECEIPT_SCHEMA_VERSION,
            "reason": reason,
            "local_only": True,
        }
        receipt["receipt_hash"] = _self_hash(receipt, "receipt_hash")
        self._append("escalation_receipt_committed", receipt)
        terminal_hash = self._append("human_escalation_required", {"terminal_status": "human_escalation_required"})
        if reason.startswith("p133_ack_artifact"):
            self._write_cursor("human_escalation_required", terminal_hash)
        return "human_escalation_required"

    def _quarantine_active_episode(self) -> None:
        paths = (
            (self.journal_path, self.case_dir / "journal.rejected.jsonl"),
            (self.cursor_path, self.case_dir / "cursor.rejected.json"),
            (self.lab_path, self.case_dir / "fault-lab-state.rejected.json"),
            (self.lease_path, self.case_dir / "lease.rejected.json"),
            (self.crash_path, self.case_dir / "crash-state.rejected.json"),
            (
                self.case_dir / "escalation-receipt.json",
                self.case_dir / "escalation-receipt.rejected.json",
            ),
        )
        for source, destination in paths:
            if source.exists():
                replace(source, destination)
        for ack_path in self.case_dir.glob("p133-ack*.json"):
            replace(ack_path, ack_path.with_suffix(".json.rejected"))

    def result(self, terminal: str, *, baseline: Mapping[str, Any] | None = None) -> EpisodeResult:
        entries = self._load_journal()
        acknowledgements = self._reconcile_acknowledgements(entries)
        counts = _derive_counts(
            self.case_dir,
            entries,
            baseline=baseline,
            acknowledged_artifact_count=len(acknowledgements),
        )
        receipts = [entry for entry in entries if entry["phase"] == "action_receipt_committed"]
        rollback = next((entry for entry in reversed(entries) if entry["phase"] == "rollback_receipt_committed"), None)
        recovery = next((entry for entry in reversed(entries) if entry["phase"] == "recovery_receipt_committed"), None)
        policy = next((entry for entry in entries if entry["phase"] in {"local_policy_authorized", "observe_only_authorized"}), None)
        ack = acknowledgements[0] if acknowledgements else None
        correlation = next((entry for entry in entries if entry["phase"] == "correlation_action_receipt_committed"), None)
        crash = _read_json_if_present(self.crash_path)
        payload: dict[str, Any] = {
            "case_id": self.spec["case_id"], "scenario": self.spec["scenario"], "selector": self.spec["selector"],
            "terminal_status": terminal, "phase_path": [entry["phase"] for entry in entries], "counts": counts,
            "crash_point": crash.get("crash_point") if crash else None, "journal_path": str(self.journal_path),
            "cursor_path": str(self.cursor_path), "ack_receipt_hash": ack.get("ack_hash") if ack else None,
            "ack_receipt_hashes": [artifact["ack_hash"] for artifact in acknowledgements],
            "policy_receipt_hash": policy["payload"].get("receipt_hash") if policy else None,
            "action_receipt_hashes": [entry["payload"]["receipt_hash"] for entry in receipts],
            "correlation_action_receipt": (
                {**correlation["payload"], "journal_receipt_hash": correlation["receipt_hash"]}
                if correlation else None
            ),
            "rollback_receipt_hash": rollback["payload"].get("receipt_hash") if rollback else None,
            "recovery_receipt_hash": recovery["payload"].get("recovery_proof_hash") if recovery else None,
            "terminal_receipt_hash": entries[-1]["receipt_hash"], "command_notes": list(dict.fromkeys(self.notes)),
        }
        payload["result_hash"] = stable_hash(payload)
        return EpisodeResult(**payload)


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None


def _exact_mapping(raw: Any, fields: frozenset[str], reason: str) -> Mapping[str, Any]:
    if not isinstance(raw, Mapping) or set(raw) != fields:
        raise P145DutyOfficerError(reason)
    return raw


def _validate_p133_event_contract(raw: Any, *, correlated: bool, allow_correlation: bool = False) -> None:
    reason = "input_schema_invalid:correlated_p133_event" if correlated else "input_schema_invalid:p133_event"
    if not isinstance(raw, Mapping):
        raise P145DutyOfficerError(reason)
    expected_fields = P133_EVENT_FIELDS | ({"correlation_id"} if correlated or allow_correlation else set())
    event = _exact_mapping(raw, frozenset(expected_fields), reason)
    if (
        event.get("schema_version") != P133_EVENT_SCHEMA_VERSION
        or not _is_sha256(event.get("event_id"))
        or not isinstance(event.get("incident_id"), str)
        or not event["incident_id"]
        or type(event.get("sequence")) is not int
        or event["sequence"] <= 0
        or event.get("domain") not in ALLOWED_EVENT_DOMAINS
        or not _is_sha256(event.get("event_hash"))
    ):
        raise P145DutyOfficerError(reason)
    if "correlation_id" in event and not _is_sha256(event.get("correlation_id")):
        raise P145DutyOfficerError(reason)


def _validate_evidence_contract(raw: Any) -> None:
    evidence = _exact_mapping(raw, EVIDENCE_FIELDS, "input_schema_invalid:evidence")
    for key in (
        "schema_valid", "hash_valid", "fresh", "support_complete", "contradiction_absent",
        "critical_missing_evidence", "prompt_injection_present", "prior_memory_poisoned",
    ):
        if type(evidence.get(key)) is not bool:
            raise P145DutyOfficerError("input_schema_invalid:evidence")
    for key in ("confidence_margin_bps", "minimum_margin_bps"):
        if type(evidence.get(key)) is not int or not 0 <= evidence[key] <= 10000:
            raise P145DutyOfficerError("input_schema_invalid:evidence")


def _validate_policy_contract(raw: Any) -> None:
    policy = _exact_mapping(raw, POLICY_FIELDS, "input_schema_invalid:policy")
    for key in ("allowed", "rollback_metadata_present", "preflight_passed"):
        if type(policy.get(key)) is not bool:
            raise P145DutyOfficerError("input_schema_invalid:policy")
    for key in ("blast_radius_bps", "max_blast_radius_bps"):
        if type(policy.get(key)) is not int or not 0 <= policy[key] <= 10000:
            raise P145DutyOfficerError("input_schema_invalid:policy")
    if type(policy.get("action_budget")) is not int or not 0 <= policy["action_budget"] <= 2:
        raise P145DutyOfficerError("input_schema_invalid:policy")


def _validate_predecessor_binding_contract(raw: Any) -> None:
    bindings = _exact_mapping(raw, frozenset(PREDECESSOR_BINDINGS), "input_schema_invalid:predecessor_bindings")
    if any(not _is_sha256(value) for value in bindings.values()):
        raise P145DutyOfficerError("input_schema_invalid:predecessor_bindings")


def _validate_source_profile_binding_contract(raw: Any) -> None:
    bindings = _exact_mapping(raw, SOURCE_PROFILE_BINDING_FIELDS, "input_schema_invalid:source_profile_bindings")
    if (
        bindings.get("profile") != "p145-release"
        or not isinstance(bindings.get("selector"), str)
        or not bindings["selector"]
        or any(
            not _is_sha256(bindings.get(key))
            for key in ("approved_plan_sha256", "approved_test_spec_sha256", "plan_review_sha256", "profile_sha256")
        )
    ):
        raise P145DutyOfficerError("input_schema_invalid:source_profile_bindings")


def _validate_hypothesis_contract(raw: Any) -> None:
    if type(raw) is not list or not 2 <= len(raw) <= 8:
        raise P145DutyOfficerError("input_schema_invalid:hypotheses")
    names: list[str] = []
    allowed_names = set(ACTION_HYPOTHESIS.values())
    for item in raw:
        hypothesis = _exact_mapping(item, HYPOTHESIS_FIELDS, "input_schema_invalid:hypotheses")
        name = hypothesis.get("name")
        if not isinstance(name, str) or name not in allowed_names:
            raise P145DutyOfficerError("input_schema_invalid:hypotheses")
        names.append(name)
        if type(hypothesis.get("confidence_bps")) is not int or not 0 <= hypothesis["confidence_bps"] <= 10000:
            raise P145DutyOfficerError("input_schema_invalid:hypotheses")
        for key in ("support", "contradictions"):
            values = hypothesis.get(key)
            if type(values) is not list or any(not isinstance(value, str) or not value for value in values):
                raise P145DutyOfficerError("input_schema_invalid:hypotheses")
    if len(names) != len(set(names)):
        raise P145DutyOfficerError("input_schema_invalid:hypotheses")


def _validate_authority_input_contracts(spec: Mapping[str, Any]) -> None:
    correlated_mode = spec.get("replay_mode") == "correlated_duplicate"
    _validate_p133_event_contract(
        spec.get("p133_event"), correlated=False, allow_correlation=correlated_mode,
    )
    correlated_event = spec.get("correlated_p133_event")
    if correlated_mode:
        _validate_p133_event_contract(correlated_event, correlated=True)
    elif correlated_event is not None:
        raise P145DutyOfficerError("input_schema_invalid:correlated_p133_event")
    _validate_evidence_contract(spec.get("evidence"))
    _validate_policy_contract(spec.get("policy"))
    _validate_predecessor_binding_contract(spec.get("predecessor_bindings"))
    _validate_source_profile_binding_contract(spec.get("source_profile_bindings"))
    _validate_hypothesis_contract(spec.get("hypotheses"))


def _validate_expected_comparison_contract(value: Mapping[str, Any]) -> None:
    terminal = value.get("expected_terminal_status")
    phases = value.get("expected_phase_path")
    if terminal not in TERMINALS:
        raise P145DutyOfficerError("invalid_expected_terminal")
    if (
        type(phases) is not list
        or not phases
        or any(not isinstance(phase, str) or phase not in EXPECTED_PHASES for phase in phases)
        or phases[-1] != terminal
    ):
        raise P145DutyOfficerError("invalid_expected_phase_path")
    crash = value.get("expected_crash_point")
    if crash is not None and crash not in FAULT_INJECTION_MODES:
        raise P145DutyOfficerError("invalid_expected_crash_point")
    counts = value.get("expected_counts")
    expected_groups = {
        "forbidden_authority": FORBIDDEN_AUTHORITY_KEYS,
        "runtime_activity": RUNTIME_ACTIVITY_KEYS,
        "lab_activity": LAB_ACTIVITY_KEYS,
        "evaluator_activity": EVALUATOR_ACTIVITY_KEYS,
        "resource_usage": RESOURCE_USAGE_KEYS,
    }
    if not isinstance(counts, Mapping) or set(counts) != set(expected_groups):
        raise P145DutyOfficerError("invalid_expected_counts")
    for group, keys in expected_groups.items():
        if not exact_counter_map(counts[group], keys, exact_zero=group == "forbidden_authority"):
            raise P145DutyOfficerError("invalid_expected_counts")


def validate_case_fixture(fixture: Mapping[str, Any], *, validate_expectations: bool = True) -> dict[str, Any]:
    value = deepcopy(dict(fixture))
    fields = {
        "schema_version", "case_id", "scenario", "selector", "episode_id", "branch", "p133_event",
        "correlated_p133_event",
        "predecessor_bindings", "source_profile_bindings", "evidence", "evidence_hash", "initial_lab_state",
        "hypotheses", "selected_action", "action_count", "policy", "observation_mode", "rollback_mode",
        "fault_injection", "tamper_mode", "lease_mode", "existing_ack", "replay_mode",
        "expected_terminal_status", "expected_phase_path", "expected_crash_point", "expected_counts", "fixture_hash",
    }
    if set(value) != fields or value.get("schema_version") != CASE_SCHEMA_VERSION:
        raise P145DutyOfficerError("invalid_case_fixture_schema")
    if not isinstance(value.get("case_id"), str) or _CASE_ID_RE.fullmatch(value["case_id"]) is None:
        raise P145DutyOfficerError("invalid_case_id")
    expected_selector = f"tests/test_p145_response_duty_officer.py::{_selector_name(value['case_id'])}"
    if value.get("selector") != expected_selector:
        raise P145DutyOfficerError("selector_binding_invalid")
    if not isinstance(value.get("scenario"), str) or not value["scenario"]:
        raise P145DutyOfficerError("invalid_scenario")
    if not _is_sha256(value.get("episode_id")):
        raise P145DutyOfficerError("invalid_episode_id")
    if not isinstance(value.get("branch"), str) or not value["branch"]:
        raise P145DutyOfficerError("invalid_branch")
    if not isinstance(value.get("initial_lab_state"), Mapping):
        raise P145DutyOfficerError("invalid_fault_lab_state_schema")
    validate_fault_lab_state(value["initial_lab_state"])
    if value.get("selected_action") not in TRANSFORMS or type(value.get("action_count")) is not int or not 0 <= value["action_count"] <= 2:
        raise P145DutyOfficerError("invalid_action_contract")
    if value.get("observation_mode") not in OBSERVATION_MODES or value.get("rollback_mode") not in ROLLBACK_MODES:
        raise P145DutyOfficerError("invalid_observation_or_rollback_mode")
    if value.get("fault_injection") is not None and value.get("fault_injection") not in FAULT_INJECTION_MODES:
        raise P145DutyOfficerError("invalid_fault_injection")
    if value.get("tamper_mode") is not None and value.get("tamper_mode") not in TAMPER_MODES:
        raise P145DutyOfficerError("invalid_tamper_mode")
    if value.get("lease_mode") not in LEASE_MODES or value.get("existing_ack") not in EXISTING_ACK_MODES:
        raise P145DutyOfficerError("invalid_lease_or_ack_mode")
    if value.get("replay_mode") not in REPLAY_MODES:
        raise P145DutyOfficerError("invalid_replay_mode")
    if not _is_sha256(value.get("evidence_hash")):
        raise P145DutyOfficerError("invalid_evidence_hash_contract")
    if validate_expectations:
        _validate_expected_comparison_contract(value)
    if not _is_sha256(value.get("fixture_hash")) or value.get("fixture_hash") != _self_hash(value, "fixture_hash"):
        raise P145DutyOfficerError("fixture_hash_invalid")
    return value


def _pre_ownership_blocker(spec: Mapping[str, Any], ack_path: Path) -> str | None:
    try:
        _validate_authority_input_contracts(spec)
    except P145DutyOfficerError as exc:
        return str(exc)
    if spec.get("predecessor_bindings") != PREDECESSOR_BINDINGS:
        return "predecessor_binding_drift"
    if spec.get("source_profile_bindings") != expected_source_profile_bindings(str(spec["selector"])):
        return "source_profile_binding_drift"
    event = spec.get("p133_event")
    if not isinstance(event, Mapping) or event.get("event_hash") != _self_hash(event, "event_hash"):
        return "p133_event_hash_invalid"
    if event.get("domain") in PROTECTED_DOMAINS:
        return "protected_domain"
    correlated_event = spec.get("correlated_p133_event")
    if correlated_event is not None:
        if not isinstance(correlated_event, Mapping) or correlated_event.get("event_hash") != _self_hash(correlated_event, "event_hash"):
            return "correlated_p133_event_hash_invalid"
        if correlated_event.get("domain") in PROTECTED_DOMAINS:
            return "protected_domain"
    if spec.get("replay_mode") == "correlated_duplicate":
        if not isinstance(correlated_event, Mapping):
            return "correlated_p133_event_missing"
        if event.get("event_id") == correlated_event.get("event_id") or event.get("incident_id") == correlated_event.get("incident_id"):
            return "correlated_p133_identity_collision"
        correlation_id = event.get("correlation_id")
        if not isinstance(correlation_id, str) or not correlation_id or correlated_event.get("correlation_id") != correlation_id:
            return "correlated_p133_binding_invalid"
    evidence = spec["evidence"]
    expected_hash = stable_hash({
        "event": event, "correlated_event": correlated_event,
        "predecessor_bindings": spec["predecessor_bindings"],
        "source_profile_bindings": spec["source_profile_bindings"], "evidence": evidence,
    })
    if evidence.get("schema_valid") is not True:
        return "evidence_schema_invalid"
    if evidence.get("hash_valid") is not True or spec.get("evidence_hash") != expected_hash:
        return "evidence_hash_invalid"
    if spec.get("existing_ack") == "conflict" and ack_path.exists():
        return "p133_ack_cas_conflict"
    return None


def _adjudicate_hypotheses(spec: Mapping[str, Any]) -> dict[str, Any]:
    hypotheses = deepcopy(list(spec["hypotheses"]))
    if len(hypotheses) < 2:
        raise P145DutyOfficerError("competing_hypotheses_required")
    evidence = spec["evidence"]
    receipt: dict[str, Any] = {
        "schema_version": "p145.hypothesis_adjudication.v1",
        "top_hypothesis": ACTION_HYPOTHESIS[str(spec["selected_action"])],
        "selected_action": spec["selected_action"], "hypotheses": hypotheses,
        "confidence_margin_bps": evidence["confidence_margin_bps"],
        "minimum_margin_bps": evidence["minimum_margin_bps"],
        "support_complete": evidence["support_complete"], "contradiction_absent": evidence["contradiction_absent"],
        "fresh": evidence["fresh"], "critical_missing_evidence": evidence["critical_missing_evidence"],
        "prompt_injection_present": evidence["prompt_injection_present"],
    }
    receipt["adjudication_hash"] = _self_hash(receipt, "adjudication_hash")
    return receipt


def _adjudication_allows_policy(receipt: Mapping[str, Any]) -> bool:
    return (
        receipt["support_complete"] is True and receipt["contradiction_absent"] is True
        and receipt["fresh"] is True and receipt["critical_missing_evidence"] is False
        and receipt["prompt_injection_present"] is False
        and receipt["confidence_margin_bps"] >= receipt["minimum_margin_bps"]
    )


def _adjudication_blocker(receipt: Mapping[str, Any]) -> str:
    if receipt["fresh"] is not True:
        return "stale_evidence"
    if receipt["critical_missing_evidence"] is True or receipt["support_complete"] is not True:
        return "critical_evidence_missing"
    if receipt["prompt_injection_present"] is True:
        return "prompt_injection_is_untrusted_evidence"
    if receipt["contradiction_absent"] is not True:
        return "contradictory_evidence"
    return "hypothesis_margin_insufficient"


def _policy_receipt(spec: Mapping[str, Any], action: str) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "schema_version": LOCAL_POLICY_RECEIPT_SCHEMA_VERSION, "episode_id": spec["episode_id"],
        "case_id": spec["case_id"], "authorized_action": action, "policy": "p145.local_policy.frozen.v1",
        "scope": "process_owned_fault_lab_only", "not_human_or_external_approval": True,
        "forbidden_authority": zero_forbidden_authority(),
    }
    receipt["receipt_hash"] = _self_hash(receipt, "receipt_hash")
    return receipt


def _scenario_observations(state: Mapping[str, Any], mode: str) -> list[dict[str, Any]]:
    count = 1 if mode == "insufficient" else 3 if mode == "flapping" else 2
    observations = [build_observation(state, logical_time=100 + index, stale=mode == "stale_observation") for index in range(count)]
    base = int(state["observation_seq"])
    for index, observation in enumerate(observations):
        observation["sequence"] = base + index
        if mode == "out_of_order":
            observation["sequence"] = base + (1 - index)
        elif mode == "gap" and index == 1:
            observation["sequence"] = base + 2
        if mode == "clock_rollback" and index == 1:
            observation["logical_time"] = 99
        if mode == "primary_only":
            observation["signals"]["latency_ms"] = 900
        elif mode in {"recurrence", "delayed_regression"} and index == count - 1:
            observation["signals"]["error_rate_bps"] = 2200
        elif mode == "flapping" and index == 1:
            observation["signals"]["error_rate_bps"] = 2200
        elif mode == "partial":
            observation["signals"]["backlog"] = 900
        observation["observation_hash"] = _self_hash(observation, "observation_hash")
    return observations


def _validate_observation(raw: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(raw))
    if (
        set(value) != _OBSERVATION_FIELDS
        or value.get("schema_version") != OBSERVATION_SCHEMA_VERSION
        or not _is_sha256(value.get("state_hash"))
        or value.get("observation_hash") != _self_hash(value, "observation_hash")
    ):
        raise P145DutyOfficerError("observation_hash_invalid")
    signals = value.get("signals")
    if not isinstance(signals, Mapping) or set(signals) != _OBSERVATION_SIGNAL_FIELDS:
        raise P145DutyOfficerError("observation_signals_invalid")
    for key in _OBSERVATION_SIGNAL_FIELDS:
        if type(signals.get(key)) is not int or signals[key] < 0:
            raise P145DutyOfficerError(f"invalid_observation_signal:{key}")
    if any(signals[key] > 10000 for key in (
        "error_rate_bps", "saturation_bps", "dependency_timeout_bps", "collateral_health_bps",
    )):
        raise P145DutyOfficerError("observation_signal_range_invalid")
    if (
        type(value.get("sequence")) is not int
        or value["sequence"] < 0
        or type(value.get("logical_time")) is not int
        or value["logical_time"] < 0
        or type(value.get("fresh")) is not bool
    ):
        raise P145DutyOfficerError("observation_metadata_invalid")
    return value


def _validate_recovery_proof(raw: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(raw))
    blockers = value.get("blockers")
    observation_hashes = value.get("observation_hashes")
    if (
        set(value) != _RECOVERY_PROOF_FIELDS
        or value.get("schema_version") != RECOVERY_PROOF_SCHEMA_VERSION
        or type(value.get("recovered")) is not bool
        or type(blockers) is not list
        or any(not isinstance(item, str) or not item for item in blockers)
        or blockers != sorted(set(blockers))
        or type(observation_hashes) is not list
        or any(not _is_sha256(item) for item in observation_hashes)
        or not _is_sha256(value.get("current_state_hash"))
        or type(value.get("consecutive_required")) is not int
        or value["consecutive_required"] <= 0
        or type(value.get("collateral_floor")) is not int
        or not 0 <= value["collateral_floor"] <= 10000
        or value.get("recovery_proof_hash") != _self_hash(value, "recovery_proof_hash")
    ):
        raise P145DutyOfficerError("terminal_truth_recovery_proof_invalid")
    return value


def _validate_action_history(
    entries: list[dict[str, Any]], spec: Mapping[str, Any],
) -> tuple[dict[str, Any], int]:
    initial = validate_fault_lab_state(spec["initial_lab_state"])
    state = initial
    phases = ("action_intent_committed", "lab_mutated", "action_receipt_committed")
    grouped = {phase: [entry for entry in entries if entry["phase"] == phase] for phase in phases}
    if any(len(items) > int(spec["action_count"]) for items in grouped.values()):
        raise P145DutyOfficerError("terminal_truth_action_count_invalid")
    for phase in phases:
        indexes = [entry["payload"].get("action_index") for entry in grouped[phase]]
        if any(type(index) is not int for index in indexes) or indexes != sorted(set(indexes)):
            raise P145DutyOfficerError("terminal_truth_action_index_invalid")
    committed = 0
    for index in range(int(spec["action_count"])):
        action_id = _action_id(spec, index)
        intent = next((entry for entry in grouped["action_intent_committed"] if entry["payload"].get("action_index") == index), None)
        mutated = next((entry for entry in grouped["lab_mutated"] if entry["payload"].get("action_index") == index), None)
        receipt = next((entry for entry in grouped["action_receipt_committed"] if entry["payload"].get("action_index") == index), None)
        if intent is None:
            if mutated is not None or receipt is not None:
                raise P145DutyOfficerError("terminal_truth_action_predecessor_invalid")
            continue
        expected_intent = {
            "action_id": action_id,
            "action_index": index,
            "action": spec["selected_action"],
            "pre_state_hash": state["state_hash"],
        }
        if intent["payload"] != expected_intent:
            raise P145DutyOfficerError("terminal_truth_action_intent_invalid")
        if mutated is None:
            if receipt is not None:
                raise P145DutyOfficerError("terminal_truth_action_predecessor_invalid")
            continue
        if entries.index(mutated) <= entries.index(intent):
            raise P145DutyOfficerError("terminal_truth_action_predecessor_invalid")
        if spec["selected_action"] == "observe_only":
            raise P145DutyOfficerError("terminal_truth_observe_only_mutation")
        state = apply_lab_transform(state, str(spec["selected_action"]), action_id=action_id)
        if mutated["payload"] != {
            "action_id": action_id,
            "action_index": index,
            "post_state_hash": state["state_hash"],
        }:
            raise P145DutyOfficerError("terminal_truth_lab_mutation_invalid")
        if receipt is None:
            continue
        if entries.index(receipt) <= entries.index(mutated):
            raise P145DutyOfficerError("terminal_truth_action_predecessor_invalid")
        expected_receipt = {
            "schema_version": ACTION_RECEIPT_SCHEMA_VERSION,
            "action_id": action_id,
            "action_index": index,
            "post_state_hash": state["state_hash"],
            "rollback_pre_state_hash": initial["state_hash"],
        }
        expected_receipt["receipt_hash"] = _self_hash(expected_receipt, "receipt_hash")
        if receipt["payload"] != expected_receipt:
            raise P145DutyOfficerError("terminal_truth_action_receipt_invalid")
        committed += 1
    known_ids = {_action_id(spec, index) for index in range(int(spec["action_count"]))}
    for phase in phases:
        if any(entry["payload"].get("action_id") not in known_ids for entry in grouped[phase]):
            raise P145DutyOfficerError("terminal_truth_action_identity_invalid")
    return state, committed


def _terminal_observations(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_validate_observation(entry["payload"]) for entry in entries if entry["phase"] == "observation_committed"]


def _expected_durable_lab_state(
    entries: list[dict[str, Any]], spec: Mapping[str, Any],
) -> dict[str, Any]:
    action_state, _committed = _validate_action_history(entries, spec)
    rollback_mutations = [entry for entry in entries if entry["phase"] == "rollback_lab_mutated"]
    if rollback_mutations:
        rollback_intents = [entry for entry in entries if entry["phase"] == "rollback_intent_committed"]
        if len(rollback_mutations) != 1 or len(rollback_intents) != 1:
            raise P145DutyOfficerError("durable_rollback_projection_invalid")
        initial = validate_fault_lab_state(spec["initial_lab_state"])
        action_id = rollback_intents[0]["payload"].get("action_id")
        if not isinstance(action_id, str) or rollback_intents[0]["payload"] != {
            "action_id": action_id,
            "pre_state_hash": initial["state_hash"],
        }:
            raise P145DutyOfficerError("terminal_truth_rollback_intent_invalid")
        expected = rollback_lab_transform(action_state, initial, action_id=action_id)
        if spec["observation_mode"] == "rollback_collateral_harm":
            expected["collateral_health_bps"] = 7000
            expected["state_hash"] = _self_hash(expected, "state_hash")
        if rollback_mutations[0]["payload"] != {
            "action_id": action_id,
            "restored_state_hash": expected["state_hash"],
        }:
            raise P145DutyOfficerError("durable_rollback_projection_invalid")
        return expected
    if any(entry["phase"] == "verification_failed" for entry in entries) and spec["observation_mode"] == "lab_drift":
        action_state["latency_ms"] += 1
        action_state["generation"] += 1
        action_state["state_hash"] = _self_hash(action_state, "state_hash")
    return action_state


def _validate_recovery_terminal(
    entries: list[dict[str, Any]], spec: Mapping[str, Any], current: Mapping[str, Any],
) -> None:
    action_state, committed = _validate_action_history(entries, spec)
    if committed != int(spec["action_count"]) or validate_fault_lab_state(current) != action_state:
        raise P145DutyOfficerError("terminal_truth_current_lab_invalid")
    recovery_entries = [entry for entry in entries if entry["phase"] == "recovery_receipt_committed"]
    verification_entries = [entry for entry in entries if entry["phase"] == "verification_started"]
    observation_entries = [entry for entry in entries if entry["phase"] == "observation_committed"]
    if len(recovery_entries) != 1 or len(verification_entries) != 1 or not observation_entries:
        raise P145DutyOfficerError("terminal_truth_recovery_receipt_missing")
    if not (
        entries.index(verification_entries[0])
        < min(entries.index(entry) for entry in observation_entries)
        <= max(entries.index(entry) for entry in observation_entries)
        < entries.index(recovery_entries[0])
    ):
        raise P145DutyOfficerError("terminal_truth_verification_predecessor_invalid")
    persisted = _validate_recovery_proof(recovery_entries[0]["payload"])
    observations = _terminal_observations(entries)
    recomputed = verify_recovery(
        current,
        observations,
        consecutive_required=persisted["consecutive_required"],
        collateral_floor=persisted["collateral_floor"],
    )
    if persisted != recomputed or recomputed["recovered"] is not True or recomputed["blockers"]:
        raise P145DutyOfficerError("terminal_truth_recovery_not_verified")


def _validate_rollback_terminal(
    entries: list[dict[str, Any]], spec: Mapping[str, Any], current: Mapping[str, Any],
) -> None:
    action_state, _committed = _validate_action_history(entries, spec)
    initial = validate_fault_lab_state(spec["initial_lab_state"])
    intents = [entry for entry in entries if entry["phase"] == "rollback_intent_committed"]
    receipts = [entry for entry in entries if entry["phase"] == "rollback_receipt_committed"]
    mutations = [entry for entry in entries if entry["phase"] == "rollback_lab_mutated"]
    if len(intents) != 1 or len(receipts) != 1 or len(mutations) > 1:
        raise P145DutyOfficerError("terminal_truth_rollback_receipt_missing")
    if entries.index(receipts[0]) <= entries.index(intents[0]):
        raise P145DutyOfficerError("terminal_truth_rollback_predecessor_invalid")
    if mutations and not entries.index(intents[0]) < entries.index(mutations[0]) < entries.index(receipts[0]):
        raise P145DutyOfficerError("terminal_truth_rollback_predecessor_invalid")
    action_id = str(intents[0]["payload"].get("action_id"))
    if action_id not in {_action_id(spec, index) for index in range(int(spec["action_count"]))}:
        raise P145DutyOfficerError("terminal_truth_rollback_action_identity_invalid")
    if intents[0]["payload"] != {"action_id": action_id, "pre_state_hash": initial["state_hash"]}:
        raise P145DutyOfficerError("terminal_truth_rollback_intent_invalid")
    if mutations:
        expected_state = rollback_lab_transform(action_state, initial, action_id=action_id)
        if spec["observation_mode"] == "rollback_collateral_harm":
            expected_state["collateral_health_bps"] = 7000
            expected_state["state_hash"] = _self_hash(expected_state, "state_hash")
        if mutations[0]["payload"] != {
            "action_id": action_id,
            "restored_state_hash": expected_state["state_hash"],
        }:
            raise P145DutyOfficerError("terminal_truth_rollback_mutation_invalid")
    else:
        expected_state = initial
    if validate_fault_lab_state(current) != expected_state:
        raise P145DutyOfficerError("terminal_truth_rollback_lab_invalid")
    expected_receipt = {
        "schema_version": ROLLBACK_RECEIPT_SCHEMA_VERSION,
        "action_id": action_id,
        "restored_state_hash": expected_state["state_hash"],
        "expected_pre_state_hash": initial["state_hash"],
        "verified": True,
    }
    expected_receipt["receipt_hash"] = _self_hash(expected_receipt, "receipt_hash")
    if receipts[0]["payload"] != expected_receipt:
        raise P145DutyOfficerError("terminal_truth_rollback_receipt_invalid")


def _validate_escalation_journal_receipt(entries: list[dict[str, Any]]) -> dict[str, Any]:
    receipts = [entry for entry in entries if entry["phase"] == "escalation_receipt_committed"]
    if len(receipts) != 1:
        raise P145DutyOfficerError("escalation_receipt_journal_projection_invalid")
    receipt = deepcopy(dict(receipts[0]["payload"]))
    if (
        set(receipt) != _ESCALATION_RECEIPT_FIELDS
        or receipt.get("schema_version") != ESCALATION_RECEIPT_SCHEMA_VERSION
        or not isinstance(receipt.get("reason"), str)
        or not receipt["reason"]
        or receipt.get("local_only") is not True
        or receipt.get("receipt_hash") != _self_hash(receipt, "receipt_hash")
    ):
        raise P145DutyOfficerError("escalation_receipt_schema_or_hash_invalid")
    return receipt


def _validate_human_escalation_terminal(
    entries: list[dict[str, Any]], spec: Mapping[str, Any], current: Mapping[str, Any] | None,
) -> None:
    receipt = _validate_escalation_journal_receipt(entries)
    expected_reason = _expected_escalation_reason(entries, spec)
    if receipt["reason"] != expected_reason:
        raise P145DutyOfficerError("escalation_receipt_reason_drift")
    if current is not None and validate_fault_lab_state(current) != _expected_durable_lab_state(entries, spec):
        raise P145DutyOfficerError("terminal_truth_current_lab_invalid")
    verification = [entry for entry in entries if entry["phase"] == "verification_failed"]
    if verification:
        if len(verification) != 1 or current is None:
            raise P145DutyOfficerError("terminal_truth_verification_projection_invalid")
        observation_entries = [entry for entry in entries if entry["phase"] == "observation_committed"]
        verification_started = [entry for entry in entries if entry["phase"] == "verification_started"]
        if (
            len(verification_started) != 1
            or not observation_entries
            or not entries.index(verification_started[0])
            < min(entries.index(entry) for entry in observation_entries)
            <= max(entries.index(entry) for entry in observation_entries)
            < entries.index(verification[0])
        ):
            raise P145DutyOfficerError("terminal_truth_verification_predecessor_invalid")
        _validate_action_history(entries, spec)
        persisted = _validate_recovery_proof(verification[0]["payload"])
        recomputed = verify_recovery(
            current,
            _terminal_observations(entries),
            consecutive_required=persisted["consecutive_required"],
            collateral_floor=persisted["collateral_floor"],
        )
        if persisted != recomputed or recomputed["recovered"] is not False:
            raise P145DutyOfficerError("terminal_truth_verification_blockers_invalid")
    elif any(entry["phase"] == "rollback_receipt_committed" for entry in entries):
        if current is None:
            raise P145DutyOfficerError("terminal_truth_rollback_lab_missing")
        _validate_rollback_terminal(entries, spec, current)
    elif any(entry["phase"] == "rollback_intent_committed" for entry in entries):
        _validate_action_history(entries, spec)
        if spec["rollback_mode"] != "fail":
            raise P145DutyOfficerError("terminal_truth_rollback_failure_invalid")


def _expected_escalation_reason(entries: list[dict[str, Any]], spec: Mapping[str, Any]) -> str:
    phases = {entry["phase"] for entry in entries}
    registered = entries[0]["payload"] if entries else {}
    actual = next(
        entry["payload"].get("reason")
        for entry in entries
        if entry["phase"] == "escalation_receipt_committed"
    )
    if registered.get("tamper_recovery") is True:
        allowed_prefixes = (
            "crash_state_", "cursor_", "direct_terminal_write", "duplicate_json_key:",
            "durable_", "escalation_receipt_", "fault_lab_", "invalid_fault_lab_",
            "journal_", "lease_", "noncanonical_json:", "p133_ack_", "terminal_sequence",
            "terminal_truth_",
        )
        if isinstance(actual, str) and actual.startswith(allowed_prefixes):
            return actual
        raise P145DutyOfficerError("escalation_receipt_reason_drift")
    if "verification_failed" in phases:
        return "recovery_not_verified"
    if "rollback_receipt_committed" in phases:
        return str(spec["observation_mode"])
    if "rollback_intent_committed" in phases:
        return "rollback_failed"
    if "preflight_blocked" in phases:
        return "rollback_or_preflight_invalid"
    if "deadman_handoff_committed" in phases:
        return "dead_runner_handoff"
    if spec.get("lease_mode") == "contention" and "action_receipt_committed" in phases:
        return "same_resource_lease_contention"
    if spec.get("fault_injection") == "lease_expiry_during_verification" and "verification_started" in phases:
        return "lease_expired_during_verification"
    if spec.get("fault_injection") == "journal_disk_full" and "local_policy_authorized" in phases:
        return "journal_disk_full"
    if "hypotheses_adjudicated" in phases:
        adjudication = _adjudicate_hypotheses(spec)
        if not _adjudication_allows_policy(adjudication):
            return _adjudication_blocker(adjudication)
        policy = spec["policy"]
        if (
            policy["allowed"] is not True
            or policy["blast_radius_bps"] > policy["max_blast_radius_bps"]
            or policy["action_budget"] < spec["action_count"]
        ):
            return "local_policy_rejected"
    if spec.get("existing_ack") == "conflict":
        return "p133_ack_cas_conflict"
    blocker = _pre_ownership_blocker(spec, Path("__p145_no_ack_artifact__"))
    if blocker is not None:
        return blocker
    raise P145DutyOfficerError("escalation_receipt_reason_unbound")


def _action_phase_sequence(entries: list[dict[str, Any]], spec: Mapping[str, Any]) -> list[str]:
    phases: list[str] = []
    for index in range(int(spec["action_count"])):
        for phase in ("action_intent_committed", "lab_mutated", "action_receipt_committed"):
            if any(
                entry["phase"] == phase and entry["payload"].get("action_index") == index
                for entry in entries
            ):
                phases.append(phase)
    return phases


def _validate_complete_terminal_sequence(
    entries: list[dict[str, Any]], spec: Mapping[str, Any],
) -> None:
    phases = [str(entry["phase"]) for entry in entries]
    terminal = _terminal_from_entries(entries)
    if terminal is None:
        raise P145DutyOfficerError("terminal_sequence_missing")
    terminal_suffix = ["escalation_receipt_committed", "human_escalation_required"]
    if terminal == "human_escalation_required" and "evidence_validated" not in phases:
        expected = ["registered", *terminal_suffix]
    else:
        if phases[: len(_TERMINAL_PREFIX)] != _TERMINAL_PREFIX:
            raise P145DutyOfficerError("terminal_sequence_prefix_invalid")
        action_phases = _action_phase_sequence(entries, spec)
        correlation_phases = [phase for phase in phases if phase in _CORRELATION_PHASES]
        observations = ["observation_committed"] * phases.count("observation_committed")
        if terminal == "recovery_verified":
            policy_phase = (
                "observe_only_authorized"
                if spec["selected_action"] == "observe_only"
                else "local_policy_authorized"
            )
            expected = [
                *_TERMINAL_PREFIX,
                policy_phase,
                *action_phases,
                *correlation_phases,
                "verification_started",
                *observations,
                "recovery_receipt_committed",
                "recovery_verified",
            ]
        elif terminal == "rollback_verified":
            rollback_phases = ["rollback_intent_committed"]
            if "rollback_lab_mutated" in phases:
                rollback_phases.append("rollback_lab_mutated")
            rollback_phases.extend(["rollback_receipt_committed", "rollback_verified"])
            expected = [*_TERMINAL_PREFIX, "local_policy_authorized", *action_phases]
            if "verification_started" in phases:
                expected.append("verification_started")
            expected.extend(rollback_phases)
        elif "deadman_handoff_committed" in phases:
            expected = [*_TERMINAL_PREFIX, "deadman_handoff_committed", *terminal_suffix]
        elif "local_policy_authorized" not in phases and "observe_only_authorized" not in phases:
            expected = [*_TERMINAL_PREFIX, *terminal_suffix]
        elif "preflight_blocked" in phases:
            expected = [
                *_TERMINAL_PREFIX, "local_policy_authorized", "preflight_blocked", *terminal_suffix,
            ]
        else:
            policy_phase = (
                "observe_only_authorized"
                if "observe_only_authorized" in phases
                else "local_policy_authorized"
            )
            expected = [*_TERMINAL_PREFIX, policy_phase, *action_phases, *correlation_phases]
            if "verification_failed" in phases:
                expected.extend([
                    "verification_started", *observations, "verification_failed", *terminal_suffix,
                ])
            elif "rollback_receipt_committed" in phases:
                if "verification_started" in phases:
                    expected.append("verification_started")
                expected.append("rollback_intent_committed")
                if "rollback_lab_mutated" in phases:
                    expected.append("rollback_lab_mutated")
                expected.extend(["rollback_receipt_committed", *terminal_suffix])
            elif "rollback_intent_committed" in phases:
                if "verification_started" in phases:
                    expected.append("verification_started")
                expected.extend(["rollback_intent_committed", *terminal_suffix])
            elif "verification_started" in phases:
                expected.extend(["verification_started", *terminal_suffix])
            else:
                expected.extend(terminal_suffix)
    if phases != expected:
        raise P145DutyOfficerError("terminal_sequence_invalid")


def _validate_terminal_truth(
    entries: list[dict[str, Any]], spec: Mapping[str, Any], lab_path: Path,
) -> None:
    terminal = _terminal_from_entries(entries)
    if terminal is None or entries[-1]["payload"] != {"terminal_status": terminal}:
        raise P145DutyOfficerError("terminal_truth_payload_invalid")
    _validate_complete_terminal_sequence(entries, spec)
    current = validate_fault_lab_state(_read_json(lab_path)) if lab_path.exists() else None
    if terminal == "recovery_verified":
        if current is None:
            raise P145DutyOfficerError("terminal_truth_lab_missing")
        _validate_recovery_terminal(entries, spec, current)
    elif terminal == "rollback_verified":
        if current is None:
            raise P145DutyOfficerError("terminal_truth_lab_missing")
        _validate_rollback_terminal(entries, spec, current)
    else:
        _validate_human_escalation_terminal(entries, spec, current)


def _validate_escalation_side_receipt(
    receipt: Mapping[str, Any], entries: list[dict[str, Any]],
) -> None:
    journal_receipt = _validate_escalation_journal_receipt(entries)
    if dict(receipt) != journal_receipt:
        raise P145DutyOfficerError("escalation_receipt_side_projection_invalid")


def _crash_recovery_strategy(point: str) -> str:
    if point in {"action_receipt_before_fsync", "lab_fsync_failure"}:
        return "rollback"
    if point == "journal_disk_full":
        return "escalate"
    return "resume"


def _validate_crash_state(marker: Mapping[str, Any], spec: Mapping[str, Any]) -> None:
    if (
        set(marker) != _CRASH_FIELDS
        or marker.get("schema_version") != CRASH_SCHEMA_VERSION
        or marker.get("crash_point") not in FAULT_INJECTION_MODES
        or marker.get("crash_point") != spec.get("fault_injection")
        or marker.get("recovery_strategy") != _crash_recovery_strategy(str(marker.get("crash_point")))
        or marker.get("crash_hash") != _self_hash(marker, "crash_hash")
    ):
        raise P145DutyOfficerError("crash_state_schema_or_projection_invalid")


def _validate_journal_entries(entries: list[dict[str, Any]], spec: Mapping[str, Any]) -> None:
    previous = _ZERO_HASH
    seen_nonrepeatable: set[str] = set()
    phases: list[str] = []
    for index, entry in enumerate(entries, start=1):
        if set(entry) != _JOURNAL_FIELDS or entry.get("schema_version") != JOURNAL_SCHEMA_VERSION:
            raise P145DutyOfficerError("journal_schema_invalid")
        if entry.get("episode_id") != spec["episode_id"] or entry.get("case_id") != spec["case_id"]:
            raise P145DutyOfficerError("journal_episode_binding_invalid")
        if entry.get("cas_version") != index or entry.get("logical_time") != index:
            raise P145DutyOfficerError("journal_cas_or_time_drift")
        if entry.get("previous_receipt_hash") != previous:
            raise P145DutyOfficerError("journal_missing_predecessor")
        if entry.get("payload_hash") != stable_hash(entry.get("payload")) or entry.get("receipt_hash") != _self_hash(entry, "receipt_hash"):
            raise P145DutyOfficerError("journal_receipt_hash_invalid")
        phase = str(entry.get("phase"))
        if phase not in EXPECTED_PHASES or not isinstance(entry.get("payload"), Mapping):
            raise P145DutyOfficerError("journal_phase_or_payload_invalid")
        if phase in seen_nonrepeatable and phase not in _REPEATABLE_PHASES:
            raise P145DutyOfficerError("journal_duplicate_phase")
        if phase not in _REPEATABLE_PHASES:
            seen_nonrepeatable.add(phase)
        phases.append(phase)
        previous = str(entry["receipt_hash"])
    if phases and phases[0] != "registered":
        raise P145DutyOfficerError("journal_phase_reorder")
    for terminal in TERMINALS:
        if terminal in phases:
            terminal_index = phases.index(terminal)
            expected_previous = {
                "recovery_verified": "recovery_receipt_committed",
                "rollback_verified": "rollback_receipt_committed",
                "human_escalation_required": "escalation_receipt_committed",
            }[terminal]
            if terminal_index != len(phases) - 1 or terminal_index == 0 or phases[terminal_index - 1] != expected_previous:
                raise P145DutyOfficerError("direct_terminal_write")
    required_prefix = ["registered", "evidence_validated", "ownership_intent_committed", "owned_acknowledged", "hypotheses_adjudicated"]
    for phase in phases:
        if phase in required_prefix:
            position = required_prefix.index(phase)
            if phases[: position + 1] != required_prefix[: position + 1]:
                raise P145DutyOfficerError("journal_phase_reorder")
    correlated_phases = [
        "correlated_event_registered",
        "correlated_ownership_intent_committed",
        "correlated_owned_acknowledged",
        "correlation_action_receipt_committed",
    ]
    observed_correlated = [phase for phase in phases if phase in correlated_phases]
    if observed_correlated:
        if spec.get("replay_mode") != "correlated_duplicate":
            raise P145DutyOfficerError("unexpected_correlation_phase")
        if observed_correlated != correlated_phases[: len(observed_correlated)]:
            raise P145DutyOfficerError("correlation_phase_reorder")
        first_correlation_index = phases.index("correlated_event_registered")
        if "action_receipt_committed" not in phases[:first_correlation_index]:
            raise P145DutyOfficerError("correlation_action_receipt_missing")
        _validate_correlation_journal_proof(entries, spec)


def _validate_correlation_journal_proof(entries: list[dict[str, Any]], spec: Mapping[str, Any]) -> None:
    first_event = spec["p133_event"]
    second_event = spec["correlated_p133_event"]
    if not isinstance(second_event, Mapping):
        raise P145DutyOfficerError("correlated_p133_event_missing")
    by_phase = {entry["phase"]: entry for entry in entries}
    registered = by_phase.get("correlated_event_registered")
    if registered is not None and registered["payload"] != {
        "event_id": second_event["event_id"],
        "incident_id": second_event["incident_id"],
        "event_hash": second_event["event_hash"],
        "correlation_id": second_event["correlation_id"],
    }:
        raise P145DutyOfficerError("correlated_event_registration_invalid")
    intent = by_phase.get("correlated_ownership_intent_committed")
    if intent is not None and intent["payload"] != {
        "event_id": second_event["event_id"],
        "correlation_id": second_event["correlation_id"],
    }:
        raise P145DutyOfficerError("correlated_ownership_intent_invalid")
    acknowledgement = by_phase.get("correlated_owned_acknowledged")
    if acknowledgement is not None:
        ack = acknowledgement["payload"]
        if (
            ack.get("event_id") != second_event["event_id"]
            or ack.get("event_hash") != second_event["event_hash"]
            or ack.get("incident_id") != second_event["incident_id"]
            or ack.get("correlation_id") != second_event["correlation_id"]
            or ack.get("ack_hash") != _self_hash(ack, "ack_hash")
        ):
            raise P145DutyOfficerError("correlated_ack_invalid")
    correlation = by_phase.get("correlation_action_receipt_committed")
    if correlation is not None:
        action_entry = next(entry for entry in entries if entry["phase"] == "action_receipt_committed")
        expected = _correlation_action_receipt(spec, action_entry["payload"]["receipt_hash"])
        if correlation["payload"] != expected or first_event.get("correlation_id") != second_event.get("correlation_id"):
            raise P145DutyOfficerError("correlation_action_receipt_invalid")


def _validate_acknowledgement_projection(
    acknowledgement: Mapping[str, Any], event: Mapping[str, Any], episode_id: str,
    lease: Mapping[str, Any],
) -> None:
    expected_fields = {
        "schema_version", "event_id", "event_hash", "incident_id", "correlation_id", "episode_id",
        "lease_owner", "lease_epoch", "lease_cas_version", "lease_receipt_hash",
        "meaning", "authority_counters", "ack_hash",
    }
    if set(acknowledgement) != expected_fields:
        raise P145DutyOfficerError("p133_ack_artifact_schema_invalid")
    if (
        acknowledgement.get("schema_version") != P133_ACK_SCHEMA_VERSION
        or acknowledgement.get("event_id") != event.get("event_id")
        or acknowledgement.get("event_hash") != event.get("event_hash")
        or acknowledgement.get("incident_id") != event.get("incident_id")
        or acknowledgement.get("correlation_id") != event.get("correlation_id")
        or acknowledgement.get("episode_id") != episode_id
        or not isinstance(acknowledgement.get("lease_owner"), str)
        or not acknowledgement["lease_owner"]
        or type(acknowledgement.get("lease_epoch")) is not int
        or type(acknowledgement.get("lease_cas_version")) is not int
        or not _is_sha256(acknowledgement.get("lease_receipt_hash"))
        or acknowledgement.get("meaning") != "local_ownership_only_not_external_delivery_or_closure"
        or acknowledgement.get("authority_counters") != zero_forbidden_authority()
        or acknowledgement.get("ack_hash") != _self_hash(acknowledgement, "ack_hash")
    ):
        raise P145DutyOfficerError("p133_ack_artifact_projection_invalid")
    if not any(
        receipt.get("owner_id") == acknowledgement["lease_owner"]
        and receipt.get("epoch") == acknowledgement["lease_epoch"]
        and receipt.get("cas_version") == acknowledgement["lease_cas_version"]
        and receipt.get("active") is True
        and receipt.get("receipt_hash") == acknowledgement["lease_receipt_hash"]
        for receipt in lease["ownership_history"]
    ):
        raise P145DutyOfficerError("p133_ack_lease_binding_invalid")


def _derive_counts(
    case_dir: Path,
    entries: list[dict[str, Any]],
    *,
    baseline: Mapping[str, Any] | None,
    acknowledged_artifact_count: int,
) -> dict[str, dict[str, int]]:
    start = int(baseline.get("entry_count", 0)) if baseline else 0
    measured = entries[start:]
    phase_counts = {phase: sum(1 for entry in measured if entry["phase"] == phase) for phase in {entry["phase"] for entry in measured}}
    lease = _read_json_if_present(case_dir / "lease.json")
    base_lease = baseline.get("lease", {}) if baseline else {}
    runtime = zero_runtime_activity()
    runtime["journal_append_count"] = len(measured)
    runtime["journal_fsync_count"] = len(measured)
    runtime["lease_acquire_count"] = int(lease.get("acquire_count", 0)) - int(base_lease.get("acquire_count", 0))
    runtime["lease_renew_count"] = int(lease.get("renew_count", 0)) - int(base_lease.get("renew_count", 0))
    runtime["p133_ack_write_count"] = acknowledged_artifact_count - int(
        baseline.get("acknowledged_artifact_count", 0) if baseline else 0
    )
    runtime["heartbeat_write_count"] = phase_counts.get("deadman_handoff_committed", 0)
    runtime["cursor_write_count"] = int((case_dir / "cursor.json").exists()) - int(bool(baseline and baseline.get("cursor_exists")))
    runtime["escalation_receipt_count"] = phase_counts.get("escalation_receipt_committed", 0)
    lab = zero_lab_activity()
    lab["local_policy_authorization_count"] = phase_counts.get("local_policy_authorized", 0) + phase_counts.get("observe_only_authorized", 0)
    lab["lab_state_read_count"] = runtime["lease_acquire_count"] + runtime["lease_renew_count"]
    lab["lab_state_mutation_count"] = phase_counts.get("lab_mutated", 0) + phase_counts.get("rollback_lab_mutated", 0)
    lab["lab_state_fsync_count"] = lab["lab_state_mutation_count"] + (1 if start == 0 and (case_dir / "fault-lab-state.json").exists() else 0)
    lab["action_intent_count"] = phase_counts.get("action_intent_committed", 0)
    lab["action_commit_count"] = phase_counts.get("action_receipt_committed", 0)
    lab["observation_count"] = phase_counts.get("observation_committed", 0)
    lab["recovery_proof_count"] = phase_counts.get("recovery_receipt_committed", 0) + phase_counts.get("verification_failed", 0)
    lab["rollback_intent_count"] = phase_counts.get("rollback_intent_committed", 0)
    lab["rollback_commit_count"] = phase_counts.get("rollback_receipt_committed", 0)
    lease_writes = int(lease.get("write_count", 0)) - int(base_lease.get("write_count", 0))
    runtime["directory_fsync_count"] = lease_writes + runtime["p133_ack_write_count"] + lab["lab_state_fsync_count"] + runtime["cursor_write_count"]
    resources = zero_resource_usage()
    journal_path = case_dir / "journal.jsonl"
    lab_path = case_dir / "fault-lab-state.json"
    resources["journal_bytes"] = journal_path.stat().st_size if journal_path.exists() else 0
    resources["lab_bytes"] = lab_path.stat().st_size if lab_path.exists() else 0
    resources["artifact_count"] = sum(1 for path in case_dir.rglob("*") if path.is_file())
    return {
        "forbidden_authority": zero_forbidden_authority(), "runtime_activity": runtime,
        "lab_activity": lab, "evaluator_activity": zero_evaluator_activity(), "resource_usage": resources,
    }


def _snapshot(controller: _EpisodeController) -> dict[str, Any]:
    entries = controller._load_journal()
    return {
        "entry_count": len(entries), "lease": _read_json_if_present(controller.lease_path),
        "cursor_exists": controller.cursor_path.exists(),
        "acknowledged_artifact_count": len(controller._reconcile_acknowledgements(entries)),
    }


def _run_with_replay(spec: Mapping[str, Any], case_dir: Path, notes: list[str]) -> _EpisodeController:
    controller = _EpisodeController(spec, case_dir, "worker-a", notes, consumed_faults=set())
    controller.run()
    return controller


def _prepare_scenario_artifacts(spec: Mapping[str, Any], case_dir: Path) -> None:
    if spec["existing_ack"] == "conflict":
        forged = {
            "schema_version": P133_ACK_SCHEMA_VERSION, "event_id": "conflicting-event", "event_hash": _ZERO_HASH,
            "episode_id": "conflicting-episode", "lease_owner": "other-worker",
            "meaning": "local_ownership_only_not_external_delivery_or_closure", "authority_counters": zero_forbidden_authority(),
        }
        forged["ack_hash"] = _self_hash(forged, "ack_hash")
        _write_json_fsynced(case_dir / "p133-ack.json", forged)
    mode = spec["tamper_mode"]
    if mode == "journal_duplicate_phase":
        entries = _raw_entries(spec, [("registered", {}), ("registered", {})])
        _write_jsonl_fsynced(case_dir / "journal.jsonl", entries)
    elif mode == "terminal_reorder":
        entries = _raw_entries(spec, [("registered", {}), ("recovery_verified", {"terminal_status": "recovery_verified"})])
        _write_jsonl_fsynced(case_dir / "journal.jsonl", entries)
    elif mode == "cursor_missing_predecessor":
        entries = _raw_entries(spec, [
            ("registered", {}), ("escalation_receipt_committed", {"reason": "seeded"}),
            ("human_escalation_required", {"terminal_status": "human_escalation_required"}),
        ])
        _write_jsonl_fsynced(case_dir / "journal.jsonl", entries)
        cursor = {
            "schema_version": CURSOR_SCHEMA_VERSION, "episode_id": spec["episode_id"], "case_id": spec["case_id"],
            "terminal_status": "human_escalation_required", "terminal_receipt_hash": _ZERO_HASH,
        }
        cursor["cursor_hash"] = _self_hash(cursor, "cursor_hash")
        _write_json_fsynced(case_dir / "cursor.json", cursor)
    elif mode == "escalation_receipt":
        receipt = {"schema_version": ESCALATION_RECEIPT_SCHEMA_VERSION, "reason": "forged", "local_only": True, "receipt_hash": _ZERO_HASH}
        _write_json_fsynced(case_dir / "escalation-receipt.json", receipt)


def _raw_entries(spec: Mapping[str, Any], phases: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    previous = _ZERO_HASH
    for version, (phase, payload) in enumerate(phases, start=1):
        entry: dict[str, Any] = {
            "schema_version": JOURNAL_SCHEMA_VERSION, "episode_id": spec["episode_id"], "case_id": spec["case_id"],
            "cas_version": version, "phase": phase, "logical_time": version, "payload": payload,
            "payload_hash": stable_hash(payload), "previous_receipt_hash": previous,
        }
        entry["receipt_hash"] = _self_hash(entry, "receipt_hash")
        previous = entry["receipt_hash"]
        result.append(entry)
    return result


def _write_crash_marker(case_dir: Path, point: str) -> None:
    marker = {
        "schema_version": CRASH_SCHEMA_VERSION,
        "crash_point": point,
        "recovery_strategy": _crash_recovery_strategy(point),
    }
    marker["crash_hash"] = _self_hash(marker, "crash_hash")
    _write_json_fsynced(case_dir / "crash-state.json", marker)


def _validate_lease(lease: Mapping[str, Any], event_id: str) -> None:
    expected = {
        "schema_version", "event_id", "owner_id", "active", "acquire_count", "renew_count",
        "write_count", "ownership_history", "lease_hash",
    }
    if set(lease) != expected or lease.get("schema_version") != LEASE_SCHEMA_VERSION or lease.get("event_id") != event_id:
        raise P145DutyOfficerError("lease_schema_or_event_drift")
    if not isinstance(lease.get("owner_id"), str) or not lease["owner_id"]:
        raise P145DutyOfficerError("lease_owner_invalid")
    if any(type(lease.get(key)) is not int or lease[key] < 0 for key in ("acquire_count", "renew_count", "write_count")):
        raise P145DutyOfficerError("lease_counter_invalid")
    history = lease.get("ownership_history")
    if type(history) is not list or len(history) != lease["write_count"] or not history:
        raise P145DutyOfficerError("lease_ownership_history_invalid")
    previous: Mapping[str, Any] | None = None
    renewals = 0
    for index, raw in enumerate(history, start=1):
        if not isinstance(raw, Mapping) or set(raw) != _LEASE_HISTORY_FIELDS:
            raise P145DutyOfficerError("lease_ownership_history_invalid")
        if (
            raw.get("event_id") != event_id
            or not isinstance(raw.get("owner_id"), str)
            or not raw["owner_id"]
            or type(raw.get("epoch")) is not int
            or raw["epoch"] < 1
            or raw.get("cas_version") != index
            or type(raw.get("active")) is not bool
            or raw.get("receipt_hash") != _self_hash(raw, "receipt_hash")
        ):
            raise P145DutyOfficerError("lease_ownership_history_invalid")
        if previous is None:
            if raw["epoch"] != 1 or raw["active"] is not True:
                raise P145DutyOfficerError("lease_ownership_history_invalid")
        elif raw["owner_id"] == previous["owner_id"]:
            if raw["epoch"] != previous["epoch"] or previous["active"] is False and raw["active"] is True:
                raise P145DutyOfficerError("lease_ownership_history_invalid")
            if previous["active"] is True and raw["active"] is True:
                renewals += 1
        elif (
            previous["active"] is not False
            or raw["active"] is not True
            or raw["epoch"] != previous["epoch"] + 1
        ):
            raise P145DutyOfficerError("lease_ownership_history_invalid")
        previous = raw
    assert previous is not None
    if (
        previous["owner_id"] != lease["owner_id"]
        or previous["epoch"] != lease["acquire_count"]
        or previous["active"] is not lease["active"]
        or renewals != lease["renew_count"]
    ):
        raise P145DutyOfficerError("lease_ownership_history_projection_invalid")
    if (
        lease["acquire_count"] < 1
        or lease["write_count"] < lease["acquire_count"] + lease["renew_count"]
        or type(lease.get("active")) is not bool
        or lease.get("lease_hash") != _self_hash(lease, "lease_hash")
    ):
        raise P145DutyOfficerError("lease_hash_invalid")


def _append_lease_ownership_receipt(lease: dict[str, Any]) -> None:
    receipt: dict[str, Any] = {
        "event_id": lease["event_id"],
        "owner_id": lease["owner_id"],
        "epoch": lease["acquire_count"],
        "cas_version": lease["write_count"],
        "active": lease["active"],
    }
    receipt["receipt_hash"] = _self_hash(receipt, "receipt_hash")
    history = lease.get("ownership_history")
    if type(history) is not list:
        raise P145DutyOfficerError("lease_ownership_history_invalid")
    history.append(receipt)


def _validate_lease_projection(
    lease: Mapping[str, Any], entries: list[dict[str, Any]], crash: Mapping[str, Any],
) -> None:
    expiry_points = {"lease_expiry_during_rollback", "lease_expiry_during_verification"}
    crash_point = crash.get("crash_point")
    terminal = _terminal_from_entries(entries)
    expected_owner = "worker-b" if terminal is not None and crash_point in expiry_points else "worker-a"
    expected_active = terminal is not None or crash_point not in expiry_points
    if lease.get("owner_id") != expected_owner or lease.get("active") is not expected_active:
        raise P145DutyOfficerError("lease_semantic_projection_invalid")


def _terminal_from_entries(entries: list[dict[str, Any]]) -> str | None:
    return str(entries[-1]["phase"]) if entries and entries[-1]["phase"] in TERMINALS else None


def _action_id(spec: Mapping[str, Any], index: int) -> str:
    return stable_hash({
        "episode_id": spec["episode_id"], "event_id": spec["p133_event"]["event_id"],
        "action": spec["selected_action"], "action_index": index,
    })


def _correlation_action_receipt(spec: Mapping[str, Any], action_receipt_hash: str) -> dict[str, Any]:
    first_event = spec["p133_event"]
    second_event = spec["correlated_p133_event"]
    if not isinstance(second_event, Mapping):
        raise P145DutyOfficerError("correlated_p133_event_missing")
    return {
        "schema_version": "p145.correlation_action_receipt.v1",
        "correlation_id": first_event["correlation_id"],
        "first_event_id": first_event["event_id"],
        "first_incident_id": first_event["incident_id"],
        "second_event_id": second_event["event_id"],
        "second_incident_id": second_event["incident_id"],
        "action_receipt_hash": action_receipt_hash,
        "action_reused": True,
        "second_action_mutation": False,
    }


def _contained_case_dir(output_dir: Path, case_id: str) -> Path:
    base = output_dir.resolve()
    candidate = (base / case_id).resolve()
    if candidate.parent != base:
        raise P145DutyOfficerError("fault_lab_path_escape")
    return candidate


def _assert_runtime_authority_boundary() -> None:
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    forbidden_modules = {"subprocess", "socket", "requests", "httpx", "urllib", "boto3", "kubernetes"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(alias.name.split(".", 1)[0] in forbidden_modules for alias in node.names):
            raise P145DutyOfficerError("forbidden_runtime_import")
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".", 1)[0] in forbidden_modules:
            raise P145DutyOfficerError("forbidden_runtime_import")
        if isinstance(node, ast.ImportFrom) and node.module == "os":
            allowed_os_names = {"O_RDONLY", "close", "fsync", "open", "replace"}
            if any(alias.name not in allowed_os_names for alias in node.names):
                raise P145DutyOfficerError("forbidden_os_runtime_reachability")
        if isinstance(node, ast.Attribute) and node.attr in {"environ", "getenv", "system", "popen"}:
            raise P145DutyOfficerError("forbidden_runtime_reachability")


def _write_json_fsynced(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        handle.write(_canonical_json(value) + "\n")
        handle.flush()
        fsync(handle.fileno())
    replace(temp, path)
    _fsync_directory(path.parent)


def _write_json_exclusive_fsynced(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(_canonical_json(value) + "\n")
            handle.flush()
            fsync(handle.fileno())
    except FileExistsError as exc:
        raise _LeaseConflict("p133_ack_cas_conflict") from exc
    _fsync_directory(path.parent)


def _write_jsonl_fsynced(path: Path, entries: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(_canonical_json(entry) + "\n")
        handle.flush()
        fsync(handle.fileno())
    _fsync_directory(path.parent)


def _fsync_directory(path: Path) -> None:
    descriptor = open_directory(path, O_RDONLY)
    try:
        fsync(descriptor)
    finally:
        close(descriptor)


def _read_json(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    try:
        value = json.loads(raw, object_pairs_hook=_strict_json_object)
    except (json.JSONDecodeError, P145DutyOfficerError) as exc:
        raise P145DutyOfficerError(f"corrupt_json:{path.name}") from exc
    if not isinstance(value, dict) or raw != _canonical_json(value) + "\n":
        raise P145DutyOfficerError(f"noncanonical_json:{path.name}")
    return value


def _read_json_if_present(path: Path) -> dict[str, Any]:
    return _read_json(path) if path.exists() else {}


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise P145DutyOfficerError(f"duplicate_json_key:{key}")
        value[key] = item
    return value


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _bounded_signal(key: str, value: int) -> int:
    if key in {"error_rate_bps", "saturation_bps", "dependency_timeout_bps", "collateral_health_bps"}:
        return min(10000, max(0, value))
    return max(0, value)


def _self_hash(value: Mapping[str, Any], hash_key: str) -> str:
    return stable_hash({key: item for key, item in value.items() if key != hash_key})


def _selector_name(case_id: str) -> str:
    return CASE_SELECTOR_NAMES[case_id]


CASE_SELECTOR_NAMES: dict[str, str] = {
    "P145-CASE-01": "test_deploy_regression_rolls_back_and_recovers",
    "P145-CASE-02": "test_pool_saturation_contradicts_deploy_hypothesis",
    "P145-CASE-03": "test_dependency_timeout_rejects_restart",
    "P145-CASE-04": "test_queue_backlog_uses_two_bounded_actions",
    "P145-CASE-05": "test_natural_recovery_is_observe_only",
    "P145-CASE-06": "test_conflicting_telemetry_escalates_without_action",
    "P145-CASE-07": "test_stale_evidence_cannot_authorize_action",
    "P145-CASE-08": "test_log_prompt_injection_is_untrusted_evidence",
    "P145-CASE-09": "test_missing_critical_evidence_requests_then_escalates",
    "P145-CASE-10": "test_harmful_first_action_rolls_back",
    "P145-CASE-11": "test_primary_metric_only_is_not_recovery",
    "P145-CASE-12": "test_missing_rollback_blocks_before_mutation",
    "P145-CASE-13": "test_crash_after_action_receipt_resumes_verification_once",
    "P145-CASE-14": "test_crash_before_action_commit_is_at_most_once",
    "P145-CASE-15": "test_same_resource_lease_contention_allows_one_mutator",
    "P145-CASE-16": "test_dead_runner_emits_recoverable_handoff",
    "P145-CASE-17": "test_action_budget_exhaustion_preserves_history",
    "P145-CASE-18": "test_duplicate_incident_replay_reuses_terminal_receipt",
    "P145-CASE-19": "test_poisoned_prior_memory_is_contradiction_not_authority",
    "P145-CASE-20": "test_protected_domain_is_human_required",
    "P145-CASE-21": "test_evidence_hash_forgery_fails_before_ownership",
    "P145-CASE-22": "test_journal_duplicate_phase_fails_closed",
    "P145-CASE-23": "test_journal_reorder_fails_closed",
    "P145-CASE-24": "test_journal_missing_predecessor_fails_closed",
    "P145-CASE-25": "test_lab_state_drift_invalidates_recovery",
    "P145-CASE-26": "test_rollback_failure_never_claims_recovery",
    "P145-CASE-27": "test_recurrence_after_apparent_recovery_is_rejected",
    "P145-CASE-28": "test_insufficient_consecutive_observations_escalates",
    "P145-CASE-29": "test_out_of_order_observations_fail_closed",
    "P145-CASE-30": "test_observation_gap_fails_closed",
    "P145-CASE-31": "test_clock_rollback_fails_closed",
    "P145-CASE-32": "test_flapping_recovery_is_not_sustained",
    "P145-CASE-33": "test_partial_degraded_recovery_is_not_success",
    "P145-CASE-34": "test_delayed_regression_after_rollback_escalates",
    "P145-CASE-35": "test_rollback_collateral_harm_escalates",
    "P145-CASE-36": "test_lab_mutated_before_receipt_recovers_without_repeat",
    "P145-CASE-37": "test_action_receipt_before_fsync_is_not_committed",
    "P145-CASE-38": "test_rollback_mutated_before_receipt_recovers_once",
    "P145-CASE-39": "test_terminal_receipt_before_cursor_replays_without_action",
    "P145-CASE-40": "test_lease_expiry_during_verification_escalates",
    "P145-CASE-41": "test_lease_expiry_during_rollback_recovers_or_escalates",
    "P145-CASE-42": "test_journal_disk_full_fails_before_action",
    "P145-CASE-43": "test_lab_fsync_failure_forces_verified_rollback",
    "P145-CASE-44": "test_cursor_fsync_failure_replays_terminal_only",
    "P145-CASE-45": "test_duplicate_correlated_incidents_share_one_action",
    "P145-CASE-46": "test_local_escalation_receipt_corruption_fails_closed",
    "P145-CASE-47": "test_unknown_schema_field_and_authority_word_rejected",
    "P145-CASE-48": "test_conflicting_existing_p133_ack_fails_closed",
}
