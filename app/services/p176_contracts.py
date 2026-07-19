"""P176 strict contracts for deterministic staging qualification inputs."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from app.services.p110_evaluation import stable_hash

CAMPAIGN_SCHEMA_VERSION = "p176.deterministic_campaign.v1"
EPISODE_SCHEMA_VERSION = "p176.episode_mapping.v1"
HEALTHY_WINDOW_SCHEMA_VERSION = "p176.healthy_noisy_window.v1"

SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")

EPISODE_FIELDS = frozenset(
    {
        "schema_version",
        "episode_id",
        "index",
        "family_id",
        "primary_layer",
        "service_id",
        "severity",
        "traffic_shape",
        "cross_service",
        "pair_class",
        "source_service_id",
        "downstream_service_id",
        "agent_visible_evidence_refs",
        "evaluator_truth_ref_hash",
        "episode_hash",
    }
)
HEALTHY_WINDOW_FIELDS = frozenset(
    {
        "schema_version",
        "window_id",
        "index",
        "telemetry_class",
        "service_id",
        "noisy",
        "window_hash",
    }
)
SERVICE_FIELDS = frozenset({"service_id", "criticality_tier", "ownership_domain", "independently_deployable", "depends_on"})
FAULT_FAMILY_FIELDS = frozenset(
    {
        "family_id",
        "primary_layer",
        "affected_service_ids",
        "precursor_signal_refs",
        "incident_signal_refs",
        "recovery_signal_refs",
        "expected_routing",
        "promotion_core",
        "sealed_label_hash",
    }
)
DENOMINATOR_FIELDS = frozenset(
    {
        "fault_episode_count",
        "promotion_core_family_count",
        "primary_layer_count",
        "core_families_by_primary_layer",
        "fault_episodes_by_primary_layer",
        "severity_counts",
        "traffic_shape_counts",
        "service_episode_counts",
        "cross_service_episode_count",
        "cross_service_family_count",
        "cross_service_pair_class_count",
        "cross_service_pair_class_counts",
        "cross_service_participating_service_count",
        "healthy_noisy_window_count",
        "healthy_windows_by_telemetry_class",
        "independently_deployable_service_count",
        "criticality_tier_count",
        "ownership_domain_count",
        "dependency_graph_depth",
        "fan_out_node_count",
        "fan_in_node_count",
        "min_core_families_per_primary_layer",
        "min_fault_episodes_per_primary_layer",
        "min_episodes_per_cross_service_pair_class",
        "max_core_family_fault_episode_share",
        "max_primary_layer_fault_episode_share",
        "cross_service_fault_episode_share",
        "min_traffic_shape_fault_episode_share",
        "max_service_fault_episode_share",
        "min_healthy_windows_per_primary_telemetry_layer",
    }
)
CAMPAIGN_FIELDS = frozenset(
    {
        "schema_version",
        "campaign_id",
        "seed",
        "topology",
        "fault_families",
        "episodes",
        "healthy_windows",
        "denominators",
        "truth_payload_policy",
        "campaign_hash",
    }
)


class P176ContractError(ValueError):
    """Raised when P176 input contracts fail closed."""


def validate_episode_mapping(raw: Mapping[str, Any]) -> dict[str, Any]:
    episode = _copy_exact(raw, EPISODE_FIELDS, label="episode")
    _require_literal(episode, "schema_version", EPISODE_SCHEMA_VERSION, label="episode")
    for field in (
        "episode_id",
        "family_id",
        "primary_layer",
        "service_id",
        "severity",
        "traffic_shape",
        "pair_class",
        "source_service_id",
        "downstream_service_id",
    ):
        _require_non_empty_str(episode, field, label="episode")
    _require_int(episode, "index", minimum=0, label="episode")
    _require_bool(episode, "cross_service", label="episode")
    refs = episode["agent_visible_evidence_refs"]
    if not isinstance(refs, list) or not refs or any(type(ref) is not str or not ref for ref in refs):
        raise P176ContractError("invalid_episode_refs:agent_visible_evidence_refs")
    _require_hash(episode, "evaluator_truth_ref_hash", label="episode")
    expected_hash = stable_hash({key: value for key, value in episode.items() if key != "episode_hash"})
    if episode["episode_hash"] != expected_hash:
        raise P176ContractError("episode_hash_invalid")
    return episode


def validate_healthy_window(raw: Mapping[str, Any]) -> dict[str, Any]:
    window = _copy_exact(raw, HEALTHY_WINDOW_FIELDS, label="healthy_window")
    _require_literal(window, "schema_version", HEALTHY_WINDOW_SCHEMA_VERSION, label="healthy_window")
    for field in ("window_id", "telemetry_class", "service_id"):
        _require_non_empty_str(window, field, label="healthy_window")
    _require_int(window, "index", minimum=0, label="healthy_window")
    _require_bool(window, "noisy", label="healthy_window")
    expected_hash = stable_hash({key: value for key, value in window.items() if key != "window_hash"})
    if window["window_hash"] != expected_hash:
        raise P176ContractError("healthy_window_hash_invalid")
    return window


def validate_campaign_payload(raw: Mapping[str, Any]) -> dict[str, Any]:
    campaign = _copy_exact(raw, CAMPAIGN_FIELDS, label="campaign")
    _require_literal(campaign, "schema_version", CAMPAIGN_SCHEMA_VERSION, label="campaign")
    _require_non_empty_str(campaign, "campaign_id", label="campaign")
    _require_non_empty_str(campaign, "seed", label="campaign")
    _require_literal(campaign, "truth_payload_policy", "evaluator_only_hash_refs", label="campaign")
    if not isinstance(campaign["topology"], list):
        raise P176ContractError("invalid_campaign_list:topology")
    if not isinstance(campaign["fault_families"], list):
        raise P176ContractError("invalid_campaign_list:fault_families")
    episodes = _require_list(campaign, "episodes", label="campaign")
    windows = _require_list(campaign, "healthy_windows", label="campaign")
    if not isinstance(campaign["denominators"], dict):
        raise P176ContractError("invalid_campaign_denominators")

    seen_episodes: set[str] = set()
    normalized_episodes: list[dict[str, Any]] = []
    for raw_episode in episodes:
        if not isinstance(raw_episode, Mapping):
            raise P176ContractError("invalid_episode_record")
        episode = validate_episode_mapping(raw_episode)
        episode_id = episode["episode_id"]
        if episode_id in seen_episodes:
            raise P176ContractError(f"duplicate_episode_id:{episode_id}")
        seen_episodes.add(episode_id)
        normalized_episodes.append(episode)

    seen_windows: set[str] = set()
    normalized_windows: list[dict[str, Any]] = []
    for raw_window in windows:
        if not isinstance(raw_window, Mapping):
            raise P176ContractError("invalid_healthy_window_record")
        window = validate_healthy_window(raw_window)
        window_id = window["window_id"]
        if window_id in seen_windows:
            raise P176ContractError(f"duplicate_healthy_window_id:{window_id}")
        seen_windows.add(window_id)
        normalized_windows.append(window)

    campaign["episodes"] = normalized_episodes
    campaign["healthy_windows"] = normalized_windows
    expected_hash = stable_hash({key: value for key, value in campaign.items() if key != "campaign_hash"})
    if campaign["campaign_hash"] != expected_hash:
        raise P176ContractError("campaign_hash_invalid")
    return campaign


def _copy_exact(raw: Mapping[str, Any], fields: frozenset[str], *, label: str) -> dict[str, Any]:
    value = deepcopy(dict(raw))
    actual = set(value)
    missing = fields - actual
    if missing:
        raise P176ContractError(f"missing_{label}_field:{sorted(missing)[0]}")
    unexpected = actual - fields
    if unexpected:
        raise P176ContractError(f"unexpected_{label}_field:{sorted(unexpected)[0]}")
    _reject_non_finite(value, label=label)
    return value


def _reject_non_finite(value: Any, *, label: str) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise P176ContractError(f"non_finite_{label}_number")
    if isinstance(value, Mapping):
        for item in value.values():
            _reject_non_finite(item, label=label)
    elif isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        for item in value:
            _reject_non_finite(item, label=label)


def _require_literal(value: Mapping[str, Any], field: str, expected: str, *, label: str) -> None:
    if value.get(field) != expected:
        raise P176ContractError(f"invalid_{label}_literal:{field}")


def _require_non_empty_str(value: Mapping[str, Any], field: str, *, label: str) -> None:
    if type(value.get(field)) is not str or not value[field]:
        raise P176ContractError(f"invalid_{label}_str:{field}")


def _require_int(value: Mapping[str, Any], field: str, *, minimum: int, label: str) -> None:
    item = value.get(field)
    if type(item) is not int or item < minimum:
        raise P176ContractError(f"invalid_{label}_int:{field}")


def _require_bool(value: Mapping[str, Any], field: str, *, label: str) -> None:
    if type(value.get(field)) is not bool:
        raise P176ContractError(f"invalid_{label}_bool:{field}")


def _require_hash(value: Mapping[str, Any], field: str, *, label: str) -> None:
    if type(value.get(field)) is not str or not SHA256_RE.fullmatch(value[field]):
        raise P176ContractError(f"invalid_{label}_hash:{field}")


def _require_list(value: Mapping[str, Any], field: str, *, label: str) -> list[Any]:
    item = value.get(field)
    if not isinstance(item, list):
        raise P176ContractError(f"invalid_{label}_list:{field}")
    return item


__all__ = [
    "CAMPAIGN_FIELDS",
    "CAMPAIGN_SCHEMA_VERSION",
    "DENOMINATOR_FIELDS",
    "EPISODE_FIELDS",
    "EPISODE_SCHEMA_VERSION",
    "FAULT_FAMILY_FIELDS",
    "HEALTHY_WINDOW_FIELDS",
    "HEALTHY_WINDOW_SCHEMA_VERSION",
    "P176ContractError",
    "SERVICE_FIELDS",
    "validate_campaign_payload",
    "validate_episode_mapping",
    "validate_healthy_window",
]
