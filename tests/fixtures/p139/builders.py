from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p138_observation_triage_supervisor import (
    build_observation_triage_supervisor_config,
)
from app.services.p139_local_triage_service import (
    EXPECTED_P138_EVIDENCE_HASH,
    EXPECTED_P138_REVIEW_HASH,
    P138_QUALIFIED_STATUS,
    build_local_triage_service_bundle,
    serialize_p136_runtime,
    zero_forbidden_authority,
)
from tests.fixtures.p138.builders import P138Fixture, build_p138_fixture


@dataclass
class P139Fixture:
    root: Path
    p138: P138Fixture
    bundle_input: dict[str, Any]
    bundle: dict[str, Any]


def build_p139_fixture(tmp_path: Path, **overrides: Any) -> P139Fixture:
    p138 = build_p138_fixture(
        tmp_path,
        publish_genesis=True,
        accept_genesis=True,
    )
    config = build_observation_triage_supervisor_config(p138.config_input)
    serialized_runtime = serialize_p136_runtime(p138.p136_runtime)
    bundle_input: dict[str, Any] = {
        "service_id": "opscat-local-triage",
        "config_version": 1,
        "created_at": "2026-07-13T00:10:03Z",
        "base_dir_ref_hash": stable_hash({"path": p138.root.name}),
        "p138_config": config,
        "p136_runtime": serialized_runtime,
        "publisher_inputs": deepcopy(p138.publisher_inputs),
        "validated_p138_release_status": P138_QUALIFIED_STATUS,
        "p138_release_evidence_hash": EXPECTED_P138_EVIDENCE_HASH,
        "p138_final_review_hash": EXPECTED_P138_REVIEW_HASH,
        "service_lease_path": "p139/service.lock",
        "exit_receipt_path": "p139/exit-current.json",
        "exit_intent_path": "p139/exit-intent.json",
        "exit_history_dir": "p139/exit-history",
        "restart_control_path": "p139/restart-control.json",
        "restart_history_dir": "p139/restart-history",
        "status_snapshot_path": "p139/status.json",
        "limits": {
            "max_bundle_bytes": 8_388_608,
            "max_state_bytes": 4_194_304,
            "max_exit_history_records": 8,
            "startup_readiness_stale_after_ms": 30_000,
            "wall_limit_ms": 60_000,
            "cpu_limit_ms": 30_000,
            "peak_memory_limit_bytes": 268_435_456,
        },
        "forbidden_authority": zero_forbidden_authority(),
    }
    bundle_input.update(overrides)
    bundle = build_local_triage_service_bundle(bundle_input)
    return P139Fixture(
        root=p138.root,
        p138=p138,
        bundle_input=bundle_input,
        bundle=bundle,
    )
