"""P169-P173 governed staging qualification contracts.

These phases extend the canonical P168 lab qualification into staging-shaped
evidence without granting live action, mutation, or approval authority.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.p147_p152_contracts import file_hash, stable_hash
from app.services.p164_p168_disposable_operator_program import (
    validate_release_evidence as validate_p164_p168_release_evidence,
)

_PHASES = ("p169", "p170", "p171", "p172", "p173")
_HASH_RE = re.compile(r"sha256:[0-9a-f]{64}")
_UUID7_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")
_UTC_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
_FORBIDDEN_CLAIMS = (
    "live_staging_observed_without_attachment_receipts",
    "customer_staging_readiness",
    "production_operator_replacement",
    "provider_write_adapter_safety",
    "tenant_isolation",
    "credential_operations",
)
_PRODUCTION_BLOCKERS = (
    "customer_owned_read_only_staging_attachment_required",
    "real_wall_clock_24h_staging_soak_required",
    "provider_action_adapters_required",
    "security_privacy_operational_review_required",
    "supervised_production_canary_required",
)
_COUNTER_KEYS = (
    "read_request_count",
    "live_attachment_read_count",
    "local_artifact_write_count",
    "write_request_count",
    "counterfactual_would_approve_count",
    "auto_approval_count",
    "human_approval_count",
    "action_execution_count",
    "rollback_count",
    "external_model_call_count",
    "external_network_call_count",
    "staging_mutation_count",
    "production_mutation_count",
    "real_provider_action_count",
    "credential_read_count",
    "shell_execution_count",
    "deadman_escape_count",
    "unsafe_action_count",
)
_ROOT_CAUSE_ACTIONS = {
    "db_pool_exhaustion": "tune_pool",
    "queue_backlog": "restart_worker",
    "recent_deploy_regression": "rollback_canary",
}
_SOURCE_FILES = (
    "app/services/p169_p173_governed_staging_program.py",
    "docs/operations/p169-p173-governed-staging-program.md",
    "scripts/run_p169_p173_qualification.py",
    "scripts/verify_p169_p173.sh",
    "tests/test_p169_p173_governed_staging_program.py",
)


class ProgramError(ValueError):
    """Raised when governed-staging evidence cannot prove its contract."""


@dataclass(frozen=True)
class PhaseSpec:
    phase: str
    status: str
    maximum_mode: str
    predecessor_phase: str
    predecessor_path: str
    predecessor_schema: str
    predecessor_status: str

    @property
    def report_schema(self) -> str:
        return f"{self.phase}.report.v1"

    @property
    def release_schema(self) -> str:
        return f"{self.phase}.release_evidence.v1"


SPECS = {
    "p169": PhaseSpec(
        "p169",
        "p169_governed_read_only_staging_attachment_ready",
        "governed_read_only_staging_attachment_ready_not_observed",
        "p168",
        "evals/p168/output/release-evidence.json",
        "p168.release_evidence.v1",
        "p168_accelerated_unattended_lab_soak_qualified",
    ),
    "p170": PhaseSpec(
        "p170",
        "p170_wall_clock_staging_soak_ready",
        "wall_clock_24h_staging_soak_ready_not_live",
        "p169",
        "evals/p169/output/release-evidence.json",
        "p169.release_evidence.v1",
        "p169_governed_read_only_staging_attachment_ready",
    ),
    "p171": PhaseSpec(
        "p171",
        "p171_blinded_staging_benchmark_qualified",
        "blinded_staging_judgment_benchmark_not_live",
        "p170",
        "evals/p170/output/release-evidence.json",
        "p170.release_evidence.v1",
        "p170_wall_clock_staging_soak_ready",
    ),
    "p172": PhaseSpec(
        "p172",
        "p172_attached_capability_registry_qualified",
        "observed_read_tools_only_registry_not_action_authority",
        "p171",
        "evals/p171/output/release-evidence.json",
        "p171.release_evidence.v1",
        "p171_blinded_staging_benchmark_qualified",
    ),
    "p173": PhaseSpec(
        "p173",
        "p173_shadow_approval_counterfactual_qualified",
        "counterfactual_shadow_approval_not_authority",
        "p172",
        "evals/p172/output/release-evidence.json",
        "p172.release_evidence.v1",
        "p172_attached_capability_registry_qualified",
    ),
}


class GovernedAttachmentRecorder:
    """Append-only receipt chain for governed read-only attachment attempts."""

    def __init__(self, *, mode: str, target_owner_approval: bool, live_ack: bool, credential_ref: str) -> None:
        if mode not in {"recorded", "live"}:
            raise ProgramError("attachment_mode_invalid")
        if mode == "live" and not target_owner_approval:
            raise ProgramError("target_owner_approval_required")
        if mode == "live" and live_ack is not True:
            raise ProgramError("live_attachment_ack_required")
        if mode == "live" and not re.fullmatch(r"env:[A-Z][A-Z0-9_]*", credential_ref):
            raise ProgramError("credential_reference_must_be_env_only")
        if mode == "recorded" and (target_owner_approval or live_ack or credential_ref):
            raise ProgramError("recorded_mode_must_not_claim_live_authority")
        self._mode = mode
        self._receipts: list[dict[str, Any]] = []

    def record(self, event: Mapping[str, Any]) -> dict[str, Any]:
        value = deepcopy(dict(event))
        request_id = _text(value.get("request_id"), "request_id")
        provider = _text(value.get("provider"), "provider")
        source_class = _text(value.get("source_class"), "source_class")
        observed_at = _timestamp(value.get("observed_at"))
        collected_at = _timestamp(value.get("collected_at"))
        response_hash = _hash(value.get("response_hash"), "response_hash")
        real_network = bool(value.get("real_network"))
        if self._mode == "recorded" and real_network:
            raise ProgramError("recorded_mode_cannot_claim_real_network")
        receipt = {
            "schema_version": "p169.attachment_receipt.v1",
            "request_id": request_id,
            "source_id": _text(value.get("source_id"), "source_id"),
            "provider": provider,
            "source_class": source_class,
            "observed_at": observed_at,
            "collected_at": collected_at,
            "response_hash": response_hash,
            "redaction_applied": bool(value.get("redaction_applied")),
            "real_network": real_network,
            "previous_receipt_hash": self._receipts[-1]["receipt_hash"] if self._receipts else "sha256:" + "0" * 64,
            "receipt_hash": "",
        }
        if not receipt["redaction_applied"]:
            raise ProgramError("redaction_required")
        receipt = _self_hash(receipt, "receipt_hash")
        self._receipts.append(receipt)
        return deepcopy(receipt)

    def summary(self) -> dict[str, Any]:
        provider_count = len({item["provider"] for item in self._receipts})
        source_class_count = len({item["source_class"] for item in self._receipts})
        real_network_call_count = sum(bool(item["real_network"]) for item in self._receipts)
        live_attachment_observed = (
            self._mode == "live"
            and real_network_call_count > 0
            and provider_count >= 2
            and source_class_count >= 3
        )
        return {
            "receipt_count": len(self._receipts),
            "provider_count": provider_count,
            "source_class_count": source_class_count,
            "real_network_call_count": real_network_call_count,
            "live_attachment_observed": live_attachment_observed,
            "maximum_claim": (
                "governed_read_only_staging_attachment_observed"
                if live_attachment_observed
                else "governed_read_only_staging_attachment_ready_not_observed"
            ),
            "receipt_chain_head": self._receipts[-1]["receipt_hash"] if self._receipts else "sha256:" + "0" * 64,
        }

    def validate_receipts(self, receipts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        previous = "sha256:" + "0" * 64
        validated: list[dict[str, Any]] = []
        for raw in receipts:
            receipt = deepcopy(dict(raw))
            if "response_body" in receipt or receipt.get("schema_version") != "p169.attachment_receipt.v1":
                raise ProgramError("receipt_contract_invalid")
            if receipt.get("previous_receipt_hash") != previous:
                raise ProgramError("receipt_chain_invalid")
            _validate_self_hash(receipt, "receipt_hash")
            previous = receipt["receipt_hash"]
            validated.append(receipt)
        return validated


def validate_wall_clock_soak(payload: Mapping[str, Any], *, require_live_24h: bool) -> dict[str, Any]:
    value = deepcopy(dict(payload))
    started = _timestamp(value.get("started_at"))
    ended = _timestamp(value.get("ended_at"))
    elapsed = _age_seconds(started, ended)
    if elapsed <= 0:
        raise ProgramError("wall_clock_interval_invalid")
    interval = int(value.get("frozen_poll_interval_seconds", 0))
    expected = int(value.get("expected_poll_count", 0))
    successful = int(value.get("successful_poll_count", 0))
    failed = int(value.get("failed_poll_count", 0))
    if interval <= 0 or expected <= 0 or successful < 0 or failed < 0 or successful + failed != expected:
        raise ProgramError("poll_denominator_invalid")
    segments = _mappings(value.get("segments"), "segments")
    segment_polls = 0
    segment_elapsed_ns = 0
    session_ids: set[str] = set()
    boot_ids: set[str] = set()
    for segment in segments:
        started_monotonic_ns = int(segment.get("started_monotonic_ns", 0))
        ended_monotonic_ns = int(segment.get("ended_monotonic_ns", 0))
        if ended_monotonic_ns <= started_monotonic_ns:
            raise ProgramError("monotonic_segment_invalid")
        session_id = _text(segment.get("session_id"), "session_id")
        boot_id = _text(segment.get("boot_id"), "boot_id")
        poll_count = int(segment.get("poll_count", 0))
        if session_id in session_ids or boot_id in boot_ids or poll_count <= 0:
            raise ProgramError("monotonic_segment_identity_invalid")
        session_ids.add(session_id)
        boot_ids.add(boot_id)
        segment_polls += poll_count
        segment_elapsed_ns += ended_monotonic_ns - started_monotonic_ns
    if segment_polls != expected:
        raise ProgramError("monotonic_segment_poll_mismatch")
    if segment_elapsed_ns < elapsed * 1_000_000_000:
        raise ProgramError("monotonic_segments_do_not_cover_wall_clock")
    completed = bool(value.get("wall_clock_24h_completed"))
    if completed != (elapsed >= 86_400):
        raise ProgramError("24h_claim_does_not_match_utc_wall_clock")
    polling_success_rate = _rate(successful, expected)
    if polling_success_rate < 0.999:
        raise ProgramError("polling_success_rate_below_gate")
    if require_live_24h and (not completed or value.get("restart_resume_verified") is not True or len(segments) < 2):
        raise ProgramError("24h_live_soak_required")
    if int(value.get("duplicate_evidence_count", 0)) != 0:
        raise ProgramError("duplicate_evidence_detected")
    return {
        **value,
        "elapsed_seconds": elapsed,
        "polling_success_rate": polling_success_rate,
        "wall_clock_24h_completed": completed,
    }


class BlindedStagingBenchmark:
    """Evaluate committed predictions only after checking for truth leakage."""

    def evaluate(self, cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        for case in cases:
            evidence = _mappings(case.get("evidence"), "evidence")
            for item in evidence:
                if {"truth", "outcome", "root_cause"} & set(item):
                    raise ProgramError("future_truth_leakage")
            prediction = _mapping(case.get("prediction"), "prediction")
            truth = _mapping(case.get("sealed_truth"), "sealed_truth")
            committed = _timestamp(case.get("prediction_committed_at"))
            opened = _timestamp(case.get("truth_opened_at"))
            if _age_seconds(committed, opened) <= 0:
                raise ProgramError("prediction_not_committed_before_truth")
            citations = _strings(prediction.get("citations", []), "citations", allow_empty=True)
            evidence_ids = {_text(item.get("id"), "evidence_id") for item in evidence}
            top3 = _strings(prediction.get("root_cause_top3", []), "root_cause_top3", allow_empty=True)
            incident = bool(truth.get("incident"))
            root = _text(truth.get("root_cause"), "root_cause")
            rows.append(
                {
                    "case_id": _text(case.get("case_id"), "case_id"),
                    "truth": {"incident": incident, "root_cause": root},
                    "prediction": deepcopy(dict(prediction)),
                    "top1_correct": incident and bool(top3) and top3[0] == root,
                    "top3_correct": incident and root in top3,
                    "precursor_correct": incident and bool(prediction.get("precursor")),
                    "false_alert": (not incident) and bool(prediction.get("incident")),
                    "citation_valid": set(citations).issubset(evidence_ids),
                }
            )
        positives = [row for row in rows if row["truth"]["incident"]]
        negatives = [row for row in rows if not row["truth"]["incident"]]
        false_alerts = sum(row["false_alert"] for row in negatives)
        false_rate = _rate(false_alerts, len(negatives))
        upper = _zero_false_upper_bound(len(negatives)) if false_alerts == 0 else min(1.0, false_rate + 1.96 * math.sqrt(false_rate * (1 - false_rate) / max(1, len(negatives))))
        metrics = {
            "incident_case_count": len(positives),
            "healthy_window_count": len(negatives),
            "root_cause_top1_accuracy": _rate(sum(row["top1_correct"] for row in positives), len(positives)),
            "root_cause_top3_recall": _rate(sum(row["top3_correct"] for row in positives), len(positives)),
            "precursor_recall": _rate(sum(row["precursor_correct"] for row in positives), len(positives)),
            "false_alert_rate": false_rate,
            "false_alert_rate_95pct_upper": upper,
            "citation_validity_rate": _rate(sum(row["citation_valid"] for row in rows), len(rows)),
        }
        per_family = {
            family: {
                "case_count": len(items),
                "top3_recall": _rate(sum(row["top3_correct"] for row in items), len(items)),
            }
            for family, items in _group_by_family(positives).items()
        }
        qualified = (
            metrics["incident_case_count"] >= 30
            and metrics["healthy_window_count"] >= 300
            and metrics["root_cause_top1_accuracy"] >= 0.80
            and metrics["root_cause_top3_recall"] >= 0.95
            and metrics["precursor_recall"] >= 0.80
            and metrics["false_alert_rate"] == 0.0
            and metrics["false_alert_rate_95pct_upper"] <= 0.01
            and metrics["citation_validity_rate"] == 1.0
        )
        return {
            "schema_version": "p171.blinded_benchmark.v1",
            "metrics": metrics,
            "per_family": per_family,
            "confidence_bound_qualified": qualified,
            "qualification": "confidence_bound_qualified" if qualified else "informational_point_estimate_only",
            "rows_hash": stable_hash(rows),
        }


class AttachedCapabilityRegistry:
    """Registry limited to observed read tools."""

    def __init__(self, observed_sources: Sequence[Mapping[str, Any]], *, max_tool_calls: int) -> None:
        if max_tool_calls <= 0 or max_tool_calls > 8:
            raise ProgramError("tool_call_budget_invalid")
        self._max_tool_calls = max_tool_calls
        tools: set[str] = set()
        for item in observed_sources:
            source = _mapping(item, "observed_source")
            if source.get("observed") is True:
                provider = _text(source.get("provider"), "provider")
                source_class = _text(source.get("source_class"), "source_class")
                tools.add(f"{provider}.{source_class}.read")
        self._tools = tuple(sorted(tools))

    def available_tools(self) -> tuple[str, ...]:
        return self._tools

    def evaluate(self, *, tool_calls: Sequence[str], evidence: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        calls = tuple(tool_calls)
        if len(calls) > self._max_tool_calls:
            raise ProgramError("tool_call_budget_exceeded")
        unknown = set(calls) - set(self._tools)
        if unknown:
            raise ProgramError("tool_not_observed")
        rows = _mappings(evidence, "evidence")
        evidence_ids: set[str] = set()
        for item in rows:
            evidence_id = _text(item.get("id"), "evidence_id")
            provider = _text(item.get("provider"), "provider")
            source_class = _text(item.get("source_class"), "source_class")
            state = _text(item.get("state"), "state")
            age_seconds = float(item.get("age_seconds", -1))
            if evidence_id in evidence_ids or f"{provider}.{source_class}.read" not in self._tools:
                raise ProgramError("evidence_source_not_observed")
            if state not in {"supporting", "contradicting", "absent", "unavailable"} or age_seconds < 0:
                raise ProgramError("evidence_state_invalid")
            evidence_ids.add(evidence_id)
        classes = {_text(item.get("source_class"), "source_class") for item in rows if item.get("state") == "supporting"}
        stale = any(float(item.get("age_seconds", 0)) > 60.0 for item in rows)
        contradicting = any(item.get("state") == "contradicting" for item in rows)
        route = "evidence_sufficient" if len(classes) >= 2 and not stale and not contradicting else "investigate_more"
        if stale or contradicting:
            route = "human_required"
        return {
            "route": route,
            "tool_call_count": len(calls),
            "independent_source_class_count": len(classes),
            "available_tools": self._tools,
        }


class ShadowApprovalEvaluator:
    """Counterfactual approval evaluator that never mints authority."""

    def __init__(self) -> None:
        self._counterfactual = 0
        self._requests: dict[str, tuple[str, dict[str, Any]]] = {}

    def evaluate(self, candidate: Mapping[str, Any]) -> dict[str, Any]:
        value = deepcopy(dict(candidate))
        request_id = _text(value.get("request_id"), "request_id")
        content_hash = stable_hash(value)
        previous = self._requests.get(request_id)
        if previous is not None:
            if previous[0] != content_hash:
                raise ProgramError("counterfactual_idempotency_content_mismatch")
            return deepcopy(previous[1])
        root = _text(value.get("root_cause"), "root_cause")
        action = _ROOT_CAUSE_ACTIONS.get(root)
        citations = _mappings(value.get("citations"), "citations")
        classes = {_text(item.get("source_class"), "source_class") for item in citations}
        blocked = value.get("kill_switch") is True or value.get("deadman_active") is not True
        eligible = (
            action is not None
            and float(value.get("confidence", 0.0)) >= 0.90
            and len(classes) >= 2
            and 0.0 <= float(value.get("observed_age_seconds", 9999)) <= 30.0
            and 0.0 <= float(value.get("heartbeat_age_seconds", 9999)) <= 60.0
            and value.get("target") == "staging-shadow"
            and not blocked
        )
        if blocked:
            route = "blocked"
        elif eligible:
            route = "would_approve_not_authorized"
            self._counterfactual += 1
        else:
            route = "human_required"
        reasons: list[str] = []
        if blocked:
            reasons.append("kill_switch_or_deadman_blocked")
        elif not eligible:
            reasons.append("evidence_policy_or_freshness_insufficient")
        decision = {
            "schema_version": "p173.shadow_approval_decision.v1",
            "request_id": request_id,
            "route": route,
            "action": action or "deny",
            "reasons": reasons,
            "expected_postcheck": "fresh_health_and_fault_signal_reduction" if eligible else "none",
            "rollback_plan": "restore_pre_state_and_verify" if eligible else "none",
            "authority_receipt": "counterfactual_no_execution_authority",
            "expires_in_seconds": 30 if eligible else 0,
            "evidence_hash": stable_hash(citations),
            "replay_hash": stable_hash({"candidate_hash": content_hash, "route": route, "action": action or "deny"}),
            "decision_hash": stable_hash({"candidate": value, "route": route, "action": action or "deny"}),
        }
        self._requests[request_id] = (content_hash, deepcopy(decision))
        return decision

    def counters(self) -> dict[str, int]:
        return {
            "counterfactual_would_approve_count": self._counterfactual,
            "auto_approval_count": 0,
            "human_approval_count": 0,
            "action_execution_count": 0,
            "staging_mutation_count": 0,
            "production_mutation_count": 0,
            "unsafe_action_count": 0,
        }


def load_phase_input(path: Path, phase: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ProgramError(f"input_missing:{path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProgramError(f"input_json_invalid:{path}") from exc
    if not isinstance(value, dict):
        raise ProgramError("input_object_required")
    if phase in _PHASES and (value.get("schema_version") != f"{phase}.input.v1" or value.get("phase") != phase):
        raise ProgramError(f"input_schema_invalid:{phase}")
    return value


def evaluate_p169(payload: Mapping[str, Any], predecessor: Mapping[str, Any], *, project_root: Path) -> dict[str, Any]:
    value = _input(payload, "p169")
    recorder = GovernedAttachmentRecorder(mode="recorded", target_owner_approval=False, live_ack=False, credential_ref="")
    receipts = [recorder.record(event) for event in _mappings(value.get("attachment_events", value.get("events", [])), "attachment_events")]
    recorder.validate_receipts(receipts)
    summary = recorder.summary()
    passed = summary["receipt_count"] > 0 and summary["real_network_call_count"] == 0
    rows = [_row("p169-attachment-receipts", passed, summary)]
    metrics = {**summary, "maximum_qualified_mode": SPECS["p169"].maximum_mode}
    return _report("p169", value, predecessor, rows, metrics, _counters(read_request_count=summary["receipt_count"]), project_root)


def evaluate_p170(payload: Mapping[str, Any], predecessor: Mapping[str, Any], *, project_root: Path) -> dict[str, Any]:
    value = _input(payload, "p170")
    soak = validate_wall_clock_soak(_mapping(value.get("soak", value.get("wall_clock_soak", value.get("configuration"))), "soak"), require_live_24h=False)
    rows = [_row("p170-wall-clock-soak", soak["wall_clock_24h_completed"] is False, soak)]
    metrics = {
        "elapsed_seconds": soak["elapsed_seconds"],
        "polling_success_rate": soak["polling_success_rate"],
        "wall_clock_24h_completed": soak["wall_clock_24h_completed"],
        "restart_resume_verified": bool(soak.get("restart_resume_verified")),
        "maximum_qualified_mode": SPECS["p170"].maximum_mode,
    }
    return _report("p170", value, predecessor, rows, metrics, _counters(read_request_count=int(soak["successful_poll_count"])), project_root)


def evaluate_p171(payload: Mapping[str, Any], predecessor: Mapping[str, Any], *, project_root: Path) -> dict[str, Any]:
    value = _input(payload, "p171")
    result = BlindedStagingBenchmark().evaluate(_mappings(value.get("cases"), "cases"))
    rows = [_row("p171-blinded-benchmark", result["confidence_bound_qualified"] is True, result["metrics"])]
    metrics = {**result["metrics"], "maximum_qualified_mode": SPECS["p171"].maximum_mode}
    return _report("p171", value, predecessor, rows, metrics, _counters(), project_root)


def evaluate_p172(payload: Mapping[str, Any], predecessor: Mapping[str, Any], *, project_root: Path) -> dict[str, Any]:
    value = _input(payload, "p172")
    registry = AttachedCapabilityRegistry(_mappings(value.get("observed_sources"), "observed_sources"), max_tool_calls=int(value.get("max_tool_calls", 8)))
    decision = registry.evaluate(tool_calls=_strings(value.get("tool_calls", []), "tool_calls", allow_empty=True), evidence=_mappings(value.get("evidence"), "evidence"))
    rows = [_row("p172-observed-read-tools", decision["route"] == "evidence_sufficient", decision)]
    metrics = {
        "available_tool_count": len(registry.available_tools()),
        "independent_source_class_count": decision["independent_source_class_count"],
        "route": decision["route"],
        "maximum_qualified_mode": SPECS["p172"].maximum_mode,
    }
    return _report("p172", value, predecessor, rows, metrics, _counters(read_request_count=decision["tool_call_count"]), project_root)


def evaluate_p173(payload: Mapping[str, Any], predecessor: Mapping[str, Any], *, project_root: Path) -> dict[str, Any]:
    value = _input(payload, "p173")
    evaluator = ShadowApprovalEvaluator()
    decisions = [evaluator.evaluate(candidate) for candidate in _mappings(value.get("candidates"), "candidates")]
    rows = [_row("p173-counterfactual-approval", any(item["route"] == "would_approve_not_authorized" for item in decisions), {"decisions": decisions})]
    counters = _counters(**evaluator.counters())
    metrics = {
        "decision_count": len(decisions),
        "would_approve_not_authorized_count": evaluator.counters()["counterfactual_would_approve_count"],
        "maximum_qualified_mode": SPECS["p173"].maximum_mode,
    }
    return _report("p173", value, predecessor, rows, metrics, counters, project_root)


def build_freeze_manifest(phase: str, report: Mapping[str, Any], *, project_root: Path) -> dict[str, Any]:
    validated = validate_report(phase, report)
    current = _source_hashes(project_root, phase)
    if validated["source_hashes"] != current:
        raise ProgramError("freeze_source_hashes_stale")
    return _self_hash(
        {
            "schema_version": f"{phase}.freeze_manifest.v1",
            "phase": phase,
            "source_hashes": current,
            "predecessor": validated["predecessor"],
            "report_hash": validated["report_hash"],
            "manifest_hash": "",
        },
        "manifest_hash",
    )


def build_final_review(
    phase: str,
    report: Mapping[str, Any],
    freeze: Mapping[str, Any],
    *,
    writer_agent_id: str,
    reviewer_agent_id: str,
    reviewed_at: str,
) -> dict[str, Any]:
    validated_report = validate_report(phase, report)
    validated_freeze = validate_freeze_manifest(phase, freeze)
    if writer_agent_id == reviewer_agent_id or _UUID7_RE.fullmatch(writer_agent_id) is None or _UUID7_RE.fullmatch(reviewer_agent_id) is None:
        raise ProgramError("reviewer_identity_not_independent")
    return _self_hash(
        {
            "schema_version": f"{phase}.final_review.v1",
            "phase": phase,
            "writer_agent_id": writer_agent_id,
            "reviewer_agent_id": reviewer_agent_id,
            "reviewed_at": _timestamp(reviewed_at),
            "decision": "approved_bounded_claim",
            "finding_count": 0,
            "report_hash": validated_report["report_hash"],
            "freeze_hash": validated_freeze["manifest_hash"],
            "review_hash": "",
        },
        "review_hash",
    )


def assemble_release_evidence(phase: str, report: Mapping[str, Any], freeze: Mapping[str, Any], review: Mapping[str, Any]) -> dict[str, Any]:
    validated_report = validate_report(phase, report)
    validated_freeze = validate_freeze_manifest(phase, freeze)
    validated_review = validate_final_review(phase, review, report=validated_report, freeze=validated_freeze)
    return _self_hash(
        {
            "schema_version": SPECS[_phase(phase)].release_schema,
            "phase": phase,
            "status": validated_report["status"],
            "maximum_qualified_mode": validated_report["maximum_qualified_mode"],
            "forbidden_claims": validated_report["forbidden_claims"],
            "production_blockers": validated_report["production_blockers"],
            "source_hashes": validated_report["source_hashes"],
            "predecessor": validated_report["predecessor"],
            "metrics": validated_report["metrics"],
            "counters": validated_report["counters"],
            "passed": validated_report["passed"],
            "failed": validated_report["failed"],
            "report_hash": validated_report["report_hash"],
            "freeze_hash": validated_freeze["manifest_hash"],
            "review_hash": validated_review["review_hash"],
            "evidence_hash": "",
        },
        "evidence_hash",
    )


def validate_release_evidence(
    phase: str,
    release: Mapping[str, Any],
    *,
    project_root: Path,
    report: Mapping[str, Any] | None = None,
    freeze: Mapping[str, Any] | None = None,
    review: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    spec = SPECS[_phase(phase)]
    value = deepcopy(dict(release))
    required = {
        "schema_version",
        "phase",
        "status",
        "maximum_qualified_mode",
        "forbidden_claims",
        "production_blockers",
        "source_hashes",
        "predecessor",
        "metrics",
        "counters",
        "passed",
        "failed",
        "report_hash",
        "freeze_hash",
        "review_hash",
        "evidence_hash",
    }
    if set(value) != required or value["schema_version"] != spec.release_schema or value["phase"] != phase:
        raise ProgramError("release_contract_invalid")
    if value["status"] != spec.status or value["maximum_qualified_mode"] != spec.maximum_mode:
        raise ProgramError("release_claim_invalid")
    if value["forbidden_claims"] != list(_FORBIDDEN_CLAIMS) or value["production_blockers"] != list(_PRODUCTION_BLOCKERS):
        raise ProgramError("release_bounded_claim_invalid")
    _validate_self_hash(value, "evidence_hash")
    if value["source_hashes"] != _source_hashes(project_root, phase):
        raise ProgramError("release_source_bindings_stale")
    if value["predecessor"] != _canonical_predecessor(phase, project_root):
        raise ProgramError("release_predecessor_binding_stale")
    _validate_counters(value["counters"])
    report_path = project_root / f"evals/{phase}/output/report.json"
    freeze_path = project_root / f"evals/{phase}/output/freeze-manifest.json"
    review_path = project_root / f"evals/{phase}/final-implementation-review.json"
    canonical_report = validate_report(phase, report or load_phase_input(report_path, f"{phase}-report"))
    canonical_freeze = validate_freeze_manifest(phase, freeze or load_phase_input(freeze_path, f"{phase}-freeze"))
    canonical_review = validate_final_review(
        phase,
        review or load_phase_input(review_path, f"{phase}-review"),
        report=canonical_report,
        freeze=canonical_freeze,
    )
    if (
        value["report_hash"] != canonical_report["report_hash"]
        or value["freeze_hash"] != canonical_freeze["manifest_hash"]
        or value["review_hash"] != canonical_review["review_hash"]
        or value["metrics"] != canonical_report["metrics"]
        or value["counters"] != canonical_report["counters"]
    ):
        raise ProgramError("release_companion_binding_invalid")
    return value


def validate_report(phase: str, report: Mapping[str, Any]) -> dict[str, Any]:
    spec = SPECS[_phase(phase)]
    value = deepcopy(dict(report))
    required = {
        "schema_version",
        "phase",
        "status",
        "maximum_qualified_mode",
        "forbidden_claims",
        "production_blockers",
        "input_hash",
        "predecessor",
        "source_hashes",
        "metrics",
        "counters",
        "case_count",
        "passed",
        "failed",
        "rows",
        "report_hash",
    }
    if set(value) != required or value["schema_version"] != spec.report_schema or value["phase"] != phase:
        raise ProgramError("report_contract_invalid")
    if value["status"] != spec.status or value["maximum_qualified_mode"] != spec.maximum_mode:
        raise ProgramError("report_claim_invalid")
    if value["forbidden_claims"] != list(_FORBIDDEN_CLAIMS) or value["production_blockers"] != list(_PRODUCTION_BLOCKERS):
        raise ProgramError("report_bounded_claim_invalid")
    _hash(value["input_hash"], "input_hash")
    _validate_predecessor_shape(phase, value["predecessor"])
    _hash_map(value["source_hashes"], "source_hashes")
    value["counters"] = _validate_counters(value["counters"])
    rows = _mappings(value["rows"], "rows")
    if value["case_count"] != len(rows) or value["passed"] != sum(bool(row.get("passed")) for row in rows) or value["failed"] != len(rows) - value["passed"]:
        raise ProgramError("report_denominator_invalid")
    for row in rows:
        _validate_row(row)
    _validate_self_hash(value, "report_hash")
    return value


def validate_freeze_manifest(phase: str, freeze: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(freeze))
    if set(value) != {"schema_version", "phase", "source_hashes", "predecessor", "report_hash", "manifest_hash"}:
        raise ProgramError("freeze_keyset_invalid")
    if value["schema_version"] != f"{phase}.freeze_manifest.v1" or value["phase"] != phase:
        raise ProgramError("freeze_contract_invalid")
    _hash_map(value["source_hashes"], "source_hashes")
    _validate_predecessor_shape(phase, value["predecessor"])
    _hash(value["report_hash"], "report_hash")
    _validate_self_hash(value, "manifest_hash")
    return value


def validate_final_review(phase: str, review: Mapping[str, Any], *, report: Mapping[str, Any], freeze: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(review))
    required = {
        "schema_version",
        "phase",
        "writer_agent_id",
        "reviewer_agent_id",
        "reviewed_at",
        "decision",
        "finding_count",
        "report_hash",
        "freeze_hash",
        "review_hash",
    }
    if set(value) != required or value["schema_version"] != f"{phase}.final_review.v1" or value["phase"] != phase:
        raise ProgramError("review_contract_invalid")
    if value["writer_agent_id"] == value["reviewer_agent_id"] or _UUID7_RE.fullmatch(value["writer_agent_id"]) is None or _UUID7_RE.fullmatch(value["reviewer_agent_id"]) is None:
        raise ProgramError("reviewer_identity_not_independent")
    _timestamp(value["reviewed_at"])
    if value["decision"] != "approved_bounded_claim" or value["finding_count"] != 0:
        raise ProgramError("review_findings_not_closed")
    if value["report_hash"] != report["report_hash"] or value["freeze_hash"] != freeze["manifest_hash"]:
        raise ProgramError("review_binding_invalid")
    _validate_self_hash(value, "review_hash")
    return value


def _report(
    phase: str,
    payload: Mapping[str, Any],
    predecessor: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    metrics: Mapping[str, Any],
    counters: Mapping[str, Any],
    project_root: Path,
) -> dict[str, Any]:
    normalized_rows = [_validate_row(row) for row in rows]
    if any(not row["passed"] for row in normalized_rows):
        raise ProgramError(f"{phase}_case_gate_failed")
    spec = SPECS[phase]
    value = {
        "schema_version": spec.report_schema,
        "phase": phase,
        "status": spec.status,
        "maximum_qualified_mode": spec.maximum_mode,
        "forbidden_claims": list(_FORBIDDEN_CLAIMS),
        "production_blockers": list(_PRODUCTION_BLOCKERS),
        "input_hash": stable_hash(payload),
        "predecessor": _validate_predecessor(phase, predecessor, project_root),
        "source_hashes": _source_hashes(project_root, phase),
        "metrics": deepcopy(dict(metrics)),
        "counters": _validate_counters(counters),
        "case_count": len(normalized_rows),
        "passed": len(normalized_rows),
        "failed": 0,
        "rows": normalized_rows,
        "report_hash": "",
    }
    return validate_report(phase, _self_hash(value, "report_hash"))


def _validate_predecessor(phase: str, predecessor: Mapping[str, Any], project_root: Path) -> dict[str, Any]:
    canonical_value = load_phase_input(project_root / SPECS[phase].predecessor_path, f"{SPECS[phase].predecessor_phase}-release")
    if deepcopy(dict(predecessor)) != canonical_value:
        raise ProgramError("predecessor_not_canonical")
    return _canonical_predecessor(phase, project_root)


def _canonical_predecessor(phase: str, project_root: Path) -> dict[str, Any]:
    spec = SPECS[phase]
    path = project_root / spec.predecessor_path
    value = load_phase_input(path, f"{spec.predecessor_phase}-release")
    if phase == "p169":
        validated = validate_p164_p168_release_evidence("p168", value, project_root=project_root)
    else:
        validated = validate_release_evidence(spec.predecessor_phase, value, project_root=project_root)
    if validated.get("schema_version") != spec.predecessor_schema or validated.get("status") != spec.predecessor_status:
        raise ProgramError("predecessor_schema_or_status_invalid")
    return {
        "phase": spec.predecessor_phase,
        "path": spec.predecessor_path,
        "schema_version": spec.predecessor_schema,
        "required_status": spec.predecessor_status,
        "file_hash": file_hash(path),
        "evidence_hash": _hash(validated.get("evidence_hash"), "predecessor_evidence_hash"),
    }


def _source_hashes(project_root: Path, phase: str) -> dict[str, str]:
    paths = (
        *_SOURCE_FILES,
        f"docs/operations/{phase}-plan-review.md",
        f"docs/operations/{phase}-test-spec.md",
        f"docs/tickets/{phase}/README.md",
        f"evals/{phase}/input/cases.json",
    )
    return {relative: file_hash(project_root / relative) for relative in paths}


def _input(payload: Mapping[str, Any], phase: str) -> dict[str, Any]:
    value = deepcopy(dict(payload))
    if value.get("schema_version") != f"{phase}.input.v1" or value.get("phase") != phase:
        raise ProgramError(f"input_schema_invalid:{phase}")
    return value


def _row(row_id: str, passed: bool, details: Mapping[str, Any]) -> dict[str, Any]:
    return _self_hash({"row_id": row_id, "passed": bool(passed), "details": deepcopy(dict(details)), "row_hash": ""}, "row_hash")


def _validate_row(row: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(row))
    if set(value) != {"row_id", "passed", "details", "row_hash"}:
        raise ProgramError("row_keyset_invalid")
    _text(value["row_id"], "row_id")
    if not isinstance(value["details"], dict):
        raise ProgramError("row_details_invalid")
    _validate_self_hash(value, "row_hash")
    return value


def _counters(**overrides: int) -> dict[str, int]:
    counters = {key: 0 for key in _COUNTER_KEYS}
    for key, value in overrides.items():
        if key not in counters:
            raise ProgramError(f"counter_unknown:{key}")
        counters[key] = int(value)
    return _validate_counters(counters)


def _validate_counters(counters: Mapping[str, Any]) -> dict[str, int]:
    if set(counters) != set(_COUNTER_KEYS):
        raise ProgramError("counter_keyset_invalid")
    value = {key: int(counters[key]) for key in _COUNTER_KEYS}
    for key, item in value.items():
        if item < 0:
            raise ProgramError(f"counter_negative:{key}")
    for key in ("write_request_count", "auto_approval_count", "human_approval_count", "action_execution_count", "staging_mutation_count", "production_mutation_count"):
        if value[key] != 0:
            raise ProgramError(f"zero_authority_counter_nonzero:{key}")
    return value


def _phase(phase: str) -> str:
    if phase not in SPECS:
        raise ProgramError(f"phase_unknown:{phase}")
    return phase


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ProgramError(f"{name}_object_required")
    return deepcopy(dict(value))


def _mappings(value: Any, name: str) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ProgramError(f"{name}_list_required")
    return [_mapping(item, name) for item in value]


def _strings(value: Any, name: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ProgramError(f"{name}_list_required")
    result = [_text(item, name) for item in value]
    if not allow_empty and not result:
        raise ProgramError(f"{name}_empty")
    return result


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ProgramError(f"{name}_text_required")
    return value


def _hash(value: Any, name: str) -> str:
    text = _text(value, name)
    if _HASH_RE.fullmatch(text) is None:
        raise ProgramError(f"{name}_hash_invalid")
    return text


def _hash_map(value: Any, name: str) -> dict[str, str]:
    mapping = _mapping(value, name)
    if not mapping:
        raise ProgramError(f"{name}_empty")
    return {_text(key, f"{name}_key"): _hash(item, f"{name}_value") for key, item in mapping.items()}


def _timestamp(value: Any) -> str:
    text = _text(value, "timestamp")
    if _UTC_RE.fullmatch(text) is None:
        raise ProgramError("timestamp_must_be_utc_z")
    try:
        datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise ProgramError("timestamp_invalid") from exc
    return text


def _age_seconds(start: str, end: str) -> int:
    first = datetime.strptime(_timestamp(start), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    second = datetime.strptime(_timestamp(end), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    return int((second - first).total_seconds())


def _rate(numerator: int, denominator: int) -> float:
    return 0.0 if denominator == 0 else float(numerator) / float(denominator)


def _zero_false_upper_bound(negative_count: int) -> float:
    return 1.0 if negative_count <= 0 else 1.0 - (0.05 ** (1.0 / negative_count))


def _group_by_family(rows: Sequence[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    result: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        family = _text(_mapping(row.get("truth"), "truth").get("root_cause"), "root_cause")
        result.setdefault(family, []).append(row)
    return result


def _self_hash(value: Mapping[str, Any], field: str) -> dict[str, Any]:
    result = deepcopy(dict(value))
    result[field] = stable_hash({key: item for key, item in result.items() if key != field})
    return result


def _validate_self_hash(value: Mapping[str, Any], field: str) -> None:
    _hash(value.get(field), field)
    expected = stable_hash({key: item for key, item in value.items() if key != field})
    if value[field] != expected:
        raise ProgramError(f"{field}_self_hash_invalid")


def _validate_predecessor_shape(phase: str, value: Any) -> dict[str, Any]:
    predecessor = _mapping(value, "predecessor")
    spec = SPECS[phase]
    expected = {
        "phase": spec.predecessor_phase,
        "path": spec.predecessor_path,
        "schema_version": spec.predecessor_schema,
        "required_status": spec.predecessor_status,
    }
    for key, item in expected.items():
        if predecessor.get(key) != item:
            raise ProgramError("predecessor_shape_invalid")
    _hash(predecessor.get("file_hash"), "predecessor_file_hash")
    _hash(predecessor.get("evidence_hash"), "predecessor_evidence_hash")
    return predecessor
