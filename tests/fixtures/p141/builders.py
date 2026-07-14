from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.p133_deadman_outbox import DeadmanOutbox, load_deadman_config
from app.services.p141_notification_authority import NotificationConfig, load_notification_config


@dataclass
class P141Fixture:
    root: Path
    p133_config_path: Path
    p133_data: Path
    p141_data: Path
    config_path: Path
    config: NotificationConfig


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_p141_fixture(tmp_path: Path, **overrides: Any) -> P141Fixture:
    root = tmp_path.resolve()
    config_root = root / "config"
    p133_data = root / "p133"
    p141_data = root / "p141"
    for directory in (config_root, p133_data, p141_data):
        directory.mkdir(parents=True, exist_ok=True)
    state_path = p133_data / "monitor-state.json"
    state_path.write_text("{}\n", encoding="utf-8")
    p133_config_path = config_root / "p133.json"
    write_json(
        p133_config_path,
        {
            "schema_version": "p133.deadman_config.v1",
            "allowed_artifact_roots": [str(config_root), str(p133_data)],
            "state_path": str(state_path),
            "outbox_dir": str(p133_data / "outbox"),
            "cursor_path": str(p133_data / "cursor.json"),
            "ack_dir": str(p133_data / "acks"),
            "runtime_ref": "p141-fixture-runtime",
            "check_interval_seconds": 1,
            "heartbeat_timeout_seconds": 30,
            "reminder_interval_seconds": 5,
            "max_event_files": 64,
            "max_outbox_bytes": 1_048_576,
            "max_event_bytes": 32_768,
            "min_artifact_free_bytes": 1,
        },
    )
    p133_config = load_deadman_config(p133_config_path)
    DeadmanOutbox(
        p133_config,
        now=lambda: datetime(2026, 7, 14, 0, 0, tzinfo=UTC),
        watchdog_evaluator=lambda *_args, **_kwargs: {
            "healthy": False,
            "reason": "runtime_stopped",
            "state_hash": "sha256:" + "a" * 64,
            "heartbeat_age_seconds": 10,
        },
    ).check_once()
    raw: dict[str, Any] = {
        "schema_version": "p141.notification_config.v1",
        "simulator_id": "local-incident-notifier",
        "allowed_artifact_roots": [str(config_root), str(p133_data), str(p141_data)],
        "p133_config_path": str(p133_config_path),
        "envelope_dir": str(p141_data / "envelopes"),
        "receipt_dir": str(p141_data / "receipts"),
        "cursor_path": str(p141_data / "cursor.json"),
        "destination_ids": ["primary-operator", "backup-operator"],
        "transition_kinds": ["opened", "updated", "reminder", "recovered"],
        "template_version": "p141-deadman-v1",
        "poll_interval_seconds": 5,
        "max_envelope_bytes": 16_384,
        "max_receipt_bytes": 16_384,
        "max_artifact_files": 128,
        "max_total_bytes": 2_097_152,
        "min_artifact_free_bytes": 1,
    }
    raw.update(overrides)
    config_path = config_root / "p141.json"
    write_json(config_path, raw)
    return P141Fixture(
        root=root,
        p133_config_path=p133_config_path,
        p133_data=p133_data,
        p141_data=p141_data,
        config_path=config_path,
        config=load_notification_config(config_path),
    )
