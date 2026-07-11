from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from app.services.p112_cross_system_model import train_cross_system_model
from app.services.p113_decoupled_rca import (
    P113Config,
    P113ContractError,
    build_p113_packet,
    replay_p113_raw_response,
    run_p113_decoupled_rca,
)


def _source_packet() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for service in ("checkout", "payments", "cart"):
        rows.append(
            {
                "evidence_id": f"ev-{service}-latency",
                "service": service,
                "metric": "istio-latency-95",
                "statistic": "robust_shift",
                "signed_score": 20.0 if service == "checkout" else 0.2,
            }
        )
        rows.append(
            {
                "evidence_id": f"ev-{service}-disk",
                "service": service,
                "metric": "container-fs-writes-bytes-total",
                "statistic": "robust_shift",
                "signed_score": 25.0 if service == "checkout" else 0.1,
            }
        )
    return {
        "schema_version": "p112.re1_candidate_packet.v1",
        "case_id": "tt-opaque-001",
        "system": "train-ticket",
        "service_catalog": ["checkout", "payments", "cart"],
        "evidence": [],
        "diagnostic_evidence": rows,
    }


def _training_packet(case: int, root: str, fault: str) -> dict[str, Any]:
    rows = []
    metrics = {
        "cpu": "container-cpu-usage-seconds-total",
        "mem": "container-memory-usage-bytes",
        "disk": "container-fs-writes-bytes-total",
        "delay": "istio-latency-95",
        "loss": "container-network-receive-packets-dropped-total",
    }
    for service in ("alpha", "beta", "gamma"):
        rows.append(
            {
                "evidence_id": f"ev-{case}-{service}-latency",
                "service": service,
                "metric": "istio-latency-50",
                "statistic": "robust_rate_shift",
                "signed_score": 0.5,
            }
        )
        rows.append(
            {
                "evidence_id": f"ev-{case}-{service}-fault",
                "service": service,
                "metric": metrics[fault],
                "statistic": "robust_rate_shift",
                "signed_score": 20.0 if service == root else 0.1,
            }
        )
    return {
        "schema_version": "p112.re1_candidate_packet.v1",
        "case_id": f"opaque-{case}",
        "service_catalog": ["alpha", "beta", "gamma"],
        "evidence": [],
        "diagnostic_evidence": rows,
    }


def _model_artifact() -> dict[str, Any]:
    samples = [
        (_training_packet(1, "alpha", "cpu"), {"root_service": "alpha", "fault_type": "cpu"}),
        (_training_packet(2, "beta", "mem"), {"root_service": "beta", "fault_type": "mem"}),
        (_training_packet(3, "gamma", "disk"), {"root_service": "gamma", "fault_type": "disk"}),
        (_training_packet(4, "alpha", "delay"), {"root_service": "alpha", "fault_type": "delay"}),
        (_training_packet(5, "beta", "loss"), {"root_service": "beta", "fault_type": "loss"}),
    ]
    return train_cross_system_model(
        samples,
        training_source_hash="sha256:" + "1" * 64,
        training_repetitions=(1, 2, 3),
    )


class _Provider:
    name = "scripted"
    model_calls_enabled = False

    def __init__(self, output: Mapping[str, Any] | str | Exception) -> None:
        self.output = output

    def diagnose(self, packet: Mapping[str, Any], prompt: str) -> Mapping[str, Any] | str:
        if isinstance(self.output, Exception):
            raise self.output
        return self.output


def test_deterministic_judgment_survives_malformed_oversized_and_provider_errors() -> None:
    packet = build_p113_packet(_source_packet(), _model_artifact())
    config = P113Config(max_response_chars=50)
    outputs: tuple[Mapping[str, Any] | str | Exception, ...] = (
        "not-json",
        {"explanation": "x" * 100, "contradictions": [], "inspection_suggestions": []},
        RuntimeError("provider down"),
    )

    for output in outputs:
        result = run_p113_decoupled_rca(packet, provider=_Provider(output), config=config)

        assert result["diagnosis_status"] == "valid"
        assert result["deterministic_judgment"] == packet["deterministic_judgment"]
        assert result["ranked_services"] == packet["deterministic_judgment"]["ranked_services"]
        assert result["fault_type"] == packet["deterministic_judgment"]["fault_type"]
        assert result["llm_advisory"]["explanation"] == ""
        assert result["llm_advisory"]["inspection_suggestions"] == []
        assert result["action_contract_status"] == "disabled"
        assert result["executed_actions"] == []


def test_valid_narrative_cannot_mutate_top_level_diagnosis_or_enable_actions() -> None:
    packet = build_p113_packet(_source_packet(), _model_artifact())
    provider_output = {
        "explanation": "The provider claims payments is root cause.",
        "contradictions": ["model may be wrong"],
        "inspection_suggestions": ["inspect checkout disk write metrics using ev-checkout-disk"],
        "ranked_services": ["payments"],
        "fault_type": "cpu",
        "actions": ["kubectl delete pod checkout-123"],
    }

    result = run_p113_decoupled_rca(packet, provider=_Provider(provider_output))

    assert result["raw_contract_status"] == "invalid"
    assert result["normalized_contract_status"] == "valid"
    assert "unknown_output_field:actions" in result["llm_advisory"]["validation_errors"]
    assert "unknown_output_field:ranked_services" in result["llm_advisory"]["validation_errors"]
    assert result["deterministic_judgment"] == packet["deterministic_judgment"]
    assert result["ranked_services"] == packet["deterministic_judgment"]["ranked_services"]
    assert result["fault_type"] == packet["deterministic_judgment"]["fault_type"]
    assert result["safety"]["harmful_raw_action_count"] == 1
    assert result["llm_advisory"]["inspection_suggestions"] == [
        "inspect checkout disk write metrics using ev-checkout-disk"
    ]
    assert result["executed_actions"] == []


def test_invalid_raw_actions_are_audited_but_never_exposed_as_executable() -> None:
    packet = build_p113_packet(_source_packet(), _model_artifact())
    provider_output = {
        "explanation": "Run a dangerous command.",
        "contradictions": [],
        "inspection_suggestions": ["kubectl delete pod checkout-123", "inspect checkout metrics using ev-checkout-latency"],
    }

    result = run_p113_decoupled_rca(packet, provider=_Provider(provider_output))

    assert result["raw_contract_status"] == "invalid"
    assert result["normalized_contract_status"] == "invalid"
    assert "unsafe_inspection_suggestion:0" in result["llm_advisory"]["validation_errors"]
    assert result["llm_advisory"]["inspection_suggestions"] == []
    assert result["safety"]["harmful_raw_action_count"] == 2
    assert result["safety"]["executed_action_count"] == 0
    assert result["executed_actions"] == []
    assert result["action_contract_status"] == "disabled"


def test_replay_hashes_are_deterministic_and_bind_packet_model_scores() -> None:
    packet = build_p113_packet(_source_packet(), _model_artifact())
    raw = {
        "explanation": "Disk evidence is strongest.",
        "contradictions": [],
        "inspection_suggestions": ["inspect checkout disk write metrics using ev-checkout-disk"],
    }
    config = P113Config(model="nvidia/test")

    first = replay_p113_raw_response(packet, raw, config=config)
    second = replay_p113_raw_response(packet, raw, config=config)

    assert first["result_hash"] == second["result_hash"]
    assert first["cache_key"] == second["cache_key"]
    assert first["packet_hash"] == packet["packet_hash"]
    assert first["deterministic_judgment"]["model_scores_hash"] == packet["deterministic_judgment"]["model_scores_hash"]
    assert first["raw_response_sha256"] == second["raw_response_sha256"]

    mutated = {**packet, "system_id": "tampered"}
    with pytest.raises(P113ContractError, match="packet_hash_mismatch"):
        replay_p113_raw_response(mutated, raw, config=config)


def test_harmful_text_anywhere_in_narrative_fails_closed_and_is_audited() -> None:
    packet = build_p113_packet(_source_packet(), _model_artifact())
    for raw in (
        {
            "explanation": "kubectl delete pod checkout-123",
            "contradictions": [],
            "inspection_suggestions": [],
        },
        {
            "explanation": "Evidence is mixed.",
            "contradictions": ["restart checkout in production"],
            "inspection_suggestions": [],
        },
    ):
        result = replay_p113_raw_response(packet, raw)
        assert result["raw_contract_status"] == "invalid"
        assert result["normalized_contract_status"] == "invalid"
        assert result["narrative_status"] == "fail_closed"
        assert result["llm_advisory"]["explanation"] == ""
        assert result["safety"]["harmful_raw_action_count"] == 1


def test_inspection_suggestion_requires_known_evidence_and_rejects_mutation_phrases() -> None:
    packet = build_p113_packet(_source_packet(), _model_artifact())
    for suggestion in (
        "query checkout database and update row using ev-checkout-latency",
        "inspect checkout disk write metrics",
        "inspect checkout using ev-unknown",
    ):
        result = replay_p113_raw_response(
            packet,
            {"explanation": "Evidence is mixed.", "contradictions": [], "inspection_suggestions": [suggestion]},
        )
        assert result["normalized_contract_status"] == "invalid"
        assert result["llm_advisory"]["inspection_suggestions"] == []


def test_result_hash_excludes_runtime_latency_but_preserves_latency_telemetry() -> None:
    packet = build_p113_packet(_source_packet(), _model_artifact())
    raw = {
        "explanation": "Disk evidence is strongest.",
        "contradictions": [],
        "inspection_suggestions": ["inspect checkout disk write metrics using ev-checkout-disk"],
    }
    fast = replay_p113_raw_response(packet, raw, latency_ms=1)
    slow = replay_p113_raw_response(packet, raw, latency_ms=999)
    assert fast["latency_ms"] == 1
    assert slow["latency_ms"] == 999
    assert fast["result_hash"] == slow["result_hash"]
