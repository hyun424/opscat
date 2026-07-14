from __future__ import annotations

import fcntl
import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p136_incremental_observer import build_incremental_observer_config, observe_one_cycle
from tests.fixtures.p136.builders import (
    ActivityProbe,
    authority_bundle,
    canonical_bytes,
    config_input,
    independent_review_artifact,
    limits,
    provider_index_entries,
    release_evidence,
    runtime_inputs,
)


def _contracts() -> Any:
    try:
        from app.services import p137_contracts
    except ModuleNotFoundError as exc:
        pytest.fail(f"missing P137 contracts module: {exc}")
    return p137_contracts


def _handoff() -> Any:
    try:
        from app.services import p137_p136_handoff
    except ModuleNotFoundError as exc:
        pytest.fail(f"missing P137 handoff module: {exc}")
    return p137_p136_handoff


def _bind_runtime(tmp_path: Path) -> dict[str, Any]:
    authority = authority_bundle(index_receipts=2, segment_receipts=5)
    cfg_input = config_input(
        tmp_path,
        authority,
        limits={**limits(), "max_journal_bytes": 1_000_000, "max_promotion_bytes": 1_000_000},
    )
    runtime = runtime_inputs(tmp_path, authority=authority, config=cfg_input, probe=ActivityProbe())
    config = build_incremental_observer_config(runtime["config"])
    checkpoint = deepcopy(runtime["checkpoint"])
    checkpoint["config_hash"] = config["config_hash"]
    checkpoint["checkpoint_hash"] = stable_hash({key: value for key, value in checkpoint.items() if key != "checkpoint_hash"})
    runtime["config"] = config
    runtime["checkpoint"] = checkpoint
    entries = provider_index_entries(authority["segment_receipts"])[:2]
    index_path = Path(runtime["base_path"]) / config["index_path"]
    index_path.write_bytes(b"".join(canonical_bytes(entry) + b"\n" for entry in entries))
    runtime["provider_entries"] = {entry["entry_hash"]: entry for entry in entries}
    return runtime


def _published(tmp_path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    contracts = _contracts()
    handoff = _handoff()
    runtime = _bind_runtime(tmp_path)
    observed = observe_one_cycle(runtime)
    bundle = handoff.publish_p136_handoff_bundle(
        base_path=Path(runtime["base_path"]),
        state_path="state/p137-publisher.json",
        intent_path="state/p137-publisher-intent.json",
        fixed_handoff_path=contracts.FIXED_P136_HANDOFF_PATH,
        p136_config=runtime["config"],
        p136_runtime_authority=runtime["authority"],
        now=runtime["now"],
        p136_checkpoint=observed["advanced_checkpoint"],
        canonical_entry_map=runtime["provider_entries"],
        promotion_records=observed["promotion_records"],
        p136_independent_review=independent_review_artifact(),
        p136_release_evidence=release_evidence(status=contracts.P136_QUALIFIED_RELEASE_STATUS),
        created_at="2026-07-14T00:00:01Z",
    )
    p137_limits = {key: index + 1 for index, key in enumerate(contracts.LIMIT_KEYS)}
    p137_limits.update(
        {
            "max_promotions_per_cycle": 128,
            "max_records_per_cycle": 256,
            "max_incidents_open": 64,
            "max_correlation_window_ms": 900_000,
            "max_incident_duration_ms": 86_400_000,
            "max_hypotheses_per_incident": 64,
            "max_support_edges_per_hypothesis": 64,
            "max_contradiction_edges_per_hypothesis": 64,
            "max_missing_evidence_items_per_hypothesis": 64,
            "max_evidence_requests_per_incident": 8,
            "max_request_input_records": 256,
            "max_request_output_records": 64,
            "max_request_output_bytes": 65_536,
            "max_ledger_records": 4_096,
            "max_cycle_wall_ms": 1_000,
            "max_agent_wall_ms": 10_000,
            "max_cpu_ms": 1_000,
            "max_peak_memory_bytes": 16_777_216,
        }
    )
    config = contracts.build_triage_agent_config(
        {
            "agent_id": "p137-triage-agent",
            "config_version": 1,
            "created_at": "2026-07-14T00:00:00Z",
            "base_dir_ref_hash": stable_hash({"path": "p137"}),
            "state_root_ref_hash": stable_hash({"path": "p137/state"}),
            "handoff_root_ref_hash": stable_hash({"path": "p137/handoff"}),
            "p136_handoff_bundle_path": contracts.FIXED_P136_HANDOFF_PATH,
            "p136_handoff_chain_root_hash": bundle["handoff_chain_root_hash"],
            "checkpoint_path": "p137-state/checkpoint.json",
            "lease_path": "p137-state/p137.lock",
            "journal_dir": "p137-state/journal",
            "incident_dir": "p137-state/incidents",
            "hypothesis_dir": "p137-state/hypotheses",
            "request_dir": "p137-state/requests",
            "classification_dir": "p137-state/classifications",
            "heartbeat_path": "p137-state/heartbeat.json",
            "readiness_path": "p137-state/readiness.json",
            "termination_dir": "p137-state/terminations",
            "ledger_path": "p137-state/ledger.json",
            "validated_p136_release_status": contracts.P136_QUALIFIED_RELEASE_STATUS,
            "allowed_request_catalog": list(contracts.ALLOWED_REQUEST_CATALOG),
            "correlation_policy": contracts.build_correlation_policy(),
            "ranking_policy": contracts.build_ranking_policy(),
            "classification_policy": contracts.build_classification_policy(),
            "continuous_mode": contracts.build_continuous_mode(
                enabled=False,
                max_cycles=p137_limits["max_cycles"],
                poll_interval_ms=p137_limits["poll_interval_ms"],
                heartbeat_interval_ms=p137_limits["heartbeat_interval_ms"],
                readiness_path="p137-state/readiness.json",
                readiness_stale_after_ms=p137_limits["readiness_stale_after_ms"],
                handoff_version_stale_after_ms=p137_limits["handoff_version_stale_after_ms"],
            ),
            "limits": p137_limits,
            "forbidden_authority": contracts.zero_forbidden_authority(),
        }
    )
    return runtime, bundle, config


def test_real_p136_handoff_runs_through_local_triage_and_commits_terminal_ledger(tmp_path: Path) -> None:
    from app.services.p137_runtime import run_p137_runtime_once

    runtime, bundle, config = _published(tmp_path)
    result = run_p137_runtime_once(base_path=Path(runtime["base_path"]), config=config)

    assert result["status"] == "ok"
    assert result["classification"] in {"confirmed_incident", "insufficient_evidence", "benign_anomaly"}
    assert result["runtime_activity"]["p136_validator_invocation_count"] == 2 + len(bundle["promotion_map"])
    expected_atoms = sum(item["promotion"]["p135_normalized_bundle"]["record_count"] for item in bundle["promotion_map"].values())
    assert result["runtime_activity"]["evidence_atom_count"] == expected_atoms
    assert len(result["incidents"]) == len(result["classifications"])
    assert result["checkpoint"]["last_accepted_ledger_hash"] == result["ledger"]["ledger_hash"]
    assert result["authority_counters"] == _contracts().zero_forbidden_authority()


def test_real_validator_accepts_next_bundle_against_exact_p137_checkpoint(tmp_path: Path) -> None:
    from app.services.p137_runtime import run_p137_runtime_once

    runtime, first_bundle, config = _published(tmp_path)
    base_path = Path(runtime["base_path"])
    first = run_p137_runtime_once(base_path=base_path, config=config)
    assert first["status"] == "ok"

    second_bundle = deepcopy(first_bundle)
    second_bundle["bundle_sequence"] = 2
    second_bundle["previous_bundle_hash"] = first_bundle["bundle_hash"]
    second_bundle["created_at"] = "2026-07-14T00:00:02Z"
    second_bundle["bundle_hash"] = stable_hash(
        {key: value for key, value in second_bundle.items() if key != "bundle_hash"}
    )
    handoff_path = base_path / config["p136_handoff_bundle_path"]
    handoff_path.write_bytes(_handoff().canonical_json_bytes(second_bundle) + b"\n")

    second = run_p137_runtime_once(base_path=base_path, config=config)

    assert second["status"] == "ok"
    assert second["checkpoint"]["last_accepted_bundle_sequence"] == 2
    assert second["checkpoint"]["last_accepted_bundle_hash"] == second_bundle["bundle_hash"]
    assert second["checkpoint"]["last_accepted_checkpoint_hash"] == first["checkpoint"]["checkpoint_hash"]


def test_publisher_genesis_persists_root_writes_fixed_path_and_next_publish_chains_previous_hash(tmp_path: Path) -> None:
    contracts = _contracts()
    handoff = _handoff()
    runtime, first, _config = _published(tmp_path)
    first_path = Path(runtime["base_path"]) / contracts.FIXED_P136_HANDOFF_PATH
    state_path = Path(runtime["base_path"]) / "state/p137-publisher.json"

    assert first["bundle_sequence"] == 1
    assert first["previous_bundle_hash"] is None
    assert first["fixed_handoff_path"] == contracts.FIXED_P136_HANDOFF_PATH
    assert first_path.read_bytes() == handoff.canonical_json_bytes(first) + b"\n"
    state = json.loads(state_path.read_text())
    assert state["handoff_chain_root_hash"] == first["handoff_chain_root_hash"]
    assert state["last_bundle_hash"] == first["bundle_hash"]

    second = handoff.publish_p136_handoff_bundle(
        base_path=Path(runtime["base_path"]),
        state_path="state/p137-publisher.json",
        intent_path="state/p137-publisher-intent.json",
        fixed_handoff_path=contracts.FIXED_P136_HANDOFF_PATH,
        p136_config=runtime["config"],
        p136_runtime_authority=runtime["authority"],
        now=runtime["now"],
        p136_checkpoint=first["p136_checkpoint"],
        canonical_entry_map={key: item["entry"] for key, item in first["canonical_entry_map"].items()},
        promotion_records=[item["promotion"] for item in first["promotion_map"].values()],
        p136_independent_review=first["p136_independent_review"],
        p136_release_evidence=first["p136_release_evidence"],
        created_at="2026-07-14T00:00:02Z",
    )

    assert second["bundle_sequence"] == 2
    assert second["previous_bundle_hash"] == first["bundle_hash"]
    assert second["handoff_chain_root_hash"] == first["handoff_chain_root_hash"]


def test_publisher_crash_recovery_commits_unlinks_intent_and_allows_next_publication(tmp_path: Path) -> None:
    handoff = _handoff()
    runtime = _bind_runtime(tmp_path)
    observed = observe_one_cycle(runtime)
    kwargs = {
        "base_path": Path(runtime["base_path"]),
        "state_path": "state/p137-publisher.json",
        "intent_path": "state/p137-publisher-intent.json",
        "fixed_handoff_path": _contracts().FIXED_P136_HANDOFF_PATH,
        "p136_config": runtime["config"],
        "p136_runtime_authority": runtime["authority"],
        "now": runtime["now"],
        "p136_checkpoint": observed["advanced_checkpoint"],
        "canonical_entry_map": runtime["provider_entries"],
        "promotion_records": observed["promotion_records"],
        "p136_independent_review": independent_review_artifact(),
        "p136_release_evidence": release_evidence(),
        "created_at": "2026-07-14T00:00:01Z",
    }

    def crash_after_intent(phase: str) -> None:
        if phase == "publisher_intent_durable":
            raise handoff.P137HandoffError("publisher_crash_after_intent")

    with pytest.raises(handoff.P137HandoffError, match="publisher_crash_after_intent"):
        handoff.publish_p136_handoff_bundle(**kwargs, evaluator_crash_injector=crash_after_intent)
    changed = dict(kwargs)
    changed["created_at"] = "2026-07-14T00:00:09Z"
    with pytest.raises(handoff.P137HandoffError, match="conflicting_pending_handoff_intent"):
        handoff.publish_p136_handoff_bundle(**changed)

    recovered = handoff.publish_p136_handoff_bundle(**kwargs)
    intent_path = Path(runtime["base_path"]) / "state/p137-publisher-intent.json"

    assert not intent_path.exists()
    assert json.loads((Path(runtime["base_path"]) / _contracts().FIXED_P136_HANDOFF_PATH).read_text()) == recovered

    second = handoff.publish_p136_handoff_bundle(**changed)

    assert second["bundle_sequence"] == 2
    assert second["previous_bundle_hash"] == recovered["bundle_hash"]
    assert second["created_at"] == "2026-07-14T00:00:09Z"


@pytest.mark.parametrize(
    ("crash_phase", "error_label"),
    [
        ("publisher_intent_durable", "publisher_crash_after_intent"),
        ("publisher_fixed_replaced", "publisher_crash_after_fixed_replacement"),
        ("publisher_state_replaced", "publisher_crash_after_state_replacement"),
    ],
)
def test_publisher_whole_operation_lease_recovers_every_split_commit_exactly_once(
    tmp_path: Path,
    crash_phase: str,
    error_label: str,
) -> None:
    handoff = _handoff()
    runtime, first, _config = _published(tmp_path)
    base_path = Path(runtime["base_path"])
    state_path = base_path / "state/p137-publisher.json"
    intent_path = base_path / "state/p137-publisher-intent.json"
    fixed_path = base_path / _contracts().FIXED_P136_HANDOFF_PATH
    prior_state = state_path.read_bytes()
    prior_fixed = fixed_path.read_bytes()
    kwargs = {
        "base_path": base_path,
        "state_path": "state/p137-publisher.json",
        "intent_path": "state/p137-publisher-intent.json",
        "lease_path": "state/p137-publisher.lock",
        "fixed_handoff_path": _contracts().FIXED_P136_HANDOFF_PATH,
        "p136_config": runtime["config"],
        "p136_runtime_authority": runtime["authority"],
        "now": runtime["now"],
        "p136_checkpoint": first["p136_checkpoint"],
        "canonical_entry_map": {
            key: item["entry"] for key, item in first["canonical_entry_map"].items()
        },
        "promotion_records": [item["promotion"] for item in first["promotion_map"].values()],
        "p136_independent_review": first["p136_independent_review"],
        "p136_release_evidence": first["p136_release_evidence"],
        "created_at": "2026-07-14T00:00:02Z",
    }

    def crash_at(phase: str) -> None:
        if phase == crash_phase:
            raise handoff.P137HandoffError(error_label)

    with pytest.raises(handoff.P137HandoffError, match=error_label):
        handoff.publish_p136_handoff_bundle(**kwargs, evaluator_crash_injector=crash_at)
    pending = json.loads(intent_path.read_text())
    pending_bundle = pending["bundle"]

    if crash_phase == "publisher_intent_durable":
        assert state_path.read_bytes() == prior_state
        assert fixed_path.read_bytes() == prior_fixed
    elif crash_phase == "publisher_fixed_replaced":
        assert state_path.read_bytes() == prior_state
        assert json.loads(fixed_path.read_text()) == pending_bundle
    else:
        assert json.loads(state_path.read_text())["last_bundle_hash"] == pending_bundle["bundle_hash"]
        assert json.loads(fixed_path.read_text()) == pending_bundle

    recovered = handoff.publish_p136_handoff_bundle(**kwargs)

    assert recovered == pending_bundle
    assert recovered["bundle_sequence"] == first["bundle_sequence"] + 1
    assert recovered["previous_bundle_hash"] == first["bundle_hash"]
    assert not intent_path.exists()
    assert json.loads(state_path.read_text())["last_bundle_hash"] == recovered["bundle_hash"]
    assert json.loads(fixed_path.read_text()) == recovered


def test_publisher_lease_conflict_precedes_reads_and_path_or_tuple_mismatch_fails_closed(
    tmp_path: Path,
) -> None:
    handoff = _handoff()
    runtime, first, _config = _published(tmp_path)
    base_path = Path(runtime["base_path"])
    lease_path = base_path / "state/p137-publisher.lock"
    state_path = base_path / "state/p137-publisher.json"
    fixed_path = base_path / _contracts().FIXED_P136_HANDOFF_PATH
    state_before = state_path.read_bytes()
    fixed_before = fixed_path.read_bytes()
    kwargs = {
        "base_path": base_path,
        "state_path": "state/p137-publisher.json",
        "intent_path": "state/p137-publisher-intent.json",
        "lease_path": "state/p137-publisher.lock",
        "fixed_handoff_path": _contracts().FIXED_P136_HANDOFF_PATH,
        "p136_config": runtime["config"],
        "p136_runtime_authority": runtime["authority"],
        "now": runtime["now"],
        "p136_checkpoint": first["p136_checkpoint"],
        "canonical_entry_map": {
            key: item["entry"] for key, item in first["canonical_entry_map"].items()
        },
        "promotion_records": [item["promotion"] for item in first["promotion_map"].values()],
        "p136_independent_review": first["p136_independent_review"],
        "p136_release_evidence": first["p136_release_evidence"],
        "created_at": "2026-07-14T00:00:02Z",
    }
    lease_path.touch()
    with lease_path.open("a+") as held:
        fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(handoff.P137HandoffError, match="publisher_lease_unavailable"):
            handoff.publish_p136_handoff_bundle(**kwargs)
    assert state_path.read_bytes() == state_before
    assert fixed_path.read_bytes() == fixed_before

    with pytest.raises(handoff.P137HandoffError, match="publisher_paths_overlap"):
        handoff.publish_p136_handoff_bundle(
            **{**kwargs, "lease_path": kwargs["state_path"]}
        )
    assert state_path.read_bytes() == state_before
    assert fixed_path.read_bytes() == fixed_before


@pytest.mark.parametrize(
    ("symlink_parent", "paths"),
    [
        (
            "publisher-state",
            {
                "state_path": "publisher-state/state.json",
                "intent_path": "publisher-intent/intent.json",
                "lease_path": "publisher-lease/publisher.lock",
            },
        ),
        (
            "publisher-intent",
            {
                "state_path": "publisher-state/state.json",
                "intent_path": "publisher-intent/intent.json",
                "lease_path": "publisher-lease/publisher.lock",
            },
        ),
        (
            "publisher-lease",
            {
                "state_path": "publisher-state/state.json",
                "intent_path": "publisher-intent/intent.json",
                "lease_path": "publisher-lease/publisher.lock",
            },
        ),
        (
            "handoff",
            {
                "state_path": "publisher-state/state.json",
                "intent_path": "publisher-intent/intent.json",
                "lease_path": "publisher-lease/publisher.lock",
            },
        ),
    ],
)
def test_publisher_rejects_symlinked_parent_without_outside_mutation(
    tmp_path: Path,
    symlink_parent: str,
    paths: dict[str, str],
) -> None:
    handoff = _handoff()
    runtime = _bind_runtime(tmp_path)
    observed = observe_one_cycle(runtime)
    base_path = Path(runtime["base_path"])
    outside = tmp_path / f"outside-{symlink_parent}"
    outside.mkdir()
    os.symlink(outside, base_path / symlink_parent, target_is_directory=True)

    with pytest.raises(handoff.P137HandoffError, match="publisher_parent_symlink_or_invalid"):
        handoff.publish_p136_handoff_bundle(
            base_path=base_path,
            fixed_handoff_path=_contracts().FIXED_P136_HANDOFF_PATH,
            p136_config=runtime["config"],
            p136_runtime_authority=runtime["authority"],
            now=runtime["now"],
            p136_checkpoint=observed["advanced_checkpoint"],
            canonical_entry_map=runtime["provider_entries"],
            promotion_records=observed["promotion_records"],
            p136_independent_review=independent_review_artifact(),
            p136_release_evidence=release_evidence(),
            created_at="2026-07-14T00:00:01Z",
            **paths,
        )

    assert list(outside.iterdir()) == []


def test_publisher_recovery_rejects_forked_fixed_bytes_and_preserves_last_valid_state(
    tmp_path: Path,
) -> None:
    handoff = _handoff()
    runtime, first, _config = _published(tmp_path)
    base_path = Path(runtime["base_path"])
    state_path = base_path / "state/p137-publisher.json"
    fixed_path = base_path / _contracts().FIXED_P136_HANDOFF_PATH
    kwargs = {
        "base_path": base_path,
        "state_path": "state/p137-publisher.json",
        "intent_path": "state/p137-publisher-intent.json",
        "lease_path": "state/p137-publisher.lock",
        "fixed_handoff_path": _contracts().FIXED_P136_HANDOFF_PATH,
        "p136_config": runtime["config"],
        "p136_runtime_authority": runtime["authority"],
        "now": runtime["now"],
        "p136_checkpoint": first["p136_checkpoint"],
        "canonical_entry_map": {
            key: item["entry"] for key, item in first["canonical_entry_map"].items()
        },
        "promotion_records": [item["promotion"] for item in first["promotion_map"].values()],
        "p136_independent_review": first["p136_independent_review"],
        "p136_release_evidence": first["p136_release_evidence"],
        "created_at": "2026-07-14T00:00:02Z",
    }

    def crash_after_fixed(phase: str) -> None:
        if phase == "publisher_fixed_replaced":
            raise handoff.P137HandoffError("publisher_crash_after_fixed_replacement")

    with pytest.raises(handoff.P137HandoffError, match="publisher_crash_after_fixed_replacement"):
        handoff.publish_p136_handoff_bundle(**kwargs, evaluator_crash_injector=crash_after_fixed)
    state_before = state_path.read_bytes()
    forked = json.loads(fixed_path.read_text())
    forked["bundle_sequence"] += 1
    fixed_path.write_text(json.dumps(forked, sort_keys=True, separators=(",", ":")) + "\n")
    forked_before = fixed_path.read_bytes()

    with pytest.raises(handoff.P137HandoffError, match="publisher_bundle_hash_invalid"):
        handoff.publish_p136_handoff_bundle(**kwargs)
    assert state_path.read_bytes() == state_before
    assert fixed_path.read_bytes() == forked_before


def test_publisher_rejects_noncanonical_persisted_predecessor_bytes(
    tmp_path: Path,
) -> None:
    handoff = _handoff()
    runtime, first, _config = _published(tmp_path)
    base_path = Path(runtime["base_path"])
    fixed_path = base_path / _contracts().FIXED_P136_HANDOFF_PATH
    fixed_path.write_text(json.dumps(first, indent=2, sort_keys=True) + "\n")

    with pytest.raises(
        handoff.P137HandoffError,
        match="noncanonical_publisher_json_bytes",
    ):
        handoff.publish_p136_handoff_bundle(
            base_path=base_path,
            state_path="state/p137-publisher.json",
            intent_path="state/p137-publisher-intent.json",
            lease_path="state/p137-publisher.lock",
            fixed_handoff_path=_contracts().FIXED_P136_HANDOFF_PATH,
            p136_config=runtime["config"],
            p136_runtime_authority=runtime["authority"],
            now=runtime["now"],
            p136_checkpoint=first["p136_checkpoint"],
            canonical_entry_map={
                key: item["entry"]
                for key, item in first["canonical_entry_map"].items()
            },
            promotion_records=[
                item["promotion"] for item in first["promotion_map"].values()
            ],
            p136_independent_review=first["p136_independent_review"],
            p136_release_evidence=first["p136_release_evidence"],
            created_at="2026-07-14T00:00:02Z",
        )


def test_publisher_rejects_tampered_state_before_deriving_next_sequence(tmp_path: Path) -> None:
    handoff = _handoff()
    runtime, first, _config = _published(tmp_path)
    base_path = Path(runtime["base_path"])
    state_path = base_path / "state/p137-publisher.json"
    state = json.loads(state_path.read_text())
    state["last_bundle_sequence"] = 40
    state_path.write_text(json.dumps(state, sort_keys=True, separators=(",", ":")) + "\n")
    fixed_before = (base_path / _contracts().FIXED_P136_HANDOFF_PATH).read_bytes()

    with pytest.raises(handoff.P137HandoffError, match="publisher_state_hash_invalid"):
        handoff.publish_p136_handoff_bundle(
            base_path=base_path,
            state_path="state/p137-publisher.json",
            intent_path="state/p137-publisher-intent.json",
            fixed_handoff_path=_contracts().FIXED_P136_HANDOFF_PATH,
            p136_config=runtime["config"],
            p136_runtime_authority=runtime["authority"],
            now=runtime["now"],
            p136_checkpoint=first["p136_checkpoint"],
            canonical_entry_map={key: item["entry"] for key, item in first["canonical_entry_map"].items()},
            promotion_records=[item["promotion"] for item in first["promotion_map"].values()],
            p136_independent_review=first["p136_independent_review"],
            p136_release_evidence=first["p136_release_evidence"],
            created_at="2026-07-14T00:00:02Z",
        )

    assert (base_path / _contracts().FIXED_P136_HANDOFF_PATH).read_bytes() == fixed_before
    assert not (base_path / "state/p137-publisher-intent.json").exists()


def test_publisher_rejects_tampered_pending_intent_before_recovery_writes(tmp_path: Path) -> None:
    handoff = _handoff()
    runtime = _bind_runtime(tmp_path)
    observed = observe_one_cycle(runtime)
    base_path = Path(runtime["base_path"])
    kwargs = {
        "base_path": base_path,
        "state_path": "state/p137-publisher.json",
        "intent_path": "state/p137-publisher-intent.json",
        "fixed_handoff_path": _contracts().FIXED_P136_HANDOFF_PATH,
        "p136_config": runtime["config"],
        "p136_runtime_authority": runtime["authority"],
        "now": runtime["now"],
        "p136_checkpoint": observed["advanced_checkpoint"],
        "canonical_entry_map": runtime["provider_entries"],
        "promotion_records": observed["promotion_records"],
        "p136_independent_review": independent_review_artifact(),
        "p136_release_evidence": release_evidence(),
        "created_at": "2026-07-14T00:00:01Z",
    }
    with pytest.raises(handoff.P137HandoffError, match="publisher_crash_after_intent"):
        handoff.publish_p136_handoff_bundle(**kwargs, crash_after_intent=True)
    intent_path = base_path / "state/p137-publisher-intent.json"
    intent = json.loads(intent_path.read_text())
    intent["bundle_sequence"] = 40
    intent_path.write_text(json.dumps(intent, sort_keys=True, separators=(",", ":")) + "\n")

    with pytest.raises(handoff.P137HandoffError, match="publisher_intent_hash_invalid"):
        handoff.publish_p136_handoff_bundle(**kwargs)

    assert not (base_path / _contracts().FIXED_P136_HANDOFF_PATH).exists()
    assert not (base_path / "state/p137-publisher.json").exists()


def test_publisher_rejects_malformed_state_and_intent_fields_before_writes(tmp_path: Path) -> None:
    handoff = _handoff()
    contracts = _contracts()
    runtime, first, _config = _published(tmp_path)
    base_path = Path(runtime["base_path"])
    fixed_path = base_path / contracts.FIXED_P136_HANDOFF_PATH
    state_path = base_path / "state/p137-publisher.json"
    intent_path = base_path / "state/p137-publisher-intent.json"
    fixed_before = fixed_path.read_bytes()
    state_before = state_path.read_bytes()
    publish_kwargs = {
        "base_path": base_path,
        "state_path": "state/p137-publisher.json",
        "intent_path": "state/p137-publisher-intent.json",
        "fixed_handoff_path": contracts.FIXED_P136_HANDOFF_PATH,
        "p136_config": runtime["config"],
        "p136_runtime_authority": runtime["authority"],
        "now": runtime["now"],
        "p136_checkpoint": first["p136_checkpoint"],
        "canonical_entry_map": {key: item["entry"] for key, item in first["canonical_entry_map"].items()},
        "promotion_records": [item["promotion"] for item in first["promotion_map"].values()],
        "p136_independent_review": first["p136_independent_review"],
        "p136_release_evidence": first["p136_release_evidence"],
        "created_at": "2026-07-14T00:00:02Z",
    }

    malformed_state = json.loads(state_before)
    malformed_state["schema_version"] = "p136.p137_handoff_publisher_state.v0"
    malformed_state["state_hash"] = stable_hash(
        {key: value for key, value in malformed_state.items() if key != "state_hash"}
    )
    state_path.write_bytes(handoff.canonical_json_bytes(malformed_state) + b"\n")
    with pytest.raises(handoff.P137HandoffError, match="invalid_publisher_state_fields"):
        handoff.publish_p136_handoff_bundle(**publish_kwargs)

    state_path.write_bytes(state_before)
    malformed_intent = {
        "schema_version": handoff.PUBLISHER_INTENT_SCHEMA_VERSION,
        "state_hash": json.loads(state_before)["state_hash"],
        "fixed_handoff_path": contracts.FIXED_P136_HANDOFF_PATH,
        "bundle_sequence": 2,
        "previous_bundle_hash": first["bundle_hash"],
        "bundle_hash": first["bundle_hash"],
        "fsync": {"file": True, "parent_directory": True},
    }
    malformed_intent["intent_hash"] = stable_hash(
        {key: value for key, value in malformed_intent.items() if key != "intent_hash"}
    )
    intent_path.write_bytes(handoff.canonical_json_bytes(malformed_intent) + b"\n")
    with pytest.raises(handoff.P137HandoffError, match="invalid_publisher_intent_fields"):
        handoff.publish_p136_handoff_bundle(**publish_kwargs)

    assert fixed_path.read_bytes() == fixed_before
    assert state_path.read_bytes() == state_before


def test_validate_handoff_invokes_current_p136_validators_and_converts_atoms_without_rereads(tmp_path: Path) -> None:
    handoff = _handoff()
    runtime, bundle, config = _published(tmp_path)
    probe = runtime["probe"]
    before = list(probe.events)

    result = handoff.validate_p136_handoff_bundle(handoff.canonical_json_bytes(bundle), config=config)

    assert result["bundle_hash"] == bundle["bundle_hash"]
    expected_atoms = sum(item["promotion"]["p135_normalized_bundle"]["record_count"] for item in bundle["promotion_map"].values())
    assert len(result["evidence_atoms"]) == expected_atoms
    assert {atom["evidence_state"] for atom in result["evidence_atoms"]} == {"promoted_success"}
    assert all(set(atom) == _contracts().EVIDENCE_ATOM_FIELDS for atom in result["evidence_atoms"])
    assert probe.events == before


def test_validation_rejects_two_field_fake_p136_release_evidence(tmp_path: Path) -> None:
    handoff = _handoff()
    contracts = _contracts()
    _runtime, bundle, config = _published(tmp_path)
    tampered = deepcopy(bundle)
    fake_release = {"status": contracts.P136_QUALIFIED_RELEASE_STATUS}
    fake_release["evidence_hash"] = stable_hash(fake_release)
    tampered["p136_release_evidence"] = fake_release
    tampered["p136_release_evidence_hash"] = fake_release["evidence_hash"]
    tampered["bundle_hash"] = stable_hash({key: value for key, value in tampered.items() if key != "bundle_hash"})

    with pytest.raises(handoff.P137HandoffError, match="release_evidence"):
        handoff.validate_p136_handoff_bundle(handoff.canonical_json_bytes(tampered), config=config)


def test_validation_rejects_two_field_fake_p136_independent_review_bound_to_release(tmp_path: Path) -> None:
    handoff = _handoff()
    _runtime, bundle, config = _published(tmp_path)
    tampered = deepcopy(bundle)
    fake_review = {"schema_version": "p136.independent_review.v1"}
    fake_review["independent_review_hash"] = stable_hash(fake_review)
    tampered["p136_independent_review"] = fake_review
    tampered["p136_independent_review_hash"] = fake_review["independent_review_hash"]
    tampered["p136_release_evidence"]["independent_review_hash"] = fake_review["independent_review_hash"]
    tampered["p136_release_evidence"]["evidence_hash"] = stable_hash(
        {key: value for key, value in tampered["p136_release_evidence"].items() if key != "evidence_hash"}
    )
    tampered["p136_release_evidence_hash"] = tampered["p136_release_evidence"]["evidence_hash"]
    tampered["bundle_hash"] = stable_hash({key: value for key, value in tampered.items() if key != "bundle_hash"})

    with pytest.raises(handoff.P137HandoffError, match="independent_review"):
        handoff.validate_p136_handoff_bundle(handoff.canonical_json_bytes(tampered), config=config)


@pytest.mark.parametrize(
    ("mutator", "error"),
    [
        (lambda b: b["p136_checkpoint"]["promotion_keys"].pop(next(iter(b["promotion_map"]))), "checkpoint_promotion_entry_missing"),
        (lambda b: b["p136_checkpoint"]["promotion_keys"].update({next(iter(b["promotion_map"])): {"forged": True}}), "checkpoint_promotion_value_mismatch"),
        (lambda b: next(iter(b["promotion_map"].values()))["promotion"].update({"promotion_key": stable_hash({"tamper": "nested"})}), "promotion_key_invalid"),
    ],
)
def test_validation_rejects_checkpoint_membership_and_nested_promotion_key_tamper(tmp_path: Path, mutator: Any, error: str) -> None:
    handoff = _handoff()
    _runtime, bundle, config = _published(tmp_path)
    tampered = deepcopy(bundle)
    mutator(tampered)
    tampered["bundle_hash"] = stable_hash({key: value for key, value in tampered.items() if key != "bundle_hash"})

    with pytest.raises(handoff.P137HandoffError, match=error):
        handoff.validate_p136_handoff_bundle(handoff.canonical_json_bytes(tampered), config=config)


def test_validation_rejects_noncanonical_authority_hex_and_segment_receipt_byte_tamper(tmp_path: Path) -> None:
    handoff = _handoff()
    _runtime, bundle, config = _published(tmp_path)
    uppercase = deepcopy(bundle)
    uppercase["p136_runtime_authority"]["contract_bytes"] = str(uppercase["p136_runtime_authority"]["contract_bytes"]).upper()
    uppercase["bundle_hash"] = stable_hash({key: value for key, value in uppercase.items() if key != "bundle_hash"})

    with pytest.raises(handoff.P137HandoffError, match="invalid_canonical_hex"):
        handoff.validate_p136_handoff_bundle(handoff.canonical_json_bytes(uppercase), config=config)

    segment_tamper = deepcopy(bundle)
    segment_tamper["p136_runtime_authority"]["segment_receipts"][0]["decision"] = "denied"
    segment_tamper["bundle_hash"] = stable_hash({key: value for key, value in segment_tamper.items() if key != "bundle_hash"})
    with pytest.raises(handoff.P137HandoffError, match="segment_receipt_bytes_mismatch"):
        handoff.validate_p136_handoff_bundle(handoff.canonical_json_bytes(segment_tamper), config=config)


def test_validation_rejects_rollback_fork_previous_hash_discontinuity_and_torn_fixed_path_bytes(tmp_path: Path) -> None:
    handoff = _handoff()
    _runtime, bundle, config = _published(tmp_path)
    accepted = {
        "last_accepted_bundle_sequence": 1,
        "last_accepted_bundle_hash": bundle["bundle_hash"],
    }

    assert handoff.validate_p136_handoff_bundle(
        handoff.canonical_json_bytes(bundle),
        config=config,
        p137_checkpoint=accepted,
    )["bundle_hash"] == bundle["bundle_hash"]

    rollback_checkpoint = {
        "last_accepted_bundle_sequence": 2,
        "last_accepted_bundle_hash": stable_hash({"accepted": "later"}),
    }
    with pytest.raises(handoff.P137HandoffError, match="p136_handoff_sequence_rollback"):
        handoff.validate_p136_handoff_bundle(
            handoff.canonical_json_bytes(bundle),
            config=config,
            p137_checkpoint=rollback_checkpoint,
        )

    fork = deepcopy(bundle)
    fork["bundle_sequence"] = 1
    fork["created_at"] = "2026-07-14T00:00:09Z"
    fork["bundle_hash"] = stable_hash({key: value for key, value in fork.items() if key != "bundle_hash"})
    with pytest.raises(handoff.P137HandoffError, match="p136_handoff_same_sequence_fork"):
        handoff.validate_p136_handoff_bundle(handoff.canonical_json_bytes(fork), config=config, p137_checkpoint=accepted)

    discontinuity = deepcopy(bundle)
    discontinuity["bundle_sequence"] = 2
    discontinuity["previous_bundle_hash"] = stable_hash({"wrong": "previous"})
    discontinuity["bundle_hash"] = stable_hash({key: value for key, value in discontinuity.items() if key != "bundle_hash"})
    with pytest.raises(handoff.P137HandoffError, match="p136_handoff_previous_hash_discontinuity"):
        handoff.validate_p136_handoff_bundle(handoff.canonical_json_bytes(discontinuity), config=config, p137_checkpoint=accepted)

    torn = handoff.canonical_json_bytes(bundle) + b" "
    with pytest.raises(handoff.P137HandoffError, match="noncanonical_handoff_bytes"):
        handoff.validate_p136_handoff_bundle(torn, config=config)
