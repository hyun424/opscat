from __future__ import annotations

import fcntl
import json
import os
import signal
from pathlib import Path
from typing import Any

import pytest

from app.services.p110_evaluation import stable_hash
from app.services.p137_contracts import (
    ALLOWED_REQUEST_CATALOG,
    EVALUATOR_ACTIVITY_KEYS,
    FIXED_P136_HANDOFF_PATH,
    LIMIT_KEYS,
    P136_QUALIFIED_RELEASE_STATUS,
    RUNTIME_ACTIVITY_KEYS,
    build_classification_policy,
    build_continuous_mode,
    build_correlation_policy,
    build_ranking_policy,
    zero_forbidden_authority,
    zero_runtime_activity,
)


def _api() -> Any:
    try:
        from app.services import p137_runtime
    except ModuleNotFoundError as exc:
        pytest.fail(f"missing P137 runtime module: {exc}")
    return p137_runtime


def _config(tmp_path: Path, **overrides: Any) -> dict[str, Any]:
    from app.services.p137_contracts import build_triage_agent_config

    overrides = dict(overrides)
    continuous_enabled = bool(overrides.pop("continuous_mode", False))
    limit_overrides = dict(overrides.pop("limit_overrides", {}))
    limits = {key: index + 10 for index, key in enumerate(LIMIT_KEYS)}
    limits.update(
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
            "max_cycles": 2,
            "poll_interval_ms": 1,
            "heartbeat_interval_ms": 1,
            "readiness_stale_after_ms": 5,
            "handoff_version_stale_after_ms": 5,
        }
    )
    limits.update(limit_overrides)
    raw: dict[str, Any] = {
        "agent_id": "p137-runtime",
        "config_version": 1,
        "created_at": "2026-07-14T00:00:00Z",
        "base_dir_ref_hash": stable_hash({"path": tmp_path.name}),
        "state_root_ref_hash": stable_hash({"path": "state"}),
        "handoff_root_ref_hash": stable_hash({"path": "handoff"}),
        "p136_handoff_bundle_path": FIXED_P136_HANDOFF_PATH,
        "p136_handoff_chain_root_hash": stable_hash({"chain": "root"}),
        "checkpoint_path": "state/checkpoint.json",
        "lease_path": "state/p137.lock",
        "journal_dir": "state/journal",
        "incident_dir": "state/incidents",
        "hypothesis_dir": "state/hypotheses",
        "request_dir": "state/requests",
        "classification_dir": "state/classifications",
        "heartbeat_path": "state/heartbeat.json",
        "readiness_path": "state/readiness.json",
        "termination_dir": "state/terminations",
        "ledger_path": "state/ledger.json",
        "validated_p136_release_status": P136_QUALIFIED_RELEASE_STATUS,
        "allowed_request_catalog": list(ALLOWED_REQUEST_CATALOG),
        "correlation_policy": build_correlation_policy(),
        "ranking_policy": build_ranking_policy(),
        "classification_policy": build_classification_policy(),
        "continuous_mode": build_continuous_mode(
            enabled=continuous_enabled,
            max_cycles=limits["max_cycles"],
            poll_interval_ms=limits["poll_interval_ms"],
            heartbeat_interval_ms=limits["heartbeat_interval_ms"],
            readiness_path="state/readiness.json",
            readiness_stale_after_ms=limits["readiness_stale_after_ms"],
            handoff_version_stale_after_ms=limits["handoff_version_stale_after_ms"],
        ),
        "limits": limits,
        "forbidden_authority": zero_forbidden_authority(),
    }
    raw.update(overrides)
    return build_triage_agent_config(raw)


def _bundle(sequence: int = 1, previous: str | None = None, **overrides: Any) -> dict[str, Any]:
    atom = {
        "schema_version": "p137.evidence_atom.v1",
        "atom_id": f"atom-{sequence}",
        "promotion_record_hash": stable_hash({"promotion": sequence}),
        "promotion_key": stable_hash({"promotion_key": sequence}),
        "p136_entry_hash": stable_hash({"entry": sequence}),
        "p135_bundle_hash": stable_hash({"p135_bundle": sequence}),
        "source_id": f"source-{sequence}",
        "provider": "prometheus",
        "format": "prometheus.query_range.matrix.v1",
        "signal_family": "metrics",
        "system_id": "system-a",
        "entity_ref_hash": stable_hash({"entity": "checkout"}),
        "window": {"start": "2026-07-14T00:00:00Z", "end": "2026-07-14T00:05:00Z"},
        "signal_name": "error_rate",
        "numeric_value": 5,
        "numeric_unit": "ratio",
        "evidence_state": "promoted_success",
        "severity_code": "sev2",
        "metric_breach_code": "above_critical",
        "marker_code": "none",
        "counter_signal_code": "none",
        "state_reason_codes": [],
        "denominator_visible": False,
        "content_hash": stable_hash({"content": sequence}),
        "label_hashes": [stable_hash({"label": "checkout"})],
        "topology_ref_hashes": [],
        "deploy_config_ref_hashes": [],
        "risk_flags": [],
        "redacted_preview_hash": stable_hash({"preview": sequence}),
        "ordinal": sequence,
    }
    atom["atom_hash"] = stable_hash(atom)
    value: dict[str, Any] = {
        "bundle_version": 1,
        "bundle_sequence": sequence,
        "bundle_hash": stable_hash({"bundle": sequence}),
        "previous_bundle_hash": previous,
        "handoff_chain_root_hash": stable_hash({"chain": "root"}),
        "fixed_handoff_path": FIXED_P136_HANDOFF_PATH,
        "evidence_atoms": [atom],
    }
    value.update(overrides)
    return value


def _bundle_with_two_atoms() -> dict[str, Any]:
    value = _bundle()
    first = dict(value["evidence_atoms"][0])
    second = dict(first)
    second.update(
        atom_id="atom-2",
        promotion_record_hash=stable_hash({"promotion": 2}),
        promotion_key=stable_hash({"promotion_key": 2}),
        p136_entry_hash=stable_hash({"entry": 2}),
        source_id="source-2",
        content_hash=stable_hash({"content": 2}),
        ordinal=2,
    )
    second["atom_hash"] = stable_hash({key: item for key, item in second.items() if key != "atom_hash"})
    value["evidence_atoms"] = [first, second]
    return value


def _local_selection_bundle() -> dict[str, Any]:
    value = _bundle()
    atom = dict(value["evidence_atoms"][0])
    atom.update(
        {
            "evidence_state": "denominator_visible_failure",
            "metric_breach_code": "none",
            "state_reason_codes": ["local_catalog_selectable", "p135_adapter_failure"],
            "denominator_visible": True,
        }
    )
    atom["atom_hash"] = stable_hash({key: item for key, item in atom.items() if key != "atom_hash"})
    value["evidence_atoms"] = [atom]
    return value


def _publish_bytes(tmp_path: Path, payload: bytes = b'{"bundle":"one"}\n') -> bytes:
    path = tmp_path / FIXED_P136_HANDOFF_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return payload


def _validator(bundle: dict[str, Any]) -> Any:
    def validate(raw: bytes, *, config: dict[str, Any], p137_checkpoint: dict[str, Any] | None = None) -> dict[str, Any]:
        assert raw
        assert config["p136_handoff_bundle_path"] == FIXED_P136_HANDOFF_PATH
        assert p137_checkpoint is None or p137_checkpoint["schema_version"] == "p137.checkpoint.v1"
        return dict(bundle)

    return validate


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")


def _rehash(value: dict[str, Any], field: str) -> None:
    value[field] = stable_hash({key: item for key, item in value.items() if key != field})


def _forge_extra_atom(tmp_path: Path, config: dict[str, Any]) -> dict[str, Any]:
    atom_path = next((tmp_path / config["journal_dir"] / "atoms").glob("*.json"))
    atom = _read_json(atom_path)
    atom.update(
        {
            "atom_id": "forged-unrelated-atom",
            "promotion_record_hash": stable_hash({"forged": "promotion"}),
            "promotion_key": stable_hash({"forged": "promotion-key"}),
            "p136_entry_hash": stable_hash({"forged": "entry"}),
            "source_id": "forged-source",
            "system_id": "unrelated-system",
            "entity_ref_hash": stable_hash({"forged": "entity"}),
            "content_hash": stable_hash({"forged": "content"}),
            "label_hashes": [stable_hash({"forged": "label"})],
            "redacted_preview_hash": stable_hash({"forged": "preview"}),
            "ordinal": 99,
        }
    )
    _rehash(atom, "atom_hash")
    _write_json(tmp_path / config["journal_dir"] / "atoms" / f"{atom['atom_hash']}.json", atom)
    return atom


def _rewrite_ledger_and_checkpoint(
    tmp_path: Path,
    config: dict[str, Any],
    *,
    incident_hash: str,
    classification_hash: str | None = None,
) -> None:
    ledger_path = tmp_path / config["ledger_path"]
    ledger = _read_json(ledger_path)
    ledger["incident_hashes"][-1] = incident_hash
    if classification_hash is not None:
        ledger["classification_hashes"][-1] = classification_hash
    _rehash(ledger, "ledger_hash")
    _write_json(ledger_path, ledger)

    checkpoint_path = tmp_path / config["checkpoint_path"]
    checkpoint = _read_json(checkpoint_path)
    checkpoint["last_accepted_ledger_hash"] = ledger["ledger_hash"]
    _rehash(checkpoint, "checkpoint_hash")
    _write_json(checkpoint_path, checkpoint)


def _assert_canonical_activity(activity: dict[str, int]) -> None:
    assert set(activity) == set(RUNTIME_ACTIVITY_KEYS)
    assert "p136_validation_count" not in activity
    assert "checkpoint_write_count" not in activity
    assert set(zero_runtime_activity()) == set(activity)


def test_nonblocking_lease_is_acquired_before_any_state_or_handoff_read(tmp_path: Path) -> None:
    api = _api()
    config = _config(tmp_path)
    _publish_bytes(tmp_path)
    checkpoint_path = tmp_path / config["checkpoint_path"]
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_text("not json")
    lease_path = tmp_path / config["lease_path"]
    lease_fd = os.open(lease_path, os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(lease_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        result = api.run_p137_runtime_once(base_path=tmp_path, config=config, validate_handoff=_validator(_bundle()))
    finally:
        fcntl.flock(lease_fd, fcntl.LOCK_UN)
        os.close(lease_fd)

    assert result["status"] == "failed_closed"
    assert result["expected_error"] == "lease_conflict"
    assert result["classification"] == "none"
    assert result["runtime_activity"]["lease_acquire_count"] == 0
    assert result["runtime_activity"]["state_read_count"] == 0
    assert result["runtime_activity"]["handoff_bundle_read_count"] == 0
    _assert_canonical_activity(result["runtime_activity"])
    assert set(result["evaluator_activity"]) == set(EVALUATOR_ACTIVITY_KEYS)
    assert result["authority_counters"] == zero_forbidden_authority()


def test_runtime_rejects_symlinked_state_parent_before_handoff_or_state_write(tmp_path: Path) -> None:
    api = _api()
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "state").symlink_to(outside, target_is_directory=True)
    config = _config(tmp_path)

    with pytest.raises(api.P137RuntimeError, match="runtime_path_symlink_forbidden"):
        api.run_p137_runtime_once(base_path=tmp_path, config=config, validate_handoff=_validator(_bundle()))

    assert list(outside.iterdir()) == []


@pytest.mark.parametrize(
    "crash_after",
    ["ingest_intent", "incident_write", "request_write", "classification_write"],
)
def test_recovery_after_required_crash_points_reuses_deterministic_bytes_once(tmp_path: Path, crash_after: str) -> None:
    api = _api()
    config = _config(tmp_path)
    payload = _publish_bytes(tmp_path)
    bundle = _bundle()

    crashed = api.run_p137_runtime_once(
        base_path=tmp_path,
        config=config,
        validate_handoff=_validator(bundle),
        crash_after=crash_after,
    )
    recovered = api.run_p137_runtime_once(base_path=tmp_path, config=config, validate_handoff=_validator(bundle))
    again = api.run_p137_runtime_once(base_path=tmp_path, config=config, validate_handoff=_validator(bundle))

    assert crashed["status"] == "failed_closed"
    assert crashed["expected_error"] == f"crash_after_{crash_after}"
    assert recovered["status"] == "ok"
    assert again["status"] == "ok"
    assert again["runtime_activity"]["duplicate_atom_count"] == 1
    assert again["runtime_activity"]["recovery_replay_count"] == 1
    assert again["runtime_activity"]["p136_validator_invocation_count"] == 1
    assert again["runtime_activity"]["handoff_bundle_bytes_read"] == len(payload)
    _assert_canonical_activity(again["runtime_activity"])
    checkpoint = _read_json(tmp_path / config["checkpoint_path"])
    ledger = _read_json(tmp_path / config["ledger_path"])
    assert checkpoint["last_accepted_bundle_sequence"] == 1
    assert checkpoint["last_accepted_bundle_hash"] == bundle["bundle_hash"]
    assert checkpoint["last_accepted_ledger_hash"] == ledger["ledger_hash"]
    assert checkpoint["last_accepted_checkpoint_hash"] is None
    assert set(checkpoint) == {
        "schema_version",
        "config_hash",
        "last_accepted_bundle_sequence",
        "last_accepted_bundle_hash",
        "last_accepted_ledger_hash",
        "last_accepted_checkpoint_hash",
        "checkpoint_hash",
    }
    assert len(list((tmp_path / config["journal_dir"] / "intents").glob("*.json"))) == 1
    assert len(list((tmp_path / config["journal_dir"] / "atoms").glob("*.json"))) == 1
    assert len(list((tmp_path / config["classification_dir"]).glob("*.json"))) == 1
    assert recovered["classification"] == "confirmed_incident"
    assert recovered["classifications"][0]["classification"] == "confirmed_incident"


def test_hypothesis_budget_failure_after_incident_is_durably_aborted(tmp_path: Path) -> None:
    api = _api()
    config = _config(tmp_path, limit_overrides={"max_hypotheses_per_incident": 1})
    _publish_bytes(tmp_path)

    result = api.run_p137_runtime_once(
        base_path=tmp_path,
        config=config,
        validate_handoff=_validator(_bundle_with_two_atoms()),
    )

    assert result["status"] == "ok"
    assert result["expected_error"] is None
    assert result["termination_reason"] == "aborted_fail_closed"
    assert result["classification"] == "aborted_fail_closed"
    assert result["classifications"][0]["classification"] == "aborted_fail_closed"
    assert result["classifications"][0]["decision_reasons"] == [
        "hypothesis_budget_exceeded",
        "runtime_failure_closed",
    ]
    assert result["runtime_activity"]["classification_write_count"] == 1
    assert result["runtime_activity"]["ledger_write_count"] == 1


def test_incident_duration_budget_failure_after_correlation_is_durably_aborted(tmp_path: Path) -> None:
    api = _api()
    config = _config(tmp_path, limit_overrides={"max_incident_duration_ms": 1})
    _publish_bytes(tmp_path)

    result = api.run_p137_runtime_once(base_path=tmp_path, config=config, validate_handoff=_validator(_bundle()))

    assert result["classification"] == "aborted_fail_closed"
    assert result["termination_reason"] == "aborted_fail_closed"
    assert result["classifications"][0]["decision_reasons"] == [
        "incident_duration_budget_exceeded",
        "runtime_failure_closed",
    ]
    assert result["runtime_activity"]["classification_write_count"] == 1
    assert result["runtime_activity"]["ledger_write_count"] == 1


def test_incident_duration_budget_failure_never_retries_with_a_wider_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    config = _config(tmp_path, limit_overrides={"max_incident_duration_ms": 1})
    _publish_bytes(tmp_path)
    original = api.correlate_incident_state
    invocations = 0

    def counted(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal invocations
        invocations += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(api, "correlate_incident_state", counted)
    result = api.run_p137_runtime_once(base_path=tmp_path, config=config, validate_handoff=_validator(_bundle()))

    assert result["classification"] == "aborted_fail_closed"
    assert invocations == 1


def test_aborted_classification_crash_before_ledger_recovers_exactly_once(tmp_path: Path) -> None:
    api = _api()
    config = _config(tmp_path, limit_overrides={"max_hypotheses_per_incident": 1})
    _publish_bytes(tmp_path)
    bundle = _bundle_with_two_atoms()

    crashed = api.run_p137_runtime_once(
        base_path=tmp_path,
        config=config,
        validate_handoff=_validator(bundle),
        crash_after="classification_write",
    )
    recovered = api.run_p137_runtime_once(base_path=tmp_path, config=config, validate_handoff=_validator(bundle))
    again = api.run_p137_runtime_once(base_path=tmp_path, config=config, validate_handoff=_validator(bundle))

    assert crashed["expected_error"] == "crash_after_classification_write"
    assert crashed["runtime_activity"]["classification_write_count"] == 1
    assert crashed["runtime_activity"]["ledger_write_count"] == 0
    assert recovered["classification"] == "aborted_fail_closed"
    assert recovered["termination_reason"] == "aborted_fail_closed"
    assert recovered["runtime_activity"]["classification_write_count"] == 0
    assert recovered["runtime_activity"]["ledger_write_count"] == 1
    assert again["classification"] == "none"
    assert again["runtime_activity"]["recovery_replay_count"] == 1
    assert len(list((tmp_path / config["classification_dir"]).glob("*.json"))) == 1
    assert len(recovered["ledger"]["classification_hashes"]) == 1


def test_request_write_crash_reuses_durable_selection_after_revalidation(tmp_path: Path) -> None:
    api = _api()
    config = _config(tmp_path)
    _publish_bytes(tmp_path)
    bundle = _local_selection_bundle()

    crashed = api.run_p137_runtime_once(
        base_path=tmp_path,
        config=config,
        validate_handoff=_validator(bundle),
        crash_after="request_write",
    )
    request_path = next((tmp_path / config["request_dir"]).glob("*.json"))
    durable_bytes = request_path.read_bytes()
    durable_request = json.loads(durable_bytes)
    recovered = api.run_p137_runtime_once(base_path=tmp_path, config=config, validate_handoff=_validator(bundle))

    assert crashed["expected_error"] == "crash_after_request_write"
    assert crashed["runtime_activity"]["evidence_request_write_count"] == 1
    assert recovered["status"] == "ok"
    assert recovered["requests"] == [durable_request]
    assert recovered["runtime_activity"]["evidence_request_write_count"] == 0
    assert recovered["runtime_activity"]["attempted_request_hash_write_count"] == 0
    assert list((tmp_path / config["request_dir"]).glob("*.json")) == [request_path]
    assert request_path.read_bytes() == durable_bytes


def test_ledger_checkpoint_split_commit_recovers_without_replaying_completed_work(tmp_path: Path) -> None:
    api = _api()
    config = _config(tmp_path)
    _publish_bytes(tmp_path)
    bundle = _local_selection_bundle()

    crashed = api.run_p137_runtime_once(
        base_path=tmp_path,
        config=config,
        validate_handoff=_validator(bundle),
        crash_after="ledger_write",
    )
    ledger_path = tmp_path / config["ledger_path"]
    ledger_bytes = ledger_path.read_bytes()
    ledger = json.loads(ledger_bytes)

    assert crashed["expected_error"] == "crash_after_ledger_write"
    assert crashed["runtime_activity"]["ledger_write_count"] == 1
    assert not (tmp_path / config["checkpoint_path"]).exists()

    recovered = api.run_p137_runtime_once(base_path=tmp_path, config=config, validate_handoff=_validator(bundle))

    assert recovered["status"] == "ok"
    assert recovered["termination_reason"] == "recovered_split_commit"
    assert recovered["runtime_activity"]["recovery_replay_count"] == 1
    assert recovered["runtime_activity"]["evidence_request_write_count"] == 0
    assert recovered["runtime_activity"]["attempted_request_hash_write_count"] == 0
    assert recovered["runtime_activity"]["classification_write_count"] == 0
    assert recovered["runtime_activity"]["ledger_write_count"] == 0
    assert ledger_path.read_bytes() == ledger_bytes
    checkpoint = _read_json(tmp_path / config["checkpoint_path"])
    assert checkpoint["last_accepted_ledger_hash"] == ledger["ledger_hash"]

    replayed = api.run_p137_runtime_once(base_path=tmp_path, config=config, validate_handoff=_validator(bundle))
    assert replayed["termination_reason"] == "reused_bundle"
    assert replayed["classification"] == "none"
    assert replayed["runtime_activity"]["ledger_write_count"] == 0


def test_second_cycle_split_commit_recovers_only_checkpoint_and_rejects_a_fork(tmp_path: Path) -> None:
    api = _api()
    config = _config(tmp_path)
    _publish_bytes(tmp_path)
    first_bundle = _bundle(sequence=1)
    first = api.run_p137_runtime_once(base_path=tmp_path, config=config, validate_handoff=_validator(first_bundle))
    first_checkpoint_hash = first["checkpoint"]["checkpoint_hash"]
    second_bundle = _bundle(sequence=2, previous=first_bundle["bundle_hash"])

    crashed = api.run_p137_runtime_once(
        base_path=tmp_path,
        config=config,
        validate_handoff=_validator(second_bundle),
        crash_after="ledger_write",
    )
    fork = dict(second_bundle)
    fork["bundle_hash"] = stable_hash({"fork": "second-cycle"})
    rejected = api.run_p137_runtime_once(base_path=tmp_path, config=config, validate_handoff=_validator(fork))
    recovered = api.run_p137_runtime_once(base_path=tmp_path, config=config, validate_handoff=_validator(second_bundle))

    assert crashed["expected_error"] == "crash_after_ledger_write"
    assert rejected["expected_error"] == "p137_state_corrupt_hash_mismatch"
    assert rejected["termination_reason"] == "corrupt_state"
    assert recovered["termination_reason"] == "recovered_split_commit"
    assert recovered["checkpoint"]["last_accepted_bundle_sequence"] == 2
    assert recovered["checkpoint"]["last_accepted_checkpoint_hash"] == first_checkpoint_hash
    assert recovered["checkpoint"]["last_accepted_ledger_hash"] == recovered["ledger"]["ledger_hash"]
    assert recovered["runtime_activity"]["classification_write_count"] == 0
    assert recovered["runtime_activity"]["ledger_write_count"] == 0


def test_checkpoint_rejects_rollback_fork_and_previous_hash_discontinuity_without_advancing_ledger(tmp_path: Path) -> None:
    api = _api()
    config = _config(tmp_path)
    _publish_bytes(tmp_path)
    first = _bundle(sequence=1)
    accepted = api.run_p137_runtime_once(base_path=tmp_path, config=config, validate_handoff=_validator(first))
    ledger_hash = accepted["ledger"]["ledger_hash"]

    rollback = api.run_p137_runtime_once(base_path=tmp_path, config=config, validate_handoff=_validator(first))
    fork = _bundle(sequence=1, bundle_hash=stable_hash({"fork": 1}))
    forked = api.run_p137_runtime_once(base_path=tmp_path, config=config, validate_handoff=_validator(fork))
    discontinuity = _bundle(sequence=2, previous=stable_hash({"wrong": "previous"}))
    broken = api.run_p137_runtime_once(base_path=tmp_path, config=config, validate_handoff=_validator(discontinuity))

    assert rollback["status"] == "ok"
    assert rollback["reused_bundle"] is True
    assert forked["expected_error"] == "p136_handoff_same_sequence_fork"
    assert broken["expected_error"] == "p136_handoff_previous_hash_discontinuity"
    assert _read_json(tmp_path / config["ledger_path"])["ledger_hash"] == ledger_hash


def test_runtime_fails_closed_when_ledger_terminal_incident_is_missing_from_durable_state(tmp_path: Path) -> None:
    api = _api()
    config = _config(tmp_path)
    _publish_bytes(tmp_path)
    accepted = api.run_p137_runtime_once(base_path=tmp_path, config=config, validate_handoff=_validator(_bundle()))
    incident_hash = accepted["ledger"]["incident_hashes"][-1]
    (tmp_path / config["incident_dir"] / f"{incident_hash}.json").unlink()

    result = api.run_p137_runtime_once(base_path=tmp_path, config=config, validate_handoff=_validator(_bundle()))

    assert result["status"] == "failed_closed"
    assert result["expected_error"] == "p137_state_corrupt_hash_mismatch"
    assert result["termination_reason"] == "corrupt_state"


def test_runtime_fails_closed_when_classification_top_hypothesis_is_missing(tmp_path: Path) -> None:
    api = _api()
    config = _config(tmp_path)
    _publish_bytes(tmp_path)
    accepted = api.run_p137_runtime_once(base_path=tmp_path, config=config, validate_handoff=_validator(_bundle()))
    hypothesis_hash = accepted["classifications"][0]["top_hypothesis_hash"]
    assert hypothesis_hash is not None
    (tmp_path / config["hypothesis_dir"] / f"{hypothesis_hash}.json").unlink()

    result = api.run_p137_runtime_once(base_path=tmp_path, config=config, validate_handoff=_validator(_bundle()))

    assert result["status"] == "failed_closed"
    assert result["expected_error"] == "p137_state_corrupt_hash_mismatch"
    assert result["termination_reason"] == "corrupt_state"


def test_runtime_fails_closed_when_ledger_request_is_missing_from_durable_state(tmp_path: Path) -> None:
    api = _api()
    config = _config(tmp_path)
    _publish_bytes(tmp_path)
    accepted = api.run_p137_runtime_once(
        base_path=tmp_path,
        config=config,
        validate_handoff=_validator(_local_selection_bundle()),
    )
    attempt_hash = accepted["ledger"]["attempted_request_hashes"][-1]
    request = next(item for item in accepted["requests"] if item["attempted_request_hash"] == attempt_hash)
    (tmp_path / config["request_dir"] / f"{request['request_hash']}.json").unlink()

    result = api.run_p137_runtime_once(
        base_path=tmp_path,
        config=config,
        validate_handoff=_validator(_local_selection_bundle()),
    )

    assert result["status"] == "failed_closed"
    assert result["expected_error"] == "p137_state_corrupt_hash_mismatch"
    assert result["termination_reason"] == "corrupt_state"


def test_runtime_rejects_forged_rehashed_hypothesis_edge_to_unrelated_atom(tmp_path: Path) -> None:
    api = _api()
    config = _config(tmp_path)
    _publish_bytes(tmp_path)
    accepted = api.run_p137_runtime_once(base_path=tmp_path, config=config, validate_handoff=_validator(_bundle()))
    unrelated = _forge_extra_atom(tmp_path, config)

    hypothesis_path = tmp_path / config["hypothesis_dir"] / f"{accepted['classifications'][0]['top_hypothesis_hash']}.json"
    hypothesis = _read_json(hypothesis_path)
    hypothesis["support"][0]["evidence_atom_hash"] = unrelated["atom_hash"]
    _rehash(hypothesis["support"][0], "edge_hash")
    _rehash(hypothesis, "hypothesis_hash")
    _write_json(hypothesis_path, hypothesis)

    classification_path = tmp_path / config["classification_dir"] / f"{accepted['classifications'][0]['classification_hash']}.json"
    classification = _read_json(classification_path)
    classification["top_hypothesis_hash"] = hypothesis["hypothesis_hash"]
    classification["support_summary_hashes"] = [hypothesis["support"][0]["edge_hash"]]
    _rehash(classification, "classification_hash")
    _write_json(classification_path, classification)

    incident_path = tmp_path / config["incident_dir"] / f"{accepted['ledger']['incident_hashes'][-1]}.json"
    incident = _read_json(incident_path)
    incident["hypothesis_hashes"] = [hypothesis["hypothesis_hash"]]
    incident["classification_hash"] = classification["classification_hash"]
    _rehash(incident, "incident_hash")
    _write_json(incident_path, incident)
    _rewrite_ledger_and_checkpoint(
        tmp_path,
        config,
        incident_hash=incident["incident_hash"],
        classification_hash=classification["classification_hash"],
    )

    result = api.run_p137_runtime_once(base_path=tmp_path, config=config, validate_handoff=_validator(_bundle()))

    assert result["status"] == "failed_closed"
    assert result["expected_error"] == "p137_state_corrupt_hash_mismatch"
    assert result["termination_reason"] == "corrupt_state"


def test_runtime_rejects_forged_rehashed_request_match_to_unrelated_atom(tmp_path: Path) -> None:
    api = _api()
    config = _config(tmp_path)
    _publish_bytes(tmp_path)
    bundle = _local_selection_bundle()
    accepted = api.run_p137_runtime_once(base_path=tmp_path, config=config, validate_handoff=_validator(bundle))
    unrelated = _forge_extra_atom(tmp_path, config)

    request_path = next((tmp_path / config["request_dir"]).glob("*.json"))
    request = _read_json(request_path)
    request["result_summary"]["matched_atom_hashes"].append(unrelated["atom_hash"])
    request["result_summary"]["matched_atom_hashes"].sort()
    request["result_summary"]["output_count"] = len(request["result_summary"]["matched_atom_hashes"])
    request["runtime_activity"]["output_records_selected"] = request["result_summary"]["output_count"]
    _rehash(request, "request_hash")
    _write_json(request_path, request)

    incident_path = tmp_path / config["incident_dir"] / f"{accepted['ledger']['incident_hashes'][-1]}.json"
    incident = _read_json(incident_path)
    incident["request_hashes"] = [request["request_hash"]]
    _rehash(incident, "incident_hash")
    _write_json(incident_path, incident)
    _rewrite_ledger_and_checkpoint(tmp_path, config, incident_hash=incident["incident_hash"])

    result = api.run_p137_runtime_once(base_path=tmp_path, config=config, validate_handoff=_validator(bundle))

    assert result["status"] == "failed_closed"
    assert result["expected_error"] == "p137_state_corrupt_hash_mismatch"
    assert result["termination_reason"] == "corrupt_state"


def test_runtime_rejects_rehashed_durable_atom_with_invalid_enum(tmp_path: Path) -> None:
    api = _api()
    config = _config(tmp_path)
    _publish_bytes(tmp_path)
    api.run_p137_runtime_once(base_path=tmp_path, config=config, validate_handoff=_validator(_bundle()))

    atom_path = next((tmp_path / config["journal_dir"] / "atoms").glob("*.json"))
    atom = _read_json(atom_path)
    atom["evidence_state"] = "promoted_later"
    _rehash(atom, "atom_hash")
    atom_path.unlink()
    _write_json(tmp_path / config["journal_dir"] / "atoms" / f"{atom['atom_hash']}.json", atom)

    result = api.run_p137_runtime_once(base_path=tmp_path, config=config, validate_handoff=_validator(_bundle()))

    assert result["status"] == "failed_closed"
    assert result["expected_error"] == "p137_state_corrupt_hash_mismatch"
    assert result["termination_reason"] == "corrupt_state"


def test_runtime_rejects_forged_rehashed_request_that_omits_catalog_match(tmp_path: Path) -> None:
    api = _api()
    config = _config(tmp_path)
    _publish_bytes(tmp_path)
    bundle = _local_selection_bundle()
    first = dict(bundle["evidence_atoms"][0])
    second = dict(first)
    second.update(
        atom_id="atom-2",
        promotion_record_hash=stable_hash({"promotion": "local-2"}),
        promotion_key=stable_hash({"promotion_key": "local-2"}),
        p136_entry_hash=stable_hash({"entry": "local-2"}),
        source_id="source-2",
        content_hash=stable_hash({"content": "local-2"}),
        ordinal=2,
    )
    second["atom_hash"] = stable_hash({key: item for key, item in second.items() if key != "atom_hash"})
    bundle["evidence_atoms"] = [first, second]
    accepted = api.run_p137_runtime_once(base_path=tmp_path, config=config, validate_handoff=_validator(bundle))
    assert len(accepted["requests"][0]["result_summary"]["matched_atom_hashes"]) == 2

    request_path = tmp_path / config["request_dir"] / f"{accepted['requests'][0]['request_hash']}.json"
    request = _read_json(request_path)
    request["result_summary"]["matched_atom_hashes"] = request["result_summary"]["matched_atom_hashes"][:1]
    request["result_summary"]["output_count"] = 1
    request["runtime_activity"]["output_records_selected"] = 1
    _rehash(request, "request_hash")
    request_path.unlink()
    _write_json(tmp_path / config["request_dir"] / f"{request['request_hash']}.json", request)

    incident_path = tmp_path / config["incident_dir"] / f"{accepted['ledger']['incident_hashes'][-1]}.json"
    incident = _read_json(incident_path)
    incident["request_hashes"] = [request["request_hash"]]
    _rehash(incident, "incident_hash")
    _write_json(incident_path, incident)
    _rewrite_ledger_and_checkpoint(tmp_path, config, incident_hash=incident["incident_hash"])

    result = api.run_p137_runtime_once(base_path=tmp_path, config=config, validate_handoff=_validator(bundle))

    assert result["status"] == "failed_closed"
    assert result["expected_error"] == "p137_state_corrupt_hash_mismatch"
    assert result["termination_reason"] == "corrupt_state"


def test_runtime_rejects_forged_rehashed_wrong_classification(tmp_path: Path) -> None:
    api = _api()
    config = _config(tmp_path)
    _publish_bytes(tmp_path)
    accepted = api.run_p137_runtime_once(base_path=tmp_path, config=config, validate_handoff=_validator(_bundle()))

    classification_path = tmp_path / config["classification_dir"] / f"{accepted['classifications'][0]['classification_hash']}.json"
    classification = _read_json(classification_path)
    classification["classification"] = "benign_anomaly"
    classification["confidence_code"] = "benign_supported"
    classification["decision_reasons"] = ["supported_benign_pattern"]
    _rehash(classification, "classification_hash")
    _write_json(classification_path, classification)

    incident_path = tmp_path / config["incident_dir"] / f"{accepted['ledger']['incident_hashes'][-1]}.json"
    incident = _read_json(incident_path)
    incident["status"] = "benign_anomaly"
    incident["classification_hash"] = classification["classification_hash"]
    _rehash(incident, "incident_hash")
    _write_json(incident_path, incident)
    _rewrite_ledger_and_checkpoint(
        tmp_path,
        config,
        incident_hash=incident["incident_hash"],
        classification_hash=classification["classification_hash"],
    )

    result = api.run_p137_runtime_once(base_path=tmp_path, config=config, validate_handoff=_validator(_bundle()))

    assert result["status"] == "failed_closed"
    assert result["expected_error"] == "p137_state_corrupt_hash_mismatch"
    assert result["termination_reason"] == "corrupt_state"


def test_runtime_rejects_checkpoint_ledger_hash_outside_current_or_previous_lineage(tmp_path: Path) -> None:
    api = _api()
    config = _config(tmp_path)
    _publish_bytes(tmp_path)
    api.run_p137_runtime_once(base_path=tmp_path, config=config, validate_handoff=_validator(_bundle()))
    checkpoint_path = tmp_path / config["checkpoint_path"]
    checkpoint = _read_json(checkpoint_path)
    checkpoint["last_accepted_ledger_hash"] = stable_hash({"detached": "ledger"})
    checkpoint["checkpoint_hash"] = stable_hash({key: value for key, value in checkpoint.items() if key != "checkpoint_hash"})
    checkpoint_path.write_text(json.dumps(checkpoint, sort_keys=True, separators=(",", ":")) + "\n")

    result = api.run_p137_runtime_once(base_path=tmp_path, config=config, validate_handoff=_validator(_bundle()))

    assert result["status"] == "failed_closed"
    assert result["expected_error"] == "p137_state_corrupt_hash_mismatch"
    assert result["termination_reason"] == "corrupt_state"


def test_runtime_executes_bounded_local_selection_before_insufficient_classification(tmp_path: Path) -> None:
    api = _api()
    config = _config(tmp_path)
    _publish_bytes(tmp_path)
    bundle = _local_selection_bundle()

    result = api.run_p137_runtime_once(base_path=tmp_path, config=config, validate_handoff=_validator(bundle))

    assert result["status"] == "ok"
    assert result["classification"] == "insufficient_evidence"
    assert len(result["requests"]) == 1
    assert result["requests"][0]["catalog_name"] == "select_records_by_system_id"
    assert result["requests"][0]["runtime_activity"]["external_call_count"] == 0
    assert result["runtime_activity"]["evidence_request_write_count"] == 1
    assert result["runtime_activity"]["attempted_request_hash_write_count"] == 1
    stored_atom = _read_json(next((tmp_path / config["journal_dir"] / "atoms").glob("*.json")))
    stored_request = _read_json(next((tmp_path / config["request_dir"]).glob("*.json")))
    assert stored_atom["schema_version"] == "p137.evidence_atom.v1"
    assert stored_request["schema_version"] == "p137.evidence_request.v1"
    assert "payload" not in stored_atom and "payload" not in stored_request


def test_bounded_continuous_loop_writes_heartbeat_readiness_and_stale_handoff_state(tmp_path: Path) -> None:
    api = _api()
    config = _config(tmp_path, continuous_mode=True)
    _publish_bytes(tmp_path)
    stale = _bundle(sequence=1)

    result = api.run_p137_runtime_loop(
        base_path=tmp_path,
        config=config,
        validate_handoff=_validator(stale),
        now_values=["2026-07-14T00:00:00Z", "2026-07-14T00:00:01Z"],
    )

    assert result["cycles_completed"] == 2
    assert result["bounded"] is True
    heartbeat = _read_json(tmp_path / config["heartbeat_path"])
    readiness = _read_json(tmp_path / config["readiness_path"])
    assert heartbeat["cycle_sequence"] == 2
    assert heartbeat["readiness_state"] == "stale"
    assert readiness["status"] == "stale"
    assert readiness["last_accepted_bundle_hash"] == stale["bundle_hash"]


def test_sigint_sigterm_set_stop_flag_and_terminate_only_at_safe_boundary(tmp_path: Path) -> None:
    api = _api()
    config = _config(tmp_path)
    _publish_bytes(tmp_path)
    stop = api.P137StopController()

    stop.handle_signal(signal.SIGTERM, None)
    result = api.run_p137_runtime_once(
        base_path=tmp_path,
        config=config,
        validate_handoff=_validator(_bundle()),
        stop_controller=stop,
    )

    assert result["status"] == "stopped"
    assert result["classification"] == "none"
    assert result["expected_error"] == "signal_before_handoff_safe_boundary"
    assert result["termination_reason"] == "sigterm"
    assert result["runtime_activity"]["termination_receipt_write_count"] == 1
    assert result["authority_counters"] == zero_forbidden_authority()
    assert set(result["termination"]) == {
        "schema_version",
        "agent_id",
        "config_hash",
        "stop_reason",
        "safe_boundary",
        "last_valid_ledger_hash",
        "open_incident_hashes",
        "terminal_classification_hashes",
        "runtime_activity",
        "evaluator_activity",
        "resource_usage",
        "authority_counters",
        "termination_hash",
    }


def test_sigterm_at_classification_boundary_never_writes_terminal_classification(tmp_path: Path) -> None:
    api = _api()
    config = _config(tmp_path)
    _publish_bytes(tmp_path)
    stop = api.P137StopController()
    stop.handle_signal(signal.SIGTERM, None)

    result = api.run_p137_runtime_once(
        base_path=tmp_path,
        config=config,
        validate_handoff=_validator(_bundle()),
        stop_controller=stop,
        stop_before="classification",
    )

    assert result["expected_error"] == "signal_before_classification_unsafe"
    assert result["termination_reason"] == "sigterm"
    assert result["classification"] == "none"
    assert result["runtime_activity"]["incident_write_count"] > 0
    assert result["runtime_activity"]["classification_write_count"] == 0
    assert result["runtime_activity"]["ledger_write_count"] == 0


def test_measured_resource_limit_stops_before_classification_write(tmp_path: Path) -> None:
    api = _api()
    config = _config(tmp_path)
    _publish_bytes(tmp_path)

    result = api.run_p137_runtime_once(
        base_path=tmp_path,
        config=config,
        validate_handoff=_validator(_bundle()),
        resource_probe=lambda: {
            "wall_time_ms": int(config["limits"]["max_cycle_wall_ms"]) + 1,
            "cpu_time_ms": 0,
            "child_cpu_time_ms": 0,
            "peak_memory_bytes": 0,
            "wall_limit_ms": int(config["limits"]["max_cycle_wall_ms"]),
            "cpu_limit_ms": int(config["limits"]["max_cpu_ms"]),
            "peak_memory_limit_bytes": int(config["limits"]["max_peak_memory_bytes"]),
        },
    )

    assert result["expected_error"] == "resource_limit_exceeded"
    assert result["termination_reason"] == "resource_exhausted"
    assert result["classification"] == "none"
    assert result["runtime_activity"]["classification_write_count"] == 0
    assert result["runtime_activity"]["ledger_write_count"] == 0
    assert result["runtime_activity"]["termination_receipt_write_count"] == 1
