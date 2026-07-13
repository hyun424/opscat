#!/usr/bin/env python3
"""Run the source-bound P136 incremental-observer release qualification."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.p110_evaluation import stable_hash  # noqa: E402
from app.services.p121_signals import zero_authority_counters as zero_p121_authority  # noqa: E402
from app.services.p134_observation_authority import (  # noqa: E402
    build_contract,
    build_contract_core,
    build_proposal,
    build_review_receipt,
    evaluate_proposal,
)
from app.services.p134_observation_authority import (  # noqa: E402
    new_receipt_ledger as new_p134_receipt_ledger,
)
from app.services.p136_incremental_observer import (  # noqa: E402
    build_incremental_index_entry,
    build_incremental_observer_config,
    zero_forbidden_authority,
    zero_runtime_activity,
)
from app.services.p136_release_evidence import (  # noqa: E402
    P136_READY_STATUS,
    current_source_hashes,
    validate_independent_review_artifact,
)
from app.services.p136_runner import p136_release_case_matrix, run_p136_release_matrix  # noqa: E402

PROFILE_SCHEMA_VERSION = "p136.incremental_observer_profile.v1"
PROFILE_FIELDS = frozenset(
    {
        "schema_version",
        "case_matrix_version",
        "fixture_root",
        "output_artifacts",
        "required_case_ids",
        "resource_limits",
        "root_ref_hash",
    }
)
RESOURCE_LIMITS = {
    "wall_limit_ms": 30_000,
    "cpu_limit_ms": 15_000,
    "peak_memory_limit_bytes": 134_217_728,
}
EXPECTED_OUTPUT_ARTIFACTS = ["release-evidence.json"]
DEFAULT_OUTPUT_DIR = ROOT / "evals/p136/output"
DEFAULT_INDEPENDENT_REVIEW = ROOT / "evals/p136/independent-review.json"
NOW = "2026-07-13T00:10:02Z"
PROVIDERS: tuple[dict[str, Any], ...] = (
    {
        "source_id": "grafana-dashboard",
        "provider": "grafana",
        "format": "grafana.dashboard.classic.v1",
        "signal_family": "topology",
        "capability": "telemetry.topology.read",
        "fixture": "grafana_dashboard.json",
        "expected_records": 1,
    },
    {
        "source_id": "loki-streams",
        "provider": "loki",
        "format": "loki.query_range.streams.v1",
        "signal_family": "logs",
        "capability": "telemetry.logs.read",
        "fixture": "loki_streams.json",
        "expected_records": 2,
    },
    {
        "source_id": "otlp-metrics",
        "provider": "opentelemetry",
        "format": "otlp.file.jsonl.v1",
        "signal_family": "metrics",
        "capability": "telemetry.metrics.read",
        "fixture": "otlp_metrics.jsonl",
        "expected_records": 1,
    },
    {
        "source_id": "prometheus-matrix",
        "provider": "prometheus",
        "format": "prometheus.query_range.matrix.v1",
        "signal_family": "metrics",
        "capability": "telemetry.metrics.read",
        "fixture": "prometheus_matrix.json",
        "expected_records": 2,
    },
    {
        "source_id": "sentry-issues",
        "provider": "sentry",
        "format": "sentry.issues.api.list.v1",
        "signal_family": "events",
        "capability": "telemetry.events.read",
        "fixture": "sentry_issues.json",
        "expected_records": 1,
    },
)


class P136ProfileError(ValueError):
    """Raised when the canonical P136 release profile is unsafe or stale."""


class CanonicalRuntimeFactory:
    """Build isolated case runtimes from fixed local provider exports."""

    def __init__(self, work_root: Path, fixture_root: Path) -> None:
        self.work_root = work_root
        self.fixture_root = fixture_root
        self.authority = _build_authority(fixture_root)
        self.entries = _build_provider_entries(fixture_root, self.authority)

    def __call__(self, case_id: str) -> Mapping[str, Any]:
        if case_id not in {str(item["case_id"]) for item in p136_release_case_matrix()}:
            raise P136ProfileError("unknown_case_id")
        base_path = self.work_root / case_id
        (base_path / "data").mkdir(parents=True, exist_ok=True)
        (base_path / "state").mkdir(parents=True, exist_ok=True)
        (base_path / "data" / "index.jsonl").touch(exist_ok=True)
        config = build_incremental_observer_config(
            _config_input(base_path, self.authority)
        )
        return {
            "config": config,
            "authority": deepcopy(self.authority),
            "checkpoint": _checkpoint(config),
            "provider_entries": deepcopy(self.entries),
            "now": NOW,
            "base_path": base_path,
            "export_root": self.fixture_root,
        }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile",
        type=Path,
        default=ROOT / "evals/p136/input/incremental-observer-profile.json",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--independent-review",
        type=Path,
        default=DEFAULT_INDEPENDENT_REVIEW,
    )
    args = parser.parse_args(argv)
    try:
        profile = validate_profile(_read_json(args.profile))
        fixture_root = _fixture_root(profile)
        source_bindings = current_source_hashes(ROOT)
        independent_review = _mapping(
            _read_json(args.independent_review), "independent_review"
        )
        validate_independent_review_artifact(
            independent_review,
            expected_source_hashes=source_bindings,
        )
        args.output_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="p136-release-") as temporary:
            factory = CanonicalRuntimeFactory(Path(temporary), fixture_root)
            evidence = run_p136_release_matrix(
                args.output_dir,
                runtime_factory=factory,
                source_bindings=source_bindings,
                independent_review=independent_review,
                evaluator_activity={
                    "runner_invocation_count": 1,
                    "profile_read_count": 1,
                    "artifact_write_count": 1,
                    "child_process_count": 0,
                    "signal_delivery_count": 0,
                },
            )
        _write_exact_artifacts(
            args.output_dir,
            {"release-evidence.json": evidence},
            protected_paths=(args.profile, args.independent_review),
        )
        print(
            json.dumps(
                {
                    "release_status": evidence["status"],
                    "evidence_hash": evidence["evidence_hash"],
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0 if evidence["status"] == P136_READY_STATUS else 1
    except Exception as exc:
        print(
            json.dumps(
                {
                    "release_status": "p136_blocked",
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 1


def validate_profile(value: Any) -> Mapping[str, Any]:
    profile = _mapping(value, "profile")
    if set(profile) != PROFILE_FIELDS:
        raise P136ProfileError("invalid_profile_fields")
    if profile.get("schema_version") != PROFILE_SCHEMA_VERSION:
        raise P136ProfileError("invalid_profile_schema")
    if profile.get("case_matrix_version") != 1:
        raise P136ProfileError("invalid_case_matrix_version")
    if profile.get("required_case_ids") != [
        item["case_id"] for item in p136_release_case_matrix()
    ]:
        raise P136ProfileError("required_case_ids_mismatch")
    if profile.get("output_artifacts") != EXPECTED_OUTPUT_ARTIFACTS:
        raise P136ProfileError("output_artifacts_mismatch")
    if dict(_mapping(profile.get("resource_limits"), "resource_limits")) != RESOURCE_LIMITS:
        raise P136ProfileError("resource_limits_mismatch")
    fixture_root = _relative_path(profile.get("fixture_root"), "fixture_root")
    expected_root_hash = stable_hash(
        {"schema_version": "p136.fixture_root_ref.v1", "fixture_root": fixture_root}
    )
    if profile.get("root_ref_hash") != expected_root_hash:
        raise P136ProfileError("root_ref_hash_mismatch")
    return profile


def _fixture_root(profile: Mapping[str, Any]) -> Path:
    relative = _relative_path(profile.get("fixture_root"), "fixture_root")
    root = (ROOT / relative).resolve()
    if not root.is_relative_to(ROOT) or not root.is_dir() or root.is_symlink():
        raise P136ProfileError("fixture_root_unavailable")
    return root


def _build_authority(fixture_root: Path) -> dict[str, Any]:
    core = build_contract_core(
        {
            "contract_id": "p136-incremental-local-observer",
            "contract_version": 1,
            "subject_ref_hash": stable_hash({"subject": "p136-canonical-local-index"}),
            "max_authority_level": "OA1_LOCAL_ARTIFACT",
            "allowed_hosts": ["local-artifact.telemetry-read"],
            "allowed_methods": ["LOCAL_READ_FILE"],
            "allowed_capabilities": [
                "telemetry.events.read",
                "telemetry.logs.read",
                "telemetry.metrics.read",
                "telemetry.topology.read",
            ],
            "budgets": {
                "window_seconds": 3600,
                "max_allowed_requests_per_window": 16,
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
            "reviewer_ref_hash": stable_hash({"reviewer": "p136-canonical-reviewer"}),
            "reviewed_at": "2026-07-13T00:00:01Z",
            "expires_at": "2026-07-13T23:59:59Z",
        },
    )
    contract = build_contract(core, review)
    ledger = new_p134_receipt_ledger(
        contract, window_started_at="2026-07-13T00:00:00Z"
    )
    index_source_ref_hash = stable_hash({"p136_index": "current"})
    requests: list[dict[str, Any]] = []
    for sequence in range(1, 4):
        requests.append(
            {
                "request_id": f"p136-index-{sequence}",
                "sequence": sequence,
                "capability": "telemetry.events.read",
                "source_ref_hash": index_source_ref_hash,
                "estimated_response_bytes": 4096,
                "estimated_records": 100,
            }
        )
    for sequence, spec in enumerate(PROVIDERS, start=4):
        content = (fixture_root / str(spec["fixture"])).read_bytes()
        requests.append(
            {
                "request_id": f"p136-segment-{sequence - 3}",
                "sequence": sequence,
                "capability": spec["capability"],
                "source_ref_hash": stable_hash(
                    {"p136_source_id": str(spec["source_id"])}
                ),
                "estimated_response_bytes": len(content),
                "estimated_records": int(spec["expected_records"]),
            }
        )
    receipts: list[dict[str, Any]] = []
    for request in requests:
        sequence = int(request["sequence"])
        proposal = build_proposal(
            {
                "request_id": request["request_id"],
                "sequence": sequence,
                "proposed_at": f"2026-07-13T00:{sequence:02d}:00Z",
                "requested_level": "OA1_LOCAL_ARTIFACT",
                "source_ref_hash": request["source_ref_hash"],
                "host_label": "local-artifact.telemetry-read",
                "method": "LOCAL_READ_FILE",
                "capability": request["capability"],
                "estimated_response_bytes": request["estimated_response_bytes"],
                "estimated_records": request["estimated_records"],
                "timeout_ms": 1000,
                "attempt_number": 1,
            }
        )
        evaluated = evaluate_proposal(contract, proposal, ledger)
        if evaluated.receipt["decision"] != "allowed":
            raise P136ProfileError("canonical_authority_receipt_denied")
        receipts.append(evaluated.receipt)
        ledger = evaluated.ledger
    return {
        "contract": contract,
        "review_receipt": contract["review_receipt"],
        "receipt_ledger": ledger,
        "index_receipts": receipts[:3],
        "segment_receipts": receipts[3:],
        "contract_bytes": _canonical_bytes(contract),
        "review_receipt_bytes": _canonical_bytes(contract["review_receipt"]),
        "receipt_ledger_bytes": _canonical_bytes(ledger),
        "index_receipt_bytes": [_canonical_bytes(receipt) for receipt in receipts[:3]],
        "index_source_ref_hash": index_source_ref_hash,
    }


def _build_provider_entries(
    fixture_root: Path,
    authority: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    receipts = list(_sequence(authority.get("segment_receipts"), "segment_receipts"))
    entries: dict[str, dict[str, Any]] = {}
    previous_hash: str | None = None
    for sequence, (spec, receipt) in enumerate(zip(PROVIDERS, receipts, strict=True), start=1):
        content = (fixture_root / str(spec["fixture"])).read_bytes()
        entry = build_incremental_index_entry(
            {
                "entry_id": f"entry-{spec['source_id']}",
                "entry_sequence": sequence,
                "segment_id": f"segment-{spec['source_id']}",
                "source_id": spec["source_id"],
                "provider": spec["provider"],
                "format": spec["format"],
                "signal_family": spec["signal_family"],
                "relative_segment_path": spec["fixture"],
                "expected_content_hash": _content_hash(content),
                "expected_bytes": len(content),
                "expected_records": spec["expected_records"],
                "segment_authority_receipt_hash": receipt["receipt_hash"],
                "segment_authority_capability": spec["capability"],
                "created_at": f"2026-07-13T00:10:{sequence:02d}Z",
                "previous_entry_hash": previous_hash,
                "rotation_from_hash": None,
            }
        )
        entries[str(spec["provider"])] = entry
        previous_hash = str(entry["entry_hash"])
    return entries


def _config_input(base_path: Path, authority: Mapping[str, Any]) -> dict[str, Any]:
    del base_path
    index_receipts = _sequence(authority.get("index_receipts"), "index_receipts")
    return {
        "observer_id": "p136-canonical-local-observer",
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
        "p134_contract_hash": _mapping(authority.get("contract"), "contract")[
            "contract_hash"
        ],
        "p134_receipt_ledger_hash": _mapping(
            authority.get("receipt_ledger"), "receipt_ledger"
        )["ledger_hash"],
        "index_source_ref_hash": authority["index_source_ref_hash"],
        "index_read_receipt_hashes": [receipt["receipt_hash"] for receipt in index_receipts],
        "limits": {
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
        },
        "forbidden_authority": zero_forbidden_authority(),
    }


def _checkpoint(config: Mapping[str, Any]) -> dict[str, Any]:
    checkpoint: dict[str, Any] = {
        "schema_version": "p136.observation_checkpoint.v1",
        "config_hash": config["config_hash"],
        "index_identity_hash": stable_hash({"index_identity": "canonical-empty"}),
        "committed_cursor": 0,
        "consumed_prefix_hash": _content_hash(b""),
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
    checkpoint["checkpoint_hash"] = stable_hash(checkpoint)
    return checkpoint


def _write_exact_artifacts(
    output_dir: Path,
    artifacts: Mapping[str, Any],
    *,
    protected_paths: Sequence[Path] = (),
) -> None:
    expected = set(EXPECTED_OUTPUT_ARTIFACTS)
    if set(artifacts) != expected:
        raise P136ProfileError("output_artifact_set_mismatch")
    protected = {path.expanduser().resolve() for path in protected_paths}
    for path in output_dir.iterdir():
        if path.is_file() and path.name not in expected and path.resolve() not in protected:
            path.unlink()
    for name, value in artifacts.items():
        destination = output_dir / name
        temporary = destination.with_name(f".{destination.name}.tmp")
        temporary.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        temporary.replace(destination)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _content_hash(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _relative_path(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value.startswith("/"):
        raise P136ProfileError(f"invalid_{label}")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise P136ProfileError(f"invalid_{label}")
    return path.as_posix()


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise P136ProfileError(f"invalid_{label}_shape")
    return value


def _sequence(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise P136ProfileError(f"invalid_{label}_shape")
    result: list[Mapping[str, Any]] = []
    for item in value:
        result.append(_mapping(item, label))
    return result


if __name__ == "__main__":
    raise SystemExit(main())
