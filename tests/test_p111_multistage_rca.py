from __future__ import annotations

import json
import math
from typing import Any

import pytest

from app.services.p110_candidate_runner import MockP110CandidateProvider, P110RunnerConfig
from app.services.p111_multistage_rca import (
    P110_OUTPUT_KEYS,
    P111_DIGEST_ALGORITHM_VERSION,
    P111_DIGEST_SCHEMA_VERSION,
    P111_PACKET_SCHEMA_VERSION,
    P111_PROMPT_SCHEMA_VERSION,
    P111MultistageRCAError,
    build_evidence_digest,
    build_p111_packet,
    build_p111_prompt,
    run_p111_candidate_diagnostics,
)


def _p110_packet() -> dict[str, Any]:
    return {
        "schema_version": "p110.rcaeval_candidate_packet.v1",
        "case_id": "p110_case_001",
        "system": "online_boutique",
        "injection_timestamp": "100",
        "service_catalog": ["checkoutservice", "frontend"],
        "metric_catalog": ["cpu", "latency"],
        "evidence": [
            {"evidence_id": "ev_frontend_latency_pre", "service": "frontend", "metric": "latency", "window": "pre", "statistic": "mean", "value": 100.0},
            {"evidence_id": "ev_frontend_latency_post", "service": "frontend", "metric": "latency", "window": "post", "statistic": "mean", "value": 260.0},
            {"evidence_id": "ev_frontend_latency_delta", "service": "frontend", "metric": "latency", "window": "delta", "statistic": "mean", "value": 160.0},
            {"evidence_id": "ev_checkout_latency_pre", "service": "checkoutservice", "metric": "latency", "window": "pre", "statistic": "mean", "value": 50.0},
            {"evidence_id": "ev_checkout_latency_post", "service": "checkoutservice", "metric": "latency", "window": "post", "statistic": "mean", "value": 55.0},
            {"evidence_id": "ev_checkout_latency_delta", "service": "checkoutservice", "metric": "latency", "window": "delta", "statistic": "mean", "value": 5.0},
        ],
    }


def test_p111_packet_is_deterministic_and_embeds_original_p110_packet_unchanged() -> None:
    packet = _p110_packet()

    first = build_p111_packet(packet)
    second = build_p111_packet(json.loads(json.dumps(packet)))

    assert first == second
    assert first["schema_version"] == P111_PACKET_SCHEMA_VERSION
    assert first["digest_schema_version"] == P111_DIGEST_SCHEMA_VERSION
    assert first["prompt_schema_version"] == P111_PROMPT_SCHEMA_VERSION
    assert first["algorithm_version"] == P111_DIGEST_ALGORITHM_VERSION
    assert first["p110_packet"] == packet
    assert first["hashes"]["p110_packet_hash"].startswith("sha256:")
    assert first["packet_hash"].startswith("sha256:")


def test_digest_builds_per_service_metric_values_and_cross_service_magnitude_rank() -> None:
    digest = build_evidence_digest(_p110_packet())
    entries = {(row["service"], row["metric"]): row for row in digest["entries"]}

    frontend = entries[("frontend", "latency")]
    checkout = entries[("checkoutservice", "latency")]
    assert frontend["pre"] == 100.0
    assert frontend["post"] == 260.0
    assert frontend["delta"] == 160.0
    assert frontend["relative_change"] == 1.6
    assert frontend["magnitude_rank"] == 1
    assert frontend["magnitude_percentile"] == 1.0
    assert checkout["magnitude_rank"] == 2
    assert checkout["magnitude_percentile"] == 0.0


def test_digest_relative_change_is_finite_for_zero_and_negative_baselines() -> None:
    packet = _p110_packet()
    packet["evidence"].extend(
        [
            {"evidence_id": "ev_zero_pre", "service": "frontend", "metric": "cpu", "window": "pre", "statistic": "mean", "value": 0.0},
            {"evidence_id": "ev_zero_post", "service": "frontend", "metric": "cpu", "window": "post", "statistic": "mean", "value": 5.0},
            {"evidence_id": "ev_zero_delta", "service": "frontend", "metric": "cpu", "window": "delta", "statistic": "mean", "value": 5.0},
            {"evidence_id": "ev_negative_pre", "service": "checkoutservice", "metric": "cpu", "window": "pre", "statistic": "mean", "value": -2.0},
            {"evidence_id": "ev_negative_post", "service": "checkoutservice", "metric": "cpu", "window": "post", "statistic": "mean", "value": -5.0},
            {"evidence_id": "ev_negative_delta", "service": "checkoutservice", "metric": "cpu", "window": "delta", "statistic": "mean", "value": -3.0},
        ]
    )

    digest = build_evidence_digest(packet)

    for entry in digest["entries"]:
        assert math.isfinite(entry["relative_change"])
        assert math.isfinite(entry["absolute_relative_change"])
    zero = next(entry for entry in digest["entries"] if entry["service"] == "frontend" and entry["metric"] == "cpu")
    negative = next(entry for entry in digest["entries"] if entry["service"] == "checkoutservice" and entry["metric"] == "cpu")
    assert zero["relative_change"] == 5.0
    assert negative["relative_change"] == -1.5


def test_digest_binds_supporting_original_evidence_ids() -> None:
    digest = build_evidence_digest(_p110_packet())
    frontend = next(entry for entry in digest["entries"] if entry["service"] == "frontend")

    assert frontend["evidence_ids"] == ["ev_frontend_latency_pre", "ev_frontend_latency_post", "ev_frontend_latency_delta"]
    assert frontend["window_evidence_ids"] == {
        "pre": "ev_frontend_latency_pre",
        "post": "ev_frontend_latency_post",
        "delta": "ev_frontend_latency_delta",
    }
    assert "ev_frontend_latency_delta" in digest["evidence_ids"]


@pytest.mark.parametrize(
    "leak",
    [
        {"scorer_only_truth": {"root_service": "frontend"}},
        {"source_path": "frontend_delay/3"},
        {"metadata": {"repetition": 3}},
        {"metadata": {"case_directory": "frontend_delay/3"}},
    ],
)
def test_truth_source_path_and_repetition_leaks_are_rejected(leak: dict[str, Any]) -> None:
    packet = _p110_packet()
    packet.update(leak)

    with pytest.raises(P111MultistageRCAError, match="candidate_visible_truth_leak"):
        build_p111_packet(packet)


def test_prompt_is_strict_json_with_exact_p110_output_contract() -> None:
    prompt = build_p111_prompt(_p110_packet())
    payload = json.loads(prompt)

    assert payload["prompt_schema_version"] == P111_PROMPT_SCHEMA_VERSION
    assert payload["required_output_keys"] == list(P110_OUTPUT_KEYS)
    assert set(payload["output_shape"]) == set(P110_OUTPUT_KEYS)
    assert len(payload["output_shape"]["advisory_actions"]) <= 3
    assert payload["service_allowlist"] == ["checkoutservice", "frontend"]
    assert payload["fault_allowlist"] == ["cpu", "mem", "disk", "delay", "loss"]
    rendered = json.dumps(payload, sort_keys=True)
    assert "root_service" not in rendered
    assert "source_path" not in rendered
    assert "repetition" not in rendered


def test_runner_reuses_p110_strict_boundary_with_p111_cache_identity() -> None:
    config = P110RunnerConfig(
        model="mock/p111",
        prompt_schema_version=P111_PROMPT_SCHEMA_VERSION,
        decoding_config={"temperature": 0.0},
        max_cases=1,
        max_calls=1,
    )
    report = run_p111_candidate_diagnostics(
        [_p110_packet()], mode="mock", provider=MockP110CandidateProvider(), config=config
    )

    assert report["schema_version"] == "p111.multistage_rca_report.v1"
    assert report["summary"]["valid_count"] == 1
    assert report["summary"]["action_execution_enabled"] is False
    assert report["predictions"][0]["candidate_context"]["schema_version"] == P111_PACKET_SCHEMA_VERSION
    assert report["predictions"][0]["prompt_schema_version"] == P111_PROMPT_SCHEMA_VERSION
