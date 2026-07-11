"""P113 taint ledger and fresh-blind governance."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import Any

from app.services.p110_evaluation import stable_hash

TAINT_LEDGER_SCHEMA_VERSION = "p113.taint_ledger.v1"
FREEZE_SCHEMA_VERSION = "p113.fresh_blind_freeze.v1"
P113_OFFICIAL_TT_SOURCE_HASH = "sha256:2b33b7ab07198e0d69f229e697bfcef794a656e8db73a1d732142effde17c595"
P112_REP4_PROHIBITED_INPUTS = frozenset(
    {
        "training",
        "selection",
        "fixtures",
        "prompts",
        "thresholds",
        "weights",
        "release_counting",
    }
)
P112_CASE_LEVEL_ARTIFACTS = frozenset(
    {
        "case_result",
        "case_id",
        "feature_choice",
        "fault_identity",
        "fixture",
        "label",
        "labels",
        "per_case_error",
        "prompt_example",
        "service_identity",
        "threshold",
        "weight",
    }
)
REQUIRED_FREEZE_HASH_FIELDS = (
    "model_hash",
    "p112_baseline_hash",
    "diagnosis_packet_hash",
    "narrative_packet_hash",
    "system_prompt_hash",
    "endpoint_hash",
    "decoding_hash",
    "code_hash",
    "gates_hash",
)
_ALLOWED_AGGREGATE_FACT_KEYS = frozenset({"source_hash", "fact_id", "fact_value", "granularity", "artifact_type"})


class P113GovernanceError(ValueError):
    """Raised when P113 release inputs violate the governance contract."""


def build_p113_taint_ledger(
    *,
    consumed_p112_source_hashes: Sequence[str],
    allowed_p112_final_summary_facts: Mapping[str, str],
) -> dict[str, Any]:
    """Build a machine-readable ledger for consumed P112 facts allowed into P113."""

    if not consumed_p112_source_hashes:
        raise P113GovernanceError("missing_consumed_p112_sources")
    if not allowed_p112_final_summary_facts:
        raise P113GovernanceError("missing_allowed_p112_final_summary_facts")

    payload: dict[str, Any] = {
        "schema_version": TAINT_LEDGER_SCHEMA_VERSION,
        "consumed_phase": "P112",
        "consumed_blind_system": "RE1-OB",
        "consumed_blind_repetition": 4,
        "consumed_p112_source_hashes": sorted(str(item) for item in consumed_p112_source_hashes),
        "allowed_p112_final_summary_facts": {str(key): str(value) for key, value in sorted(allowed_p112_final_summary_facts.items())},
        "allowed_p112_granularity": "aggregate_final_summary",
        "prohibited_inputs": sorted(P112_REP4_PROHIBITED_INPUTS),
        "prohibited_artifact_types": sorted(P112_CASE_LEVEL_ARTIFACTS),
    }
    payload["ledger_hash"] = stable_hash(payload)
    return payload


def validate_p113_release_inputs(taint_ledger: Mapping[str, Any], release_inputs: Mapping[str, Sequence[Mapping[str, Any]]]) -> None:
    """Reject tainted P112 repetition-4 material from P113 release-counting inputs."""

    _validate_taint_ledger(taint_ledger)
    consumed_hashes = {str(item) for item in _sequence(taint_ledger.get("consumed_p112_source_hashes", ()))}
    allowed_facts = {str(key): str(value) for key, value in _mapping(taint_ledger.get("allowed_p112_final_summary_facts", {})).items()}

    for input_name, artifacts in release_inputs.items():
        normalized_input = str(input_name)
        for artifact in artifacts:
            artifact_type = str(artifact.get("artifact_type", ""))
            if normalized_input in P112_REP4_PROHIBITED_INPUTS and artifact_type in P112_CASE_LEVEL_ARTIFACTS and not _has_case_level_provenance(artifact):
                raise P113GovernanceError("unproven_case_level_provenance")
            is_p112_rep4 = _is_p112_rep4_artifact(artifact, consumed_hashes)
            if is_p112_rep4 and normalized_input in P112_REP4_PROHIBITED_INPUTS:
                raise P113GovernanceError(f"tainted_p112_rep4:{normalized_input}")
            if is_p112_rep4:
                _validate_allowed_p112_aggregate_fact(artifact, allowed_facts)


def build_p113_freeze(
    *,
    tt_source_hash: str,
    tt_cases: Sequence[Mapping[str, Any]],
    train_case_ids: Sequence[str],
    dev_case_ids: Sequence[str],
    model_hash: str,
    p112_baseline_hash: str,
    diagnosis_packet_hash: str,
    narrative_packet_hash: str,
    system_prompt_hash: str,
    endpoint_hash: str,
    decoding_hash: str,
    code_hash: str,
    gates_hash: str,
    frozen_at: str,
) -> dict[str, Any]:
    """Freeze P113 TT inputs before any truth scoring."""

    tt_case_ids = _validate_tt_cases(tt_source_hash=tt_source_hash, tt_cases=tt_cases, train_case_ids=train_case_ids, dev_case_ids=dev_case_ids)
    _parse_timestamp(frozen_at, field_name="frozen_at")
    payload: dict[str, Any] = {
        "schema_version": FREEZE_SCHEMA_VERSION,
        "status": "frozen",
        "benchmark_role": "fresh_blind",
        "tt_source_hash": tt_source_hash,
        "tt_case_count": 125,
        "tt_case_ids_hash": stable_hash(tt_case_ids),
        "train_case_ids_hash": stable_hash(sorted(str(item) for item in train_case_ids)),
        "dev_case_ids_hash": stable_hash(sorted(str(item) for item in dev_case_ids)),
        "model_hash": model_hash,
        "p112_baseline_hash": p112_baseline_hash,
        "diagnosis_packet_hash": diagnosis_packet_hash,
        "narrative_packet_hash": narrative_packet_hash,
        "system_prompt_hash": system_prompt_hash,
        "endpoint_hash": endpoint_hash,
        "decoding_hash": decoding_hash,
        "code_hash": code_hash,
        "gates_hash": gates_hash,
        "frozen_at": frozen_at,
        "narrative_subset_case_ids": list(select_p113_narrative_subset(tt_cases)),
        "action_contract_status": "disabled",
        "action_execution_enabled": False,
        "credential_access_enabled": False,
        "auth_authority": "none",
    }
    _validate_required_hashes(payload)
    payload["freeze_hash"] = stable_hash(payload)
    return payload


def validate_p113_blind_governance(
    frozen: Mapping[str, Any],
    *,
    tt_source_hash: str,
    tt_cases: Sequence[Mapping[str, Any]],
    train_case_ids: Sequence[str],
    dev_case_ids: Sequence[str],
    scoring_started_at: str,
) -> None:
    """Validate that P113 TT scoring is fresh, complete, frozen, and authority-free."""

    if tt_source_hash != P113_OFFICIAL_TT_SOURCE_HASH or frozen.get("tt_source_hash") != P113_OFFICIAL_TT_SOURCE_HASH:
        raise P113GovernanceError("tt_source_not_fresh")
    if frozen.get("schema_version") != FREEZE_SCHEMA_VERSION or frozen.get("status") != "frozen":
        raise P113GovernanceError("invalid_freeze_manifest")
    _validate_no_authority(frozen)

    scoring_started = _parse_timestamp(scoring_started_at, field_name="scoring_started_at")
    frozen_at = _parse_timestamp(str(frozen.get("frozen_at", "")), field_name="frozen_at")
    if scoring_started <= frozen_at:
        raise P113GovernanceError("score_before_freeze")

    submitted_hash = str(frozen.get("freeze_hash", ""))
    unhashed = {key: value for key, value in frozen.items() if key != "freeze_hash"}
    if submitted_hash != stable_hash(unhashed):
        raise P113GovernanceError("freeze_manifest_tampered")

    expected = build_p113_freeze(
        tt_source_hash=tt_source_hash,
        tt_cases=tt_cases,
        train_case_ids=train_case_ids,
        dev_case_ids=dev_case_ids,
        model_hash=str(frozen.get("model_hash", "")),
        p112_baseline_hash=str(frozen.get("p112_baseline_hash", "")),
        diagnosis_packet_hash=str(frozen.get("diagnosis_packet_hash", "")),
        narrative_packet_hash=str(frozen.get("narrative_packet_hash", "")),
        system_prompt_hash=str(frozen.get("system_prompt_hash", "")),
        endpoint_hash=str(frozen.get("endpoint_hash", "")),
        decoding_hash=str(frozen.get("decoding_hash", "")),
        code_hash=str(frozen.get("code_hash", "")),
        gates_hash=str(frozen.get("gates_hash", "")),
        frozen_at=str(frozen.get("frozen_at", "")),
    )
    for key, value in expected.items():
        if key == "freeze_hash":
            continue
        if frozen.get(key) != value:
            raise P113GovernanceError(f"freeze_mismatch:{key}")


def select_p113_narrative_subset(tt_cases: Sequence[Mapping[str, Any]], *, size: int = 25) -> tuple[str, ...]:
    """Select a deterministic narrative subset from frozen case IDs only."""

    if size != 25:
        raise P113GovernanceError("narrative_subset_size_must_be_25")
    case_ids = _case_ids_from_cases(tt_cases)
    if len(case_ids) < size:
        raise P113GovernanceError("insufficient_narrative_subset_cases")
    ranked = sorted(case_ids, key=lambda case_id: (stable_hash({"p113_narrative_subset_v1": case_id}), case_id))
    return tuple(sorted(ranked[:size]))


def _validate_taint_ledger(taint_ledger: Mapping[str, Any]) -> None:
    if taint_ledger.get("schema_version") != TAINT_LEDGER_SCHEMA_VERSION:
        raise P113GovernanceError("invalid_taint_ledger")
    submitted_hash = str(taint_ledger.get("ledger_hash", ""))
    unhashed = {key: value for key, value in taint_ledger.items() if key != "ledger_hash"}
    if submitted_hash != stable_hash(unhashed):
        raise P113GovernanceError("taint_ledger_tampered")


def _validate_allowed_p112_aggregate_fact(artifact: Mapping[str, Any], allowed_facts: Mapping[str, str]) -> None:
    if str(artifact.get("granularity", "")) != "aggregate_final_summary":
        raise P113GovernanceError("tainted_p112_case_level_material")
    if set(str(key) for key in artifact) != _ALLOWED_AGGREGATE_FACT_KEYS:
        raise P113GovernanceError("aggregate_fact_schema_violation")
    if str(artifact.get("artifact_type", "")) != "aggregate_final_summary_fact":
        raise P113GovernanceError("aggregate_fact_schema_violation")
    fact_id = str(artifact.get("fact_id", ""))
    if fact_id not in allowed_facts:
        raise P113GovernanceError("undeclared_p112_final_summary_fact")
    if str(artifact.get("fact_value", "")) != allowed_facts[fact_id]:
        raise P113GovernanceError("aggregate_fact_content_mismatch")


def _is_p112_rep4_artifact(artifact: Mapping[str, Any], consumed_hashes: set[str]) -> bool:
    source_hash = str(artifact.get("source_hash", ""))
    system = str(artifact.get("system", "")).upper()
    repetition = artifact.get("repetition")
    artifact_type = str(artifact.get("artifact_type", ""))
    return source_hash in consumed_hashes or (system == "RE1-OB" and repetition == 4) or (artifact_type in P112_CASE_LEVEL_ARTIFACTS and source_hash in consumed_hashes)


def _has_case_level_provenance(artifact: Mapping[str, Any]) -> bool:
    source_hash = str(artifact.get("source_hash", ""))
    system = str(artifact.get("system", ""))
    repetition = artifact.get("repetition")
    return bool(source_hash) or (bool(system) and isinstance(repetition, int) and not isinstance(repetition, bool))


def _validate_tt_cases(
    *,
    tt_source_hash: str,
    tt_cases: Sequence[Mapping[str, Any]],
    train_case_ids: Sequence[str],
    dev_case_ids: Sequence[str],
) -> tuple[str, ...]:
    if tt_source_hash != P113_OFFICIAL_TT_SOURCE_HASH:
        raise P113GovernanceError("tt_source_not_fresh")
    case_ids = _case_ids_from_cases(tt_cases)
    if len(case_ids) != 125 or len(set(case_ids)) != 125:
        raise P113GovernanceError("tt_case_count_or_uniqueness")
    consumed_ids = {str(item) for item in train_case_ids} | {str(item) for item in dev_case_ids}
    if set(case_ids) & consumed_ids:
        raise P113GovernanceError("tt_overlaps_train_or_dev")
    return tuple(sorted(case_ids))


def _case_ids_from_cases(tt_cases: Sequence[Mapping[str, Any]]) -> list[str]:
    case_ids = [str(item.get("case_id", "")) for item in tt_cases]
    if not all(case_ids):
        raise P113GovernanceError("missing_case_id")
    return case_ids


def _validate_required_hashes(payload: Mapping[str, Any]) -> None:
    for field in REQUIRED_FREEZE_HASH_FIELDS:
        value = str(payload.get(field, ""))
        if not value.startswith(("sha256:", "md5:")):
            raise P113GovernanceError(f"invalid_freeze_hash:{field}")


def _validate_no_authority(frozen: Mapping[str, Any]) -> None:
    if frozen.get("action_contract_status") != "disabled":
        raise P113GovernanceError("action_authority_enabled")
    if frozen.get("action_execution_enabled") is not False:
        raise P113GovernanceError("action_authority_enabled")
    if frozen.get("credential_access_enabled") is not False:
        raise P113GovernanceError("auth_authority_enabled")
    if frozen.get("auth_authority") != "none":
        raise P113GovernanceError("auth_authority_enabled")


def _parse_timestamp(value: str, *, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise P113GovernanceError(f"invalid_timestamp:{field_name}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise P113GovernanceError(f"timezone_required:{field_name}")
    return parsed


def _sequence(value: Any) -> Iterable[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, str) else ()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
