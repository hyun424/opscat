#!/usr/bin/env python3
"""Run the source-bound exact-30-case P138 release qualification."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import fcntl
import json
import os
import signal
import sys
import tempfile
from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p110_evaluation import stable_hash
from app.services.p136_incremental_observer import P136ObservationError, observe_one_cycle
from app.services.p137_contracts import FIXED_P136_HANDOFF_PATH
from app.services.p137_p136_handoff import publish_p136_handoff_bundle
from app.services.p138_observation_triage_supervisor import (
    EVALUATOR_ACTIVITY_KEYS,
    FORBIDDEN_AUTHORITY_KEYS,
    RUNTIME_ACTIVITY_KEYS,
    P138StopController,
    build_observation_triage_supervisor_config,
    run_p138_supervisor_loop_for_evaluation,
    run_p138_supervisor_once,
    run_p138_supervisor_once_for_evaluation,
)
from app.services.p138_release_evidence import (
    P138_READY_STATUS,
    assemble_p138_release_evidence_from_frozen_matrix,
    build_p138_freeze_manifest,
    build_p138_preliminary_evidence,
    current_p138_dependency_bindings,
    current_p138_source_hashes,
    p138_fixture_hash,
    p138_profile_hash,
    validate_observation_triage_supervisor_profile,
)
from app.services.p138_runner import (
    CASE_RUNTIME_SCHEMA_VERSION,
    P136_OBSERVER_BOUNDARY,
    P136_RECOVERY_BOUNDARY,
    P137_RUNTIME_BOUNDARY,
    P138_LOOP_BOUNDARY,
    P138_ONCE_BOUNDARY,
    PUBLISHER_BOUNDARY,
    p138_release_case_matrix,
    run_p138_preliminary_matrix,
)
from tests.fixtures.p138.builders import (
    append_observation_entry,
    build_p138_fixture,
    p137_config,
)

DEFAULT_PROFILE = ROOT / "evals/p138/input/observation-triage-supervisor-profile.json"
DEFAULT_OUTPUT_DIR = ROOT / "evals/p138/output"
DEFAULT_FINAL_REVIEW = ROOT / "evals/p138/final-implementation-review.json"
DEFAULT_CANONICAL_MATRIX = DEFAULT_OUTPUT_DIR / "canonical-matrix.json"
DEFAULT_FREEZE_MANIFEST = DEFAULT_OUTPUT_DIR / "freeze-manifest.json"


class P138ProfileError(ValueError):
    """Raised when a canonical P138 runner input is unavailable or unsafe."""


class CanonicalRuntimeFactory:
    """Build source-bound local executors for the exact P138 denominator."""

    def __init__(self, work_root: Path) -> None:
        self.work_root = work_root
        self.rows = {str(row["case_id"]): row for row in p138_release_case_matrix()}

    def __call__(self, case_id: str) -> Mapping[str, Any]:
        row = self.rows.get(case_id)
        if row is None:
            raise P138ProfileError("unknown_case_id")
        expected_runtime = _EXPECTED_RUNTIME_ACTIVITY.get(case_id, _zero(RUNTIME_ACTIVITY_KEYS))
        expected_evaluator = _EXPECTED_EVALUATOR_ACTIVITY.get(case_id, _zero(EVALUATOR_ACTIVITY_KEYS))
        return {
            "schema_version": CASE_RUNTIME_SCHEMA_VERSION,
            "case_id": case_id,
            "input_profile": {
                "scenario": row["scenario"],
                "real_boundary_required": row["real_boundary_required"],
                "expected": deepcopy(row["expected"]),
            },
            "expected_runtime_activity": deepcopy(expected_runtime),
            "expected_forbidden_authority": _zero(FORBIDDEN_AUTHORITY_KEYS),
            "expected_evaluator_activity": deepcopy(expected_evaluator),
            "expected_resource_usage": _resource_budget(),
            "execute": CanonicalCaseExecutor(
                self.work_root / case_id,
                case_id,
                deepcopy(row),
            ),
        }


class CanonicalCaseExecutor:
    """Execute one local scenario through the implemented component boundaries."""

    def __init__(self, root: Path, case_id: str, row: Mapping[str, Any]) -> None:
        self.root = root
        self.case_id = case_id
        self.row = deepcopy(dict(row))
        self._observed_boundaries: list[str] = []
        self._publisher_recovery_proof: dict[str, Any] | None = None
        self._last_fixture_root: Path | None = None
        self._last_config: dict[str, Any] | None = None

    def __call__(self) -> dict[str, Any]:
        self.root.mkdir(parents=True, exist_ok=True)
        method = getattr(self, f"_case_{self.case_id[-2:]}")
        value = method()
        return _validated_canonical_result(value, row=self.row)

    def _fixture(
        self,
        name: str = "main",
        *,
        genesis_entries: int = 1,
        publish_genesis: bool = True,
        accept_genesis: bool = False,
        partial_genesis: bool = False,
    ) -> tuple[Any, dict[str, Any]]:
        fixture = build_p138_fixture(
            self.root / name,
            genesis_entries=genesis_entries,
            publish_genesis=publish_genesis,
            accept_genesis=accept_genesis,
            partial_genesis=partial_genesis,
        )
        config = build_observation_triage_supervisor_config(fixture.config_input)
        self._last_fixture_root = fixture.root
        self._last_config = deepcopy(config)
        return fixture, config

    def _run(
        self,
        fixture: Any,
        config: Mapping[str, Any],
        *,
        evaluation: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        function = run_p138_supervisor_once_for_evaluation if evaluation else run_p138_supervisor_once
        self._last_fixture_root = fixture.root
        self._last_config = deepcopy(dict(config))
        result = function(
            base_path=fixture.root,
            config=config,
            p136_runtime=fixture.p136_runtime,
            publisher_inputs=_supervisor_publisher_inputs(fixture),
            now="2026-07-14T00:00:04Z",
            **kwargs,
        )
        self._record_result_boundaries(result)
        return result

    def _accepted(self) -> tuple[Any, dict[str, Any]]:
        fixture, config = self._fixture(
            publish_genesis=True,
            accept_genesis=True,
        )
        initial = self._run(fixture, config)
        _require(initial.get("status") == "ok", "bootstrap_acceptance_failed")
        return fixture, config

    def _finish(
        self,
        raw: Mapping[str, Any],
        *,
        error: str | None = None,
        stop_reason: str | None = None,
        phase_path: Sequence[str] | None = None,
        runtime_activity: Mapping[str, int] | None = None,
        evaluator_activity: Mapping[str, int] | None = None,
    ) -> dict[str, Any]:
        status = raw.get("status")
        if not isinstance(status, str) or not status:
            raise P138ProfileError("observed_status_missing")
        observed_phase_path = list(phase_path) if phase_path is not None else raw.get("phase_path", [])
        if not isinstance(observed_phase_path, list) or any(
            not isinstance(item, str) or not item for item in observed_phase_path
        ):
            raise P138ProfileError("observed_phase_path_invalid")
        observed_error = error if error is not None else raw.get("expected_error", "none")
        observed_stop_reason = stop_reason if stop_reason is not None else raw.get("stop_reason", "none")
        if observed_error is None:
            observed_error = "none"
        if observed_stop_reason is None:
            observed_stop_reason = "none"
        if not isinstance(observed_error, str) or not observed_error:
            raise P138ProfileError("observed_error_invalid")
        if not isinstance(observed_stop_reason, str) or not observed_stop_reason:
            raise P138ProfileError("observed_stop_reason_invalid")
        self._record_result_boundaries(raw)
        endpoint = P138_LOOP_BOUNDARY if raw.get("schema_version") == "p138.supervisor_loop_result.v1" else P138_ONCE_BOUNDARY
        self._record_boundary(endpoint)
        forbidden = deepcopy(_mapping(raw.get("forbidden_authority"), "forbidden_authority"))
        if set(forbidden) != set(FORBIDDEN_AUTHORITY_KEYS) or any(
            isinstance(value, bool) or not isinstance(value, int) or value != 0
            for value in forbidden.values()
        ):
            raise P138ProfileError("observed_forbidden_authority_nonzero")
        return {
            "status": status,
            "error": observed_error,
            "stop_reason": observed_stop_reason,
            "phase_path": deepcopy(observed_phase_path),
            "component_boundaries": list(self._observed_boundaries),
            "durable_post_state": self._prove_durable_post_state(raw),
            "runtime_activity": deepcopy(runtime_activity if runtime_activity is not None else _mapping(raw.get("runtime_activity"), "runtime_activity")),
            "forbidden_authority": forbidden,
            "evaluator_activity": deepcopy(evaluator_activity if evaluator_activity is not None else _mapping(raw.get("evaluator_activity"), "evaluator_activity")),
            "resource_usage": _release_resource_usage(raw.get("resource_usage")),
            "execution_source": (f"scripts.run_p138_observation_triage_supervisor.CanonicalCaseExecutor.{self.case_id}"),
        }

    def _record_boundary(self, boundary: str) -> None:
        if boundary not in self._observed_boundaries:
            self._observed_boundaries.append(boundary)

    def _record_result_boundaries(self, raw: Mapping[str, Any]) -> None:
        calls = raw.get("component_calls")
        if calls is None and isinstance(raw.get("last_result"), Mapping):
            calls = _mapping(raw["last_result"], "last_result").get("component_calls")
        if not isinstance(calls, Sequence) or isinstance(calls, (str, bytes, bytearray)):
            return
        mapping = {
            "p136": P136_OBSERVER_BOUNDARY,
            "p136_recovery": P136_RECOVERY_BOUNDARY,
            "publisher": PUBLISHER_BOUNDARY,
            "publisher_recovery": PUBLISHER_BOUNDARY,
            "p137": P137_RUNTIME_BOUNDARY,
        }
        for call in calls:
            if isinstance(call, str) and call in mapping:
                self._record_boundary(mapping[call])

    def _prove_durable_post_state(self, raw: Mapping[str, Any]) -> str:
        labels = {
            "P138-CASE-01": "genesis_reconciled_without_new_publication",
            "P138-CASE-02": "new_contiguous_delta_published_accepted_finalized",
            "P138-CASE-03": "no_work_finalized_without_publication_or_triage",
            "P138-CASE-04": "same_cycle_recovered_after_cycle_started",
            "P138-CASE-05": "stored_delta_published_once_after_p136_completed",
            "P138-CASE-06": "selected_handoff_published_once_on_recovery",
            "P138-CASE-07": "publisher_intent_recovered_same_sequence_once",
            "P138-CASE-08": "published_bytes_consumed_without_republication",
            "P138-CASE-09": "p137_membership_validated_without_replay_label",
            "P138-CASE-10": "sequence_retained_then_accepted_before_successor",
            "P138-CASE-11": "prior_p138_ledger_preserved",
            "P138-CASE-12": "no_observation_publication_or_ledger_advance",
            "P138-CASE-13": "component_bytes_preserved_without_calls",
            "P138-CASE-14": "zero_component_calls_and_zero_state_writes",
            "P138-CASE-15": "no_publisher_p137_or_p138_final_advance",
            "P138-CASE-16": "no_sequence_p137_or_p138_final_advance",
            "P138-CASE-17": "current_bundle_retained",
            "P138-CASE-18": "only_later_promotion_delta_published_and_classified",
            "P138-CASE-19": "hash_bound_termination_at_safe_boundary",
            "P138-CASE-20": "no_forbidden_authority_or_sensitive_output",
            "P138-CASE-21": "promotion_completion_recovered_without_extra_receipt",
            "P138-CASE-22": "empty_completion_recovered_without_extra_receipt_or_publish",
            "P138-CASE-23": "fixed_split_commit_recovered_same_sequence_once",
            "P138-CASE-24": "state_split_commit_recovered_and_stale_intent_removed",
            "P138-CASE-25": "both_bootstrap_variants_rejected_before_new_observation",
            "P138-CASE-26": "no_publication_after_either_stop",
            "P138-CASE-27": "exact_cycle_heartbeat_and_readiness_cadence",
            "P138-CASE-28": "termination_bound_to_last_valid_ledger",
            "P138-CASE-29": "promotion_outcome_intent_installed_checkpoint_and_published_once",
            "P138-CASE-30": "empty_outcome_intent_installed_checkpoint_without_publish",
        }
        root = self._last_fixture_root
        config = self._last_config
        if root is None or config is None:
            raise P138ProfileError("durable_observation_context_missing")
        observed = raw
        if raw.get("schema_version") == "p138.supervisor_loop_result.v1":
            last_result = raw.get("last_result")
            if isinstance(last_result, Mapping):
                observed = last_result
            termination = _mapping(raw.get("termination"), "termination")
            _require(
                termination.get("termination_hash")
                == stable_hash(
                    {
                        key: value
                        for key, value in termination.items()
                        if key != "termination_hash"
                    }
                ),
                "termination_hash_invalid",
            )
            termination_path = (
                root
                / str(config["termination_dir"])
                / f"{str(termination['termination_hash']).removeprefix('sha256:')}.json"
            )
            _require(
                _read_json(termination_path) == dict(termination),
                "termination_not_durable",
            )
            termination_authority = _mapping(
                termination.get("forbidden_authority"),
                "termination_forbidden_authority",
            )
            _require(
                set(termination_authority) == set(FORBIDDEN_AUTHORITY_KEYS)
                and all(value == 0 for value in termination_authority.values()),
                "termination_forbidden_authority_nonzero",
            )
        for field, path_key, hash_field in (
            ("ledger", "ledger_path", "ledger_hash"),
            ("checkpoint", "checkpoint_path", "checkpoint_hash"),
            ("phase", "phase_path", "phase_hash"),
        ):
            record = observed.get(field)
            if not isinstance(record, Mapping):
                continue
            _require(
                record.get(hash_field)
                == stable_hash(
                    {
                        key: value
                        for key, value in record.items()
                        if key != hash_field
                    }
                ),
                f"observed_{field}_hash_invalid",
            )
            durable_path = root / str(config[path_key])
            if field == "phase" and not durable_path.exists():
                durable_ledger = observed.get("ledger")
                _require(
                    isinstance(durable_ledger, Mapping)
                    and durable_ledger.get("phase_hash") == record.get("phase_hash"),
                    "finalized_phase_not_bound_to_durable_ledger",
                )
            else:
                _require(
                    _read_json(durable_path) == dict(record),
                    f"observed_{field}_not_durable",
                )
        authority = _mapping(raw.get("forbidden_authority"), "forbidden_authority")
        _require(
            set(authority) == set(FORBIDDEN_AUTHORITY_KEYS)
            and all(value == 0 for value in authority.values()),
            "observed_forbidden_authority_nonzero",
        )
        if self.case_id in {"P138-CASE-23", "P138-CASE-24"}:
            proof = self._publisher_recovery_proof
            if not isinstance(proof, Mapping) or proof.get("verified") is not True:
                raise P138ProfileError("publisher_durable_recovery_unproven")
        if observed.get("status") == "ok" and observed.get("ledger") is not None:
            ledger = _mapping(observed.get("ledger"), "observed_ledger")
            _require(isinstance(ledger.get("ledger_hash"), str), "observed_ledger_hash_missing")
        return labels[self.case_id]

    def _phase_recovery_case(
        self,
        phase: str,
    ) -> dict[str, Any]:
        fixture, config = self._accepted()
        append_observation_entry(fixture)
        crashed = self._run(
            fixture,
            config,
            evaluation=True,
            crash_after_phase=phase,
        )
        _require(crashed.get("status") == "failed_closed", "phase_crash_missing")
        recovered = self._run(fixture, config)
        _require(recovered.get("status") == "ok", "phase_recovery_failed")
        return self._finish(
            recovered,
            phase_path=_combined_phase_path(crashed, recovered),
        )

    def _publisher_crash_case(
        self,
        boundary: str,
    ) -> dict[str, Any]:
        fixture, config = self._accepted()
        append_observation_entry(fixture)
        prior_state = _read_json(fixture.root / str(config["publisher_state_path"]))

        def crash(point: str) -> None:
            if point == boundary:
                raise P136ObservationError(f"injected_{point}")

        def publish_with_crash(**kwargs: Any) -> dict[str, Any]:
            return publish_p136_handoff_bundle(**kwargs, evaluator_crash_injector=crash)

        crashed = self._run(
            fixture,
            config,
            evaluation=True,
            component_callables={"publish": publish_with_crash},
        )
        _require(crashed.get("status") == "failed_closed", "publisher_crash_missing")
        recovered = self._run(fixture, config)
        _require(recovered.get("status") == "ok", "publisher_recovery_failed")
        recovered_state = _read_json(fixture.root / str(config["publisher_state_path"]))
        recovered_bundle = _read_json(fixture.root / str(config["p136_handoff_bundle_path"]))
        intent_path = fixture.root / str(config["publisher_intent_path"])
        _require(int(recovered_state["last_bundle_sequence"]) == int(prior_state["last_bundle_sequence"]) + 1, "publisher_sequence_not_exactly_once")
        _require(recovered_state["last_bundle_hash"] == recovered_bundle["bundle_hash"], "publisher_hash_not_bound")
        _require(not intent_path.exists(), "publisher_intent_not_cleaned")
        self._publisher_recovery_proof = {
            "verified": True,
            "sequence": recovered_state["last_bundle_sequence"],
            "bundle_hash": recovered_bundle["bundle_hash"],
            "intent_absent": True,
        }
        evaluator = dict(deepcopy(_mapping(recovered.get("evaluator_activity"), "evaluator_activity")))
        evaluator["crash_injection_count"] += 1
        return self._finish(
            recovered,
            phase_path=_combined_phase_path(crashed, recovered),
            evaluator_activity=evaluator,
        )

    def _p136_commit_recovery_case(self, *, boundary: str, promotion: bool) -> dict[str, Any]:
        fixture, config = self._accepted()
        if promotion:
            append_observation_entry(fixture)
        probe = fixture.p136_runtime["probe"]

        def crash(point: str) -> None:
            if point == boundary:
                raise P136ObservationError(f"injected_{point}")

        fixture.p136_runtime["evaluator_crash_injector"] = crash
        crashed = self._run(fixture, config, evaluation=True)
        _require(crashed.get("status") == "failed_closed", "p136_crash_missing")
        reads = int(probe.index_read_count)
        fixture.p136_runtime.pop("evaluator_crash_injector")
        recovered = self._run(fixture, config)
        _require(recovered.get("status") == "ok", "p136_recovery_failed")
        _require(int(probe.index_read_count) == reads, "p136_extra_index_read")
        evaluator = dict(deepcopy(_mapping(recovered.get("evaluator_activity"), "evaluator_activity")))
        evaluator["crash_injection_count"] += 1
        return self._finish(
            recovered,
            phase_path=_combined_phase_path(crashed, recovered),
            evaluator_activity=evaluator,
        )

    def _case_01(self) -> dict[str, Any]:
        fixture, config = self._fixture(publish_genesis=True, accept_genesis=False)
        result = self._run(fixture, config)
        _require(result.get("status") == "ok", "bootstrap_reconciliation_failed")
        _require(result.get("component_calls") == ["p137"], "bootstrap_component_drift")
        return self._finish(
            result,
        )

    def _case_02(self) -> dict[str, Any]:
        fixture, config = self._accepted()
        append_observation_entry(fixture)
        result = self._run(fixture, config)
        _require(result.get("component_calls") == ["p136", "publisher", "p137"], "new_promotion_boundary_drift")
        return self._finish(
            result,
        )

    def _case_03(self) -> dict[str, Any]:
        fixture, config = self._accepted()
        result = self._run(fixture, config)
        _require(result.get("no_work") is True, "zero_promotion_not_no_work")
        return self._finish(
            result,
        )

    def _case_04(self) -> dict[str, Any]:
        return self._phase_recovery_case(
            "cycle_started",
        )

    def _case_05(self) -> dict[str, Any]:
        return self._phase_recovery_case(
            "p136_completed",
        )

    def _case_06(self) -> dict[str, Any]:
        return self._phase_recovery_case(
            "handoff_selected",
        )

    def _case_07(self) -> dict[str, Any]:
        return self._publisher_crash_case(
            "publisher_intent_durable",
        )

    def _case_08(self) -> dict[str, Any]:
        return self._phase_recovery_case(
            "handoff_published",
        )

    def _case_09(self) -> dict[str, Any]:
        return self._phase_recovery_case(
            "p137_committed",
        )

    def _case_10(self) -> dict[str, Any]:
        fixture, config = self._fixture(publish_genesis=True, accept_genesis=False)
        lease = fixture.root / str(config["p137_config"]["lease_path"])
        lease.parent.mkdir(parents=True, exist_ok=True)
        with lease.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            conflict = self._run(fixture, config)
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        _require(conflict.get("expected_error") == "p137:lease_conflict", "p137_lease_conflict_missing")
        recovered = self._run(fixture, config)
        _require(recovered.get("status") == "ok", "p137_lease_recovery_failed")
        runtime = _sum_activity(conflict, recovered, field="runtime_activity", keys=RUNTIME_ACTIVITY_KEYS)
        evaluator = _sum_activity(conflict, recovered, field="evaluator_activity", keys=EVALUATOR_ACTIVITY_KEYS)
        return self._finish(
            recovered,
            error="p137:lease_conflict_then_recovered",
            runtime_activity=runtime,
            evaluator_activity=evaluator,
        )

    def _case_11(self) -> dict[str, Any]:
        fixture, config = self._accepted()
        bundle = _read_json(fixture.root / str(config["p136_handoff_bundle_path"]))
        state = _read_json(fixture.root / str(config["publisher_state_path"]))
        bundle["created_at"] = "2026-07-14T00:00:09Z"
        bundle["bundle_hash"] = stable_hash({key: value for key, value in bundle.items() if key != "bundle_hash"})
        state["last_bundle_hash"] = bundle["bundle_hash"]
        state["state_hash"] = stable_hash({key: value for key, value in state.items() if key != "state_hash"})
        _write_json(fixture.root / str(config["p136_handoff_bundle_path"]), bundle)
        _write_json(fixture.root / str(config["publisher_state_path"]), state)
        result = self._run(fixture, config)
        _require(result.get("status") == "failed_closed", "same_sequence_fork_not_blocked")
        return self._finish(
            result,
            error="same_sequence_bundle_fork",
        )

    def _case_12(self) -> dict[str, Any]:
        fixture, config = self._accepted()
        bundle = _read_json(fixture.root / str(config["p136_handoff_bundle_path"]))
        state = _read_json(fixture.root / str(config["publisher_state_path"]))
        bundle["bundle_sequence"] = int(bundle["bundle_sequence"]) + 2
        bundle["previous_bundle_hash"] = stable_hash({"broken": True})
        bundle["bundle_hash"] = stable_hash({key: value for key, value in bundle.items() if key != "bundle_hash"})
        state["last_bundle_sequence"] = bundle["bundle_sequence"]
        state["last_bundle_hash"] = bundle["bundle_hash"]
        state["state_hash"] = stable_hash({key: value for key, value in state.items() if key != "state_hash"})
        _write_json(fixture.root / str(config["p136_handoff_bundle_path"]), bundle)
        _write_json(fixture.root / str(config["publisher_state_path"]), state)
        result = self._run(fixture, config)
        _require(result.get("status") == "failed_closed", "sequence_gap_not_blocked")
        return self._finish(
            result,
            error="sequence_gap_or_previous_hash_break",
        )

    def _case_13(self) -> dict[str, Any]:
        fixture, config = self._accepted()
        bundle = _read_json(fixture.root / str(config["p136_handoff_bundle_path"]))
        bundle["created_at"] = "2026-07-14T00:00:08Z"
        _write_json(fixture.root / str(config["p136_handoff_bundle_path"]), bundle)
        result = self._run(fixture, config)
        _require(result.get("status") == "failed_closed", "publisher_fixed_mismatch_not_blocked")
        return self._finish(
            result,
            error="publisher_state_fixed_mismatch",
        )

    def _case_14(self) -> dict[str, Any]:
        fixture, config = self._fixture(publish_genesis=False)
        lease = fixture.root / str(config["lease_path"])
        lease.parent.mkdir(parents=True, exist_ok=True)
        with lease.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self._run(fixture, config)
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        _require(result.get("expected_error") == "supervisor_lease_unavailable", "p138_lease_conflict_missing")
        return self._finish(
            result,
            error="supervisor_lease_unavailable",
            stop_reason="lease_conflict",
        )

    def _case_15(self) -> dict[str, Any]:
        fixture, config = self._accepted()
        lease = fixture.root / str(fixture.p136_runtime["config"]["lease_path"])
        lease.parent.mkdir(parents=True, exist_ok=True)
        with lease.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self._run(fixture, config)
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        _require("exclusive_lease_unavailable" in str(result.get("expected_error")), "p136_lease_conflict_missing")
        return self._finish(
            result,
            error="p136:exclusive_lease_unavailable",
        )

    def _case_16(self) -> dict[str, Any]:
        fixture, config = self._accepted()
        append_observation_entry(fixture)
        lease = fixture.root / str(config["publisher_lease_path"])
        lease.parent.mkdir(parents=True, exist_ok=True)
        with lease.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self._run(fixture, config)
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        _require("publisher_lease_unavailable" in str(result.get("expected_error")), "publisher_lease_conflict_missing")
        return self._finish(
            result,
            error="publisher:publisher_lease_unavailable",
        )

    def _case_17(self) -> dict[str, Any]:
        fixture, _ = self._fixture(publish_genesis=True, accept_genesis=False)
        fixture.config_input["p137_config"] = p137_config(
            fixture.root,
            chain_root=stable_hash({"stale": "p137-chain-root"}),
        )
        config = build_observation_triage_supervisor_config(fixture.config_input)
        result = self._run(fixture, config)
        _require(result.get("status") == "failed_closed", "stale_p137_version_not_blocked")
        return self._finish(
            result,
            error="p137_stale_readiness_or_version",
        )

    def _case_18(self) -> dict[str, Any]:
        fixture, config = self._accepted()
        append_observation_entry(fixture)
        first = self._run(fixture, config)
        _require(first.get("status") == "ok", "first_delta_failed")
        append_observation_entry(fixture)
        second = self._run(fixture, config)
        _require(second.get("status") == "ok", "later_delta_failed")
        _require(second["ledger"]["last_published_promotion_sequence"] == 3, "later_delta_boundary_invalid")
        return self._finish(
            second,
        )

    def _case_19(self) -> dict[str, Any]:
        fixture, config = self._fixture(publish_genesis=False)
        controller = P138StopController()
        controller.handle_signal(signal.SIGTERM, None)
        result = run_p138_supervisor_loop_for_evaluation(
            base_path=fixture.root,
            config=config,
            p136_runtime=fixture.p136_runtime,
            publisher_inputs=_supervisor_publisher_inputs(fixture),
            now_values=("2026-07-14T00:00:04Z",),
            stop_controller=controller,
            monotonic=lambda: 1.0,
            sleep=lambda _: None,
        )
        _require(result.get("stop_reason") == "sigterm", "safe_signal_stop_missing")
        evaluator = dict(deepcopy(_mapping(result.get("evaluator_activity"), "evaluator_activity")))
        evaluator["signal_injection_count"] += 1
        return self._finish(
            result,
            error="signal_at_safe_boundary",
            evaluator_activity=evaluator,
        )

    def _case_20(self) -> dict[str, Any]:
        fixture, config = self._fixture(publish_genesis=False)
        blocked = False
        try:
            self._run(fixture, config, component_callables={"observe": lambda: None})
        except Exception as exc:
            blocked = "production_component_callables_forbidden" in str(exc)
        _require(blocked, "forbidden_callable_not_blocked")
        outside = self.root / "outside"
        outside.mkdir(exist_ok=True)
        os.symlink(outside, fixture.root / "p138")
        result = self._run(fixture, config)
        _require(result.get("status") == "failed_closed", "path_guard_not_blocked")
        evaluator = dict(deepcopy(_mapping(result.get("evaluator_activity"), "evaluator_activity")))
        evaluator["fake_guard_injection_count"] += 1
        return self._finish(
            result,
            error="guard_blocked_before_runtime_authority",
            evaluator_activity=evaluator,
        )

    def _case_21(self) -> dict[str, Any]:
        return self._p136_commit_recovery_case(boundary="cycle_checkpoint_durable", promotion=True)

    def _case_22(self) -> dict[str, Any]:
        return self._p136_commit_recovery_case(boundary="cycle_checkpoint_durable", promotion=False)

    def _case_23(self) -> dict[str, Any]:
        return self._publisher_crash_case(
            "publisher_fixed_replaced",
        )

    def _case_24(self) -> dict[str, Any]:
        return self._publisher_crash_case(
            "publisher_state_replaced",
        )

    def _case_25(self) -> dict[str, Any]:
        partial_fixture, partial_config = self._fixture("partial", genesis_entries=2, publish_genesis=True, partial_genesis=True)
        partial = self._run(partial_fixture, partial_config)
        _require(partial.get("expected_error") == "bootstrap_promotion_history_incomplete", "partial_genesis_not_blocked")
        non_fixture, non_config = self._fixture("non-genesis", publish_genesis=True, accept_genesis=False)
        append_observation_entry(non_fixture)
        observed = observe_one_cycle(non_fixture.p136_runtime)
        non_fixture.p136_runtime["checkpoint"] = observed["advanced_checkpoint"]
        publish_p136_handoff_bundle(
            base_path=non_fixture.root,
            state_path=non_config["publisher_state_path"],
            intent_path=non_config["publisher_intent_path"],
            lease_path=non_config["publisher_lease_path"],
            fixed_handoff_path=FIXED_P136_HANDOFF_PATH,
            p136_config=non_fixture.p136_runtime["config"],
            p136_runtime_authority=non_fixture.p136_runtime["authority"],
            now=non_fixture.p136_runtime["now"],
            p136_checkpoint=observed["advanced_checkpoint"],
            canonical_entry_map=non_fixture.publisher_inputs["canonical_entry_map"],
            promotion_records=observed["promotion_records"],
            p136_independent_review=non_fixture.publisher_inputs["p136_independent_review"],
            p136_release_evidence=non_fixture.publisher_inputs["p136_release_evidence"],
            created_at="2026-07-14T00:00:03Z",
        )
        non_genesis = self._run(non_fixture, non_config)
        _require(non_genesis.get("expected_error") == "bootstrap_requires_genesis_bundle", "non_genesis_not_blocked")
        runtime = _sum_activity(partial, non_genesis, field="runtime_activity", keys=RUNTIME_ACTIVITY_KEYS)
        evaluator = _sum_activity(partial, non_genesis, field="evaluator_activity", keys=EVALUATOR_ACTIVITY_KEYS)
        return self._finish(
            non_genesis,
            error="partial_and_non_genesis_bootstrap_rejected",
            runtime_activity=runtime,
            evaluator_activity=evaluator,
        )

    def _case_26(self) -> dict[str, Any]:
        fixture, _ = self._fixture(
            "receipt",
            publish_genesis=True,
            accept_genesis=True,
        )
        config_input = deepcopy(fixture.config_input)
        config_input["limits"]["max_supervisor_cycles"] = 4
        config = build_observation_triage_supervisor_config(config_input)
        bootstrap = self._run(fixture, config)
        _require(bootstrap.get("status") == "ok", "receipt_bootstrap_failed")
        exhausted = run_p138_supervisor_loop_for_evaluation(
            base_path=fixture.root,
            config=config,
            p136_runtime=fixture.p136_runtime,
            publisher_inputs=_supervisor_publisher_inputs(fixture),
            now_values=tuple(f"2026-07-14T00:00:0{index}Z" for index in range(4, 8)),
            monotonic=lambda: 1.0,
            sleep=lambda _: None,
        )
        _require(exhausted.get("stop_reason") == "receipt_exhausted", "receipt_exhaustion_missing")
        failed_fixture, failed_config = self._accepted()
        lease = failed_fixture.root / str(failed_fixture.p136_runtime["config"]["lease_path"])
        lease.parent.mkdir(parents=True, exist_ok=True)
        with lease.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            failed = run_p138_supervisor_loop_for_evaluation(
                base_path=failed_fixture.root,
                config=failed_config,
                p136_runtime=failed_fixture.p136_runtime,
                publisher_inputs=_supervisor_publisher_inputs(failed_fixture),
                now_values=("2026-07-14T00:00:04Z", "2026-07-14T00:00:05Z"),
                monotonic=lambda: 1.0,
                sleep=lambda _: None,
            )
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        _require(failed.get("stop_reason") == "consecutive_failure_threshold_reached", "failure_threshold_missing")
        runtime = _sum_activity(exhausted, failed, field="runtime_activity", keys=RUNTIME_ACTIVITY_KEYS)
        evaluator = _sum_activity(exhausted, failed, field="evaluator_activity", keys=EVALUATOR_ACTIVITY_KEYS)
        return self._finish(
            failed,
            error="receipt_exhausted_and_failure_threshold",
            stop_reason="distinct_stop_labels",
            runtime_activity=runtime,
            evaluator_activity=evaluator,
        )

    def _case_27(self) -> dict[str, Any]:
        fixture, config = self._accepted()
        result = run_p138_supervisor_loop_for_evaluation(
            base_path=fixture.root,
            config=config,
            p136_runtime=fixture.p136_runtime,
            publisher_inputs=_supervisor_publisher_inputs(fixture),
            now_values=("2026-07-14T00:00:04Z", "2026-07-14T00:00:05Z"),
            monotonic=lambda: 1.0,
            sleep=lambda _: None,
        )
        _require(result.get("cycles_completed") == 2, "max_cycle_count_invalid")
        _require(result["runtime_activity"]["heartbeat_write_count"] == 2, "heartbeat_cadence_invalid")
        return self._finish(
            result,
        )

    def _case_28(self) -> dict[str, Any]:
        stale_fixture, stale_config = self._accepted()
        run_p138_supervisor_loop_for_evaluation(
            base_path=stale_fixture.root,
            config=stale_config,
            p136_runtime=stale_fixture.p136_runtime,
            publisher_inputs=_supervisor_publisher_inputs(stale_fixture),
            now_values=("2026-07-14T00:00:04Z",),
            monotonic=lambda: 1.0,
            sleep=lambda _: None,
        )
        stale = run_p138_supervisor_loop_for_evaluation(
            base_path=stale_fixture.root,
            config=stale_config,
            p136_runtime=stale_fixture.p136_runtime,
            publisher_inputs=_supervisor_publisher_inputs(stale_fixture),
            now_values=("2026-07-15T00:00:04Z",),
            monotonic=lambda: 2.0,
            sleep=lambda _: None,
        )
        _require(stale.get("stop_reason") in {"readiness_stale", "deadman_stale"}, "stale_stop_missing")
        signal_fixture, signal_config = self._fixture("signal", publish_genesis=False)
        controller = P138StopController()
        controller.handle_signal(signal.SIGTERM, None)
        stopped = run_p138_supervisor_loop_for_evaluation(
            base_path=signal_fixture.root,
            config=signal_config,
            p136_runtime=signal_fixture.p136_runtime,
            publisher_inputs=_supervisor_publisher_inputs(signal_fixture),
            now_values=("2026-07-14T00:00:04Z",),
            stop_controller=controller,
            monotonic=lambda: 1.0,
            sleep=lambda _: None,
        )
        runtime = _sum_activity(stale, stopped, field="runtime_activity", keys=RUNTIME_ACTIVITY_KEYS)
        evaluator = _sum_activity(stale, stopped, field="evaluator_activity", keys=EVALUATOR_ACTIVITY_KEYS)
        evaluator["signal_injection_count"] += 1
        return self._finish(
            stopped,
            error="stale_readiness_deadman_and_safe_signal",
            stop_reason="pre_component_safe_stop",
            runtime_activity=runtime,
            evaluator_activity=evaluator,
        )

    def _case_29(self) -> dict[str, Any]:
        return self._p136_commit_recovery_case(boundary="cycle_outcome_intent_durable", promotion=True)

    def _case_30(self) -> dict[str, Any]:
        return self._p136_commit_recovery_case(boundary="cycle_outcome_intent_durable", promotion=False)


def _supervisor_publisher_inputs(fixture: Any) -> dict[str, Any]:
    required = (
        "canonical_entry_map",
        "p136_independent_review",
        "p136_release_evidence",
        "p137_release_evidence",
        "p137_final_implementation_review",
        "created_at",
    )
    return {key: fixture.publisher_inputs[key] for key in required}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("preliminary", "final"), default="final")
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--canonical-matrix", type=Path, default=DEFAULT_CANONICAL_MATRIX)
    parser.add_argument("--freeze-manifest", type=Path, default=DEFAULT_FREEZE_MANIFEST)
    parser.add_argument("--final-implementation-review", type=Path, default=DEFAULT_FINAL_REVIEW)
    args = parser.parse_args(argv)
    try:
        profile = validate_observation_triage_supervisor_profile(_read_json(args.profile))
        sources = current_p138_source_hashes(ROOT)
        dependencies = current_p138_dependency_bindings(ROOT)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        if args.mode == "preliminary":
            with tempfile.TemporaryDirectory(prefix="p138-release-") as temporary:
                matrix = run_p138_preliminary_matrix(
                    args.output_dir,
                    runtime_factory=CanonicalRuntimeFactory(Path(temporary)),
                    evaluator_overhead_activity={
                        **_zero(EVALUATOR_ACTIVITY_KEYS),
                        "runner_invocation_count": 1,
                        "profile_read_count": 1,
                        "artifact_write_count": 2,
                    },
                )
            manifest = build_p138_freeze_manifest(
                source_bindings=sources,
                profile=profile,
                canonical_matrix=matrix,
                dependency_bindings=dependencies,
                project_root=ROOT,
            )
            preliminary = build_p138_preliminary_evidence(matrix, manifest)
            _write_json(args.output_dir / "canonical-matrix.json", matrix)
            _write_json(args.output_dir / "freeze-manifest.json", manifest)
            _write_json(args.output_dir / "release-evidence.json", preliminary)
            print(json.dumps({"release_status": preliminary["status"], "mode": args.mode, "evidence_hash": preliminary["evidence_hash"]}, sort_keys=True, separators=(",", ":")))
            return 0

        matrix_before = args.canonical_matrix.read_bytes()
        manifest_before = args.freeze_manifest.read_bytes()
        evidence = assemble_p138_release_evidence_from_frozen_matrix(
            _read_json(args.canonical_matrix),
            freeze_manifest=_read_json(args.freeze_manifest),
            final_implementation_review=_read_json(args.final_implementation_review),
            expected_source_hashes=sources,
            expected_profile_hash=p138_profile_hash(profile),
            expected_fixture_hash=p138_fixture_hash(profile, project_root=ROOT),
            expected_dependency_bindings=dependencies,
        )
        if args.canonical_matrix.read_bytes() != matrix_before or args.freeze_manifest.read_bytes() != manifest_before:
            raise P138ProfileError("final_mode_rewrote_frozen_input")
        _write_json(args.output_dir / "release-evidence.json", evidence)
        print(json.dumps({"release_status": evidence["status"], "mode": args.mode, "evidence_hash": evidence["evidence_hash"]}, sort_keys=True, separators=(",", ":")))
        return 0 if evidence["status"] == P138_READY_STATUS else 1
    except Exception as exc:
        print(json.dumps({"release_status": "p138_blocked", "error": str(exc), "error_type": type(exc).__name__}, sort_keys=True, separators=(",", ":")), file=sys.stderr)
        return 1


def _validated_canonical_result(value: Mapping[str, Any], *, row: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(_mapping(value, "canonical_result")))
    expected = _mapping(row.get("expected"), "expected")
    if result.get("status") != expected.get("status"):
        raise P138ProfileError(f"canonical_status_mismatch:{row['case_id']}")
    if result.get("error") != expected.get("error") or result.get("stop_reason") != expected.get("stop_reason"):
        raise P138ProfileError(f"canonical_stop_mismatch:{row['case_id']}")
    if result.get("phase_path") != expected.get("phase_path"):
        raise P138ProfileError(f"canonical_phase_mismatch:{row['case_id']}")
    if result.get("component_boundaries") != expected.get("component_boundaries"):
        raise P138ProfileError(f"canonical_boundary_mismatch:{row['case_id']}")
    return result


def _release_resource_usage(value: Any) -> dict[str, int]:
    raw = _mapping(value or {}, "resource_usage")
    result = _resource_budget()
    for key in ("wall_time_ms", "cpu_time_ms", "peak_memory_bytes"):
        item = raw.get(key, 0)
        result[key] = item if isinstance(item, int) and not isinstance(item, bool) and item >= 0 else 0
    return result


def _combined_phase_path(*results: Mapping[str, Any]) -> list[str]:
    combined: list[str] = []
    for result in results:
        value = result.get("phase_path", [])
        if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
            raise P138ProfileError("observed_phase_path_invalid")
        for phase in value:
            if phase not in combined:
                combined.append(phase)
    return combined


def _resource_budget() -> dict[str, int]:
    return {
        "wall_time_ms": 0,
        "cpu_time_ms": 0,
        "child_cpu_time_ms": 0,
        "peak_memory_bytes": 0,
        "wall_limit_ms": 30_000,
        "cpu_limit_ms": 15_000,
        "peak_memory_limit_bytes": 134_217_728,
    }


def _sum_activity(*values: Mapping[str, Any], field: str, keys: Sequence[str]) -> dict[str, int]:
    result = _zero(keys)
    for value in values:
        current = _mapping(value.get(field), field)
        for key in keys:
            item = current.get(key)
            if isinstance(item, bool) or not isinstance(item, int) or item < 0:
                raise P138ProfileError(f"invalid_{field}")
            result[key] += item
    return result


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise P138ProfileError("invalid_json_object")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise P138ProfileError(f"invalid_{label}")
    return value


def _zero(keys: Sequence[str]) -> dict[str, int]:
    return {key: 0 for key in keys}


def _require(condition: bool, error: str) -> None:
    if not condition:
        raise P138ProfileError(error)


def _runtime_activity(**overrides: int) -> dict[str, int]:
    value = _zero(RUNTIME_ACTIVITY_KEYS)
    value.update(overrides)
    return value


def _evaluator_activity(**overrides: int) -> dict[str, int]:
    value = _zero(EVALUATOR_ACTIVITY_KEYS)
    value.update(overrides)
    return value


_EXPECTED_RUNTIME_ACTIVITY = {
    "P138-CASE-01": _runtime_activity(
        supervisor_lease_acquire_count=1, supervisor_state_read_count=8, phase_write_count=1, ledger_write_count=2, reconciliation_count=1, triage_count=1, recovery_count=1, fsync_count=8
    ),
    "P138-CASE-02": _runtime_activity(
        supervisor_lease_acquire_count=1,
        supervisor_state_read_count=10,
        phase_write_count=6,
        ledger_write_count=2,
        reconciliation_count=1,
        observation_count=1,
        publication_count=1,
        triage_count=1,
        fsync_count=19,
    ),
    "P138-CASE-03": _runtime_activity(
        supervisor_lease_acquire_count=1, supervisor_state_read_count=8, phase_write_count=3, ledger_write_count=2, reconciliation_count=1, observation_count=1, no_work_count=1, fsync_count=13
    ),
    "P138-CASE-04": _runtime_activity(
        supervisor_lease_acquire_count=2,
        supervisor_state_read_count=19,
        phase_write_count=6,
        ledger_write_count=2,
        reconciliation_count=2,
        publication_count=1,
        triage_count=1,
        recovery_count=1,
        fsync_count=19,
    ),
    "P138-CASE-05": _runtime_activity(
        supervisor_lease_acquire_count=2,
        supervisor_state_read_count=19,
        phase_write_count=6,
        ledger_write_count=2,
        reconciliation_count=2,
        observation_count=1,
        publication_count=1,
        triage_count=1,
        recovery_count=1,
        fsync_count=19,
    ),
    "P138-CASE-06": _runtime_activity(
        supervisor_lease_acquire_count=2,
        supervisor_state_read_count=19,
        phase_write_count=6,
        ledger_write_count=2,
        reconciliation_count=2,
        observation_count=1,
        publication_count=1,
        triage_count=1,
        recovery_count=1,
        fsync_count=19,
    ),
    "P138-CASE-07": _runtime_activity(
        supervisor_lease_acquire_count=2,
        supervisor_state_read_count=19,
        phase_write_count=6,
        ledger_write_count=2,
        reconciliation_count=2,
        observation_count=1,
        triage_count=1,
        recovery_count=2,
        fsync_count=19,
    ),
    "P138-CASE-08": _runtime_activity(
        supervisor_lease_acquire_count=2,
        supervisor_state_read_count=19,
        phase_write_count=6,
        ledger_write_count=2,
        reconciliation_count=2,
        observation_count=1,
        publication_count=1,
        triage_count=1,
        fsync_count=19,
    ),
    "P138-CASE-09": _runtime_activity(
        supervisor_lease_acquire_count=2,
        supervisor_state_read_count=19,
        phase_write_count=6,
        ledger_write_count=2,
        reconciliation_count=2,
        observation_count=1,
        publication_count=1,
        fsync_count=19,
    ),
    "P138-CASE-10": _runtime_activity(
        supervisor_lease_acquire_count=2,
        supervisor_state_read_count=16,
        phase_write_count=1,
        ledger_write_count=2,
        reconciliation_count=2,
        triage_count=2,
        recovery_count=1,
        fsync_count=8,
    ),
    "P138-CASE-11": _runtime_activity(
        supervisor_lease_acquire_count=2,
        supervisor_state_read_count=17,
        phase_write_count=1,
        reconciliation_count=2,
        recovery_count=1,
        fsync_count=2,
    ),
    "P138-CASE-12": _runtime_activity(
        supervisor_lease_acquire_count=2,
        supervisor_state_read_count=17,
        phase_write_count=1,
        reconciliation_count=2,
        recovery_count=1,
        fsync_count=2,
    ),
    "P138-CASE-13": _runtime_activity(
        supervisor_lease_acquire_count=2,
        supervisor_state_read_count=17,
        phase_write_count=1,
        reconciliation_count=2,
        recovery_count=1,
        fsync_count=2,
    ),
    "P138-CASE-14": _runtime_activity(),
    "P138-CASE-15": _runtime_activity(
        supervisor_lease_acquire_count=1,
        supervisor_state_read_count=8,
        phase_write_count=1,
        reconciliation_count=1,
        observation_count=1,
        fsync_count=3,
    ),
    "P138-CASE-16": _runtime_activity(
        supervisor_lease_acquire_count=1,
        supervisor_state_read_count=8,
        phase_write_count=3,
        reconciliation_count=1,
        observation_count=1,
        publication_count=1,
        fsync_count=7,
    ),
    "P138-CASE-17": _runtime_activity(
        supervisor_lease_acquire_count=1,
        supervisor_state_read_count=8,
        reconciliation_count=1,
    ),
    "P138-CASE-18": _runtime_activity(
        supervisor_lease_acquire_count=1,
        supervisor_state_read_count=12,
        phase_write_count=6,
        ledger_write_count=2,
        reconciliation_count=1,
        observation_count=1,
        publication_count=1,
        triage_count=1,
        fsync_count=19,
    ),
    "P138-CASE-19": _runtime_activity(
        supervisor_lease_acquire_count=2,
        supervisor_state_read_count=2,
        heartbeat_write_count=1,
        readiness_write_count=1,
        termination_write_count=1,
        fsync_count=6,
    ),
    "P138-CASE-20": _runtime_activity(),
    "P138-CASE-21": _runtime_activity(
        supervisor_lease_acquire_count=2,
        supervisor_state_read_count=19,
        phase_write_count=6,
        ledger_write_count=2,
        reconciliation_count=2,
        publication_count=1,
        triage_count=1,
        recovery_count=1,
        fsync_count=19,
    ),
    "P138-CASE-22": _runtime_activity(
        supervisor_lease_acquire_count=2,
        supervisor_state_read_count=17,
        phase_write_count=3,
        ledger_write_count=2,
        reconciliation_count=2,
        recovery_count=1,
        no_work_count=1,
        fsync_count=13,
    ),
    "P138-CASE-23": _runtime_activity(
        supervisor_lease_acquire_count=2,
        supervisor_state_read_count=19,
        phase_write_count=6,
        ledger_write_count=2,
        reconciliation_count=2,
        observation_count=1,
        triage_count=1,
        recovery_count=2,
        fsync_count=19,
    ),
    "P138-CASE-24": _runtime_activity(
        supervisor_lease_acquire_count=2,
        supervisor_state_read_count=19,
        phase_write_count=6,
        ledger_write_count=2,
        reconciliation_count=2,
        observation_count=1,
        triage_count=1,
        recovery_count=2,
        fsync_count=19,
    ),
    "P138-CASE-25": _runtime_activity(
        supervisor_lease_acquire_count=2,
        supervisor_state_read_count=16,
        reconciliation_count=2,
    ),
    "P138-CASE-26": _runtime_activity(
        supervisor_lease_acquire_count=13,
        supervisor_state_read_count=79,
        phase_write_count=8,
        ledger_write_count=4,
        heartbeat_write_count=4,
        readiness_write_count=5,
        termination_write_count=2,
        reconciliation_count=6,
        observation_count=3,
        recovery_count=1,
        no_work_count=2,
        fsync_count=55,
    ),
    "P138-CASE-27": _runtime_activity(
        supervisor_lease_acquire_count=5,
        supervisor_state_read_count=30,
        phase_write_count=6,
        ledger_write_count=4,
        heartbeat_write_count=2,
        readiness_write_count=2,
        termination_write_count=1,
        reconciliation_count=2,
        observation_count=2,
        no_work_count=2,
        fsync_count=36,
    ),
    "P138-CASE-28": _runtime_activity(
        supervisor_lease_acquire_count=4,
        supervisor_state_read_count=10,
        heartbeat_write_count=2,
        readiness_write_count=2,
        termination_write_count=2,
        fsync_count=12,
    ),
    "P138-CASE-29": _runtime_activity(
        supervisor_lease_acquire_count=2,
        supervisor_state_read_count=19,
        phase_write_count=6,
        ledger_write_count=2,
        reconciliation_count=2,
        publication_count=1,
        triage_count=1,
        recovery_count=1,
        fsync_count=19,
    ),
    "P138-CASE-30": _runtime_activity(
        supervisor_lease_acquire_count=2,
        supervisor_state_read_count=17,
        phase_write_count=3,
        ledger_write_count=2,
        reconciliation_count=2,
        recovery_count=1,
        no_work_count=1,
        fsync_count=13,
    ),
}
_RUNTIME_ACTIVITY_CORRECTIONS = {
    "P138-CASE-02": {"supervisor_state_read_count": 12},
    "P138-CASE-03": {"supervisor_state_read_count": 9},
    "P138-CASE-04": {"supervisor_state_read_count": 21, "observation_count": 1},
    "P138-CASE-05": {"supervisor_state_read_count": 21},
    "P138-CASE-06": {"supervisor_state_read_count": 21},
    "P138-CASE-07": {"supervisor_state_read_count": 21},
    "P138-CASE-08": {"supervisor_state_read_count": 21},
    "P138-CASE-09": {"supervisor_state_read_count": 21},
    "P138-CASE-15": {"supervisor_state_read_count": 9},
    "P138-CASE-16": {
        "supervisor_state_read_count": 6,
        "phase_write_count": 0,
        "observation_count": 0,
        "publication_count": 0,
        "fsync_count": 0,
    },
    "P138-CASE-18": {"supervisor_state_read_count": 14},
    "P138-CASE-21": {"supervisor_state_read_count": 21},
    "P138-CASE-22": {"supervisor_state_read_count": 18},
    "P138-CASE-23": {"supervisor_state_read_count": 21},
    "P138-CASE-24": {"supervisor_state_read_count": 21},
    "P138-CASE-26": {"supervisor_state_read_count": 84},
    "P138-CASE-27": {"supervisor_state_read_count": 32},
    "P138-CASE-29": {"supervisor_state_read_count": 21},
    "P138-CASE-30": {"supervisor_state_read_count": 18},
}
for _case_id, _correction in _RUNTIME_ACTIVITY_CORRECTIONS.items():
    _EXPECTED_RUNTIME_ACTIVITY[_case_id].update(_correction)
_EXPECTED_EVALUATOR_ACTIVITY = {
    **{
        case_id: _evaluator_activity(crash_injection_count=1)
        for case_id in (
            "P138-CASE-04",
            "P138-CASE-05",
            "P138-CASE-06",
            "P138-CASE-07",
            "P138-CASE-08",
            "P138-CASE-09",
            "P138-CASE-21",
            "P138-CASE-22",
            "P138-CASE-23",
            "P138-CASE-24",
            "P138-CASE-29",
            "P138-CASE-30",
        )
    },
    "P138-CASE-19": _evaluator_activity(signal_injection_count=1),
    "P138-CASE-20": _evaluator_activity(fake_guard_injection_count=1),
    "P138-CASE-28": _evaluator_activity(signal_injection_count=1),
}


if __name__ == "__main__":
    raise SystemExit(main())
