from __future__ import annotations

import copy
import json

from app.services.p110_candidate_runner import MockP110CandidateProvider, P110RunnerConfig, replay_p110_raw_response
from app.services.p112_cross_system_model import train_cross_system_model
from app.services.p112_multistage_rca import (
    PROMPT_SCHEMA_VERSION,
    build_p112_packet,
    build_p112_prompt,
    run_p112_candidate_diagnostics,
)


def _packet(case_id: str, root: str, fault: str) -> dict:
    metrics = {
        "cpu": "container-cpu-usage-seconds-total",
        "mem": "container-memory-usage-bytes",
        "disk": "container-fs-reads-bytes-total",
        "delay": "istio-latency-95",
        "loss": "container-network-receive-packets-dropped-total",
    }
    evidence = []
    diagnostics = []
    for service in ("alpha", "beta", "gamma"):
        evidence.append(
            {
                "evidence_id": f"ev-{case_id}-{service}",
                "service": service,
                "metric": metrics[fault],
                "window": "delta",
                "statistic": "post_minus_pre_mean",
                "value": 10 if service == root else 1,
                "sample_count": 4,
                "source_binding": {"raw_sha256": "1" * 64, "raw_path_token": "metric_source"},
            }
        )
        diagnostics.extend(
            [
                {
                    "evidence_id": f"dev-{case_id}-{service}-istio",
                    "service": service,
                    "metric": "istio-latency-50",
                    "statistic": "robust_post_shift",
                    "signed_score": 1.0,
                    "absolute_score": 1.0,
                },
                {
                    "evidence_id": f"dev-{case_id}-{service}-fault",
                    "service": service,
                    "metric": metrics[fault],
                    "statistic": "robust_rate_shift",
                    "signed_score": 20.0 if service == root else 0.5,
                    "absolute_score": 20.0 if service == root else 0.5,
                },
            ]
        )
    return {
        "schema_version": "p112.re1_candidate_packet.v1",
        "case_id": case_id,
        "system": "synthetic",
        "service_catalog": ["alpha", "beta", "gamma"],
        "metric_catalog": list(metrics.values()),
        "evidence": evidence,
        "diagnostic_evidence": diagnostics,
    }


def _artifact() -> dict:
    training = []
    for index, fault in enumerate(("cpu", "mem", "disk", "delay", "loss")):
        root = ("alpha", "beta", "gamma")[index % 3]
        training.append((_packet(f"train-{index}", root, fault), {"root_service": root, "fault_type": fault}))
    return train_cross_system_model(
        training,
        training_source_hash="sha256:" + "2" * 64,
        training_repetitions=(1, 2, 3),
    )


def test_packet_is_bounded_and_prompt_is_strict() -> None:
    packet = build_p112_packet(_packet("case-1", "beta", "loss"), _artifact())
    prompt = json.loads(build_p112_prompt(packet))
    assert packet["model_scores"]["ranked_services"][0] == "beta"
    assert packet["model_scores"]["ranked_faults"][0] == "loss"
    assert len(packet["diagnostic_evidence"]) <= 40
    assert len(packet["evidence"]) <= 60
    assert prompt["prompt_schema_version"] == PROMPT_SCHEMA_VERSION
    rendered = json.dumps(packet, sort_keys=True)
    assert "root_service" not in rendered
    assert "fault_type" not in rendered


def test_runner_preserves_provider_and_synthesis_replay() -> None:
    source = _packet("case-1", "beta", "loss")
    config = P110RunnerConfig(
        model="mock/p112",
        prompt_schema_version=PROMPT_SCHEMA_VERSION,
        decoding_config={"temperature": 0.0, "top_p": 1.0, "max_tokens": 2048},
        max_cases=1,
        max_calls=1,
    )
    report = run_p112_candidate_diagnostics(
        [source],
        mode="mock",
        provider=MockP110CandidateProvider(),
        config=config,
        model_artifact=_artifact(),
    )
    prediction = report["predictions"][0]
    assert prediction["ranked_services"][0] == "beta"
    assert prediction["fault_type"] == "loss"
    assert prediction["provider_stage"]["raw_response"]
    replayed = replay_p110_raw_response(prediction["candidate_context"], prediction["raw_response"], config=config)
    assert replayed["ranked_services"] == prediction["ranked_services"]


def test_packet_hash_changes_when_diagnostic_changes() -> None:
    source = _packet("case-1", "beta", "loss")
    original = build_p112_packet(source, _artifact())
    changed = copy.deepcopy(source)
    changed["diagnostic_evidence"][0]["signed_score"] = 99.0
    changed["diagnostic_evidence"][0]["absolute_score"] = 99.0
    assert build_p112_packet(changed, _artifact())["packet_hash"] != original["packet_hash"]
