from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from app.services.p176_action_eligibility import ELIGIBLE_ACTION_BY_FAMILY
from app.services.p176_campaign import (
    CORE_FAMILY_LAYER_DISTRIBUTION,
    CROSS_SERVICE_PAIR_CLASSES,
    PRIMARY_LAYERS,
    SERVICES,
    TELEMETRY_CLASSES,
    TRAFFIC_SHAPES,
    generate_p176_campaign,
    generate_p176_sealed_truth,
    validate_p176_campaign,
)

ROOT = Path(__file__).resolve().parents[1]


def test_campaign_topology_catalog_and_episode_denominators_are_exact() -> None:
    campaign = generate_p176_campaign()
    validated = validate_p176_campaign(campaign)
    denominators = validated["denominators"]

    assert denominators["independently_deployable_service_count"] == 8
    assert denominators["criticality_tier_count"] == 3
    assert denominators["ownership_domain_count"] == 3
    assert denominators["dependency_graph_depth"] >= 3
    assert denominators["fan_out_node_count"] >= 2
    assert denominators["fan_in_node_count"] >= 2

    assert denominators["promotion_core_family_count"] == 30
    assert denominators["primary_layer_count"] == 7
    assert [sum(1 for family in validated["fault_families"] if family["primary_layer"] == layer) for layer in PRIMARY_LAYERS] == list(
        CORE_FAMILY_LAYER_DISTRIBUTION
    )

    episodes = validated["episodes"]
    assert len(episodes) == 480
    assert Counter(episode["family_id"] for episode in episodes) == {family["family_id"]: 16 for family in validated["fault_families"]}
    assert Counter(episode["severity"] for episode in episodes) == {"P0": 40, "P1": 120, "P2": 240, "P3": 80}
    assert Counter(episode["traffic_shape"] for episode in episodes) == {shape: 160 for shape in TRAFFIC_SHAPES}
    assert Counter(episode["service_id"] for episode in episodes) == {service["service_id"]: 60 for service in SERVICES}
    assert {
        family["family_id"]
        for family in validated["fault_families"]
        if family["expected_routing"] == "fixed_action_eligible"
    } == set(ELIGIBLE_ACTION_BY_FAMILY)


def test_cross_service_distribution_is_exact_and_truth_payload_is_not_agent_visible() -> None:
    campaign = generate_p176_campaign()
    episodes = campaign["episodes"]
    cross_service = [episode for episode in episodes if episode["cross_service"]]

    assert len(cross_service) == 120
    assert len({episode["family_id"] for episode in cross_service}) == 12
    assert Counter(episode["pair_class"] for episode in cross_service) == {pair_class: 30 for pair_class in CROSS_SERVICE_PAIR_CLASSES}
    assert len({episode["source_service_id"] for episode in cross_service} | {episode["downstream_service_id"] for episode in cross_service}) >= 6
    assert all(episode["source_service_id"] != episode["downstream_service_id"] for episode in cross_service)
    assert all(episode["evaluator_truth_ref_hash"].startswith("sha256:") for episode in episodes)
    assert all("scorer_only_truth" not in episode and "evaluator_truth" not in episode for episode in episodes)
    sealed = generate_p176_sealed_truth(campaign)
    assert sealed["visibility"] == "evaluator_only"
    assert len(sealed["records"]) == 480
    assert {item["truth_hash"] for item in sealed["records"]} == {
        item["evaluator_truth_ref_hash"] for item in episodes
    }


def test_healthy_noisy_windows_are_exactly_balanced_by_telemetry_class_and_json_ready() -> None:
    campaign = generate_p176_campaign()
    windows = campaign["healthy_windows"]

    assert len(windows) == 240
    assert Counter(window["telemetry_class"] for window in windows) == {telemetry_class: 30 for telemetry_class in TELEMETRY_CLASSES}
    assert {type(window["noisy"]) for window in windows} == {bool}
    json.dumps(campaign, sort_keys=True)


def test_tracked_input_manifest_pins_the_deterministic_campaign() -> None:
    campaign = generate_p176_campaign()
    manifest = json.loads((ROOT / "evals/p176/input/manifest.json").read_text(encoding="utf-8"))

    assert manifest["schema_version"] == "p176.input_manifest.v1"
    assert manifest["campaign_hash"] == campaign["campaign_hash"]
    assert manifest["episode_count"] == 480
    assert manifest["healthy_noisy_window_count"] == 240
    assert manifest["truth_payload_policy"] == "evaluator_only_hash_refs"
    sealed = json.loads((ROOT / manifest["sealed_truth_path"]).read_text(encoding="utf-8"))
    assert manifest["sealed_truth_hash"] == sealed["sealed_truth_hash"]
    assert sealed["campaign_hash"] == campaign["campaign_hash"]


def test_denominator_reports_expose_evaluator_consumable_counts() -> None:
    campaign = generate_p176_campaign()
    denominators = campaign["denominators"]

    assert denominators["max_core_family_fault_episode_share"] == 16 / 480
    assert denominators["max_primary_layer_fault_episode_share"] == 80 / 480
    assert denominators["cross_service_fault_episode_share"] == 120 / 480
    assert denominators["min_traffic_shape_fault_episode_share"] == 160 / 480
    assert denominators["min_healthy_windows_per_primary_telemetry_layer"] == 30

    by_layer: dict[str, int] = defaultdict(int)
    for episode in campaign["episodes"]:
        by_layer[episode["primary_layer"]] += 1
    assert by_layer == denominators["fault_episodes_by_primary_layer"]
