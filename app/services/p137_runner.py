"""Deterministic P137 canonical 60-case release runner."""

# ruff: noqa: E501

from __future__ import annotations

import resource
import time
from collections.abc import Callable, Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p137_classification import derive_classification
from app.services.p137_contracts import (
    ALLOWED_REQUEST_CATALOG,
    P137ContractError,
    bounded_resource_usage,
    validate_triage_agent_config,
    zero_evaluator_activity,
    zero_forbidden_authority,
    zero_runtime_activity,
)
from app.services.p137_correlation import correlate_incident_state
from app.services.p137_hypotheses import rank_incident_hypotheses
from app.services.p137_release_evidence import (
    P137ReleaseEvidenceError,
    assemble_p137_release_evidence_from_frozen_matrix,
    validate_final_implementation_review,
)
from app.services.p137_requests import build_request_budget, execute_evidence_request

RuntimeFactory = Callable[[str], Mapping[str, Any]]


class P137RunnerError(ValueError):
    """Raised when the P137 runner cannot prove the release matrix."""


def _case(
    category: str,
    semantic: str,
    expected_label: str,
    expected_error: str | None,
    termination_reason: str,
    scope: str,
    delta_profile: str,
    *,
    request_catalog_entry: str | None = None,
    provider_profile: str | None = None,
) -> dict[str, Any]:
    return {
        "category": category,
        "semantic": semantic,
        "expected_label": expected_label,
        "expected_error": expected_error,
        "termination_reason": termination_reason,
        "scope": scope,
        "delta_profile": delta_profile,
        "request_catalog_entry": request_catalog_entry,
        "provider_profile": provider_profile,
    }


_PROVIDERS = ("prometheus", "loki", "grafana", "sentry", "opentelemetry")
PRELIMINARY_MATRIX_SCHEMA_VERSION = "p137.preliminary_matrix.v2"


def _request_label(index: int) -> str:
    labels = {
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
    }
    return labels[index]


_ROWS: tuple[dict[str, Any], ...] = (
    _case("ingest", "Ingest single Prometheus metric promotion and create one atom.", "insufficient_evidence", None, "none", "accepted incident", "dp_classified_no_request", provider_profile="prometheus"),
    _case("ingest", "Ingest single Loki log promotion and validate preview hash.", "insufficient_evidence", None, "none", "accepted incident", "dp_classified_no_request", provider_profile="loki"),
    _case("ingest", "Ingest single Grafana topology promotion.", "insufficient_evidence", None, "none", "accepted incident", "dp_classified_no_request", provider_profile="grafana"),
    _case("ingest", "Ingest single Sentry event promotion.", "insufficient_evidence", None, "none", "accepted incident", "dp_classified_no_request", provider_profile="sentry"),
    _case("ingest", "Ingest single OTLP metric promotion.", "insufficient_evidence", None, "none", "accepted incident", "dp_classified_no_request", provider_profile="opentelemetry"),
    _case("handoff", "Reject unqualified P136 release status.", "none", "p136_release_status_unqualified", "pre_ingest_rejected", "pre-ingest", "dp_pre_ingest_reject"),
    _case("handoff", "Reject bundle sequence rollback below P137 checkpoint.", "none", "p136_handoff_sequence_rollback", "pre_ingest_rejected", "pre-ingest", "dp_pre_ingest_reject"),
    _case("handoff", "Reject same-sequence fork with different bundle hash.", "none", "p136_handoff_same_sequence_fork", "pre_ingest_rejected", "pre-ingest", "dp_pre_ingest_reject"),
    _case("handoff", "Reject previous-hash discontinuity from the last accepted bundle hash.", "none", "p136_handoff_previous_hash_discontinuity", "pre_ingest_rejected", "pre-ingest", "dp_pre_ingest_reject"),
    _case("handoff", "Reject torn fixed-path replacement by descriptor length/hash, bundle hash, and parent fsync mismatch.", "none", "p136_handoff_torn_fixed_path_replacement", "pre_ingest_rejected", "pre-ingest", "dp_pre_ingest_reject"),
    _case("handoff", "Reject absent promotion.entry_hash key in checkpoint promotion_keys.", "none", "p136_checkpoint_promotion_entry_absent", "pre_ingest_rejected", "pre-ingest", "dp_pre_ingest_reject"),
    _case("handoff", "Reject altered canonical promotion record value under the correct checkpoint key.", "none", "p136_checkpoint_promotion_record_mismatch", "pre_ingest_rejected", "pre-ingest", "dp_pre_ingest_reject"),
    _case("handoff", "Reject nested promotion_key tamper after recomputing embedded promotion key.", "none", "p136_embedded_promotion_key_mismatch", "pre_ingest_rejected", "pre-ingest", "dp_pre_ingest_reject"),
    _case("authority", "Reject noncanonical authority hexadecimal bytes, nonzero P136 forbidden counters, or promoted forbidden fields.", "none", "p136_handoff_authority_contract_invalid", "pre_ingest_rejected", "pre-ingest", "dp_pre_ingest_reject"),
    _case("guard", "Evaluator-injected fake guard callables are blocked before the runtime boundary.", "none", "guard_probe_blocked_before_boundary", "evaluator_only", "evaluator-only", "dp_evaluator_guard"),
    _case("correlation", "Correlate same system/time metrics and logs into one incident.", "confirmed_incident", None, "none", "accepted incident", "dp_classified_no_request"),
    _case("correlation", "Keep different systems separate.", "insufficient_evidence", None, "none", "accepted incidents", "dp_classified_no_request"),
    _case("correlation", "Correlate shared entity hash across providers.", "confirmed_incident", None, "none", "accepted incident", "dp_classified_no_request"),
    _case("correlation", "Correlate denominator-visible P136 rejection with nearby telemetry.", "insufficient_evidence", None, "none", "accepted incident", "dp_classified_no_request"),
    _case("correlation", "Reject correlation window budget exceeded after incident creation.", "aborted_fail_closed", None, "aborted_fail_closed", "accepted incident", "dp_abort_written"),
    _case("correlation", "Preserve stable incident ID on restart duplicate ingest.", "insufficient_evidence", None, "none", "accepted incident", "dp_recovery_after_ingest_intent"),
    _case("hypothesis", "Rank error-rate hypothesis above telemetry-gap when support dominates.", "confirmed_incident", None, "none", "accepted incident", "dp_classified_no_request"),
    _case("hypothesis", "Rank telemetry-gap hypothesis when only missing-source evidence exists.", "insufficient_evidence", None, "none", "accepted incident", "dp_classified_no_request"),
    _case("hypothesis", "Rank benign-pattern hypothesis with scheduled-noise support.", "benign_anomaly", None, "none", "accepted incident", "dp_classified_no_request"),
    _case("hypothesis", "Record decisive contradiction that suppresses confirmation.", "insufficient_evidence", None, "none", "accepted incident", "dp_classified_no_request"),
    _case("hypothesis", "Record blocking missing local evidence after one-shot request attempt.", "insufficient_evidence", None, "none", "accepted incident", "dp_classified_with_request"),
    _case("hypothesis", "Record blocking external unavailable need without executing it.", "insufficient_evidence", None, "none", "accepted incident", "dp_classified_no_request"),
    _case("hypothesis", "Preserve unresolved semantic tie even though lexical hash orders storage.", "insufficient_evidence", None, "none", "accepted incident", "dp_classified_no_request"),
    _case("budget", "Enforce hypothesis, support-edge, contradiction-edge, and missing-evidence budgets.", "aborted_fail_closed", None, "aborted_fail_closed", "accepted incident", "dp_abort_written"),
    *tuple(_case("request", f"Execute {entry}.", _request_label(index), None, "none", "accepted incident", "dp_classified_with_request", request_catalog_entry=entry) for index, entry in enumerate(ALLOWED_REQUEST_CATALOG, start=30)),
    _case("signal", "SIGINT at a safe boundary before handoff read returns no classification.", "none", "signal_before_handoff_safe_boundary", "sigint", "runtime termination", "dp_signal_no_classification"),
    _case("durability", "Corrupt durable state hash mismatch preserves last valid ledger and returns no classification.", "none", "p137_state_corrupt_hash_mismatch", "corrupt_state", "state rejection", "dp_corrupt_state_no_write"),
    _case("classification", "Confirm incident with multi-source support and no blocking gaps.", "confirmed_incident", None, "none", "accepted incident", "dp_classified_no_request"),
    _case("classification", "Classify insufficient evidence after bounded local requests are exhausted.", "insufficient_evidence", None, "none", "accepted incident", "dp_classified_with_request"),
    _case("classification", "Classify benign anomaly with benign support and no blocking gaps.", "benign_anomaly", None, "none", "accepted incident", "dp_classified_no_request"),
    _case("lease", "Lease conflict before handoff/state read performs zero ingest/request/classification writes.", "none", "lease_conflict", "lease_conflict", "pre-ingest", "dp_no_runtime_write"),
    _case("continuous", "Bounded continuous mode writes one heartbeat and stops at max_cycles without path discovery.", "none", None, "max_cycles_reached", "runtime termination", "dp_continuous_control"),
    _case("readiness", "Stale readiness stops finite loop before ingest.", "none", "readiness_stale", "readiness_stale", "runtime termination", "dp_continuous_control"),
    _case("handoff", "Stale handoff version stops finite loop before accepting the bundle.", "none", "handoff_version_stale", "handoff_version_stale", "runtime termination", "dp_continuous_control"),
    _case("signal", "SIGTERM before classification write and ledger CAS returns no classification.", "none", "signal_before_classification_unsafe", "sigterm", "runtime termination", "dp_signal_no_classification"),
    _case("recovery", "Crash after ingest intent recovers exactly once without duplicate atoms.", "insufficient_evidence", None, "none", "accepted incident", "dp_recovery_after_ingest_intent"),
    _case("recovery", "Crash after incident write recovers exactly once without duplicate incident state.", "confirmed_incident", None, "none", "accepted incident", "dp_recovery_after_incident_write"),
    _case("recovery", "Crash after request write reuses durable request bytes and does not re-execute the selection.", "confirmed_incident", None, "none", "accepted incident", "dp_recovery_after_request_write"),
    _case("recovery", "Crash after aborted_fail_closed classification write before ledger CAS advances that durable classification exactly once after successful CAS.", "aborted_fail_closed", None, "aborted_fail_closed", "accepted incident", "dp_recovery_after_classification_before_ledger"),
    _case("durability", "CAS predecessor conflict preserves prior ledger and cannot claim terminal classification.", "none", "ledger_cas_predecessor_mismatch", "cas_failure", "state rejection", "dp_no_runtime_write"),
    _case("resource", "Case-specific low measured resource limit trips before classification intent.", "none", "resource_limit_exceeded", "resource_exhausted", "state rejection", "dp_resource_preclassification_stop"),
)


def p137_release_case_matrix() -> list[dict[str, Any]]:
    if len(_ROWS) != 60:
        raise P137RunnerError("canonical_case_matrix_size_invalid")
    cases = []
    for ordinal, row in enumerate(_ROWS, start=1):
        case = {"case_id": f"p137-case-{ordinal:02d}", **deepcopy(row)}
        cases.append(case)
    return cases


def run_p137_release_matrix(
    output_dir: Path | str,
    *,
    canonical_matrix: Mapping[str, Any] | None = None,
    freeze_manifest: Mapping[str, Any] | None = None,
    runtime_factory: RuntimeFactory | None = None,
    precomputed_evidence: Mapping[str, Any] | None = None,
    source_bindings: Mapping[str, str] | None = None,
    final_implementation_review: Mapping[str, Any] | None = None,
    evaluator_activity: Mapping[str, int] | None = None,
    expected_profile_hash: str | None = None,
    expected_fixture_hash: str | None = None,
) -> dict[str, Any]:
    if precomputed_evidence is not None:
        raise P137RunnerError("release_matrix_final_path_is_frozen_only")
    if runtime_factory is not None or evaluator_activity is not None:
        raise P137RunnerError("release_matrix_final_path_is_frozen_only")
    if canonical_matrix is None or freeze_manifest is None:
        raise P137RunnerError("frozen_matrix_and_manifest_required")
    if source_bindings is None or final_implementation_review is None or expected_profile_hash is None or expected_fixture_hash is None:
        raise P137RunnerError("frozen_source_profile_fixture_and_final_review_required")
    try:
        review = validate_final_implementation_review(final_implementation_review, expected_source_hashes=source_bindings)
        return assemble_p137_release_evidence_from_frozen_matrix(
            canonical_matrix,
            freeze_manifest=freeze_manifest,
            final_implementation_review=review,
            expected_source_hashes=source_bindings,
            expected_profile_hash=expected_profile_hash,
            expected_fixture_hash=expected_fixture_hash,
        )
    except P137ReleaseEvidenceError as exc:
        raise P137RunnerError(f"p137_release_evidence_validation_failed:{exc}") from exc


def run_p137_preliminary_matrix(
    output_dir: Path | str,
    *,
    runtime_factory: RuntimeFactory | None,
    evaluator_activity: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Execute and freeze the matrix without claiming a qualified release."""

    if runtime_factory is None or not callable(runtime_factory):
        raise P137RunnerError("runtime_factory_required")
    started_wall = time.monotonic()
    started_self = resource.getrusage(resource.RUSAGE_SELF)
    started_children = resource.getrusage(resource.RUSAGE_CHILDREN)
    cases: list[dict[str, Any]] = []
    case_inputs: list[dict[str, Any]] = []
    expected_evaluator_overhead = _exact_evaluator_activity(
        evaluator_activity or zero_evaluator_activity(runner_invocation_count=1)
    )
    evaluator_totals = dict(expected_evaluator_overhead)
    for spec in p137_release_case_matrix():
        case_id = str(spec["case_id"])
        runtime = _mapping(runtime_factory(case_id), "runtime")
        case_inputs.append(_case_input_binding(case_id, runtime))
        evidence = _execute_case(spec, runtime, output_dir=Path(output_dir))
        observed_label = str(evidence["actual_label"])
        observed_error = str(evidence["actual_error"])
        observed_termination = str(evidence["termination_reason"])
        expected_error = str(spec["expected_error"] or "none")
        if observed_label != spec["expected_label"]:
            raise P137RunnerError(f"case_observed_label_mismatch:{case_id}:{observed_label}!={spec['expected_label']}")
        if observed_error != expected_error:
            raise P137RunnerError(f"case_observed_error_mismatch:{case_id}:{observed_error}!={expected_error}")
        if observed_termination != spec["termination_reason"]:
            raise P137RunnerError(f"case_observed_termination_mismatch:{case_id}:{observed_termination}!={spec['termination_reason']}")
        _merge(evaluator_totals, evidence["evaluator_activity"])
        case = {
            "case_id": case_id,
            "category": spec["category"],
            "semantic": spec["semantic"],
            "expected": "pass",
            "actual": "pass",
            "status": "passed",
            "expected_label": spec["expected_label"],
            "expected_error": spec["expected_error"],
            "termination_reason": spec["termination_reason"],
            "scope": spec["scope"],
            "delta_profile": spec["delta_profile"],
            "request_catalog_entry": spec["request_catalog_entry"],
            "provider_profile": spec["provider_profile"] or runtime.get("provider"),
            "evidence": evidence,
        }
        case["case_evidence_hash"] = stable_hash(case)
        cases.append(case)
    evaluator_case_totals = _sum_case_evaluator_activity(cases)
    evaluator_overhead = _counter_delta(evaluator_totals, evaluator_case_totals, "matrix_evaluator_activity_less_than_cases")
    if evaluator_overhead != expected_evaluator_overhead:
        raise P137RunnerError("matrix_evaluator_overhead_delta_profile_mismatch")
    resource_usage = _resource_usage(started_wall, started_self, started_children)
    resource_overhead = _exact_resource_usage(resource_usage)
    expected_resource_overhead = bounded_resource_usage(
        wall_time_ms=30_000,
        cpu_time_ms=15_000,
        child_cpu_time_ms=15_000,
        peak_memory_bytes=134_217_728,
        wall_limit_ms=30_000,
        cpu_limit_ms=15_000,
        peak_memory_limit_bytes=134_217_728,
    )
    if not _resource_within_budget(resource_overhead, expected_resource_overhead):
        raise P137RunnerError("matrix_resource_overhead_budget_exceeded")
    for case in cases:
        case["case_evidence_hash"] = stable_hash({key: item for key, item in case.items() if key != "case_evidence_hash"})
    case_config_bindings = [_case_config_binding(item) for item in case_inputs]
    return {
        "schema_version": PRELIMINARY_MATRIX_SCHEMA_VERSION,
        "status": "p137_preliminary_matrix_frozen",
        "cases": cases,
        "case_inputs": case_inputs,
        "evaluator_activity": evaluator_totals,
        "evaluator_overhead_activity": evaluator_overhead,
        "expected_evaluator_overhead_activity": expected_evaluator_overhead,
        "resource_usage": resource_usage,
        "resource_overhead_usage": resource_overhead,
        "expected_resource_overhead_usage": expected_resource_overhead,
        "matrix_hash": stable_hash(cases),
        "case_input_hash": stable_hash(case_inputs),
        "case_config_hash": stable_hash(case_config_bindings),
        "case_evidence_hash": stable_hash([case["case_evidence_hash"] for case in cases]),
    }


def _execute_case(spec: Mapping[str, Any], runtime: Mapping[str, Any], *, output_dir: Path) -> dict[str, Any]:
    handoff_bytes = _bytes(runtime.get("canonical_handoff_bundle_bytes"), "canonical_handoff_bundle_bytes")
    promotion_bytes = [_bytes(item, "canonical_promotion_bytes") for item in _sequence(runtime.get("canonical_promotion_bytes"), "canonical_promotion_bytes")]
    observed = _observe_case(spec, runtime)
    runtime_activity = _exact_runtime_activity(observed.get("runtime_activity"))
    expected_runtime_activity = _exact_runtime_activity(runtime.get("expected_runtime_activity"))
    if runtime_activity != expected_runtime_activity:
        raise P137RunnerError(f"observed_runtime_activity_delta_mismatch:{spec['case_id']}")
    forbidden = _exact_forbidden_authority(observed.get("forbidden_authority") or zero_forbidden_authority())
    evaluator = _exact_evaluator_activity(observed.get("evaluator_activity") or zero_evaluator_activity())
    expected_evaluator = _exact_evaluator_activity(runtime.get("expected_evaluator_activity"))
    if evaluator != expected_evaluator:
        raise P137RunnerError(f"observed_evaluator_activity_delta_mismatch:{spec['case_id']}")
    resources = _exact_resource_usage(observed.get("resource_usage") or _zero_resource_usage())
    expected_resources = _exact_resource_usage(runtime.get("expected_resource_usage"))
    if resources != expected_resources:
        raise P137RunnerError(f"observed_resource_usage_delta_mismatch:{spec['case_id']}")
    return {
        "executed": True,
        "observation_source": observed["source"],
        "api_calls": observed["api_calls"],
        "output_dir_ref_hash": stable_hash(str(output_dir)),
        "actual_label": observed["actual_label"],
        "actual_error": observed["actual_error"],
        "termination_reason": observed["termination_reason"],
        "scope": spec["scope"],
        "delta_profile": spec["delta_profile"],
        "provider_profile": spec["provider_profile"] or runtime.get("provider"),
        "request_catalog_entry": spec["request_catalog_entry"],
        "request_record_hashes": observed.get("request_record_hashes", []),
        "probe_invocation": observed.get("probe_invocation"),
        "probe_exception": observed.get("probe_exception"),
        "handoff_bundle_hash": stable_hash(handoff_bytes.hex()),
        "promotion_record_count": len(promotion_bytes),
        "runtime_activity": runtime_activity,
        "expected_runtime_activity": expected_runtime_activity,
        "forbidden_authority": forbidden,
        "expected_forbidden_authority": zero_forbidden_authority(),
        "evaluator_activity": evaluator,
        "expected_evaluator_activity": expected_evaluator,
        "resource_usage": resources,
        "expected_resource_usage": expected_resources,
    }


def _observe_case(spec: Mapping[str, Any], runtime: Mapping[str, Any]) -> dict[str, Any]:
    if spec.get("request_catalog_entry") is not None:
        return _observe_request_case(spec, runtime)
    category = str(spec["category"])
    if category in {"ingest", "correlation", "hypothesis", "classification"}:
        return _observe_triage_case(spec, runtime)
    if category == "budget":
        return _observe_triage_case(spec, runtime)
    return _observe_probe_case(spec, runtime)


def _observe_request_case(spec: Mapping[str, Any], runtime: Mapping[str, Any]) -> dict[str, Any]:
    atoms = _sequence(runtime.get("atoms"), "atoms")
    catalog_name = str(spec["request_catalog_entry"])
    parameters_by_catalog = _mapping(runtime.get("request_parameters_by_catalog"), "request_parameters_by_catalog")
    parameters = _mapping(parameters_by_catalog.get(catalog_name), f"request_parameters:{catalog_name}")
    result = execute_evidence_request(
        incident_id=str(runtime.get("incident_id", "p137-runner-incident")),
        incident_hash=_hash_text(runtime.get("incident_hash") or stable_hash({"incident": str(spec["case_id"])}), "incident_hash"),
        request_sequence=int(runtime.get("request_sequence", 1)),
        catalog_name=catalog_name,
        parameters=parameters,
        atoms=[_mapping(atom, "atom") for atom in atoms],
        budget=build_request_budget(_mapping(runtime.get("request_budget"), "request_budget") if runtime.get("request_budget") is not None else None),
        previous_request_hash=runtime.get("previous_request_hash"),
    )
    observed = _observe_triage_case(spec, runtime)
    observed["source"] = f"p137_requests.execute_evidence_request+{observed['source']}"
    observed["api_calls"] = [
        "p137_requests.execute_evidence_request",
        *observed["api_calls"],
    ]
    observed["request_record_hashes"] = [str(result.record["request_hash"])]
    runtime_activity = _exact_runtime_activity(observed.get("runtime_activity"))
    if runtime_activity["evidence_request_write_count"] < 1 or runtime_activity["attempted_request_hash_write_count"] < 1:
        raise P137RunnerError("request_case_missing_observed_durable_request")
    return observed


def _observe_triage_case(spec: Mapping[str, Any], runtime: Mapping[str, Any]) -> dict[str, Any]:
    forced_failure = runtime.get("failure_probe")
    if isinstance(forced_failure, Mapping):
        label = derive_classification(
            [],
            accepted_incident=True,
            failure_code=str(forced_failure.get("failure_code", "runtime_failure")),
            classification_write_succeeded=bool(forced_failure.get("classification_write_succeeded")),
            ledger_cas_succeeded=bool(forced_failure.get("ledger_cas_succeeded")),
        )
        observed = _observed(
            source="p137_classification.derive_classification.failure_probe",
            actual_label=label or "none",
            actual_error=str(forced_failure.get("actual_error", "none")),
            termination_reason=str(forced_failure.get("termination_reason", "none")),
            api_calls=["p137_classification.derive_classification"],
            runtime_activity=zero_runtime_activity(),
        )
        return _attach_runtime_probe(observed, spec, runtime)
    atoms = [_mapping(atom, "atom") for atom in _sequence(runtime.get("classification_atoms") or runtime.get("atoms"), "atoms")]
    correlation = correlate_incident_state(atoms, now=str(runtime.get("now", "2026-07-14T00:00:00Z")))
    incidents = _sequence(correlation.get("incidents"), "incidents")
    if not incidents:
        label = "none"
        api_calls = ["p137_correlation.correlate_incident_state"]
    else:
        incident = _mapping(incidents[0], "incident")
        ranking = rank_incident_hypotheses(incident, atoms, now=str(runtime.get("now", "2026-07-14T00:00:00Z")))
        hypotheses = [_mapping(item, "hypothesis") for item in _sequence(ranking.get("hypotheses"), "hypotheses")]
        label = derive_classification(
            hypotheses,
            accepted_incident=True,
            semantic_tie=len(_sequence(ranking.get("top_tie_hypothesis_hashes"), "top_tie_hypothesis_hashes")) > 1,
        )
        api_calls = [
            "p137_correlation.correlate_incident_state",
            "p137_hypotheses.rank_incident_hypotheses",
            "p137_classification.derive_classification",
        ]
    observed = _observed(
        source="+".join(api_calls),
        actual_label=label or "none",
        actual_error="none",
        termination_reason="none",
        api_calls=api_calls,
        runtime_activity=zero_runtime_activity(),
    )
    return _attach_runtime_probe(observed, spec, runtime)


def _attach_runtime_probe(observed: dict[str, Any], spec: Mapping[str, Any], runtime: Mapping[str, Any]) -> dict[str, Any]:
    probe = runtime.get("runtime_probe")
    if not callable(probe):
        raise P137RunnerError("runtime_evidence_probe_required")
    identity = _callable_identity(probe)
    try:
        raw = probe(spec=spec, runtime=runtime)
    except Exception as exc:
        raise P137RunnerError(f"runtime_evidence_probe_failed:{identity}:{type(exc).__name__}:{exc}") from exc
    result = _mapping(raw, "runtime_evidence_probe_result")
    actual_label = str(result.get("actual_label", "none"))
    actual_error = str(result.get("actual_error", "none"))
    termination_reason = str(result.get("termination_reason", "none"))
    if actual_label != observed["actual_label"]:
        raise P137RunnerError(f"component_runtime_label_mismatch:{spec['case_id']}:{observed['actual_label']}!={actual_label}")
    if actual_error != observed["actual_error"]:
        raise P137RunnerError(f"component_runtime_error_mismatch:{spec['case_id']}:{observed['actual_error']}!={actual_error}")
    if termination_reason != observed["termination_reason"]:
        raise P137RunnerError(
            f"component_runtime_termination_mismatch:{spec['case_id']}:{observed['termination_reason']}!={termination_reason}"
        )
    observed["runtime_activity"] = _exact_runtime_activity(result.get("runtime_activity"))
    probe_evaluator = _exact_evaluator_activity(result.get("evaluator_activity"))
    current_evaluator = _exact_evaluator_activity(observed.get("evaluator_activity"))
    _merge(current_evaluator, probe_evaluator)
    observed["evaluator_activity"] = current_evaluator
    probe_forbidden = _exact_forbidden_authority(result.get("forbidden_authority"))
    current_forbidden = _exact_forbidden_authority(observed.get("forbidden_authority"))
    _merge(current_forbidden, probe_forbidden)
    observed["forbidden_authority"] = _exact_forbidden_authority(current_forbidden)
    observed["source"] = f"{observed['source']}+{result.get('source', identity)}"
    observed["api_calls"] = sorted(
        {*observed["api_calls"], *(str(item) for item in _sequence(result.get("api_calls"), "runtime_probe_api_calls"))}
    )
    return observed


def _observe_probe_case(spec: Mapping[str, Any], runtime: Mapping[str, Any]) -> dict[str, Any]:
    probe = runtime.get("probe")
    if not callable(probe):
        raise P137RunnerError("observed_probe_must_be_callable")
    identity = _callable_identity(probe)
    try:
        raw_result = probe(spec=spec, runtime=runtime)
    except Exception as exc:
        raise P137RunnerError(f"observed_probe_callable_failed:{identity}:{type(exc).__name__}:{exc}") from exc
    result = _mapping(raw_result, "probe_result")
    exception = _mapping(result.get("exception", {"type": "none", "message": "none"}), "probe_exception")
    api_calls = [str(item) for item in _sequence(result.get("api_calls"), "api_calls")]
    if not api_calls:
        raise P137RunnerError("observed_probe_missing_api_calls")
    observed = _observed(
        source=str(result.get("source", identity)),
        actual_label=str(result.get("actual_label", "none")),
        actual_error=str(result.get("actual_error", "none")),
        termination_reason=str(result.get("termination_reason", "none")),
        api_calls=api_calls,
        runtime_activity=result.get("runtime_activity"),
        forbidden_authority=result.get("forbidden_authority"),
        evaluator_activity=result.get("evaluator_activity"),
    )
    observed["probe_invocation"] = {
        "callable": identity,
        "case_id": str(spec["case_id"]),
    }
    observed["probe_exception"] = {
        "type": str(exception.get("type", "none")),
        "message": str(exception.get("message", "none")),
    }
    return observed


def _observed(
    *,
    source: str,
    actual_label: str,
    actual_error: str,
    termination_reason: str,
    api_calls: list[str],
    runtime_activity: Any = None,
    forbidden_authority: Any = None,
    evaluator_activity: Any = None,
) -> dict[str, Any]:
    if actual_label not in {"confirmed_incident", "insufficient_evidence", "benign_anomaly", "aborted_fail_closed", "none"}:
        raise P137RunnerError("invalid_observed_label")
    if not source or not api_calls:
        raise P137RunnerError("invalid_observed_source")
    return {
        "source": source,
        "actual_label": actual_label,
        "actual_error": actual_error,
        "termination_reason": termination_reason,
        "api_calls": sorted(api_calls),
        "runtime_activity": _exact_runtime_activity(runtime_activity),
        "forbidden_authority": _exact_forbidden_authority(forbidden_authority or zero_forbidden_authority()),
        "evaluator_activity": _exact_evaluator_activity(evaluator_activity or zero_evaluator_activity()),
    }


def _callable_identity(value: Callable[..., Any]) -> str:
    module = getattr(value, "__module__", type(value).__module__)
    qualname = getattr(value, "__qualname__", type(value).__qualname__)
    return f"{module}.{qualname}"


def _exact_runtime_activity(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping) or set(value) != set(zero_runtime_activity()):
        raise P137RunnerError("invalid_runtime_activity_schema")
    result: dict[str, int] = {}
    for key, item in value.items():
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            raise P137RunnerError("invalid_runtime_activity_schema")
        result[key] = item
    return result


def _exact_forbidden_authority(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping) or set(value) != set(zero_forbidden_authority()):
        raise P137RunnerError("invalid_forbidden_authority_schema")
    result: dict[str, int] = {}
    for key, item in value.items():
        if isinstance(item, bool) or not isinstance(item, int) or item != 0:
            raise P137RunnerError("invalid_forbidden_authority_schema")
        result[key] = item
    return result


def _resource_usage(started_wall: float, started_self: Any, started_children: Any) -> dict[str, int]:
    current_self = resource.getrusage(resource.RUSAGE_SELF)
    current_children = resource.getrusage(resource.RUSAGE_CHILDREN)
    wall_time_ms = max(0, int((time.monotonic() - started_wall) * 1000))
    cpu_time_ms = max(0, int(((current_self.ru_utime + current_self.ru_stime) - (started_self.ru_utime + started_self.ru_stime)) * 1000))
    child_cpu_time_ms = max(
        0,
        int(((current_children.ru_utime + current_children.ru_stime) - (started_children.ru_utime + started_children.ru_stime)) * 1000),
    )
    peak_memory_bytes = max(0, _normalized_peak_rss_bytes(current_self) - _normalized_peak_rss_bytes(started_self))
    return bounded_resource_usage(
        wall_time_ms=wall_time_ms,
        cpu_time_ms=cpu_time_ms,
        child_cpu_time_ms=child_cpu_time_ms,
        peak_memory_bytes=peak_memory_bytes,
        wall_limit_ms=30_000,
        cpu_limit_ms=15_000,
        peak_memory_limit_bytes=134_217_728,
    )


def _zero_resource_usage() -> dict[str, int]:
    return bounded_resource_usage(
        wall_time_ms=0,
        cpu_time_ms=0,
        child_cpu_time_ms=0,
        peak_memory_bytes=0,
        wall_limit_ms=0,
        cpu_limit_ms=0,
        peak_memory_limit_bytes=0,
    )


def _sum_case_evaluator_activity(cases: list[dict[str, Any]]) -> dict[str, int]:
    case_totals = zero_evaluator_activity()
    for case in cases:
        evidence = _mapping(case.get("evidence"), "case_evidence")
        _merge(case_totals, _exact_evaluator_activity(evidence.get("evaluator_activity")))
    return case_totals


def _counter_delta(total: Mapping[str, int], subtotal: Mapping[str, int], error: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for key, value in total.items():
        delta = value - subtotal[key]
        if delta < 0:
            raise P137RunnerError(error)
        result[key] = delta
    return result


def _case_input_binding(case_id: str, runtime: Mapping[str, Any]) -> dict[str, Any]:
    config = _mapping(runtime.get("effective_p137_config"), "effective_p137_config")
    try:
        validate_triage_agent_config(config)
    except P137ContractError as exc:
        raise P137RunnerError(f"invalid_effective_p137_config:{case_id}:{exc}") from exc
    bindings = {
        str(key): _input_descriptor(value)
        for key, value in sorted(runtime.items())
        if key != "fixture_root"
    }
    return {
        "case_id": case_id,
        "schema_version": "p137.case_input_binding.v2",
        "bindings": bindings,
        "runtime_input_hash": stable_hash(bindings),
    }


def _case_config_binding(case_input: Mapping[str, Any]) -> dict[str, str]:
    bindings = _mapping(case_input.get("bindings"), "case_input_bindings")
    config = _mapping(bindings.get("effective_p137_config"), "effective_p137_config")
    return {
        "case_id": str(case_input.get("case_id")),
        "config_hash": _hash_text(config.get("config_hash"), "effective_p137_config_hash"),
    }


def _input_descriptor(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"kind": "bytes", "byte_count": len(value), "content_hash": stable_hash(value.hex())}
    if isinstance(value, Path):
        return {"kind": "path", "path_ref_hash": stable_hash(value.as_posix()), "name": value.name}
    if callable(value):
        state = getattr(value, "__dict__", {})
        return {
            "kind": "callable",
            "identity": _callable_identity(value),
            "state": _input_descriptor(state),
        }
    if isinstance(value, Mapping):
        return {
            str(key): _input_descriptor(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_input_descriptor(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise P137RunnerError(f"unsupported_case_input_type:{type(value).__name__}")


def _resource_within_budget(observed: Mapping[str, int], budget: Mapping[str, int]) -> bool:
    limits = ("wall_limit_ms", "cpu_limit_ms", "peak_memory_limit_bytes")
    return (
        observed["wall_time_ms"] <= budget["wall_time_ms"]
        and observed["cpu_time_ms"] + observed["child_cpu_time_ms"] <= budget["cpu_limit_ms"]
        and observed["peak_memory_bytes"] <= budget["peak_memory_bytes"]
        and all(observed[key] == budget[key] for key in limits)
    )


def _normalized_peak_rss_bytes(usage: Any) -> int:
    value = int(getattr(usage, "ru_maxrss", 0))
    return value if value > 10_000_000 else value * 1024


def _exact_evaluator_activity(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping) or set(value) != set(zero_evaluator_activity()):
        raise P137RunnerError("invalid_evaluator_activity_schema")
    result: dict[str, int] = {}
    for key, item in value.items():
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            raise P137RunnerError("invalid_evaluator_activity_schema")
        result[key] = item
    return result


def _exact_resource_usage(value: Any) -> dict[str, int]:
    template = bounded_resource_usage(wall_limit_ms=30_000, cpu_limit_ms=15_000, peak_memory_limit_bytes=134_217_728)
    if not isinstance(value, Mapping) or set(value) != set(template):
        raise P137RunnerError("invalid_resource_usage_schema")
    result: dict[str, int] = {}
    for key, item in value.items():
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            raise P137RunnerError("invalid_resource_usage_schema")
        result[key] = item
    return result


def _merge(target: dict[str, int], source: Mapping[str, int]) -> None:
    for key, item in source.items():
        target[key] += item


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise P137RunnerError(f"invalid_{label}")
    return value


def _sequence(value: Any, label: str) -> list[Any]:
    if not isinstance(value, (list, tuple)):
        raise P137RunnerError(f"invalid_{label}")
    return list(value)


def _bytes(value: Any, label: str) -> bytes:
    if not isinstance(value, bytes) or not value:
        raise P137RunnerError(f"invalid_{label}")
    return value


def _hash_text(value: Any, label: str) -> str:
    text = str(value)
    if not text.startswith("sha256:") or len(text) != 71:
        raise P137RunnerError(f"invalid_{label}")
    return text


__all__ = [
    "P137RunnerError",
    "p137_release_case_matrix",
    "run_p137_preliminary_matrix",
    "run_p137_release_matrix",
    "_normalized_peak_rss_bytes",
    "_resource_usage",
]
