"""P112 robust cross-system RCA packet, prompt, and deterministic synthesis."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from app.services.p110_candidate_runner import (
    P110CandidateProvider,
    P110RunnerConfig,
    replay_p110_raw_response,
    run_p110_candidate_diagnostics,
)
from app.services.p112_cross_system_model import score_cross_system_model, stable_hash, validate_model
from app.services.p112_re1_loader import reject_candidate_truth_leak

PACKET_SCHEMA_VERSION = "p112.multistage_rca_packet.v1"
PROMPT_SCHEMA_VERSION = "p112.localization_prompt.v1"
SYSTEM_PROMPT = "You are an evidence-driven incident RCA analyst. Return one strict JSON object only. Never execute actions."
FAULTS = ("cpu", "mem", "disk", "delay", "loss")
OUTPUT_KEYS = ("case_id", "ranked_services", "fault_type", "evidence_refs", "confidence", "abstain", "advisory_actions")


class P112MultistageError(ValueError):
    """Raised when a P112 packet or synthesis violates its contract."""


def build_p112_packet(source_packet: Mapping[str, Any], model_artifact: Mapping[str, Any]) -> dict[str, Any]:
    reject_candidate_truth_leak((source_packet,))
    validate_model(model_artifact)
    scores = score_cross_system_model(source_packet, model_artifact)
    diagnostics = _select_diagnostics(source_packet, scores)
    evidence = _select_base_evidence(source_packet, diagnostics, scores)
    packet: dict[str, Any] = {
        "schema_version": PACKET_SCHEMA_VERSION,
        "case_id": str(source_packet.get("case_id", "")),
        "system_id": str(source_packet.get("system", "")),
        "service_allowlist": list(scores["ranked_services"]),
        "fault_allowlist": list(FAULTS),
        "evidence": evidence,
        "evidence_ids": [str(item["id"]) for item in evidence],
        "diagnostic_evidence": diagnostics,
        "model_scores": {
            "schema_version": scores["schema_version"],
            "artifact_hash": scores["artifact_hash"],
            "ranked_services": scores["ranked_services"],
            "ranked_faults": scores["ranked_faults"],
            "ranked_pairs": scores["ranked_pairs"],
        },
        "hashes": {
            "source_packet_hash": stable_hash(source_packet),
            "model_artifact_hash": str(model_artifact["artifact_hash"]),
        },
    }
    packet["prompt_hash"] = stable_hash({"schema": PROMPT_SCHEMA_VERSION, "prompt": build_p112_prompt(packet)})
    packet["packet_hash"] = stable_hash({key: value for key, value in packet.items() if key != "packet_hash"})
    reject_candidate_truth_leak((packet,))
    return packet


def build_p112_prompt(packet: Mapping[str, Any]) -> str:
    prompt = {
        "prompt_schema_version": PROMPT_SCHEMA_VERSION,
        "task": "analyze the selected raw evidence and robust diagnostics, challenge the ranked model hypotheses, and return an advisory RCA judgment",
        "instructions": [
            "Return one strict JSON object only.",
            f"Return exactly these semantic keys: {', '.join(OUTPUT_KEYS)}.",
            "Use only service_allowlist and fault_allowlist values.",
            "Cite only evidence_ids; diagnostic evidence supports reasoning but is not directly citable.",
            "Distinguish loss from delay: loss needs drop/error/throughput evidence, while delay is latency-dominant without proportional loss evidence.",
            "Treat model_scores as a fallible prior and explicitly inspect contradictory diagnostic evidence.",
            "advisory_actions are read-only inspection suggestions and will never be executed.",
        ],
        "output_shape": {
            "case_id": str(packet.get("case_id", "")),
            "ranked_services": [],
            "fault_type": None,
            "evidence_refs": [],
            "confidence": 0.0,
            "abstain": True,
            "advisory_actions": ["inspect the strongest cited metric without changing the system"],
        },
        "service_allowlist": packet.get("service_allowlist", []),
        "fault_allowlist": list(FAULTS),
        "evidence_ids": packet.get("evidence_ids", []),
        "selected_evidence": packet.get("evidence", []),
        "diagnostic_evidence": packet.get("diagnostic_evidence", []),
        "model_scores": packet.get("model_scores", {}),
    }
    return _dumps(prompt)


def run_p112_candidate_diagnostics(
    cases: Sequence[Mapping[str, Any]],
    *,
    mode: str,
    provider: P110CandidateProvider,
    config: P110RunnerConfig,
    model_artifact: Mapping[str, Any],
    replay_outputs: Mapping[str, Mapping[str, Any] | str] | None = None,
) -> dict[str, Any]:
    if config.prompt_schema_version != PROMPT_SCHEMA_VERSION:
        raise P112MultistageError("p112_prompt_schema_required")
    validate_model(model_artifact)

    report = run_p110_candidate_diagnostics(
        cases,
        mode=mode,
        provider=provider,
        replay_outputs=replay_outputs,
        config=config,
        packet_builder=lambda case: build_p112_packet(case, model_artifact),
        prompt_builder=lambda packet, _config: build_p112_prompt(packet),
    )
    report["schema_version"] = "p112.multistage_rca_report.v1"
    report["provenance"]["model_artifact_hash"] = model_artifact["artifact_hash"]
    report["provenance"]["system_prompt_sha256"] = hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest()
    report["predictions"] = [_synthesize_prediction(item, config=config) for item in report["predictions"]]
    return report


def _synthesize_prediction(prediction: Mapping[str, Any], *, config: P110RunnerConfig) -> dict[str, Any]:
    if prediction.get("validation_status") != "valid":
        return dict(prediction)
    packet = prediction.get("candidate_context")
    raw = prediction.get("raw_response")
    if not isinstance(packet, Mapping) or not isinstance(raw, (Mapping, str)):
        return dict(prediction)
    scores = packet.get("model_scores")
    if not isinstance(scores, Mapping):
        return dict(prediction)
    services = scores.get("ranked_services")
    faults = scores.get("ranked_faults")
    if not isinstance(services, Sequence) or not services or not isinstance(faults, Sequence) or not faults:
        return dict(prediction)
    if isinstance(raw, Mapping):
        data = dict(raw)
    else:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return dict(prediction)
    if not isinstance(data, dict):
        return dict(prediction)
    data["ranked_services"] = [str(item) for item in services[:5]]
    data["fault_type"] = str(faults[0])
    synthesized_raw = _dumps(data)
    synthesized = replay_p110_raw_response(packet, synthesized_raw, config=config)
    synthesized["latency_ms"] = int(prediction.get("latency_ms", 0))
    synthesized["provider_stage"] = {
        "raw_response": raw,
        "raw_response_sha256": prediction.get("raw_response_sha256"),
        "parsed_ranked_services": prediction.get("ranked_services"),
        "parsed_fault_type": prediction.get("fault_type"),
    }
    synthesized["synthesis"] = {
        "schema_version": "p112.deterministic_synthesis.v1",
        "selected_service": str(services[0]),
        "selected_fault": str(faults[0]),
        "ranked_services": [str(item) for item in services[:5]],
        "ranked_faults": [str(item) for item in faults],
        "model_artifact_hash": scores.get("artifact_hash"),
        "response_origin": "deterministic_synthesis",
    }
    return synthesized


def _select_diagnostics(source_packet: Mapping[str, Any], scores: Mapping[str, Any]) -> list[dict[str, Any]]:
    allowed = set(str(item) for item in scores.get("ranked_services", [])[:5])
    rows = [
        dict(item)
        for item in _sequence(source_packet.get("diagnostic_evidence"))
        if isinstance(item, Mapping) and str(item.get("service", "")) in allowed
    ]
    rows.sort(key=lambda item: (-float(item.get("absolute_score", 0.0)), str(item.get("service", "")), str(item.get("metric", ""))))
    return rows[:40]


def _select_base_evidence(
    source_packet: Mapping[str, Any], diagnostics: Sequence[Mapping[str, Any]], scores: Mapping[str, Any]
) -> list[dict[str, Any]]:
    diagnostic_keys = {(str(item.get("service", "")), str(item.get("metric", ""))) for item in diagnostics[:20]}
    allowed = set(str(item) for item in scores.get("ranked_services", [])[:5])
    rows: list[dict[str, Any]] = []
    for item in _sequence(source_packet.get("evidence")):
        if not isinstance(item, Mapping):
            continue
        service = str(item.get("service", ""))
        metric = str(item.get("metric", ""))
        if service not in allowed or (service, metric) not in diagnostic_keys:
            continue
        normalized = dict(item)
        if "id" not in normalized and normalized.get("evidence_id"):
            normalized["id"] = str(normalized.pop("evidence_id"))
        rows.append(normalized)
    rows.sort(key=lambda item: (str(item.get("service", "")), str(item.get("metric", "")), str(item.get("window", ""))))
    return rows[:60]


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) else ()


def _dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str)
