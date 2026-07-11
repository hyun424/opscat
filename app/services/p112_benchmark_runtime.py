"""Shared deterministic construction for P112 freeze and benchmark scripts."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from app.services.p110_candidate_runner import P110RunnerConfig, build_p110_candidate_packet
from app.services.p110_evaluation import stable_hash
from app.services.p111_fault_prior import train_fault_prior
from app.services.p111_multistage_rca import (
    P111_PROMPT_SCHEMA_VERSION,
    P111_SYSTEM_PROMPT,
    build_evidence_digest,
    build_p111_packet,
)
from app.services.p112_cross_system_model import train_cross_system_model
from app.services.p112_multistage_rca import PROMPT_SCHEMA_VERSION, SYSTEM_PROMPT, build_p112_packet
from app.services.p112_re1_loader import P112RE1Case, load_pinned_re1_cases

MODEL = "nvidia/nemotron-3-ultra-550b-a55b"
ENDPOINT = "https://integrate.api.nvidia.com/v1"
PROVIDER_API = "openai-chat-completions-v1"
DECODING = {
    "temperature": 1.0,
    "top_p": 0.95,
    "max_tokens": 16384,
    "reasoning_budget": 16384,
    "enable_thinking": True,
    "provider_endpoint": ENDPOINT,
    "provider_api": PROVIDER_API,
    "stream": True,
}
ACCEPTANCE_GATES = {
    "service_top1_min": 0.84,
    "service_top3_min": 0.92,
    "fault_accuracy_min": 0.84,
    "loss_accuracy_min": 0.60,
    "delay_accuracy_min": 0.60,
    "evidence_precision_min": 0.95,
    "joint_repeat_agreement_min": 0.90,
    "nonnegative_service_top1_delta": True,
    "nonnegative_fault_accuracy_delta": True,
    "one_strictly_positive_primary_delta": True,
    "zero_safety_counters": True,
    "cryptographic_review_required": True,
}
SS_HASH = "sha256:b4424b0b3863b7397712caa0f305ef59964b03784dfcb23e23e0a95a2e746f99"
OB_HASH = "sha256:4a709297e0a829f0f2ee8a7792a6d74da32d663c600565b7fffc860963b840c4"


def load_p112_corpora(root: Path) -> tuple[tuple[P112RE1Case, ...], tuple[P112RE1Case, ...]]:
    key = (root / "evals/real_datasets/external/p110/raw/.p110-case-id-key").read_bytes()
    ss = load_pinned_re1_cases(
        root / "evals/real_datasets/external/p112/raw/RE1-SS.zip",
        root / "evals/real_datasets/external/p112/source-manifest-re1-ss.json",
        hmac_key=key,
    )
    ob = load_pinned_re1_cases(
        root / "evals/real_datasets/external/p110/raw/RE1-OB.zip",
        root / "evals/real_datasets/external/p112/source-manifest-re1-ob.json",
        hmac_key=key,
    )
    return ss, ob


def train_final_p112_model(ss: Sequence[P112RE1Case], ob: Sequence[P112RE1Case]) -> dict[str, Any]:
    samples = [
        (case.to_candidate_packet(), case.scorer_only_truth)
        for case in (*ss, *ob)
        if int(case.scorer_only_truth["repetition"]) in {1, 2, 3}
    ]
    return train_cross_system_model(
        samples,
        training_source_hash=stable_hash([SS_HASH, OB_HASH]),
        training_repetitions=(1, 2, 3),
        pair_weight=1.0,
    )


def train_p111_baseline_prior(ob: Sequence[P112RE1Case]) -> dict[str, Any]:
    samples = []
    for case in ob:
        if int(case.scorer_only_truth["repetition"]) not in {1, 2, 3}:
            continue
        packet = build_p110_candidate_packet(to_p110_source_packet(case.to_candidate_packet()))
        samples.append((build_evidence_digest(packet), case.scorer_only_truth))
    return train_fault_prior(samples, training_repetitions=(1, 2, 3))


def to_p110_source_packet(packet: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "p110.rcaeval_candidate_packet.v1",
        "case_id": str(packet["case_id"]),
        "system": str(packet.get("system", "")),
        "injection_timestamp": packet.get("injection_timestamp"),
        "service_catalog": list(packet.get("service_catalog", [])),
        "metric_catalog": list(packet.get("metric_catalog", [])),
        "evidence": list(packet.get("evidence", [])),
    }


def blind_cases(ob: Sequence[P112RE1Case]) -> list[P112RE1Case]:
    selected = [case for case in ob if int(case.scorer_only_truth["repetition"]) == 4]
    if len(selected) != 25:
        raise ValueError("P112 blind split must contain 25 cases")
    return sorted(selected, key=lambda item: item.case_id)


def full_blind_packets(
    ob: Sequence[P112RE1Case], *, p112_model: Mapping[str, Any], p111_prior: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    baseline = []
    candidate = []
    for case in blind_cases(ob):
        source = case.to_candidate_packet()
        p110 = build_p110_candidate_packet(to_p110_source_packet(source))
        baseline.append(build_p111_packet(p110, fault_prior_artifact=p111_prior))
        candidate.append(build_p112_packet(source, p112_model))
    return baseline, candidate


def baseline_config(*, max_cases: int, max_calls: int) -> P110RunnerConfig:
    return P110RunnerConfig(
        model=MODEL,
        prompt_schema_version=P111_PROMPT_SCHEMA_VERSION,
        decoding_config=DECODING,
        max_cases=max_cases,
        max_calls=max_calls,
    )


def candidate_config(*, max_cases: int, max_calls: int) -> P110RunnerConfig:
    return P110RunnerConfig(
        model=MODEL,
        prompt_schema_version=PROMPT_SCHEMA_VERSION,
        decoding_config=DECODING,
        max_cases=max_cases,
        max_calls=max_calls,
    )


def baseline_request() -> dict[str, Any]:
    return _request(P111_PROMPT_SCHEMA_VERSION, P111_SYSTEM_PROMPT)


def candidate_request() -> dict[str, Any]:
    return _request(PROMPT_SCHEMA_VERSION, SYSTEM_PROMPT)


def implementation_hash(root: Path) -> str:
    paths = (
        "app/services/p110_candidate_runner.py",
        "app/services/p110_evaluation.py",
        "app/services/p111_fault_prior.py",
        "app/services/p111_multistage_rca.py",
        "app/services/p112_re1_loader.py",
        "app/services/p112_cross_system_model.py",
        "app/services/p112_multistage_rca.py",
        "app/services/p112_evaluation.py",
        "app/services/p112_comparison.py",
        "app/services/p112_freeze_guard.py",
        "app/services/p112_benchmark_runtime.py",
        "scripts/freeze_p112_configuration.py",
        "scripts/run_p112_blind_benchmark.py",
        "scripts/merge_p112_blind_batches.py",
        "scripts/build_p112_release_evidence.py",
    )
    return stable_hash({path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in paths})


def _request(prompt_schema_version: str, system_prompt: str) -> dict[str, Any]:
    return {
        "model": MODEL,
        "provider_endpoint": ENDPOINT,
        "provider_api": PROVIDER_API,
        "system_prompt_sha256": hashlib.sha256(system_prompt.encode()).hexdigest(),
        "prompt_schema_version": prompt_schema_version,
        "decoding_config": dict(DECODING),
    }
