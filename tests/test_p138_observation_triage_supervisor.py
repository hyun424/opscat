from __future__ import annotations

import fcntl
import json
import os
import signal
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest

from app.services import p138_observation_triage_supervisor as p138_api
from app.services.p110_evaluation import stable_hash
from app.services.p136_incremental_observer import (
    FORBIDDEN_AUTHORITY_KEYS as P136_FORBIDDEN_AUTHORITY_KEYS,
)
from app.services.p136_incremental_observer import (
    P136ObservationError,
    observe_one_cycle,
)
from app.services.p137_contracts import (
    FIXED_P136_HANDOFF_PATH,
)
from app.services.p137_contracts import (
    FORBIDDEN_AUTHORITY_KEYS as P137_FORBIDDEN_AUTHORITY_KEYS,
)
from app.services.p137_p136_handoff import (
    P137HandoffError,
    publish_p136_handoff_bundle,
)
from app.services.p138_observation_triage_supervisor import (
    EVALUATOR_ACTIVITY_KEYS,
    FORBIDDEN_AUTHORITY_KEYS,
    RUNTIME_ACTIVITY_KEYS,
    P138StopController,
    P138SupervisorError,
    build_observation_triage_supervisor_config,
    run_p138_supervisor_once,
    run_p138_supervisor_once_for_evaluation,
    validate_observation_triage_supervisor_config,
    validate_supervisor_ledger,
    validate_supervisor_phase,
    zero_evaluator_activity,
    zero_forbidden_authority,
    zero_runtime_activity,
)
from tests.fixtures.p138 import (
    append_observation_entry,
    build_p138_fixture,
)


def _read_json(root: Path, relative: str) -> dict[str, Any]:
    value = json.loads((root / relative).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write_json(root: Path, relative: str, value: dict[str, Any]) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def _config(tmp_path: Path, **fixture_kwargs: Any) -> tuple[Any, dict[str, Any]]:
    fixture = build_p138_fixture(tmp_path, **fixture_kwargs)
    config = build_observation_triage_supervisor_config(fixture.config_input)
    return fixture, config


def _run_once(fixture: Any, config: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    return run_p138_supervisor_once(
        base_path=fixture.root,
        config=config,
        p136_runtime=fixture.p136_runtime,
        publisher_inputs=fixture.publisher_inputs,
        now="2026-07-13T00:10:04Z",
        **kwargs,
    )


def _bootstrap_accepted(tmp_path: Path) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    fixture, config = _config(
        tmp_path,
        publish_genesis=True,
        accept_genesis=True,
    )
    result = _run_once(fixture, config)
    assert result["status"] == "ok", result
    assert result["ledger"]["last_published_promotion_sequence"] == 1
    return fixture, config, result


def test_counter_schemas_are_exact_and_shared() -> None:
    assert tuple(FORBIDDEN_AUTHORITY_KEYS) == tuple(P136_FORBIDDEN_AUTHORITY_KEYS)
    assert tuple(FORBIDDEN_AUTHORITY_KEYS) == tuple(P137_FORBIDDEN_AUTHORITY_KEYS)
    assert set(zero_forbidden_authority()) == set(FORBIDDEN_AUTHORITY_KEYS)
    assert set(zero_runtime_activity()) == set(RUNTIME_ACTIVITY_KEYS)
    assert set(zero_evaluator_activity()) == set(EVALUATOR_ACTIVITY_KEYS)
    assert all(type(value) is int and value == 0 for value in zero_forbidden_authority().values())


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (lambda value: value.__setitem__("unknown", 1), "unexpected_config_field"),
        (lambda value: value.pop("phase_path"), "missing_config_field"),
        (lambda value: value.__setitem__("phase_path", "/tmp/phase.json"), "unsafe_path"),
        (lambda value: value.__setitem__("phase_path", "../phase.json"), "unsafe_path"),
        (lambda value: value.__setitem__("ledger_path", value["phase_path"]), "paths_overlap"),
        (
            lambda value: value["limits"].__setitem__("max_supervisor_cycles", True),
            "invalid_limit",
        ),
        (
            lambda value: value["forbidden_authority"].__setitem__("network_call_count", 1),
            "invalid_forbidden_authority_schema",
        ),
        (
            lambda value: value["forbidden_authority"].__setitem__("notification_count", 0),
            "invalid_forbidden_authority_schema",
        ),
    ],
)
def test_config_rejects_schema_path_limit_and_authority_drift(
    tmp_path: Path,
    mutation: Any,
    expected: str,
) -> None:
    fixture = build_p138_fixture(tmp_path, publish_genesis=False)
    value = deepcopy(fixture.config_input)
    mutation(value)
    with pytest.raises(P138SupervisorError, match=expected):
        build_observation_triage_supervisor_config(value)


def test_config_is_exact_self_hashed_and_binds_complete_components(tmp_path: Path) -> None:
    fixture = build_p138_fixture(tmp_path, publish_genesis=False)
    config = build_observation_triage_supervisor_config(fixture.config_input)
    validate_observation_triage_supervisor_config(config)
    assert config["schema_version"] == "p138.observation_triage_supervisor_config.v1"
    assert config["p136_config"] == fixture.p136_runtime["config"]
    assert config["p137_config"]["schema_version"] == "p137.triage_agent_config.v1"
    assert config["config_hash"] == stable_hash(
        {key: item for key, item in config.items() if key != "config_hash"}
    )
    tampered = deepcopy(config)
    tampered["limits"]["max_supervisor_cycles"] += 1
    with pytest.raises(P138SupervisorError, match="config_hash_invalid"):
        validate_observation_triage_supervisor_config(tampered)


def test_nonblocking_p138_lease_precedes_all_state_and_component_work(tmp_path: Path) -> None:
    fixture, config = _config(tmp_path, publish_genesis=False)
    lease = fixture.root / config["lease_path"]
    lease.parent.mkdir(parents=True, exist_ok=True)
    with lease.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = _run_once(fixture, config)
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    assert result["status"] == "failed_closed"
    assert result["expected_error"] == "supervisor_lease_unavailable"
    assert result["component_calls"] == []
    assert result["runtime_activity"] == zero_runtime_activity()
    assert not (fixture.root / config["phase_path"]).exists()
    assert not (fixture.root / config["ledger_path"]).exists()


def test_publisher_snapshot_lease_conflict_precedes_observation_and_phase_writes(
    tmp_path: Path,
) -> None:
    fixture, config, _bootstrap = _bootstrap_accepted(tmp_path)
    append_observation_entry(fixture)
    lease = fixture.root / config["publisher_lease_path"]
    lease.parent.mkdir(parents=True, exist_ok=True)
    with lease.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = _run_once(fixture, config)
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    assert result["status"] == "failed_closed"
    assert result["expected_error"] == "publisher:publisher_lease_unavailable"
    assert result["phase_path"] == []
    assert result["component_calls"] == []
    assert result["runtime_activity"]["observation_count"] == 0
    assert result["runtime_activity"]["phase_write_count"] == 0


@pytest.mark.parametrize("raw", [b'{\n  "value": 1\n}\n', b'{"value":1}', b'{"value":1}\n\n'])
def test_p138_state_reader_rejects_noncanonical_json_framing(
    tmp_path: Path,
    raw: bytes,
) -> None:
    root = tmp_path / "runtime"
    root.mkdir()
    p138_api._atomic_write_json(root, "p138/probe.json", {"value": 1}, maximum=1024)
    (root / "p138/probe.json").write_bytes(raw)
    with pytest.raises(P138SupervisorError, match="state_json_noncanonical"):
        p138_api._read_json_optional(root, "p138/probe.json", maximum=1024)


def test_absent_publisher_genesis_rejects_before_observation(tmp_path: Path) -> None:
    fixture, config = _config(tmp_path, publish_genesis=False)
    component_calls: list[str] = []

    def observe(_runtime: Any) -> dict[str, Any]:
        component_calls.append("p136")
        raise AssertionError("observation_must_not_run_without_genesis")

    result = run_p138_supervisor_once_for_evaluation(
        base_path=fixture.root,
        config=config,
        p136_runtime=fixture.p136_runtime,
        publisher_inputs=fixture.publisher_inputs,
        now="2026-07-13T00:10:04Z",
        component_callables={"observe": observe},
    )

    assert result["status"] == "failed_closed"
    assert result["expected_error"] == "bootstrap_publisher_genesis_required"
    assert result["component_calls"] == []
    assert component_calls == []


def test_bootstrap_reconciles_unaccepted_genesis_before_observation(tmp_path: Path) -> None:
    fixture, config = _config(
        tmp_path,
        publish_genesis=True,
        accept_genesis=False,
    )
    consumed_before = list(
        fixture.p136_runtime["checkpoint"]["consumed_index_read_receipt_hashes"]
    )
    result = _run_once(fixture, config)
    assert result["status"] == "ok", result
    assert result["component_calls"] == ["p137"]
    assert result["runtime_activity"]["observation_count"] == 0
    assert result["runtime_activity"]["publication_count"] == 0
    assert result["runtime_activity"]["triage_count"] == 1
    assert result["ledger"]["bundle_sequence"] == 1
    assert result["ledger"]["last_published_promotion_sequence"] == 1
    assert fixture.p136_runtime["checkpoint"]["consumed_index_read_receipt_hashes"] == consumed_before


def test_real_new_promotion_runs_p136_publisher_and_p137_once(tmp_path: Path) -> None:
    fixture, config, _ = _bootstrap_accepted(tmp_path)
    append_observation_entry(fixture)
    result = _run_once(fixture, config)
    assert result["status"] == "ok", result
    assert result["component_calls"] == ["p136", "publisher", "p137"]
    assert result["phase_path"] == [
        "cycle_started",
        "p136_completed",
        "handoff_selected",
        "handoff_published",
        "p137_accepted",
        "cycle_finalized",
    ]
    assert result["ledger"]["bundle_sequence"] == 2
    assert result["ledger"]["last_published_promotion_sequence"] == 2
    assert list(result["publisher_bundle"]["promotion_map"]) == [
        fixture.entries[1]["entry_hash"]
    ]
    assert result["forbidden_authority"] == zero_forbidden_authority()


def test_real_zero_work_suppresses_publisher_and_p137(tmp_path: Path) -> None:
    fixture, config, _ = _bootstrap_accepted(tmp_path)
    publisher_state_before = _read_json(fixture.root, config["publisher_state_path"])
    p137_ledger_before = _read_json(
        fixture.root, config["p137_config"]["ledger_path"]
    )
    result = _run_once(fixture, config)
    assert result["status"] == "ok", result
    assert result["component_calls"] == ["p136"]
    assert result["phase_path"] == [
        "cycle_started",
        "p136_completed",
        "cycle_finalized",
    ]
    assert result["no_work"] is True
    assert result["runtime_activity"]["no_work_count"] == 1
    assert _read_json(fixture.root, config["publisher_state_path"]) == publisher_state_before
    assert _read_json(fixture.root, config["p137_config"]["ledger_path"]) == p137_ledger_before


@pytest.mark.parametrize(
    "crash_boundary",
    ["cycle_outcome_intent_durable", "cycle_checkpoint_durable"],
)
def test_p136_empty_same_cycle_recovery_consumes_no_second_receipt(
    tmp_path: Path,
    crash_boundary: str,
) -> None:
    fixture, config, _bootstrap = _bootstrap_accepted(tmp_path)
    probe = fixture.p136_runtime["probe"]

    def crash(phase: str) -> None:
        if phase == crash_boundary:
            raise P136ObservationError(f"injected_{phase}")

    fixture.p136_runtime["evaluator_crash_injector"] = crash
    first = run_p138_supervisor_once_for_evaluation(
        base_path=fixture.root,
        config=config,
        p136_runtime=fixture.p136_runtime,
        publisher_inputs=fixture.publisher_inputs,
        now="2026-07-13T00:10:04Z",
    )
    assert first["status"] == "failed_closed"
    assert first["phase"]["phase"] == "cycle_started"
    index_reads = probe.index_read_count
    fixture.p136_runtime.pop("evaluator_crash_injector")
    recovered = _run_once(fixture, config)
    assert recovered["status"] == "ok", recovered
    assert recovered["no_work"] is True
    assert recovered["runtime_activity"]["recovery_count"] >= 1
    assert probe.index_read_count == index_reads
    assert len(
        recovered["p136_result"]["advanced_checkpoint"][
            "consumed_index_read_receipt_hashes"
        ]
    ) == 2
    assert recovered["p136_result"]["cycle_outcome"]["schema_version"] == "p136.cycle_completion.v1"


@pytest.mark.parametrize(
    "crash_after",
    [
        "cycle_started",
        "p136_completed",
        "handoff_selected",
        "handoff_published",
        "p137_committed",
        "p137_accepted",
    ],
)
def test_restart_through_every_phase_boundary_publishes_and_triages_once(
    tmp_path: Path,
    crash_after: str,
) -> None:
    fixture, config, _ = _bootstrap_accepted(tmp_path)
    append_observation_entry(fixture)
    first = run_p138_supervisor_once_for_evaluation(
        base_path=fixture.root,
        config=config,
        p136_runtime=fixture.p136_runtime,
        publisher_inputs=fixture.publisher_inputs,
        now="2026-07-13T00:10:04Z",
        crash_after_phase=crash_after,
    )
    assert first["status"] == "failed_closed"
    state_after_crash = _read_json(fixture.root, config["publisher_state_path"])
    p137_ledger_path = config["p137_config"]["ledger_path"]
    p137_ledger_after_crash = (
        _read_json(fixture.root, p137_ledger_path)
        if (fixture.root / p137_ledger_path).exists()
        else None
    )
    recovered = _run_once(fixture, config)
    assert recovered["status"] == "ok", recovered
    final_state = _read_json(fixture.root, config["publisher_state_path"])
    assert final_state["last_bundle_sequence"] == 2
    if state_after_crash["last_bundle_sequence"] == 2:
        assert final_state["last_bundle_hash"] == state_after_crash["last_bundle_hash"]
    final_p137_ledger = _read_json(fixture.root, p137_ledger_path)
    if p137_ledger_after_crash is not None and crash_after in {"p137_committed", "p137_accepted"}:
        assert final_p137_ledger["ledger_hash"] == p137_ledger_after_crash["ledger_hash"]
        assert "p137" not in recovered["component_calls"]
    assert recovered["ledger"]["bundle_sequence"] == 2
    assert recovered["ledger"]["last_published_promotion_sequence"] == 2


def test_p137_lease_conflict_retains_current_bundle_until_restart(tmp_path: Path) -> None:
    fixture, config = _config(
        tmp_path,
        publish_genesis=True,
        accept_genesis=False,
    )
    lease_path = fixture.root / config["p137_config"]["lease_path"]
    lease_path.parent.mkdir(parents=True, exist_ok=True)
    with lease_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        conflicted = _run_once(fixture, config)
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    assert conflicted["status"] == "failed_closed"
    assert conflicted["expected_error"] == "p137:lease_conflict"
    assert conflicted["component_calls"] == ["p137"]
    assert _read_json(fixture.root, config["publisher_state_path"])["last_bundle_sequence"] == 1
    recovered = _run_once(fixture, config)
    assert recovered["status"] == "ok", recovered
    assert recovered["ledger"]["bundle_sequence"] == 1


def test_partial_genesis_fails_closed_before_any_component_call(tmp_path: Path) -> None:
    fixture, config = _config(
        tmp_path,
        genesis_entries=2,
        publish_genesis=True,
        partial_genesis=True,
    )
    result = _run_once(fixture, config)
    assert result["status"] == "failed_closed"
    assert result["expected_error"] == "bootstrap_promotion_history_incomplete"
    assert result["component_calls"] == []
    assert not (fixture.root / config["ledger_path"]).exists()


def test_non_genesis_without_p138_history_fails_closed(tmp_path: Path) -> None:
    fixture, config = _config(
        tmp_path,
        publish_genesis=True,
        accept_genesis=False,
    )
    append_observation_entry(fixture)
    observed = observe_one_cycle(fixture.p136_runtime)
    fixture.p136_runtime["checkpoint"] = observed["advanced_checkpoint"]
    bundle = publish_p136_handoff_bundle(
        base_path=fixture.root,
        state_path=config["publisher_state_path"],
        intent_path=config["publisher_intent_path"],
        lease_path=config["publisher_lease_path"],
        fixed_handoff_path=FIXED_P136_HANDOFF_PATH,
        p136_config=fixture.p136_runtime["config"],
        p136_runtime_authority=fixture.p136_runtime["authority"],
        now=fixture.p136_runtime["now"],
        p136_checkpoint=observed["advanced_checkpoint"],
        canonical_entry_map=fixture.publisher_inputs["canonical_entry_map"],
        promotion_records=observed["promotion_records"],
        p136_independent_review=fixture.publisher_inputs["p136_independent_review"],
        p136_release_evidence=fixture.publisher_inputs["p136_release_evidence"],
        created_at="2026-07-13T00:10:03Z",
    )
    assert bundle["bundle_sequence"] == 2
    result = _run_once(fixture, config)
    assert result["status"] == "failed_closed"
    assert result["expected_error"] == "bootstrap_requires_genesis_bundle"
    assert result["component_calls"] == []


def test_production_entrypoint_rejects_arbitrary_component_callables_before_invocation(tmp_path: Path) -> None:
    fixture, config = _config(tmp_path, publish_genesis=False)
    called = False

    def forbidden() -> None:
        nonlocal called
        called = True

    with pytest.raises(P138SupervisorError, match="production_component_callables_forbidden"):
        _run_once(
            fixture,
            config,
            component_callables={"observe": forbidden},
        )
    assert called is False
    assert not (fixture.root / config["lease_path"]).exists()


def test_supplied_p136_checkpoint_must_match_prior_p138_ledger_before_components(
    tmp_path: Path,
) -> None:
    fixture, config, prior = _bootstrap_accepted(tmp_path)
    stale = deepcopy(fixture.p136_runtime["checkpoint"])
    stale["updated_at"] = "2026-07-13T00:10:03Z"
    stale["checkpoint_hash"] = stable_hash(
        {key: item for key, item in stale.items() if key != "checkpoint_hash"}
    )
    fixture.p136_runtime["checkpoint"] = stale
    called: list[str] = []

    def observe(_runtime: Any) -> dict[str, Any]:
        called.append("p136")
        raise AssertionError("stale_checkpoint_must_fail_preflight")

    result = run_p138_supervisor_once_for_evaluation(
        base_path=fixture.root,
        config=config,
        p136_runtime=fixture.p136_runtime,
        publisher_inputs=fixture.publisher_inputs,
        now="2026-07-13T00:10:04Z",
        component_callables={"observe": observe},
    )

    assert prior["ledger"]["resulting_p136_checkpoint_hash"] != stale["checkpoint_hash"]
    assert result["status"] == "failed_closed"
    assert result["expected_error"] == "p136_checkpoint_p138_ledger_mismatch"
    assert result["component_calls"] == []
    assert called == []


def test_real_p137_release_validator_rejects_fabricated_minimal_evidence(
    tmp_path: Path,
) -> None:
    fixture = build_p138_fixture(tmp_path, publish_genesis=True)
    fake_evidence = {
        "schema_version": "p137.release_evidence.v1",
        "status": "p137_local_evidence_triage_qualified",
        "forbidden_authority": zero_forbidden_authority(),
    }
    fake_evidence["evidence_hash"] = stable_hash(fake_evidence)
    fake_review = {
        "schema_version": "p137.final_implementation_review.v1",
        "decision": "approve",
    }
    config_input = deepcopy(fixture.config_input)
    config_input["p137_release_evidence_hash"] = fake_evidence["evidence_hash"]
    config = build_observation_triage_supervisor_config(config_input)
    publisher_inputs = deepcopy(fixture.publisher_inputs)
    publisher_inputs["p137_release_evidence"] = fake_evidence
    publisher_inputs["p137_final_implementation_review"] = fake_review

    with pytest.raises(P138SupervisorError, match="invalid_p137_release_evidence"):
        run_p138_supervisor_once(
            base_path=fixture.root,
            config=config,
            p136_runtime=fixture.p136_runtime,
            publisher_inputs=publisher_inputs,
            now="2026-07-13T00:10:04Z",
        )


@pytest.mark.parametrize(
    "publisher_crash_phase",
    [
        "publisher_intent_durable",
        "publisher_fixed_replaced",
        "publisher_state_replaced",
    ],
)
def test_supervisor_recovers_real_publisher_split_crashes_exactly_once(
    tmp_path: Path,
    publisher_crash_phase: str,
) -> None:
    fixture, config, _prior = _bootstrap_accepted(tmp_path)
    append_observation_entry(fixture)

    def crashing_publish(**kwargs: Any) -> dict[str, Any]:
        def crash_at(phase: str) -> None:
            if phase == publisher_crash_phase:
                raise P137HandoffError(f"injected_{phase}")

        return publish_p136_handoff_bundle(
            **kwargs,
            evaluator_crash_injector=crash_at,
        )

    first = run_p138_supervisor_once_for_evaluation(
        base_path=fixture.root,
        config=config,
        p136_runtime=fixture.p136_runtime,
        publisher_inputs=fixture.publisher_inputs,
        now="2026-07-13T00:10:04Z",
        component_callables={"publish": crashing_publish},
    )
    assert first["status"] == "failed_closed"
    assert first["phase"]["phase"] == "handoff_selected"
    pending = _read_json(fixture.root, config["publisher_intent_path"])
    expected_bundle = pending["bundle"]

    recovered = _run_once(fixture, config)

    assert recovered["status"] == "ok", recovered
    assert recovered["ledger"]["bundle_sequence"] == 2
    assert recovered["ledger"]["bundle_hash"] == expected_bundle["bundle_hash"]
    assert _read_json(fixture.root, config["publisher_state_path"])[
        "last_bundle_sequence"
    ] == 2
    assert not (fixture.root / config["publisher_intent_path"]).exists()


@pytest.mark.parametrize("crash_after", ["cycle_finalized", "ledger_durable"])
def test_finalization_crash_windows_reconcile_one_ledger_and_checkpoint(
    tmp_path: Path,
    crash_after: str,
) -> None:
    fixture, config, prior = _bootstrap_accepted(tmp_path)
    append_observation_entry(fixture)
    first = run_p138_supervisor_once_for_evaluation(
        base_path=fixture.root,
        config=config,
        p136_runtime=fixture.p136_runtime,
        publisher_inputs=fixture.publisher_inputs,
        now="2026-07-13T00:10:04Z",
        crash_after_phase=crash_after,
    )
    assert first["status"] == "failed_closed"
    assert _read_json(fixture.root, config["phase_path"])["phase"] == "cycle_finalized"
    publisher_after_crash = _read_json(fixture.root, config["publisher_state_path"])
    assert publisher_after_crash["last_bundle_sequence"] == 2

    recovered = _run_once(fixture, config)

    assert recovered["status"] == "ok", recovered
    assert recovered["ledger"]["cycle_sequence"] == prior["ledger"]["cycle_sequence"] + 1
    assert recovered["ledger"]["bundle_sequence"] == 2
    assert recovered["checkpoint"]["last_p138_ledger_hash"] == recovered["ledger"]["ledger_hash"]
    assert _read_json(fixture.root, config["publisher_state_path"])["state_hash"] == publisher_after_crash["state_hash"]


def test_ledger_validation_and_startup_reject_recomputed_non_genesis_fork(
    tmp_path: Path,
) -> None:
    fixture, config, result = _bootstrap_accepted(tmp_path)
    fork = deepcopy(result["ledger"])
    fork["cycle_sequence"] = 2
    fork["previous_ledger_hash"] = stable_hash({"unproven": "predecessor"})
    fork["ledger_hash"] = stable_hash(
        {key: item for key, item in fork.items() if key != "ledger_hash"}
    )
    with pytest.raises(P138SupervisorError, match="ledger_genesis_lineage_invalid"):
        validate_supervisor_ledger(fork, config=config)

    (fixture.root / config["phase_path"]).unlink()
    _write_json(fixture.root, config["ledger_path"], fork)
    ledger_path = Path(config["ledger_path"])
    fork_history_path = (
        ledger_path.parent
        / f".{ledger_path.name}.history"
        / f"{fork['ledger_hash'].removeprefix('sha256:')}.json"
    )
    _write_json(fixture.root, fork_history_path.as_posix(), fork)
    checkpoint = deepcopy(result["checkpoint"])
    checkpoint.update(
        {
            "last_finalized_cycle_sequence": fork["cycle_sequence"],
            "last_finalized_cycle_id": fork["cycle_id"],
            "last_p138_ledger_hash": fork["ledger_hash"],
        }
    )
    checkpoint["checkpoint_hash"] = stable_hash(
        {key: item for key, item in checkpoint.items() if key != "checkpoint_hash"}
    )
    _write_json(fixture.root, config["checkpoint_path"], checkpoint)
    startup = _run_once(fixture, config)
    assert startup["status"] == "failed_closed"
    assert "ledger_history_predecessor_missing" in startup["expected_error"]
    assert startup["component_calls"] == []


def test_generated_phase_and_ledger_are_exact_hash_chains(tmp_path: Path) -> None:
    fixture, config, result = _bootstrap_accepted(tmp_path)
    phase = result["phase"]
    ledger = result["ledger"]
    validate_supervisor_phase(phase, config=config)
    validate_supervisor_ledger(ledger, config=config)
    assert phase["phase"] == "cycle_finalized"
    assert ledger["phase_hash"] == phase["phase_hash"]
    assert ledger["previous_ledger_hash"] is None
    bad_phase = deepcopy(phase)
    bad_phase["bundle_hash"] = stable_hash({"fork": True})
    with pytest.raises(P138SupervisorError, match="phase_hash_invalid"):
        validate_supervisor_phase(bad_phase, config=config)
    bad_ledger = deepcopy(ledger)
    bad_ledger["previous_ledger_hash"] = stable_hash({"fork": True})
    with pytest.raises(P138SupervisorError, match="ledger_hash_invalid"):
        validate_supervisor_ledger(bad_ledger, config=config)


def test_corrupt_ledger_preserves_prior_component_bytes_and_fails_closed(tmp_path: Path) -> None:
    fixture, config, _ = _bootstrap_accepted(tmp_path)
    publisher_before = (fixture.root / config["p136_handoff_bundle_path"]).read_bytes()
    ledger = _read_json(fixture.root, config["ledger_path"])
    ledger["ledger_hash"] = stable_hash({"corrupt": True})
    _write_json(fixture.root, config["ledger_path"], ledger)
    result = _run_once(fixture, config)
    assert result["status"] == "failed_closed"
    assert "ledger_hash_invalid" in result["expected_error"]
    assert result["component_calls"] == []
    assert (fixture.root / config["p136_handoff_bundle_path"]).read_bytes() == publisher_before


def test_finite_loop_writes_heartbeat_readiness_and_max_cycle_termination(tmp_path: Path) -> None:
    fixture, config, _bootstrap = _bootstrap_accepted(tmp_path)
    result = p138_api.run_p138_supervisor_loop_for_evaluation(
        base_path=fixture.root,
        config=config,
        p136_runtime=fixture.p136_runtime,
        publisher_inputs=fixture.publisher_inputs,
        now_values=("2026-07-13T00:10:04Z", "2026-07-13T00:10:05Z"),
        monotonic=lambda: 1.0,
        sleep=lambda _: None,
    )
    assert result["status"] == "stopped", result
    assert result["stop_reason"] == "max_cycles_reached"
    assert result["cycles_completed"] == 2
    assert result["runtime_activity"]["heartbeat_write_count"] == 2
    assert result["runtime_activity"]["readiness_write_count"] == 2
    assert result["runtime_activity"]["termination_write_count"] == 1
    assert _read_json(fixture.root, config["heartbeat_path"])["cycle_sequence"] == 2
    assert _read_json(fixture.root, config["readiness_path"])["status"] == "stopped"
    assert result["forbidden_authority"] == zero_forbidden_authority()


def test_loop_propagates_each_cycle_time_into_p136_and_publisher_inputs(
    tmp_path: Path,
) -> None:
    fixture, config, _bootstrap = _bootstrap_accepted(tmp_path)
    observed_times: list[str] = []

    def observe(runtime: Mapping[str, Any]) -> dict[str, Any]:
        observed_times.append(str(runtime["now"]))
        return observe_one_cycle(runtime)

    times = ("2026-07-13T00:10:04Z", "2026-07-13T00:10:05Z")
    result = p138_api.run_p138_supervisor_loop_for_evaluation(
        base_path=fixture.root,
        config=config,
        p136_runtime=fixture.p136_runtime,
        publisher_inputs=fixture.publisher_inputs,
        now_values=times,
        monotonic=lambda: 1.0,
        sleep=lambda _: None,
        component_callables={"observe": observe},
    )

    assert result["status"] == "stopped"
    assert observed_times == list(times)
    assert fixture.p136_runtime["now"] == times[-1]
    assert fixture.publisher_inputs["created_at"] == times[-1]


def test_loop_receipt_exhaustion_and_failure_threshold_have_distinct_stops(tmp_path: Path) -> None:
    fixture = build_p138_fixture(
        tmp_path / "receipt",
        publish_genesis=True,
        accept_genesis=True,
    )
    config_input = deepcopy(fixture.config_input)
    config_input["limits"]["max_supervisor_cycles"] = 4
    receipt_config = build_observation_triage_supervisor_config(config_input)
    bootstrap = _run_once(fixture, receipt_config)
    assert bootstrap["status"] == "ok", bootstrap
    exhausted = p138_api.run_p138_supervisor_loop_for_evaluation(
        base_path=fixture.root,
        config=receipt_config,
        p136_runtime=fixture.p136_runtime,
        publisher_inputs=fixture.publisher_inputs,
        now_values=tuple(f"2026-07-13T00:10:0{index}Z" for index in range(4, 8)),
        monotonic=lambda: 1.0,
        sleep=lambda _: None,
    )
    assert exhausted["stop_reason"] == "receipt_exhausted"

    failed_fixture, failed_config, _bootstrap = _bootstrap_accepted(
        tmp_path / "failure"
    )
    p136_lease = failed_fixture.root / failed_fixture.p136_runtime["config"]["lease_path"]
    p136_lease.parent.mkdir(parents=True, exist_ok=True)
    with p136_lease.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        failed = p138_api.run_p138_supervisor_loop_for_evaluation(
            base_path=failed_fixture.root,
            config=failed_config,
            p136_runtime=failed_fixture.p136_runtime,
            publisher_inputs=failed_fixture.publisher_inputs,
            now_values=("2026-07-13T00:10:04Z", "2026-07-13T00:10:05Z"),
            monotonic=lambda: 1.0,
            sleep=lambda _: None,
        )
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    assert failed["stop_reason"] == "consecutive_failure_threshold_reached"
    assert failed["runtime_activity"]["publication_count"] == 0
    assert failed["runtime_activity"]["triage_count"] == 0


def test_loop_stale_readiness_deadman_and_safe_signal_stop_before_components(tmp_path: Path) -> None:
    stale_fixture, stale_config, _bootstrap = _bootstrap_accepted(
        tmp_path / "stale"
    )
    prior = p138_api.run_p138_supervisor_loop_for_evaluation(
        base_path=stale_fixture.root,
        config=stale_config,
        p136_runtime=stale_fixture.p136_runtime,
        publisher_inputs=stale_fixture.publisher_inputs,
        now_values=("2026-07-13T00:10:04Z",),
        monotonic=lambda: 1.0,
        sleep=lambda _: None,
    )
    assert prior["cycles_completed"] == 1
    stale = p138_api.run_p138_supervisor_loop_for_evaluation(
        base_path=stale_fixture.root,
        config=stale_config,
        p136_runtime=stale_fixture.p136_runtime,
        publisher_inputs=stale_fixture.publisher_inputs,
        now_values=("2026-07-15T00:00:04Z",),
        monotonic=lambda: 2.0,
        sleep=lambda _: None,
    )
    assert stale["stop_reason"] in {"readiness_stale", "deadman_stale"}
    assert stale["cycles_completed"] == 0

    signal_fixture, signal_config, _bootstrap = _bootstrap_accepted(
        tmp_path / "signal"
    )
    controller = P138StopController()
    controller.handle_signal(signal.SIGTERM, None)
    stopped = p138_api.run_p138_supervisor_loop_for_evaluation(
        base_path=signal_fixture.root,
        config=signal_config,
        p136_runtime=signal_fixture.p136_runtime,
        publisher_inputs=signal_fixture.publisher_inputs,
        now_values=("2026-07-13T00:10:04Z",),
        stop_controller=controller,
        monotonic=lambda: 1.0,
        sleep=lambda _: None,
    )
    assert stopped["stop_reason"] == "sigterm"
    assert stopped["cycles_completed"] == 0
    assert stopped["forbidden_authority"]["signal_count"] == 0


def test_production_loop_rejects_clock_and_sleep_injection_surface(tmp_path: Path) -> None:
    fixture, config, _bootstrap = _bootstrap_accepted(tmp_path)
    called = False

    def injected_clock() -> float:
        nonlocal called
        called = True
        return 0.0

    with pytest.raises(TypeError, match="unexpected keyword argument 'monotonic'"):
        cast(Any, p138_api.run_p138_supervisor_loop)(
            base_path=fixture.root,
            config=config,
            p136_runtime=fixture.p136_runtime,
            publisher_inputs=fixture.publisher_inputs,
            monotonic=injected_clock,
            sleep=lambda _seconds: None,
        )
    assert called is False


def test_loop_heartbeat_interval_and_existing_ledger_binding(tmp_path: Path) -> None:
    fixture = build_p138_fixture(
        tmp_path,
        publish_genesis=True,
        accept_genesis=True,
        index_receipts=5,
    )
    config_input = deepcopy(fixture.config_input)
    config_input["limits"].update(
        {
            "max_supervisor_cycles": 3,
            "poll_interval_ms": 1,
            "heartbeat_interval_ms": 100,
        }
    )
    config = build_observation_triage_supervisor_config(config_input)
    bootstrap = _run_once(fixture, config)
    assert bootstrap["status"] == "ok", bootstrap
    ticks = iter([0.0, 0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06])
    result = p138_api.run_p138_supervisor_loop_for_evaluation(
        base_path=fixture.root,
        config=config,
        p136_runtime=fixture.p136_runtime,
        publisher_inputs=fixture.publisher_inputs,
        now_values=(
            "2026-07-13T00:10:04Z",
            "2026-07-13T00:10:05Z",
            "2026-07-13T00:10:06Z",
        ),
        monotonic=lambda: next(ticks),
        sleep=lambda _seconds: None,
    )
    assert result["cycles_completed"] == 3
    assert result["runtime_activity"]["heartbeat_write_count"] == 2
    assert result["runtime_activity"]["readiness_write_count"] == 3
    heartbeat = _read_json(fixture.root, config["heartbeat_path"])
    assert heartbeat["last_valid_ledger_hash"] == result["last_result"]["ledger"]["ledger_hash"]

    controller = P138StopController()
    controller.handle_signal(signal.SIGTERM, None)
    stopped = p138_api.run_p138_supervisor_loop_for_evaluation(
        base_path=fixture.root,
        config=config,
        p136_runtime=fixture.p136_runtime,
        publisher_inputs=fixture.publisher_inputs,
        now_values=("2026-07-13T00:10:07Z",),
        stop_controller=controller,
        monotonic=lambda: 1.0,
        sleep=lambda _seconds: None,
    )
    assert stopped["termination"]["last_valid_ledger_hash"] == result["last_result"]["ledger"]["ledger_hash"]


def test_runtime_rejects_symlink_parent_before_component_calls(tmp_path: Path) -> None:
    fixture, config = _config(tmp_path, publish_genesis=False)
    outside = tmp_path / "outside"
    outside.mkdir()
    os.symlink(outside, fixture.root / "p138")
    result = _run_once(fixture, config)
    assert result["status"] == "failed_closed"
    assert result["expected_error"] == "runtime_path_symlink_forbidden"
    assert result["component_calls"] == []
