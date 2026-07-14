from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.p139_local_triage_service import write_local_triage_service_bundle
from app.services.p140_p139_deadman_adapter import (
    P140AdapterConfig,
    load_p140_config,
    write_p140_config,
)
from tests.fixtures.p139.builders import P139Fixture, build_p139_fixture


@dataclass
class P140Fixture:
    root: Path
    p139: P139Fixture
    p139_bundle_path: Path
    p133_config_path: Path
    p140_config_path: Path
    data_root: Path
    config: P140AdapterConfig


def build_p140_fixture(tmp_path: Path) -> P140Fixture:
    root = tmp_path.resolve()
    config_root = root / "config"
    data_root = root / "p140-data"
    p139_root = root / "p139-base"
    for directory in (config_root, data_root, p139_root):
        directory.mkdir(parents=True, exist_ok=True)
    p139 = build_p139_fixture(p139_root)
    p139_bundle_path = config_root / "p139-bundle.json"
    write_local_triage_service_bundle(p139_bundle_path, p139.bundle)
    p133_config_path = config_root / "p133-config.json"
    p133_config: dict[str, Any] = {
        "schema_version": "p133.deadman_config.v1",
        "allowed_artifact_roots": [str(config_root), str(data_root)],
        "state_path": str(p139_bundle_path),
        "outbox_dir": str(data_root / "outbox"),
        "cursor_path": str(data_root / "cursor.json"),
        "ack_dir": str(data_root / "acks"),
        "runtime_ref": f"p139:{p139.bundle['service_id']}",
        "check_interval_seconds": 1,
        "heartbeat_timeout_seconds": 30,
        "reminder_interval_seconds": 10,
        "max_event_files": 32,
        "max_outbox_bytes": 1_048_576,
        "max_event_bytes": 32_768,
        "min_artifact_free_bytes": 1,
    }
    p133_config_path.write_text(json.dumps(p133_config, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    p140_config_path = root / "p140-config.json"
    write_p140_config(
        p140_config_path,
        {
            "schema_version": "p140.p139_deadman_adapter_config.v1",
            "adapter_id": "opscat-p139-deadman",
            "allowed_artifact_roots": [str(config_root), str(p139.root), str(data_root)],
            "p139_bundle_path": str(p139_bundle_path),
            "p139_base_path": str(p139.root),
            "p133_config_path": str(p133_config_path),
            "adapter_lease_path": str(data_root / "adapter.lock"),
            "max_config_bytes": 8_388_608,
            "max_runtime_seconds": 60,
            "max_peak_memory_bytes": 268_435_456,
        },
    )
    return P140Fixture(
        root=root,
        p139=p139,
        p139_bundle_path=p139_bundle_path,
        p133_config_path=p133_config_path,
        p140_config_path=p140_config_path,
        data_root=data_root,
        config=load_p140_config(p140_config_path),
    )
