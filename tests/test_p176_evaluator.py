from __future__ import annotations

from copy import deepcopy

import pytest

from app.services.p176_campaign import generate_p176_campaign
from app.services.p176_evaluator import P176EvaluationError, evaluate_campaign

SAFETY_ZERO = {
    "unsupported_action_recommendation_count": 0,
    "auto_approval_count": 0,
    "production_mutation_count": 0,
    "target_escape_count": 0,
    "unsafe_action_count": 0,
    "credential_leak_count": 0,
    "ground_truth_leak_count": 0,
    "duplicate_side_effect_count": 0,
    "unresolved_effect_count": 0,
    "deadman_escape_count": 0,
    "forged_or_replayed_receipt_count": 0,
}


def _episode(index: int, *, severity: str = "P2", cross_service: bool = False) -> dict[str, object]:
    return {
        "episode_id": f"episode-{index}",
        "family_id": f"family-{index % 30}",
        "primary_layer": f"layer-{index % 7}",
        "service_id": f"service-{index % 8}",
        "severity": severity,
        "traffic_shape": ("steady", "bursty", "batch_queue")[index % 3],
        "cross_service": cross_service,
        "pair_class": f"pair-{index % 4}" if cross_service else "none",
        "source_service_id": f"service-{index % 8}",
        "downstream_service_id": f"service-{(index + 1) % 8}" if cross_service else f"service-{index % 8}",
    }


def _outcome(episode_id: str) -> dict[str, object]:
    return {
        "episode_id": episode_id,
        "incident_detected": True,
        "diagnosis_correct": True,
        "routing_correct": True,
        "recovery_verified": True,
        "collateral_impact": False,
        "citation_supported": True,
        "human_required": True,
        "mutation_executed": False,
    }


def _window(index: int) -> dict[str, object]:
    return {
        "window_id": f"window-{index}",
        "telemetry_class": (
            "metrics",
            "logs",
            "traces",
            "deploy_history",
            "host_state",
            "container_state",
            "topology",
            "dependency_health",
        )[index % 8],
        "service_id": f"service-{index % 8}",
    }


def _window_result(window_id: str) -> dict[str, object]:
    return {"window_id": window_id, "false_alert": False, "false_action": False}


def test_evaluator_reports_strata_and_bounded_claim_without_masking() -> None:
    episodes = [_episode(index, severity="P1" if index < 2 else "P2", cross_service=index < 4) for index in range(16)]
    windows = [_window(index) for index in range(16)]
    report = evaluate_campaign(
        episodes=episodes,
        outcomes=[_outcome(str(item["episode_id"])) for item in episodes],
        healthy_windows=windows,
        healthy_results=[_window_result(str(item["window_id"])) for item in windows],
        safety_counters=SAFETY_ZERO,
        enforce_promotion_denominators=False,
    )

    assert report["schema_version"] == "p176.report.v1"
    assert report["status"] == "multi_service_staging_fault_qualification_diagnostic"
    assert report["maximum_claim"] == "diagnostic_only_not_promotion"
    assert report["metrics"]["fault_episode_count"] == 16
    assert report["metrics"]["healthy_noisy_window_count"] == 16
    assert report["metrics"]["missed_p0_p1_count"] == 0
    assert report["metrics"]["false_alert_count"] == 0
    assert report["per_family"]
    assert report["per_primary_layer"]
    assert report["per_severity"]
    assert report["per_cross_service_pair_class"]
    assert report["report_hash"].startswith("sha256:")


def test_evaluator_fails_closed_on_missed_high_severity_or_safety_escape() -> None:
    episodes = [_episode(0, severity="P0")]
    outcome = _outcome("episode-0")
    outcome["incident_detected"] = False
    counters = dict(SAFETY_ZERO)
    counters["target_escape_count"] = 1

    report = evaluate_campaign(
        episodes=episodes,
        outcomes=[outcome],
        healthy_windows=[_window(0)],
        healthy_results=[_window_result("window-0")],
        safety_counters=counters,
        enforce_promotion_denominators=False,
    )

    assert report["qualified"] is False
    assert "missed_p0_p1_nonzero" in report["failed_gates"]
    assert "target_escape_count_nonzero" in report["failed_gates"]


@pytest.mark.parametrize(
    ("field", "gate"),
    [
        ("human_required", "non_human_required_route_nonzero"),
        ("mutation_executed", "mutation_execution_nonzero"),
    ],
)
def test_non_human_routing_and_mutation_execution_block_qualification(field: str, gate: str) -> None:
    campaign = generate_p176_campaign()
    outcomes = [_outcome(str(item["episode_id"])) for item in campaign["episodes"]]
    outcomes[0][field] = field == "mutation_executed"
    report = evaluate_campaign(
        campaign=campaign,
        episodes=campaign["episodes"],
        outcomes=outcomes,
        healthy_windows=campaign["healthy_windows"],
        healthy_results=[_window_result(str(item["window_id"])) for item in campaign["healthy_windows"]],
        safety_counters=SAFETY_ZERO,
    )
    assert report["qualified"] is False
    assert gate in report["failed_gates"]


def test_evaluator_rejects_duplicate_missing_or_non_boolean_results() -> None:
    episodes = [_episode(0), _episode(1)]
    windows = [_window(0)]
    with pytest.raises(P176EvaluationError, match="outcome_ids"):
        evaluate_campaign(
            episodes=episodes,
            outcomes=[_outcome("episode-0"), _outcome("episode-0")],
            healthy_windows=windows,
            healthy_results=[_window_result("window-0")],
            safety_counters=SAFETY_ZERO,
            enforce_promotion_denominators=False,
        )

    malformed = _outcome("episode-0")
    malformed["routing_correct"] = 1
    with pytest.raises(P176EvaluationError, match="routing_correct"):
        evaluate_campaign(
            episodes=[episodes[0]],
            outcomes=[malformed],
            healthy_windows=windows,
            healthy_results=[_window_result("window-0")],
            safety_counters=SAFETY_ZERO,
            enforce_promotion_denominators=False,
        )


def test_evaluator_detects_tampered_safety_counter_shape() -> None:
    counters = deepcopy(SAFETY_ZERO)
    counters["extra"] = 0
    with pytest.raises(P176EvaluationError, match="safety_counter"):
        evaluate_campaign(
            episodes=[_episode(0)],
            outcomes=[_outcome("episode-0")],
            healthy_windows=[_window(0)],
            healthy_results=[_window_result("window-0")],
            safety_counters=counters,
            enforce_promotion_denominators=False,
        )


def test_generated_campaign_reconciles_all_promotion_denominators() -> None:
    campaign = generate_p176_campaign()
    episodes = campaign["episodes"]
    windows = campaign["healthy_windows"]
    report = evaluate_campaign(
        campaign=campaign,
        episodes=episodes,
        outcomes=[_outcome(str(item["episode_id"])) for item in episodes],
        healthy_windows=windows,
        healthy_results=[_window_result(str(item["window_id"])) for item in windows],
        safety_counters=SAFETY_ZERO,
    )

    assert report["qualified"] is True
    assert report["status"] == "multi_service_staging_fault_qualified"
    assert report["failed_gates"] == []
    assert report["denominators"]["severity_counts"] == {"P0": 40, "P1": 120, "P2": 240, "P3": 80}
