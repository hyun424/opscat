from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p141_notification_authority import process_pending_notifications
from app.services.p142_loopback_transport_lab import LoopbackTransportConfig, load_loopback_transport_config
from tests.fixtures.p141.builders import P141Fixture, build_p141_fixture, write_json


@dataclass
class P142Fixture:
    root: Path
    p141: P141Fixture
    p142_data: Path
    config_path: Path
    config: LoopbackTransportConfig
    p141_release_evidence_path: Path
    p141_release_evidence_hash: str


def build_p142_fixture(tmp_path: Path, *, authority: str = "127.0.0.1:9", path: str = "/p142", **overrides: Any) -> P142Fixture:
    root = tmp_path.resolve()
    p141 = build_p141_fixture(root / "dependency")
    process_pending_notifications(p141.config, now=datetime(2026, 7, 14, 1, 0, tzinfo=UTC))
    p142_data = root / "p142"
    config_root = root / "config"
    for directory in (p142_data, config_root):
        directory.mkdir(parents=True, exist_ok=True)
        directory.chmod(0o700)
    p141_evidence = {
        "schema_version": "p141.release_evidence.v1",
        "status": "test-p141-qualified",
        "source": "p142-fixture",
        "p141_config_hash": p141.config.config_hash,
    }
    p141_evidence["evidence_hash"] = stable_hash(p141_evidence)
    p141_release_evidence_path = config_root / "p141-release-evidence.json"
    write_json(p141_release_evidence_path, p141_evidence)
    raw: dict[str, Any] = {
        "schema_version": "p142.loopback_transport_config.v1",
        "lab_id": "loopback-lab",
        "p141_config_path": str(p141.config_path),
        "p141_release_evidence_path": str(p141_release_evidence_path),
        "p141_expected_release_evidence_hash": p141_evidence["evidence_hash"],
        "routes": [
            {
                "route_id": "primary-route",
                "destination_id": "primary-operator",
                "method": "POST",
                "authority": authority,
                "path": path,
            },
            {
                "route_id": "backup-route",
                "destination_id": "backup-operator",
                "method": "POST",
                "authority": authority,
                "path": path,
            },
        ],
        "dispatch_dir": str(p142_data / "dispatch"),
        "journal_dir": str(p142_data / "journals"),
        "receipt_dir": str(p142_data / "receipts"),
        "cursor_path": str(p142_data / "cursor.json"),
        "run_dir": str(p142_data / "runs"),
        "max_attempts": 2,
        "connect_timeout_ms": 500,
        "response_timeout_ms": 500,
        "body_read_timeout_ms": 500,
        "max_request_bytes": 32_768,
        "max_response_bytes": 8_192,
        "max_total_dispatch_ms": 3_000,
        "base_backoff_ms": 1,
        "max_backoff_ms": 10,
        "max_retry_after_ms": 2_000,
        "max_artifact_files": 256,
        "max_total_bytes": 2_097_152,
        "max_receipt_bytes": 65_536,
        "min_artifact_free_bytes": 1,
    }
    raw.update(overrides)
    config_path = config_root / "p142.json"
    write_json(config_path, raw)
    return P142Fixture(
        root=root,
        p141=p141,
        p142_data=p142_data,
        config_path=config_path,
        config=load_loopback_transport_config(config_path),
        p141_release_evidence_path=p141_release_evidence_path,
        p141_release_evidence_hash=p141_evidence["evidence_hash"],
    )


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
