from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.p142_loopback_transport_lab import process_loopback_transport
from app.services.p143_egress_contract_lab import EgressContractConfig, load_egress_contract_config
from tests.fixtures.p141.builders import write_json
from tests.fixtures.p142.builders import P142Fixture, build_p142_fixture


@dataclass
class P143Fixture:
    root: Path
    p142: P142Fixture
    config_path: Path
    profile_path: Path
    config: EgressContractConfig


def build_p143_fixture(tmp_path: Path, **overrides: Any) -> P143Fixture:
    digest = hashlib.sha256(str(tmp_path.resolve()).encode("utf-8")).hexdigest()[:20].translate(str.maketrans("0123456789", "abcdefghij"))
    root = Path("/private/tmp") / ("locallab-" + digest)
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    p142 = build_p142_fixture(root / "dependency")
    process_loopback_transport(p142.config, sleep=lambda _seconds: None)
    data = root / "p143"
    profile_root = root / "profile"
    config_root = root / "config"
    for directory in (data, profile_root, config_root):
        directory.mkdir(parents=True, exist_ok=True)
        directory.chmod(0o700)
    profile = {
        "schema_version": "p143.shadow_provider_profile.v1",
        "profile_id": "local-shadow",
        "channels": [
            {
                "channel_type": "chat_message",
                "required_fields": ["title", "body", "severity", "idempotency_key", "dedupe_key"],
                "max_title_chars": 80,
                "max_body_chars": 220,
                "max_evidence_refs": 8,
                "supports_idempotency": True,
                "supports_dedupe": True,
                "rate_limit_policy": "manifest_only",
            },
            {
                "channel_type": "email_message",
                "required_fields": ["title", "body", "severity", "idempotency_key", "dedupe_key"],
                "max_title_chars": 120,
                "max_body_chars": 400,
                "max_evidence_refs": 8,
                "supports_idempotency": True,
                "supports_dedupe": True,
                "rate_limit_policy": "manifest_only",
            },
            {
                "channel_type": "pager_event",
                "required_fields": ["title", "severity", "idempotency_key", "dedupe_key"],
                "max_title_chars": 60,
                "max_body_chars": 160,
                "max_evidence_refs": 4,
                "supports_idempotency": True,
                "supports_dedupe": True,
                "rate_limit_policy": "manifest_only",
            },
            {
                "channel_type": "incident_comment",
                "required_fields": ["title", "body", "severity", "idempotency_key", "dedupe_key"],
                "max_title_chars": 100,
                "max_body_chars": 300,
                "max_evidence_refs": 12,
                "supports_idempotency": True,
                "supports_dedupe": True,
                "rate_limit_policy": "manifest_only",
            },
        ],
    }
    profile_path = profile_root / "shadow-profile.json"
    write_json(profile_path, profile)
    raw: dict[str, Any] = {
        "schema_version": "p143.egress_contract_config.v1",
        "lab_id": "egress-contract-lab",
        "immutable_read_roots": [str(p142.p141.p141_data), str(p142.p142_data), str(Path("evals/p142/output").resolve())],
        "p141_config_path": str(p142.p141.config_path),
        "p142_config_path": str(p142.config_path),
        "p142_release_evidence_path": str(Path("evals/p142/output/release-evidence.json").resolve()),
        "shadow_profile_path": str(profile_path),
        "intent_dir": str(data / "intents"),
        "projection_dir": str(data / "projections"),
        "result_dir": str(data / "results"),
        "journal_dir": str(data / "journals"),
        "cursor_path": str(root / "cursor-store" / "cursor.json"),
        "run_dir": str(data / "runs"),
        "max_sources_per_run": 16,
        "max_profiles_per_source": 8,
        "max_projection_bytes": 8192,
        "max_evidence_refs": 12,
        "max_artifact_files": 512,
        "max_total_bytes": 4_194_304,
        "min_artifact_free_bytes": 1,
    }
    raw.update(overrides)
    config_path = config_root / "p143.json"
    write_json(config_path, raw)
    return P143Fixture(root=root, p142=p142, config_path=config_path, profile_path=profile_path, config=load_egress_contract_config(config_path))


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
