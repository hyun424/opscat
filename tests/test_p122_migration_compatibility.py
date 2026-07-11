from __future__ import annotations

from pathlib import Path

from app.services.p121_signals import P121_AUTHORITY_COUNTER_KEYS
from scripts.verify_p122_migration_compatibility import has_exact_p121_authority, run_migration_verification


def test_p122_fixture_upgrade_backup_restore_rollback_and_compatibility(tmp_path: Path) -> None:
    report = run_migration_verification(workdir=tmp_path)
    assert report["fixture_upgrade_executed"] is True
    assert report["backup_created"] is True
    assert report["restore_verified"] is True
    assert report["rollback_verified"] is True
    assert report["compatibility_verified"] is True
    assert report["authority_key_set_exact"] is True
    assert report["authority_values_int_zero"] is True
    assert report["expected_authority_keys"] == list(P121_AUTHORITY_COUNTER_KEYS)
    assert all(value == 0 for value in report["authority_counters"].values())


def test_migration_authority_compatibility_rejects_missing_extra_bool_and_nonzero() -> None:
    valid = {key: 0 for key in P121_AUTHORITY_COUNTER_KEYS}
    assert has_exact_p121_authority(valid) is True
    assert has_exact_p121_authority({key: value for key, value in valid.items() if key != P121_AUTHORITY_COUNTER_KEYS[0]}) is False
    assert has_exact_p121_authority({**valid, "unexpected": 0}) is False
    assert has_exact_p121_authority({**valid, P121_AUTHORITY_COUNTER_KEYS[0]: False}) is False
    assert has_exact_p121_authority({**valid, P121_AUTHORITY_COUNTER_KEYS[0]: 1}) is False
