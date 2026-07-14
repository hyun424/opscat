"""P136-owned P137 handoff publisher and P137 validation adapter."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path, PurePosixPath
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p136_incremental_observer import (
    P136ObservationError,
    validate_incremental_observer_config,
    validate_observer_runtime_authority,
    validate_promotion_record,
)
from app.services.p136_release_evidence import P136ReleaseEvidenceError, validate_p136_release_evidence
from app.services.p137_contracts import (
    BUNDLE_FIELDS,
    BUNDLE_SCHEMA_VERSION,
    FIXED_P136_HANDOFF_PATH,
    P136_AUTHORITY_FIELDS,
    P136_QUALIFIED_RELEASE_STATUS,
    P137ContractError,
    build_evidence_atom,
    content_hash,
    decode_canonical_lower_hex,
    validate_triage_agent_config,
)

PUBLISHER_STATE_SCHEMA_VERSION = "p136.p137_handoff_publisher_state.v1"
PUBLISHER_INTENT_SCHEMA_VERSION = "p136.p137_handoff_publish_intent.v1"
PUBLISHER_GENESIS_SCHEMA_VERSION = "p136.p137_handoff_publisher.v1"
PUBLISHER_STATE_FIELDS = frozenset(
    {
        "schema_version",
        "handoff_chain_root_hash",
        "last_bundle_sequence",
        "last_bundle_hash",
        "last_p136_checkpoint_hash",
        "fixed_handoff_path",
        "state_hash",
    }
)
PUBLISHER_INTENT_FIELDS = frozenset(
    {
        "schema_version",
        "state_hash",
        "fixed_handoff_path",
        "bundle_sequence",
        "previous_bundle_hash",
        "bundle_hash",
        "bundle",
        "fsync",
        "intent_hash",
    }
)


class P137HandoffError(ValueError):
    """Raised when P136->P137 handoff validation fails closed."""


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def publish_p136_handoff_bundle(
    *,
    base_path: Path,
    state_path: str,
    intent_path: str,
    fixed_handoff_path: str,
    p136_config: Mapping[str, Any],
    p136_runtime_authority: Mapping[str, Any],
    now: str,
    p136_checkpoint: Mapping[str, Any],
    canonical_entry_map: Mapping[str, Mapping[str, Any]],
    promotion_records: Sequence[Mapping[str, Any]],
    p136_independent_review: Mapping[str, Any],
    p136_release_evidence: Mapping[str, Any],
    created_at: str,
    crash_after_intent: bool = False,
) -> dict[str, Any]:
    if fixed_handoff_path != FIXED_P136_HANDOFF_PATH:
        raise P137HandoffError("invalid_fixed_handoff_path")
    state = _read_json_optional(base_path, state_path, label="publisher_state")
    pending = _read_json_optional(base_path, intent_path, label="publisher_intent")
    if state is not None:
        _validate_publisher_state(state, fixed_handoff_path=fixed_handoff_path)
        _validate_publisher_state_current_bundle(base_path, fixed_handoff_path, state)
    if pending is not None:
        _validate_publisher_intent(
            pending,
            state=state,
            fixed_handoff_path=fixed_handoff_path,
        )
    if pending is not None:
        pending_bundle = _mapping(pending.get("bundle"), "pending_bundle")
        candidate = _candidate_bundle(
            state=state,
            fixed_handoff_path=fixed_handoff_path,
            p136_config=p136_config,
            p136_runtime_authority=p136_runtime_authority,
            now=now,
            p136_checkpoint=p136_checkpoint,
            canonical_entry_map=canonical_entry_map,
            promotion_records=promotion_records,
            p136_independent_review=p136_independent_review,
            p136_release_evidence=p136_release_evidence,
            created_at=created_at,
        )
        if dict(pending_bundle) != candidate:
            raise P137HandoffError("conflicting_pending_handoff_intent")
        _atomic_write_json(base_path, fixed_handoff_path, pending_bundle)
        _atomic_write_json(base_path, state_path, _state_from_bundle(pending_bundle))
        _unlink_optional(base_path, intent_path)
        return dict(pending_bundle)

    bundle = _candidate_bundle(
        state=state,
        fixed_handoff_path=fixed_handoff_path,
        p136_config=p136_config,
        p136_runtime_authority=p136_runtime_authority,
        now=now,
        p136_checkpoint=p136_checkpoint,
        canonical_entry_map=canonical_entry_map,
        promotion_records=promotion_records,
        p136_independent_review=p136_independent_review,
        p136_release_evidence=p136_release_evidence,
        created_at=created_at,
    )
    intent = {
        "schema_version": PUBLISHER_INTENT_SCHEMA_VERSION,
        "state_hash": None if state is None else state.get("state_hash"),
        "fixed_handoff_path": fixed_handoff_path,
        "bundle_sequence": bundle["bundle_sequence"],
        "previous_bundle_hash": bundle["previous_bundle_hash"],
        "bundle_hash": bundle["bundle_hash"],
        "bundle": bundle,
        "fsync": {"file": True, "parent_directory": True},
    }
    intent["intent_hash"] = stable_hash({key: item for key, item in intent.items() if key != "intent_hash"})
    _atomic_write_json(base_path, intent_path, intent)
    if crash_after_intent:
        raise P137HandoffError("publisher_crash_after_intent")
    _atomic_write_json(base_path, fixed_handoff_path, bundle)
    _atomic_write_json(base_path, state_path, _state_from_bundle(bundle))
    _unlink_optional(base_path, intent_path)
    return bundle


def validate_p136_handoff_bundle(
    bundle_bytes: bytes,
    *,
    config: Mapping[str, Any],
    p137_checkpoint: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        validate_triage_agent_config(config)
        bundle = _load_canonical_bundle_bytes(bundle_bytes)
        _validate_bundle_envelope(bundle, config=config, p137_checkpoint=p137_checkpoint)
        authority = _decoded_p136_authority(bundle)
        validate_incremental_observer_config(_mapping(bundle["p136_config"], "p136_config"))
        validate_observer_runtime_authority(
            _mapping(bundle["p136_config"], "p136_config"),
            authority,
            now=str(bundle["now"]),
        )
        atoms: list[dict[str, Any]] = []
        runtime = {
            "config": bundle["p136_config"],
            "authority": authority,
            "checkpoint": bundle["p136_checkpoint"],
            "now": bundle["now"],
        }
        checkpoint_promotions = _mapping(bundle["p136_checkpoint"].get("promotion_keys"), "promotion_keys")
        for entry_hash, wrapper_raw in sorted(_mapping(bundle["promotion_map"], "promotion_map").items()):
            wrapper = _mapping(wrapper_raw, "promotion_wrapper")
            promotion = _mapping(wrapper.get("promotion"), "promotion")
            expected_entry = _mapping(_mapping(bundle["canonical_entry_map"], "canonical_entry_map")[entry_hash], "entry_wrapper").get("entry")
            expected_entry_map = _mapping(expected_entry, "expected_entry")
            checkpoint_value = checkpoint_promotions.get(entry_hash)
            if checkpoint_value is None:
                raise P137HandoffError("checkpoint_promotion_entry_missing")
            if dict(_mapping(checkpoint_value, "checkpoint_promotion")) != dict(promotion):
                if _differs_only_promotion_key(_mapping(checkpoint_value, "checkpoint_promotion"), promotion):
                    raise P137HandoffError("promotion_key_invalid")
                raise P137HandoffError("checkpoint_promotion_value_mismatch")
            if promotion.get("entry_hash") != entry_hash:
                raise P137HandoffError("promotion_entry_hash_mismatch")
            if promotion.get("promotion_key") != wrapper.get("promotion_key"):
                raise P137HandoffError("promotion_key_invalid")
            _validate_wrapper_bytes(wrapper, object_field="promotion", bytes_field="promotion_bytes")
            _validate_wrapper_bytes(_mapping(bundle["canonical_entry_map"][entry_hash], "entry_wrapper"), object_field="entry", bytes_field="entry_bytes")
            try:
                validate_promotion_record(promotion, expected_entry=expected_entry_map, runtime=runtime)
            except P136ObservationError as exc:
                raise P137HandoffError(str(exc)) from exc
            atoms.extend(
                _atoms_from_promotion(
                    promotion,
                    classification_policy=_mapping(config["classification_policy"], "classification_policy"),
                )
            )
        return {
            "bundle_hash": bundle["bundle_hash"],
            "bundle_sequence": bundle["bundle_sequence"],
            "previous_bundle_hash": bundle["previous_bundle_hash"],
            "handoff_chain_root_hash": bundle["handoff_chain_root_hash"],
            "fixed_handoff_path": bundle["fixed_handoff_path"],
            "evidence_atoms": atoms,
            "promotion_record_count": len(bundle["promotion_map"]),
            "promotion_bytes_validated": sum(
                len(
                    decode_canonical_lower_hex(
                        _mapping(wrapper, "promotion_wrapper")["promotion_bytes"],
                        field="promotion_bytes",
                    )
                )
                for wrapper in _mapping(bundle["promotion_map"], "promotion_map").values()
            ),
            "p136_validator_calls": {
                "validate_incremental_observer_config": 1,
                "validate_observer_runtime_authority": 1,
                "validate_promotion_record": len(bundle["promotion_map"]),
            },
        }
    except P137HandoffError:
        raise
    except (P137ContractError, P136ObservationError, KeyError, TypeError, ValueError) as exc:
        raise P137HandoffError(str(exc)) from exc


def _candidate_bundle(
    *,
    state: Mapping[str, Any] | None,
    fixed_handoff_path: str,
    p136_config: Mapping[str, Any],
    p136_runtime_authority: Mapping[str, Any],
    now: str,
    p136_checkpoint: Mapping[str, Any],
    canonical_entry_map: Mapping[str, Mapping[str, Any]],
    promotion_records: Sequence[Mapping[str, Any]],
    p136_independent_review: Mapping[str, Any],
    p136_release_evidence: Mapping[str, Any],
    created_at: str,
) -> dict[str, Any]:
    sequence = 1 if state is None else _positive_int(state.get("last_bundle_sequence"), "last_bundle_sequence") + 1
    previous_hash = None if state is None else _hash(state.get("last_bundle_hash"), "last_bundle_hash")
    entry_wrappers = _entry_wrappers(canonical_entry_map)
    promotion_wrappers = _promotion_wrappers(promotion_records)
    descriptors, byte_hashes = _descriptors_and_hashes(p136_runtime_authority, entry_wrappers, promotion_wrappers)
    checkpoint_hash = _hash(p136_checkpoint.get("checkpoint_hash"), "p136_checkpoint_hash")
    config_hash = _hash(p136_config.get("config_hash"), "p136_config_hash")
    review_hash = _hash(p136_independent_review.get("independent_review_hash"), "p136_independent_review_hash")
    release_hash = _hash(p136_release_evidence.get("evidence_hash"), "p136_release_evidence_hash")
    _validate_p136_release_boundary(
        independent_review=p136_independent_review,
        release_evidence=p136_release_evidence,
    )
    if p136_release_evidence.get("status") != P136_QUALIFIED_RELEASE_STATUS:
        raise P137HandoffError("invalid_p136_release_status")
    chain_root = _chain_root_for_candidate(
        state=state,
        sequence=sequence,
        previous_bundle_hash=previous_hash,
        fixed_handoff_path=fixed_handoff_path,
        created_at=created_at,
        p136_checkpoint_hash=checkpoint_hash,
        promotion_entry_hashes=tuple(sorted(promotion_wrappers)),
    )
    bundle: dict[str, Any] = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "bundle_version": 1,
        "bundle_sequence": sequence,
        "previous_bundle_hash": previous_hash,
        "handoff_chain_root_hash": chain_root,
        "created_at": created_at,
        "p136_config": deepcopy(dict(p136_config)),
        "p136_config_hash": config_hash,
        "p136_runtime_authority": _encoded_authority(p136_runtime_authority),
        "now": now,
        "p136_checkpoint": deepcopy(dict(p136_checkpoint)),
        "p136_checkpoint_hash": checkpoint_hash,
        "canonical_entry_map": entry_wrappers,
        "promotion_map": promotion_wrappers,
        "p136_independent_review": deepcopy(dict(p136_independent_review)),
        "p136_independent_review_hash": review_hash,
        "p136_release_evidence": deepcopy(dict(p136_release_evidence)),
        "p136_release_evidence_hash": release_hash,
        "descriptors": descriptors,
        "canonical_byte_hashes": byte_hashes,
        "fixed_handoff_path": fixed_handoff_path,
        "write_durability": {"atomic_replace": True, "file_fsync": True, "parent_directory_fsync": True},
    }
    bundle["bundle_hash"] = stable_hash(bundle)
    return bundle


def _chain_root_for_candidate(
    *,
    state: Mapping[str, Any] | None,
    sequence: int,
    previous_bundle_hash: str | None,
    fixed_handoff_path: str,
    created_at: str,
    p136_checkpoint_hash: str,
    promotion_entry_hashes: tuple[str, ...],
) -> str:
    if state is not None:
        return _hash(state.get("handoff_chain_root_hash"), "handoff_chain_root_hash")
    genesis = {
        "schema_version": PUBLISHER_GENESIS_SCHEMA_VERSION,
        "bundle_sequence": sequence,
        "previous_bundle_hash": previous_bundle_hash,
        "fixed_handoff_path": fixed_handoff_path,
        "created_at": created_at,
        "p136_checkpoint_hash": p136_checkpoint_hash,
        "promotion_entry_hashes": list(promotion_entry_hashes),
    }
    genesis["publisher_record_hash"] = stable_hash(genesis)
    return str(genesis["publisher_record_hash"])


def _state_from_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]:
    state = {
        "schema_version": PUBLISHER_STATE_SCHEMA_VERSION,
        "handoff_chain_root_hash": bundle["handoff_chain_root_hash"],
        "last_bundle_sequence": bundle["bundle_sequence"],
        "last_bundle_hash": bundle["bundle_hash"],
        "last_p136_checkpoint_hash": bundle["p136_checkpoint_hash"],
        "fixed_handoff_path": bundle["fixed_handoff_path"],
    }
    state["state_hash"] = stable_hash({key: item for key, item in state.items() if key != "state_hash"})
    return state


def _validate_publisher_state(state: Mapping[str, Any], *, fixed_handoff_path: str) -> None:
    if set(state) != PUBLISHER_STATE_FIELDS or state.get("schema_version") != PUBLISHER_STATE_SCHEMA_VERSION:
        raise P137HandoffError("invalid_publisher_state_fields")
    _hash(state.get("handoff_chain_root_hash"), "publisher_state_handoff_chain_root_hash")
    _positive_int(state.get("last_bundle_sequence"), "publisher_state_last_bundle_sequence")
    _hash(state.get("last_bundle_hash"), "publisher_state_last_bundle_hash")
    _hash(state.get("last_p136_checkpoint_hash"), "publisher_state_last_p136_checkpoint_hash")
    if state.get("fixed_handoff_path") != fixed_handoff_path:
        raise P137HandoffError("publisher_state_fixed_handoff_path_mismatch")
    expected_hash = stable_hash({key: value for key, value in state.items() if key != "state_hash"})
    if state.get("state_hash") != expected_hash:
        raise P137HandoffError("publisher_state_hash_invalid")


def _validate_publisher_state_current_bundle(
    base_path: Path,
    fixed_handoff_path: str,
    state: Mapping[str, Any],
) -> None:
    current = _read_json_optional(base_path, fixed_handoff_path, label="current_handoff_bundle")
    if current is None:
        raise P137HandoffError("publisher_state_current_bundle_missing")
    _validate_publisher_bundle(current, fixed_handoff_path=fixed_handoff_path)
    if current.get("bundle_sequence") != state.get("last_bundle_sequence"):
        raise P137HandoffError("publisher_state_current_sequence_mismatch")
    if current.get("bundle_hash") != state.get("last_bundle_hash"):
        raise P137HandoffError("publisher_state_current_hash_mismatch")
    if current.get("p136_checkpoint_hash") != state.get("last_p136_checkpoint_hash"):
        raise P137HandoffError("publisher_state_current_checkpoint_hash_mismatch")
    if current.get("handoff_chain_root_hash") != state.get("handoff_chain_root_hash"):
        raise P137HandoffError("publisher_state_current_chain_root_mismatch")


def _validate_publisher_intent(
    intent: Mapping[str, Any],
    *,
    state: Mapping[str, Any] | None,
    fixed_handoff_path: str,
) -> None:
    if set(intent) != PUBLISHER_INTENT_FIELDS or intent.get("schema_version") != PUBLISHER_INTENT_SCHEMA_VERSION:
        raise P137HandoffError("invalid_publisher_intent_fields")
    expected_intent_hash = stable_hash({key: value for key, value in intent.items() if key != "intent_hash"})
    if intent.get("intent_hash") != expected_intent_hash:
        raise P137HandoffError("publisher_intent_hash_invalid")
    if intent.get("fixed_handoff_path") != fixed_handoff_path:
        raise P137HandoffError("publisher_intent_fixed_handoff_path_mismatch")
    if intent.get("fsync") != {"file": True, "parent_directory": True}:
        raise P137HandoffError("publisher_intent_fsync_invalid")

    state_hash = intent.get("state_hash")
    if state is None:
        if state_hash is not None:
            raise P137HandoffError("publisher_intent_state_missing")
        expected_sequence = 1
        expected_previous_hash = None
    else:
        expected_state_hash = _hash(state.get("state_hash"), "publisher_state_hash")
        if state_hash != expected_state_hash:
            raise P137HandoffError("publisher_intent_state_hash_mismatch")
        expected_sequence = _positive_int(state.get("last_bundle_sequence"), "publisher_state_last_bundle_sequence") + 1
        expected_previous_hash = _hash(state.get("last_bundle_hash"), "publisher_state_last_bundle_hash")

    sequence = _positive_int(intent.get("bundle_sequence"), "publisher_intent_bundle_sequence")
    if sequence != expected_sequence:
        raise P137HandoffError("publisher_intent_bundle_sequence_mismatch")
    previous_hash = intent.get("previous_bundle_hash")
    if previous_hash != expected_previous_hash:
        raise P137HandoffError("publisher_intent_previous_bundle_hash_mismatch")
    if previous_hash is not None:
        _hash(previous_hash, "publisher_intent_previous_bundle_hash")
    bundle_hash = _hash(intent.get("bundle_hash"), "publisher_intent_bundle_hash")
    bundle = _mapping(intent.get("bundle"), "pending_bundle")
    _validate_publisher_bundle(bundle, fixed_handoff_path=fixed_handoff_path)
    if bundle.get("bundle_hash") != bundle_hash:
        raise P137HandoffError("publisher_intent_bundle_hash_mismatch")
    if bundle.get("bundle_sequence") != sequence:
        raise P137HandoffError("publisher_intent_bundle_sequence_mismatch")
    if bundle.get("previous_bundle_hash") != previous_hash:
        raise P137HandoffError("publisher_intent_previous_bundle_hash_mismatch")
    if state is not None and bundle.get("handoff_chain_root_hash") != state.get("handoff_chain_root_hash"):
        raise P137HandoffError("publisher_intent_state_chain_root_mismatch")
    if state is not None and bundle.get("previous_bundle_hash") != state.get("last_bundle_hash"):
        raise P137HandoffError("publisher_intent_state_previous_hash_mismatch")


def _validate_publisher_bundle(bundle: Mapping[str, Any], *, fixed_handoff_path: str) -> None:
    if set(bundle) != BUNDLE_FIELDS or bundle.get("schema_version") != BUNDLE_SCHEMA_VERSION:
        raise P137HandoffError("publisher_bundle_fields_invalid")
    if bundle.get("bundle_hash") != stable_hash({key: value for key, value in bundle.items() if key != "bundle_hash"}):
        raise P137HandoffError("publisher_bundle_hash_invalid")
    if bundle.get("fixed_handoff_path") != fixed_handoff_path:
        raise P137HandoffError("publisher_bundle_fixed_handoff_path_mismatch")
    sequence = _positive_int(bundle.get("bundle_sequence"), "publisher_bundle_sequence")
    previous = bundle.get("previous_bundle_hash")
    if sequence == 1:
        if previous is not None:
            raise P137HandoffError("publisher_bundle_genesis_previous_hash_not_null")
    else:
        _hash(previous, "publisher_bundle_previous_bundle_hash")
    _hash(bundle.get("handoff_chain_root_hash"), "publisher_bundle_handoff_chain_root_hash")
    if bundle.get("p136_config_hash") != _mapping(bundle.get("p136_config"), "p136_config").get("config_hash"):
        raise P137HandoffError("publisher_bundle_p136_config_hash_mismatch")
    if bundle.get("p136_checkpoint_hash") != _mapping(bundle.get("p136_checkpoint"), "p136_checkpoint").get("checkpoint_hash"):
        raise P137HandoffError("publisher_bundle_p136_checkpoint_hash_mismatch")
    if bundle.get("p136_independent_review_hash") != _mapping(bundle.get("p136_independent_review"), "p136_independent_review").get("independent_review_hash"):
        raise P137HandoffError("publisher_bundle_p136_independent_review_hash_mismatch")
    release_evidence = _mapping(bundle.get("p136_release_evidence"), "p136_release_evidence")
    if bundle.get("p136_release_evidence_hash") != release_evidence.get("evidence_hash"):
        raise P137HandoffError("publisher_bundle_p136_release_evidence_hash_mismatch")
    if release_evidence.get("status") != P136_QUALIFIED_RELEASE_STATUS:
        raise P137HandoffError("publisher_bundle_invalid_p136_release_status")
    _validate_p136_release_boundary(
        independent_review=_mapping(bundle.get("p136_independent_review"), "p136_independent_review"),
        release_evidence=release_evidence,
    )
    if _mapping(bundle.get("write_durability"), "write_durability") != {"atomic_replace": True, "file_fsync": True, "parent_directory_fsync": True}:
        raise P137HandoffError("publisher_bundle_not_durable")


def _entry_wrappers(entries: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for entry_hash, entry_raw in sorted(entries.items()):
        entry = deepcopy(dict(_mapping(entry_raw, "entry")))
        if entry.get("entry_hash") != entry_hash:
            raise P137HandoffError("entry_hash_mismatch")
        raw = canonical_json_bytes(entry)
        result[entry_hash] = {"entry": entry, "entry_bytes": raw.hex(), "entry_bytes_hash": content_hash(raw), "entry_byte_length": len(raw)}
    return result


def _promotion_wrappers(promotions: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for promotion_raw in promotions:
        promotion = deepcopy(dict(_mapping(promotion_raw, "promotion")))
        entry_hash = _hash(promotion.get("entry_hash"), "promotion_entry_hash")
        raw = canonical_json_bytes(promotion)
        result[entry_hash] = {
            "promotion": promotion,
            "promotion_bytes": raw.hex(),
            "promotion_bytes_hash": content_hash(raw),
            "promotion_byte_length": len(raw),
            "promotion_key": _hash(promotion.get("promotion_key"), "promotion_key"),
            "p135_normalized_bundle": deepcopy(dict(_mapping(promotion.get("p135_normalized_bundle"), "p135_normalized_bundle"))),
            "p134_p135_bindings": {
                "p135_manifest_hash": promotion["p135_manifest_hash"],
                "p135_artifact_spec_hash": promotion["p135_artifact_spec_hash"],
                "p134_segment_receipt_hash": promotion["p134_segment_receipt_hash"],
                "p135_execution_receipt_hash": promotion["p135_execution_receipt_hash"],
                "p135_receipt_ledger_hash": promotion["p135_receipt_ledger_hash"],
                "p135_normalized_bundle_hash": promotion["p135_normalized_bundle_hash"],
            },
        }
    return result


def _encoded_authority(authority_raw: Mapping[str, Any]) -> dict[str, Any]:
    authority = _mapping(authority_raw, "authority")
    if not P136_AUTHORITY_FIELDS <= set(authority):
        raise P137HandoffError("missing_p136_authority_field")
    result: dict[str, Any] = {
        "contract": deepcopy(dict(_mapping(authority["contract"], "contract"))),
        "review_receipt": deepcopy(dict(_mapping(authority["review_receipt"], "review_receipt"))),
        "receipt_ledger": deepcopy(dict(_mapping(authority["receipt_ledger"], "receipt_ledger"))),
        "index_receipts": [deepcopy(dict(_mapping(item, "index_receipt"))) for item in _sequence(authority["index_receipts"], "index_receipts")],
        "segment_receipts": [deepcopy(dict(_mapping(item, "segment_receipt"))) for item in _sequence(authority["segment_receipts"], "segment_receipts")],
        "contract_bytes": _bytes(authority["contract_bytes"], "contract_bytes").hex(),
        "review_receipt_bytes": _bytes(authority["review_receipt_bytes"], "review_receipt_bytes").hex(),
        "receipt_ledger_bytes": _bytes(authority["receipt_ledger_bytes"], "receipt_ledger_bytes").hex(),
        "index_receipt_bytes": [_bytes(item, "index_receipt_bytes").hex() for item in _sequence(authority["index_receipt_bytes"], "index_receipt_bytes")],
        "segment_receipt_bytes": [_bytes(item, "segment_receipt_bytes").hex() for item in _sequence(authority["segment_receipt_bytes"], "segment_receipt_bytes")],
    }
    return result


def _descriptors_and_hashes(
    authority: Mapping[str, Any],
    entries: Mapping[str, Mapping[str, Any]],
    promotions: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, str]]:
    encoded = _encoded_authority(authority)
    descriptors: dict[str, Any] = {}
    byte_hashes: dict[str, str] = {}

    def add(name: str, raw: bytes) -> None:
        descriptors[name] = {"relative_path": f"embedded/{name}.json", "object_type": name, "byte_length": len(raw), "fsync": True}
        byte_hashes[name] = content_hash(raw)

    for field in ("contract_bytes", "review_receipt_bytes", "receipt_ledger_bytes"):
        add(field, bytes.fromhex(str(encoded[field])))
    for index, item in enumerate(_sequence(encoded["index_receipt_bytes"], "index_receipt_bytes")):
        add(f"index_receipt_bytes:{index}", bytes.fromhex(str(item)))
    for index, item in enumerate(_sequence(encoded["segment_receipt_bytes"], "segment_receipt_bytes")):
        add(f"segment_receipt_bytes:{index}", bytes.fromhex(str(item)))
    for entry_hash, wrapper in entries.items():
        add(f"entry_bytes:{entry_hash}", bytes.fromhex(str(wrapper["entry_bytes"])))
    for entry_hash, wrapper in promotions.items():
        add(f"promotion_bytes:{entry_hash}", bytes.fromhex(str(wrapper["promotion_bytes"])))
    return descriptors, byte_hashes


def _load_canonical_bundle_bytes(bundle_bytes: bytes) -> dict[str, Any]:
    try:
        decoded = json.loads(bundle_bytes)
    except json.JSONDecodeError as exc:
        raise P137HandoffError("invalid_handoff_json") from exc
    if not isinstance(decoded, Mapping):
        raise P137HandoffError("invalid_handoff_shape")
    bundle = dict(decoded)
    if canonical_json_bytes(bundle) != bundle_bytes:
        raise P137HandoffError("noncanonical_handoff_bytes")
    return bundle


def _validate_bundle_envelope(bundle: Mapping[str, Any], *, config: Mapping[str, Any], p137_checkpoint: Mapping[str, Any] | None) -> None:
    if set(bundle) != BUNDLE_FIELDS or bundle.get("schema_version") != BUNDLE_SCHEMA_VERSION:
        raise P137HandoffError("invalid_handoff_bundle_fields")
    if bundle.get("bundle_hash") != stable_hash({key: item for key, item in bundle.items() if key != "bundle_hash"}):
        raise P137HandoffError("bundle_hash_invalid")
    if bundle.get("fixed_handoff_path") != config.get("p136_handoff_bundle_path"):
        raise P137HandoffError("fixed_handoff_path_mismatch")
    if bundle.get("handoff_chain_root_hash") != config.get("p136_handoff_chain_root_hash"):
        raise P137HandoffError("handoff_chain_root_hash_mismatch")
    if bundle.get("p136_config_hash") != _mapping(bundle["p136_config"], "p136_config").get("config_hash"):
        raise P137HandoffError("p136_config_hash_mismatch")
    if bundle.get("p136_checkpoint_hash") != _mapping(bundle["p136_checkpoint"], "p136_checkpoint").get("checkpoint_hash"):
        raise P137HandoffError("p136_checkpoint_hash_mismatch")
    if bundle.get("p136_independent_review_hash") != _mapping(bundle["p136_independent_review"], "p136_independent_review").get("independent_review_hash"):
        raise P137HandoffError("p136_independent_review_hash_mismatch")
    if bundle.get("p136_release_evidence_hash") != _mapping(bundle["p136_release_evidence"], "p136_release_evidence").get("evidence_hash"):
        raise P137HandoffError("p136_release_evidence_hash_mismatch")
    release_evidence = _mapping(bundle["p136_release_evidence"], "p136_release_evidence")
    if release_evidence.get("status") != P136_QUALIFIED_RELEASE_STATUS:
        raise P137HandoffError("invalid_p136_release_status")
    _validate_p136_release_boundary(
        independent_review=_mapping(bundle["p136_independent_review"], "p136_independent_review"),
        release_evidence=release_evidence,
    )
    durability = _mapping(bundle["write_durability"], "write_durability")
    if durability != {"atomic_replace": True, "file_fsync": True, "parent_directory_fsync": True}:
        raise P137HandoffError("handoff_not_durable")
    sequence = _positive_int(bundle.get("bundle_sequence"), "bundle_sequence")
    previous = bundle.get("previous_bundle_hash")
    if sequence == 1:
        if previous is not None:
            raise P137HandoffError("genesis_previous_bundle_hash_not_null")
    else:
        _hash(previous, "previous_bundle_hash")
    if p137_checkpoint is not None:
        last_sequence = _positive_int(
            p137_checkpoint.get("last_accepted_bundle_sequence"),
            "last_accepted_bundle_sequence",
        )
        last_hash = _hash(
            p137_checkpoint.get("last_accepted_bundle_hash"),
            "last_accepted_bundle_hash",
        )
        if sequence < last_sequence:
            raise P137HandoffError("p136_handoff_sequence_rollback")
        if sequence == last_sequence:
            if bundle.get("bundle_hash") != last_hash:
                raise P137HandoffError("p136_handoff_same_sequence_fork")
        else:
            if sequence != last_sequence + 1:
                raise P137HandoffError("handoff_sequence_gap")
            if previous != last_hash:
                raise P137HandoffError("p136_handoff_previous_hash_discontinuity")


def _decoded_p136_authority(bundle: Mapping[str, Any]) -> dict[str, Any]:
    auth = _mapping(bundle["p136_runtime_authority"], "p136_runtime_authority")
    if set(auth) != P136_AUTHORITY_FIELDS:
        raise P137HandoffError("invalid_p136_authority_fields")
    descriptors = _mapping(bundle["descriptors"], "descriptors")
    hashes = _mapping(bundle["canonical_byte_hashes"], "canonical_byte_hashes")

    def decode_field(field: str) -> bytes:
        descriptor = _mapping(descriptors[field], f"descriptor:{field}")
        return decode_canonical_lower_hex(auth[field], field=field, expected_hash=str(hashes[field]), expected_length=int(descriptor["byte_length"]))

    contract_bytes = decode_field("contract_bytes")
    review_bytes = decode_field("review_receipt_bytes")
    ledger_bytes = decode_field("receipt_ledger_bytes")
    index_bytes: list[bytes] = []
    for index, item in enumerate(_sequence(auth["index_receipt_bytes"], "index_receipt_bytes")):
        field = f"index_receipt_bytes:{index}"
        descriptor = _mapping(descriptors[field], f"descriptor:{field}")
        index_bytes.append(decode_canonical_lower_hex(item, field=field, expected_hash=str(hashes[field]), expected_length=int(descriptor["byte_length"])))
    segment_bytes: list[bytes] = []
    for index, item in enumerate(_sequence(auth["segment_receipt_bytes"], "segment_receipt_bytes")):
        field = f"segment_receipt_bytes:{index}"
        descriptor = _mapping(descriptors[field], f"descriptor:{field}")
        decoded = decode_canonical_lower_hex(item, field=field, expected_hash=str(hashes[field]), expected_length=int(descriptor["byte_length"]))
        parsed = json.loads(decoded)
        expected = _sequence(auth["segment_receipts"], "segment_receipts")[index]
        if parsed != expected:
            raise P137HandoffError("segment_receipt_bytes_mismatch")
        segment_bytes.append(decoded)
    return {
        "contract": deepcopy(dict(_mapping(auth["contract"], "contract"))),
        "review_receipt": deepcopy(dict(_mapping(auth["review_receipt"], "review_receipt"))),
        "receipt_ledger": deepcopy(dict(_mapping(auth["receipt_ledger"], "receipt_ledger"))),
        "index_receipts": [deepcopy(dict(_mapping(item, "index_receipt"))) for item in _sequence(auth["index_receipts"], "index_receipts")],
        "segment_receipts": [deepcopy(dict(_mapping(item, "segment_receipt"))) for item in _sequence(auth["segment_receipts"], "segment_receipts")],
        "contract_bytes": contract_bytes,
        "review_receipt_bytes": review_bytes,
        "receipt_ledger_bytes": ledger_bytes,
        "index_receipt_bytes": index_bytes,
        "segment_receipt_bytes": segment_bytes,
    }


def _validate_wrapper_bytes(wrapper: Mapping[str, Any], *, object_field: str, bytes_field: str) -> None:
    raw = canonical_json_bytes(_mapping(wrapper[object_field], object_field))
    decoded = decode_canonical_lower_hex(
        wrapper[bytes_field],
        field=bytes_field,
        expected_hash=str(wrapper[f"{bytes_field}_hash"]),
        expected_length=int(wrapper[bytes_field.replace("bytes", "byte_length")]),
    )
    if decoded != raw:
        raise P137HandoffError(f"{bytes_field}_mismatch")


def _validate_p136_release_boundary(
    *,
    independent_review: Mapping[str, Any],
    release_evidence: Mapping[str, Any],
) -> None:
    try:
        validate_p136_release_evidence(
            release_evidence,
            independent_review=independent_review,
        )
    except P136ReleaseEvidenceError as exc:
        raise P137HandoffError(str(exc)) from exc


def _atoms_from_promotion(
    promotion: Mapping[str, Any],
    *,
    classification_policy: Mapping[str, Any],
) -> list[dict[str, Any]]:
    status = str(promotion["status"])
    bundle = _mapping(promotion["p135_normalized_bundle"], "p135_normalized_bundle")
    if status == "denominator_failure":
        _validate_denominator_failure_conversion(bundle)
    atoms: list[dict[str, Any]] = []
    for record in _sequence(bundle.get("records"), "records"):
        record_map = _mapping(record, "p135_record")
        p120 = _mapping(record_map["p120_record"], "p120_record")
        source_evidence_state = str(p120["evidence_state"])
        evidence_state = _atom_state(status, source_evidence_state)
        numeric = p120.get("value")
        if isinstance(numeric, bool):
            raise P137HandoffError("p120_numeric_value_bool")
        numeric_value = numeric if isinstance(numeric, (int, float)) and not isinstance(numeric, bool) else None
        state_reason_codes = _state_reason_codes(status, p120)
        risk_flags = sorted(str(item) for item in _sequence(record_map.get("risk_flags"), "risk_flags"))
        topology_refs = list(_sequence(p120.get("topology_refs"), "topology_refs"))
        deploy_config_refs = list(_sequence(p120.get("deploy_config_refs"), "deploy_config_refs"))
        labels = _mapping(p120.get("labels"), "labels")
        redacted_preview = record_map.get("redacted_preview")
        atom = build_evidence_atom(
            {
                "atom_id": "atom-" + str(record_map["evidence_id"]).removeprefix("sha256:")[:32],
                "promotion_record_hash": promotion["promotion_hash"],
                "promotion_key": promotion["promotion_key"],
                "p136_entry_hash": promotion["entry_hash"],
                "p135_bundle_hash": promotion["p135_normalized_bundle_hash"],
                "source_id": p120["source_id"],
                "provider": record_map["provider"],
                "format": record_map["format"],
                "signal_family": bundle["signal_family"],
                "system_id": p120["system_id"],
                "entity_ref_hash": _entity_ref_hash(p120["entity_ref"]),
                "window": _mapping(p120.get("window"), "window"),
                "signal_name": p120["signal_name"],
                "numeric_value": numeric_value,
                "numeric_unit": p120.get("unit") if numeric_value is not None else None,
                "evidence_state": evidence_state,
                "severity_code": _severity_code(p120.get("severity")),
                "metric_breach_code": _metric_breach_code(
                    signal_name=str(p120["signal_name"]),
                    numeric_value=numeric_value,
                    numeric_unit=p120.get("unit") if numeric_value is not None else None,
                    policy=classification_policy,
                ),
                "marker_code": _marker_code(p120, risk_flags, topology_refs, deploy_config_refs),
                "counter_signal_code": _counter_signal_code(risk_flags),
                "state_reason_codes": state_reason_codes,
                "denominator_visible": bool(p120["denominator_visible"]),
                "content_hash": record_map["content_hash"],
                "label_hashes": sorted(stable_hash({"key": str(key), "value": value}) for key, value in labels.items()),
                "topology_ref_hashes": sorted(stable_hash(item) for item in topology_refs),
                "deploy_config_ref_hashes": sorted(stable_hash(item) for item in deploy_config_refs),
                "risk_flags": risk_flags,
                "redacted_preview_hash": stable_hash(redacted_preview) if redacted_preview else None,
                "ordinal": record_map["ordinal"],
            }
        )
        atoms.append(atom)
    return atoms


def _validate_denominator_failure_conversion(bundle: Mapping[str, Any]) -> None:
    reason = bundle.get("failure_reason")
    if not isinstance(reason, str) or not reason:
        raise P137HandoffError("invalid_p135_failure_reason")
    records = _sequence(bundle.get("records"), "records")
    if len(records) != 1:
        raise P137HandoffError("invalid_p135_failure_records")
    p120 = _mapping(_mapping(records[0], "record").get("p120_record"), "p120_record")
    reasons = _sequence(p120.get("state_reasons"), "state_reasons")
    if p120.get("evidence_state") != "fail_closed" or len(reasons) != 1 or reasons[0] != reason:
        raise P137HandoffError("p135_failure_reason_mismatch")
    labels = _mapping(p120.get("labels"), "labels")
    if "failure_reason" in labels and labels["failure_reason"] != reason:
        raise P137HandoffError("p135_failure_label_mismatch")


def _atom_state(status: str, evidence_state: str) -> str:
    if status == "denominator_failure":
        if evidence_state != "fail_closed":
            raise P137HandoffError("denominator_failure_not_fail_closed")
        return "denominator_visible_failure"
    if status == "success" and evidence_state == "valid":
        return "promoted_success"
    if status == "success" and evidence_state in {"missing_evidence", "contradiction", "ood", "investigate_more", "abstain", "escalate", "context", "fail_closed"}:
        return "context_only"
    raise P137HandoffError("invalid_promotion_atom_state")


def _state_reason_codes(status: str, p120: Mapping[str, Any]) -> list[str]:
    if status == "denominator_failure":
        return ["local_catalog_selectable", "p135_adapter_failure"]
    reasons = [str(item) for item in _sequence(p120.get("state_reasons"), "state_reasons")]
    mapping = {
        **{
            reason: "parser_failure"
            for reason in {
                "unsupported_modality",
                "unsupported_modality_hidden",
                "missing_telemetry_record_id",
                "missing_source_id",
                "missing_system_id",
                "missing_service_id",
                "missing_entity_ref",
                "missing_modality",
                "missing_observed_at",
                "missing_window",
                "missing_signal_name",
                "missing_unit",
                "nullable_metric_preserved",
                "missing_redaction_receipt",
                "invalid_normalization_version",
                "telemetry_dropped_from_denominator",
                "invalid_evidence_state",
            }
        },
        "redaction_failure": "redaction_failure",
        **{
            reason: "provenance_failure"
            for reason in {
                "authority_drift_visible",
                "p120_raw_ref_source_hash_mismatch",
                "p120_raw_ref_record_id_mismatch",
                "record_source_hash_mismatch",
                "record_source_id_mismatch",
                "record_source_schema_mismatch",
            }
        },
        **{
            reason: "local_catalog_selectable"
            for reason in {
                "timestamp_uncertainty_visible",
                "timestamp_skew_visible",
                "delayed_record_visible",
                "duplicate_record_visible",
                "reorder_visible",
                "contradictory_telemetry_visible",
                "stale_record",
            }
        },
        "provider_authority_required": "provider_authority_required",
        "network_authority_required": "network_authority_required",
        "credential_authority_required": "credential_authority_required",
        "operator_authority_required": "operator_authority_required",
        "action_authority_required": "action_authority_required",
    }
    try:
        return sorted({mapping[reason] for reason in reasons})
    except KeyError as exc:
        raise P137HandoffError("p120_state_reason_unmapped") from exc


def _entity_ref_hash(value: Any) -> str:
    if isinstance(value, str) and value.startswith("sha256:") and len(value) == 71:
        return value
    return stable_hash(value)


def _severity_code(value: Any) -> str:
    normalized = str(value).lower()
    return normalized if normalized in {"sev0", "sev1", "sev2", "sev3", "sev4"} else "unknown"


def _marker_code(
    p120: Mapping[str, Any],
    risk_flags: Sequence[str],
    topology_refs: Sequence[Any],
    deploy_config_refs: Sequence[Any],
) -> str:
    flags = set(risk_flags)
    if "known_benign_schedule" in flags:
        return "known_benign_schedule"
    if "topology_noise" in flags:
        return "topology_noise"
    if deploy_config_refs:
        return "deployment_marker"
    if topology_refs:
        return "topology_marker"
    if flags & {"prompt_like_text", "credential_like_text", "unsafe_action_request"}:
        return "security_marker"
    if p120.get("signal_name") == "data_quality":
        return "data_quality_marker"
    if p120.get("modality") == "topology":
        return "topology_noise"
    return "none"


def _counter_signal_code(risk_flags: Sequence[str]) -> str:
    if "decisive_counter_signal" in risk_flags:
        return "decisive_counter_signal"
    if "weak_counter_signal" in risk_flags:
        return "weak_counter_signal"
    return "none"


def _metric_breach_code(
    *,
    signal_name: str,
    numeric_value: int | float | None,
    numeric_unit: Any,
    policy: Mapping[str, Any],
) -> str:
    if numeric_value is None or not isinstance(numeric_unit, str):
        return "none"
    thresholds = policy.get("metric_thresholds")
    if not isinstance(thresholds, Mapping):
        return "none"
    by_signal = thresholds.get(signal_name)
    if not isinstance(by_signal, Mapping):
        return "none"
    bounds = by_signal.get(numeric_unit)
    if not isinstance(bounds, Mapping) or set(bounds) != {"warning_lower", "critical_lower", "warning_upper", "critical_upper"}:
        return "none"
    ordered = (
        ("critical_lower", "below_critical", lambda value, bound: value <= bound),
        ("critical_upper", "above_critical", lambda value, bound: value >= bound),
        ("warning_lower", "below_warning", lambda value, bound: value <= bound),
        ("warning_upper", "above_warning", lambda value, bound: value >= bound),
    )
    for key, code, predicate in ordered:
        bound = bounds[key]
        if isinstance(bound, (int, float)) and not isinstance(bound, bool) and predicate(numeric_value, bound):
            return code
    return "none"


def _differs_only_promotion_key(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    if set(left) != set(right):
        return False
    differing = {key for key in left if left[key] != right[key]}
    return differing == {"promotion_key"}


def _atomic_write_json(base_path: Path, relative_path: str, value: Mapping[str, Any]) -> None:
    path = base_path / _relative_path(relative_path, "relative_path")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.parent / f".{path.name}.{os.getpid()}.{time.monotonic_ns()}.tmp"
    try:
        with temp.open("wb") as handle:
            handle.write(canonical_json_bytes(value) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def _read_json_optional(base_path: Path, relative_path: str, *, label: str) -> dict[str, Any] | None:
    path = base_path / _relative_path(relative_path, "relative_path")
    if not path.exists():
        return None
    raw = path.read_bytes()
    if raw.endswith(b"\n"):
        raw = raw[:-1]
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise P137HandoffError(f"invalid_{label}_json") from exc
    if not isinstance(value, Mapping):
        raise P137HandoffError(f"invalid_{label}")
    return dict(value)


def _unlink_optional(base_path: Path, relative_path: str) -> None:
    path = base_path / _relative_path(relative_path, "relative_path")
    try:
        path.unlink()
    except FileNotFoundError:
        return
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _relative_path(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise P137HandoffError(f"invalid_path:{label}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise P137HandoffError(f"unsafe_path:{label}")
    return path.as_posix()


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise P137HandoffError(f"invalid_{label}_shape")
    return value


def _sequence(value: Any, label: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise P137HandoffError(f"invalid_{label}_shape")
    return value


def _bytes(value: Any, label: str) -> bytes:
    if not isinstance(value, bytes):
        raise P137HandoffError(f"invalid_{label}_shape")
    return value


def _hash(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        raise P137HandoffError(f"invalid_hash:{label}")
    return value


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise P137HandoffError(f"invalid_positive_int:{label}")
    return value
