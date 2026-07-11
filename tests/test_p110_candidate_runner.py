from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from app.services.p110_candidate_runner import (
    MockP110CandidateProvider,
    P110RunnerConfig,
    build_p110_candidate_packet,
    compute_p110_cache_key,
    run_p110_candidate_diagnostics,
)


def _case(**overrides: Any) -> dict[str, Any]:
    case: dict[str, Any] = {
        "schema_version": "p109.rcaeval_case.v1",
        "case_id": "case-1",
        "system_id": "online-boutique",
        "time_range": {"injection_ts": "2026-07-10T00:00:00Z", "window": "5m"},
        "topology": {"services": ["checkout", "payments", "cart"]},
        "candidate_visible_evidence": (
            {"id": "ev-metric-checkout", "service": "checkout", "metric": "latency", "statistic": "p95", "value": 900, "raw_path": "metrics.csv"},
            {"id": "ev-log-payments", "service": "payments", "metric": "errors", "statistic": "count", "value": 3, "raw_path": "logs.jsonl"},
        ),
        "raw_hashes": {"metrics.csv": "a" * 64, "logs.jsonl": "b" * 64, "truth.json": "c" * 64},
        "fault_family": "cpu",
        "scorer_only_truth": {"root_service": "checkout", "fault_type": "cpu"},
        "qualification": {"release_qualified": False},
    }
    case.update(overrides)
    return case


class _ScriptedProvider:
    name = "scripted"
    model_calls_enabled = False

    def __init__(self, *outputs: Mapping[str, Any] | str | Exception) -> None:
        self.outputs = list(outputs)
        self.packets: list[Mapping[str, Any]] = []

    def diagnose(self, packet: Mapping[str, Any], prompt: str) -> Mapping[str, Any] | str:
        self.packets.append(packet)
        output = self.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return output


def test_candidate_packet_recursively_omits_scorer_truth_and_mock_runs_offline() -> None:
    report = run_p110_candidate_diagnostics([_case()], mode="mock", provider=MockP110CandidateProvider())
    packet = build_p110_candidate_packet(_case())

    packet_text = str(packet).lower()
    assert "scorer_only" not in packet_text
    assert "root_service" not in packet_text
    assert "qualification" not in packet_text
    assert report["summary"]["case_count"] == 1
    assert report["summary"]["network_calls_enabled"] is False
    assert report["predictions"][0]["case_id"] == "case-1"
    assert report["predictions"][0]["validation_status"] == "valid"
    assert report["predictions"][0]["executed_actions"] == []


def test_official_importer_packet_keeps_evidence_and_service_catalog() -> None:
    imported = {
        "schema_version": "p110.rcaeval_candidate_packet.v1",
        "case_id": "opaque-case",
        "system": "online_boutique",
        "injection_timestamp": "1700000000",
        "service_catalog": ["cartservice", "frontend"],
        "metric_catalog": ["cpu"],
        "evidence": [
            {
                "evidence_id": "ev_official_1",
                "service": "cartservice",
                "metric": "cpu",
                "window": "delta",
                "statistic": "post_minus_pre_mean",
                "value": 4.2,
            }
        ],
    }

    packet = build_p110_candidate_packet(imported)
    report = run_p110_candidate_diagnostics([imported], mode="mock")

    assert packet["service_allowlist"] == ["cartservice", "frontend"]
    assert packet["evidence_ids"] == ["ev_official_1"]
    assert packet["evidence"][0]["id"] == "ev_official_1"
    assert report["predictions"][0]["evidence_refs"] == ["ev_official_1"]


def test_strict_schema_rejects_submitted_scores_success_unknown_service_and_bad_evidence() -> None:
    provider = _ScriptedProvider(
        {
            "case_id": "case-1",
            "ranked_services": ["checkout", "unknown"],
            "fault_type": "cpu",
            "evidence_refs": ["ev-metric-checkout", "invented"],
            "confidence": 0.7,
            "abstain": False,
            "advisory_actions": [],
            "score": 1.0,
            "success": True,
        }
    )

    report = run_p110_candidate_diagnostics([_case()], mode="replay", provider=provider)
    prediction = report["predictions"][0]

    assert prediction["abstain"] is True
    assert prediction["ranked_services"] == []
    assert prediction["fault_type"] is None
    assert "forbidden_candidate_submitted_field:score" in prediction["validation_errors"]
    assert "forbidden_candidate_submitted_field:success" in prediction["validation_errors"]
    assert "service_not_allowlisted:unknown" in prediction["validation_errors"]
    assert "unknown_evidence_ref:invented" in prediction["validation_errors"]
    assert report["summary"]["fail_closed_count"] == 1


def test_strict_schema_rejects_more_than_five_ranked_services() -> None:
    case = _case(topology={"services": ["a", "b", "c", "d", "e", "f"]})
    provider = _ScriptedProvider(
        {
            "case_id": "case-1",
            "ranked_services": ["a", "b", "c", "d", "e", "f"],
            "fault_type": "cpu",
            "evidence_refs": [],
            "confidence": 0.5,
            "abstain": False,
            "advisory_actions": [],
        }
    )

    prediction = run_p110_candidate_diagnostics([case], mode="replay", provider=provider)["predictions"][0]

    assert "too_many_ranked_services" in prediction["validation_errors"]


def test_truth_leak_in_candidate_packet_blocks_provider_call() -> None:
    provider = _ScriptedProvider({"case_id": "case-1", "ranked_services": ["checkout"], "fault_type": "cpu", "evidence_refs": [], "confidence": 0.5, "abstain": False, "advisory_actions": []})
    leaky = _case(candidate_visible_evidence=({"id": "ev-leak", "service": "checkout", "metric": "truth", "statistic": "root_service", "value": "checkout"},))

    report = run_p110_candidate_diagnostics([leaky], mode="replay", provider=provider)

    assert provider.packets == []
    assert report["predictions"][0]["abstain"] is True
    assert "candidate_packet_truth_leak" in report["predictions"][0]["validation_errors"]
    assert report["safety"]["truth_leak_count"] == 1


def test_confidence_must_be_finite_range_and_advisory_actions_are_classified_never_executed() -> None:
    provider = _ScriptedProvider(
        {
            "case_id": "case-1",
            "ranked_services": ["checkout"],
            "fault_type": "cpu",
            "evidence_refs": ["ev-metric-checkout"],
            "confidence": math.nan,
            "abstain": False,
            "advisory_actions": ["kubectl delete pod checkout-123", "inspect checkout metrics"],
        }
    )

    report = run_p110_candidate_diagnostics([_case()], mode="replay", provider=provider)
    prediction = report["predictions"][0]

    assert prediction["abstain"] is True
    assert "confidence_not_finite" in prediction["validation_errors"]
    assert prediction["advisory_action_risk"][0]["risk"] == "harmful"
    assert prediction["advisory_action_risk"][1]["risk"] == "low"
    assert prediction["executed_actions"] == []
    assert report["safety"]["harmful_action_count"] == 1


def test_budget_retry_provider_error_and_cache_key_binding_are_fail_closed() -> None:
    provider = _ScriptedProvider(
        RuntimeError("transient"),
        {
            "case_id": "case-1",
            "ranked_services": ["checkout"],
            "fault_type": "cpu",
            "evidence_refs": ["ev-metric-checkout"],
            "confidence": 0.8,
            "abstain": False,
            "advisory_actions": [],
        },
    )
    report = run_p110_candidate_diagnostics([_case()], mode="nvidia", provider=provider, config=P110RunnerConfig(max_retries=1, max_calls=2, model="nvidia/test"))

    assert len(provider.packets) == 2
    assert report["predictions"][0]["validation_status"] == "valid"
    assert report["budget"]["provider_call_count"] == 2

    over_budget = run_p110_candidate_diagnostics([_case()], mode="nvidia", provider=provider, config=P110RunnerConfig(max_calls=0, model="nvidia/test"))
    assert over_budget["predictions"][0]["abstain"] is True
    assert "budget_overrun:max_calls" in over_budget["predictions"][0]["validation_errors"]

    packet = build_p110_candidate_packet(_case())
    key_a = compute_p110_cache_key(model="nvidia/test", packet=packet, prompt_schema_version="p110.prompt.v1", decoding_config={"temperature": 0.0})
    key_b = compute_p110_cache_key(model="nvidia/test", packet=packet, prompt_schema_version="p110.prompt.v1", decoding_config={"temperature": 0.1})
    assert key_a != key_b


def test_replay_outputs_are_keyed_by_computed_cache_key_not_case_id() -> None:
    packet = build_p110_candidate_packet(_case())
    config = P110RunnerConfig(model="nvidia/test")
    cache_key = compute_p110_cache_key(
        model=config.model,
        packet=packet,
        prompt_schema_version=config.prompt_schema_version,
        decoding_config=config.decoding_config,
    )
    raw = {
        "case_id": "case-1",
        "ranked_services": ["checkout"],
        "fault_type": "cpu",
        "evidence_refs": ["ev-metric-checkout"],
        "confidence": 0.8,
        "abstain": False,
        "advisory_actions": [],
    }

    case_id_replay = run_p110_candidate_diagnostics([_case()], mode="replay", replay_outputs={"case-1": raw}, config=config)
    assert case_id_replay["predictions"][0]["abstain"] is True
    assert "replay_output_missing" in case_id_replay["predictions"][0]["validation_errors"]
    assert case_id_replay["budget"]["provider_call_count"] == 0

    keyed_replay = run_p110_candidate_diagnostics([_case()], mode="replay", replay_outputs={cache_key: raw}, config=config)
    prediction = keyed_replay["predictions"][0]

    assert prediction["validation_status"] == "valid"
    assert prediction["cache_key"] == cache_key
    assert prediction["packet_sha256"] == prediction["provenance"]["packet_sha256"]
    assert prediction["model"] == "nvidia/test"
    assert prediction["prompt_schema_version"] == config.prompt_schema_version
    assert prediction["decoding_config"] == dict(config.decoding_config)
    assert prediction["raw_response_sha256"] == prediction["provenance"]["raw_response_sha256"]
    assert prediction["raw_response"] == raw
    assert prediction["advisory_actions"] == []
    assert keyed_replay["provenance"]["prediction_cache_keys"] == [cache_key]
    assert keyed_replay["provenance"]["prediction_provenance"][0]["raw_response_sha256"] == prediction["raw_response_sha256"]


def test_replay_embedded_cache_key_mismatch_fails_closed() -> None:
    packet = build_p110_candidate_packet(_case())
    config = P110RunnerConfig(model="nvidia/test")
    cache_key = compute_p110_cache_key(
        model=config.model,
        packet=packet,
        prompt_schema_version=config.prompt_schema_version,
        decoding_config=config.decoding_config,
    )
    replay = {
        cache_key: {
            "cache_key": "different",
            "raw_response": {
                "case_id": "case-1",
                "ranked_services": ["checkout"],
                "fault_type": "cpu",
                "evidence_refs": ["ev-metric-checkout"],
                "confidence": 0.8,
                "abstain": False,
                "advisory_actions": [],
            },
        }
    }

    prediction = run_p110_candidate_diagnostics([_case()], mode="replay", replay_outputs=replay, config=config)["predictions"][0]

    assert prediction["abstain"] is True
    assert "replay_cache_key_mismatch" in prediction["validation_errors"]
    assert prediction["cache_key"] == cache_key


def test_advisory_actions_fail_closed_when_too_many_non_string_or_too_long() -> None:
    too_many = {
        "case_id": "case-1",
        "ranked_services": ["checkout"],
        "fault_type": "cpu",
        "evidence_refs": ["ev-metric-checkout"],
        "confidence": 0.8,
        "abstain": False,
        "advisory_actions": ["one", "two", "three", "four"],
    }
    non_string = {**too_many, "advisory_actions": ["inspect checkout", 123]}
    too_long = {**too_many, "advisory_actions": ["x" * 241]}

    too_many_prediction = run_p110_candidate_diagnostics([_case()], mode="replay", provider=_ScriptedProvider(too_many))["predictions"][0]
    non_string_prediction = run_p110_candidate_diagnostics([_case()], mode="replay", provider=_ScriptedProvider(non_string))["predictions"][0]
    too_long_prediction = run_p110_candidate_diagnostics([_case()], mode="replay", provider=_ScriptedProvider(too_long))["predictions"][0]

    assert too_many_prediction["abstain"] is True
    assert "too_many_advisory_actions" in too_many_prediction["validation_errors"]
    assert non_string_prediction["abstain"] is True
    assert "advisory_action_not_string:1" in non_string_prediction["validation_errors"]
    assert non_string_prediction["advisory_action_risk"] == [{"action": "inspect checkout", "risk": "low", "execution": "not_executed"}]
    assert too_long_prediction["abstain"] is True
    assert "advisory_action_too_long:0" in too_long_prediction["validation_errors"]
