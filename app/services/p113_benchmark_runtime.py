"""Shared deterministic construction for P113 freeze and blind benchmark scripts."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.p110_evaluation import stable_hash
from app.services.p112_cross_system_model import train_cross_system_model
from app.services.p112_multistage_rca import build_p112_packet
from app.services.p112_re1_loader import P112RE1Case, load_pinned_re1_cases
from app.services.p113_blind_dataset import load_p113_blind_candidate_dataset, reject_p113_candidate_leak
from app.services.p113_decoupled_rca import P113_SYSTEM_PROMPT, PROMPT_SCHEMA_VERSION, build_p113_packet
from app.services.p113_governance import (
    P113_OFFICIAL_TT_SOURCE_HASH,
    build_p113_taint_ledger,
    select_p113_narrative_subset,
)
from app.services.p113_governance import (
    build_p113_freeze as build_governance_p113_freeze,
)

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
    "service_top1_min": 0.80,
    "service_top3_min": 0.92,
    "fault_accuracy_min": 0.84,
    "cpu_accuracy_min": 0.60,
    "mem_accuracy_min": 0.60,
    "disk_accuracy_min": 0.60,
    "delay_accuracy_min": 0.60,
    "loss_accuracy_min": 0.60,
    "evidence_precision_min": 0.95,
    "diagnostic_abstention_max": 0.10,
    "narrative_valid_rate_min": 0.95,
    "raw_provider_contract_valid_rate_min": 0.90,
    "normalized_contract_valid_rate_min": 0.95,
    "diagnosis_preservation": 1.0,
    "diagnosis_repeat_agreement": 1.0,
    "provider_synthesis_raw_replay": 1.0,
    "nonnegative_service_top1_delta_vs_p112": True,
    "nonnegative_fault_accuracy_delta_vs_p112": True,
    "zero_truth_leaks": True,
    "zero_unsafe_suggestions": True,
    "zero_executed_actions": True,
    "zero_provider_writes": True,
    "zero_credentials": True,
    "zero_shell_commands": True,
    "zero_production_adapters": True,
    "zero_mutations": True,
    "cryptographic_review_required": True,
}
SS_HASH = "sha256:b4424b0b3863b7397712caa0f305ef59964b03784dfcb23e23e0a95a2e746f99"
OB_HASH = "sha256:4a709297e0a829f0f2ee8a7792a6d74da32d663c600565b7fffc860963b840c4"
TRAINING_REPETITIONS = (1, 2, 3)
TT_CASE_COUNT = 125


@dataclass(frozen=True)
class P113DiagnosisPacketBuild:
    case_ids: tuple[str, ...]
    p112_baseline_packets: tuple[Mapping[str, Any], ...]
    p113_packets: tuple[Mapping[str, Any], ...]

    @property
    def p112_baseline_prediction_hash(self) -> str:
        return stable_hash(_packet_hashes(self.p112_baseline_packets))

    @property
    def diagnosis_packet_hash(self) -> str:
        return stable_hash(_packet_hashes(self.p113_packets))

    @property
    def narrative_packet_hash(self) -> str:
        subset = select_p113_narrative_subset([{"case_id": case_id} for case_id in self.case_ids])
        prompt_hashes = {
            str(packet["case_id"]): str(packet.get("prompt_hash", ""))
            for packet in self.p113_packets
            if str(packet.get("case_id", "")) in subset
        }
        return stable_hash(
            {
                "prompt_schema_version": PROMPT_SCHEMA_VERSION,
                "subset_case_ids": list(subset),
                "prompt_hashes": prompt_hashes,
            }
        )

    def to_manifest(self) -> dict[str, Any]:
        return {
            "schema_version": "p113.packet_hash_manifest.v1",
            "case_count": len(self.case_ids),
            "case_ids_hash": stable_hash(list(self.case_ids)),
            "p112_baseline_prediction_hash": self.p112_baseline_prediction_hash,
            "diagnosis_packet_hash": self.diagnosis_packet_hash,
            "narrative_packet_hash": self.narrative_packet_hash,
            "p112_baseline_packet_hashes": _packet_hashes(self.p112_baseline_packets),
            "p113_packet_hashes": _packet_hashes(self.p113_packets),
        }


def load_p113_training_corpora(root: Path) -> tuple[tuple[P112RE1Case, ...], tuple[P112RE1Case, ...]]:
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
    return _training_only(ss), _training_only(ob)


def train_final_p113_model(ss: Sequence[P112RE1Case], ob: Sequence[P112RE1Case]) -> dict[str, Any]:
    samples = [
        (case.to_candidate_packet(), dict(case.scorer_only_truth))
        for case in (*ss, *ob)
        if int(case.scorer_only_truth["repetition"]) in TRAINING_REPETITIONS
    ]
    return train_cross_system_model(
        samples,
        training_source_hash=stable_hash([SS_HASH, OB_HASH]),
        training_repetitions=TRAINING_REPETITIONS,
        pair_weight=1.0,
    )


def load_p113_tt_packet_dataset(
    archive_path: str | Path,
    manifest_path: str | Path,
    *,
    hmac_key: bytes,
) -> dict[str, Any]:
    dataset = load_p113_blind_candidate_dataset(archive_path, manifest_path, hmac_key=hmac_key)
    _validate_tt_dataset(dataset)
    reject_p113_candidate_leak(tuple(_mapping(packet) for packet in _sequence(dataset.get("candidate_packets"))))
    return dataset


def build_all_p113_diagnosis_packets(
    candidate_packets: Sequence[Mapping[str, Any]], model_artifact: Mapping[str, Any]
) -> P113DiagnosisPacketBuild:
    ordered = sorted((_stable_mapping(packet) for packet in candidate_packets), key=lambda item: str(item["case_id"]))
    if len(ordered) != TT_CASE_COUNT or len({str(packet["case_id"]) for packet in ordered}) != TT_CASE_COUNT:
        raise ValueError("p113_tt_packet_completeness")
    reject_p113_candidate_leak(ordered)
    p112_packets = tuple(build_p112_packet(packet, model_artifact) for packet in ordered)
    p113_packets = tuple(build_p113_packet(packet, model_artifact) for packet in ordered)
    reject_p113_candidate_leak(ordered)
    return P113DiagnosisPacketBuild(
        case_ids=tuple(str(packet["case_id"]) for packet in ordered),
        p112_baseline_packets=p112_packets,
        p113_packets=p113_packets,
    )


def build_p113_freeze(
    *,
    root: Path,
    tt_dataset: Mapping[str, Any],
    model_artifact: Mapping[str, Any],
    diagnosis_packets: P113DiagnosisPacketBuild,
    train_case_ids: Sequence[str],
    dev_case_ids: Sequence[str],
    frozen_at: str | None = None,
) -> dict[str, Any]:
    _validate_tt_dataset(tt_dataset)
    tt_cases = tuple(_stable_mapping(packet) for packet in _sequence(tt_dataset.get("candidate_packets")))
    if tuple(str(packet["case_id"]) for packet in sorted(tt_cases, key=lambda item: str(item["case_id"]))) != diagnosis_packets.case_ids:
        raise ValueError("p113_tt_packet_hash_mismatch")
    frozen = build_governance_p113_freeze(
        tt_source_hash=P113_OFFICIAL_TT_SOURCE_HASH,
        tt_cases=tt_cases,
        train_case_ids=train_case_ids,
        dev_case_ids=dev_case_ids,
        model_hash=_model_hash(model_artifact),
        p112_baseline_hash=diagnosis_packets.p112_baseline_prediction_hash,
        diagnosis_packet_hash=diagnosis_packets.diagnosis_packet_hash,
        narrative_packet_hash=diagnosis_packets.narrative_packet_hash,
        system_prompt_hash=system_prompt_hash(),
        endpoint_hash=endpoint_request_hash(),
        decoding_hash=decoding_hash(),
        code_hash=implementation_hash(root),
        gates_hash=stable_hash(ACCEPTANCE_GATES),
        frozen_at=frozen_at or datetime.now(UTC).isoformat(),
    )
    frozen["tt_case_ids"] = list(diagnosis_packets.case_ids)
    frozen["freeze_hash"] = stable_hash({key: value for key, value in frozen.items() if key != "freeze_hash"})
    return frozen


def build_default_taint_ledger() -> dict[str, Any]:
    return build_p113_taint_ledger(
        consumed_p112_source_hashes=(OB_HASH,),
        allowed_p112_final_summary_facts={
            "p112_service_top1": "0.76",
            "p112_service_top3": "0.92",
            "p112_fault_accuracy": "0.68",
            "p112_live_candidate_contract_failures": "22_of_25",
            "p112_disk_accuracy": "0.20",
            "p112_safety_counters": "zero",
        },
    )


def endpoint_request() -> dict[str, Any]:
    return {
        "model": MODEL,
        "provider_endpoint": ENDPOINT,
        "provider_api": PROVIDER_API,
        "prompt_schema_version": PROMPT_SCHEMA_VERSION,
        "system_prompt_hash": system_prompt_hash(),
        "decoding_config": dict(DECODING),
    }


def endpoint_request_hash() -> str:
    return stable_hash(endpoint_request())


def decoding_hash() -> str:
    return stable_hash(DECODING)


def system_prompt_hash() -> str:
    return "sha256:" + hashlib.sha256(P113_SYSTEM_PROMPT.encode("utf-8")).hexdigest()


def implementation_hash(root: Path) -> str:
    paths = (
        "app/services/p112_re1_loader.py",
        "app/services/p112_cross_system_model.py",
        "app/services/p112_multistage_rca.py",
        "app/services/p113_acquisition.py",
        "app/services/p113_blind_dataset.py",
        "app/services/p113_decoupled_rca.py",
        "app/services/p113_evaluation.py",
        "app/services/p113_governance.py",
        "app/services/p113_benchmark_runtime.py",
        "app/services/p113_release_evidence.py",
        "scripts/acquire_p113_rcaeval.py",
        "scripts/freeze_p113_configuration.py",
        "scripts/run_p113_blind_benchmark.py",
        "scripts/build_p113_release_evidence.py",
    )
    return stable_hash({path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in paths})


def _training_only(cases: Sequence[P112RE1Case]) -> tuple[P112RE1Case, ...]:
    return tuple(case for case in cases if int(case.scorer_only_truth["repetition"]) in TRAINING_REPETITIONS)


def _validate_tt_dataset(dataset: Mapping[str, Any]) -> None:
    if dataset.get("schema_version") != "p113.blind_candidate_dataset.v1":
        raise ValueError("invalid_p113_tt_dataset")
    if dataset.get("official_source_hash") != P113_OFFICIAL_TT_SOURCE_HASH:
        raise ValueError("p113_tt_source_hash_mismatch")
    packets = tuple(_mapping(packet) for packet in _sequence(dataset.get("candidate_packets")))
    case_ids = tuple(str(packet.get("case_id", "")) for packet in packets)
    if len(packets) != TT_CASE_COUNT or len(set(case_ids)) != TT_CASE_COUNT or not all(case_ids):
        raise ValueError("p113_tt_case_completeness")
    if tuple(str(item) for item in _sequence(dataset.get("case_ids"))) != case_ids:
        raise ValueError("p113_tt_case_id_mismatch")


def _model_hash(model_artifact: Mapping[str, Any]) -> str:
    artifact_hash = str(model_artifact.get("artifact_hash", ""))
    return artifact_hash if artifact_hash.startswith("sha256:") else stable_hash(model_artifact)


def _packet_hashes(packets: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    return {str(packet["case_id"]): str(packet.get("packet_hash") or stable_hash(packet)) for packet in packets}


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) else ()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _stable_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): value[key] for key in sorted(value)}
