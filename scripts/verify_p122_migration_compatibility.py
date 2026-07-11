#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from app.public_contracts import PUBLIC_CONTRACT_VERSION  # noqa: E402
from app.services.p110_evaluation import stable_hash  # noqa: E402
from app.services.p121_signals import P121_AUTHORITY_COUNTER_KEYS, zero_authority_counters  # noqa: E402


def run_migration_verification(*, workdir: Path) -> dict[str, Any]:
    workdir.mkdir(parents=True, exist_ok=True)
    fixture = workdir / "opscat-0.1.x-state.json"
    backup = workdir / "opscat-0.1.x-state.backup.json"
    upgraded = workdir / "opscat-0.2.0-state.json"
    restored = workdir / "opscat-restored-0.1.x-state.json"
    rollback = workdir / "opscat-rollback-state.json"

    legacy = _legacy_fixture()
    fixture.write_text(json.dumps(legacy, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    shutil.copy2(fixture, backup)

    upgraded_payload = _upgrade_legacy_state(json.loads(fixture.read_text(encoding="utf-8")))
    upgraded.write_text(json.dumps(upgraded_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    shutil.copy2(backup, restored)
    rollback_payload = _rollback_upgraded_state(json.loads(upgraded.read_text(encoding="utf-8")))
    rollback.write_text(json.dumps(rollback_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    upgraded_authority = upgraded_payload.get("authority_counters")
    restored_authority = legacy.get("authority_counters")
    rollback_authority = rollback_payload.get("authority_counters")
    authority_key_set_exact = all(isinstance(value, Mapping) and set(value) == set(P121_AUTHORITY_COUNTER_KEYS) for value in (upgraded_authority, restored_authority, rollback_authority))
    authority_values_int_zero = all(isinstance(value, Mapping) and has_exact_p121_authority(value) for value in (upgraded_authority, restored_authority, rollback_authority))

    report: dict[str, Any] = {
        "schema_version": "p122.migration_compatibility.v1",
        "source_version": legacy["release_version"],
        "target_version": upgraded_payload["release_version"],
        "fixture_upgrade_executed": True,
        "backup_created": backup.is_file() and _file_hash(backup) == _file_hash(fixture),
        "restore_verified": json.loads(restored.read_text(encoding="utf-8")) == legacy,
        "rollback_verified": rollback_payload["release_version"] == legacy["release_version"] and rollback_payload["records"] == legacy["records"],
        "compatibility_verified": _is_compatible(upgraded_payload),
        "authority_key_set_exact": authority_key_set_exact,
        "authority_values_int_zero": authority_values_int_zero,
        "expected_authority_keys": list(P121_AUTHORITY_COUNTER_KEYS),
        "authority_counters": zero_authority_counters(),
        "artifacts": {
            "fixture": str(fixture),
            "backup": str(backup),
            "upgraded": str(upgraded),
            "restored": str(restored),
            "rollback": str(rollback),
        },
    }
    report["report_hash"] = stable_hash(report)
    return report


def _legacy_fixture() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "opscat.local_state.v0",
        "release_version": "0.1.9",
        "records": [
            {"id": "inc-001", "kind": "replay", "status": "complete"},
            {"id": "audit-001", "kind": "audit", "status": "complete"},
        ],
        "authority_counters": zero_authority_counters(),
    }
    payload["fixture_hash"] = stable_hash(payload)
    return payload


def _upgrade_legacy_state(payload: Mapping[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") != "opscat.local_state.v0" or not str(payload.get("release_version", "")).startswith("0.1."):
        raise ValueError("unsupported_legacy_fixture")
    upgraded: dict[str, Any] = {
        "schema_version": "opscat.local_state.v1",
        "release_version": "0.2.0",
        "source_release_version": payload["release_version"],
        "public_contract_version": PUBLIC_CONTRACT_VERSION,
        "records": list(payload.get("records", [])),
        "legacy_fixture_hash": stable_hash({key: value for key, value in payload.items() if key != "fixture_hash"}),
        "authority_counters": payload.get("authority_counters", zero_authority_counters()),
    }
    upgraded["state_hash"] = stable_hash(upgraded)
    return upgraded


def _rollback_upgraded_state(payload: Mapping[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") != "opscat.local_state.v1" or payload.get("source_release_version") is None:
        raise ValueError("unsupported_rollback_fixture")
    rolled_back: dict[str, Any] = {
        "schema_version": "opscat.local_state.v0",
        "release_version": payload["source_release_version"],
        "records": list(payload.get("records", [])),
        "authority_counters": payload.get("authority_counters", zero_authority_counters()),
    }
    rolled_back["fixture_hash"] = stable_hash(rolled_back)
    return rolled_back


def _is_compatible(payload: Mapping[str, Any]) -> bool:
    return (
        payload.get("schema_version") == "opscat.local_state.v1"
        and payload.get("release_version") == "0.2.0"
        and payload.get("public_contract_version") == PUBLIC_CONTRACT_VERSION
        and isinstance(payload.get("records"), list)
        and isinstance(payload.get("authority_counters"), Mapping)
        and has_exact_p121_authority(payload["authority_counters"])
    )


def has_exact_p121_authority(value: Mapping[str, Any]) -> bool:
    return set(value) == set(P121_AUTHORITY_COUNTER_KEYS) and all(
        isinstance(value[key], int) and not isinstance(value[key], bool) and value[key] == 0 for key in P121_AUTHORITY_COUNTER_KEYS
    )


def _file_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workdir", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = run_migration_verification(workdir=args.workdir)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"report_hash": report["report_hash"], "rollback_verified": report["rollback_verified"]}, sort_keys=True))
    return 0 if all(report[key] is True for key in ("backup_created", "restore_verified", "rollback_verified", "compatibility_verified", "authority_key_set_exact", "authority_values_int_zero")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
