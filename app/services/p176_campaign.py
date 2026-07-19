"""Deterministic P176 multi-service staging campaign generator."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p176_action_eligibility import ELIGIBLE_ACTION_BY_FAMILY, ELIGIBLE_SERVICES_BY_FAMILY
from app.services.p176_contracts import (
    CAMPAIGN_SCHEMA_VERSION,
    DENOMINATOR_FIELDS,
    EPISODE_SCHEMA_VERSION,
    FAULT_FAMILY_FIELDS,
    HEALTHY_WINDOW_SCHEMA_VERSION,
    SERVICE_FIELDS,
    P176ContractError,
    validate_campaign_payload,
)

P176_CAMPAIGN_ID = "p176-deterministic-multi-service-staging-v1"
P176_CAMPAIGN_SEED = "p176-seed-2026-07-18-v1"

PRIMARY_LAYERS = ("api", "worker", "database", "cache_queue", "deployment", "network", "dependency")
CORE_FAMILY_LAYER_DISTRIBUTION = (5, 5, 4, 4, 4, 4, 4)
SEVERITIES = ("P0", "P1", "P2", "P3")
TRAFFIC_SHAPES = ("steady", "bursty", "batch_queue")
TELEMETRY_CLASSES = (
    "metrics",
    "logs",
    "traces",
    "deploy_history",
    "host_state",
    "container_state",
    "topology",
    "dependency_health",
)
CROSS_SERVICE_PAIR_CLASSES = ("north_south_api", "sync_downstream", "async_queue", "shared_dependency")

SERVICES: tuple[dict[str, Any], ...] = (
    {
        "service_id": "web-gateway",
        "criticality_tier": "tier0",
        "ownership_domain": "experience",
        "independently_deployable": True,
        "depends_on": ["checkout-api", "catalog-api"],
    },
    {
        "service_id": "checkout-api",
        "criticality_tier": "tier0",
        "ownership_domain": "commerce",
        "independently_deployable": True,
        "depends_on": ["order-worker", "postgres-db", "redis-cache"],
    },
    {
        "service_id": "catalog-api",
        "criticality_tier": "tier1",
        "ownership_domain": "commerce",
        "independently_deployable": True,
        "depends_on": ["postgres-db", "redis-cache"],
    },
    {
        "service_id": "order-worker",
        "criticality_tier": "tier0",
        "ownership_domain": "platform",
        "independently_deployable": True,
        "depends_on": ["event-queue", "postgres-db"],
    },
    {
        "service_id": "event-queue",
        "criticality_tier": "tier1",
        "ownership_domain": "platform",
        "independently_deployable": True,
        "depends_on": ["notification-worker"],
    },
    {
        "service_id": "notification-worker",
        "criticality_tier": "tier2",
        "ownership_domain": "experience",
        "independently_deployable": True,
        "depends_on": [],
    },
    {
        "service_id": "postgres-db",
        "criticality_tier": "tier0",
        "ownership_domain": "platform",
        "independently_deployable": True,
        "depends_on": [],
    },
    {
        "service_id": "redis-cache",
        "criticality_tier": "tier1",
        "ownership_domain": "platform",
        "independently_deployable": True,
        "depends_on": [],
    },
)

_FAMILY_NAMES = (
    ("api", "http_5xx_spike"),
    ("api", "request_timeout_regression"),
    ("api", "schema_contract_rejection"),
    ("api", "authz_dependency_denial"),
    ("api", "idempotency_key_conflict"),
    ("worker", "retry_storm"),
    ("worker", "job_handler_exception"),
    ("worker", "dead_letter_growth"),
    ("worker", "scheduler_lag"),
    ("worker", "partial_batch_commit"),
    ("database", "connection_pool_exhaustion"),
    ("database", "lock_wait_saturation"),
    ("database", "replica_lag"),
    ("database", "query_plan_regression"),
    ("cache_queue", "cache_hot_key"),
    ("cache_queue", "queue_backlog"),
    ("cache_queue", "message_visibility_timeout"),
    ("cache_queue", "cache_eviction_storm"),
    ("deployment", "bad_config_rollout"),
    ("deployment", "image_pull_backoff"),
    ("deployment", "canary_error_regression"),
    ("deployment", "feature_flag_mismatch"),
    ("network", "packet_loss"),
    ("network", "dns_resolution_failure"),
    ("network", "tls_handshake_regression"),
    ("network", "egress_rate_limit"),
    ("dependency", "third_party_latency"),
    ("dependency", "payment_provider_5xx"),
    ("dependency", "object_store_throttle"),
    ("dependency", "webhook_delivery_delay"),
)


def generate_p176_campaign() -> dict[str, Any]:
    """Return the frozen P176 campaign as JSON-ready dict/list values."""

    topology = _build_topology()
    fault_families = _build_fault_families()
    episodes = _build_episodes(fault_families)
    healthy_windows = _build_healthy_windows()
    campaign: dict[str, Any] = {
        "schema_version": CAMPAIGN_SCHEMA_VERSION,
        "campaign_id": P176_CAMPAIGN_ID,
        "seed": P176_CAMPAIGN_SEED,
        "topology": topology,
        "fault_families": fault_families,
        "episodes": episodes,
        "healthy_windows": healthy_windows,
        "denominators": _build_denominators(topology, fault_families, episodes, healthy_windows),
        "truth_payload_policy": "evaluator_only_hash_refs",
    }
    campaign["campaign_hash"] = stable_hash(campaign)
    return validate_p176_campaign(campaign)


def generate_p176_sealed_truth(campaign: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Build evaluator-only labels whose hashes are the campaign's opaque refs."""

    validated = validate_p176_campaign(campaign or generate_p176_campaign())
    family_by_id = {item["family_id"]: item for item in validated["fault_families"]}
    records = []
    for episode in validated["episodes"]:
        truth = _episode_truth_record(
            episode_id=episode["episode_id"],
            family_id=episode["family_id"],
            root_service_id=episode["service_id"],
            severity=episode["severity"],
            pair_class=episode["pair_class"],
            cross_service=episode["cross_service"],
            expected_routing=family_by_id[episode["family_id"]]["expected_routing"],
        )
        if stable_hash(truth) != episode["evaluator_truth_ref_hash"]:
            raise P176ContractError("sealed_truth_reference_mismatch")
        records.append({**truth, "truth_hash": stable_hash(truth)})
    artifact: dict[str, Any] = {
        "schema_version": "p176.evaluator_only_sealed_truth.v1",
        "campaign_hash": validated["campaign_hash"],
        "visibility": "evaluator_only",
        "records": records,
    }
    artifact["sealed_truth_hash"] = stable_hash(artifact)
    return artifact


def validate_p176_campaign(raw: Mapping[str, Any]) -> dict[str, Any]:
    campaign = validate_campaign_payload(raw)
    topology = _validate_topology(campaign["topology"])
    families = _validate_fault_families(campaign["fault_families"], topology)
    episodes = campaign["episodes"]
    windows = campaign["healthy_windows"]
    expected_denominators = _build_denominators(topology, families, episodes, windows)
    if campaign["denominators"] != expected_denominators:
        raise P176ContractError("campaign_denominators_invalid")
    _enforce_acceptance_denominators(expected_denominators)
    campaign["topology"] = topology
    campaign["fault_families"] = families
    campaign["denominators"] = expected_denominators
    return campaign


def _build_topology() -> list[dict[str, Any]]:
    return [deepcopy(service) for service in SERVICES]


def _build_fault_families() -> list[dict[str, Any]]:
    families: list[dict[str, Any]] = []
    for index, (layer, name) in enumerate(_FAMILY_NAMES):
        family_id = f"p176-family-{index + 1:02d}-{name}"
        service_a = SERVICES[index % len(SERVICES)]["service_id"]
        service_b = SERVICES[(index + 3) % len(SERVICES)]["service_id"]
        affected_service_ids = sorted(ELIGIBLE_SERVICES_BY_FAMILY.get(family_id, {service_a, service_b}))
        family = {
            "family_id": family_id,
            "primary_layer": layer,
            "affected_service_ids": affected_service_ids,
            "precursor_signal_refs": [f"{layer}.precursor.{name}"],
            "incident_signal_refs": [f"{layer}.incident.{name}"],
            "recovery_signal_refs": [f"{layer}.recovery.{name}"],
            "expected_routing": "fixed_action_eligible" if family_id in ELIGIBLE_ACTION_BY_FAMILY else "human_required",
            "promotion_core": True,
        }
        family["sealed_label_hash"] = stable_hash(
            {
                "family_id": family_id,
                "primary_layer": layer,
                "expected_routing": family["expected_routing"],
                "truth_policy": "sealed_evaluator_only",
            }
        )
        families.append(family)
    return families


def _build_episodes(fault_families: list[dict[str, Any]]) -> list[dict[str, Any]]:
    severity_schedule = (["P0"] * 40) + (["P1"] * 120) + (["P2"] * 240) + (["P3"] * 80)
    episodes: list[dict[str, Any]] = []
    cross_index = 0
    for family_index, family in enumerate(fault_families):
        for family_episode_index in range(16):
            index = family_index * 16 + family_episode_index
            service_index = index % len(SERVICES)
            service_id = SERVICES[service_index]["service_id"]
            cross_service = family_index < 12 and family_episode_index < 10
            pair_class = "none"
            source_service_id = service_id
            downstream_service_id = service_id
            if cross_service:
                pair_class = CROSS_SERVICE_PAIR_CLASSES[cross_index % len(CROSS_SERVICE_PAIR_CLASSES)]
                downstream_service_id = SERVICES[(service_index + 1 + (cross_index % 3)) % len(SERVICES)]["service_id"]
                if downstream_service_id == source_service_id:
                    downstream_service_id = SERVICES[(service_index + 1) % len(SERVICES)]["service_id"]
                cross_index += 1
            episode = {
                "schema_version": EPISODE_SCHEMA_VERSION,
                "episode_id": f"p176-episode-{index + 1:03d}",
                "index": index,
                "family_id": family["family_id"],
                "primary_layer": family["primary_layer"],
                "service_id": service_id,
                "severity": severity_schedule[index],
                "traffic_shape": TRAFFIC_SHAPES[index % len(TRAFFIC_SHAPES)],
                "cross_service": cross_service,
                "pair_class": pair_class,
                "source_service_id": source_service_id,
                "downstream_service_id": downstream_service_id,
                "agent_visible_evidence_refs": [
                    f"p176/redacted/{TELEMETRY_CLASSES[index % len(TELEMETRY_CLASSES)]}/{service_id}/{index:03d}",
                    f"p176/redacted/{family['primary_layer']}/{family['family_id']}/{family_episode_index:02d}",
                ],
                "evaluator_truth_ref_hash": stable_hash(
                    _episode_truth_record(
                        episode_id=f"p176-episode-{index + 1:03d}",
                        family_id=family["family_id"],
                        root_service_id=service_id,
                        severity=severity_schedule[index],
                        pair_class=pair_class,
                        cross_service=cross_service,
                        expected_routing=family["expected_routing"],
                    )
                ),
            }
            episode["episode_hash"] = stable_hash(episode)
            episodes.append(episode)
    return episodes


def _episode_truth_record(
    *,
    episode_id: str,
    family_id: str,
    root_service_id: str,
    severity: str,
    pair_class: str,
    cross_service: bool,
    expected_routing: str,
) -> dict[str, Any]:
    return {
        "schema_version": "p176.evaluator_truth_row.v1",
        "episode_id": episode_id,
        "family_id": family_id,
        "root_service_id": root_service_id,
        "severity": severity,
        "pair_class": pair_class,
        "collateral_expected": cross_service,
        "expected_routing": expected_routing,
        "expected_action": ELIGIBLE_ACTION_BY_FAMILY.get(family_id),
    }


def _build_healthy_windows() -> list[dict[str, Any]]:
    windows: list[dict[str, Any]] = []
    for index in range(240):
        service_id = SERVICES[index % len(SERVICES)]["service_id"]
        telemetry_class = TELEMETRY_CLASSES[index // 30]
        window = {
            "schema_version": HEALTHY_WINDOW_SCHEMA_VERSION,
            "window_id": f"p176-window-{index + 1:03d}",
            "index": index,
            "telemetry_class": telemetry_class,
            "service_id": service_id,
            "noisy": index % 2 == 1,
        }
        window["window_hash"] = stable_hash(window)
        windows.append(window)
    return windows


def _validate_topology(raw_topology: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_topology, list) or len(raw_topology) != 8:
        raise P176ContractError("invalid_topology_service_count")
    topology: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_service in raw_topology:
        if not isinstance(raw_service, Mapping) or set(raw_service) != SERVICE_FIELDS:
            raise P176ContractError("invalid_topology_service_fields")
        service = deepcopy(dict(raw_service))
        if type(service["service_id"]) is not str or not service["service_id"]:
            raise P176ContractError("invalid_service_id")
        if service["service_id"] in seen:
            raise P176ContractError(f"duplicate_service_id:{service['service_id']}")
        if type(service["criticality_tier"]) is not str or type(service["ownership_domain"]) is not str:
            raise P176ContractError("invalid_service_labels")
        if type(service["independently_deployable"]) is not bool or service["independently_deployable"] is not True:
            raise P176ContractError("service_not_independently_deployable")
        if not isinstance(service["depends_on"], list) or any(type(item) is not str or not item for item in service["depends_on"]):
            raise P176ContractError("invalid_service_dependencies")
        seen.add(service["service_id"])
        topology.append(service)
    for service in topology:
        if any(dependency not in seen or dependency == service["service_id"] for dependency in service["depends_on"]):
            raise P176ContractError("invalid_dependency_ref")
    return topology


def _validate_fault_families(raw_families: Any, topology: list[dict[str, Any]]) -> list[dict[str, Any]]:
    service_ids = {service["service_id"] for service in topology}
    if not isinstance(raw_families, list) or len(raw_families) != 30:
        raise P176ContractError("invalid_fault_family_count")
    families: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_family in raw_families:
        if not isinstance(raw_family, Mapping) or set(raw_family) != FAULT_FAMILY_FIELDS:
            raise P176ContractError("invalid_fault_family_fields")
        family = deepcopy(dict(raw_family))
        if type(family["family_id"]) is not str or family["family_id"] in seen:
            raise P176ContractError("duplicate_or_invalid_family_id")
        if family["primary_layer"] not in PRIMARY_LAYERS:
            raise P176ContractError("invalid_primary_layer")
        if family["promotion_core"] is not True:
            raise P176ContractError("non_core_family_in_campaign")
        affected = family["affected_service_ids"]
        if not isinstance(affected, list) or len(affected) < 2 or any(service_id not in service_ids for service_id in affected):
            raise P176ContractError("invalid_family_affected_services")
        for key in ("precursor_signal_refs", "incident_signal_refs", "recovery_signal_refs"):
            if not isinstance(family[key], list) or not family[key] or any(type(item) is not str or not item for item in family[key]):
                raise P176ContractError(f"invalid_family_signal_refs:{key}")
        if family["expected_routing"] not in {"fixed_action_eligible", "human_required"}:
            raise P176ContractError("invalid_expected_routing")
        if family["sealed_label_hash"] != stable_hash(
            {
                "family_id": family["family_id"],
                "primary_layer": family["primary_layer"],
                "expected_routing": family["expected_routing"],
                "truth_policy": "sealed_evaluator_only",
            }
        ):
            raise P176ContractError("sealed_family_label_hash_invalid")
        seen.add(family["family_id"])
        families.append(family)
    return families


def _build_denominators(
    topology: list[dict[str, Any]],
    fault_families: list[dict[str, Any]],
    episodes: list[dict[str, Any]],
    healthy_windows: list[dict[str, Any]],
) -> dict[str, Any]:
    layer_family_counts = Counter(family["primary_layer"] for family in fault_families)
    layer_episode_counts = Counter(episode["primary_layer"] for episode in episodes)
    severity_counts = Counter(episode["severity"] for episode in episodes)
    traffic_counts = Counter(episode["traffic_shape"] for episode in episodes)
    service_counts = Counter(episode["service_id"] for episode in episodes)
    cross_service_episodes = [episode for episode in episodes if episode["cross_service"] is True]
    pair_class_counts = Counter(episode["pair_class"] for episode in cross_service_episodes)
    window_counts = Counter(window["telemetry_class"] for window in healthy_windows)
    topology_stats = _topology_stats(topology)
    fault_episode_count = len(episodes)
    denominators: dict[str, Any] = {
        "fault_episode_count": fault_episode_count,
        "promotion_core_family_count": len(fault_families),
        "primary_layer_count": len(layer_family_counts),
        "core_families_by_primary_layer": {layer: layer_family_counts[layer] for layer in PRIMARY_LAYERS},
        "fault_episodes_by_primary_layer": {layer: layer_episode_counts[layer] for layer in PRIMARY_LAYERS},
        "severity_counts": {severity: severity_counts[severity] for severity in SEVERITIES},
        "traffic_shape_counts": {shape: traffic_counts[shape] for shape in TRAFFIC_SHAPES},
        "service_episode_counts": {service["service_id"]: service_counts[service["service_id"]] for service in topology},
        "cross_service_episode_count": len(cross_service_episodes),
        "cross_service_family_count": len({episode["family_id"] for episode in cross_service_episodes}),
        "cross_service_pair_class_count": len(pair_class_counts),
        "cross_service_pair_class_counts": {pair_class: pair_class_counts[pair_class] for pair_class in CROSS_SERVICE_PAIR_CLASSES},
        "cross_service_participating_service_count": len(
            {episode["source_service_id"] for episode in cross_service_episodes}
            | {episode["downstream_service_id"] for episode in cross_service_episodes}
        ),
        "healthy_noisy_window_count": len(healthy_windows),
        "healthy_windows_by_telemetry_class": {telemetry_class: window_counts[telemetry_class] for telemetry_class in TELEMETRY_CLASSES},
        **topology_stats,
        "min_core_families_per_primary_layer": min(layer_family_counts.values()),
        "min_fault_episodes_per_primary_layer": min(layer_episode_counts.values()),
        "min_episodes_per_cross_service_pair_class": min(pair_class_counts.values()),
        "max_core_family_fault_episode_share": max(Counter(episode["family_id"] for episode in episodes).values()) / fault_episode_count,
        "max_primary_layer_fault_episode_share": max(layer_episode_counts.values()) / fault_episode_count,
        "cross_service_fault_episode_share": len(cross_service_episodes) / fault_episode_count,
        "min_traffic_shape_fault_episode_share": min(traffic_counts.values()) / fault_episode_count,
        "max_service_fault_episode_share": max(service_counts.values()) / fault_episode_count,
        "min_healthy_windows_per_primary_telemetry_layer": min(window_counts.values()),
    }
    if set(denominators) != DENOMINATOR_FIELDS:
        raise P176ContractError("denominator_fields_invalid")
    return denominators


def _topology_stats(topology: list[dict[str, Any]]) -> dict[str, int]:
    dependencies = {service["service_id"]: list(service["depends_on"]) for service in topology}
    fan_in: dict[str, int] = defaultdict(int)
    for downstreams in dependencies.values():
        for downstream in downstreams:
            fan_in[downstream] += 1

    def depth(service_id: str, seen: frozenset[str]) -> int:
        downstreams = dependencies[service_id]
        if not downstreams:
            return 0
        return 1 + max(depth(downstream, seen | {service_id}) for downstream in downstreams if downstream not in seen)

    return {
        "independently_deployable_service_count": sum(1 for service in topology if service["independently_deployable"] is True),
        "criticality_tier_count": len({service["criticality_tier"] for service in topology}),
        "ownership_domain_count": len({service["ownership_domain"] for service in topology}),
        "dependency_graph_depth": max(depth(service["service_id"], frozenset()) for service in topology),
        "fan_out_node_count": sum(1 for service in topology if len(service["depends_on"]) >= 2),
        "fan_in_node_count": sum(1 for count in fan_in.values() if count >= 2),
    }


def _enforce_acceptance_denominators(denominators: dict[str, Any]) -> None:
    expected = {
        "fault_episode_count": 480,
        "promotion_core_family_count": 30,
        "primary_layer_count": 7,
        "cross_service_episode_count": 120,
        "healthy_noisy_window_count": 240,
        "independently_deployable_service_count": 8,
        "criticality_tier_count": 3,
        "ownership_domain_count": 3,
    }
    for key, value in expected.items():
        if denominators[key] != value:
            raise P176ContractError(f"p176_denominator_not_exact:{key}")
    if list(denominators["core_families_by_primary_layer"].values()) != list(CORE_FAMILY_LAYER_DISTRIBUTION):
        raise P176ContractError("p176_layer_family_distribution_invalid")
    if denominators["severity_counts"] != {"P0": 40, "P1": 120, "P2": 240, "P3": 80}:
        raise P176ContractError("p176_severity_distribution_invalid")
    if denominators["traffic_shape_counts"] != {shape: 160 for shape in TRAFFIC_SHAPES}:
        raise P176ContractError("p176_traffic_shape_distribution_invalid")
    if any(count != 60 for count in denominators["service_episode_counts"].values()):
        raise P176ContractError("p176_service_distribution_invalid")
    if denominators["cross_service_pair_class_counts"] != {pair_class: 30 for pair_class in CROSS_SERVICE_PAIR_CLASSES}:
        raise P176ContractError("p176_pair_class_distribution_invalid")
    if denominators["healthy_windows_by_telemetry_class"] != {telemetry_class: 30 for telemetry_class in TELEMETRY_CLASSES}:
        raise P176ContractError("p176_healthy_window_distribution_invalid")


__all__ = [
    "CORE_FAMILY_LAYER_DISTRIBUTION",
    "CROSS_SERVICE_PAIR_CLASSES",
    "P176_CAMPAIGN_ID",
    "P176_CAMPAIGN_SEED",
    "PRIMARY_LAYERS",
    "SERVICES",
    "SEVERITIES",
    "TELEMETRY_CLASSES",
    "TRAFFIC_SHAPES",
    "generate_p176_campaign",
    "validate_p176_campaign",
]
