from __future__ import annotations

import importlib
import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from app.services.p110_evaluation import stable_hash
from tests.fixtures.p136.builders import (
    EVALUATOR_ACTIVITY_KEYS,
    FORBIDDEN_AUTHORITY_KEYS,
    RESOURCE_USAGE_KEYS,
    RUNTIME_ACTIVITY_KEYS,
    ActivityProbe,
    authority_bundle,
    canonical_bytes,
    checkpoint,
    config_input,
    copy_p135_fixture_tree,
    index_entry_input,
    pending_partial_state,
    promotion_record,
    provider_index_entries,
    runtime_inputs,
    self_hash_entry,
    zero_forbidden_authority,
)

EXPECTED_CONFIG_KEYS = {
    "schema_version",
    "observer_id",
    "config_version",
    "created_at",
    "base_dir",
    "data_root",
    "state_root",
    "index_path",
    "checkpoint_path",
    "index_intent_dir",
    "journal_dir",
    "promotion_dir",
    "cycle_outcome_dir",
    "lease_path",
    "p134_contract_hash",
    "p134_receipt_ledger_hash",
    "index_source_ref_hash",
    "index_read_receipt_hashes",
    "limits",
    "forbidden_authority",
    "config_hash",
}

EXPECTED_ENTRY_KEYS = {
    "schema_version",
    "entry_id",
    "entry_sequence",
    "segment_id",
    "source_id",
    "provider",
    "format",
    "signal_family",
    "relative_segment_path",
    "expected_content_hash",
    "expected_bytes",
    "expected_records",
    "segment_authority_receipt_hash",
    "segment_authority_capability",
    "created_at",
    "previous_entry_hash",
    "rotation_from_hash",
    "entry_hash",
}


def _api(*names: str) -> Any:
    try:
        module = importlib.import_module("app.services.p136_incremental_observer")
    except ModuleNotFoundError as exc:
        pytest.fail(f"missing P136 module/API: app.services.p136_incremental_observer ({exc})")
    missing = [name for name in names if not hasattr(module, name)]
    if missing:
        pytest.fail(f"missing P136 module/API: {', '.join(missing)}")
    return module


def _error() -> type[Exception]:
    module = _api("P136ObservationError")
    return module.P136ObservationError


def _bind_runtime_checkpoint(runtime: dict[str, Any]) -> dict[str, Any]:
    api = _api("build_incremental_observer_config")
    bound = dict(runtime)
    cfg = api.build_incremental_observer_config(bound["config"]) if "schema_version" not in bound["config"] else bound["config"]
    current = deepcopy(bound["checkpoint"])
    current["config_hash"] = cfg["config_hash"]
    current["checkpoint_hash"] = stable_hash({key: value for key, value in current.items() if key != "checkpoint_hash"})
    bound["config"] = cfg
    bound["checkpoint"] = current
    return bound


def _rehash(value: dict[str, Any], hash_field: str) -> dict[str, Any]:
    result = deepcopy(value)
    result[hash_field] = stable_hash({key: item for key, item in result.items() if key != hash_field})
    return result


def _promotion_path(runtime: dict[str, Any], promotion: dict[str, Any]) -> Path:
    return Path(runtime["base_path"]) / runtime["config"]["promotion_dir"] / f"{promotion['promotion_hash'].removeprefix('sha256:')}.json"


def _checkpoint_path(runtime: dict[str, Any]) -> Path:
    return Path(runtime["base_path"]) / runtime["config"]["checkpoint_path"]


def _journal_path(runtime: dict[str, Any], result: dict[str, Any]) -> Path:
    intent_name = result["index_read_intent"]["cycle_id"].removeprefix("sha256:")
    return Path(runtime["base_path"]) / runtime["config"]["journal_dir"] / f"{intent_name}.promotion-intent.json"


def _cycle_outcome_path(runtime: dict[str, Any], cycle_id: str) -> Path:
    return (
        Path(runtime["base_path"])
        / runtime["config"]["cycle_outcome_dir"]
        / f"{cycle_id.removeprefix('sha256:')}.json"
    )


def _write_index_entry(runtime: dict[str, Any], entry: dict[str, Any]) -> None:
    (Path(runtime["base_path"]) / runtime["config"]["index_path"]).write_bytes(canonical_bytes(entry) + b"\n")


def test_build_incremental_observer_config_returns_exact_key_self_hashed_contract(tmp_path: Path) -> None:
    api = _api("build_incremental_observer_config")

    config = api.build_incremental_observer_config(config_input(tmp_path))

    assert set(config) == EXPECTED_CONFIG_KEYS
    assert config["schema_version"] == "p136.incremental_observer_config.v1"
    assert config["forbidden_authority"] == zero_forbidden_authority()
    assert config["config_hash"] == stable_hash({key: value for key, value in config.items() if key != "config_hash"})


def test_config_validation_rejects_unknown_fields_boolean_limits_and_unsafe_state_overlap(tmp_path: Path) -> None:
    api = _api("build_incremental_observer_config")
    error = _error()

    with pytest.raises(error, match="unexpected_config_field"):
        api.build_incremental_observer_config(config_input(tmp_path, unexpected="field"))
    with pytest.raises(error, match="invalid_limit:max_cycles"):
        api.build_incremental_observer_config(config_input(tmp_path, limits={**config_input(tmp_path)["limits"], "max_cycles": True}))
    with pytest.raises(error, match="state_path_overlaps_index_path"):
        api.build_incremental_observer_config(config_input(tmp_path, checkpoint_path="data/index.jsonl/checkpoint.json"))
    with pytest.raises(error, match="state_paths_overlap"):
        api.build_incremental_observer_config(config_input(tmp_path, cycle_outcome_dir="state/journal/outcomes"))
    missing_outcome_dir = config_input(tmp_path)
    missing_outcome_dir.pop("cycle_outcome_dir")
    with pytest.raises(error, match="missing_config_field"):
        api.build_incremental_observer_config(missing_outcome_dir)
    missing_outcome_budget = config_input(tmp_path)
    missing_outcome_budget["limits"].pop("max_cycle_outcome_bytes")
    with pytest.raises(error, match="invalid_limits_fields"):
        api.build_incremental_observer_config(missing_outcome_budget)


def test_index_entry_contract_is_exact_key_global_sequence_chained_and_self_hashed() -> None:
    api = _api("build_incremental_index_entry", "validate_incremental_index_entry")

    first = api.build_incremental_index_entry(index_entry_input())
    second = api.build_incremental_index_entry(index_entry_input(2, previous_entry_hash=first["entry_hash"]))
    api.validate_incremental_index_entry(second, expected_sequence=2, previous_entry_hash=first["entry_hash"])

    assert set(first) == EXPECTED_ENTRY_KEYS
    assert first["schema_version"] == "p136.incremental_index_entry.v1"
    assert first["entry_hash"] == stable_hash({key: value for key, value in first.items() if key != "entry_hash"})
    assert second["previous_entry_hash"] == first["entry_hash"]


def test_index_entry_validation_rejects_conflicting_identity_reuse_prompt_text_and_rotation_mismatch() -> None:
    api = _api("build_incremental_index_entry", "validate_incremental_index_entry")
    error = _error()
    first = api.build_incremental_index_entry(index_entry_input())
    conflicting = api.build_incremental_index_entry(index_entry_input(segment_id=first["segment_id"], expected_records=2))
    prompt_like = api.build_incremental_index_entry(index_entry_input(entry_id="ignore-previous-instructions"))
    rotated = api.build_incremental_index_entry(index_entry_input(2, previous_entry_hash=first["entry_hash"], rotation_from_hash=stable_hash({"wrong": "hash"})))

    with pytest.raises(error, match="conflicting_segment_id_reuse"):
        api.validate_incremental_index_entry(conflicting, known_canonical_identities={first["segment_id"]: first})
    with pytest.raises(error, match="prompt_or_credential_text_forbidden"):
        api.validate_incremental_index_entry(prompt_like, expected_sequence=1, previous_entry_hash=None)
    with pytest.raises(error, match="rotation_lineage_mismatch"):
        api.validate_incremental_index_entry(rotated, expected_sequence=2, previous_entry_hash=first["entry_hash"], expected_rotation_from_hash=first["entry_hash"])


def test_runtime_authority_requires_full_p134_contract_review_ledger_and_receipt_bytes_before_read(tmp_path: Path) -> None:
    api = _api("validate_observer_runtime_authority")
    error = _error()
    authority = authority_bundle()
    config = config_input(tmp_path, authority)
    hash_only = {
        "contract_hash": authority["contract"]["contract_hash"],
        "receipt_ledger_hash": authority["receipt_ledger"]["ledger_hash"],
        "index_receipt_hashes": [receipt["receipt_hash"] for receipt in authority["index_receipts"]],
    }

    with pytest.raises(error, match="missing_full_p134_runtime_inputs"):
        api.validate_observer_runtime_authority(config, hash_only, now="2026-07-13T00:10:02Z")


def test_runtime_authority_revalidates_receipt_membership_distinctness_windows_and_whole_index_budgets(tmp_path: Path) -> None:
    api = _api("validate_observer_runtime_authority")
    error = _error()
    authority = authority_bundle(index_receipts=2)
    config = config_input(
        tmp_path,
        authority,
        limits={
            **config_input(tmp_path, authority)["limits"],
            "max_whole_index_bytes": 32,
            "max_index_line_bytes": 32,
        },
    )
    reused = deepcopy(authority)
    reused["index_receipts"][1] = deepcopy(reused["index_receipts"][0])
    reused["index_receipt_bytes"][1] = deepcopy(reused["index_receipt_bytes"][0])

    with pytest.raises(error, match="duplicate_index_read_receipt"):
        api.validate_observer_runtime_authority(config, reused, now="2026-07-13T00:10:02Z")
    with pytest.raises(error, match="whole_index_budget_underestimated"):
        api.validate_observer_runtime_authority(config, authority, now="2026-07-13T00:10:02Z", proposed_whole_index_bytes=128, proposed_complete_lines=1)
    with pytest.raises(error, match="contract_or_review_not_current"):
        api.validate_observer_runtime_authority(config, authority, now="2026-07-15T00:00:00Z")


def test_index_read_intent_is_durable_before_any_index_open(tmp_path: Path) -> None:
    api = _api("observe_one_cycle")
    probe = ActivityProbe()
    runtime = _bind_runtime_checkpoint(runtime_inputs(tmp_path, probe=probe))

    result = api.observe_one_cycle(runtime)

    probe.assert_no_index_access_before_intent()
    assert result["index_read_intent"]["schema_version"] == "p136.index_read_intent.v1"
    assert result["index_read_intent"]["receipt_hash"] == runtime["authority"]["index_receipts"][0]["receipt_hash"]
    assert result["index_read_intent"]["checkpoint_hash"] == runtime["checkpoint"]["checkpoint_hash"]
    assert result["index_read_intent"]["maximum_whole_index_bytes"] == runtime["config"]["limits"]["max_whole_index_bytes"]
    assert result["index_read_intent"]["fsync"]["file"] is True
    assert result["index_read_intent"]["fsync"]["parent_directory"] is True


def test_observe_cycle_rejects_excess_clock_rollback_and_keeps_time_monotonic(
    tmp_path: Path,
) -> None:
    api = _api("observe_one_cycle")
    error = _error()
    rejected = _bind_runtime_checkpoint(runtime_inputs(tmp_path / "rejected"))
    rejected["now"] = "2026-07-13T00:10:01Z"

    with pytest.raises(error, match="clock_rollback_exceeded"):
        api.observe_one_cycle(rejected)
    assert rejected["probe"].events == []

    tolerated = _bind_runtime_checkpoint(runtime_inputs(tmp_path / "tolerated"))
    tolerated["now"] = "2026-07-13T00:10:01.800000Z"

    result = api.observe_one_cycle(tolerated)

    assert result["advanced_checkpoint"]["updated_at"] == "2026-07-13T00:10:02Z"


def test_observe_cycle_promotes_and_checkpoints_only_after_durable_records(tmp_path: Path) -> None:
    api = _api("observe_one_cycle")
    authority = authority_bundle(index_receipts=2, segment_receipts=5)
    runtime = _bind_runtime_checkpoint(runtime_inputs(tmp_path, authority=authority))
    entry = provider_index_entries(authority["segment_receipts"])[0]
    index_path = Path(runtime["base_path"]) / runtime["config"]["index_path"]
    index_path.write_bytes(canonical_bytes(entry) + b"\n")

    result = api.observe_one_cycle(runtime)

    events = runtime["probe"].events
    assert events.index("write_index_read_intent") < events.index("index_open") < events.index("index_read") < events.index("segment_open")
    assert len(result["promotion_records"]) == 1
    assert result["advanced_checkpoint"]["consumed_index_read_receipt_hashes"] == [authority["index_receipts"][0]["receipt_hash"]]
    assert result["advanced_checkpoint"]["promotion_keys"][entry["entry_hash"]]["promotion_hash"] == result["promotion_records"][0]["promotion_hash"]
    promotion_name = result["promotion_records"][0]["promotion_hash"].removeprefix("sha256:")
    intent_name = result["index_read_intent"]["cycle_id"].removeprefix("sha256:")
    assert (Path(runtime["base_path"]) / runtime["config"]["journal_dir"] / f"{intent_name}.promotion-intent.json").is_file()
    assert (Path(runtime["base_path"]) / runtime["config"]["promotion_dir"] / f"{promotion_name}.json").is_file()
    assert (Path(runtime["base_path"]) / runtime["config"]["checkpoint_path"]).is_file()
    outcome = json.loads(_cycle_outcome_path(runtime, result["index_read_intent"]["cycle_id"]).read_text())
    assert outcome["schema_version"] == "p136.cycle_completion.v1"
    assert outcome["starting_checkpoint_hash"] == runtime["checkpoint"]["checkpoint_hash"]
    assert outcome["resulting_checkpoint"] == result["advanced_checkpoint"]
    assert outcome["resulting_checkpoint_hash"] == result["advanced_checkpoint"]["checkpoint_hash"]
    assert outcome["committed_checkpoint_hash"] == result["advanced_checkpoint"]["checkpoint_hash"]
    assert outcome["promotion_sequences"] == [1]
    assert outcome["promotion_hashes"] == [result["promotion_records"][0]["promotion_hash"]]
    assert outcome["promotion_records"] == result["promotion_records"]
    assert outcome["fsync"] == {"file": True, "parent_directory": True}
    assert outcome["completion_hash"] == stable_hash(
        {key: value for key, value in outcome.items() if key != "completion_hash"}
    )
    assert result["activity"]["promotion_intent_write_count"] == 1
    assert result["activity"]["checkpoint_write_count"] == 1


@pytest.mark.parametrize("with_promotion", [True, False], ids=["nonempty", "empty"])
@pytest.mark.parametrize(
    "crash_phase",
    ["cycle_outcome_intent_durable", "cycle_checkpoint_durable"],
    ids=["before-checkpoint", "after-checkpoint"],
)
def test_two_phase_cycle_outcome_recovers_exact_cycle_without_new_index_read(
    tmp_path: Path,
    with_promotion: bool,
    crash_phase: str,
) -> None:
    api = _api("observe_one_cycle", "recover_cycle_outcome", "validate_cycle_outcome")
    error = _error()
    authority = authority_bundle(index_receipts=2, segment_receipts=5)
    runtime = _bind_runtime_checkpoint(runtime_inputs(tmp_path, authority=authority))
    if with_promotion:
        _write_index_entry(runtime, provider_index_entries(authority["segment_receipts"])[0])

    def crash_at(phase: str) -> None:
        if phase == crash_phase:
            raise error(f"evaluator_crash:{phase}")

    with pytest.raises(error, match=f"evaluator_crash:{crash_phase}"):
        api.observe_one_cycle({**runtime, "evaluator_crash_injector": crash_at})

    outcome_paths = list(
        (Path(runtime["base_path"]) / runtime["config"]["cycle_outcome_dir"]).glob("*.json")
    )
    assert len(outcome_paths) == 1
    intent = json.loads(outcome_paths[0].read_text())
    assert intent["schema_version"] == "p136.cycle_outcome_intent.v1"
    assert intent["promotion_count"] == int(with_promotion)
    assert intent["promotion_sequences"] == ([1] if with_promotion else [])
    durable_checkpoint_path = _checkpoint_path(runtime)
    if crash_phase == "cycle_outcome_intent_durable":
        assert not durable_checkpoint_path.exists()
        recovery_checkpoint = runtime["checkpoint"]
    else:
        recovery_checkpoint = json.loads(durable_checkpoint_path.read_text())
        assert recovery_checkpoint["checkpoint_hash"] == intent["resulting_checkpoint_hash"]

    runtime["probe"] = ActivityProbe()
    recovered = api.recover_cycle_outcome(
        {
            **runtime,
            "checkpoint": recovery_checkpoint,
        },
        cycle_id=intent["cycle_id"],
        index_read_receipt_hash=intent["index_read_receipt_hash"],
    )
    completion = json.loads(outcome_paths[0].read_text())
    api.validate_cycle_outcome(completion, runtime["config"])

    assert recovered["recovered_cycle_outcome"] is True
    assert recovered["cycle_outcome"] == completion
    assert completion["schema_version"] == "p136.cycle_completion.v1"
    assert recovered["advanced_checkpoint"] == intent["resulting_checkpoint"]
    assert recovered["advanced_checkpoint"]["consumed_index_read_receipt_hashes"] == [
        authority["index_receipts"][0]["receipt_hash"]
    ]
    assert len(recovered["promotion_records"]) == int(with_promotion)
    assert runtime["probe"].index_open_count == 0
    assert runtime["probe"].index_read_count == 0
    assert runtime["probe"].segment_open_count == 0
    assert recovered["activity"]["recovery_replay_count"] == 1


def test_cycle_outcome_completion_reconciles_only_exact_bound_tuple_and_fails_closed_on_tamper(
    tmp_path: Path,
) -> None:
    api = _api("observe_one_cycle", "recover_cycle_outcome")
    error = _error()
    authority = authority_bundle(index_receipts=2, segment_receipts=5)
    runtime = _bind_runtime_checkpoint(runtime_inputs(tmp_path, authority=authority))
    _write_index_entry(runtime, provider_index_entries(authority["segment_receipts"])[0])
    observed = api.observe_one_cycle(runtime)
    cycle_id = observed["index_read_intent"]["cycle_id"]
    receipt_hash = observed["index_read_intent"]["receipt_hash"]
    outcome_path = _cycle_outcome_path(runtime, cycle_id)
    checkpoint_before = _checkpoint_path(runtime).read_bytes()

    runtime["probe"] = ActivityProbe()
    reconciled = api.recover_cycle_outcome(
        {
            **runtime,
            "checkpoint": observed["advanced_checkpoint"],
        },
        cycle_id=cycle_id,
        index_read_receipt_hash=receipt_hash,
    )
    assert reconciled["recovered_cycle_outcome"] is True
    assert runtime["probe"].events == []

    tampered = json.loads(outcome_path.read_text())
    tampered["resulting_checkpoint"]["committed_cursor"] += 1
    tampered["resulting_checkpoint_hash"] = stable_hash(
        {key: value for key, value in tampered["resulting_checkpoint"].items() if key != "checkpoint_hash"}
    )
    tampered["completion_hash"] = stable_hash(
        {key: value for key, value in tampered.items() if key != "completion_hash"}
    )
    outcome_path.write_text(json.dumps(tampered, sort_keys=True, separators=(",", ":")) + "\n")

    with pytest.raises(error, match="cycle_outcome"):
        api.recover_cycle_outcome(
            {
                **runtime,
                "checkpoint": observed["advanced_checkpoint"],
            },
            cycle_id=cycle_id,
            index_read_receipt_hash=receipt_hash,
        )
    assert _checkpoint_path(runtime).read_bytes() == checkpoint_before


@pytest.mark.parametrize("encoding", ["pretty", "missing_newline", "extra_newline"])
def test_cycle_outcome_recovery_rejects_noncanonical_persisted_bytes(
    tmp_path: Path,
    encoding: str,
) -> None:
    api = _api("observe_one_cycle", "recover_cycle_outcome")
    error = _error()
    authority = authority_bundle(index_receipts=2, segment_receipts=5)
    runtime = _bind_runtime_checkpoint(runtime_inputs(tmp_path, authority=authority))
    _write_index_entry(runtime, provider_index_entries(authority["segment_receipts"])[0])
    observed = api.observe_one_cycle(runtime)
    cycle_id = observed["index_read_intent"]["cycle_id"]
    outcome_path = _cycle_outcome_path(runtime, cycle_id)
    outcome = json.loads(outcome_path.read_text(encoding="utf-8"))
    if encoding == "pretty":
        raw = json.dumps(outcome, indent=2, sort_keys=True).encode() + b"\n"
    elif encoding == "missing_newline":
        raw = canonical_bytes(outcome)
    else:
        raw = canonical_bytes(outcome) + b"\n\n"
    outcome_path.write_bytes(raw)

    with pytest.raises(error, match="state_json_noncanonical"):
        api.recover_cycle_outcome(
            {**runtime, "checkpoint": observed["advanced_checkpoint"]},
            cycle_id=cycle_id,
            index_read_receipt_hash=observed["index_read_intent"]["receipt_hash"],
        )


def test_bound_cycle_recovery_fails_closed_when_outcome_is_missing(
    tmp_path: Path,
) -> None:
    api = _api("recover_cycle_outcome")
    error = _error()
    authority = authority_bundle(index_receipts=2, segment_receipts=5)
    runtime = _bind_runtime_checkpoint(runtime_inputs(tmp_path, authority=authority))
    receipt_hash = authority["index_receipts"][0]["receipt_hash"]
    cycle_id = stable_hash(
        {
            "schema_version": "p136.deterministic_cycle_id.v1",
            "config_hash": runtime["config"]["config_hash"],
            "checkpoint_hash": runtime["checkpoint"]["checkpoint_hash"],
            "receipt_hash": receipt_hash,
        }
    )

    with pytest.raises(error, match="expected_cycle_outcome_missing"):
        api.recover_cycle_outcome(
            runtime,
            cycle_id=cycle_id,
            index_read_receipt_hash=receipt_hash,
        )

    assert runtime["probe"].events == []
    assert not _checkpoint_path(runtime).exists()


def test_cycle_outcome_binds_each_ordered_promotion_record_hash(
    tmp_path: Path,
) -> None:
    api = _api("observe_one_cycle", "validate_cycle_outcome")
    error = _error()
    authority = authority_bundle(index_receipts=2, segment_receipts=5)
    config = config_input(tmp_path, authority)
    config["limits"]["max_journal_bytes"] = 1_000_000
    config["limits"]["max_promotion_bytes"] = 1_000_000
    runtime = _bind_runtime_checkpoint(
        runtime_inputs(tmp_path, authority=authority, config=config)
    )
    entries = provider_index_entries(authority["segment_receipts"])[:2]
    index_path = Path(runtime["base_path"]) / runtime["config"]["index_path"]
    index_path.write_bytes(
        b"".join(canonical_bytes(entry) + b"\n" for entry in entries)
    )

    def crash_at(phase: str) -> None:
        if phase == "cycle_outcome_intent_durable":
            raise error("evaluator_crash:cycle_outcome_intent_durable")

    with pytest.raises(error, match="evaluator_crash:cycle_outcome_intent_durable"):
        api.observe_one_cycle({**runtime, "evaluator_crash_injector": crash_at})

    outcome_path = next(
        (
            Path(runtime["base_path"])
            / runtime["config"]["cycle_outcome_dir"]
        ).glob("*.json")
    )
    intent = json.loads(outcome_path.read_text())
    assert len(intent["promotion_records"]) == 2
    intent["promotion_hashes"][0] = stable_hash({"forged": "first"})
    intent["intent_hash"] = stable_hash(
        {key: value for key, value in intent.items() if key != "intent_hash"}
    )

    with pytest.raises(error, match="cycle_outcome_promotion_record_hash_mismatch"):
        api.validate_cycle_outcome(intent, runtime["config"])


def test_observe_cycle_rejects_symlink_parent_before_index_open(tmp_path: Path) -> None:
    api = _api("observe_one_cycle")
    error = _error()
    runtime = _bind_runtime_checkpoint(runtime_inputs(tmp_path))
    probe = runtime["probe"]
    base_path = Path(runtime["base_path"])
    (base_path / "data" / "index.jsonl").unlink()
    (base_path / "data").rmdir()
    external = tmp_path / "external-data"
    external.mkdir()
    (base_path / "data").symlink_to(external, target_is_directory=True)

    with pytest.raises(error, match="index_parent_symlink_or_invalid"):
        api.observe_one_cycle(runtime)
    assert probe.events == ["write_index_read_intent"]


def test_observe_cycle_rejects_symlinked_state_dir_without_escape(tmp_path: Path) -> None:
    api = _api("observe_one_cycle")
    error = _error()
    runtime = _bind_runtime_checkpoint(runtime_inputs(tmp_path))
    probe = runtime["probe"]
    base_path = Path(runtime["base_path"])
    (base_path / "state").rmdir()
    external = tmp_path / "external-state"
    external.mkdir()
    (base_path / "state").symlink_to(external, target_is_directory=True)

    with pytest.raises(error, match="exclusive_lease_invalid"):
        api.observe_one_cycle(runtime)
    assert probe.events == []
    assert not any(external.iterdir())


def test_index_read_rejects_replacement_after_open_before_scan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _api("observe_one_cycle")
    error = _error()
    runtime = _bind_runtime_checkpoint(runtime_inputs(tmp_path))
    index_path = Path(runtime["base_path"]) / runtime["config"]["index_path"]
    original_read = os.read
    swapped = False

    def replacing_read(fd: int, count: int) -> bytes:
        nonlocal swapped
        if not swapped:
            swapped = True
            replacement = index_path.with_suffix(".replacement")
            replacement.write_bytes(b"")
            replacement.replace(index_path)
        return original_read(fd, count)

    monkeypatch.setattr(module.os, "read", replacing_read)

    with pytest.raises(error, match="index_path_binding_changed"):
        module.observe_one_cycle(runtime)
    assert runtime["probe"].events == ["write_index_read_intent", "index_open", "index_read"]


def test_receipt_retry_is_allowed_only_from_exact_durable_uncommitted_intent(tmp_path: Path) -> None:
    api = _api("observe_one_cycle")
    error = _error()
    runtime = _bind_runtime_checkpoint(runtime_inputs(tmp_path, authority=authority_bundle(index_receipts=1)))
    receipt_hash = runtime["authority"]["index_receipts"][0]["receipt_hash"]
    valid = api.observe_one_cycle(runtime)["index_read_intent"]
    stale_intent = _rehash({**valid, "checkpoint_hash": stable_hash({"stale": "checkpoint"})}, "intent_hash")

    with pytest.raises(error, match="index_read_receipt_pool_exhausted"):
        api.observe_one_cycle(
            _bind_runtime_checkpoint(
                {
                    **runtime,
                    "checkpoint": checkpoint(consumed_index_read_receipt_hashes=[receipt_hash]),
                }
            )
        )
    with pytest.raises(error, match="index_read_intent_checkpoint_mismatch"):
        api.observe_one_cycle({**runtime, "recovery_intent": stale_intent})


def test_secure_whole_index_scanner_defers_partial_line_without_advancing_committed_cursor(tmp_path: Path) -> None:
    api = _api("scan_incremental_index")
    pending_bytes = b'{"entry_id":"entry-0001"'
    runtime = runtime_inputs(tmp_path)

    result = api.scan_incremental_index(runtime, index_bytes=pending_bytes)

    assert result["complete_entries"] == []
    assert result["checkpoint_patch"]["committed_cursor"] == 0
    assert result["checkpoint_patch"]["observed_index_size"] == len(pending_bytes)
    assert result["checkpoint_patch"]["pending_partial"]["pending_byte_length"] == len(pending_bytes)


def test_secure_whole_index_scanner_rejects_prefix_mutation_truncation_duplicate_keys_and_budget_excess(tmp_path: Path) -> None:
    api = _api("scan_incremental_index")
    error = _error()
    current = checkpoint(committed_cursor=12, consumed_prefix_hash=stable_hash({"prefix": "expected"}))
    runtime = runtime_inputs(tmp_path, checkpoint_value=current)

    with pytest.raises(error, match="consumed_prefix_mismatch"):
        api.scan_incremental_index(runtime, index_bytes=b'{"changed":1}\n')
    with pytest.raises(error, match="index_truncation_detected"):
        api.scan_incremental_index(runtime, index_bytes=b"short")
    with pytest.raises(error, match="duplicate_json_key"):
        api.scan_incremental_index(runtime_inputs(tmp_path), index_bytes=b'{"entry_id":"a","entry_id":"b"}\n')
    large_runtime = runtime_inputs(
        tmp_path,
        config=config_input(
            tmp_path,
            limits={**config_input(tmp_path)["limits"], "max_whole_index_bytes": 8192},
        ),
    )
    with pytest.raises(error, match="index_line_byte_budget_exceeded"):
        api.scan_incremental_index(large_runtime, index_bytes=b'{"entry_id":"' + (b"a" * 4096) + b'"}\n')


def test_secure_whole_index_scanner_enforces_configured_json_tree_limits(tmp_path: Path) -> None:
    api = _api("scan_incremental_index")
    error = _error()
    small_limits = {
        **config_input(tmp_path)["limits"],
        "max_json_depth": 1,
        "max_json_nodes": 2,
        "max_json_string_bytes": 4,
    }

    with pytest.raises(error, match="index_json_string_budget_exceeded"):
        api.scan_incremental_index(
            runtime_inputs(tmp_path, config=config_input(tmp_path, limits=small_limits)),
            index_bytes=b'{"x":"abcde"}\n',
        )
    with pytest.raises(error, match="index_json_node_budget_exceeded"):
        api.scan_incremental_index(
            runtime_inputs(tmp_path, config=config_input(tmp_path, limits={**small_limits, "max_json_string_bytes": 32})),
            index_bytes=b'{"a":1,"b":2}\n',
        )
    with pytest.raises(error, match="index_json_depth_exceeded"):
        api.scan_incremental_index(
            runtime_inputs(tmp_path, config=config_input(tmp_path, limits={**small_limits, "max_json_nodes": 10, "max_json_string_bytes": 32})),
            index_bytes=b'{"a":{"b":1}}\n',
        )


def test_pending_partial_must_match_exact_prefix_and_blocks_old_identity_rotation(tmp_path: Path) -> None:
    api = _api("scan_incremental_index")
    error = _error()
    pending = pending_partial_state()
    current = checkpoint(pending_partial=pending, committed_cursor=pending["line_start_cursor"], observed_index_size=pending["observed_index_size"])
    runtime = runtime_inputs(tmp_path, checkpoint_value=current)

    with pytest.raises(error, match="pending_partial_prefix_mismatch"):
        api.scan_incremental_index(runtime, index_bytes=b'{"entry_id":"different"}\n', file_identity_hash=pending["file_identity_hash"])
    with pytest.raises(error, match="rotation_rejected_with_pending_partial"):
        api.scan_incremental_index(runtime, index_bytes=b"", file_identity_hash=stable_hash({"index_identity": "new"}))


def test_rotation_replay_prefix_resolves_duplicates_before_p135_with_zero_segment_reads(tmp_path: Path) -> None:
    api = _api("scan_incremental_index", "resolve_index_entries")
    first = self_hash_entry(index_entry_input())
    current = checkpoint(
        committed_cursor=128,
        next_entry_sequence=2,
        last_entry_hash=first["entry_hash"],
        canonical_entry_identities={first["entry_id"]: first, first["segment_id"]: first},
        promotion_keys={first["entry_hash"]: promotion_record(first)},
    )
    probe = ActivityProbe()
    runtime = runtime_inputs(tmp_path, checkpoint_value=current, probe=probe)

    scan = api.scan_incremental_index(runtime, index_bytes=canonical_bytes(first) + b"\n", file_identity_hash=stable_hash({"index_identity": "rotated"}))
    result = api.resolve_index_entries(runtime, scan["complete_entries"])

    assert result["duplicate_entries"] == [first["entry_hash"]]
    assert result["promotions_written"] == []
    assert probe.segment_open_count == 0
    assert probe.segment_read_count == 0


def test_resolve_index_entries_enforces_pending_entry_budget_before_p135(tmp_path: Path) -> None:
    api = _api("resolve_index_entries")
    error = _error()
    first = self_hash_entry(index_entry_input())
    second = self_hash_entry(index_entry_input(2, previous_entry_hash=first["entry_hash"]))
    probe = ActivityProbe()
    runtime = runtime_inputs(
        tmp_path,
        config=config_input(tmp_path, limits={**config_input(tmp_path)["limits"], "max_pending_entries": 1}),
        probe=probe,
    )

    with pytest.raises(error, match="pending_entry_budget_exceeded"):
        api.resolve_index_entries(runtime, [first, second])
    assert probe.segment_open_count == 0


def test_resolve_index_entries_assigns_unique_sequences_and_deduplicates_within_batch(
    tmp_path: Path,
) -> None:
    api = _api("resolve_index_entries")
    authority = authority_bundle(index_receipts=2, segment_receipts=5)
    entries = provider_index_entries(authority["segment_receipts"])
    runtime = _bind_runtime_checkpoint(
        runtime_inputs(tmp_path / "unique", authority=authority)
    )

    result = api.resolve_index_entries(runtime, entries[:2])

    assert [record["promotion_sequence"] for record in result["promotion_records"]] == [
        1,
        2,
    ]
    assert len(set(result["promotions_written"])) == 2

    duplicate_runtime = _bind_runtime_checkpoint(
        runtime_inputs(tmp_path / "duplicate", authority=authority)
    )
    duplicate = api.resolve_index_entries(
        duplicate_runtime,
        [entries[0], entries[0]],
    )

    assert len(duplicate["promotion_records"]) == 1
    assert duplicate["duplicate_entries"] == [entries[0]["entry_hash"]]
    assert duplicate_runtime["probe"].segment_read_count == 1


def test_rotation_first_unseen_entry_requires_global_sequence_previous_hash_and_rotation_hash(tmp_path: Path) -> None:
    api = _api("scan_incremental_index")
    error = _error()
    first = self_hash_entry(index_entry_input())
    invalid_unseen = self_hash_entry(
        index_entry_input(
            3,
            previous_entry_hash=stable_hash({"gap": True}),
            rotation_from_hash=first["entry_hash"],
        )
    )
    current = checkpoint(
        next_entry_sequence=2,
        last_entry_hash=first["entry_hash"],
        canonical_entry_identities={first["entry_id"]: first},
    )

    with pytest.raises(error, match="rotation_sequence_gap"):
        api.scan_incremental_index(
            runtime_inputs(tmp_path, checkpoint_value=current),
            index_bytes=canonical_bytes(invalid_unseen) + b"\n",
            file_identity_hash=stable_hash({"index_identity": "rotated"}),
        )


def test_first_seen_entries_use_real_p135_bridge_with_independent_ledger_namespaces_and_tamper_validation(tmp_path: Path) -> None:
    api = _api("promote_first_seen_entry", "validate_promotion_record")
    error = _error()
    authority = authority_bundle(index_receipts=3, segment_receipts=5)
    entries = provider_index_entries(authority["segment_receipts"])
    export_root = copy_p135_fixture_tree(tmp_path)
    runtime = runtime_inputs(tmp_path, authority=authority)

    left = api.promote_first_seen_entry({**runtime, "export_root": export_root}, entries[0])
    right = api.promote_first_seen_entry({**runtime, "export_root": export_root}, entries[1])
    tampered = deepcopy(left["promotion_record"])
    tampered["p135_receipt_ledger_hash"] = right["promotion_record"]["p135_receipt_ledger_hash"]
    tampered["promotion_hash"] = stable_hash({key: value for key, value in tampered.items() if key != "promotion_hash"})

    assert left["promotion_record"]["p135_receipt_ledger_hash"] != right["promotion_record"]["p135_receipt_ledger_hash"]
    assert left["p135_result"]["receipt"]["adapter_version"].startswith("p135.adapter.")
    assert right["p135_result"]["receipt"]["adapter_version"].startswith("p135.adapter.")
    assert left["activity"]["segment_file_read_count"] == 1
    assert right["activity"]["segment_file_read_count"] == 1
    with pytest.raises(error, match="p135_independent_ledger_tamper"):
        api.validate_promotion_record(tampered, expected_entry=entries[0], runtime={**runtime, "export_root": export_root})


def test_persisted_promotion_intent_recovery_restores_missing_record_and_checkpoint_without_p135(tmp_path: Path) -> None:
    api = _api("observe_one_cycle", "recover_observer_state")
    authority = authority_bundle(index_receipts=2, segment_receipts=5)
    runtime = _bind_runtime_checkpoint(runtime_inputs(tmp_path, authority=authority))
    entry = provider_index_entries(authority["segment_receipts"])[0]
    _write_index_entry(runtime, entry)
    observed = api.observe_one_cycle(runtime)
    promotion = observed["promotion_records"][0]
    expected_promotion_bytes = _promotion_path(runtime, promotion).read_bytes()
    expected_checkpoint_bytes = _checkpoint_path(runtime).read_bytes()
    _promotion_path(runtime, promotion).unlink()
    _checkpoint_path(runtime).unlink()
    runtime["probe"] = ActivityProbe()

    recovered = api.recover_observer_state(runtime)
    recovered_again = api.recover_observer_state(runtime)

    assert recovered["promotions_written"] == [promotion["promotion_hash"]]
    assert recovered["checkpoint_advanced"] is True
    assert recovered["recovered_from_promotion_intent"] is True
    assert recovered["p135_invocation_count"] == 0
    assert runtime["probe"].segment_open_count == 0
    assert runtime["probe"].segment_read_count == 0
    assert _promotion_path(runtime, promotion).read_bytes() == expected_promotion_bytes
    assert _checkpoint_path(runtime).read_bytes() == expected_checkpoint_bytes
    assert recovered_again["promotions_written"] == []
    assert recovered_again["checkpoint_advanced"] is False


def test_promotion_before_checkpoint_recovery_advances_exact_checkpoint_without_segment_reads(tmp_path: Path) -> None:
    api = _api("observe_one_cycle", "recover_observer_state")
    authority = authority_bundle(index_receipts=2, segment_receipts=5)
    runtime = _bind_runtime_checkpoint(runtime_inputs(tmp_path, authority=authority))
    entry = provider_index_entries(authority["segment_receipts"])[0]
    _write_index_entry(runtime, entry)
    observed = api.observe_one_cycle(runtime)
    promotion = observed["promotion_records"][0]
    expected_promotion_bytes = _promotion_path(runtime, promotion).read_bytes()
    expected_checkpoint_bytes = _checkpoint_path(runtime).read_bytes()
    _checkpoint_path(runtime).unlink()
    runtime["probe"] = ActivityProbe()

    recovered = api.recover_observer_state(runtime)

    assert recovered["promotions_written"] == []
    assert recovered["promotions_verified"] == [promotion["promotion_hash"]]
    assert recovered["checkpoint_advanced"] is True
    assert recovered["recovered_from_promotions_before_checkpoint"] is True
    assert recovered["p135_invocation_count"] == 0
    assert runtime["probe"].segment_open_count == 0
    assert runtime["probe"].segment_read_count == 0
    assert _promotion_path(runtime, promotion).read_bytes() == expected_promotion_bytes
    assert _checkpoint_path(runtime).read_bytes() == expected_checkpoint_bytes


def test_recovery_rejects_promotion_hash_tamper_duplicate_p135_and_checkpoint_binding(tmp_path: Path) -> None:
    api = _api("observe_one_cycle", "promote_first_seen_entry", "recover_observer_state")
    error = _error()
    authority = authority_bundle(index_receipts=2, segment_receipts=5)
    runtime = _bind_runtime_checkpoint(runtime_inputs(tmp_path, authority=authority))
    entries = provider_index_entries(authority["segment_receipts"])
    entry = entries[0]
    _write_index_entry(runtime, entry)
    promotion = api.observe_one_cycle(runtime)["promotion_records"][0]
    right = api.promote_first_seen_entry(
        {**runtime, "checkpoint": checkpoint(next_promotion_sequence=2, config_hash=runtime["config"]["config_hash"])},
        entries[1],
    )["promotion_record"]
    tampered = deepcopy(promotion)
    tampered["status"] = "denominator_failure"
    forged_nested = deepcopy(promotion)
    forged_nested["p135_normalized_bundle"] = deepcopy(right["p135_normalized_bundle"])
    forged_nested["p135_normalized_bundle_hash"] = right["p135_normalized_bundle_hash"]
    forged_nested["promotion_hash"] = stable_hash({key: value for key, value in forged_nested.items() if key != "promotion_hash"})
    duplicate = deepcopy(promotion)
    duplicate["promotion_sequence"] = 2
    duplicate["promotion_hash"] = stable_hash({key: value for key, value in duplicate.items() if key != "promotion_hash"})
    bad_checkpoint = checkpoint(config_hash=stable_hash({"wrong": "config"}))
    memory_runtime = {key: value for key, value in runtime.items() if key != "base_path"}

    with pytest.raises(error, match="promotion_hash_invalid"):
        api.recover_observer_state({**memory_runtime, "promotion_intents": [], "promotions": [tampered], "checkpoints": []})
    with pytest.raises(error, match="p135|promotion|receipt_bundle_hash_mismatch"):
        api.recover_observer_state({**memory_runtime, "promotion_intents": [], "promotions": [forged_nested], "checkpoints": []})
    with pytest.raises(error, match="duplicate_p135_promotion_for_entry"):
        api.recover_observer_state({**memory_runtime, "promotion_intents": [], "promotions": [promotion, duplicate], "checkpoints": []})
    with pytest.raises(error, match="checkpoint_config_hash_mismatch"):
        api.recover_observer_state({**memory_runtime, "promotion_intents": [], "promotions": [], "checkpoints": [bad_checkpoint]})


def test_recovery_rejects_batch_intent_promotion_sequence_mismatch(tmp_path: Path) -> None:
    api = _api("observe_one_cycle", "recover_observer_state")
    error = _error()
    authority = authority_bundle(index_receipts=2, segment_receipts=5)
    runtime = _bind_runtime_checkpoint(runtime_inputs(tmp_path, authority=authority))
    entry = provider_index_entries(authority["segment_receipts"])[0]
    _write_index_entry(runtime, entry)
    observed = api.observe_one_cycle(runtime)
    intent_path = _journal_path(runtime, observed)
    intent = json.loads(intent_path.read_text(encoding="utf-8"))
    promotion = intent["promotion_records"][0]
    promotion["promotion_sequence"] = 99
    promotion["promotion_hash"] = stable_hash({key: value for key, value in promotion.items() if key != "promotion_hash"})
    intent["promotion_hashes"] = [promotion["promotion_hash"]]
    intent["intent_hash"] = stable_hash({key: value for key, value in intent.items() if key != "intent_hash"})
    intent_path.write_text(json.dumps(intent, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    _checkpoint_path(runtime).unlink()

    with pytest.raises(error, match="promotion_sequence_mismatch"):
        api.recover_observer_state(runtime)


def test_checkpoint_advance_enforces_retained_identity_budget_before_persisting(tmp_path: Path) -> None:
    api = _api("observe_one_cycle")
    error = _error()
    authority = authority_bundle(index_receipts=2, segment_receipts=5)
    cfg = config_input(
        tmp_path,
        authority,
        limits={**config_input(tmp_path, authority)["limits"], "max_retained_entry_identities": 1},
    )
    runtime = _bind_runtime_checkpoint(runtime_inputs(tmp_path, authority=authority, config=cfg))
    first, second = provider_index_entries(authority["segment_receipts"])[:2]
    (Path(runtime["base_path"]) / runtime["config"]["index_path"]).write_bytes(
        canonical_bytes(first) + b"\n" + canonical_bytes(second) + b"\n"
    )

    with pytest.raises(error, match="retained_entry_identity_budget_exceeded"):
        api.observe_one_cycle(runtime)
    assert not _checkpoint_path(runtime).exists()


def test_observe_enforces_journal_and_promotion_canonical_byte_budgets(tmp_path: Path) -> None:
    api = _api("observe_one_cycle")
    error = _error()
    authority = authority_bundle(index_receipts=2, segment_receipts=5)
    entry = provider_index_entries(authority["segment_receipts"])[0]
    journal_cfg = config_input(
        tmp_path / "journal",
        authority,
        limits={**config_input(tmp_path / "journal", authority)["limits"], "max_journal_bytes": 128},
    )
    journal_runtime = _bind_runtime_checkpoint(runtime_inputs(tmp_path / "journal", authority=authority, config=journal_cfg))
    _write_index_entry(journal_runtime, entry)

    with pytest.raises(error, match="promotion_intent_byte_budget_exceeded"):
        api.observe_one_cycle(journal_runtime)

    promotion_cfg = config_input(
        tmp_path / "promotion",
        authority,
        limits={**config_input(tmp_path / "promotion", authority)["limits"], "max_promotion_bytes": 128},
    )
    promotion_runtime = _bind_runtime_checkpoint(runtime_inputs(tmp_path / "promotion", authority=authority, config=promotion_cfg))
    _write_index_entry(promotion_runtime, entry)

    with pytest.raises(error, match="promotion_record_byte_budget_exceeded"):
        api.observe_one_cycle(promotion_runtime)


def test_checkpoint_replace_fsync_uncertainty_stops_without_claiming_success(tmp_path: Path) -> None:
    api = _api("advance_checkpoint")
    error = _error()
    runtime = runtime_inputs(tmp_path)

    with pytest.raises(error, match="checkpoint_parent_fsync_uncertain"):
        api.advance_checkpoint(runtime, checkpoint(), simulate_parent_fsync_uncertain=True)


def test_exclusive_lease_blocks_competitors_before_state_index_or_segment_reads(tmp_path: Path) -> None:
    api = _api("observe_one_cycle")
    error = _error()
    probe = ActivityProbe()
    runtime = _bind_runtime_checkpoint(runtime_inputs(tmp_path, probe=probe))

    with pytest.raises(error, match="exclusive_lease_unavailable"):
        api.observe_one_cycle({**runtime, "lease_competitor": True})
    assert probe.events == []
    assert probe.index_open_count == 0
    assert probe.segment_open_count == 0


def test_loop_stops_on_receipt_exhaustion_failure_threshold_and_safe_signals(tmp_path: Path) -> None:
    api = _api("run_observer_loop")
    runtime = _bind_runtime_checkpoint(runtime_inputs(tmp_path, authority=authority_bundle(index_receipts=1)))

    exhausted = api.run_observer_loop(runtime, max_cycles=2)
    failed = api.run_observer_loop({**runtime, "force_cycle_failures": 2}, max_cycles=3)
    interrupted = api.run_observer_loop({**runtime, "inject_signal": "SIGTERM"}, max_cycles=3)

    assert exhausted["termination_receipt"]["stop_reason"] == "receipt_exhaustion"
    assert failed["termination_receipt"]["stop_reason"] == "failure_threshold"
    assert interrupted["termination_receipt"]["stop_reason"] == "signal_SIGTERM_safe_boundary"
    assert interrupted["termination_receipt"]["final_checkpoint_hash"] == interrupted["checkpoint"]["checkpoint_hash"]


def test_loop_uses_real_cycles_and_monotonic_poll_cadence(tmp_path: Path) -> None:
    api = _api("run_observer_loop")
    runtime = _bind_runtime_checkpoint(runtime_inputs(tmp_path, authority=authority_bundle(index_receipts=2)))
    sleeps: list[float] = []

    result = api.run_observer_loop(
        {
            **runtime,
            "monotonic": lambda: 0.0,
            "sleep": sleeps.append,
        },
        max_cycles=2,
    )

    assert result["cycles_completed"] == 2
    assert result["checkpoint"]["consumed_index_read_receipt_hashes"] == [receipt["receipt_hash"] for receipt in runtime["authority"]["index_receipts"]]
    assert sleeps == [runtime["config"]["limits"]["poll_interval_ms"] / 1000.0]


def test_authority_activity_and_resource_schemas_are_exact_zero_or_positive_as_required() -> None:
    api = _api("validate_measurement_schemas")
    error = _error()
    valid = {
        "forbidden_authority": {key: 0 for key in FORBIDDEN_AUTHORITY_KEYS},
        "runtime_activity": {key: 0 for key in RUNTIME_ACTIVITY_KEYS},
        "evaluator_activity": {key: 0 for key in EVALUATOR_ACTIVITY_KEYS},
        "resource_usage": {key: 1 for key in RESOURCE_USAGE_KEYS},
    }
    api.validate_measurement_schemas(valid)

    invalid = deepcopy(valid)
    invalid["forbidden_authority"]["network_call_count"] = True
    with pytest.raises(error, match="invalid_forbidden_authority_schema"):
        api.validate_measurement_schemas(invalid)
    invalid = deepcopy(valid)
    invalid["runtime_activity"]["unknown_counter"] = 0
    with pytest.raises(error, match="invalid_runtime_activity_schema"):
        api.validate_measurement_schemas(invalid)
