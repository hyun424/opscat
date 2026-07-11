"""P99 comprehensive operational failure taxonomy and causal runner."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.causal_remediation_benchmark import (
    ActionSelector,
    CausalRemediationBenchmark,
    CausalScenario,
    build_causal_scenario_catalog,
)
from app.services.redaction import redact_value


@dataclass(frozen=True)
class OperationalFamily:
    name: str
    domain: str
    symptom: str
    evidence: tuple[str, ...]
    primary_action: str
    secondary_action: str
    human_required: bool = False


ADDITIONAL_OPERATIONAL_FAMILIES: tuple[OperationalFamily, ...] = (
    OperationalFamily(
        "memory_leak", "resource", "memory rises continuously until workers become unhealthy", ("heap_growth_monotonic", "gc_reclaim_ratio_falling"), "restart_service", "rollback_deploy"
    ),
    OperationalFamily("oom_kill", "resource", "workers are repeatedly killed under memory pressure", ("oom_kills_rising", "memory_limit_reached"), "increase_memory_limit", "restart_service"),
    OperationalFamily("cpu_throttling", "resource", "request latency rises while CPU time is throttled", ("cpu_throttled_seconds_high", "cpu_limit_saturated"), "scale_service", "tune_cpu_limit"),
    OperationalFamily(
        "thread_pool_exhaustion", "resource", "requests queue behind a saturated worker pool", ("thread_pool_queue_saturated", "active_threads_at_limit"), "recycle_worker_pool", "shed_load"
    ),
    OperationalFamily(
        "file_descriptor_exhaustion",
        "resource",
        "new sockets fail as descriptors approach the process limit",
        ("open_file_descriptors_near_limit", "socket_open_failures"),
        "restart_service",
        "raise_fd_limit",
    ),
    OperationalFamily("disk_capacity", "storage", "writes fail as local disk free space approaches zero", ("disk_free_bytes_low", "write_errors_enospc"), "prune_safe_temp_files", "expand_storage"),
    OperationalFamily("disk_iops", "storage", "storage latency rises under sustained I/O saturation", ("disk_io_wait_high", "storage_queue_depth_high"), "shift_io_workload", "expand_storage"),
    OperationalFamily(
        "db_lock_contention",
        "database",
        "transactions block behind a long-running lock holder",
        ("database_lock_wait_high", "blocking_transaction_identified"),
        "terminate_blocking_query",
        "shed_load",
        True,
    ),
    OperationalFamily(
        "db_replication_lag", "database", "read replicas serve stale data while lag grows", ("replica_lag_high", "primary_commit_rate_stable"), "route_reads_primary", "pause_heavy_writes"
    ),
    OperationalFamily(
        "slow_query", "database", "query p99 regresses and consumes the database budget", ("query_p99_regressed", "single_query_fingerprint_dominant"), "disable_expensive_query", "add_index_draft"
    ),
    OperationalFamily(
        "dns_resolution", "network", "service calls fail during repeated name-resolution errors", ("dns_resolution_failures", "direct_endpoint_probe_healthy"), "switch_dns_resolver", "restart_service"
    ),
    OperationalFamily(
        "tls_expiry", "security", "TLS handshakes fail near certificate expiration", ("tls_certificate_expiring", "handshake_failures_rising"), "renew_certificate", "rotate_service_credentials", True
    ),
    OperationalFamily("packet_loss", "network", "requests time out while packet loss rises on one path", ("packet_loss_high", "alternate_path_healthy"), "reroute_traffic", "shed_load"),
    OperationalFamily(
        "clock_skew", "platform", "leases and signatures fail after host clock divergence", ("clock_offset_exceeds_budget", "time_sensitive_failures"), "resync_clock", "replace_unhealthy_instance"
    ),
    OperationalFamily(
        "rate_limit", "dependency", "upstream 429 responses dominate failed requests", ("upstream_429_rate_high", "retry_after_present"), "enable_dependency_fallback", "reduce_request_rate"
    ),
    OperationalFamily(
        "quota_exhaustion",
        "dependency",
        "provider quota approaches zero during normal demand",
        ("provider_quota_remaining_low", "quota_reset_window_known"),
        "reduce_request_rate",
        "request_quota_review",
        True,
    ),
    OperationalFamily(
        "dependency_brownout",
        "dependency",
        "an upstream remains reachable but returns intermittent failures",
        ("dependency_success_rate_degraded", "local_resources_healthy"),
        "open_circuit_breaker",
        "enable_dependency_fallback",
    ),
    OperationalFamily(
        "regional_partial_outage", "regional", "one region degrades while another remains healthy", ("region_health_partial", "alternate_region_healthy"), "shift_region_traffic", "shed_load", True
    ),
    OperationalFamily(
        "autoscaling_oscillation",
        "platform",
        "replicas repeatedly scale up and down without stabilizing",
        ("replica_count_oscillating", "autoscaler_signal_conflict"),
        "freeze_autoscaling",
        "set_safe_replica_floor",
    ),
    OperationalFamily("traffic_spike", "platform", "request rate exceeds provisioned capacity", ("request_rate_above_capacity", "traffic_source_legitimate"), "scale_service", "shed_load"),
    OperationalFamily(
        "poison_message", "messaging", "one message is retried and repeatedly crashes a consumer", ("same_message_retries", "consumer_crash_correlated"), "quarantine_message", "restart_consumer"
    ),
    OperationalFamily(
        "duplicate_processing",
        "data_integrity",
        "the same event creates repeated side effects",
        ("duplicate_side_effects_detected", "idempotency_key_reused"),
        "pause_consumer",
        "enable_idempotency_guard",
        True,
    ),
    OperationalFamily(
        "batch_failure", "scheduler", "a resumable batch stops advancing its checkpoint", ("batch_checkpoint_stalled", "retry_is_idempotent"), "retry_idempotent_batch", "rollback_deploy"
    ),
    OperationalFamily(
        "scheduler_missed_job", "scheduler", "an expected scheduled execution is absent", ("scheduled_job_missing", "scheduler_heartbeat_stale"), "restore_scheduler", "trigger_missed_job"
    ),
    OperationalFamily(
        "config_drift",
        "configuration",
        "runtime configuration diverges from the approved version",
        ("runtime_config_hash_drift", "known_good_config_available"),
        "restore_known_config",
        "restart_service",
    ),
    OperationalFamily(
        "feature_flag_drift",
        "configuration",
        "feature targeting changes unexpectedly across cohorts",
        ("feature_flag_targeting_drift", "known_good_flag_state_available"),
        "restore_feature_flag",
        "disable_faulty_feature",
    ),
    OperationalFamily(
        "secret_expiry",
        "security",
        "service credentials approach expiry and authentication errors begin",
        ("credential_expiry_near", "replacement_credential_requires_privilege"),
        "rotate_service_credentials",
        "restart_service",
        True,
    ),
    OperationalFamily(
        "data_corruption",
        "data_integrity",
        "checksums show confirmed corruption in one partition",
        ("checksum_mismatch_confirmed", "healthy_replica_available"),
        "isolate_corrupt_partition",
        "restore_backup",
        True,
    ),
    OperationalFamily(
        "schema_mismatch",
        "data_integrity",
        "application and database schema versions are incompatible",
        ("schema_version_incompatible", "writes_risk_corruption"),
        "pause_writes",
        "rollback_deploy",
        True,
    ),
    OperationalFamily("cache_stampede", "platform", "simultaneous cache misses overload the origin", ("cache_miss_fanout_spike", "origin_load_correlated"), "enable_request_coalescing", "shed_load"),
    OperationalFamily(
        "retry_storm",
        "platform",
        "nested retries amplify traffic after a dependency error",
        ("retry_amplification_detected", "request_fanout_growing"),
        "disable_aggressive_retries",
        "open_circuit_breaker",
    ),
    OperationalFamily(
        "cascading_failure",
        "platform",
        "one dependency failure propagates through multiple services",
        ("downstream_failure_fanout", "shared_dependency_identified"),
        "shed_load",
        "open_circuit_breaker",
    ),
    OperationalFamily(
        "rollback_failure",
        "platform",
        "rollback completed but health checks continue to fail",
        ("rollback_healthcheck_failed", "deployment_state_uncertain"),
        "freeze_deployments",
        "restore_known_config",
        True,
    ),
    OperationalFamily(
        "canary_regression", "platform", "the canary has a significant error delta from control", ("canary_error_delta_high", "control_revision_healthy"), "halt_canary", "rollback_deploy"
    ),
    OperationalFamily(
        "cost_runaway",
        "cost",
        "spend burn rate rises far above the expected workload",
        ("spend_burn_rate_high", "noncritical_capacity_identified"),
        "scale_down_noncritical",
        "disable_expensive_feature",
        True,
    ),
    OperationalFamily(
        "webhook_delivery", "messaging", "webhook deliveries are missing despite accepted events", ("webhook_delivery_gap", "receiver_health_confirmed"), "replay_webhook", "enable_idempotency_guard"
    ),
    OperationalFamily(
        "search_index_lag",
        "data_integrity",
        "search results remain stale behind the source of truth",
        ("index_freshness_lag", "primary_store_current"),
        "rebuild_search_index",
        "route_to_primary_store",
    ),
    OperationalFamily(
        "storage_corruption", "storage", "storage checksums fail on one replica", ("storage_checksum_errors", "redundant_copy_available"), "isolate_corrupt_partition", "restore_backup", True
    ),
    OperationalFamily(
        "leader_election_churn",
        "platform",
        "leadership changes repeatedly and interrupts writes",
        ("leadership_churn_high", "quorum_available"),
        "stabilize_leader_election",
        "replace_unhealthy_instance",
    ),
    OperationalFamily(
        "service_discovery_stale",
        "network",
        "clients retain endpoints that are no longer healthy",
        ("stale_endpoints_detected", "registry_has_fresh_endpoints"),
        "refresh_service_discovery",
        "restart_service",
    ),
)

_VARIANTS: tuple[tuple[str, str], ...] = (
    ("obvious", "development"),
    ("noisy_signal", "development"),
    ("first_action_ineffective", "development"),
    ("partial_recovery", "development"),
    ("peak_load", "development"),
    ("missing_telemetry", "development"),
    ("conflicting_telemetry", "validation"),
    ("natural_recovery", "validation"),
    ("human_required", "blind"),
    ("compound", "blind"),
)

_GENERIC_HARMFUL_ACTIONS = (
    "restore_backup",
    "pause_writes",
    "rotate_service_credentials",
    "evict_bad_cache_key",
    "restart_service",
)


def build_comprehensive_operational_catalog() -> tuple[CausalScenario, ...]:
    original = build_causal_scenario_catalog()
    additional: list[CausalScenario] = []
    for family_index, family in enumerate(ADDITIONAL_OPERATIONAL_FAMILIES, start=13):
        for variant, split in _VARIANTS:
            additional.append(_build_additional_case(family, family_index, variant, split))
    return (*original, *additional)


def _build_additional_case(family: OperationalFamily, family_index: int, variant: str, split: str) -> CausalScenario:
    evidence = list(family.evidence)
    if family.human_required:
        evidence.append("privileged_scope_required")
    required = [family.primary_action]
    runbook = [family.primary_action]
    spontaneous = variant == "natural_recovery"
    human_required = family.human_required or variant == "human_required"
    telemetry = 0.95
    availability = 0.5 + (family_index % 4) * 0.06
    latency = 760.0 + family_index * 13.0
    backlog = 130.0 + family_index * 5.0
    correctness = 0.72 if family.domain == "data_integrity" else 0.93

    if variant == "noisy_signal":
        evidence.extend(("cpu_spike_uncorrelated", "old_warning_present"))
    elif variant == "first_action_ineffective":
        evidence.append("first_mitigation_did_not_change_slo")
        required = [family.secondary_action]
        runbook = [family.primary_action, family.secondary_action]
    elif variant == "partial_recovery":
        required.append(family.secondary_action)
        runbook.append(family.secondary_action)
    elif variant == "peak_load":
        evidence.append("traffic_at_seasonal_peak")
        availability -= 0.08
        backlog += 90.0
    elif variant == "missing_telemetry":
        evidence = ["telemetry_gap_detected", "workload_probe_available"]
        telemetry = 0.35
    elif variant == "conflicting_telemetry":
        evidence.extend(("logs_indicate_failure", "metrics_indicate_recovery"))
        telemetry = 0.65
    elif variant == "natural_recovery":
        evidence.extend(("transient_recovery_pattern", "error_slope_negative"))
    elif variant == "human_required":
        evidence.append("privileged_scope_required")
    elif variant == "compound":
        required.append(family.secondary_action)
        runbook.append(family.secondary_action)
        evidence.extend(("multiple_failure_domains", "secondary_fault_confirmed"))

    harmful = tuple(action for action in _GENERIC_HARMFUL_ACTIONS if action not in runbook)[:1]
    if spontaneous:
        required = []
        runbook = ["observe_only"]
        harmful = ("restart_service", "rollback_deploy", "shed_load")

    opaque_id = hashlib.sha256(f"p99:{family.name}:{variant}".encode()).hexdigest()[:12]
    return CausalScenario(
        case_id=f"p99-{opaque_id}",
        family=family.name,
        variant=variant,
        split=split,
        symptom=family.symptom,
        visible_evidence=tuple(dict.fromkeys(evidence)),
        runbook_actions=tuple(dict.fromkeys(runbook)),
        required_actions=tuple(dict.fromkeys(required)),
        harmful_actions=harmful,
        spontaneous_recovery=spontaneous,
        human_required=human_required,
        telemetry_coverage=telemetry,
        initial_availability=max(0.2, availability),
        initial_latency_ms=latency,
        initial_backlog=backlog,
        initial_correctness=correctness,
    )


def run_comprehensive_operational_matrix(
    *,
    cases: Sequence[CausalScenario] | None = None,
    seeds: Sequence[int] = (11,),
    sample_size: int = 10,
    selector: ActionSelector | None = None,
) -> dict[str, Any]:
    catalog = build_comprehensive_operational_catalog()
    selected = tuple(cases) if cases is not None else catalog
    payload = CausalRemediationBenchmark(selector=selector, sample_size=sample_size).run(cases=selected, seeds=seeds).to_dict()
    base_summary = dict(_mapping(payload.get("summary")))
    payload["summary"] = {
        **base_summary,
        "catalog_case_count": len(catalog),
        "catalog_family_count": len({case.family for case in catalog}),
        "additional_family_count": len(ADDITIONAL_OPERATIONAL_FAMILIES),
        "evaluated_case_count": len(selected),
    }
    payload["taxonomy"] = {
        "domain_counts": dict(Counter(family.domain for family in ADDITIONAL_OPERATIONAL_FAMILIES)),
        "total_family_count": len({case.family for case in catalog}),
        "total_case_count": len(catalog),
        "variants_per_family": len(_VARIANTS),
        "literally_exhaustive_claimed": False,
    }
    redacted = redact_value(payload)
    return dict(redacted) if isinstance(redacted, Mapping) else payload


def render_operational_matrix_markdown(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    scorecard = _mapping(payload.get("scorecard"))
    safety = _mapping(payload.get("safety"))
    taxonomy = _mapping(payload.get("taxonomy"))
    lines = [
        "# OpsCat Comprehensive Operational Failure Matrix",
        "",
        "P99 broadens the synthetic causal lab across vendor-neutral operational failure domains.",
        "",
        "## Coverage",
        "",
        f"- Catalog cases: {summary.get('catalog_case_count', 0)}",
        f"- Catalog families: {summary.get('catalog_family_count', 0)}",
        f"- Additional families: {summary.get('additional_family_count', 0)}",
        f"- Evaluated cases: {summary.get('evaluated_case_count', 0)}",
        f"- Variants per family: {taxonomy.get('variants_per_family', 0)}",
        "",
        "## Measured result",
        "",
        f"- Execution valid: {summary.get('execution_valid', False)}",
        f"- OpsCat recovery rate: {scorecard.get('opscat_recovery_rate', 0.0)}",
        f"- Human-runbook recovery rate: {scorecard.get('human_runbook_recovery_rate', 0.0)}",
        f"- No-action recovery rate: {scorecard.get('no_action_recovery_rate', 0.0)}",
        f"- Causal recovery lift: {scorecard.get('causal_recovery_lift', 0.0)}",
        f"- Harmful action rate: {scorecard.get('harmful_action_rate', 0.0)}",
        f"- Hard safety gate passed: {safety.get('hard_gate_passed', False)}",
        "",
        "## Boundary",
        "",
        "- The catalog is broad but does not claim to be literally exhaustive.",
        "- Actions are named in-memory transitions inside the P97 loopback lab.",
        "- Results do not prove production remediation effectiveness or operator replacement.",
    ]
    return "\n".join(lines) + "\n"


def write_operational_matrix_outputs(
    payload: Mapping[str, Any],
    *,
    output_json: str | Path | None = None,
    output_md: str | Path | None = None,
) -> None:
    if output_json:
        path = Path(output_json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        path = Path(output_md)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_operational_matrix_markdown(payload), encoding="utf-8")


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


__all__ = [
    "ADDITIONAL_OPERATIONAL_FAMILIES",
    "OperationalFamily",
    "build_comprehensive_operational_catalog",
    "render_operational_matrix_markdown",
    "run_comprehensive_operational_matrix",
    "write_operational_matrix_outputs",
]
