from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p136_incremental_observer import (
    build_incremental_observer_config,
    observe_one_cycle,
)
from app.services.p137_contracts import (
    ALLOWED_REQUEST_CATALOG,
    FIXED_P136_HANDOFF_PATH,
    LIMIT_KEYS,
    P136_QUALIFIED_RELEASE_STATUS,
    build_classification_policy,
    build_continuous_mode,
    build_correlation_policy,
    build_ranking_policy,
    build_triage_agent_config,
)
from app.services.p137_p136_handoff import publish_p136_handoff_bundle
from app.services.p137_runtime import run_p137_runtime_once
from tests.fixtures.p136.builders import (
    ActivityProbe,
    authority_bundle,
    independent_review_artifact,
    provider_index_entries,
)
from tests.fixtures.p136.builders import (
    config_input as p136_config_input,
)
from tests.fixtures.p136.builders import (
    release_evidence as p136_release_evidence,
)
from tests.fixtures.p136.builders import (
    runtime_inputs as p136_runtime_inputs,
)

NOW = "2026-07-13T00:10:00Z"
P136_STATUS = "p136_incremental_local_observation_qualified"
P137_STATUS = "p137_local_evidence_triage_qualified"

FORBIDDEN_AUTHORITY_KEYS = (
    "provider_call_count",
    "live_connector_call_count",
    "network_call_count",
    "dns_lookup_count",
    "socket_call_count",
    "credential_read_count",
    "environment_read_count",
    "subprocess_launch_count",
    "shell_execution_count",
    "signal_count",
    "delivery_count",
    "remediation_count",
    "staging_mutation_count",
    "production_mutation_count",
    "operator_replacement_count",
)
RUNTIME_ACTIVITY_KEYS = (
    "supervisor_lease_acquire_count",
    "supervisor_state_read_count",
    "phase_write_count",
    "ledger_write_count",
    "heartbeat_write_count",
    "readiness_write_count",
    "termination_write_count",
    "reconciliation_count",
    "observation_count",
    "publication_count",
    "triage_count",
    "recovery_count",
    "no_work_count",
    "fsync_count",
)
EVALUATOR_ACTIVITY_KEYS = (
    "runner_invocation_count",
    "profile_read_count",
    "artifact_write_count",
    "fake_guard_injection_count",
    "signal_injection_count",
    "crash_injection_count",
)


def canonical_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def zero_forbidden_authority() -> dict[str, int]:
    return {key: 0 for key in FORBIDDEN_AUTHORITY_KEYS}


def zero_runtime_activity(**overrides: int) -> dict[str, int]:
    value = {key: 0 for key in RUNTIME_ACTIVITY_KEYS}
    value.update(overrides)
    return value


def zero_evaluator_activity(**overrides: int) -> dict[str, int]:
    value = {key: 0 for key in EVALUATOR_ACTIVITY_KEYS}
    value.update(overrides)
    return value


@lru_cache(maxsize=1)
def _qualified_p137_release_artifacts() -> tuple[dict[str, Any], dict[str, Any]]:
    project_root = Path(__file__).resolve().parents[3]
    evidence = json.loads(
        (project_root / "evals/p137/output/release-evidence.json").read_text(
            encoding="utf-8"
        )
    )
    review = json.loads(
        (project_root / "evals/p137/final-implementation-review.json").read_text(
            encoding="utf-8"
        )
    )
    if not isinstance(evidence, dict) or not isinstance(review, dict):
        raise AssertionError("qualified_p137_release_artifacts_invalid")
    return evidence, review


def p137_release_evidence() -> dict[str, Any]:
    evidence, _review = _qualified_p137_release_artifacts()
    return deepcopy(evidence)


def p137_final_implementation_review() -> dict[str, Any]:
    _evidence, review = _qualified_p137_release_artifacts()
    return deepcopy(review)


def p137_config(root: Path, *, chain_root: str) -> dict[str, Any]:
    limits = {key: index + 10 for index, key in enumerate(LIMIT_KEYS)}
    limits.update(
        {
            "max_promotions_per_cycle": 128,
            "max_records_per_cycle": 256,
            "max_incidents_open": 64,
            "max_correlation_window_ms": 900_000,
            "max_incident_duration_ms": 86_400_000,
            "max_hypotheses_per_incident": 64,
            "max_support_edges_per_hypothesis": 64,
            "max_contradiction_edges_per_hypothesis": 64,
            "max_missing_evidence_items_per_hypothesis": 64,
            "max_evidence_requests_per_incident": 8,
            "max_request_input_records": 256,
            "max_request_output_records": 64,
            "max_request_output_bytes": 65_536,
            "max_journal_bytes": 1_000_000,
            "max_ledger_records": 4_096,
            "max_cycle_wall_ms": 5_000,
            "max_agent_wall_ms": 20_000,
            "max_cpu_ms": 5_000,
            "max_peak_memory_bytes": 134_217_728,
            "max_cycles": 2,
            "poll_interval_ms": 1,
            "heartbeat_interval_ms": 1,
            "readiness_stale_after_ms": 5_000,
            "handoff_version_stale_after_ms": 5_000,
        }
    )
    readiness_path = "p137/readiness.json"
    return build_triage_agent_config(
        {
            "agent_id": "p137-p138-runtime",
            "config_version": 1,
            "created_at": NOW,
            "base_dir_ref_hash": stable_hash({"path": root.name}),
            "state_root_ref_hash": stable_hash({"path": "p137"}),
            "handoff_root_ref_hash": stable_hash({"path": "handoff"}),
            "p136_handoff_bundle_path": FIXED_P136_HANDOFF_PATH,
            "p136_handoff_chain_root_hash": chain_root,
            "checkpoint_path": "p137/checkpoint.json",
            "lease_path": "p137/p137.lock",
            "journal_dir": "p137/journal",
            "incident_dir": "p137/incidents",
            "hypothesis_dir": "p137/hypotheses",
            "request_dir": "p137/requests",
            "classification_dir": "p137/classifications",
            "heartbeat_path": "p137/heartbeat.json",
            "readiness_path": readiness_path,
            "termination_dir": "p137/terminations",
            "ledger_path": "p137/ledger.json",
            "validated_p136_release_status": P136_QUALIFIED_RELEASE_STATUS,
            "allowed_request_catalog": list(ALLOWED_REQUEST_CATALOG),
            "correlation_policy": build_correlation_policy(),
            "ranking_policy": build_ranking_policy(),
            "classification_policy": build_classification_policy(),
            "continuous_mode": build_continuous_mode(
                enabled=False,
                max_cycles=limits["max_cycles"],
                poll_interval_ms=limits["poll_interval_ms"],
                heartbeat_interval_ms=limits["heartbeat_interval_ms"],
                readiness_path=readiness_path,
                readiness_stale_after_ms=limits[
                    "readiness_stale_after_ms"
                ],
                handoff_version_stale_after_ms=limits[
                    "handoff_version_stale_after_ms"
                ],
            ),
            "limits": limits,
            "forbidden_authority": zero_forbidden_authority(),
        }
    )


def p138_config_input(
    *,
    p136_config: dict[str, Any],
    p137_config_value: dict[str, Any],
    p136_evidence: dict[str, Any],
    p137_evidence: dict[str, Any],
    **overrides: Any,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "supervisor_id": "p138-local-supervisor",
        "config_version": 1,
        "created_at": NOW,
        "base_dir_ref_hash": stable_hash({"path": "observer"}),
        "p136_config": deepcopy(p136_config),
        "p137_config": deepcopy(p137_config_value),
        "validated_p136_release_status": P136_STATUS,
        "validated_p137_release_status": P137_STATUS,
        "p136_release_evidence_hash": p136_evidence["evidence_hash"],
        "p137_release_evidence_hash": p137_evidence["evidence_hash"],
        "phase_path": "p138/phase.json",
        "ledger_path": "p138/ledger.json",
        "checkpoint_path": "p138/checkpoint.json",
        "lease_path": "p138/p138.lock",
        "heartbeat_path": "p138/heartbeat.json",
        "readiness_path": "p138/readiness.json",
        "termination_dir": "p138/terminations",
        "publisher_state_path": "publisher/state.json",
        "publisher_intent_path": "publisher/intent.json",
        "publisher_lease_path": "publisher/publisher.lock",
        "p136_handoff_bundle_path": FIXED_P136_HANDOFF_PATH,
        "limits": {
            "max_supervisor_cycles": 2,
            "poll_interval_ms": 1,
            "heartbeat_interval_ms": 1,
            "readiness_stale_after_ms": 5_000,
            "deadman_stale_after_ms": 10_000,
            "max_consecutive_failures": 2,
            "max_state_bytes": 2_000_000,
            "wall_limit_ms": 30_000,
            "cpu_limit_ms": 15_000,
            "peak_memory_limit_bytes": 134_217_728,
        },
        "forbidden_authority": zero_forbidden_authority(),
    }
    value.update(overrides)
    return value


@dataclass
class P138Fixture:
    root: Path
    p136_runtime: dict[str, Any]
    publisher_inputs: dict[str, Any]
    p136_evidence: dict[str, Any]
    p137_evidence: dict[str, Any]
    p137_review: dict[str, Any]
    config_input: dict[str, Any]
    entries: list[dict[str, Any]]
    genesis_observation: dict[str, Any] | None
    genesis_bundle: dict[str, Any] | None
    genesis_p137_result: dict[str, Any] | None


def _checkpoint_for_config(
    checkpoint: dict[str, Any], config: dict[str, Any]
) -> dict[str, Any]:
    value = deepcopy(checkpoint)
    value["config_hash"] = config["config_hash"]
    value["checkpoint_hash"] = stable_hash(
        {key: item for key, item in value.items() if key != "checkpoint_hash"}
    )
    return value


def build_p138_fixture(
    tmp_path: Path,
    *,
    genesis_entries: int = 1,
    publish_genesis: bool = True,
    accept_genesis: bool = False,
    partial_genesis: bool = False,
    index_receipts: int = 3,
) -> P138Fixture:
    authority = authority_bundle(index_receipts=index_receipts, segment_receipts=5)
    raw_p136_config = p136_config_input(
        tmp_path,
        authority,
        limits={
            **p136_config_input(tmp_path, authority)["limits"],
            "max_journal_bytes": 1_000_000,
            "max_promotion_bytes": 1_000_000,
            "max_cycle_outcome_bytes": 2_000_000,
        },
    )
    p136_runtime = p136_runtime_inputs(
        tmp_path,
        authority=authority,
        config=raw_p136_config,
        probe=ActivityProbe(),
    )
    config = build_incremental_observer_config(p136_runtime["config"])
    p136_runtime["config"] = config
    p136_runtime["checkpoint"] = _checkpoint_for_config(
        p136_runtime["checkpoint"], config
    )
    entries = provider_index_entries(authority["segment_receipts"])
    p136_runtime["provider_entries"] = {
        str(entry["entry_hash"]): entry for entry in entries
    }
    root = Path(p136_runtime["base_path"])
    index_path = root / str(config["index_path"])
    index_path.parent.mkdir(parents=True, exist_ok=True)
    initial_entry_count = genesis_entries if publish_genesis else 0
    index_path.write_bytes(
        b"".join(
            canonical_bytes(entry) + b"\n"
            for entry in entries[:initial_entry_count]
        )
    )
    review = independent_review_artifact()
    p136_evidence = p136_release_evidence(status=P136_STATUS)
    p137_evidence = p137_release_evidence()
    p137_review = p137_final_implementation_review()
    genesis_observation: dict[str, Any] | None = None
    genesis_bundle: dict[str, Any] | None = None
    genesis_p137_result: dict[str, Any] | None = None
    chain_root = stable_hash({"chain": "unused-until-publication"})
    if publish_genesis:
        genesis_observation = observe_one_cycle(p136_runtime)
        p136_runtime["checkpoint"] = deepcopy(
            genesis_observation["advanced_checkpoint"]
        )
        promotions = list(genesis_observation["promotion_records"])
        selected = promotions[-1:] if partial_genesis else promotions
        genesis_bundle = publish_p136_handoff_bundle(
            base_path=root,
            state_path="publisher/state.json",
            intent_path="publisher/intent.json",
            fixed_handoff_path=FIXED_P136_HANDOFF_PATH,
            lease_path="publisher/publisher.lock",
            p136_config=config,
            p136_runtime_authority=authority,
            now=str(p136_runtime["now"]),
            p136_checkpoint=genesis_observation["advanced_checkpoint"],
            canonical_entry_map=p136_runtime["provider_entries"],
            promotion_records=selected,
            p136_independent_review=review,
            p136_release_evidence=p136_evidence,
            created_at="2026-07-13T00:10:01Z",
        )
        chain_root = str(genesis_bundle["handoff_chain_root_hash"])
    p137_config_value = p137_config(root, chain_root=chain_root)
    if accept_genesis:
        if genesis_bundle is None:
            raise AssertionError("accept_genesis_requires_published_genesis")
        genesis_p137_result = run_p137_runtime_once(
            base_path=root,
            config=p137_config_value,
            now="2026-07-13T00:10:02Z",
        )
        if genesis_p137_result["status"] != "ok":
            raise AssertionError(genesis_p137_result)
    config_input = p138_config_input(
        p136_config=config,
        p137_config_value=p137_config_value,
        p136_evidence=p136_evidence,
        p137_evidence=p137_evidence,
    )
    publisher_inputs = {
        "canonical_entry_map": p136_runtime["provider_entries"],
        "p136_independent_review": review,
        "p136_release_evidence": p136_evidence,
        "p137_release_evidence": p137_evidence,
        "p137_final_implementation_review": p137_review,
        "created_at": "2026-07-13T00:10:03Z",
    }
    return P138Fixture(
        root=root,
        p136_runtime=p136_runtime,
        publisher_inputs=publisher_inputs,
        p136_evidence=p136_evidence,
        p137_evidence=p137_evidence,
        p137_review=p137_review,
        config_input=config_input,
        entries=entries,
        genesis_observation=genesis_observation,
        genesis_bundle=genesis_bundle,
        genesis_p137_result=genesis_p137_result,
    )


def append_observation_entry(fixture: P138Fixture, *, count: int = 1) -> None:
    checkpoint = fixture.p136_runtime["checkpoint"]
    consumed_entries = int(checkpoint["next_entry_sequence"]) - 1
    selected = fixture.entries[: consumed_entries + count]
    index_path = fixture.root / str(fixture.p136_runtime["config"]["index_path"])
    index_path.write_bytes(
        b"".join(canonical_bytes(entry) + b"\n" for entry in selected)
    )
