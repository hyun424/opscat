from __future__ import annotations

import hashlib
import json
import shutil
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p121_signals import zero_authority_counters as zero_p121_authority
from app.services.p134_observation_authority import build_contract, build_contract_core, build_proposal, build_review_receipt, evaluate_proposal
from app.services.p134_observation_authority import new_receipt_ledger as new_p134_receipt_ledger

STARTED_AT = "2026-07-13T00:10:00Z"
NOW = "2026-07-13T00:10:02Z"

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
    "index_stat_count",
    "index_file_open_count",
    "index_file_read_count",
    "index_bytes_read",
    "index_complete_lines_evaluated",
    "index_partial_bytes_observed",
    "index_read_intent_write_count",
    "segment_stat_count",
    "segment_file_open_count",
    "segment_file_read_count",
    "segment_bytes_read",
    "segment_records_parsed",
    "promotion_intent_write_count",
    "promotion_record_write_count",
    "checkpoint_write_count",
    "directory_fsync_count",
    "duplicate_resolution_count",
    "recovery_replay_count",
    "rotation_count",
    "rejection_record_count",
)

EVALUATOR_ACTIVITY_KEYS = (
    "runner_invocation_count",
    "profile_read_count",
    "artifact_write_count",
    "child_process_count",
    "signal_delivery_count",
)

RESOURCE_USAGE_KEYS = (
    "wall_time_ms",
    "cpu_time_ms",
    "child_cpu_time_ms",
    "peak_memory_bytes",
    "wall_limit_ms",
    "cpu_limit_ms",
    "peak_memory_limit_bytes",
)

RELEASE_STATUS = "p136_incremental_local_observation_qualified"
TEST_SOURCE_BINDINGS = {
    "app/services/p136_incremental_observer.py": stable_hash({"source": "p136-test"})
}
P135_FIXTURE_ROOT = Path("evals/p135/input/exports")
PROVIDER_CASES: tuple[dict[str, str], ...] = (
    {
        "source_id": "grafana-dashboard",
        "provider": "grafana",
        "format": "grafana.dashboard.classic.v1",
        "signal_family": "topology",
        "capability": "telemetry.topology.read",
        "fixture": "grafana_dashboard.json",
    },
    {
        "source_id": "loki-streams",
        "provider": "loki",
        "format": "loki.query_range.streams.v1",
        "signal_family": "logs",
        "capability": "telemetry.logs.read",
        "fixture": "loki_streams.json",
    },
    {
        "source_id": "otlp-metrics",
        "provider": "opentelemetry",
        "format": "otlp.file.jsonl.v1",
        "signal_family": "metrics",
        "capability": "telemetry.metrics.read",
        "fixture": "otlp_metrics.jsonl",
    },
    {
        "source_id": "prometheus-matrix",
        "provider": "prometheus",
        "format": "prometheus.query_range.matrix.v1",
        "signal_family": "metrics",
        "capability": "telemetry.metrics.read",
        "fixture": "prometheus_matrix.json",
    },
    {
        "source_id": "sentry-issues",
        "provider": "sentry",
        "format": "sentry.issues.api.list.v1",
        "signal_family": "events",
        "capability": "telemetry.events.read",
        "fixture": "sentry_issues.json",
    },
)


@dataclass
class ActivityProbe:
    events: list[str] = field(default_factory=list)
    index_open_count: int = 0
    index_read_count: int = 0
    segment_open_count: int = 0
    segment_read_count: int = 0

    def record(self, event: str) -> None:
        self.events.append(event)
        if event == "index_open":
            self.index_open_count += 1
        elif event == "index_read":
            self.index_read_count += 1
        elif event == "segment_open":
            self.segment_open_count += 1
        elif event == "segment_read":
            self.segment_read_count += 1

    def assert_no_index_access_before_intent(self) -> None:
        assert "write_index_read_intent" in self.events
        first_intent = self.events.index("write_index_read_intent")
        first_index_events = [self.events.index(event) for event in ("index_open", "index_read") if event in self.events]
        assert first_index_events
        assert min(first_index_events) > first_intent


def canonical_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def content_hash(data: bytes | dict[str, Any]) -> str:
    raw = canonical_bytes(data) if isinstance(data, dict) else data
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def zero_forbidden_authority() -> dict[str, int]:
    return {key: 0 for key in FORBIDDEN_AUTHORITY_KEYS}


def zero_runtime_activity(**overrides: int) -> dict[str, int]:
    values = {key: 0 for key in RUNTIME_ACTIVITY_KEYS}
    values.update(overrides)
    return values


def zero_evaluator_activity(**overrides: int) -> dict[str, int]:
    values = {key: 0 for key in EVALUATOR_ACTIVITY_KEYS}
    values.update(overrides)
    return values


def bounded_resource_usage(**overrides: int) -> dict[str, int]:
    values = {
        "wall_time_ms": 100,
        "cpu_time_ms": 30,
        "child_cpu_time_ms": 5,
        "peak_memory_bytes": 8_388_608,
        "wall_limit_ms": 30_000,
        "cpu_limit_ms": 15_000,
        "peak_memory_limit_bytes": 134_217_728,
    }
    values.update(overrides)
    return values


def p134_contract() -> dict[str, Any]:
    core = build_contract_core(
        {
            "contract_id": "p136-incremental-local-observer",
            "contract_version": 1,
            "subject_ref_hash": stable_hash({"subject": "p136-local-index"}),
            "max_authority_level": "OA1_LOCAL_ARTIFACT",
            "allowed_hosts": ["local-artifact.telemetry-read"],
            "allowed_methods": ["LOCAL_READ_FILE"],
            "allowed_capabilities": ["telemetry.events.read", "telemetry.logs.read", "telemetry.metrics.read", "telemetry.topology.read"],
            "budgets": {
                "window_seconds": 3600,
                "max_allowed_requests_per_window": 50,
                "max_allowed_estimated_response_bytes_per_window": 2_000_000,
                "max_allowed_estimated_records_per_window": 20_000,
                "max_unique_hosts_per_window": 1,
                "max_unique_methods_per_window": 1,
                "max_unique_capabilities_per_window": 4,
                "max_single_response_bytes": 100_000,
                "max_timeout_ms": 5_000,
                "max_attempt_number": 1,
            },
            "valid_from": "2026-07-13T00:00:00Z",
            "expires_at": "2026-07-14T00:00:00Z",
            "default_decision": "deny",
            "kill_switch": False,
            "action_authority": zero_p121_authority(),
        }
    )
    review = build_review_receipt(
        core,
        {
            "decision": "approve",
            "reviewer_ref_hash": stable_hash({"reviewer": "p136-independent-reviewer"}),
            "reviewed_at": "2026-07-13T00:00:01Z",
            "expires_at": "2026-07-13T23:59:59Z",
        },
    )
    return build_contract(core, review)


def authority_bundle(*, index_receipts: int = 3, segment_receipts: int = 5) -> dict[str, Any]:
    contract = p134_contract()
    ledger = new_p134_receipt_ledger(contract, window_started_at="2026-07-13T00:00:00Z")
    receipts: list[dict[str, Any]] = []
    requests: list[tuple[str, str, str, int, int]] = []
    for index in range(index_receipts):
        requests.append((f"p136-index-{index + 1}", "telemetry.events.read", stable_hash({"index": "current"}), 4096, 100))
    for index in range(segment_receipts):
        capability = PROVIDER_CASES[index % len(PROVIDER_CASES)]["capability"]
        requests.append(
            (
                f"p136-segment-{index + 1}",
                capability,
                stable_hash({"segment": index + 1}),
                1024,
                10,
            )
        )
    for sequence, (request_id, capability, source_ref_hash, estimated_bytes, estimated_records) in enumerate(requests, start=1):
        proposal = build_proposal(
            {
                "request_id": request_id,
                "sequence": sequence,
                "proposed_at": f"2026-07-13T00:{sequence:02d}:00Z",
                "requested_level": "OA1_LOCAL_ARTIFACT",
                "source_ref_hash": source_ref_hash,
                "host_label": "local-artifact.telemetry-read",
                "method": "LOCAL_READ_FILE",
                "capability": capability,
                "estimated_response_bytes": estimated_bytes,
                "estimated_records": estimated_records,
                "timeout_ms": 1000,
                "attempt_number": 1,
            }
        )
        result = evaluate_proposal(contract, proposal, ledger)
        assert result.receipt["decision"] == "allowed"
        receipts.append(result.receipt)
        ledger = result.ledger
    return {
        "contract": contract,
        "review_receipt": contract["review_receipt"],
        "receipt_ledger": ledger,
        "index_receipts": receipts[:index_receipts],
        "segment_receipts": receipts[index_receipts:],
        "contract_bytes": canonical_bytes(contract),
        "review_receipt_bytes": canonical_bytes(contract["review_receipt"]),
        "receipt_ledger_bytes": canonical_bytes(ledger),
        "index_receipt_bytes": [canonical_bytes(receipt) for receipt in receipts[:index_receipts]],
        "segment_receipt_bytes": [canonical_bytes(receipt) for receipt in receipts[index_receipts:]],
    }


def config_input(tmp_path: Path, bundle: dict[str, Any] | None = None, **overrides: Any) -> dict[str, Any]:
    authority = bundle or authority_bundle()
    base = tmp_path / "observer"
    data = base / "data"
    state = base / "state"
    for path in (data, state):
        path.mkdir(parents=True, exist_ok=True)
    value: dict[str, Any] = {
        "observer_id": "p136-local-observer",
        "config_version": 1,
        "created_at": "2026-07-13T00:00:02Z",
        "base_dir": {"path_ref_hash": stable_hash({"path": "observer"})},
        "data_root": {"path_ref_hash": stable_hash({"path": "observer/data"})},
        "state_root": {"path_ref_hash": stable_hash({"path": "observer/state"})},
        "index_path": "data/index.jsonl",
        "checkpoint_path": "state/checkpoint.json",
        "index_intent_dir": "state/index-intents",
        "journal_dir": "state/journal",
        "promotion_dir": "state/promotions",
        "lease_path": "state/p136.lock",
        "p134_contract_hash": authority["contract"]["contract_hash"],
        "p134_receipt_ledger_hash": authority["receipt_ledger"]["ledger_hash"],
        "index_source_ref_hash": stable_hash({"index": "current"}),
        "index_read_receipt_hashes": [receipt["receipt_hash"] for receipt in authority["index_receipts"]],
        "limits": limits(),
        "forbidden_authority": zero_forbidden_authority(),
    }
    value.update(overrides)
    return value


def limits(**overrides: int) -> dict[str, int]:
    value = {
        "poll_interval_ms": 25,
        "max_cycles": 3,
        "max_receipt_pool_size": 8,
        "max_whole_index_bytes": 4096,
        "max_complete_lines_per_cycle": 100,
        "max_index_line_bytes": 2048,
        "max_json_depth": 16,
        "max_json_nodes": 1000,
        "max_json_string_bytes": 512,
        "max_pending_entries": 16,
        "max_promotions_per_cycle": 8,
        "max_journal_bytes": 65_536,
        "max_promotion_bytes": 65_536,
        "max_consecutive_failures": 2,
        "max_clock_rollback_ms": 250,
        "max_retained_entry_identities": 64,
    }
    value.update(overrides)
    return value


def index_entry_input(sequence: int = 1, previous_entry_hash: str | None = None, **overrides: Any) -> dict[str, Any]:
    segment_bytes = b'{"status":"ok","value":1}\n'
    value: dict[str, Any] = {
        "entry_id": f"entry-{sequence:04d}",
        "entry_sequence": sequence,
        "segment_id": f"segment-{sequence:04d}",
        "source_id": f"source-{sequence:04d}",
        "provider": "prometheus",
        "format": "prometheus.query_range.matrix.v1",
        "signal_family": "metrics",
        "relative_segment_path": f"segments/{sequence:04d}.json",
        "expected_content_hash": content_hash(segment_bytes),
        "expected_bytes": len(segment_bytes),
        "expected_records": 1,
        "segment_authority_receipt_hash": stable_hash({"segment_receipt": sequence}),
        "segment_authority_capability": "telemetry.metrics.read",
        "created_at": f"2026-07-13T00:10:{sequence:02d}Z",
        "previous_entry_hash": previous_entry_hash,
        "rotation_from_hash": None,
    }
    value.update(overrides)
    return value


def self_hash_entry(entry_without_hash: dict[str, Any]) -> dict[str, Any]:
    entry = deepcopy(entry_without_hash)
    entry.setdefault("schema_version", "p136.incremental_index_entry.v1")
    entry["entry_hash"] = stable_hash(entry)
    return entry


def copy_p135_fixture_tree(tmp_path: Path) -> Path:
    root = tmp_path / "exports"
    root.mkdir(exist_ok=True)
    for case in PROVIDER_CASES:
        shutil.copyfile(P135_FIXTURE_ROOT / case["fixture"], root / case["fixture"])
    return root


def provider_index_entries(segment_receipts: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    previous_hash: str | None = None
    for sequence, case in enumerate(PROVIDER_CASES, start=1):
        content = (P135_FIXTURE_ROOT / case["fixture"]).read_bytes()
        receipt_hash = segment_receipts[sequence - 1]["receipt_hash"] if segment_receipts is not None else stable_hash({"segment_receipt": sequence})
        entry = self_hash_entry(
            index_entry_input(
                sequence,
                previous_entry_hash=previous_hash,
                entry_id=f"entry-{case['source_id']}",
                segment_id=f"segment-{case['source_id']}",
                source_id=case["source_id"],
                provider=case["provider"],
                format=case["format"],
                signal_family=case["signal_family"],
                relative_segment_path=case["fixture"],
                expected_content_hash=content_hash(content),
                expected_bytes=len(content),
                expected_records=2 if case["provider"] in {"prometheus", "loki"} else 1,
                segment_authority_receipt_hash=receipt_hash,
                segment_authority_capability=case["capability"],
            )
        )
        entries.append(entry)
        previous_hash = entry["entry_hash"]
    return entries


def checkpoint(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": "p136.observation_checkpoint.v1",
        "config_hash": stable_hash({"config": "p136"}),
        "index_identity_hash": stable_hash({"index_identity": 1}),
        "committed_cursor": 0,
        "consumed_prefix_hash": content_hash(b""),
        "observed_index_size": 0,
        "pending_partial": None,
        "next_entry_sequence": 1,
        "next_promotion_sequence": 1,
        "last_entry_hash": None,
        "last_promotion_hash": None,
        "reserved_index_read_receipt_hashes": [],
        "consumed_index_read_receipt_hashes": [],
        "canonical_entry_identities": {},
        "promotion_keys": {},
        "counters": zero_runtime_activity(),
        "forbidden_authority": zero_forbidden_authority(),
        "updated_at": NOW,
    }
    value.update(overrides)
    value["checkpoint_hash"] = stable_hash(value)
    return value


def pending_partial_state(**overrides: Any) -> dict[str, Any]:
    pending = {
        "file_identity_hash": stable_hash({"index_identity": 1}),
        "line_start_cursor": 128,
        "pending_byte_hash": content_hash(b'{"entry_id":"partial"'),
        "pending_byte_length": 21,
        "observed_index_size": 149,
    }
    pending.update(overrides)
    return pending


def promotion_record(entry: dict[str, Any] | None = None, *, namespace: str = "a", status: str = "success") -> dict[str, Any]:
    source_entry = entry or self_hash_entry(index_entry_input())
    manifest_hash = stable_hash({"p135_manifest": namespace})
    ledger_hash = stable_hash({"p135_ledger": namespace})
    value = {
        "schema_version": "p136.promotion_record.v1",
        "promotion_sequence": 1,
        "entry_hash": source_entry["entry_hash"],
        "status": status,
        "p135_manifest_hash": manifest_hash,
        "p135_artifact_spec_hash": stable_hash({"artifact": namespace}),
        "p134_segment_receipt_hash": source_entry["segment_authority_receipt_hash"],
        "p135_execution_receipt_hash": stable_hash({"execution": namespace}),
        "p135_receipt_ledger_hash": ledger_hash,
        "p135_normalized_bundle_hash": stable_hash({"bundle": namespace}),
        "promotion_key": stable_hash({"entry": source_entry["entry_hash"], "manifest": manifest_hash, "ledger": ledger_hash, "status": status}),
        "activity": zero_runtime_activity(
            segment_file_open_count=1,
            segment_file_read_count=1,
            segment_records_parsed=1,
        ),
        "forbidden_authority": zero_forbidden_authority(),
    }
    value["promotion_hash"] = stable_hash(value)
    return value


def runtime_inputs(
    tmp_path: Path,
    *,
    authority: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    checkpoint_value: dict[str, Any] | None = None,
    probe: ActivityProbe | None = None,
) -> dict[str, Any]:
    bundle = authority or authority_bundle()
    cfg = config or config_input(tmp_path, bundle)
    base_path = tmp_path / "observer"
    index_path = base_path / str(cfg["index_path"])
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.touch(exist_ok=True)
    value = {
        "config": cfg,
        "authority": bundle,
        "checkpoint": checkpoint_value or checkpoint(),
        "p135_bundles_by_entry_hash": {},
        "probe": probe or ActivityProbe(),
        "now": NOW,
        "base_path": base_path,
    }
    if len(bundle["segment_receipts"]) >= len(PROVIDER_CASES):
        entries = provider_index_entries(bundle["segment_receipts"])
        value["provider_entries"] = {str(entry["provider"]): entry for entry in entries}
        value["export_root"] = copy_p135_fixture_tree(tmp_path)
    return value


def release_case(case_id: int, *, passed: bool = True, status: str = "passed") -> dict[str, Any]:
    case = {
        "case_id": f"p136-case-{case_id:02d}",
        "category": "fixed-matrix",
        "semantic": f"deterministic P136 release semantic {case_id:02d}",
        "expected": "pass",
        "actual": "pass" if passed else "fail",
        "status": status,
        "duplicate_segment_reads": 0,
        "duplicate_promotions": 0,
        "provider_first_batch_promotion": case_id <= 5,
        "evidence": {
            "executed": True,
            "case_ordinal": case_id,
            "measured_duplicate_segment_reads": 0,
            "measured_duplicate_promotions": 0,
        },
    }
    case["case_evidence_hash"] = stable_hash(case)
    return case


def independent_review_artifact(
    source_bindings: dict[str, str] | None = None,
) -> dict[str, Any]:
    review = {
        "schema_version": "p136.independent_review.v1",
        "reviewer_role": "independent_code_reviewer",
        "implementation_role": "implementation_agent",
        "reviewer_context_hash": stable_hash({"context": "independent-test-reviewer"}),
        "implementation_context_hash": stable_hash({"context": "test-implementation"}),
        "reviewed_source_hashes": dict(sorted((source_bindings or TEST_SOURCE_BINDINGS).items())),
        "findings": {"p0": 0, "p1": 0, "p2": 0, "p3": 0},
        "decision": "approve",
        "limitations": [
            "reviewer_identity_unauthenticated",
            "local_artifact_only_no_live_provider_claim",
            "no_action_authority",
        ],
    }
    review["independent_review_hash"] = stable_hash(review)
    return review


def release_evidence(case_count: int = 50, *, status: str = RELEASE_STATUS) -> dict[str, Any]:
    cases = [release_case(index) for index in range(1, case_count + 1)]
    review = independent_review_artifact()
    evidence = {
        "schema_version": "p136.release_evidence.v1",
        "status": status,
        "cases": cases,
        "totals": {"expected": case_count, "passed": case_count, "failed": 0},
        "provider_first_batch_promotions": 5,
        "duplicate_promotions": 0,
        "duplicate_segment_reads": 0,
        "exact_schema_gates": True,
        "release_gates": True,
        "forbidden_authority": zero_forbidden_authority(),
        "runtime_activity": zero_runtime_activity(
            index_file_open_count=50,
            index_file_read_count=50,
        ),
        "evaluator_activity": zero_evaluator_activity(runner_invocation_count=1),
        "resource_usage": bounded_resource_usage(),
        "source_bindings": dict(TEST_SOURCE_BINDINGS),
        "independent_review_hash": review["independent_review_hash"],
    }
    evidence["evidence_hash"] = stable_hash(evidence)
    return evidence
