"""Immutable P108 prevention outcome ledger records and JSONL replay."""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

GENESIS_HASH = "GENESIS"
LEDGER_REPLAY_SCHEMA = "p108.outcome_ledger_replay.v1"
REQUIRED_CROSS_PHASE_EDGES = frozenset(
    {
        "signal",
        "evidence",
        "forecast",
        "plan",
        "policy",
        "canary",
        "rollback",
        "final_outcome",
    }
)


@dataclass(frozen=True)
class PreventionOutcomeLedgerEntry:
    episode_id: str
    sequence: int
    parent_hash: str
    occurred_at: str
    p107_audit_head_hash: str
    p107_outcome_report_hash: str
    p107_release_replay_hash: str
    cross_phase_edges: Mapping[str, str]
    temporal_cutoffs: Mapping[str, Any]
    outcome_payload: Mapping[str, Any]
    idempotency_key: str
    schema_version: str = "p108.outcome_ledger_entry.v1"
    source_phase: str = "p108"
    authority_boundary: Mapping[str, Any] = field(
        default_factory=lambda: {
            "offline_only": True,
            "policy_write_path": False,
            "prompt_write_path": False,
            "runbook_write_path": False,
            "registry_write_path": False,
        }
    )


@dataclass(frozen=True)
class PreventionOutcomeLedgerReplay:
    deterministic_replay: bool
    replay_hash: str
    head_hash: str
    record_count: int
    entries: tuple[dict[str, Any], ...]


class PreventionOutcomeLedgerError(ValueError):
    """Raised when P108 outcome ledger append or replay validation fails."""


class PreventionOutcomeLedger:
    """In-memory append-only P108 outcome ledger."""

    def __init__(self, entries: list[Mapping[str, Any]] | None = None) -> None:
        self._entries = [_entry_payload(entry) for entry in entries or []]
        _validate_chain(self._entries, allow_empty=True)

    @property
    def entries(self) -> tuple[dict[str, Any], ...]:
        return tuple(copy.deepcopy(self._entries))

    @property
    def head_hash(self) -> str:
        return self._entries[-1]["entry_hash"] if self._entries else GENESIS_HASH

    def append(self, entry: PreventionOutcomeLedgerEntry | Mapping[str, Any]) -> str:
        payload = _entry_payload(entry)
        entry_hash, appended = _append_payload(self._entries, payload)
        if appended:
            self._entries.append(payload)
        return entry_hash


class JsonlPreventionOutcomeLedgerStore:
    """Append-only JSONL store for local P108 outcome ledger entries."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.flush_count = 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def append(self, entry: PreventionOutcomeLedgerEntry | Mapping[str, Any]) -> str:
        existing = _read_jsonl_entries(self.path, allow_empty=True)
        _validate_chain(existing, allow_empty=True)
        payload = _entry_payload(entry)
        entry_hash, appended = _append_payload(existing, payload)
        if not appended:
            return entry_hash
        line = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
            self.flush_count += 1
        return entry_hash


def canonical_entry_bytes(entry: PreventionOutcomeLedgerEntry | Mapping[str, Any]) -> bytes:
    payload = _entry_payload(entry)
    payload.pop("entry_hash", None)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def ledger_entry_hash(entry: PreventionOutcomeLedgerEntry | Mapping[str, Any]) -> str:
    return _sha256_json(json.loads(canonical_entry_bytes(entry).decode("ascii")))


def replay_prevention_outcome_ledger(
    store_or_path: JsonlPreventionOutcomeLedgerStore | str | Path,
) -> PreventionOutcomeLedgerReplay:
    path = Path(store_or_path.path) if isinstance(store_or_path, JsonlPreventionOutcomeLedgerStore) else Path(store_or_path)
    entries = _read_jsonl_entries(path, allow_empty=False)
    head_hash = _validate_chain(entries, allow_empty=False)
    replay_model = {
        "schema_version": LEDGER_REPLAY_SCHEMA,
        "record_count": len(entries),
        "head_hash": head_hash,
        "entries": entries,
    }
    return PreventionOutcomeLedgerReplay(
        deterministic_replay=True,
        replay_hash=_sha256_json(replay_model),
        head_hash=head_hash,
        record_count=len(entries),
        entries=tuple(entries),
    )


def _entry_payload(entry: PreventionOutcomeLedgerEntry | Mapping[str, Any]) -> dict[str, Any]:
    if dataclasses.is_dataclass(entry):
        if isinstance(entry, type):
            raise PreventionOutcomeLedgerError("ledger entry must be an instance, not a dataclass type")
        payload = dataclasses.asdict(entry)
    elif isinstance(entry, Mapping):
        payload = dict(entry)
    else:
        raise PreventionOutcomeLedgerError(f"unsupported ledger entry type {type(entry).__name__}")
    return _freeze_jsonable(payload)


def _prepare_payload_for_append(payload: dict[str, Any], existing: list[dict[str, Any]]) -> None:
    expected_sequence = len(existing) + 1
    sequence = payload.get("sequence")
    if sequence != expected_sequence:
        raise PreventionOutcomeLedgerError(f"append sequence violation: expected {expected_sequence}, got {sequence!r}")
    expected_parent = existing[-1]["entry_hash"] if existing else GENESIS_HASH
    if payload.get("parent_hash") != expected_parent:
        raise PreventionOutcomeLedgerError("append parent hash does not match current head")
    computed_hash = _computed_entry_hash(payload)
    if "entry_hash" in payload and payload["entry_hash"] != computed_hash:
        raise PreventionOutcomeLedgerError("append entry hash does not match canonical content")
    payload["entry_hash"] = computed_hash


def _append_payload(existing: list[dict[str, Any]], payload: dict[str, Any]) -> tuple[str, bool]:
    _validate_required_content(payload)

    duplicate = _find_duplicate(existing, payload)
    if duplicate is not None:
        expected_hash = _computed_entry_hash(payload)
        if duplicate.get("entry_hash") == expected_hash:
            return str(duplicate["entry_hash"]), False
        raise PreventionOutcomeLedgerError("episode or idempotency conflict with different content")

    _prepare_payload_for_append(payload, existing)
    return str(payload["entry_hash"]), True


def _find_duplicate(entries: list[dict[str, Any]], payload: Mapping[str, Any]) -> dict[str, Any] | None:
    episode_id = payload.get("episode_id")
    idempotency_key = payload.get("idempotency_key")
    for entry in entries:
        if entry.get("episode_id") == episode_id or entry.get("idempotency_key") == idempotency_key:
            return entry
    return None


def _validate_required_content(entry: Mapping[str, Any]) -> None:
    _require_content_hash(entry, "p107_audit_head_hash")
    _require_content_hash(entry, "p107_outcome_report_hash")
    _require_content_hash(entry, "p107_release_replay_hash")

    edges = entry.get("cross_phase_edges")
    if not isinstance(edges, Mapping):
        raise PreventionOutcomeLedgerError("cross_phase_edges must be an object")
    for edge in sorted(REQUIRED_CROSS_PHASE_EDGES):
        if edge not in edges:
            raise PreventionOutcomeLedgerError(f"missing required cross-phase edge: {edge}")
        _require_content_hash(edges, edge, context=f"cross_phase_edges.{edge}")

    cutoffs = entry.get("temporal_cutoffs")
    if not isinstance(cutoffs, Mapping) or not cutoffs:
        raise PreventionOutcomeLedgerError("temporal_cutoffs are required")

    outcome = entry.get("outcome_payload")
    if not isinstance(outcome, Mapping) or not outcome:
        raise PreventionOutcomeLedgerError("outcome_payload is required")

    if not entry.get("episode_id"):
        raise PreventionOutcomeLedgerError("episode_id is required")
    if not entry.get("idempotency_key"):
        raise PreventionOutcomeLedgerError("idempotency_key is required")


def _require_content_hash(source: Mapping[str, Any], key: str, *, context: str | None = None) -> None:
    value = source.get(key)
    if not (isinstance(value, str) and value.startswith("sha256:") and len(value) > len("sha256:")):
        raise PreventionOutcomeLedgerError(f"{context or key} must be content-bound with sha256:")


def _read_jsonl_entries(path: Path, *, allow_empty: bool) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if not text:
        if allow_empty:
            return []
        raise PreventionOutcomeLedgerError("empty outcome ledger is incomplete")
    if not text.endswith("\n"):
        raise PreventionOutcomeLedgerError("partial outcome ledger entry at end of file")
    entries = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PreventionOutcomeLedgerError(f"partial outcome ledger entry at line {line_no}") from exc
        if not isinstance(entry, dict):
            raise PreventionOutcomeLedgerError(f"outcome ledger entry at line {line_no} is not an object")
        entries.append(entry)
    return entries


def _validate_chain(entries: list[dict[str, Any]], *, allow_empty: bool) -> str:
    if not entries:
        if allow_empty:
            return GENESIS_HASH
        raise PreventionOutcomeLedgerError("empty outcome ledger is incomplete")

    previous_hash = GENESIS_HASH
    seen_parents: set[str] = set()
    seen_episode_ids: dict[str, str] = {}
    seen_idempotency_keys: dict[str, str] = {}

    for index, entry in enumerate(entries, start=1):
        sequence = entry.get("sequence")
        if sequence != index:
            reason = "sequence gap" if isinstance(sequence, int) and sequence > index else "sequence order"
            raise PreventionOutcomeLedgerError(f"{reason}: expected sequence {index}, got {sequence!r}")

        parent_hash = entry.get("parent_hash")
        if parent_hash != previous_hash:
            if parent_hash in seen_parents:
                raise PreventionOutcomeLedgerError(f"duplicate-parent fork at sequence {sequence}")
            raise PreventionOutcomeLedgerError(f"parent/order mismatch at sequence {sequence}")
        if parent_hash in seen_parents:
            raise PreventionOutcomeLedgerError(f"duplicate-parent fork at sequence {sequence}")
        seen_parents.add(str(parent_hash))

        _validate_required_content(entry)
        _validate_entry_hash(entry)
        entry_hash = str(entry["entry_hash"])
        _validate_unique_binding(seen_episode_ids, str(entry["episode_id"]), entry_hash, "episode")
        _validate_unique_binding(seen_idempotency_keys, str(entry["idempotency_key"]), entry_hash, "idempotency")
        previous_hash = entry_hash

    return previous_hash


def _validate_unique_binding(seen: dict[str, str], key: str, entry_hash: str, label: str) -> None:
    existing_hash = seen.get(key)
    if existing_hash is not None and existing_hash != entry_hash:
        raise PreventionOutcomeLedgerError(f"{label} conflict with different content")
    seen[key] = entry_hash


def _validate_entry_hash(entry: Mapping[str, Any]) -> None:
    entry_hash = entry.get("entry_hash")
    if entry_hash == _computed_entry_hash(entry):
        return
    raise PreventionOutcomeLedgerError(f"tamper or hash mismatch at sequence {entry.get('sequence')!r}")


def _computed_entry_hash(entry: Mapping[str, Any]) -> str:
    payload = dict(entry)
    payload.pop("entry_hash", None)
    return _sha256_json(payload)


def _sha256_json(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _freeze_jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _freeze_jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_freeze_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_freeze_jsonable(item) for item in value]
    return value
