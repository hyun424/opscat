"""P107 deterministic replay contract checks for recovery and release gates."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

TERMINAL_STATES = frozenset({"succeeded", "rolled_back", "rollback_failed_escalated", "escalated", "blocked_fail_closed", "replay_invalid"})
RECOVERY_REPLAY_PREFIXES = ("recovery-", "rollback-recovery-", "audit-recovery-")
FULL_SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


def validate_recovery_replay_contract(replay: Mapping[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    replay_id = replay.get("replay_id")
    if not isinstance(replay_id, str) or not replay_id.startswith(RECOVERY_REPLAY_PREFIXES):
        reasons.append("recovery replay id must use a recovery prefix")
    if replay.get("purpose") != "recovery_outcome":
        reasons.append("recovery replay purpose must be recovery_outcome")
    if replay.get("source") != "audit":
        reasons.append("recovery replay source must be audit")
    if not _sha(replay.get("source_audit_head_hash")):
        reasons.append("recovery replay must bind source audit head hash")
    recomputed_replay_hash = compute_replay_hash(replay)
    replay_hash = replay.get("hash")
    if not _sha(replay_hash):
        reasons.append("recovery replay must have a replay hash")
    elif _full_sha(replay_hash) and replay_hash != recomputed_replay_hash:
        reasons.append("recovery replay hash must match canonical replay content excluding its own hash field")

    audit_records = replay.get("audit_records")
    if not isinstance(audit_records, Sequence) or isinstance(audit_records, (str, bytes)):
        reasons.append("recovery replay requires an audit chain proof")
        audit_records = ()
    reasons.extend(
        _audit_chain_reasons(
            replay,
            audit_records,
            replay_kind="recovery",
            require_terminal=False,
        )
    )

    idempotency = replay.get("idempotency_state")
    if not isinstance(idempotency, Mapping):
        reasons.append("recovery replay requires idempotency state proof")
    else:
        if not isinstance(idempotency.get("idempotency_key"), str) or not idempotency.get("idempotency_key"):
            reasons.append("recovery replay idempotency key is missing")
        committed_effect_count = idempotency.get("committed_effect_count")
        if not isinstance(committed_effect_count, int) or isinstance(committed_effect_count, bool) or committed_effect_count not in {0, 1}:
            reasons.append("recovery replay committed effect count must be zero or one")
        if idempotency.get("duplicate_effect_count") != 0:
            reasons.append("recovery replay duplicate effect count must be zero")
        last_record = audit_records[-1] if audit_records and isinstance(audit_records[-1], Mapping) else {}
        terminal_state = last_record.get("terminal_state", last_record.get("state"))
        is_terminal = last_record.get("event_type") == "terminal_state" and terminal_state in TERMINAL_STATES
        if is_terminal:
            if idempotency.get("terminal_state") != terminal_state:
                reasons.append("recovery replay idempotency terminal state contradicts audit terminal state")
        elif idempotency.get("terminal_state") is not None:
            reasons.append("recovery replay non-terminal prefix cannot claim an idempotency terminal state")
        if not is_terminal and replay.get("resume_safe") is not True:
            reasons.append("recovery replay non-terminal audit prefix must be explicitly safe to resume")
        if not is_terminal and (replay.get("recovered") is not False or replay.get("rollback_verified") is not False):
            reasons.append("recovery replay non-terminal audit prefix cannot claim recovery or rollback completion")
    return {"accepted": not reasons, "reasons": reasons, "replay_hash": replay.get("hash"), "recomputed_replay_hash": recomputed_replay_hash}


def validate_release_replay_contract(replay: Mapping[str, Any], audit_records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    reasons: list[str] = []
    if replay.get("purpose") != "release_regression":
        reasons.append("release replay purpose must be release_regression")
    if replay.get("source") != "audit":
        reasons.append("release replay source must be audit")
    if not bool(replay.get("release_gates_passed")):
        reasons.append("release replay gates must pass")
    recomputed_replay_hash = compute_replay_hash(replay)
    replay_hash = replay.get("hash")
    if not _sha(replay_hash):
        reasons.append("release replay must have a replay hash")
    elif _full_sha(replay_hash) and replay_hash != recomputed_replay_hash:
        reasons.append("release replay hash must match canonical replay content excluding its own hash field")
    reasons.extend(
        _audit_chain_reasons(
            replay,
            audit_records,
            replay_kind="release",
            require_terminal=True,
        )
    )
    return {"accepted": not reasons, "reasons": reasons, "replay_hash": replay.get("hash"), "recomputed_replay_hash": recomputed_replay_hash}


def _audit_chain_reasons(
    replay: Mapping[str, Any],
    audit_records: Sequence[Any],
    *,
    replay_kind: str,
    require_terminal: bool,
) -> list[str]:
    label = f"{replay_kind} replay"
    minimum_records = 3 if require_terminal else 2
    if len(audit_records) < minimum_records:
        return [f"{label} requires a complete terminal audit chain"]
    if any(not isinstance(record, Mapping) for record in audit_records):
        return [f"{label} audit chain records must be objects"]

    reasons: list[str] = []
    source_episode_id = replay.get("source_episode_id")
    source_head = replay.get("source_audit_head_hash")
    expected_head = replay.get("expected_terminal_head_hash")
    if not isinstance(source_episode_id, str) or not source_episode_id:
        reasons.append(f"{label} must bind a source episode id")
    if not _sha(source_head):
        reasons.append(f"{label} must bind source audit head hash")
    if expected_head != source_head or not _sha(expected_head):
        reasons.append(f"{label} expected terminal head hash must match source audit head")

    previous_head: Any = None
    previous_canonical_head: Any = None
    seen_heads: set[str] = set()
    tail_is_terminal_event = audit_records[-1].get("event_type") == "terminal_state"
    for index, record in enumerate(audit_records, start=1):
        if record.get("sequence") != index:
            reasons.append(f"{label} audit chain sequence is invalid")
        if record.get("episode_id") != source_episode_id:
            reasons.append(f"{label} audit chain episode id mismatch")
        head = record.get("head_hash")
        if not isinstance(head, str) or not _sha(head) or head in seen_heads:
            reasons.append(f"{label} audit chain head hash is invalid")
        else:
            seen_heads.add(head)
        if index == 1:
            if record.get("event_type") != "episode_started" or record.get("previous_hash") not in {None, "GENESIS"}:
                reasons.append(f"{label} audit chain must start at episode_started")
        elif record.get("previous_hash") != previous_head:
            reasons.append(f"{label} audit chain linkage is invalid")
        if _full_sha(record.get("previous_hash")) and record.get("previous_hash") != previous_canonical_head:
            reasons.append(f"{label} audit chain canonical linkage is invalid")
        is_terminal_tail = tail_is_terminal_event and index == len(audit_records)
        if index > 1 and not is_terminal_tail and record.get("event_type") != "attempt_recorded":
            reasons.append(f"{label} audit chain event type is invalid")
        canonical_head = compute_audit_record_hash(record)
        if _full_sha(head) and head != canonical_head:
            reasons.append(f"{label} audit chain head hash must match canonical event content")
        previous_head = head
        previous_canonical_head = canonical_head

    last = audit_records[-1]
    terminal = last.get("terminal_state", last.get("state"))
    if require_terminal and (last.get("event_type") != "terminal_state" or terminal not in TERMINAL_STATES):
        reasons.append(f"{label} requires terminal audit chain")
    elif last.get("event_type") == "terminal_state" and terminal not in TERMINAL_STATES:
        reasons.append(f"{label} terminal audit state is invalid")
    attempt_records = audit_records[1:-1] if require_terminal else audit_records[1:]
    if not any(record.get("event_type") == "attempt_recorded" for record in attempt_records):
        reasons.append(f"{label} audit chain requires an attempt record")
    if previous_head != source_head:
        reasons.append(f"{label} source audit head does not match terminal chain head")
    if _full_sha(source_head) and previous_canonical_head != source_head:
        reasons.append(f"{label} source audit head does not match canonical terminal chain head")
    return list(dict.fromkeys(reasons))


def _sha(value: Any) -> bool:
    return _full_sha(value)


def _full_sha(value: Any) -> bool:
    return isinstance(value, str) and FULL_SHA256_PATTERN.fullmatch(value) is not None


def compute_replay_hash(replay: Mapping[str, Any]) -> str:
    payload = dict(replay)
    payload.pop("hash", None)
    return _stable_hash(payload)


def compute_audit_record_hash(record: Mapping[str, Any]) -> str:
    payload = dict(record)
    payload.pop("head_hash", None)
    return _stable_hash(payload)


def _stable_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"
