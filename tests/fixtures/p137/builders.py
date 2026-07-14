from __future__ import annotations

import fcntl
import json
import os
import signal
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p136_incremental_observer import build_incremental_observer_config, observe_one_cycle
from app.services.p137_contracts import (
    ALLOWED_REQUEST_CATALOG,
    FIXED_P136_HANDOFF_PATH,
    GUARD_PROBE_SURFACES,
    LIMIT_KEYS,
    P136_QUALIFIED_RELEASE_STATUS,
    P137ContractError,
    bounded_resource_usage,
    build_classification_policy,
    build_continuous_mode,
    build_correlation_policy,
    build_ranking_policy,
    build_triage_agent_config,
    reject_evaluator_guard_callables,
    zero_evaluator_activity,
    zero_forbidden_authority,
    zero_runtime_activity,
)
from app.services.p137_ledger import advance_investigation_ledger, new_investigation_ledger
from app.services.p137_p136_handoff import P137HandoffError, canonical_json_bytes, publish_p136_handoff_bundle, validate_p136_handoff_bundle
from app.services.p137_runtime import P137StopController, run_p137_runtime_loop, run_p137_runtime_once
from tests.fixtures.p136.builders import (
    ActivityProbe,
    authority_bundle,
    config_input,
    independent_review_artifact,
    provider_index_entries,
)
from tests.fixtures.p136.builders import (
    limits as p136_limits,
)
from tests.fixtures.p136.builders import (
    release_evidence as p136_release_evidence,
)
from tests.fixtures.p136.builders import (
    runtime_inputs as p136_runtime_inputs,
)

PROVIDERS = ("prometheus", "loki", "grafana", "sentry", "opentelemetry")
P137_SOURCE_SCOPE = (
    "app/services/p134_observation_authority.py",
    "app/services/p135_provider_export_attachment.py",
    "app/services/p136_incremental_observer.py",
    "app/services/p137_classification.py",
    "app/services/p137_contracts.py",
    "app/services/p137_correlation.py",
    "app/services/p137_hypotheses.py",
    "app/services/p137_ledger.py",
    "app/services/p137_p136_handoff.py",
    "app/services/p137_release_evidence.py",
    "app/services/p137_requests.py",
    "app/services/p137_runner.py",
    "app/services/p137_runtime.py",
    "scripts/run_p137_local_triage.py",
    "scripts/verify.sh",
    "tests/fixtures/p137/__init__.py",
    "tests/fixtures/p137/builders.py",
    "tests/fixtures/p136/builders.py",
    "tests/test_p137_classification.py",
    "tests/test_p137_contracts.py",
    "tests/test_p137_correlation.py",
    "tests/test_p137_hypotheses.py",
    "tests/test_p137_ledger.py",
    "tests/test_p137_p136_handoff.py",
    "tests/test_p137_release_evidence.py",
    "tests/test_p137_requests.py",
    "tests/test_p137_runner.py",
    "tests/test_p137_runtime.py",
    "tests/test_p137_authority_boundary.py",
    "evals/p137/input/local-triage-profile.json",
    "README.md",
    "ROADMAP.md",
    "CHANGELOG.md",
    "docs/operations/p137-evidence-to-incident-roadmap.md",
    "docs/operations/p137-test-spec.md",
    "docs/operations/p137-plan-review.md",
    "docs/tickets/p137/README.md",
    "docs/tickets/p137/P137-001-contract-schema.md",
    "docs/tickets/p137/P137-002-p136-ingest.md",
    "docs/tickets/p137/P137-003-correlation.md",
    "docs/tickets/p137/P137-004-hypotheses.md",
    "docs/tickets/p137/P137-005-bounded-evidence-requests.md",
    "docs/tickets/p137/P137-006-classification-ledger.md",
    "docs/tickets/p137/P137-007-recovery-lease-signals-budgets.md",
    "docs/tickets/p137/P137-008-canonical-runner-cli.md",
    "docs/tickets/p137/P137-009-release-evidence-docs-review.md",
    "docs/tickets/p137/P137-010-final-verification.md",
)
RELEASE_STATUS = "p137_local_evidence_triage_qualified"
TEST_SOURCE_BINDINGS = {path: stable_hash({"source": path}) for path in P137_SOURCE_SCOPE}


def canonical_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def runtime_inputs(tmp_path: Path, case_id: str = "p137-case-01") -> dict[str, Any]:
    ordinal = int(case_id.rsplit("-", 1)[1])
    provider = PROVIDERS[(ordinal - 1) % len(PROVIDERS)]
    label = _case_label(ordinal)
    category = _case_category(ordinal)
    needs_local_request = ordinal == 26 or 30 <= ordinal <= 44 or ordinal == 48
    promotions = [
        {
            "schema_version": "p136.promotion_record.v1",
            "entry_hash": stable_hash({"entry": case_id, "provider": provider}),
            "promotion_key": stable_hash({"promotion": case_id, "provider": provider}),
            "status": "success",
            "provider": provider,
            "signal_family": "metrics" if provider in {"prometheus", "opentelemetry"} else ("logs" if provider == "loki" else ("topology" if provider == "grafana" else "events")),
        }
    ]
    promotion_bytes = [canonical_bytes(item) for item in promotions]
    handoff = {
        "schema_version": "p137.p136_handoff_bundle.v1",
        "case_id": case_id,
        "provider": provider,
        "promotion_hashes": [stable_hash(item) for item in promotions],
        "bundle_sequence": ordinal,
    }
    handoff_bytes = canonical_bytes(handoff)
    atoms = _atoms_for_label(
        case_id,
        label,
        provider=provider,
        local_request=needs_local_request and label == "insufficient_evidence",
        external_unavailable=ordinal == 27,
    )
    validated_p136_config: dict[str, Any] | None = None
    input_authenticity = "component_fixture"
    if ordinal in {2, 3}:
        published, validated_p136_config = _published_handoff(tmp_path / "p136-input", provider=provider)
        handoff_bytes = canonical_json_bytes(published)
        promotion_bytes = [
            bytes.fromhex(str(wrapper["promotion_bytes"]))
            for wrapper in published["promotion_map"].values()
        ]
        validated = validate_p136_handoff_bundle(handoff_bytes, config=validated_p136_config)
        atoms = [deepcopy(dict(atom)) for atom in validated["evidence_atoms"]]
        handoff = deepcopy(published)
        promotions = [deepcopy(dict(wrapper["promotion"])) for wrapper in published["promotion_map"].values()]
        input_authenticity = "p136_validator_exact"
    if 30 <= ordinal <= 44 and label in {"confirmed_incident", "benign_anomaly"}:
        atoms = _append_local_request_atom(atoms, case_id, provider=provider)
    runtime = {
        "case_id": case_id,
        "canonical_handoff_bundle_bytes": handoff_bytes,
        "canonical_promotion_bytes": promotion_bytes,
        "handoff_bundle": handoff,
        "promotions": promotions,
        "provider": provider,
        "fixture_root": str(tmp_path),
        "forbidden_authority": zero_forbidden_authority(),
        "atoms": atoms,
        "classification_atoms": deepcopy(atoms),
        "input_authenticity": input_authenticity,
        "incident_id": f"incident-{case_id}",
        "incident_hash": stable_hash({"incident": case_id}),
        "request_sequence": 1,
        "request_budget": _request_budget(),
        "request_parameters_by_catalog": _request_parameters(),
        **_scenario_probe(category, label, ordinal),
    }
    if validated_p136_config is not None:
        runtime["validated_p136_config"] = validated_p136_config
    runtime["effective_p137_config"] = _effective_p137_config(tmp_path, ordinal, runtime)
    if category in {"ingest", "correlation", "hypothesis", "classification", "request", "budget"}:
        runtime["runtime_probe"] = _RuntimeEvidenceProbe(tmp_path / "runtime-evidence", case_id)
    runtime["expected_runtime_activity"] = _expected_runtime_activity(runtime, ordinal)
    runtime["expected_evaluator_activity"] = _expected_evaluator_activity(ordinal)
    runtime["expected_resource_usage"] = bounded_resource_usage(
        wall_time_ms=0,
        cpu_time_ms=0,
        child_cpu_time_ms=0,
        peak_memory_bytes=0,
        wall_limit_ms=0,
        cpu_limit_ms=0,
        peak_memory_limit_bytes=0,
    )
    return runtime


def _expected_evaluator_activity(ordinal: int) -> dict[str, int]:
    activity = zero_evaluator_activity()
    if ordinal == 15:
        activity["fake_guard_callable_count"] = len(GUARD_PROBE_SURFACES)
        return activity
    if ordinal == 59:
        return activity
    activity["handoff_fixture_write_count"] = 1
    if ordinal in {45, 54}:
        activity["signal_delivery_count"] = 1
    return activity


def _expected_runtime_activity(runtime: dict[str, Any], ordinal: int) -> dict[str, int]:
    activity = zero_runtime_activity()
    regular = set(range(1, 6)) | set(range(16, 30)) | set(range(30, 45)) | {47, 48, 49}
    if ordinal in regular:
        handoff_bytes = bytes(runtime["canonical_handoff_bundle_bytes"])
        promotion_bytes = [bytes(item) for item in runtime["canonical_promotion_bytes"]]
        atoms = list(runtime["classification_atoms"])
        if ordinal == 21:
            activity.update(
                lease_acquire_count=3,
                state_read_count=13,
                handoff_bundle_open_count=3,
                handoff_bundle_read_count=3,
                handoff_bundle_bytes_read=3 * (len(handoff_bytes) + 1),
                p136_validator_invocation_count=3,
                promotion_record_read_count=3 * len(promotion_bytes),
                promotion_bytes_validated=3 * sum(len(item) for item in promotion_bytes),
                evidence_atom_count=1,
                ingest_intent_write_count=1,
                evidence_atom_write_count=1,
                incident_write_count=6,
                hypothesis_write_count=1,
                classification_write_count=1,
                ledger_write_count=1,
                readiness_write_count=1,
                directory_fsync_count=13,
                recovery_replay_count=1,
                duplicate_atom_count=1,
            )
            return activity
        atom_count = 1 if ordinal == 20 else (2 if ordinal == 29 else len(atoms))
        incident_writes = 2 if ordinal == 20 else (4 if ordinal == 29 else 6)
        hypothesis_writes = 0 if ordinal in {20, 29} else atom_count
        request_writes = 0 if ordinal in {20, 29} else int(
            any("local_catalog_selectable" in atom["state_reason_codes"] for atom in atoms)
        )
        activity.update(
            lease_acquire_count=1,
            handoff_bundle_open_count=1,
            handoff_bundle_read_count=1,
            handoff_bundle_bytes_read=len(handoff_bytes) + 1,
            p136_validator_invocation_count=(2 + len(promotion_bytes)) if ordinal in {2, 3} else 1,
            promotion_record_read_count=len(promotion_bytes),
            promotion_bytes_validated=sum(len(item) for item in promotion_bytes),
            evidence_atom_count=atom_count,
            ingest_intent_write_count=1,
            evidence_atom_write_count=atom_count,
            incident_write_count=incident_writes,
            hypothesis_write_count=hypothesis_writes,
            evidence_request_write_count=request_writes,
            attempted_request_hash_write_count=request_writes,
            classification_write_count=1,
            ledger_write_count=1,
            readiness_write_count=1,
            directory_fsync_count=4 + 1 + atom_count + incident_writes + hypothesis_writes + request_writes,
        )
        if ordinal == 2:
            activity.update(
                incident_write_count=12,
                classification_write_count=2,
                directory_fsync_count=24,
            )
        return activity
    return _expected_control_runtime_activity(ordinal)


def _expected_control_runtime_activity(ordinal: int) -> dict[str, int]:
    activity = zero_runtime_activity()
    if ordinal in {6, 7, 9, 10, 11, 12, 13, 14, 15, 50, 59}:
        return activity
    control_bytes = len(b'{"bundle":"p137-control"}\n')
    if ordinal == 8:
        promotion_bytes = 2 * _bundle_promotion_bytes(_runtime_bundle("p137-case-08"))
        activity.update(
            lease_acquire_count=2,
            state_read_count=12,
            handoff_bundle_open_count=2,
            handoff_bundle_read_count=2,
            handoff_bundle_bytes_read=2 * control_bytes,
            p136_validator_invocation_count=2,
            promotion_bytes_validated=promotion_bytes,
            evidence_atom_count=1,
            ingest_intent_write_count=1,
            evidence_atom_write_count=1,
            incident_write_count=6,
            hypothesis_write_count=1,
            classification_write_count=1,
            ledger_write_count=1,
            readiness_write_count=1,
            directory_fsync_count=13,
        )
        return activity
    if ordinal == 45:
        activity.update(lease_acquire_count=1, termination_receipt_write_count=1, directory_fsync_count=1)
        return activity
    if ordinal == 46:
        activity.update(lease_acquire_count=1, state_read_count=1, termination_receipt_write_count=1, directory_fsync_count=1)
        return activity
    if ordinal == 52:
        activity.update(termination_receipt_write_count=1, directory_fsync_count=1)
        return activity
    if ordinal == 53:
        activity.update(
            lease_acquire_count=1,
            handoff_bundle_open_count=1,
            handoff_bundle_read_count=1,
            handoff_bundle_bytes_read=control_bytes,
            heartbeat_write_count=1,
            readiness_write_count=1,
            termination_receipt_write_count=1,
            directory_fsync_count=3,
        )
        return activity
    if ordinal in {51, 54, 60}:
        bundle = _runtime_bundle(f"p137-case-{ordinal:02d}")
        activity.update(
            lease_acquire_count=1,
            handoff_bundle_open_count=1,
            handoff_bundle_read_count=1,
            handoff_bundle_bytes_read=control_bytes,
            p136_validator_invocation_count=1,
            promotion_bytes_validated=_bundle_promotion_bytes(bundle),
            evidence_atom_count=1,
            ingest_intent_write_count=1,
            evidence_atom_write_count=1,
            incident_write_count=6,
            hypothesis_write_count=1,
        )
        if ordinal == 51:
            activity.update(
                classification_write_count=1,
                ledger_write_count=1,
                heartbeat_write_count=1,
                readiness_write_count=2,
                directory_fsync_count=15,
            )
        else:
            activity.update(termination_receipt_write_count=1, directory_fsync_count=10)
        return activity
    if ordinal in {55, 56, 57, 58}:
        label = "insufficient_evidence" if ordinal == 55 else "confirmed_incident"
        bundle = _runtime_budget_abort_bundle("p137-case-58") if ordinal == 58 else _runtime_bundle(f"p137-case-{ordinal:02d}", label=label)
        if ordinal == 57:
            bundle["evidence_atoms"] = _append_local_request_atom(
                [dict(bundle["evidence_atoms"][0])],
                "p137-case-57",
                provider="prometheus",
            )
        atom_count = len(bundle["evidence_atoms"])
        activity.update(
            lease_acquire_count=3,
            state_read_count={55: 13, 56: 20, 57: 27, 58: 18}[ordinal],
            handoff_bundle_open_count=3,
            handoff_bundle_read_count=3,
            handoff_bundle_bytes_read=3 * control_bytes,
            p136_validator_invocation_count=3,
            promotion_bytes_validated=3 * _bundle_promotion_bytes(bundle),
            evidence_atom_count=atom_count if ordinal == 55 else 2 * atom_count,
            ingest_intent_write_count=1,
            evidence_atom_write_count=atom_count,
            incident_write_count=4 if ordinal == 58 else 6,
            hypothesis_write_count=0 if ordinal == 58 else atom_count,
            evidence_request_write_count=1 if ordinal == 57 else 0,
            attempted_request_hash_write_count=1 if ordinal == 57 else 0,
            classification_write_count=1,
            ledger_write_count=1,
            readiness_write_count=1,
            directory_fsync_count={55: 13, 56: 13, 57: 16, 58: 11}[ordinal],
            recovery_replay_count=1,
            duplicate_atom_count={55: 1, 56: 2, 57: 4, 58: 4}[ordinal],
        )
        return activity
    raise AssertionError(f"missing_expected_control_delta:p137-case-{ordinal:02d}")


def _bundle_promotion_bytes(bundle: dict[str, Any]) -> int:
    return sum(len(canonical_bytes(dict(atom))) + 1 for atom in bundle["evidence_atoms"])


def final_implementation_review(source_bindings: dict[str, str] | None = None) -> dict[str, Any]:
    review = {
        "schema_version": "p137.final_implementation_review.v1",
        "reviewer_role": "independent_code_reviewer",
        "implementation_role": "implementation_agent",
        "reviewed_source_hashes": dict(sorted((source_bindings or TEST_SOURCE_BINDINGS).items())),
        "reviewed_profile_hash": stable_hash({"profile": "p137-test"}),
        "reviewed_fixture_hash": stable_hash({"fixtures": "p137-test"}),
        "reviewed_matrix_hash": stable_hash({"matrix": "p137-test"}),
        "findings": {"p0": 0, "p1": 0, "p2": 0, "p3": 0},
        "decision": "approve",
        "limitations": [
            "reviewer_identity_unauthenticated",
            "local_artifact_only_no_live_provider_claim",
            "no_auth_no_credentials_no_network_no_provider_api_no_notification_no_action_no_remediation",
        ],
    }
    review["implementation_review_hash"] = stable_hash(review)
    return review


def local_triage_profile() -> dict[str, Any]:
    required_case_ids = [f"p137-case-{index:02d}" for index in range(1, 61)]
    profile = {
        "schema_version": "p137.local_triage_profile.v1",
        "case_matrix_version": 1,
        "fixture_root": "evals/p137/input",
        "output_artifacts": ["canonical-matrix.json", "freeze-manifest.json", "release-evidence.json"],
        "required_case_ids": required_case_ids,
        "resource_limits": {
            "wall_limit_ms": 30_000,
            "cpu_limit_ms": 15_000,
            "peak_memory_limit_bytes": 134_217_728,
        },
        "allowed_request_catalog": list(ALLOWED_REQUEST_CATALOG),
        "root_ref_hash": stable_hash({"schema_version": "p137.fixture_root_ref.v1", "fixture_root": "evals/p137/input"}),
    }
    return deepcopy(profile)


def release_evidence_stub(case_count: int = 60) -> dict[str, Any]:
    return {
        "schema_version": "p137.release_evidence.v1",
        "status": RELEASE_STATUS,
        "cases": [],
        "totals": {"expected": case_count, "passed": case_count, "failed": 0},
        "classification_totals": {},
        "request_catalog": list(ALLOWED_REQUEST_CATALOG),
        "provider_profiles": list(PROVIDERS),
        "forbidden_authority": zero_forbidden_authority(),
        "runtime_activity": zero_runtime_activity(),
        "evaluator_activity": zero_evaluator_activity(),
        "resource_usage": bounded_resource_usage(wall_limit_ms=30_000, cpu_limit_ms=15_000, peak_memory_limit_bytes=134_217_728),
        "source_bindings": dict(TEST_SOURCE_BINDINGS),
    }


def _case_category(ordinal: int) -> str:
    if ordinal <= 5:
        return "ingest"
    if ordinal <= 14:
        return "handoff"
    if ordinal == 15:
        return "guard"
    if ordinal <= 21:
        return "correlation"
    if ordinal <= 28:
        return "hypothesis"
    if ordinal == 29:
        return "budget"
    if ordinal <= 44:
        return "request"
    if ordinal in {45, 54}:
        return "signal"
    if ordinal in {46, 59}:
        return "durability"
    if ordinal <= 49:
        return "classification"
    if ordinal == 50:
        return "lease"
    if ordinal == 51:
        return "continuous"
    if ordinal == 52:
        return "readiness"
    if ordinal == 53:
        return "handoff"
    if ordinal <= 58:
        return "recovery"
    return "resource"


def _case_label(ordinal: int) -> str:
    labels = {
        15: "none",
        16: "confirmed_incident",
        17: "insufficient_evidence",
        18: "confirmed_incident",
        19: "insufficient_evidence",
        20: "aborted_fail_closed",
        21: "insufficient_evidence",
        22: "confirmed_incident",
        23: "insufficient_evidence",
        24: "benign_anomaly",
        25: "insufficient_evidence",
        26: "insufficient_evidence",
        27: "insufficient_evidence",
        28: "insufficient_evidence",
        29: "aborted_fail_closed",
        30: "confirmed_incident",
        31: "insufficient_evidence",
        32: "confirmed_incident",
        33: "confirmed_incident",
        34: "confirmed_incident",
        35: "confirmed_incident",
        36: "insufficient_evidence",
        37: "confirmed_incident",
        38: "insufficient_evidence",
        39: "confirmed_incident",
        40: "confirmed_incident",
        41: "insufficient_evidence",
        42: "insufficient_evidence",
        43: "confirmed_incident",
        44: "benign_anomaly",
        45: "none",
        46: "none",
        47: "confirmed_incident",
        48: "insufficient_evidence",
        49: "benign_anomaly",
        50: "none",
        51: "none",
        52: "none",
        53: "none",
        54: "none",
        55: "insufficient_evidence",
        56: "confirmed_incident",
        57: "confirmed_incident",
        58: "aborted_fail_closed",
        59: "none",
        60: "none",
    }
    if 1 <= ordinal <= 5:
        return "insufficient_evidence"
    if 6 <= ordinal <= 14:
        return "none"
    return labels[ordinal]


def _scenario_probe(category: str, label: str, ordinal: int) -> dict[str, Any]:
    if category in {"ingest", "correlation", "hypothesis", "classification", "request", "budget"}:
        if label == "aborted_fail_closed":
            return {
                "failure_probe": {
                    "failure_code": "runtime_failure",
                    "classification_write_succeeded": True,
                    "ledger_cas_succeeded": True,
                    "actual_error": "none",
                    "termination_reason": "aborted_fail_closed",
                }
            }
        return {}
    return {"probe": _ControlProbe(ordinal)}


class _ControlProbe:
    def __init__(self, ordinal: int) -> None:
        self.ordinal = ordinal

    def __call__(self, *, spec: dict[str, Any], runtime: dict[str, Any]) -> dict[str, Any]:
        case_id = str(spec["case_id"])
        root = Path(str(runtime["fixture_root"])) / "control-probe"
        config = deepcopy(dict(runtime["effective_p137_config"]))
        if 6 <= self.ordinal <= 14:
            return _handoff_probe(self.ordinal, root, p137_config=config)
        if self.ordinal == 15:
            return _guard_probe()
        if self.ordinal in {45, 46, 50, 51, 52, 53, 54, 55, 56, 57, 58}:
            return _runtime_probe(self.ordinal, root, case_id, config=config)
        if self.ordinal == 59:
            return _cas_conflict_probe()
        if self.ordinal == 60:
            return _resource_contract_probe(root, config=config)
        raise AssertionError(f"unsupported_control_probe:{self.ordinal}")


class _RuntimeEvidenceProbe:
    def __init__(self, root: Path, case_id: str) -> None:
        self.root = root
        self.case_id = case_id

    def __call__(self, *, spec: dict[str, Any], runtime: dict[str, Any]) -> dict[str, Any]:
        ordinal = int(self.case_id.rsplit("-", 1)[1])
        exact_p136 = runtime.get("input_authenticity") == "p136_validator_exact"
        config = deepcopy(dict(runtime["effective_p137_config"]))
        handoff_bytes = bytes(runtime["canonical_handoff_bundle_bytes"])
        promotion_bytes = [bytes(item) for item in runtime["canonical_promotion_bytes"]]
        _publish_runtime_bytes(self.root, handoff_bytes)
        if exact_p136:
            bundle = validate_p136_handoff_bundle(
                handoff_bytes,
                config=dict(runtime["validated_p136_config"]),
            )
        elif ordinal == 20:
            bundle = _runtime_bundle(self.case_id, label="confirmed_incident")
        elif ordinal == 29:
            bundle = _runtime_budget_abort_bundle(self.case_id)
        else:
            bundle = _runtime_bundle(self.case_id)
            bundle["evidence_atoms"] = deepcopy(runtime["classification_atoms"])
        bundle["promotion_record_count"] = len(promotion_bytes)
        bundle["promotion_bytes_validated"] = sum(len(item) for item in promotion_bytes)
        if ordinal == 21:
            crashed = run_p137_runtime_once(
                base_path=self.root,
                config=config,
                validate_handoff=validate_p136_handoff_bundle if exact_p136 else _runtime_validator(bundle),
                crash_after="ingest_intent",
            )
            recovered = run_p137_runtime_once(
                base_path=self.root,
                config=config,
                validate_handoff=validate_p136_handoff_bundle if exact_p136 else _runtime_validator(bundle),
            )
            replayed = run_p137_runtime_once(
                base_path=self.root,
                config=config,
                validate_handoff=validate_p136_handoff_bundle if exact_p136 else _runtime_validator(bundle),
            )
            if replayed.get("runtime_activity", {}).get("recovery_replay_count") != 1:
                raise AssertionError("restart_duplicate_ingest_not_replayed")
            return _probe_result(
                source="p137_runtime.run_p137_runtime_once.crash_recover_replay",
                actual_label=str(recovered["classification"]),
                actual_error="none",
                termination_reason="none",
                api_calls=["p137_runtime.run_p137_runtime_once"],
                runtime_activity=_sum_runtime_activity(crashed, recovered, replayed),
                handoff_fixture_writes=1,
            )
        result = run_p137_runtime_once(
            base_path=self.root,
            config=config,
            validate_handoff=validate_p136_handoff_bundle if exact_p136 else _runtime_validator(bundle),
        )
        termination = str(result["termination_reason"])
        if termination == "cycle_complete":
            termination = "none"
        return _probe_result(
            source="p137_runtime.run_p137_runtime_once",
            actual_label=str(result["classification"]),
            actual_error=str(result["expected_error"] or "none"),
            termination_reason=termination,
            api_calls=["p137_runtime.run_p137_runtime_once"],
            runtime_activity=dict(result["runtime_activity"]),
            handoff_fixture_writes=1,
        )


def _probe_result(
    *,
    source: str,
    actual_label: str,
    actual_error: str,
    termination_reason: str,
    api_calls: list[str],
    runtime_activity: dict[str, int] | None = None,
    evaluator_activity: dict[str, int] | None = None,
    handoff_fixture_writes: int = 0,
    signal_deliveries: int = 0,
    exception: BaseException | None = None,
) -> dict[str, Any]:
    measured_evaluator_activity = dict(evaluator_activity or zero_evaluator_activity())
    measured_evaluator_activity["handoff_fixture_write_count"] += handoff_fixture_writes
    measured_evaluator_activity["signal_delivery_count"] += signal_deliveries
    return {
        "source": source,
        "actual_label": actual_label,
        "actual_error": actual_error,
        "termination_reason": termination_reason,
        "api_calls": api_calls,
        "runtime_activity": runtime_activity if runtime_activity is not None else zero_runtime_activity(),
        "forbidden_authority": zero_forbidden_authority(),
        "evaluator_activity": measured_evaluator_activity,
        "exception": {
            "type": type(exception).__name__ if exception is not None else "none",
            "message": str(exception) if exception is not None else "none",
        },
    }


def _handoff_probe(ordinal: int, root: Path, *, p137_config: dict[str, Any]) -> dict[str, Any]:
    bundle, p136_config = _published_handoff(root)
    checkpoint = None
    raw = canonical_json_bytes(bundle)
    if ordinal == 6:
        _rehash_nested(bundle["p136_release_evidence"], "evidence_hash")
        bundle["p136_release_evidence"]["status"] = "p136_unqualified"
        _rehash_nested(bundle["p136_release_evidence"], "evidence_hash")
        bundle["p136_release_evidence_hash"] = bundle["p136_release_evidence"]["evidence_hash"]
        _rehash_nested(bundle, "bundle_hash")
        raw = canonical_json_bytes(bundle)
    elif ordinal == 7:
        checkpoint = {
            "last_accepted_bundle_sequence": 2,
            "last_accepted_bundle_hash": stable_hash({"accepted": "later"}),
        }
    elif ordinal == 8:
        return _runtime_same_sequence_fork_probe(root, config=p137_config)
    elif ordinal == 9:
        checkpoint = {
            "last_accepted_bundle_sequence": 1,
            "last_accepted_bundle_hash": stable_hash({"accepted": "previous"}),
        }
        bundle["bundle_sequence"] = 2
        bundle["previous_bundle_hash"] = stable_hash({"wrong": "previous"})
        _rehash_nested(bundle, "bundle_hash")
        raw = canonical_json_bytes(bundle)
    elif ordinal == 10:
        raw = canonical_json_bytes(bundle) + b" "
    elif ordinal == 11:
        bundle["p136_checkpoint"]["promotion_keys"].pop(next(iter(bundle["promotion_map"])))
        _rehash_nested(bundle["p136_checkpoint"], "checkpoint_hash")
        bundle["p136_checkpoint_hash"] = bundle["p136_checkpoint"]["checkpoint_hash"]
        _rehash_nested(bundle, "bundle_hash")
        raw = canonical_json_bytes(bundle)
    elif ordinal == 12:
        bundle["p136_checkpoint"]["promotion_keys"][next(iter(bundle["promotion_map"]))] = {"forged": True}
        _rehash_nested(bundle["p136_checkpoint"], "checkpoint_hash")
        bundle["p136_checkpoint_hash"] = bundle["p136_checkpoint"]["checkpoint_hash"]
        _rehash_nested(bundle, "bundle_hash")
        raw = canonical_json_bytes(bundle)
    elif ordinal == 13:
        next(iter(bundle["promotion_map"].values()))["promotion"]["promotion_key"] = stable_hash({"tamper": "nested"})
        _rehash_nested(bundle, "bundle_hash")
        raw = canonical_json_bytes(bundle)
    elif ordinal == 14:
        bundle["p136_runtime_authority"]["contract_bytes"] = str(bundle["p136_runtime_authority"]["contract_bytes"]).upper()
        _rehash_nested(bundle, "bundle_hash")
        raw = canonical_json_bytes(bundle)
    try:
        validate_p136_handoff_bundle(raw, config=p136_config, p137_checkpoint=checkpoint)
    except P137HandoffError as exc:
        return _probe_result(
            source="p137_p136_handoff.validate_p136_handoff_bundle",
            actual_label="none",
            actual_error=_handoff_error_code(str(exc)),
            termination_reason="pre_ingest_rejected",
            api_calls=["p137_p136_handoff.validate_p136_handoff_bundle"],
            handoff_fixture_writes=1,
            exception=exc,
        )
    raise AssertionError(f"handoff_probe_did_not_fail:{ordinal}")


def _runtime_probe(ordinal: int, root: Path, case_id: str, *, config: dict[str, Any]) -> dict[str, Any]:
    if ordinal in {45, 54}:
        _publish_runtime_bytes(root)
        stop = P137StopController()
        stop.handle_signal(signal.SIGINT if ordinal == 45 else signal.SIGTERM, None)
        result = run_p137_runtime_once(
            base_path=root,
            config=config,
            validate_handoff=_runtime_validator(_runtime_bundle(case_id)),
            stop_controller=stop,
            stop_before="handoff" if ordinal == 45 else "classification",
        )
        return _probe_result(
            source="p137_runtime.run_p137_runtime_once",
            actual_label=str(result["classification"]),
            actual_error=str(result["expected_error"]),
            termination_reason=str(result["termination_reason"]),
            api_calls=["p137_runtime.P137StopController.handle_signal", "p137_runtime.run_p137_runtime_once"],
            runtime_activity=dict(result["runtime_activity"]),
            handoff_fixture_writes=1,
            signal_deliveries=1,
        )
    if ordinal == 46:
        _publish_runtime_bytes(root)
        ledger_path = root / config["ledger_path"]
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger_path.write_text('{"schema_version":"corrupt"}', encoding="utf-8")
        result = run_p137_runtime_once(base_path=root, config=config, validate_handoff=_runtime_validator(_runtime_bundle(case_id)))
        return _probe_result(
            source="p137_runtime.run_p137_runtime_once",
            actual_label=str(result["classification"]),
            actual_error=str(result["expected_error"]),
            termination_reason=str(result["termination_reason"]),
            api_calls=["p137_runtime.run_p137_runtime_once"],
            runtime_activity=dict(result["runtime_activity"]),
            handoff_fixture_writes=1,
        )
    if ordinal == 50:
        _publish_runtime_bytes(root)
        lease_path = root / config["lease_path"]
        lease_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(lease_path, os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            result = run_p137_runtime_once(base_path=root, config=config, validate_handoff=_runtime_validator(_runtime_bundle(case_id)))
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        return _probe_result(
            source="p137_runtime.run_p137_runtime_once",
            actual_label=str(result["classification"]),
            actual_error=str(result["expected_error"]),
            termination_reason=str(result["termination_reason"]),
            api_calls=["p137_runtime.run_p137_runtime_once"],
            runtime_activity=dict(result["runtime_activity"]),
            handoff_fixture_writes=1,
        )
    if ordinal in {51, 52, 53}:
        _publish_runtime_bytes(root)
        if ordinal == 52:
            readiness_path = root / config["readiness_path"]
            readiness_path.parent.mkdir(parents=True, exist_ok=True)
            readiness_path.write_text(
                json.dumps({"status": "stale", "written_at": "2026-07-13T00:00:00Z"}),
                encoding="utf-8",
            )
        bundle = _runtime_bundle(case_id)
        if ordinal == 53:
            bundle["bundle_version"] = 2
        loop = run_p137_runtime_loop(
            base_path=root,
            config=config,
            validate_handoff=_runtime_validator(bundle),
            now_values=["2026-07-14T00:00:00Z", "2026-07-14T00:00:01Z"],
        )
        last = dict(loop["last_result"] or {})
        activity = zero_runtime_activity()
        for source_activity in (last.get("runtime_activity"), loop.get("control_runtime_activity")):
            if isinstance(source_activity, dict):
                for key, value in source_activity.items():
                    activity[key] += int(value)
        return _probe_result(
            source="p137_runtime.run_p137_runtime_loop",
            actual_label="none",
            actual_error=str(last.get("expected_error") or "none"),
            termination_reason=str(loop["termination_reason"]),
            api_calls=["p137_runtime.run_p137_runtime_loop", "p137_runtime.run_p137_runtime_once"],
            runtime_activity=activity,
            handoff_fixture_writes=1,
        )
    if ordinal == 58:
        _publish_runtime_bytes(root)
        bundle = _runtime_budget_abort_bundle(case_id)
        crashed = run_p137_runtime_once(
            base_path=root,
            config=config,
            validate_handoff=_runtime_validator(bundle),
            crash_after="classification_write",
        )
        recovered = run_p137_runtime_once(base_path=root, config=config, validate_handoff=_runtime_validator(bundle))
        replayed = run_p137_runtime_once(base_path=root, config=config, validate_handoff=_runtime_validator(bundle))
        classification_files = list((root / config["classification_dir"]).glob("*.json"))
        ledger = recovered.get("ledger")
        if (
            crashed.get("expected_error") != "crash_after_classification_write"
            or recovered.get("classification") != "aborted_fail_closed"
            or replayed.get("runtime_activity", {}).get("recovery_replay_count") != 1
            or len(classification_files) != 1
            or not isinstance(ledger, dict)
            or len(ledger.get("classification_hashes", [])) != 1
        ):
            raise AssertionError("aborted_classification_recovery_not_exactly_once")
        return _probe_result(
            source="p137_runtime.run_p137_runtime_once.crash_recover_replay",
            actual_label=str(recovered["classification"]),
            actual_error="none",
            termination_reason=str(recovered["termination_reason"]),
            api_calls=["p137_runtime.run_p137_runtime_once"],
            runtime_activity=_sum_runtime_activity(crashed, recovered, replayed),
            handoff_fixture_writes=1,
        )
    _publish_runtime_bytes(root)
    bundle = _runtime_bundle(case_id, label="insufficient_evidence" if ordinal == 55 else "confirmed_incident")
    if ordinal == 57:
        bundle["evidence_atoms"] = _append_local_request_atom(
            [dict(bundle["evidence_atoms"][0])],
            case_id,
            provider="prometheus",
        )
    crash_after = {55: "ingest_intent", 56: "incident_write", 57: "request_write"}[ordinal]
    crashed = run_p137_runtime_once(base_path=root, config=config, validate_handoff=_runtime_validator(bundle), crash_after=crash_after)
    recovered = run_p137_runtime_once(base_path=root, config=config, validate_handoff=_runtime_validator(bundle))
    replayed = run_p137_runtime_once(base_path=root, config=config, validate_handoff=_runtime_validator(bundle))
    return _probe_result(
        source="p137_runtime.run_p137_runtime_once.crash_recover_replay",
        actual_label=str(recovered["classification"]),
        actual_error="none",
        termination_reason="none",
        api_calls=["p137_runtime.run_p137_runtime_once"],
        runtime_activity=_sum_runtime_activity(crashed, recovered, replayed),
        handoff_fixture_writes=1,
    )


def _runtime_same_sequence_fork_probe(root: Path, *, config: dict[str, Any]) -> dict[str, Any]:
    _publish_runtime_bytes(root)
    first = _runtime_bundle("p137-case-08")
    accepted = run_p137_runtime_once(base_path=root, config=config, validate_handoff=_runtime_validator(first))
    fork = _runtime_bundle("p137-case-08", bundle_hash=stable_hash({"fork": "p137-case-08"}))
    result = run_p137_runtime_once(base_path=root, config=config, validate_handoff=_runtime_validator(fork))
    return _probe_result(
        source="p137_runtime.run_p137_runtime_once",
        actual_label=str(result["classification"]),
        actual_error=str(result["expected_error"]),
        termination_reason="pre_ingest_rejected",
        api_calls=["p137_runtime.run_p137_runtime_once"],
        runtime_activity=_sum_runtime_activity(accepted, result),
        handoff_fixture_writes=1,
    )


def _guard_probe() -> dict[str, Any]:
    evaluator = zero_evaluator_activity()
    evaluator["fake_guard_callable_count"] = len(GUARD_PROBE_SURFACES)
    invocations = {surface: 0 for surface in GUARD_PROBE_SURFACES}

    def blocked(surface: str) -> Any:
        def invoke() -> None:
            invocations[surface] += 1

        return invoke

    guard_callables = {surface: blocked(surface) for surface in GUARD_PROBE_SURFACES}
    try:
        reject_evaluator_guard_callables(guard_callables)
    except P137ContractError as exc:
        if str(exc) != "guard_probe_blocked_before_boundary" or any(invocations.values()):
            raise
        return _probe_result(
            source="p137_contracts.reject_evaluator_guard_callables",
            actual_label="none",
            actual_error="guard_probe_blocked_before_boundary",
            termination_reason="evaluator_only",
            api_calls=["p137_contracts.reject_evaluator_guard_callables"],
            runtime_activity=zero_runtime_activity(),
            evaluator_activity=evaluator,
            exception=exc,
        )
    raise AssertionError("fake_guard_probe_did_not_fail")


def _cas_conflict_probe() -> dict[str, Any]:
    ledger = new_investigation_ledger(config_hash=stable_hash({"config": "p137-case-59"}), **_ledger_maps())
    try:
        advance_investigation_ledger(ledger, expected_previous_hash=stable_hash({"wrong": "previous"}))
    except Exception as exc:
        return _probe_result(
            source="p137_ledger.advance_investigation_ledger",
            actual_label="none",
            actual_error=str(exc),
            termination_reason="cas_failure",
            api_calls=["p137_ledger.new_investigation_ledger", "p137_ledger.advance_investigation_ledger"],
            runtime_activity=zero_runtime_activity(),
            exception=exc,
        )
    raise AssertionError("cas_conflict_probe_did_not_fail")


def _resource_contract_probe(root: Path, *, config: dict[str, Any]) -> dict[str, Any]:
    _publish_runtime_bytes(root)
    result = run_p137_runtime_once(
        base_path=root,
        config=config,
        validate_handoff=_runtime_validator(_runtime_bundle("p137-case-60")),
        resource_probe=lambda: {
            "wall_time_ms": 2,
            "cpu_time_ms": 0,
            "child_cpu_time_ms": 0,
            "peak_memory_bytes": 0,
            "wall_limit_ms": 1,
            "cpu_limit_ms": int(config["limits"]["max_cpu_ms"]),
            "peak_memory_limit_bytes": int(config["limits"]["max_peak_memory_bytes"]),
        },
    )
    return _probe_result(
        source="p137_runtime.run_p137_runtime_once",
        actual_label=str(result["classification"]),
        actual_error=str(result["expected_error"]),
        termination_reason=str(result["termination_reason"]),
        api_calls=["p137_runtime.run_p137_runtime_once"],
        runtime_activity=dict(result["runtime_activity"]),
        handoff_fixture_writes=1,
    )


def _published_handoff(root: Path, *, provider: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    root.mkdir(parents=True, exist_ok=True)
    authority = authority_bundle(index_receipts=2, segment_receipts=5)
    cfg_input = config_input(
        root,
        authority,
        limits={**p136_limits(), "max_journal_bytes": 1_000_000, "max_promotion_bytes": 1_000_000},
    )
    p136_runtime = p136_runtime_inputs(root, authority=authority, config=cfg_input, probe=ActivityProbe())
    config = build_incremental_observer_config(p136_runtime["config"])
    checkpoint = deepcopy(p136_runtime["checkpoint"])
    checkpoint["config_hash"] = config["config_hash"]
    checkpoint["checkpoint_hash"] = stable_hash({key: value for key, value in checkpoint.items() if key != "checkpoint_hash"})
    p136_runtime["config"] = config
    p136_runtime["checkpoint"] = checkpoint
    all_entries = provider_index_entries(authority["segment_receipts"])
    if provider is None:
        entries = all_entries[:2]
    else:
        matching = [index for index, entry in enumerate(all_entries) if entry.get("provider") == provider]
        entries = all_entries[: matching[0] + 1] if matching else []
    if not entries:
        raise AssertionError(f"missing_p136_provider_fixture:{provider}")
    index_path = Path(p136_runtime["base_path"]) / config["index_path"]
    index_path.write_bytes(b"".join(canonical_bytes(entry) + b"\n" for entry in entries))
    p136_runtime["provider_entries"] = {entry["entry_hash"]: entry for entry in entries}
    observed = observe_one_cycle(p136_runtime)
    bundle = publish_p136_handoff_bundle(
        base_path=Path(p136_runtime["base_path"]),
        state_path="state/p137-publisher.json",
        intent_path="state/p137-publisher-intent.json",
        fixed_handoff_path=FIXED_P136_HANDOFF_PATH,
        p136_config=p136_runtime["config"],
        p136_runtime_authority=p136_runtime["authority"],
        now=p136_runtime["now"],
        p136_checkpoint=observed["advanced_checkpoint"],
        canonical_entry_map=p136_runtime["provider_entries"],
        promotion_records=observed["promotion_records"],
        p136_independent_review=independent_review_artifact(),
        p136_release_evidence=p136_release_evidence(status=P136_QUALIFIED_RELEASE_STATUS),
        created_at="2026-07-14T00:00:01Z",
    )
    return bundle, _runtime_config(root, chain_root=str(bundle["handoff_chain_root_hash"]))


def _effective_p137_config(root: Path, ordinal: int, runtime: dict[str, Any]) -> dict[str, Any]:
    runtime_case = ordinal in (set(range(1, 6)) | set(range(16, 45)) | {47, 48, 49})
    config_root = root / ("runtime-evidence" if runtime_case else "control-probe")
    chain_root = (
        str(runtime["handoff_bundle"]["handoff_chain_root_hash"])
        if runtime.get("input_authenticity") == "p136_validator_exact"
        else None
    )
    limits_override: dict[str, int] | None = None
    continuous_mode = False
    if ordinal == 20:
        limits_override = {"max_incident_duration_ms": 1}
    elif ordinal in {29, 58}:
        limits_override = {"max_hypotheses_per_incident": 1}
    elif ordinal in {51, 52, 53}:
        continuous_mode = True
        limits_override = {"max_cycles": 1 if ordinal == 51 else 2}
    elif ordinal == 60:
        limits_override = {"max_cycle_wall_ms": 1}
    return _runtime_config(
        config_root,
        chain_root=chain_root,
        limits_override=limits_override,
        continuous_mode=continuous_mode,
    )


def _runtime_config(root: Path, *, chain_root: str | None = None, limits_override: dict[str, int] | None = None, continuous_mode: bool = False) -> dict[str, Any]:
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
            "max_ledger_records": 4_096,
            "max_cycle_wall_ms": 1_000,
            "max_agent_wall_ms": 10_000,
            "max_cpu_ms": 1_000,
            "max_peak_memory_bytes": 16_777_216,
            "max_cycles": 2,
            "poll_interval_ms": 1,
            "heartbeat_interval_ms": 1,
            "readiness_stale_after_ms": 5,
            "handoff_version_stale_after_ms": 5,
        }
    )
    limits.update(limits_override or {})
    return build_triage_agent_config(
        {
            "agent_id": "p137-runtime",
            "config_version": 1,
            "created_at": "2026-07-14T00:00:00Z",
            "base_dir_ref_hash": stable_hash({"path": root.name}),
            "state_root_ref_hash": stable_hash({"path": "state"}),
            "handoff_root_ref_hash": stable_hash({"path": "handoff"}),
            "p136_handoff_bundle_path": FIXED_P136_HANDOFF_PATH,
            "p136_handoff_chain_root_hash": chain_root or stable_hash({"chain": "root"}),
            "checkpoint_path": "state/checkpoint.json",
            "lease_path": "state/p137.lock",
            "journal_dir": "state/journal",
            "incident_dir": "state/incidents",
            "hypothesis_dir": "state/hypotheses",
            "request_dir": "state/requests",
            "classification_dir": "state/classifications",
            "heartbeat_path": "state/heartbeat.json",
            "readiness_path": "state/readiness.json",
            "termination_dir": "state/terminations",
            "ledger_path": "state/ledger.json",
            "validated_p136_release_status": P136_QUALIFIED_RELEASE_STATUS,
            "allowed_request_catalog": list(ALLOWED_REQUEST_CATALOG),
            "correlation_policy": build_correlation_policy(),
            "ranking_policy": build_ranking_policy(),
            "classification_policy": build_classification_policy(),
            "continuous_mode": build_continuous_mode(
                enabled=continuous_mode,
                max_cycles=limits["max_cycles"],
                poll_interval_ms=limits["poll_interval_ms"],
                heartbeat_interval_ms=limits["heartbeat_interval_ms"],
                readiness_path="state/readiness.json",
                readiness_stale_after_ms=limits["readiness_stale_after_ms"],
                handoff_version_stale_after_ms=limits["handoff_version_stale_after_ms"],
            ),
            "limits": limits,
            "forbidden_authority": zero_forbidden_authority(),
        }
    )


def _runtime_bundle(case_id: str, *, label: str = "confirmed_incident", bundle_hash: str | None = None) -> dict[str, Any]:
    sequence = int(case_id.rsplit("-", 1)[1])
    atom = _atoms_for_label(case_id, label, provider="prometheus")[0]
    value: dict[str, Any] = {
        "bundle_version": 1,
        "bundle_sequence": 1,
        "bundle_hash": bundle_hash or stable_hash({"bundle": case_id}),
        "previous_bundle_hash": None,
        "handoff_chain_root_hash": stable_hash({"chain": "root"}),
        "fixed_handoff_path": FIXED_P136_HANDOFF_PATH,
        "evidence_atoms": [{**atom, "ordinal": sequence}],
    }
    return value


def _runtime_budget_abort_bundle(case_id: str) -> dict[str, Any]:
    value = _runtime_bundle(case_id, label="confirmed_incident")
    first = dict(value["evidence_atoms"][0])
    second = dict(first)
    second.update(
        atom_id=f"atom-{case_id}-budget-peer",
        promotion_record_hash=stable_hash({"promotion_record": case_id, "peer": True}),
        promotion_key=stable_hash({"promotion_key": case_id, "peer": True}),
        p136_entry_hash=stable_hash({"entry": case_id, "peer": True}),
        source_id=f"source-{case_id}-budget-peer",
        content_hash=stable_hash({"content": case_id, "peer": True}),
        ordinal=int(case_id.rsplit("-", 1)[1]) + 100,
    )
    second["atom_hash"] = stable_hash({key: item for key, item in second.items() if key != "atom_hash"})
    value["evidence_atoms"] = [first, second]
    return value


def _sum_runtime_activity(*results: dict[str, Any]) -> dict[str, int]:
    total = zero_runtime_activity()
    for result in results:
        activity = result.get("runtime_activity")
        if not isinstance(activity, dict) or set(activity) != set(total):
            raise AssertionError("runtime_activity_schema_not_observed")
        for key in total:
            total[key] += int(activity[key])
    return total


def _runtime_validator(bundle: dict[str, Any]) -> Any:
    def validate(raw: bytes, *, config: dict[str, Any], p137_checkpoint: dict[str, Any] | None = None) -> dict[str, Any]:
        assert raw
        assert config["p136_handoff_bundle_path"] == FIXED_P136_HANDOFF_PATH
        assert p137_checkpoint is None or p137_checkpoint["schema_version"] == "p137.checkpoint.v1"
        return dict(bundle)

    return validate

def _publish_runtime_bytes(root: Path, payload: bytes = b'{"bundle":"p137-control"}') -> None:
    path = root / FIXED_P136_HANDOFF_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload if payload.endswith(b"\n") else payload + b"\n")


def _ledger_maps() -> dict[str, dict[str, int]]:
    return {
        "counters": {"incident_count": 0},
        "authority_counters": zero_forbidden_authority(),
        "runtime_activity": zero_runtime_activity(),
        "evaluator_activity": zero_evaluator_activity(),
        "resource_usage": bounded_resource_usage(wall_limit_ms=30_000, cpu_limit_ms=15_000, peak_memory_limit_bytes=134_217_728),
    }


def _rehash_nested(value: dict[str, Any], hash_field: str) -> None:
    value[hash_field] = stable_hash({key: item for key, item in value.items() if key != hash_field})


def _handoff_error_code(raw: str) -> str:
    if raw.startswith("invalid_canonical_hex"):
        return "p136_handoff_authority_contract_invalid"
    return {
        "invalid_p136_release_status": "p136_release_status_unqualified",
        "handoff_sequence_rollback": "p136_handoff_sequence_rollback",
        "p136_handoff_sequence_rollback": "p136_handoff_sequence_rollback",
        "p136_handoff_same_sequence_fork": "p136_handoff_same_sequence_fork",
        "previous_bundle_hash_mismatch": "p136_handoff_previous_hash_discontinuity",
        "p136_handoff_previous_hash_discontinuity": "p136_handoff_previous_hash_discontinuity",
        "noncanonical_handoff_bytes": "p136_handoff_torn_fixed_path_replacement",
        "checkpoint_promotion_entry_missing": "p136_checkpoint_promotion_entry_absent",
        "checkpoint_promotion_value_mismatch": "p136_checkpoint_promotion_record_mismatch",
        "promotion_key_invalid": "p136_embedded_promotion_key_mismatch",
    }.get(raw, raw)


def _atoms_for_label(
    case_id: str,
    label: str,
    *,
    provider: str,
    local_request: bool = False,
    external_unavailable: bool = False,
) -> list[dict[str, Any]]:
    atom = _atom(case_id, provider=provider)
    if label == "confirmed_incident":
        atom.update(evidence_state="promoted_success", signal_name="error_rate", metric_breach_code="above_critical", marker_code="none", counter_signal_code="none", state_reason_codes=[])
    elif label == "benign_anomaly":
        atom.update(evidence_state="promoted_success", signal_name="scheduled_noise", metric_breach_code="none", marker_code="known_benign_schedule", counter_signal_code="none", state_reason_codes=[])
    elif label == "aborted_fail_closed":
        atom.update(evidence_state="promoted_success", signal_name="error_rate", metric_breach_code="above_critical", marker_code="none", counter_signal_code="none", state_reason_codes=[])
    elif local_request or external_unavailable:
        atom.update(
            evidence_state="denominator_visible_failure",
            signal_name="missing_source",
            metric_breach_code="none",
            marker_code="none",
            counter_signal_code="none",
            state_reason_codes=["local_catalog_selectable" if local_request else "provider_authority_required"],
            denominator_visible=True,
            numeric_value=None,
            numeric_unit=None,
        )
    else:
        atom.update(
            evidence_state="context_only",
            signal_name="context_only",
            metric_breach_code="none",
            marker_code="none",
            counter_signal_code="none",
            state_reason_codes=[],
            denominator_visible=False,
            numeric_value=None,
            numeric_unit=None,
        )
    atom["atom_hash"] = stable_hash({key: value for key, value in atom.items() if key != "atom_hash"})
    return [atom]


def _append_local_request_atom(atoms: list[dict[str, Any]], case_id: str, *, provider: str) -> list[dict[str, Any]]:
    missing = _atoms_for_label(case_id, "insufficient_evidence", provider=provider, local_request=True)[0]
    missing.update(
        atom_id=f"atom-{case_id}-local-request",
        promotion_record_hash=stable_hash({"promotion_record": case_id, "local_request": True}),
        promotion_key=stable_hash({"promotion_key": case_id, "local_request": True}),
        p136_entry_hash=stable_hash({"entry": case_id, "local_request": True}),
        source_id=f"source-{case_id}-local-request",
        content_hash=stable_hash({"content": case_id, "local_request": True}),
        ordinal=int(case_id.rsplit("-", 1)[1]) + 100,
    )
    missing["atom_hash"] = stable_hash({key: value for key, value in missing.items() if key != "atom_hash"})
    return [*deepcopy(atoms), missing]


def _atom(case_id: str, *, provider: str) -> dict[str, Any]:
    signal_family = "metrics" if provider in {"prometheus", "opentelemetry"} else ("logs" if provider == "loki" else ("topology" if provider == "grafana" else "events"))
    return {
        "schema_version": "p137.evidence_atom.v1",
        "atom_id": f"atom-{case_id}",
        "promotion_record_hash": stable_hash({"promotion_record": case_id}),
        "promotion_key": stable_hash({"promotion_key": case_id}),
        "p136_entry_hash": stable_hash({"entry": case_id}),
        "p135_bundle_hash": stable_hash({"p135_bundle": case_id}),
        "source_id": f"source-{case_id}",
        "provider": provider,
        "format": f"{provider}.fixture.v1",
        "signal_family": signal_family,
        "system_id": "system-a",
        "entity_ref_hash": stable_hash({"entity": "checkout"}),
        "window": {"start": "2026-07-14T00:00:00Z", "end": "2026-07-14T00:05:00Z"},
        "signal_name": "error_rate",
        "numeric_value": 5,
        "numeric_unit": "ratio",
        "evidence_state": "promoted_success",
        "severity_code": "sev2",
        "metric_breach_code": "above_critical",
        "marker_code": "none",
        "counter_signal_code": "none",
        "state_reason_codes": [],
        "denominator_visible": False,
        "content_hash": stable_hash({"content": case_id}),
        "label_hashes": [stable_hash({"label": "checkout"})],
        "topology_ref_hashes": [stable_hash({"topology": case_id})],
        "deploy_config_ref_hashes": [],
        "risk_flags": ["availability"],
        "redacted_preview_hash": stable_hash({"preview": case_id}),
        "ordinal": int(case_id.rsplit("-", 1)[1]),
        "atom_hash": stable_hash({"placeholder": case_id}),
    }


def _request_budget() -> dict[str, int]:
    return {
        "max_input_records": 256,
        "max_output_records": 64,
        "max_output_bytes": 65_536,
        "max_requests_per_incident": 8,
        "wall_limit_ms": 1_000,
        "cpu_limit_ms": 500,
        "peak_memory_limit_bytes": 16_777_216,
    }


def _request_parameters() -> dict[str, dict[str, Any]]:
    entity = stable_hash({"entity": "checkout"})
    label = stable_hash({"label": "checkout"})
    start = "2026-07-14T00:00:00Z"
    end = "2026-07-14T00:05:00Z"
    return {
        "compare_current_window_to_promoted_baseline": {
            "signal_name": "error_rate",
            "current_window_start": start,
            "current_window_end": end,
            "baseline_window_start": "2026-07-13T00:00:00Z",
            "baseline_window_end": "2026-07-13T00:05:00Z",
            "limit": 10,
        },
        "fetch_record_by_evidence_id": {"evidence_id": "atom-p137-case-31", "limit": 10},
        "join_records_by_entity_and_window": {"entity_ref_hash": entity, "window_start": start, "window_end": end, "limit": 10},
        "select_records_by_content_hash": {"content_hash": stable_hash({"content": "p137-case-33"}), "limit": 10},
        "select_records_by_entity_ref": {"entity_ref_hash": entity, "limit": 10},
        "select_records_by_label_hash": {"label_hash": label, "limit": 10},
        "select_records_by_provider": {"provider": "prometheus", "limit": 10},
        "select_records_by_risk_flag": {"risk_flag": "availability", "limit": 10},
        "select_records_by_signal_family": {"signal_family": "metrics", "limit": 10},
        "select_records_by_system_id": {"system_id": "system-a", "limit": 10},
        "select_records_by_time_window": {"window_start": start, "window_end": end, "limit": 10},
        "select_rejections_by_reason": {"reason_code": "local_catalog_selectable", "limit": 10},
        "summarize_log_preview_hashes": {"limit": 10},
        "summarize_numeric_samples": {"signal_name": "error_rate", "limit": 10},
        "summarize_topology_refs": {"limit": 10},
    }
